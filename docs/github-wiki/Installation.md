# 설치와 실행

```bash
git clone https://github.com/YounghwanKil/haean.git
cd haean
./install.sh
haean doctor
haean "LEET 추리논증 문항을 만들고 독립 검토해줘"
```

Python 3.11+, Git, Codex CLI와 ChatGPT 구독 로그인이 필요합니다. API 키는 사용하지 않습니다. 프로젝트 스킬·역할을 설치하며 전역 Codex 설정을 덮어쓰지 않습니다. 앱에서는 해안 프로젝트를 열고 자연어로 요청합니다. `$haean`은 총괄을 명시하는 선택사항입니다. CLI 기본 모델은 `gpt-6-astra`입니다.

`haean --madmax "작업 요청"`은 해당 실행에만 Codex의 승인·샌드박스 생략 옵션을 전달합니다. 기본 실행에는 적용하지 않습니다. 시작 화면과 모델·컨텍스트·사용량 하단 상태줄을 사용합니다. Codex 본체를 포크한 별도 TUI는 아닙니다.

설치 후 `haean doctor --check`로 핵심 설치 상태를 확인합니다. `haean`을 찾지 못하면 `~/.local/bin/haean doctor --check`로 실행하고 설치기가 안내한 PATH 설정을 적용하세요. `./haean`은 저장소 폴더 안에서 직접 실행하는 표기입니다.

파란 하단 HUD에는 tmux가 필요합니다. macOS에서는 `brew install tmux`, Debian/Ubuntu에서는 `sudo apt install tmux`로 준비합니다. `haean hud`로 표시 조건을 확인하고 `haean banner`로 모델 호출 없이 로고를 미리 볼 수 있습니다. 이미 tmux 안이라면 기존 배치를 보존하므로 해안의 별도 HUD를 추가하지 않습니다.

설치에는 팀 원문·문항 DB가 포함되지 않습니다. 자료 준비와 Codex 대화창 입력 방법은 [사용법](Usage), 한글 출력 도구는 [양식 출력](Layout)을 확인하세요.
