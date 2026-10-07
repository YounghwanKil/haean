import importlib.util
from pathlib import Path
import re


def test_welcome_card_width_and_plain_output():
    spec = importlib.util.spec_from_file_location('branding_test',Path('scripts/branding.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for color in [True, False]:
        lines=module.welcome_lines(80,color,True,'haean-psat')
        assert len(lines)==14
        assert {module.display_width(re.sub(r'\x1b\[[0-9;]*m','',s)) for s in lines}=={74}
        assert 'MADMAX' in '\n'.join(lines) and '$haean-psat' in '\n'.join(lines)
        if not color:assert '\x1b' not in '\n'.join(lines)
    narrow=module.welcome_lines(40,False)
    assert all(module.display_width(s)<=40 for s in narrow)
