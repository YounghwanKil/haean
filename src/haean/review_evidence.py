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


def json_sha256(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    save(run / REQUEST_FILE, {"candidate_sha256": file_sha256(run / "candidate.json"),
                              "bindings": bindings})
    for role, binding in bindings.items():
        filename = "editorial" if role == "editor" else role
        save(run / f"{filename}-review-template.json", {
            "result": None,
            "evidence": {"input_binding": binding,
                         "producer": {"execution_mode": "external-attestation", "reviewer": "",
                                      "requested_model": None, "actual_model": None}},
        })
        save(run / f"{filename}-review.schema.json", envelope_schema(role, binding))
    return bindings


def current_binding(run, role):
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
    data = json.loads(Path(path).read_text())
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
    receipt = {**evidence, "result_sha256": result_sha,
               "result_file_sha256": file_sha256(path),
               "assurance": ("runner-linked-cli-trace" if mode == "codex-cli" else
                             "external-attestation; not cryptographic proof of reviewer execution")}
    return result, receipt
