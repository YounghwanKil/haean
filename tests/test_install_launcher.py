import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_conflict_and_uninstall_preserve_unrelated_files(tmp_path, monkeypatch):
    module = load("install")
    root, bin_dir = tmp_path / "repo", tmp_path / "bin"
    root.mkdir(); bin_dir.mkdir()
    target = bin_dir / "haean"; target.write_text("other launcher")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("must refuse before setup"))
    for uninstall in (False, True):
        with pytest.raises(ValueError): module.install(root, bin_dir, Path(sys.executable), uninstall=uninstall)
    assert target.read_text() == "other launcher"
    target.unlink(); target.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError): module.install(root, bin_dir, Path(sys.executable))


def test_wrapper_runs_from_other_cwd_with_spaces_and_is_reversible(tmp_path, monkeypatch):
    module = load("install")
    root = tmp_path / "repo with spaces"; scripts = root / "scripts"; scripts.mkdir(parents=True)
    (scripts / "launch.py").write_text("import sys; print('|'.join(sys.argv[1:]))")
    data = root / "data"; data.mkdir(); (data / "keep.txt").write_text("private fixture")
    bin_dir = tmp_path / "bin with spaces"
    # This fixture exercises the OS wrapper and setup invocation, not the real dependency installer.
    module.install(root, bin_dir, Path(sys.executable)); module.install(root, bin_dir, Path(sys.executable))
    result = subprocess.run([str(bin_dir / "haean"), "two words", "$(no shell expansion)"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "two words|$(no shell expansion)"
    module.install(root, bin_dir, Path(sys.executable), uninstall=True)
    assert not (bin_dir / "haean").exists() and (data / "keep.txt").read_text() == "private fixture"


def test_status_does_not_count_assembled_views_as_new_reviews(tmp_path, monkeypatch, capsys):
    module = load("launch"); monkeypatch.setattr(module, "ROOT", tmp_path)
    for path in ["runs/one/status.json", "runs/exam/items/01/status.json"]:
        p=tmp_path/path; p.parent.mkdir(parents=True); p.write_text('{"state":"awaiting_human_review"}')
    module.status()
    output=capsys.readouterr().out
    assert "사람 검토 대기: 1묶음" in output
    assert "실행 중 여부" in output


def test_current_exam_selection_preserves_artifacts_and_detects_changed_snapshot(tmp_path, monkeypatch, capsys):
    import json
    module = load('launch'); monkeypatch.setattr(module, 'ROOT', tmp_path)
    result = {'exam':'leet','subject':'추리논증','requested':40,'written':40,
              'errors':[],'human_approved':False,'layout_verified':False}
    for name in ['v1','v2']:
        run = tmp_path/'runs'/name;run.mkdir(parents=True)
        (run/'assembled.json').write_text(json.dumps(result))
    old = (tmp_path/'runs/v1/assembled.json').read_bytes()
    module.track_exam('runs/v1');module.track_exam(str(tmp_path/'runs/v2'))
    assert (tmp_path/'runs/v1/assembled.json').read_bytes()==old
    registry = json.loads((tmp_path/'runs/current-exams.json').read_text())
    assert len(registry['exams'])==1
    module.status();text=capsys.readouterr().out
    assert 'runs/v2' in text and '사람 승인: 미확인' in text
    result['errors']=['recheck required']
    (tmp_path/'runs/v2/assembled.json').write_text(json.dumps(result))
    module.status();text=capsys.readouterr().out
    assert '지정 후 조립 기록이 변경됨' in text and '조립 당시 오류 1건' in text


def test_current_exam_rejects_outside_runs_and_survives_missing_output(tmp_path, monkeypatch, capsys):
    import json
    module=load('launch');monkeypatch.setattr(module,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='runs/'):
        module.track_exam('../another-project')
    run=tmp_path/'runs/example';run.mkdir(parents=True)
    source=run/'assembled.json';source.write_text(json.dumps({'exam':'psat7','subject':'자료해석','requested':25,'written':1,'errors':['missing']}))
    module.track_exam('runs/example')
    source.unlink()
    module.status()
    assert '현재 회차 기록 확인 필요' in capsys.readouterr().out


def test_doctor_missing_install_has_actions_and_does_not_create_database(tmp_path, monkeypatch, capsys):
    import json
    module=load("launch"); monkeypatch.setattr(module,"ROOT",tmp_path)
    (tmp_path/"skills").mkdir()
    monkeypatch.setattr(module.shutil,"which",lambda _: None)
    assert module.doctor(strict=True)==1
    result=json.loads(capsys.readouterr().out)
    assert not result['core_ready'] and result['runtime_role_loading']=='not_verified'
    assert result['sources']['state']=='not_imported'
    assert any('setup-figures' in action for action in result['next_actions'])
    assert not (tmp_path/'data').exists()


def test_source_status_counts_roles_without_rewriting_sources(tmp_path, monkeypatch):
    import sqlite3
    module=load("launch"); monkeypatch.setattr(module,"ROOT",tmp_path)
    path=tmp_path/'data/corpus.sqlite';path.parent.mkdir()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE records(exam TEXT, role TEXT)')
        db.executemany('INSERT INTO records VALUES (?,?)',[('leet','example'),('psat5','metadata')])
    before=path.read_bytes()
    result=module.source_status()
    assert result['records']==2 and len(result['groups'])==2
    assert path.read_bytes()==before


def test_humanizer_setup_checks_existing_revision_without_overwriting_edits(monkeypatch):
    module=load('launch')
    states=iter([{'state':'mismatch','expected':'pinned','actual':'old'},
                 {'state':'pinned','expected':'pinned','actual':'pinned'}])
    monkeypatch.setattr(module,'humanizer_state',lambda:next(states))
    calls=[]
    monkeypatch.setattr(module.subprocess,'run',lambda command,**kw:calls.append(command))
    assert module.ensure_humanizer()['state']=='pinned'
    assert calls==[['git','submodule','update','--init','--depth','1','--','vendor/im-not-ai']]
    calls.clear()
    monkeypatch.setattr(module,'humanizer_state',lambda:{'state':'modified'})
    with pytest.raises(ValueError,match='로컬 수정'):module.ensure_humanizer()
    assert not calls
    monkeypatch.setattr(module,'humanizer_state',lambda:{'state':'pinned'})
    assert module.ensure_humanizer()['state']=='pinned' and not calls


def test_humanizer_revision_distinguishes_dirty_and_wrong_commit(tmp_path,monkeypatch):
    from types import SimpleNamespace
    module=load('launch');monkeypatch.setattr(module,'ROOT',tmp_path)
    (tmp_path/'.git').mkdir();vendor=tmp_path/'vendor/im-not-ai';vendor.mkdir(parents=True);(vendor/'.git').write_text('fixture')
    def responses(actual,dirty):
        values=iter(['160000 abc123 0\tvendor/im-not-ai\n',actual,dirty])
        monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=next(values)))
    responses('abc123\n','')
    assert module.humanizer_state()['state']=='pinned'
    responses('other\n','')
    assert module.humanizer_state()['state']=='mismatch'
    responses('abc123\n',' M SKILL.md\n')
    assert module.humanizer_state()['state']=='modified'


def test_reading_current_exam_tracks_content_without_claiming_approval(tmp_path, monkeypatch, capsys):
    import json
    module = load('launch'); monkeypatch.setattr(module, 'ROOT', tmp_path)
    run = tmp_path/'runs/reading'; run.mkdir(parents=True)
    book = {'passages': [{'questions': [{'number': 1, 'stem': 'original'}]}]}
    path = run/'book.json'; path.write_text(json.dumps(book))
    before = path.read_bytes()
    module.track_exam('runs/reading'); module.status()
    text = capsys.readouterr().out
    assert '언어이해 / 1문항' in text and '1지문' in text
    assert '회차 지정은 승인 증거가 아닙니다' in text
    assert before == path.read_bytes()
    book['passages'][0]['questions'][0]['stem'] = 'revised'
    path.write_text(json.dumps(book)); module.status()
    assert '지정 후 문항 내용이 변경됨' in capsys.readouterr().out
    book['passages'][0]['questions'].append({'number': 1})
    path.write_text(json.dumps(book))
    with pytest.raises(ValueError, match='연속'):
        module.track_exam('runs/reading')
