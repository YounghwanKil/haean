# 회차 형식·내용설계 연결

외부 로컬 규칙을 가진 팀을 위한 선택 기능입니다. LEET 추리논증과 PSAT 5급 세 과목의 40슬롯 설계를 기존 작성·독립 검토에 연결합니다. 기출 분석표·소재 대장·프로필은 로컬에 보관하며 공개 설치 파일에는 포함하지 않습니다.

```bash
haean tools compose design data/composition-profile.json --seed 7 --out runs/composition/design-01
haean tools compose check runs/composition/design-01/design.json
haean tools compose bind data/exam-plan.json runs/composition/design-01/design.json data/slot-mapping.json --out runs/composition/binding-01
haean tools exam-build data/exam-plan.json --composition-packet runs/composition/binding-01/packet.json --out runs/exam-01
```

`design`은 모델 호출 없이 형식과 내용설계 제안을 만듭니다. `exam-build`에서 실제 문항 작성과 독립 풀이·편집 검토가 진행됩니다. 설계에 표시된 기출 ID와 빈 원천 메모는 검증된 참고 전문이 아닙니다.

원래 배정표가 기준입니다. 문항 번호와 stable ID를 따로 유지하며, 외부 유형·난도·세트는 명시 대응합니다. 설계의 정답 번호에 맞추려고 논리를 바꾸지 않습니다. 작성·검토·조립에서 입력과 후보 버전을 확인하고 독립 풀이에는 제작 설계를 전달하지 않습니다. 변경·파손된 파일에 이전 검토 가능 상태를 재사용하지 않습니다.

현재 이 연결은 40문항과 하·중·상 계획 난도를 지원합니다. PSAT 7급·언어이해는 기존 제작 경로를 유지합니다. composition 회차는 `haean tools exam-resume 이전회차 --out 새회차`로 원 기록을 보존하며 이어갈 수 있습니다. 완료 묶음의 검토와 설계 연결을 확인해 재사용하고 미완료 묶음만 새 실행에서 처리합니다. 입력·코드가 달라진 설계, 누락된 검토 연결, 별도 `--replacement`는 거절합니다. [재개 사용법](https://github.com/YounghwanKil/haean/blob/main/docs/PRODUCTION.md#외부-회차-설계를-사용한-실행-재개)을 참고하세요. 프로필 형식과 슬롯 대응 예시는 [상세 문서](https://github.com/YounghwanKil/haean/blob/main/docs/COMPOSITION.md)를 확인하세요.

코드 테스트·설계 재현·ID 연결 확인은 문항 품질이나 전문가 승인, 실제 한글 렌더 확인과 별개입니다.


## 실제 선택 문항 실행 확인

네 과목의 40슬롯 계획에서 단독 문항 1개씩 작성·독립 검토·평가를 실행했습니다. 추리논증과 자료해석은 한 번씩 수정 후 재풀이했고, 네 건 모두 사람 검토 대기입니다. 오답 기능과 난도 설명의 잔여 문제는 보존했습니다. [실행 조건·결과·범위](https://github.com/YounghwanKil/haean/blob/main/docs/COMPOSITION_MODEL_SMOKE.md)를 확인하세요. 총 4문항의 연결 시험이며 160문항 완성이나 전문가·한글 렌더 검증은 아닙니다.
