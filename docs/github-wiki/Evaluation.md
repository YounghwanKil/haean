# 평가와 개선

`evals/protocol.md`와 평가기를 고정하고 baseline과 candidate를 비교합니다. 텍스트 피드백에서 실패 원인을 추출해 출제 지침·검색·윤문·작업 흐름의 개선 가설을 만듭니다. 모델 가중치를 훈련하는 방식이 아닙니다.

고정 과제·분할·요청 모델과 확인 가능한 실제 모델 ID·하네스 해시·문항과 검토 원문·수정 내역·사용량을 보존합니다. 평가기 변경으로 점수를 올리지 않습니다. 후보가 개선되지 않으면 채택하지 않습니다. 한 유형의 소수 사례로 PSAT·LEET 전체 전문가 수준을 입증했다고 하지 않습니다.

프로토콜 v3는 혼합 묶음의 문항별 원 유형·난도를 평가 입력에 전달합니다. `haean tools evaluate-run RUN --revision 0 --out 새경로`로 저장된 초안을 재평가할 수 있습니다. 원 결과·후속 피드백·승인은 바꾸지 않습니다. 기존 검토 연결이 확인되지 않은 옛 자료는 진단용 점수만 제공합니다. v2와 v3를 섞어 개선을 주장하지 않습니다. [입력 계약·재평가 사용법](https://github.com/YounghwanKil/haean/blob/main/docs/EVALUATION_INPUT.md)을 참고하세요.

7급 세 과목의 보존 초기·최종 원고를 [실제 6회 재평가](https://github.com/YounghwanKil/haean/blob/main/docs/EVALUATION_INPUT_SMOKE.md)해 개별 목표 전달을 확인했습니다. 같은 원고의 점수도 달라졌으며 생성 하네스 성능 향상이나 기존 수정 의견 해소로 해석하지 않습니다.

독립 모델 풀이, 편집 의견, 형식 검사, 실제 사람 승인, 실측 풀이 시간, 한글 렌더 검증은 서로 다른 증거입니다. 개발 피드백은 로컬 지식 위키에 축적할 수 있지만 봉인 평가·holdout 정답은 제외합니다.

수동 `check`는 독립 풀이 요청과 결과 양식을 만듭니다. 풀이가 끝나면 `haean tools editor-prepare RUN --blind RUN/blind-result.json`으로 편집 검토 입력을 고정합니다. CLI `blind`는 이 준비를 자동으로 수행합니다. 편집자는 준비 기록의 풀이 사본과 새 양식을 사용합니다. `review-result`는 문항·지침·요청과 그때 대조한 풀이의 연결을 검사합니다. 자세한 절차는 [검토 스킬](https://github.com/YounghwanKil/haean/blob/main/skills/haean-review/SKILL.md)에 있습니다.

같은 문항이라도 독립 풀이가 바뀌거나 편집 준비를 새로 하면 이전 편집 결과를 다시 제출할 수 없습니다. 새 풀이를 대조해 편집 결과를 갱신해야 합니다. 자동 단계형 생성은 매 수정마다 풀이·편집을 새로 실행합니다. 입력 연결은 검토 대상의 일치를 확인하며 외부 검토자의 실제 판단이나 신원을 증명하지는 않습니다.

단계형 생성은 실제 입력·지침·스키마와 중첩 규칙을 포함한 패키지 코드를 스냅샷으로 보존합니다. 각 수정본과 검토 기록을 별도로 묶으며, 기록의 해시 일치가 문항 품질이나 검토자 신원을 보증하지는 않습니다.

실제로 실행한 결과와 한계는 [첫 제품군별 파일럿](https://github.com/YounghwanKil/haean/blob/main/docs/PILOT.md)과 [LEET 검토의견 반영 전후 비교](https://github.com/YounghwanKil/haean/blob/main/docs/EDITORIAL_FEEDBACK_PILOT.md)에 공개합니다. 후자는 한 과제의 각 3회 실행에서 나온 모델 평가상 개선 신호이며, 전문가 승인이나 다른 과목·한글 출력 품질의 증거는 아닙니다. 원문 문항과 팀 검토 자료는 로컬에 보관합니다.

[단계형 출제 연결 검증](https://github.com/YounghwanKil/haean/blob/main/docs/STAGED_AUTHORING_SMOKE.md)은 두 공개 과제의 각 1회 실행입니다. LEET의 문장 모호성은 수정 후 재검토했고, 두 문항 모두 추론 가치의 부족을 기록했습니다. 기능 동작 확인이며 성능 비교·전문가 승인이 아닙니다.

## 단계형 지침 후보 비교

2026-10-19에는 LEET 추리논증·PSAT 5급 자료해석 두 공개 과제에서 baseline과 candidate를 각 3회 비교했습니다. 예정 12건을 모두 보존했고 고정 비교 결과는 `reject_regression`입니다. 후보는 기본 지침에 반영하지 않았습니다. [실행 조건·원문 감사의 한계·점수·사용량](https://github.com/YounghwanKil/haean/blob/main/docs/STAGED_BURDEN_COMPARISON.md)을 확인하세요. 양쪽 모델 적격은 각 5/6이며 전문가 승인이나 다른 과목의 성능 검증은 아닙니다.
