"""Exercise the repository shell entry point without the developer's Python/PATH."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[1]


def fake_python(path, label, version_ok=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '#!/bin/sh\n'
        f'if [ "$1" = "-c" ]; then exit {0 if version_ok else 1}; fi\n'
        f'printf "%s\\n" {shlex.quote(label)}\n'
        f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    path.chmod(0o755)


@pytest.mark.parametrize("selection", ["override", "venv", "fallback"])
def test_repository_entry_selects_python_and_preserves_arguments(tmp_path, selection):
    root = tmp_path / "repo with spaces"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "haean", root / "haean")
    (scripts / "launch.py").write_text("import json, sys; print(json.dumps(sys.argv[1:]))")
    bin_dir = tmp_path / "bin with spaces"
    fake_python(bin_dir / "python3", "fallback")
    if selection != "fallback":
        fake_python(root / ".venv/bin/python", "venv")
    env = dict(os.environ, PATH=str(bin_dir) + ":/usr/bin:/bin")
    env.pop("HAEAN_PYTHON", None)
    if selection == "override":
        python = bin_dir / "explicit python"
        fake_python(python, "override")
        env["HAEAN_PYTHON"] = str(python)
    args = ["skill", "psat", "two words", "$(touch must-not-run)", "quote'\"literal"]
    result = subprocess.run([str(root / "haean"), *args], cwd=tmp_path, env=env,
                            capture_output=True, text=True, check=True)
    chosen, arguments = result.stdout.splitlines()
    assert chosen == selection
    assert json.loads(arguments) == args
    assert not (tmp_path / "must-not-run").exists()


def test_repository_entry_explains_unsupported_python_before_loading_launcher(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy2(ROOT / "haean", root / "haean")
    old_python = tmp_path / "old python"
    fake_python(old_python, "must not run launcher", version_ok=False)
    result = subprocess.run([str(root / "haean"), "--help"],
                            env=dict(os.environ, HAEAN_PYTHON=str(old_python)),
                            capture_output=True, text=True)
    assert result.returncode == 2 and not result.stdout
    assert "Python 3.11" in result.stderr and "HAEAN_PYTHON=" in result.stderr
    assert "Traceback" not in result.stderr


def test_packaged_helper_does_not_shadow_installed_launcher():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["scripts"] == {"haean-tool": "haean.cli:main"}
