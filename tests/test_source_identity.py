"""Synthetic provenance fixtures only; no original exam material."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from haean.source_identity import locate, payload_digest, verify


@pytest.fixture
def packet(tmp_path):
    item = {"id": "synthetic-091", "number": 4, "passage": "합성 지문",
            "choices": ["가", "나"], "judgments": [{"correct": True}],
            "explanation": "합성 해설"}
    other = {**item, "id": "synthetic-007"}
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"items": [item, other]}, ensure_ascii=False))
    profile = {"id": item["id"], "source": str(source), "locator": "$.items[0]",
               "source_file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "payload_sha256": payload_digest(item),
               "student_original": {k: item[k] for k in ("id", "number", "passage", "choices")},
               "original_judgments": item["judgments"], "original_explanation": item["explanation"]}
    return tmp_path / "profiles.json", profile, item, other


def run(packet, profiles=None, out=None):
    path, profile, *_ = packet
    path.write_text(json.dumps([profile] if profiles is None else profiles, ensure_ascii=False))
    return verify(path, out)


def errors(report):
    return [e for row in report["profiles"] for e in row["errors"]]


def test_id_is_not_exam_number(packet):
    report = run(packet)
    assert report["valid"]
    assert report["profiles"][0]["payload_encoding_matches"] == ["raw_sorted_compact"]
    assert report["profiles"][0]["full_student_text_verified"] is False


def test_matching_hash_of_other_item_cannot_certify_identity(packet):
    _, profile, _, other = packet
    profile["locator"] = "/items/1"
    profile["payload_sha256"] = payload_digest(other)
    profile.pop("student_original")
    report = run(packet)
    assert not report["valid"]
    assert "source_item_id_mismatch" in errors(report)
    assert "raw_payload_hash_mismatch" not in errors(report)


@pytest.mark.parametrize("field", ["student_original", "original_judgments", "original_explanation"])
def test_embedded_content_tampering(packet, field):
    profile = packet[1]
    profile[field] = {"passage": "변경"} if field == "student_original" else ([] if field == "original_judgments" else "변경")
    assert not run(packet)["valid"]


@pytest.mark.parametrize("value", [True, "4", 4.0, None])
def test_embedded_comparison_preserves_types(packet, value):
    packet[1]["student_original"]["number"] = value
    assert "student_field_mismatch:number" in errors(run(packet))


@pytest.mark.parametrize("locator", ["/items/-1", "/items/01", "/items/9", "/items/~2", "$.items[x]", None, 1, "__import__('os')", "/items/0/id/x"])
def test_bad_locators_report_failure(packet, locator):
    packet[1]["locator"] = locator
    assert not run(packet)["valid"]


def test_json_pointer_escaping_and_root():
    doc = {"a/b": {"~key": ["ok"]}}
    assert locate(doc, "/a~1b/~0key/0") == "ok"
    assert locate(doc, "") is doc


def test_duplicate_id_and_nonobject(packet):
    report = run(packet, [packet[1], copy.deepcopy(packet[1]), None, "7"])
    assert not report["valid"]
    assert "duplicate_id" in errors(report)
    assert "profile_must_be_object" in errors(report)


@pytest.mark.parametrize("field", ["id", "source", "source_file_sha256", "locator", "payload_sha256"])
@pytest.mark.parametrize("mode", ["missing", "null", "list"])
def test_required_fields(packet, field, mode):
    if mode == "missing":
        del packet[1][field]
    else:
        packet[1][field] = None if mode == "null" else []
    assert not run(packet)["valid"]


def test_missing_source_and_wrong_file_hash(packet):
    packet[1]["source_file_sha256"] = "0" * 64
    assert "source_file_hash_mismatch" in errors(run(packet))
    Path(packet[1]["source"]).unlink()
    assert any(e.startswith("unresolved_source:") for e in errors(run(packet)))


def test_serialization_compatibility_and_explicit_mismatch(packet):
    profile, item = packet[1:3]
    profile["payload_sha256"] = payload_digest(item, "raw_sorted_default")
    assert run(packet)["profiles"][0]["payload_encoding_matches"] == ["raw_sorted_default"]
    profile["payload_encoding"] = "raw_sorted_compact"
    assert "raw_payload_hash_mismatch" in errors(run(packet))
    profile["payload_encoding"] = "raw_sorted_default"
    assert run(packet)["valid"]
    profile["payload_encoding"] = "catalog_normalized"
    assert "unsupported_payload_encoding" in errors(run(packet))


def test_normalized_digest_is_not_raw_digest(packet):
    packet[1]["payload_sha256"] = payload_digest({k: v for k, v in packet[2].items() if k != "number"})
    assert "raw_payload_hash_mismatch" in errors(run(packet))


def test_partial_and_empty_embedded_scope(packet):
    profile = packet[1]
    for key in ("student_original", "original_explanation", "original_judgments"):
        profile.pop(key)
    report = run(packet)
    assert report["valid"]
    assert len(report["profiles"][0]["missing_embedded_evidence"]) == 3
    profile["student_original"] = {}
    assert "student_original:empty" in run(packet)["profiles"][0]["missing_embedded_evidence"]
    assert not run(packet, [])["valid"]


@pytest.mark.parametrize("raw", ['null', '{}', '[', '[{"id":"x","id":"y"}]', '[NaN]'])
def test_invalid_collection_is_reported(packet, raw):
    packet[0].write_text(raw)
    report = verify(packet[0])
    assert not report["valid"]
    assert report["errors"]


@pytest.mark.parametrize("target", ["input", "source", "existing", "symlink", "hardlink", "missing_source"])
def test_output_collision_preserves_files(packet, target):
    path, profile, *_ = packet
    run(packet)
    source = Path(profile["source"])
    output = path.parent / "report.json"
    if target == "input":
        output = path
    elif target == "source":
        output = source
    elif target == "existing":
        output.write_text("existing report")
    elif target == "symlink":
        output.symlink_to(source)
    elif target == "hardlink":
        os.link(source, output)
    elif target == "missing_source":
        source.unlink()
        output = source
    before = {p: p.read_bytes() for p in (path, source, output) if p.exists()}
    result = verify(path, output)
    assert not result["valid"]
    assert result["errors"][-1]["code"] == "report_output_refused"
    for p, content in before.items():
        assert p.read_bytes() == content
    if target == "missing_source":
        assert not source.exists()


def test_cli_registration_report_and_exit(packet):
    run(packet)
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    command = [sys.executable, "-m", "haean.cli", "verify-source-profiles", str(packet[0])]
    output = packet[0].parent / "report.json"
    completed = subprocess.run([*command, "--out", str(output)], env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == json.loads(output.read_text())
    completed = subprocess.run([*command, "--out", str(packet[0])], env=env, capture_output=True, text=True)
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["errors"][-1]["code"] == "report_output_refused"
    packet[1]["id"] = "synthetic-other"
    run(packet)
    completed = subprocess.run(command, env=env, capture_output=True, text=True)
    assert completed.returncode == 1
    assert "source_item_id_mismatch" in errors(json.loads(completed.stdout))


@pytest.mark.parametrize("key,value", [("student_original", None), ("original_judgments", None),
                                       ("original_explanation", None), ("payload_encoding", None),
                                       ("payload_encoding", []), ("payload_sha256", "12")])
def test_optional_schema_and_hash_format_fail_closed(packet, key, value):
    packet[1][key] = value
    assert not run(packet)["valid"]


@pytest.mark.parametrize("raw", ['{"items":[null]}', '{"items":[{"id":null}]}',
                                '{"items":[{"id":"a","id":"b"}]}', '{"items":[NaN]}'])
def test_invalid_raw_source_is_reported(packet, raw):
    source = Path(packet[1]["source"])
    source.write_text(raw)
    packet[1]["source_file_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    assert not run(packet)["valid"]
