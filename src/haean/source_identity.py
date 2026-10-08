"""Read-only checks of raw JSON source identity; no semantic certification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ENCODINGS = ("raw_sorted_compact", "raw_sorted_default")
REQUIRED = ("id", "source", "source_file_sha256", "locator", "payload_sha256")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON number")


def _loads(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)


def payload_digest(item, encoding="raw_sorted_compact"):
    """Hash the complete, unnormalized item, including its number and ID."""
    if encoding not in ENCODINGS:
        raise ValueError("unsupported payload_encoding")
    kwargs = {"separators": (",", ":")} if encoding == ENCODINGS[0] else {}
    return _sha(json.dumps(item, ensure_ascii=False, sort_keys=True,
                           allow_nan=False, **kwargs).encode("utf-8"))


def locate(document, locator):
    """RFC 6901 pointer (including root) or legacy $.items[n], no evaluation."""
    if not isinstance(locator, str):
        raise ValueError("locator must be a string")
    legacy = re.fullmatch(r"\$\.items\[(0|[1-9][0-9]*)\]", locator)
    if legacy:
        locator = "/items/" + legacy[1]
    if locator == "":
        return document
    if not locator.startswith("/"):
        raise ValueError("unsupported locator")
    for token in locator[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("invalid JSON pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(document, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("invalid array index")
            document = document[int(token)]
        elif isinstance(document, dict):
            document = document[token]
        else:
            raise ValueError("locator traverses a scalar")
    return document


def _equal(left, right):
    # Python equality alone accepts True == 1 and 1 == 1.0.
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def verify(profile_path: Path, out: Path | None = None):
    """Return a report, optionally creating a NEW report file. Never modify inputs."""
    profile_path = Path(profile_path)
    report = {
        "profile_path": str(profile_path.absolute()), "profile_sha256": None,
        "records": 0, "valid": False, "errors": [], "profiles": [],
        "raw_digest_encoding_counts": {},
        "scope": "Declared ID equals located raw item ID; raw file bytes and raw item "
                 "digests; equality of supplied embedded fields only. No full-text reading, "
                 "semantic, originality, answer correctness or expert review certification.",
        "source_path_base": str(Path.cwd()),
    }
    protected = [profile_path]
    try:
        raw = profile_path.read_bytes()
        report["profile_sha256"] = _sha(raw)
        profiles = _loads(raw)
        if not isinstance(profiles, list):
            raise ValueError("profile collection must be a list")
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        report["errors"].append({"code": "invalid_input", "detail": str(exc)})
        profiles = []
    if not profiles:
        report["errors"].append({"code": "empty_profile_collection"})
    report["records"] = len(profiles)
    seen, cache = set(), {}
    for index, profile in enumerate(profiles):
        row = {"profile_index": index, "id": None, "errors": [],
               "embedded_fields_checked": [], "missing_embedded_evidence": [],
               "full_student_text_verified": False}
        report["profiles"].append(row)
        errors = row["errors"]
        if not isinstance(profile, dict):
            errors.append("profile_must_be_object")
            continue
        item_id = profile.get("id")
        if isinstance(item_id, str):
            row["id"] = item_id
            if item_id in seen:
                errors.append("duplicate_id")
            seen.add(item_id)
        for key in REQUIRED:
            value = profile.get(key)
            if key not in profile:
                errors.append("missing_field:" + key)
            elif not isinstance(value, str) or (key != "locator" and not value.strip()):
                errors.append("invalid_field:" + key)
            elif key.endswith("sha256") and not re.fullmatch(r"[0-9a-f]{64}", value):
                errors.append("invalid_sha256:" + key)
        if isinstance(profile.get("source"), str) and profile["source"]:
            protected.append(Path(profile["source"]))
        for key in ("student_original", "original_judgments", "original_explanation"):
            if key not in profile:
                row["missing_embedded_evidence"].append(key)
        student = profile.get("student_original")
        if "student_original" in profile:
            if not isinstance(student, dict):
                errors.append("student_original_must_be_object")
            elif not student:
                row["missing_embedded_evidence"].append("student_original:empty")
        if "original_explanation" in profile and (not isinstance(profile["original_explanation"], str) or not profile["original_explanation"].strip()):
            errors.append("original_explanation_must_be_nonempty_string")
        if "original_judgments" in profile and (not isinstance(profile["original_judgments"], list) or not profile["original_judgments"]):
            errors.append("original_judgments_must_be_nonempty_array")
        encoding = profile.get("payload_encoding")
        if "payload_encoding" in profile and (not isinstance(encoding, str) or encoding not in ENCODINGS):
            errors.append("unsupported_payload_encoding")
        if any(e.startswith(("missing_field:", "invalid_field:", "invalid_sha256:")) for e in errors):
            continue
        try:
            source = Path(profile["source"])
            if source not in cache:
                raw = source.read_bytes()
                cache[source] = (_sha(raw), _loads(raw))
            source_hash, document = cache[source]
            if source_hash != profile["source_file_sha256"]:
                errors.append("source_file_hash_mismatch")
            try:
                item = locate(document, profile["locator"])
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                errors.append("invalid_locator:" + type(exc).__name__)
                continue
            if not isinstance(item, dict):
                errors.append("source_item_must_be_object")
                continue
            if not isinstance(item.get("id"), str) or item["id"] != item_id:
                errors.append("source_item_id_mismatch")
            if "unsupported_payload_encoding" not in errors:
                choices = (encoding,) if encoding is not None else ENCODINGS
                matches = [enc for enc in choices if payload_digest(item, enc) == profile["payload_sha256"]]
                row["payload_encoding_matches"] = matches
                row["payload_encoding_mode"] = "explicit" if encoding else "legacy_auto"
                if not matches:
                    errors.append("raw_payload_hash_mismatch")
                for match in matches:
                    counts = report["raw_digest_encoding_counts"]
                    counts[match] = counts.get(match, 0) + 1
            if isinstance(student, dict):
                for key, value in student.items():
                    row["embedded_fields_checked"].append("student_original." + key)
                    if key not in item or not _equal(value, item[key]):
                        errors.append("student_field_mismatch:" + key)
            for key, source_key in (("original_judgments", "judgments"),
                                    ("original_explanation", "explanation")):
                if key in profile:
                    row["embedded_fields_checked"].append(key)
                    if source_key not in item or not _equal(profile[key], item[source_key]):
                        errors.append("original_field_mismatch:" + source_key)
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            errors.append("unresolved_source:" + type(exc).__name__)
    report["valid"] = not report["errors"] and not any(r["errors"] for r in report["profiles"])
    if out is not None:
        out = Path(out)
        try:
            if any(out.resolve() == path.resolve() for path in protected):
                raise ValueError("report path collides with input or source")
            # Exclusive create also refuses existing reports, hard links and symlinks.
            with out.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        except (OSError, ValueError, RuntimeError) as exc:
            report["valid"] = False
            report["errors"].append({"code": "report_output_refused", "detail": str(exc)})
    return report
