"""Synthetic manual-review replay and fresh CLI receipt checks; no model calls."""
import hashlib
import json
from argparse import Namespace

import pytest

from haean.cli import dispatch
from haean.codex_runtime import strict_schema
from haean.models import BlindReview, EditorialReview
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


def test_fresh_attested_flow_hashes_results_without_asking_model(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
    e = external_result(tmp_path, "editor", editor)
    assert "result_sha256" not in json.loads(b.read_text())["evidence"]
    assert accept(tmp_path, b, e) == {"state": "awaiting_human_review", "errors": []}
    receipt = json.loads((tmp_path / "manual-review.json").read_text())
    assert receipt["evidence"]["blind"]["result_sha256"] == json_sha256(blind.model_dump())
    assert "not cryptographic proof" in receipt["evidence"]["blind"]["assurance"]
    assert receipt["candidate_sha256"] == file_sha256(tmp_path / "candidate.json")
    assert json.loads((tmp_path / "status.json").read_text())["human_approved"] is False


def test_changed_student_text_cannot_replay_old_reviews_with_current_sha(tmp_path, draft, brief):
    setup_run(tmp_path, draft, brief)
    blind, editor = results(draft)
    b = external_result(tmp_path, "blind", blind)
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
    e = external_result(tmp_path, "editor", editor, "old-editor.json")
    old_public = json.loads((tmp_path / "blind-input.json").read_text())
    draft.items[0].explanation += " 새로 고친 해설이다."
    check(tmp_path, draft)
    assert json.loads((tmp_path / "blind-input.json").read_text()) == old_public
    b = external_result(tmp_path, "blind", blind)
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
            save(self.trace_dir / "01-blind.input.json", {
                "instructions": instructions, "payload": payload, "model": self.model,
                "schema": strict_schema(schema.model_json_schema()), "images": [],
                "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
            })
            (self.trace_dir / "01-blind.jsonl").write_text('{"type":"turn.completed"}\n')
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
    e = external_result(tmp_path, "editor", editor)
    value = json.loads(e.read_text())
    value["evidence"]["result_sha256"] = json_sha256(value["result"])
    value["result"]["summary"] = "hash를 만든 뒤 바뀐 검토"
    save(e, value)
    with pytest.raises(ValueError, match="review_result_hash_mismatch"):
        accept(tmp_path, b, e)
