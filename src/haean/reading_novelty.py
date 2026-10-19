"""Native reading-book records for the local generation memory.

A record keeps a whole shared passage and its three questions. It is not a
reasoning Draft/Item. Author IDs identify revisions; old books without IDs get
book-version/locator IDs and no inferred cross-version lineage.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from . import reading_production as production
from .human_review import _read_json, _reject_constant, _unique_keys
from .reading_human_review import validate_book_data


FORMAT = "haean-reading-novelty-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PAYLOAD = {"_format", "id", "identity_scope", "passage", "selected_question_index", "provenance", "content_sha256"}
_PROVENANCE = {"source", "book_sha256", "book_metadata", "book_passage_count", "book_question_count",
               "passage_locator", "question_locator", "production", "assembly", "adjacent_verification"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    # The existing novelty DB uses this serialization for complete payloads.
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode())


def _read(path, capture=None):
    path = Path(path)
    if capture is not None:
        capture(path)
    raw = path.read_bytes()
    return raw, json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_keys)


def _manifest_inputs(folder, capture=None, *, root=False):
    """Capture declared evidence before production's existing validator reads it."""
    if root:
        if capture is not None:
            capture(folder / "manifest.sha256")
            capture(folder / "plan.json")
    _, manifest = _read(folder / "manifest.json", capture)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("언어이해 manifest files가 없습니다")
    for relative, expected in files.items():
        target = (folder / relative).resolve()
        if (not isinstance(expected, str) or not _SHA.fullmatch(expected)
                or Path(relative).is_absolute() or not target.is_relative_to(folder.resolve())):
            raise ValueError("잘못된 언어이해 manifest 경로·해시")
        if capture is not None:
            capture(target)
    return manifest


def is_reading(item):
    return isinstance(item, dict) and item.get("_format") == FORMAT


def question(item):
    """The verbatim selected question; validate retained DB payloads first."""
    return item["passage"]["questions"][item["selected_question_index"]]


def _content_hash(item):
    return _sha(_canonical({"passage": item["passage"],
                            "selected_question_index": item["selected_question_index"]}).encode())


def validate_item(item):
    """Validate a retained native payload without claiming its source exists."""
    if not is_reading(item) or set(item) != _PAYLOAD:
        raise ValueError("지원하지 않는 언어이해 novelty payload")
    index, provenance = item["selected_question_index"], item["provenance"]
    if type(index) is not int or not 0 <= index < 3:
        raise ValueError("언어이해 selected_question_index는 0~2 정수여야 합니다")
    if not isinstance(provenance, dict) or set(provenance) - _PROVENANCE or not (_PROVENANCE - {"production", "assembly", "adjacent_verification"}) <= set(provenance):
        raise ValueError("언어이해 원문 provenance가 잘못되었습니다")
    source, sha = provenance["source"], provenance["book_sha256"]
    if not isinstance(source, str) or not Path(source).is_absolute() or not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("언어이해 원문 절대 경로·SHA256이 필요합니다")
    count = provenance["book_passage_count"]
    if type(count) is not int or not 1 <= count <= 10 or type(provenance["book_question_count"]) is not int or provenance["book_question_count"] != count * 3:
        raise ValueError("언어이해는 1~9지문 pilot 또는 10지문 30문항이어야 합니다")
    locator = provenance["passage_locator"]
    match = re.fullmatch(r"/passages/(0|[1-9][0-9]*)", locator) if isinstance(locator, str) else None
    if not match or int(match[1]) >= count or provenance["question_locator"] != f"{locator}/questions/{index}":
        raise ValueError("언어이해 원문 locator 불일치")
    metadata = provenance["book_metadata"]
    if not isinstance(metadata, dict) or "passages" in metadata:
        raise ValueError("언어이해 book_metadata가 잘못되었습니다")
    passage = item["passage"]
    questions = passage.get("questions", []) if isinstance(passage, dict) else []
    first = questions[0].get("number") if questions and isinstance(questions[0], dict) else None
    if type(first) is not int:
        raise ValueError("언어이해 원문 문항 번호가 필요합니다")
    validate_book_data({**metadata, "passages": [passage]}, source=Path(source), book_sha=sha,
                       expected_numbers=range(first, first + 3), require_passage_ids=False)
    for key in ("production", "assembly"):
        if key in provenance and not isinstance(provenance[key], dict):
            raise ValueError("언어이해 제작 출처 연결이 잘못되었습니다")
    if "production" in provenance:
        bound = provenance["production"]
        fields = {"run", "run_id", "plan_sha256", "attempt_id", "attempt_manifest_sha256", "passage_id",
                  "declared_passage_count", "declared_question_count"}
        if (set(bound) != fields or not all(isinstance(bound[k], str) and bound[k] for k in fields - {"declared_passage_count", "declared_question_count"})
                or not Path(bound["run"]).is_absolute()
                or not all(production.TOKEN.fullmatch(bound[k]) for k in ("run_id", "attempt_id", "passage_id"))
                or not all(_SHA.fullmatch(bound[k]) for k in ("plan_sha256", "attempt_manifest_sha256"))
                or type(bound["declared_passage_count"]) is not int or not 1 <= bound["declared_passage_count"] <= 10
                or type(bound["declared_question_count"]) is not int or bound["declared_question_count"] != bound["declared_passage_count"] * 3
                or bound["passage_id"] != passage.get("id") or count != 1
                or Path(source) != Path(bound["run"]) / "passages" / bound["passage_id"] / "attempts" / bound["attempt_id"] / "candidate.json"):
            raise ValueError("언어이해 production provenance가 잘못되었습니다")
    if "assembly" in provenance:
        bound = provenance["assembly"]
        fields = {"verification_path", "verification_sha256", "run", "plan_sha256", "mode"}
        if (set(bound) != fields or not all(isinstance(v, str) and v for v in bound.values())
                or not Path(bound["run"]).is_absolute()
                or Path(bound["verification_path"]) != Path(source).parent / "verification.json"
                or not all(_SHA.fullmatch(bound[k]) for k in ("plan_sha256", "verification_sha256"))
                or bound["mode"] != ("full" if count == 10 else "pilot")):
            raise ValueError("언어이해 assembly provenance가 잘못되었습니다")
    if "adjacent_verification" in provenance:
        bound = provenance["adjacent_verification"]
        fields = {"path", "sha256", "classification", "claimed_book_sha256_verified"}
        if (not isinstance(bound, dict) or set(bound) != fields
                or bound["path"] != str(Path(source).parent / "verification.json")
                or not isinstance(bound["sha256"], str) or not _SHA.fullmatch(bound["sha256"])
                or bound["classification"] != "legacy_unverified_metadata"
                or type(bound["claimed_book_sha256_verified"]) is not bool
                or "assembly" in provenance):
            raise ValueError("언어이해 인접 verification 메타데이터가 잘못되었습니다")
    if "production" not in provenance and first != 3 * int(match[1]) + 1:
        raise ValueError("언어이해 book 문항 번호와 locator 불일치")
    q = question(item)
    expected_id = q.get("id", f"reading:{sha}:p{match[1]}:q{index}")
    expected_scope = "author_id" if "id" in q else "book_version"
    if item["id"] != expected_id or item["identity_scope"] != expected_scope:
        raise ValueError("언어이해 원문 문항 ID·identity_scope 불일치")
    if item["content_sha256"] != _content_hash(item):
        raise ValueError("언어이해 지문·형제문항 content 해시 불일치")
    return item


def _book_rows(path, raw, book, *, passage_id=None, expected_numbers=None, provenance_extra=None):
    passages = book.get("passages") if isinstance(book, dict) else None
    if not isinstance(passages, list) or not 1 <= len(passages) <= 10:
        raise ValueError("언어이해는 1~9지문 pilot 또는 10지문 30문항이어야 합니다")
    sha = _sha(raw)
    binding, _ = validate_book_data(book, source=path, book_sha=sha, expected_numbers=expected_numbers,
                                    require_passage_ids=False)
    selected = [(i, p) for i, p in enumerate(passages) if passage_id is None or p.get("id") == passage_id]
    if not selected:
        raise ValueError(f"book에 없는 지문 ID: {passage_id}")
    metadata = {k: deepcopy(v) for k, v in book.items() if k != "passages"}
    rows = []
    for p_index, passage in selected:
        for q_index, q in enumerate(passage["questions"]):
            mapping = binding["items"][3 * p_index + q_index]
            provenance = {"source": str(path), "book_sha256": sha, "book_metadata": metadata,
                          "book_passage_count": len(passages), "book_question_count": 3 * len(passages),
                          "passage_locator": mapping["passage_locator"], "question_locator": mapping["question_locator"],
                          **(provenance_extra or {})}
            item = {"_format": FORMAT, "id": q.get("id", mapping["item_id"]),
                    "identity_scope": "author_id" if "id" in q else "book_version",
                    "passage": deepcopy(passage), "selected_question_index": q_index, "provenance": provenance}
            item["content_sha256"] = _content_hash(item)
            validate_item(item)
            rows.append({"exam": "leet", "subject": "언어이해", "item": item,
                         "sha256": _digest(item), "source": str(path)})
    return rows


def _attempt_rows(folder, capture=None):
    """An explicitly selected historical attempt does not follow current.json."""
    if folder.parent.name != "attempts" or folder.parent.parent.parent.name != "passages":
        raise ValueError("언어이해 제작 attempt 경로가 아닙니다")
    run = folder.parents[3]
    _manifest_inputs(run, capture, root=True)
    run, plan, manifest = production._load(run)
    passage = production._planned(plan, folder.parent.parent.name)
    _manifest_inputs(folder, capture)
    record = production._verify(folder)
    expected = {"version": 1, "attempt_id": folder.name, "passage_id": passage["id"],
                "run_id": manifest["run_id"], "plan_sha256": manifest["plan_sha256"]}
    if type(record.get("version")) is not int or any(record.get(k) != v for k, v in expected.items()):
        raise ValueError("언어이해 attempt의 계획·지문 연결 불일치")
    path = folder / "candidate.json"
    raw, _ = _read(path, capture)
    if _sha(raw) != record["candidate_sha256"]:
        raise ValueError("언어이해 attempt 후보 해시 불일치")
    book = production._candidate(raw, plan, passage)
    public = production._student(book)
    if capture is not None:
        for relative in ("student.json", "blind-request/binding.json", "blind-request/input.json",
                         "blind-request/instructions.md", "blind-request/response.schema.json"):
            capture(folder / relative)
    if _read_json(folder / "student.json") != public or _sha(production._json_bytes(public)) != record["student_sha256"]:
        raise ValueError("언어이해 attempt 학생용 내용 불일치")
    production._verify_request(folder / "blind-request", "blind", public)
    extra = {"production": {"run": str(run), "run_id": manifest["run_id"], "plan_sha256": manifest["plan_sha256"],
                             "attempt_id": folder.name, "attempt_manifest_sha256": production._digest(folder / "manifest.json"),
                             "passage_id": passage["id"], "declared_passage_count": len(plan["passages"]),
                             "declared_question_count": 3 * len(plan["passages"])}}
    return _book_rows(path, raw, book, expected_numbers=[q["number"] for q in passage["questions"]], provenance_extra=extra)


def _run_rows(run, passage_id=None, capture=None):
    _manifest_inputs(run, capture, root=True)
    run, plan, manifest = production._load(run)
    selected = plan["passages"] if passage_id is None else [production._planned(plan, passage_id)]
    rows = []
    for passage in selected:
        base = run / "passages" / passage["id"]
        if not (base / "current.json").exists():
            if capture is not None:
                capture(base / "current.json")
            raise ValueError(f"언어이해 {passage['id']}에 초안이 없습니다. --passage-id로 제작된 지문 하나를 선택하세요")
        _, pointer = _read(base / "current.json", capture)
        folder = production._safe_child(base / "attempts", pointer["attempt_id"])
        _manifest_inputs(folder, capture)
        production._verify(folder, pointer["manifest_sha256"])
        rows.extend(_attempt_rows(folder, capture))
    return rows


def _assembly_extra(path, book, raw, capture=None):
    verification = path.parent / "verification.json"
    if not verification.exists():
        return {}
    verified_raw, record = _read(verification, capture)
    if not isinstance(record, dict):
        raise ValueError("언어이해 book verification은 객체여야 합니다")
    if record.get("kind") != "reading_production_assembly":
        # Older books have review/layout metadata here. Preserve its exact
        # binding without promoting approval fields to production evidence.
        if "book_sha256" in record and record["book_sha256"] != _sha(raw):
            raise ValueError("언어이해 이전 verification의 book 해시 불일치")
        return {"adjacent_verification": {"path": str(verification), "sha256": _sha(verified_raw),
                                           "classification": "legacy_unverified_metadata",
                                           "claimed_book_sha256_verified": "book_sha256" in record}}
    count = len(book["passages"])
    mode = "full" if count == 10 else "pilot"
    expected = {"version": 1, "mode": mode, "scope": f"{mode}_declared_plan", "passage_count": count,
                "question_count": count * 3, "book_sha256": _sha(raw)}
    if (any(type(record.get(k)) is not type(v) or record.get(k) != v for k, v in expected.items())):
        raise ValueError("언어이해 조립 선언·book 해시 불일치")
    run = Path(record["run"])
    if not run.is_absolute():
        raise ValueError("언어이해 조립 run 절대 경로가 필요합니다")
    _manifest_inputs(run, capture, root=True)
    _, plan, manifest = production._load(run)
    if (manifest["plan_sha256"] != record["plan_sha256"] or plan["mode"] != mode or len(plan["passages"]) != count
            or book.get("title") != plan["title"] or book.get("minutes") != plan["minutes"]
            or book.get("human_approved") is not False):
        raise ValueError("언어이해 조립 계획 불일치")
    sets = record.get("sets")
    if not isinstance(sets, list) or len(sets) != count:
        raise ValueError("언어이해 조립 세트 수 불일치")
    for actual, planned, entry in zip(book["passages"], plan["passages"], sets, strict=True):
        if entry["passage_id"] != planned["id"] or entry["question_ids"] != [q["id"] for q in planned["questions"]]:
            raise ValueError("언어이해 조립 지문·문항 ID 불일치")
        folder = production._safe_child(run / "passages" / planned["id"] / "attempts", entry["attempt_id"])
        editor = production._safe_child(folder / "editor-requests", entry["editor_request_id"])
        files = entry.get("source_files")
        if not isinstance(files, list) or len(files) != 11:
            raise ValueError("언어이해 조립의 필수 근거 11개가 필요합니다")
        paths = []
        for file in files:
            if not isinstance(file, dict) or set(file) != {"path", "sha256"} or not isinstance(file["path"], str):
                raise ValueError("잘못된 언어이해 조립 근거 선언")
            evidence = Path(file["path"])
            if (not evidence.is_absolute() or not evidence.resolve().is_relative_to(run.resolve())
                    or not isinstance(file["sha256"], str) or not _SHA.fullmatch(file["sha256"])):
                raise ValueError("언어이해 조립 근거는 제작 run 안의 경로·SHA256이어야 합니다")
            paths.append(evidence)
        required = {run / "plan.json", run / "manifest.json", folder / "manifest.json", folder / "candidate.json",
                    folder / "student.json", folder / "blind-request/binding.json", editor / "manifest.json",
                    editor / "blind.json", editor / "request/binding.json"}
        result_files = set(paths) - required
        if (len(set(paths)) != 11 or not required <= set(paths) or len(result_files) != 2
                or {p.name for p in result_files} != {"manifest.json", "editorial.json"}
                or len({p.parent for p in result_files}) != 1):
            raise ValueError("언어이해 조립 필수 근거 누락·중복·연결 불일치")
        result_folder = next(iter(result_files)).parent
        if (result_folder.parent != editor / "results" or not production.TOKEN.fullmatch(result_folder.name)):
            raise ValueError("언어이해 조립 결과 경로 연결 불일치")
        for file, evidence in zip(files, paths, strict=True):
            if capture is not None:
                capture(evidence)
            if _sha(evidence.read_bytes()) != file["sha256"]:
                raise ValueError("언어이해 조립 근거 해시 불일치")
        attempt = _attempt_rows(folder, capture)
        if _canonical(attempt[0]["item"]["passage"]) != _canonical(actual):
            raise ValueError("언어이해 조립 book·시도 원문 불일치")
    return {"assembly": {"verification_path": str(verification), "verification_sha256": _sha(verified_raw),
                          "run": str(run), "plan_sha256": record["plan_sha256"], "mode": mode}}


def maybe_records(path, passage_id=None, capture=None):
    """Return native reading records or None for a standard Draft input.

    Each read is captured first when a review's snapshot guard is supplied.
    Whole run input requires every declared set to have a valid current draft;
    select a passage explicitly to inspect an incomplete production run.
    """
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        if (path / "book.json").exists():
            return records(path / "book.json", passage_id=passage_id, capture=capture)
        if (path / "plan.json").exists() and (path / "manifest.sha256").exists():
            return _run_rows(path, passage_id, capture)
        candidate = path / "candidate.json"
        if not candidate.exists():
            return None
    else:
        candidate = path
    raw, data = _read(candidate, capture)
    if not isinstance(data, dict) or "passages" not in data:
        return None
    if candidate.name == "candidate.json" and candidate.parent.parent.name == "attempts":
        rows = _attempt_rows(candidate.parent, capture)
        if passage_id is not None and rows[0]["item"]["passage"].get("id") != passage_id:
            raise ValueError(f"attempt에 없는 지문 ID: {passage_id}")
        return rows
    # Validate the actual book before interpreting adjacent declarations.
    initial = _book_rows(candidate, raw, data, passage_id=passage_id)
    extra = _assembly_extra(candidate, data, raw, capture) if candidate.name == "book.json" else {}
    if not extra:
        return initial
    return _book_rows(candidate, raw, data, passage_id=passage_id, provenance_extra=extra)


def records(path, passage_id=None, capture=None):
    rows = maybe_records(path, passage_id=passage_id, capture=capture)
    if rows is None:
        raise ValueError(f"언어이해 book·제작 run·attempt 입력이 아닙니다: {path}")
    return rows


def shared_pair(left, right):
    """Suppress only intentionally shared passage/data, never question logic."""
    if not is_reading(left) or not is_reading(right):
        return False
    a, b = left["passage"], right["passage"]
    same_snapshot = (left["provenance"]["book_sha256"] == right["provenance"]["book_sha256"]
                     and left["provenance"]["passage_locator"] == right["provenance"]["passage_locator"]
                     and _canonical(a) == _canonical(b))
    # The same authored set can appear in a checked attempt and an assembled
    # book, or retain its passage while a sibling question is revised. Require
    # all three author IDs, not merely a reused passage label or similar text.
    a_ids = [q.get("id") for q in a["questions"]]
    b_ids = [q.get("id") for q in b["questions"]]
    authored_shared = (isinstance(a.get("id"), str) and a["id"] == b.get("id")
                       and all(isinstance(value, str) and value for value in a_ids)
                       and a_ids == b_ids and _canonical(a["paragraphs"]) == _canonical(b["paragraphs"]))
    return same_snapshot or authored_shared
