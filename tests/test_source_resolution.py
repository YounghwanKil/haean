"""Synthetic historical aliases only; no production catalog or run fixtures."""
from copy import deepcopy
import hashlib
import json
import pytest

from haean.novelty import digest, remember, memory_get, memory_index
from haean.source_resolution import resolve_source


def write(path, items, **kwargs):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'items': items}, **kwargs))
    return path


def test_historical_alias_retains_payload_hash_source_and_readonly_db(tmp_path):
    source = tmp_path / 'batch' / 'candidate.json'
    old = {'id': 'synthetic-084', 'text': '가상 조건', 'answer': 1}
    new = dict(old, answer=2)
    db = tmp_path / 'catalog.sqlite'
    rows = []
    for item in (old, new):
        write(source, [item])
        entry = dict(exam='leet', subject='logic', item=item,
                     sha256=digest(item), source=str(source))
        remember(db, [entry])
        rows.append(entry)
        if item == old:
            archive = write(source.parent / 'revision-00' / 'candidate.json', [old])
    before = db.read_bytes()
    response = memory_get(db, 'leet', 'logic', [old['id']], all_versions=True)
    assert db.read_bytes() == before
    for actual in response['items']:
        original = next(row for row in rows if row['sha256'] == actual['sha256'])
        assert {key: actual[key] for key in original} == original
        metadata = actual['source_resolution']
        assert metadata['origin_path'] == str(source)
        if actual['item'] == old:
            assert metadata['origin_check']['status'] == 'mismatch'
            assert metadata['status'] == 'resolved_archive'
            assert metadata['matches'] == [{'path': str(archive), 'locator': '$.items[0]',
                'raw_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}]
        else:
            assert metadata['status'] == 'verified_origin'
    assert memory_index(db, 'leet', 'logic')['items'][0]['source_resolution']['status'] == 'not_checked'


def test_all_matches_disclosed_with_exact_locators_and_raw_hashes(tmp_path):
    item = {'id': 'S', 'text': '합성 원문', 'values': [1, True]}
    source = write(tmp_path / 'candidate.json', [dict(item, text='수정')])
    a = write(tmp_path / 'revision-00' / 'candidate.json', [{'id': 'other'}, item], indent=2)
    b = write(tmp_path / 'revision-01' / 'candidate.json', [item], ensure_ascii=False)
    result = resolve_source(str(source), item)
    assert result['status'] == 'ambiguous'
    assert [m['locator'] for m in result['matches']] == ['$.items[1]', '$.items[0]']
    assert [m['path'] for m in result['matches']] == [str(a), str(b)]
    assert len({m['raw_sha256'] for m in result['matches']}) == 2


@pytest.mark.parametrize('actual', [
    {'id': 'S', 'value': True}, {'id': 'S', 'value': 1.0},
    {'id': 'S', 'value': '1'}, {'id': 'other', 'value': 1},
    {'value': 1}, {'id': 'S', 'value': 1, 'extra': None},
])
def test_no_coercion_defaults_partial_or_id_only_match(tmp_path, actual):
    source = write(tmp_path / 'candidate.json', [actual])
    result = resolve_source(str(source), {'id': 'S', 'value': 1})
    assert result['status'] == 'unresolved'
    assert result['origin_check']['status'] == 'mismatch'
    assert not result['matches']


def test_id_bool_not_numeric_alias(tmp_path):
    source = write(tmp_path / 'candidate.json', [{'id': True}])
    assert resolve_source(str(source), {'id': 1})['status'] == 'unresolved'


def test_missing_source_and_no_archive_keeps_explicit_status(tmp_path):
    result = resolve_source(str(tmp_path / 'candidate.json'), {'id': 'S'})
    assert result['status'] == 'unresolved'
    assert result['origin_check']['status'] == 'missing'
    assert result['archive_scan_complete']
    assert resolve_source('candidate.json', {'id': 'S'})['origin_check']['status'] == 'unsupported'


@pytest.mark.parametrize('broken', ['{', '{"items":[] , "items":[]}', '{"items":[NaN]}'])
def test_archive_errors_prevent_unique_resolution_claim(tmp_path, broken):
    source = tmp_path / 'candidate.json'
    write(tmp_path / 'revision-00' / 'candidate.json', [{'id': 'S'}])
    bad = tmp_path / 'revision-01' / 'candidate.json'
    bad.parent.mkdir()
    bad.write_text(broken)
    result = resolve_source(str(source), {'id': 'S'})
    assert result['status'] == 'incomplete'
    assert len(result['matches']) == 1
    assert result['archive_checks'][1]['status'] == 'error'
    assert result['archive_checks'][1]['raw_sha256']


def test_exact_origin_duplicate_is_ambiguous(tmp_path):
    source = write(tmp_path / 'candidate.json', [{'id': 'S'}, {'id': 'S'}])
    assert resolve_source(str(source), {'id': 'S'})['status'] == 'ambiguous'


def test_lookup_is_single_level_and_does_not_follow_archive_symlinks(tmp_path):
    source = tmp_path / 'batch' / 'candidate.json'
    item = {'id': 'S'}
    write(tmp_path / 'elsewhere' / 'candidate.json', [item])
    write(source.parent / 'not-a-revision' / 'candidate.json', [item])
    write(source.parent / 'revision-00' / 'nested' / 'candidate.json', [item])
    (source.parent / 'revision-linked').symlink_to(tmp_path / 'elsewhere', target_is_directory=True)
    result = resolve_source(str(source), item)
    assert result['status'] == 'incomplete'
    assert not result['matches']
    assert len(result['archive_checks']) == 2
    assert any('symlink' in c.get('error', '') for c in result['archive_checks'])


def test_read_permission_error_is_reported(tmp_path, monkeypatch):
    from pathlib import Path
    source = write(tmp_path / 'candidate.json', [{'id': 'S'}])
    monkeypatch.setattr(Path, 'read_bytes', lambda self: (_ for _ in ()).throw(PermissionError('denied')))
    result = resolve_source(str(source), {'id': 'S'})
    assert result['status'] == 'unresolved'
    assert result['origin_check']['status'] == 'error'
    assert 'PermissionError' in result['origin_check']['error']
