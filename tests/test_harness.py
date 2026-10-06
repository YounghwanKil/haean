import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from haean.codex_runtime import CodexProvider, strict_schema
from haean.evaluation import compare, ItemEvaluation
from haean.models import StrictModel
from haean.style import protected_tokens
from haean.layout import package
from haean.pipeline import save
from haean.roles import role_packet


def test_portable_role_keeps_blind_context_contract():
    packet = role_packet('haean_blind_solver')
    assert packet['fresh_context'] is True
    assert packet['developer_instructions']
    with pytest.raises(ValueError):
        role_packet('../../unknown')


def test_subscription_runtime_uses_codex_and_strips_api_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-sent")
    monkeypatch.setenv("CODEX_API_KEY", "test-key-not-sent")
    monkeypatch.setattr("haean.codex_runtime.shutil.which", lambda _: "/codex")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[1] == "login": return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr="")
        assert "OPENAI_API_KEY" not in kwargs["env"] and "CODEX_API_KEY" not in kwargs["env"]
        assert "--ephemeral" in command and "--output-schema" in command
        assert command[command.index("-m") + 1] == "gpt-6-astra"
        assert Path(command[command.index("-C") + 1]) != Path.cwd()
        Path(command[command.index("-o") + 1]).write_text('{"status":"ready"}')
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed","usage":{"output_tokens":3}}', stderr="")
    monkeypatch.setattr("haean.codex_runtime.subprocess.run", run)
    class Result(StrictModel): status: str
    provider = CodexProvider(trace_dir=tmp_path)
    assert provider.call("blind", "solve", {"question": "q"}, Result).status == "ready"
    assert len(calls) == 2


def test_subscription_runtime_rejects_tool_contamination(monkeypatch, tmp_path):
    monkeypatch.setattr("haean.codex_runtime.shutil.which", lambda _: "/codex")
    def run(command, **kwargs):
        if command[1] == "login": return SimpleNamespace(returncode=0, stdout="ChatGPT", stderr="")
        Path(command[command.index("-o") + 1]).write_text('{"status":"ready"}')
        return SimpleNamespace(returncode=0, stdout='{"type":"item.completed","item":{"type":"command_execution"}}', stderr="")
    monkeypatch.setattr("haean.codex_runtime.subprocess.run", run)
    class Result(StrictModel): status: str
    with pytest.raises(RuntimeError, match="격리"):
        CodexProvider(trace_dir=tmp_path).call("blind", "solve", {}, Result)


def test_strict_output_schema():
    original = {"type":"object","properties":{"x":{"type":"string","default":"a"}}}
    strict = strict_schema(original)
    assert strict["additionalProperties"] is False and strict["required"] == ["x"]
    assert "default" not in strict["properties"]["x"]
    assert "additionalProperties" not in original


def result_set():
    return {"suite":"pilot-v1","split":"pilot","model":"gpt-6-astra","repeats":1,"max_revisions":1,
            "mode":"test","humanizer":"not_applied","frozen":{"rubric":"same"},"complete":True,
            "results":[{"case_id":"leet","repeat":0,"exam":"leet","subject":"추리논증","eligible":True,"quality":3,"fatal_count":0},
                       {"case_id":"psat","repeat":0,"exam":"psat7","subject":"자료해석","eligible":True,"quality":3,"fatal_count":0}]}


def test_evaluation_cannot_hide_fatal_regression_with_style():
    baseline = result_set(); candidate = copy.deepcopy(baseline)
    candidate["results"][0].update(quality=4, eligible=False, fatal_count=1)
    assert compare(baseline,candidate)["decision"] == "reject_regression"


def test_evaluation_separates_subjects_and_never_auto_promotes():
    baseline = result_set(); candidate = copy.deepcopy(baseline)
    candidate["results"][0]["quality"] = 4
    candidate["results"][1]["quality"] = 2.9
    assert compare(baseline,candidate)["decision"] == "reject_regression"
    candidate["results"][1]["quality"] = 3
    comparison = compare(baseline,candidate)
    assert comparison["decision"] == "candidate_signal" and comparison["auto_promoted"] is False


def test_evaluation_refuses_different_protocol_and_missing_trials():
    baseline = result_set(); candidate = copy.deepcopy(baseline)
    candidate["frozen"]["rubric"] = "changed"
    with pytest.raises(ValueError): compare(baseline,candidate)
    candidate = copy.deepcopy(baseline); candidate["results"].pop()
    with pytest.raises(ValueError): compare(baseline,candidate)
    candidate = copy.deepcopy(baseline); candidate["complete"] = False
    assert compare(baseline,candidate)["decision"] == "inconclusive"


def test_style_protects_dates_negation_quantifiers():
    assert protected_tokens("모든 사람은 10일 이내에 신청한다.") != protected_tokens("어떤 사람은 10일 이후에 신청한다.")
    assert protected_tokens("일부 대상은 허용되는 것이 아니다.") != protected_tokens("모두 허용되는 것이다.")
    assert protected_tokens("반드시 3개이다.") == protected_tokens("수량은 반드시 3개이다.")


def test_layout_manifest_does_not_claim_rendered(tmp_path, draft):
    save(tmp_path / "candidate.json",draft.model_dump())
    q=tmp_path/'q.hwp';s=tmp_path/'s.hwpx';q.write_bytes(b'fixture');s.write_bytes(b'fixture2')
    result=package(tmp_path,q,s)
    assert result['layout_verified'] is False and result['item_count']==1
    assert result['templates']['questions']['sha256']


def test_setup_links_are_idempotent_and_preserve_existing(tmp_path):
    spec=importlib.util.spec_from_file_location('launcher',Path('scripts/launch.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=tmp_path/'source';source.mkdir();target=tmp_path/'skills'/'haean'
    module.link_skill(source,target);module.link_skill(source,target)
    assert target.resolve()==source
    occupied=tmp_path/'occupied';occupied.mkdir()
    with pytest.raises(ValueError):module.link_skill(source,occupied)
