"""Read version-bound, post-review opinions without altering saved reviews."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import Brief, Draft


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _draft_sha(seed):
    value = Draft.model_validate(seed).model_dump(mode="json")
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode())


def requires_revision(packet):
    """C opinions are useful editorial context, not an automatic rewrite."""
    return bool(packet and packet.get("application") == "pending_revision"
                and any(record["entry"]["severity"] in {"A", "B"}
                               for record in packet["records"]))


def _inherited(run):
    saved = run / "revision-feedback.json"
    packet = json.loads(saved.read_text()) if saved.exists() else None
    context_path = run / "context.json"
    if context_path.exists():
        context = json.loads(context_path.read_text())
        lineage = context.get("resume_lineage", {})
        lineage_packet = lineage.get("revision_feedback") if isinstance(lineage, dict) else None
        if packet is not None and lineage_packet is not None and packet != lineage_packet:
            raise ValueError("상속 후속 의견과 lineage 불일치")
        if packet is None:
            packet = lineage_packet
    return packet


def load_revision_feedback(run, seed, *, _inherit=True):
    """Return an exact-current-candidate feedback packet, or None.

    ``seed`` is the actual draft selected for resumption. Matching feedback on
    an older candidate must not silently apply to a newer, interrupted draft.
    Other runs and explicitly stale candidate hashes are excluded. Original
    JSONL entries, line hashes and source file hashes remain in the packet.
    """
    run = Path(run).resolve()
    source = run.parent / "feedback.jsonl"
    raw = source.read_bytes() if source.exists() else b""
    relevant = []
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"후속 의견 JSONL 오류: {source}:{number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"후속 의견 행 형식 오류: {source}:{number}")
        if row.get("run") == run.name:
            relevant.append((number, line, row))
    records, excluded = [], []
    if relevant:
        candidate_path, brief_path = run / "candidate.json", run / "brief.json"
        if not candidate_path.exists():
            raise ValueError("후속 의견이 연결된 candidate 원본 누락")
        candidate_bytes, brief_bytes = candidate_path.read_bytes(), brief_path.read_bytes()
        candidate_sha = _sha(candidate_bytes)
        candidate = Draft.model_validate_json(candidate_bytes)
        brief = Brief.model_validate_json(brief_bytes)
        ids = {item.id for item in candidate.items}
        for number, line, row in relevant:
            bound_sha = row.get("candidate_sha256")
            if (not isinstance(bound_sha, str) or len(bound_sha) != 64
                    or any(char not in "0123456789abcdef" for char in bound_sha)):
                raise ValueError("후속 의견 candidate 해시 누락·형식 오류")
            if bound_sha != candidate_sha:
                excluded.append({"line": number, "line_sha256": _sha(line),
                                 "candidate_sha256": bound_sha, "reason": "stale_candidate"})
                continue
            if row.get("exam") != brief.exam or row.get("subject") != brief.subject:
                raise ValueError("후속 의견 시험·과목 연결 불일치")
            if row.get("item_id") not in ids:
                raise ValueError("후속 의견 문항 ID 연결 불일치")
            if (row.get("severity") not in {"A", "B", "C"}
                    or any(not isinstance(row.get(key), str) or not row[key].strip()
                           for key in ("text", "reviewer"))
                    or row.get("origin", "unknown") not in {"human", "model", "unknown"}):
                raise ValueError("후속 의견 원문·주체·등급 형식 오류")
            reviewed = row.get("reviewed_candidate_sha256")
            if reviewed is not None and reviewed != candidate_sha:
                raise ValueError("후속 의견 검토자가 지정한 candidate 해시 불일치")
            records.append({"line": number, "line_sha256": _sha(line), "entry": row})
        if records:
            if seed is None or _draft_sha(seed) != _draft_sha(candidate):
                raise ValueError("재개 seed와 후속 의견 candidate 내용이 다릅니다. 현 초안을 다시 검토해 의견을 연결하세요.")
            return {"schema_version": 1, "application": "pending_revision", "run": str(run),
                    "candidate": {"path": str(candidate_path), "sha256": candidate_sha},
                    "brief": {"path": str(brief_path), "sha256": _sha(brief_bytes)},
                    "source": {"path": str(source), "sha256": _sha(raw)},
                    "seed_content_sha256": _draft_sha(seed), "records": records,
                    "excluded_stale_records": excluded}
    if not _inherit:
        return None
    paths = list(run.glob("draft-r*.json"))
    latest = max(paths, key=lambda path: int(path.stem.split("-r")[1])) if paths else None
    # Once a fresh review is saved it owns the next revision decision. The
    # inherited B must not be replayed forever. An interrupted blind/editor
    # stage, however, still needs the original opinion for editorial comparison.
    if latest is not None and latest.with_name(latest.name.replace("draft-", "review-")).exists():
        return None
    if latest is None and (run / "candidate.json").exists():
        return None
    inherited = _inherited(run)
    if inherited is None:
        return None
    if latest is None:
        validate_revision_feedback(inherited, seed)
        return inherited
    original = _original_packet(inherited)
    original_seed = Draft.model_validate_json(Path(original["candidate"]["path"]).read_bytes())
    validate_revision_feedback(original, original_seed)
    if seed is None or _draft_sha(seed) != _draft_sha(Draft.model_validate_json(latest.read_bytes())):
        raise ValueError("후속 의견의 재검토 seed와 저장된 최신 초안 불일치")
    return {**original, "application": "historical_review",
            "resumed_seed_content_sha256": _draft_sha(seed),
            "resume_seed": {"path": str(latest), "sha256": _sha(latest.read_bytes())}}


def _original_packet(packet):
    result = {key: value for key, value in packet.items()
              if key not in {"resumed_seed_content_sha256", "resume_seed"}}
    result["application"] = "pending_revision"
    return result


def validate_revision_feedback(packet, seed):
    """Verify a copied packet against its immutable source and selected seed."""
    if packet is None:
        return
    if (not isinstance(packet, dict) or packet.get("schema_version") != 1
            or not isinstance(packet.get("run"), str) or not packet.get("records")
            or packet.get("application") not in {"pending_revision", "historical_review"}):
        raise ValueError("후속 의견 패킷 형식 오류")
    if packet["application"] == "historical_review":
        if seed is None or packet.get("resumed_seed_content_sha256") != _draft_sha(seed):
            raise ValueError("후속 의견의 재검토 seed 내용 불일치")
        ref = packet.get("resume_seed")
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
            raise ValueError("후속 의견의 재검토 초안 원본 연결 누락")
        raw = Path(ref["path"]).read_bytes()
        if ref.get("sha256") != _sha(raw) or _draft_sha(Draft.model_validate_json(raw)) != _draft_sha(seed):
            raise ValueError("후속 의견의 재검토 초안 원본 해시·내용 불일치")
        original = _original_packet(packet)
        original_seed = Draft.model_validate_json(Path(original["candidate"]["path"]).read_bytes())
        validate_revision_feedback(original, original_seed)
        return
    if seed is None or packet.get("seed_content_sha256") != _draft_sha(seed):
        raise ValueError("재개 seed와 후속 의견 candidate 내용 불일치")
    # This also checks item IDs, subject, text and provenance. A packet with
    # selected records always resolves directly, never through inherited data.
    source = Path(packet["run"]).resolve()
    current = load_revision_feedback(source, seed, _inherit=False)
    if current != packet:
        raise ValueError("후속 의견 원문·위치·해시 변경 또는 연결 불일치")
