# 선택 원문쌍 구조 검토

`novelty-review`는 이미 저장된 후보 1–4문항 묶음 또는 언어이해 한 지문×3문항과 누적 이력에서 선택한 원문쌍을
새 Codex CLI 세션 한 번에 전달한다. ChatGPT 구독의 기존 `CodexProvider`를 사용하며
기본 요청 모델은 `gpt-6-astra`다. API 키 설정을 만들지 않는다.

```sh
scripts/haean-tool novelty-review runs/example \
  --out _workspace/example-novelty-review \
  --neighbors 1 --history data/generated.sqlite --model gpt-6-astra
```

일반 입력 RUN에 `candidate.json`, `brief.json`이 필요하고 `context.json`은 있으면 해시를 고정한다.
모델에는 context 전체 대신 exam_assignment의 명세 필드와 exam_contract만 전달한다.
기존 feedback·review·targeted_repair와 composition_resolution은 전달하지 않는다.
전체 회차의 `assembled.json` 폴더는 받지 않는다. 출력은 원 RUN 밖의 새 경로여야 한다.
이미 존재하는 폴더는 재사용하지 않는다. 실패한 실행도 같은 경로에서 덮어쓰지 않는다.

언어이해는 [별도 원문 어댑터](READING_NOVELTY.md)로 `book.json`, book 폴더, `reading` 제작 run 또는 attempt를 읽는다. 지문이 여럿이면 `--passage-id`로 하나를 고른다. `Brief`/`Item`으로 변환하지 않고 공통지문·세 문항 전문과 선택 문항 위치를 보존한다. 원고의 정답은 선택 문항에서 읽으며 그 문항의 네 오답 역할을 검증한다. 지문 단위 제작 입력의 계획·시도 결속도 확인한다.

## 선택과 버전

- 후보마다 기존 `novelty.audit`의 상위 `--neighbors`개(1–5, 기본 1)를 flag가 없어도 포함한다.
- 기존 규칙에 따라 반환된 모든 flag 후보도 포함한다. 검색 rank와 모델 관계 판정은 별개다.
- `context.exam_assignment`의 해당 후보 ID에 `based_on_item_id`가 있으면 같은 시험·과목의
  그 ID **모든 저장 버전**을 우선 포함한다. based_on에는 생성 때 사용한 버전 SHA가
  없으므로 current/latest를 당시 원형이라고 선택하지 않는다. 한 버전뿐이어도 당시
  사용 버전의 결속은 미확정이다. 해당 ID가 없으면 명시적으로 실패한다.
- 동일 시험·동일 ID의 이력 수정본은 기존 novelty 규칙대로 새 비교 대상으로 세지 않는다.
  based_on이 다른 ID를 명시하면 그 원형은 포함한다. 과목이 다른 이력은 검색하지 않는다.
- 같은 정확한 버전에 여러 선정 이유가 있으면 합친다. 최대 12쌍, 입력 UTF-8 500,000바이트다.
  초과 시 필수 based_on/flag를 잘라내지 않고 실패한다. 입력 바이트·문자 수와 실제 CLI usage를
  기록한다. 토큰 수는 사전 추정하지 않는다. 범위 조정은 별도 실행 계획으로 결정한다.

이력 DB의 원 파일을 먼저 해시로 고정하고 새 출력 폴더의 바이트 사본에만 기존
`novelty.history`를 적용한다. 원 DB는 쓰기 연결하지 않으며 읽은 사본의 바이트가 바뀌어도
실패한다. 미반영 WAL이 있는 DB는 안정된 사본을 제공할 때까지 거부한다.

## 원문과 결과 결속

`manifest.json`은 시작·완료 시각, candidate/brief/context/DB 및 확인한 출처 파일의
before raw SHA, 입력·프롬프트 SHA, 선택 이유, 크기, 모델 요청값, 호출 수, 사용량·trace와
산출물 SHA를 기록한다. 모델 직전·직후 입력 변경을 검사한다. 파일 해시는 로컬 변경 검출이며
서명이나 검토자 신원의 증명이 아니다.

`pairs.json`과 `review-input.json`에는 양쪽 원문 전문, canonical payload SHA,
기존 catalog digest, 고유 pair_id, 선택 이유와 source_resolution을 보존한다.
catalog digest와 canonical payload SHA는 직렬화 방식이 다르므로 별도 필드로 둔다.
`resolve_source`의 실제 파일 일치·보관본 일치·미해소·복수 일치·불완전 상태를 그대로 남긴다.
미해소일 때는 저장 payload 비교이며 원본 파일 확인이라고 하지 않는다.
언어이해의 출처는 book 원바이트 SHA와 지문·문항 위치로 대조하며 일반 run의 `revision-*` 경로를 추정하지 않는다. 출처가 다른 버전을 같은 ID의 새 문항으로 세지 않는다.
`retrieval.json`, `unselected-history.json`에는 검색 결과와 미선택 저장 버전을 남긴다.
같은 묶음 내부 쌍은 이번 명령의 모델 비교 대상이 아니다.

결과 스키마는 각 pair_id의 관계(구조 반복/정상 유형 재사용/명세 공통성/공유 자료/
실질 차이/불확실), 핵심 조건·결정 추론·네 오답 역할 대응, 양쪽 JSON pointer+정확한
원문 인용, 남은 불확실성, 권고를 요구한다. pair_id 누락·중복·추가, 버전 SHA 불일치,
포인터·인용 불일치, 네 오답 누락을 거부한다. 이 검사는 **의미 판정의 증명이 아니다**.

`draft.items`는 그림 렌더에만 사용하는 `{id, figures}`다. 이 id는 pair_id+side의
`rendering_id` 별칭이며 `pairs` 안의 원문 ID는 변경하지 않는다. `rendering_map`은
중복 ID의 서로 다른 버전까지 이미지와 연결한다. 기존 editor PNG 렌더·첨부를 재사용하며
그림 오류를 텍스트 검토로 대체하지 않는다. 실제 첨부·scope는 `codex-traces`에 남는다.
PNG 첨부는 HWP/PDF 배치 검증과 별개이며, JSON만으로 그림 확인 완료라고 하지 않는다.

## 결과의 범위

성공 상태는 `selected_pair_review_complete`다. 선택한 정확한 쌍에 대한 모델 검토 완료를
뜻한다. 전체 독창성 승인, 사람 전문가 확인, 정답 독립 풀이, 100회 연속 생성 실험,
평가 점수 개선을 뜻하지 않는다. 요청 모델을 기록하고 독립 확인하지 못한 actual_model은
null로 둔다. 관계가 structural_repeat여도 원 RUN의 status/review/feedback이나 누적 DB를
자동 변경하지 않는다. 후속 수정은 결과 근거를 확인한 뒤 기존 feedback 절차로 진행한다.

CLI는 1회만 호출하고 자동 재시도하지 않는다. 실패하면 manifest·CLI stdout/stderr·usage와
수신한 원응답을 보존한다. 구조화 결과를 받았다면 스키마 검사 전 `model-output.raw.json`에
보관한다. 프로세스 실패·시간 초과 때 수신 가능한 원문은 CLI trace에 남으며 완전한 최종
응답이 없을 수 있다. 일반 generate/run_pipeline, 고정 평가 입력·평가기에는 연결하지 않는다.
