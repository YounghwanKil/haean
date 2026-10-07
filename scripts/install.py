"""Install a reversible launcher without changing shell or Codex configuration."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def wrapper(root, python):
    return ('#!/bin/sh\n# Haean managed launcher\n'
            f'exec {shlex.quote(str(python))} {shlex.quote(str(root / "scripts/launch.py"))} "$@"\n')


def install(root, bin_dir, python, *, uninstall=False):
    root, bin_dir = root.resolve(), bin_dir.expanduser().absolute()
    target = bin_dir / "haean"
    content = wrapper(root, python)
    if target.is_symlink() or (target.exists() and (not target.is_file() or target.read_text() != content)):
        raise ValueError(f"기존 명령은 덮어쓰거나 삭제하지 않습니다: {target}. --bin-dir 로 다른 위치를 지정하세요.")
    if uninstall:
        if target.exists(): target.unlink()
        print(f"해안 실행 명령 해제: {target}\n저장소·자료·실행 이력은 보존했습니다.")
        return
    # Detect conflicts before making any environment changes.
    subprocess.run([str(python), str(root / "scripts/launch.py"), "setup"], cwd=root, check=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        # Exclusive creation protects a launcher installed concurrently.
        with target.open("x") as stream: stream.write(content)
    target.chmod(0o755)
    print(f"\n설치 완료: {target}\n  haean --help\n  haean doctor\n  haean \"LEET 문항 2개를 만들고 검토해줘\"")
    path_dirs = [Path(p).expanduser().absolute() for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if bin_dir not in path_dirs:
        print(f"\n현재 PATH에 설치 폴더가 없습니다. 이번 터미널에서 실행:\nexport PATH={shlex.quote(str(bin_dir))}:\"$PATH\"")
        print("계속 사용하려면 위 줄을 사용하는 셸 설정에 추가하세요. 설치기는 셸 설정을 수정하지 않습니다.")


def main():
    parser = argparse.ArgumentParser(description="해안 설치 및 실행 명령 등록")
    parser.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
    parser.add_argument("--uninstall", action="store_true", help="이 저장소의 실행 명령만 해제; 자료 보존")
    args = parser.parse_args()
    install(ROOT, args.bin_dir, Path(sys.executable), uninstall=args.uninstall)


if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"설치 중단: {exc}", file=sys.stderr)
        raise SystemExit(2)
