import json
import pytest
from haean.full_exam import load_plan, bundles, check_slot, assemble
from haean.validation import validate


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
        'slots':[{'id':'TEST-001','number':1,'item_type':'조건 추론'}]}))
    (run.parent/'production.json').write_text(json.dumps({'jobs':[{'run':str(run),'bundle':1,'ids':['TEST-001']}]}))
    monkeypatch.chdir(tmp_path)
    result=assemble('production')
    assert result['ready_for_human_review']
    assert (run.parent/'questions.html').exists() and (run.parent/'solutions.html').exists()
