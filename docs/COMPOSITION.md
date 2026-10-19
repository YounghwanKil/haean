# 외부 규칙으로 회차 설계 연결

`compose`는 로컬 규칙으로 한 회차의 형식과 내용설계 제안을 만들고 기존 `exam-build`에 연결하는 선택 기능이다. LEET 추리논증 40문항, PSAT 5급 언어논리·자료해석·상황판단 각 40문항을 지원한다. PSAT 7급과 언어이해의 기존 제작 경로는 유지한다.

설계에는 소재 범위, 판단 원리, 응답 형식과 정답 배분 제안 등이 들어간다. 이것은 아직 학생이 풀 수 있는 완성 문항이 아니다. 작성·독립 풀이·편집 검토·사람 확인과 한글 출력은 각각 후속 단계다.

## 로컬 입력

기출에서 추출한 분류·통계·소재 대장은 공개 패키지에 넣지 않는다. 사용자는 자신이 가진 규칙 JSON의 경로와 SHA-256, 원천·버전을 프로필에 기록한다. `format_rules`, `content_rules`, `content_config`, `rules_config`가 필요하며 언어논리는 `labels`도 필요하다. 외부 Python 파일을 실행하거나 환경변수로 전역 규칙을 교체하지 않는다. 서로 다른 프로필은 별도 엔진 인스턴스에서 처리한다.

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

## 설계와 기존 배정표 연결

```bash
haean tools compose design data/composition-profile.json --seed 7 --out runs/composition/design-01
haean tools compose check runs/composition/design-01/design.json
haean tools compose bind data/exam-plan.json runs/composition/design-01/design.json data/slot-mapping.json --out runs/composition/binding-01
haean tools exam-build data/exam-plan.json --composition-packet runs/composition/binding-01/packet.json --out runs/exam-01
```

`design`은 모델을 호출하지 않는다. `exam-build`에서 기존 Codex 작성·검토가 실행된다. 기존 `prepare`와 corpus 검색 자료도 유지한다. `--options`로 트랙별 표본 추출 옵션 JSON, `--ledger`로 로컬 소재 대장을 명시할 수 있다. 잘못된 급수, 중복·누락 슬롯, 형식 검증 오류가 있으면 다음 단계로 넘어가지 않는다. 소재 대장을 읽는 것만으로 공유 문항풀을 조회하거나 누적 생성의 구조 반복을 검사했다고 보지 않는다.

`slot-mapping.json`은 문항별 대응 목록이다. 예시는 구조만 보여 주며 실제 회차의 40개 행이 필요하다. `number`는 인쇄 순서, `item_id`는 기존 문항 ID다. ID의 끝 숫자나 배열 위치에서 서로를 추측하지 않는다.

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

외부 유형명은 해당 `format_design.slots`의 원문 필드와 맞춰야 한다. 외부 숫자 난도를 하·중·상으로 자동 변환하지 않는다. 공통지문은 외부 세트의 실제 멤버와 기존 세트 ID의 구성원이 같아야 한다. 언어논리 boolean 세트는 프로필의 명시 멤버십을 확인하고 `slots:19,20` 같은 키로 표현한다. 자료해석은 `bundle`, 상황판단은 `set_id`를 따른다. LEET 외부 설계에는 공통지문 명세가 없어 이 연결에서 세트를 임의로 만들지 않는다.

이 선택 연결의 plan 난도는 기존 Item 스키마의 `하`·`중`·`상`으로 명시한다. `중상` 같은 별도 세부 라벨은 자동 환산하지 않고 거절한다. 기존 일반 회차 경로의 세부 난도 처리는 바뀌지 않는다. 작성 후 배정 난도와 다르거나 공통지문의 그림이 서로 다르면 검토 오류로 남는다.

기존 plan의 소재·유형·난도가 우선이다. 충돌한다면 새 계획을 명시적으로 검토해서 만들고 새 패킷에 연결한다. 설계의 정답 배분에 맞추려고 논리를 바꾸지 않는다. 외부 기출 ID는 기존 corpus의 `source_ids`에 자동 편입하지 않는다.

## 검토와 실행 기록

설계 원문, 입력 규칙과 코드, seed·옵션, plan·mapping을 해시로 연결한다. 묶음마다 적용할 설계만 작성·편집 검토에 전달한다. 독립 풀이 입력에는 제작 설계와 정답 계획을 넣지 않는다. 조립 시에도 설계·배정·후보·검토 기록의 연결을 확인한다. 변경된 입력에 예전 검토를 재사용하지 않는다.

기존 실행 디렉터리를 덮어쓰지 않는다. 실패한 실행 기록도 남기고 새 디렉터리에서 다시 시작한다. 코드를 바꾼 후 이전 설계가 실행 근거 검사에서 거절되면 새 설계를 만들어 연결한다. 현재 composition을 사용한 회차의 `exam-resume`는 지원하지 않으므로 보존된 배정표와 새 실행 경로를 사용한다.

외부 설계에 있는 출처 익명화, 제도 변형, 우회 점검 같은 정책은 검증 전 제안이다. 실제 근거를 임의로 바꾸거나 배경지식을 썼다는 이유로 오답을 만들지 않는다. 원천 메모의 `__TODO`는 검증된 출처가 아니며, 빈 근거는 연구·편집 검토에서 해결한다. 누적 구조·오답 함정의 반복 검토와 실제 난도 판단도 별도로 남는다.

구조 검사·설계 재현 성공은 전문가 수준 출제, 실제 Astra 성능 향상, HWP/HWPX 렌더나 납품 승인에 대한 증거가 아니다. 현재 지원 범위와 실제 실행 결과를 구분해 보고한다.

2026-10-19 연결 검증에서는 전체 코드 테스트 495개, 스킬 discovery 11개와 역할 설정 7개가 통과했다. 네 과목의 로컬 프로필로 CLI에서 각각 40슬롯을 설계하고, 순서를 역전한 명시 대응표와 숫자 의미가 없는 ID로 연결을 확인했다. 난도·공통 그래프 불일치, 입력 변경, 후보 파일 파손도 차단했다. 이 검증에서 새 모델 문항 생성과 한글 렌더는 수행하지 않았다.


이후 같은 코드의 별도 고정 checkout에서 네 과목 각 1문항의 실제 작성·독립 풀이·수정·평가를 확인했다. [선택 문항 실행 결과](COMPOSITION_MODEL_SMOKE.md)는 회차 전체나 전문가 품질 검증과 구분한다. 잔여 오답·난도 문제와 실제 실행량도 함께 기록했다.
