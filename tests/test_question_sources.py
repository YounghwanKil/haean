import hashlib
import json
import pytest
from haean.corpus import Corpus
from haean.models import Brief
from haean.question_sources import import_questions
from haean.retrieval import retrieve


def packet(tmp_path):
    pdf=tmp_path/'synthetic.pdf';pdf.write_bytes(b'%PDF-test fixture only')
    item={'exam':'psat5','subject':'자료해석','year':2026,'number':1,'item_type':'표 비교',
          'stem':'옳은 것은?', 'passage':'가상 자료', 'statements':[],
          'tables':[{'title':'생산량','unit':'개','columns':['지역','수량'],'rows':[['가','10']], 'note':''}],
          'options':[{'number':i,'text':f'선지 {i}'} for i in range(1,6)],
          'answer':None,'answer_verified':False,'transcription_verified':True,
          'verification_note':'합성 테스트 픽스처',
          'source':{'pdf_path':str(pdf),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    'pages':[1],'url':'https://example.invalid/test.pdf','publisher':'fixture','mirror':False}}
    path=tmp_path/'packet.json';path.write_text(json.dumps({'items':[item]}))
    return path,item


def test_checked_transcription_retrieves_whole_tables_without_inventing_answer(tmp_path):
    path,item=packet(tmp_path);corpus=Corpus(tmp_path/'db.sqlite')
    assert import_questions(corpus,path)['imported']==1
    import_questions(corpus,path)
    assert corpus.db.execute('SELECT count(*) FROM records').fetchone()[0]==1
    refs,receipt=retrieve(corpus,Brief(exam='psat5',subject='자료해석',item_type='표 비교',topic='생산량'))
    assert refs[0]['full_question'] and refs[0]['transcription_verified']
    assert not refs[0]['answer_verified']
    assert json.loads(refs[0]['text'])['표'][0]['rows']==[['가','10']]
    assert receipt['unverified_answer_reference_ids']==receipt['full_few_shot_ids']


def test_bad_later_source_cannot_partially_import(tmp_path):
    path,item=packet(tmp_path);other=dict(item,number=2,source=dict(item['source'],pdf_sha256='0'*64))
    path.write_text(json.dumps({'items':[item,other]}));corpus=Corpus(tmp_path/'db.sqlite')
    with pytest.raises(ValueError,match='해시 불일치'):import_questions(corpus,path)
    assert corpus.db.execute('SELECT count(*) FROM records').fetchone()[0]==0


def test_unverified_or_guessed_answers_are_not_authoritative_sources(tmp_path):
    path,item=packet(tmp_path);corpus=Corpus(tmp_path/'db.sqlite')
    item['answer']=3;path.write_text(json.dumps({'items':[item]}))
    with pytest.raises(ValueError,match='정답'):import_questions(corpus,path)
