"""Synthetic text only: workflow binding, whole-set revision and book compatibility."""
import copy
import json
from pathlib import Path

import pytest

from haean import reading_production as rp
from haean.human_review import create_packet
from haean.reading_human_review import source_data


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def read(path):
    return json.loads(Path(path).read_text())


def plan(count=1, mode="pilot"):
    return {"version": 1, "mode": mode, "title": "합성 언어이해", "minutes": 70,
            "passages": [{"id": f"p{i}", "domain": "합성 영역", "topic": f"가상 소재 {i}", "structure": "가설과 반례",
                          "sources": ["가상 이론; 자체 작성 범위; 현실 사실 확인을 주장하지 않음"],
                          "questions": [{"id": f"q{3*i+j}", "number": 3*i+j,
                                         "cognitive_task": rp.TASKS[j-1], "difficulty": ["하", "중", "상"][j-1]}
                                        for j in range(1, 4)]} for i in range(count)]}


def book(spec, index=0):
    p = spec["passages"][index]
    questions = [{**q, "stem": "합성 발문", "box": "합성 보기", "options": [f"합성 선지 {k}" for k in range(1, 6)],
                  "answer": 2, "explanation": "비공개 해설", "option_explanations": [f"비공개 선지 근거 {k}" for k in range(1, 6)],
                  "strongest_counterreading": "비공개 최강 반대 해석과 배제 근거"} for q in p["questions"]]
    return {"title": spec["title"], "minutes": spec["minutes"], "human_approved": False,
            "passages": [{"id": p["id"], "title": "비공개 지문 제목", "domain": p["domain"],
                          "sources": p["sources"], "paragraphs": ["학생용 합성 지문."], "questions": questions}]}


def prepared(tmp_path, count=1, mode="pilot"):
    spec = plan(count, mode)
    run = tmp_path / "run"
    rp.prepare(save(tmp_path / "plan.json", spec), run)
    return run, spec


def checked(tmp_path, run, spec, index=0):
    p = spec["passages"][index]
    draft = save(tmp_path / f"draft-{index}.json", book(spec, index))
    return rp.check(run, p["id"], draft)


def blind_file(tmp_path, report, *, suffix="", answer=2, unique=True):
    response = read(report["blind_template"])
    response["producer"].update(reviewer="합성 풀이자", requested_model="requested-test", actual_model=None)
    for row in response["answers"]:
        row.update(answer=answer, unique=unique, reasoning="학생용 문면을 근거로 판단함")
    return save(tmp_path / f"blind-{report['passage_id']}-{report['attempt_id']}{suffix}.json", response)


def editor_file(tmp_path, report, *, issues=None, suffix=""):
    response = read(report["editor_template"])
    response["producer"].update(reviewer="합성 편집자", requested_model=None, actual_model=None)
    response.update(issues=issues or [], summary="합성 검토 완료")
    return save(tmp_path / f"editor-{report['passage_id']}-{report['editor_request_id']}{suffix}.json", response)


def complete(tmp_path, run, spec, index=0, *, issues=None):
    checked_report = checked(tmp_path, run, spec, index)
    blind = blind_file(tmp_path, checked_report)
    editor_report = rp.editor_prepare(run, checked_report["passage_id"], blind)
    editorial = editor_file(tmp_path, editor_report, issues=issues)
    return rp.review_result(run, checked_report["passage_id"], editorial), blind, editorial


def issue(level="C", number=None):
    return {"scope": "passage" if number is None else "question", "number": number, "severity": level,
            "location": "합성 지문 1문단", "quote": "합성", "problem": "개선 의견", "proposed_fix": "표현 개선"}


@pytest.mark.parametrize("count,mode", [(1, "pilot"), (9, "pilot"), (10, "full")])
def test_prepare_scope_and_frozen_work(tmp_path, count, mode):
    run, spec = prepared(tmp_path, count, mode)
    report = rp.status(run)
    assert report["question_count"] == count * 3
    assert report["mode"] == mode and not report["human_approved"]
    assert all(s["state"] == "draft_required" for s in report["sets"])
    assert read(run / "plan.json") == spec
    for p in spec["passages"]:
        folder = run / "passages" / p["id"]
        assert read(folder / "writer-task.json")["passage"] == p
        assert read(folder / "candidate.schema.json")["additionalProperties"] is False
    with pytest.raises(ValueError, match="새 출력"):
        rp.prepare(tmp_path / "plan.json", run)


@pytest.mark.parametrize("mutation", ["small_full", "large_pilot", "duplicate", "traversal", "number", "task", "difficulty", "sources", "unknown", "version_bool"])
def test_plan_rejects_invalid_and_unknown(tmp_path, mutation):
    value = plan()
    if mutation == "small_full": value["mode"] = "full"
    elif mutation == "large_pilot": value = plan(10)
    elif mutation == "duplicate": value["passages"][0]["questions"][0]["id"] = "p0"
    elif mutation == "traversal": value["passages"][0]["id"] = "../bad"
    elif mutation == "number": value["passages"][0]["questions"][0]["number"] = 4
    elif mutation == "task": value["passages"][0]["questions"][0]["cognitive_task"] = "로컬 유형"
    elif mutation == "difficulty": value["passages"][0]["questions"][0]["difficulty"] = "보통"
    elif mutation == "sources": value["passages"][0]["sources"] = [" "]
    elif mutation == "unknown": value["answer_quota"] = [1, 2, 3]
    else: value["version"] = True
    with pytest.raises(ValueError):
        rp.prepare(save(tmp_path / "plan.json", value), tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_second_set_keeps_global_numbers_and_student_whitelist(tmp_path):
    run, spec = prepared(tmp_path, 2)
    report = checked(tmp_path, run, spec, 1)
    public = read(report["blind_input"])
    assert set(public) == {"paragraphs", "questions"}
    assert [q["number"] for q in public["questions"]] == [4, 5, 6]
    assert all(set(q) == {"number", "stem", "box", "options"} for q in public["questions"])
    binding = read(Path(report["blind_input"]).parent / "binding.json")
    assert "candidate_sha256" not in binding and "plan_sha256" not in binding
    for path in Path(report["blind_input"]).parent.iterdir():
        assert "비공개" not in path.read_text() and "합성 영역" not in path.read_text()
    with pytest.raises(ValueError, match="1부터"):
        source_data(Path(report["candidate"]))
    binding, entries = source_data(Path(report["candidate"]), expected_numbers=[4, 5, 6])
    assert len(entries) == 3
    assert [row["number"] for row in binding["items"]] == [4, 5, 6]
    assert rp.status(run)["sets"][0]["state"] == "draft_required"


@pytest.mark.parametrize("mutation", ["id", "number", "domain", "task", "difficulty", "counterreading", "title", "unknown", "approved", "duplicate_option", "multiple_sets"])
def test_check_rejects_bad_candidate_without_attempt(tmp_path, mutation):
    run, spec = prepared(tmp_path)
    value = book(spec)
    p, q = value["passages"][0], value["passages"][0]["questions"][0]
    if mutation == "id": q["id"] = "elsewhere"
    elif mutation == "number": q["number"] = 4
    elif mutation == "domain": p["domain"] = "다른 영역"
    elif mutation == "task": q["cognitive_task"] = rp.TASKS[3]
    elif mutation == "difficulty": q["difficulty"] = "상"
    elif mutation == "counterreading": q["strongest_counterreading"] = " "
    elif mutation == "title": p["title"] = ""
    elif mutation == "unknown": p["chart"] = {"data": [1]}
    elif mutation == "approved": value["human_approved"] = True
    elif mutation == "duplicate_option": q["options"][1] = q["options"][0]
    else: value["passages"].append(copy.deepcopy(p))
    with pytest.raises(ValueError):
        rp.check(run, "p0", save(tmp_path / "bad.json", value))
    assert rp.status(run)["sets"][0]["state"] == "draft_required"
    assert not (run / "passages/p0/current.json").exists()


def test_assembly_all_declared_sets_and_existing_packet_compatibility(tmp_path):
    run, spec = prepared(tmp_path, 2)
    first, _, _ = complete(tmp_path, run, spec, issues=[issue()])
    assert first["state"] == "ready_human_review" and first["issue_counts"] == {"A": 0, "B": 0, "C": 1}
    with pytest.raises(ValueError, match="모든 지문"):
        rp.assemble(run, tmp_path / "incomplete")
    complete(tmp_path, run, spec, 1)
    result = rp.assemble(run, tmp_path / "assembled")
    assert result["mode"] == "pilot" and result["question_count"] == 6
    assembly = read(result["verification"])
    assert assembly["scope"] == "pilot_declared_plan" and not assembly["human_approved"]
    assert assembly["sets"][0]["issues"][0]["severity"] == "C"
    assert all(item["source_files"] for item in assembly["sets"])
    packet = create_packet(Path(result["book"]), tmp_path / "packet")
    assert packet["items"] == 6
    assert len(read(tmp_path / "packet/student/questions.json")["passages"]) == 2
    with pytest.raises(ValueError, match="새 출력"):
        rp.assemble(run, tmp_path / "assembled")


def test_full_requires_ten_complete_sets(tmp_path):
    run, spec = prepared(tmp_path, 10, "full")
    complete(tmp_path, run, spec)
    with pytest.raises(ValueError, match="모든 지문"):
        rp.assemble(run, tmp_path / "partial")
    for index in range(1, 10):
        complete(tmp_path, run, spec, index)
    result = rp.assemble(run, tmp_path / "full")
    assert result["passage_count"] == 10 and result["question_count"] == 30
    assert read(result["verification"])["scope"] == "full_declared_plan"


@pytest.mark.parametrize("level", ["A", "B"])
def test_revision_reopens_entire_set_and_preserves_history(tmp_path, level):
    run, spec = prepared(tmp_path)
    prior, blind, editorial = complete(tmp_path, run, spec, issues=[issue(level, 2)])
    assert prior["state"] == "needs_revision"
    old_attempt = Path(prior["candidate"]).parent
    originals = {p: p.read_bytes() for p in old_attempt.rglob("*") if p.is_file()}
    fresh = checked(tmp_path, run, spec)
    assert fresh["attempt_id"] != prior["attempt_id"] and fresh["state"] == "blind_required"
    assert fresh["numbers"] == [1, 2, 3]
    for path, raw in originals.items(): assert path.read_bytes() == raw
    with pytest.raises(ValueError, match="결속"):
        rp.editor_prepare(run, "p0", blind)
    fresh_editor = rp.editor_prepare(run, "p0", blind_file(tmp_path, fresh))
    with pytest.raises(ValueError, match="결속"):
        rp.review_result(run, "p0", editorial)
    final = rp.review_result(run, "p0", editor_file(tmp_path, fresh_editor))
    assert final["state"] == "ready_human_review"


@pytest.mark.parametrize("answer,unique", [(3, True), (None, True), (2, False)])
def test_blind_mismatch_requires_revision(tmp_path, answer, unique):
    run, spec = prepared(tmp_path)
    report = checked(tmp_path, run, spec)
    editor = rp.editor_prepare(run, "p0", blind_file(tmp_path, report, answer=answer, unique=unique))
    assert editor["state"] == "needs_revision"
    assert editor["blind_mismatch_numbers"] == [1, 2, 3]
    final = rp.review_result(run, "p0", editor_file(tmp_path, editor))
    assert final["state"] == "needs_revision"
    with pytest.raises(ValueError): rp.assemble(run, tmp_path / "bad")


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "number", "bool_answer", "blank_reason", "model_mode", "extra", "producer"])
def test_blind_validation(tmp_path, mutation):
    run, spec = prepared(tmp_path)
    report = checked(tmp_path, run, spec)
    path = blind_file(tmp_path, report)
    value = read(path)
    if mutation == "missing": value["answers"].pop()
    elif mutation == "duplicate": value["answers"][1]["number"] = 1
    elif mutation == "number": value["answers"][1]["number"] = 8
    elif mutation == "bool_answer": value["answers"][0]["answer"] = True
    elif mutation == "blank_reason": value["answers"][0]["reasoning"] = " "
    elif mutation == "model_mode": value["producer"]["execution_mode"] = "codex-cli"
    elif mutation == "extra": value["runtime_proof"] = "forged"
    else: value["producer"].pop("actual_model")
    save(path, value)
    with pytest.raises(ValueError): rp.editor_prepare(run, "p0", path)


def test_cross_set_binding_cannot_be_reused(tmp_path):
    run, spec = prepared(tmp_path, 2)
    first = checked(tmp_path, run, spec)
    second = checked(tmp_path, run, spec, 1)
    with pytest.raises(ValueError, match="결속"):
        rp.editor_prepare(run, "p1", blind_file(tmp_path, first))
    forged = read(blind_file(tmp_path, first, suffix="-other"))
    forged["binding"] = read(second["blind_template"])["binding"]
    with pytest.raises(ValueError, match="번호"):
        rp.editor_prepare(run, "p1", save(tmp_path / "forged.json", forged))


@pytest.mark.parametrize("target", ["plan", "candidate", "student", "blind_input", "blind_schema", "blind_instructions", "blind_snapshot", "editor_snapshot", "editor_schema"])
def test_tampered_connection_becomes_stale_and_blocks_assembly(tmp_path, target):
    run, spec = prepared(tmp_path)
    report, blind, editorial = complete(tmp_path, run, spec)
    editor_request = Path(report["editor_input"]).parent
    paths = {"plan": run / "plan.json", "candidate": Path(report["candidate"]),
             "student": Path(report["candidate"]).parent / "student.json", "blind_input": Path(report["blind_input"]),
             "blind_schema": Path(report["blind_schema"]), "blind_instructions": Path(report["blind_instructions"]),
             "blind_source": blind, "blind_snapshot": editor_request.parent / "blind.json", "editor_source": editorial,
             "editor_snapshot": Path(report["editorial_result"]), "editor_schema": Path(report["editor_schema"])}
    path = paths[target]
    path.write_bytes(path.read_bytes() + b" ")
    current = rp.status(run)
    assert current["state"] == "stale" if target == "plan" else current["sets"][0]["state"] == "stale"
    with pytest.raises(ValueError): rp.assemble(run, tmp_path / "tampered")


def test_changed_blind_gets_new_editor_request_old_editor_rejected(tmp_path):
    run, spec = prepared(tmp_path)
    old, blind, editorial = complete(tmp_path, run, spec)
    value = read(blind)
    value["notes"] = "독립 풀이 보충"
    save(blind, value)
    assert rp.status(run)["sets"][0]["state"] == "ready_human_review"
    fresh = rp.editor_prepare(run, "p0", blind)
    assert fresh["editor_request_id"] != old["editor_request_id"]
    assert fresh["state"] == "editor_required"
    with pytest.raises(ValueError, match="결속"): rp.review_result(run, "p0", editorial)
    rp.review_result(run, "p0", editor_file(tmp_path, fresh))
    assert rp.status(run)["state"] == "ready_human_review"


@pytest.mark.parametrize("mutation", ["other_number", "scope", "severity", "blank", "unknown"])
def test_editor_validation(tmp_path, mutation):
    run, spec = prepared(tmp_path)
    first = checked(tmp_path, run, spec)
    report = rp.editor_prepare(run, "p0", blind_file(tmp_path, first))
    path = editor_file(tmp_path, report, issues=[issue("C", 1)])
    value = read(path)
    if mutation == "other_number": value["issues"][0]["number"] = 5
    elif mutation == "scope": value["issues"][0]["scope"] = "passage"
    elif mutation == "severity": value["issues"][0]["severity"] = "OK"
    elif mutation == "blank": value["summary"] = " "
    else: value["human_approved"] = True
    with pytest.raises(ValueError): rp.review_result(run, "p0", save(path, value))
    assert rp.status(run)["sets"][0]["state"] == "editor_required"


def test_ingested_original_paths_can_be_reused_or_deleted(tmp_path):
    run, spec = prepared(tmp_path, 2)
    first, blind, editorial = complete(tmp_path, run, spec)
    blind.write_text("reused for another call")
    editorial.unlink()
    assert rp.status(run)["sets"][0]["state"] == "ready_human_review"
    complete(tmp_path, run, spec, 1)
    assert rp.status(run)["state"] == "ready_human_review"
    assembled = rp.assemble(run, tmp_path / "reused")
    assert assembled["question_count"] == 6
