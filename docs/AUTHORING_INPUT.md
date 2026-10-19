# 작성·편집 입력의 검증 목록 축약

`generate`, `exam-build`, `exam-resume`에 `--compact-reference-audit`를 지정하면 작성·수정·편집 모델에 전달할 선택 참고자료의 검증 파일 목록을 별도 보관 기록으로 대체한다. 기본 동작은 전체 입력을 그대로 전달하는 것이다. 이 옵션은 개발용 입력 기능이며 출제 품질이 개선됐다고 검증한 기본 설정이 아니다.

```bash
haean tools exam-build runs/plan-with-references/plan.json \
  --out runs/production-compact --compact-reference-audit
```

축약 대상은 `selected_reference_input.references[].source` 안의 `evidence_files`와 `official_answer.evidence.files` 두 목록뿐이다. 알려진 파일 경로·해시 형식만 처리하며, 파일별 이름과 locator·usage는 보존한다. 새로운 키나 예상하지 못한 구조가 섞인 목록은 그대로 전달한다. 학생용 문면, 출처 ID, 공식 답과 그 확인 상태, 분류 근거·불확실성, 전사 주의, `application`·`match_scope`·`gaps`와 그 밖의 필드는 삭제하지 않는다.

원본 `context.json`과 `request.md`, 출처 검증·composition 연결은 전체 자료를 기준으로 유지한다. 별도 보관한 원 context의 경로·바이트 해시와 목록의 JSON Pointer·해시를 축약 기록에 남기고, 실제 모델 입력 사본도 저장한다. 작성·편집 후의 출처 재검증도 원자료에 적용한다. 독립 풀이에는 기존대로 학생용 문항만 전달하며 고정 평가 입력은 바꾸지 않는다.

각 묶음의 `authoring-inputs/<실행 식별자>/`에 `original-context.json`, `projection-manifest.json`, `writer-context.json`, `editor-exam-assignment.json`, `delivery-manifest.json`을 남긴다. 마지막 파일은 각 사본의 해시와 적용 범위를 기록한다. 전체 요청·현행 원고·검토 의견을 포함한 실제 호출 payload는 기존 `codex-traces`에서 확인한다. `request.md`는 원본 자료를 보는 문서이며 축약 후 실제 전송본과 구분한다.

재개 실행에서는 이 옵션을 다시 명시한다. 이전 run의 입력이나 기록은 소급 변경하지 않는다. 별도 `track generate`와 언어이해 `reading` 경로에는 이 옵션을 적용하지 않는다. 축약 전후 JSON 문자 수는 입력 크기 관찰이며 실제 토큰 절감이나 품질 향상의 증거가 아니다. 성능을 비교하려면 동일 과제·모델·수정 예산에서 실제 사용량과 원문 평가를 함께 확인한다.

원자료 선택과 출처 ID 연결은 [전체 회차 입력 안내](EXAM_INPUTS.md)를 따른다.
