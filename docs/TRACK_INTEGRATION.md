# 과목별 트랙 통합

기존 해안의 출제·독립 풀이·중복 검사·고정 평가·로컬 위키를 유지하면서 과목별 설계와 HWPX 조판을 연결한다. 기존 run과 자료를 새 형식으로 자동 덮어쓰지 않는다.

## 현재 연결 범위

`haean tools track`은 과목별 명세, JSON 스키마, 단계 지침과 참고 검색의 진입점이다. `attach`와 `generate`는 소재·핵심 판단 설계를 기존 문항 작성·독립 검토 흐름에 연결한다. 기존 `prepare`, `generate`, `evaluate`, `wiki`, `layout-fill` 명령의 입력 형식은 유지한다. 명세 검사 통과는 문항 품질 검증을 뜻하지 않는다.

[실제 연결 검증](STAGED_AUTHORING_SMOKE.md)에서 LEET 추리논증과 PSAT 5급 자료해석을 각 1회 생성·검토했다. 정답 검토와 별개로 추론 가치의 부족이 관찰되어 성능 개선으로 채택하지 않았다.

회차 전체는 별도 선택 [형식·내용설계 연결](COMPOSITION.md)을 제공한다. 외부 로컬 규칙으로 LEET 추리논증·PSAT 5급의 40슬롯을 설계하고, 기존 배정표와 명시 대응한 뒤 `exam-build --composition-packet`으로 작성·검토한다. 이 기능의 구조 검사와 설계 재현을 모델 성능 향상으로 합산하지 않는다.

```bash
haean tools track list
haean tools track schema brief
haean tools track brief-check data/my-track-brief.json
haean tools track rules psat_verbal design
haean tools track ref-build data/curated-references.jsonl --out data/track-references.sqlite
haean tools track ref-search data/my-query.json --index data/track-references.sqlite
```

기존 corpus에 등록한 완전한 PSAT 전사는 `track ref-export`로 선택한 ID만 정제 색인 입력으로 내보낼 수 있다. [원문 DB와 정제 참고자료 연결](REFERENCE_DATA.md)에 명시 선택 파일과 출처 검증 절차가 있다. 누락된 분류를 자동 추정하거나 통계·검토 행을 전문 사례로 바꾸지 않는다. 색인 수와 실제 요청의 검색 결과 수를 구분한다.

문항 버전과 연결되는 과거 검토 의견은 [검토 사례 내보내기](REVIEW_CASES.md)로 별도 색인할 수 있다. 선택된 사례는 작성·수정·편집 입력에 포함되며 독립 풀이에는 전달하지 않는다. 의견의 출처와 부분 수정 상태를 보존하고 현행 정답의 근거로 자동 채택하지 않는다.

새 트랙 명세 예시는 다음과 같다. 원문 자료가 아닌 합성 입력 예다.

```json
{
  "track": "psat_verbal", "grade": 5,
  "area": "사회", "area_detail": "경제·경영",
  "item_type": "일치부합", "item_format": "일반", "discourse": "평서문",
  "topic": "공공 도서관의 운영 방식", "difficulty": "중", "count": 1
}
```

트랙은 `leet_reasoning`, `leet_reading`, `psat_verbal`, `psat_data`, `psat_situation`이다. 급수·세트 정책·유형 어휘를 해당 트랙에서 확인한다. 새 명세를 기존 생성 명령에 그대로 전달하지 않는다. 연결 상태는 `track list`의 `integration_stage`와 한계 항목으로 확인한다.

## 소재·설계를 거쳐 기존 형식으로 작성하기

기존 `prepare`로 검색 자료를 고정한 새 run에 상세 트랙 명세를 연결한다. LEET 추리논증과 PSAT 5·7급 세 과목을 지원한다. 언어이해는 기존 파일럿 경로를 유지한다.

```bash
haean tools prepare --exam psat5 --subject 언어논리 --type 일치부합 --topic '공공 도서관의 운영 방식'
# 위 명령에서 받은 새 run 경로를 사용한다.
haean tools track attach RUN data/my-track-brief.json
haean tools track generate RUN --model gpt-6-astra --max-revisions 2
```

실행은 소재 → 설계 → 작성 → 새 컨텍스트 독립 풀이 → 편집 검토 순서다. 작성자는 처음부터 기존 `haean.models.Draft`로 쓴다. 따라서 `판단불가`, 근거, 난도 설명, 표와 기존 검토·출력 계약을 유지하며 native 블록 문항의 자동 변환은 하지 않는다. 매 수정 후에도 명세를 검사하고 독립 풀이·편집 검토를 새로 실행한다. 이 선택 경로의 구현은 기존 기본 프롬프트의 성능 개선이나 전문가 승인을 뜻하지 않는다.

선택 정제 색인은 `track attach ... --index data/track-references.sqlite`로 명시한다. 트랙 참고 사례와 기존 corpus 참고는 서로 다른 이름공간으로 보존한다. 기존 `source_ids`에 새 색인의 ID를 섞지 않는다. 원래 유형과 새 분류가 다르면 아래처럼 양쪽 이름과 대응 이유를 적은 JSON을 `--type-mapping`에 지정한다. 자동으로 동의어라고 가정하거나 고정 평가 과제의 유형을 바꾸지 않는다.

```json
{
  "legacy_item_type": "강화·약화·평가",
  "track_item_type": "강화·약화",
  "rationale": "이 요청은 정책 효과에 대한 강화·약화 판단을 구체 과제로 선택한다."
}
```

run의 `staged/`에는 명세·소재·설계·선택 참고와 실행 스냅샷을 남긴다. 실제 사용한 지침·스키마, 중첩 트랙 규칙을 포함한 패키지 코드, 입력과 호출 예산을 함께 기록한다. 실행 중 코드나 입력이 달라지면 성공 판정을 차단한다. 실패한 호출과 부분 산출물도 보존하므로 재시도는 새 run에서 시작한다. 기존 평가기의 fingerprint를 이 스냅샷으로 대체하거나 과거 점수를 다시 쓰지 않는다.

## Native 블록 문항을 HWPX 원고로 옮기기

이미 native 트랙 `Draft`로 작성된 문항은 명시적으로 변환할 수 있다. 위 staged 생성의 기존 `Draft`와 다른 스키마이며, 둘을 묵시적으로 바꾸지 않는다.

```bash
haean tools track manuscript data/track-brief.json data/native-draft.json --out runs/preview/manuscript.json
haean tools track manuscript data/track-brief.json data/native-draft.json --out runs/preview/student.json --student-only
```

이 어댑터는 새 원고 JSON만 만들고 원문을 수정하지 않는다. 지원하지 않는 급수·공통지문·그림 또는 보존할 수 없는 정보가 있으면 오류로 알린다. 학생용 원고에서는 정답·해설·제작 기록을 제외한다. 원고 변환 성공은 조판·독립 검토·실제 한글 출력 성공과 별개다.

HWPX 조판 코드는 선택 설치한다. 원고 JSON과 호환되는 문제·해설 양식을 별도로 준비해야 한다.

```bash
haean setup-typeset
haean typeset --help
haean typeset data/manuscript.json --profile psat5_data --template data/question-template.hwpx --solution-template data/solution-template.hwpx -o runs/preview/questions.hwpx --strict
```

기존 HWP 파일은 `layout-fill` 경로를 사용한다. 위 명령으로 파일이 만들어져도 한글에서의 페이지 배치를 확인한 상태는 아니다. 양식 파일을 공개 저장소에 넣지 않는다.

## 보존해야 하는 연결

| 기존 기능 | 통합 원칙 |
|---|---|
| 원문과 SQLite 검색 | 원문을 보존하고 새 정제 사례 색인을 별도 파일에 둔다. |
| `data/wiki` | 원문·출처 해시·locator와 연결한 종합 지식으로 유지한다. |
| GitHub Wiki | 설치·사용 설명서다. 내부 지식 위키나 대화 원문을 게시하지 않는다. |
| 누적 생성물·수정 이력 | ID와 버전을 유지하고 과거 원문으로 되돌아갈 수 있게 한다. |
| 독립 풀이 | 학생용 입력만 전달하고 변경된 조건·선지에 대한 검토를 갱신한다. |
| 고정 평가 | 평가기·기존 결과를 새 생성 구조에 맞춰 소급 수정하지 않는다. |
| HWP 출력 | 기존 양식 삽입을 유지한다. HWPX 코드 생성과 한글 렌더 확인은 별도 상태다. |

참고 검색은 시험·급수·유형의 부족분을 다른 제품군 자료로 조용히 메우지 않는다. 자료의 출처가 유효하다는 사실은 정답 검증이나 전문가 승인이 아니다. 원문·기출·양식·폰트·인증정보는 공개 배포 파일에 포함하지 않는다.

## 이어서 연결할 기능과 검증

1. 새 회차 설계 연결의 실제 모델 작성·독립 검토를 제품군별로 확인한다. 구현·합성 검증과 실제 회차 품질을 구분한다. 새 composition 경로의 PSAT 7급·언어이해는 아직 지원하지 않는다. 중단된 composition 회차는 원 설계·출처·검토 연결을 확인해 새 경로로 재개할 수 있다([재개 안내](PRODUCTION.md#외부-회차-설계를-사용한-실행-재개)).
2. 지문 이해 부담과 선지 판단 부담을 분리하고, 오답의 오류 경로와 핵심 판단 우회를 검토한다.
3. 검수 시간·토큰·재시도를 단계별로 측정한다. 결과를 재사용할 때 입력·지침·규칙·모델과 검토 증거의 일치를 확인한다.
4. native 블록 작성·그림·회차 조립을 HWPX 출력과 연결하고 실제 한글 배치를 확인한다.
5. 같은 과제·모델·수정 예산으로 생성과 독립 검토를 비교한다. 코드 테스트, 모델 평가, 사람 검토, 한글 렌더를 구분해 보고한다.

기능을 이식했다는 이유만으로 품질 향상이나 전문가 수준 출제를 주장하지 않는다. 각 연결 단계의 실행 증거를 남긴 뒤 사용 스킬과 기본 경로에 반영한다.


2026-10-19의 [단계형 출제 지침 비교](STAGED_BURDEN_COMPARISON.md)는 두 과제에서 양쪽 각 3회를 실행한 별도 모델 평가다. 후보는 일관된 개선을 보여주지 못해 기본 지침에 반영하지 않았다. 기능 연결의 성공과 출제 품질 향상을 구분한다.
