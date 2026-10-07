import json
import pytest
from haean.full_exam import load_plan, bundles, check_slot, assemble
from haean.validation import validate


def test_whole_exam_report_exposes_balanced_but_repetitive_answers():
    from haean.full_exam import composition_observations
    plan={'slots':[{'number':n,'difficulty':'중'} for n in range(1,41)]}
    items=[{'number':n,'answer':(n-1)%5+1,'difficulty':'중'} for n in range(1,41)]
    items[14]['difficulty']='하'
    report=composition_observations(plan,items)
    assert report['all_five_answers_once_blocks']==8
    assert report['difficulty_mismatches']==[{'number':15,'planned':'중','actual':'하'}]
    # Missing questions must not make later answers shift into an earlier block.
    report=composition_observations(plan,items[1:])
    assert len(report['five_item_blocks'])==7
    assert report['five_item_blocks'][0]['numbers']==[6,7,8,9,10]


def test_full_plan_requires_every_number(tmp_path):
    p=tmp_path/'plan.json'
    p.write_text(json.dumps({'exam':'leet','subject':'추리논증','slots':[]}))
    with pytest.raises(ValueError, match='문항 수'):
        load_plan(p)


def test_mixed_type_shared_pair_stays_together():
    slots=[{'id':'a','number':1,'domain':'사회','item_type':'내용 일치','shared_passage_id':'set1'},
           {'id':'b','number':2,'domain':'사회','item_type':'빈칸 추론','shared_passage_id':'set1'}]
    assert bundles({'slots':slots})==[slots]
    with pytest.raises(ValueError,match='2문항'):
        bundles({'slots':slots[:1]})


def test_exam_assignment_validates_item_identity_and_type(draft,brief):
    assert validate(draft,brief,{'source-1'},[{'id':'TEST-001','item_type':'조건 추론'}]) == []
    assert any('ID' in e for e in validate(draft,brief,{'source-1'},[{'id':'wrong','item_type':'조건 추론'}]))
    assert any('유형' in e for e in validate(draft,brief,{'source-1'},[{'id':'TEST-001','item_type':'다른 유형'}]))


def test_required_graphs_cannot_silently_become_text(draft):
    slot={'number':23,'item_type':'조건 추론','special_design':'argument_structure'}
    assert any('그림 5개' in e for e in check_slot(slot,draft.items[0],'추리논증'))
    slot.pop('special_design'); slot['graph_design']={ 'graph_kind':'line' }
    assert any('그래프 선택지' in e for e in check_slot(slot,draft.items[0],'추리논증'))


def test_assembly_rejects_changed_reviewed_candidate(tmp_path, draft, brief, monkeypatch):
    run=tmp_path/'bundle';run.mkdir()
    (run/'candidate.json').write_text(draft.model_dump_json())
    (run/'brief.json').write_text(brief.model_dump_json())
    (run/'status.json').write_text(json.dumps({'state':'awaiting_human_review','candidate_sha256':'old'}))
    plan={'exam':'leet','subject':'추리논증','slots':[{'id':'TEST-001','number':1,'item_type':'조건 추론'}]}
    (tmp_path/'plan.json').write_text(json.dumps(plan))
    (tmp_path/'production.json').write_text(json.dumps({'jobs':[{'run':str(run),'bundle':1,'ids':['TEST-001']}]}))
    monkeypatch.setattr('haean.full_exam.render_exam',lambda *args:None)
    result=assemble(tmp_path)
    assert not result['ready_for_human_review']
    assert any('해시 불일치' in e for e in result['errors'])


def test_relative_output_assembles_and_exports_in_item_order(tmp_path, draft, brief, monkeypatch):
    import hashlib
    run=tmp_path/'production'/'bundle';run.mkdir(parents=True)
    (run/'candidate.json').write_text(draft.model_dump_json())
    (run/'brief.json').write_text(brief.model_dump_json())
    (run/'status.json').write_text(json.dumps({'state':'awaiting_human_review',
        'candidate_sha256':hashlib.sha256((run/'candidate.json').read_bytes()).hexdigest()}))
    (run.parent/'plan.json').write_text(json.dumps({'exam':'leet','subject':'추리논증',
        'slots':[{'id':'TEST-001','number':1,'item_type':'조건 추론','difficulty':'하','topic':'개별 배정'}]}))
    (run.parent/'production.json').write_text(json.dumps({'jobs':[{'run':str(run),'bundle':1,'ids':['TEST-001']}]}))
    monkeypatch.chdir(tmp_path)
    result=assemble('production')
    assert result['ready_for_human_review']
    assert (run.parent/'questions.html').exists() and (run.parent/'solutions.html').exists()

    item_brief=json.loads((run.parent/'items/01/brief.json').read_text())
    assert item_brief['difficulty']=='하' and item_brief['topic']=='개별 배정'
    assert json.loads((run/'brief.json').read_text())['difficulty']=='중'


def test_shared_layout_requires_same_adjacent_passage(draft):
    from haean.hwp import shared_layout
    a=draft.items[0].model_copy(deep=True);a.shared_passage_id='shared'
    b=a.model_copy(deep=True);b.id='TEST-002'
    pairs=shared_layout([a,b],19)
    assert pairs[19]['first'] and not pairs[20]['first'] and pairs[19]['pair']==[19,20]
    assert shared_layout([a],19)=={}
    b.passage+=' 다른 지문'
    with pytest.raises(ValueError,match='불일치'):shared_layout([a,b])
    b.passage=a.passage
    other=a.model_copy(deep=True);other.shared_passage_id=None
    with pytest.raises(ValueError,match='인접'):shared_layout([a,other,b])


def test_manual_check_uses_each_shared_item_type(tmp_path,draft,brief,monkeypatch):
    from haean.cli import main
    first=draft.items[0];first.shared_passage_id='shared'
    second=first.model_copy(deep=True);second.id='TEST-002';second.item_type='자료 변환'
    draft.items.append(second)
    shared_brief=brief.model_copy(update={'count':2,'shared_passage':True})
    (tmp_path/'context.json').write_text(json.dumps({'brief':shared_brief.model_dump(),
        'references':[{'id':'source-1','text':''}],
        'exam_assignment':[{'id':first.id,'item_type':first.item_type},{'id':second.id,'item_type':second.item_type}]}))
    source=tmp_path/'input.json';source.write_text(draft.model_dump_json())
    monkeypatch.setattr('sys.argv',['haean-tool','check',str(tmp_path),str(source)])
    main()
    status=json.loads((tmp_path/'status.json').read_text())
    assert status['state']=='awaiting_independent_review' and status['errors']==[]
