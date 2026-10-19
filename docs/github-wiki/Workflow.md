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

LEET 언어이해는 아래의 별도 파일럿 범위로 지원합니다. PSAT 5급은 과목당 40문항, 7급은 과목당 25문항 명세를 구분합니다. 회차 등록·파일 출력·모델 통과를 납품 승인으로 표시하지 않습니다.

## 소재와 판단을 먼저 설계하기

기존 `prepare`로 만든 새 run에 `haean tools track attach RUN 상세명세.json`을 연결하고 `haean tools track generate RUN`을 실행하면 소재 → 핵심 판단·오답 설계 → 기존 문항 형식 작성 → 독립 검토 순서로 진행합니다. 기존 자료·수정·검토 경로를 유지하는 선택 기능입니다. 현재 LEET 추리논증과 PSAT 5·7급 세 과목을 지원하며, 언어이해와 전체 회차 배정은 이 새 연결의 범위에 포함하지 않습니다.

명세 예시와 유형 대응, 별도 참고 색인, 실패 기록은 [트랙 통합 안내](https://github.com/YounghwanKil/haean/blob/main/docs/TRACK_INTEGRATION.md)를 확인하세요. 구현 완료와 출제 성능 향상은 별도로 검증합니다.

## 회차 전체의 형식·내용설계

별도 선택 기능인 `compose`는 로컬 규칙으로 40슬롯의 형식·내용설계를 만듭니다. LEET 추리논증과 PSAT 5급 세 과목을 지원하며, 기존 배정표의 ID·유형·난도·공통지문을 명시적으로 연결한 뒤 작성·검토합니다. PSAT 7급·언어이해는 기존 경로를 유지합니다. [회차 설계 사용법](Composition)을 참고하세요.

## PSAT 검토와 언어이해 파일럿

PSAT 검토는 공통 독립 풀이·편집 역할에 급수·과목별 지침을 자동 연결한다. [과목별 검토 기준](https://github.com/YounghwanKil/haean/blob/main/docs/PSAT_REVIEW.md)을 참고한다. 새 지침의 실행 결과를 이전 회차에 소급하지 않는다.

LEET 언어이해는 `$haean-reading`으로 파일럿을 작성·검토할 수 있다. 현재 기본 문항 스키마·고정 평가·HWP 자동 출력에 정식 통합된 상태는 아니다. 추리논증으로 표시하여 기존 평가 점수를 사용하지 않는다.

언어이해의 텍스트형 `book.json`도 `haean tools review-packet 회차/book.json --out 새패킷`과 `review-collect 새패킷 실제응답.json`으로 팀 의견을 수집할 수 있다. 공통지문을 세 문항 앞에 한 번 표시하고 정답·해설을 분리한다. book 해시·지문 ID·문항 위치·실제 번호를 함께 확인하며, 패킷 ID는 해당 book 버전의 식별자다. 공통지문 수정 뒤에는 연결된 모든 문항을 재검토한다. 기존 candidate용 `feedback`·`human-checkpoint`에 언어이해를 넣지 않는다. 수집은 사람의 전문성·난도·한글 인쇄 확인이나 납품 승인을 인증하지 않는다.

## 긴 생성 작업의 진행 확인

Codex 대화 입력창이 아닌 별도 터미널에서 실행한다.

```sh
haean tools exam-status runs/example/production-v1
```

묶음별 마지막 요청 단계, 검토 버전 해시가 일치하는 문항 수, 마지막 검토의 오류와 편집 의견을 조회한다. 모델 호출이나 재시작은 하지 않는다. 마지막 요청 기록은 완료·프로세스 생존의 증거가 아니므로 원래 실행 터미널도 함께 확인한다. 수정 중에는 이전 오류를 보존하고 새 검토가 저장되면 갱신한다. 자세한 생성·재개 절차는 [제작 안내](https://github.com/YounghwanKil/haean/blob/main/docs/PRODUCTION.md)를 참고한다.
