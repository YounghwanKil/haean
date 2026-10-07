import json
from pathlib import Path
import pytest
from haean import hwp
from haean.retrieval import source_item_id, retrieve
from haean.models import Brief
from haean.planning import blueprint


def test_exam_scoped_source_identity():
    meta = json.dumps({'fields': {'연도': 2025, '문항 번호': 3, '과목': '자료해석', '회차': '2025 추가'}})
    assert source_item_id({'exam': 'leet', 'meta': meta}) == '2025_03'
    assert source_item_id({'exam': 'psat5', 'meta': meta}) != source_item_id({'exam': 'psat7', 'meta': meta})


def test_metadata_is_not_full_question_fewshot():
    class Database:
        def execute(self, *args): return []
    class Corpus:
        db = Database()
        def rows(self, *args): return []
        def search(self, query, exam, limit, roles):
            if 'metadata' not in roles: return []
            return [{'id': 'm1', 'locator': 'sheet:2', 'exam': exam, 'role': 'metadata',
                     'sha': 'a'*64, 'score': 5, 'text': '통계', 'meta': json.dumps({'fields': {
                         '연도': 2026, '문항 번호': 1, '과목': '자료해석', '문항유형': '비율'}})}]
    refs, log = retrieve(Corpus(), Brief(exam='psat7', subject='자료해석', item_type='비율', topic='통계'))
    assert not refs[0]['full_question']
    assert log['full_few_shot_ids'] == []
    assert log['design_metadata_ids'] == ['m1'] and log['missing']


def test_bridge_reserves_one_unproduced_argument_slot():
    class Corpus:
        def rows(self, exam):
            return [{'fields': {'연도': 2025, '과목': '추리논증', '지문': '본문',
                     '내용영역': '규범', '문항유형': '논증 평가', '문항 번호': 1}, 'source_id': 's1'}]
    result = blueprint(Corpus(), 'leet', '추리논증', product='bridge')
    assert result['total'] == len(result['slots']) == 20
    assert sum(result['allocation'].values()) == 19
    assert result['slots'][-1]['state'] == 'reserved'


def test_layout_refuses_mixed_exams_before_writing(tmp_path, draft, brief):
    runs=[]
    for index, b in enumerate([brief.model_dump(), Brief(exam='psat7', subject='자료해석', item_type='비율', topic='통계').model_dump()]):
        run=tmp_path/str(index);run.mkdir();runs.append(run)
        (run/'candidate.json').write_text(draft.model_dump_json())
        (run/'brief.json').write_text(json.dumps(b))
    with pytest.raises(ValueError, match='섞을 수'):
        hwp.fill_template(runs,tmp_path/'template.hwp',tmp_path/'output.hwp','검토')
    assert not (tmp_path/'output.hwp').exists()


def test_layout_refuses_existing_output(tmp_path):
    output=tmp_path/'existing.hwp';output.write_bytes(b'original')
    with pytest.raises(ValueError, match='덮어쓰지'):
        hwp.fill_template([],output,output,'검토')
    assert output.read_bytes()==b'original'


def test_solution_export_preserves_reasoning_without_editorial_history(tmp_path, draft):
    from haean.export import export_review
    draft.items[0].commentary = 'source_ids를 교체했다. brief와 exam_contract의 배정 기록.'
    candidate = tmp_path/'candidate.json'
    candidate.write_text(draft.model_dump_json())
    original = candidate.read_bytes()
    (tmp_path/'status.json').write_text(json.dumps({'state': 'awaiting_human_review'}))
    export_review(tmp_path)
    solution = (tmp_path/'solutions.html').read_text()
    assert draft.items[0].explanation in solution
    assert all(j.explanation in solution for j in draft.items[0].judgments)
    assert 'source_ids' not in solution and 'exam_contract' not in solution
    assert candidate.read_bytes() == original


@pytest.mark.parametrize('page_start,kind', [(1,'questions'), (41,'questions'), (2,'solutions')])
def test_page_start_refuses_invalid_scope_before_export(tmp_path, draft, brief, page_start, kind):
    (tmp_path/'candidate.json').write_text(draft.model_dump_json())
    (tmp_path/'brief.json').write_text(brief.model_dump_json())
    with pytest.raises(ValueError, match='새 쪽 시작'):
        hwp.fill_template([tmp_path],tmp_path/'template.hwp',tmp_path/'out.hwp','검토',kind=kind,page_starts=[page_start])
    assert not (tmp_path/'out.template.json').exists()


def test_page_start_does_not_separate_shared_second_question(tmp_path, draft, brief):
    draft.items[0].shared_passage_id='PAIR'
    second=draft.items[0].model_copy(deep=True);second.id='TEST-002'
    draft.items.append(second)
    (tmp_path/'candidate.json').write_text(draft.model_dump_json())
    (tmp_path/'brief.json').write_text(brief.model_dump_json())
    with pytest.raises(ValueError, match='공통지문'):
        hwp.fill_template([tmp_path],tmp_path/'template.hwp',tmp_path/'out.hwp','검토',page_starts=[2])


@pytest.mark.parametrize('exam_size,start,exam,count', [(25,1,'psat7',1),(25,2,'psat7',25),(25,1,'leet',25),(24,1,'psat7',24),(40,1,'leet',25)])
def test_full_exam_size_rejects_incomplete_or_wrong_exam(tmp_path,draft,brief,exam_size,start,exam,count):
    b=brief.model_dump();b['exam']=exam
    if exam=='psat7':b['subject']='언어논리'
    runs=[]
    for i in range(count):
        run=tmp_path/str(i);run.mkdir();runs.append(run)
        single=draft.model_copy(deep=True)
        single.items=[draft.items[0].model_copy(update={'id':f'TEST-{i:03}'},deep=True)]
        (run/'candidate.json').write_text(single.model_dump_json())
        (run/'brief.json').write_text(json.dumps(b))
    with pytest.raises(ValueError,match='문항|회차'):
        hwp.fill_template(runs,tmp_path/'template.hwp',tmp_path/'out.hwp','검토',start=start,exam_size=exam_size)
    assert not (tmp_path/'out.template.json').exists()
