"""Small subscription-native launcher. No credentials are read or modified."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


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


def doctor():
    skills = []
    for source in sorted((ROOT / "skills").iterdir()):
        if (source / "SKILL.md").exists():
            target = ROOT / ".agents/skills" / source.name
            skills.append({"name": source.name, "discovered": target.exists()})
    roles = []
    for file in sorted((ROOT / ".codex/agents").glob("*.toml")):
        role = tomllib.loads(file.read_text())
        roles.append({"name": role["name"], "valid": all(role.get(k) for k in ("name", "description", "developer_instructions"))})
    codex = shutil.which("codex")
    auth = subprocess.run([codex, "login", "status"], capture_output=True, text=True) if codex else None
    print(json.dumps({"root": str(ROOT), "codex": codex,
                      "chatgpt_login": bool(auth and auth.returncode == 0 and "ChatGPT" in auth.stdout + auth.stderr),
                      "tools_installed": (ROOT / ".venv/bin/python").exists(),
                      "humanizer": (ROOT / ".agents/skills/humanize-korean/SKILL.md").exists(),
                      "skills": skills, "roles": roles}, ensure_ascii=False, indent=2))


def main():
    args = sys.argv[1:]
    if args == ["setup"]: return setup()
    if args == ["setup-layout"]:
        python = ROOT / ".venv/bin/python"
        if not python.exists(): raise ValueError("먼저 ./haean setup 을 실행하세요")
        subprocess.run([str(python), "-m", "pip", "install", "-e", ".[layout]"], cwd=ROOT, check=True)
        return subprocess.run([sys.executable, str(ROOT / "scripts/setup_layout.py")], check=True).returncode
    if args == ["doctor"]: return doctor()
    if args and args[0] == "tools":
        return subprocess.run([str(ROOT / "scripts/haean-tool"), *args[1:]]).returncode
    if args and args[0] in {"-h", "--help"}:
        print('./haean setup | doctor | tools COMMAND | "자연어 요청"\n기본 실행: Codex ChatGPT 로그인 + Astra + $haean')
        return 0
    codex = shutil.which("codex")
    if not codex: raise ValueError("Codex CLI를 설치하고 codex login으로 ChatGPT 로그인하세요")
    login = subprocess.run([codex, "login", "status"], capture_output=True, text=True)
    if login.returncode or "ChatGPT" not in login.stdout + login.stderr:
        raise ValueError("ChatGPT 구독 로그인 상태가 아닙니다. codex login을 실행하세요")
    task = " ".join(args) or "해안 작업 환경과 자료 상태를 확인하고 다음 작업을 받을 준비를 해줘."
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(key, None)
    return subprocess.run([codex, "-C", str(ROOT), "-m", "gpt-6-astra", "$haean " + task], env=env).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
