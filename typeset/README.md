# 선택 HWPX 조판 엔진

구조화된 원고를 사용자가 지정한 로컬 HWPX 양식에 삽입한다. Python 3.11 이상과 표준 라이브러리만 사용한다. 기존 `layout-fill`의 Java HWP 경로는 그대로 유지된다.

이 패키지에는 양식, 기출, 원문 샘플, 폰트, 그림, 원격 접속 설정이 없다. 프로필은 특정 양식의 스타일 ID와 배치 규칙을 기술하는 코드이며 임의의 HWPX에 적용되는 범용 변환기는 아니다. 양식 파일은 `data/` 등 Git에서 제외된 로컬 경로에 두고 명시적으로 전달한다.

```sh
./haean setup-typeset
./haean typeset --profiles
./haean typeset 원고.json -o runs/example/questions.hwpx \
  --profile leet_reasoning --template data/templates/questions.hwpx \
  --solution-template data/templates/solutions.hwpx --strict
```

해설을 만들지 않을 때는 `--no-solution`을 사용한다. 출력 파일과 원본 양식은 덮어쓰지 않는다. 문제지와 해설지는 임시 디렉터리에서 함께 생성한 뒤 확정한다. strict 진단이 마지막 단계에서 실패해도 부분 HWPX를 확정하지 않는다.

`setup-typeset`은 기존 프로젝트 `.venv`에 이 패키지만 설치한다. 가상환경이 아직 없으면 먼저 `./haean setup`을 실행한다. 독립 패키지 명령인 `.venv/bin/haean-typeset`도 같은 옵션을 지원한다.

```python
from haean_typeset import api

diags = api.validate(item, profile="psat5_data", template_path=question_template)
measure = api.measure(item, profile="psat5_data", template_path=question_template)
result = api.typeset(
    exam, output_path, profile="psat5_data",
    template_path=question_template,
    solution_template_path=solution_template,
    strict=True,
)
```

`validate`, `wrap`, `measure`, `line_guide`, `load_profile`도 `template_path`를 받는다. PSAT·언어이해의 치수와 문단 모양은 지정 양식에서 읽으므로 사전 진단에도 경로가 필요하다. 프로필은 호출별 복제되어 다른 요청의 양식·치수 캐시를 바꾸지 않는다. `wrap`은 새 원고를 반환하며 입력을 수정하지 않는다.

원고는 `profile`, `시험명`, `문항` 목록을 가진 dict다. 단일 문항은 `id`, `발문`, `지문` 블록 목록, `선지` 5개, 선택적인 `보기`, `정답`, `해설`을 가진다. 정답·해설이 포함된 내부 원고를 블라인드 풀이 입력으로 사용하지 않는다. 기존 해안 모델의 제작용 `commentary`는 학생용 해설에 옮기지 않는다.

지원 프로필은 `leet_reasoning`, `leet_verbal`, `psat5_language`, `psat5_situation`, `psat5_data`다. LEET 추리논증 HWPX 프로필은 공통지문 세트를 지원하지 않으며 PSAT 7급 HWPX 프로필은 아직 없다. 기존 HWP 엔진에서 지원하는 기능의 범위를 이 목록으로 축소하지 않는다.

반환값에는 진단, 어림 줄 수·높이·쪽수, 입력·양식 해시와 출력 경로가 있다. `pages_are_estimated`는 true이고 한글 렌더·납품 검증 플래그는 false다. 실제 한글에서 열어 PDF로 저장한 뒤 모든 작성 페이지의 글자, 표·그림·수식, 머리말, 정답표와 쪽수를 별도로 검증해야 한다. XML 생성과 합성 테스트는 한글 렌더나 문항 전문가 승인을 뜻하지 않는다.

```sh
.venv/bin/pytest -q typeset/tests tests/test_typeset_integration.py
```

테스트 원고와 ZIP 구조는 코드에서 새로 만든 합성 자료다. 실제 양식을 사용하는 통합 시험 결과는 로컬 작업 폴더에만 기록한다. 설치 패키지의 자산 포함 여부는 wheel/sdist도 함께 확인한다.
