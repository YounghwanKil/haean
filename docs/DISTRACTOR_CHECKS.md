# 선택형 수치 오독 경로 점검

`distractor-check`는 출제자나 편집자가 명시한 정상식과 오독식에 대해 **해당 비교의 진위가 바뀌는지** 계산한다. 문항 제작 중 필요할 때 따로 작성하는 선택 검토 보조지이며 기존 문항 스키마, 검토 게이트, 평가 점수, 승인 상태를 바꾸지 않는다.

```sh
scripts/haean-tool distractor-check runs/example/candidate.json _workspace/example-sidecar.json
```

성공하면 stdout에 JSON을 출력한다. 파일을 만들거나 입력·`status.json`을 고치지 않는다. 파일 읽기, JSON 구조, SHA 연결, 문항·target 연결, 인용문, 산술식 오류가 있으면 실패하고 CLI는 종료 코드 2와 stderr 메시지를 반환한다. 부분 성공 보고서는 출력하지 않는다. 출제 판정 불일치는 검토용 결과이므로 명령 실패 사유가 아니다.

## 입력 sidecar

두 번째 인수는 아래 형식의 JSON 파일이다. 모든 필드를 명시하며 알려지지 않은 필드와 중복 JSON 키는 거부한다. `candidate_sha256`은 첫 번째 인수로 지정한 candidate 파일의 **원본 바이트 SHA-256**이다. 공백만 바뀌어도 다시 연결해야 한다. `shasum -a 256 runs/example/candidate.json`으로 확인할 수 있다.

다음은 합성 예다. SHA 자리에는 실제 candidate의 64자리 소문자 해시를 넣고 문항 ID와 선지 원문도 해당 candidate와 일치시킨다.

```json
{
  "candidate_sha256": "여기에 실제 candidate 파일의 SHA-256",
  "checks": [
    {
      "item_id": "SYNTHETIC-DATA-1",
      "target": "1",
      "statement_text": "합성 비율은 기준값보다 크다.",
      "source_locator": "합성 표의 분자와 분모",
      "misread_description": "분모 100을 80으로 읽음",
      "normal": {"left": "60/100", "operator": ">", "right": "1/2"},
      "misread": {"left": "60/80", "operator": ">", "right": "1/2"}
    }
  ]
}
```

- `checks`는 비어 있지 않은 배열이다. 같은 target의 다른 오독을 여러 행으로 적을 수 있다.
- `item_id`는 candidate에서 유일해야 하고, `target`은 그 문항의 `judgments`에 정확히 한 번 있어야 한다. 번호는 문자열 `"1"`처럼 적는다.
- target이 `"1"`~`"5"`이면 `statement_text`가 해당 선지 전체 원문과 완전히 같아야 한다. 일부 인용이나 공백 정규화는 하지 않는다.
- 그 외 target은 `statement_text`가 `statements`의 원문 한 개와 완전히 같아야 한다. `ㄱ.`, `A)` 등 단일 한글 자음·영문자와 구두점으로 표시된 라벨은 target과 대조한다. 표시가 없으면 `target_link: "declared_only"`로 보고하고 보기와 target의 대응을 사람이 확인한다. 자연어 의미를 분석하지 않는다.
- `source_locator`와 `misread_description`은 사람이 원자료를 대조할 때 쓸 비어 있지 않은 기록이다. 경로를 열거나 설명 속 지시를 실행하지 않는다.
- `normal`, `misread`는 각각 `left`, `operator`, `right`를 가진다. 양쪽 식 모두 문자열이며 기존 `validation.arithmetic`의 숫자·사칙연산·괄호와 길이·복잡도 제한을 적용한다. 비교 연산자는 `==`, `!=`, `<`, `<=`, `>`, `>=`만 허용한다. `eval`이나 별도 계산기는 사용하지 않는다.

소수는 이진 부동소수점으로 반올림된 값 대신 입력한 숫자 원문을 유리수로 읽는다. 따라서 `1.0000000000000001 > 1`이나 `1e-400 > 0`의 차이를 보존한다. 과도한 분수 생성을 막기 위해 과학적 표기의 지수 절댓값은 1,000까지 허용한다. 기존 숫자 크기·식 길이·복잡도 제한도 유지한다.

## 결과 해석

결과에는 읽은 candidate와 sidecar 각각의 파일 SHA-256, 행별 원문 연결, 좌우 식의 정확한 유리수 문자열(`left_exact`, `right_exact`), 비교 진위(`truth`), `truth_changed`가 담긴다. 정수는 `"1"`, 분수는 `"3/5"`처럼 표현한다. 보기의 `statement_binding.index`는 0부터 센다.

위 예는 정상값 `3/5`와 오독값 `3/4`가 모두 `1/2`보다 커서 `truth_changed: false`다. 양쪽 `right`를 `"7/10"`으로 바꾸면 거짓에서 참으로 바뀌어 `true`다. 값이 다르다는 사실만으로 그 오독이 해당 비교의 판정을 바꾸지는 않는다. 등호의 포함 여부도 명시한 연산자 그대로 계산한다.

`authored_verdict`는 연결된 현행 `Judgment.verdict`를 보존한다. 참·거짓만 bool `authored_truth`로 옮겨 정상 비교와 대조하고 `normal_matches_authored_verdict` 및 `authored_verdict_comparison`의 `match`/`mismatch`로 보고한다. **판단불가는 거짓으로 취급하지 않는다.** 이 경우 두 bool 대응 필드는 `null`이고 비교 상태는 `not_boolean`이다.

이 비교는 입력한 식의 계산 결과다. 복합 선지의 일부 조건만 적었다면 출제 판정과 정상 비교가 달라도 그 자체로 문항 오류가 확정되지는 않는다. 비교식과 선지 전체의 의미 관계, 부정·조건·범위는 편집자가 확인한다. 도구는 비교식을 출제 정답으로 강제하지 않는다.

`truth_changed`는 한 오독을 적용한 **입력 비교의 진위 변화**만 뜻한다. 최종 정답 번호 변화, 오답의 개연성, 원자료 전사 정확성, 검토 완료나 품질 승인에 대한 증명이 아니다. 원자료의 수치를 잘못 옮겨도 식은 계산될 수 있다. 두 비교의 연산자가 다르면 그 차이도 입력한 오독의 일부이므로 사람이 적절성을 검토한다.

이 결과는 출제자 기록을 볼 수 있는 편집 검토에서 원자료·해설과 함께 사용한다. 정답·정상식·오독식을 담은 sidecar와 결과를 블라인드 풀이에 제공하지 않는다. 자동 검토 흐름에 연결하거나 모든 문항에 작성을 요구하지 않는다.
