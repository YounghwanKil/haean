import hashlib
import json
import pytest
from haean import wiki


def packet(tmp_path, **changes):
    source = tmp_path / 'source.txt'
    if not source.exists(): source.write_text('synthetic development evidence')
    obj = dict(id='test-topic', title='합성 주제', summary='합성 근거', status='model-synthesis', body='근거 [1]',
               sources=[dict(path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), locator='line 1', usage='development')], links=[])
    obj.update(changes)
    p = tmp_path / 'packet.json'; p.write_text(json.dumps(obj))
    return p


def test_revision_search_and_source_immutability(tmp_path):
    root = tmp_path / 'wiki'
    p = packet(tmp_path); before = (tmp_path/'source.txt').read_bytes()
    wiki.put(root, p)
    old_log = (root/'log.md').read_text()
    wiki.put(root, packet(tmp_path, body='수정 근거 [1]'))
    assert list((root/'history/test-topic').glob('*/test-topic.md'))
    assert (root/'log.md').read_text().startswith(old_log)
    assert wiki.search(root, '수정')[0]['page'].endswith('test-topic.md')
    assert (tmp_path/'source.txt').read_bytes() == before


def test_lint_stale_missing_links_and_untracked_edit(tmp_path):
    root = tmp_path/'wiki'
    wiki.put(root, packet(tmp_path, links=['missing'], status='conflicted'))
    (tmp_path/'source.txt').write_text('changed')
    (root/'pages/test-topic.md').write_text('untracked')
    kinds = {i['kind'] for i in wiki.lint(root)['issues']}
    assert {'stale-source', 'broken-link', 'untracked-edit', 'unresolved-conflict', 'orphan'} <= kinds


@pytest.mark.parametrize('change', [{'id':'../escape'}, {'status':'expert-approved'}, {'sources':[]}])
def test_reject_invalid_packet(tmp_path, change):
    with pytest.raises(ValueError): wiki.put(tmp_path/'wiki', packet(tmp_path, **change))


def test_reject_hash_and_holdout(tmp_path):
    p = packet(tmp_path); obj = json.loads(p.read_text())
    for field, value in [('sha256','bad'), ('usage','holdout')]:
        bad = json.loads(json.dumps(obj)); bad['sources'][0][field] = value
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError): wiki.put(tmp_path/'wiki', p)
    assert not (tmp_path/'wiki').exists()
