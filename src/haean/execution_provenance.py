"""Immutable local snapshots of the code and inputs used by staged authoring.

This is execution provenance, not a replacement for the frozen evaluation
fingerprint and not proof of model quality or reviewer identity.
"""
from __future__ import annotations

import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
from datetime import datetime, timezone


VERSION = "haean-execution-snapshot-v1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _reject_constant(value):
    raise ValueError("Non-finite JSON number: " + value)


def _validate_manifest(value):
    """A matching local seal does not make a malformed manifest usable."""
    if not isinstance(value, dict):
        raise ValueError("Manifest must be an object")
    if not isinstance(value.get("parameters"), dict):
        raise ValueError("Manifest parameters must be an object")
    for key in ("created_at", "scope"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError("Missing manifest metadata: " + key)
    for key in ("frozen_evaluator_replaced", "quality_improvement_verified"):
        if value.get(key) is not False:
            raise ValueError("Unsupported provenance claim: " + key)

    def record(item, *, source=False):
        if not isinstance(item, dict):
            raise ValueError("Manifest record must be an object")
        if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Invalid record digest")
        if not isinstance(item.get("snapshot"), str) or not item["snapshot"]:
            raise ValueError("Missing snapshot path")
        if source and (not isinstance(item.get("path"), str) or not Path(item["path"]).is_absolute()):
            raise ValueError("Source path must be absolute")

    for key in ("runtime", "inputs"):
        if not isinstance(value.get(key), dict):
            raise ValueError("Manifest inventory must be an object")
        for name, item in value[key].items():
            if key == "inputs" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
                raise ValueError("Invalid input name")
            record(item, source=key == "inputs")
    record(value["instructions"])
    record(value["schemas"])


def runtime_sources() -> dict[str, bytes]:
    """Read installed package resources, including nested track instructions."""
    found = {}

    def walk(node, prefix=""):
        for child in sorted(node.iterdir(), key=lambda p: p.name):
            name = prefix + child.name
            if child.is_dir():
                if child.name != "__pycache__":
                    walk(child, name + "/")
            elif Path(name).suffix in {".py", ".md", ".json", ".toml"}:
                found[name] = child.read_bytes()

    walk(files("haean"))
    return found


def capture(destination: Path, *, inputs: dict[str, Path], instructions: dict[str, str],
            schemas: dict[str, dict], parameters: dict) -> Path:
    """Reserve a new directory and preserve actual inputs before model calls.

    Callers must give files that stay fixed for this phase. If a later phase
    modifies context, capture another directory rather than replacing this one.
    No raw source files, repository configuration or authentication files are
    discovered implicitly; only the installed package and named inputs are read.
    """
    destination = Path(destination)
    if not isinstance(parameters, dict):
        raise ValueError("실행 매개변수는 JSON 객체여야 합니다")
    for name in inputs:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ValueError("실행 입력 이름은 영문·숫자·점·밑줄·하이픈만 사용하세요")
    originals = {name: (str(Path(path).absolute()), Path(path).read_bytes())
                 for name, path in inputs.items()}
    runtime = runtime_sources()
    # Validate serializability before reserving the evidence directory.
    instruction_bytes, schema_bytes = encoded(instructions), encoded(schemas)
    encoded(parameters)
    destination.mkdir(parents=True, exist_ok=False)

    def store(relative, data):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        return {"sha256": digest(data), "snapshot": relative}

    manifest = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parameters": parameters,
        "runtime": {name: store("runtime/" + name, data) for name, data in runtime.items()},
        "inputs": {name: {"path": path, **store("inputs/" + name, data)}
                   for name, (path, data) in originals.items()},
        "instructions": store("instructions.json", instruction_bytes),
        "schemas": store("schemas.json", schema_bytes),
        "scope": "package code, named phase inputs and actual supplied instructions/schemas",
        "frozen_evaluator_replaced": False,
        "quality_improvement_verified": False,
    }
    data = encoded(manifest)
    store("manifest.json", data)
    store("manifest.sha256", (digest(data) + "\n").encode())
    result = destination / "manifest.json"
    check = verify(result)
    if not check["valid"]:
        raise ValueError("실행 스냅샷 작성 중 입력이 변경되었습니다: " + "; ".join(check["issues"]))
    return result


def verify(manifest_path: Path, *, expected_sha256: str | None = None,
           verify_runtime: bool = True) -> dict:
    """Fail closed on missing/changed inputs, code or snapshot copies.

    An optional caller-held digest also binds the manifest itself. The local
    seal catches accidental edits; neither mechanism authenticates a reviewer.
    Archived reevaluation may explicitly skip comparison to the current package,
    while still checking every stored runtime copy, source input and local seal.
    """
    if type(verify_runtime) is not bool:
        raise ValueError("verify_runtime은 bool이어야 합니다")

    def report(issues):
        result = {"valid": not issues, "issues": issues}
        if not verify_runtime:
            result.update(runtime_verification="archived_snapshot_only", current_runtime_verified=False,
                          assurance="Stored snapshots and source inputs are checked; current package runtime equality is not verified.")
        return result

    manifest_path = Path(manifest_path)
    root = manifest_path.parent.resolve()
    issues = []
    try:
        raw = manifest_path.read_bytes()
        seal = (root / "manifest.sha256").read_text().strip()
        if digest(raw) != seal or (expected_sha256 is not None and digest(raw) != expected_sha256):
            return report(["manifest_hash_mismatch"])
        manifest = json.loads(raw, parse_constant=_reject_constant)
        _validate_manifest(manifest)
        if manifest["version"] != VERSION:
            return report(["unsupported_manifest_version"])
        current = runtime_sources() if verify_runtime else None
        if verify_runtime and set(current) != set(manifest["runtime"]):
            issues.append("runtime_inventory_changed")

        def check_copy(record, label):
            path = (root / record["snapshot"]).resolve()
            if not path.is_relative_to(root):
                issues.append(label + ":snapshot_outside_root")
                return
            try:
                if digest(path.read_bytes()) != record["sha256"]:
                    issues.append(label + ":snapshot_hash_mismatch")
            except OSError:
                issues.append(label + ":snapshot_missing_or_unreadable")

        for name, record in manifest["runtime"].items():
            check_copy(record, "runtime:" + name)
            if verify_runtime and (name not in current or digest(current[name]) != record["sha256"]):
                issues.append("runtime:" + name + ":source_changed")
        for name, record in manifest["inputs"].items():
            check_copy(record, "input:" + name)
            try:
                if digest(Path(record["path"]).read_bytes()) != record["sha256"]:
                    issues.append("input:" + name + ":source_changed")
            except OSError:
                issues.append("input:" + name + ":source_missing_or_unreadable")
        check_copy(manifest["instructions"], "instructions")
        check_copy(manifest["schemas"], "schemas")
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        issues.append("invalid_or_missing_manifest")
    return report(issues)
