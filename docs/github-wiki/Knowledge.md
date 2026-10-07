# 데이터와 지식 위키

| 저장소 | 역할 |
|---|---|
| 원본 파일·ZIP·출처 감사 | 수정하지 않는 근거, 원본 해시와 추출 한계 |
| `data/corpus.sqlite` | 원문·기출·유형 통계·검토 이력의 검색 DB |
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
