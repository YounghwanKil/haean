"""Bounded, incremental project observation. Collection is not comprehension."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from .wiki_bridge import check_path, digest, repository_root, resolve_root

CHUNK = 1024 * 1024


def write_new(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def project_session(path, repo):
    try:
        with path.open('rb') as f: row = json.loads(f.readline(256 * 1024))
        cwd = Path(row['payload']['cwd']).resolve()
        return row.get('type') == 'session_meta' and (cwd == repo or cwd.is_relative_to(repo))
    except (OSError, ValueError, KeyError, TypeError): return False


def pending(folder):
    rows = [json.loads(p.read_text()) for p in (folder/'inbox').glob('*.json')
            if not (folder/'decisions'/p.name).exists()]
    return sorted(rows, key=lambda x: (x.get('observed_at', ''), x['id']), reverse=True)


def monitor(*, repo=None, sessions=None, limit=20):
    repo = Path(repo or repository_root()).resolve()
    if type(limit) is not int or not 1 <= limit <= 100: raise ValueError('limit은 1~100입니다')
    folder = repo/'data/wiki-memory'
    folder.mkdir(parents=True,exist_ok=True)
    for name in ['inbox','snapshots','decisions']: (folder/name).mkdir(exist_ok=True)
    lock=folder/'.monitor.lock'
    try: lock.mkdir()
    except FileExistsError: raise ValueError('위키 관측이 실행 중입니다. 중단된 실행인지 확인 후 .monitor.lock을 해제하세요')
    try:
        state_path=folder/'cursors.json'
        state=json.loads(state_path.read_text()) if state_path.exists() else {}
        candidates=[]; errors=[]; added=[]
        logroot=Path(sessions) if sessions is not None else Path.home()/'.codex/sessions'
        if logroot.is_dir():
            for p in logroot.rglob('*.jsonl'):
                if project_session(p,repo): candidates.append((p,'session'))
        if (repo/'runs').is_dir():
            for p in (repo/'runs').rglob('*'):
                if p.is_file() and (p.name in {'status.json','handoff.md','feedback.jsonl','wiki-use.jsonl'} or p.match('review-r*.json')):
                    if p.resolve().is_relative_to(repo): candidates.append((p,'work'))
        # Fixed read-only git operation; never execute commands found in logs.
        git=subprocess.run(['git','-C',str(repo),'log','-20','--format=%H %cI %s'],capture_output=True,text=True)
        if git.returncode==0:
            gitfile=folder/'git-observation.txt';gitfile.write_text(git.stdout,encoding='utf-8');candidates.append((gitfile,'git'))
        for p,kind in sorted(candidates,key=lambda x:(-x[0].stat().st_mtime,str(x[0]))):
            if len(added)>=limit: break
            try:
                p=check_path(p); key=str(p); prior=state.get(key,{})
                size=p.stat().st_size
                offset=prior.get('offset',0) if kind=='session' else 0
                history_offset=prior.get('history_offset',0)
                history_end=prior.get('history_end',0)
                history=(kind=='session' and size==offset and history_offset<history_end)
                if history: offset=history_offset
                if kind=='session' and not prior and size>CHUNK:
                    # First connection sees recent work immediately; older bytes remain
                    # an explicit backlog and are filled incrementally on quiet polls.
                    with p.open('rb') as tail:
                        tail.seek(size-CHUNK);tail.readline()
                        offset=tail.tell()
                    history_end=offset
                changed_prefix=False
                with p.open('rb') as f:
                    h=hashlib.sha256();left=offset
                    while left:
                        b=f.read(min(left,CHUNK))
                        if not b: break
                        h.update(b);left-=len(b)
                    expected=prior.get('history_prefix_sha256' if history else 'prefix_sha256')
                    if left or (offset and expected is not None and h.hexdigest()!=expected):
                        f.seek(0);offset=0;h=hashlib.sha256();changed_prefix=True
                        history=False;history_offset=0;history_end=0
                    if kind!='session' and size>CHUNK:
                        errors.append({'path':key,'issue':'oversized_work_file','bytes':size});continue
                    boundary=history_end if history else size
                    raw=f.read(min(CHUNK, max(0, boundary-offset)))
                    if kind=='session' and raw and not raw.endswith(b'\n'):
                        end=raw.rfind(b'\n')
                        if end<0:
                            errors.append({'path':key,'issue':'incomplete_or_oversized_session_line','offset':offset});continue
                        raw=raw[:end+1]
                    if not raw: continue
                    raw.decode('utf-8')  # Reject binary input and partial UTF-8.
                    h.update(raw);sha=digest(raw)
                    if kind!='session' and prior.get('sha256')==sha: continue
                    ident=digest((key+':'+str(offset)+':'+sha).encode())
                    snap=folder/'snapshots'/f'{ident}.txt';entry=folder/'inbox'/f'{ident}.json'
                    if not snap.exists(): snap.write_bytes(raw)
                    if digest(snap.read_bytes())!=sha: raise ValueError('관측 스냅샷이 변경되었습니다')
                    value={'id':ident,'kind':kind,'source':key,'offset':offset,'end':offset+len(raw),
                           'observed_size':size,'remaining_bytes':max(0,size-offset-len(raw)),
                           'source_rewritten':changed_prefix,'snapshot':str(snap),'sha256':sha,
                           'status':'unreviewed','semantic_reviewed':False,
                           'observed_at':datetime.now(timezone.utc).isoformat(),
                           'stream':'history' if history else 'recent',
                           'historical_unobserved_bytes':max(0,history_end-(offset+len(raw) if history else history_offset))}
                    if not entry.exists(): write_new(entry,value)
                    if history:
                        state[key]={**prior,'history_offset':offset+len(raw),'history_prefix_sha256':h.hexdigest()}
                    else:
                        state[key]={'offset':offset+len(raw),'prefix_sha256':h.hexdigest(),'sha256':sha,
                                    'history_offset':history_offset,'history_end':history_end,
                                    'history_prefix_sha256':prior.get('history_prefix_sha256')}
                    added.append(value)
            except (OSError,ValueError,KeyError) as exc:
                errors.append({'path':str(p),'issue':str(exc)})
        temp=folder/'cursors.tmp';temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.replace(state_path)
        queue=pending(folder)
        result={'project':str(repo),'new':added,'pending':queue[:limit],'pending_count':len(queue),'issues':errors,
                'bounded_limit':limit,'candidate_files':len(candidates),'background_service':False,
                'historical_backlog':[{'path':p,'bytes':s['history_end']-s.get('history_offset',0)}
                                      for p,s in state.items() if s.get('history_end',0)>s.get('history_offset',0)],
                'note':'관측한 변경분입니다. 읽기·종합·지침 개선 완료를 뜻하지 않습니다.'}
        (folder/'latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        return result
    finally: lock.rmdir()


def acknowledge(entry_id, outcome, pages, note, *, repo=None, root=None):
    repo=Path(repo or repository_root()).resolve();folder=repo/'data/wiki-memory'
    if len(entry_id or '')!=64 or any(c not in '0123456789abcdef' for c in entry_id): raise ValueError('잘못된 entry ID')
    if outcome not in {'integrated','local-only','deferred'} or not note or not note.strip(): raise ValueError('판단 종류와 이유가 필요합니다')
    entry=json.loads((folder/'inbox'/f'{entry_id}.json').read_text())
    snap=check_path(entry['snapshot'])
    if not snap.is_relative_to(folder/'snapshots') or digest(snap.read_bytes())!=entry['sha256']: raise ValueError('관측 스냅샷 연결이 변경됐습니다')
    if outcome=='integrated':
        from . import wiki
        if not pages: raise ValueError('통합한 위키 페이지를 명시하세요')
        wiki_root=resolve_root(root,repo=repo)
        for ident in pages:
            wiki.page_id(ident);meta=json.loads((wiki_root/'pages'/f'{ident}.json').read_text())
            if not any(Path(s['path']).resolve()==snap and s['sha256']==entry['sha256'] for s in meta['sources']):
                raise ValueError('통합 페이지에 해당 관측 스냅샷을 출처로 연결하세요')
    decision={'id':entry_id,'outcome':outcome,'pages':pages or [],'note':note,'origin':'agent_or_user_recorded','expert_verified':False}
    # A deferred finding remains pending; it must not disappear from the next review.
    dest=(folder/'decisions'/f'{entry_id}.json') if outcome!='deferred' else (folder/f'deferred-{entry_id}.json')
    if dest.exists():
        if json.loads(dest.read_text()) == decision:
            return decision
        if outcome != 'deferred':
            raise ValueError('기존 판단을 덮어쓰지 않습니다')
        # Preserve earlier deferrals; the entry remains pending.
        dest=folder/f'deferred-{entry_id}-{digest(json.dumps(decision,sort_keys=True).encode())}.json'
    if not dest.exists():
        write_new(dest,decision)
    return decision
