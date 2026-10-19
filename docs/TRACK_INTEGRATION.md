# 과목별 트랙 통합

기존 해안의 출제·독립 풀이·중복 검사·고정 평가·로컬 위키를 유지하면서 과목별 설계와 HWPX 조판을 연결한다. 기존 run과 자료를 새 형식으로 자동 덮어쓰지 않는다.

## 현재 연결 범위

`haean tools track`은 과목별 명세, JSON 스키마, 단계 지침과 참고 검색의 진입점이다. 이 단계의 명세 검사 통과는 실제 문항 생성이나 품질 검증을 뜻하지 않는다. 기존 `prepare`, `generate`, `evaluate`, `wiki`, `layout-fill` 명령의 입력 형식은 유지한다.

```bash
haean tools track list
haean tools track schema brief
haean tools track brief-check data/my-track-brief.json
haean tools track rules psat_verbal design
haean tools track ref-build data/curated-references.jsonl --out data/track-references.sqlite
haean tools track ref-search data/my-query.json --index data/track-references.sqlite
```

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

1. 형식 설계 → 내용 설계 → 작성의 산출물을 기존 run·출처·누적 문항 이력에 연결한다.
2. 지문 이해 부담과 선지 판단 부담을 분리하고, 오답의 오류 경로와 핵심 판단 우회를 검토한다.
3. 검수 시간·토큰·재시도를 단계별로 측정한다. 결과를 재사용할 때 입력·지침·규칙·모델과 검토 증거의 일치를 확인한다.
4. 외부 양식을 받는 HWPX 조판을 통합하고, 표·그림·보기·해설의 내용 보존과 실제 한글 배치를 확인한다.
5. 같은 과제·모델·수정 예산으로 생성과 독립 검토를 비교한다. 코드 테스트, 모델 평가, 사람 검토, 한글 렌더를 구분해 보고한다.

기능을 이식했다는 이유만으로 품질 향상이나 전문가 수준 출제를 주장하지 않는다. 각 연결 단계의 실행 증거를 남긴 뒤 사용 스킬과 기본 경로에 반영한다.
