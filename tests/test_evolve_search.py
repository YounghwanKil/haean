"""Synthetic cohort contracts for GEPA-inspired selection; no production inputs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = runpy.run_path(str(ROOT / 'skills/haean-evolve/scripts/search_experiment.py'))
select = TOOLS['select_experiment']
merge = TOOLS['merge_experiment']


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path):
    cases = ['feedback', 'logic', 'language']
    pool = {'split': 'development', 'feedback_cases': cases[:1], 'selection_cases': cases[1:],
            'case_families': {c: c for c in cases}, 'candidates': []}
    for identity, grades in [('baseline', [3, 3.6, 3.6]), ('specialist', [3, 4, 3])]:
        cohort = dict(suite='synthetic', split='development', model='test-model', repeats=3,
                      max_revisions=2, mode='test', humanizer='off', frozen={'protocol': 'a'*64},
                      evaluation_protocol='synthetic-v1', codex_version='test', complete=True,
                      harness={'prompt': ('b' if identity == 'baseline' else 'c')*64}, cases=cases, results=[])
        for case, grade in zip(cases, grades):
            for repeat in range(3):
                cohort['results'].append(dict(case_id=case, repeat=repeat, exam='leet', subject='추리논증',
                    group='synthetic', state='awaiting_human_review', eligible=True, fatal_count=0, quality=grade,
                    dimensions=dict.fromkeys(TOOLS['DIAGNOSTICS']['DIMENSIONS'], grade),
                    run=f'private/{identity}/{case}/{repeat}'))
        path = tmp_path / f'{identity}.json'
        pool['candidates'].append({'id': identity, 'results': path.name, 'sha256': save(path, cohort)})
    save(tmp_path/'pool.json', pool)
    return pool


def mutate_cohort(tmp_path, pool, fn):
    entry = pool['candidates'][1]
    path = tmp_path / entry['results']
    cohort = json.loads(path.read_text())
    fn(cohort)
    entry['sha256'] = save(path, cohort)
    save(tmp_path/'pool.json', pool)


def test_lower_average_specialist_survives_and_only_feedback_refs_are_exposed(tmp_path):
    fixture(tmp_path)
    result = select(tmp_path/'pool.json', tmp_path/'decision.json', seed=17)
    assert set(result['decision']['survivors']) == {'baseline', 'specialist'}
    assert {x['case_id'] for x in result['feedback_runs']} == {'feedback'}
    assert not result['auto_promoted'] and not result['raw_feedback_read']
    assert not result['actual_model_verified']
    assert len(result['sources']) == 2
    with pytest.raises(FileExistsError):
        select(tmp_path/'pool.json', tmp_path/'decision.json')


@pytest.mark.parametrize('kind', ['overlap', 'family_overlap', 'duplicate_id', 'missing_family', 'holdout', 'wrong_hash'])
def test_partition_and_source_provenance_rejects(tmp_path, kind):
    pool = fixture(tmp_path)
    if kind == 'overlap': pool['feedback_cases'].append('logic')
    elif kind == 'family_overlap': pool['case_families']['logic'] = 'feedback'
    elif kind == 'duplicate_id': pool['candidates'].append(deepcopy(pool['candidates'][0]))
    elif kind == 'missing_family': del pool['case_families']['logic']
    elif kind == 'holdout': pool['candidates'][0]['split'] = 'holdout'
    elif kind == 'wrong_hash': pool['candidates'][0]['sha256'] = 'd'*64
    save(tmp_path/'pool.json', pool)
    with pytest.raises(ValueError): select(tmp_path/'pool.json', tmp_path/'out.json')
    assert not (tmp_path/'out.json').exists()


@pytest.mark.parametrize('kind', ['repeat', 'missing', 'duplicate', 'protocol', 'product', 'harness', 'dimensions', 'actual_model', 'revision_budget'])
def test_invalid_comparison_cannot_be_silently_selected(tmp_path, kind):
    pool = fixture(tmp_path)
    def change(cohort):
        if kind == 'repeat': cohort['repeats'] = 1
        elif kind == 'missing': cohort['results'].pop()
        elif kind == 'duplicate': cohort['results'].append(deepcopy(cohort['results'][0]))
        elif kind == 'protocol': cohort.pop('evaluation_protocol')
        elif kind == 'product': cohort['results'][0]['exam'] = 'psat7'
        elif kind == 'harness': cohort.pop('harness')
        elif kind == 'dimensions': cohort['results'][0]['dimensions']['validity'] = float('nan')
        elif kind == 'actual_model': cohort['actual_model'] = 'other-model'
        elif kind == 'revision_budget': cohort['max_revisions'] = 3
    mutate_cohort(tmp_path, pool, change)
    with pytest.raises(ValueError): select(tmp_path/'pool.json', tmp_path/'out.json')


@pytest.mark.parametrize('kind', ['fatal', 'failed', 'invalidity', 'incomplete', 'running', 'missing_state'])
def test_failure_is_preserved_as_exclusion_not_removed_from_average(tmp_path, kind):
    pool = fixture(tmp_path)
    def change(cohort):
        row = cohort['results'][0]
        if kind == 'fatal': row.update(fatal_count=1, eligible=False)
        elif kind == 'failed': row.update(state='failed', quality=None, dimensions=None, fatal_count=None)
        elif kind == 'invalidity':
            row['dimensions'] = dict.fromkeys(TOOLS['DIAGNOSTICS']['DIMENSIONS'], 2)
            row['quality'] = 2
        elif kind == 'running': row['state'] = 'running'
        elif kind == 'missing_state': row.pop('state')
        else: cohort['complete'] = False
    mutate_cohort(tmp_path, pool, change)
    result = select(tmp_path/'pool.json', tmp_path/'out.json')
    assert result['decision']['selected'] == 'baseline'
    assert result['excluded'][0]['id'] == 'specialist'
    assert result['excluded'][0]['reasons']


def test_merge_is_unapproved_artifact_and_never_installs_sources(tmp_path):
    paths = [tmp_path / f'{name}.json' for name in ('ancestor', 'left', 'right')]
    originals = [{'writer': 'old', 'style': 'old'}, {'writer': 'new', 'style': 'old'}, {'writer': 'old', 'style': 'new'}]
    for path, value in zip(paths, originals): save(path, value)
    result = merge(*paths, tmp_path/'merged.json')
    assert result['components'] == {'writer': 'new', 'style': 'new'}
    assert not result['ancestry_verified'] and result['evaluation_required'] and not result['auto_promoted']
    assert [json.loads(p.read_text()) for p in paths] == originals


def test_unspecified_psat_grade_cannot_form_its_own_valid_pool(tmp_path):
    pool = fixture(tmp_path)
    for entry in pool['candidates']:
        path = tmp_path / entry['results']
        cohort = json.loads(path.read_text())
        for row in cohort['results']:
            row.update(exam='psat', subject='자료해석')
        entry['sha256'] = save(path, cohort)
    save(tmp_path/'pool.json', pool)
    with pytest.raises(ValueError, match='grade'):
        select(tmp_path/'pool.json', tmp_path/'out.json')


def test_track_grade_schema_supported_without_cross_grade_pooling(tmp_path):
    pool = fixture(tmp_path)
    for entry in pool['candidates']:
        path = tmp_path / entry['results']
        cohort = json.loads(path.read_text())
        for row in cohort['results']:
            row.pop('exam'); row.pop('subject')
            row.update(track='psat_data', grade=7)
        entry['sha256'] = save(path, cohort)
    save(tmp_path/'pool.json', pool)
    assert select(tmp_path/'pool.json', tmp_path/'good.json')['product'] == ['track_grade', 'psat_data', '7급']
    mutate_cohort(tmp_path, pool, lambda c: c['results'][0].update(grade=5))
    with pytest.raises(ValueError, match='separate pools'):
        select(tmp_path/'pool.json', tmp_path/'bad.json')
