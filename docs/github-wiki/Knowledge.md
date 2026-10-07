# 데이터와 지식 위키

| 저장소 | 역할 |
|---|---|
| 원본 파일·ZIP·출처 감사 | 수정하지 않는 근거, 원본 해시와 추출 한계 |
| `data/corpus.sqlite` | 원문·기출·유형 통계·검토 이력의 검색 DB |
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
