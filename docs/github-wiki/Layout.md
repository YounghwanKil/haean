# 한글 양식 출력

Python과 Java 코드가 원본 HWP 양식의 슬롯에 지문·보기·선지·정답·해설을 삽입합니다. 제목·과목명, 정답 상자 글자 크기, 첫 슬롯 나눔 방지, 지정 문항 새 쪽 시작, 전체 쪽수 표시를 조정합니다. 원본 양식은 보존합니다.

```bash
./haean setup-layout
./haean tools layout-fill RUN --template TEMPLATE.hwp --out OUTPUT.hwp --title "해안 모의고사"
```

`--kind solutions`는 해설지, `--page-start 23`은 해당 문제의 새 쪽 시작, `--total-pages N`은 실제 렌더로 확인한 전체 쪽수입니다. 뒤 두 값은 배치 확인 후 결정하며 다시 렌더해야 합니다. 내부 제작 commentary는 학생용 출력에서 제외합니다.

최종 PDF는 현재 한컴 앱 인쇄 기능으로 생성하고 시각 검토합니다. HWP 텍스트 재읽기만으로 배치 성공이나 99% 재현을 주장하지 않습니다. 폰트·한컴 버전·수식·표·도식에 따라 인쇄 확인이 필요합니다. 자동 변환만으로 납품 확정하지 않습니다.

상세 계약: 저장소 `docs/LAYOUT.md`.
