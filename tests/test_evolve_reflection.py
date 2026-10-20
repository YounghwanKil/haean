"""Synthetic diagnostic invariants; never reads production or holdout runs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/haean-evolve/scripts/reflect_experiment.py'
MODULE = runpy.run_path(str(SCRIPT))
reflect = MODULE['reflect']


def cohort():
    return dict(suite='synthetic', split='development', model='test-model', repeats=3,
                max_revisions=2, mode='test', humanizer='off', frozen={'protocol': 'a'*64},
                evaluation_protocol='synthetic-v1', codex_version='test', complete=True,
                cases=['synthetic-item'], results=[dict(
                    case_id='synthetic-item', repeat=i, exam='leet', subject='추리논증', group='norm',
                    state='complete', eligible=True, quality=3, fatal_count=0,
                    dimensions=dict.fromkeys(MODULE['DIMENSIONS'], 3),
                    usage=[dict(seconds=10, usage=dict(input_tokens=100, output_tokens=20,
                        cached_input_tokens=80, reasoning_output_tokens=10))]) for i in range(3)])


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return path


def diagnose(tmp_path, a=None, b=None, **kwargs):
    a = cohort() if a is None else a
    b = deepcopy(a) if b is None else b
    return reflect(write(tmp_path/'a.json', a), write(tmp_path/'b.json', b), tmp_path/'diagnosis.json', **kwargs)


def test_dimension_tradeoff_cannot_be_hidden_by_higher_mean(tmp_path):
    a, b = cohort(), cohort()
    for row in b['results']:
        row['dimensions']['language'] = 4
        row['dimensions']['explanation'] = 4
        row['dimensions']['distractors'] = 2
        row['quality'] = 3.125
    r = diagnose(tmp_path, a, b, top_n=1)
    assert r['comparable'] and len(r['pairs']) == 3 and len(r['priority_evidence']) == 1
    assert r['products']['leet/추리논증']['quality_relation'] == 'tradeoff'
    assert r['pairs'][0]['declining_dimensions'] == ['distractors']
    assert r['auto_promoted'] is False and r['expert_verified'] is False


def test_quality_gain_with_more_cost_is_tradeoff_and_tokens_not_double_counted(tmp_path):
    a, b = cohort(), cohort()
    for row in b['results']:
        row['dimensions']['reasoning_value'] = 4
        row['usage'][0]['usage']['input_tokens'] = 120
    r = diagnose(tmp_path, a, b)
    pair = r['pairs'][0]
    assert pair['quality_relation'] == 'candidate_dominates'
    assert pair['quality_cost_relation'] == 'tradeoff'
    assert pair['cost']['baseline']['input_tokens'] == 100
    assert pair['cost']['baseline']['output_tokens'] == 20


def test_cheaper_equal_quality_can_dominate(tmp_path):
    a, b = cohort(), cohort()
    for row in b['results']:
        row['usage'][0]['seconds'] = 5
    r = diagnose(tmp_path, a, b)
    assert r['pairs'][0]['quality_cost_relation'] == 'candidate_dominates'


@pytest.mark.parametrize('field', MODULE['CONDITIONS'])
def test_both_missing_conditions_never_count_as_equal(tmp_path, field):
    if field == 'split':
        a = cohort(); a.pop(field)
        with pytest.raises(ValueError): diagnose(tmp_path, a)
    else:
        a = cohort(); a.pop(field)
        r = diagnose(tmp_path, a)
        assert not r['comparable'] and not r['frontier_eligible']
        assert all(p['quality_relation'] == 'withheld' for p in r['pairs'])


@pytest.mark.parametrize('kind', ['duplicate', 'missing', 'failed', 'product', 'dimensions', 'fatal_conflict'])
def test_invalid_pairs_preserved_and_blocked(tmp_path, kind):
    a, b = cohort(), cohort()
    if kind == 'duplicate': b['results'].append(deepcopy(b['results'][0]))
    elif kind == 'missing': b['results'].pop()
    elif kind == 'failed': b['results'][1].update(state='failed', quality=None)
    elif kind == 'product': b['results'][1]['subject'] = '자료해석'
    elif kind == 'dimensions': b['results'][1]['dimensions']['language'] = None
    else: b['results'][1]['fatal_count'] = 1
    r = diagnose(tmp_path, a, b)
    assert not r['comparable'] and not r['frontier_eligible']
    assert len(r['pairs']) == 3
    if kind == 'duplicate': assert len(r['unindexed_rows']) == 1


def test_gate_regression_prioritized_not_cancelled_by_other_scores(tmp_path):
    a, b = cohort(), cohort()
    b['results'][2].update(eligible=False, fatal_count=1)
    b['results'][0]['dimensions']['language'] = 4
    r = diagnose(tmp_path, a, b)
    assert not r['frontier_eligible']
    assert r['priority_evidence'][0]['repeat'] == 2
    assert r['pairs'][2]['quality_relation'] == 'withheld'
    assert r['products']['leet/추리논증']['quality_relation'] == 'withheld'


@pytest.mark.parametrize('usage', [None, [], [None], [{'seconds': 0, 'usage': None}]])
def test_missing_cost_is_unknown_not_free(tmp_path, usage):
    a, b = cohort(), cohort()
    b['results'][0]['usage'] = usage
    r = diagnose(tmp_path, a, b)
    assert r['pairs'][0]['cost']['candidate']['input_tokens'] is None
    assert r['pairs'][0]['quality_cost_relation'] == 'unknown'


def test_original_decision_and_files_unchanged_evidence_has_hash_and_stage(tmp_path):
    run = tmp_path/'run'; run.mkdir()
    original = write(run/'review-r0.json', {'editorial': {'issues': ['수정 전 조건 누락']}})
    a = cohort(); a['results'][0]['run'] = 'run'
    comparison = write(tmp_path/'comparison.json', {'decision': 'reject_regression', 'auto_promoted': False})
    before = original.read_bytes(), comparison.read_bytes()
    r = diagnose(tmp_path, a, comparison_path=comparison, evidence_root=tmp_path)
    assert r['frozen_comparison']['original']['decision'] == 'reject_regression'
    evidence = r['pairs'][0]['evidence']['baseline']
    excerpt = evidence['excerpts'][0]
    assert excerpt['stage'] == 'review-r0' and excerpt['text'] == '수정 전 조건 누락'
    assert excerpt['source']['sha256'] == hashlib.sha256(before[0]).hexdigest()
    assert (original.read_bytes(), comparison.read_bytes()) == before
    with pytest.raises(FileExistsError): reflect(tmp_path/'a.json', tmp_path/'b.json', tmp_path/'diagnosis.json')


def test_malformed_raw_evidence_does_not_destroy_diagnosis(tmp_path):
    run = tmp_path/'run'; run.mkdir()
    write(run/'review-r0.json', {'errors': None, 'editorial': None})
    write(run/'evaluation.json', {'items': [None, {'fatal_errors': None, 'dimensions': None}]})
    a = cohort(); a['results'][0]['run'] = 'run'
    r = diagnose(tmp_path, a, evidence_root=tmp_path)
    assert len(r['pairs'][0]['evidence']['baseline']['files']) == 2


def test_raw_evidence_symlink_outside_root_is_not_read(tmp_path):
    root = tmp_path/'allowed'; root.mkdir(); run = root/'run'; run.mkdir()
    outside = write(tmp_path/'secret.json', {'errors': ['should not be in report']})
    (run/'status.json').symlink_to(outside)
    a = cohort(); a['results'][0]['run'] = 'run'
    r = diagnose(tmp_path, a, evidence_root=root)
    assert 'should not be in report' not in json.dumps(r)
    assert any('밖' in i for i in r['pairs'][0]['evidence']['baseline']['issues'])


@pytest.mark.parametrize('where', ['manifest', 'raw'])
def test_nested_holdout_rejected(tmp_path, where):
    a = cohort()
    if where == 'manifest': a['metadata'] = {'nested': [{'split': 'holdout'}]}
    else:
        run = tmp_path/'run'; run.mkdir()
        write(run/'status.json', {'nested': {'split': 'holdout'}})
        a['results'][0]['run'] = 'run'
    with pytest.raises(ValueError, match='holdout'): diagnose(tmp_path, a, evidence_root=tmp_path)
    assert not (tmp_path/'diagnosis.json').exists()


def test_cli_routes_to_skill(tmp_path, monkeypatch):
    from haean.cli import main
    a = write(tmp_path/'a.json', cohort()); b = write(tmp_path/'b.json', cohort())
    out = tmp_path/'diagnosis.json'
    monkeypatch.setattr('sys.argv', ['haean-tool', 'evolve-reflect', str(a), str(b), '--out', str(out)])
    main()
    assert json.loads(out.read_text())['comparable'] is True


def track_cohort():
    a = cohort()
    for row in a['results']:
        row.pop('exam'); row.pop('subject')
        row.update(track='psat_data', grade=5)
    return a


def test_track_grade_schema_without_guessing_legacy_fields(tmp_path):
    r = diagnose(tmp_path, track_cohort())
    assert r['comparable'] and r['frontier_eligible']
    assert 'psat_data/5급' in r['products']


@pytest.mark.parametrize('mutation', ['grade', 'track', 'missing_grade', 'mixed'])
def test_track_products_cannot_cross_contaminate(tmp_path, mutation):
    a, b = track_cohort(), track_cohort()
    if mutation == 'grade': b['results'][1]['grade'] = 7
    elif mutation == 'track': b['results'][1]['track'] = 'psat_verbal'
    elif mutation == 'missing_grade': b['results'][1].pop('grade')
    else: b['results'][1].update(exam='leet', subject='추리논증')
    r = diagnose(tmp_path, a, b)
    assert not r['comparable'] and not r['frontier_eligible']
