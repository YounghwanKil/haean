---
name: haean-review
description: 해안 LEET·PSAT 문항의 독립 풀이, 논리 오류, 해설 동기화와 한국어 윤문을 검토한다. 출제 정답을 보지 않는 풀이와 편집 검토를 분리한다.
---

# 문항 검토

1. `scripts/haean-tool check RUN DRAFT`를 실행해 현행 문항을 고정한다. 기계 검증은 문항의 의미상 정답을 증명하지 않는다.
2. **독립 풀이에는 새 컨텍스트 서브에이전트 haean_blind_solver를 사용한다.** 입력은 `blind-input.json`, `blind-instructions.md`, `blind-review-template.json`, `blind-review.schema.json`이다. 템플릿의 입력 연결 정보(`input_binding`)를 그대로 돌려주고 `result`에 풀이를 쓴다. 출제 대화와 정답을 상속하지 않는다. 새 컨텍스트가 불가능하면 `scripts/haean-tool blind RUN`으로 별도 Codex 세션을 사용한다.
3. **haean_editor에게 편집 검토를 위임한다.** 현행 candidate와 context, 독립 풀이 결과, `editorial-instructions.md`(`check`가 급수·과목별 지침을 생성한다), 관련 수정 사례와 `editorial-review-template.json`을 읽게 한다. 출력은 `editorial-review.schema.json`에 맞춘 `editorial-result.json`이다. `result`에 검토를, `evidence`에 검토 당시 입력 연결 정보와 실행 주체를 기록한다.
4. 검토 당시 candidate 해시로 `review-result`를 실행한다. 이 명령은 결과에 연결된 문항·지침·명세·요청 ID도 대조한다. 예전 raw 결과에 최신 연결 정보를 붙여 재사용하지 않는다. A/B 오류는 수정 후 check와 독립 검토를 반복한다. 기본 수정은 2회까지이며 해결되지 않은 것은 이유와 함께 표시한다.

같은 check 요청에서 블라인드 풀이만 다시 실행한 경우에도 편집자는 새 풀이와 대조해 결과를 갱신한다. 현재 수동 편집 결과의 연결 정보에는 대조한 블라인드 결과의 해시가 포함되지 않아 이 갱신을 자동으로 강제하지 못한다. 입력 연결 통과를 모든 검토 계보의 검증이라고 설명하지 않는다. 자동 단계형 생성은 매 수정마다 새 풀이·편집을 실행한다.

외부 검토 결과의 `producer.execution_mode`는 `external-attestation`이며 검토자, 요청 모델과 확인된 실제 모델을 구분한다. 확인하지 못한 모델 ID는 null로 둔다. 결과 해시는 실행기가 계산하므로 모델에게 계산시키지 않는다. 외부 검토자의 명시 기록은 실행 진위를 암호학적으로 증명하지 않는다. CLI `blind`는 실제 요청·응답 trace를 연결한다. 예전 연결 정보 없는 결과는 기록으로 보존하되 새 검토 통과 근거로 자동 승격하지 않는다.

LEET 추리논증의 편집 검토에는 `src/haean/prompts/leet_editorial.md`를 적용한다. `editorial-plan.json`과 `context.json`의 회차 소재·구조 컨텍스트가 있으면 함께 읽는다. 판단에 쓰이는 조건의 이관과 삭제, 주체·정의 변경에 따른 전체 동기화를 확인한다. 이 자료는 블라인드 풀이자에게 전달하지 않는다.

출제자가 자신의 정답을 가리고 다시 생각하는 방식은 독립 컨텍스트가 아니다. 같은 모델을 별도 세션으로 호출하는 것은 컨텍스트 분리이며 모델 간 독립성을 뜻하지 않는다.

위임 도구에 역할 선택 인자가 없으면 `role haean_blind_solver` 또는 `role haean_editor`로 지침을 읽어 작업 메시지에 넣는다. 블라인드 에이전트는 부모 대화를 상속하지 않으며, 참고 경로를 따라 candidate·context·원문 정답을 탐색하지 않도록 공개 입력만 전달한다. 파일 읽기까지 격리할 수 없으면 입력만 받는 별도 Codex `blind` 명령을 우선한다.

윤문은 주술 호응·수식 범위·대명사·번역투를 고치되 논리 연산자·수치·조문·직접 인용을 보존한다. 단순 스타일 제안은 C로, 해석을 바꿀 수 있는 모호성은 B 이상으로 구분한다. 검토자의 주장도 문면과 반례로 확인한다.

이미 완성된 외부 문항의 검토 요청이면 입력 형식 때문에 검토를 멈추지 않는다. 먼저 읽을 수 있는 원문으로 검토하고, 구조화·내보내기가 필요할 때 스키마로 옮긴다. 필요한 원문·표·그림이 없으면 결손을 구체적으로 밝힌다.
