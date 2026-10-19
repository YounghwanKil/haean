"""Synthetic books only: native identity, shared context and exact provenance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from haean import novelty, reading_novelty as rn, reading_production as rp
from haean.source_resolution import resolve_source


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def book(count=1, *, prefix="", ids=True):
    passages = []
    for i in range(count):
        questions = []
        for j in range(3):
            question = {"number": 3 * i + j + 1, "stem": "가상 이론의 조건을 달리 적용하면 어떻게 되는가?",
                        "options": [f"항목 {k}은 서로 다른 가상 판단이다." for k in range(5)],
                        "answer": j + 1, "cognitive_task": rp.TASKS[j], "difficulty": "중",
                        "explanation": "합성 규칙의 적용 범위를 확인한 다음 문장에 명시된 기준에 따라 판단한다.",
                        "option_explanations": [f"합성 조건 {k}의 역할이 다르기 때문에 이 선택지를 판단한다." for k in range(5)],
                        "strongest_counterreading": "조건을 확대하는 해석은 본문에 나타난 제한에 따라 배제한다."}
            if ids:
                question["id"] = f"{prefix}q{3*i+j+1}"
            questions.append(question)
        passage = {"title": "합성 지문의 제목", "domain": "합성 영역", "sources": ["자체 완결 가상 이론"],
                   "paragraphs": ["가상의 이론에서 기록은 조건이 충족될 때에만 공개된다. 공개 시점과 기록 시점은 구별한다. 반복 검사를 위한 합성 지문이다."],
                   "questions": questions}
        if ids:
            passage["id"] = f"{prefix}p{i}"
        passages.append(passage)
    return {"title": "합성 언어이해", "minutes": 70, "human_approved": False, "passages": passages}


def plan(count=1):
    value = book(count)
    return {"version": 1, "mode": "full" if count == 10 else "pilot", "title": value["title"], "minutes": value["minutes"],
            "passages": [{"id": p["id"], "domain": p["domain"], "topic": "합성 주제", "structure": "가설과 반례",
                          "sources": p["sources"], "questions": [{k: q[k] for k in ("id", "number", "cognitive_task", "difficulty")}
                                                                 for q in p["questions"]]} for p in value["passages"]]}


def checked(tmp_path, count=1):
    run = tmp_path / "production"
    rp.prepare(save(tmp_path / "plan.json", plan(count)), run)
    reports = []
    for i, passage in enumerate(book(count)["passages"]):
        draft = {**book(), "passages": [passage]}
        reports.append(rp.check(run, passage["id"], save(tmp_path / f"draft-{i}.json", draft)))
    return run, reports


def complete(tmp_path, run, reports):
    for report in reports:
        response = json.loads(Path(report["blind_template"]).read_text())
        response["producer"].update(reviewer="합成 풀이자", requested_model=None, actual_model=None)
        for i, row in enumerate(response["answers"]):
            row.update(answer=i+1, unique=True, reasoning="합성 문면 근거")
        ready = rp.editor_prepare(run, report["passage_id"], save(tmp_path / "blind.json", response))
        editor = json.loads(Path(ready["editor_template"]).read_text())
        editor["producer"].update(reviewer="합성 편집자", requested_model=None, actual_model=None)
        editor.update(issues=[], summary="합성 검토")
        rp.review_result(run, report["passage_id"], save(tmp_path / "editor.json", editor))


@pytest.mark.parametrize("count", [1, 9, 10])
def test_native_book_and_folder_preserve_whole_sets(tmp_path, count):
    value = book(count)
    path = save(tmp_path / "input" / "book.json", value)
    rows = novelty.records([path])
    assert rows == novelty.records([path.parent]) == rn.records(path)
    assert len(rows) == count * 3
    for i, row in enumerate(rows):
        item = row["item"]
        assert rn.is_reading(item) and rn.validate_item(item) == item
        assert item["id"] == f"q{i+1}" and item["identity_scope"] == "author_id"
        assert item["passage"] == value["passages"][i//3]
        assert rn.question(item) == value["passages"][i//3]["questions"][i%3]
        assert item["provenance"]["question_locator"] == f"/passages/{i//3}/questions/{i%3}"
        assert item["provenance"]["book_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert row["sha256"] == novelty.digest(item)
        assert resolve_source(row["source"], item)["status"] == "verified_origin"


def test_book_passage_selection_and_duplicate_import(tmp_path):
    path = save(tmp_path / "book.json", book(2))
    assert [r["item"]["id"] for r in novelty.records([path], passage_id="p1")] == ["q4", "q5", "q6"]
    assert len(novelty.records([path, path.parent])) == 6
    with pytest.raises(ValueError, match="없는 지문"):
        novelty.records([path], passage_id="missing")
    changed = book(2)
    changed["passages"][0]["questions"][1]["explanation"] += " 수정."
    with pytest.raises(ValueError, match="Conflicting"):
        novelty.records([path, save(tmp_path / "other.json", changed)])


def test_sibling_edits_change_all_three_content_hashes_other_sets_only_provenance(tmp_path):
    path = save(tmp_path / "book.json", book(2))
    before = novelty.records([path])
    changed = book(2)
    changed["passages"][0]["questions"][1]["explanation"] += " 수정된 형제 문항 해설."
    save(path, changed)
    after = novelty.records([path])
    assert all(a["item"]["id"] == b["item"]["id"] for a, b in zip(before, after))
    assert all(a["sha256"] != b["sha256"] for a, b in zip(before, after))
    assert all(a["item"]["content_sha256"] != b["item"]["content_sha256"] for a, b in zip(before[:3], after[:3]))
    assert all(a["item"]["content_sha256"] == b["item"]["content_sha256"] for a, b in zip(before[3:], after[3:]))
    db = tmp_path / "generated.sqlite"
    novelty.remember(db, before)
    result = novelty.remember(db, after)
    assert result["current_items"] == 6 and result["versions"] == 12
    retrieved = novelty.memory_get(db, "leet", "언어이해", ["q1"], all_versions=True)
    assert {r["source_resolution"]["status"] for r in retrieved["items"]} == {"unresolved", "verified_origin"}
    same_lineage = novelty.audit([after[0]], [before[0]])
    assert same_lineage["items"][0]["neighbors"] == []


def test_old_book_ids_are_version_scoped_without_invented_lineage(tmp_path):
    value = book(ids=False)
    path = save(tmp_path / "book.json", value)
    old = rn.records(path)
    assert all(r["item"]["identity_scope"] == "book_version" for r in old)
    assert old[0]["item"]["id"] == f"reading:{hashlib.sha256(path.read_bytes()).hexdigest()}:p0:q0"
    value["passages"][0]["paragraphs"][0] += " 추가."
    save(path, value)
    new = rn.records(path)
    assert {r["item"]["id"] for r in old}.isdisjoint(r["item"]["id"] for r in new)


def test_same_content_copied_paths_have_separate_provenance_versions(tmp_path):
    left = rn.records(save(tmp_path / "left.json", book()))
    right = rn.records(save(tmp_path / "right.json", book()))
    assert left[0]["item"]["content_sha256"] == right[0]["item"]["content_sha256"]
    assert left[0]["sha256"] != right[0]["sha256"]


@pytest.mark.parametrize("mutation", ["empty", "too_many", "questions", "bool_answer", "number_gap", "unknown", "duplicate_id", "duplicate_key"])
def test_malformed_books_fail_closed(tmp_path, mutation):
    value = book()
    if mutation == "empty": value["passages"] = []
    elif mutation == "too_many": value = book(11)
    elif mutation == "questions": value["passages"][0]["questions"].pop()
    elif mutation == "bool_answer": value["passages"][0]["questions"][0]["answer"] = True
    elif mutation == "number_gap": value["passages"][0]["questions"][2]["number"] = 5
    elif mutation == "unknown": value["passages"][0]["diagram"] = "unrendered"
    elif mutation == "duplicate_id": value["passages"][0]["questions"][1]["id"] = "q1"
    path = save(tmp_path / "book.json", value)
    if mutation == "duplicate_key": path.write_text('{"passages":[],"passages":[]}')
    with pytest.raises(ValueError): novelty.records([path])


@pytest.mark.parametrize("field,value", [("selected_question_index", True), ("identity_scope", "inferred"),
                                         ("content_sha256", "0" * 64), ("id", "invented")])
def test_retained_payload_not_accepted_by_marker_alone(tmp_path, field, value):
    row = rn.records(save(tmp_path / "book.json", book()))[0]
    row["item"][field] = value
    row["sha256"] = novelty.digest(row["item"])
    with pytest.raises(ValueError): novelty.remember(tmp_path / "db.sqlite", [row])
    assert not (tmp_path / "db.sqlite").exists()


def test_record_hash_exam_and_source_cannot_be_relabeled(tmp_path):
    row = rn.records(save(tmp_path / "book.json", book()))[0]
    for key, value in [("exam", "psat7"), ("subject", "추리논증"), ("source", "elsewhere"), ("sha256", "bad")]:
        invalid = dict(row, **{key: value})
        with pytest.raises(ValueError): novelty.remember(tmp_path / "db.sqlite", [invalid])


def test_native_memory_cards_and_mixed_subject_history(tmp_path):
    rows = rn.records(save(tmp_path / "book.json", book()))
    ordinary = {"exam": "leet", "subject": "추리논증", "source": "synthetic",
                "item": {"id": "q1", "passage": "별개 추리 지문", "cognitive_task": "추리 과제", "essential_conditions": [],
                         "explanation": "추리 해설", "options": [{"text": str(i)} for i in range(5)], "tables": []}}
    ordinary["sha256"] = novelty.digest(ordinary["item"])
    db = tmp_path / "db.sqlite"
    novelty.remember(db, [*rows, ordinary])
    card = novelty.memory_index(db, "leet", "언어이해")["items"][0]
    assert card["number"] == 1 and card["domain"] == "합성 영역"
    assert card["source_resolution"]["status"] == "not_checked" and "essential_conditions" not in card
    assert novelty.memory_index(db, "leet", "추리논증")["total_items"] == 1
    findings = novelty.audit(rows, novelty.history(db))
    assert all(hit["previous_item"].get("_format") == rn.FORMAT for row in findings["items"] for hit in row["neighbors"])


def test_intentional_shared_passage_does_not_suppress_reused_question_logic(tmp_path):
    rows = rn.records(save(tmp_path / "book.json", book()))
    same_set = novelty.audit([rows[1]], [rows[0]])["items"][0]["neighbors"][0]
    assert same_set["shared_passage_pair"] and same_set["scores"]["passage"] == 0
    # Same common passage is permitted, but these deliberately reused synthetic
    # explanations and distractor roles must remain review candidates.
    assert same_set["review_candidate"] and same_set["scores"]["reasoning"] > .55
    other = rn.records(save(tmp_path / "other.json", book(prefix="new-")))
    copied = novelty.audit([other[0]], [rows[0]])["items"][0]["neighbors"][0]
    assert not copied["shared_passage_pair"] and copied["scores"]["passage"] == 1


def test_explicit_current_run_and_historical_attempts_keep_numbers_and_context(tmp_path):
    run, reports = checked(tmp_path, 2)
    all_rows = rn.records(run)
    selected = rn.records(run, passage_id="p1")
    candidate = Path(reports[1]["candidate"])
    assert len(all_rows) == 6 and [rn.question(r["item"])["number"] for r in selected] == [4, 5, 6]
    assert selected == rn.records(candidate) == rn.records(candidate.parent)
    old = deepcopy(selected)
    changed = book(2)
    draft = {**changed, "passages": [changed["passages"][1]]}
    draft["passages"][0]["questions"][2]["explanation"] += " 수정."
    rp.check(run, "p1", save(tmp_path / "new.json", draft))
    assert rn.records(candidate) == old
    assert rn.records(run, passage_id="p1")[0]["sha256"] != old[0]["sha256"]
    assert resolve_source(old[0]["source"], old[0]["item"])["status"] == "verified_origin"


def test_incomplete_run_needs_explicit_set_and_capture_covers_selectors(tmp_path):
    run = tmp_path / "production"
    rp.prepare(save(tmp_path / "plan.json", plan(2)), run)
    report = rp.check(run, "p0", save(tmp_path / "draft.json", book()))
    with pytest.raises(ValueError, match="--passage-id"):
        rn.records(run)
    captured = []
    rows = rn.records(run, passage_id="p0", capture=lambda p: captured.append(Path(p)))
    assert len(rows) == 3
    assert run / "passages/p0/current.json" in captured
    assert run / "manifest.json" in captured and run / "plan.json" in captured
    assert Path(report["candidate"]) in captured
    assert Path(report["blind_input"]) in captured


@pytest.mark.parametrize("target", ["candidate", "manifest", "pointer", "plan", "student"])
def test_production_declared_hash_tampering_rejected(tmp_path, target):
    run, reports = checked(tmp_path)
    candidate = Path(reports[0]["candidate"])
    paths = {"candidate": candidate, "manifest": candidate.parent / "manifest.json",
             "pointer": run / "passages/p0/current.json", "plan": run / "plan.json", "student": candidate.parent / "student.json"}
    if target == "pointer":
        pointer = json.loads(paths[target].read_text())
        pointer["manifest_sha256"] = "0" * 64
        save(paths[target], pointer)
    else:
        paths[target].write_bytes(paths[target].read_bytes() + b" ")
    with pytest.raises(ValueError): rn.records(run)


def test_assembly_source_binding_does_not_hide_missing_or_modified_evidence(tmp_path):
    run, reports = checked(tmp_path, 2)
    complete(tmp_path, run, reports)
    assembled = rp.assemble(run, tmp_path / "assembled")
    path = Path(assembled["book"])
    rows = rn.records(path)
    original = rn.records(Path(reports[0]["candidate"]))
    assert rows[0]["item"]["content_sha256"] == original[0]["item"]["content_sha256"]
    assert rows[0]["sha256"] != original[0]["sha256"]
    assert rows[0]["item"]["id"] == original[0]["item"]["id"]
    assert rn.shared_pair(rows[1]["item"], original[0]["item"])
    captured = []
    result = resolve_source(rows[0]["source"], rows[0]["item"], capture=lambda p: captured.append(Path(p)))
    assert result["status"] == "verified_origin"
    assert path.parent / "verification.json" in captured and Path(reports[0]["candidate"]) in captured
    Path(reports[0]["candidate"]).write_bytes(Path(reports[0]["candidate"]).read_bytes() + b" ")
    with pytest.raises(ValueError): rn.records(path)
    assert resolve_source(rows[0]["source"], rows[0]["item"])["status"] == "unresolved"


def test_mutable_book_alias_never_resolves_by_matching_id_alone(tmp_path):
    path = save(tmp_path / "book.json", book())
    row = rn.records(path)[0]
    # Even a whitespace-only raw-source edit is a different bound version.
    path.write_bytes(path.read_bytes() + b" ")
    result = resolve_source(str(path), row["item"])
    assert result["status"] == "unresolved" and result["origin_check"]["status"] == "mismatch"
    assert not result["archive_checks"] and not result["matches"]


def test_same_authored_set_survives_sibling_revision_but_new_ids_do_not(tmp_path):
    path = save(tmp_path / "book.json", book())
    old = rn.records(path)
    value = book()
    value["passages"][0]["questions"][2]["explanation"] += " 형제 수정."
    revised = rn.records(save(path, value))
    assert rn.shared_pair(revised[1]["item"], old[0]["item"])
    value["passages"][0]["questions"][2]["id"] = "new-q3"
    new_authorship = rn.records(save(path, value))
    assert not rn.shared_pair(new_authorship[1]["item"], old[0]["item"])


def test_legacy_adjacent_verification_is_bound_metadata_not_production_approval(tmp_path):
    path = save(tmp_path / "book.json", book(10, ids=False))
    legacy = {"status": "team_preview_ready", "book_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "human_approved": True, "delivery_ready": True, "native_visual_review": {"claimed": True},
              "artifacts": [{"path": "/must/not/be/followed"}]}
    verify = save(path.parent / "verification.json", legacy)
    captures = []
    rows = rn.records(path, capture=lambda p: captures.append(str(p)))
    assert len(rows) == 30 and "/must/not/be/followed" not in captures
    bound = rows[0]["item"]["provenance"]["adjacent_verification"]
    assert bound == {"path": str(verify), "sha256": hashlib.sha256(verify.read_bytes()).hexdigest(),
                     "classification": "legacy_unverified_metadata", "claimed_book_sha256_verified": True}
    assert "assembly" not in rows[0]["item"]["provenance"]
    assert resolve_source(str(path), rows[0]["item"])["status"] == "verified_origin"
    legacy["status"] = "changed"
    save(verify, legacy)
    assert resolve_source(str(path), rows[0]["item"])["status"] == "unresolved"
    legacy["book_sha256"] = "0" * 64
    save(verify, legacy)
    with pytest.raises(ValueError, match="이전 verification.*해시"):
        rn.records(path)


@pytest.mark.parametrize("mutation", ["omit", "duplicate", "outside"])
def test_assembly_rejects_incomplete_or_outside_evidence_without_reading_it(tmp_path, mutation):
    run, reports = checked(tmp_path)
    complete(tmp_path, run, reports)
    assembled = rp.assemble(run, tmp_path / "assembled")
    verification = Path(assembled["verification"])
    value = json.loads(verification.read_text())
    files = value["sets"][0]["source_files"]
    if mutation == "omit": files.pop()
    elif mutation == "duplicate": files[-1] = deepcopy(files[-2])
    else: files[-1]["path"] = str(tmp_path / "private-outside-file")
    save(verification, value)
    captured = []
    with pytest.raises(ValueError):
        rn.records(Path(assembled["book"]), capture=lambda p: captured.append(str(p)))
    assert str(tmp_path / "private-outside-file") not in captured
