# 전체 회차에 전달할 근거

이 문서는 LEET 추리논증·PSAT의 `exam-build`를 실행하기 전에 읽는다. 회차 계획에는 유형·난도뿐 아니라 실제 작성자가 읽을 자료도 필요하다. 자료가 로컬 DB나 위키에 있다는 사실과 해당 실행의 입력에 들어갔다는 사실을 구분한다.

## 현재 자동 전달 범위

| 자료·단계 | 전체 회차에서의 동작 |
|---|---|
| 기존 corpus | `prepare`가 관련 예시·통계, 원칙, 피드백을 검색한다. 검색된 범위는 각 묶음의 `context.json`에서 확인한다. |
| 배정표의 슬롯 필드 | `context.exam_assignment`와 `request.md`에 전달한다. `authoring_notes` 등에 적은 근거도 포함한다. |
| 선택 composition | 연결한 형식·내용설계와 대응표를 작성·편집 검토에 전달한다. 독립 풀이에는 전달하지 않는다. |
| 로컬 지식 위키 | `data/wiki`의 페이지를 자동 주입하지 않는다. `prepare`의 조건부 fallback은 기존 corpus의 `wiki`·`reference` 분류 레코드 검색이다. |
| 정제 트랙 색인 | `exam-ref-bind`가 명시적으로 고른 참고 전문을 새 계획에 연결한다. `exam-build` 자체가 색인을 검색하거나 자료 적합성을 승인하지는 않는다. 별도 prepared run에서는 기존 `track attach --index`를 쓴다. |
| 누적 생성 DB·공통 텍스트 피드백 | `novelty-memory/get`과 `feedback-notes`로 조회할 수 있다. 전체 회차 작성 입력에는 별도로 연결해야 한다. |
| 단계별 소재·설계·작성 | `track generate`의 별도 prepared run 경로다. 회차의 `exam_assignment`가 있는 run에 `track attach`를 덧붙일 수 없다. |
| 한국어 윤문·고정 평가·한글 출력 | `exam-build`의 자동 단계가 아니다. 각각의 실제 수행 여부와 결과를 따로 기록한다. |

이 표는 기능 경계이며 성능 평가 결과가 아니다. 단순 corpus 검색을 정제 기출 few-shot, 누적 구조 비교 또는 전체 위키 활용으로 보고하지 않는다.

## 계획을 봉인하기 전에

회차 담당자가 해당 시험·급수·과목의 필요한 근거를 고른다. 다음은 수집 경로다. 검색 결과를 모으는 데서 멈추지 않고 사용할 원문을 읽는다.

- `wiki search`로 관련 원칙을 찾고 페이지와 출처를 확인한다. [위키 스킬](../skills/haean-wiki/SKILL.md)의 원문·모델 종합·가설 구분을 유지한다.
- [정제 참고자료](REFERENCE_DATA.md)의 `track ref-search`로 정확한 급수·과목·유형 조건을 조회한다. 부족한 유형은 결손으로 남긴다. 통계 행, 정답 확인, 전문 전사, 모델 분류, 사람 검토 사례는 서로 다른 근거다.
- [누적 생성 이력](../skills/haean/references/tools.md#과거-문항의-원문-연결)의 `novelty-memory`에서 소재·추론 후보를 고르고 `novelty-get`으로 관련 문항과 수정 버전을 읽는다. 출처 연결이 미확정이면 그 상태를 보존한다.
- `feedback-notes --exam EXAM --subject SUBJECT`와 필요한 팀 공통 의견을 확인한다. 사람의 원래 말, 모델의 제안, 채택된 규칙을 섞지 않는다.

선택한 페이지·조회 결과·관련 원문은 새 회차의 로컬 근거 폴더에 사본으로 보관하고 원본 경로·ID·locator·SHA-256·읽은 범위·검증 상태를 기록한다. 사용하지 않은 자료도 자동으로 사용된 것처럼 나열하지 않는다. 평가 holdout·봉인 정답을 출제 입력으로 가져오지 않는다.

각 슬롯에 **그 문항에 필요한 근거 내용과 적용 이유**를 적는다. `authoring_notes`는 문자열 또는 문자열 배열로, 구조화한 근거는 객체를 지원하는 `composition_resolution`에 둔다. 이는 후속 평가 입력에서도 지원하는 형식이다. 경로만 적어 두면 작성자가 내용을 읽었다는 증거가 되지 않는다. few-shot이 필요한 경우에는 출처가 확인된 선택 문항의 실제 본문을 전달하고, 원칙만 전달한 경우에는 원칙 활용으로 기록한다. 관련 과거 문항은 모방할 정답 템플릿이 아니라 반복을 피할 비교 자료일 수 있다.

```json
{
  "composition_resolution": {
    "principle": "읽은 원문에서 이 슬롯에 적용할 판단과 이유",
    "evidence": [{
      "kind": "wiki_principle",
      "source_path": "로컬 원문 경로",
      "snapshot_path": "로컬 사본 경로",
      "source_sha256": "실제 계산값",
      "locator": "읽은 구간 또는 문항 ID",
      "content": "실제로 전달할 발췌 또는 종합",
      "verification": "model-synthesis"
    }],
    "gaps": ["이 유형의 검증된 참고 전문은 아직 없음"]
  }
}
```

위 `evidence`는 자유 메타데이터다. 실행기가 이 자유 형식의 해시나 의미 정확성을 자동 검증하지는 않는다. 회차 담당자가 원문·사본을 대조하고 검증 기록을 남긴다. ID만 적은 메모나 통계 행을 `source_ids`의 출처로 승격하지 않는다.

### 선택한 전문·사실 자료의 ID 연결

기본 `exam-build`와 `exam-resume`에서는 다음 두 명시 필드를 사용해 기존 corpus 밖의 자료도 연결할 수 있다. 각각 슬롯의 `composition_resolution` 안에 둔다.

| 필드 | 실제 전달 내용 | 원본 패킷의 목록 |
|---|---|---|
| `selected_reference_input` | `references[]`의 `reference_id`, `student` 전문, `source.path/sha256` | `references[]` |
| `topic_fact_input` | `sources[]`의 `id`, `facts` 요약, `url`, `snapshot_path/sha256` | `sources[]` |

두 필드 모두 `packet_path`와 `packet_sha256`을 포함한다. 출처 패킷과 선택 내용이 일치하고 원PDF 또는 사실 사본의 해시가 맞아야 해당 ID를 `source_ids`에서 사용할 수 있다. 빈 목록에는 새 ID가 등록되지 않는다. 같은 ID에 다른 내용이 붙으면 중단한다. 패킷과 원본은 로컬에 유지하며 과거 실행이 참조하는 파일을 교체하지 않는다.

작성 시작 전에 전체 회차의 명시 자료를 검사하며, 파이프라인과 수동 `check`도 같은 ID 계약을 사용한다. 생성 후에는 자료가 바뀌지 않았는지 다시 확인한다. 이는 **전달한 자료와 출처의 연결 검사**다. 사실 요약의 정확성, 전문의 유형 분류, 독창성이나 전문가 승인을 대신하지 않는다. 일반 위키 근거·통계·`authoring_notes`에 적은 ID는 자동 허용하지 않는다.

이 자료는 작성·편집 입력에만 포함한다. 독립 풀이에는 학생용 문항만 보낸다. 새 composition 연결은 검증된 명시 패킷 ID도 허용하지만, 설계 메모의 미확인 외부 ID를 허용하는 것은 아니다. 기존에 봉인한 composition 계약과 별도 `track` 계약은 해당 버전의 범위를 유지한다.

모든 근거를 묶음마다 복제하기보다 해당 슬롯에 필요한 내용만 전달한다. 계획·근거를 확정한 뒤 `compose bind`를 수행한다. 이미 실행한 계획이나 후보의 입력을 소급 교체하지 않는다. 실행 후에는 실제 묶음의 `context.json`, `request.md`와 호출 기록에 내용이 들어갔는지 확인한다. 독립 풀이 입력에는 이 제작 근거·과거 정답·검토를 전달하지 않는다.

### 선택한 참고문항을 새 계획에 붙이기

“이 회차에 참고 기출을 연결해줘”라고 요청하면 해안이 원문을 읽고 슬롯별 선택 파일을 준비한다. `exam-ref-bind`는 선택한 ID를 색인에서 직접 조회해 출처와 기존 검증 근거를 확인하고, 전문 사본과 새 계획을 만든다. 모델을 호출하거나 유형 이름을 임의로 대응시키지 않는다. 기존 계획·색인·원문은 수정하지 않는다.

```json
{
  "schema_version": 1,
  "usage": "development",
  "plan_sha256": "원 계획 파일 바이트의 SHA256",
  "slots": [{
    "slot_id": "원 계획의 실제 stable ID",
    "reference_ids": ["색인의 실제 참고문항 ID"],
    "application": "읽은 원문 중 이 슬롯의 선지 범위 설계에 참고할 점",
    "match_scope": "format_only",
    "gaps": ["같은 소재·핵심 판단의 직접 예시는 아직 없음"]
  }]
}
```

`application`과 `match_scope`는 선택자가 읽고 판단한 설명이다. `format_only` 같은 값은 선택 범위를 기록하는 표기이며 자동으로 인증한 분류가 아니다. 원래 유형·소재·난도는 바뀌지 않는다. 시험·과목·급수가 맞지 않는 자료는 묵시적으로 대체하지 않는다. 명시적인 빈 `reference_ids`에는 부족한 자료와 그 이유를 적을 수 있다. 선택하지 않은 슬롯도 보고서에 남는다. 이미 명시 자료가 있는 슬롯에 새 선택을 겹쳐 쓰면 충돌을 알려 주며, 이전 선택을 자동 교체하지 않는다.

```bash
haean tools exam-ref-bind runs/plan.json \
  --index data/references.sqlite \
  --selection runs/reference-selection.json \
  --out runs/plan-with-references
# 새 계획을 이후 회차 설계 연결·출제에 사용한다.
haean tools exam-build runs/plan-with-references/plan.json \
  --out runs/production
```

출력에는 `source-plan.json`, `selection.json`, `references.json`, `plan.json`, 전체 슬롯의 `coverage.json`과 근거 사본이 있다. 선택 수와 고유 참고문항 수를 구별한다. 자료 연결 완료는 판단 과제의 적합성·정답 타당성·실제 작성자의 활용 확인이 아니며 `generation_executed=false`, `quality_verified=false`로 표시한다. 부족한 슬롯은 자료를 보강하거나 결손을 인지한 상태에서 작성 범위를 결정한다.

기존 선택은 원래 패킷·사본 경로를 계속 참조한다. 이미 연결한 참고를 다른 슬롯에도 쓰는 경우에는 학생용 내용과 출처 근거가 같은지 확인한 뒤 기존 출처 객체를 재사용한다. 새 결과 폴더만으로 모든 이전 자료가 이관되는 것은 아니므로 기존 근거 폴더도 함께 유지한다.

지원 대상은 문항 역할(`role=item`)의 완전한 학생용 전문이다. 기존 PSAT 전사와 명시적인 학생용 JSON을 연결하며, 평문에서 정답·해설을 임의로 분리하거나 native 블록 문항을 자동 평탄화하지 않는다. 검토 사례(`role=case`)는 [별도 사례 연결](REVIEW_CASES.md) 경로를 사용한다. 언어이해의 별도 `reading` 계획에는 이 명령을 적용하지 않는다.

확인된 참고 정답을 전달할 때도 `source.official_answer`의 검증 상태·근거를 함께 보존하며 해설을 새로 지어 넣지 않는다. 전사 당시의 미확인 값과 후속 공식 답 확인을 합쳐 과거 기록을 수정하지 않는다. 명령 실행 시 기존 전사·정답·분류 검증 체인을 확인하고 근거 사본을 남긴다. 후속 출제의 명시 패킷 검사는 패킷·학생용 내용·출처 객체와 원본 파일의 일치를 검사하며, 외부 사이트나 모든 하위 근거를 매번 다시 검증하는 기능으로 보고하지 않는다.

composition을 함께 쓸 때는 **참고문항 연결 → 새 계획으로 `compose bind` → `exam-build --composition-packet`** 순서다. 새 계약에서 검증한 명시 출처 ID는 작성·편집·재개에서 사용 가능하며, 이전 계약의 봉인 자료를 새 버전으로 소급 변경하지 않는다. 독립 풀이에는 참고 정답·전문·제작 의견이 들어가지 않는다.

## 선택 기능: 검증 파일 목록의 입력 축약

`generate`, `exam-build`, `exam-resume`에 `--compact-reference-audit`를 지정하면 작성·수정·편집 모델에 전달할 선택 참고자료의 검증 파일 목록을 별도 보관 기록으로 대체한다. 기본 동작은 전체 입력을 그대로 전달하는 것이다. 이 옵션은 개발용 입력 기능이며 출제 품질이 개선됐다고 검증한 기본 설정이 아니다.

```bash
haean tools exam-build runs/plan-with-references/plan.json \
  --out runs/production-compact --compact-reference-audit
```

축약 대상은 `selected_reference_input.references[].source` 안의 `evidence_files`와 `official_answer.evidence.files` 두 목록뿐이다. 알려진 파일 경로·해시 형식만 처리하며, 파일별 이름과 locator·usage는 보존한다. 새로운 키나 예상하지 못한 구조가 섞인 목록은 그대로 전달한다. 학생용 문면, 출처 ID, 공식 답과 그 확인 상태, 분류 근거·불확실성, 전사 주의, `application`·`match_scope`·`gaps`와 그 밖의 필드는 삭제하지 않는다.

원본 `context.json`과 `request.md`, 출처 검증·composition 연결은 전체 자료를 기준으로 유지한다. 별도 보관한 원 context의 경로·바이트 해시와 목록의 JSON Pointer·해시를 축약 기록에 남기고, 실제 모델 입력 사본도 저장한다. 작성·편집 후의 출처 재검증도 원자료에 적용한다. 독립 풀이에는 기존대로 학생용 문항만 전달하며 고정 평가 입력은 바꾸지 않는다.

각 묶음의 `authoring-inputs/<실행 식별자>/`에 `original-context.json`, `projection-manifest.json`, `writer-context.json`, `editor-exam-assignment.json`, `delivery-manifest.json`을 남긴다. 마지막 파일은 각 사본의 해시와 적용 범위를 기록한다. 전체 요청·현행 원고·검토 의견을 포함한 실제 호출 payload는 기존 `codex-traces`에서 확인한다. `request.md`는 원본 자료를 보는 문서이며 축약 후 실제 전송본과 구분한다.

재개 실행에서는 이 옵션을 다시 명시한다. 이전 run의 입력이나 기록은 소급 변경하지 않는다. 별도 `track generate`와 언어이해 `reading` 경로에는 이 옵션을 적용하지 않는다. 축약 전후 JSON 문자 수는 입력 크기 관찰이며 실제 토큰 절감이나 품질 향상의 증거가 아니다. 성능을 비교하려면 동일 과제·모델·수정 예산에서 실제 사용량과 원문 평가를 함께 확인한다.

## 실행 범위와 후속 단계

`full_exam.bundles(plan)`의 실제 묶음 수를 B로 계산한다. 독립 문항은 영역·유형별 최대 4문항, 공통지문은 세트를 유지한다. `workers=3`은 동시 작업 수이며 전체 모델 호출 수가 아니다. 새 생성은 묶음마다 작성·풀이·편집 3회, 수정 한 회마다 추가 3회다. 수정 예산 R이면 전체 상한은 `B × (3 + 3R)`이며 별도 고정 평가는 묶음당 추가 1회다. 실패·재개 호출도 함께 집계한다. 이 상한은 새 `exam-build`에 대한 것이며 재개 경로의 예산은 [재개 계약](PRODUCTION.md)을 따른다.

`exam-build`는 humanizer를 적용하지 않았다는 provenance를 남긴다. 윤문이 필요하면 [해안 윤문](../skills/haean-style/SKILL.md)을 별도로 수행하고 바뀐 문항은 새 독립 풀이·편집 검토를 받는다. composition 실행의 후보를 일반 `check`로 덮어쓰면 기존 revision·설계 검토 연결을 잃을 수 있다. 현재 CLI에는 이 후보를 윤문 후 같은 composition 검토로 자동 복귀시키는 기능이 없다. 변경 없는 문체 진단은 진단으로 남기고, 실제 윤문 채택에는 새 실행의 입력·설계·검토 연결을 마련해야 한다.

고정 평가는 문항별 `items/NN` 편집 뷰가 아니라 원 묶음 run에 `evaluate-run`을 적용한다. 선택 문항 평가를 전체 회차 평가로 확대하지 않는다. 최종 보고에는 새로 작성한 문항 수, 남은 A/B/C 의견, 실제 모델 호출량, 사용한 근거와 결손, 윤문 적용 여부, 반복 검토 범위, 사람 검토와 출력 확인 상태를 구분한다.
