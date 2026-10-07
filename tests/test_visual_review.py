import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from haean.codex_runtime import CodexProvider
from haean.models import StrictModel
from haean.visual_review import review_images
from haean.validation import public_item
from test_figures import chart


class Result(StrictModel):
    status: str


def test_cli_attaches_real_pngs_and_preserves_blind_image_provenance(tmp_path, monkeypatch, draft):
    pytest.importorskip('matplotlib')
    from PIL import Image
    draft.items[0].figures=[chart([10,20],placement='option_1',layout_note='PRIVATE ANSWER MEMO')]
    payload={'items':[public_item(draft.items[0])]}
    original=json.dumps(payload,sort_keys=True)
    monkeypatch.setattr('haean.codex_runtime.shutil.which',lambda _: '/codex')
    image_bytes=[]
    def run(command,**kwargs):
        if command[1]=='login':return SimpleNamespace(returncode=0,stdout='ChatGPT',stderr='')
        path=Path(command[command.index('--image')+1])
        with Image.open(path) as image:assert image.width>500 and image.height>300
        image_bytes.append(path.read_bytes())
        assert 'PRIVATE ANSWER MEMO' not in kwargs['input']
        assert '"answer"' not in kwargs['input'] and 'rendered_images' in kwargs['input']
        Path(command[command.index('-o')+1]).write_text('{"status":"reviewed"}')
        return SimpleNamespace(returncode=0,stdout='{"type":"turn.completed","usage":{"output_tokens":3}}',stderr='')
    monkeypatch.setattr('haean.codex_runtime.subprocess.run',run)
    provider=CodexProvider(trace_dir=tmp_path/'trace')
    assert provider.call('blind','Solve only the public item.',payload,Result).status=='reviewed'
    trace=json.loads((tmp_path/'trace/01-blind.input.json').read_text())
    assert trace['visual_scope']=='rendered_png_only'
    entry=trace['images'][0]
    assert entry['sha256']==hashlib.sha256(image_bytes[0]).hexdigest()
    assert (tmp_path/'trace/01-blind.figures'/entry['file']).read_bytes()==image_bytes[0]
    assert json.dumps(payload,sort_keys=True)==original


def test_render_failure_never_silently_uses_text_only(tmp_path,monkeypatch):
    monkeypatch.setattr('haean.codex_runtime.shutil.which',lambda _: '/codex')
    def run(command,**kwargs):
        assert command[1]=='login', 'No model call is allowed after failed rendering'
        return SimpleNamespace(returncode=0,stdout='ChatGPT',stderr='')
    monkeypatch.setattr('haean.codex_runtime.subprocess.run',run)
    def fail(*args):raise ImportError('matplotlib missing')
    monkeypatch.setattr('haean.visual_review.review_images',fail)
    provider=CodexProvider(trace_dir=tmp_path)
    with pytest.raises(RuntimeError,match='렌더 실패'):provider.call('blind','solve',{'items':[]},Result)
    assert json.loads((tmp_path/'01-blind.image-error.json').read_text())['model_called'] is False


def test_generate_never_attaches_retrieval_paths_or_creates_figures(tmp_path):
    paths,manifest=review_images('generate',{'items':[{'figures':['not an image']}],
                                          'references':[{'path':'/private/source.png'}]},tmp_path/'images')
    assert paths==manifest==[] and not (tmp_path/'images').exists()


def test_missing_korean_font_fails_instead_of_rendering_tofu(tmp_path, monkeypatch):
    pytest.importorskip('matplotlib')
    from haean import figures
    from matplotlib import font_manager
    monkeypatch.setattr(figures, '__file__', str(tmp_path/'src/haean/figures.py'))
    def missing(*args, **kwargs):
        assert kwargs.get('fallback_to_default') is False
        raise ValueError('Font not installed')
    monkeypatch.setattr(font_manager, 'findfont', missing)
    with pytest.raises(ValueError, match='한국어 그래프 폰트'):
        figures.configure_font(chart([10,20], title='분기별 지수'))


def test_latin_chart_needs_no_team_or_korean_font(tmp_path, monkeypatch):
    pytest.importorskip('matplotlib')
    from haean import figures
    monkeypatch.setattr(figures, '__file__', str(tmp_path/'src/haean/figures.py'))
    font = figures.configure_font(chart([10,20]))
    assert font['family']=='DejaVu Sans' and Path(font['path']).is_file()


def test_editor_images_exclude_nonprinted_memos_and_group_argument_choices(tmp_path, draft):
    pytest.importorskip('matplotlib')
    import shutil
    if not shutil.which('dot'):pytest.skip('Graphviz required')
    from test_figures import graph
    draft.items[0].figures=[graph().model_copy(update={'id':f'g{n}','placement':f'option_{n}',
                            'layout_note':'INTERNAL','note':'LEGACY PRIVATE'}) for n in range(1,6)]
    paths,manifest=review_images('editor',{'draft':draft.model_dump()},tmp_path)
    assert len(paths)==1 and manifest[0]['placements']==[f'option_{n}' for n in range(1,6)]
    for receipt in tmp_path.glob('item-*/*.json'):
        data=receipt.read_text();assert 'INTERNAL' not in data and 'LEGACY PRIVATE' not in data
