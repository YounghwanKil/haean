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
