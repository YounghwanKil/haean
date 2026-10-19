"""Synthetic contracts; no corpus data or model execution is required."""
import copy
import json
from pathlib import Path

import pytest

from haean import composition_adapter as adapter
from haean.models import Brief
from haean.pipeline import run_pipeline, save


def read(path):
    return json.loads(Path(path).read_text())


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    """Mock only the upstream engine loader; preserve actual file/hash checks."""
    plan = {"exam": "leet", "subject": "추리논증", "slots": [
        {"number": n, "id": f"opaque-{chr(65 + n // 10)}-{50-n}", "item_type": "조건 추론",
         "topic": f"고정 소재 {n}", "domain": "규범", "difficulty": "하"} for n in range(1, 41)]}
    source, snapshot = tmp_path / "rules.json", tmp_path / "runtime.json"
    save(source, {"synthetic": True})
    save(snapshot, {"synthetic_runtime": "fixed"})
    design = {"schema_version": 1, "exam": "leet", "subject": "추리논증", "track": "leet_reasoning", "exam_grade": None,
        "format_design": {"meta": {"synthetic": True}, "slots": [
            {"slot": n, "type": "조건 원리", "difficulty": 2, "answer": 5} for n in range(1, 41)]},
        "content_spec": {"슬롯": [{"slot": n, "소재": {"범위_지시": "자유 소재 제안"},
                                "논리_설계": {"정답_조건": f"편집 전용 비밀 {n}"}} for n in range(1, 41)]},
        "profile": {"files": [{"role": "format_rules", **adapter._file_ref(source), "usage": "development", "locator": "synthetic"}]},
        "execution_snapshot": adapter._file_ref(snapshot), "validation": {"errors": [], "warnings": [], "unavailable_checks": []}}
    mapping = [{"number": slot["number"], "item_id": slot["id"], "external_slot": 41-slot["number"],
                "legacy_item_type": slot["item_type"], "external_type": "조건 원리", "mapping_rationale": "합성 명시 대응",
                "external_set_key": None, "shared_passage_id": None, "external_difficulty": 2,
                "difficulty_mapping": {"legacy": "하", "external": 2, "rationale": "척도 환산이 아니라 합성 대응 승인"}}
               for slot in reversed(plan["slots"])]
    paths = {"plan": tmp_path / "plan.json", "design": tmp_path / "design.json", "mapping": tmp_path / "mapping.json",
             "source": source, "runtime": snapshot}
    for key, data in (("plan", plan), ("design", design), ("mapping", mapping)):
        save(paths[key], data)

    def fake_load(path, *, verify_runtime=True):
        value = read(path)
        for ref in value["profile"]["files"]:
            adapter._verify_ref(ref, "source")
        adapter._verify_ref(value["execution_snapshot"], "runtime")
        return value

    monkeypatch.setattr(adapter, "_load_design", fake_load)
    return paths


def packet(inputs, tmp_path):
    return adapter.bind(inputs["plan"], inputs["design"], inputs["mapping"], tmp_path / "bound")


def prepared(root, slots, subject="추리논증", exam="leet"):
    root.mkdir(parents=True)
    brief = Brief(exam=exam, subject=subject, item_type=slots[0]["item_type"], topic=" / ".join(s["topic"] for s in slots),
                  count=len(slots), difficulty="하", shared_passage=bool(slots[0].get("shared_passage_id")))
    context = {"brief": brief.model_dump(), "references": [{"id": "source-1", "text": "합성 출처"}],
               "retrieval": {"synthetic": True}, "exam_assignment": slots}
    for name, data in (("context.json", context), ("brief.json", brief.model_dump()),
                       ("provenance.json", {"source_ids": ["source-1"]}), ("retrieval.json", context["retrieval"]),
                       ("status.json", {"state": "prepared", "human_approved": False})):
        save(root / name, data)
    (root / "request.md").write_text("합성 준비 요청")
    return root


class Provider:
    def __init__(self, template, hook=None):
        self.template, self.hook, self.calls, self.usage = template, hook, [], []

    def call(self, stage, instructions, payload, schema):
        self.calls.append((stage, instructions, copy.deepcopy(payload)))
        if self.hook:
            self.hook(stage)
        if stage in {"generate", "revise"}:
            context = payload if stage == "generate" else payload["context"]
            items = []
            for slot in context["exam_assignment"]:
                item = self.template.items[0].model_copy(deep=True)
                for key in ("id", "item_type", "topic", "domain", "difficulty"):
                    setattr(item, key, slot[key])
                item.subject = context["brief"]["subject"]
                item.shared_passage_id = slot.get("shared_passage_id")
                item.passage += " " + slot["id"]
                items.append(item)
            return schema(design_summary="합성 legacy 직접 작성", items=items)
        if stage == "blind":
            return schema(solutions=[{"item_id": item["id"], "answer": 1, "uniquely_answerable": True,
                                     "option_reasons": ["합성 근거"] * 5, "missing_conditions": []} for item in payload["items"]], issues=[])
        return schema(issues=[], summary="합성 편집 검토")


def completed_bundle(inputs, tmp_path, draft):
    bound = packet(inputs, tmp_path)
    slots = read(inputs["plan"])["slots"][:2]
    run = prepared(tmp_path / "bundle", slots)
    expected = adapter.attach_bundle(run, plan_path=inputs["plan"], packet_path=bound, slots=slots)
    provider = Provider(draft)
    candidate = run_pipeline(run, provider, max_revisions=0, **adapter.pipeline_callbacks(run, expected))
    return run, expected, provider, candidate


def test_explicit_permuted_slot_mapping_preserves_opaque_ids(inputs, tmp_path):
    bound = packet(inputs, tmp_path)
    result = adapter.load_packet(bound, inputs["plan"])
    assert result["bindings"][0]["item_id"] == read(inputs["plan"])["slots"][0]["id"]
    assert result["bindings"][0]["external_slot"] == 40
    assert result["plan"]["sha256"] == adapter._sha(inputs["plan"])
    assert result["design"]["sha256"] == adapter._sha(inputs["design"])
    assert result["validation"]["unavailable_checks"] == adapter.LIMITS
    with pytest.raises(FileExistsError):
        packet(inputs, tmp_path)


@pytest.mark.parametrize("kind", ["missing_format", "duplicate_content", "duplicate_mapping", "wrong_id", "wrong_type", "wrong_grade", "difficulty", "shared"])
def test_invalid_binding_rejected_before_artifact(inputs, tmp_path, kind):
    design, mapping = read(inputs["design"]), read(inputs["mapping"])
    if kind == "missing_format": design["format_design"]["slots"].pop()
    if kind == "duplicate_content": design["content_spec"]["슬롯"][0]["slot"] = 2
    if kind == "duplicate_mapping": mapping[0]["external_slot"] = mapping[1]["external_slot"]
    if kind == "wrong_id": mapping[0]["item_id"] = "inferred-id-40"
    if kind == "wrong_type": mapping[0]["external_type"] = "암묵 변환"
    if kind == "wrong_grade": design["exam_grade"] = 5
    if kind == "difficulty": mapping[0]["difficulty_mapping"] = None
    if kind == "shared": mapping[0]["external_set_key"] = "invented-pair"
    save(inputs["design"], design)
    save(inputs["mapping"], mapping)
    with pytest.raises(ValueError):
        packet(inputs, tmp_path)
    assert not (tmp_path / "bound").exists()


def test_verbal_sets_use_raw_rules_membership_not_boolean_position(inputs, tmp_path):
    plan, design, mapping = (read(inputs[key]) for key in ("plan", "design", "mapping"))
    plan.update(exam="psat5", subject="언어논리")
    design.update(exam="psat5", subject="언어논리", track="psat_verbal", exam_grade=5)
    for row in design["format_design"]["slots"]:
        row["set"] = row["slot"] in {3, 17}
    for row in mapping:
        if row["external_slot"] in {3, 17}:
            row.update(external_set_key="slots:3,17", shared_passage_id="shared-opaque")
            plan["slots"][row["number"] - 1]["shared_passage_id"] = "shared-opaque"
    save(inputs["source"], {"skeleton": {"sets": [[3, 17]]}})
    design["profile"]["files"][0].update(adapter._file_ref(inputs["source"]))
    for key, data in (("plan", plan), ("design", design), ("mapping", mapping)):
        save(inputs[key], data)
    bound = packet(inputs, tmp_path)
    assert len([r for r in adapter.load_packet(bound, inputs["plan"])["bindings"] if r["external_set_key"]]) == 2
    # Boolean set remains identical, but changing one pair to a guessed adjacent
    # pair must fail even when the human map is changed to match that guess.
    save(inputs["source"], {"skeleton": {"sets": [[3, 4]]}})
    design["profile"]["files"][0].update(adapter._file_ref(inputs["source"]))
    save(inputs["design"], design)
    with pytest.raises(ValueError, match="멤버십"):
        adapter.bind(inputs["plan"], inputs["design"], inputs["mapping"], tmp_path / "wrong-pair")


@pytest.mark.parametrize("changed", ["plan", "design", "mapping", "source", "runtime", "packet"])
def test_bound_input_mutation_invalidates_packet(inputs, tmp_path, changed):
    bound = packet(inputs, tmp_path)
    path = bound if changed == "packet" else inputs[changed]
    value = read(path)
    if changed == "mapping": value[0]["mapping_rationale"] += " 변경"
    else: value["mutation"] = True
    save(path, value)
    with pytest.raises(ValueError):
        adapter.load_packet(bound, inputs["plan"])


def test_direct_legacy_writer_and_editor_receive_design_but_blind_does_not(inputs, tmp_path, draft):
    run, expected, provider, candidate = completed_bundle(inputs, tmp_path, draft)
    calls = {stage: payload for stage, _, payload in provider.calls}
    assert calls["generate"]["composition_context"]["assignments"][0]["external_content"]["slot"] == 40
    assert calls["editor"]["additional_context"]["assignments"][0]["external_content"]["slot"] == 40
    blind = calls["blind"]
    assert set(blind) == {"items"}
    assert "비밀" not in json.dumps(blind, ensure_ascii=False)
    assert not {"answer", "judgments", "source_ids"} & blind["items"][0].keys()
    assert all(item.source_ids == ["source-1"] for item in candidate.items)
    assert "고정 소재" in candidate.items[0].topic
    assert candidate.items[0].answer == 1  # External answer=5 is advisory.
    state = read(run / "status.json")
    assert state["state"] == "awaiting_human_review"
    assert adapter.assembly_errors(run, expected, candidate, state) == []
    assert "기존 고정 소재·시험/유형·논리 조건·출처 검증이 우선" in (run / "request.md").read_text()


@pytest.mark.parametrize("changed", ["composition.json", "composition-binding.json", "context.json", "request.md", "brief.json", "provenance.json", "retrieval.json", "review-r0.json", "candidate.json"])
def test_post_review_mutation_cannot_pass_assembly(inputs, tmp_path, draft, changed):
    run, expected, _, candidate = completed_bundle(inputs, tmp_path, draft)
    path = run / changed
    path.write_text(path.read_text() + "\n")
    assert adapter.assembly_errors(run, expected, candidate, read(run / "status.json"))


def test_mutation_during_review_fails_preserving_artifacts(inputs, tmp_path, draft):
    bound = packet(inputs, tmp_path)
    slots = read(inputs["plan"])["slots"][:1]
    run = prepared(tmp_path / "bundle", slots)
    expected = adapter.attach_bundle(run, plan_path=inputs["plan"], packet_path=bound, slots=slots)
    def hook(stage):
        if stage == "editor":
            (run / "composition.json").write_text((run / "composition.json").read_text() + "\n")
    with pytest.raises(ValueError, match="해시"):
        run_pipeline(run, Provider(draft, hook), max_revisions=0, **adapter.pipeline_callbacks(run, expected))
    assert read(run / "status.json")["state"] == "failed"
    assert (run / "review-r0.json").exists() and (run / "draft-r0.json").exists()
    assert not (run / "candidate.json").exists()


def test_declared_sidecar_cannot_be_missing(inputs, tmp_path, draft):
    run, expected, _, candidate = completed_bundle(inputs, tmp_path, draft)
    (run / "composition.json").unlink()
    assert adapter.assembly_errors(run, expected, candidate, read(run / "status.json"))
    assert adapter.assembly_errors(run, None, candidate, read(run / "status.json"))


def test_incomplete_composition_resume_is_rejected_without_output(tmp_path):
    from haean.exam_resume import resume
    previous = tmp_path / "previous"
    previous.mkdir()
    save(previous / "production.json", {"composition": {}, "jobs": []})
    with pytest.raises(ValueError, match="회차 선언"):
        resume(previous, tmp_path / "db.sqlite", tmp_path / "next")
    assert not (tmp_path / "next").exists()


@pytest.mark.parametrize("mutation", ["changed_review", "corrupt_candidate", "corrupt_status", "corrupt_plan", "corrupt_production", "render_failure"])
def test_full_exam_optional_integration_and_mutation_gates(inputs, tmp_path, draft, monkeypatch, mutation):
    from haean.full_exam import build, assemble
    bound = packet(inputs, tmp_path)
    providers = []
    def prepare(_corpus, brief, root):
        run = Path(root) / f"bundle-{len(list(Path(root).glob('*'))) if Path(root).exists() else 0}"
        # full_exam assigns real opaque identities immediately after prepare.
        slots = [{"id": "preparing", "number": 1, "topic": brief.topic, "item_type": brief.item_type,
                  "domain": "규범", "difficulty": brief.difficulty}]
        prepared(run, slots)
        context = read(run / "context.json")
        context["brief"] = brief.model_dump()
        context.pop("exam_assignment")
        save(run / "brief.json", brief.model_dump())
        save(run / "context.json", context)
        return run
    def provider(*args, **kwargs):
        instance = Provider(draft)
        providers.append(instance)
        return instance
    monkeypatch.setattr("haean.full_exam.prepare", prepare)
    monkeypatch.setattr("haean.full_exam.Corpus", lambda _db: None)
    monkeypatch.setattr("haean.full_exam.CodexProvider", provider)
    monkeypatch.setattr("haean.full_exam.render_exam", lambda *args: None)
    out = tmp_path / "exam"
    result = build(inputs["plan"], "unused-db", out, workers=1, max_revisions=0, composition_packet=bound)
    assert result["written"] == 40 and result["ready_for_human_review"], result["errors"]
    assert (out / "plan.json").read_bytes() == inputs["plan"].read_bytes()
    production = read(out / "production.json")
    run = Path(production["jobs"][0]["run"])
    assert read(out / "items/01/status.json")["parent_review_run"] == str(run)
    if mutation == "changed_review":
        (run / "review-r0.json").write_text((run / "review-r0.json").read_text() + "\n")
    elif mutation == "render_failure":
        def broken_render(*args):
            raise ValueError("합성 출력 실패")
        monkeypatch.setattr("haean.full_exam.render_exam", broken_render)
    else:
        path = {"corrupt_candidate": run / "candidate.json", "corrupt_status": run / "status.json",
                "corrupt_plan": out / "plan.json", "corrupt_production": out / "production.json"}[mutation]
        path.write_text("{ broken JSON")
    after = assemble(out)
    assert not after["ready_for_human_review"]
    assert after["errors"]
    assert not read(out / "assembled.json")["ready_for_human_review"]
    assert not result["external_composition"]["quality_verified"]


def test_invalid_packet_blocks_full_exam_before_output_and_provider(inputs, tmp_path, monkeypatch):
    from haean.full_exam import build
    bound = packet(inputs, tmp_path)
    inputs["plan"].write_text(inputs["plan"].read_text() + "\n")
    monkeypatch.setattr("haean.full_exam.CodexProvider", lambda *a, **k: pytest.fail("provider should not initialize"))
    out = tmp_path / "blocked"
    with pytest.raises(ValueError, match="해시"):
        build(inputs["plan"], "unused", out, composition_packet=bound)
    assert not out.exists()


def test_candidate_difficulty_cannot_silently_change_assignment(inputs, tmp_path, draft):
    run, expected, _, candidate = completed_bundle(inputs, tmp_path, draft)
    candidate.items[0].difficulty = "상"
    assert any("난도 불일치" in error for error in adapter.validate_bundle(run, expected, candidate))


def test_fine_grained_plan_difficulty_is_not_silently_coerced(inputs, tmp_path):
    plan, mapping = read(inputs["plan"]), read(inputs["mapping"])
    plan["slots"][0]["difficulty"] = "중상"
    next(row for row in mapping if row["number"] == 1)["difficulty_mapping"]["legacy"] = "중상"
    save(inputs["plan"], plan)
    save(inputs["mapping"], mapping)
    with pytest.raises(ValueError, match="세부 난도를 임의 환산하지"):
        packet(inputs, tmp_path)
    assert not (tmp_path / "bound").exists()


def test_shared_passage_figures_must_match(inputs, tmp_path, draft):
    from haean.models import Draft, Figure
    plan, design, mapping = (read(inputs[key]) for key in ("plan", "design", "mapping"))
    plan.update(exam="psat5", subject="상황판단")
    design.update(exam="psat5", subject="상황판단", track="psat_situation", exam_grade=5)
    for row in design["format_design"]["slots"]:
        row["set_id"] = "raw-set" if row["slot"] in {39, 40} else None
    for row in mapping:
        if row["external_slot"] in {39, 40}:
            row.update(external_set_key="raw-set", shared_passage_id="shared")
            plan["slots"][row["number"] - 1]["shared_passage_id"] = "shared"
    for key, data in (("plan", plan), ("design", design), ("mapping", mapping)):
        save(inputs[key], data)
    bound = packet(inputs, tmp_path)
    slots = plan["slots"][:2]
    run = prepared(tmp_path / "shared", slots, subject="상황판단", exam="psat5")
    expected = adapter.attach_bundle(run, plan_path=inputs["plan"], packet_path=bound, slots=slots)
    items = []
    for slot in slots:
        item = draft.items[0].model_copy(deep=True)
        for key in ("id", "topic", "domain", "item_type", "difficulty", "shared_passage_id"):
            setattr(item, key, slot[key])
        item.subject = "상황판단"
        item.figures = [Figure(id="common", placement="passage", kind="bar", title="공통 수치",
            x_label="구분", y_label="개", categories=["가"], series=[{"name": "수량", "values": [2]}],
            nodes=[], edges=[], note="")]
        items.append(item)
    candidate = Draft(design_summary="합성 공통 그림", items=items)
    assert adapter.validate_bundle(run, expected, candidate) == []
    candidate.items[1].figures[0].series[0].values[0] = 3
    assert any("지문 그림 불일치" in error for error in adapter.validate_bundle(run, expected, candidate))
