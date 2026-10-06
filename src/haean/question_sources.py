"""Import visually checked question transcriptions, separately from answer validation."""
import hashlib
import json
from pathlib import Path

from pydantic import ConfigDict, Field, model_validator

from .corpus import digest
from .models import StrictModel, Option, Table, Brief


class Source(StrictModel):
    model_config = ConfigDict(extra='allow')
    pdf_path: str
    pdf_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    pages: list[int] = Field(min_length=1)
    url: str
    publisher: str
    mirror: bool


class SourceTable(Table):
    model_config = ConfigDict(extra='allow')


class QuestionSource(StrictModel):
    model_config = ConfigDict(extra='allow')
    exam: str
    subject: str
    year: int
    number: int = Field(ge=1, le=40)
    item_type: str
    stem: str = Field(min_length=1)
    passage: str
    statements: list[str]
    tables: list[SourceTable]
    options: list[Option] = Field(min_length=5, max_length=5)
    answer: int | None = Field(ge=1, le=5)
    answer_verified: bool
    source: Source
    transcription_verified: bool
    verification_note: str = Field(min_length=1)

    @model_validator(mode='after')
    def complete(self):
        Brief(exam=self.exam, subject=self.subject, item_type=self.item_type, topic='원문 참조')
        if [o.number for o in self.options] != [1,2,3,4,5]: raise ValueError('선지 1–5 순서 필요')
        if not self.passage and not self.tables: raise ValueError('문항 전문 또는 표 필요')
        for table in self.tables:
            if not table.columns or any(len(r) != len(table.columns) for r in table.rows):
                raise ValueError('표 열·행 불일치')
        if not self.transcription_verified: raise ValueError('화면 전사 대조가 끝난 문항만 등록')
        if self.answer_verified: raise ValueError('이 경로는 문제 전사만 등록합니다. 공식 정답 근거 검증은 별도입니다')
        if self.answer is not None: raise ValueError('확인되지 않은 정답을 참조 문항에 넣지 마세요')
        if any(n < 1 for n in self.source.pages): raise ValueError('PDF 쪽 번호는 1부터')
        return self


def import_questions(corpus, path):
    path = Path(path)
    packet = json.loads(path.read_text())
    items = [QuestionSource.model_validate(i) for i in packet['items']]
    if not items: raise ValueError('빈 참조 패킷')
    entries, seen = [], set()
    for item in items:
        pdf = Path(item.source.pdf_path)
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != item.source.pdf_sha256:
            raise ValueError('원본 PDF 해시 불일치: '+str(pdf))
        locator = f'{pdf.name}#{item.exam}:{item.year}:{item.subject}:{item.number:02d}'
        key = (item.source.pdf_sha256, locator)
        if key in seen: raise ValueError('패킷 내 문항 중복')
        seen.add(key)
        fields = {'과목':item.subject, '연도':item.year, '회차':str(item.year), '문항 번호':item.number,
            '문항유형':item.item_type, '발문':item.stem, '지문':item.passage, '보기':item.statements,
            '표':[t.model_dump() for t in item.tables], '선지':[o.model_dump() for o in item.options],
            '정답':None, '정답 검증':False, '분류 검증':'provisional',
            '출처':item.source.model_dump(), '전사 대조':item.verification_note,
            '전사 부가정보':item.model_extra or {}}
        text = json.dumps(fields, ensure_ascii=False)
        prior = corpus.db.execute('SELECT text FROM records WHERE sha=? AND locator=?', key).fetchone()
        if prior and prior['text'] != text:
            raise ValueError('기존 전사와 다릅니다. 버전 대조 후 별도 출처로 등록하세요: '+locator)
        entries.append((item, pdf, locator, fields, text))
    # Validate the entire packet before any source/record mutation.
    with corpus.db:
        for item, pdf, locator, fields, text in entries:
            corpus.db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)',
                (item.source.pdf_sha256, pdf.name, str(pdf.resolve()), 'partial_transcription',
                 '선택 문항의 화면 대조 전사. 공식 정답·PDF 전체 검증 아님.'))
            corpus.add(item.source.pdf_sha256, locator, item.exam, 'example', text,
                {'fields':fields, 'label_status':'provisional', 'answer_verified':False,
                 'transcription_verified':True, 'source':item.source.model_dump(),
                 'packet_sha256':digest(path.read_bytes()), 'packet_path':str(path.resolve())})
    return {'imported':len(items), 'answer_verified':False, 'packet':str(path),
            'note':'시각 전사 대조와 정답 검증은 별개입니다.'}
