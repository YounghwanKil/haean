# 설치와 실행

```bash
gh repo clone YounghwanKil/haean
cd haean
./install.sh
haean doctor
haean "LEET 추리논증 문항을 만들고 독립 검토해줘"
```

Python 3.11+, Git, Codex CLI와 ChatGPT 구독 로그인이 필요합니다. API 키는 사용하지 않습니다. 프로젝트 스킬·역할을 설치하며 전역 Codex 설정을 덮어쓰지 않습니다. 앱에서는 프로젝트를 열고 `$haean`을 호출합니다. CLI 기본 모델은 `gpt-6-astra`입니다.

`haean --madmax "작업 요청"`은 해당 실행에만 Codex의 승인·샌드박스 생략 옵션을 전달합니다. 기본 실행에는 적용하지 않습니다. 시작 화면과 모델·컨텍스트·사용량 하단 상태줄을 사용합니다. Codex 본체를 포크한 별도 TUI는 아닙니다.
