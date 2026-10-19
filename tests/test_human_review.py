"""Synthetic records only; no model generation or expert-review claims."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from haean.human_review import ReviewResponse, collect_packet, create_packet


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_fixture(path, draft, brief, *, parent=None):
    path.mkdir(parents=True)
    write(path / "candidate.json", draft)
    write(path / "brief.json", {**brief, "count": len(draft["items"]), "shared_passage": False})
    state = {"state": "awaiting_human_review", "human_approved": False,
             "candidate_sha256": hashlib.sha256((path / "candidate.json").read_bytes()).hexdigest()}
    if parent:
        state["parent_review_run"] = str(parent)
    write(path / "status.json", state)
    return path


@pytest.fixture
def source(tmp_path, draft, brief):
    return run_fixture(tmp_path / "run", draft.model_dump(), brief.model_dump())


@pytest.fixture
def assembled(tmp_path, draft, brief):
    data = draft.model_dump()
    second = copy.deepcopy(data["items"][0])
    data["items"][0]["id"] = "BUNDLE-ID-909"
    second["id"] = "OTHER-ID-003"
    second["answer"] = 2
    data["items"].append(second)
    parent = run_fixture(tmp_path / "parent", data, brief.model_dump())
    exam = tmp_path / "exam"
    exam.mkdir()
    rows = []
    for number, item in zip([23, 7], data["items"]):
        view = run_fixture(exam / "items" / str(number), {"design_summary": "편집 뷰", "items": [item]},
                           brief.model_dump(), parent=parent)
        rows.append({"number": number, "id": item["id"], "run": str(view),
                     "parent_run": str(parent), "state": "awaiting_human_review"})
    write(exam / "assembled.json", {"exam": "leet", "subject": "추리논증", "items": rows})
    return exam


def response_file(packet, tmp_path, *, origin="human"):
    response = read(packet / "review" / "response.json")
    response.update(reviewer="합성 검토자", origin=origin)
    response["items"][0].update(completed=True, prior_answer_seen=False, answer=1,
                                  solve_seconds=12.5, edit_seconds=None)
    path = tmp_path / "response.json"
    write(path, response)
    return path


def test_new_packet_freezes_sources_and_separates_public_content(tmp_path, source):
    before = {path: path.read_bytes() for path in source.iterdir()}
    output = tmp_path / "packet"
    result = create_packet(source, output)
    assert result["items"] == 1
    assert {path: path.read_bytes() for path in source.iterdir()} == before
    manifest = read(output / "manifest.json")
    assert {Path(ref["path"]).name for ref in manifest["source_files"]} == {"candidate.json", "brief.json"}
    assert manifest["items"][0]["parent_item_content_matches"] is True
    assert manifest["items"][0]["candidate_sha256"] == manifest["items"][0]["parent_candidate_sha256"]
    assert manifest["human_approved"] is manifest["expert_verified"] is manifest["layout_verified"] is False
    public = read(output / "student" / "questions.json")
    item = public["items"][0]
    assert set(item) == {"number", "stem", "passage", "statements", "tables", "options", "figures"}
    public_text = "\n".join(path.read_text() for path in (output / "student").rglob("*") if path.is_file())
    assert str(source) not in public_text
    for private_key in ["answer", "judgments", "source_ids", "originality", "difficulty_basis", "essential_conditions", "parent_run", "candidate.json"]:
        assert f'"{private_key}"' not in public_text
    assert "예약 승인에서 문자 발송이 따른다." not in public_text
    assert "예약 승인에서 문자 발송이 따른다." in (output / "review" / "solutions.html").read_text()
    template = read(output / "review" / "response.json")
    assert template["origin"] is None
    assert template["items"][0]["issues"] is None
    assert template["items"][0]["solve_seconds"] is None
    assert read(output / "review" / "response.schema.json") == ReviewResponse.model_json_schema()
    with pytest.raises(ValueError, match="새 출력"):
        create_packet(source, output)


def test_assembled_printed_numbers_id_reordering_and_links(tmp_path, assembled):
    packet = tmp_path / "packet"
    create_packet(assembled / "assembled.json", packet)
    mapping = read(packet / "manifest.json")["items"]
    assert [(item["number"], item["item_id"]) for item in mapping] == [(7, "OTHER-ID-003"), (23, "BUNDLE-ID-909")]
    html = (packet / "student" / "questions.html").read_text()
    assert "<h2>7." in html and "<h2>23." in html
    assert "<h2>1." not in html and "<h2>909." not in html
    response = response_file(packet, tmp_path)
    data = read(response)
    data["items"].reverse()
    data["items"][0]["issues"] = [{"severity": "A", "location": "선택지 1", "quote": "민수에게 문자가 발송되었다.",
                                   "problem": "합성 지적", "proposed_fix": "합성 수정 제안"}]
    write(response, data)
    result = collect_packet(packet, response)
    receipt = read(Path(result["receipt"]))
    assert [row["number"] for row in receipt["items"]] == [23, 7]
    assert receipt["items"][0]["issues"][0]["severity"] == "A"
    assert receipt["items"][0]["parent_run"] == mapping[1]["parent_run"]
    assert receipt["items"][0]["parent_candidate_sha256"] == mapping[1]["parent_candidate_sha256"]


def test_partial_and_unknown_values_are_preserved_without_certification(tmp_path, assembled):
    packet = tmp_path / "packet"
    create_packet(assembled, packet)
    response = response_file(packet, tmp_path, origin="model")
    data = read(response)
    data["items"] = [data["items"][1]]
    data["items"][0]["completed"] = True
    write(response, data)
    result = collect_packet(packet, response)
    receipt = read(Path(result["receipt"]))
    assert receipt["origin"] == "model"
    assert receipt["partial"] is True
    assert receipt["missing_item_ids"] == ["OTHER-ID-003"]
    assert receipt["completed_items"] == 1
    for field in ["answer", "prior_answer_seen", "solve_seconds", "edit_seconds", "issues"]:
        assert receipt["items"][0][field] is None
    for field in ["human_approved", "expert_verified", "difficulty_validated"]:
        assert receipt[field] is False
    assert receipt["feedback_application_required"] is True


def test_collect_is_byte_preserving_idempotent_and_does_not_update_source(tmp_path, source):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    before = {path: path.read_bytes() for path in source.iterdir()}
    response = response_file(packet, tmp_path)
    first = collect_packet(packet, response)
    destination = Path(first["collection"])
    collected = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in destination.iterdir()}
    second = collect_packet(packet / "manifest.json", response)
    assert first["duplicate"] is False and second["duplicate"] is True
    assert first["collection"] == second["collection"]
    assert destination.name == hashlib.sha256(response.read_bytes()).hexdigest()
    assert (destination / "response.json").read_bytes() == response.read_bytes()
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in destination.iterdir()} == collected
    assert {path: path.read_bytes() for path in source.iterdir()} == before


@pytest.mark.parametrize("mutation", ["number", "id", "duplicate_number", "duplicate_id", "unknown"])
def test_bad_response_mapping_rejected_before_writes(tmp_path, assembled, mutation):
    packet = tmp_path / "packet"
    create_packet(assembled, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    if mutation == "number":
        data["items"][0]["number"] = 23
    elif mutation == "id":
        data["items"][0]["item_id"] = "BUNDLE-ID-909"
    elif mutation == "duplicate_number":
        data["items"].append(copy.deepcopy(data["items"][0]))
    elif mutation == "duplicate_id":
        data["items"][1]["item_id"] = data["items"][0]["item_id"]
    else:
        data["items"][0].update(number=999, item_id="unknown")
    write(response, data)
    with pytest.raises(ValueError, match="번호|ID"):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, "12", True])
def test_invalid_elapsed_time_is_not_coerced(tmp_path, source, value):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    data["items"][0]["solve_seconds"] = value
    write(response, data)
    with pytest.raises(ValueError):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()


@pytest.mark.parametrize("change", [
    {"origin": None}, {"origin": "expert"}, {"reviewer": "  "}, {"extra": "ignored?"},
])
def test_submission_requires_explicit_origin_and_strict_fields(tmp_path, source, change):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    data.update(change)
    write(response, data)
    with pytest.raises(ValueError):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()


@pytest.mark.parametrize("field,value", [("answer", "1"), ("answer", True), ("answer", 6),
                                          ("completed", "true"), ("prior_answer_seen", 0),
                                          ("edit_seconds", -1), ("option_reasoning", {"6": "근거"}),
                                          ("option_reasoning", {"1": "   "})])
def test_response_item_types_are_strict(tmp_path, source, field, value):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    data["items"][0][field] = value
    write(response, data)
    with pytest.raises(ValueError):
        collect_packet(packet, response)


def test_stale_parent_candidate_fails_without_collection_writes(tmp_path, assembled):
    packet = tmp_path / "packet"
    create_packet(assembled, packet)
    response = response_file(packet, tmp_path)
    parent = Path(read(packet / "manifest.json")["items"][0]["parent_run"])
    candidate = read(parent / "candidate.json")
    candidate["items"][0]["passage"] += " 원본 변경"
    write(parent / "candidate.json", candidate)
    with pytest.raises(ValueError, match="원본 source/parent 해시"):
        collect_packet(packet, response, tmp_path / "custom-collections")
    assert not (tmp_path / "custom-collections").exists()


def test_view_mismatch_is_rejected_before_packet_creation(tmp_path, assembled):
    row = read(assembled / "assembled.json")["items"][0]
    candidate_path = Path(row["run"]) / "candidate.json"
    candidate = read(candidate_path)
    candidate["items"][0]["answer"] = 4
    write(candidate_path, candidate)
    with pytest.raises(ValueError, match="편집 뷰·parent 문항 내용"):
        create_packet(assembled, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("field", ["number", "id"])
def test_assembled_duplicate_identity_is_rejected(tmp_path, assembled, field):
    data = read(assembled / "assembled.json")
    data["items"][1][field] = data["items"][0][field]
    write(assembled / "assembled.json", data)
    with pytest.raises(ValueError, match="중복"):
        create_packet(assembled, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("target", ["student/questions.html", "review/solutions.json", "manifest.json", "review/response.schema.json"])
def test_packet_tampering_rejected_before_collection(tmp_path, source, target):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path)
    path = packet / target
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="해시"):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()


def test_wrong_manifest_and_extra_public_files_are_rejected(tmp_path, source):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    data["manifest_sha256"] = "0" * 64
    write(response, data)
    with pytest.raises(ValueError, match="manifest 해시"):
        collect_packet(packet, response)
    response = response_file(packet, tmp_path)
    (packet / "student" / "untracked.txt").write_text("extra")
    with pytest.raises(ValueError, match="학생 폴더 파일 목록"):
        collect_packet(packet, response)


def test_psat_route_accepted_and_reading_explicitly_unsupported(tmp_path, draft, brief):
    for exam in ["psat5", "psat7"]:
        data = draft.model_dump()
        data["items"][0]["subject"] = "자료해석"
        route = {**brief.model_dump(), "exam": exam, "subject": "자료해석"}
        run = run_fixture(tmp_path / exam, data, route)
        create_packet(run, tmp_path / f"{exam}-packet")
    write(tmp_path / "book.json", {"exam": "leet", "subject": "언어이해"})
    with pytest.raises(ValueError, match="언어이해 book"):
        create_packet(tmp_path / "book.json", tmp_path / "unsupported")


def test_real_render_assets_are_portable_and_internal_receipts_excluded(tmp_path, source):
    pytest.importorskip("matplotlib")
    data = read(source / "candidate.json")
    data["items"][0]["figures"] = [{
        "id": "chart", "placement": "passage", "kind": "bar", "title": "Values",
        "x_label": "Category", "y_label": "Count", "categories": ["A", "B"],
        "series": [{"name": "Series", "values": [1, 2]}], "nodes": [], "edges": [],
        "note": "Printed note", "layout_note": "SECRET-PROVENANCE-INTERNAL"}]
    write(source / "candidate.json", data)
    packet = tmp_path / "packet"
    create_packet(source, packet)
    asset = packet / "student" / "assets" / "1" / "figure-01.png"
    assert asset.is_file() and asset.with_suffix(".svg").is_file()
    assert not asset.with_suffix(".json").exists()
    public_json = read(packet / "student" / "questions.json")
    assert "layout_note" not in public_json["items"][0]["figures"][0]
    assert "assets/1/figure-01.png" in (packet / "student" / "questions.html").read_text()
    assert "SECRET-PROVENANCE-INTERNAL" not in asset.with_suffix(".svg").read_text()
    files = {row["path"] for row in read(packet / "manifest.json")["files"]}
    assert "student/assets/1/figure-01.png" in files
    assert "student/assets/1/figure-01.svg" in files
    response = response_file(packet, tmp_path)
    collect_packet(packet, response)
    asset.write_bytes(asset.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="파일 해시"):
        collect_packet(packet, response)


def test_duplicate_json_keys_are_rejected(tmp_path, source):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path)
    response.write_text(response.read_text().replace('"origin": "human"', '"origin": "human", "origin": "model"'))
    with pytest.raises(ValueError, match="중복 JSON 키"):
        collect_packet(packet, response)


def test_workflow_status_changes_do_not_stale_other_reviewers(tmp_path, assembled):
    packet = tmp_path / "packet"
    create_packet(assembled, packet)
    response = response_file(packet, tmp_path)
    mapping = read(packet / "manifest.json")["items"][0]
    parent_status = Path(mapping["parent_run"]) / "status.json"
    state = read(parent_status)
    state["state"] = "needs_revision"
    write(parent_status, state)
    assert collect_packet(packet, response)["duplicate"] is False
    state["state"] = "another_review_completed"
    write(parent_status, state)
    assert collect_packet(packet, response)["duplicate"] is True
    # Parent identity is still checked, even though workflow status is mutable.
    view_status = Path(mapping["run"]) / "status.json"
    state = read(view_status)
    state["parent_review_run"] = str(tmp_path / "wrong-parent")
    write(view_status, state)
    with pytest.raises(ValueError, match="parent_run 불일치"):
        collect_packet(packet, response)


@pytest.mark.parametrize("field,value", [("origin", "human"), ("completed_items", 100),
                                          ("expert_verified", True), ("reviewer", "다른 사람"),
                                          ("items", []), ("partial", True)])
def test_idempotence_revalidates_receipt_semantics(tmp_path, source, field, value):
    packet = tmp_path / "packet"
    create_packet(source, packet)
    response = response_file(packet, tmp_path, origin="model")
    first = collect_packet(packet, response)
    receipt_path = Path(first["receipt"])
    receipt = read(receipt_path)
    receipt[field] = value
    write(receipt_path, receipt)
    with pytest.raises(ValueError, match="기존 수집 기록"):
        collect_packet(packet, response)


def test_legacy_brief_difficulty_is_preserved_and_only_scope_is_adapted(tmp_path, source):
    brief_path = source / "brief.json"
    brief = read(brief_path)
    brief["difficulty"] = "중하"
    brief["legacy_note"] = "구형 출력용 난도"
    write(brief_path, brief)
    original = brief_path.read_bytes()
    packet = tmp_path / "packet"
    create_packet(source, packet)
    assert brief_path.read_bytes() == original
    frozen = next(ref for ref in read(packet / "manifest.json")["source_files"] if ref["path"] == str(brief_path))
    assert frozen["sha256"] == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("change", [{"exam": "leet", "subject": "자료해석"}, {"exam": "psat9"},
                                    {"count": 2}, {"count": "1"}, {"count": True}])
def test_brief_adapter_still_rejects_bad_scope_or_count(tmp_path, source, change):
    brief_path = source / "brief.json"
    brief = read(brief_path)
    brief.update(change)
    write(brief_path, brief)
    with pytest.raises(ValueError):
        create_packet(source, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()
