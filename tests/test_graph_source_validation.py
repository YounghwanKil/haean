import pytest
from haean.models import Brief, Figure, Calculation
from haean.validation import validate


@pytest.mark.parametrize('kind,placement', [
    ('line', 'passage'), ('bar', 'passage'), ('line', 'statements'), ('bar', 'statements')])
def test_real_numeric_source_does_not_require_duplicate_table(draft, kind, placement):
    brief = Brief(exam='psat7', subject='자료해석', item_type='자료 판단(선지)', topic='합성 검증')
    item = draft.items[0]
    item.subject, item.item_type = brief.subject, brief.item_type
    item.figures = [Figure(id='graph', kind=kind, placement=placement, title='합성 자료',
        x_label='기간', y_label='명', categories=['1', '2'],
        series=[{'name': '가', 'values': [10, 20]}], nodes=[], edges=[], note='합성')]
    item.calculations = [Calculation(label='합', expression='10+20', expected='30', unit='명', evidence='그래프')]
    assert not validate(draft, brief, {'source-1'})
    item.calculations = []
    assert any('재계산' in e for e in validate(draft, brief, {'source-1'}))
    item.calculations = [Calculation(label='합', expression='10+20', expected='31', unit='명', evidence='그래프')]
    assert any('계산 불일치' in e for e in validate(draft, brief, {'source-1'}))
    item.calculations[0].expected = '30'
    item.figures[0].placement = 'option_1'
    assert any('수치 그래프' in e for e in validate(draft, brief, {'source-1'}))
    item.figures = []
    assert any('수치 그래프' in e for e in validate(draft, brief, {'source-1'}))
