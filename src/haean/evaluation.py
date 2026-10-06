from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field, model_validator
from .models import StrictModel, Brief, Draft
from .pipeline import prepare, run_pipeline, save
from .codex_runtime import CodexProvider
from .corpus import Corpus

ROOT = Path(__file__).resolve().parents[2]
DIMENSIONS = {"validity", "exam_fit", "reasoning_value", "distractors", "language", "explanation", "originality", "workload"}


class Dimension(StrictModel):
    name: Literal["validity", "exam_fit", "reasoning_value", "distractors", "language", "explanation", "originality", "workload"]
    score: int = Field(ge=0, le=4)
    evidence: str = Field(min_length=1)


class ItemEvaluation(StrictModel):
    item_id: str
    dimensions: list[Dimension]
    fatal_errors: list[str]
    missing_evidence: list[str]
    expert_verified: Literal[False]

    @model_validator(mode="after")
    def complete(self):
        if len(self.dimensions) != 8 or {d.name for d in self.dimensions} != DIMENSIONS:
            raise ValueError("8개 평가 차원을 중복 없이 채워야 합니다")
        return self


class Evaluation(StrictModel):
    items: list[ItemEvaluation]
    summary: str


def fingerprint(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


def harness_fingerprint():
    return fingerprint([*ROOT.glob("skills/**/*.md"), *ROOT.glob(".codex/agents/*.toml"),
                        *ROOT.glob("src/haean/*.py"), *ROOT.glob("src/haean/prompts/*.md")])


def frozen_fingerprint(suite: Path):
    paths = [ROOT / "evals/protocol.md", ROOT / "evals/rubric.md", Path(__file__), suite.resolve()]
    # External private suites are fingerprinted without copying their contents.
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def evaluate_suite(corpus: Corpus, suite_path: Path, out: Path, case_ids=None,
                   repeats=1, max_revisions=1, model="gpt-6-astra"):
    if out.exists(): raise ValueError("실험 결과 디렉터리는 새 경로를 사용하세요")
    if not 1 <= repeats <= 5: raise ValueError("repeats는 1–5")
    suite = json.loads(suite_path.read_text())
    cases = [c for c in suite["cases"] if not case_ids or c["id"] in case_ids]
    if not cases or (case_ids and set(case_ids) - {c["id"] for c in cases}): raise ValueError("평가 과제 ID를 확인하세요")
    if len({c["id"] for c in cases}) != len(cases): raise ValueError("과제 ID 중복")
    out.mkdir(parents=True)
    lock = frozen_fingerprint(suite_path)
    harness = harness_fingerprint()
    manifest = {"suite": suite["version"], "split": suite["split"], "cases": [c["id"] for c in cases],
                "model": model, "repeats": repeats, "max_revisions": max_revisions,
                "mode": "codex-prompt-pipeline", "humanizer": "not_applied", "expert_calibrated": False,
                "codex_version": subprocess.run(["codex", "--version"], capture_output=True, text=True).stdout.strip(),
                "frozen": lock, "harness": harness, "results": []}
    save(out / "results.json", manifest)
    for case in cases:
        for repeat in range(repeats):
            if frozen_fingerprint(suite_path) != lock or harness_fingerprint() != harness:
                raise ValueError("평가 중 코드/평가 기준이 바뀌었습니다. 새 실험으로 재실행하세요")
            run = prepare(corpus, Brief.model_validate(case["brief"]), out / "runs")
            row = {"case_id": case["id"], "group": case["group"], "repeat": repeat, "run": str(run),
                   "exam": case["brief"]["exam"], "subject": case["brief"]["subject"]}
            provider = CodexProvider(model, max_calls=14, trace_dir=run / "codex-traces")
            try:
                draft = run_pipeline(run, provider, max_revisions)
                status = json.loads((run / "status.json").read_text())
                review = json.loads((run / f"review-r{status['revision']}.json").read_text())
                result = provider.call("evaluate", (ROOT / "evals/rubric.md").read_text(),
                                       {"brief": case["brief"], "draft": draft.model_dump(), "review": review}, Evaluation)
                if {i.item_id for i in result.items} != {i.id for i in draft.items} or len(result.items) != len(draft.items):
                    raise ValueError("평가 문항 누락·중복")
                save(run / "evaluation.json", result.model_dump())
                row.update(state=status["state"], eligible=not status["errors"] and all(
                    not i.fatal_errors and next(d.score for d in i.dimensions if d.name == "validity") >= 3 for i in result.items),
                    quality=sum(d.score for i in result.items for d in i.dimensions) / (8 * len(result.items)),
                    fatal_count=sum(len(i.fatal_errors) for i in result.items), errors=status["errors"],
                    dimensions={d.name: sum(x.score for i in result.items for x in i.dimensions if x.name == d.name) / len(result.items)
                                for d in result.items[0].dimensions})
            except Exception as exc:
                row.update(state="failed", eligible=False, quality=None, fatal_count=None, error=f"{type(exc).__name__}: {exc}")
            save(run / "usage.json", provider.usage)
            row["usage"] = provider.usage
            manifest["results"].append(row)
            save(out / "results.json", manifest)
    manifest["complete"] = len(manifest["results"]) == len(cases) * repeats and all(r["state"] != "failed" for r in manifest["results"])
    save(out / "results.json", manifest)
    return manifest


def compare(baseline: dict, candidate: dict):
    for field in ("suite", "split", "model", "repeats", "max_revisions", "mode", "humanizer", "frozen"):
        if baseline.get(field) != candidate.get(field): raise ValueError("동일 조건이 아닙니다: " + field)
    index = lambda x: {(r["case_id"], r["repeat"]): r for r in x["results"]}
    a, b = index(baseline), index(candidate)
    if not a or a.keys() != b.keys() or len(a) != len(baseline["results"]) or len(b) != len(candidate["results"]):
        raise ValueError("동일 과제·반복의 중복 없는 결과가 필요합니다")
    if not baseline.get("complete") or not candidate.get("complete"):
        return {"decision": "inconclusive", "reason": "실행 실패/미완료가 있습니다. 실패를 제외해 평균을 내지 않습니다."}
    changes = [{"case_id": k[0], "repeat": k[1], "quality_delta": b[k]["quality"] - a[k]["quality"],
                "baseline_eligible": a[k]["eligible"], "candidate_eligible": b[k]["eligible"],
                "regression": (a[k]["eligible"] and not b[k]["eligible"]) or b[k]["fatal_count"] > a[k]["fatal_count"]} for k in a]
    strata = {}
    for k in a:
        label = b[k]["exam"] + "/" + b[k]["subject"]
        strata.setdefault(label, []).append(b[k]["quality"] - a[k]["quality"])
    regressions = any(c["regression"] for c in changes) or any(sum(ds) < 0 for ds in strata.values())
    improved = any(c["quality_delta"] > 0 or (not c["baseline_eligible"] and c["candidate_eligible"]) for c in changes)
    return {"decision": "reject_regression" if regressions else "candidate_signal" if improved else "no_improvement",
            "pairs": changes, "stratum_mean_delta": {k: sum(v)/len(v) for k,v in strata.items()},
            "auto_promoted": False, "expert_verified": False,
            "note": "짝지은 모델 평가 신호. 전문가 교정·봉인 평가·충분한 반복 전 성능 향상 확정 아님."}


def experiment(name: str, baseline_path: Path):
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", name): raise ValueError("실험명은 영문 소문자·숫자·하이픈")
    baseline = json.loads(baseline_path.read_text())
    if not baseline.get("complete"): raise ValueError("완료된 baseline 평가가 필요합니다")
    out = ROOT / "experiments" / name
    out.mkdir(parents=True, exist_ok=False)
    save(out / "baseline.json", baseline)
    save(out / "lock.json", {"frozen": baseline["frozen"], "baseline_harness": baseline["harness"],
                             "allowed": ["skills/", "src/haean/prompts/", "src/haean/corpus.py", "src/haean/pipeline.py"],
                             "forbidden": ["evals/", "src/haean/evaluation.py", "holdout/", "기존 결과"]})
    (out / "proposal.md").write_text("# 개선 가설\n\n실패 문항과 실행 단계:\n\n원인 가설:\n\n변경 대상과 이유:\n\n예상 퇴행과 검증:\n", encoding="utf-8")
    return {"experiment": str(out), "state": "proposal_pending"}
