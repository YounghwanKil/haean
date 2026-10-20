import hashlib
import json
from pathlib import Path
import pytest
from haean import wiki
from haean import wiki_bridge as W


def make_page(tmp_path, ident='lesson', **kwargs):
    source=tmp_path/'source.txt'
    if not source.exists(): source.write_text('synthetic development evidence')
    root=tmp_path/'knowledge'
    packet=dict(id=ident,title='합성 검토 원칙',summary='합성 원칙',body='WIKI_SENTINEL_ANNOTATION [1]',status='model-synthesis',
                sources=[dict(path=str(source),sha256=W.digest(source.read_bytes()),locator='line 1',usage='development')],links=[])
    packet.update(kwargs)
    p=tmp_path/'packet.json';p.write_text(json.dumps(packet));wiki.put(root,p)
    return root,source


def attach(tmp_path, **kwargs):
    root,source=make_page(tmp_path,**kwargs)
    run=tmp_path/'run';run.mkdir(exist_ok=True)
    result=W.snapshot(root,['lesson'],run/'wiki-context.json',track='psat_data',grade=5,reason='이 과목에 적용할 검토 원칙')
    return root,source,run,result


def test_two_repos_share_same_wiki_without_copying_sources(tmp_path):
    root,source=make_page(tmp_path)
    for name in ['repo-a','repo-b']:
        repo=tmp_path/name
        W.link(root,repo=repo)
        assert W.resolve_root(repo=repo)==root.resolve()
        assert not (repo/'data/wiki').exists()
    p=tmp_path/'packet.json';obj=json.loads(p.read_text());obj['body']='새로운 합성 지식 [1]';p.write_text(json.dumps(obj))
    wiki.put(W.resolve_root(repo=tmp_path/'repo-b'),p)
    assert wiki.search(W.resolve_root(repo=tmp_path/'repo-a'),'새로운')
    assert list((root/'history/lesson').glob('*/lesson.md'))
    assert source.read_text()=='synthetic development evidence'


def test_writer_snapshot_is_pinned_while_blind_is_rejected_before_read(tmp_path):
    root,source,run,result=attach(tmp_path)
    original=W.authoring_instructions('RULES',run,track='psat_data',grade=5,stage='generate')
    assert 'WIKI_SENTINEL_ANNOTATION' in original
    p=tmp_path/'packet.json';obj=json.loads(p.read_text());obj['body']='NEW_PAGE_VERSION [1]';p.write_text(json.dumps(obj));wiki.put(root,p)
    current=W.authoring_instructions('RULES',run,track='psat_data',grade=5,stage='revise')
    assert 'WIKI_SENTINEL_ANNOTATION' in current and 'NEW_PAGE_VERSION' not in current
    receipt=(run/'wiki-use.jsonl').read_text()
    for stage in ['blind','editor','evaluate']:
        with pytest.raises(ValueError): W.authoring_instructions('RULES',run,track='psat_data',grade=5,stage=stage)
    assert (run/'wiki-use.jsonl').read_text()==receipt
    assert json.loads(receipt.splitlines()[0])['snapshot_sha256']==result['sha256']


def test_no_attachment_keeps_existing_behavior(tmp_path):
    before = set(tmp_path.iterdir())
    assert W.authoring_instructions('RULES',tmp_path,track='psat_data',grade=5,stage='generate')=='RULES'
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize('track,grade',[('psat_data',7),('psat_verbal',5),('leet_reasoning',None)])
def test_scope_mismatch_stops_before_model(tmp_path,track,grade):
    _,_,run,_=attach(tmp_path)
    with pytest.raises(ValueError,match='과목·급수'):
        W.authoring_instructions('RULES',run,track=track,grade=grade,stage='generate')
    assert not (run/'wiki-use.jsonl').exists()


def test_stale_sources_require_review_not_hash_replacement(tmp_path):
    root,source,run,_=attach(tmp_path)
    source.write_text('changed source')
    with pytest.raises(ValueError,match='출처'):
        W.authoring_instructions('RULES',run,track='psat_data',grade=5,stage='generate')
    with pytest.raises(ValueError,match='출처'):
        W.snapshot(root,['lesson'],run/'wiki-context.json',track='psat_data',grade=5,reason='reason')


def test_snapshot_tamper_and_overwrite_rejected(tmp_path):
    root,_,run,_=attach(tmp_path)
    with pytest.raises(FileExistsError):W.snapshot(root,['lesson'],run/'wiki-context.json',track='psat_data',grade=5,reason='reason')
    p=run/'wiki-context.json';obj=json.loads(p.read_text());obj['pages'][0]['text']='changed';p.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='변경'):W.authoring_instructions('RULES',run,track='psat_data',grade=5,stage='generate')


def test_conflicted_page_cannot_be_used_as_consensus(tmp_path):
    with pytest.raises(ValueError,match='충돌'): attach(tmp_path,status='conflicted')


def test_holdout_paths_blocked_even_with_self_declared_development(tmp_path):
    root,source=make_page(tmp_path)
    hold=tmp_path/'holdout';hold.mkdir();file=hold/'source.txt';file.write_text(source.read_text())
    p=tmp_path/'packet.json';obj=json.loads(p.read_text());obj['sources'][0]['path']=str(file);p.write_text(json.dumps(obj));wiki.put(root,p)
    run=tmp_path/'run';run.mkdir()
    with pytest.raises(ValueError,match='holdout'):W.snapshot(root,['lesson'],run/'wiki-context.json',track='psat_data',grade=5,reason='reason')


def test_cli_uses_link_and_snapshots_explicit_pages(tmp_path,monkeypatch,capsys):
    from haean.cli import main
    root,_=make_page(tmp_path);repo=tmp_path/'repo';monkeypatch.setattr(W,'repository_root',lambda:repo)
    for args in [['link','--root',str(root)],['search','--query','검토'],['status']]:
        monkeypatch.setattr('sys.argv',['haean-tool','wiki',*args]);main()
    assert W.resolve_root()==root.resolve()
    assert str(root) in capsys.readouterr().out
