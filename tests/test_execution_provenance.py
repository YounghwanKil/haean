from pathlib import Path
import json

import pytest

from haean import execution_provenance as provenance


def capture(tmp_path, monkeypatch):
    source = tmp_path / "context.json"
    source.write_text('{"topic":"합성 소재"}')
    runtime = {"pipeline.py": b"# version one", "tracks/psat_data/rules/design.md": b"design v1"}
    monkeypatch.setattr(provenance, "runtime_sources", lambda: runtime.copy())
    manifest = provenance.capture(tmp_path / "evidence", inputs={"context": source},
                                  instructions={"design": "합성 설계"}, schemas={"design": {"type": "object"}},
                                  parameters={"requested_model": "test-double", "max_revisions": 1})
    return manifest, source, runtime


def test_snapshot_preserves_inputs_and_cannot_be_overwritten(tmp_path, monkeypatch):
    manifest, source, runtime = capture(tmp_path, monkeypatch)
    assert provenance.verify(manifest)["valid"]
    saved = manifest.read_bytes()
    with pytest.raises(FileExistsError):
        provenance.capture(manifest.parent, inputs={"context": source}, instructions={}, schemas={}, parameters={})
    assert manifest.read_bytes() == saved
    source.write_text("changed")
    assert "input:context:source_changed" in provenance.verify(manifest)["issues"]
    assert (manifest.parent / "inputs/context").read_text() == '{"topic":"합성 소재"}'


def test_nested_track_rule_change_and_code_addition_invalidate_snapshot(tmp_path, monkeypatch):
    manifest, source, runtime = capture(tmp_path, monkeypatch)
    runtime["tracks/psat_data/rules/design.md"] = b"design v2"
    assert "runtime:tracks/psat_data/rules/design.md:source_changed" in provenance.verify(manifest)["issues"]
    runtime["new_module.py"] = b"# new execution code"
    assert "runtime_inventory_changed" in provenance.verify(manifest)["issues"]


def test_missing_source_and_modified_snapshot_do_not_verify(tmp_path, monkeypatch):
    manifest, source, runtime = capture(tmp_path, monkeypatch)
    source.unlink()
    (manifest.parent / "instructions.json").write_text("{}")
    result = provenance.verify(manifest)
    assert not result["valid"]
    assert "input:context:source_missing_or_unreadable" in result["issues"]
    assert "instructions:snapshot_hash_mismatch" in result["issues"]


def test_manifest_binding_and_invalid_input_name(tmp_path, monkeypatch):
    manifest, source, runtime = capture(tmp_path, monkeypatch)
    assert not provenance.verify(manifest, expected_sha256="0" * 64)["valid"]
    value = json.loads(manifest.read_text())
    value["parameters"]["max_revisions"] = 0
    manifest.write_text(json.dumps(value))
    assert provenance.verify(manifest)["issues"] == ["manifest_hash_mismatch"]
    with pytest.raises(ValueError):
        provenance.capture(tmp_path / "unsafe", inputs={"../outside": source}, instructions={}, schemas={}, parameters={})
    assert not (tmp_path / "unsafe").exists()


def test_runtime_inventory_contains_nested_packaged_rules():
    sources = provenance.runtime_sources()
    assert "tracks/psat_data/rules/design.md" in sources
    assert "pipeline.py" in sources
    assert not any("__pycache__" in p for p in sources)


@pytest.mark.parametrize("field,value", [
    ("runtime", []), ("inputs", []), ("parameters", []),
    ("runtime", {"pipeline.py": None}), ("inputs", {"context": {"sha256": []}}),
    ("instructions", []), ("schemas", None), ("created_at", None),
    ("quality_improvement_verified", True), ("frozen_evaluator_replaced", 0),
])
def test_sealed_malformed_manifest_fails_closed(tmp_path, monkeypatch, field, value):
    manifest, _, _ = capture(tmp_path, monkeypatch)
    malformed = json.loads(manifest.read_text())
    malformed[field] = value
    raw = provenance.encoded(malformed)
    manifest.write_bytes(raw)
    (manifest.parent / "manifest.sha256").write_text(provenance.digest(raw) + "\n")
    assert provenance.verify(manifest) == {"valid": False, "issues": ["invalid_or_missing_manifest"]}


def test_nonfinite_parameters_rejected_before_reserving_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, "runtime_sources", lambda: {"test.py": b"test"})
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError):
        provenance.capture(destination, inputs={}, instructions={}, schemas={}, parameters={"timeout": float("nan")})
    assert not destination.exists()


def test_nonfinite_json_and_empty_expected_digest_fail_closed(tmp_path, monkeypatch):
    manifest, _, _ = capture(tmp_path, monkeypatch)
    assert provenance.verify(manifest, expected_sha256="")["issues"] == ["manifest_hash_mismatch"]
    malformed = json.loads(manifest.read_text())
    malformed["parameters"]["timeout"] = float("nan")
    raw = json.dumps(malformed).encode()
    manifest.write_bytes(raw)
    (manifest.parent / "manifest.sha256").write_text(provenance.digest(raw) + "\n")
    assert provenance.verify(manifest) == {"valid": False, "issues": ["invalid_or_missing_manifest"]}


def test_capture_failure_preserves_snapshot_without_blessing_changed_input(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text("before")
    def change_during_capture():
        source.write_text("after")
        return {"test.py": b"test"}
    monkeypatch.setattr(provenance, "runtime_sources", change_during_capture)
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="source_changed"):
        provenance.capture(destination, inputs={"source": source}, instructions={}, schemas={}, parameters={})
    assert (destination / "inputs/source").read_text() == "before"
    assert source.read_text() == "after"
    assert (destination / "manifest.json").exists()
    assert not provenance.verify(destination / "manifest.json")["valid"]
