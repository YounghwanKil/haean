"""Synthetic archive/projection integrity; no private or exam source material."""
from copy import deepcopy
import hashlib
import json

import pytest

from haean.authoring_projection import (
    AuthoringProjectionError, _pointer, project_authoring_context,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def inventory(kind="path", count=12):
    return {
        f"/original/~source/{number:02d}.json": {
            kind: "/archived/" + "synthetic-only/" * 16 + f"{number:02d}.json",
            "sha256": sha(f"file-{number}"),
            **({"locator": f"audit file: {number:02d}.json", "usage": "development"}
               if kind == "file" else {}),
        }
        for number in range(count)
    }


def reference(number=1):
    return {
        "reference_id": f"ref-{number}", "application": "개념 적용만 참고",
        "match_scope": ["partial"], "gaps": ["동일 인지 과제 아님"],
        "student": {"stem": "합성 문항  ①\n", "passage": "규칙 A → B.\n\n조건을 유지한다.",
                    "choices": [{"number": n, "text": f"선지{n}"} for n in range(1, 6)],
                    "unknown_student_field": {"text": "나중에 추가한 필드도 그대로"}},
        "source": {
            "path": "/synthetic/source.pdf", "sha256": sha("source"),
            "original_path": "/original/source.pdf", "locator": "p1", "usage": "development",
            "evidence_files": inventory(),
            "official_answer": {"answer": 3, "verified": True, "human_verified": False,
                                "evidence": {"files": inventory("file"), "method": "원 답표"}},
            "classification_evidence": {"status": "provisional", "human_verified": False,
                                        "origin": "model", "actual_model": None},
            "corpus_evidence": {"notes": "전사 주의: 빈칸 모양 보존", "files": inventory()},
            "unknown_source": {"confidence": "unverified", "files": inventory()},
        },
    }


def context_for(*refs):
    return {
        "references": [reference(90)],
        "exam_assignment": [{"id": f"slot-{n}", "composition_resolution": {
            "selected_reference_input": {"packet_path": "references.json", "packet_sha256": sha("packet"),
                                         "references": [ref]},
            "topic_fact_input": {"sources": [{"id": "fact-1", "files": inventory()}]},
            "unknown_resolution": {"evidence_files": inventory()},
        }} for n, ref in enumerate(refs)],
        "unknown_context": {"evidence_files": inventory()},
    }


def save_and_project(tmp_path, context, **overrides):
    path = tmp_path / "context-full.json"
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    kwargs = {"archive_path": path, "archive_sha256": sha(path.read_bytes()), **overrides}
    return project_authoring_context(context, **kwargs)


def selected(context, slot=0, ref=0):
    return context["exam_assignment"][slot]["composition_resolution"]["selected_reference_input"]["references"][ref]


def resolve(value, pointer):
    for key in pointer.split("/")[1:]:
        key = key.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def test_only_two_exact_maps_change_with_complete_recovery_binding(tmp_path):
    original = context_for(reference(), reference(2))
    before = deepcopy(original)
    result, manifest = save_and_project(tmp_path, original)
    assert original == before
    assert manifest["counts"] == {"compacted_maps": 4, "preserved_maps": 0, "absent_maps": 0,
                                  "skipped_locations": 0, "archived_entries": 48}
    archive_bytes = (tmp_path / "context-full.json").read_bytes()
    assert manifest["archive"]["sha256"] == sha(archive_bytes)
    assert manifest["context_canonical_sha256"] == sha(canonical(original))
    assert manifest["projected_canonical_sha256"] == sha(canonical(result))
    assert manifest["character_counts"] == {
        "original": len(canonical(original)), "projected": len(canonical(result)),
        "saved": len(canonical(original)) - len(canonical(result)),
    }
    assert manifest["character_counts"]["saved"] > 0
    restored = deepcopy(result)
    for decision in manifest["decisions"]:
        descriptor = resolve(result, decision["json_pointer"])
        original_map = resolve(original, descriptor["json_pointer"])
        assert descriptor["original_canonical_sha256"] == sha(canonical(original_map))
        assert descriptor["archive_sha256"] == sha(archive_bytes)
        assert descriptor["archive_path"] == str((tmp_path / "context-full.json").resolve())
        assert descriptor["entry_count"] == len(original_map)
        if descriptor["entry_shape"] == "path_sha256":
            assert descriptor["entry_keys"] == list(original_map)
        else:
            assert descriptor["entry_annotations"] == {
                name: {"locator": entry["locator"], "usage": entry["usage"]}
                for name, entry in original_map.items()
            }
        parent, key = descriptor["json_pointer"].rsplit("/", 1)
        resolve(restored, parent)[key] = deepcopy(original_map)
    assert restored == original  # Includes students, IDs, all unknown state and semantic metadata.
    result["unknown_context"]["new"] = True
    selected(result)["student"]["passage"] += "changed copy"
    assert original == before


def test_shared_python_references_are_projected_per_json_location(tmp_path):
    ref = reference()
    original = context_for(ref, ref)
    original["exam_assignment"][0]["composition_resolution"]["selected_reference_input"]["references"].append(ref)
    result, manifest = save_and_project(tmp_path, original)
    assert manifest["counts"]["compacted_maps"] == 6
    pointers = [selected(result, slot, number)["source"]["evidence_files"]["json_pointer"]
                for slot, number in [(0, 0), (0, 1), (1, 0)]]
    assert len(set(pointers)) == 3
    assert selected(original)["source"]["evidence_files"] == inventory()


def test_json_pointer_escaping_resolves_original_entry_keys(tmp_path):
    original = context_for(reference())
    result, _ = save_and_project(tmp_path, original)
    descriptor = selected(result)["source"]["evidence_files"]
    name = descriptor["entry_keys"][0]
    entry_pointer = descriptor["json_pointer"] + _pointer((name,))
    assert "~1original~1~0source~1" in entry_pointer
    assert resolve(original, entry_pointer) == inventory()[name]
    assert _pointer(("a~/b", 0)) == "/a~0~1b/0"


@pytest.mark.parametrize("target", ["evidence_files", "answer_files"])
@pytest.mark.parametrize("mutation,reason", [
    ("empty", "empty_file_map"), ("list", "not_a_file_map"),
    ("extra", "unknown_entry_shape"), ("missing", "unknown_entry_shape"),
    ("bad_sha", "invalid_path_or_sha256"), ("blank_path", "invalid_path_or_sha256"),
    ("blank_key", "unknown_entry_shape"), ("nonobject", "unknown_entry_shape"),
])
def test_unexpected_inventory_kept_whole(tmp_path, target, mutation, reason):
    original = context_for(reference())
    source = selected(original)["source"]
    owner, key = (source, "evidence_files") if target == "evidence_files" else (source["official_answer"]["evidence"], "files")
    mapping = owner[key]
    first = next(iter(mapping))
    entry = mapping[first]
    if mutation == "empty": owner[key] = {}
    elif mutation == "list": owner[key] = list(mapping)
    elif mutation == "extra": entry["semantic_warning"] = "원문 판독 불확실"
    elif mutation == "missing": entry.pop("sha256")
    elif mutation == "bad_sha": entry["sha256"] = "not-a-sha"
    elif mutation == "blank_path": entry["path" if target == "evidence_files" else "file"] = " "
    elif mutation == "blank_key": mapping[" "] = mapping.pop(first)
    elif mutation == "nonobject": mapping[first] = "reference"
    before = deepcopy(owner[key])
    result, manifest = save_and_project(tmp_path, original)
    out = selected(result)["source"]
    assert (out["evidence_files"] if target == "evidence_files" else out["official_answer"]["evidence"]["files"]) == before
    assert any(d["status"] == "preserved" and d["reason"] == reason for d in manifest["decisions"])
    assert manifest["counts"]["compacted_maps"] == 1


@pytest.mark.parametrize("field,value", [("locator", None), ("usage", ["development"])])
def test_official_annotations_must_be_strings(tmp_path, field, value):
    original = context_for(reference())
    files = selected(original)["source"]["official_answer"]["evidence"]["files"]
    files[next(iter(files))][field] = value
    result, manifest = save_and_project(tmp_path, original)
    assert selected(result)["source"]["official_answer"]["evidence"]["files"] == files
    assert any(d["reason"] == "invalid_annotation_type" for d in manifest["decisions"])


def test_unknown_annotation_text_is_not_rewritten_or_promoted(tmp_path):
    original = context_for(reference())
    files = selected(original)["source"]["official_answer"]["evidence"]["files"]
    files[next(iter(files))].update(locator="주의: 해석 보류\n", usage="unknown scope")
    result, _ = save_and_project(tmp_path, original)
    annotations = selected(result)["source"]["official_answer"]["evidence"]["files"]["entry_annotations"]
    assert annotations[next(iter(files))] == {"locator": "주의: 해석 보류\n", "usage": "unknown scope"}
    assert selected(result)["source"]["classification_evidence"]["human_verified"] is False


def test_small_known_inventory_is_preserved_without_size_growth(tmp_path):
    original = context_for(reference())
    selected(original)["source"]["evidence_files"] = {"a": {"path": "a", "sha256": sha("a")}}
    result, manifest = save_and_project(tmp_path, original)
    assert selected(result)["source"]["evidence_files"] == selected(original)["source"]["evidence_files"]
    decision = next(d for d in manifest["decisions"] if d["reason"] == "descriptor_not_smaller")
    assert decision["projected_characters"] == decision["original_characters"]
    assert decision["descriptor_characters"] >= decision["projected_characters"]


@pytest.mark.parametrize("assignment", [None, {}, [None], [{"composition_resolution": []}],
                                       [{"composition_resolution": {"selected_reference_input": {"references": {}}}}]])
def test_unexpected_parent_shapes_are_preserved(tmp_path, assignment):
    original = {"exam_assignment": assignment, "meaningful": "unchanged"}
    result, manifest = save_and_project(tmp_path, original)
    assert result == original
    assert manifest["counts"]["skipped_locations"] == 1


def test_missing_or_malformed_answer_parent_is_preserved(tmp_path):
    original = context_for(reference(), reference(2))
    del selected(original, 0)["source"]["official_answer"]
    selected(original, 1)["source"]["official_answer"] = ["unrecognized"]
    result, manifest = save_and_project(tmp_path, original)
    assert "official_answer" not in selected(result, 0)["source"]
    assert selected(result, 1)["source"]["official_answer"] == ["unrecognized"]
    assert manifest["counts"]["absent_maps"] == 1
    assert manifest["counts"]["skipped_locations"] == 1


@pytest.mark.parametrize("fault", ["wrong_sha", "invalid_sha", "missing", "different_content", "duplicate_key", "nonfinite"])
def test_archive_binding_failures_reject_projection(tmp_path, fault):
    original = context_for(reference())
    path = tmp_path / "full.json"
    path.write_text(json.dumps(original))
    digest = sha(path.read_bytes())
    if fault == "wrong_sha": digest = "0" * 64
    elif fault == "invalid_sha": digest = "invalid"
    elif fault == "missing": path.unlink()
    elif fault == "different_content":
        path.write_text(json.dumps({**original, "extra": "not present"}))
        digest = sha(path.read_bytes())
    elif fault == "duplicate_key":
        path.write_text('{"exam_assignment":[],"exam_assignment":[]}')
        digest = sha(path.read_bytes())
    elif fault == "nonfinite":
        path.write_text('{"value":NaN}')
        digest = sha(path.read_bytes())
    with pytest.raises(AuthoringProjectionError):
        project_authoring_context(original, archive_path=path, archive_sha256=digest)


def test_archive_does_not_treat_boolean_as_integer(tmp_path):
    path = tmp_path / "full.json"
    path.write_text('{"flag":1}')
    with pytest.raises(AuthoringProjectionError, match="content does not match"):
        project_authoring_context({"flag": True}, archive_path=path, archive_sha256=sha(path.read_bytes()))


@pytest.mark.parametrize("context", [{1: "not a JSON key"}, {"tuple": (1, 2)}, {"number": float("nan")}])
def test_non_json_context_is_not_normalized(tmp_path, context):
    path = tmp_path / "full.json"
    path.write_text("{}")
    with pytest.raises(AuthoringProjectionError):
        project_authoring_context(context, archive_path=path, archive_sha256=sha(path.read_bytes()))
