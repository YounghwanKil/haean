# 원문 DB와 정제 참고자료 연결

해안은 원문 검색 DB(`data/corpus.sqlite`), 과목별 정제 참고자료 색인, 출처가 연결된 로컬 지식 위키(`data/wiki`)를 구분한다. 원문과 위키를 새 색인으로 덮어쓰지 않는다. GitHub Wiki에는 사용법을 두며 개인 대화·원문 문항·정제 자료는 로컬에 보관한다.

## 명시적으로 고른 전사 문항 내보내기

`track ref-export`는 기존 corpus를 읽기 전용으로 열고 선택한 문항을 새 폴더에 내보낸다. 현재 범위는 PSAT 5급·7급의 전사 확인 기록이 있는 완전한 문항이다. 통계 행, 검토 의견 행, LEET 자료를 자동 변환하지 않는다. 검토 의견의 A/B/C 등급과 PSAT의 5/7급도 다른 필드다.

먼저 실제 corpus ID로 선택 파일을 만든다. 다음은 구조 예시다.

```json
{
  "schema_version": 1,
  "usage": "development",
  "records": [
    {
      "id": "실제-corpus-record-id",
      "track": "psat_verbal",
      "grade": 5,
      "usage": "development"
    }
  ]
}
```

`psat_verbal`·`psat_data`·`psat_situation`은 각각 언어논리·자료해석·상황판단이다. ID는 파일 순서나 문항 번호로 다시 만들지 않는다. 자료의 개발용 사용 범위는 선택자가 확인하며, `development` 표기만으로 데이터의 실제 분할을 증명할 수는 없다.

기존 전사에 상대 PDF 경로가 있으면 명령을 실행한 폴더를 기준으로 확인한다. 다른 폴더에서 실행할 때는 선택 JSON의 최상위 `source_root`에 원래 프로젝트의 절대경로를 명시한다.

```bash
haean tools track ref-export --corpus data/corpus.sqlite \
  --selection data/reference-selection.json --out data/reference-export-01
haean tools track ref-build data/reference-export-01/refs.jsonl \
  --out data/track-references-01.sqlite
```

내보낸 자료에는 선택 파일, 선택된 corpus 행의 사본, 원본 PDF·전사 packet의 경로와 해시, 기존 ID와 locator, 검증 상태가 함께 남는다. 새 색인으로 가져와도 `item=None`이며, 기존 원문을 새 트랙의 문항 모델로 변환했다고 표시하지 않는다. `text`는 원문을 유지한다. 추가 `corpus_evidence`를 읽을 수 있는 현재 하네스가 필요하며, 구버전 실행기에 새 자료를 강제로 넣지 않는다.

## 나중에 확인한 공식 정답 연결

공식 정답을 확보했다면 기존 전사나 corpus의 미확인 값을 덮어쓰지 않는다. 공식 정답표와 문제지의 연도·급수·과목·책형·문항 번호를 대조한 근거를 별도로 준비해 새 자료를 만든다.

```bash
haean tools track ref-answers data/reference-export-01/refs.jsonl \
  --evidence data/official-answer-evidence.json --out data/reference-answers-01
haean tools track ref-build data/reference-answers-01/refs.jsonl \
  --out data/track-references-02.sqlite
```

`ref-answers`는 답을 풀거나 인터넷에서 답안을 찾는 명령이 아니다. 정제한 근거와 PDF의 정답 행을 대조하고 출처 사본을 보존하는 단계다. 해안에게 “공식 확정 정답을 찾아 원문과 책형을 확인하고 `ref-answers` 근거를 준비해줘”라고 요청할 수 있다. PDF 텍스트 대조에는 Poppler의 `pdftotext`가 필요하다. 이 의존성은 `ref-answers`와 공식 정답 근거가 포함된 자료의 `ref-build`·`ref-search`에 적용된다. 없는 경우 검증을 실패로 처리하며 정답을 추정하지 않는다.

입력은 `schema_version=1`, `usage=development`인 감사 JSON이다. `sources`에는 공식 게시물·확정 문구·첨부·다운로드 기록·정답 PDF·추출 텍스트를, `records`에는 기존 ID·시험 식별·정답 행 위치·문제지 대응·시각 확인 근거를 둔다. 각 파일의 경로와 해시도 필요하다. 현재 지원 범위는 **정답표 좌측의 1–20번 행**이며, 감사 ID 집합과 입력 refs ID 집합이 같아야 한다. 다른 표나 부분 선택을 조용히 추정하지 않는다. 세부 검증 계약은 [구현](../src/haean/reference_answers.py)과 [합성 예제](../tests/test_reference_answers.py)에 있다.

새 참고 레코드의 `answer`·`answer_verified`와 `official_answer_evidence`가 후속 확인을 나타낸다. 원문 `text`와 `corpus_evidence`의 `answer_verified=false`는 **전사 당시 상태**로 보존된다. 같은 문항의 서로 다른 확인 시점을 뜻하므로 과거 기록을 수정해 두 값을 맞추지 않는다. 새 출처 파일들은 실행 스냅샷에도 포함된다.

원문과 공식 문제지의 바이트 일치, 공식 정답 행 대조, 분류의 정확성, 사람 전문가의 품질 승인은 각각 다르다. 답을 확인해도 임시 유형·빈 영역 분류는 그대로다. 파일 검증은 확보한 근거의 일관성을 검사하며 공식 사이트의 진위나 새로운 사람 검토를 자동으로 보증하지 않는다.

## 원문 근거로 분류를 보강하기

공식 답이 확인되어도 새 트랙의 유형·영역·형식이 자동으로 채워지지는 않는다. 해안에게 “이 참고문항의 원문과 현재 트랙 어휘를 읽고 분류 근거를 정리해줘”라고 요청한다. 원래 임시 유형과 새 트랙의 분류축이 다르면 대응 이유를 기록하고, 불확실한 필드는 그대로 둔다.

```bash
haean tools track ref-curate data/reference-answers-01/refs.jsonl \
  --classification data/reference-classification.json --out data/reference-curated-01
haean tools track ref-build data/reference-curated-01/refs.jsonl \
  --out data/track-references-curated-01.sqlite
```

`ref-curate`는 분류를 자동 추론하는 명령이 아니다. 원문을 읽어 만든 분류 manifest를 검증하고 별도 새 자료에 연결한다. v1은 공식 정답 근거가 있는 PSAT 전사를 입력받으며, 이미 분류 근거를 붙인 자료에 다시 덧붙이지 않는다. 재분류할 때는 같은 원본 refs와 새 manifest·출력 경로를 사용한다.

출처의 연도·급수별 라벨과 생성 프로필의 분류 체계를 구분한다. 두 기준이 다르면 각각의 근거를 남기고, 같은 발문 표현만으로 다른 문항을 재분류하지 않는다. 해당 문항의 실제 판단 과제와 원본 근거를 확인한 뒤 필요한 분류만 별도 버전으로 보강한다.

manifest는 `schema_version=1`, `usage=development`, 작성 주체 `origin`(model/human), 실제 `actual_model`(모르면 명시적으로 `null`), 그에 맞는 `status`를 기록한다. 모델 상태는 `source_grounded_model_curation`, 사람 상태는 `source_grounded_human_curation`이다. `human_approved=false`, `semantic_accuracy_verified=false`는 그대로 유지한다. 사람 작성이라고 적었다는 사실만으로 전문가 승인이 되지는 않는다.

각 `records` 행에는 `id`, 원본 행 객체의 `source_record_sha256`, 수정할 `fields`를 둔다. 해시는 원래 JSONL 행 객체를 `json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')`로 직렬화한 SHA256이다. 허용 필드는 `area/item_type/item_format/discourse/stem_type`이며, 각 필드는 `value`, `rationale`, 하나 이상의 `evidence`를 갖는다. 근거의 `pointer`는 `json.loads(ref.text)` 내부의 문자열을 가리키는 JSON Pointer이고 `quote`는 그 문자열에 실제로 존재하는 인용이다. 각 필드에는 `발문·지문·보기·표·선지` 안의 문자열을 인용한 근거가 최소 하나 필요하다. 잠정 유형·검증 상태 같은 메타정보만으로 분류를 보강할 수 없다. 입력 refs와 manifest의 ID 집합은 같아야 한다. 세부 예제는 [합성 테스트](../tests/test_reference_curation.py)를 따른다.

닫힌 트랙 어휘는 수정한 값에 적용한다. 열린 어휘인 PSAT 응답 형식·담화는 `일반/합답형`, `평서문/대화형/규정·사례/표`처럼 관찰 가능한 형식을 로컬 규약으로 명시할 수 있다. 이는 공식 유형명이 아니다. 애매한 필드를 `unknown`이라는 검색 라벨로 채우지 말고 `fields`에서 제외하여 원래 값을 보존한다.

출력은 원래 본문·정답·ID·급수·출처를 그대로 두고 명시한 분류와 `classification_evidence`만 붙인다. 원래 `notes`와 corpus의 임시 분류 표시는 당시 기록이다. 검색 시에는 새 분류 근거와 원래 기록을 함께 본다. 색인 생성·검색 때 기존 전사와 공식답 검사를 원본 행에 그대로 적용하고, 새 분류가 manifest와 일치하는지 확인한다. 분류 근거 파일도 단계형 출제의 입력 스냅샷에 포함한다. 정확 인용·해시 검사 통과는 분류의 의미적 타당성이나 출제 품질 향상을 보증하지 않는다.

## 검색 확인과 출제 연결

```json
{"track":"psat_verbal","grade":5,"role":"item","k":3}
```

위 JSON을 `data/reference-query.json`에 저장한 뒤 확인한다.

```bash
haean tools track ref-search data/reference-query.json \
  --index data/track-references-01.sqlite
haean tools track attach runs/준비된-run data/track-brief.json \
  --index data/track-references-01.sqlite
```

색인이 생겼다고 모든 출제 요청에 참고 문항이 들어가는 것은 아니다. 검색은 급수·과목·역할과 명시된 유형·영역·응답 형식을 정확히 맞춘다. 원자료에 영역이나 응답 형식이 없으면 해당 조건의 검색 결과는 부족할 수 있다. 자동으로 조건을 풀거나 비슷한 이름을 같은 유형으로 바꾸지 않는다. 필요한 분류는 원문을 읽어 별도로 정제하고 대응 근거를 남긴다.

`ref-search`의 `hits`·`missing`과 실행의 참고자료 스냅샷을 확인한다. 단계형 출제는 PDF뿐 아니라 전사 packet과 선택 행 사본도 실행 근거에 포함한다. 이 색인은 기존 회차 `compose`에 자동 연결되지 않는다. 기존 회차 작성의 corpus 검색과 선택적인 `track attach --index`는 서로 다른 연결이다.

## 검증 상태와 위키

문항 버전에 연결된 실제 검토 의견은 [과거 검토 사례 연결](REVIEW_CASES.md)의 `track review-export`로 별도 등록할 수 있다. 기출 예시와 역할을 나누고, 재인용된 사람 의견·모델 의견·완전한 수정본·부분 수정 기록을 구분한다. 검색에 들어갔다는 사실을 의견 채택이나 사람 승인으로 세지 않는다.

- 전사 확인은 발문·지문·보기·표·선지의 재현 범위다. 정답 확인이나 사람 출제 전문가의 승인이 아니다.
- 정답 미확인 자료의 `answer=null`, `answer_verified=false`를 유지한다. 검색 결과에서 정답을 추정해 채우지 않는다.
- 제3자 미러 파일의 해시 일치는 공식 서버 원본과의 동일성을 증명하지 않는다. 원래 출처 표시와 공식 바이트 확인 여부를 유지한다.
- 유형의 임시 분류, 시각 검토의 미확인 값, 통계와 전문 문항의 차이를 보존한다. 원문 파일·전사 자료가 바뀌면 재검토 후 새 내보내기와 색인을 만든다.
- `ref-build`·`ref-search`의 파일 검사는 의미 정확성 검사와 다르다. 위키에도 확인한 범위와 남은 결손을 따로 기록한다.

위키에는 반복 검토에서 얻은 원칙과 출처를 축적한다. 사례 수와 검토자 수를 구별하고, 같은 `case_key`나 캐시 사본을 독립적인 근거로 중복 집계하지 않는다. 원칙 후보의 실제 적용·회귀 검증이 없으면 확정 규칙으로 승격하지 않는다. 사용법은 `skills/haean-wiki/SKILL.md`를 따른다.
