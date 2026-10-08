# 과거 문항의 원문 경로 검증

이 후보는 `memory_get`이 반환하는 과거 문항의 원문 경로를 검증한다. 저장된
payload는 보존되어도 `source`의 candidate.json 내용은 수정으로 바뀔 수 있다.
한 사례에서 확인한 경로 재사용 문제에 한정하며 출제 품질·독창성 점수 향상을
주장하지 않는다. 2026-10-09 배포본에 통합했다. 진행 중 관찰실험은 별도 고정 checkout을 계속 사용하므로 이 변경을 적용하지 않는다.

## 반환 계약

기존 item, sha256, source는 바꾸지 않는다. DB schema/행도 쓰지 않는다.
`memory_index`에는 source_resolution.origin_path와 status=not_checked를 붙인다.
`memory_get`에는 다음 source_resolution 메타데이터를 덧붙인다.

- origin_path는 기록 당시 경로이며 불변 원문이라는 보증이 아니다.
- payload_canonical_sha256는 UTF-8, sort_keys=True, separators=(',', ':'),
  ensure_ascii=False, allow_nan=False JSON의 SHA256이다. 기존 sha256의 공백
  포함 직렬화와 다를 수 있으며 기존 해시를 대체하지 않는다.
- origin_check는 현재 파일의 match/mismatch/missing/error/unsupported와
  가능한 raw_sha256를 보고한다.
- matches의 각 항목은 실제 읽은 파일 path, raw_sha256, $.items[n] locator다.
  실제 id와 전체 canonical JSON을 대조한다. 스키마 기본값을 채우거나 타입을
  변환하지 않으며 True, 1, 1.0, '1'은 서로 다르다.
- status=verified_origin이면 현재 경로 안에서 정확한 원문이 하나 확인되었다.
  origin 안에 정확한 중복 항목이 있으면 ambiguous다.
- origin이 일치하지 않으면 그 부모의 직계 revision-*/candidate.json만 조사한다.
  resolved_archive는 조사 완료 후 정확한 일치 하나, ambiguous는 복수 일치,
  unresolved는 일치 없음, incomplete는 조사 오류/누락으로 완결되지 않음이다.
  일치 목록을 모두 공개하고 대표 경로를 임의로 선택하지 않는다.
- archive_checks에 읽기·파싱·symlink 오류를 공개한다. 상대 source는 기준 디렉터리가
  기록되지 않아 unsupported이며 현재 작업 폴더를 임의로 사용하지 않는다.
  기록된 경로가 candidate.json이 아니면 보관 폴더를 조사하지 않는다.

동일 내용의 JSON 공백·키 순서 차이는 허용하지만 raw file SHA는 별도로 남긴다.
중복 JSON 키·비유한 숫자는 오류로 처리한다. 발견한 보관 파일/폴더 symlink는
따라가지 않는다. 원래 지정된 origin 경로 자체는 읽을 수 있다. 파일의 형제 폴더만
열거하고 하위 재귀 검색, 다른 catalog, 평가 자료 검색은 하지 않는다.

## 검증과 before/after

합성 테스트 `tests/test_source_resolution.py`는 두 버전 저장 후 현재 파일 교체,
원문/해시/경로 및 DB 바이트 보존, 복수 원문, 포맷 차이, 타입 차이, id 불일치,
누락·파싱·읽기 오류, symlink 및 검색 경계를 다룬다. 기존 전체 필드 동일성
테스트는 추가 메타데이터를 제외한 필드가 동일함을 계속 확인한다.

```
PYTHONPATH=src /Users/auspic/haean/.venv/bin/pytest -q
```

후보 작업 폴더에서 143 passed, 1 skipped (1.63s). frontmatter 10개와
Codex .agents/skills 해안 10개 discovery를 확인했다. 격리 worktree의
humanize-korean submodule은 미초기화여서 해당 discovery는 확인되지 않았다.
네트워크 설치는 하지 않았다. 생성·윤문 지침, 역할 분리, 윤문 순서는 이번
경로 검증 문제의 발생 원인이 아니므로 바꾸지 않았다.

실제 실행 이력은 지정 DB를 읽기 전용으로 조회하여 재현했다. 기존 retrieval은
과거·현재 버전에 같은 source를 반환했다. 후보는 과거 버전에서 mismatch를
보고하고 정확한 보관 원문을 찾았으며 현재 버전은 verified_origin이었다.
원문 포함 before/after, 원래 proposal, validation은 로컬 전용
`_workspace/source-resolution-evidence/`에 보존한다. 기존 실행 파일·DB·결과는
수정하지 않는다. Git에는 합성 테스트와 구현·설명만 포함한다.

## 예상 퇴행과 한계

검색 응답에 메타데이터가 추가되므로 전체 객체의 정확한 키 집합을 기대하는
외부 클라이언트는 조정이 필요하다. 기존 필드 의미와 값은 그대로다.
과거 원문 조회마다 파일을 읽으므로 대량 all_versions 조회 비용이 늘어난다.
같은 파일을 한 요청 안에서도 다시 읽을 수 있고 snapshot 격리는 제공하지 않는다.
결과는 읽은 순간의 raw SHA/locator이며 이후 파일 변경을 막지 않는다.

raw JSON과 저장된 모델 payload의 기본값/정규화 차이도 불일치로 보고한다.
이는 추정 일치를 피하기 위한 보수적 선택이다. 과거 상대 경로, 다른 이름의
아카이브, sibling 범위 밖 원문은 해결하지 못한다. 한 정확한 원문과 읽기 오류가
동시에 있으면 incomplete로 남긴다. 여러 파일의 정확한 일치는 ambiguous이며
내용이 동일하다는 이유로 하나를 채택하지 않는다. verified_origin이면 archive는
조사하지 않으므로 다른 보관본의 존재나 전역 유일성을 보증하지 않는다.

Astra 생성·모델 평가·전문가 검토·HWP 렌더는 실행하지 않았다. 확인된 성과는
원문 경로 불일치의 공개와 제한된 범위 내 정확한 원문 식별이다.

## 배포본 통합 검증 · 2026-10-09

원문 ID 검증 CLI와 함께 통합한 뒤 전체 테스트 **216개 통과, 건너뜀 0개**를 확인했다. 해안 스킬 10개와 고정 humanize-korean의 frontmatter·프로젝트 discovery를 확인했다. 앞서 기재한 후보 단계의 수치와 결손은 당시 기록으로 보존한다. 실제 152개 프로필의 ID·파일·payload 연결 검증도 통과했다. 이는 원문 연결 검증이며 전문 독해·출제 품질·한글 화면 검증을 대신하지 않는다. 평가기와 고정 평가 자료는 변경하지 않았다.
