# 외부 규칙으로 회차 설계 연결

`compose`는 로컬 규칙으로 한 회차의 형식과 내용설계 제안을 만들고 기존 `exam-build`에 연결하는 선택 기능이다. LEET 추리논증 40문항, PSAT 5급 세 과목 각 40문항, PSAT 7급 세 과목 각 25문항을 지원한다. 7급은 별도 형식·내용 프로필을 사용한다. 언어이해는 기존 제작 경로를 유지한다.

설계에는 소재 범위, 판단 원리, 응답 형식과 정답 배분 제안 등이 들어간다. 이것은 아직 학생이 풀 수 있는 완성 문항이 아니다. 작성·독립 풀이·편집 검토·사람 확인과 한글 출력은 각각 후속 단계다.

## 로컬 입력

기출에서 추출한 분류·통계·소재 대장은 공개 패키지에 넣지 않는다. 사용자는 자신이 가진 규칙 JSON의 경로와 SHA-256, 원천·버전을 프로필에 기록한다. `format_rules`, `content_rules`, `content_config`, `rules_config`가 필요하며 5급 언어논리는 `labels`도 필요하다. 7급은 아래 전용 계약의 네 파일만 사용한다. 외부 Python 파일을 실행하거나 환경변수로 전역 규칙을 교체하지 않는다. 서로 다른 프로필은 별도 엔진 인스턴스에서 처리한다.

프로필의 구조 예시다. `files`에 필요한 역할을 각각 한 번씩 넣는다. 아래 SHA는 실제 파일 값으로 채워야 한다.

```json
{
  "schema_version": 1,
  "track": "psat_data", "exam": "psat5", "subject": "자료해석", "exam_grade": 5,
  "usage": "development",
  "origin": {"source": "팀 내부 자료명", "revision": "자료 버전"},
  "files": [
    {"role": "format_rules", "path": "rules/format_rules.json", "sha256": "실제 파일 SHA-256",
     "usage": "development", "exam_grade": 5, "locator": "파일 전체·해당 시트나 원천 위치"}
  ]
}
```

추리논증은 `track=leet_reasoning`, `exam=leet`, `subject=추리논증`, `exam_grade=null`이다. PSAT의 나머지 트랙은 `psat_verbal`, `psat_situation`이다. 파일의 해시를 확인해도 그 안의 유형 라벨·통계·기출 정답까지 검증한 것은 아니다. 분할과 출처 기록은 제공자의 명시이며, holdout으로 표시한 입력은 거절한다.

## PSAT 7급 전용 프로필

7급 manifest는 `exam=psat7`, `exam_grade=7`, 과목에 맞는 기존 `psat_verbal`·`psat_data`·`psat_situation` 트랙을 사용한다. 엔진은 manifest와 네 파일 내부의 과목·급수·버전을 모두 대조한다. 5급 파일의 겉표시만 바꾸거나 40슬롯 중 일부를 자른 프로필은 사용할 수 없다.

네 JSON은 공통으로 `schema_version: 1`, `engine: "psat7-v1"`, `exam_grade: 7`, `subject: "자료해석"` 같은 정체성 필드를 갖는다. 다음 필드를 덧붙인다. 괄호의 값은 자료와 편집 목표에 맞게 작성하며, 과목별 고정 기출 법칙이 아니다.

| 파일 역할 | 필드 |
|---|---|
| `format_rules` | `total_slots:25`, `types:[{code,label,count,response_formats:[문자열]}]`, `shared_sets:[{id,members:[번호,번호],types:[코드,코드]}]`, `difficulty_counts:{하,중,상}`, 선택 `section_preferences:[{start,end,types:[코드]}]` |
| `content_rules` | `types:{코드:{domains,reasoning_tasks,distractor_paths,review_checks,construction_notes}}`. 각 값은 비어 있지 않은 문자열 배열 |
| `content_config` | `common_passage_policy`, `difficulty_policy`, `source_policy`, `subject_review`. 각각 문자열 배열 |
| `rules_config` | `observations` 객체에 원자료·SHA·시트/행·기간·필터·관측치를 기록하고, `editorial_decisions` 문자열 배열에 채택한 편집 목표와 이유를 기록 |

각 파일과 하위 구조에는 정의된 필드만 쓴다. `observations` 내부는 출처를 기록할 자유 JSON 객체다. 출처·정책 문장은 실행할 명령이 아닌 자료이며, 해시 확인으로 그 의미가 전문가 검증됐다고 간주하지 않는다.

유형 개수와 난도 개수는 각각 합계 25여야 한다. 유형의 0배정은 허용하고 내용설계 정의도 유지한다. 이번 회차에 배정하지 않았다는 뜻이며 해당 유형의 출제를 금지하지 않는다. 모든 유형에 해당 과목의 판단 과제·오답 경로·검토 기준을 작성해야 한다. 통계 행의 유형명만 반복한 빈 지침으로 대신하지 않는다.

공통지문은 겹치지 않는 인접 2문항의 ID·회원·유형을 명시한다. 세트의 개수와 위치는 프로필의 편집 선택이다. 관측 위치와 선택한 위치가 다르면 이유를 기록한다. 세트에 먼저 배정한 유형 수가 전체 할당량보다 많으면 설계를 거절한다. 구간별 선호 유형은 `section_preferences`의 부드러운 목표이며, 충족하지 못하면 경고로 남긴다.

`sample`은 이 할당량·세트·응답 형식에서 seed에 따른 새 배치를 만들고, `content`는 실제 배치된 유형의 과목별 판단 과제와 오답 경로를 연결한다. 기존 plan의 25행을 감싸거나 기존 문항 본문을 복제하지 않는다. 난도는 실측값이 아닌 편집 목표다. 정답 번호·보기 진위는 미리 배분하지 않으며 작성 후 기존 검토 흐름에서 확정하고 분포를 관찰한다.

7급 옵션은 생략하거나 `{"size":25}`만 쓴다. 5급의 `mode`, `presets` 등을 가져오지 않는다. 소재 대장은 `{"entries":[객체,...]}`를 명시할 수 있으며 출제 때 확인할 자료로 보존한다. 대장을 전달했다고 자동으로 누적 문항의 의미상 중복 검사를 수행한 것은 아니다.

프로필은 로컬에 두고 아래와 같은 기존 명령으로 사용한다. 기출·팀 자료는 공개 Git에 추가하지 않는다.

```bash
haean tools compose design data/psat7-data/profile.json --seed 7 --out runs/psat7-data-design
haean tools compose check runs/psat7-data-design/design.json
```

## 설계와 기존 배정표 연결

```bash
haean tools compose design data/composition-profile.json --seed 7 --out runs/composition/design-01
haean tools compose check runs/composition/design-01/design.json
haean tools compose bind data/exam-plan.json runs/composition/design-01/design.json data/slot-mapping.json --out runs/composition/binding-01
haean tools exam-build data/exam-plan.json --composition-packet runs/composition/binding-01/packet.json --out runs/exam-01
```

`design`은 모델을 호출하지 않는다. `exam-build`에서 기존 Codex 작성·검토가 실행된다. 기존 `prepare`와 corpus 검색 자료도 유지한다. `--options`로 트랙별 표본 추출 옵션 JSON, `--ledger`로 로컬 소재 대장을 명시할 수 있다. 잘못된 급수, 중복·누락 슬롯, 형식 검증 오류가 있으면 다음 단계로 넘어가지 않는다. 소재 대장을 읽는 것만으로 공유 문항풀을 조회하거나 누적 생성의 구조 반복을 검사했다고 보지 않는다.

`slot-mapping.json`은 문항별 대응 목록이다. 예시는 구조만 보여 주며 실제 회차의 모든 행(추리논증·5급 40개, 7급 25개)이 필요하다. `number`는 인쇄 순서, `item_id`는 기존 문항 ID다. ID의 끝 숫자나 배열 위치에서 서로를 추측하지 않는다.

```json
[
  {
    "number": 1, "item_id": "my-stable-id", "external_slot": 7,
    "legacy_item_type": "자료분석", "external_type": "기본",
    "mapping_rationale": "해당 외부 분류의 과제를 기존 자료분석 슬롯으로 배정한다.",
    "external_set_key": null, "shared_passage_id": null,
    "external_difficulty": "중",
    "difficulty_mapping": {"legacy": "중", "external": "중", "rationale": "이 슬롯의 계획 난도와 대응한다."}
  }
]
```

외부 유형명은 해당 `format_design.slots`의 원문 필드와 맞춰야 한다. 외부 숫자 난도를 하·중·상으로 자동 변환하지 않는다. 공통지문은 외부 세트의 실제 멤버와 기존 세트 ID의 구성원이 같아야 한다. 5급 언어논리 boolean 세트는 프로필의 명시 멤버십을 확인하고 `slots:19,20` 같은 키로 표현한다. 5급 자료해석은 `bundle`, 상황판단은 `set_id`를 따른다. 7급 세 과목은 전용 프로필의 `shared_sets`와 출력 `set_id`를 따른다. LEET 외부 설계에는 공통지문 명세가 없어 이 연결에서 세트를 임의로 만들지 않는다.

이 선택 연결의 plan 난도는 기존 Item 스키마의 `하`·`중`·`상`으로 명시한다. `중상` 같은 별도 세부 라벨은 자동 환산하지 않고 거절한다. 기존 일반 회차 경로의 세부 난도 처리는 바뀌지 않는다. 작성 후 배정 난도와 다르거나 공통지문의 그림이 서로 다르면 검토 오류로 남는다.

기존 plan의 소재·유형·난도가 우선이다. 충돌한다면 새 계획을 명시적으로 검토해서 만들고 새 패킷에 연결한다. 설계의 정답 배분에 맞추려고 논리를 바꾸지 않는다. 외부 기출 ID는 기존 corpus의 `source_ids`에 자동 편입하지 않는다.

## 검토와 실행 기록

설계 원문, 입력 규칙과 코드, seed·옵션, plan·mapping을 해시로 연결한다. 묶음마다 적용할 설계만 작성·편집 검토에 전달한다. 독립 풀이 입력에는 제작 설계와 정답 계획을 넣지 않는다. 조립 시에도 설계·배정·후보·검토 기록의 연결을 확인한다. 변경된 입력에 예전 검토를 재사용하지 않는다.

기존 실행 디렉터리를 덮어쓰지 않는다. 실패한 실행 기록도 남기고 새 디렉터리에서 다시 시작한다. 코드를 바꾼 후 이전 설계가 실행 근거 검사에서 거절되면 새 설계를 만들어 연결한다. composition을 사용한 회차도 `exam-resume 이전회차 --out 새회차`로 이어갈 수 있다. 전체 배정표와 production manifest, 원 설계·출처·코드 및 묶음별 검토 연결이 일치해야 한다. 완료 묶음은 기존 검토를 확인해 재사용하고 미완료 묶음만 새 run에서 이어간다. 상세 조건은 [생성과 재개](PRODUCTION.md#외부-회차-설계를-사용한-실행-재개)를 따른다.

외부 설계에 있는 출처 익명화, 제도 변형, 우회 점검 같은 정책은 검증 전 제안이다. 실제 근거를 임의로 바꾸거나 배경지식을 썼다는 이유로 오답을 만들지 않는다. 원천 메모의 `__TODO`는 검증된 출처가 아니며, 빈 근거는 연구·편집 검토에서 해결한다. 누적 구조·오답 함정의 반복 검토와 실제 난도 판단도 별도로 남는다.

구조 검사·설계 재현 성공은 전문가 수준 출제, 실제 Astra 성능 향상, HWP/HWPX 렌더나 납품 승인에 대한 증거가 아니다. 현재 지원 범위와 실제 실행 결과를 구분해 보고한다.

2026-10-19 연결 검증에서는 전체 코드 테스트 495개, 스킬 discovery 11개와 역할 설정 7개가 통과했다. 네 과목의 로컬 프로필로 CLI에서 각각 40슬롯을 설계하고, 순서를 역전한 명시 대응표와 숫자 의미가 없는 ID로 연결을 확인했다. 난도·공통 그래프 불일치, 입력 변경, 후보 파일 파손도 차단했다. 이 검증에서 새 모델 문항 생성과 한글 렌더는 수행하지 않았다.


이후 같은 코드의 별도 고정 checkout에서 네 과목 각 1문항의 실제 작성·독립 풀이·수정·평가를 확인했다. [선택 문항 실행 결과](COMPOSITION_MODEL_SMOKE.md)는 회차 전체나 전문가 품질 검증과 구분한다. 잔여 오답·난도 문제와 실제 실행량도 함께 기록했다.
