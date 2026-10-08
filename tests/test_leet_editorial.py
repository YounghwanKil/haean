"""Synthetic integration checks: advisory context reaches writers/editors only."""
import copy
import json

import pytest

from haean.corpus import Corpus
from haean.leet_editorial import editorial_plan, exam_editorial_context
from haean.models import Brief, BlindReview, EditorialReview
from haean.pipeline import prepare, prompt, review_prompt, run_pipeline, save, writer_prompt


def test_prepare_delivers_same_editorial_plan_to_request_and_runtime(tmp_path, brief, draft):
    corpus = Corpus(tmp_path / 'corpus.sqlite')
    corpus.add('example', 'synthetic', 'leet', 'example', '조건 사례',
                        {'fields': {'과목': '추리논증'}})
    run = prepare(corpus, brief, tmp_path / 'runs')
    context = json.loads((run / 'context.json').read_text())
    plan = json.loads((run / 'editorial-plan.json').read_text())
    assert plan == context['editorial_plan']
    request = (run / 'request.md').read_text()
    assert json.loads(request.split('입력 자료(JSON):\n')[1]) == context
    draft.items[0].source_ids = [context['references'][0]['id']]
    before = draft.model_dump()
    calls = []

    class Provider:
        usage = []

        def call(self, stage, instructions, payload, schema):
            calls.append(stage)
            if stage == 'generate':
                assert payload['editorial_plan'] == plan
                assert prompt('leet_editorial') in instructions
                return draft
            if stage == 'blind':
                assert instructions == prompt('blind')
                assert set(payload) == {'items'}
                assert not {'answer', 'judgments', 'design_summary', 'editorial_plan'} & payload['items'][0].keys()
                return BlindReview(solutions=[{'item_id': draft.items[0].id, 'answer': 1,
                    'uniquely_answerable': True, 'option_reasons': ['합성 근거'] * 5,
                    'missing_conditions': []}], issues=[])
            assert stage == 'editor'
            assert payload['editorial_plan'] == plan
            assert prompt('leet_editorial') in instructions
            return EditorialReview(issues=[], summary='합성 검토')

    run_pipeline(run, Provider(), max_revisions=0)
    assert calls == ['generate', 'blind', 'editor']
    assert draft.model_dump() == before  # Production advice never rewrites an item itself.
    assert json.loads((run / 'status.json').read_text())['human_approved'] is False


@pytest.mark.parametrize('exam', ['psat5', 'psat7'])
@pytest.mark.parametrize('subject', ['언어논리', '자료해석', '상황판단'])
def test_psat_requests_and_review_do_not_receive_leet_policy(tmp_path, exam, subject):
    brief = Brief(exam=exam, subject=subject, item_type='합성 유형', topic='합성 소재')
    corpus = Corpus(tmp_path / 'corpus.sqlite')
    corpus.add('example', 'synthetic', exam, 'example', subject, {'fields': {'과목': subject}})
    run = prepare(corpus, brief, tmp_path / 'runs')
    assert 'editorial_plan' not in json.loads((run / 'context.json').read_text())
    assert not (run / 'editorial-plan.json').exists()
    assert writer_prompt(brief) == prompt('haean') + '\n' + prompt('psat')
    assert prompt('leet_editorial') not in review_prompt('editor', brief)
    assert editorial_plan(brief) is None
    assert exam_editorial_context({'exam': exam, 'subject': subject, 'slots': []}, []) is None


def test_exam_context_exposes_other_bundles_but_preserves_assignments():
    slots = [{'id': 'SYN-A', 'number': 1, 'domain': '규범', 'topic': '물의 배분',
              'item_type': '견해 분석', 'cognitive_task': '예외의 범위', 'answer_target': 3},
             {'id': 'SYN-B', 'number': 9, 'domain': '사회', 'topic': '이익의 배분',
              'item_type': '견해 분석', 'cognitive_task': '예외의 범위', 'answer_target': 4}]
    plan = {'exam': 'leet', 'subject': '추리논증', 'slots': slots}
    original = copy.deepcopy(plan)
    context = exam_editorial_context(plan, slots[:1])
    assert context['assigned_ids'] == ['SYN-A']
    assert [s['id'] for s in context['slot_overview']] == ['SYN-A', 'SYN-B']
    assert context['slot_overview'][1]['cognitive_task'] == '예외의 범위'
    assert all('answer_target' not in s for s in context['slot_overview'])
    assert plan == original


def test_manual_check_uses_editor_profile_without_leaking_it_to_blind(tmp_path, brief, draft, monkeypatch):
    from haean.cli import main
    save(tmp_path / 'context.json', {'brief': brief.model_dump(),
         'references': [{'id': 'source-1', 'text': ''}], 'editorial_plan': editorial_plan(brief)})
    save(tmp_path / 'input.json', draft.model_dump())
    monkeypatch.setattr('sys.argv', ['haean-tool', 'check', str(tmp_path), str(tmp_path / 'input.json')])
    main()
    assert prompt('leet_editorial') in (tmp_path / 'editorial-instructions.md').read_text()
    assert (tmp_path / 'blind-instructions.md').read_text() == prompt('blind')
    assert 'editorial_plan' not in json.loads((tmp_path / 'blind-input.json').read_text())


def test_build_passes_whole_exam_advice_through_bundle_runtime(tmp_path, brief, monkeypatch):
    from haean.full_exam import build
    slots = [{'id': f'SYN-{n}', 'number': n, 'domain': '규범' if n < 21 else '사회',
              'topic': f'합성 소재 {n}', 'item_type': '조건 추론', 'difficulty': '중'} for n in range(1, 41)]
    plan_path = tmp_path / 'plan.json'
    save(plan_path, {'exam': 'leet', 'subject': '추리논증', 'slots': slots})
    corpus = Corpus(tmp_path / 'corpus.sqlite')
    corpus.add('example', 'synthetic', 'leet', 'example', '조건 사례', {'fields': {'과목': '추리논증'}})
    corpus.db.commit()
    seen = []

    def capture(run, provider, max_revisions):
        context = json.loads((run / 'context.json').read_text())
        advice = context['exam_editorial_context']
        assert len(advice['slot_overview']) == 40
        assert advice['assigned_ids'] == [s['id'] for s in context['exam_assignment']]
        request = (run / 'request.md').read_text()
        assert json.loads(request.split('회차 소재·구조 대조:\n')[1]) == advice
        seen.extend(advice['assigned_ids'])
        raise RuntimeError('synthetic capture, no model execution')

    monkeypatch.setattr('haean.full_exam.run_pipeline', capture)
    monkeypatch.setattr('haean.full_exam.CodexProvider', lambda *a, **k: None)
    build(plan_path, tmp_path / 'corpus.sqlite', tmp_path / 'output', workers=1, max_revisions=0)
    assert sorted(seen) == sorted(s['id'] for s in slots)
