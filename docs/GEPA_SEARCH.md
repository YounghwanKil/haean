# GEPA에서 가져온 후보 탐색

논문: [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457), v2. 공식 구현: [gepa-ai/gepa](https://github.com/gepa-ai/gepa/tree/8f287de942f41a6d1e0e7e5b2d576247c4bedee9). 2026-10-20 확인한 커밋을 고정했다. 논문의 방법과 이후 확장된 공식 코드의 기능을 구분한다.

## 논문과 코드에서 확인한 내용

논문 §3, Algorithm 1–2는 실행 기록과 텍스트 피드백으로 지침을 바꾸고, 과제별 최고 성과를 낸 후보들을 다음 탐색에 활용한다. 평균 점수가 낮아도 특정 과제에 강한 후보가 남는다. Appendix C는 현재 지침·실제 출력·피드백을 함께 읽는 반성을, Appendix D의 Algorithm 3–4는 공통 조상에서 갈라진 구성요소 결합을 설명한다. 병합 효과는 모델에 따라 달라졌으므로 해안에서 이득을 전제하지 않는다.

공식 소스에서 다음 경로를 확인했다. 링크는 위 커밋의 `src/gepa/` 기준이다.

| 코드 | 실제 동작 | 해안 적용 판단 |
|---|---|---|
| `gepa_utils.py`, `strategies/candidate_selector.py` | 각 과제 최고 후보 집합을 만들고, 최고점 범위를 잃지 않는 중복 후보를 제거한 후 범위 수로 가중 추첨 | `evolve-select`에 독립 구현. 일반적인 점수 벡터의 Pareto 지배 검사와 다름 |
| `core/adapter.py` | `evaluate`와 `make_reflective_dataset`을 분리하고, 입력·출력·피드백을 제공 | 기존 실행 원문과 `evolve-reflect`를 계속 사용. 숫자만으로 지침을 고치지 않음 |
| `proposer/reflective_mutation/reflective_mutation.py`, `strategies/component_selector.py` | 부모에서 선택한 구성요소를 수정하고 나머지는 상속; 순환 선택 지원 | 한 차례에 한 구성요소를 고치는 스킬 절차. 자동 순환 상태 관리까지 구현한 것은 아님 |
| `strategies/acceptance.py`, `core/engine.py` | 기본 반성 후보는 같은 소집합에서 엄격 개선 검사 후 전체 선택 평가; 최신 코드는 사용자 선택 전략도 허용 | 기존 고정 `compare`를 유지. 공식 기본 조건만 설명하고 모든 사용자 전략의 보장으로 일반화하지 않음 |
| `proposer/merge.py`, `core/engine.py` | 공통 조상·겹치는 평가 과제 확인, 구성요소 결합, 부모와 비교 후 전체 평가 | `evolve-merge`는 더 보수적으로 같은 구성요소의 상충 수정을 거부. 계보 자동 탐색·검증은 미구현 |
| `core/state.py` | 후보 해시·train/val 구분을 포함한 캐시, 계보·실행 상태 저장 | 결과 파일 SHA256을 고정. 해안 반복 평가는 캐시로 대체하지 않음 |
| `utils/stop_condition.py` | 호출·제안·시간·정체 등 중단 조건 조합 | 기존 스킬의 기본 한 차례 비교와 Codex 호출 상한을 유지. 무한 자동 탐색기는 추가하지 않음 |

공식 최신 코드에는 objective/hybrid/cartesian frontier와 병렬 제안 등 논문 기본 구성보다 넓은 기능도 있다. 이번에는 **instance frontier에 해당하는 선택**을 가져왔다. 공식 패키지를 설치하거나 API 인증을 추가하지 않았고, 라이브러리 코드를 복제하지 않은 표준 라이브러리 구현이다.

## 사용법

한 pool에는 같은 시험·과목·급수만 넣는다. 먼저 개발 과제를 피드백용과 후보 선택용으로 나눈다. 같은 지문·출처에서 파생된 과제는 같은 묶음으로 배치한다. holdout은 이 도구에 넣지 않는다. 이미 읽어버린 과제를 나중에 이름만 바꿔 선택용으로 지정하면 독립 평가가 되지 않는다.

로컬 `experiments/.../pool.json` 예시:

```json
{
  "split": "development",
  "feedback_cases": ["feedback-case"],
  "selection_cases": ["selection-case-a", "selection-case-b"],
  "case_families": {
    "feedback-case": "source-family-1",
    "selection-case-a": "source-family-2",
    "selection-case-b": "source-family-3"
  },
  "candidates": [
    {"id": "baseline", "results": "baseline/results.json", "sha256": "실제 결과 파일의 SHA256 64자리"},
    {"id": "candidate-a", "results": "candidate-a/results.json", "sha256": "실제 결과 파일의 SHA256 64자리"}
  ]
}
```

```sh
scripts/haean-tool evolve-select experiments/example/pool.json \
  --seed 0 --out experiments/example/selection-01.json
```

두 분할의 모든 과제를 동일 조건으로 평가한 기존 cohort 형식을 사용한다. 과제당 독립 반복 3–5회, 평가 프로토콜·코드 해시·하네스 해시가 필요하다. 해시가 일치해도 기록의 과거 진실성이 증명되지는 않는다. `actual_model` 미확인은 그대로 표시한다. 예전 실험에 없던 필드를 소급해서 채워 넣지 말고 새 조건으로 평가한다.

도구는 입력 SHA 불일치, 중복·누락 반복, 서로 다른 제품군·조건, 부정확한 점수 합계를 거부한다. 실행 실패·치명 오류·타당성 미달이 있는 후보는 제외 사유와 함께 남긴다. 실패 행을 지워 평균을 올리는 방식은 허용하지 않는다. 선택은 선택용 과제의 반복 평균으로 수행하며, 원래 8차원 결과를 덮어쓰지 않는다.

결과에는 과제별 원 최고 후보, 중복 제거 후 후보, 추첨 가중치와 seed, 제외 사유, 선택된 부모의 **피드백용 run 경로만** 나온다. 도구는 그 원문을 읽지 않는다. 에이전트가 해당 원문 전체를 읽고 근거를 연결한 뒤 한 구성요소의 수정 후보를 만든다. 선택용 원문을 윤문·개선 프롬프트에 넣지 않는다. 가족 묶음 라벨의 정확성이나 데이터 오염 여부까지 자동 입증하는 것은 아니다.

구성요소 결합은 `{ "writer": "지침 전문", "style": "지침 전문" }` 형식의 세 JSON 스냅샷을 사용한다.

```sh
scripts/haean-tool evolve-merge experiments/example/ancestor.json \
  experiments/example/left.json experiments/example/right.json \
  --out experiments/example/merged-01.json
```

한쪽만 바꾼 구성요소는 가져오고, 양쪽의 동일한 수정은 한 번만 반영한다. 상충 수정과 부모 복제본은 거부한다. 실제 공통 조상 여부와 보관된 다른 후보와의 중복은 에이전트가 기록을 대조해야 한다. 출력의 `components`는 새 미평가 후보이며, 하네스에 자동 설치되지 않는다. 입력·출력 해시와 구성요소별 출처를 함께 보존한다.

## 평가와 위키

선택·결합은 탐색용 보조 도구다. 자동 모델 호출, 전체 GEPA optimizer, 후보 승격 기능은 아니다. 후보는 기존 평가기로 같은 과제·모델·수정 예산에 따라 비교하고, 타당성·8차원 퇴행·비용을 별도로 검토한다. 자동 선택된 부모가 현재 운영 지침보다 좋다는 뜻도 아니다. 과제군을 늘리거나 반복 예산을 바꾸면 새 실험으로 남긴다.

위키에는 근거 run·후보 해시와 함께 가설, 채택/보류/롤백 이유를 축적한다. 합성 코드 테스트를 문항 품질의 근거로 저장하지 않는다. `evolve-select` 결과의 선택용 사례별 점수·원문을 피드백 위키에 재유입하지 않는다. 실제 문항·실험·개인 위키는 로컬에 두고 Git에는 도구·지침·합성 테스트만 공유한다.
