# 언어이해 지문별 제작

언어이해는 `reading` 명령으로 계획·작성·독립 검토를 연결한다. Codex가 실제 원고를 쓰고 풀이하며, 보조 명령은 파일과 검토 버전을 관리한다. `prepare`만 실행하면 문항이 자동 생성되는 것은 아니다. 추리논증용 `Brief`, `exam-build`, 고정 평가 점수와는 별도 경로다.

## 계획과 작성

총괄이 아래 형식으로 계획을 쓴다. `full`은 10지문·30문항, `pilot`은 1~9지문이다. 각 지문의 문항 번호는 전체 회차에서 1부터 이어지고, 지문·문항 ID는 수정해도 유지한다. 아래는 합성 이론으로 만드는 1지문 예시이며 공식 영역 비율이나 실전 난도 표본이 아니다.

```json
{
  "version": 1,
  "mode": "pilot",
  "title": "해안 언어이해 제작 시험",
  "minutes": 7,
  "passages": [{
    "id": "READ-P01",
    "domain": "인문",
    "topic": "가상 이론의 기록 분류 기준",
    "structure": "두 관점의 기준을 비교하고 경계 사례에 적용",
    "sources": ["가상 이론으로 작성하며 실제 학설이나 역사적 사실로 제시하지 않는다."],
    "questions": [
      {"id": "READ-Q01", "number": 1, "cognitive_task": "정보 확인·재구성", "difficulty": "하"},
      {"id": "READ-Q02", "number": 2, "cognitive_task": "추론·해석", "difficulty": "중"},
      {"id": "READ-Q03", "number": 3, "cognitive_task": "평가·적용", "difficulty": "상"}
    ]
  }]
}
```

인지과제는 위 세 가지와 `주제·구조·관점 파악` 중 선택한다. 지문별 과제·내용 영역·전개 구조를 따로 설계하고, 같은 관계를 세 번 확인하는 구성을 피한다. `sources`에 글을 적었다는 사실만으로 출처가 검증되지는 않는다. 실제 자료를 쓰면 읽은 원문과 위치, 사실 확인 범위를 제작 기록에 남긴다.

```sh
haean tools reading prepare runs/reading-plan.json --out runs/reading-next
haean tools reading status runs/reading-next
```

각 지문의 작성 패킷을 별도 출제자에게 전달한다. 일반 서브에이전트를 사용하며 추리논증 전용 writer를 이름만 바꿔 쓰지 않는다. 출력은 패킷의 `candidate.schema.json`에 맞춘 **1지문×3문항 book**이다. 계획에 고정한 번호·ID·인지과제·난도를 유지하고 정답·전체 해설·선지별 근거·가장 강한 반대 해석을 함께 쓴다. 한 회차를 나눠 작성할 때는 총괄만 등록 명령을 실행한다.

```sh
haean tools reading check runs/reading-next --passage READ-P01 --draft runs/reading-draft.json
```

등록할 때마다 새 시도 폴더를 만들고 이전 원고와 검토는 보존한다. `check` 결과와 `status`에 표시된 현행 경로를 사용한다. 새 파일을 이전 시도 폴더에 직접 덮어쓰지 않는다.

계획 전에는 누적 생성 이력에서 소재·추론·오답 설계를 확인한다. 작성 후 [언어이해 반복 검사](READING_NOVELTY.md)로 현재 지문을 과거 문항과 대조하고, 필요한 원문쌍 검토를 별도로 수행한다. 검토한 원고는 `novelty-index`로 명시 등록한다. `reading check`나 `assemble`이 누적 DB를 자동 갱신하거나 독창성을 승인하지는 않는다.

## 독립 풀이와 편집 검토

1. 새 컨텍스트 풀이자에게 현행 `student.json`과 `blind-request`의 공개 입력·지침·응답 스키마/양식만 전달한다. 지문·발문·보기·선지 외의 출제 계획, 정답·해설, 이전 검토, 부모 대화를 주지 않는다.
2. 풀이 결과를 등록하여 편집 입력을 준비한다. 편집 검토자는 이 준비가 고정한 원고·독립 풀이·지침과 새 응답 양식을 읽는다.
3. 편집 결과를 등록한다. 결과를 다른 버전에 옮겨 붙이거나 최신 binding을 예전 결과에 붙이지 않는다.

```sh
haean tools reading editor-prepare runs/reading-next --passage READ-P01 --blind runs/reading-blind.json
haean tools reading review-result runs/reading-next --passage READ-P01 --editorial runs/reading-editorial.json
haean tools reading status runs/reading-next
```

외부 위임 결과의 `producer`는 `external-attestation`으로 실행 주체와 요청 모델을 기록한다. 확인되지 않은 실제 모델은 `null`이다. 파일 연결은 어떤 입력 버전을 대상으로 했는지 확인하는 장치이며, 실제 독립 실행 자체를 증명하지 않는다. 새 세션을 사용할 수 없으면 독립 검토 대기로 남긴다. 별도 Codex 실행을 이용했다면 요청·응답 원문과 사용량도 보존한다.

독립 풀이가 정답과 다르거나 유일성을 인정하지 못한 경우, 편집 A/B 오류가 있는 경우에는 수정이 필요하다. 지문이나 해설만 고쳐도 `check`부터 새 시도로 등록하고 세 문항의 독립 풀이·편집을 다시 받는다. C 의견은 남겨 두며 기본 수정 예산은 2회다. 구조 검증과 모델 간 일치로 전문가 수준이나 실전 난도를 확정하지 않는다.

## 이어하기와 조립

다음 세션에서 같은 run의 `reading status`를 읽어 미완료 단계부터 이어간다. 완료된 지문을 새로 생성할 필요는 없다. 계획 변경은 새 run으로 시작하고, 오래된 계획·원고·풀이·편집 파일의 해시를 고쳐 다시 승인하지 않는다.

총괄은 중단할 때 `RUN/handoff.md`에 생산 run 경로와 남은 지문·단계를 남긴다. 경로 없이 이어하기를 요청하면 대화·handoff를 우선하고, 필요하면 `runs/leet-reading/`의 plan·manifest를 찾아 현재 상태를 확인한다. 후보가 여럿이면 회차를 선택한다. `track-exam`은 조립된 book을 등록하므로 미조립 작업의 목록을 대신하지 않는다.

```sh
haean tools reading assemble runs/reading-next --out runs/reading-next-book
haean tools review-packet runs/reading-next-book/book.json --out runs/reading-next-review
haean track-exam runs/reading-next-book
```

계획에 있는 **모든 지문**에 현재 원고와 연결된 풀이·편집 결과가 있어야 조립할 수 있다. 빠진 지문이 있는 full 계획을 30문항 완성본으로 만들지 않는다. 조립된 `book.json`은 기존 사람 검토 패킷과 현재 회차 등록에 연결되며, `verification.json`에는 사용한 버전과 사람 승인·native 출력의 미확인 상태를 남긴다. `pilot`의 짧은 book도 사람 검토는 가능하지만 한글 전체 회차 어댑터는 10지문·30문항만 받는다.

전체 회차 출력은 [한글 양식](LAYOUT.md)의 `haean.reading_layout`을 따른다. HWP 생성과 텍스트 재읽기, 실제 한글에서의 PDF·배치 검증은 구분한다. 조립은 모델 검토본 준비이며, 사람의 최종 승인이나 자동 납품 완료가 아니다.
