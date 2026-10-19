# 문항별 명세와 저장 원고 재평가

회차의 공통지문 묶음은 서로 다른 유형·난도의 문항을 포함할 수 있습니다. 평가 프로토콜 v3는 공통 `brief`와 함께 **원 배정의 ID별 유형·난도·소재**를 평가자에게 전달합니다. 후보가 스스로 표시한 유형·난도로 평가 목표를 바꾸지 않습니다. 점수 척도와 `evals/rubric.md`는 유지합니다.

`context.exam_assignment`가 있으면 해당 ID의 배정을 우선합니다. 없으면 공통 brief를 사용합니다. 선언된 배정이 비었거나 ID가 중복·누락되면 중단합니다. 목표를 준수했는지와 실제 문면의 난도는 별개의 판단입니다. 정답 분포용 `answer_target`은 정답의 근거로 전달하지 않습니다.

## 저장된 초안 평가하기

Codex에 로그인한 터미널에서 실행합니다. API 키는 필요하지 않습니다.

```sh
# 보존된 초기 초안·당시 검토
haean tools evaluate-run /절대경로/원run --revision 0 --out _workspace/eval-v3-initial

# 현재 candidate·해당 수정 번호의 검토
haean tools evaluate-run /절대경로/원run --out _workspace/eval-v3-final
```

각 명령은 평가 모델을 최대 1회 호출합니다. 기본 요청 모델은 `gpt-6-astra`이며 `--model`로 지정할 수 있습니다. 자동 재시도·재출제·재검토는 하지 않습니다. 결과 경로는 원 run 밖의 **새 디렉터리**여야 합니다. 기존 후보·평가·후속 피드백·검토 상태를 갱신하지 않습니다.

자동 파이프라인의 `brief.json`, `status.json`, 선택한 `draft-rN.json`/`review-rN.json`이 필요합니다. 현재 후보 선택 시 `candidate.json`도 검토 버전과 대조합니다. 일반 수동 `check`의 검토 envelope나 언어이해 book을 이 명령으로 재평가하지 않습니다.

기존 composition 실행은 저장된 revision receipt의 초안·검토 해시와 원 plan·context 연결을 재검증합니다. 저장된 composition 설계 생성 스냅샷의 코드 사본도 확인하지만, 당시 코드가 현재 평가 코드와 같을 필요는 없습니다. 문항 작성·풀이·편집의 전체 실행 코드를 소급 인증하는 절차는 아닙니다. 일반 생성·조립 경로는 계속 현행 코드 일치를 검사합니다. 연결 증거가 없는 옛 파이프라인은 `saved_provenance`의 요구·검토를 `unverified`로 표시하고 `eligible=false`를 유지합니다. `model_eligible`은 저장 검토와 모델 점수만의 진단 조건입니다. 로컬 해시는 변경 감지 근거이며 검토자 신원이나 독립 실행을 인증하지 않습니다. 단계별 출제(staged)의 별도 설계 계약과 수동 검토 연결은 이 재평가 명령의 확인 범위가 아닙니다.

출력에는 다음이 포함됩니다.

- `inputs/`: 실제 읽은 원 요청·초안·검토·연결 기록 사본
- `evaluation-input.json`, `rubric.md`, `evaluation.schema.json`: 평가자에게 전달한 입력·기준·출력 형식
- `execution/`: 실행 코드와 입력·지침·스키마의 고정 사본 및 해시
- `codex-traces/`, `evaluation.json`: 실제 호출 기록과 모델 결과
- `result.json`: 프로토콜, 원 경로·해시, 요청 모델, 사용량, 검증 상태와 한계

평가 폴더에는 원문·정답·검토 사본이 들어갑니다. 로컬 `_workspace`에 보관하고 공개 Git과 GitHub Wiki에는 원문·trace를 올리지 않습니다.

호출 중 입력·코드·기준이 바뀌거나 반환 ID가 잘못되면 실패로 기록합니다. 반환된 응답은 보존하지만 유효한 점수로 채택하지 않습니다. 현재 실행기는 요청 모델을 기록하며 실제 backend 모델 ID를 검증하지 않아 `actual_model=null`로 남깁니다.

## 결과를 해석할 때

v2와 v3의 점수를 직접 비교하지 않습니다. 초기·최종 원고를 같은 v3로 다시 평가하더라도 이는 **평가 입력 교정의 진단**이며 생성 하네스 A/B 실험은 아닙니다. 동일 원고의 반복 점수도 달라질 수 있습니다. 새로운 하네스 성능 주장은 고정 과제·동일 조건의 별도 비교와 전문가 확인이 필요합니다.

재평가는 해당 revision의 저장 검토만 읽으며 이후의 피드백 전체를 대신하지 않습니다. 예를 들어 후속 구조 반복 지적으로 `needs_revision`이 된 문항은 모델 점수가 높아져도 그 상태를 유지합니다. `eligible`은 납품 승인이나 현재 수정 의견 해소가 아닙니다. `release_approved`, `human_approved`, `expert_verified`, `native_layout_verified`는 모두 false입니다.

사람 검토 뒤의 `final-review`도 같은 문항별 요구사항을 사용하며 두 검토 단계 사이 요청 변경을 감지합니다. 최종 품질 자문은 새 독립 풀이·사람 승인과 구분합니다. 현재 보완은 brief/회차 배정 경로에 한정되며 staged의 모든 추가 설계 명세를 최종 자문으로 통합했다는 뜻은 아닙니다.
