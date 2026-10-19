"""Synthetic exact-ID selection and delivery contracts; no model or real questions."""
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from haean.authoring_sources import supplied_source_ids
from haean.corpus import Corpus
from haean.exam_references import bind_exam_references
from haean.pipeline import save
from haean.question_sources import import_questions
from haean.reference_bridge import export
from haean.tracks.core.references import ReferenceIndex, RefRecord, RefQuery
from test_reference_bridge import corpus_data
from test_reference_answers import audit, enrich


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def plan_and_selection(root, reference_id, *, exam="psat5", subject="언어논리"):
    plan = {"exam": exam, "subject": subject, "edition": {"unchanged": True}, "slots": [
        {"number": n, "id": f"slot-{n}", "item_type": "기존 유형", "topic": f"소재 {n}",
         "difficulty": "중", "domain": "기존 영역", "answer_target": n % 5 + 1,
         "shared_passage_id": "pair" if n in (1, 2) else None,
         "custom": {"keep": [n, "보존"]}} for n in range(1, 26 if exam == "psat7" else 41)]}
    path, selection = root / "exam-plan.json", root / "exam-selection.json"
    save(path, plan)
    save(selection, {"schema_version": 1, "usage": "development", "plan_sha256": sha(path), "slots": [
        {"slot_id": "slot-1", "reference_ids": [reference_id], "application": "선지 판단 구조 참고", "match_scope": "형식만 참고"},
        {"slot_id": "slot-2", "reference_ids": [reference_id], "application": "보기 구성 참고", "match_scope": "별도 적용", "gaps": ["직접 일치하는 유형 아님"]},
        {"slot_id": "slot-3", "reference_ids": [], "application": "선택 유보", "match_scope": "없음", "gaps": ["원문 부족"]}]})
    return path, selection


def built_index(data):
    export(data["corpus"], data["selection"], data["out"])
    index_path = data["out"].parent / "index.sqlite"
    with ReferenceIndex(index_path) as index:
        result = index.build(data["out"] / "refs.jsonl")
        assert not result["errors"]
    return index_path


def test_plan_preservation_all_slot_gaps_and_per_slot_application(corpus_data, tmp_path):
    index_path = built_index(corpus_data)
    source_id = corpus_data["rows"][0]["id"]
    plan, selection = plan_and_selection(tmp_path, source_id)
    raw = plan.read_bytes()
    out = tmp_path / "bound"
    new_path = bind_exam_references(plan, index_path, selection, out)
    assert plan.read_bytes() == raw == (out / "source-plan.json").read_bytes()
    assert (out / "selection.json").read_bytes() == selection.read_bytes()
    new = read(new_path)
    for original, updated in zip(read(plan)["slots"], new["slots"]):
        stripped = {k: v for k, v in updated.items() if k != "composition_resolution"}
        assert stripped == original
    first, second = [slot["composition_resolution"]["selected_reference_input"] for slot in new["slots"][:2]]
    assert first["application"] != second["application"]
    assert first["references"] == second["references"]
    assert "application" not in first["references"][0]["source"]
    source = first["references"][0]["source"]
    assert source["official_answer"]["answer"] is None
    assert source["official_answer"]["answer_verified"] is False
    assert supplied_source_ids({"references": [], "exam_assignment": new["slots"]}) == {source_id}
    coverage = read(out / "coverage.json")
    assert coverage["total_slots"] == 40 and coverage["attached_slots"] == 2 and coverage["gap_slots"] == 38
    assert coverage["new_reference_uses"] == coverage["plan_reference_uses"] == 2
    assert coverage["new_unique_reference_count"] == coverage["plan_unique_reference_count"] == 1
    assert coverage["existing_preserved_slots"] == 0
    assert coverage["slots"][2]["gaps"] == ["원문 부족", "명시적으로 선택한 참고가 없습니다."]
    assert all(row["status"] == "gap" for row in coverage["slots"][2:])
    # Delivery depends on copied bytes, not mutable corpus/index/original PDFs.
    corpus_data["pdf"].unlink()
    corpus_data["packet"].unlink()
    index_path.unlink()
    shutil.rmtree(corpus_data["out"])
    assert supplied_source_ids({"references": [], "exam_assignment": new["slots"]}) == {source_id}
    for ref in source["evidence_files"].values():
        assert sha(ref["path"]) == ref["sha256"]


@pytest.mark.parametrize("grade", [5, 7])
@pytest.mark.parametrize("subject,track", [("언어논리", "psat_verbal"), ("자료해석", "psat_data"), ("상황판단", "psat_situation")])
def test_actual_corpus_transcription_for_both_grades_all_subjects(corpus_data, tmp_path, grade, subject, track):
    packet = read(corpus_data["packet"])
    for item in packet["items"]:
        item["subject"] = subject
    save(corpus_data["packet"], packet)
    corpus_data["corpus"] = tmp_path / "new-corpus.sqlite"
    corpus = Corpus(corpus_data["corpus"])
    try:
        import_questions(corpus, corpus_data["packet"])
        row = dict(corpus.db.execute("SELECT * FROM records WHERE exam=?", (f"psat{grade}",)).fetchone())
    finally:
        corpus.db.close()
    save(corpus_data["selection"], {"schema_version": 1, "usage": "development", "records": [
        {"id": row["id"], "track": track, "grade": grade, "usage": "development"}]})
    index_path = built_index(corpus_data)
    plan, selection = plan_and_selection(tmp_path, row["id"], exam=f"psat{grade}", subject=subject)
    result = read(bind_exam_references(plan, index_path, selection, tmp_path / "bound"))
    selected = result["slots"][0]["composition_resolution"]["selected_reference_input"]["references"][0]
    assert selected["student"]["passage"] == packet["items"][0]["passage"]
    assert selected["source"]["grade"] == grade and selected["source"]["track"] == track
    assert len(read(tmp_path / "bound" / "coverage.json")["slots"]) == (25 if grade == 7 else 40)


@pytest.mark.parametrize("change", ["duplicate_slot", "duplicate_ref", "unknown_slot", "missing_ref", "grade", "subject", "sha", "stale_source", "forged_row"])
def test_preflight_rejects_ambiguous_stale_or_wrong_identity(corpus_data, tmp_path, change):
    index_path = built_index(corpus_data)
    plan, selection = plan_and_selection(tmp_path, corpus_data["rows"][0]["id"])
    value, original = read(selection), read(plan)
    if change == "duplicate_slot": value["slots"].append(value["slots"][0])
    if change == "duplicate_ref": value["slots"][0]["reference_ids"] *= 2
    if change == "unknown_slot": value["slots"][0]["slot_id"] = "absent"
    if change == "missing_ref": value["slots"][0]["reference_ids"] = ["absent"]
    if change == "grade":
        original["exam"], original["slots"] = "psat7", original["slots"][:25]
    if change == "subject": original["subject"] = "자료해석"
    if change in {"grade", "subject"}:
        save(plan, original)
        value["plan_sha256"] = sha(plan)
    if change == "sha": value["plan_sha256"] = "0" * 64
    if change == "stale_source": corpus_data["pdf"].write_bytes(b"changed")
    if change == "forged_row":
        with ReferenceIndex(index_path) as index:
            index.db.execute("UPDATE track_refs SET item_type='forged' WHERE grade=5")
            index.db.commit()
    save(selection, value)
    before = plan.read_bytes()
    with pytest.raises(ValueError):
        bind_exam_references(plan, index_path, selection, tmp_path / "bound")
    assert plan.read_bytes() == before
    assert not (tmp_path / "bound").exists()


def test_preserves_existing_selection_and_refuses_overwrite(corpus_data, tmp_path):
    index_path = built_index(corpus_data)
    plan, selection = plan_and_selection(tmp_path, corpus_data["rows"][0]["id"])
    attached = bind_exam_references(plan, index_path, selection, tmp_path / "first")
    value = read(selection)
    value["plan_sha256"] = sha(attached)
    save(selection, value)
    with pytest.raises(ValueError, match="기존.*덮어쓰지"):
        bind_exam_references(attached, index_path, selection, tmp_path / "replace")
    value["slots"] = [value["slots"][2]]
    save(selection, value)
    next_path = bind_exam_references(attached, index_path, selection, tmp_path / "preserved")
    assert read(attached) == read(next_path)
    assert read(tmp_path / "preserved" / "coverage.json")["slots"][0]["status"] == "existing_preserved"


def test_exact_ids_beyond_search_limit_share_payload_and_file_checks(tmp_path):
    source = tmp_path / "synthetic.txt"
    source.write_text("synthetic bytes")
    rows = [RefRecord(id=f"ref-{i:03d}", track="leet_reasoning", role="item", text="synthetic text",
                      provenance={"file": str(source), "sha256": sha(source), "locator": str(i), "usage": "development"})
            for i in range(75)]
    refs = tmp_path / "refs.jsonl"
    refs.write_text("\n".join(row.model_dump_json() for row in rows))
    with ReferenceIndex(tmp_path / "index.sqlite") as index:
        assert index.build(refs)["indexed"] == 75
        assert "ref-074" not in {r["id"] for r in index.search(RefQuery(track="leet_reasoning", k=50))["hits"]}
        assert index.select_ids(track="leet_reasoning", grade=None, ids=["ref-074"])[0].id == "ref-074"
        with pytest.raises(ValueError, match="중복"):
            index.select_ids(track="leet_reasoning", grade=None, ids=["ref-074", "ref-074"])
        index.db.execute("UPDATE track_refs SET year=2000 WHERE id='ref-074'")
        with pytest.raises(ValueError, match="저장 본문"):
            index.select_ids(track="leet_reasoning", grade=None, ids=["ref-074"])
        index.db.rollback()
        source.write_text("changed")
        with pytest.raises(ValueError, match="SHA256"):
            index.select_ids(track="leet_reasoning", grade=None, ids=["ref-074"])


def test_verified_official_answer_is_bound_without_invented_explanation(audit, tmp_path):
    assert enrich(audit)["exported"] == 2
    index_path = tmp_path / "index.sqlite"
    with ReferenceIndex(index_path) as index:
        assert index.build(audit["new"] / "refs.jsonl")["indexed"] == 2
    source_id = audit["rows"][0]["id"]
    plan, selection = plan_and_selection(tmp_path, source_id)
    result = read(bind_exam_references(plan, index_path, selection, tmp_path / "bound"))
    selected = result["slots"][0]["composition_resolution"]["selected_reference_input"]["references"][0]
    assert selected["source"]["official_answer"]["answer"] == 2
    assert selected["source"]["official_answer"]["answer_verified"] is True
    assert selected["source"]["official_answer"]["evidence"]
    assert "answer" not in selected["student"] and "explanation" not in selected["student"]
    forged = copy.deepcopy(result)
    forged["slots"][0]["composition_resolution"]["selected_reference_input"]["references"][0]["source"]["official_answer"]["answer"] = 5
    with pytest.raises(ValueError, match="content mismatch"):
        supplied_source_ids({"references": [], "exam_assignment": forged["slots"]})


@pytest.mark.parametrize("kind", ["complete", "raw_text", "case", "native", "student_answer"])
def test_leet_requires_explicit_complete_student_without_native_conversion(tmp_path, kind):
    source = tmp_path / "synthetic.txt"
    source.write_text("synthetic source")
    student = {"stem": "합성 발문", "passage": "합성 지문", "choices": [
        {"number": n, "text": f"선지 {n}"} for n in range(1, 6)]}
    if kind == "student_answer": student["answer"] = 2
    record = RefRecord(id="explicit-leet", track="leet_reasoning", role="case" if kind == "case" else "item",
        text="raw text only" if kind == "raw_text" else json.dumps({"student": student}, ensure_ascii=False),
        item={"passage": [{"kind": "문단", "text": "native"}]} if kind == "native" else None,
        answer=3, answer_verified=False,
        provenance={"file": str(source), "sha256": sha(source), "locator": "synthetic", "usage": "development"})
    refs, index_path = tmp_path / "refs.jsonl", tmp_path / "index.sqlite"
    refs.write_text(record.model_dump_json() + "\n")
    with ReferenceIndex(index_path) as index:
        assert index.build(refs)["indexed"] == 1
    plan, selection = plan_and_selection(tmp_path, record.id, exam="leet", subject="추리논증")
    if kind == "complete":
        result = read(bind_exam_references(plan, index_path, selection, tmp_path / "bound"))
        reference = result["slots"][0]["composition_resolution"]["selected_reference_input"]["references"][0]
        assert reference["student"] == student
        assert reference["source"]["official_answer"]["answer"] is None
    else:
        with pytest.raises(ValueError):
            bind_exam_references(plan, index_path, selection, tmp_path / "bound")
        assert not (tmp_path / "bound").exists()


def test_same_reference_can_extend_existing_plan_only_with_equal_source_identity(corpus_data, tmp_path):
    index_path = built_index(corpus_data)
    source_id = corpus_data["rows"][0]["id"]
    plan, selection = plan_and_selection(tmp_path, source_id)
    first = bind_exam_references(plan, index_path, selection, tmp_path / "first")
    next_selection = read(selection)
    next_selection["plan_sha256"] = sha(first)
    next_selection["slots"] = [{"slot_id": "slot-4", "reference_ids": [source_id],
                                "application": "다른 슬롯에서 재사용", "match_scope": "동일한 원문"}]
    save(selection, next_selection)
    second = bind_exam_references(first, index_path, selection, tmp_path / "second")
    first_value, second_value = read(first), read(second)
    assert first_value["slots"][:3] == second_value["slots"][:3]
    original = first_value["slots"][0]["composition_resolution"]["selected_reference_input"]["references"][0]
    added = second_value["slots"][3]["composition_resolution"]["selected_reference_input"]["references"][0]
    assert added == original
    assert supplied_source_ids({"references": [], "exam_assignment": second_value["slots"]}) == {source_id}
    # A resealed existing packet still must agree with the currently selected
    # index record's complete student/source/answer identity, not merely its ID.
    original["source"]["official_answer"]["answer"] = 5
    block = first_value["slots"][0]["composition_resolution"]["selected_reference_input"]
    ref_packet = Path(block["packet_path"])
    value = read(ref_packet)
    value["references"] = [original]
    save(ref_packet, value)
    for slot in first_value["slots"][:2]:
        block = slot["composition_resolution"]["selected_reference_input"]
        block["references"] = [original]
        block["packet_sha256"] = sha(ref_packet)
    save(first, first_value)
    next_selection["plan_sha256"] = sha(first)
    save(selection, next_selection)
    with pytest.raises(ValueError, match="이번 색인의.*다릅니다"):
        bind_exam_references(first, index_path, selection, tmp_path / "conflict")
    assert not (tmp_path / "conflict" / "plan.json").exists()


@pytest.mark.parametrize("legacy_metadata", [None, "기존 메모", ["legacy"]])
def test_unselected_legacy_resolution_metadata_is_preserved(corpus_data, tmp_path, legacy_metadata):
    index_path = built_index(corpus_data)
    plan, selection = plan_and_selection(tmp_path, corpus_data["rows"][0]["id"])
    value = read(plan)
    value["slots"][-1]["composition_resolution"] = legacy_metadata
    save(plan, value)
    selected = read(selection)
    selected["plan_sha256"] = sha(plan)
    save(selection, selected)
    new = read(bind_exam_references(plan, index_path, selection, tmp_path / "bound"))
    assert new["slots"][-1] == value["slots"][-1]
