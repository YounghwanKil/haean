"""Review-state claims cannot replace item-scoped saved review evidence."""
import hashlib
import json

import pytest

from haean.pipeline import save
from haean.production_review_provenance import review_provenance
from haean.production_status import production_status


def recorded(run, draft, brief, *, parent=None, review=True):
    from test_review_binding import results
    run.mkdir(parents=True, exist_ok=True)
    save(run / 'candidate.json', draft.model_dump())
    save(run / 'brief.json', brief.model_dump())
    save(run / 'context.json', {'brief': brief.model_dump(), 'references': []})
    state = {'state': 'awaiting_human_review', 'candidate_sha256': hashlib.sha256(
        (run / 'candidate.json').read_bytes()).hexdigest()}
    if parent is not None:
        state['parent_review_run'] = str(parent)
    if review:
        blind, editorial = results(draft)
        state['revision'] = 0
        save(run / 'draft-r0.json', draft.model_dump())
        save(run / 'review-r0.json', {'revision': 0, 'blind': blind.model_dump(),
                                    'editorial': editorial.model_dump(), 'errors': []})
    save(run / 'status.json', state)
    return run


def status(run, brief, count=1):
    save(run.parent / 'production.json', {'exam': brief.exam, 'subject': brief.subject,
        'total': count, 'jobs': [{'bundle': 1, 'slots': list(range(1, count+1)),
                                'run': str(run), 'state': 'awaiting_human_review'}]})
    return production_status(run.parent)


def item(run, **kwargs):
    return review_provenance(run, **kwargs)['items'][0]


def test_status_only_is_not_a_review(tmp_path, draft, brief):
    run = recorded(tmp_path / 'run', draft, brief, review=False)
    report = status(run, brief)
    assert report['status_claimed_reviewed_items_with_matching_hash'] == 1
    assert report['model_reviewed_items_with_matching_hash'] == report['ready_for_human_review_items'] == 0
    assert report['jobs'][0]['candidate_hash_matches_status'] is True
    assert report['jobs'][0]['reviewed_candidate_hash_matches'] is False
    assert report['jobs'][0]['effective_state'] == 'review_unverified'


def test_direct_review_is_bound_and_read_only(tmp_path, draft, brief):
    run = recorded(tmp_path / 'run', draft, brief)
    report = status(run, brief)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert production_status(run.parent) == report
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    evidence = report['jobs'][0]['review_provenance']['items'][0]
    assert evidence['verified'] and evidence['review_passed']
    assert evidence['source_kind'] == 'automatic'
    assert evidence['origin'] == 'direct'
    assert evidence['source_revision'] == 0
    assert evidence['source_path'] == str(run / 'review-r0.json')
    assert report['model_reviewed_items_with_matching_hash'] == report['ready_for_human_review_items'] == 1


@pytest.mark.parametrize('change', ['private_explanation', 'answer', 'source_ids'])
def test_rehashed_current_candidate_does_not_rebind_old_review(tmp_path, draft, brief, change):
    run = recorded(tmp_path / 'run', draft, brief)
    changed = draft.model_copy(deep=True)
    if change == 'private_explanation':
        changed.items[0].explanation += ' 다른 설명'
    elif change == 'answer':
        changed.items[0].answer = 2
    else:
        changed.items[0].source_ids = ['different']
    save(run / 'candidate.json', changed.model_dump())
    state = json.loads((run / 'status.json').read_text())
    state['candidate_sha256'] = hashlib.sha256((run / 'candidate.json').read_bytes()).hexdigest()
    save(run / 'status.json', state)
    result = item(run)
    assert result['reason'] == 'reviewed_item_content_changed'
    assert not result['verified']
    assert status(run, brief)['ready_for_human_review_items'] == 0


def test_multihop_inheritance_compares_whole_item_not_package_bytes(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    changed_package = draft.model_copy(deep=True)
    changed_package.design_summary = '문항 내용은 그대로인 분리 원고'
    middle = recorded(tmp_path / 'middle', changed_package, brief, parent=parent, review=False)
    child = recorded(tmp_path / 'child', changed_package, brief, parent=middle, review=False)
    result = item(child)
    assert result['verified'] and result['review_passed']
    assert result['origin'] == 'inherited' and result['source_run'] == str(parent)
    assert len(result['chain']) == 3
    assert result['chain'][0]['candidate_sha256'] != result['chain'][2]['candidate_sha256']
    assert status(child, brief)['ready_for_human_review_items'] == 1


def test_changed_same_id_stops_inheritance(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    changed = draft.model_copy(deep=True)
    changed.items[0].commentary += ' 새 내부 조건'
    child = recorded(tmp_path / 'child', changed, brief, parent=parent, review=False)
    result = item(child)
    assert result['reason'] == 'item_content_changed'
    assert not result['verified']


@pytest.mark.parametrize('fault,reason', [
    ('cycle', 'parent_cycle'), ('missing', 'missing_candidate'),
    ('malformed', 'malformed_candidate'), ('duplicate', 'duplicate_or_empty_item_id'),
    ('status_missing', 'missing_status'), ('status_malformed', 'malformed_status'),
    ('depth', 'parent_depth_limit')])
def test_parent_failures_are_explicit(tmp_path, draft, brief, fault, reason):
    parent = recorded(tmp_path / 'parent', draft, brief)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    kwargs = {}
    if fault == 'cycle':
        child = recorded(child, draft, brief, parent=child, review=False)
    elif fault == 'missing':
        (parent / 'candidate.json').unlink()
    elif fault == 'malformed':
        (parent / 'candidate.json').write_text('{')
    elif fault == 'duplicate':
        duplicate = draft.model_copy(deep=True)
        duplicate.items.append(draft.items[0])
        save(parent / 'candidate.json', duplicate.model_dump())
    elif fault == 'status_missing':
        (parent / 'status.json').unlink()
    elif fault == 'status_malformed':
        (parent / 'status.json').write_text('[]')
    else:
        kwargs['max_depth'] = 0
    result = item(child, **kwargs)
    assert result['reason'] == reason
    assert not result['verified']
    if fault in {'status_missing', 'status_malformed'}:
        assert str(parent / 'review-r0.json') in result['records_found']


@pytest.mark.parametrize('change,reason', [
    ('malformed', 'malformed_review'), ('revision', 'review_revision_mismatch'),
    ('missing_solution', 'review_item_ids_mismatch'), ('unknown_issue', 'review_item_ids_mismatch')])
def test_bad_direct_evidence_does_not_count(tmp_path, draft, brief, change, reason):
    run = recorded(tmp_path / 'run', draft, brief)
    path = run / 'review-r0.json'
    value = json.loads(path.read_text())
    if change == 'malformed':
        value = {'errors': []}
    elif change == 'revision':
        value['revision'] = 1
    elif change == 'missing_solution':
        value['blind']['solutions'] = []
    else:
        value['editorial']['issues'] = [{'severity': 'C', 'category': 'test', 'item_id': 'other',
            'location': 'test', 'problem': 'test', 'fix': 'test'}]
    save(path, value)
    # Malformed review lacks the revision first; both are invalid evidence.
    expected = 'review_revision_mismatch' if change == 'malformed' else reason
    assert item(run)['reason'] == expected
    assert status(run, brief)['ready_for_human_review_items'] == 0


def test_legacy_manual_is_found_but_never_bound_by_summary_sha(tmp_path, draft, brief):
    from test_review_binding import results
    parent = recorded(tmp_path / 'parent', draft, brief, review=False)
    blind, editor = results(draft)
    editor.summary += ' candidate SHA ' + hashlib.sha256((parent / 'candidate.json').read_bytes()).hexdigest()
    save(parent / 'manual-review.json', {'blind': blind.model_dump(), 'editorial': editor.model_dump(), 'errors': []})
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    result = item(child)
    assert result['reason'] == 'legacy_record_found'
    assert result['source_kind'] == 'legacy' and result['origin'] == 'inherited'
    assert not result['verified']
    report = status(child, brief)
    assert report['review_records_found_items'] == 1
    assert report['ready_for_human_review_items'] == 0


def test_modern_manual_preserves_attestation_assurance(tmp_path, draft, brief):
    from test_review_binding import setup_run, results, external_result, prepare_editor, accept
    run = tmp_path / 'run'
    run.mkdir()
    setup_run(run, draft, brief)
    blind, editor = results(draft)
    b = external_result(run, 'blind', blind)
    prepare_editor(run, b)
    e = external_result(run, 'editor', editor, name='different-editor-name.json')
    accept(run, b, e)
    # Modern bound receipts existed before original source paths were stored.
    receipt = json.loads((run / 'manual-review.json').read_text())
    receipt.pop('source_paths', None)
    save(run / 'manual-review.json', receipt)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = item(run)
    assert result['verified'] and result['review_passed']
    assert result['source_kind'] == 'manual'
    assert 'not cryptographic proof' in result['assurance']['editorial']
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    e.write_text('{}')
    assert item(run)['reason'] == 'manual_result_file_missing'


def test_parent_feedback_is_item_scoped_and_stale_feedback_excluded(tmp_path, draft, brief):
    from haean.pipeline import feedback
    two = draft.model_copy(deep=True)
    other = draft.items[0].model_copy(deep=True)
    other.id = 'TEST-002'
    two.items.append(other)
    parent = recorded(tmp_path / 'parent', two, brief.model_copy(update={'count': 2}))
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    feedback(parent, other.id, '다른 문항 B', '합성 검토자', 'B')
    assert item(child)['pending_revision_feedback'] is False
    assert status(child, brief)['ready_for_human_review_items'] == 1
    feedback(parent, draft.items[0].id, '해당 문항 B', '합성 검토자', 'B')
    report = status(child, brief)
    assert report['model_reviewed_items_with_matching_hash'] == 1
    assert report['ready_for_human_review_items'] == 0
    assert report['jobs'][0]['effective_state'] == 'needs_revision'


def test_other_parent_item_errors_do_not_block_selected_item(tmp_path, draft, brief):
    two = draft.model_copy(deep=True)
    other = draft.items[0].model_copy(deep=True)
    other.id = 'TEST-002'
    two.items.append(other)
    parent = recorded(tmp_path / 'parent', two, brief.model_copy(update={'count': 2}))
    value = json.loads((parent / 'review-r0.json').read_text())
    value['errors'] = ['TEST-002: B 단순한 오답']
    value['editorial']['issues'] = [{'severity': 'B', 'category': 'test', 'item_id': other.id,
        'location': 'test', 'problem': 'test', 'fix': 'test'}]
    save(parent / 'review-r0.json', value)
    state = json.loads((parent / 'status.json').read_text())
    state['state'] = 'needs_revision'
    save(parent / 'status.json', state)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    result = item(child)
    assert result['verified'] and result['review_passed'] and result['issues'] == []
    assert status(child, brief)['ready_for_human_review_items'] == 1
    value['errors'].append('문항 묶음 공통 검산 오류')
    save(parent / 'review-r0.json', value)
    assert item(child)['verified'] and not item(child)['review_passed']
    assert status(child, brief)['ready_for_human_review_items'] == 0


@pytest.mark.parametrize('target,blocks', [('TEST-002, TEST-003', False),
                                          ('TEST-001, TEST-002', True)])
def test_shared_issue_ids_apply_only_to_matching_items(tmp_path, draft, brief, target, blocks):
    three = draft.model_copy(deep=True)
    for number in [2, 3]:
        other = draft.items[0].model_copy(deep=True)
        other.id = f'TEST-00{number}'
        three.items.append(other)
    parent = recorded(tmp_path / 'parent', three, brief.model_copy(update={'count': 3}))
    record = json.loads((parent / 'review-r0.json').read_text())
    record['errors'] = [f'{target}: B 공통 조건 누락']
    record['editorial']['issues'] = [{'severity': 'B', 'category': 'test', 'item_id': target,
        'location': 'test', 'problem': 'test', 'fix': 'test'}]
    save(parent / 'review-r0.json', record)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    result = item(child)
    assert result['verified'] and result['review_passed'] is not blocks
    assert len(result['issues']) == int(blocks)
    assert len(result['errors']) == (2 if blocks else 0)


@pytest.mark.parametrize('ids', [['TEST-OTHER'], ['TEST-002', 'TEST-001']])
def test_manifest_ids_must_match_current_item_order(tmp_path, draft, brief, ids):
    candidate = draft.model_copy(deep=True)
    if len(ids) == 2:
        other = draft.items[0].model_copy(deep=True)
        other.id = 'TEST-002'
        candidate.items.append(other)
    run = recorded(tmp_path / 'run', candidate, brief.model_copy(update={'count': len(ids)}))
    status(run, brief, count=len(ids))
    path = run.parent / 'production.json'
    manifest = json.loads(path.read_text())
    manifest['jobs'][0]['ids'] = ids
    save(path, manifest)
    report = production_status(run.parent)
    assert report['model_reviewed_items_with_matching_hash'] == report['ready_for_human_review_items'] == 0
    assert report['jobs'][0]['review_provenance']['error'] == 'manifest_item_ids_mismatch'
    assert report['jobs'][0]['effective_state'] == 'review_unverified'


def test_unbound_current_review_cannot_fall_back_to_older_parent(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    save(child / 'review-r0.json', {'errors': []})
    result = item(child)
    assert result['reason'] == 'review_revision_missing'
    assert not result['verified'] and len(result['chain']) == 1


def test_bound_review_answer_mismatch_is_reviewed_but_not_ready(tmp_path, draft, brief):
    run = recorded(tmp_path / 'run', draft, brief)
    path = run / 'review-r0.json'
    record = json.loads(path.read_text())
    record['blind']['solutions'][0]['answer'] = 2
    save(path, record)
    report = status(run, brief)
    assert report['model_reviewed_items_with_matching_hash'] == 1
    assert report['ready_for_human_review_items'] == 0
    assert report['jobs'][0]['effective_state'] == 'needs_revision'
    assert item(run)['errors'] == ['독립 풀이 불일치·조건 부족']


def test_unreadable_parent_feedback_is_unknown_not_ready(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent, review=False)
    (tmp_path / 'feedback.jsonl').write_text('not json')
    result = item(child)
    assert result['verified'] and result['pending_revision_feedback'] is None
    assert result['feedback_error']
    report = status(child, brief)
    assert report['model_reviewed_items_with_matching_hash'] == 1
    assert report['ready_for_human_review_items'] == 0
    assert report['jobs'][0]['effective_state'] == 'review_unverified'


def test_current_corrupt_review_blocks_parent_fallback(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent)
    (child / 'review-r0.json').write_text('{')
    result = item(child)
    assert not result['verified'] and result['reason'] == 'malformed_review'
    assert len(result['chain']) == 1


def test_manual_binding_changes_are_not_backfilled(tmp_path, draft, brief):
    from test_review_binding import setup_run, results, external_result, prepare_editor, accept
    run = tmp_path / 'run'
    run.mkdir()
    setup_run(run, draft, brief)
    blind, editor = results(draft)
    b = external_result(run, 'blind', blind)
    prepare_editor(run, b)
    e = external_result(run, 'editor', editor)
    accept(run, b, e)
    request = json.loads((run / 'review-request.json').read_text())
    request['bindings']['blind']['input_sha256'] = '0' * 64
    save(run / 'review-request.json', request)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = item(run)
    assert not result['verified'] and result['reason'] == 'manual_binding_invalid'
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_missing_selected_revision_does_not_fall_back(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    child = recorded(tmp_path / 'child', draft, brief, parent=parent)
    (child / 'review-r0.json').unlink()
    result = item(child)
    assert result['reason'] == 'missing_review'
    assert not result['verified'] and result['source_run'] == str(child)


def test_boolean_revision_is_not_an_integer_revision(tmp_path, draft, brief):
    run = recorded(tmp_path / 'run', draft, brief)
    record = json.loads((run / 'review-r0.json').read_text())
    record['revision'] = False
    save(run / 'review-r0.json', record)
    assert item(run)['reason'] == 'review_revision_mismatch'


@pytest.mark.parametrize('hops', [1, 2])
def test_assembled_views_retain_revision_without_own_review_files(tmp_path, draft, brief, hops):
    parent = recorded(tmp_path / 'source', draft, brief)
    current = parent
    for number in range(hops):
        current = recorded(tmp_path / f'view-{number}', draft, brief, parent=current, review=False)
        state = json.loads((current / 'status.json').read_text())
        state['revision'] = 0
        save(current / 'status.json', state)
    result = item(current)
    assert result['verified'] and result['review_passed']
    assert result['origin'] == 'inherited'
    assert result['source_run'] == str(parent)
    assert result['source_revision'] == 0
    assert len(result['chain']) == hops + 1
    assert status(current, brief)['ready_for_human_review_items'] == 1


def test_view_with_local_draft_cannot_hide_missing_selected_review(tmp_path, draft, brief):
    parent = recorded(tmp_path / 'parent', draft, brief)
    child = recorded(tmp_path / 'view', draft, brief, parent=parent, review=False)
    state = json.loads((child / 'status.json').read_text())
    state['revision'] = 0
    save(child / 'status.json', state)
    save(child / 'draft-r1.json', draft.model_dump())
    result = item(child)
    assert not result['verified'] and result['reason'] == 'missing_review'
    assert len(result['chain']) == 1


@pytest.mark.parametrize('collision', ['run', 'id', 'slot'])
def test_duplicate_manifest_rows_do_not_inflate_counts(tmp_path, draft, brief, collision):
    first = recorded(tmp_path / 'one', draft, brief)
    other = draft.model_copy(deep=True)
    if collision == 'slot':
        other.items[0].id = 'TEST-002'
    second = first if collision == 'run' else recorded(tmp_path / 'two', other, brief)
    save(tmp_path / 'production.json', {'exam': brief.exam, 'subject': brief.subject, 'total': 2,
        'jobs': [{'bundle': n+1, 'slots': [1 if collision == 'slot' else n+1],
                  'run': str(run), 'state': 'awaiting_human_review'} for n, run in enumerate([first, second])]})
    report = production_status(tmp_path)
    assert report['status_claimed_reviewed_items_with_matching_hash'] == 2
    assert report['model_reviewed_items_with_matching_hash'] == 0
    assert report['ready_for_human_review_items'] == 0
    assert all(job['effective_state'] == 'review_unverified' for job in report['jobs'])
    assert all(job['review_provenance']['error'] == 'manifest_duplicate_item_mapping' for job in report['jobs'])


@pytest.mark.parametrize('name', ['review-request.json', 'editor-review-request.json'])
def test_malformed_manual_binding_json_object_does_not_crash_status(tmp_path, draft, brief, name):
    from test_review_binding import setup_run, results, external_result, prepare_editor, accept
    run = tmp_path / 'run'
    run.mkdir()
    setup_run(run, draft, brief)
    blind, editor = results(draft)
    b = external_result(run, 'blind', blind)
    prepare_editor(run, b)
    e = external_result(run, 'editor', editor)
    accept(run, b, e)
    save(run / name, [])
    result = item(run)
    assert not result['verified'] and result['reason'] == 'manual_binding_invalid'
    report = status(run, brief)
    assert report['ready_for_human_review_items'] == 0
    assert report['jobs'][0]['effective_state'] == 'review_unverified'


@pytest.mark.parametrize('failure', [None, 'missing', 'hash'])
def test_explicit_external_editor_source_is_verified_without_local_fallback(tmp_path, draft, brief, failure):
    from test_review_binding import setup_run, results, external_result, prepare_editor, accept
    run = tmp_path / 'run'
    run.mkdir()
    setup_run(run, draft, brief)
    blind, editor = results(draft)
    b = external_result(run, 'blind', blind)
    prepare_editor(run, b)
    external = external_result(run, 'editor', editor, name='../outside-editor.json')
    accept(run, b, external)
    receipt = json.loads((run / 'manual-review.json').read_text())
    receipt['source_paths'] = {'blind': str(b.resolve()), 'editorial': str(external.resolve())}
    save(run / 'manual-review.json', receipt)
    # Keep a byte-identical local copy: a broken explicit reference must still
    # fail, rather than silently accepting this alternate local file.
    (run / 'editorial-result.json').write_bytes(external.read_bytes())
    if failure == 'missing':
        external.unlink()
    elif failure == 'hash':
        external.write_text('{}')
    result = item(run)
    if failure is None:
        assert result['verified'] and result['review_passed']
        assert str(external.resolve()) in result['result_paths']
    else:
        assert not result['verified']
        assert result['reason'] == ('manual_result_file_missing' if failure == 'missing'
                                    else 'manual_result_file_hash_mismatch')
