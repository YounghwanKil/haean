import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    spec = importlib.util.spec_from_file_location('haean_terminal_test', Path('scripts/terminal_ui.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clean_screen_restores_shell_on_failure(monkeypatch, capsys):
    ui = load()
    monkeypatch.setattr(ui.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(ui.sys.stdout, 'isatty', lambda: True)
    monkeypatch.setenv('TERM', 'xterm-256color')
    with pytest.raises(RuntimeError):
        with ui.clean_screen():
            print('HAEAN banner then Codex')
            raise RuntimeError('child failed')
    text = capsys.readouterr().out
    assert text.startswith('\033[?1049h\033[2J\033[H')
    assert text.index('HAEAN') < text.index('\033[?1049l')
    assert text.endswith('\033[?1049l')


def test_tmux_server_is_isolated_and_cleaned_when_attach_fails(monkeypatch, tmp_path):
    ui = load()
    calls = []
    prompt = '$haean text; $(touch should-not-run)'
    command = ['codex', '--no-alt-screen', prompt]
    def fake_run(argv, **kwargs):
        calls.append(argv)
        if 'new-session' in argv:
            import shlex
            packet = Path(shlex.split(argv[-1])[-1])
            assert json.loads(packet.read_text())['command'] == command
            assert packet.stat().st_mode & 0o777 == 0o600
        if 'attach-session' in argv:
            raise OSError('synthetic attach failure')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(ui.subprocess, 'run', fake_run)
    with pytest.raises(OSError):
        ui.run_tmux('tmux', command, {}, tmp_path, True, 'haean')
    assert calls[-1][-1] == 'kill-server'
    assert all(c[:5] == calls[0][:5] for c in calls)
    assert calls[0][1] == '-L' and calls[0][2].startswith('haean-')
    assert any('colour39' in c[-1] and 'MADMAX' in c[-1] for c in calls)
    assert all(prompt not in ' '.join(c) for c in calls)
