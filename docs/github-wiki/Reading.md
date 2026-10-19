# 언어이해 제작과 이어하기

해안 대화창에서 “언어이해 10지문·30문항을 구성하고 지문별로 작성·검토해 줘”라고 요청합니다. 총괄이 `haean-reading`을 읽고 별도 언어이해 계획과 작성 패킷을 만듭니다. 실전 난도가 검증된 상품이 아닌 파일럿 범위입니다.

별도 터미널에서는 다음처럼 진행 상태를 확인할 수 있습니다.

```sh
haean tools reading --help
haean tools reading status runs/leet-reading/회차
```

한 지문과 세 문항을 함께 등록하고, 정답·해설을 제외한 공개 입력으로 새 컨텍스트에서 독립 풀이합니다. 그 풀이를 고정한 뒤 편집 검토를 수행합니다. 수정하면 이전 검토는 보존하고 새 버전의 세 문항을 다시 검토합니다. 다음 세션에서도 `status`에 표시된 미완료 단계부터 이어갈 수 있습니다.

모든 지문의 현행 검토가 연결되면 `reading assemble`로 기존 `book.json`을 만들고, [사람 검토 패킷](Human-Review)과 [한글 출력](Layout)에 연결합니다. 명령 자체가 모델을 자동 호출하거나 사람 승인을 대신하지는 않습니다. 작성·풀이·편집은 총괄이 실제로 위임해야 합니다.

계획 JSON 예시, 단계별 명령과 기록 범위는 [언어이해 제작 안내](https://github.com/YounghwanKil/haean/blob/main/docs/READING_PRODUCTION.md)를 참고하세요.
