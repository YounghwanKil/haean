"""Opt-in model projection of two reference audit inventories.

The full context is authoritative. Call ``supplied_source_ids`` on it *before*
this helper and never validate reference identity against the returned copy.
This module verifies the archive binding, not question or source validity.
Unknown fields and shapes are preserved, including corpus/transcription notes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


class AuthoringProjectionError(ValueError):
    """The complete original context cannot be bound to its audit archive."""


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TARGETS = (("evidence_files",), ("official_answer", "evidence", "files"))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _pointer(parts: tuple[str | int, ...]) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthoringProjectionError("archive contains duplicate JSON keys")
        result[key] = value
    return result


def _invalid_constant(value):
    raise AuthoringProjectionError(f"archive contains non-finite JSON number: {value}")


def _validate_json(value: Any) -> None:
    # Do not coerce tuple/list, non-string keys or unknown Python values while
    # binding to an archive; preservation is of the original JSON structure.
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise AuthoringProjectionError("context JSON object keys must be strings")
        for child in value.values():
            _validate_json(child)
    elif isinstance(value, list):
        for child in value:
            _validate_json(child)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise AuthoringProjectionError("context must contain only JSON values")


def _copy_json(value: Any) -> Any:
    # JSON has no shared object identity. Copy each occurrence independently so
    # a Python alias reused in two slots gets the correct archive pointer twice.
    if isinstance(value, dict):
        return {key: _copy_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_json(child) for child in value]
    return value


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _inventory_shape(value: Any, expected: str) -> tuple[str | None, str]:
    if not isinstance(value, dict):
        return None, "not_a_file_map"
    if not value:
        return None, "empty_file_map"
    keys = {"path", "sha256"} if expected == "path_sha256" else {"file", "sha256", "locator", "usage"}
    path_key = "path" if expected == "path_sha256" else "file"
    for name, entry in value.items():
        if not _nonempty_string(name) or not isinstance(entry, dict) or set(entry) != keys:
            return None, "unknown_entry_shape"
        if not _nonempty_string(entry[path_key]) or not isinstance(entry["sha256"], str) \
                or _SHA256.fullmatch(entry["sha256"]) is None:
            return None, "invalid_path_or_sha256"
        if expected != "path_sha256" and (not isinstance(entry["locator"], str)
                                           or not isinstance(entry["usage"], str)):
            return None, "invalid_annotation_type"
    return expected, "known_file_inventory"


def project_authoring_context(
    context: dict, *, archive_path: str | Path, archive_sha256: str,
) -> tuple[dict, dict]:
    """Return an independent model-input copy and a loss-accounting manifest.

    Only the two exact selected-reference inventory locations are candidates.
    Original entry keys remain visible; official-answer ``locator`` and ``usage``
    annotations remain verbatim. Paths and digests remain recoverable through the
    verified full archive and each inventory's JSON Pointer and canonical hash.
    A descriptor larger than its original map is not substituted.
    """
    if not isinstance(context, dict):
        raise AuthoringProjectionError("context must be a JSON object")
    if not isinstance(archive_sha256, str) or _SHA256.fullmatch(archive_sha256) is None:
        raise AuthoringProjectionError("archive_sha256 must be a lowercase SHA-256")
    try:
        _validate_json(context)
        original_text = _canonical(context)
        path = Path(archive_path).resolve(strict=True)
        archive_bytes = path.read_bytes()
        if _sha(archive_bytes) != archive_sha256:
            raise AuthoringProjectionError("archive SHA-256 mismatch")
        archived = json.loads(archive_bytes, object_pairs_hook=_object,
                              parse_constant=_invalid_constant)
        if _canonical(archived) != original_text:
            raise AuthoringProjectionError("archive content does not match original context")
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        if isinstance(exc, AuthoringProjectionError):
            raise
        raise AuthoringProjectionError(f"cannot verify original context archive: {exc}") from exc

    projected = _copy_json(context)
    archive = {"path": str(path), "sha256": archive_sha256}
    decisions: list[dict] = []

    def observe(parts, status, reason, **detail):
        decisions.append({"json_pointer": _pointer(parts), "status": status,
                          "reason": reason, **detail})

    def project_source(source: dict, base: tuple):
        for target in _TARGETS:
            parent = source
            for key in target[:-1]:
                if key not in parent:
                    observe(base + target, "absent", "parent_missing")
                    break
                if not isinstance(parent[key], dict):
                    observe(base + target, "skipped", "parent_not_object")
                    break
                parent = parent[key]
            else:
                key = target[-1]
                if key not in parent:
                    observe(base + target, "absent", "field_missing")
                    continue
                value = parent[key]
                expected = "path_sha256" if len(target) == 1 else "file_sha256_locator_usage"
                shape, reason = _inventory_shape(value, expected)
                original_map = _canonical(value)
                detail = {"original_characters": len(original_map),
                          "original_canonical_sha256": _sha(original_map)}
                if shape is None:
                    observe(base + target, "preserved", reason, **detail)
                    continue
                descriptor = {
                    "projection_kind": "archived_file_inventory",
                    "schema_version": 1,
                    "archive_path": archive["path"], "archive_sha256": archive["sha256"],
                    "json_pointer": _pointer(base + target),
                    "original_canonical_sha256": detail["original_canonical_sha256"],
                    "entry_count": len(value), "entry_shape": shape,
                }
                if shape == "path_sha256":
                    descriptor["entry_keys"] = list(value)
                else:
                    descriptor["entry_annotations"] = {
                        name: {"locator": entry["locator"], "usage": entry["usage"]}
                        for name, entry in value.items()
                    }
                descriptor_characters = len(_canonical(descriptor))
                detail.update(entry_count=len(value), entry_shape=shape,
                              descriptor_characters=descriptor_characters,
                              projected_characters=descriptor_characters)
                if detail["projected_characters"] >= detail["original_characters"]:
                    detail["projected_characters"] = detail["original_characters"]
                    observe(base + target, "preserved", "descriptor_not_smaller", **detail)
                    continue
                parent[key] = descriptor
                observe(base + target, "compacted", reason, **detail)

    assignments = projected.get("exam_assignment")
    if not isinstance(assignments, list):
        observe(("exam_assignment",), "skipped", "missing_or_not_list")
    else:
        for slot_index, slot in enumerate(assignments):
            parts = ("exam_assignment", slot_index)
            node = slot
            for key in ("composition_resolution", "selected_reference_input", "references"):
                if not isinstance(node, dict) or key not in node:
                    observe(parts, "skipped", "missing_or_non_object_parent")
                    break
                node, parts = node[key], parts + (key,)
            else:
                if not isinstance(node, list):
                    observe(parts, "skipped", "references_not_list")
                    continue
                for ref_index, ref in enumerate(node):
                    base = parts + (ref_index, "source")
                    if not isinstance(ref, dict) or not isinstance(ref.get("source"), dict):
                        observe(base, "skipped", "source_missing_or_not_object")
                        continue
                    project_source(ref["source"], base)

    projected_text = _canonical(projected)
    manifest = {
        "schema_version": 1, "mode": "compact_reference_audit", "archive": archive,
        "context_canonical_sha256": _sha(original_text),
        "projected_canonical_sha256": _sha(projected_text),
        "character_counts": {"original": len(original_text), "projected": len(projected_text),
                             "saved": len(original_text) - len(projected_text)},
        "counts": {"compacted_maps": sum(d["status"] == "compacted" for d in decisions),
                   "preserved_maps": sum(d["status"] == "preserved" for d in decisions),
                   "absent_maps": sum(d["status"] == "absent" for d in decisions),
                   "skipped_locations": sum(d["status"] == "skipped" for d in decisions),
                   "archived_entries": sum(d["entry_count"] for d in decisions
                                           if d["status"] == "compacted")},
        "decisions": decisions,
    }
    return projected, manifest
