<p align="center"><img src="assets/haean-mascot-v1.png" width="240" alt="책을 읽는 파도, 해안 마스코트"></p>

# haean — 해안 전용 Codex 하네스

**Codex에 ChatGPT 계정으로 로그인한 팀원이 Astra와 함께 쓰는 출제 작업 환경**입니다. `$haean`이 자료 조사, LEET·PSAT 출제, 한국어 윤문, 독립 풀이, 편집 검토, 회차 구성, 평가·개선 실험을 조율합니다. API 키나 별도 LLM 서버를 설정하지 않습니다.

## 설치

```bash
git clone https://github.com/YounghwanKil/haean.git
cd haean
./install.sh
haean doctor
```

물결 로고가 있는 파란 하단 HUD까지 사용하려면 tmux를 설치합니다: macOS `brew install tmux`, Debian/Ubuntu `sudo apt install tmux`. `haean hud`로 설치·비활성화·기존 tmux 여부를 확인할 수 있습니다. HUD는 Codex 기본 상태줄 바로 아래의 **별도 고정 줄**이며 터미널의 일반 본문 복사에는 포함되지 않을 수 있습니다.

Python 3.11+, Git, Codex CLI가 필요합니다. `codex login`으로 ChatGPT 로그인합니다. `setup`은 프로젝트 안에 스킬 링크·Python 가상환경을 설치하고, 고정된 im-not-ai submodule을 가져옵니다. 전역 Codex 설정·계정 인증·권한을 덮어쓰지 않습니다. 현재 런처는 macOS/Linux용입니다.

Codex 앱에서 이 프로젝트를 열고 자연어로 요청하거나, 터미널에서 다음처럼 시작하세요. `$haean`은 총괄을 명시하고 싶을 때 붙이는 선택사항입니다.

```bash
./haean
./haean "LEET 규범 영역의 논증 평가 문항 2개를 만들고 독립 검토해줘"
./haean "PSAT 7급 자료해석 25문항의 회차 구성을 잡아줘"
./haean "최근 평가에서 실패한 문항을 분석하고 하네스 개선 후보 하나를 시험해줘"
```

CLI 런처는 `gpt-6-astra`를 선택합니다. 앱에서는 Astra를 직접 선택합니다. 계정의 모델 접근 권한과 Codex 사용량 한도가 적용됩니다. 사용할 수 없는 모델을 다른 모델로 조용히 대체하지 않습니다.

## 스킬 찾기와 바로 실행

일반 터미널에서는 `haean skills`로 전체 목록을 보고, `haean skills psat`로 설명·예시를 확인합니다. `haean skill psat "작업 요청"`은 해당 스킬로 시작하며 `haean --madmax skill psat "작업 요청"`도 지원합니다. 보통은 `haean "작업 요청"`으로 총괄에게 맡기면 됩니다.

열린 해안 대화창에서는 “리트 40문항 구성해줘”, “피셋 7급 자료해석 만들고 검토해줘”처럼 요청합니다. 런처가 시작할 때 해안 총괄을 연결하며, 총괄은 필요한 전문 스킬을 선택합니다. `$haean`, `$haean-psat`으로 사용할 스킬을 명시할 수도 있습니다. 해안 스킬은 프로젝트 범위로 설치되므로, 다른 프로젝트에서 연 일반 Codex까지 자동 연결되는 것은 아닙니다. `haean`과 `./haean`은 터미널 명령입니다. 앱의 스킬 표시는 프로젝트를 다시 열거나 새 세션에서 확인하세요. 각 스킬에 한국어 표시 이름·고유 설명·시작 예시를 제공합니다. 전체 Codex 화면을 바꾼 별도 TUI가 아니라, 해안 배너·명령과 Codex 상태 표시줄을 구성한 런처입니다.

언어이해는 `$haean-reading` 파일럿이며 30문항 실전 회차·HWP 자동 출력은 아직 정식 지원하지 않습니다. 로컬 지식 축적은 `$haean-wiki`가 담당합니다.

## 구성

| 층 | 구성 | 역할 |
|---|---|---|
| 총괄 | `$haean` | 요청을 과목별 작업으로 나누고 상태·자료·결과 관리 |
| 전문 스킬 | `$haean-leet`, `$haean-psat` | 시험별 새 문항 설계·수정 |
| 품질 | `$haean-review`, `$haean-style` | 정답 독립 풀이, 편집, im-not-ai 윤문 |
| 양식 | `$haean-layout` | 기존 HWP 문제지·해설지에 내용 삽입과 시각 검증 |
| 회차 | `$haean-exam` | 유형·난도·소재·공유 지문·정답 배치 |
| 개선 | `$haean-evolve` | 원문 실행 기록을 읽어 고정 평가로 후보 비교 |
| Codex 역할 | `.codex/agents/*.toml` | 조사·출제·풀이·편집·구성·개선 담당 |
| 로컬 도구 | `scripts/haean-tool` | 자료 검색·스키마·검산·이력·평가 집계 |

스킬은 프로젝트 `.agents/skills`에서 발견됩니다. 사용자 모델과 권한을 상속하는 역할 파일을 함께 제공합니다. 자동 작성은 Codex가 담당하고, Python은 자료·검증을 보조합니다. [Codex 스킬](https://learn.chatgpt.com/docs/build-skills)과 [custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents)의 공식 구조를 따릅니다.

런타임에 custom-role 선택 인자가 없으면 총괄이 `tools role ROLE_NAME`으로 지침을 읽어 일반 서브에이전트에 전달합니다. 현재 환경에서 이 방식으로 Astra 윤문·개선 역할을 실제 실행했습니다. 역할 TOML이 존재한다는 사실과 자동 로딩 성공을 구분하며, 독립 풀이는 새 컨텍스트로 실행합니다.

## 팀 자료

```bash
./haean tools audit-sources ~/Downloads
./haean tools import-team ~/Downloads --refresh
./haean tools import '/path/to/additional-source.xlsx'
./haean tools import-questions '/path/to/visually-checked-question-packet.json'
./haean tools status
```

제공된 LEET 통합 엑셀·위키·수정 대조, PSAT 5급/7급 통계, 검토 의견과 HWP를 로컬 SQLite에 색인합니다. 동일 파일은 해시로 중복 제거합니다. 원본은 수정하지 않습니다. 팀원마다 허용된 원본을 별도로 가져와야 하며 원문은 GitHub에 올라가지 않습니다.

PSAT 입력에는 지문 전문이 없는 통계가 많습니다. HWP 텍스트 추출은 수식·도형·레이아웃 검증을 대신하지 않습니다. [자료 분석](docs/SOURCE_FINDINGS.md)을 참고하세요.

`import-questions`는 PDF 해시·쪽·출처와 화면 대조 기록이 있는 전문 전사를 등록합니다. 표·보기·선지와 추가 배치 정보를 보존하며, 이 경로에서는 미확인 정답을 추정해 넣지 않습니다. 전사 확인과 정답 검증을 구분합니다.

## 출제·검토

평소에는 자연어 요청으로 충분합니다. 내부적으로 다음 도구를 사용합니다.

```bash
./haean tools prepare --exam leet --subject 추리논증 --type '논증 평가 및 문제 해결' --topic '공공 전자기록'
./haean tools check RUN RUN/draft.json
./haean tools blind RUN
./haean tools review-result RUN RUN/blind-result.json RUN/editorial-result.json --candidate-sha '검토 당시 해시'
./haean tools export RUN
```

`prepare`는 자료와 스키마를 만들며 문항을 만든 척하지 않습니다. Codex 출제자가 실제 JSON을 씁니다. `blind`는 현재 ChatGPT 로그인으로 **새 Codex 세션**을 실행해 정답을 제외한 문항만 풉니다. 정답·조건 불일치나 A/B 오류가 있으면 수정 뒤 다시 검토합니다. 통과 상태도 사람의 최종 검토 대기입니다.

도식·그래프 문항은 `haean setup-figures`로 그림 패키지를 준비하세요. 논증 도식에는 Graphviz, 한국어 그래프에는 NanumGothic·Noto Sans CJK KR·AppleGothic 등 한국어 폰트가 필요합니다. `doctor`가 Python 그림 패키지와 Graphviz 상태를 안내합니다. 폰트는 실제 그림을 만들 때 확인합니다.

자동 독립 풀이·편집 검토에는 구조 데이터와 수험생용 PNG를 함께 전달합니다. 이미지와 해시를 실행 기록에 보관하고 내부 제작 메모는 그림에서 제외합니다. 렌더 실패 시 모델 호출을 중단하며 텍스트 검토로 조용히 대체하지 않습니다. PNG 검토는 HWP의 실제 인쇄 배치 검증과 별개입니다. 이미지 입력 추가 전후의 평가는 하네스 버전을 구분하고, 고정 비교 실험에는 같은 입력 방식을 사용합니다.

`generate`는 자연어 총괄 대신 동일한 생성·풀이·편집 절차를 스크립트로 재현할 때 쓰는 보조 명령입니다. 이것도 OpenAI API SDK 대신 Codex CLI를 사용합니다.

## 텍스트 피드백으로 개선하기

팀원의 자유로운 검토 의견이 개선의 입력입니다. 특정 문항 의견은 현재 문항 해시와 연결하고, 공통 의견은 시험·과목별 피드백함에 원문 그대로 보관합니다. 자연어로 총괄에게 전달하거나 UTF-8 `.txt` 파일을 넣을 수 있습니다.

```bash
# 문항별 의견: 이 버전에 대한 지적이라는 연결을 유지
./haean tools feedback RUN --item ITEM-001 --reviewer 팀검토자 --severity B --file 검토의견.txt
# 여러 문항에 적용될 수 있는 공통 의견
./haean tools feedback-note --exam psat7 --subject 자료해석 --reviewer 팀검토자 --file 검토의견.txt
./haean tools feedback-notes --exam psat7 --subject 자료해석
./haean "PSAT 7급 자료해석 피드백함을 읽고, 근거 문항을 확인해 개선 후보 하나를 평가해줘"
```

급수 공통 문체 의견은 `--exam team`으로 기록합니다. 모델이 쓴 의견은 `--origin model`로 표시합니다. 같은 내용·작성자·범위의 중복 등록은 합쳐집니다. 공통 의견은 `data/feedback/`에 저장되어 Git에 올라가지 않습니다.

총괄은 의견을 그대로 고정 규칙으로 붙이지 않고, 관련 원문에서 **오류·취향·국소 수정·일반화 가능한 지침**을 구분합니다. 개선 담당은 피드백 ID, 근거 문항, 변경 가설, 패치와 평가 결과를 연결합니다. 효과가 없거나 다른 과목에 퇴행이 생기면 후보를 기각하고 원래 지침을 유지합니다. 지침 변경을 전문가 품질 향상으로 인정하려면 실제 팀 검토와 별도 평가가 필요합니다.

## 누적 문항의 반복 점검

과거 생성물은 출처 자료와 별도로 로컬 `data/generated.sqlite`에 기록합니다. 이전 문항을 명시적으로 등록한 뒤 새 문항과 대조합니다.

```bash
./haean tools novelty-index PREVIOUS_RUN_OR_PRODUCTION
./haean tools novelty-check NEW_RUN_OR_PRODUCTION --out runs/novelty-review.json
```

수정본은 같은 ID의 버전으로 남기며 새 문항 수에 더하지 않습니다. 숫자·영문 기호를 바꾼 지문, 조건·해설, 선지의 유사 후보를 찾고, 과목별로 과거 버전까지 검색합니다. 동일 유형이나 공통지문이라는 이유만으로 표절 판정을 내리지 않습니다. 편집 검토자가 후보 쌍의 결정적 추론과 오답 설계를 비교해야 합니다. 문자 유사도가 낮은 구조 재탕은 놓칠 수 있어 이 명령만으로 독창성을 승인하지 않습니다. 100문항 이후 품질은 별도의 연속 생성 실험으로 확인해야 합니다.

## im-not-ai 연결

설치 시 이미 내려받은 submodule도 고정 커밋과 대조합니다. 수정 없는 다른 버전은 지정 버전으로 맞추고, 로컬 수정이 있으면 보존한 채 설치를 멈춰 안내합니다. `haean doctor`의 `humanizer_revision`에서 고정 버전·실제 버전·수정 여부를 확인할 수 있습니다.


[im-not-ai](https://github.com/epoko77-ai/im-not-ai)를 **Git submodule로 고정**하고 `$humanize-korean` 스킬을 설치합니다. `$haean-style`은 이 도구의 실제 진단·윤문·게이트에 시험 문제용 조건 보존 검사를 더합니다.

```bash
./haean tools style-prepare RUN --item ITEM-001 --field passage
# Codex가 반환된 폴더에서 humanize-korean 절차를 수행
./haean tools style-check RUN/style/ITEM-001/passage
```

날짜·수치·부정·양화사의 변경을 감시하며 윤문 결과는 자동으로 원문을 덮어쓰지 않습니다. 의미 비교와 새 독립 풀이 후 채택합니다. upstream 문체 점수가 시험 문항의 정답 타당성을 보장하지 않습니다.

## 평가와 스스로 개선하는 구조

```mermaid
flowchart LR
    A[해안 총괄] --> B[LEET / PSAT 출제]
    B --> C[새 컨텍스트 독립 풀이]
    C --> D[편집 검토·필요시 수정]
    D --> E[고정 평가·전문가 의견]
    E --> F[실패 원문과 실행 기록]
    F --> G[개선 가설·후보 패치]
    G --> H[동일 조건 비교]
    H --> I[채택·보류·기각 기록]
    I --> A
```

[평가 프로토콜](evals/protocol.md)은 정답 타당성을 필수 조건으로 두고 8개 품질 차원을 별도로 평가합니다. LEET와 PSAT의 7개 제품군을 나눠 보며 고정 과제·모델·수정 예산으로 비교합니다.

```bash
./haean tools evaluate --suite evals/pilot.json --cases leet-norm psat7-data --out experiments/baseline
./haean tools experiment improve-001 --baseline experiments/baseline/results.json
# $haean-evolve가 실패 원문 분석, 후보 브랜치 변경, 동일 조건 재평가를 수행
./haean tools compare experiments/baseline/results.json experiments/candidate/results.json
```

`evaluate`의 현재 실행 모드는 **Codex 프롬프트 파이프라인 평가**입니다. 대화형 총괄의 모든 도구 사용과 im-not-ai 윤문을 자동 재현하지는 않습니다. 이 모드는 결과에 명시됩니다. 대화형 전체 하네스·윤문 포함 실험은 `$haean-evolve`가 해당 실행 원문을 별도 기록하고 같은 조건끼리 비교합니다.

[Meta-Harness 논문](https://arxiv.org/abs/2603.28052)의 코드·점수·실행 이력 기반 외부 개선 루프를 적용했습니다. 모델 가중치를 학습하는 기능은 아닙니다. 초기 pilot 7과제는 실행 점검용이며 전문가 인증 데이터가 아닙니다. 실제 전문가 문항 평가와 봉인 holdout을 쌓기 전에는 자동 점수 상승을 전문가급 출제 능력으로 해석하지 않습니다. 기본 반복은 후보 한 차례부터이며 무한 실행하지 않습니다.

[첫 Astra 실험 기록](docs/PILOT.md)에 7개 제품군의 실제 생성·검토와 첫 후보 비교를 정리했습니다. 모델 점수 상승, 초안 오류, 수정 비용, 아직 검증하지 못한 범위를 함께 기록했습니다.

## 한글 양식

`./haean setup-layout`으로 한글 MCP와 Java 삽입 도구를 설치합니다. `$haean-layout`은 제공된 빈 HWP 마스터에 문항을 채우며 LEET·PSAT의 시험명과 과목 제목을 바꿉니다. 원본의 편집 틀을 재사용합니다. JDK 17 이상이 필요하며 API 설정은 없습니다.

LEET·PSAT 자료해석 샘플의 한글 열기와 내용 배치를 확인했습니다. 전체 회차·해설지·인쇄 결과를 포함한 99% 재현을 인증한 상태는 아닙니다. [지원 마스터와 검증 범위](docs/LAYOUT.md)를 확인하세요.

## 검증

```bash
.venv/bin/pytest -q
./haean doctor
```

[팀 작업법](docs/WORKFLOW.md), [품질 게이트](docs/QUALITY.md)를 참고하세요. 실행·수정·검토·점수와 미완료 범위를 남기며, 테스트 통과와 실제 전문가 품질 검증을 구분합니다.

## 해안 명령·로고·상태 표시

`./install.sh`를 한 번 실행하면 `~/.local/bin/haean`에 이 저장소를 가리키는 실행 명령을 등록합니다. 이후 어느 폴더에서나 `haean "작업 요청"`으로 같은 해안 작업 환경을 엽니다. 기존 동명 명령은 덮어쓰지 않으며, 다른 위치는 `./install.sh --bin-dir /원하는/폴더`로 지정합니다. Python 경로 지정은 `HAEAN_PYTHON=python3.13 ./install.sh`를 사용합니다.

```bash
haean --help
haean --version
haean status
haean doctor
```

CLI 시작 시 해안 물결 로고를 표시합니다. 하단에는 Codex의 실제 모델·현재 폴더·남은 컨텍스트·5시간/주간 사용량을 표시합니다. 런처가 실행별 `-c tui.status_line=…` 설정을 전달하고, 프로젝트 설정에도 같은 기본값을 제공합니다. 사용량 정보는 Codex가 제공할 때 표시됩니다. 전역 설정이나 앱 UI를 변경하지 않습니다. [공식 status_line 설정](https://learn.chatgpt.com/docs/config-file/config-reference)을 사용하며 런처 항목은 `scripts/launch.py`의 `STATUS_ITEMS`에서 조정할 수 있습니다. Codex 0.160.1에서는 `-c`를 쓴 세션이 공용 백그라운드 서버 대신 내장 모드로 실행된다는 시작 알림이 표시됩니다.

`haean status`는 로컬 문항 검토 상태를 읽으며 분리된 회차 편집 뷰는 중복 집계하지 않습니다. 과거 수정 실행은 포함되므로 현행 회차 수나 살아 있는 프로세스 수가 아닙니다. 모델 검토 대기/통과와 전문가 승인을 구분합니다.

현재 볼 회차는 `haean track-exam runs/회차폴더`로 지정합니다. `assembled.json`이 있는 프로젝트 내부 회차 또는 언어이해 `book.json` 회차를 시험·과목·문항 수별로 하나씩 표시하며, 같은 종류를 다시 지정해도 이전 산출물을 지우지 않습니다. `status` 상단에 현재 경로·조립 당시 오류·사람 승인 및 한글 검증 기록을 보여 줍니다. 지정 뒤 조립 기록이 바뀌면 확인 메시지가 나오며, 회차 지정 자체는 검토나 승인 상태를 바꾸지 않습니다.

해제는 설치에 쓴 저장소에서 `./install.sh --uninstall`을 실행합니다. 다른 경로에 설치했다면 같은 `--bin-dir`를 지정합니다. 이 설치기가 만든 실행 명령만 지우고 원문·실행 기록·저장소·Codex 설정은 보존합니다. 저장소를 이동했거나 Python 경로가 바뀌어 기존 명령과 일치하지 않으면 덮어쓰지 않고 중단합니다.

GitHub 저장소는 공개되어 누구나 클론할 수 있습니다. 팀 원문 자료와 로컬 지식 위키는 포함하지 않습니다. 설치 자동화가 저장소의 공개 범위를 바꾸지는 않습니다. Windows에서는 WSL을 사용하세요.

첫 실행에서 Codex가 프로젝트 신뢰를 요청하면 저장소 내용을 확인한 뒤 직접 선택하세요. 신뢰하지 않은 프로젝트의 스킬은 발견되어도 `.codex`의 역할·MCP 설정은 비활성화될 수 있습니다. 설치기는 전역 신뢰 목록이나 권한을 바꾸지 않습니다. `doctor`의 역할 `valid`는 파일 검증이며 현재 세션에서 역할이 로딩됐다는 증거는 아닙니다.

`haean doctor --check`는 핵심 설치·ChatGPT 로그인·스킬·역할 파일 검증이 빠지면 종료 코드 1을 반환합니다. 가상환경 파일 존재뿐 아니라 필요한 Python 패키지의 import도 확인합니다. 자료 DB는 읽기 전용으로 과목·자료 역할별 색인 수를 보여 주며, 비어 있거나 한글 도구가 없으면 `next_actions`에 준비 명령을 안내합니다. 자료와 HWP 도구는 선택 작업이므로 이들의 부재는 핵심 설치의 실패로 처리하지 않습니다. `core_ready=true`도 실제 서브에이전트 로딩·문항 품질·한글 렌더 합격을 뜻하지 않습니다.

## 지식 축적과 실행 모드

`$haean-wiki`는 원문·검색 DB 위에 출처 기반 로컬 지식 위키를 축적합니다. `./haean tools wiki init`, `wiki search --query "검색어"`, `wiki lint`로 관리합니다. 사용법은 [GitHub Wiki](https://github.com/YounghwanKil/haean/wiki)를 참고하세요. 원문·로컬 위키는 Git에 올리지 않습니다.

`haean --madmax "작업 요청"`은 해당 실행에만 승인·샌드박스 생략 옵션을 적용합니다. 시작 화면에 모드를 표시하고 기본 실행의 권한은 바꾸지 않습니다. 터미널은 Codex 본체와 해안 시작 화면·하단 상태줄을 사용합니다.

`haean`과 `haean --madmax`는 일반 터미널에서 실행합니다. `./haean`은 저장소 폴더 안에서 같은 명령을 직접 실행하는 표기입니다. 이미 해안 프로젝트의 Codex 대화창에 있다면 자연어로 작업을 요청하세요. `$haean 작업 요청`으로 총괄을 명시해도 됩니다. 다른 프로젝트의 일반 Codex에는 해안 설정이 자동 적용되지 않습니다. [처음 사용하는 팀원을 위한 안내](https://github.com/YounghwanKil/haean/wiki/Usage)에 입력 위치·화면·자료 준비를 정리했습니다.

### 큰 시작 로고

`haean` 또는 `haean --madmax`로 진입하면 책을 읽는 파도 마스코트와 실행 모드·선택 스킬이 담긴 환영 카드를 표시한 뒤 Codex로 이어집니다. `haean banner`는 모델 호출 없이 시작 화면만 보여주며, `haean banner --madmax`로 모드 표시도 확인할 수 있습니다. 좁은 창은 작은 로고로 전환하고 `NO_COLOR=1`이면 색을 끕니다. 대화형 터미널에서는 큰 HAEAN 글자를 먼저 약 1.5초 보여준 다음, 그 아래 마스코트 카드를 한 줄씩 표시하고 잠깐 머무릅니다. 전체 시작 연출은 약 3초이며 두 로고 모두 스크롤 기록에 남습니다. `HAEAN_NO_ANIMATION=1 haean`으로 지연을 끌 수 있습니다. 런처가 별도 화면을 열어 기존 셸 출력을 가리고 그 안에 로고와 Codex를 표시합니다. 종료하면 원래 셸 화면으로 돌아옵니다. 로고는 상단 고정 헤더가 아니며 대화가 길어지면 화면 위로 밀립니다. tmux가 설치돼 있고 tmux 밖에서 실행하면 별도 세션 하단에 파란색 `haean` 바를 추가합니다. Codex의 모델·컨텍스트·사용량은 그 위의 기본 상태줄에 유지합니다. `HAEAN_NO_TMUX=1 haean`은 별도 하단 바를 끕니다. 기존 tmux 안에서는 그 환경의 배치를 보존하고 별도 바를 추가하지 않습니다. 해안이 만든 tmux에서 detach하면 해당 실행도 종료됩니다. macOS에서 tmux 설치는 `brew install tmux`입니다.

시작 화면은 책을 읽는 파도 마스코트와 환영 카드입니다. PNG 로고는 `assets/haean-mascot-v1.png`, 터미널용 블록 그림은 `scripts/branding.py`에 있습니다. 터미널에서는 이미지 프로토콜 없이 문자와 ANSI 색으로 표시하며, 색을 끄거나 창이 좁으면 간단한 문자 그림을 사용합니다.
