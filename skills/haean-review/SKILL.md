---
name: haean-review
description: 해안 LEET·PSAT 문항의 독립 풀이, 논리 오류, 해설 동기화와 한국어 윤문을 검토한다. 출제 정답을 보지 않는 풀이와 편집 검토를 분리한다.
---

# 문항 검토

1. `scripts/haean-tool check RUN DRAFT`를 실행해 현행 문항을 고정한다. 기계 검증은 문항의 의미상 정답을 증명하지 않는다.
2. **독립 풀이에는 새 컨텍스트 서브에이전트 haean_blind_solver를 사용한다.** 입력은 `blind-input.json`, `blind.schema.json`, `blind-instructions.md`만이다. 출제 대화와 정답을 상속하지 않는다. 새 컨텍스트가 불가능하면 `scripts/haean-tool blind RUN`으로 별도 Codex 세션을 사용한다.
3. **haean_editor에게 편집 검토를 위임한다.** 현행 candidate, 독립 풀이 결과, `editorial-instructions.md`(`check`가 급수·과목별 지침을 생성한다), 관련 수정 사례를 읽게 한다. 출력은 `editorial.schema.json`에 맞춘 `editorial-result.json`이다.
4. 검토 당시 candidate 해시로 `review-result`를 실행한다. A/B 오류는 수정 후 check와 독립 검토를 반복한다. 기본 수정은 2회까지이며 해결되지 않은 것은 이유와 함께 표시한다.

출제자가 자신의 정답을 가리고 다시 생각하는 방식은 독립 컨텍스트가 아니다. 같은 모델을 별도 세션으로 호출하는 것은 컨텍스트 분리이며 모델 간 독립성을 뜻하지 않는다.

위임 도구에 역할 선택 인자가 없으면 `role haean_blind_solver` 또는 `role haean_editor`로 지침을 읽어 작업 메시지에 넣는다. 블라인드 에이전트는 부모 대화를 상속하지 않으며, 참고 경로를 따라 candidate·context·원문 정답을 탐색하지 않도록 공개 입력만 전달한다. 파일 읽기까지 격리할 수 없으면 입력만 받는 별도 Codex `blind` 명령을 우선한다.

윤문은 주술 호응·수식 범위·대명사·번역투를 고치되 논리 연산자·수치·조문·직접 인용을 보존한다. 단순 스타일 제안은 C로, 해석을 바꿀 수 있는 모호성은 B 이상으로 구분한다. 검토자의 주장도 문면과 반례로 확인한다.

이미 완성된 외부 문항의 검토 요청이면 입력 형식 때문에 검토를 멈추지 않는다. 먼저 읽을 수 있는 원문으로 검토하고, 구조화·내보내기가 필요할 때 스키마로 옮긴다. 필요한 원문·표·그림이 없으면 결손을 구체적으로 밝힌다.
