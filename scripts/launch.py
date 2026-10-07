"""Small subscription-native launcher. No credentials are read or modified."""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
STATUS_ITEMS = ["model-with-reasoning", "current-dir", "context-remaining", "five-hour-limit", "weekly-limit"]


def banner(madmax=False):
    accent = "\033[36;1m" if sys.stdout.isatty() else ""
    reset = "\033[0m" if accent else ""
    mode = "MADMAX · 승인/샌드박스 생략" if madmax else "STANDARD · 기존 권한 설정"
    print(f"\n{accent}  ≋≋≋  H A E A N  ·  해안{reset}\n  LEET 추리논증  /  PSAT 5급 · 7급\n  {mode}\n", flush=True)


def codex_command(codex, task, madmax=False):
    command = [codex, "-C", str(ROOT), "-m", "gpt-6-astra",
               "-c", "tui.status_line=" + json.dumps(STATUS_ITEMS)]
    if madmax:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    return command + ["$haean " + task]


def help_text():
    banner()
    print('''시작하기
  haean setup            스킬과 로컬 도구 설치
  haean doctor           설치·로그인 상태 점검 (JSON)
  haean status           로컬 문항 작업 현황
  haean track-exam RUN   status에 표시할 현재 회차 지정
  haean setup-figures     도식·그래프 검토 도구 설치
  haean setup-layout     한글 양식 도구 설치
  haean "작업 요청"      Astra와 해안 작업 시작
  haean --madmax "요청"  이번 실행만 승인·샌드박스 생략

예시
  haean "LEET 규범 논증 평가 2문항을 만들고 독립 검토해줘"
  haean "PSAT 7급 자료해석 25문항 회차를 구성해줘"
  haean "검토의견.txt를 읽고 문항 수정과 개선 가설을 구분해줘"

앱에서는 이 저장소를 열고 $haean을 호출하세요.
CLI 하단: 실제 모델 · 작업 폴더 · 남은 컨텍스트 · 사용량 한도.
원문 자료와 최종 전문가 검토는 팀에서 별도로 제공합니다.''')


def status():
    from collections import Counter
    banner()
    current_exam_status()
    states = Counter()
    unreadable = 0
    # Only authoritative run states, not process liveness or expert quality.
    for file in (ROOT / "runs").rglob("status.json"):
        if "items" in file.relative_to(ROOT / "runs").parts:
            continue  # Assembled item views duplicate their parent review run.
        try:
            states[json.loads(file.read_text()).get("state", "unknown")] += 1
        except (OSError, ValueError, TypeError):
            unreadable += 1
    labels = {"prepared": "준비됨", "awaiting_independent_review": "독립 검토 대기",
              "awaiting_human_review": "사람 검토 대기", "needs_revision": "수정 필요", "failed": "실행 실패"}
    print(f"작업 폴더: {ROOT}")
    if not states: print('아직 기록된 문항 작업이 없습니다. haean "문항 제작 요청"으로 시작하세요.')
    for state, count in sorted(states.items()): print(f"  {labels.get(state, state)}: {count}묶음")
    if unreadable: print(f"  읽기 대기/오류: {unreadable}개")
    print("이전 수정 실행도 포함한 기록입니다. 실행 중 여부·전문가 승인·납품 완료를 뜻하지 않습니다.")


def exam_registry():
    path = ROOT / 'runs/current-exams.json'
    if not path.exists(): return {'version': 1, 'exams': {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('exams'), dict):
        raise ValueError('현재 회차 목록 형식이 올바르지 않습니다: ' + str(path))
    return data


def tracked_exam_path(value):
    run = Path(value).expanduser()
    run = (ROOT / run).resolve() if not run.is_absolute() else run.resolve()
    try: run.relative_to((ROOT / 'runs').resolve())
    except ValueError: raise ValueError('현재 회차는 이 저장소의 runs/ 안에서 지정하세요')
    return run


def track_exam(value):
    run = tracked_exam_path(value)
    content = (run / 'assembled.json').read_bytes()
    result = json.loads(content)
    if not isinstance(result, dict) or not all(k in result for k in ['exam', 'subject', 'requested', 'written', 'errors']):
        raise ValueError('assembled.json이 있는 회차를 지정하세요')
    key = f"{result['exam']} / {result['subject']} / {result['requested']}문항"
    registry = exam_registry()
    registry['exams'][key] = {'run': str(run.relative_to(ROOT)),
                              'assembled_sha256': hashlib.sha256(content).hexdigest()}
    path = ROOT / 'runs/current-exams.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
    temporary.replace(path)
    print(f'현재 회차 지정: {key}\n{run}\n검토·승인 상태는 변경하지 않았습니다.')


def current_exam_status():
    try: entries = exam_registry()['exams']
    except (OSError, ValueError) as exc:
        print(f'현재 회차 목록 확인 필요: {exc}')
        return
    if not entries:
        print('현재 회차 미지정. haean track-exam runs/회차폴더 로 지정하세요.')
        return
    print('현재 회차')
    for key, entry in entries.items():
        try:
            run = tracked_exam_path(entry['run'])
            content = (run / 'assembled.json').read_bytes(); result = json.loads(content)
            changed = hashlib.sha256(content).hexdigest() != entry['assembled_sha256']
            print(f"  {key}: {result['written']}/{result['requested']} · 조립 당시 오류 {len(result['errors'])}건")
            print(f'    {run}')
            if changed: print('    지정 후 조립 기록이 변경됨. 현재 파일과 검토 이력을 확인하세요.')
            print('    사람 승인: ' + ('기록 있음' if result.get('human_approved') else '미확인')
                  + ' · 한글 배치 검증: ' + ('기록 있음' if result.get('layout_verified') else '미확인'))
            if (run / 'hwp').is_dir(): print(f"    한글 산출물: {run / 'hwp'}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f'  {key}: 현재 회차 기록 확인 필요 ({exc})')
    print('조립 기록은 문항·회차 전체의 품질 승인이나 실행 중 여부를 뜻하지 않습니다.\n')


def link_skill(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() and target.resolve() == source.resolve():
        return
    if target.exists() or target.is_symlink():
        raise ValueError(f"기존 스킬과 충돌합니다. 덮어쓰지 않았습니다: {target}")
    target.symlink_to(os.path.relpath(source, target.parent), target_is_directory=True)


def setup():
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 이상이 필요합니다")
    for source in (ROOT / "skills").iterdir():
        if (source / "SKILL.md").is_file():
            link_skill(source, ROOT / ".agents/skills" / source.name)
    if not (ROOT / "vendor/im-not-ai/.git").exists():
        subprocess.run(["git", "submodule", "update", "--init", "--depth", "1"], cwd=ROOT, check=True)
    humanizer = ROOT / "vendor/im-not-ai/codex/skills/humanize-korean"
    if not (humanizer / "SKILL.md").is_file():
        raise ValueError("고정된 im-not-ai submodule을 불러오지 못했습니다")
    link_skill(humanizer, ROOT / ".agents/skills/humanize-korean")
    python = ROOT / ".venv/bin/python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-e", ".[dev]"], cwd=ROOT, check=True)
    print("해안 스킬·역할·로컬 도구 설치 완료. Codex에서 이 폴더를 다시 열고 $haean을 호출하세요.")


def source_status():
    import sqlite3
    database = ROOT / "data/corpus.sqlite"
    if not database.is_file(): return {"records": 0, "state": "not_imported"}
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            rows = db.execute("SELECT exam, role, COUNT(*) FROM records GROUP BY exam, role").fetchall()
        total = sum(row[2] for row in rows)
        return {"records": total, "state": "indexed" if total else "empty",
                "groups": [{"exam": exam, "role": role, "count": count} for exam, role, count in rows],
                "note": "색인 수는 정답·전문가 검증 수가 아닙니다."}
    except sqlite3.Error:
        return {"records": None, "state": "unreadable", "note": "원본을 보존하고 DB 경로·스키마를 확인하세요."}


def doctor(strict=False):
    skills = []
    for source in sorted((ROOT / "skills").iterdir()):
        if (source / "SKILL.md").exists():
            target = ROOT / ".agents/skills" / source.name
            skills.append({"name": source.name, "discovered": target.exists() and target.resolve() == source.resolve()})
    roles = []
    for file in sorted((ROOT / ".codex/agents").glob("*.toml")):
        role = tomllib.loads(file.read_text())
        roles.append({"name": role["name"], "valid": all(role.get(k) for k in ("name", "description", "developer_instructions"))})
    codex = shutil.which("codex")
    auth = subprocess.run([codex, "login", "status"], capture_output=True, text=True, timeout=10) if codex else None
    logged_in = bool(auth and auth.returncode == 0 and "ChatGPT" in auth.stdout + auth.stderr)
    python = ROOT / ".venv/bin/python"
    dependencies = subprocess.run([str(python), "-c", "import haean, pydantic, openpyxl, olefile"],
                                  cwd=ROOT, capture_output=True, text=True, timeout=10) if python.exists() else None
    tools_ready = bool(dependencies and dependencies.returncode == 0)
    humanizer = (ROOT / ".agents/skills/humanize-korean/SKILL.md").exists()
    sources = source_status()
    figures = subprocess.run([str(python), "-c", "import matplotlib, PIL"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10) if python.exists() else None
    figures_ready = bool(figures and figures.returncode == 0)
    actions = []
    if not codex: actions.append("Codex CLI를 설치하세요: https://learn.chatgpt.com/docs/cli")
    elif not logged_in: actions.append("codex login 으로 ChatGPT 구독 계정에 로그인하세요.")
    if not tools_ready or not humanizer or not all(s['discovered'] for s in skills):
        actions.append("./haean setup 으로 프로젝트 도구와 스킬을 설치하세요.")
    if sources['state'] != 'indexed': actions.append('haean tools import /허용된/자료경로 로 출제 참고자료를 가져오세요.')
    if not figures_ready: actions.append("도식·그래프 문항은 haean setup-figures 로 이미지 검토 도구를 설치하세요.")
    layout_ready = (ROOT / "data/bin/hwp").is_file() and (ROOT / "data/bin/HaeanFill.class").is_file()
    if not layout_ready: actions.append("한글 출력이 필요하면 haean setup-layout 을 실행하고 팀의 빈 양식을 준비하세요.")
    ready = bool(codex and logged_in and tools_ready and humanizer and skills
                 and all(s['discovered'] for s in skills) and roles and all(r['valid'] for r in roles))
    print(json.dumps({"root": str(ROOT), "codex": codex,
                      "chatgpt_login": logged_in,
                      "tools_installed": tools_ready,
                      "humanizer": (ROOT / ".agents/skills/humanize-korean/SKILL.md").exists(),
                      "skills": skills, "roles": roles, "core_ready": ready,
                      "runtime_role_loading": "not_verified",
                      "runtime_role_note": "역할 파일 검증과 실제 로딩은 다릅니다. 프로젝트 신뢰와 세션 도구를 확인하세요. 미지원 시 role 명령의 지침 전달 경로를 사용합니다.",
                      "sources": sources, "layout_tools_installed": layout_ready,
                      "figure_dependencies_installed": figures_ready, "graphviz": shutil.which('dot'),
                      "native_layout_verified": False, "next_actions": actions}, ensure_ascii=False, indent=2))
    return 1 if strict and not ready else 0


def main():
    args = sys.argv[1:]
    if args == ["setup"]: return setup()
    if args == ["setup-figures"]:
        python = ROOT / ".venv/bin/python"
        if not python.exists(): raise ValueError("먼저 haean setup 을 실행하세요")
        subprocess.run([str(python), "-m", "pip", "install", "-e", ".[layout]"], cwd=ROOT, check=True)
        print("그림 검토용 Python 도구 설치 완료.")
        if not shutil.which('dot'): print("논증 도식에는 Graphviz도 필요합니다. macOS: brew install graphviz / Linux: sudo apt install graphviz")
        print("한국어 폰트는 팀 폰트 또는 설치된 NanumGothic/Noto Sans CJK KR/AppleGothic/맑은 고딕을 사용합니다.")
        return 0
    if args == ["setup-layout"]:
        python = ROOT / ".venv/bin/python"
        if not python.exists(): raise ValueError("먼저 ./haean setup 을 실행하세요")
        subprocess.run([str(python), "-m", "pip", "install", "-e", ".[layout]"], cwd=ROOT, check=True)
        return subprocess.run([sys.executable, str(ROOT / "scripts/setup_layout.py")], check=True).returncode
    if args in (["doctor"], ["doctor", "--check"]): return doctor(strict="--check" in args)
    if args == ["status"]: return status()
    if args and args[0] == 'track-exam':
        if len(args) != 2: raise ValueError('사용법: haean track-exam runs/회차폴더')
        return track_exam(args[1])
    if args == ["--version"]:
        print("haean " + tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"])
        return 0
    if args and args[0] == "tools":
        return subprocess.run([str(ROOT / "scripts/haean-tool"), *args[1:]]).returncode
    if args and args[0] in {"-h", "--help", "help"}: return help_text()
    codex = shutil.which("codex")
    if not codex: raise ValueError("Codex CLI를 설치하고 codex login으로 ChatGPT 로그인하세요")
    login = subprocess.run([codex, "login", "status"], capture_output=True, text=True)
    if login.returncode or "ChatGPT" not in login.stdout + login.stderr:
        raise ValueError("ChatGPT 구독 로그인 상태가 아닙니다. codex login을 실행하세요")
    madmax = bool(args and args[0] == "--madmax")
    if madmax: args = args[1:]
    task = " ".join(args) or "해안 작업 환경과 자료 상태를 확인하고 다음 작업을 받을 준비를 해줘."
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(key, None)
    if not (ROOT / ".agents/skills/haean/SKILL.md").exists() or not (ROOT / ".venv/bin/python").exists():
        raise ValueError("해안 설치가 필요합니다. ./haean setup 을 먼저 실행하세요")
    banner(madmax=madmax)
    return subprocess.run(codex_command(codex, task, madmax), env=env).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
