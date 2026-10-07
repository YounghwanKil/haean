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
    assert normal.count("--no-alt-screen") == madmax.count("--no-alt-screen") == 1
    assert flag not in normal
    assert madmax.count(flag) == 1
    assert normal[-1] == madmax[-1] == '$haean ' + task
    assert normal[normal.index('-m') + 1] == 'gpt-6-astra'


def test_skill_catalog_and_direct_dispatch(monkeypatch, capsys, tmp_path):
    import json
    import pytest
    from types import SimpleNamespace
    path=Path(__file__).resolve().parents[1]/'scripts/launch.py'
    spec=importlib.util.spec_from_file_location('launch_catalog_test',path)
    launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
    catalog=launch.skill_catalog()
    assert len(catalog)==10 and all(s['discovered'] for s in catalog)
    assert len({s['short_description'] for s in catalog})==10
    assert all(s['default_prompt'].startswith('$'+s['name']+' ') for s in catalog)
    assert launch.select_skill('psat')['name']=='haean-psat'
    assert launch.select_skill('$haean-reading')['name']=='haean-reading'
    with pytest.raises(ValueError):launch.select_skill('../../outside')
    # Dispatch fixture is independent of the developer's installed virtualenv.
    (tmp_path/'skills').symlink_to(launch.ROOT/'skills',target_is_directory=True)
    (tmp_path/'.agents').symlink_to(launch.ROOT/'.agents',target_is_directory=True)
    (tmp_path/'.venv/bin').mkdir(parents=True)
    (tmp_path/'.venv/bin/python').touch()
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0,stdout='ChatGPT',stderr='')
    monkeypatch.setattr(launch.subprocess,'run',run)
    monkeypatch.setattr(launch.shutil,'which',lambda _: '/codex')
    monkeypatch.setattr(launch.sys,'argv',['haean','skills','psat'])
    assert launch.main()==0 and not calls
    assert '$haean-psat' in capsys.readouterr().out
    request='검토; $(echo must-remain-literal)'
    monkeypatch.setattr(launch.sys,'argv',['haean','--madmax','skill','psat',request])
    assert launch.main()==0
    assert calls[-1][-1]=='$haean-psat '+request
    assert calls[-1].count('--dangerously-bypass-approvals-and-sandbox')==1
