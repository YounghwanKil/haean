"""Bind explicitly supplied authoring material to its local evidence, read-only.

This verifies delivery and byte/content identity, not factual correctness, full
webpage reading, answer evidence, copyright status, or expert approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


class AuthoringSourceError(ValueError):
    """An explicitly supplied source cannot be bound without ambiguity."""


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthoringSourceError("duplicate JSON key in source packet")
        result[key] = value
    return result


def _loads(raw):
    def reject_constant(value):
        raise AuthoringSourceError("non-finite number in source packet")
    return json.loads(raw, object_pairs_hook=_object_pairs,
                      parse_constant=reject_constant)


def _student_valid(student):
    if not isinstance(student, dict) or not _nonempty(student.get("stem")):
        return False
    if not isinstance(student.get("passage"), str):
        return False
    # A table/conditions question may have no prose passage. A shared ID alone
    # is not supplied shared text; the text must occur in one of these fields.
    body = any(_nonempty(student.get(k)) for k in
               ("passage", "additional_passage", "shared_passage"))
    for key in ("conditions", "statements", "tables", "experiments", "results"):
        value = student.get(key, [])
        if not isinstance(value, list):
            return False
        body = body or any(_nonempty(v) or isinstance(v, dict) and bool(v)
                           for v in value)
    choices = student.get("choices")
    return (body and isinstance(choices, list) and len(choices) == 5
            and all(isinstance(c, dict) and type(c.get("number")) is int
                    and _nonempty(c.get("text")) for c in choices)
            and {c["number"] for c in choices} == set(range(1, 6)))


def _source_metadata_matches(left, right, keys=("path", "sha256")):
    """Compare shared native provenance fields without reinterpreting schemas.

    Legacy exports may describe a mirror PDF with pdf_path/pdf_sha256 and other
    metadata. Those are not the selected packet's native path/sha256 contract.
    """
    if not isinstance(left, dict) or not isinstance(right, dict):
        return True
    return all(_canonical(left[key]) == _canonical(right[key])
               for key in keys if key in left and key in right)


def _retrieval_matches(record, kind, material):
    """Compare overlapping retrieval material without inventing absent fields."""
    snapshot_keys = ("snapshot_path", "snapshot_sha256")
    if kind == "fact" and not _source_metadata_matches(record, material, snapshot_keys):
        return False
    try:
        content = _loads(record.get("text", ""))
    except (TypeError, ValueError):
        return kind == "fact" and record.get("text") == material["facts"]
    if not isinstance(content, dict):
        return False
    if kind == "fact":
        return (_source_metadata_matches(content, material, snapshot_keys)
                and all(_canonical(content.get(k)) == _canonical(material[k])
                        for k in ("facts", "url")))
    if any(not _source_metadata_matches(source, material["source"])
           for source in (record.get("source"), content.get("source"), content.get("출처"))):
        return False
    student = material["student"]
    if isinstance(content.get("student"), dict):
        return _canonical(content["student"]) == _canonical(student)
    # Corpus reference exports use Korean keys; native student data uses English.
    aliases = {"stem": "발문", "passage": "지문", "choices": "선지",
               "conditions": "조건", "statements": "보기", "tables": "표",
               "additional_passage": "추가 지문"}
    compared = set()
    for key in set(student) | set(aliases):
        source_key = key if key in content else aliases.get(key)
        if source_key in content:
            if _canonical(content[source_key]) != _canonical(student.get(key)):
                return False
            compared.add(key)
    return {"stem", "passage", "choices"} <= compared


def supplied_source_ids(context: dict, *, base_dir: str | Path | None = None) -> set[str]:
    """Return retrieval IDs plus verified, explicitly delivered assignment IDs.

    Only ``exam_assignment[].composition_resolution.selected_reference_input``
    and ``topic_fact_input`` extend the legacy ``references[].id`` allowlist.
    Their nonempty ``references``/``sources`` lists require a JSON packet at
    ``packet_path`` with matching ``packet_sha256`` and matching top-level list.
    Selected references bind complete ``student`` and ``source`` objects; source
    ``path``/``sha256`` bind the PDF bytes. Facts bind ``facts``, ``url``, and
    ``snapshot_path``/``snapshot_sha256``. Snapshot bytes are checked, but the
    snapshot may be any format and are not treated as a full archived webpage.
    Relative paths resolve against base_dir (default: current working directory),
    never relative to a packet. Missing optional blocks and empty lists add no
    IDs. Malformed explicit inputs or conflicting duplicate IDs raise ValueError
    before any ID set is returned. No files are written or instructions executed.
    """
    base = Path.cwd() if base_dir is None else Path(base_dir)
    cache: dict[Path, tuple[str, bytes]] = {}
    packets: dict[tuple[Path, str], dict] = {}

    def checked_file(path, sha):
        if not _nonempty(path) or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise AuthoringSourceError("source path and SHA-256 are required")
        target = Path(path)
        if not target.is_absolute():
            target = base / target
        if target not in cache:
            try:
                if not stat.S_ISREG(target.stat().st_mode):
                    raise AuthoringSourceError("source must be a regular file")
                raw = target.read_bytes()
            except OSError as exc:
                raise AuthoringSourceError("source file is unavailable") from exc
            cache[target] = (hashlib.sha256(raw).hexdigest(), raw)
        actual, raw = cache[target]
        if actual != sha:
            raise AuthoringSourceError("source file SHA-256 mismatch")
        return target, raw

    def packet_rows(block, list_key):
        path, raw = checked_file(block.get("packet_path"), block.get("packet_sha256"))
        key = (path, list_key)
        if key not in packets:
            try:
                packet = _loads(raw)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise AuthoringSourceError("source packet must be unambiguous JSON") from exc
            if not isinstance(packet, dict) or not isinstance(packet.get(list_key), list):
                raise AuthoringSourceError("source packet list is missing")
            packets[key] = packet
        return packets[key][list_key]

    def projection(row, kind):
        if not isinstance(row, dict):
            raise AuthoringSourceError("source record must be an object")
        if kind == "reference":
            if not _student_valid(row.get("student")) or not isinstance(row.get("source"), dict):
                raise AuthoringSourceError("selected reference requires full student content and source")
            return {k: row[k] for k in ("student", "source")}
        if not _nonempty(row.get("facts")) or not _nonempty(row.get("url")):
            raise AuthoringSourceError("fact source requires facts and URL")
        try:
            url = urlsplit(row["url"])
            valid_url = url.scheme in {"http", "https"} and bool(url.netloc)
        except ValueError:
            valid_url = False
        if not valid_url:
            raise AuthoringSourceError("fact source requires an HTTP(S) URL")
        return {k: row.get(k) for k in ("facts", "url", "snapshot_path", "snapshot_sha256")}

    allowed = set()
    retrieval = {}
    for row in context.get("references", []):
        source_id = row["id"]
        previous = retrieval.setdefault(source_id, [])
        if any(_canonical(prior.get("text")) != _canonical(row.get("text"))
               or not _source_metadata_matches(prior.get("source"), row.get("source"))
               or not _source_metadata_matches(prior, row, ("snapshot_path", "snapshot_sha256"))
               for prior in previous):
            raise AuthoringSourceError("conflicting retrieval source ID: " + source_id)
        previous.append(row)
        allowed.add(source_id)

    supplied = {}
    assignments = context.get("exam_assignment", [])
    if not isinstance(assignments, list):
        return allowed
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        resolution = assignment.get("composition_resolution", {})
        if not isinstance(resolution, dict):
            continue
        for block_key, list_key, id_key, kind in (
                ("selected_reference_input", "references", "reference_id", "reference"),
                ("topic_fact_input", "sources", "id", "fact")):
            if block_key not in resolution:
                continue
            block = resolution[block_key]
            if not isinstance(block, dict) or not isinstance(block.get(list_key), list):
                raise AuthoringSourceError("explicit source input requires a list: " + block_key)
            if not block[list_key]:
                continue
            rows = packet_rows(block, list_key)
            for row in block[list_key]:
                if not isinstance(row, dict) or not _nonempty(row.get(id_key)):
                    raise AuthoringSourceError("explicit source ID is missing")
                source_id = row[id_key]
                material = projection(row, kind)
                matches = [r for r in rows if isinstance(r, dict) and r.get(id_key) == source_id]
                if not matches or any(_canonical(projection(r, kind)) != _canonical(material) for r in matches):
                    raise AuthoringSourceError("source packet content mismatch: " + source_id)
                if kind == "reference":
                    checked_file(material["source"].get("path"), material["source"].get("sha256"))
                else:
                    checked_file(material["snapshot_path"], material["snapshot_sha256"])
                identity = (kind, _canonical(material))
                if source_id in supplied and supplied[source_id] != identity:
                    raise AuthoringSourceError("conflicting supplied source ID: " + source_id)
                if any(not _retrieval_matches(record, kind, material)
                       for record in retrieval.get(source_id, [])):
                    raise AuthoringSourceError("conflicting retrieval/supplied source ID: " + source_id)
                supplied[source_id] = identity
                allowed.add(source_id)
    return allowed
