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
