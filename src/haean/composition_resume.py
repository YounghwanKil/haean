"""Resume sealed composition bundles only after validating every source job."""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import re

from . import composition_adapter as adapter
from .codex_runtime import CodexProvider
from .corpus import Corpus
from .full_exam import assemble, brief_difficulty, load_plan
from .models import Brief, Draft, BlindReview, EditorialReview
from .pipeline import prepare, run_pipeline, save, writer_prompt
from .revision_feedback import load_revision_feedback, requires_revision


def _read(path):
    return json.loads(Path(path).read_text())


def _revision(path, prefix):
    match = re.fullmatch(rf"{prefix}-r(0|[1-9][0-9]*)\.json", path.name)
    if not match:
        raise ValueError("composition 재개 revision 파일명 불일치")
    return int(match[1])


def _review(run, expected, draft_path, review_path):
    """A review is usable only with the receipt for this exact saved draft."""
    revision = _revision(draft_path, "draft")
    if review_path != run / f"review-r{revision}.json":
        raise ValueError("composition 재개 검토 경로 불일치")
    receipt = _read(run / f"composition-review-r{revision}.json")
    if (receipt.get("schema_version") != 1 or receipt.get("inputs") != expected
            or type(receipt.get("revision")) is not int or receipt["revision"] != revision):
        raise ValueError("composition 재개 검토 receipt 입력·revision 불일치")
    for key, path in (("draft", draft_path), ("review", review_path)):
        if adapter._verify_ref(receipt.get(key), key) != path:
            raise ValueError("composition 재개 검토 receipt 경로 불일치")
    review = _read(review_path)
    if (type(review.get("revision")) is not int or review["revision"] != revision
            or not isinstance(review.get("errors"), list)
            or any(not isinstance(error, str) for error in review["errors"])
            or not isinstance(review.get("similarity_hits"), list)):
        raise ValueError("composition 재개 검토 내용·revision 불일치")
    BlindReview.model_validate(review.get("blind"))
    EditorialReview.model_validate(review.get("editorial"))
    return review


def _seed(run, expected, context, group, state):
    paths = list(run.glob("draft-r*.json"))
    for prefix in ("draft", "review", "composition-review"):
        for path in run.glob(f"{prefix}-r*.json"):
            _revision(path, prefix)
    candidate = run / "candidate.json"
    if state["state"] == "needs_revision" and not candidate.exists():
        raise ValueError("composition 검토된 후보 원본 누락")
    if candidate.exists():
        candidate_sha = adapter._sha(candidate)
        if (state.get("candidate_sha256") is not None and state["candidate_sha256"] != candidate_sha
                or state["state"] == "needs_revision" and state.get("candidate_sha256") != candidate_sha):
            raise ValueError("composition 검토된 후보 해시 불일치")
        # A failed later review may leave an older, already reviewed candidate.
        # Verify that older receipt without demanding a receipt for the latest draft.
        matches = [path for path in paths if adapter._sha(path) == candidate_sha
                   and (run / f"review-r{_revision(path, 'draft')}.json").exists()]
        if state.get("revision") is not None:
            if type(state["revision"]) is not int:
                raise ValueError("composition 후보 revision 불일치")
            matches = [path for path in matches if _revision(path, "draft") == state["revision"]]
        if not matches:
            raise ValueError("composition 후보의 검토 초안·receipt 누락")
        reviewed_path = max(matches, key=lambda path: _revision(path, "draft"))
        _review(run, expected, reviewed_path, run / f"review-r{_revision(reviewed_path, 'draft')}.json")
    if paths:
        path = max(paths, key=lambda p: _revision(p, "draft"))
        revision = _revision(path, "draft")
        review_path = run / f"review-r{revision}.json"
        if any(_revision(p, "review") > revision for p in run.glob("review-r*.json")):
            raise ValueError("composition 초안 없는 후속 검토")
        review = _review(run, expected, path, review_path) if review_path.exists() else None
        if not review_path.exists() and (run / f"composition-review-r{revision}.json").exists():
            raise ValueError("composition 검토 receipt의 검토 원본 누락")
        lineage = {"seed_path": str(path), "seed_sha256": adapter._sha(path),
                   "review_path": str(review_path) if review is not None else None,
                   "review_sha256": adapter._sha(review_path) if review is not None else None,
                   "seed_composition": expected}
        seed = Draft.model_validate_json(path.read_text())
    elif ((run / "inherited-draft.json").exists()
          or isinstance(context.get("resume_lineage"), dict) and context["resume_lineage"].get("seed_path")):
        if list(run.glob("review-r*.json")) or list(run.glob("composition-review-r*.json")):
            raise ValueError("composition 검토 원본 초안 누락")
        lineage = context.get("resume_lineage")
        if not isinstance(lineage, dict):
            raise ValueError("composition 상속 초안의 봉인된 lineage 누락")
        path = adapter._verify_ref({"path": lineage.get("seed_path"), "sha256": lineage.get("seed_sha256")}, "원본 seed")
        origin = path.parent
        _revision(path, "draft")  # Flattened lineage always points to a real revision.
        origin_expected = lineage.get("seed_composition")
        adapter.validate_bundle(origin, origin_expected)
        if (origin_expected["packet"] != expected["packet"]
                or origin_expected["plan"]["sha256"] != expected["plan"]["sha256"]
                or _read(origin / "composition.json")["assignment"] != group):
            raise ValueError("composition 상속 초안 원본 배정 불일치")
        seed = Draft.model_validate_json(path.read_text())
        inherited = run / "inherited-draft.json"
        if inherited.exists() and seed != Draft.model_validate_json(inherited.read_text()):
            raise ValueError("composition 상속 초안과 원본 의미 불일치")
        inherited_review = run / "inherited-review.json"
        review = None
        if lineage.get("review_path") is not None:
            review_path = adapter._verify_ref({"path": lineage["review_path"],
                                               "sha256": lineage.get("review_sha256")}, "원본 review")
            review = _review(origin, origin_expected, path, review_path)
            if inherited_review.exists() and _read(inherited_review) != review:
                raise ValueError("composition 상속 검토와 원본 의미 불일치")
        elif inherited_review.exists() or lineage.get("review_sha256") is not None:
            raise ValueError("composition 상속 검토 원본 연결 누락")
        lineage = {key: lineage[key] for key in
                   ("seed_path", "seed_sha256", "review_path", "review_sha256", "seed_composition")}
    else:
        if ((run / "candidate.json").exists() or (run / "inherited-review.json").exists()
                or list(run.glob("review-r*.json")) or list(run.glob("composition-review-r*.json"))):
            raise ValueError("composition 검토·후보만 있고 초안 이력이 없습니다")
        return None, None, {"seed_path": None, "seed_sha256": None,
                            "review_path": None, "review_sha256": None, "seed_composition": None}
    if [item.id for item in seed.items] != [slot["id"] for slot in group]:
        raise ValueError("composition 재개 초안 ID·순서 불일치")
    return seed.model_dump(), review, lineage


def preflight(previous):
    """Read all inputs before making an output directory or creating a provider."""
    previous = Path(previous).resolve()
    try:
        production = _read(previous / "production.json")
        declaration = production.get("composition")
        if not isinstance(declaration, dict) or set(declaration) != {"packet", "plan_sha256"}:
            raise ValueError("composition 회차 선언 누락·불완전")
        packet_path = adapter._verify_ref(declaration["packet"], "production packet")
        plan_bytes = (previous / "plan.json").read_bytes()
        if adapter._sha(previous / "plan.json") != declaration["plan_sha256"]:
            raise ValueError("composition 재개 plan 원문 해시 불일치")
        adapter.load_packet(packet_path, previous / "plan.json")
        plan = load_plan(previous / "plan.json")
        if any(production.get(key) != plan[key] for key in ("exam", "subject")) or production.get("total") != len(plan["slots"]):
            raise ValueError("composition 회차 명세 불일치")
        jobs = production.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("composition 재개 묶음 누락")
        slot_map = {slot["id"]: slot for slot in plan["slots"]}
        seen, runs, entries, shared = set(), set(), [], defaultdict(set)
        for index, job in enumerate(jobs):
            ids = job.get("ids")
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 4 or
                    any(not isinstance(i, str) or i not in slot_map or i in seen for i in ids)
                    or len(set(ids)) != len(ids)):
                raise ValueError("composition 재개 배정 ID 중복·누락")
            group = [slot_map[i] for i in ids]
            if job.get("slots") != [slot["number"] for slot in group]:
                raise ValueError("composition 재개 배정 ID·번호·순서 불일치")
            seen.update(ids)
            run = Path(job["run"]).resolve()
            if run in runs:
                raise ValueError("composition 재개 run 중복")
            runs.add(run)
            expected = job.get("composition")
            adapter.validate_bundle(run, expected)
            if (expected["packet"] != declaration["packet"]
                    or expected["plan"]["sha256"] != declaration["plan_sha256"]
                    or _read(run / "composition.json")["assignment"] != group):
                raise ValueError("composition 회차·묶음 배정 불일치")
            for slot in group:
                if slot.get("shared_passage_id"):
                    shared[slot["shared_passage_id"]].add(index)
            context, state = _read(run / "context.json"), _read(run / "status.json")
            if state.get("state") not in {"prepared", "failed", "needs_revision", "awaiting_human_review"}:
                raise ValueError("composition 재개 상태 불일치")
            ready = state["state"] == "awaiting_human_review"
            seed, review, lineage = None, None, None
            revision_feedback = None
            if ready:
                candidate_path = run / "candidate.json"
                candidate = Draft.model_validate_json(candidate_path.read_text())
                if state.get("candidate_sha256") != adapter._sha(candidate_path):
                    raise ValueError("composition 기존 검토 후보 해시 불일치")
                errors = adapter.assembly_errors(run, expected, candidate, state)
                if errors:
                    raise ValueError("; ".join(errors))
                revision_feedback = load_revision_feedback(run, candidate)
                ready = not requires_revision(revision_feedback)
            if not ready:
                seed, review, lineage = _seed(run, expected, context, group, state)
                revision_feedback = load_revision_feedback(run, seed)
                if revision_feedback is not None:
                    lineage["revision_feedback"] = revision_feedback
            entries.append({"job": job, "run": run, "group": group, "state": state,
                            "context": context, "ready": ready, "seed": seed,
                            "review": review, "lineage": lineage, "revision_feedback": revision_feedback})
        if seen != set(slot_map) or any(len(owners) != 1 for owners in shared.values()):
            raise ValueError("composition 재개 ID 누락·공통지문 묶음 분리")
        return plan, plan_bytes, declaration, entries
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"composition 재개 입력 불완전: {exc}") from exc


def resume_composition(previous, db, out, *, workers, max_revisions, model, replacements=(),
                       compact_reference_audit=False):
    if type(compact_reference_audit) is not bool:
        raise ValueError("compact_reference_audit must be bool")
    if replacements:
        raise ValueError("composition 재개는 대체 묶음 replacements를 지원하지 않습니다")
    original_inputs = preflight(previous)
    plan, plan_bytes, declaration, entries = original_inputs
    out, previous = Path(out).resolve(), Path(previous).resolve()
    if out.exists():
        raise ValueError("새 재개 출력 경로가 필요합니다. 기존 기록을 보존합니다")
    out.mkdir(parents=True)
    (out / "plan.json").write_bytes(plan_bytes)
    from .evaluation import harness_fingerprint
    save(out / "provenance.json", {"mode": "resumed-composition-production", "model": model,
         "parent": str(previous), "parent_manifest_sha256": adapter._sha(previous / "production.json"),
         "plan_sha256": declaration["plan_sha256"], "harness": harness_fingerprint(),
         "max_revisions": max_revisions, "humanizer": "not_applied", "expert_verified": False,
         "compact_reference_audit": compact_reference_audit})
    jobs, seeds = [], {}
    corpus = Corpus(db) if any(not entry["ready"] for entry in entries) else None
    for entry in entries:
        source, parent, group = entry["job"], entry["run"], entry["group"]
        if entry["ready"]:
            jobs.append({**source, "bundle": len(jobs) + 1, "state": "awaiting_human_review", "reused": True})
            continue
        brief = Brief(exam=plan["exam"], subject=plan["subject"], item_type=group[0]["item_type"],
                      topic=" / ".join(slot["topic"] for slot in group), count=len(group),
                      difficulty=brief_difficulty(group), shared_passage=bool(group[0].get("shared_passage_id")))
        run = prepare(corpus, brief, out / "bundles").resolve()
        context = _read(run / "context.json")
        # Preserve old references and authoring context even when generation never started.
        context.update({key: value for key, value in entry["context"].items()
                        if key not in {"brief", "exam_assignment", "composition_context", "resume_lineage"}})
        context["exam_assignment"] = group
        context["resume_lineage"] = {"parent": str(parent), "parent_state": entry["state"]["state"], **entry["lineage"]}
        save(run / "context.json", context)
        save(run / "lineage.json", context["resume_lineage"])
        save(run / "retrieval.json", context["retrieval"])
        if "editorial_plan" in context:
            save(run / "editorial-plan.json", context["editorial_plan"])
        provenance = _read(run / "provenance.json")
        provenance["source_ids"] = [ref["id"] for ref in context["references"]]
        save(run / "provenance.json", provenance)
        (run / "request.md").write_text(writer_prompt(brief) + "\n\n입력 자료(JSON):\n" + json.dumps(context, ensure_ascii=False, indent=2))
        expected = adapter.attach_bundle(run, plan_path=out / "plan.json", packet_path=declaration["packet"]["path"], slots=group)
        jobs.append({"bundle": len(jobs) + 1, "run": str(run), "ids": source["ids"], "slots": source["slots"],
                     "state": "prepared", "parent_run": str(parent), "reused": False, "composition": expected})
        seeds[str(run)] = entry["seed"], entry["review"], entry["revision_feedback"]
    manifest = {"exam": plan["exam"], "subject": plan["subject"], "total": len(plan["slots"]), "jobs": jobs,
                "complete": False, "human_approved": False, "parent": str(previous), "composition": declaration}
    save(out / "production.json", manifest)

    def verify_parent():
        # Preparation and model execution can be long. Recheck the original
        # candidate/seed/review lineage, not just the newly attached sidecar.
        if preflight(previous) != original_inputs:
            raise ValueError("composition 재개 중 원본 입력·검토 변경")

    def work(job):
        run = Path(job["run"])
        try:
            callbacks = adapter.pipeline_callbacks(run, job["composition"])
            original_validate = callbacks["additional_validation"]
            original_after_review = callbacks["after_review_saved"]

            def validate(draft):
                verify_parent()
                return original_validate(draft)

            def after_review(path, review):
                verify_parent()
                return original_after_review(path, review)

            callbacks.update(additional_validation=validate, after_review_saved=after_review)
            if compact_reference_audit:
                callbacks["compact_reference_audit"] = True
            verify_parent()
            provider = CodexProvider(model, max_calls=4 + 3 * max_revisions, timeout=1200, trace_dir=run / "codex-traces")
            seed, review, revision_feedback = seeds[str(run)]
            run_pipeline(run, provider, max_revisions, initial_draft=seed, initial_review=review,
                         revision_feedback=revision_feedback, **callbacks)
            state = _read(run / "status.json")
            return {**job, "state": state["state"], "errors": state.get("errors", [])}
        except Exception as exc:
            save(run / "status.json", {"state": "failed", "human_approved": False, "error": f"{type(exc).__name__}: {exc}"})
            return {**job, "state": "failed", "error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(work, job): index for index, job in enumerate(jobs) if not job["reused"]}
        for future in as_completed(pending):
            manifest["jobs"][pending[future]] = future.result()
            save(out / "production.json", manifest)
    manifest["complete"] = all(job["state"] == "awaiting_human_review" for job in manifest["jobs"])
    save(out / "production.json", manifest)
    return assemble(out)
