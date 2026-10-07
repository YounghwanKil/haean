import importlib.util
from pathlib import Path


def test_madmax_is_explicit_and_task_is_single_argument():
    path = Path(__file__).resolve().parents[1] / 'scripts/launch.py'
    spec = importlib.util.spec_from_file_location('launch_test', path)
    launch = importlib.util.module_from_spec(spec); spec.loader.exec_module(launch)
    task = '문항 제작; $(echo unsafe)'
    normal = launch.codex_command('codex', task)
    madmax = launch.codex_command('codex', task, True)
    flag = '--dangerously-bypass-approvals-and-sandbox'
    assert flag not in normal
    assert madmax.count(flag) == 1
    assert normal[-1] == madmax[-1] == '$haean ' + task
    assert normal[normal.index('-m') + 1] == 'gpt-6-astra'

    assert not any("trust_level" in x for x in normal)
    assert any("trust_level" in x and str(launch.ROOT) in x for x in madmax)
