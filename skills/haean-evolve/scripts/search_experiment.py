"""GEPA-inspired, read-only parent selection over frozen development cohorts.

This is a search aid, not an evaluator, prompt runner, or promotion mechanism.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import runpy
from statistics import mean

HERE = Path(__file__).resolve().parent
DIAGNOSTICS = runpy.run_path(str(HERE / 'reflect_experiment.py'))
LEGACY_PRODUCTS = {('leet', subject) for subject in ('추리논증', '언어이해')} | {
    (exam, subject) for exam in ('psat5', 'psat7')
    for subject in ('언어논리', '자료해석', '상황판단')
}
TRACKS = {'leet_reasoning', 'leet_reading', 'psat_verbal', 'psat_data', 'psat_situation'}


def _ids(value, name):
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f'{name}: nonempty string list required')
    if len(set(value)) != len(value):
        raise ValueError(f'{name}: duplicate IDs')
    return set(value)


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _hashes(value):
    return isinstance(value, dict) and bool(value) and all(isinstance(k, str) and k.strip() and _digest(v) for k, v in value.items())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _save(out, value):
    out = Path(out)
    # Exclusive create also protects input files and concurrent invocations.
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return value


def select_experiment(pool_path, out, *, seed=0):
    """Select one search parent; no raw selection-set traces are loaded."""
    pool_path = Path(pool_path).resolve()
    pool, pool_source = DIAGNOSTICS['_read'](pool_path)
    if not isinstance(pool, dict) or pool.get('split') != 'development':
        raise ValueError('only an explicit development pool is supported')
    feedback = _ids(pool.get('feedback_cases'), 'feedback_cases')
    selection = _ids(pool.get('selection_cases'), 'selection_cases')
    if feedback & selection:
        raise ValueError('feedback and selection cases overlap')
    cases = feedback | selection
    families = pool.get('case_families')
    if not isinstance(families, dict) or set(families) != cases or any(not isinstance(v, str) or not v.strip() for v in families.values()):
        raise ValueError('case_families must cover every case')
    if {families[x] for x in feedback} & {families[x] for x in selection}:
        raise ValueError('shared passage/source family crosses feedback and selection')
    entries = pool.get('candidates')
    if not isinstance(entries, list) or not entries:
        raise ValueError('candidates required')
    conditions, product, identities, admitted, excluded, sources, records = None, None, set(), [], [], [], {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not entry['id'].strip():
            raise ValueError('candidate ID required')
        identity = entry['id']
        if identity in identities:
            raise ValueError('duplicate candidate ID')
        identities.add(identity)
        if not isinstance(entry.get('results'), str) or not entry['results'].strip() or not _digest(entry.get('sha256')):
            raise ValueError('candidate results path and pinned sha256 required')
        path = (pool_path.parent / entry['results']).resolve()
        cohort, source = DIAGNOSTICS['_read'](path)
        if source['sha256'] != entry['sha256']:
            raise ValueError(f'{identity}: results hash mismatch')
        if not isinstance(cohort, dict) or cohort.get('split') != 'development':
            raise ValueError('development cohorts only')
        current = {k: cohort.get(k) for k in DIAGNOSTICS['CONDITIONS']}
        for name in ('suite', 'split', 'model', 'mode', 'humanizer', 'evaluation_protocol', 'codex_version'):
            if not isinstance(current[name], str) or not current[name].strip():
                raise ValueError(f'{identity}: missing condition {name}')
        if type(current['repeats']) is not int or not 3 <= current['repeats'] <= 5:
            raise ValueError('three to five independent repeats required')
        if type(current['max_revisions']) is not int or not 0 <= current['max_revisions'] <= 2 or not _hashes(current['frozen']):
            raise ValueError('invalid revision budget or frozen hashes')
        if not _hashes(cohort.get('harness')):
            raise ValueError('harness snapshot hashes required')
        # Unknown backend identity is disclosed, never upgraded to verified.
        current['actual_model'] = cohort.get('actual_model')
        if current['actual_model'] is not None and (not isinstance(current['actual_model'], str) or not current['actual_model'].strip()):
            raise ValueError('invalid actual_model')
        if conditions is None:
            conditions = current
        elif conditions != current:
            raise ValueError(f'{identity}: comparison conditions differ')
        if _ids(cohort.get('cases'), 'cohort cases') != cases:
            raise ValueError('cohort must cover exactly both development partitions')
        rows = cohort.get('results')
        if not isinstance(rows, list):
            raise ValueError('results must be a list')
        indexed, reasons = {}, []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('invalid result row')
            case, repeat = row.get('case_id'), row.get('repeat')
            if not isinstance(case, str) or case not in cases or type(repeat) is not int or repeat not in range(current['repeats']):
                raise ValueError('unexpected case or repeat')
            key = (case, repeat)
            if key in indexed:
                raise ValueError('duplicate case/repeat')
            indexed[key] = row
            p = DIAGNOSTICS['_product'](row)
            if not p['valid']:
                raise ValueError('product identity required')
            if p['schema'] == 'exam_subject' and tuple(p['display']) not in LEGACY_PRODUCTS:
                raise ValueError('unsupported exam/subject; explicit PSAT grade required')
            if p['schema'] == 'track_grade' and row['track'] not in TRACKS:
                raise ValueError('unsupported track')
            row_product = (p['schema'], *p['display'])
            if product is None:
                product = row_product
            elif product != row_product:
                raise ValueError('use separate pools for each exam/subject/grade')
            dimensions = row.get('dimensions', {})
            valid_dimensions = isinstance(dimensions, dict) and set(dimensions) == set(DIAGNOSTICS['DIMENSIONS']) and all(_number(x) and 0 <= x <= 4 for x in dimensions.values())
            quality = row.get('quality')
            failed = row.get('state') != 'awaiting_human_review'
            if not failed and (not valid_dimensions or not _number(quality) or not math.isclose(quality, mean(dimensions.values()), abs_tol=1e-8)):
                raise ValueError('stored quality/dimensions inconsistent')
            if failed or row.get('eligible') is not True or type(row.get('fatal_count')) is not int or row['fatal_count'] != 0 or not valid_dimensions or dimensions['validity'] < 3 or row.get('errors'):
                reasons.append({'case_id': case, 'repeat': repeat, 'reason': 'failed_or_validity_gate'})
        expected = {(c, r) for c in cases for r in range(current['repeats'])}
        if set(indexed) != expected:
            raise ValueError('missing case/repeat; failed rows must be preserved')
        if cohort.get('complete') is not True:
            reasons.append({'reason': 'incomplete_cohort'})
        sources.append({'id': identity, **source, 'harness': cohort['harness']})
        records[identity] = indexed
        if reasons:
            excluded.append({'id': identity, 'reasons': reasons})
        else:
            admitted.append({'id': identity, 'scores': {c: mean(indexed[c, r]['quality'] for r in range(current['repeats'])) for c in sorted(selection)}})
    selector = runpy.run_path(str(HERE / 'gepa_candidates.py'))['select_parent']
    decision = selector(admitted, seed=seed) if admitted else None
    parent = decision['selected'] if decision else None
    # References only: full originals must be read before reflection. No validation traces.
    feedback_runs = [{'case_id': c, 'repeat': r, 'run': records[parent][c, r].get('run')}
                     for c in sorted(feedback) for r in range(conditions['repeats'])] if parent else []
    return _save(out, {
        'schema': 'haean-gepa-search-v1', 'purpose': 'next_search_parent_only',
        'pool_source': pool_source, 'sources': sources, 'conditions': conditions,
        'product': list(product), 'partition': {'feedback_cases': sorted(feedback), 'selection_cases': sorted(selection), 'case_families': families},
        'decision': decision, 'excluded': excluded, 'feedback_runs': feedback_runs,
        'raw_feedback_read': False, 'actual_model_verified': False,
        'family_labels_independently_verified': False,
        'auto_promoted': False, 'expert_verified': False,
        'next_step': 'Read full feedback-run originals, modify one component, then run the fixed paired evaluation. Do not reflect on selection traces or holdout.',
    })


def merge_experiment(ancestor_path, left_path, right_path, out):
    """Merge caller-supplied component snapshots; ancestry is NOT certified."""
    values, sources = [], []
    for path in (ancestor_path, left_path, right_path):
        value, source = DIAGNOSTICS['_read'](path)
        values.append(value)
        sources.append(source)
    merge = runpy.run_path(str(HERE / 'gepa_candidates.py'))['merge_components']
    return _save(out, {**merge(*values), 'sources': sources,
                       'ancestry_verified': False, 'evaluation_required': True,
                       'auto_promoted': False, 'expert_verified': False})
