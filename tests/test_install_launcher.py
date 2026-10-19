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


def test_typeset_launcher_preserves_literal_arguments_and_child_failure(tmp_path, monkeypatch):
    from types import SimpleNamespace
    module = load("launch")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    arguments = ["source with spaces.json", "--template", "$(literal).hwpx", "--strict"]
    monkeypatch.setattr(sys, "argv", ["haean", "typeset", *arguments])
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == 1
    assert calls == [([str(python), "-m", "haean_typeset", *arguments], {})]


@pytest.mark.parametrize("arguments", [["--help"], ["-h"], ["--check", "--help"]])
def test_doctor_help_never_starts_diagnostics_or_codex(arguments, monkeypatch, capsys):
    module = load("launch")
    monkeypatch.setattr(sys, "argv", ["haean", "doctor", *arguments])
    monkeypatch.setattr(module, "doctor", lambda **kw: pytest.fail("help must not run diagnostics"))
    monkeypatch.setattr(module.shutil, "which", lambda *a: pytest.fail("help must not find Codex"))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("help must not launch subprocesses"))
    assert module.main() == 0
    output = capsys.readouterr().out
    assert "사용법: haean doctor [--check]" in output and "종료 코드 1" in output


def test_invalid_doctor_option_does_not_fall_through_to_codex(monkeypatch):
    module = load("launch")
    monkeypatch.setattr(sys, "argv", ["haean", "doctor", "--unknown"])
    monkeypatch.setattr(module.shutil, "which", lambda *a: pytest.fail("invalid doctor option must not find Codex"))
    with pytest.raises(ValueError, match="사용법: haean doctor"):
        module.main()


@pytest.mark.parametrize("arguments", [
    ["--madmax", "--help"], ["--help", "--madmax"],
    ["--madmax", "setup", "--help"], ["--madmax", "status", "--help"],
    ["--madmax", "doctor", "--help"], ["skill", "psat", "--help"],
])
def test_global_madmax_with_help_never_probes_or_starts_codex(arguments, monkeypatch, capsys):
    module = load("launch")
    monkeypatch.setattr(sys, "argv", ["haean", *arguments])
    monkeypatch.setattr(module, "installation_state", lambda: pytest.fail("help must not probe installation"))
    monkeypatch.setattr(module.shutil, "which", lambda *a: pytest.fail("help must not find Codex"))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("help must not start a subprocess"))
    assert module.main() == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize("arguments", [
    ["--unknown"], ["--madmax", "--unknown"], ["작업 요청", "--unknown"],
    ["setup", "--unknown"], ["banner", "--unknown"], ["hud", "--unknown"],
    ["status", "--unknown"], ["setup-figures", "--unknown"],
    ["setup-layout", "--unknown"], ["setup-typeset", "--unknown"],
    ["skills", "--unknown"], ["skill", "psat", "--unknown"],
    ["track-exam", "--unknown"], ["--version", "--unknown"],
])
def test_invalid_options_fail_before_installation_login_or_model(arguments, monkeypatch):
    module = load("launch")
    monkeypatch.setattr(sys, "argv", ["haean", *arguments])
    monkeypatch.setattr(module, "installation_state", lambda: pytest.fail("invalid arguments must fail first"))
    monkeypatch.setattr(module.shutil, "which", lambda *a: pytest.fail("invalid arguments must not find Codex"))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: pytest.fail("invalid arguments must not start a subprocess"))
    with pytest.raises(ValueError, match="사용법|알 수 없는"):
        module.main()


def test_global_options_leave_delegated_and_literal_arguments_untouched():
    module = load("launch")
    assert module.launcher_arguments(["--madmax", "tools", "search", "--madmax"])[0] == ["tools", "search", "--madmax"]
    assert module.launcher_arguments(["typeset", "--unknown"])[0] == ["typeset", "--unknown"]
    args, madmax = module.launcher_arguments(["--", "--madmax", "--unknown"])
    assert not madmax
    assert module.request_arguments(args) == ["--madmax", "--unknown"]


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


def test_install_shows_path_fix_before_examples_and_absolute_command(tmp_path, monkeypatch, capsys):
    import shlex
    module = load("install")
    root, bin_dir = tmp_path / "repo", tmp_path / "bin with spaces"
    root.mkdir()
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: None)
    module.install(root, bin_dir, Path(sys.executable))
    output = capsys.readouterr().out
    assert output.index("export PATH=") < output.index("  haean --help")
    assert f"{shlex.quote(str(bin_dir / 'haean'))} --help" in output


@pytest.mark.parametrize("failure", ["packages", "skill_link", "humanizer_link", "revision"])
def test_partial_install_never_reaches_login_or_model(tmp_path, monkeypatch, failure):
    import venv
    module = load("launch")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    source = tmp_path / "skills/haean"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("fixture")
    links = tmp_path / ".agents/skills"
    links.mkdir(parents=True)
    (links / "haean").symlink_to(source)
    humanizer = tmp_path / "vendor/im-not-ai/codex/skills/humanize-korean"
    humanizer.mkdir(parents=True)
    (humanizer / "SKILL.md").write_text("fixture")
    (links / "humanize-korean").symlink_to(humanizer)
    monkeypatch.setattr(module, "humanizer_state", lambda: {"state": "mismatch" if failure == "revision" else "pinned"})
    if failure == "packages":
        # A real empty virtualenv reproduces interrupted pip installation even though
        # its Python and the visible skill files all exist.
        venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    else:
        monkeypatch.setattr(module, "installed_imports", lambda modules: True)
    if failure == "skill_link":
        (links / "haean").unlink()
    if failure == "humanizer_link":
        (links / "humanize-korean").unlink()
        (links / "humanize-korean").mkdir()
        (links / "humanize-korean/SKILL.md").write_text("unrelated skill")
    monkeypatch.setattr(module.shutil, "which", lambda *a: pytest.fail("partial install must fail before Codex/login"))
    monkeypatch.setattr(sys, "argv", ["haean", "문항을 검토해줘"])
    with pytest.raises(ValueError, match="haean setup"):
        module.main()


def test_setup_recovers_missing_pip_without_removing_existing_venv(tmp_path, monkeypatch):
    import venv
    from types import SimpleNamespace
    module = load("launch")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "skills").mkdir()
    humanizer = tmp_path / "vendor/im-not-ai/codex/skills/humanize-korean"
    humanizer.mkdir(parents=True)
    (humanizer / "SKILL.md").write_text("fixture")
    monkeypatch.setattr(module, "ensure_humanizer", lambda: {"state": "pinned"})
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    marker = tmp_path / ".venv/existing-package-marker"
    marker.write_text("preserve")
    real_run = subprocess.run
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[1:4] == ["-m", "pip", "install"]:
            # Keep dependency downloads out of this bootstrap regression test.
            return SimpleNamespace(returncode=0)
        return real_run(command, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", run)
    module.setup()
    module.setup()
    python = str(tmp_path / ".venv/bin/python")
    assert calls.count([python, "-m", "ensurepip", "--upgrade"]) == 1
    assert calls.count([python, "-m", "pip", "install", "-e", ".[dev]"]) == 2
    assert marker.read_text() == "preserve"
    assert real_run([python, "-m", "pip", "--version"], capture_output=True).returncode == 0


def test_pip_repair_refuses_python_outside_project_venv(tmp_path, monkeypatch):
    module = load("launch")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys._base_executable)
    real_run = subprocess.run
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return real_run(command, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(ValueError, match="패키지 설치를 중단"):
        module.ensure_project_pip(python)
    assert all("pip" not in command and "ensurepip" not in command for command in calls)


def test_failed_pip_repair_preserves_environment_and_explains_recovery(tmp_path, monkeypatch):
    import venv
    module = load("launch")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    python = tmp_path / ".venv/bin/python"
    real_run = subprocess.run
    def run(command, **kwargs):
        if "ensurepip" in command:
            raise subprocess.CalledProcessError(1, command)
        return real_run(command, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(ValueError, match="pip를 복구하지 못했습니다.*기존 .venv는 보존"):
        module.ensure_project_pip(python)
    assert python.is_file()


def test_recovery_commands_work_from_another_directory_with_spaces(tmp_path, monkeypatch, capsys):
    import json
    import shlex
    module = load("launch")
    root = tmp_path / "repo with spaces"
    root.mkdir()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module.shutil, "which", lambda *a: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["haean", "작업 요청"])
    with pytest.raises(ValueError) as error:
        module.main()
    for command in ("setup", "doctor"):
        assert shlex.join([str(root / "haean"), command]) in str(error.value)
    module.doctor()
    result = json.loads(capsys.readouterr().out)
    assert any(shlex.join([str(root / "haean"), "setup"]) in action for action in result["next_actions"])


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
