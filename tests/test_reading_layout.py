import pytest
from haean.reading_layout import validate_book


def book():
    return {'passages':[{'paragraphs':['합성 지문'], 'questions':[{'number':p*3+i+1,'stem':'발문','options':['가','나','다','라','마'],'answer':1,'explanation':'근거','option_explanations':['근거']*5} for i in range(3)]} for p in range(10)]}


def test_full_reading_requires_ten_complete_ordered_triplets():
    assert len(validate_book(book()))==10
    for edit in ['count','number','options','answer','explanation']:
        b=book();q=b['passages'][0]['questions'][0]
        if edit=='count':b['passages'].pop()
        elif edit=='number':q['number']=2
        elif edit=='options':q['options']=['같음']*5
        elif edit=='answer':q['answer']=6
        else:q['explanation']=''
        with pytest.raises(ValueError):validate_book(b)
