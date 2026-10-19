# 한글 양식 출력

Python과 Java 코드가 원본 HWP 양식의 슬롯에 지문·보기·선지·정답·해설을 삽입합니다. 제목·과목명, 정답 상자 글자 크기, 첫 슬롯 나눔 방지, 지정 문항 새 쪽 시작, 전체 쪽수 표시를 조정합니다. 원본 양식은 보존합니다.

```bash
./haean setup-layout
./haean tools layout-fill RUN --template TEMPLATE.hwp --out OUTPUT.hwp --title "해안 모의고사"
```

`--kind solutions`는 해설지, `--page-start 23`은 해당 문제의 새 쪽 시작, `--total-pages N`은 실제 렌더로 확인한 전체 쪽수입니다. 뒤 두 값은 배치 확인 후 결정하며 다시 렌더해야 합니다. 내부 제작 commentary는 학생용 출력에서 제외합니다.

최종 PDF는 현재 한컴 앱 인쇄 기능으로 생성하고 시각 검토합니다. HWP 텍스트 재읽기만으로 배치 성공이나 99% 재현을 주장하지 않습니다. 폰트·한컴 버전·수식·표·도식에 따라 인쇄 확인이 필요합니다. 자동 변환만으로 납품 확정하지 않습니다.

상세 계약: 저장소 `docs/LAYOUT.md`.

HWPX 조판은 선택 코드 패키지로도 사용할 수 있습니다. `haean setup-typeset`으로 설치하고 `haean typeset --help`로 사용법을 확인합니다. 문제·해설 양식은 `--template`과 `--solution-template`에 로컬 경로로 지정합니다. 원고 JSON은 기존 candidate와 다른 형식이며, 호환 프로필을 확인해야 합니다. `--strict` 검사와 파일 생성 이후에도 실제 한글에서 전 페이지를 확인해야 합니다. 양식 파일 자체는 공개 배포하지 않습니다.
