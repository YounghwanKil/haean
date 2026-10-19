"""Real 7급 design/binding/build/resume with synthetic local sources and calls.

The composition loader, evidence snapshots, validation and review receipts stay
real. Only corpus preparation, model calls and document rendering are stubbed.
These tests establish integration contracts, not exam quality or model scores.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from haean import cli, composition_adapter as adapter, composition_resume, full_exam
from haean.composition import design, load_design
from haean.composition.profiles import sha
from haean.exam_resume import resume
from haean.models import Calculation, Table
from haean.pipeline import save
from test_composition_adapter import Provider, prepared, read


SUBJECTS = [("언어논리", "psat_verbal"), ("자료해석", "psat_data"), ("상황판단", "psat_situation")]
PRIVATE = "FLOW_EDITOR_ONLY_정답설계비밀"
SYNTHETIC_MODEL = "synthetic-test-provider"


def source_profile(root, subject, track):
    """Four independent grade-7 source files; quotas are synthetic, not official."""
    root.mkdir()
    identity = {"schema_version": 1, "engine": "psat7-v1", "exam_grade": 7, "subject": subject}
    values = {
        "format_rules": {**identity, "total_slots": 25,
            "types": [
                {"code": "A", "label": "합성 외부 유형 A", "count": 13, "response_formats": ["선택형"]},
                {"code": "B", "label": "합성 외부 유형 B", "count": 12, "response_formats": ["선택형"]}],
            "shared_sets": [{"id": "source-pair", "members": [24, 25], "types": ["A", "B"]}],
            "difficulty_counts": {"하": 10, "중": 10, "상": 5}},
        "content_rules": {**identity, "types": {code: {
            "domains": ["합성 규칙"], "reasoning_tasks": ["명시된 조건 연결"],
            "distractor_paths": ["조건의 역을 가정"], "review_checks": ["제시된 조건만으로 판단"],
            "construction_notes": [PRIVATE, "외부 참고 source-pool-opaque는 실제 내용 출처가 아님"]}
            for code in ("A", "B")}},
        "content_config": {**identity,
            "common_passage_policy": ["명시한 두 문항에만 공통 지문 사용"],
            "difficulty_policy": ["프로필 난도는 합성 편집 목표"],
            "source_policy": ["준비 단계에서 조회한 출처만 사용"],
            "subject_review": [subject + "의 문항별 근거 검토"]},
        "rules_config": {**identity, "observations": {"basis": "synthetic only"},
            "editorial_decisions": ["7급 전용 25문항 합성 테스트"]},
    }
    records = []
    for role, value in values.items():
        path = root / f"{role}.json"
        save(path, value)
        records.append({"role": role, "path": path.name, "sha256": sha(path),
            "usage": "development", "exam_grade": 7, "locator": f"synthetic:{subject}:{role}"})
    profile = root / "profile.json"
    save(profile, {"schema_version": 1, "exam": "psat7", "exam_grade": 7,
        "subject": subject, "track": track, "usage": "development",
        "origin": {"source": "synthetic grade-7 integration fixture", "revision": "1"}, "files": records})
    return profile


def hashes(root):
    return {str(path.relative_to(root)): sha(path) for path in root.rglob("*") if path.is_file()}


@pytest.fixture(params=SUBJECTS, ids=[row[0] for row in SUBJECTS])
def composition_inputs(tmp_path, request):
    subject, track = request.param
    profile = source_profile(tmp_path / "sources", subject, track)
    proposal = design(profile, tmp_path / "design", seed=71, options={"size": 25})
    design_path = Path(proposal["design"])
    packet = load_design(design_path)
    formats = {row["slot"]: row for row in packet["format_design"]["slots"]}
    slots, mapping = [], []
    for number in range(1, 26):
        external = formats[26 - number]
        identifier = "opaque-" + hashlib.sha256(f"stable-{subject}-{number}".encode()).hexdigest()[:16]
        slot = {"number": number, "id": identifier, "topic": f"기존 고정 소재 {number}",
            "item_type": "기존 조건 적용" if external["type_code"] == "A" else "기존 관계 비교",
            "domain": "합성 규칙", "difficulty": "하",
            "shared_passage_id": "legacy-pair-opaque" if external["set_id"] else None}
        slots.append(slot)
        mapping.append({"number": number, "item_id": identifier, "external_slot": external["slot"],
            "legacy_item_type": slot["item_type"], "external_type": external["type"],
            "mapping_rationale": "합성 테스트의 명시적 역순 대응; 자동 유형 환산 아님",
            "external_set_key": external["set_id"], "shared_passage_id": slot["shared_passage_id"],
            "external_difficulty": external["difficulty"], "difficulty_mapping": {
                "legacy": "하", "external": external["difficulty"], "rationale": "합성 대응을 명시; 실측 환산 아님"}})
    plan_path, mapping_path = tmp_path / "plan.json", tmp_path / "mapping.json"
    # Noncanonical bytes must survive build and resume without normalization.
    plan_path.write_text(json.dumps({"exam": "psat7", "subject": subject, "slots": slots},
                                   ensure_ascii=False, separators=(",", ":")) + "\n\n")
    save(mapping_path, list(reversed(mapping)))
    return {"profile": profile, "design": design_path, "plan": plan_path, "mapping": mapping_path,
            "sources": profile.parent, "proposal": proposal}


class SyntheticProvider(Provider):
    def __init__(self, template, *, interrupt_pair=False):
        super().__init__(template)
        self.interrupt_pair = interrupt_pair

    def call(self, stage, instructions, payload, schema):
        if stage == "blind" and self.interrupt_pair and payload["items"][0]["shared_passage_id"]:
            raise RuntimeError("synthetic interruption before pair review")
        result = super().call(stage, instructions, payload, schema)
        if stage in {"generate", "revise"}:
            for item in result.items:
                if item.shared_passage_id:
                    item.passage = "합성 공통 지문. 예약 승인 시 알림을 보낸다. 두 예약이 승인되었다."
                if item.subject == "자료해석":
                    item.tables = [Table(title="합성 건수", unit="건", columns=["구분", "건수"],
                        rows=[["승인", "2"], ["대기", "1"]], note="테스트 수치")]
                    item.calculations = [Calculation(label="합계", expression="2 + 1", expected="3",
                        unit="건", evidence="표의 승인 2건과 대기 1건")]
        return result


def runtime(monkeypatch, draft, *, interrupt_pair=False):
    providers = []

    def fake_prepare(_corpus, brief, root):
        root = Path(root)
        index = len(list(root.iterdir())) if root.exists() else 0
        slots = [{"number": n + 1, "id": f"prepare-only-{n}", "item_type": brief.item_type,
            "topic": brief.topic, "domain": "합성 규칙", "difficulty": brief.difficulty,
            "shared_passage_id": "prepare-only-pair" if brief.shared_passage else None}
            for n in range(brief.count)]
        run = prepared(root / f"synthetic-{index}", slots, brief.subject, brief.exam)
        context = read(run / "context.json")
        context["brief"] = brief.model_dump()
        context.pop("exam_assignment")
        save(run / "context.json", context)
        save(run / "brief.json", brief.model_dump())
        return run

    def fake_provider(*args, **kwargs):
        provider = SyntheticProvider(draft, interrupt_pair=interrupt_pair)
        providers.append(provider)
        return provider

    for module in (full_exam, composition_resume):
        monkeypatch.setattr(module, "Corpus", lambda _db: None)
        monkeypatch.setattr(module, "prepare", fake_prepare)
        monkeypatch.setattr(module, "CodexProvider", fake_provider)
    monkeypatch.setattr(full_exam, "render_exam", lambda *args: None)
    return providers


def assert_private_context_and_public_blind(providers):
    for provider in providers:
        for stage, _, payload in provider.calls:
            if stage == "generate":
                assert PRIVATE in json.dumps(payload["composition_context"], ensure_ascii=False)
            elif stage == "editor":
                assert PRIVATE in json.dumps(payload["additional_context"], ensure_ascii=False)
            elif stage == "blind":
                assert set(payload) == {"items"}
                text = json.dumps(payload, ensure_ascii=False)
                assert PRIVATE not in text and "source-pool-opaque" not in text
                for item in payload["items"]:
                    assert set(item) == {"id", "stem", "passage", "statements", "tables", "options",
                                         "shared_passage_id", "figures"}


def assert_complete(out, result, plan):
    assert result["requested"] == result["written"] == 25
    assert result["ready_for_human_review"], result["errors"]
    assert not result["human_approved"] and not result["layout_verified"] and not result["delivery_ready"]
    assert not result["external_composition"]["quality_verified"]
    assert not result["external_composition"]["semantic_compliance_verified"]
    production = read(out / "production.json")
    assert production["total"] == 25 and production["complete"] and not production["human_approved"]
    provenance = read(out / "provenance.json")
    assert provenance["model"] == SYNTHETIC_MODEL and not provenance["expert_verified"]
    items = read(out / "exam-items.json")["items"]
    assert [item["id"] for item in items] == [slot["id"] for slot in plan["slots"]]
    assert [item["topic"] for item in items] == [slot["topic"] for slot in plan["slots"]]
    assert all(item["source_ids"] == ["source-1"] for item in items)
    assert items[0]["passage"] == items[1]["passage"]
    assert items[0]["shared_passage_id"] == items[1]["shared_passage_id"] == "legacy-pair-opaque"
    for job in production["jobs"]:
        run = Path(job["run"])
        receipt = read(run / "composition-review-r0.json")
        assert receipt["inputs"] == job["composition"]
        for key in ("draft", "review"):
            assert sha(receipt[key]["path"]) == receipt[key]["sha256"]
        state = read(run / "status.json")
        assert state["candidate_sha256"] == sha(run / "candidate.json")
    return production


def test_real_design_bind_build_and_resume_25(composition_inputs, tmp_path, draft, monkeypatch):
    paths = composition_inputs
    original_sources = hashes(paths["sources"])
    original_plan = paths["plan"].read_bytes()
    proposal = paths["proposal"]
    assert proposal["slots"] == 25 and not proposal["model_generation_executed"] and not proposal["human_approved"]
    packet_path = adapter.bind(paths["plan"], paths["design"], paths["mapping"], tmp_path / "bound")
    packet = adapter.load_packet(packet_path, paths["plan"])
    plan = read(paths["plan"])
    assert len(packet["bindings"]) == len(packet["format_design"]["slots"]) == len(packet["content_spec"]["슬롯"]) == 25
    assert [row["external_slot"] for row in packet["bindings"]] == list(range(25, 0, -1))
    assert [row["item_id"] for row in packet["bindings"]] == [slot["id"] for slot in plan["slots"]]
    assert [row["number"] for row in packet["bindings"] if row["external_set_key"]] == [1, 2]

    providers = runtime(monkeypatch, draft)
    complete = tmp_path / "complete"
    result = full_exam.build(paths["plan"], "unused", complete, workers=1, max_revisions=0,
                             model=SYNTHETIC_MODEL, composition_packet=packet_path)
    assert_complete(complete, result, plan)
    assert (complete / "plan.json").read_bytes() == original_plan
    assert_private_context_and_public_blind(providers)

    interrupted_providers = runtime(monkeypatch, draft, interrupt_pair=True)
    previous = tmp_path / "interrupted"
    partial = full_exam.build(paths["plan"], "unused", previous, workers=1, max_revisions=0,
                              model=SYNTHETIC_MODEL, composition_packet=packet_path)
    assert partial["written"] == 23 and not partial["ready_for_human_review"]
    before = read(previous / "production.json")
    failed = [job for job in before["jobs"] if job["state"] == "failed"]
    assert len(failed) == 1 and failed[0]["slots"] == [1, 2]
    origin = Path(failed[0]["run"])
    assert (origin / "draft-r0.json").exists() and not (origin / "review-r0.json").exists()
    assert all((Path(job["run"]) / "composition-review-r0.json").exists()
               for job in before["jobs"] if job["state"] == "awaiting_human_review")
    original_parent = hashes(previous)

    resumed_providers = runtime(monkeypatch, draft)
    out = tmp_path / "resumed"
    result = resume(previous, "unused", out, workers=1, max_revisions=0, model=SYNTHETIC_MODEL)
    production = assert_complete(out, result, plan)
    assert sum(job["reused"] for job in production["jobs"]) == len(before["jobs"]) - 1
    assert len(resumed_providers) == 1
    assert [stage for stage, _, _ in resumed_providers[0].calls] == ["blind", "editor"]
    new_job = next(job for job in production["jobs"] if not job["reused"])
    assert new_job["slots"] == [1, 2] and new_job["ids"] == failed[0]["ids"]
    new_context = read(Path(new_job["run"]) / "context.json")
    assert new_context["resume_lineage"]["seed_path"] == str(origin / "draft-r0.json")
    assert new_context["resume_lineage"]["seed_sha256"] == sha(origin / "draft-r0.json")
    assert new_context["references"] == read(origin / "context.json")["references"]
    assert (out / "plan.json").read_bytes() == original_plan
    assert hashes(previous) == original_parent and hashes(paths["sources"]) == original_sources
    assert_private_context_and_public_blind([*interrupted_providers, *resumed_providers])


def test_compose_cli_check_reports_25(composition_inputs, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["haean-tool", "compose", "check", str(composition_inputs["design"])])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] and result["slots"] == 25
    assert not result["quality_verified"] and not result["human_approved"]


@pytest.mark.parametrize("mutation", ["source", "forty_plan", "wrong_pair", "boolean_plan_number"])
def test_invalid_inputs_fail_before_provider_or_output(composition_inputs, tmp_path, monkeypatch, mutation):
    paths = composition_inputs
    monkeypatch.setattr(full_exam, "CodexProvider", lambda *a, **kw: pytest.fail("provider before validation"))
    monkeypatch.setattr(full_exam, "prepare", lambda *a, **kw: pytest.fail("prepare before validation"))
    if mutation == "source":
        packet_path = adapter.bind(paths["plan"], paths["design"], paths["mapping"], tmp_path / "bound")
        source = paths["sources"] / "content_rules.json"
        source.write_text(source.read_text() + "\n")
        with pytest.raises(ValueError, match="해시 불일치"):
            full_exam.build(paths["plan"], "unused", tmp_path / "blocked", composition_packet=packet_path)
        assert not (tmp_path / "blocked").exists()
    else:
        if mutation == "forty_plan":
            plan = read(paths["plan"])
            plan["exam"] = "psat5"
            for number in range(26, 41):
                row = deepcopy(plan["slots"][-1])
                row.update(number=number, id=f"grade5-only-{number}", shared_passage_id=None)
                plan["slots"].append(row)
            save(paths["plan"], plan)
        elif mutation == "boolean_plan_number":
            plan = read(paths["plan"])
            plan["slots"][0]["number"] = True
            save(paths["plan"], plan)
        else:
            mapping = read(paths["mapping"])
            # Move one explicit external set member onto a singleton slot.
            by_number = {row["number"]: row for row in mapping}
            by_number[2]["external_set_key"], by_number[3]["external_set_key"] = None, "source-pair"
            save(paths["mapping"], mapping)
        with pytest.raises(ValueError):
            adapter.bind(paths["plan"], paths["design"], paths["mapping"], tmp_path / "blocked")
        assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("subject,track", SUBJECTS, ids=[row[0] for row in SUBJECTS])
@pytest.mark.parametrize("invalid", ["forty_profile", "nonadjacent_set"])
def test_invalid_source_contract_cannot_create_design(tmp_path, subject, track, invalid):
    profile = source_profile(tmp_path / "sources", subject, track)
    source = profile.parent / "format_rules.json"
    value = read(source)
    if invalid == "forty_profile":
        value["total_slots"] = 40
    else:
        value["shared_sets"][0]["members"] = [23, 25]
    save(source, value)
    manifest = read(profile)
    next(row for row in manifest["files"] if row["role"] == "format_rules")["sha256"] = sha(source)
    save(profile, manifest)
    with pytest.raises(ValueError):
        design(profile, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()
