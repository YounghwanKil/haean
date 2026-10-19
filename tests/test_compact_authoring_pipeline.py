"""Synthetic opt-in delivery checks; no production DB or model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from haean.pipeline import run_pipeline, save
from test_authoring_sources import material, rewrite_packet
from test_composition_adapter import inputs
from test_core import reviews


def read(path):
    return json.loads(Path(path).read_bytes())


@pytest.fixture
def compact_context(material, brief, draft):
    context, resolution, reference, _ = material
    source = reference["source"]
    entry = {"path": source["path"], "sha256": source["sha256"]}
    source.update(
        evidence_files={f"synthetic-audit-source-{n}": deepcopy(entry) for n in range(12)},
        official_answer={"answer": 4, "answer_verified": True, "evidence": {
            "files": {f"synthetic-audit-source-{n}": {"file": source["path"], "sha256": source["sha256"],
                "locator": "synthetic", "usage": "development"} for n in range(12)},
            "verification_scope": "official_answer_row_and_question_bytes", "human_approved": False}},
        classification_evidence={"origin": "model", "human_approved": False},
        unknown_semantic_field={"preserve": ["그대로 보존"]})
    resolution["selected_reference_input"].update(application="판단 구조 비교", match_scope="부분 일치", gaps=["소재 차이"])
    rewrite_packet(resolution["selected_reference_input"], "references")
    context["references"].append({"id": "source-1", "text": "다른 합성 예시"})
    context["brief"] = brief.model_dump()
    context["exam_assignment"][0].update(id=draft.items[0].id, item_type=draft.items[0].item_type)
    return context


def prepared(tmp_path, brief, context, name="run"):
    run = tmp_path / name
    run.mkdir()
    save(run / "brief.json", brief.model_dump())
    save(run / "context.json", context)
    return run


class Spy:
    def __init__(self, draft, *, revise_once=False, hook=None):
        self.draft, self.revise_once, self.hook = draft, revise_once, hook
        self.calls, self.usage, self.editors = [], [], 0

    def call(self, stage, instructions, payload, schema):
        self.calls.append((stage, deepcopy(payload)))
        if self.hook:
            self.hook(stage)
        if stage in {"generate", "revise"}:
            return self.draft.model_copy(deep=True)
        if stage == "blind":
            return reviews(self.draft)[0]
        self.editors += 1
        if self.revise_once and self.editors == 1:
            return schema(issues=[{"item_id": self.draft.items[0].id, "severity": "B", "category": "clarity",
                "location": "지문", "problem": "합성 수정 지적", "fix": "합성 수정"}], summary="재검토")
        return reviews(self.draft)[1]


def selected(context):
    return context["exam_assignment"][0]["composition_resolution"]["selected_reference_input"]


def without_audit_maps(reference):
    result = deepcopy(reference)
    result["source"].pop("evidence_files")
    result["source"]["official_answer"]["evidence"].pop("files")
    return result


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("inherited", [False, True])
def test_actual_writer_editor_delivery_keeps_full_validation_and_blind_isolation(
        tmp_path, brief, draft, compact_context, compact, inherited):
    run = prepared(tmp_path, brief, compact_context)
    original = (run / "context.json").read_bytes()
    provider = Spy(draft, revise_once=True)
    options = {"initial_draft": draft.model_dump(), "initial_review": {"errors": ["이전 지적"]}} if inherited else {}
    # Omit the keyword in the default path, preserving the legacy call contract.
    if compact:
        options["compact_reference_audit"] = True
    run_pipeline(run, provider, max_revisions=1, **options)
    assert (run / "context.json").read_bytes() == original
    original_ref = selected(compact_context)["references"][0]
    for stage, payload in provider.calls:
        if stage == "blind":
            assert set(payload) == {"items"}
            assert "selected-1" not in json.dumps(payload)
            assert "official_answer" not in json.dumps(payload)
            assert "answer" not in payload["items"][0]
            continue
        view = payload["context"] if stage == "revise" else payload
        block = selected(view)
        current_ref = block["references"][0]
        assert {k: v for k, v in block.items() if k != "references"} == {
            k: v for k, v in selected(compact_context).items() if k != "references"}
        if compact:
            assert current_ref["source"]["evidence_files"] != original_ref["source"]["evidence_files"]
            assert current_ref["source"]["official_answer"]["evidence"]["files"] != original_ref["source"]["official_answer"]["evidence"]["files"]
            assert without_audit_maps(current_ref) == without_audit_maps(original_ref)
        else:
            assert current_ref == original_ref
    assert [stage for stage, _ in provider.calls].count("revise") == (2 if inherited else 1)
    folders = list((run / "authoring-inputs").glob("*"))
    if not compact:
        assert folders == []
        return
    assert len(folders) == 1
    folder = folders[0]
    assert (folder / "original-context.json").read_bytes() == original
    writer = next(payload["context"] if stage == "revise" else payload
                  for stage, payload in provider.calls if stage in {"generate", "revise"})
    assert read(folder / "writer-context.json") == writer
    editor = next(payload for stage, payload in provider.calls if stage == "editor")
    assert read(folder / "editor-exam-assignment.json") == editor["exam_assignment"]
    manifest = read(folder / "delivery-manifest.json")
    assert manifest["compact_reference_audit"] is True
    for record in manifest["files"].values():
        assert hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest() == record["sha256"]


@pytest.mark.parametrize("when", ["before", "editor"])
def test_compact_mode_still_rejects_changed_original_evidence(tmp_path, brief, draft, compact_context, when):
    run = prepared(tmp_path, brief, compact_context)
    source = Path(selected(compact_context)["references"][0]["source"]["path"])
    if when == "before":
        source.write_bytes(b"changed before generation")
    provider = Spy(draft, hook=lambda stage: source.write_bytes(b"changed during editor") if stage == when else None)
    with pytest.raises(ValueError, match="SHA-256"):
        run_pipeline(run, provider, 0, compact_reference_audit=True)
    if when == "before":
        assert provider.calls == []
    assert not (run / "candidate.json").exists()


def test_historical_feedback_is_archived_but_removed_only_from_writer(tmp_path, brief, draft, compact_context):
    from haean.revision_feedback import load_revision_feedback
    from test_revision_feedback import original, add_feedback
    parent = original(tmp_path, draft, brief)
    add_feedback(parent, draft)
    pending = load_revision_feedback(parent, draft)
    changed = draft.model_copy(deep=True)
    changed.items[0].explanation += " 새 수정본"
    interrupted = tmp_path / "interrupted"
    interrupted.mkdir()
    save(interrupted / "draft-r0.json", changed.model_dump())
    save(interrupted / "revision-feedback.json", pending)
    historical = load_revision_feedback(interrupted, changed)
    compact_context["resume_lineage"] = {"parent": str(interrupted), "revision_feedback": historical}
    run = prepared(tmp_path, brief, compact_context)
    provider = Spy(changed)
    run_pipeline(run, provider, 0, initial_draft=changed, initial_review={"errors": ["새 버전 수정"]},
                 revision_feedback=historical, compact_reference_audit=True)
    writer = next(payload for stage, payload in provider.calls if stage == "revise")
    assert "revision_feedback" not in writer and "revision_feedback" not in writer["context"]["resume_lineage"]
    editor = next(payload for stage, payload in provider.calls if stage == "editor")
    assert editor["revision_feedback"] == historical
    folder = next((run / "authoring-inputs").iterdir())
    assert read(folder / "original-context.json")["resume_lineage"]["revision_feedback"] == historical
    assert read(folder / "writer-context.json") == writer["context"]


@pytest.mark.parametrize("command", ["generate", "exam-build", "exam-resume"])
@pytest.mark.parametrize("compact", [False, True])
def test_cli_opt_in_reaches_production_entry_points(tmp_path, monkeypatch, capsys, command, compact):
    from haean import cli, full_exam, exam_resume
    calls = []
    def endpoint(*args, **kwargs):
        calls.append(kwargs)
        return {"synthetic": True}
    monkeypatch.setattr(full_exam, "build", endpoint)
    monkeypatch.setattr(exam_resume, "resume", endpoint)
    monkeypatch.setattr(cli, "Corpus", lambda _: None)
    if command == "generate":
        run = tmp_path / "cli-run"
        run.mkdir()
        save(run / "provenance.json", {"source_ids": []})
        save(run / "status.json", {"state": "prepared"})
        monkeypatch.setattr(cli, "prepare", lambda *a: run)
        monkeypatch.setattr(cli, "CodexProvider", lambda *a, **k: object())
        monkeypatch.setattr(cli, "run_pipeline", endpoint)
        monkeypatch.setattr(cli, "export_review", lambda *a: None)
        args = [command, "--exam", "leet", "--subject", "추리논증", "--type", "조건 추론", "--topic", "합성"]
    else:
        args = [command, str(tmp_path / "input"), "--out", str(tmp_path / "out")]
    monkeypatch.setattr("sys.argv", ["haean-tool", *args, *(["--compact-reference-audit"] if compact else [])])
    cli.main()
    capsys.readouterr()
    assert len(calls) == 1
    if compact:
        assert calls[0]["compact_reference_audit"] is True
    else:
        assert "compact_reference_audit" not in calls[0]
    if command == "generate":
        assert read(run / "provenance.json")["compact_reference_audit"] is compact


def test_resume_forwards_opt_in_to_composition_branch(tmp_path, monkeypatch):
    from haean import composition_resume, exam_resume
    save(tmp_path / "production.json", {"composition": {}, "jobs": []})
    calls = []
    monkeypatch.setattr(composition_resume, "resume_composition", lambda *a, **k: calls.append(k) or {})
    exam_resume.resume(tmp_path, "unused", tmp_path / "out", compact_reference_audit=True)
    assert calls[0]["compact_reference_audit"] is True


@pytest.mark.parametrize("entry", ["build", "resume"])
def test_build_and_plain_resume_forward_flag_to_each_bundle(tmp_path, brief, draft, monkeypatch, entry):
    from haean import full_exam, exam_resume
    module = full_exam if entry == "build" else exam_resume
    slot = {"id": draft.items[0].id, "number": 1, "domain": "규범", "item_type": brief.item_type,
            "topic": brief.topic, "difficulty": "하"}
    plan = {"exam": brief.exam, "subject": brief.subject, "slots": [slot]}
    monkeypatch.setattr(module, "load_plan", lambda _: plan)
    monkeypatch.setattr(module, "Corpus", lambda _: None)
    monkeypatch.setattr(module, "CodexProvider", lambda *a, **k: object())
    monkeypatch.setattr(module, "assemble", lambda out: read(Path(out) / "production.json"))
    def make_run(_corpus, b, root):
        root.mkdir(parents=True, exist_ok=True)
        run = prepared(root, b, {"brief": b.model_dump(), "references": [{"id": "source-1", "text": "합성"}],
                                "retrieval": {}, "feedback": []})
        save(run / "provenance.json", {"source_ids": ["source-1"]})
        (run / "request.md").write_text("합성")
        return run
    monkeypatch.setattr(module, "prepare", make_run)
    calls = []
    def pipeline(run, _provider, *args, **kwargs):
        calls.append(kwargs)
        save(run / "status.json", {"state": "awaiting_human_review", "errors": []})
        return draft
    monkeypatch.setattr(module, "run_pipeline", pipeline)
    out = tmp_path / "out"
    if entry == "build":
        plan_path = tmp_path / "plan.json"
        save(plan_path, plan)
        full_exam.build(plan_path, "unused", out, workers=1, compact_reference_audit=True)
    else:
        parent = tmp_path / "parent"
        parent.mkdir()
        run = make_run(None, brief, parent / "bundles")
        save(run / "status.json", {"state": "failed"})
        save(parent / "plan.json", plan)
        save(parent / "production.json", {"jobs": [{"run": str(run), "ids": [slot["id"]], "slots": [1]}]})
        exam_resume.resume(parent, "unused", out, workers=1, compact_reference_audit=True)
    assert calls and all(call["compact_reference_audit"] is True for call in calls)
    assert read(out / "provenance.json")["compact_reference_audit"] is True


def test_compact_option_rejects_non_boolean_before_calls(tmp_path):
    with pytest.raises(ValueError, match="must be bool"):
        run_pipeline(tmp_path, object(), compact_reference_audit="true")


def test_composition_resume_compacts_new_calls_and_preserves_sealed_parent(
        inputs, material, compact_context, tmp_path, draft, monkeypatch):
    from haean.exam_resume import resume
    from test_composition_resume import history, install_runtime, hashes
    plan = read(inputs["plan"])
    plan["slots"][0]["composition_resolution"] = deepcopy(material[1])
    save(inputs["plan"], plan)
    previous = history(inputs, tmp_path, draft, modes={0: "seedless"})
    before = hashes(previous)
    providers = install_runtime(monkeypatch, draft)
    out = tmp_path / "compact-resume"
    result = resume(previous, "unused", out, workers=1, max_revisions=0, compact_reference_audit=True)
    assert result["written"] == 40 and result["ready_for_human_review"], result["errors"]
    assert hashes(previous) == before
    assert read(out / "provenance.json")["compact_reference_audit"] is True
    assert len(providers) == 1
    calls = {stage: payload for stage, _, payload in providers[0].calls}
    reference = selected(calls["generate"])["references"][0]
    original_reference = selected(compact_context)["references"][0]
    assert reference["source"]["evidence_files"] != original_reference["source"]["evidence_files"]
    assert without_audit_maps(reference) == without_audit_maps(original_reference)
    assert selected(calls["editor"]) == selected(calls["generate"])
    assert "selected_reference_input" not in json.dumps(calls["blind"])
    fresh = next(job for job in read(out / "production.json")["jobs"] if not job.get("reused"))
    assert len(list((Path(fresh["run"]) / "authoring-inputs").glob("*/delivery-manifest.json"))) == 1
