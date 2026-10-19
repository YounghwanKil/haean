"""Synthetic 40-slot histories exercise reuse, interrupted reviews and lineage."""
from pathlib import Path
import json

import pytest

from haean import composition_adapter as adapter
from haean import composition_resume as resumed
from haean.exam_resume import resume
from haean.full_exam import bundles
from haean.pipeline import run_pipeline, save
from test_composition_adapter import inputs, packet, prepared, Provider, read


class HistoryProvider(Provider):
    def __init__(self, template, mode="ready"):
        super().__init__(template)
        self.mode = mode

    def call(self, stage, instructions, payload, schema):
        if stage == "generate" and self.mode == "seedless":
            raise RuntimeError("synthetic first generation interruption")
        if stage == "blind" and self.mode == "seeded":
            raise RuntimeError("synthetic review interruption")
        if stage == "revise" and self.mode == "revision_failure":
            raise RuntimeError("synthetic inherited revision interruption")
        result = super().call(stage, instructions, payload, schema)
        if stage in {"generate", "revise"}:
            for item in result.items:
                if item.shared_passage_id:
                    item.passage = "합성 공통 지문이며 문제별 정답을 누설하지 않는다. " * 5
        if stage == "editor" and self.mode == "reviewed":
            return schema(issues=[{"item_id": payload["draft"]["items"][0]["id"],
                                  "severity": "B", "category": "clarity", "location": "지문",
                                  "problem": "합성 수정 지적", "fix": "조건을 명확히 표시"}], summary="합성 오류 검토")
        return result


def history(inputs, tmp_path, draft, *, modes=None):
    bound = packet(inputs, tmp_path)
    plan = read(inputs["plan"])
    previous = tmp_path / "previous"
    previous.mkdir()
    # Bind exactly the original, deliberately noncanonical JSON bytes.
    (previous / "plan.json").write_bytes(inputs["plan"].read_bytes())
    jobs = []
    modes = {0: "ready", 1: "seedless", 2: "seeded", 3: "reviewed"} if modes is None else modes
    for n, group in enumerate(bundles(plan)):
        run = prepared(previous / "bundles" / str(n), group, plan["subject"], plan["exam"])
        context = read(run / "context.json")
        context.update(exam_contract="기존 출제 계약", exam_editorial_context={"all_slots": 40},
                       feedback=[{"text": "기존 의견", "origin": "model"}])
        save(run / "context.json", context)
        expected = adapter.attach_bundle(run, plan_path=previous / "plan.json", packet_path=bound, slots=group)
        provider = HistoryProvider(draft, modes.get(n, "ready"))
        try:
            run_pipeline(run, provider, max_revisions=0, **adapter.pipeline_callbacks(run, expected))
        except RuntimeError:
            pass
        state = read(run / "status.json")
        jobs.append({"bundle": n + 1, "run": str(run), "slots": [s["number"] for s in group],
                     "ids": [s["id"] for s in group], "state": state["state"], "composition": expected})
    save(previous / "production.json", {"exam": plan["exam"], "subject": plan["subject"], "total": 40,
         "jobs": jobs, "complete": False, "human_approved": False,
         "composition": {"packet": adapter._file_ref(bound), "plan_sha256": adapter._sha(previous / "plan.json")}})
    return previous


def install_runtime(monkeypatch, draft, *, mode="ready"):
    providers = []

    def new_prepare(_corpus, brief, root):
        index = len(list(Path(root).glob("*"))) if Path(root).exists() else 0
        slots = [{"id": "prepare-only", "number": 1, "topic": brief.topic,
                  "item_type": brief.item_type, "domain": "규범", "difficulty": brief.difficulty}]
        run = prepared(Path(root) / f"new-{index}", slots, brief.subject, brief.exam)
        context = read(run / "context.json")
        context.update(brief=brief.model_dump(), references=[{"id": "new-ref", "text": "새 검색 결과"}],
                       retrieval={"new_search": True})
        context.pop("exam_assignment")
        save(run / "context.json", context)
        save(run / "brief.json", brief.model_dump())
        return run

    def new_provider(*args, **kwargs):
        provider = HistoryProvider(draft, mode)
        providers.append(provider)
        return provider

    monkeypatch.setattr(resumed, "prepare", new_prepare)
    monkeypatch.setattr(resumed, "Corpus", lambda db: None)
    monkeypatch.setattr(resumed, "CodexProvider", new_provider)
    monkeypatch.setattr("haean.full_exam.render_exam", lambda *args: None)
    return providers


def hashes(root):
    return {str(p.relative_to(root)): adapter._sha(p) for p in root.rglob("*") if p.is_file()}


def test_resume_mixed_40_slot_history_preserves_contracts_and_reviews(inputs, tmp_path, draft, monkeypatch):
    # Whitespace bytes are part of the bound plan, even if load_plan normalizes it.
    inputs["plan"].write_text(json.dumps(read(inputs["plan"]), ensure_ascii=False, separators=(",", ":")) + "\n\n")
    previous = history(inputs, tmp_path, draft)
    before = hashes(previous)
    providers = install_runtime(monkeypatch, draft)
    out = tmp_path / "next"
    result = resume(previous, "unused", out, workers=1, max_revisions=0)
    assert result["written"] == 40 and result["ready_for_human_review"], result["errors"]
    assert hashes(previous) == before
    assert (out / "plan.json").read_bytes() == (previous / "plan.json").read_bytes()
    jobs = read(out / "production.json")["jobs"]
    assert len(jobs) == 10 and sum(job["reused"] for job in jobs) == 7
    assert [len(job["ids"]) for job in jobs] == [4] * 10  # Seedless groups are not split.
    assert [[call[0] for call in p.calls] for p in providers] == [
        ["generate", "blind", "editor"], ["blind", "editor"], ["revise", "blind", "editor"]]
    for job in jobs:
        if job["reused"]:
            assert Path(job["run"]).is_relative_to(previous)
            continue
        context = read(Path(job["run"]) / "context.json")
        assert context["references"] == [{"id": "source-1", "text": "합성 출처"}]
        assert context["retrieval"] == {"synthetic": True}
        assert context["exam_contract"] == "기존 출제 계약"
        assert context["exam_editorial_context"] == {"all_slots": 40}
        assert context["feedback"] == [{"text": "기존 의견", "origin": "model"}]
        assert read(Path(job["run"]) / "composition.json")["assignment"] == context["exam_assignment"]
    for provider in providers:
        for stage, _, payload in provider.calls:
            if stage == "blind":
                assert set(payload) == {"items"}
                assert "비밀" not in json.dumps(payload, ensure_ascii=False)
                assert all(not {"answer", "source_ids", "judgments"} & item.keys() for item in payload["items"])
            if stage == "editor":
                assert payload["additional_context"]["assignments"]


def test_repeated_interruption_uses_sealed_original_seed_and_review(inputs, tmp_path, draft, monkeypatch):
    previous = history(inputs, tmp_path, draft, modes={0: "reviewed"})
    before = hashes(previous)
    install_runtime(monkeypatch, draft, mode="revision_failure")
    first = tmp_path / "first"
    result = resume(previous, "unused", first, workers=1, max_revisions=0)
    assert not result["ready_for_human_review"]
    inherited = Path(read(first / "production.json")["jobs"][0]["run"])
    assert (inherited / "inherited-draft.json").exists()
    assert (inherited / "inherited-review.json").exists()
    assert not list(inherited.glob("draft-r*.json"))
    lineage = read(inherited / "context.json")["resume_lineage"]
    origin = Path(read(previous / "production.json")["jobs"][0]["run"])
    assert lineage["seed_path"] == str(origin / "draft-r0.json")
    assert lineage["review_path"] == str(origin / "review-r0.json")
    first_before = hashes(first)
    providers = install_runtime(monkeypatch, draft)
    second = tmp_path / "second"
    result = resume(first, "unused", second, workers=1, max_revisions=0)
    assert result["ready_for_human_review"], result["errors"]
    assert [call[0] for call in providers[0].calls] == ["revise", "blind", "editor"]
    final_run = Path(read(second / "production.json")["jobs"][0]["run"])
    final_lineage = read(final_run / "context.json")["resume_lineage"]
    assert final_lineage["seed_path"] == lineage["seed_path"]
    assert final_lineage["review_sha256"] == lineage["review_sha256"]
    assert hashes(previous) == before and hashes(first) == first_before


def test_provider_constructor_failure_recovers_seed_before_inherited_files(inputs, tmp_path, draft, monkeypatch):
    previous = history(inputs, tmp_path, draft, modes={0: "reviewed"})
    install_runtime(monkeypatch, draft)
    def fail_provider(*args, **kwargs):
        raise RuntimeError("synthetic constructor failure")
    monkeypatch.setattr(resumed, "CodexProvider", fail_provider)
    first = tmp_path / "first"
    assert not resume(previous, "unused", first, workers=1, max_revisions=0)["ready_for_human_review"]
    run = Path(read(first / "production.json")["jobs"][0]["run"])
    assert not (run / "inherited-draft.json").exists()
    assert read(run / "context.json")["resume_lineage"]["seed_path"]
    providers = install_runtime(monkeypatch, draft)
    result = resume(first, "unused", tmp_path / "second", workers=1, max_revisions=0)
    assert result["ready_for_human_review"], result["errors"]
    assert [call[0] for call in providers[0].calls] == ["revise", "blind", "editor"]


def test_old_reviewed_candidate_and_latest_unreviewed_draft_are_distinct(inputs, tmp_path, draft, monkeypatch):
    previous = history(inputs, tmp_path, draft, modes={0: "reviewed"})
    run = Path(read(previous / "production.json")["jobs"][0]["run"])
    latest = read(run / "draft-r0.json")
    latest["items"][0]["passage"] += " 추가 조건을 명시한 수정본."
    save(run / "draft-r1.json", latest)
    save(run / "status.json", {"state": "failed", "human_approved": False, "error": "interrupted blind review"})
    providers = install_runtime(monkeypatch, draft)
    result = resume(previous, "unused", tmp_path / "next", workers=1, max_revisions=0)
    assert result["ready_for_human_review"], result["errors"]
    assert [call[0] for call in providers[0].calls] == ["blind", "editor"]
    assert providers[0].calls[0][2]["items"][0]["passage"].endswith("추가 조건을 명시한 수정본.")


def test_reviewed_candidate_cannot_be_downgraded_by_deleting_review_evidence(inputs, tmp_path, draft, monkeypatch):
    previous = history(inputs, tmp_path, draft, modes={0: "reviewed"})
    run = Path(read(previous / "production.json")["jobs"][0]["run"])
    (run / "review-r0.json").unlink()
    (run / "composition-review-r0.json").unlink()
    monkeypatch.setattr(resumed, "prepare", lambda *a, **kw: pytest.fail("prepare called before validation"))
    with pytest.raises(ValueError, match="receipt"):
        resume(previous, "unused", tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_parent_changed_during_prepare_blocks_provider(inputs, tmp_path, draft, monkeypatch):
    previous = history(inputs, tmp_path, draft, modes={0: "reviewed"})
    origin = Path(read(previous / "production.json")["jobs"][0]["run"])
    providers = install_runtime(monkeypatch, draft)
    real_prepare = resumed.prepare
    def changing_prepare(*args, **kwargs):
        run = real_prepare(*args, **kwargs)
        path = origin / "review-r0.json"
        path.write_text(path.read_text() + "\n")
        return run
    monkeypatch.setattr(resumed, "prepare", changing_prepare)
    out = tmp_path / "next"
    result = resume(previous, "unused", out, workers=1, max_revisions=0)
    assert not result["ready_for_human_review"] and not providers
    assert read(out / "production.json")["jobs"][0]["state"] == "failed"


@pytest.mark.parametrize("mutation", ["source", "runtime", "plan", "packet", "review", "receipt", "candidate",
                                     "wrong_ids", "wrong_slots", "missing_sidecar", "hidden_sidecar", "mixed_job"])
def test_stale_or_mixed_composition_rejected_before_output_or_calls(inputs, tmp_path, draft, monkeypatch, mutation):
    previous = history(inputs, tmp_path, draft)
    manifest = read(previous / "production.json")
    ready_run = Path(manifest["jobs"][0]["run"])
    reviewed_run = Path(manifest["jobs"][3]["run"])
    if mutation in {"source", "runtime"}:
        path = inputs[mutation]
        path.write_text(path.read_text() + "\n")
    elif mutation == "plan":
        (previous / "plan.json").write_text((previous / "plan.json").read_text() + "\n")
    elif mutation == "packet":
        path = Path(manifest["composition"]["packet"]["path"])
        path.write_text(path.read_text() + "\n")
    elif mutation == "review":
        (reviewed_run / "review-r0.json").write_text((reviewed_run / "review-r0.json").read_text() + "\n")
    elif mutation == "receipt":
        receipt = read(reviewed_run / "composition-review-r0.json")
        receipt["revision"] = 1
        save(reviewed_run / "composition-review-r0.json", receipt)
    elif mutation == "candidate":
        (ready_run / "candidate.json").write_text("{ malformed")
    elif mutation == "wrong_ids":
        manifest["jobs"][0]["ids"].reverse()
        manifest["jobs"][0]["slots"].reverse()
    elif mutation == "wrong_slots":
        manifest["jobs"][0]["slots"] = [1, 2, 3, 5]
    elif mutation == "missing_sidecar":
        (ready_run / "composition.json").unlink()
    elif mutation == "hidden_sidecar":
        manifest.pop("composition")
        for job in manifest["jobs"]:
            job.pop("composition")
    elif mutation == "mixed_job":
        manifest["jobs"][1].pop("composition")
    save(previous / "production.json", manifest)
    before = hashes(previous)
    monkeypatch.setattr(resumed, "CodexProvider", lambda *a, **kw: pytest.fail("provider called before validation"))
    monkeypatch.setattr(resumed, "prepare", lambda *a, **kw: pytest.fail("prepare called before validation"))
    out = tmp_path / "blocked"
    with pytest.raises(ValueError):
        resume(previous, "unused", out)
    assert not out.exists() and hashes(previous) == before


@pytest.mark.parametrize("mutation", ["inherited_draft", "inherited_review", "original_draft", "original_review", "lineage"])
def test_repeated_resume_rejects_unbound_inherited_artifacts(inputs, tmp_path, draft, monkeypatch, mutation):
    previous = history(inputs, tmp_path, draft, modes={0: "reviewed"})
    install_runtime(monkeypatch, draft, mode="revision_failure")
    first = tmp_path / "first"
    resume(previous, "unused", first, workers=1, max_revisions=0)
    run = Path(read(first / "production.json")["jobs"][0]["run"])
    origin = Path(read(previous / "production.json")["jobs"][0]["run"])
    if mutation in {"inherited_draft", "original_draft"}:
        path = run / "inherited-draft.json" if mutation == "inherited_draft" else origin / "draft-r0.json"
        value = read(path)
        value["items"][0]["passage"] += " 변조"
    elif mutation in {"inherited_review", "original_review"}:
        path = run / "inherited-review.json" if mutation == "inherited_review" else origin / "review-r0.json"
        value = read(path)
        value["errors"] = []
    else:
        path = run / "context.json"
        value = read(path)
        value["resume_lineage"]["review_path"] = None
    save(path, value)
    monkeypatch.setattr(resumed, "prepare", lambda *a, **kw: pytest.fail("prepare called before validation"))
    out = tmp_path / "blocked"
    with pytest.raises(ValueError):
        resume(first, "unused", out)
    assert not out.exists()


def test_composition_replacements_are_explicitly_rejected(inputs, tmp_path, draft):
    previous = history(inputs, tmp_path, draft, modes={})
    out = tmp_path / "blocked"
    with pytest.raises(ValueError, match="replacements"):
        resume(previous, "unused", out, replacements=[previous / "production.json"])
    assert not out.exists()


def test_resume_keeps_shared_pair_together(inputs, tmp_path, draft, monkeypatch):
    plan, design, mapping = (read(inputs[key]) for key in ("plan", "design", "mapping"))
    plan.update(exam="psat5", subject="상황판단")
    design.update(exam="psat5", subject="상황판단", track="psat_situation", exam_grade=5)
    for row in design["format_design"]["slots"]:
        row["set_id"] = "raw-pair" if row["slot"] in {39, 40} else None
    for row in mapping:
        if row["external_slot"] in {39, 40}:
            row.update(external_set_key="raw-pair", shared_passage_id="shared-opaque")
            plan["slots"][row["number"] - 1]["shared_passage_id"] = "shared-opaque"
    for key, value in (("plan", plan), ("design", design), ("mapping", mapping)):
        save(inputs[key], value)
    previous = history(inputs, tmp_path, draft, modes={0: "seedless"})
    providers = install_runtime(monkeypatch, draft)
    out = tmp_path / "next"
    result = resume(previous, "unused", out, workers=1, max_revisions=0)
    assert result["written"] == 40 and result["ready_for_human_review"], result["errors"]
    pair = read(out / "production.json")["jobs"][0]
    assert pair["ids"] == [s["id"] for s in plan["slots"][:2]] and pair["slots"] == [1, 2]
    assert len(providers) == 1
    assert len(providers[0].calls[0][2]["exam_assignment"]) == 2
    manifest = read(previous / "production.json")
    pair = manifest["jobs"][0]
    manifest["jobs"] = [{**pair, "ids": pair["ids"][:1], "slots": [1]},
                        {**pair, "ids": pair["ids"][1:], "slots": [2]}, *manifest["jobs"][1:]]
    save(previous / "production.json", manifest)
    with pytest.raises(ValueError, match="배정"):
        resume(previous, "unused", tmp_path / "split-pair")
    assert not (tmp_path / "split-pair").exists()
