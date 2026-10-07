import json
import pytest
from haean.models import Figure


def graph(**overrides):
    return Figure.model_validate(dict(id='g1', placement='passage', kind='argument',
        title='Argument', x_label='', y_label='', categories=[], series=[],
        nodes=[{'id':str(i),'label':str(i)} for i in range(1,4)],
        edges=[{'sources':['1','2'],'target':'3','relation':'support'}], note='Joint support', **overrides))


def test_graph_rejects_dangling_node():
    data=graph().model_dump()
    data['edges'][0]['target']='missing'
    with pytest.raises(ValueError,match='노드 참조'):
        Figure.model_validate(data)


def test_render_joint_graph_and_reject_cycle(tmp_path):
    pytest.importorskip('matplotlib')
    import shutil
    if not shutil.which('dot'): pytest.skip('Graphviz layout extra is not installed')
    from PIL import Image
    from haean.figures import render
    figure=graph()
    out=render(figure,tmp_path/'joint.png')
    with Image.open(out) as im:
        assert im.width>500 and im.height>300
        assert len(im.convert('L').getcolors(im.width*im.height))>5
    receipt=json.loads(out.with_suffix('.json').read_text())
    assert receipt['figure']['edges'][0]['sources']==['1','2']
    assert receipt['figure']['note']=='Joint support'
    assert receipt['visual_verified'] is False
    data=figure.model_dump()
    data['edges'].append({'sources':['3'],'target':'1','relation':'attack'})
    with pytest.raises(ValueError,match='순환'):
        render(Figure.model_validate(data),tmp_path/'cycle.png')


def test_chart_requires_one_value_per_category():
    data=graph().model_dump()
    data.update(kind='bar',nodes=[],edges=[],categories=['A','B'],series=[{'name':'S','values':[10]}])
    with pytest.raises(ValueError,match='계열 길이'):
        Figure.model_validate(data)


def test_options_share_geometry_without_merging_combined_premises():
    import shutil
    if not shutil.which('dot'): pytest.skip('Graphviz layout extra is not installed')
    from haean.argument_layout import layout
    data=graph().model_dump()
    data.update(id='first',placement='option_1',nodes=[{'id':v,'label':v} for v in 'abcde'],
        edges=[{'sources':['a','b'],'target':'c','relation':'support'},
               {'sources':['a','d'],'target':'e','relation':'attack'}])
    first=Figure.model_validate(data)
    data.update(id='second',placement='option_2')
    data['edges']=[{'sources':['a'],'target':'c','relation':'support'},data['edges'][1]]
    result=layout([first,Figure.model_validate(data)])
    points={o['name']:o['pos'] for o in result['graph']['objects']}
    assert points['j0']!=points['j1']
    assert len(result['active_joints']['first'])==2 and len(result['active_joints']['second'])==1
    assert any(e['arrowhead']=='tee' for e in result['graph']['edges'])


def chart(values, **changes):
    data=graph().model_dump()
    data.update(kind='line',nodes=[],edges=[],categories=['A','B'],
                series=[{'name':'index','values':values}],x_label='quarter',y_label='index',note='')
    data.update(changes)
    return Figure.model_validate(data)


def test_comparable_choices_use_same_scale_and_keep_explicit_ticks(tmp_path):
    pytest.importorskip('matplotlib')
    from haean.figures import render_item
    from types import SimpleNamespace
    a=chart([10,20],id='a',placement='option_1')
    b=chart([100,125],id='b',placement='option_2')
    paths=render_item(SimpleNamespace(figures=[a,b]),tmp_path)
    receipts=[json.loads(p.with_suffix('.json').read_text()) for p in paths.values()]
    assert receipts[0]['geometry']==receipts[1]['geometry']
    assert receipts[0]['geometry']['y_max']>=125
    from haean.figures import chart_geometry
    exact=chart([10,20],y_min=0,y_max=175,y_ticks=[0,25,50,75,100,125,150,175])
    assert chart_geometry([exact])['y_ticks']==[0,25,50,75,100,125,150,175]


def test_chart_rejects_clipping_nonfinite_and_conflicting_axes():
    from haean.figures import chart_geometry
    with pytest.raises(ValueError,match='축 범위'):chart([10,125],y_min=0,y_max=100)
    with pytest.raises(ValueError,match='유한'):chart([10,float('nan')])
    a=chart([10,20],y_min=0,y_max=100)
    b=chart([10,20],y_min=0,y_max=200)
    with pytest.raises(ValueError,match='명시 축'):chart_geometry([a,b])


def test_numeric_labels_are_opt_in_and_preserve_close_values(tmp_path):
    pytest.importorskip('matplotlib')
    from haean.figures import render
    out=render(chart([120,120.8],show_values=True,y_min=0,y_max=175),tmp_path/'labels.png')
    svg=out.with_suffix('.svg').read_text()
    assert '<!-- 120 -->' in svg and '<!-- 120.8 -->' in svg
    plain=render(chart([120,120.8],y_min=0,y_max=175),tmp_path/'no-labels.png')
    assert '<!-- 120.8 -->' not in plain.with_suffix('.svg').read_text()


def test_editor_layout_memos_never_reach_blind_or_student_html(draft,tmp_path):
    from haean.validation import public_item
    from haean.export import export_review
    figure=graph().model_copy(update={'layout_note':'INTERNAL answer hint','note':'LEGACY layout memo'})
    draft.items[0].figures=[figure]
    public=public_item(draft.items[0])
    assert 'layout_note' not in public['figures'][0]
    assert public['figures'][0]['note']==''
    import shutil
    if not shutil.which('dot'):pytest.skip('Graphviz required for HTML export')
    pytest.importorskip('matplotlib')
    (tmp_path/'candidate.json').write_text(draft.model_dump_json())
    (tmp_path/'status.json').write_text('{"state":"needs_revision"}')
    export_review(tmp_path)
    html=(tmp_path/'questions.html').read_text()
    assert 'INTERNAL answer hint' not in html and 'LEGACY layout memo' not in html
