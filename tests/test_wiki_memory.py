import json
from pathlib import Path

import pytest

from haean import wiki, wiki_memory as M
from haean.wiki_bridge import digest


def session(folder, repo, name="session.jsonl"):
    folder.mkdir(exist_ok=True)
    path=folder/name
    path.write_text(json.dumps({"type":"session_meta","payload":{"cwd":str(repo)}})+"\n"+
                    json.dumps({"type":"response_item","payload":{"text":"synthetic user request"}})+"\n")
    return path


def setup(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    logs=tmp_path/'logs'
    source=session(logs,repo)
    session(logs,tmp_path/'unrelated',name="other.jsonl")
    return repo,logs,source


def test_project_scope_incremental_append_and_no_semantic_claim(tmp_path):
    repo,logs,source=setup(tmp_path)
    first=M.monitor(repo=repo,sessions=logs)
    assert len(first['new'])==1 and first['new'][0]['source']==str(source)
    assert first['new'][0]['semantic_reviewed'] is False
    old=Path(first['new'][0]['snapshot']).read_bytes()
    assert not M.monitor(repo=repo,sessions=logs)['new']
    with source.open('a') as f:f.write('{"type":"new","text":"next evidence"}\n')
    next_=M.monitor(repo=repo,sessions=logs)
    assert len(next_['new'])==1 and next_['new'][0]['offset']==len(old)
    assert Path(next_['new'][0]['snapshot']).read_text()=='{"type":"new","text":"next evidence"}\n'
    assert Path(first['new'][0]['snapshot']).read_bytes()==old
    assert next_['pending_count']==2


def test_rewritten_prefix_restarts_and_incomplete_tail_waits(tmp_path):
    repo,logs,source=setup(tmp_path)
    M.monitor(repo=repo,sessions=logs)
    source.write_text(source.read_text().replace('synthetic user request','changed evidence'))
    result=M.monitor(repo=repo,sessions=logs)['new'][0]
    assert result['source_rewritten'] and result['offset']==0
    with source.open('a') as f:f.write('{"text":"unfinished')
    assert not M.monitor(repo=repo,sessions=logs)['new']
    with source.open('a') as f:f.write('"}\n')
    result=M.monitor(repo=repo,sessions=logs)['new'][0]
    assert Path(result['snapshot']).read_text()=='{"text":"unfinished"}\n'


def test_large_session_observes_recent_first_then_fills_history(tmp_path,monkeypatch):
    repo,logs,source=setup(tmp_path)
    monkeypatch.setattr(M,'CHUNK',1024)
    with source.open('a') as f:
        for i in range(60):f.write(json.dumps({'text':f'event {i} '+('x'*40)})+'\n')
    raw=source.read_bytes();pieces=[]
    first=M.monitor(repo=repo,sessions=logs)['new'][0];pieces.append(first)
    assert first['offset']>0 and first['historical_unobserved_bytes']==first['offset']
    assert 'event 59' in Path(first['snapshot']).read_text()
    for _ in range(10):
        result=M.monitor(repo=repo,sessions=logs);pieces.extend(result['new'])
        if not result['historical_backlog']:break
    assert not result['historical_backlog']
    assert b''.join(Path(e['snapshot']).read_bytes() for e in sorted(pieces,key=lambda e:e['offset']))==raw
    assert not M.monitor(repo=repo,sessions=logs)['new']


def test_oversized_final_session_row_is_reported_not_silently_skipped(tmp_path,monkeypatch):
    repo,logs,source=setup(tmp_path)
    monkeypatch.setattr(M,'CHUNK',1024)
    with source.open('a') as f:f.write(json.dumps({'text':'x'*2048})+'\n')
    result=M.monitor(repo=repo,sessions=logs)
    assert not result['new']
    assert any(x['issue']=='incomplete_or_oversized_session_tail' for x in result['issues'])

def test_bounded_work_observation_preserves_overflow_and_reports_large_file(tmp_path):
    repo,logs,source=setup(tmp_path)
    (repo/'runs/a').mkdir(parents=True);(repo/'runs/a/handoff.md').write_text('small synthetic handoff')
    (repo/'runs/a/status.json').write_text('x'*(M.CHUNK+1))
    first=M.monitor(repo=repo,sessions=logs,limit=1)
    assert len(first['new'])==1
    second=M.monitor(repo=repo,sessions=logs,limit=1)
    assert len(second['new'])==1 and second['pending_count']==2
    assert any(x['issue']=='oversized_work_file' for x in first['issues']+second['issues'])


def test_ack_requires_actual_wiki_citation_and_deferred_remains_pending(tmp_path):
    repo,logs,source=setup(tmp_path);entry=M.monitor(repo=repo,sessions=logs)['new'][0]
    M.acknowledge(entry['id'],'deferred',None,'읽기 보류',repo=repo)
    M.acknowledge(entry['id'],'deferred',None,'다음 회차에 재검토',repo=repo)
    assert len(M.pending(repo/'data/wiki-memory'))==1
    with pytest.raises(ValueError):M.acknowledge(entry['id'],'integrated',[],'통합',repo=repo)
    packet=dict(id="lesson",title="합성",summary="합성",body="합성 기록 [1]",status="model-synthesis",links=[],
                sources=[dict(path=entry['snapshot'],sha256=entry['sha256'],locator="bytes 0:end",usage="development")])
    p=repo/'packet.json';p.write_text(json.dumps(packet));root=repo/'data/wiki';wiki.put(root,p)
    result=M.acknowledge(entry['id'],'integrated',['lesson'],'실제 읽은 합성 기록',repo=repo)
    assert result['expert_verified'] is False
    assert not M.pending(repo/'data/wiki-memory')
    assert M.acknowledge(entry['id'],'integrated',['lesson'],'실제 읽은 합성 기록',repo=repo)==result
    with pytest.raises(ValueError):M.acknowledge(entry['id'],'local-only',[],'판정 변경',repo=repo)


def test_sealed_work_and_modified_snapshot_cannot_enter_ack(tmp_path):
    repo,logs,source=setup(tmp_path)
    hold=repo/'runs/holdout';hold.mkdir(parents=True);(hold/'handoff.md').write_text('sealed')
    result=M.monitor(repo=repo,sessions=logs)
    assert any('holdout' in x['issue'] for x in result['issues'])
    entry=result['new'][0];Path(entry['snapshot']).write_text('tampered')
    with pytest.raises(ValueError,match='변경'):
        M.acknowledge(entry['id'],'local-only',[],'skip',repo=repo)
