"""Synthetic delivery/provenance tests; no exam or private source text."""
from copy import deepcopy
import hashlib
import json

import pytest

from haean.authoring_sources import AuthoringSourceError, supplied_source_ids


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def material(tmp_path):
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"%PDF-synthetic-reference")
    snapshot = tmp_path / "snapshot.txt"
    snapshot.write_text("합성 자료의 짧은 기록")
    reference = {
        "reference_id": "selected-1",
        "source": {"path": str(pdf), "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
        "student": {"stem": "다음 조건에서 참인 것은?", "passage": "합성 조건을 따른다.",
                    "conditions": [], "statements": [], "tables": [],
                    "choices": [{"number": n, "text": f"합성 선지 {n}"} for n in range(1, 6)]},
    }
    fact = {"id": "fact-1", "facts": "합성 관찰 조건에서는 표면의 색이 달라진다.",
            "url": "https://example.test/source", "snapshot_path": str(snapshot),
            "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()}
    ref_path, fact_path = tmp_path / "references.json", tmp_path / "facts.json"
    ref_sha = save(ref_path, {"references": [reference]})
    fact_sha = save(fact_path, {"sources": [fact]})
    resolution = {
        "selected_reference_input": {"packet_path": str(ref_path), "packet_sha256": ref_sha,
                                     "references": [reference]},
        "topic_fact_input": {"packet_path": str(fact_path), "packet_sha256": fact_sha,
                             "sources": [fact]},
    }
    context = {"references": [{"id": "retrieved-1", "text": "기존 제공 자료"}],
               "exam_assignment": [{"composition_resolution": resolution}]}
    return context, resolution, reference, fact


def rewrite_packet(block, key):
    from pathlib import Path
    block["packet_sha256"] = save(Path(block["packet_path"]), {key: block[key]})


def test_supplied_full_references_and_facts_extend_legacy_allowlist(material):
    context = material[0]
    before = deepcopy(context)
    assert supplied_source_ids(context) == {"retrieved-1", "selected-1", "fact-1"}
    assert context == before


def test_manual_plan_and_metadata_do_not_extend_allowlist():
    context = {"references": [{"id": "legacy"}], "exam_assignment": [{
        "id": "slot-1", "authoring_notes": {"id": "invented", "text": "자료 있음"},
        "source_plan": {"reference_id": "stat-id"},
        "composition_resolution": {"evidence": [{"id": "evidence-id"}],
                                   "selected_reference_ids": ["unread-id"]},
    }]}
    assert supplied_source_ids(context) == {"legacy"}
    assert supplied_source_ids({"references": [{"id": "legacy"}]}) == {"legacy"}


def test_empty_optional_blocks_need_no_files(material):
    context, resolution, *_ = material
    resolution["selected_reference_input"] = {"references": []}
    resolution["topic_fact_input"] = {"sources": []}
    assert supplied_source_ids(context) == {"retrieved-1"}


@pytest.mark.parametrize("assignment", [None, [], "legacy note", {"composition_resolution": None}])
def test_unrelated_legacy_assignment_metadata_remains_compatible(assignment):
    context = {"references": [{"id": "legacy"}], "exam_assignment": [assignment]}
    assert supplied_source_ids(context) == {"legacy"}


@pytest.mark.parametrize("key", ["packet_path", "packet_sha256"])
@pytest.mark.parametrize("block_key", ["selected_reference_input", "topic_fact_input"])
def test_missing_packet_binding_is_rejected(material, key, block_key):
    context, resolution, *_ = material
    del resolution[block_key][key]
    with pytest.raises(AuthoringSourceError):
        supplied_source_ids(context)


@pytest.mark.parametrize("target", ["packet", "pdf", "snapshot"])
def test_modified_file_bytes_are_rejected(material, target):
    from pathlib import Path
    context, resolution, reference, fact = material
    path = {"packet": resolution["topic_fact_input"]["packet_path"],
            "pdf": reference["source"]["path"], "snapshot": fact["snapshot_path"]}[target]
    Path(path).write_bytes(b"changed after delivery")
    with pytest.raises(AuthoringSourceError, match="SHA-256 mismatch"):
        supplied_source_ids(context)


@pytest.mark.parametrize("kind", ["reference", "fact"])
def test_delivered_content_must_match_packet(material, kind):
    context, _, reference, fact = material
    if kind == "reference":
        reference["student"]["passage"] = "본문 교체"
    else:
        fact["facts"] = "요약 교체"
    with pytest.raises(AuthoringSourceError, match="content mismatch"):
        supplied_source_ids(context)


@pytest.mark.parametrize("mutation", ["missing_student", "empty_passage", "missing_choice",
                                      "id_only", "empty_facts", "invalid_url", "missing_snapshot"])
def test_metadata_and_partial_content_are_not_sources(material, mutation):
    context, resolution, reference, fact = material
    if mutation == "missing_student":
        del reference["student"]
    elif mutation == "empty_passage":
        reference["student"]["passage"] = " "
    elif mutation == "missing_choice":
        reference["student"]["choices"].pop()
    elif mutation == "id_only":
        reference.clear()
        reference["reference_id"] = "selected-1"
    elif mutation == "empty_facts":
        fact["facts"] = " "
    elif mutation == "invalid_url":
        fact["url"] = "javascript:alert(1)"
    else:
        del fact["snapshot_path"]
    rewrite_packet(resolution["selected_reference_input"], "references")
    rewrite_packet(resolution["topic_fact_input"], "sources")
    with pytest.raises(AuthoringSourceError):
        supplied_source_ids(context)


@pytest.mark.parametrize("body_field", ["conditions", "tables", "additional_passage", "shared_passage"])
def test_nonprose_student_body_is_supported(material, body_field):
    context, resolution, reference, _ = material
    student = reference["student"]
    student["passage"] = ""
    student[body_field] = (["합성 조건"] if body_field == "conditions" else
                           [{"rows": [[1, 2]]}] if body_field == "tables" else "합성 공통 본문")
    rewrite_packet(resolution["selected_reference_input"], "references")
    assert "selected-1" in supplied_source_ids(context)


def test_duplicate_identical_material_is_allowed(material):
    context, resolution, *_ = material
    context["exam_assignment"].append({"composition_resolution": deepcopy(resolution)})
    assert supplied_source_ids(context) == {"retrieved-1", "selected-1", "fact-1"}


def test_duplicate_id_with_changed_content_in_packet_is_rejected(material):
    context, resolution, _, fact = material
    duplicate = deepcopy(fact)
    duplicate["facts"] = "같은 ID의 다른 본문"
    resolution["topic_fact_input"]["sources"].append(duplicate)
    rewrite_packet(resolution["topic_fact_input"], "sources")
    with pytest.raises(AuthoringSourceError, match="content mismatch"):
        supplied_source_ids(context)


def test_duplicate_id_across_different_packets_is_rejected(material, tmp_path):
    context, resolution, *_ = material
    other = deepcopy(resolution)
    other["topic_fact_input"]["sources"][0]["facts"] = "다른 패킷에서 교체"
    other["topic_fact_input"]["packet_path"] = str(tmp_path / "other.json")
    rewrite_packet(other["topic_fact_input"], "sources")
    context["exam_assignment"].append({"composition_resolution": other})
    with pytest.raises(AuthoringSourceError, match="conflicting supplied"):
        supplied_source_ids(context)


def test_retrieved_and_selected_student_must_match(material):
    context, _, reference, _ = material
    student = reference["student"]
    record = {"id": reference["reference_id"], "text": json.dumps({
        "발문": student["stem"], "지문": student["passage"], "선지": student["choices"],
        "보기": [], "표": []})}
    context["references"].append(record)
    assert "selected-1" in supplied_source_ids(context)
    record["text"] = record["text"].replace("1", "6", 1)
    with pytest.raises(AuthoringSourceError, match="conflicting retrieval/supplied"):
        supplied_source_ids(context)


@pytest.mark.parametrize("location", ["record", "text", "korean_text"])
@pytest.mark.parametrize("field", ["path", "sha256"])
def test_same_student_with_conflicting_explicit_source_is_rejected(material, location, field):
    context, _, reference, _ = material
    source = deepcopy(reference["source"])
    content = {"student": deepcopy(reference["student"])}
    record = {"id": reference["reference_id"]}
    if location == "record":
        record["source"] = source
    else:
        content["source" if location == "text" else "출처"] = source
    record["text"] = json.dumps(content)
    context["references"].append(record)
    assert "selected-1" in supplied_source_ids(context)
    source[field] = "different.pdf" if field == "path" else "0" * 64
    record["text"] = json.dumps(content)
    with pytest.raises(AuthoringSourceError, match="conflicting retrieval/supplied"):
        supplied_source_ids(context)


@pytest.mark.parametrize("source", [None, {"publisher": "합성 출판사"},
                                    {"pdf_path": "legacy-mirror.pdf", "pdf_sha256": "0" * 64}])
def test_legacy_source_schema_is_not_reinterpreted(material, source):
    context, _, reference, _ = material
    context["references"].append({
        "id": reference["reference_id"], "source": source,
        "text": json.dumps({"student": reference["student"], "source": source}),
    })
    assert "selected-1" in supplied_source_ids(context)


def test_later_retrieval_duplicate_cannot_hide_conflicting_source(material):
    context, _, reference, _ = material
    record = {"id": reference["reference_id"],
              "text": json.dumps({"student": reference["student"]})}
    context["references"].extend([
        {**record, "source": {"path": "different.pdf"}}, record,
    ])
    with pytest.raises(AuthoringSourceError, match="conflicting retrieval/supplied"):
        supplied_source_ids(context)


def test_conflicting_duplicate_retrieval_source_is_rejected_without_assignment():
    context = {"references": [
        {"id": "same", "text": "same", "source": {"sha256": "0" * 64}},
        {"id": "same", "text": "same", "source": {"sha256": "1" * 64}},
    ]}
    with pytest.raises(AuthoringSourceError, match="conflicting retrieval source"):
        supplied_source_ids(context)


@pytest.mark.parametrize("location", ["record", "text", "plain_text_record"])
@pytest.mark.parametrize("field", ["snapshot_path", "snapshot_sha256"])
def test_same_facts_with_conflicting_explicit_snapshot_are_rejected(material, location, field):
    context, _, _, fact = material
    content = {"facts": fact["facts"], "url": fact["url"]}
    record = {"id": fact["id"]}
    metadata = content if location == "text" else record
    metadata[field] = fact[field]
    record["text"] = fact["facts"] if location == "plain_text_record" else json.dumps(content)
    context["references"].append(record)
    assert "fact-1" in supplied_source_ids(context)
    metadata[field] = "different-snapshot.txt" if field == "snapshot_path" else "0" * 64
    record["text"] = fact["facts"] if location == "plain_text_record" else json.dumps(content)
    with pytest.raises(AuthoringSourceError, match="conflicting retrieval/supplied"):
        supplied_source_ids(context)


def test_corpus_container_hash_is_not_a_pdf_hash(material):
    context, _, reference, _ = material
    context["references"].append({
        "id": reference["reference_id"], "source_sha256": "0" * 64,
        "text": json.dumps({"student": reference["student"], "source": reference["source"]}),
    })
    assert "selected-1" in supplied_source_ids(context)


def test_relative_paths_have_explicit_base(material, tmp_path):
    from pathlib import Path
    context, resolution, reference, fact = material
    reference["source"]["path"] = Path(reference["source"]["path"]).name
    fact["snapshot_path"] = Path(fact["snapshot_path"]).name
    for block_key, list_key in (("selected_reference_input", "references"), ("topic_fact_input", "sources")):
        block = resolution[block_key]
        rewrite_packet(block, list_key)
        block["packet_path"] = Path(block["packet_path"]).name
    assert supplied_source_ids(context, base_dir=tmp_path) == {"retrieved-1", "selected-1", "fact-1"}


def test_duplicate_json_keys_fail_closed(material):
    from pathlib import Path
    context, resolution, *_ = material
    block = resolution["topic_fact_input"]
    path = Path(block["packet_path"])
    path.write_text('{"sources": [], "sources": []}')
    block["packet_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(AuthoringSourceError, match="unambiguous JSON"):
        supplied_source_ids(context)
