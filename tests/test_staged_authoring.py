import copy
import hashlib
import json

import pytest

from haean import execution_provenance
from haean.models import Brief as LegacyBrief, Draft, Figure
from haean.pipeline import save
from haean.staged_authoring import attach, run_staged, validate_staged
from haean.tracks.core.track import Brief
from haean.tracks.core.references import ReferenceIndex


def load(path):
    return json.loads(path.read_text())


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    # Other contributors may edit package code while these synthetic runs execute.
    # Real snapshot verification remains active for all named inputs and copies.
    monkeypatch.setattr(execution_provenance, "runtime_sources", lambda: {"synthetic.py": b"fixed test runtime"})


def track_brief(**updates):
    values = dict(track="psat_situation", grade=7, area="생활·일상(가상)", item_type="조건 추론",
                  item_format="일반", discourse="평서문", topic="예약 규칙", difficulty="하", ids=["TEST-001"])
    return Brief(**(values | updates))


def prepared(tmp_path, brief=None, *, name="prepared", old_type=None):
    brief = brief or track_brief()
    run = tmp_path / name
    run.mkdir()
    subjects = {"psat_situation": "상황판단", "psat_verbal": "언어논리", "psat_data": "자료해석", "leet_reasoning": "추리논증"}
    legacy = LegacyBrief(exam=f"psat{brief.grade}" if brief.grade else "leet", subject=subjects[brief.track],
                        item_type=old_type or brief.item_type, topic=brief.topic or "예약 규칙", difficulty=brief.difficulty,
                        count=brief.count, shared_passage=brief.set)
    context = {"brief": legacy.model_dump(), "references": [{"id": "source-1", "exam": legacy.exam,
               "text": "합성 출처. 실제 기출이나 납품 문항이 아님.", "locator": "synthetic:1", "role": "principle"}],
               "retrieval": {"synthetic": True}, "feedback": [{"note": "보존할 합성 피드백"}], "note": "합성 입력"}
    save(run / "brief.json", legacy.model_dump())
    save(run / "context.json", context)
    save(run / "provenance.json", {"source_ids": ["source-1"], "version": "test"})
    save(run / "draft.schema.json", Draft.model_json_schema())
    save(run / "status.json", {"state": "prepared", "human_approved": False})
    return run


class Provider:
    model = "synthetic-test-double"

    def __init__(self, draft, hook=None):
        self.template, self.hook = draft, hook
        self.calls, self.usage = [], []

    def call(self, stage, instructions, payload, schema):
        self.calls.append((stage, instructions, copy.deepcopy(payload)))
        self.usage.append({"stage": stage, "model": self.model, "synthetic": True})
        if self.hook:
            result = self.hook(stage, payload, self)
            if result is not None:
                return result
        if stage == "material":
            return schema(materials=[dict(item_id=id_, topic=payload["brief"]["topic"], issue="쟁점 비밀",
                                         task_fit="조건 방향", background="자족적 가상 규칙", risks=[])
                                     for id_ in payload["item_ids"]], rejected=[])
        if stage == "design":
            return schema(design_summary="설계 비밀", items=[dict(item_id=id_, stem_type="반드시 참",
                core_judgment="핵심 판단 비밀", answer_condition="전건 충족", distractor_paths=["역 추론"],
                bypass_check="조건 방향 필요", block_plan=["규칙 다음 사례"], line_budget=10,
                reference_use="추가 참고 없음") for id_ in payload["item_ids"]])
        if stage in {"generate", "revise"}:
            context = payload if stage == "generate" else payload["context"]
            contract = context["staged_contract"]
            items = []
            for id_ in contract["brief"]["ids"]:
                item = self.template.items[0].model_copy(deep=True)
                item.id, item.subject, item.item_type = id_, context["brief"]["subject"], context["brief"]["item_type"]
                item.domain, item.topic, item.difficulty = contract["legacy_domain"], context["brief"]["topic"], context["brief"]["difficulty"]
                item.shared_passage_id = "shared-synthetic" if context["brief"]["shared_passage"] else None
                items.append(item)
            return schema(design_summary="legacy 직접 작성", items=items)
        if stage == "blind":
            return schema(solutions=[dict(item_id=i["id"], answer=1, uniquely_answerable=True,
                                         option_reasons=["합성 근거"] * 5, missing_conditions=[]) for i in payload["items"]], issues=[])
        return schema(issues=[], summary="합성 편집 검토")


def test_direct_legacy_authoring_preserves_reviews_and_snapshots(tmp_path, draft):
    brief = track_brief()
    run = prepared(tmp_path, brief)
    base = load(run / "context.json")
    attach(run, brief)
    provider = Provider(draft)
    result = run_staged(run, provider, max_revisions=0)
    assert [c[0] for c in provider.calls] == ["material", "design", "generate", "blind", "editor"]
    assert result.items[0].judgments[1].verdict == "판단불가"
    context = load(run / "context.json")
    assert {k: context[k] for k in base} == base
    assert result.items[0].source_ids == ["source-1"]
    assert result.items[0].id == "TEST-001"
    blind = next(c[2] for c in provider.calls if c[0] == "blind")
    assert set(blind) == {"items"}
    assert not {"judgments", "answer", "source_ids", "difficulty_basis"} & blind["items"][0].keys()
    assert "비밀" not in json.dumps(blind, ensure_ascii=False)
    editor = next(c[2] for c in provider.calls if c[0] == "editor")
    assert editor["additional_context"]["design"]["design_summary"] == "설계 비밀"
    assert all("passage는 블록 목록" not in c[1] for c in provider.calls)
    assert load(run / "status.json")["state"] == "awaiting_human_review"
    assert load(run / "status.json")["human_approved"] is False
    bindings = load(run / "staged/review-bindings.json")
    assert bindings["candidate_sha256"] == hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest()
    assert len(bindings["reviews"]) == 1
    instructions = load(run / "staged/snapshot-review/instructions.json")
    for stage, actual, _ in provider.calls:
        assert instructions[stage] == actual
    assert execution_provenance.verify(run / "staged/snapshot-review/manifest.json")["valid"]


def test_run_unique_ids_and_empty_topic_resolution(tmp_path):
    brief = track_brief(ids=[], topic="")
    first, second = prepared(tmp_path, brief, name="first"), prepared(tmp_path, brief, name="second")
    attach(first, brief)
    attach(second, brief)
    one, two = load(first / "staged/track-brief.json"), load(second / "staged/track-brief.json")
    assert "first" in one["ids"][0] and one["ids"] != two["ids"]
    assert one["topic"] == "예약 규칙"
    assert load(first / "staged/requested-brief.json")["topic"] == ""


@pytest.mark.parametrize("updates", [{"grade": 5}, {"difficulty": "상"}, {"topic": "다른 소재"}, {"count": 2, "ids": ["A", "B"]}])
def test_mismatched_prepared_brief_rejected_before_mutation(tmp_path, updates):
    run = prepared(tmp_path)
    old = (run / "context.json").read_bytes()
    with pytest.raises(ValueError, match="불일치"):
        attach(run, track_brief(**updates))
    assert (run / "context.json").read_bytes() == old and not (run / "staged").exists()


def test_explicit_type_mapping_preserves_legacy_type(tmp_path, draft):
    brief = track_brief()
    run = prepared(tmp_path, brief, old_type="기존 조건 유형")
    with pytest.raises(ValueError, match="type_mapping"):
        attach(run, brief)
    mapping = {"legacy_item_type": "기존 조건 유형", "track_item_type": brief.item_type, "rationale": "이 합성 사례는 조건 방향 판단을 측정한다"}
    attach(run, brief, type_mapping=mapping)
    result = run_staged(run, Provider(draft), max_revisions=0)
    assert result.items[0].item_type == "기존 조건 유형"
    assert load(run / "staged/design-input.json")["brief"]["item_type"] == brief.item_type
    assert load(run / "staged/contract.json")["type_mapping"] == mapping


@pytest.mark.parametrize("mapping", [
    {"legacy_item_type": "다른 유형", "track_item_type": "조건 추론", "rationale": "근거"},
    {"legacy_item_type": "기존 유형", "track_item_type": "다른 유형", "rationale": "근거"},
    {"legacy_item_type": "기존 유형", "track_item_type": "조건 추론", "rationale": " "},
])
def test_type_mapping_requires_exact_pair_and_reason(tmp_path, mapping):
    run = prepared(tmp_path, old_type="기존 유형")
    with pytest.raises(ValueError, match="type_mapping"):
        attach(run, track_brief(), type_mapping=mapping)


def test_reading_and_mixed_assignment_are_explicitly_unsupported(tmp_path):
    run = prepared(tmp_path)
    with pytest.raises(ValueError, match="언어이해"):
        attach(run, Brief(track="leet_reading", area="인문", item_type="추론", item_format="일반", discourse="평서문"))
    mixed = track_brief(count=2, set=True, ids=["A", "B"], item_type="혼합")
    run2 = prepared(tmp_path, mixed, name="mixed")
    with pytest.raises(ValueError, match="혼합"):
        attach(run2, mixed)


def test_missing_index_never_created_partial_attachment_never_retried(tmp_path):
    run = prepared(tmp_path)
    index = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        attach(run, track_brief(), index_path=index)
    assert not index.exists() and load(run / "status.json")["state"] == "failed"
    with pytest.raises(ValueError):
        attach(run, track_brief())


def test_duplicate_attach_and_execution_preserve_prior_evidence(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    with pytest.raises(FileExistsError):
        attach(run, track_brief())
    provider = Provider(draft)
    run_staged(run, provider, 0)
    old = (run / "candidate.json").read_bytes()
    with pytest.raises(ValueError):
        run_staged(run, provider, 0)
    assert (run / "candidate.json").read_bytes() == old and len(provider.calls) == 5


@pytest.mark.parametrize("stage", ["material", "design"])
def test_stage_id_drift_stops_before_writing_and_cannot_retry(tmp_path, draft, stage):
    run = prepared(tmp_path)
    attach(run, track_brief())
    normal = Provider(draft)
    def hook(name, payload, _):
        if name == stage:
            from haean.staged_authoring import MaterialResult, DesignResult
            schema = MaterialResult if name == "material" else DesignResult
            value = normal.call(name, "", payload, schema)
            (value.materials if name == "material" else value.items)[0].item_id = "UNREQUESTED"
            return value
    provider = Provider(draft, hook)
    with pytest.raises(ValueError, match="ID"):
        run_staged(run, provider, 0)
    assert not (run / "candidate.json").exists()
    assert load(run / "status.json")["state"] == "failed"
    assert load(run / "usage.json")[-1]["stage"] == stage
    with pytest.raises(ValueError):
        run_staged(run, provider, 0)


def test_revision_rechecks_spec_and_uses_fresh_blind_reviews(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    normal = Provider(draft)
    def hook(stage, payload, _):
        if stage == "generate":
            value = normal.call(stage, "", payload, Draft)
            value.items[0].difficulty = "상"
            value.items[0].source_ids = ["track-only-id"]
            return value
    provider = Provider(draft, hook)
    result = run_staged(run, provider, 1)
    assert [c[0] for c in provider.calls] == ["material", "design", "generate", "blind", "editor", "revise", "blind", "editor"]
    errors = load(run / "review-r0.json")["errors"]
    assert any("difficulty" in e for e in errors) and any("미등록" in e for e in errors)
    assert result.items[0].difficulty == "하" and result.items[0].source_ids == ["source-1"]
    assert load(run / "status.json")["state"] == "awaiting_human_review"
    assert len(load(run / "staged/review-bindings.json")["reviews"]) == 2
    revise = next(c[2] for c in provider.calls if c[0] == "revise")
    assert revise["context"]["staged_contract"]["brief"]["ids"] == ["TEST-001"]


def test_stage_failure_preserves_inputs_usage_and_trace(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    trace = run / "codex-traces"
    trace.mkdir()
    def hook(stage, payload, _):
        (trace / "01-material.stderr.txt").write_text("synthetic failure")
        raise RuntimeError("synthetic failure")
    provider = Provider(draft, hook)
    with pytest.raises(RuntimeError):
        run_staged(run, provider)
    assert (run / "staged/material-input.json").exists()
    assert (trace / "01-material.stderr.txt").read_text() == "synthetic failure"
    assert load(run / "status.json")["stage"] == "material"
    assert load(run / "usage.json")[0]["stage"] == "material"
    assert (run / "staged/snapshot-initial/manifest.json").exists()


@pytest.mark.parametrize("target", ["context.json", "staged/track-brief.json"])
def test_attached_input_change_blocks_all_model_calls(tmp_path, draft, target):
    run = prepared(tmp_path)
    attach(run, track_brief())
    (run / target).write_text("{}")
    provider = Provider(draft)
    with pytest.raises(ValueError, match="변경"):
        run_staged(run, provider, 0)
    assert provider.calls == [] and load(run / "status.json")["state"] == "failed"


def reference_index(tmp_path):
    source = tmp_path / "synthetic-source.txt"
    source.write_text("공개용 합성 참고 파일")
    rows = []
    for grade in (5, 7):
        rows.append({"id": "same-local-id", "track": "psat_situation", "grade": grade, "role": "item",
                     "area": "생활·일상(가상)", "item_type": "조건 추론", "item_format": "일반", "discourse": "평서문",
                     "text": f"합성 {grade}급 참고", "provenance": {"file": str(source), "locator": f"synthetic:{grade}",
                     "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "usage": "development"}})
    raw = tmp_path / "synthetic-references.jsonl"
    raw.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    db = tmp_path / "references.sqlite"
    with ReferenceIndex(db) as index:
        index.build(raw)
    return db, source


def test_optional_references_keep_grade_namespace_and_legacy_ids(tmp_path, draft):
    db, _ = reference_index(tmp_path)
    run = prepared(tmp_path)
    attach(run, track_brief(), index_path=db)
    references = load(run / "staged/references.json")
    hits = [h for queries in references.values() for result in queries.values() for h in result["hits"]]
    assert hits and {h["grade"] for h in hits} == {7}
    result = run_staged(run, Provider(draft), 0)
    assert result.items[0].source_ids == ["source-1"]
    assert load(run / "context.json")["references"][0]["id"] == "source-1"
    assert load(run / "staged/snapshot-review/manifest.json")["inputs"]["reference-source-0"]["path"]


@pytest.mark.parametrize("timing", ["before_run", "during_material"])
def test_reference_source_change_blocks_completion(tmp_path, draft, timing):
    db, source = reference_index(tmp_path)
    run = prepared(tmp_path)
    attach(run, track_brief(), index_path=db)
    def hook(stage, payload, _):
        if stage == "material":
            source.write_text("changed")
    if timing == "before_run":
        source.write_text("changed")
    provider = Provider(draft, hook if timing == "during_material" else None)
    with pytest.raises(ValueError, match="변경|스냅샷"):
        run_staged(run, provider, 0)
    assert load(run / "status.json")["state"] == "failed" and not (run / "candidate.json").exists()


def test_change_during_editor_blocks_success_even_with_candidate(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    def hook(stage, payload, _):
        if stage == "editor":
            (run / "staged/snapshot-review/instructions.json").write_text("{}")
    with pytest.raises(ValueError, match="스냅샷"):
        run_staged(run, Provider(draft, hook), 0)
    assert (run / "candidate.json").exists()
    assert load(run / "status.json")["state"] == "failed"
    assert load(run / "status.json")["human_approved"] is False


def test_shared_passage_figures_are_checked_without_block_conversion(tmp_path, draft):
    brief = track_brief(count=2, set=True, ids=["ONE", "TWO"])
    run = prepared(tmp_path, brief)
    attach(run, brief)
    result = run_staged(run, Provider(draft), 0)
    assert load(run / "status.json")["state"] == "awaiting_human_review"
    result.items[1].figures = [Figure(id="common", placement="passage", kind="bar", title="합성 그림",
        x_label="범주", y_label="수", categories=["가"], series=[{"name": "계열", "values": [1]}], nodes=[], edges=[], note="")]
    errors = validate_staged(result, load(run / "staged/contract.json"))
    assert any("공통지문 그림" in error for error in errors)


def test_persisted_material_change_during_design_is_not_accepted(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    def hook(stage, payload, _):
        if stage == "design":
            (run / "staged/material.json").write_text("{}")
    with pytest.raises(ValueError, match="입력·출력"):
        run_staged(run, Provider(draft, hook), 0)
    assert not (run / "candidate.json").exists()


def test_candidate_draft_changed_during_blind_cannot_be_bound_to_review(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    def hook(stage, payload, _):
        if stage == "blind":
            saved = load(run / "draft-r0.json")
            saved["items"][0]["answer"] = 2
            save(run / "draft-r0.json", saved)
    with pytest.raises(ValueError, match="검토 대상"):
        run_staged(run, Provider(draft, hook), 0)
    assert load(run / "status.json")["state"] == "failed"
    assert not (run / "staged/review-bindings.json").exists()


def test_previous_review_tampered_during_next_editor_cannot_complete(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    normal = Provider(draft)
    def hook(stage, payload, provider):
        if stage == "generate":
            value = normal.call(stage, "", payload, Draft)
            value.items[0].difficulty = "상"
            return value
        if stage == "editor" and sum(call[0] == "editor" for call in provider.calls) == 2:
            previous = load(run / "review-r0.json")
            previous["editorial"]["summary"] = "tampered after review"
            save(run / "review-r0.json", previous)
    with pytest.raises(ValueError, match="검토 결과가 변경"):
        run_staged(run, Provider(draft, hook), 1)
    assert load(run / "status.json")["state"] == "failed"
    assert not (run / "staged/review-bindings.json").exists()


def test_context_edited_during_material_is_preserved_and_run_stops(tmp_path, draft):
    run = prepared(tmp_path)
    attach(run, track_brief())
    changed = load(run / "context.json")
    changed["feedback"].append({"note": "동시 편집한 합성 피드백"})
    def hook(stage, payload, _):
        if stage == "material":
            save(run / "context.json", changed)
    provider = Provider(draft, hook)
    with pytest.raises(ValueError, match="편집본을 보존"):
        run_staged(run, provider, 0)
    assert load(run / "context.json") == changed
    assert all(call[0] != "generate" for call in provider.calls)
    assert load(run / "status.json")["state"] == "failed"
