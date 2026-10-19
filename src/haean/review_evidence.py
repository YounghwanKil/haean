"""Bind review results to a prepared input; external reviews remain attestations.

There is deliberately no command to attach today's binding to an old raw result.
The reviewer receives the binding before reviewing and returns it with the result.
Result digests are computed by the runner, not requested from the model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .models import Brief, Draft, BlindReview, EditorialReview
from .validation import public_item


SCHEMAS = {"blind": BlindReview, "editor": EditorialReview}
REQUEST_FILE = "review-request.json"
EDITOR_REQUEST_FILE = "editor-review-request.json"


def json_sha256(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preserve_review_files(run, names):
    """Keep prior manual packets/results before replacing their current pointers."""
    run = Path(run)
    previous = {name: (run / name).read_bytes() for name in names if (run / name).is_file()}
    if previous:
        history = run / "review-history" / uuid4().hex
        history.mkdir(parents=True, exist_ok=False)
        for name, data in previous.items():
            (history / name).write_bytes(data)


def _template(binding):
    return {"result": None, "evidence": {"input_binding": binding,
            "producer": {"execution_mode": "external-attestation", "reviewer": "",
                         "requested_model": None, "actual_model": None}}}


def invalidate_editor_review(run):
    from .pipeline import save
    run = Path(run)
    status_path = run / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    preserve_review_files(run, [EDITOR_REQUEST_FILE, "editorial-review-template.json",
                               "editorial-review.schema.json", "editorial-result.json", "manual-review.json", "status.json"])
    # Invalidate prior approval before changing any active editor packet. A
    # failure halfway through preparation must still leave review pending.
    status.pop("editor_preparation_id", None)
    save(status_path, {**status, "state": "awaiting_independent_review", "pending_review": "editor",
                       "human_approved": False})
    pending = {"state": "editor_prepare_required",
               "next_command": "editor-prepare RUN --blind PATH",
               "note": "독립 풀이를 먼저 고정한 뒤 새 편집 검토 템플릿을 받으세요."}
    save(run / EDITOR_REQUEST_FILE, pending)
    save(run / "editorial-review-template.json", pending)
    save(run / "editorial-review.schema.json", {"not": {}, "description": pending["note"]})


def review_inputs(run):
    """Use the same brief as manual check and reject contradictory duplicate files."""
    run = Path(run)
    context = json.loads((run / "context.json").read_text())
    brief = Brief.model_validate(context["brief"])
    if (run / "brief.json").exists():
        separate = Brief.model_validate_json((run / "brief.json").read_text())
        if separate != brief:
            raise ValueError("review_specification_mismatch: brief.json과 context.brief가 다릅니다")
    draft = Draft.model_validate_json((run / "candidate.json").read_text())
    return brief, draft, {"items": [public_item(item) for item in draft.items]}


def _bindings(run, request_id):
    from .pipeline import review_prompt
    brief, _, public = review_inputs(run)
    result = {}
    for role, schema in SCHEMAS.items():
        specification = ({"exam": brief.exam, "subject": brief.subject}
                         if role == "blind" else {
                             "brief": brief.model_dump(),
                             "context": json.loads((Path(run) / "context.json").read_text()),
                         })
        result[role] = {
            "version": 1, "request_id": request_id, "role": role,
            "input_kind": "student-public-json" if role == "blind" else "candidate-file-bytes",
            "input_sha256": json_sha256(public) if role == "blind" else file_sha256(Path(run) / "candidate.json"),
            "instructions_sha256": hashlib.sha256(review_prompt(role, brief).encode("utf-8")).hexdigest(),
            "specification_sha256": json_sha256(specification),
            "result_schema_sha256": json_sha256(schema.model_json_schema()),
        }
    return result


def envelope_schema(role, binding):
    schema = SCHEMAS[role].model_json_schema()
    definitions = schema.pop("$defs", {})
    result = {
        "type": "object", "additionalProperties": False,
        "required": ["result", "evidence"],
        "properties": {
            "result": schema,
            "evidence": {
                "type": "object", "additionalProperties": False,
                "required": ["input_binding", "producer"],
                "properties": {
                    "input_binding": {"const": binding},
                    "producer": {
                        "type": "object", "additionalProperties": False,
                        "required": ["execution_mode", "reviewer", "requested_model", "actual_model"],
                        "properties": {
                            "execution_mode": {"const": "external-attestation"},
                            "reviewer": {"type": "string", "minLength": 1},
                            "requested_model": {"type": ["string", "null"]},
                            "actual_model": {"type": ["string", "null"]},
                        },
                    },
                },
            },
        },
    }
    if definitions:
        result["$defs"] = definitions
    return result


def prepare_review_request(run):
    """Called only by explicit check. Every import requires fresh review bindings."""
    from .pipeline import save
    run = Path(run)
    bindings = _bindings(run, uuid4().hex)
    preserve_review_files(run, [REQUEST_FILE, "blind-review-template.json", "blind-review.schema.json",
                               "blind-result.json", "blind-usage.json"])
    invalidate_editor_review(run)
    save(run / REQUEST_FILE, {"candidate_sha256": file_sha256(run / "candidate.json"),
                              "bindings": bindings})
    save(run / "blind-review-template.json", _template(bindings["blind"]))
    save(run / "blind-review.schema.json", envelope_schema("blind", bindings["blind"]))
    return bindings


def _current_base_binding(run, role):
    if role not in SCHEMAS:
        raise ValueError("지원되지 않는 검토 역할")
    run = Path(run)
    if not (run / REQUEST_FILE).exists():
        raise ValueError("legacy_missing_review_evidence: 기존 결과를 자동 포장하지 않습니다. 새 check와 독립 검토가 필요합니다")
    request = json.loads((run / REQUEST_FILE).read_text())
    stored = request.get("bindings", {}).get(role)
    if not isinstance(stored, dict) or not isinstance(stored.get("request_id"), str) or not stored["request_id"]:
        raise ValueError("invalid_review_binding: 검토 요청 기록이 불완전합니다")
    if request.get("candidate_sha256") != file_sha256(run / "candidate.json"):
        raise ValueError("review_binding_changed: check 이후 문항이 바뀌었습니다")
    actual = _bindings(run, stored["request_id"])[role]
    if json_sha256(stored) != json_sha256(actual):
        raise ValueError("review_binding_changed: 검토 입력·지침·명세·스키마가 바뀌었습니다. 새 check와 검토가 필요합니다")
    return actual


def current_binding(run, role):
    base = _current_base_binding(run, role)
    if role == "blind":
        return base
    run = Path(run)
    request = json.loads((run / EDITOR_REQUEST_FILE).read_text()) if (run / EDITOR_REQUEST_FILE).exists() else {}
    if request.get("state") != "prepared":
        raise ValueError("editor_review_not_prepared: editor-prepare로 독립 풀이를 먼저 고정하세요")
    manifest_path = Path(request["manifest"]["path"]).resolve()
    root = (run / "editor-preparations").resolve()
    if root not in manifest_path.parents:
        raise ValueError("editor_review_binding_changed: 편집 검토 준비 기록이 바뀌었습니다")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != request["manifest"]["sha256"]:
        raise ValueError("editor_review_binding_changed: 편집 검토 준비 기록이 바뀌었습니다")
    manifest = json.loads(manifest_bytes)
    if manifest["base_binding"] != base:
        raise ValueError("review_input_binding_mismatch: 새 check에는 새 편집 검토 준비가 필요합니다")
    record = manifest["blind_review"]
    snapshot = manifest_path.parent / "blind-result.json"
    if (record["snapshot_path"] != str(snapshot) or file_sha256(snapshot) != record["file_sha256"]):
        raise ValueError("editor_blind_snapshot_changed: 편집자가 읽을 독립 풀이 사본이 바뀌었습니다")
    if file_sha256(manifest["blind_source_path"]) != record["file_sha256"]:
        raise ValueError("editor_blind_source_changed: 독립 풀이 원본이 바뀌었습니다. 새 editor-prepare와 편집 검토가 필요합니다")
    _, receipt = load_bound_review(snapshot, run, "blind")
    if (receipt["result_file_sha256"] != record["file_sha256"]
            or receipt["result_sha256"] != record["result_sha256"]
            or json_sha256(receipt["input_binding"]) != record["input_binding_sha256"]):
        raise ValueError("editor_blind_snapshot_changed: 고정한 독립 풀이의 검토 연결이 다릅니다")
    return {**base, "version": 2, "editor_preparation_id": manifest["preparation_id"], "blind_review": record}


def prepare_editor_review(run, blind_path):
    """Freeze a validated blind result before, never after, editorial review."""
    from .pipeline import save
    run, blind_path = Path(run).resolve(), Path(blind_path).resolve()
    outputs = [EDITOR_REQUEST_FILE, "status.json", "editorial-review-template.json", "editorial-review.schema.json"]
    if blind_path in {(run / name).resolve() for name in outputs}:
        raise ValueError("editor_blind_path_conflict: 독립 풀이 원본을 편집 준비의 출력 경로와 분리하세요")
    base = _current_base_binding(run, "editor")
    raw = blind_path.read_bytes()
    blind, receipt = load_bound_review(blind_path, run, "blind")
    digest = hashlib.sha256(raw).hexdigest()
    if receipt["result_file_sha256"] != digest:
        raise ValueError("review_result_changed: 준비 중 독립 풀이가 바뀌었습니다")
    _, draft, _ = review_inputs(run)
    expected = {item.id for item in draft.items}
    if len(blind.solutions) != len(expected) or {item.item_id for item in blind.solutions} != expected:
        raise ValueError("review_item_ids_mismatch: 독립 풀이 문항 누락·중복")
    if any(issue.item_id not in expected for issue in blind.issues):
        raise ValueError("review_item_ids_mismatch: 알 수 없는 문항의 독립 풀이 지적")
    preparation_id = uuid4().hex
    folder = run / "editor-preparations" / preparation_id
    folder.mkdir(parents=True, exist_ok=False)
    snapshot = folder / "blind-result.json"
    snapshot.write_bytes(raw)
    record = {"snapshot_path": str(snapshot), "file_sha256": digest,
              "result_sha256": receipt["result_sha256"],
              "input_binding_sha256": json_sha256(receipt["input_binding"])}
    manifest = {"preparation_id": preparation_id, "base_binding": base,
                "blind_source_path": str(blind_path), "blind_review": record, "blind_evidence": receipt}
    manifest_path = folder / "manifest.json"
    save(manifest_path, manifest)
    if (_current_base_binding(run, "editor") != base or file_sha256(blind_path) != digest
            or file_sha256(snapshot) != digest):
        raise ValueError("review_binding_changed: 편집 검토 준비 중 입력이 바뀌었습니다")
    invalidate_editor_review(run)
    save(run / EDITOR_REQUEST_FILE, {"state": "prepared",
         "manifest": {"path": str(manifest_path), "sha256": file_sha256(manifest_path)}})
    binding = current_binding(run, "editor")
    template = _template(binding)
    schema = envelope_schema("editor", binding)
    for destination in (folder, run):
        save(destination / "editorial-review-template.json", template)
        save(destination / "editorial-review.schema.json", schema)
    status_path = run / "status.json"
    status = json.loads(status_path.read_text())
    save(status_path, {**status, "state": "awaiting_independent_review", "pending_review": "editor",
                       "human_approved": False, "editor_preparation_id": preparation_id})
    return {"state": "awaiting_independent_review", "pending_review": "editor",
            "blind_snapshot": str(snapshot), "template": str(run / "editorial-review-template.json"),
            "schema": str(run / "editorial-review.schema.json"), "editor_preparation_id": preparation_id}


def verify_editor_blind_pair(run, blind_path, blind_evidence, editorial_path, editorial_evidence):
    binding = current_binding(run, "editor")
    record = binding["blind_review"]
    if (json_sha256(editorial_evidence["input_binding"]) != json_sha256(binding)
            or blind_evidence["result_file_sha256"] != record["file_sha256"]
            or blind_evidence["result_sha256"] != record["result_sha256"]
            or json_sha256(blind_evidence["input_binding"]) != record["input_binding_sha256"]):
        raise ValueError("editor_blind_binding_mismatch: 편집자가 대조한 독립 풀이와 제출된 풀이가 다릅니다")
    if (file_sha256(blind_path) != blind_evidence["result_file_sha256"]
            or file_sha256(editorial_path) != editorial_evidence["result_file_sha256"]):
        raise ValueError("review_result_changed: 제출 확인 중 검토 결과가 바뀌었습니다")


def _producer(value):
    if not isinstance(value, dict):
        raise ValueError("invalid_review_producer: 실행 주체 기록이 필요합니다")
    for key in ("requested_model", "actual_model"):
        if key not in value or (value[key] is not None and
                                (not isinstance(value[key], str) or not value[key].strip())):
            raise ValueError(f"invalid_review_producer: {key}는 확인된 문자열 또는 null이어야 합니다")
    mode = value.get("execution_mode")
    if mode == "external-attestation":
        if not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip():
            raise ValueError("invalid_review_producer: 외부 검토자를 명시하세요")
    elif mode == "codex-cli":
        if not value.get("requested_model") or value.get("actual_model") is not None:
            raise ValueError("invalid_review_producer: CLI 요청 모델과 미확인 실제 모델 ID를 구분하세요")
    else:
        raise ValueError("invalid_review_producer: 지원되지 않는 실행 방식")
    return mode


def _trace_paths(run, execution):
    root = (Path(run) / "codex-traces").resolve()
    paths = []
    for key in ("input", "events"):
        record = execution.get(key, {})
        if not isinstance(record, dict):
            raise ValueError("review_trace_mismatch: 실행 기록 형식이 잘못되었습니다")
        path = Path(record.get("path", "")).resolve()
        if path.parent != root or not path.is_file() or file_sha256(path) != record.get("sha256"):
            raise ValueError("review_trace_mismatch: 해당 run의 검토 실행 기록을 확인할 수 없습니다")
        paths.append(path)
    if not paths[0].name.endswith("-blind.input.json") or paths[1] != paths[0].with_suffix("").with_suffix(".jsonl"):
        raise ValueError("review_trace_mismatch: 독립 풀이 입력과 출력 기록이 같은 호출이 아닙니다")
    return paths


def _verify_codex_trace(run, evidence):
    from .codex_runtime import strict_schema
    from .pipeline import review_prompt
    from .visual_review import IMAGE_INSTRUCTIONS
    if evidence["input_binding"]["role"] != "blind":
        raise ValueError("review_trace_mismatch: 현재 자동 receipt는 blind 전용입니다")
    execution = evidence.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("review_trace_missing: CLI 입력·출력 기록이 필요합니다")
    input_path, _ = _trace_paths(run, execution)
    trace = json.loads(input_path.read_text())
    brief, _, public = review_inputs(run)
    images = trace.get("images", [])
    expected_payload = {**public, "rendered_images": images} if images else public
    expected_instructions = review_prompt("blind", brief) + (IMAGE_INSTRUCTIONS if images else "")
    task = expected_instructions + "\n도구·파일 탐색·웹 검색·재위임을 하지 말고 아래 입력만으로 답하라. 최종 출력은 스키마 JSON이다.\n" + json.dumps(expected_payload, ensure_ascii=False)
    if (trace.get("payload") != expected_payload or trace.get("instructions") != expected_instructions
            or trace.get("schema") != strict_schema(BlindReview.model_json_schema())
            or trace.get("model") != evidence["producer"]["requested_model"]
            or trace.get("task_sha256") != execution.get("task_sha256")
            or trace.get("task_sha256") != hashlib.sha256(task.encode("utf-8")).hexdigest()):
        raise ValueError("review_trace_mismatch: 실제 CLI 요청과 검토 binding이 다릅니다")
    figure_root = input_path.with_suffix("").with_suffix(".figures")
    for image in images:
        path = (figure_root / image["file"]).resolve()
        if figure_root.resolve() not in path.parents or not path.is_file() or file_sha256(path) != image["sha256"]:
            raise ValueError("review_trace_mismatch: 검토 이미지 증거가 다릅니다")


def codex_blind_envelope(run, binding, result, model, prior_inputs):
    """Runner-only receipt creation immediately after its fresh provider call."""
    if current_binding(run, "blind") != binding:
        raise ValueError("review_binding_changed: 독립 풀이 중 검토 요청이 바뀌었습니다")
    inputs = set((Path(run) / "codex-traces").glob("*-blind.input.json")) - set(prior_inputs)
    if len(inputs) != 1:
        raise ValueError("review_trace_missing: 이번 독립 풀이의 입력 기록 하나가 필요합니다")
    input_path = inputs.pop().resolve()
    events = input_path.with_suffix("").with_suffix(".jsonl")
    evidence = {
        "input_binding": binding,
        "producer": {"execution_mode": "codex-cli", "reviewer": "CodexProvider",
                     "requested_model": model, "actual_model": None},
        "result_sha256": json_sha256(result.model_dump()),
        "execution": {"input": {"path": str(input_path), "sha256": file_sha256(input_path)},
                      "events": {"path": str(events), "sha256": file_sha256(events)},
                      "task_sha256": json.loads(input_path.read_text())["task_sha256"]},
    }
    _verify_codex_trace(run, evidence)
    return {"result": result.model_dump(), "evidence": evidence}


def load_bound_review(path, run, role):
    """Validate bindings before the caller changes status or stores a gate result."""
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"result", "evidence"}:
        raise ValueError("legacy_missing_review_evidence: raw 검토 결과는 채택하지 않습니다. 검토 당시 binding을 담은 envelope가 필요합니다")
    evidence = data["evidence"]
    if not isinstance(evidence, dict) or json_sha256(evidence.get("input_binding")) != json_sha256(current_binding(run, role)):
        raise ValueError("review_input_binding_mismatch: 결과가 현행 입력·지침·명세에 대한 검토가 아닙니다")
    mode = _producer(evidence.get("producer"))
    result = SCHEMAS[role].model_validate(data["result"])
    result_sha = json_sha256(result.model_dump())
    if "result_sha256" in evidence and evidence["result_sha256"] != result_sha:
        raise ValueError("review_result_hash_mismatch: 저장된 검토 결과가 바뀌었습니다")
    if mode == "codex-cli":
        if "result_sha256" not in evidence:
            raise ValueError("review_result_hash_missing: CLI 실행기의 결과 해시가 필요합니다")
        _verify_codex_trace(run, evidence)
    file_digest = hashlib.sha256(raw).hexdigest()
    if file_sha256(path) != file_digest:
        raise ValueError("review_result_changed: 검토 결과를 읽는 동안 파일이 바뀌었습니다")
    receipt = {**evidence, "result_sha256": result_sha,
               "result_file_sha256": file_digest,
               "assurance": ("runner-linked-cli-trace" if mode == "codex-cli" else
                             "external-attestation; not cryptographic proof of reviewer execution")}
    return result, receipt
