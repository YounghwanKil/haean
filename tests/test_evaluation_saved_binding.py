"""Saved composition reviews bind reevaluation to the actual archived inputs."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from haean.evaluation import DIMENSIONS
from haean.evaluation_run import evaluate_run
from haean.pipeline import save
from test_composition_adapter import completed_bundle, inputs, read


class Evaluator:
    def __init__(self):
        self.calls, self.usage, self.payloads = 0, [], []

    def call(self, stage, instructions, payload, schema):
        assert stage == "evaluate"
        self.calls += 1
        self.payloads.append(deepcopy(payload))
        return schema(items=[{
            "item_id": item["id"],
            "dimensions": [{"name": name, "score": 3, "evidence": "합성 평가 근거"}
                           for name in sorted(DIMENSIONS)],
            "fatal_errors": [], "missing_evidence": ["합성 테스트이며 전문가 확인은 없음"],
            "expert_verified": False,
        } for item in payload["draft"]["items"]], summary="합성 저장 문항 평가")


def original_bytes(run, inputs):
    paths = [*run.rglob("*"), *inputs.values()]
    return {str(path): path.read_bytes() for path in paths if path.is_file()}


@pytest.fixture
def saved_bundle(inputs, tmp_path, draft, monkeypatch):
    # The synthetic pipeline still writes real composition bindings and review hashes.
    run, expected, _, candidate = completed_bundle(inputs, tmp_path, draft)
    monkeypatch.setattr("haean.evaluation_run.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(stdout="synthetic-codex-version\n"))
    return run, expected, candidate


def test_cli_saved_revision_can_be_eligible_only_with_matching_binding(
        saved_bundle, inputs, tmp_path, monkeypatch, capsys):
    from haean.cli import main

    run, expected, candidate = saved_bundle
    before = original_bytes(run, inputs)
    evaluator = Evaluator()
    monkeypatch.setattr("haean.evaluation_run.CodexProvider", lambda *args, **kwargs: evaluator)
    out = tmp_path / "reevaluated-r0"
    monkeypatch.setattr("sys.argv", ["haean-tool", "evaluate-run", str(run), "--revision", "0",
                                    "--out", str(out)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result == read(out / "result.json")

    assert evaluator.calls == 1
    assert result["complete"] and result["model_eligible"] and result["eligible"]
    assert result["selected_revision"] == 0 and result["selected_current"] is False
    assert result["saved_provenance"]["requirements"] == "composition_binding"
    assert result["saved_provenance"]["review"] == "composition_revision_binding"
    assert result["saved_provenance"]["errors"] == []
    assert result["sources"]["composition_plan"] == expected["plan"]
    assert result["sources"]["bound_draft"] == read(run / "composition-review-r0.json")["draft"]
    assert evaluator.payloads[0]["draft"] == candidate.model_dump()
    assert evaluator.payloads[0]["requirements_source"] == "context.exam_assignment"
    assert [row["id"] for row in evaluator.payloads[0]["item_requirements"]] == [i.id for i in candidate.items]
    assert original_bytes(run, inputs) == before
    assert result["expert_verified"] is False and result["human_approved"] is False
    assert result["release_approved"] is False and result["generation_calls"] == 0


@pytest.mark.parametrize("changed", ["draft_text", "review_text", "missing_context",
                                     "assignment", "original_plan", "missing_saved_review_binding"])
def test_broken_saved_binding_is_refused_before_model_or_output(
        saved_bundle, inputs, tmp_path, changed):
    run, _, candidate = saved_bundle
    if changed == "draft_text":
        path = run / "draft-r0.json"
        data = read(path)
        data["items"][0]["passage"] += " 동일 ID를 유지한 채 검토 후 지문이 바뀌었다."
        assert [item["id"] for item in data["items"]] == [item.id for item in candidate.items]
        save(path, data)
    elif changed == "review_text":
        path = run / "review-r0.json"
        data = read(path)
        data["editorial"]["summary"] += " 검토 후에 바뀐 결론."
        save(path, data)
    elif changed == "missing_context":
        (run / "context.json").unlink()
    elif changed == "assignment":
        path = run / "context.json"
        data = read(path)
        data["exam_assignment"][0]["difficulty"] = "상"
        save(path, data)
    elif changed == "original_plan":
        data = read(inputs["plan"])
        data["slots"][0]["topic"] = "검토 후 변경한 원 배정 소재"
        save(inputs["plan"], data)
    else:
        (run / "composition-review-r0.json").unlink()

    # Refusal must not recreate a context/seal or restore changed source bytes.
    before = original_bytes(run, inputs)
    evaluator, out = Evaluator(), tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="해시|누락"):
        evaluate_run(run, out, revision=0, provider=evaluator)
    assert evaluator.calls == 0 and not out.exists()
    assert original_bytes(run, inputs) == before
