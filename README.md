# haean

팀 해안의 LEET·PSAT 문항 제작 에이전트. 자료 검색, 출제 명세, 초안 작성, 정답을 가린 풀이, 편집 검토, 수정, 팀 피드백을 하나의 작업 흐름으로 연결합니다.

지원 범위는 **LEET 추리논증**, **PSAT 5급·7급 언어논리·자료해석·상황판단**입니다. LEET 언어이해와 PSAT 9급은 별도 출제기로 구현하지 않았습니다.

## 시작하기

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
haean import-team ~/Downloads
haean status
pytest -q
```

`import-team`은 제공받은 파일명 목록에 있는 파일만 읽습니다. 다른 자료는 `haean import '/path/to/file'`로 추가합니다. 원본은 수정하지 않습니다. SQLite는 `data/corpus.sqlite`에 저장되며 동일 파일은 SHA-256으로 중복 제거합니다. Windows에서는 가상환경 활성화 방법이 다릅니다.

## 자연어로 사용하기

이 저장소를 에이전트에서 열고 다음처럼 요청하세요. `AGENTS.md`에 총괄 haean의 작업 절차가 있습니다.

> 해안, LEET 규범 영역에서 논증 평가 문항 2개 만들어줘. 소재는 디지털 공공서비스이고 난도는 중으로. 실제 수정 이력도 참고해줘.

> 해안, PSAT 7급 자료해석 25문항 구성표를 만들어줘. 추가채용 회차는 포함해.

> 해안, 이 문제의 날짜 조건을 줄였는데 정답과 해설이 여전히 성립하는지 검토해줘.

API 키 없이도 출제 패킷을 만들고, 현재 사용하는 에이전트가 패킷을 읽어 제작할 수 있습니다.

```bash
haean prepare --exam leet --subject 추리논증 --type '논증 평가 및 문제 해결' --topic '디지털 공공서비스' --count 2
haean prepare --exam psat7 --subject 자료해석 --type '자료 판단(보기)' --topic '공공도서관 이용 통계'
haean plan --exam psat5 --subject 상황판단 --out runs/psat5-plan.json
haean plan --exam psat7 --subject 언어논리 --exclude-extra --out runs/psat7-plan.json
haean search '기산점 판단불가' --exam leet
```

`prepare`는 생성된 문제를 가장하지 않습니다. `runs/<ID>/request.md`와 JSON 스키마를 만듭니다. 모델이 작성한 JSON을 다음 순서로 검증합니다.

```bash
haean check runs/<ID> runs/<ID>/draft.json
# 독립 풀이자는 blind-input.json만 보고 blind.schema.json에 맞춰 결과를 작성
# 편집 검토자는 현행 문항·독립 풀이·편집 지침을 보고 editorial.schema.json에 맞춰 작성
haean review-result runs/<ID> runs/<ID>/blind-result.json runs/<ID>/editorial-result.json --candidate-sha '검토 당시 candidate.sha256의 값'
haean export runs/<ID>
haean feedback runs/<ID> --item ITEM-001 --reviewer 팀검토자 --severity A --text '이의 제기 시점이 명시되지 않아 두 해석이 가능합니다.'
```

같은 대화에서 출제 후 다시 푸는 것은 엄밀한 독립 풀이가 아닙니다. 별도 컨텍스트 검토가 완료되기 전에는 독립 검토 대기 상태로 둡니다.

## API 자동 실행

계정에서 실제 사용할 수 있는 모델 ID를 명시합니다. 대화의 Astra라는 이름을 임의의 API 모델 ID로 바꾸지 않습니다. 키는 셸에서 설정하며 `.env`는 자동 로드하지 않습니다.

```bash
export OPENAI_API_KEY='본인 키'
export HAEAN_MODEL='사용 가능한 모델 ID'
export HAEAN_REVIEW_MODEL='검토에 사용할 모델 ID'
haean generate --exam psat5 --subject 언어논리 --type '강화·약화·평가' --topic '도시 소음과 집중력' --max-revisions 2
```

모델 호출에는 검색된 자료와 관련 피드백이 전달됩니다. 기본 흐름은 초안 → 별도 컨텍스트 풀이 → 편집 검토 → 필요 시 전체 수정입니다. 수정은 최대 2회, 기본 논리 호출 상한은 12회입니다. SDK의 일시적 오류 재시도는 별도이므로 이는 금액 상한이 아닙니다. 사용 토큰·모델·응답 ID는 `usage.json`에 남깁니다. 같은 모델을 써도 컨텍스트만 독립적이며 모델 간 독립성이나 정확도를 보장하지 않습니다.

구조화 출력은 [OpenAI 공식 문서](https://developers.openai.com/api/docs/guides/structured-outputs)에 따라 Pydantic 스키마로 받습니다. API 키 없이 수행한 테스트는 실제 모델의 품질 검증이 아닙니다.

## 결과와 한계

- `candidate.json`: 초안, 정답, 다섯 선지 판정, 표, 계산식, 출처 ID, 논평. 기존 Java 한글 도구가 읽을 수 있도록 어댑터를 붙일 기준 데이터입니다.
- `questions.html`, `solutions.html`: 문제·해설을 분리한 검토용 출력. 시대인재 HWP 양식과 동일한 납품 파일은 아닙니다.
- `status.json`: `prepared`, `awaiting_independent_review`, `awaiting_human_review`, `needs_revision`, `failed`. 자동으로 사람 승인 상태가 되지 않습니다.
- `feedback.jsonl`: 다음 출제에 반영할 과목별 검토 기록. 학습 가중치를 바꾸는 파인튜닝이 아니라 검색 기반 피드백입니다.

현재 PSAT 입력은 통계·발문·라벨이며 기출 전문이 아닙니다. HWP/HWPX에서는 텍스트를 읽지만 표·수식·도형의 시각적 완전성을 보장하지 않습니다. 원본 검토가 필요한 자료는 그 상태를 유지합니다. 문구 중복 검사는 일부 복제만 찾으며 의미상의 독창성은 편집 검토가 필요합니다.

회차 구성기는 유형별 배정과 초기 순서를 제안합니다. 소재·난도·정답 분포, 공유 지문 세트 배치까지 자동으로 완성하는 시험지 제작기는 아직 아닙니다. [자료 분석](docs/SOURCE_FINDINGS.md), [품질 기준](docs/QUALITY.md), [팀 작업법](docs/WORKFLOW.md)을 참고하세요.
