# 원문 연결 검증 후보와 사용법

`verify-source-profiles`는 선언한 문항 ID와 locator가 실제로 가리키는 원문 ID를 대조한다. 파일 해시가 맞더라도 다른 문항에 연결되면 실패한다. `id`의 숫자 접미사와 현재 시험 `number`가 같다고 가정하지 않는다. 기존 생성·독창성 파이프라인에 자동 연결하지 않은 별도 CLI 후보다.

```sh
scripts/haean-tool verify-source-profiles profiles.json --out new-report.json
```

`--out` 없이 JSON 보고서만 stdout으로 받을 수 있다. 성공은 종료 코드 0, 검증 실패나 보고서 저장 거부는 1이다. 보고서는 신규 파일만 만든다. 입력·source와 같은 경로, 기존 파일, symlink, hardlink는 덮어쓰지 않는다. 원문·입력의 내용이나 locator를 자동 수정하지 않는다.

입력은 profile 객체의 JSON 배열이다. 필수 필드는 문자열 `id`, `source`, `locator`, 64자리 소문자 SHA-256 `source_file_sha256`, `payload_sha256`이다. source는 JSON 파일이며 상대경로는 **실행 프로세스의 현재 작업 디렉터리(CWD)** 기준이다. 기존 로컬 보조 검증기와 같다. `scripts/haean-tool`은 저장소 루트로 이동하므로 해당 명령으로 실행할 때는 저장소 루트 기준이다. 입력 파일이 있는 폴더 기준이 아니다. 보고서의 `source_path_base`로 실제 기준을 확인할 수 있다.

locator는 JSON Pointer(`/items/0`, 이스케이프 `~0`·`~1`, 빈 문자열로 루트 지정) 또는 기존 `$.items[0]` 형식이다. 표현식을 실행하지 않는다. 배열 인덱스의 음수·앞자리 0·문자열 표현 등은 거부한다. 중복 profile ID, 중복 JSON 객체 키, 누락 필드, 잘못된 타입, null, 없는 파일, 잘못된 locator, 빈 배열은 오류로 보고한다.

`source_file_sha256`는 파일 bytes SHA다. `payload_sha256`는 locator가 가리키는 **전체 raw 문항 객체**를 JSON 직렬화한 SHA다. ID·현재 번호·모든 필드를 포함하며 catalog 정규화, Unicode 정규화, 번호 제거를 하지 않는다. 선택 필드 `payload_encoding`의 지원값은 다음 두 가지다.

- `raw_sorted_compact`: Python `json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)`를 UTF-8로 인코딩한다.
- `raw_sorted_default`: 위와 같되 `separators`를 지정하지 않는다. 기본 공백이 해시에 포함된다.

명시한 encoding만 비교한다. 명세가 없는 기존 profile은 두 방식을 대조하고 `legacy_auto` 및 일치한 encoding을 보고한다. 추론한 방식을 명시된 계약처럼 표현하지 않는다. 다른 직렬화·정규화 digest와의 호환을 주장하지 않는다. 잘못된 명세, 명세와 불일치하는 digest는 실패한다.

선택 필드 `student_original`은 원문의 최상위 필드를 복사한 객체다. 제공한 각 필드를 원문과 비교한다. `original_judgments`는 비어 있지 않은 배열로 원문의 `judgments`와, `original_explanation`은 비어 있지 않은 문자열로 원문의 `explanation`과 비교한다. 배열 순서와 값의 타입까지 같아야 하며 `true`, `1`, `1.0`, `"1"`을 같은 값으로 취급하지 않는다. 이 검사는 의미·판정·해설 내용의 타당성을 평가하지 않는다.

삽입본은 선택 사항이다. 생략한 필드는 `missing_embedded_evidence`, 실제 비교한 필드는 `embedded_fields_checked`로 보고한다. `student_original: {}`도 빈 삽입본으로 표시한다. 전체 학생 문면을 정의하는 필수 필드 계약이 없으므로 `full_student_text_verified`는 항상 false다. 이는 주어진 필드의 일치 검사와 전문 독해·전체 문면 검증이 다름을 뜻한다. `valid: true`는 보고서 scope의 기계 검사만 통과했음을 뜻하며 독창성, 정답, 사람 검토, 납품 승인을 증명하지 않는다.

## 후보 근거·예상 퇴행

로컬 제안서 `_workspace/source-identity-guard-proposal.md`와 실험 보조 `runs/serial-novelty-20261008/verify_source_profiles.py`를 읽고 설계했다. 지정된 사례는 batch22·23의 16개 profile에서 파일 SHA가 일치하지만 선언 ID와 locator가 다른 문항을 가리킨 오류다. 이 후보의 공개 코드·테스트에는 실제 문항 원문을 넣지 않았다. 합성 사례에서 `synthetic-091`·현재 번호 4는 통과하고 다른 ID 원문의 올바른 payload hash를 붙이면 `source_item_id_mismatch`로 실패한다. 소수 사례에서 전 출제 품질의 개선을 추론하지 않는다.

검색 후 근거를 등록하는 단계에 이 검사를 둘 수 있으나 검색 순위, 역할 분리, 윤문 순서는 이번에 바꾸지 않았다. 독립 의미 검토와 윤문 후 의미·정답 재검증은 여전히 별도다. 확인된 오류가 원문 연결 단계이므로 프롬프트 확대나 윤문 순서 변경보다 ID 대조를 좁게 추가한 후보다.

엄격한 타입 검사로 기존의 느슨한 입력이 실패할 수 있다. 기본/compact 외의 적법한 JSON 직렬화 digest는 지원하지 않는다. CWD가 달라지면 상대경로를 해결하지 못한다. 원문의 필드 복사만 비교하므로 서로 일치하는 잘못된 해설은 잡지 못한다. 실행 중 원문 변경을 잠그거나 외부 신뢰 저장소로 무결성을 인증하지 않는다. 캐시는 실행 중 처음 읽은 bytes를 기준으로 한다.

## 후보 실행 기록

별도 worktree `_workspace/source-identity-candidate`에서 다음 네 파일을 변경했다. 구현 담당자는 후보만 작성했으며, 총괄 검토 후 별도 브랜치로 공개한다. main 병합·기존 실험 결과 변경은 하지 않았다.

- `src/haean/source_identity.py`: 읽기 전용 검증 및 신규 보고서 저장.
- `src/haean/cli.py`: 명령 등록·dispatch·실패 종료 코드 8줄.
- `tests/test_source_identity.py`: 합성 회귀 61개.
- `docs/SOURCE_IDENTITY_CANDIDATE.md`: 사용법 및 후보 보고서.

검증 명령은 candidate 루트에서 `PYTHONPATH="$PWD/src" /Users/auspic/haean/.venv/bin/pytest -q -rs`다. **188 passed, 1 skipped (1.73초)**. skip은 `tests/test_hwp_inline.py:16`의 native Java formatting 환경 부재이며 submodule 결손 때문이 아니다. 이 작업에서 한글 양식 렌더를 검증하지 않았다.

직접 CLI 등록 smoke는 candidate `PYTHONPATH`와 임시 합성 파일로 `/Users/auspic/haean/scripts/haean-tool verify-source-profiles ... --out ...`을 실행했다. import 경로가 candidate `src/haean/cli.py`임을 확인했고 JSON stdout/보고서와 정상 종료를 확인했다. worktree 자체에는 `.venv`가 없어 main의 Python 실행 환경만 빌렸다. CLI 합성 테스트는 잘못된 ID와 출력 충돌의 실패 종료도 검증했다. `git diff --check` 통과.

요청에 따라 candidate에서 고정 submodule을 초기화했고 `vendor/im-not-ai`는 `2f3d943d08056b612a92e12bfb72ea94dd2acd18`이다. 로컬 10개 스킬과 humanize-korean의 frontmatter 및 `.agents/skills` discovery 11개를 확인했다. 스킬·평가기·evals·holdout·원문 결과는 수정하지 않았다.

모델 생성/평가 호출 0회. Astra 출제품질 점수 상승, 전문가 확인, 한국어 윤문 실행, HWP 납품 검증은 이 후보에서 입증하지 않았다. 실제 기존 profile에 대한 후속 읽기 전용 비교는 총괄이 별도 수행한다.

## 총괄의 기존 기록 재현 확인

후보 모듈의 실제 import 경로를 확인한 별도 CLI 실행에서 과거 두 묶음의 ID 연결 오류 16건을 모두 실패로 보고했다. 정상 세 묶음의 388개 기록은 통과했다. 실행 전후 입력·참조 원문의 파일 해시는 모두 일치했다. 로컬 근거는 `_workspace/source-identity-validation/summary.json`에 보존하며 원문은 공개 저장소에 포함하지 않는다. 이 결과는 알려진 연결 오류의 재현 검출이며, 미지의 오류 검출률이나 출제 품질 향상을 측정한 결과가 아니다. 현재 main과 진행 중인 출제 실험에는 적용하지 않았다.
