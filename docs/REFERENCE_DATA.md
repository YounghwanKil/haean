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

- 전사 확인은 발문·지문·보기·표·선지의 재현 범위다. 정답 확인이나 사람 출제 전문가의 승인이 아니다.
- 정답 미확인 자료의 `answer=null`, `answer_verified=false`를 유지한다. 검색 결과에서 정답을 추정해 채우지 않는다.
- 제3자 미러 파일의 해시 일치는 공식 서버 원본과의 동일성을 증명하지 않는다. 원래 출처 표시와 공식 바이트 확인 여부를 유지한다.
- 유형의 임시 분류, 시각 검토의 미확인 값, 통계와 전문 문항의 차이를 보존한다. 원문 파일·전사 자료가 바뀌면 재검토 후 새 내보내기와 색인을 만든다.
- `ref-build`·`ref-search`의 파일 검사는 의미 정확성 검사와 다르다. 위키에도 확인한 범위와 남은 결손을 따로 기록한다.

위키에는 반복 검토에서 얻은 원칙과 출처를 축적한다. 사례 수와 검토자 수를 구별하고, 같은 `case_key`나 캐시 사본을 독립적인 근거로 중복 집계하지 않는다. 원칙 후보의 실제 적용·회귀 검증이 없으면 확정 규칙으로 승격하지 않는다. 사용법은 `skills/haean-wiki/SKILL.md`를 따른다.
