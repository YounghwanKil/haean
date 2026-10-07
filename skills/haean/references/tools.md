# 로컬 도구 사용법

`scripts/haean-tool`은 저장소 가상환경을 사용하고 저장소 루트에서 실행한다. 이 Python 도구는 데이터·검증을 담당한다. 문항을 쓰는 주체는 Codex다.

```bash
scripts/haean-tool status
scripts/haean-tool import '/path/to/source.xlsx'
scripts/haean-tool search '기산점 해설 오류' --exam leet
scripts/haean-tool prepare --exam leet --subject 추리논증 --type '논증 평가 및 문제 해결' --topic '공공 전자기록' --count 1
scripts/haean-tool prepare --exam psat7 --subject 자료해석 --type '자료 판단(보기)' --topic '공공도서관 이용 통계'
scripts/haean-tool check RUN RUN/draft.json
scripts/haean-tool blind RUN
scripts/haean-tool review-result RUN RUN/blind-result.json RUN/editorial-result.json --candidate-sha SHA
scripts/haean-tool export RUN
scripts/haean-tool feedback RUN --item ITEM-001 --reviewer 팀검토자 --severity A --text '이의 제기 시점이 없습니다.'
scripts/haean-tool feedback RUN --item ITEM-001 --reviewer 팀검토자 --severity B --file 검토의견.txt
scripts/haean-tool feedback-note --exam psat7 --subject 자료해석 --reviewer 팀검토자 --file 검토의견.txt
scripts/haean-tool feedback-notes --exam psat7 --subject 자료해석
scripts/haean-tool plan --exam psat5 --subject 상황판단 --out runs/plan.json
```

`RUN`은 prepare가 출력한 경로다. `check` 전후 문항을 수정하면 해시가 달라진다. 검토자는 읽은 버전의 `candidate.sha256`을 보관하고, review-result에는 **검토 당시 값**을 전달한다. 새 값으로 바꿔 끼워 오래된 검토를 통과시키지 않는다.

공통 텍스트 피드백은 `data/feedback/`에 원문·작성자·급수·과목·ID를 보존한다. `--exam team`은 공통 의견이며 모델 의견에는 `--origin model`을 붙인다. 등록은 지침 채택이 아니다. haean-evolve가 근거 문항과 대조해 후보 패치·평가 결과에 연결한다.

`blind`는 현재 ChatGPT 로그인으로 `codex exec`를 실행한다. API 키를 사용하지 않는다. 임시 작업 폴더와 새 대화에 수험생용 내용만 전달하고, 도구 사용이 감지되면 독립 검토 결과로 채택하지 않는다. 이용 중인 Codex의 사용량 한도는 적용된다.

Python 의존성이 없으면 저장소 루트에서 `./haean setup`을 실행한다. 모델 선택·권한·로그인 설정은 사용자의 Codex 설정을 따른다. 로그인하지 않은 경우 `codex login`을 안내한다.

## 누적 생성물과 자기 반복 검사

`novelty-index RUN_OR_PRODUCTION ...`은 명시한 생성물을 로컬 `data/generated.sqlite`에 기록한다. 같은 시험·과목·문항 ID는 수정 계보로 취급하고 버전 해시를 보관한다. 새 문항에는 새 ID를 사용한다. 평가용 봉인 자료나 실험 폴더를 통째로 색인하지 않는다.

`novelty-check RUN_OR_PRODUCTION ... --out RUN/novelty.json`은 누적 기록에서 과목별 유사 후보를 찾는다. PSAT 5·7급은 같은 과목끼리 교차 비교한다. 숫자·영문 기호를 정규화한 지문, 핵심 조건·해설, 선지의 문자 유사도를 사용한다. 동일 ID 수정본과 공통지문 공유는 별도로 처리한다. 빈 색인은 `catalog_missing_or_empty`로 드러나며 검사 완료 근거가 아니다.

새 회차 구성 전에 누적 소재·핵심 추론·오답 함정을 확인하고, 작성 뒤 `novelty-check`를 실행한다. 편집 검토자는 후보 쌍의 원문을 읽어 **정상적인 유형 재사용 / 의도한 공통지문 / 표현만 바꾼 같은 추론·함정 / 실질적으로 다른 문항**을 근거와 함께 구분한다. 높은 유사도만으로 탈락시키거나 낮은 유사도로 독창성을 승인하지 않는다. 새 소재·이름·수치만 바꾸는 수정은 반복 해소가 아니다. 반복이 확인되면 결정적 추론과 오답 설계부터 다시 작성한다. 검토한 후보·수정본도 누적 기록에 추가한다.

회차·누적 대량 생성 검토에서는 검색 상위 후보 외에도 유형별로 **핵심 전제 → 결정적 추론 → 각 오답의 실패 이유**를 짧게 정리해 대조한다. 문구가 달라도 이 세 역할이 반복되는 쌍을 추가 검토한다. 자동 검색 후보가 0개여도 이 과정을 생략하지 않는다. 유형별 정상 반복과 문항 구조 재사용의 경계는 근거를 남기고, 단일 사례를 모든 유형의 금지 규칙으로 일반화하지 않는다.

이 검사는 검색·검토 보조이며 고정 평가 점수를 바꾸지 않는다. 구조를 완전히 바꿔 표현한 재탕은 놓칠 수 있다. 장기 반복을 검증하려면 동일 명세의 연속 생성에서 1–10·11–50·51–100·101 이후 구간의 독립 판정 중복률과 최근접 쌍을 따로 기록한다. 서로 다른 시험의 100문항이나 같은 문항의 수정본을 ‘100회 연속 생성 실험’으로 보고하지 않는다.
