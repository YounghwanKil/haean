"""Session-local terminal branding. No global terminal or Codex settings."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


@contextmanager
def clean_screen():
    """Keep the caller's shell intact while giving inline Codex a clean screen."""
    enabled = sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get('TERM') != 'dumb'
    if enabled:
        print('\033[?1049h\033[2J\033[H', end='', flush=True)
    try:
        yield
    finally:
        if enabled:
            print('\033[0m\033[?25h\033[?1049l', end='', flush=True)


def hud_status(env=None):
    env = os.environ if env is None else env
    tmux = shutil.which('tmux')
    reason = ('disabled_by_environment' if env.get('HAEAN_NO_TMUX') == '1' else
              'existing_tmux' if env.get('TMUX') else
              'tmux_not_installed' if not tmux else 'ready_for_interactive_terminal')
    return {'tmux': tmux, 'state': reason,
            'placement': 'separate bottom row below Codex status line',
            'interactive_terminal_required': True, 'color_enabled': 'NO_COLOR' not in env}


def hud_format(madmax=False, skill='haean', color=True):
    # These are labels, not claims about live agent activity or review quality.
    allowed = {'haean', 'haean-leet', 'haean-reading', 'haean-psat', 'haean-review',
               'haean-style', 'haean-layout', 'haean-exam', 'haean-evolve', 'haean-wiki'}
    skill = skill if skill in allowed else 'haean'
    logo = '#[fg=colour39,bold] ≋ haean #[default]' if color else ' ≋ haean '
    mode = 'MADMAX' if madmax else 'STANDARD'
    return logo + ' │ ' + mode + ' │ $' + skill + ' │ LEET · PSAT'


def run(command, env, root, banner, madmax=False, skill='haean'):
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and env.get('TERM') != 'dumb'
    tmux = shutil.which('tmux') if interactive and env.get('HAEAN_NO_TMUX') != '1' else None
    # Nested tmux keeps its owner's layout; use only our clean-screen wrapper.
    if not tmux or env.get('TMUX'):
        with clean_screen():
            banner(madmax=madmax, large=True, skill=skill)
            return subprocess.run(command, env=env).returncode
    return run_tmux(tmux, command, env, root, madmax, skill)


def run_tmux(tmux, command, env, root, madmax, skill):
    # A unique server guarantees we never change someone else's tmux sessions.
    base = [tmux, '-L', 'haean-' + uuid.uuid4().hex, '-f', '/dev/null']
    cols, rows = shutil.get_terminal_size((80, 24))
    with tempfile.TemporaryDirectory(prefix='haean-ui-') as folder:
        packet = Path(folder) / 'launch.json'
        result = Path(folder) / 'exit.json'
        ready = Path(folder) / 'ready'
        packet.write_text(json.dumps(dict(command=command, madmax=madmax, skill=skill)))
        packet.chmod(0o600)
        child = shlex.join([sys.executable, str(Path(__file__).resolve()), str(packet)])
        def call(*args, check=True):
            return subprocess.run(base + list(args), env=env, check=check, capture_output=True, text=True)
        try:
            call('new-session', '-d', '-s', 'haean', '-c', str(root), '-x', str(cols), '-y', str(max(rows, 8)), child)
            call('set-option', '-t', 'haean', 'status-position', 'bottom')
            call('set-option', '-t', 'haean', 'status-style', 'bg=default,fg=white')
            call('set-option', '-t', 'haean', 'status-format[0]',
                 hud_format(madmax, skill, color='NO_COLOR' not in env))
            ready.touch()
            attached = subprocess.run(base + ['attach-session', '-t', 'haean'], env=env)
            if result.exists():
                return json.loads(result.read_text())['returncode']
            # Detaching ends only this launcher-owned session; do not leave hidden Codex running.
            return attached.returncode or 130
        finally:
            call('kill-server', check=False)


def child_main(packet):
    from launch import banner
    data = json.loads(packet.read_text())
    deadline = time.monotonic() + 10
    while not packet.with_name('ready').exists():
        if time.monotonic() >= deadline:
            return 2
        time.sleep(0.05)
    banner(madmax=data['madmax'], large=True, skill=data['skill'])
    code = subprocess.run(data['command']).returncode
    packet.with_name('exit.json').write_text(json.dumps({'returncode': code}))
    return code


if __name__ == '__main__':
    raise SystemExit(child_main(Path(sys.argv[1])))
