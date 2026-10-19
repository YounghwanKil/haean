"""Composition proposals preserve named sources and reject stale inputs."""
import json
from pathlib import Path

import pytest

from haean.composition import design, load_design, load_profile
from haean.composition.profiles import read_json, sha
from test_composition_ds import situation_profile


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def profile(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    values = {"rules_config": {}, **situation_profile()}
    records = []
    for role, data in values.items():
        source = write(tmp_path / (role + ".json"), data)
        records.append({"role": role, "path": source.name, "sha256": sha(source),
                        "usage": "development", "exam_grade": 5, "locator": "synthetic:whole-file"})
    return write(tmp_path / "profile.json", {
        "schema_version": 1, "track": "psat_situation", "exam": "psat5", "subject": "상황판단",
        "exam_grade": 5, "usage": "development", "origin": {"source": "synthetic fixture", "revision": "1"},
        "files": records,
    })


def test_complete_proposal_preserves_profile_and_requires_current_inputs(tmp_path):
    source = profile(tmp_path / "sources")
    before = source.read_bytes()
    result = design(source, tmp_path / "run", seed=7)
    packet = load_design(result["design"])
    assert len(packet["format_design"]["slots"]) == len(packet["content_spec"]["슬롯"]) == 40
    assert source.read_bytes() == before
    assert not packet["human_approved"] and not packet["model_generation_executed"]
    target = tmp_path / "sources" / "content_config.json"
    target.write_text(target.read_text() + "\n")
    with pytest.raises(ValueError, match="해시 불일치"):
        load_design(result["design"])


@pytest.mark.parametrize("change", ["holdout", "wrong_grade", "wrong_subject", "missing", "duplicate", "no_locator"])
def test_reject_unusable_profile_before_creating_run(tmp_path, change):
    source = profile(tmp_path / "sources")
    value = read_json(source)
    if change == "holdout": value["files"][0]["usage"] = "holdout"
    if change == "wrong_grade": value["exam_grade"] = 7
    if change == "wrong_subject": value["subject"] = "자료해석"
    if change == "missing": value["files"] = value["files"][1:]
    if change == "duplicate": value["files"].append(value["files"][0])
    if change == "no_locator": value["files"][0]["locator"] = ""
    write(source, value)
    with pytest.raises(ValueError):
        design(source, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_mutated_proposal_and_unsupported_size_cannot_bind(tmp_path):
    source = profile(tmp_path / "sources")
    with pytest.raises(ValueError, match="40문항"):
        design(source, tmp_path / "short", options={"size": 25})
    result = design(source, tmp_path / "run")
    path = Path(result["design"])
    packet = read_json(path)
    packet["content_spec"]["슬롯"].pop()
    write(path, packet)
    with pytest.raises(ValueError, match="해시 불일치"):
        load_design(path)
    path.with_suffix(".sha256").write_text(sha(path))
    with pytest.raises(ValueError, match="원문이 생성 당시와"):
        load_design(path)
    with pytest.raises(FileExistsError):
        design(source, tmp_path / "run")


def test_snapshot_code_change_and_seed_change_invalidates_design(tmp_path, monkeypatch):
    from haean import execution_provenance
    source = profile(tmp_path / "sources")
    result = design(source, tmp_path / "run")
    path = Path(result["design"])
    packet = read_json(path)
    packet["seed"] += 1
    write(path, packet)
    path.with_suffix(".sha256").write_text(sha(path))
    with pytest.raises(ValueError, match="매개변수"):
        load_design(path)
    packet["seed"] -= 1
    write(path, packet)
    path.with_suffix(".sha256").write_text(sha(path))
    previous = execution_provenance.runtime_sources()
    monkeypatch.setattr(execution_provenance, "runtime_sources", lambda: {**previous, "changed.py": b"new code"})
    with pytest.raises(ValueError, match="실행 근거"):
        load_design(path)


def test_ambiguous_json_profile_is_rejected(tmp_path):
    source = profile(tmp_path / "sources")
    source.write_text(source.read_text().replace('"usage": "development"', '"usage": "development", "usage": "holdout"', 1))
    with pytest.raises(ValueError, match="중복 JSON"):
        load_profile(source)


def test_ledger_replaced_before_capture_is_not_misattributed(tmp_path, monkeypatch):
    from haean import execution_provenance
    source = profile(tmp_path / "sources")
    ledger = write(tmp_path / "ledger.json", {"entries": [{"topic": "before"}]})
    original = execution_provenance.capture

    def switched(*args, **kwargs):
        write(ledger, {"entries": [{"topic": "after"}]})
        return original(*args, **kwargs)

    monkeypatch.setattr(execution_provenance, "capture", switched)
    with pytest.raises(ValueError, match="소재 대장이 설계 시작 전에"):
        design(source, tmp_path / "run", ledger_path=ledger)
    assert read_json(tmp_path / "run" / "failure.json")["state"] == "failed"
    assert not (tmp_path / "run" / "design.json").exists()


def test_generated_numeric_mapping_keys_survive_json_roundtrip(tmp_path, monkeypatch):
    from haean.composition.profiles import Profile
    original = Profile.engine

    def engine(profile):
        instance = original(profile)
        content = instance.content

        def with_counts(*args, **kwargs):
            return {**content(*args, **kwargs), "합성_분포": {1: "one", 10: "ten", 2: "two"}}

        instance.content = with_counts
        return instance

    monkeypatch.setattr(Profile, "engine", engine)
    result = design(profile(tmp_path / "sources"), tmp_path / "run")
    assert load_design(result["design"])["content_spec"]["합성_분포"] == {"1": "one", "2": "two", "10": "ten"}
