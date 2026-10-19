"""Synthetic manual-review replay and fresh CLI receipt checks; no model calls."""
import hashlib
import json
from argparse import Namespace
from pathlib import Path

import pytest

from haean.cli import dispatch
from haean.codex_runtime import strict_schema
from haean.models import BlindReview, EditorialReview, Issue
from haean.pipeline import save
from haean.review_evidence import current_binding, file_sha256, json_sha256


def check(run, draft):
    save(run / "input.json", draft.model_dump())
    return dispatch(Namespace(command="check", run=run, draft=run / "input.json"))


def setup_run(run, draft, brief):
    save(run / "brief.json", brief.model_dump())
    save(run / "context.json", {"brief": brief.model_dump(),
                               "references": [{"id": "source-1", "text": "별도 합성 자료"}]})
    assert check(run, draft)["state"] == "awaiting_independent_review"


def results(draft):
    return BlindReview(solutions=[{
        "item_id": item.id, "answer": item.answer, "uniquely_answerable": True,
        "option_reasons": ["합성 검토 근거"] * 5, "missing_conditions": [],
    } for item in draft.items], issues=[]), EditorialReview(issues=[], summary="합성 검토")


def external_result(run, role, result, name=None):
    filename = "editorial" if role == "editor" else role
    envelope = json.loads((run / f"{filename}-review-template.json").read_text())
    envelope["result"] = result.model_dump()
    envelope["evidence"]["producer"].update(reviewer="synthetic-reviewer", requested_model="test-model")
    path = run / (name or f"{filename}-result.json")
    save(path, envelope)
    return path


def accept(run, blind, editor):
    return dispatch(Namespace(command="review-result", run=run, blind=blind, editorial=editor,
                              candidate_sha=file_sha256(run / "candidate.json")))


def prepare_editor(run, blind):
    return dispatch(Namespace(command="editor-prepare", run=run, blind=blind))


def test_fresh_attested_flow_hashes_results_without_asking_model(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepared = prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    assert "result_sha256" not in json.loads(b.read_text())["evidence"]
    assert accept(tmp_path, b, e) == {"state": "awaiting_human_review", "errors": []}
    receipt = json.loads((tmp_path / "manual-review.json").read_text())
    assert receipt["evidence"]["blind"]["result_sha256"] == json_sha256(blind.model_dump())
    assert "not cryptographic proof" in receipt["evidence"]["blind"]["assurance"]
    assert receipt["candidate_sha256"] == file_sha256(tmp_path / "candidate.json")
    binding = receipt["evidence"]["editorial"]["input_binding"]
    assert binding["blind_review"]["snapshot_path"] == prepared["blind_snapshot"]
    assert binding["blind_review"]["file_sha256"] == file_sha256(b)
    assert json.loads((tmp_path / "status.json").read_text())["human_approved"] is False


def test_changed_student_text_cannot_replay_old_reviews_with_current_sha(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    accept(tmp_path, b, e)
    old_receipt = (tmp_path / "manual-review.json").read_bytes()
    old_sha = file_sha256(tmp_path / "candidate.json")
    draft.items[0].passage = "예약이 승인되면 문자가 발송된다. 민수의 예약 승인 여부는 알려져 있지 않다."
    check(tmp_path, draft)
    assert old_sha != file_sha256(tmp_path / "candidate.json")
    with pytest.raises(ValueError, match="review_input_binding_mismatch"):
        accept(tmp_path, b, e)
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "awaiting_independent_review"
    assert (tmp_path / "manual-review.json").read_bytes() == old_receipt


def test_editor_receipt_rejects_changed_private_explanation(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor, "old-editor.json")
    old_public = json.loads((tmp_path / "blind-input.json").read_text())
    draft.items[0].explanation += " 새로 고친 해설이다."
    check(tmp_path, draft)
    assert json.loads((tmp_path / "blind-input.json").read_text()) == old_public
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    with pytest.raises(ValueError, match="review_input_binding_mismatch"):
        accept(tmp_path, b, e)


@pytest.mark.parametrize("legacy_run", [False, True])
def test_raw_or_legacy_evidence_is_rejected_without_rewriting_run(tmp_path, draft, brief, legacy_run):
    setup_run(tmp_path, draft, brief)
    if legacy_run:
        (tmp_path / "review-request.json").unlink()
    blind, editor = results(draft)
    save(tmp_path / "raw-blind.json", blind.model_dump())
    save(tmp_path / "raw-editor.json", editor.model_dump())
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="legacy_missing_review_evidence"):
        accept(tmp_path, tmp_path / "raw-blind.json", tmp_path / "raw-editor.json")
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


@pytest.mark.parametrize("change", ["instructions", "specification", "schema"])
def test_review_binding_detects_changed_contract(tmp_path, draft, brief, monkeypatch, change):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    if change == "instructions":
        from haean import pipeline
        original = pipeline.review_prompt
        monkeypatch.setattr(pipeline, "review_prompt", lambda role, spec: original(role, spec) + " 새 지침")
    elif change == "specification":
        context = json.loads((tmp_path / "context.json").read_text())
        context["exam_assignment"] = [{"id": draft.items[0].id, "difficulty": "상"}]
        save(tmp_path / "context.json", context)
    else:
        from haean import review_evidence
        class NewEditor(EditorialReview):
            additional_check: str = "new"
        monkeypatch.setitem(review_evidence.SCHEMAS, "editor", NewEditor)
    with pytest.raises(ValueError, match="review_binding_changed"):
        accept(tmp_path, b, e)


def test_repeated_check_requires_new_request_even_for_same_bytes(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    old = current_binding(tmp_path, "blind")
    check(tmp_path, draft)
    new = current_binding(tmp_path, "blind")
    assert old["input_sha256"] == new["input_sha256"] and old["request_id"] != new["request_id"]
    with pytest.raises(ValueError, match="review_input_binding_mismatch"):
        accept(tmp_path, b, e)


def fake_provider(monkeypatch, blind, mutate=None):
    class Provider:
        usage = []
        def __init__(self, model, trace_dir):
            self.model, self.trace_dir = model, trace_dir
            trace_dir.mkdir(exist_ok=True)

        def call(self, stage, instructions, payload, schema):
            assert stage == "blind"
            assert not {"answer", "explanation", "judgments", "source_ids"} & payload["items"][0].keys()
            task = instructions + "\n도구·파일 탐색·웹 검색·재위임을 하지 말고 아래 입력만으로 답하라. 최종 출력은 스키마 JSON이다.\n" + json.dumps(payload, ensure_ascii=False)
            prefix = f"{len(list(self.trace_dir.glob('*-blind.input.json'))) + 1:02}-blind"
            save(self.trace_dir / (prefix + ".input.json"), {
                "instructions": instructions, "payload": payload, "model": self.model,
                "schema": strict_schema(schema.model_json_schema()), "images": [],
                "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
            })
            (self.trace_dir / (prefix + ".jsonl")).write_text('{"type":"turn.completed"}\n')
            if mutate:
                mutate(self.trace_dir.parent)
            return blind
    monkeypatch.setattr("haean.cli.CodexProvider", Provider)


def test_cli_blind_receipt_links_actual_request_and_result(tmp_path, draft, brief, monkeypatch):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    fake_provider(monkeypatch, blind)
    dispatch(Namespace(command="blind", run=tmp_path, model="test-model"))
    b = tmp_path / "blind-result.json"
    envelope = json.loads(b.read_text())
    evidence = envelope["evidence"]
    assert evidence["producer"] == {"execution_mode": "codex-cli", "reviewer": "CodexProvider",
                                    "requested_model": "test-model", "actual_model": None}
    assert evidence["result_sha256"] == json_sha256(blind.model_dump())
    assert evidence["execution"]["input"]["sha256"] == file_sha256(tmp_path / "codex-traces/01-blind.input.json")
    e = external_result(tmp_path, "editor", editor)
    assert accept(tmp_path, b, e)["state"] == "awaiting_human_review"
    (tmp_path / "codex-traces/01-blind.jsonl").write_text("changed trace")
    with pytest.raises(ValueError, match="review_trace_mismatch"):
        accept(tmp_path, b, e)


def test_cli_blind_rejects_input_change_during_call(tmp_path, draft, brief, monkeypatch):
    setup_run(tmp_path, draft, brief)
    blind, _ = results(draft)
    def mutate(run):
        changed = draft.model_copy(deep=True)
        changed.items[0].explanation += " 검토 중 변경"
        save(run / "candidate.json", changed.model_dump())
    fake_provider(monkeypatch, blind, mutate)
    with pytest.raises(ValueError, match="review_binding_changed"):
        dispatch(Namespace(command="blind", run=tmp_path, model="test-model"))
    assert not (tmp_path / "blind-result.json").exists()


def test_cli_blind_refuses_stale_or_private_payload_before_model(tmp_path, draft, brief, monkeypatch):
    setup_run(tmp_path, draft, brief)
    payload = json.loads((tmp_path / "blind-input.json").read_text())
    payload["items"][0]["answer"] = 1
    save(tmp_path / "blind-input.json", payload)
    monkeypatch.setattr("haean.cli.CodexProvider", lambda *a, **k: pytest.fail("must not call provider"))
    with pytest.raises(ValueError, match="review_input_binding_mismatch"):
        dispatch(Namespace(command="blind", run=tmp_path, model="test-model"))


def test_runner_result_digest_detects_modified_review(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    value = json.loads(e.read_text())
    value["evidence"]["result_sha256"] = json_sha256(value["result"])
    value["result"]["summary"] = "hash를 만든 뒤 바뀐 검토"
    save(e, value)
    with pytest.raises(ValueError, match="review_result_hash_mismatch"):
        accept(tmp_path, b, e)


def test_check_editor_placeholder_cannot_be_used_as_ready_binding(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    placeholder = json.loads((tmp_path / "editorial-review-template.json").read_text())
    assert placeholder["state"] == "editor_prepare_required" and "evidence" not in placeholder
    assert json.loads((tmp_path / "editorial-review.schema.json").read_text())["not"] == {}
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    # An old v1 check binding cannot become a prepared editor result on import.
    envelope = json.loads(b.read_text())
    envelope["result"] = editor.model_dump()
    envelope["evidence"]["input_binding"] = json.loads((tmp_path / "review-request.json").read_text())["bindings"]["editor"]
    e = tmp_path / "unprepared-editor.json"
    save(e, envelope)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="editor_review_not_prepared"):
        accept(tmp_path, b, e)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_new_blind_same_check_cannot_reuse_old_editor_without_prepare(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind, "first-blind.json")
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    accept(tmp_path, b, e)
    before = (tmp_path / "manual-review.json").read_bytes()
    blind.solutions[0].option_reasons[0] = "다시 수행한 독립 풀이의 근거"
    replacement = external_result(tmp_path, "blind", blind, "replacement-blind.json")
    with pytest.raises(ValueError, match="editor_blind_binding_mismatch"):
        accept(tmp_path, replacement, e)
    assert (tmp_path / "manual-review.json").read_bytes() == before
    assert len(list((tmp_path / "editor-preparations").iterdir())) == 1


@pytest.mark.parametrize("changed_blind", [False, True])
def test_reprepare_requires_new_editor_and_keeps_prior_results(tmp_path, draft, brief, changed_blind):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    first = prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    accept(tmp_path, b, e)
    original = {name: (tmp_path / name).read_bytes()
                for name in ("manual-review.json", "editorial-result.json", "editorial-review-template.json")}
    first_snapshot = Path(first["blind_snapshot"]).read_bytes()
    if changed_blind:
        blind.solutions[0].option_reasons[1] = "새 풀이 근거"
        b = external_result(tmp_path, "blind", blind)
    second = prepare_editor(tmp_path, b)
    assert first["editor_preparation_id"] != second["editor_preparation_id"]
    assert Path(first["blind_snapshot"]).read_bytes() == first_snapshot
    for name, raw in original.items():
        assert raw in [p.read_bytes() for p in (tmp_path / "review-history").glob("*/" + name)]
    with pytest.raises(ValueError, match="review_input_binding_mismatch"):
        accept(tmp_path, b, e)
    fresh_editor = external_result(tmp_path, "editor", editor, "new-editor.json")
    assert accept(tmp_path, b, fresh_editor)["state"] == "awaiting_human_review"


@pytest.mark.parametrize("target", ["source", "snapshot"])
@pytest.mark.parametrize("change", ["bytes_only", "result", "producer"])
def test_prepared_editor_rejects_blind_source_or_snapshot_mutation(tmp_path, draft, brief, target, change):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepared = prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    path = b if target == "source" else Path(prepared["blind_snapshot"])
    if change == "bytes_only":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        value = json.loads(path.read_text())
        if change == "result": value["result"]["solutions"][0]["option_reasons"][0] = "변경된 풀이"
        else: value["evidence"]["producer"]["reviewer"] = "다른 검토자"
        save(path, value)
    before = (tmp_path / "status.json").read_bytes()
    with pytest.raises(ValueError, match="editor_blind_" + target + "_changed"):
        accept(tmp_path, b, e)
    assert (tmp_path / "status.json").read_bytes() == before
    assert not (tmp_path / "manual-review.json").exists()


def test_new_check_preserves_ready_editor_packet_and_requires_prepare_again(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepared = prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    accept(tmp_path, b, e)
    old_template = (tmp_path / "editorial-review-template.json").read_bytes()
    old_result = (tmp_path / "manual-review.json").read_bytes()
    snapshot = Path(prepared["blind_snapshot"]).read_bytes()
    check(tmp_path, draft)
    assert old_template in [p.read_bytes() for p in (tmp_path / "review-history").glob("*/editorial-review-template.json")]
    assert old_result in [p.read_bytes() for p in (tmp_path / "review-history").glob("*/manual-review.json")]
    assert Path(prepared["blind_snapshot"]).read_bytes() == snapshot
    with pytest.raises(ValueError, match="editor_review_not_prepared"):
        current_binding(tmp_path, "editor")


@pytest.mark.parametrize("ids", [[], ["TEST-001", "TEST-001"], ["unknown"]])
def test_editor_prepare_rejects_missing_duplicate_or_unknown_blind_ids(tmp_path, draft, brief, ids):
    setup_run(tmp_path, draft, brief)
    blind, _ = results(draft)
    blind.solutions = [blind.solutions[0].model_copy(update={"item_id": item_id}) for item_id in ids]
    b = external_result(tmp_path, "blind", blind)
    with pytest.raises(ValueError, match="review_item_ids_mismatch"):
        prepare_editor(tmp_path, b)
    assert not (tmp_path / "editor-preparations").exists()


def test_editor_prepare_keeps_disagreement_and_ab_issues_for_gate(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    blind.solutions[0].answer = 2
    blind.solutions[0].uniquely_answerable = False
    blind.solutions[0].missing_conditions = ["합성 조건 부족"]
    blind.issues = [Issue(item_id=draft.items[0].id, severity=severity, category="조건", location="지문",
                          problem="합성 지적", fix="재검토") for severity in ("A", "B")]
    b = external_result(tmp_path, "blind", blind)
    prepared = prepare_editor(tmp_path, b)
    assert json.loads(Path(prepared["blind_snapshot"]).read_text())["result"] == blind.model_dump()
    e = external_result(tmp_path, "editor", editor)
    accepted = accept(tmp_path, b, e)
    assert accepted["state"] == "needs_revision"
    assert any("독립 풀이 불일치" in error for error in accepted["errors"])
    assert any(": A " in error for error in accepted["errors"])
    assert any(": B " in error for error in accepted["errors"])


def test_cli_blind_reexecution_preserves_old_result_and_requires_new_editor(tmp_path, draft, brief, monkeypatch):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    fake_provider(monkeypatch, blind)
    first = dispatch(Namespace(command="blind", run=tmp_path, model="test-model"))
    e = external_result(tmp_path, "editor", editor)
    b = tmp_path / "blind-result.json"
    accept(tmp_path, b, e)
    old_blind, old_review = b.read_bytes(), (tmp_path / "manual-review.json").read_bytes()
    second = dispatch(Namespace(command="blind", run=tmp_path, model="test-model"))
    assert first["editorial"]["editor_preparation_id"] != second["editorial"]["editor_preparation_id"]
    assert Path(first["editorial"]["blind_snapshot"]).read_bytes() == old_blind
    assert old_blind in [p.read_bytes() for p in (tmp_path / "review-history").glob("*/blind-result.json")]
    assert old_review in [p.read_bytes() for p in (tmp_path / "review-history").glob("*/manual-review.json")]
    with pytest.raises(ValueError, match="review_input_binding_mismatch"):
        accept(tmp_path, b, e)
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "awaiting_independent_review"
    e = external_result(tmp_path, "editor", editor, "fresh-editor.json")
    assert accept(tmp_path, b, e)["state"] == "awaiting_human_review"


def test_result_change_during_prepare_is_not_bound_to_parsed_old_result(tmp_path, draft, brief, monkeypatch):
    from haean import review_evidence
    setup_run(tmp_path, draft, brief)
    blind, _ = results(draft)
    b = external_result(tmp_path, "blind", blind)
    original = review_evidence._producer
    def mutate(producer):
        b.write_bytes(b.read_bytes() + b"\n")
        return original(producer)
    monkeypatch.setattr(review_evidence, "_producer", mutate)
    with pytest.raises(ValueError, match="review_result_changed"):
        prepare_editor(tmp_path, b)
    assert not (tmp_path / "editor-preparations").exists()


@pytest.mark.parametrize("name", ["status.json", "editor-review-request.json",
                                  "editorial-review-template.json", "editorial-review.schema.json"])
def test_editor_prepare_refuses_source_output_collision_without_writes(tmp_path, draft, brief, name):
    setup_run(tmp_path, draft, brief)
    blind, _ = results(draft)
    b = external_result(tmp_path, "blind", blind, name)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="editor_blind_path_conflict"):
        prepare_editor(tmp_path, b)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_failed_editor_preparation_after_transition_cannot_leave_prior_approval(tmp_path, draft, brief, monkeypatch):
    from haean import review_evidence
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    accept(tmp_path, b, e)
    save(tmp_path / "status.json", {"state": "awaiting_human_review", "human_approved": True})
    old_status = (tmp_path / "status.json").read_bytes()
    old_review = (tmp_path / "manual-review.json").read_bytes()
    original = review_evidence.current_binding
    def fail_new_editor(run, role):
        if role == "editor":
            raise ValueError("synthetic failure after prepared pointer publication")
        return original(run, role)
    monkeypatch.setattr(review_evidence, "current_binding", fail_new_editor)
    with pytest.raises(ValueError, match="synthetic failure"):
        prepare_editor(tmp_path, b)
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "awaiting_independent_review" and status["human_approved"] is False
    assert (tmp_path / "manual-review.json").read_bytes() == old_review
    assert old_status in [p.read_bytes() for p in (tmp_path / "review-history").glob("*/status.json")]


def test_invalid_blind_before_preparation_does_not_change_prior_state(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    prepare_editor(tmp_path, b)
    e = external_result(tmp_path, "editor", editor)
    accept(tmp_path, b, e)
    invalid = tmp_path / "invalid-blind.json"
    save(invalid, blind.model_dump())
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="legacy_missing_review_evidence"):
        prepare_editor(tmp_path, invalid)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
