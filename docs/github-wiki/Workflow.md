# 스킬과 제작 흐름

총괄 `haean`이 요청을 연결합니다. 전문 스킬은 `haean-leet`, `haean-psat`, `haean-reading`, `haean-review`, `haean-style`, `haean-exam`, `haean-layout`, `haean-evolve`, `haean-wiki`입니다.

1. 급수·과목·유형·난도·회차 구성을 정하고 출처를 찾습니다.
2. 출제자가 지문·선지·정답·해설을 작성합니다.
3. 새 컨텍스트의 블라인드 풀이자가 정답·해설 없이 풉니다.
4. 편집 검토를 수행하고, 윤문이 필요하면 `haean-style`로 im-not-ai를 적용한 뒤 의미·정답을 재검토합니다. 도구 설치와 실제 윤문 적용 여부를 구분해 기록합니다.
5. 오류를 수정하고 회차의 구성·중복·시간·정답 분포를 점검합니다. [누적 생성 이력](https://github.com/YounghwanKil/haean/wiki/Knowledge#오래-작업할-때-같은-문제를-반복하지-않으려면)과 원문 구조도 대조합니다.
6. 기존 HWP 양식에 삽입하고 실제 한글 렌더를 검토합니다.
7. 사람의 전문가 검토와 실제 풀이 시간을 따로 기록합니다.

사람에게 보낼 문제·해설·응답 양식은 [사람 검토와 의견 회수](Human-Review)를 따릅니다. 검토 당시 문항 버전과 의견을 연결하고, 수집 후 확인한 오류를 원 묶음에 반영합니다.

## 일부 문항만 이어서 수정하기

Codex 대화에서는 “현재 회차의2·22번 묶음만 이어서 수정하고 나머지는 보존해 줘”처럼 요청할 수 있습니다. 총괄이 번호·ID·묶음과 검토 버전을 확인해 `haean tools exam-resume 이전회차 --out 새회차 --slots 2 22`로 연결합니다. 일반 회차와 composition 모두 지원합니다.

기존 작성 묶음의 모든 번호를 지정해야 하며, 일부만 입력하면 필요한 번호를 알려 주고 실행 전에 멈춥니다. 미선택 문항의 원고·실패·미적용 A/B 의견은 보존합니다. 완료 묶음을 강제로 다시 쓰는 옵션은 아니며 새 수정 의견은 해당 후보 버전에 연결해야 합니다. 미완료 묶음이 남으면 회차 전체는 완료로 표시하지 않습니다. `exam-status`에서 저장된 검토 수와 후속 의견을 반영한 사람 검토 대기 수를 구분할 수 있습니다. [상세 사용법](https://github.com/YounghwanKil/haean/blob/main/docs/PRODUCTION.md#지정한-문항-묶음만-재개)을 확인하세요.

“이 검토본은 그대로 보존하고, 2번의 겹치는 오답과 문장만 새 버전에서 고쳐 줘”라는 요청에는 `exam-revision-request`로 의견과 검토 버전을 연결하고 `exam-resume --revision-request`로 이어갑니다. C급 개선도 명시적으로 요청할 수 있어 오류 등급을 높일 필요가 없습니다. 실제 작성 묶음에 다른 번호가 있으면 함께 처리할 범위와 유지할 문항을 확인합니다. 원고·상태·과거 검토는 보존하고 새 풀이·편집 결과를 남깁니다. [명령 예시와 범위](https://github.com/YounghwanKil/haean/blob/main/docs/PRODUCTION.md#원-검토본을-보존한-수정-요청)를 참고하세요.

누적 문항의 반복 후보를 실제 모델에게 대조시키려면 `haean tools novelty-review RUN --out NEW_DIR --neighbors 1`을 사용합니다. 1–4문항 묶음과 선택한 과거 문항의 전문·버전을 함께 전달하며, 검색 경고가 없는 상위 후보도 확인합니다. 기존 원고·검토 상태·누적 DB는 변경하지 않습니다. 선택 원문쌍의 모델 자문이며 전체 독창성·사람 승인이나 100회 연속 생성의 반복 해소를 보증하지 않습니다. [원문쌍 구조 검토 사용법](https://github.com/YounghwanKil/haean/blob/main/docs/NOVELTY_REVIEW.md)을 참고하세요.

LEET 언어이해는 아래의 별도 파일럿 범위로 지원합니다. PSAT 5급은 과목당 40문항, 7급은 과목당 25문항 명세를 구분합니다. 회차 등록·파일 출력·모델 통과를 납품 승인으로 표시하지 않습니다.

## 소재와 판단을 먼저 설계하기

기존 `prepare`로 만든 새 run에 `haean tools track attach RUN 상세명세.json`을 연결하고 `haean tools track generate RUN`을 실행하면 소재 → 핵심 판단·오답 설계 → 기존 문항 형식 작성 → 독립 검토 순서로 진행합니다. 기존 자료·수정·검토 경로를 유지하는 선택 기능입니다. 현재 LEET 추리논증과 PSAT 5·7급 세 과목을 지원하며, 언어이해와 전체 회차 배정은 이 새 연결의 범위에 포함하지 않습니다.

명세 예시와 유형 대응, 별도 참고 색인, 실패 기록은 [트랙 통합 안내](https://github.com/YounghwanKil/haean/blob/main/docs/TRACK_INTEGRATION.md)를 확인하세요. 구현 완료와 출제 성능 향상은 별도로 검증합니다.

## 회차 전체의 형식·내용설계

별도 선택 기능인 `compose`는 로컬 규칙으로 시험별 형식·내용설계를 만듭니다. LEET 추리논증·PSAT 5급40문항과 전용 PSAT 7급25문항 프로필을 지원하며, 기존 배정표의 ID·유형·난도·공통지문을 명시적으로 연결한 뒤 작성·검토합니다. 언어이해는 별도 `reading` 경로를 사용합니다. [회차 설계 사용법](Composition)을 참고하세요.

회차에 참고문항을 붙일 때는 원문을 읽고 슬롯별 적용 이유와 부족한 점을 정한 뒤 `haean tools exam-ref-bind PLAN --index INDEX --selection SELECTION --out NEW_DIR`를 사용합니다. 선택한 전문과 출처 사본을 새 계획에 연결하며 기존 계획과 선택은 보존합니다. 전체 슬롯의 `coverage.json`에서 연결·기존 선택·결손을 확인할 수 있습니다. 자료 연결은 유형 적합성이나 문항 품질 승인이 아닙니다. 새 계획으로 `compose bind`를 수행한 뒤 출제합니다. [선택 파일과 사용법](https://github.com/YounghwanKil/haean/blob/main/docs/EXAM_INPUTS.md#선택한-참고문항을-새-계획에-붙이기)을 확인하세요.

검증 파일 목록이 큰 선택 참고자료에는 개발용 `--compact-reference-audit` 옵션을 사용할 수 있습니다. `generate`, `exam-build`, `exam-resume`에서 작성·수정·편집에 전달하는 중복 파일 목록만 보관 기록으로 연결하고 문항 전문·공식 답 상태·분류 근거·적용 범위는 유지합니다. 원 context와 출처 검증, 독립 풀이·고정 평가 입력은 그대로입니다. 기본 설정은 전체 전달이며, 재개 때도 옵션을 다시 지정합니다. 문자 수 감소를 실제 토큰 절감이나 품질 향상으로 해석하지 않습니다. [입력 축약 범위와 기록](https://github.com/YounghwanKil/haean/blob/main/docs/AUTHORING_INPUT.md)을 참고하세요.

## PSAT 검토와 언어이해 파일럿

PSAT 검토는 공통 독립 풀이·편집 역할에 급수·과목별 지침을 자동 연결한다. [과목별 검토 기준](https://github.com/YounghwanKil/haean/blob/main/docs/PSAT_REVIEW.md)을 참고한다. 새 지침의 실행 결과를 이전 회차에 소급하지 않는다.

자료해석의 정상 계산과 오독 계산이 실제로 다른 판정을 만드는지 확인하려면 `haean tools distractor-check CANDIDATE SIDECAR`를 선택적으로 사용한다. 현행 파일 해시·선지 원문에 연결한 식의 정확값과 진위 변화를 출력한다. 계산값이 달라도 진위는 같을 수 있다. 원자료 전사·오답 유인·최종 정답이나 승인 여부는 별도 검토하며, 이 자료를 블라인드 풀이에 전달하지 않는다. [입력 형식과 사용 예](https://github.com/YounghwanKil/haean/blob/main/docs/DISTRACTOR_CHECKS.md)를 참고한다.

LEET 언어이해는 `$haean-reading`과 별도 `reading` 명령으로 지문별 계획·작성·독립 검토·이어하기·book 조립을 관리한다. [언어이해 제작](Reading)을 참고한다. 10지문·30문항을 기존 HWP에 넣는 별도 어댑터가 있으며 실제 한글 배치는 회차마다 확인한다. 파일럿 지원이며 추리논증의 기본 스키마·고정 평가 점수를 사용하지 않는다.

언어이해의 텍스트형 `book.json`도 `haean tools review-packet 회차/book.json --out 새패킷`과 `review-collect 새패킷 실제응답.json`으로 팀 의견을 수집할 수 있다. 공통지문을 세 문항 앞에 한 번 표시하고 정답·해설을 분리한다. book 해시·지문 ID·문항 위치·실제 번호를 함께 확인하며, 패킷 ID는 해당 book 버전의 식별자다. 공통지문 수정 뒤에는 연결된 모든 문항을 재검토한다. 기존 candidate용 `feedback`·`human-checkpoint`에 언어이해를 넣지 않는다. 수집은 사람의 전문성·난도·한글 인쇄 확인이나 납품 승인을 인증하지 않는다.

## 긴 생성 작업의 진행 확인

Codex 대화 입력창이 아닌 별도 터미널에서 실행한다.

```sh
haean tools exam-status runs/example/production-v1
```

묶음별 마지막 요청 단계, 검토 버전 해시가 일치하는 문항 수, 마지막 검토의 오류와 편집 의견을 조회한다. 모델 호출이나 재시작은 하지 않는다. 마지막 요청 기록은 완료·프로세스 생존의 증거가 아니므로 원래 실행 터미널도 함께 확인한다. 수정 중에는 이전 오류를 보존하고 새 검토가 저장되면 갱신한다. 자세한 생성·재개 절차는 [제작 안내](https://github.com/YounghwanKil/haean/blob/main/docs/PRODUCTION.md)를 참고한다.
