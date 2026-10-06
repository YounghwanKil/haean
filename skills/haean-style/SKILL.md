---
name: haean-style
description: 해안 시험 문항의 번역투·문장 품질을 im-not-ai humanize-korean으로 다듬고, 논리 조건과 정답을 재검증한다.
---

# 시험 문항 윤문

`vendor/im-not-ai/codex/skills/humanize-korean/SKILL.md`를 읽고 해당 스킬의 진단·윤문·게이트 절차를 실제로 수행한다. 버전은 저장소의 submodule 커밋으로 고정한다. 설치됐다는 사실만으로 적용됐다고 표시하지 않는다.

1. `scripts/haean-tool style-prepare RUN --item ID --field passage`로 필드별 원문과 결합 정보를 만든다. `explanation`, `commentary`도 필요할 때 각각 처리한다. 선지·보기·발문은 정답 조건 변경 위험이 있어 무조건 일괄 윤문하지 않는다.
2. 반환된 style 폴더를 upstream run으로 사용한다. 스킬이 고른 경로에 맞춰 Codex가 진단·윤문한다. 지문은 시험 문항임을 명시하고 논리 연산자, 부정, 날짜, 주체, 정의, 수치, 조문을 보존한다.
3. `style-check FOLDER`로 upstream 게이트와 해안 보호 토큰 비교를 수행한다. 실패하면 채택하지 않는다. 토큰 비교 통과는 의미 보존의 충분조건이 아니다.
4. 수정 전후 의미를 편집자가 비교한다. 바꾸려는 원본 candidate가 binding.json의 해시와 같은지 확인한다. final.md의 HUMANIZE-SUMMARY 등 메타데이터를 지문에 넣지 않는다.
5. 채택한 수정본을 새 draft 파일로 저장한 뒤 `check`와 **새 독립 풀이**를 수행한다. 풀이·해설이 어긋나면 원문으로 되돌리거나 출제 수정을 거친다.

목표는 자연스러운 시험 문장이다. AI 탐지 점수나 변경률을 낮추려고 정답 근거를 삭제하지 않는다. 일반 글의 리듬 개선이 법조문·정의·조건문의 명료함보다 우선하지 않는다.
