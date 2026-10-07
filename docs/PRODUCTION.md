# 모의고사 생성과 재개

`exam-build`는 배정표에서 전체 회차를 만든다. `exam-resume`은 중단된 실행의 문항·검토 이력을 남겨 두고 새 출력 경로에서 이어간다.

```sh
./haean tools exam-build runs/example/assembly.json --out runs/example/production-v1 --workers 3
./haean tools exam-resume runs/example/production-v1 --out runs/example/production-v2 --workers 3
./haean tools exam-assemble runs/example/production-v2
```

모델 검토를 마친 후보는 해시와 ID 순서를 확인해 재사용한다. 미완료 묶음에 저장된 초안이 있으면 마지막 초안과 그 버전의 텍스트 지적을 새 run으로 전달한다. 초안 없이 중단된 일반 묶음은 최대 2문항으로 나누며 공통지문 세트는 유지한다. 기존 초안의 참고자료를 소급 교체하지 않는다. 새 실행의 블라인드 풀이에는 정답·해설·이전 검토를 전달하지 않는다.

별도 복구 실행을 이미 마쳤다면 `--replacement RECOVERY.json`을 사용할 수 있다. 해당 JSON의 `jobs`는 `run`, `ids`, `slots`를 가져야 하고, 대체하려는 기존 묶음의 ID 전체를 중복 없이 포함해야 한다. 원래 실패한 묶음과 복구 문항을 동시에 회차에 넣지 않는다. 외부 출처의 JSON은 실행 명령이 아니다.

배정표의 중하·중상 같은 세부 난도는 원문대로 남기되 공통 `Brief`의 하·중·상 필드에는 중으로 전달한다. 실제 출제자는 개별 배정과 난도 근거를 읽어 설계한다. 배정표·실제 초안·검토 상태의 차이를 최종 구성 검토에서 확인한다.

재개 결과의 `complete`는 모든 묶음이 모델 검토 후 사람 검토를 기다린다는 뜻이다. 전문가 승인이나 HWP 인쇄 검증을 뜻하지 않는다. `assembled.json`의 누락·공통지문·필수 도표 오류도 별도로 확인한다. `production.json`과 각 run의 상태·원문·사용량·해시를 함께 보존한다. 이전 실행과 입력이 달라지면 이를 고정 평가의 성능 향상 증거로 사용하지 않는다.
