"""Archived evaluation separates current code drift from saved-evidence damage."""
from pathlib import Path

import pytest

from haean import composition_adapter as adapter, execution_provenance as provenance
from haean.composition import load_design
from haean.pipeline import run_pipeline, save
from test_composition_adapter import prepared, read
from test_composition_psat7_flow import composition_inputs, SyntheticProvider
from test_execution_provenance import capture as capture_manifest


@pytest.fixture
def bound_archive(composition_inputs, tmp_path, draft):
    inputs = composition_inputs
    packet = adapter.bind(inputs["plan"], inputs["design"], inputs["mapping"], tmp_path / "binding")
    plan = read(inputs["plan"])
    slots = plan["slots"][:2]
    run = prepared(tmp_path / "bundle", slots, subject=plan["subject"], exam=plan["exam"])
    expected = adapter.attach_bundle(run, plan_path=inputs["plan"], packet_path=packet, slots=slots)
    candidate = run_pipeline(run, SyntheticProvider(draft), max_revisions=0,
                             **adapter.pipeline_callbacks(run, expected))
    return run, expected, candidate, inputs


def test_changed_current_runtime_is_strictly_rejected_but_archive_is_readable(bound_archive, monkeypatch):
    run, expected, candidate, inputs = bound_archive
    design = read(inputs["design"])
    snapshot = Path(design["execution_snapshot"]["path"])
    original = provenance.runtime_sources()
    changed = {**original, "evaluation.py": original["evaluation.py"] + b"\n# changed evaluator\n",
               "new_evaluation_helper.py": b"# newly installed helper\n"}
    monkeypatch.setattr(provenance, "runtime_sources", lambda: changed)

    strict = provenance.verify(snapshot)
    assert not strict["valid"]
    assert "runtime_inventory_changed" in strict["issues"]
    assert "runtime:evaluation.py:source_changed" in strict["issues"]
    for check in (lambda: load_design(inputs["design"]),
                  lambda: adapter.load_packet(expected["packet"]["path"], inputs["plan"]),
                  lambda: adapter.validate_bundle(run, expected, candidate),
                  lambda: adapter.pipeline_callbacks(run, expected)):
        with pytest.raises(ValueError, match="실행 근거"):
            check()
    assert adapter.assembly_errors(run, expected, candidate, read(run / "status.json"))

    archived = provenance.verify(snapshot, expected_sha256=design["execution_snapshot"]["sha256"],
                                 verify_runtime=False)
    assert archived["valid"] and archived["issues"] == []
    assert archived["runtime_verification"] == "archived_snapshot_only"
    assert archived["current_runtime_verified"] is False
    assert "not verified" in archived["assurance"]
    # Returned source artifacts retain their original content; no retrospective seal is created.
    assert load_design(inputs["design"], verify_runtime=False) == design
    assert adapter.load_packet(expected["packet"]["path"], inputs["plan"], verify_runtime=False) == read(expected["packet"]["path"])
    assert adapter.validate_bundle(run, expected, candidate, verify_runtime=False) == []


@pytest.mark.parametrize("snapshot_key", ["execution_snapshot", "output_snapshot"])
def test_archive_still_rejects_changed_saved_runtime_copy(bound_archive, snapshot_key):
    run, expected, candidate, inputs = bound_archive
    design = read(inputs["design"])
    snapshot = Path(design[snapshot_key]["path"])
    manifest = read(snapshot)
    name = next(iter(manifest["runtime"]))
    copy = snapshot.parent / manifest["runtime"][name]["snapshot"]
    copy.write_bytes(copy.read_bytes() + b"\n# damaged archived code\n")
    for verify_runtime in (True, False):
        report = provenance.verify(snapshot, verify_runtime=verify_runtime)
        assert not report["valid"]
        assert f"runtime:{name}:snapshot_hash_mismatch" in report["issues"]
        with pytest.raises(ValueError, match="근거 불일치"):
            adapter.validate_bundle(run, expected, candidate, verify_runtime=verify_runtime)


def test_archive_still_rejects_changed_original_plan(bound_archive):
    run, expected, candidate, inputs = bound_archive
    plan = read(inputs["plan"])
    plan["slots"][0]["topic"] += " 보존 이후 변경"
    save(inputs["plan"], plan)
    for verify_runtime in (True, False):
        with pytest.raises(ValueError, match="해시 불일치"):
            adapter.load_packet(expected["packet"]["path"], inputs["plan"], verify_runtime=verify_runtime)
        with pytest.raises(ValueError, match="해시 불일치"):
            adapter.validate_bundle(run, expected, candidate, verify_runtime=verify_runtime)


@pytest.mark.parametrize("changed", ["source", "input_copy", "instructions", "schemas", "manifest"])
def test_archive_mode_retains_other_source_and_snapshot_checks(tmp_path, monkeypatch, changed):
    manifest_path, source, runtime = capture_manifest(tmp_path, monkeypatch)
    manifest = read(manifest_path)
    expected = provenance.digest(manifest_path.read_bytes())
    runtime["pipeline.py"] = b"# current code may change for reevaluation"
    if changed == "source":
        source.write_text("changed source")
    elif changed == "manifest":
        manifest["parameters"]["max_revisions"] += 1
        # Even a replaced local seal cannot evade the caller-held original digest.
        data = provenance.encoded(manifest)
        manifest_path.write_bytes(data)
        (manifest_path.parent / "manifest.sha256").write_text(provenance.digest(data) + "\n")
    else:
        record = manifest["inputs"]["context"] if changed == "input_copy" else manifest[changed]
        path = manifest_path.parent / record["snapshot"]
        path.write_bytes(path.read_bytes() + b"\nchanged snapshot")
    report = provenance.verify(manifest_path, expected_sha256=expected, verify_runtime=False)
    assert not report["valid"] and report["issues"]
    assert report["current_runtime_verified"] is False
    assert not any(issue.startswith("runtime:") or issue == "runtime_inventory_changed" for issue in report["issues"])


@pytest.mark.parametrize("flag", [None, 0, 1, "false"])
def test_non_boolean_archive_flag_cannot_silently_relax_validation(tmp_path, monkeypatch, flag):
    manifest, _, _ = capture_manifest(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="verify_runtime"):
        provenance.verify(manifest, verify_runtime=flag)
