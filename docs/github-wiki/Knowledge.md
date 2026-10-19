# 데이터와 지식 위키

| 저장소 | 역할 |
|---|---|
| 원본 파일·ZIP·출처 감사 | 수정하지 않는 근거, 원본 해시와 추출 한계 |
| `data/corpus.sqlite` | 원문·기출·유형 통계·검토 이력의 검색 DB |
| 과목별 정제 참고 색인 | 명시적으로 고른 개발용 사례, 급수·분류·원문 증거를 유지하는 별도 검색 자료 |
| `data/generated.sqlite` | 이전에 생성한 문항 전문·수정 버전·출처를 보존하는 비교용 DB |
| `data/wiki` | 읽은 근거를 종합한 Markdown 지식, 출처 JSON, 색인·변경 이력 |
| `runs`, `experiments` | 실제 입력·출력·검토·수정·모델·평가 이력 |

`$haean-wiki` 또는 `$haean`에 자료를 읽고 기존 지식과 연결해 달라고 요청합니다. 자료를 넣었다는 사실과 전문 읽기·정답 검증·이미지 검증은 다릅니다. DB 전체가 검증된 few-shot은 아닙니다.

```bash
./haean tools wiki init
./haean tools wiki search --query "유형 통계"
./haean tools wiki lint
```

LLM이 출처를 읽어 작성한 JSON 패킷을 `wiki put --packet PATH`로 등록합니다. 이전 페이지와 출처 해시를 보존하고 색인·로그를 갱신합니다. 모델 종합·가설·충돌 상태를 구분합니다. lint는 해시 변경과 링크 문제를 찾으며 의미 모순은 LLM이 별도 검토합니다. Obsidian으로 `data/wiki`를 열 수 있습니다.

개발 자료만 축적합니다. holdout·블라인드 정답을 출제 지식에 넣지 않습니다. 로컬 위키와 비공개 자료는 Git에서 제외됩니다. GitHub Wiki에는 사용 설명서만 둡니다. 자동 동기화나 무인 백업 서비스는 아닙니다.

## GitHub Wiki와 LLM Wiki의 차이

GitHub Wiki는 문서를 게시하는 공간입니다. 카파시의 LLM Wiki 패턴은 모델이 자료를 읽고 주제별 지식을 종합하며 출처·모순·변경 이력을 지속적으로 관리하는 방식입니다. 해안은 이 패턴을 로컬 `data/wiki`와 `haean-wiki` 스킬로 구현합니다. GitHub Wiki 자체가 자료를 읽거나 지식을 자동 갱신하지는 않습니다. 새 자료를 제공하고 해안에 반영을 요청하면 Codex가 읽기·종합을 수행하고 도구가 기록을 보존합니다.

## 이전 세션에서 결정과 남은 일 찾기

“이 폴더에서 작업한 이전 세션들을 검토하고, 이미 끝난 일과 남은 요청을 정리해줘”라고 요청할 수 있습니다. 해안은 지정 프로젝트의 보존 기록만 확인하고, 기존 회고 이후의 변경분과 현재 산출물을 대조합니다. 자동 재개·하위 에이전트 보고를 새 사용자 요청이나 새 실험으로 중복 계산하지 않습니다.

결정·철회·미완료 요청에는 원문 위치와 현재 근거를 연결합니다. 재사용할 원칙은 로컬 지식 위키에, 다음 작업과 완료 조건은 로컬 실행 목록에 남깁니다. 세션을 읽었다는 사실은 당시 모델의 완료 보고를 검증했다는 뜻이 아니며 실제 읽은 메시지·도구 로그·이미지의 범위를 구분합니다. 기록과 팀 내부 계획은 GitHub에 자동 게시하지 않습니다. 일반 출제 때마다 모든 세션을 다시 읽는 기능도 아닙니다.

## 오래 작업할 때 같은 문제를 반복하지 않으려면

해안 대화창에서 “이전 생성 이력을 확인하고, 핵심 추론과 오답 구조가 겹치지 않게 만들어줘”라고 요청합니다. 출제자는 이력을 읽고, 편집 검토자는 실제 원문 쌍을 대조합니다. 다음 명령은 일반 터미널에서 직접 조회할 때 사용합니다.

```bash
# 기존 생성물 등록: 출처 자료 DB와 별도로 보관
haean tools novelty-index runs/이전회차폴더
# 인지 과제·조건의 색인 확인
haean tools novelty-memory --exam leet --subject 추리논증 --out runs/memory-index.json
# 선택한 문항의 전문과 수정 전후 버전 확인
haean tools novelty-get --exam leet --subject 추리논증 --item 문항ID --all-versions --out runs/selected-history.json
# 새 생성물과 누적 이력 비교
haean tools novelty-check runs/새회차폴더 --out runs/novelty-review.json
```

색인 결과의 `next_offset`이 있으면 `--offset`에 그 값을 넣어 다음 페이지도 확인합니다. PSAT은 `--exam psat5` 또는 `psat7`과 실제 과목명을 지정합니다. 등록한 문항이 없으면 빈 결과가 나오며, 설치만으로 팀의 과거 문항이 생기지는 않습니다.

색인은 전문 독해를 대신하지 않습니다. 가까운 문항을 고른 뒤 원문과 정정 이력을 읽으며, 내부 인지 과제·난도 설명에도 오류가 있을 수 있습니다. `--all-versions`로 받은 수정 전 버전은 실패 이력일 수 있으므로 최신 판단과 구분합니다. 같은 ID의 수정본을 새로운 문항 수로 세지 않습니다.

유사도 검색은 상위 후보와 경고 기준을 넘긴 후보를 제시합니다. 문자 유사도가 낮아도 전제·결정적 추론·오답 역할이 같을 수 있으므로 편집자의 구조 비교가 필요합니다. 동일 유형이라는 사실만으로 자기 표절로 판정하지 않으며, 이 기능만으로 100문항 이후의 독창성이나 전문가 품질을 보장하지 않습니다. 장기 생성 실험에서 입력 방식이 달라지면 구간을 나누어 보고합니다.


## 기존 PSAT 전사 연결

`track ref-export`는 기존 corpus에서 명시한 ID의 PSAT 전사만 읽기 전용으로 추출합니다. 원문 PDF, 전사 packet, 선택 행과 선택 목록을 보존하고 색인 생성·검색 때 실제 내용과 해시를 대조합니다. 원문 DB·로컬 위키를 대체하지 않습니다.

```bash
haean tools track ref-export --corpus data/corpus.sqlite --selection data/reference-selection.json --out data/reference-export-01
haean tools track ref-build data/reference-export-01/refs.jsonl --out data/track-references-01.sqlite
haean tools track ref-search data/reference-query.json --index data/track-references-01.sqlite
```

선택 JSON 구조와 상세 절차는 [정제 참고자료 연결](Reference-Data)을 봅니다. 정답 미검증·잠정 유형을 유지하며, 영역·응답 형식 등 자료에 없는 조건으로 검색하면 결과가 없을 수 있습니다. 검색 조건을 자동 완화하지 않으므로 색인 수와 실제 출제에 사용된 참고 수를 구분합니다.

## 원문 근거로 참고자료 분류 보강

공식 정답을 연결한 PSAT 전사의 빈 영역·형식 또는 임시 유형은 원문을 읽고 `track ref-curate`로 별도 보강할 수 있습니다. 원문·공식 정답은 유지하고, 각 분류에 실제 문항 인용과 판단 이유를 붙입니다. 불확실한 분류는 유지하며 검색 조건을 자동으로 풀지 않습니다.

이 기능은 분류를 자동 추론하거나 전문가 승인하는 명령이 아닙니다. 새 색인의 실제 검색 결과와 출제 입력 연결을 확인해야 합니다. 입력 형식·명령·검증 범위는 [참고자료 연결 안내](https://github.com/YounghwanKil/haean/blob/main/docs/REFERENCE_DATA.md#원문-근거로-분류를-보강하기)를 따르세요.
