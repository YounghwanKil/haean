# 과거 검토 사례를 출제에 연결하기

“이 수정 이력의 실제 의견을 다음 출제에 참고하게 해줘”라고 요청하면 `haean-wiki`가 원문을 읽고 사례 선택 근거를 준비한다. `track review-export`는 그 선택을 검증하고 원문 사본을 고정한다. 의견을 자동으로 해석하거나 수정안을 승인하는 명령은 아니다.

## 어떤 자료를 연결하는가

문항의 검토 전 버전, 그 버전에 대한 의견, 확보한 후속 수정 기록을 한 사례로 묶는다. 문항 번호만 같은 다른 파일을 연결하지 않는다. 같은 문항에 검토자 여러 명이 의견을 남겨도 사례는 하나이며, 상반된 의견은 그대로 둔다.

완전한 수정본이 있으면 `after.kind=full`, 변경 부분만 있으면 `delta`, 수정 기록이 없으면 `after=null`로 둔다. delta에서 완전한 수정본을 만들어 냈다고 표시하지 않는다. `unresolved`, `partially_resolved`, `reported_resolved`는 정리자가 기록한 역사적 상태다. 마지막 값도 현재 문항의 정확성이나 전문가 승인을 의미하지 않는다.

원본 검수 파일 없이 다른 문서에 인용된 사람 의견은 `human_reported`로 기록한다. 직접 확보한 사람 의견, 모델 의견, 출처가 불명확한 의견은 각각 `human`, `model`, `unknown`이다. 별도의 최상위 `origin/actual_model`은 **사례를 정리한 주체**다. 문서 작성자·검토자·정리자를 같은 사람이나 모델로 합치지 않는다.

## 선택 파일과 실행

선택 JSON의 최상위에는 `schema_version=1`, `usage=development`, `origin`(model/human), `actual_model`(모르면 null), `human_approved=false`, `semantic_accuracy_verified=false`, `records`를 둔다. 각 사례에는 다음을 기록한다.

| 필드 | 내용 |
|---|---|
| `case_key`, `family_id` | 선택 사례와 동일 문항의 계보를 식별하는 안정된 키. 번호나 검토자만 바꿔 중복 등록하지 않는다. |
| `track`, `grade`, 분류 필드 | 실제 시험·급수와 트랙 어휘. 분류는 원문 근거로 정리하며 불확실한 대응을 추측하지 않는다. |
| `source`, `year`, `number`, `status` | 출처 표기·확인한 연도와 문번·역사적 수정 상태. 연도 미확인은 null. |
| `before` | `version_label`, `author`, 전문 `text`, 학생용 범위 `public_text`. |
| `reviewers` | 의견마다 `origin`, `label`, 원문 `text`. 서로 다른 주장과 작성 주체를 보존한다. |
| `after` | 확보한 수정 버전·작성 주체·전문 또는 delta와 그 범위. full에만 학생용 범위가 필요하다. |

`text/public_text`는 원문을 복사해 붙이는 문자열이 아니라 아래 구조의 UTF-8 파일 범위다.

```json
{
  "file": "선택파일을-기준으로-한-원문경로.md",
  "sha256": "원문 전체 바이트의 SHA256",
  "start_line": 2,
  "end_line": 8,
  "excerpt_sha256": "선택한 행 바이트의 SHA256"
}
```

행 번호는 1부터 시작하고 끝 행을 포함한다. 발췌 바이트는 Python의 `b''.join(data.splitlines(keepends=True)[start_line-1:end_line])`로 계산하며 개행을 보존한다. 학생용 범위는 같은 버전의 전문 파일·해시·행 범위 안에 있어야 한다. `public_text`는 정답·해설을 제외한 학생용 범위라는 뜻이며 공개 배포 허가를 뜻하지 않는다. delta에는 학생용 범위를 지정하지 않는다. 전체 합성 예제는 [테스트의 selection fixture](../tests/test_reference_cases.py)에 있다.

```bash
haean tools track review-export --selection data/review-selection.json \
  --out data/review-cases-01
haean tools track ref-build data/review-cases-01/refs.jsonl \
  --out data/references-with-cases-01.sqlite
haean tools track ref-search data/review-query.json \
  --index data/references-with-cases-01.sqlite
haean tools track attach RUN data/track-brief.json \
  --index data/references-with-cases-01.sqlite
```

검색 JSON 예는 `{"track":"leet_reasoning","grade":null,"role":"case","area":"규범","k":4}`다. 기존 기출 refs도 함께 넣으려면 `ref-build`에 JSONL 경로를 추가한다. 같은 family를 중복 입력하면 오류가 나므로 `indexed`뿐 아니라 `errors`도 확인한다. 기존 파일을 덮어쓰지 않고 새 출력 폴더·색인을 사용한다.

## 실제 출제에서 쓰이는 범위

`track attach`는 편집 단계의 검색 조건에 맞는 사례를 선택한다. 현재 사례 검색은 시험·급수·영역을 맞추며 유형별 정밀 순위 모델은 아니다. 적합성이 부족하면 검색 결과의 원문을 읽고 명세·선택 자료를 조정한다. 부족분을 다른 시험의 의견으로 자동 대체하지 않는다.

선택 사례는 작성·수정·편집 검토의 입력에 들어간다. 독립 풀이에는 수험생용 문항만 전달한다. 과거 의견이나 정답을 현행 문항의 판정으로 복사하지 않으며, 원문에서 사용한 추론과 함정도 새 문항과 비교한다.

사례의 before와 확보한 full-after의 학생용 내용은 기존 긴 문구 중복 검사에 포함한다. 현재 검사는 새 문항의 지문과 비교하며 검토 의견과 delta는 제외한다. 선지 전체나 추론 구조의 독창성 검사를 대신하지 않으며, 표현을 바꾼 동일 구조나 장기 자기 반복을 완전히 검출한다는 뜻은 아니다.

출력에는 선택 파일과 원문 전체 사본·해시·발췌 범위가 남는다. 색인 생성과 검색에서 이를 다시 대조하며, 출제 입력 스냅샷에도 포함한다. 내보내기 후 원래 파일을 편집해도 보관 사본은 당시 상태를 유지한다. 새 의견을 반영하려면 새 선택·내보내기를 만든다.

이 검증은 출처 연결과 내용 보존을 확인한다. 작성자 신원, 인용 의견의 타당성, 정답 유일성, 사람 승인을 인증하지 않는다. 레코드의 `answer=null`, `answer_verified=false`를 유지한다. 실제 사람 검토와 현행 문항 수정은 [사람 검토 패킷](HUMAN_REVIEW.md)의 별도 흐름을 따른다. 원문과 사례 색인은 로컬에 보관하며 GitHub에는 올리지 않는다.
