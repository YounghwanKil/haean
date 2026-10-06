"""Connect pinned im-not-ai runtime with exam-specific preservation checks."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from .models import Draft
from .pipeline import save

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor/im-not-ai"
FIELDS = ("passage", "explanation", "commentary")


def protected_tokens(text):
    # Conservative alarm, not a semantic equivalence proof.
    return Counter(re.findall(r"\d+(?:[.,]\d+)*|모든|모두|어떤|일부|누군가|전체|적어도|최대|최소|오직|반드시|않|없|아니|못|이상|이하|초과|미만|이전|이후|이내|각각|제\d+조|ㄱ|ㄴ|ㄷ|ㄹ", text))


def style_prepare(run: Path, item_id: str, field: str):
    if field not in FIELDS: raise ValueError("윤문 대상은 passage/explanation/commentary")
    draft = Draft.model_validate_json((run / "candidate.json").read_text())
    item = next((i for i in draft.items if i.id == item_id), None)
    if item is None: raise ValueError("문항 ID가 없습니다")
    if not re.fullmatch(r"[\w가-힣-]+", item_id): raise ValueError("파일 경로에 쓸 수 없는 문항 ID")
    folder = run / "style" / item_id / field
    folder.mkdir(parents=True, exist_ok=False)
    original = getattr(item, field)
    (folder / "01_input.txt").write_text(original)
    save(folder / "binding.json", {"item_id": item_id, "field": field,
                                   "candidate_sha256": hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest(),
                                   "protected_tokens": dict(protected_tokens(original))})
    command = [sys.executable, str(VENDOR / "scripts/prepare_monolith_input.py"), "--run-dir", str(folder.resolve()), "--genre", "report"]
    result = subprocess.run(command, capture_output=True, text=True)
    (folder / "prepare.log").write_text(result.stdout + result.stderr)
    if result.returncode: raise RuntimeError("im-not-ai 입력 분석 실패. prepare.log 확인")
    return {"folder": str(folder), "skill": str(VENDOR / "codex/skills/humanize-korean/SKILL.md"),
            "next": "Codex가 humanize-korean 스킬로 이 run의 final.md를 작성한 뒤 style-check를 실행"}


def style_check(folder: Path):
    before, after = folder / "01_input.txt", folder / "final.md"
    result = subprocess.run([sys.executable, str(VENDOR / "scripts/verify_gates.py"),
                             "--before", str(before.resolve()), "--after", str(after.resolve()), "--genre", "report", "--json"],
                            capture_output=True, text=True)
    (folder / "upstream-gate.txt").write_text(result.stdout + result.stderr)
    # Ignore upstream's own summary metadata when checking preserved exam tokens.
    body = re.split(r"<!--\s*HUMANIZE-SUMMARY\s*-->", after.read_text())[0]
    changed = protected_tokens(before.read_text()) != protected_tokens(body)
    report = {"upstream_exit": result.returncode, "protected_tokens_changed": changed,
              "can_consider": result.returncode == 0 and not changed,
              "semantic_verified": False, "next": "채택 전 의미 비교, check, 새 독립 풀이 필수"}
    save(folder / "haean-gate.json", report)
    return report
