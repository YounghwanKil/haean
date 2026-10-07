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
