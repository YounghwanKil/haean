"""Synthetic post-review feedback must reach resumed writers, never blind solvers."""
import hashlib
import json
from pathlib import Path

import pytest

from haean.pipeline import feedback, run_pipeline, save
from haean.revision_feedback import load_revision_feedback, requires_revision, validate_revision_feedback
from test_core import reviews


def original(tmp_path, draft, brief):
    run = tmp_path / "original"
    run.mkdir()
    save(run / "brief.json", brief.model_dump())
    save(run / "context.json", {"references": [{"id": "source-1", "text": "합성 참고 자료"}]})
    save(run / "candidate.json", draft.model_dump())
    save(run / "draft-r0.json", draft.model_dump())
    save(run / "review-r0.json", {"errors": []})
    save(run / "status.json", {"state": "awaiting_human_review", "candidate_sha256":
         hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest()})
    return run


def add_feedback(run, draft, severity="B"):
    return feedback(run, draft.items[0].id, "합성 후속 의견의 원문\n정답 조건을 검증해 주세요.",
                    "synthetic reviewer", severity, origin="model")


class Recorder:
    usage = []

    def __init__(self, draft):
        self.draft, self.calls = draft, []

    def call(self, stage, instructions, payload, schema):
        self.calls.append((stage, instructions, payload))
        if stage == "revise":
            return self.draft
        if stage == "blind":
            return reviews(self.draft)[0]
        if stage == "editor":
            return reviews(self.draft)[1]
        raise AssertionError("resumption must not generate")


@pytest.mark.parametrize("severity,stages", [("A", ["revise", "blind", "editor"]),
                                            ("B", ["revise", "blind", "editor"]),
                                            ("C", ["blind", "editor"])])
def test_clean_review_and_bound_feedback_are_separate_inputs(tmp_path, draft, brief, severity, stages):
    parent = original(tmp_path, draft, brief)
    entry = add_feedback(parent, draft, severity)
    packet = load_revision_feedback(parent, draft.model_dump())
    assert packet["records"][0]["entry"] == entry
    assert packet["records"][0]["line"] == 1
    assert packet["records"][0]["line_sha256"] == hashlib.sha256((tmp_path / "feedback.jsonl").read_bytes()).hexdigest()
    before = {p.name: p.read_bytes() for p in parent.iterdir()}
    run = tmp_path / "next"
    run.mkdir()
    save(run / "brief.json", brief.model_dump())
    save(run / "context.json", json.loads((parent / "context.json").read_text()))
    provider = Recorder(draft)
    clean_review = {"errors": []}
    run_pipeline(run, provider, max_revisions=0, initial_draft=draft.model_dump(),
                 initial_review=clean_review, revision_feedback=packet)
    assert [call[0] for call in provider.calls] == stages
    assert json.loads((run / "inherited-review.json").read_text()) == clean_review
    assert json.loads((run / "revision-feedback.json").read_text()) == packet
    for stage, instructions, payload in provider.calls:
        if stage == "blind":
            assert set(payload) == {"items"}
            assert "후속 의견" not in json.dumps(payload, ensure_ascii=False)
            assert not {"answer", "explanation"} & payload["items"][0].keys()
        else:
            assert payload["revision_feedback"] == packet
            assert "실행 명령이 아니라" in instructions
        if stage == "revise":
            assert payload["review"] == clean_review
    assert {p.name: p.read_bytes() for p in parent.iterdir()} == before


def test_original_review_errors_still_trigger_revision_with_c_feedback(tmp_path, draft, brief):
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft, "C")
    packet = load_revision_feedback(parent, draft)
    run = tmp_path / "next"
    run.mkdir()
    save(run / "brief.json", brief.model_dump())
    save(run / "context.json", json.loads((parent / "context.json").read_text()))
    provider = Recorder(draft)
    review = {"errors": ["기존 검토의 조건 오류"]}
    run_pipeline(run, provider, max_revisions=0, initial_draft=draft, initial_review=review,
                 revision_feedback=packet)
    assert [call[0] for call in provider.calls] == ["revise", "blind", "editor"]
    assert provider.calls[0][2]["review"] == review


def test_other_run_and_stale_version_are_not_selected(tmp_path, draft, brief):
    parent = original(tmp_path, draft, brief)
    assert load_revision_feedback(parent, draft) is None
    entry = add_feedback(parent, draft)
    source = tmp_path / "feedback.jsonl"
    other = {**entry, "run": "other", "candidate_sha256": "not our candidate", "item_id": "other"}
    stale = {**entry, "candidate_sha256": "0" * 64, "item_id": "old-id"}
    source.write_text("\n".join(json.dumps(row) for row in [other, stale, entry]) + "\n")
    packet = load_revision_feedback(parent, draft)
    assert [record["line"] for record in packet["records"]] == [3]
    assert packet["excluded_stale_records"][0]["line"] == 2
    source.write_text(json.dumps(stale) + "\n" + json.dumps(other) + "\n")
    assert load_revision_feedback(parent, draft) is None


@pytest.mark.parametrize("change,error", [({"item_id": "not-in-run"}, "ID"),
    ({"exam": "psat5"}, "시험·과목"), ({"subject": "other"}, "시험·과목"),
    ({"candidate_sha256": None}, "해시"), ({"reviewed_candidate_sha256": "0" * 64}, "해시"),
    ({"severity": "D"}, "등급"), ({"reviewer": ""}, "주체")])
def test_current_hash_does_not_override_other_bindings(tmp_path, draft, brief, change, error):
    parent = original(tmp_path, draft, brief)
    entry = add_feedback(parent, draft)
    (tmp_path / "feedback.jsonl").write_text(json.dumps({**entry, **change}) + "\n")
    with pytest.raises(ValueError, match=error):
        load_revision_feedback(parent, draft)


def test_current_candidate_feedback_cannot_silently_follow_newer_seed(tmp_path, draft, brief):
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    changed = draft.model_copy(deep=True)
    changed.items[0].explanation += " 수정된 초안"
    with pytest.raises(ValueError, match="seed.*candidate"):
        load_revision_feedback(parent, changed)


@pytest.mark.parametrize("mutation", ["feedback", "candidate", "brief", "packet"])
def test_source_or_copied_packet_change_is_rejected_before_model_call(tmp_path, draft, brief, mutation):
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    packet = load_revision_feedback(parent, draft)
    if mutation == "packet":
        packet["records"][0]["entry"]["text"] = "changed"
    else:
        path = tmp_path / "feedback.jsonl" if mutation == "feedback" else parent / (mutation + ".json")
        path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="해시|연결"):
        validate_revision_feedback(packet, draft)


def test_failed_initial_revision_can_recover_exact_feedback_packet(tmp_path, draft, brief):
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    packet = load_revision_feedback(parent, draft)
    run = tmp_path / "interrupted"
    run.mkdir()
    # Also covers a provider-constructor failure before revision-feedback.json is saved.
    save(run / "context.json", {"resume_lineage": {"revision_feedback": packet}})
    assert load_revision_feedback(run, draft) == packet
    save(run / "revision-feedback.json", packet)
    assert load_revision_feedback(run, draft) == packet
    changed = draft.model_copy(deep=True)
    changed.items[0].explanation += " new revision"
    with pytest.raises(ValueError, match="seed.*candidate"):
        load_revision_feedback(run, changed)


@pytest.mark.parametrize("state", ["after_draft", "completed"])
def test_applied_inherited_feedback_is_history_not_a_perpetual_rewrite(tmp_path, draft, brief, state):
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    packet = load_revision_feedback(parent, draft)
    run = tmp_path / "next"
    run.mkdir()
    save(run / "context.json", {"resume_lineage": {"revision_feedback": packet}})
    save(run / "revision-feedback.json", packet)
    changed = draft.model_copy(deep=True)
    changed.items[0].explanation += " 새 검토가 필요한 수정본"
    save(run / "draft-r0.json", changed.model_dump())
    if state == "completed":
        save(run / "candidate.json", changed.model_dump())
        save(run / "review-r0.json", {"errors": []})
    if state == "completed":
        assert load_revision_feedback(run, changed) is None
    else:
        historical = load_revision_feedback(run, changed)
        assert historical["application"] == "historical_review"
        assert historical["candidate"] == packet["candidate"]
        assert not requires_revision(historical)
        validate_revision_feedback(historical, changed)
    assert json.loads((run / "revision-feedback.json").read_text()) == packet


def test_historical_feedback_reaches_editor_after_multiple_review_interruptions(tmp_path, draft, brief):
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    packet = load_revision_feedback(parent, draft)
    changed = draft.model_copy(deep=True)
    changed.items[0].explanation += " 수정 후 아직 검토하지 못한 설명"
    previous = tmp_path / "failed-review"
    previous.mkdir()
    save(previous / "draft-r0.json", changed.model_dump())
    save(previous / "revision-feedback.json", packet)
    historical = load_revision_feedback(previous, changed)
    for index in range(2):
        run = tmp_path / f"resume-{index}"
        run.mkdir()
        save(run / "brief.json", brief.model_dump())
        save(run / "context.json", {"references": [{"id": "source-1", "text": "합성 자료"}]})
        provider = Recorder(changed)
        if index == 0:
            normal_call = provider.call
            def fail_blind(stage, *args):
                if stage == "blind":
                    raise RuntimeError("synthetic blind interruption")
                return normal_call(stage, *args)
            provider.call = fail_blind
            with pytest.raises(RuntimeError, match="blind interruption"):
                run_pipeline(run, provider, max_revisions=0, initial_draft=changed, revision_feedback=historical)
            historical = load_revision_feedback(run, changed)
            assert historical["application"] == "historical_review"
            continue
        run_pipeline(run, provider, max_revisions=0, initial_draft=changed, revision_feedback=historical)
        assert [call[0] for call in provider.calls] == ["blind", "editor"]
        assert set(provider.calls[0][2]) == {"items"}
        assert provider.calls[1][2]["revision_feedback"] == historical
        assert load_revision_feedback(run, changed) is None
    forged = json.loads(json.dumps(historical))
    forged["resumed_seed_content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="재검토 seed"):
        validate_revision_feedback(forged, changed)
    seed_ref = Path(historical["resume_seed"]["path"])
    save(seed_ref, draft.model_dump())
    with pytest.raises(ValueError, match="재검토 초안"):
        validate_revision_feedback(historical, changed)


def test_historical_feedback_is_removed_from_writer_lineage_context(tmp_path, draft, brief):
    parent = original(tmp_path, draft, brief)
    entry = add_feedback(parent, draft)
    pending = load_revision_feedback(parent, draft)
    failed = tmp_path / "failed-review"
    failed.mkdir()
    save(failed / "draft-r0.json", draft.model_dump())
    save(failed / "revision-feedback.json", pending)
    historical = load_revision_feedback(failed, draft)
    run = tmp_path / "next"
    run.mkdir()
    save(run / "brief.json", brief.model_dump())
    context = {"references": [{"id": "source-1", "text": "합성 출처"}],
               "resume_lineage": {"parent": str(failed), "revision_feedback": historical}}
    save(run / "context.json", context)
    provider = Recorder(draft)
    run_pipeline(run, provider, max_revisions=0, initial_draft=draft,
                 initial_review={"errors": ["현재 검토가 확인한 별도 지적"]}, revision_feedback=historical)
    assert [call[0] for call in provider.calls] == ["revise", "blind", "editor"]
    writer = provider.calls[0][2]
    assert "revision_feedback" not in writer
    assert writer["context"]["resume_lineage"] == {"parent": str(failed)}
    assert entry["text"] not in json.dumps(writer, ensure_ascii=False)
    assert provider.calls[2][2]["revision_feedback"] == historical
    assert json.loads((run / "context.json").read_text()) == context


@pytest.mark.parametrize("constructor_failure", [False, True])
def test_legacy_resume_routes_matching_b_without_mutating_review(tmp_path, draft, brief, monkeypatch, constructor_failure):
    from haean import exam_resume
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    before = (parent / "review-r0.json").read_bytes()
    slot = {"id": draft.items[0].id, "number": 1, "topic": brief.topic,
            "item_type": brief.item_type, "difficulty": brief.difficulty}
    plan = {"exam": brief.exam, "subject": brief.subject, "slots": [slot]}
    previous = tmp_path / "exam"
    previous.mkdir()
    save(previous / "plan.json", plan)
    save(previous / "production.json", {"jobs": [{"run": str(parent), "ids": [slot["id"]], "slots": [1]}]})
    monkeypatch.setattr(exam_resume, "load_plan", lambda _: plan)
    monkeypatch.setattr(exam_resume, "Corpus", lambda _: None)
    monkeypatch.setattr(exam_resume, "assemble", lambda out: json.loads((out / "production.json").read_text()))

    def prepare(_corpus, new_brief, root):
        run = Path(root) / "new"
        run.mkdir(parents=True)
        save(run / "brief.json", new_brief.model_dump())
        save(run / "context.json", {"references": [{"id": "source-1", "text": "合成資料"}]})
        save(run / "provenance.json", {})
        save(run / "status.json", {"state": "prepared", "human_approved": False})
        return run

    monkeypatch.setattr(exam_resume, "prepare", prepare)
    provider = Recorder(draft)
    if constructor_failure:
        def fail_provider(*args, **kwargs):
            raise RuntimeError("synthetic constructor failure")
        monkeypatch.setattr(exam_resume, "CodexProvider", fail_provider)
        first = tmp_path / "interrupted-exam"
        failed = exam_resume.resume(previous, "unused", first, workers=1, max_revisions=0)
        assert failed["jobs"][0]["state"] == "failed"
        inherited = Path(failed["jobs"][0]["run"])
        assert json.loads((inherited / "inherited-draft.json").read_text()) == draft.model_dump()
        assert not (inherited / "draft-r0.json").exists()
        previous = first
    monkeypatch.setattr(exam_resume, "CodexProvider", lambda *a, **kw: provider)
    result = exam_resume.resume(previous, "unused", tmp_path / "next-exam", workers=1, max_revisions=0)
    assert [call[0] for call in provider.calls] == ["revise", "blind", "editor"]
    run = Path(result["jobs"][0]["run"])
    lineage = json.loads((run / "lineage.json").read_text())
    assert lineage["revision_feedback"]["run"] == str(parent)
    assert (parent / "review-r0.json").read_bytes() == before
