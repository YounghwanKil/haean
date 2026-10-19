# 로컬 도구 사용법

언어이해는 [별도 지문별 제작](../../../docs/READING_PRODUCTION.md)의 `reading` 명령군을 쓴다. 아래 일반 `prepare/check/blind/export`와 입력·검토 스키마가 다르다.

`scripts/haean-tool`은 저장소 가상환경을 사용하고 저장소 루트에서 실행한다. 이 Python 도구는 데이터·검증을 담당한다. 문항을 쓰는 주체는 Codex다.

```bash
scripts/haean-tool status
scripts/haean-tool import '/path/to/source.xlsx'
scripts/haean-tool search '기산점 해설 오류' --exam leet
scripts/haean-tool prepare --exam leet --subject 추리논증 --type '논증 평가 및 문제 해결' --topic '공공 전자기록' --count 1
scripts/haean-tool prepare --exam psat7 --subject 자료해석 --type '자료 판단(보기)' --topic '공공도서관 이용 통계'
scripts/haean-tool check RUN RUN/draft.json
scripts/haean-tool blind RUN
# 외부 풀이 결과를 받은 경우만 별도 준비. CLI blind는 자동 준비한다.
# scripts/haean-tool editor-prepare RUN --blind RUN/blind-result.json
# 새 편집 양식으로 편집 검토를 위임한 뒤 결과 제출:
scripts/haean-tool review-result RUN RUN/blind-result.json RUN/editorial-result.json --candidate-sha SHA
scripts/haean-tool export RUN
scripts/haean-tool review-packet RUN --out runs/review-packet
scripts/haean-tool review-collect runs/review-packet 검토응답.json
scripts/haean-tool feedback RUN --item ITEM-001 --reviewer 팀검토자 --severity A --text '이의 제기 시점이 없습니다.'
scripts/haean-tool feedback RUN --item ITEM-001 --reviewer 팀검토자 --severity B --file 검토의견.txt
scripts/haean-tool feedback-note --exam psat7 --subject 자료해석 --reviewer 팀검토자 --file 검토의견.txt
scripts/haean-tool feedback-notes --exam psat7 --subject 자료해석
scripts/haean-tool plan --exam psat5 --subject 상황판단 --out runs/plan.json
```

`RUN`은 prepare가 출력한 경로다. `check`는 풀이 양식을 만들고, 풀이 완료 후 `editor-prepare`가 편집자가 대조할 풀이 사본과 편집 양식을 만든다. CLI `blind`는 이 준비까지 수행한다. 검토자는 읽은 버전의 `candidate.sha256`과 양식의 `input_binding`을 보관하고 `{result, evidence}` 형식으로 결과를 반환한다. `review-result`에는 **검토 당시 값과 결과**를 전달한다. 문항·지침·명세·요청 또는 편집 준비에 묶인 풀이가 다르면 거부된다. 풀이를 교체하거나 편집 준비를 새로 했다면 편집 검토도 다시 한다. 과거 결과에 최신 템플릿을 붙이지 않는다. 외부 검토자의 명시 기록은 검토 진위의 암호학적 보증은 아니다.

공통 텍스트 피드백은 `data/feedback/`에 원문·작성자·급수·과목·ID를 보존한다. `--exam team`은 공통 의견이며 모델 의견에는 `--origin model`을 붙인다. 등록은 지침 채택이 아니다. haean-evolve가 근거 문항과 대조해 후보 패치·평가 결과에 연결한다.

출력물에 대한 문항 피드백은 `feedback --candidate-sha 검토한_SHA`로 전달한다. 생략한 기존 호출은 제출 순간 파일 해시만 기록하며 검토 버전 확인을 뜻하지 않는다. 회차의 `items/NN`은 편집 뷰이므로 [사람 검토 패킷](../../../docs/HUMAN_REVIEW.md)에 기록된 `parent_run`에 의견을 연결한다. 검토 수집, 수정 필요 기록, 실제 사람 체크포인트는 별도 단계다.

회차를 `exam-resume`할 때는 [후속 의견 재개](../../../docs/PRODUCTION.md#검토-뒤에-추가한-의견)를 따른다. 저장 검토의 오류가 0이어도 현 후보에 연결된 후속 A/B 의견은 새 출제자에게 전달되어야 한다. 원검토를 고쳐 의견을 끼워 넣지 않는다. 원문의 구조 반복을 지적했다면 수정 후 같은 원문쌍의 추론·오답 역할을 다시 대조하며, 블라인드 풀이에는 이 자료를 전달하지 않는다.

`blind`는 현재 ChatGPT 로그인으로 `codex exec`를 실행한다. API 키를 사용하지 않는다. 임시 작업 폴더와 새 대화에 수험생용 내용만 전달하고, 도구 사용이 감지되면 독립 검토 결과로 채택하지 않는다. 이용 중인 Codex의 사용량 한도는 적용된다.

Python 의존성이 없으면 저장소 루트에서 `./haean setup`을 실행한다. 모델 선택·권한·로그인 설정은 사용자의 Codex 설정을 따른다. 로그인하지 않은 경우 `codex login`을 안내한다.

## 누적 생성물과 자기 반복 검사

`novelty-index RUN_OR_PRODUCTION ...`은 명시한 생성물을 로컬 `data/generated.sqlite`에 기록한다. 같은 시험·과목·문항 ID는 수정 계보로 취급하고 버전 해시를 보관한다. 새 문항에는 새 ID를 사용한다. 평가용 봉인 자료나 실험 폴더를 통째로 색인하지 않는다.

언어이해는 별도 원문 형식을 유지하면서 같은 명령을 사용한다. [언어이해 반복 검사](../../../docs/READING_NOVELTY.md)의 book·제작 run·attempt 입력, 지문 선택, 버전 한정 ID를 확인한다. 조회 과목은 `--exam leet --subject 언어이해`다. 지문과 세 문항을 함께 읽으며 기존 `Brief`/`Item`으로 변환하지 않는다.

### 과거 문항의 원문 연결

`novelty-memory --exam leet --subject 추리논증 --limit 40`으로 읽을 후보를 고르고, `novelty-get --exam leet --subject 추리논증 --item ITEM-ID --all-versions`로 지정한 문항의 저장 버전을 조회한다. 카드만 읽은 경우 전체 원문을 읽었다고 기록하지 않는다. 과거 실패와 수정 경위를 판단할 때는 현재 버전만으로 대신하지 않는다.

조회 결과의 `source`는 기록 당시 경로다. 이후 수정으로 그 파일의 내용이 바뀔 수 있으므로 `source_resolution`을 확인한다. `verified_origin`은 현재 경로의 일치, `resolved_archive`는 보관본에서 찾은 일치이며, 실제로 읽을 경로·locator·원파일 해시는 `matches`에 있다. `ambiguous`, `incomplete`, `unresolved`는 원문 연결을 확정하지 못한 상태다. `not_checked`인 색인 카드만으로 출처를 검증했다고 하지 않는다. 저장된 payload를 읽는 것은 가능하지만, 미확정 경로를 그 버전의 원본 파일로 인용하거나 임의의 다른 문항을 대체 근거로 쓰지 않는다. 상태·검색 범위·해시 직렬화는 [원문 경로 검증 계약](../../../docs/HISTORICAL_SOURCE_RESOLUTION.md)을 따른다.

기존 JSON 문항의 ID·파일 해시·locator를 옮겨 적은 프로필을 재사용한다면 `verify-source-profiles profiles.json --out NEW_REPORT.json`으로 실제 원문과 대조한다. 문항 ID의 숫자와 현재 시험지 번호가 같다고 가정하지 않는다. 입력 형식과 원문 해시 직렬화는 [프로필 검증 계약](../../../docs/SOURCE_IDENTITY_CANDIDATE.md)을 읽는다. 실패하면 원문과 연결 근거를 다시 확인하고 이전 기록을 남긴다. 통과한 파일의 해시만 다른 문항에 붙이거나, 보고서만 통과하도록 ID·해시를 바꾸지 않는다.

이 검사는 원문 연결의 기계 검증이다. 실제 읽은 범위, 논리·오답 구조의 대조, 정답 타당성은 별도로 기록한다. `valid: true`나 원문 경로 일치를 전문 독해·독창성·사람 승인으로 보고하지 않는다.

### 반복 후보 검토

`novelty-check RUN_OR_PRODUCTION ... --out RUN/novelty.json`은 누적 기록에서 과목별 유사 후보를 찾는다. PSAT 5·7급은 같은 과목끼리 교차 비교한다. 숫자·영문 기호를 정규화한 지문, 핵심 조건·해설, 선지의 문자 유사도를 사용한다. 동일 ID 수정본과 공통지문 공유는 별도로 처리한다. 빈 색인은 `catalog_missing_or_empty`로 드러나며 검사 완료 근거가 아니다.

검색된 원문쌍을 실제 모델 검토로 넘기려면 `novelty-review RUN --out NEW_DIR --neighbors 1`을 선택한다. [원문쌍 구조 검토](../../../docs/NOVELTY_REVIEW.md)의 입력 범위와 결과 해석을 읽는다. 후보 전문·역사 버전·선정 이유를 고정하고 새 Codex 세션에서 대조하며, 기존 candidate·검토·status·누적 DB를 변경하지 않는다. 단일 묶음의 선택 쌍 검토를 전체 누적 독창성이나 연속 100문항 생성 검증으로 확대하지 않는다.

새 회차 구성 전에 누적 소재·핵심 추론·오답 함정을 확인하고, 작성 뒤 `novelty-check`를 실행한다. 편집 검토자는 후보 쌍의 원문을 읽어 **정상적인 유형 재사용 / 의도한 공통지문 / 표현만 바꾼 같은 추론·함정 / 실질적으로 다른 문항**을 근거와 함께 구분한다. 높은 유사도만으로 탈락시키거나 낮은 유사도로 독창성을 승인하지 않는다. 새 소재·이름·수치만 바꾸는 수정은 반복 해소가 아니다. 반복이 확인되면 결정적 추론과 오답 설계부터 다시 작성한다. 검토한 후보·수정본도 누적 기록에 추가한다.

회차·누적 대량 생성 검토에서는 검색 상위 후보 외에도 유형별로 **핵심 전제 → 결정적 추론 → 각 오답의 실패 이유**를 짧게 정리해 대조한다. 문구가 달라도 이 세 역할이 반복되는 쌍을 추가 검토한다. 자동 검색 후보가 0개여도 이 과정을 생략하지 않는다. 유형별 정상 반복과 문항 구조 재사용의 경계는 근거를 남기고, 단일 사례를 모든 유형의 금지 규칙으로 일반화하지 않는다.

보기·선지의 역할을 대조할 때는 같은 번호끼리만 비교하지 않는다. 보기 순서를 바꾸면 동일한 추론 구조가 달라 보일 수 있으므로, 가능한 역할 대응(예: 한 문항의 ㄱ과 다른 문항의 ㄴ)을 먼저 정렬한 뒤 핵심 전제·결정적 추론·오류 경로의 실질적인 차이를 판단한다. 순서가 다르다는 이유만으로 독창성을 인정하거나, 보기 순서 변경을 구조 재사용의 해결로 보고하지 않는다. 검토자 사이에 판정이 다르면 원문 해시와 각 대응 근거를 함께 보존하고, 다수결이나 마지막 의견만으로 확정하지 않는다.

이 검사는 검색·검토 보조이며 고정 평가 점수를 바꾸지 않는다. 구조를 완전히 바꿔 표현한 재탕은 놓칠 수 있다. 장기 반복을 검증하려면 동일 명세의 연속 생성에서 1–10·11–50·51–100·101 이후 구간의 독립 판정 중복률과 최근접 쌍을 따로 기록한다. 서로 다른 시험의 100문항이나 같은 문항의 수정본을 ‘100회 연속 생성 실험’으로 보고하지 않는다.
