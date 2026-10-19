"""Re-evaluate a saved pipeline revision without changing the source run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from .codex_runtime import CodexProvider
from .evaluation import Evaluation, PROTOCOL_VERSION, ROOT, frozen_fingerprint, harness_fingerprint
from .evaluation_input import build_evaluation_input
from .models import BlindReview, Draft, EditorialReview
from .pipeline import save


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _saved_binding(run, revision, draft, context, capture):
    """Check existing composition evidence; never create a retrospective seal."""
    path = run / f"composition-review-r{revision}.json"
    composition = any((run / name).exists() for name in
                      ("composition.json", "composition-binding.json", path.name))
    composition = composition or bool(context and "composition_context" in context)
    if not composition:
        return {"requirements": "unverified", "review": "unverified", "errors": []}, None
    from .composition_adapter import validate_bundle
    evidence = json.loads(capture("composition_review", path))
    if evidence.get("schema_version") != 1 or evidence.get("revision") != revision:
        raise ValueError("composition 저장 검토 버전 불일치")
    expected = evidence.get("inputs")
    errors = validate_bundle(run, expected, draft, verify_runtime=False)
    for name, ref in expected.items():
        capture("composition_" + name, Path(ref["path"]), ref["sha256"])
    binding = json.loads((run / "composition-binding.json").read_bytes())
    for name, ref in binding["files"].items():
        capture("composition_input_" + name, Path(ref["path"]), ref["sha256"])
    for name, filename in (("draft", f"draft-r{revision}.json"), ("review", f"review-r{revision}.json")):
        ref = evidence.get(name, {})
        if ref.get("path") != str(run / filename):
            raise ValueError("composition 검토가 다른 버전 파일을 가리킵니다")
        capture("bound_" + name, run / filename, ref.get("sha256", ""))
    if Draft.model_validate_json((run / f"draft-r{revision}.json").read_bytes()) != draft:
        raise ValueError("composition 저장 검토와 선택 초안 불일치")
    return {"requirements": "composition_binding", "review": "composition_revision_binding",
            "errors": errors, "generation_runtime_matches_current": "not_required_for_archived_evaluation",
            "assurance": "local change detection; not reviewer identity or quality proof"}, expected


def evaluate_run(run: Path, out: Path, *, revision=None, model="gpt-6-astra", provider=None):
    """One diagnostic evaluation, not a new generation, review, or approval.

    ``revision=None`` selects the current candidate and its saved revision review.
    Explicit revision selects the archived draft and review. Missing or malformed
    source metadata fails before output creation/model use. Results never update
    the source's review state, including later feedback requesting revision.
    """
    run, out = Path(run).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(run):
        raise ValueError("재평가 결과는 원 run 밖의 새 경로에 저장하세요")
    if revision is not None and (type(revision) is not int or revision < 0):
        raise ValueError("revision은 0 이상의 정수여야 합니다")
    sources, hashes, contents = {}, {}, {}

    def capture(name, path, expected=None, *, optional=False):
        data = path.read_bytes() if path.is_file() else None
        sha = hashlib.sha256(data).hexdigest() if data is not None else None
        if (data is None and not optional) or (expected is not None and sha != expected):
            raise ValueError("저장된 원 입력·검토 해시 불일치 또는 파일 누락: " + name)
        sources[name], hashes[name], contents[name] = path, sha, data
        return data

    status = json.loads(capture("status", run / "status.json"))
    current = revision is None
    selected = status.get("revision") if current else revision
    if type(selected) is not int or selected < 0:
        raise ValueError("자동 파이프라인의 revision 기록이 필요합니다")
    draft_path = run / ("candidate.json" if current else f"draft-r{selected}.json")
    review_path = run / f"review-r{selected}.json"
    brief = json.loads(capture("brief", run / "brief.json"))
    context_bytes = capture("context", run / "context.json", optional=True)
    context = json.loads(context_bytes) if context_bytes is not None else None
    draft = Draft.model_validate_json(capture("draft", draft_path))
    review = json.loads(capture("review", review_path))
    if review.get("revision") != selected or type(review.get("revision")) is not int:
        raise ValueError("선택한 draft와 review의 revision이 다릅니다")
    if not isinstance(review.get("errors"), list) or not all(isinstance(e, str) for e in review["errors"]):
        raise ValueError("저장된 검토 오류 목록이 올바르지 않습니다")
    blind = BlindReview.model_validate(review.get("blind"))
    editorial = EditorialReview.model_validate(review.get("editorial"))
    ids = [item.id for item in draft.items]
    if len(blind.solutions) != len(ids) or {s.item_id for s in blind.solutions} != set(ids):
        raise ValueError("선택한 문항과 독립 풀이 ID가 다릅니다")
    for r in (blind, editorial):
        for issue in r.issues:
            issue_ids = [part.strip() for part in issue.item_id.split(",")]
            if len(set(issue_ids)) != len(issue_ids) or any(item_id not in ids for item_id in issue_ids):
                raise ValueError("저장된 검토에 알 수 없는 문항 ID 또는 중복·빈 ID가 있습니다")
    if current:
        archived = run / f"draft-r{selected}.json"
        archived_bytes = capture("revision_draft", archived)
        if (status.get("candidate_sha256") != hashes["draft"] or
                Draft.model_validate_json(archived_bytes) != draft):
            raise ValueError("현재 candidate와 검토 버전이 다릅니다")
    provenance, composition = _saved_binding(run, selected, draft, context, capture)
    payload = build_evaluation_input(brief, draft, review, context)
    from .review_evidence import json_sha256
    frozen = frozen_fingerprint(sources["brief"])
    harness = harness_fingerprint()
    rubric = (ROOT / "evals/rubric.md").read_text()
    # Missing context is also an input fact; creating it during evaluation is a change.
    def verify():
        if {name: _sha(path) for name, path in sources.items()} != hashes:
            raise ValueError("재평가 중 원 입력이 바뀌었습니다. 원 응답을 보존하고 새 결과 경로로 다시 평가하세요")
        if frozen_fingerprint(sources["brief"]) != frozen or harness_fingerprint() != harness:
            raise ValueError("재평가 중 코드/평가 기준이 바뀌었습니다")
        if composition is not None:
            from .composition_adapter import validate_bundle
            if validate_bundle(run, composition, draft, verify_runtime=False) != provenance["errors"]:
                raise ValueError("재평가 중 composition 검증 결과가 바뀌었습니다")

    verify()
    out.mkdir(parents=True, exist_ok=False)
    evidence = out / "inputs"
    evidence.mkdir()
    for name, data in contents.items():
        if data is not None:
            (evidence / f"{name}.json").write_bytes(data)
    save(out / "evaluation-input.json", payload)
    (out / "rubric.md").write_text(rubric)
    save(out / "evaluation.schema.json", Evaluation.model_json_schema())
    from .execution_provenance import capture as capture_execution, verify as verify_execution
    execution = capture_execution(out / "execution", inputs={
        "evaluation-input.json": out / "evaluation-input.json", "rubric.md": out / "rubric.md",
        "protocol.md": ROOT / "evals/protocol.md"}, instructions={"evaluate": rubric},
        schemas={"evaluate": Evaluation.model_json_schema()},
        parameters={"mode": "saved-revision-reevaluation", "requested_model": model,
                    "actual_model": None, "max_calls": 1, "generation_calls": 0, "retry": False})
    result = {"evaluation_protocol": PROTOCOL_VERSION, "mode": "saved-revision-reevaluation",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "run": str(run), "selected_revision": selected, "selected_current": current,
              "requested_model": model, "actual_model": None,
              "codex_version": subprocess.run(["codex", "--version"], capture_output=True, text=True).stdout.strip(),
              "sources": {name: {"path": str(path), "sha256": hashes[name]} for name, path in sources.items()},
              "frozen": frozen, "harness": harness, "input_contract_version": payload["input_contract_version"],
              "requirements_source": payload["requirements_source"], "source_state_at_start": status.get("state"),
              "requirements_sha256": json_sha256({"brief": payload["brief"],
                  "item_requirements": payload["item_requirements"],
                  "input_contract_version": payload["input_contract_version"],
                  "requirements_policy": payload["requirements_policy"]}),
              "saved_provenance": provenance,
              "execution_manifest": {"path": str(execution), "sha256": _sha(execution)},
              "generation_calls": 0, "expert_verified": False, "human_approved": False,
              "native_layout_verified": False, "release_approved": False, "complete": False,
              "later_feedback_included": False,
              "note": "저장된 revision 검토만 평가합니다. 후속 피드백·배포 가능 여부를 대체하거나 원 상태를 갱신하지 않습니다."}
    save(out / "result.json", result)
    caller = provider if provider is not None else CodexProvider(model, max_calls=1, timeout=1200, trace_dir=out / "codex-traces")
    try:
        verify()
        if not verify_execution(execution, expected_sha256=result["execution_manifest"]["sha256"])["valid"]:
            raise ValueError("평가 실행 스냅샷이 바뀌었습니다")
        evaluated = caller.call("evaluate", rubric, payload, Evaluation)
        save(out / "evaluation.json", evaluated.model_dump())
        verify()
        if not verify_execution(execution, expected_sha256=result["execution_manifest"]["sha256"])["valid"]:
            raise ValueError("평가 실행 스냅샷이 바뀌었습니다")
        if len(evaluated.items) != len(ids) or {i.item_id for i in evaluated.items} != set(ids):
            raise ValueError("평가 문항 누락·중복")
        model_eligible = not review["errors"] and all(not i.fatal_errors and next(
            d.score for d in i.dimensions if d.name == "validity") >= 3 for i in evaluated.items)
        result.update(complete=True, state="evaluated", model_eligible=model_eligible,
            eligible=model_eligible and provenance["review"] != "unverified" and not provenance["errors"],
            quality=sum(d.score for i in evaluated.items for d in i.dimensions) / (8 * len(evaluated.items)),
            fatal_count=sum(len(i.fatal_errors) for i in evaluated.items), errors=review["errors"],
            dimensions={d.name: sum(x.score for i in evaluated.items for x in i.dimensions if x.name == d.name)
                        / len(evaluated.items) for d in evaluated.items[0].dimensions})
    except Exception as exc:
        result.update(state="failed", eligible=False, quality=None, error=f"{type(exc).__name__}: {exc}")
    result["usage"] = getattr(caller, "usage", [])
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["attempted_calls"] = getattr(caller, "calls", None)
    save(out / "result.json", result)
    return result
