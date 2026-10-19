"""Synthetic source-grounded overlays; no real questions or model executions."""
import copy
import json
from pathlib import Path

import pytest

from haean import reference_answers, reference_curation
from haean.staged_authoring import _source_files
from haean.tracks.core.references import RefQuery, ReferenceIndex, RefRecord, verify_corpus_evidence
from test_reference_answers import audit
from test_reference_bridge import corpus_data, save, sha
from test_track_cli import local_cli


def load_records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_records(path, records):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n", encoding="utf-8")


@pytest.fixture
def curation(audit, tmp_path):
    d = audit
    reference_answers.enrich(d["refs"], d["manifest"], d["new"])
    source = d["new"] / "refs.jsonl"
    rows = load_records(source)
    fields = {
        "area": {"value": "사회", "rationale": "합성 지문의 분류 설명",
                 "evidence": [{"pointer": "/지문", "quote": "합성 지문"}]},
        "item_type": {"value": "추론", "rationale": "합성 발문과 선택지를 확인한 분류 설명",
                      "evidence": [{"pointer": "/발문", "quote": "합성 발문"},
                                   {"pointer": "/선지/0/text", "quote": "합성 선지 1"}]},
        "item_format": {"value": "일반", "rationale": "합성 선택지 형식",
                        "evidence": [{"pointer": "/선지/0/text", "quote": "합성 선지 1"}]},
        "discourse": {"value": "평서문", "rationale": "합성 지문 형식",
                      "evidence": [{"pointer": "/지문", "quote": "합성 지문"}]},
        "stem_type": {"value": "합성 발문 형식", "rationale": "합성 발문 형태",
                      "evidence": [{"pointer": "/발문", "quote": "합성 발문"}]},
    }
    manifest = {"schema_version": 1, "usage": "development", "origin": "model", "actual_model": None,
                "status": "source_grounded_model_curation", "human_approved": False,
                "semantic_accuracy_verified": False, "records": [
                    {"id": row["id"], "source_record_sha256": reference_curation.record_sha256(row),
                     "fields": copy.deepcopy(fields)} for row in rows]}
    classification = tmp_path / "classification-input.json"
    save(classification, manifest)
    return {**d, "source": source, "classification": classification, "classified": tmp_path / "classified",
            "classification_data": manifest}


def curate(d):
    return reference_curation.curate(d["source"], d["classification"], d["classified"])


def test_immutable_overlay_preserves_evidence_filters_grades_and_staged_sources(curation):
    d = curation
    protected = {path: path.read_bytes() for path in (d["source"], d["classification"], d["packet"], d["corpus"])}
    receipt = curate(d)
    assert receipt["exported"] == 2 and receipt["origin"] == "model" and receipt["actual_model"] is None
    assert receipt["status"] == "source_grounded_model_curation"
    assert receipt["human_approved"] is False and receipt["semantic_accuracy_verified"] is False
    assert all(path.read_bytes() == data for path, data in protected.items())
    assert (d["classified"] / "source-refs.jsonl").read_bytes() == protected[d["source"]]
    assert (d["classified"] / "classification.json").read_bytes() == protected[d["classification"]]
    originals = {row["id"]: row for row in load_records(d["source"])}
    refs = d["classified"] / "refs.jsonl"
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        assert index.build(refs)["indexed"] == 2
        for grade in (5, 7):
            query = RefQuery(track="psat_verbal", grade=grade, area="사회", item_type="추론",
                             item_format="일반", discourse="평서문", stem_type="합성 발문 형식")
            result = index.search(query)
            assert len(result["hits"]) == 1 and "완화하지 않았습니다" in result["missing"][0]
            hit = result["hits"][0]
            assert hit["grade"] == grade and hit["answer"] == 2 and hit["answer_verified"] is True
            original = RefRecord.model_validate(originals[hit["id"]]).model_dump()
            excluded = {*d["classification_data"]["records"][0]["fields"], "classification_evidence"}
            assert {key: value for key, value in hit.items() if key not in excluded} == {
                key: value for key, value in original.items() if key not in excluded}
            assert hit["corpus_evidence"]["label_status"] == "provisional"
            assert hit["corpus_evidence"]["answer_verified"] is False
            source_files = _source_files({"design": {"examples": result}})
            for section in ("classification_evidence", "official_answer_evidence"):
                for key in ("manifest", "source_refs"):
                    provenance = hit[section][key]
                    assert source_files[provenance["file"]] == provenance["sha256"]
            assert {value["file"] for value in hit["official_answer_evidence"]["files"].values()} <= source_files.keys()
            for overrides in ({"role": "case"}, {"area": "인문"}, {"item_type": "일치부합"},
                              {"item_format": "합답형"}, {"discourse": "대화형"}, {"stem_type": "다른 발문"}):
                assert index.search(query.model_copy(update=overrides))["hits"] == []
        assert index.search(RefQuery(track="psat_data", grade=5))["hits"] == []


def test_cli_curate_build_search_and_existing_output_are_safe(curation, monkeypatch, capsys):
    d = curation
    receipt = local_cli(monkeypatch, capsys, "ref-curate", d["source"], "--classification",
                        d["classification"], "--out", d["classified"])
    assert receipt["exported"] == 2
    refs = d["classified"] / "refs.jsonl"
    previous = refs.read_bytes()
    with pytest.raises(ValueError, match="새 --out"):
        curate(d)
    assert refs.read_bytes() == previous
    index = d["classified"] / "index.sqlite"
    assert local_cli(monkeypatch, capsys, "ref-build", refs, "--out", index)["indexed"] == 2
    query = d["classified"] / "query.json"
    save(query, {"track": "psat_verbal", "grade": 7, "area": "사회", "item_type": "추론"})
    result = local_cli(monkeypatch, capsys, "ref-search", query, "--index", index)
    assert len(result["hits"]) == 1 and result["hits"][0]["grade"] == 7


def test_undeclared_original_provisional_type_can_remain_unknown_and_human_is_not_approval(curation):
    d = curation
    manifest = d["classification_data"]
    manifest.update(origin="human", status="source_grounded_human_curation")
    for row in manifest["records"]:
        row["fields"] = {"area": row["fields"]["area"]}
    save(d["classification"], manifest)
    assert curate(d)["status"] == "source_grounded_human_curation"
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        assert index.build(d["classified"] / "refs.jsonl")["indexed"] == 2
        hit = index.search(RefQuery(track="psat_verbal", grade=5, area="사회"))["hits"][0]
        assert hit["item_type"] == "합성 잠정 유형" and hit["item_format"] == ""
        assert hit["classification_evidence"]["human_approved"] is False


@pytest.mark.parametrize("mutation", [
    "area_vocab", "type_vocab", "unsupported_notes", "unsupported_answer", "unsupported_grade", "empty_fields",
    "empty_value", "blank_value", "numeric_value", "blank_rationale", "no_evidence", "blank_quote",
    "wrong_quote", "wrong_pointer", "invalid_escape", "missing_pointer", "container_pointer", "numeric_pointer",
    "array_leading_zero", "array_outside", "row_sha", "duplicate_id", "missing_id", "empty_records",
    "extra_field", "holdout_id", "holdout_value", "usage", "origin_status", "official_status",
    "human_approved", "semantic_accuracy_verified", "empty_model", "boolean_version", "zero_approval",
])
def test_invalid_classification_fails_atomically(curation, mutation):
    d = curation
    manifest = d["classification_data"]
    row = manifest["records"][0]
    field = row["fields"]["area"]
    evidence = field["evidence"][0]
    if mutation == "area_vocab": field["value"] = "잘못된 영역"
    elif mutation == "type_vocab": row["fields"]["item_type"]["value"] = "잘못된 유형"
    elif mutation.startswith("unsupported_"): row["fields"][mutation.removeprefix("unsupported_")] = field
    elif mutation == "empty_fields": row["fields"] = {}
    elif mutation == "empty_value": field["value"] = ""
    elif mutation == "blank_value": field["value"] = "  "
    elif mutation == "numeric_value": field["value"] = 7
    elif mutation == "blank_rationale": field["rationale"] = " \n"
    elif mutation == "no_evidence": field["evidence"] = []
    elif mutation == "blank_quote": evidence["quote"] = " "
    elif mutation == "wrong_quote": evidence["quote"] = "합성 발문"
    elif mutation == "wrong_pointer": evidence["pointer"] = "/발문"
    elif mutation == "invalid_escape": evidence["pointer"] = "/~2"
    elif mutation == "missing_pointer": evidence["pointer"] = "지문"
    elif mutation == "container_pointer": evidence["pointer"] = "/선지"
    elif mutation == "numeric_pointer": evidence["pointer"] = "/연도"
    elif mutation == "array_leading_zero": evidence["pointer"] = "/선지/00/text"
    elif mutation == "array_outside": evidence["pointer"] = "/선지/5/text"
    elif mutation == "row_sha": row["source_record_sha256"] = "0" * 64
    elif mutation == "duplicate_id": manifest["records"].append(copy.deepcopy(row))
    elif mutation == "missing_id": manifest["records"].pop()
    elif mutation == "empty_records": manifest["records"] = []
    elif mutation == "extra_field": row["notes"] = "허용하지 않는 변경"
    elif mutation == "holdout_id": row["id"] = "holdout-case"
    elif mutation == "holdout_value": row["fields"]["discourse"]["value"] = "holdout"
    elif mutation == "usage": manifest["usage"] = "holdout"
    elif mutation == "origin_status": manifest["origin"] = "human"
    elif mutation == "official_status": manifest["status"] = "official_verified"
    elif mutation in ("human_approved", "semantic_accuracy_verified"): manifest[mutation] = True
    elif mutation == "empty_model": manifest["actual_model"] = " "
    elif mutation == "boolean_version": manifest["schema_version"] = True
    elif mutation == "zero_approval": manifest["human_approved"] = 0
    save(d["classification"], manifest)
    original = d["source"].read_bytes()
    with pytest.raises(ValueError, match="분류 보강 실패"):
        curate(d)
    assert d["source"].read_bytes() == original
    assert not (d["classified"] / "refs.jsonl").exists()
    assert json.loads((d["classified"] / "failure.json").read_text())["exported"] == 0


@pytest.mark.parametrize("target", ["classification_manifest", "classification_source", "pdf", "packet", "corpus_row",
                                     "selection", "official_manifest", "official_source", "official_file"])
@pytest.mark.parametrize("when", ["build", "search"])
def test_current_chain_mutation_fails_build_and_search(curation, target, when):
    d = curation
    curate(d)
    refs = d["classified"] / "refs.jsonl"
    row = load_records(refs)[0]
    targets = {
        "classification_manifest": row["classification_evidence"]["manifest"]["file"],
        "classification_source": row["classification_evidence"]["source_refs"]["file"],
        "pdf": row["provenance"]["file"], "packet": row["corpus_evidence"]["packet"]["file"],
        "corpus_row": row["corpus_evidence"]["source_record"]["file"],
        "selection": row["corpus_evidence"]["selection"]["file"],
        "official_manifest": row["official_answer_evidence"]["manifest"]["file"],
        "official_source": row["official_answer_evidence"]["source_refs"]["file"],
        "official_file": next(iter(row["official_answer_evidence"]["files"].values()))["file"],
    }
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        if when == "search": assert index.build(refs)["indexed"] == 2
        path = Path(targets[target])
        path.write_bytes(path.read_bytes() + b"changed")
        if when == "build":
            assert index.build(refs)["indexed"] == 0
        else:
            with pytest.raises(ValueError, match="참고 자료를 사용할 수 없습니다"):
                index.search(RefQuery(track="psat_verbal", grade=5))


@pytest.mark.parametrize("field", ["text", "notes", "tags", "source", "year", "number", "answer", "answer_verified",
                                  "grade", "track", "role", "area", "item_type", "corpus_evidence", "official_answer_evidence"])
@pytest.mark.parametrize("when", ["build", "search"])
def test_overlay_cannot_modify_other_fields_or_disagree_with_manifest(curation, field, when):
    d = curation
    curate(d)
    refs = d["classified"] / "refs.jsonl"
    records = load_records(refs)
    row = records[0]
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        if when == "search": assert index.build(refs)["indexed"] == 2
        values = {"text": "변조", "notes": "변조", "tags": ["변조"], "source": "변조", "year": 2033, "number": 2,
                  "answer": 3, "answer_verified": False, "grade": 7, "track": "psat_data", "role": "case",
                  "area": "인문", "item_type": "일치부합"}
        if field == "corpus_evidence": row[field]["original_meta"]["fields"]["문항유형"] = "변조"
        elif field == "official_answer_evidence": row[field]["source_id"] = "변조"
        else: row[field] = values[field]
        if when == "build":
            write_records(refs, records)
            assert index.build(refs)["indexed"] == 0
        else:
            with index.db:
                index.db.execute("UPDATE track_refs SET record=? WHERE id=?", (json.dumps(row), row["id"]))
            with pytest.raises(ValueError):
                index.search(RefQuery(track="psat_verbal", grade=5))


def test_undeclared_facet_cannot_change_even_to_a_valid_value(curation):
    d = curation
    manifest = d["classification_data"]
    for row in manifest["records"]: row["fields"].pop("discourse")
    save(d["classification"], manifest)
    curate(d)
    refs = d["classified"] / "refs.jsonl"
    rows = load_records(refs)
    rows[0]["discourse"] = "평서문"
    write_records(refs, rows)
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        result = index.build(refs)
        assert result["indexed"] == 0 and "분류 필드 외" in result["errors"][0]["error"]


@pytest.mark.parametrize("kind", ["provisional", "nested", "duplicate", "missing", "role"])
def test_unsupported_or_ambiguous_source_is_rejected(curation, kind):
    d = curation
    if kind == "provisional":
        d["source"] = d["refs"]
    elif kind == "nested":
        curate(d)
        d["source"] = d["classified"] / "refs.jsonl"
        d["classified"] = d["classified"].parent / "nested"
    rows = load_records(d["source"])
    if kind == "duplicate": rows.append(copy.deepcopy(rows[0]))
    elif kind == "missing": rows[0].pop("id")
    elif kind == "role": rows[0]["role"] = "case"
    source = d["classified"].parent / "modified-source.jsonl"
    write_records(source, rows)
    d["source"] = source
    for mapping, row in zip(d["classification_data"]["records"], rows):
        mapping["source_record_sha256"] = reference_curation.record_sha256(row)
    save(d["classification"], d["classification_data"])
    with pytest.raises(ValueError, match="분류 보강 실패"):
        curate(d)
    assert not (d["classified"] / "refs.jsonl").exists()


def test_original_validators_still_reject_curated_labels_without_wrapper(curation):
    d = curation
    curate(d)
    record = RefRecord.model_validate(load_records(d["classified"] / "refs.jsonl")[0])
    with pytest.raises(ValueError, match="corpus 전사 원본"):
        verify_corpus_evidence(record, d["classified"], {})
    with pytest.raises(ValueError, match="원래 전사 refs"):
        reference_answers.verify_official_answer_evidence(record, d["classified"], {})


def test_json_pointer_escapes_and_duplicate_manifest_keys():
    assert reference_curation._pointer({"a/b": {"~c": ["정확한 인용"]}}, "/a~1b/~0c/0") == "정확한 인용"
    with pytest.raises(ValueError, match="중복 JSON 키"):
        reference_curation._manifest('{"schema_version":1,"schema_version":1}')


def test_raw_row_hash_does_not_insert_new_optional_defaults(curation):
    row = load_records(curation["source"])[0]
    row.pop("classification_evidence", None)
    assert reference_curation.record_sha256(row) != reference_curation.record_sha256(RefRecord.model_validate(row).model_dump())


@pytest.mark.parametrize("field", ["text", "notes", "answer", "item_type"])
@pytest.mark.parametrize("when", ["build", "search"])
def test_resealed_original_snapshot_cannot_override_original_evidence(curation, field, when):
    d = curation
    curate(d)
    refs = d["classified"] / "refs.jsonl"
    rows = load_records(refs)
    record = rows[0]
    evidence = record["classification_evidence"]
    source_path, manifest_path = Path(evidence["source_refs"]["file"]), Path(evidence["manifest"]["file"])
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        if when == "search": assert index.build(refs)["indexed"] == 2
        original_rows = load_records(source_path)
        original = original_rows[0]
        value = {"text": original["text"] + " ", "notes": "변경된 원본처럼 위장", "answer": 3,
                 "item_type": "추론"}[field]
        original[field] = value
        if field != "item_type": record[field] = value
        write_records(source_path, original_rows)
        manifest = json.loads(manifest_path.read_text())
        mapping = next(row for row in manifest["records"] if row["id"] == record["id"])
        mapping["source_record_sha256"] = evidence["source_record_sha256"] = reference_curation.record_sha256(original)
        save(manifest_path, manifest)
        evidence["source_refs"]["sha256"], evidence["manifest"]["sha256"] = sha(source_path), sha(manifest_path)
        if when == "build":
            write_records(refs, rows)
            assert index.build(refs)["indexed"] == 0
        else:
            with index.db:
                index.db.execute("UPDATE track_refs SET record=? WHERE id=?", (json.dumps(record), record["id"]))
            with pytest.raises(ValueError, match="참고 자료를 사용할 수 없습니다"):
                index.search(RefQuery(track="psat_verbal", grade=5))


def test_manifest_and_original_inputs_can_change_after_frozen_export(curation):
    d = curation
    curate(d)
    d["source"].write_text("later replacement")
    d["classification"].write_text("later replacement")
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        assert index.build(d["classified"] / "refs.jsonl")["indexed"] == 2
        assert len(index.search(RefQuery(track="psat_verbal", grade=5))["hits"]) == 1


def test_omitting_overlay_evidence_does_not_bypass_original_checks(curation):
    d = curation
    curate(d)
    refs = d["classified"] / "refs.jsonl"
    rows = load_records(refs)
    for row in rows: row.pop("classification_evidence")
    write_records(refs, rows)
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        assert index.build(refs)["indexed"] == 0


@pytest.mark.parametrize("facet", ["area", "item_type", "item_format", "discourse", "stem_type"])
@pytest.mark.parametrize("pointer,quote", [("/분류 검증", "provisional"), ("/문항유형", "합성 잠정 유형"),
                                         ("/과목", "언어논리")])
def test_each_facet_requires_question_content_instead_of_metadata_only(curation, facet, pointer, quote):
    d = curation
    manifest = d["classification_data"]
    manifest["records"][0]["fields"][facet]["evidence"] = [{"pointer": pointer, "quote": quote}]
    save(d["classification"], manifest)
    with pytest.raises(ValueError, match=facet + "에는 실제 문항 본문"):
        curate(d)
    assert not (d["classified"] / "refs.jsonl").exists()
    assert json.loads((d["classified"] / "failure.json").read_text())["exported"] == 0


def test_metadata_can_supplement_a_content_quote_in_each_facet(curation):
    d = curation
    manifest = d["classification_data"]
    for row in manifest["records"]:
        for field in row["fields"].values():
            field["evidence"].insert(0, {"pointer": "/분류 검증", "quote": "provisional"})
            field["evidence"].append({"pointer": "/문항유형", "quote": "합성 잠정 유형"})
    save(d["classification"], manifest)
    assert curate(d)["exported"] == 2
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        assert index.build(d["classified"] / "refs.jsonl")["indexed"] == 2
        assert len(index.search(RefQuery(track="psat_verbal", grade=5))["hits"]) == 1


@pytest.mark.parametrize("when", ["build", "search"])
def test_resealed_metadata_only_manifest_fails_build_and_search(curation, when):
    d = curation
    curate(d)
    refs = d["classified"] / "refs.jsonl"
    rows = load_records(refs)
    evidence = rows[0]["classification_evidence"]
    manifest_path = Path(evidence["manifest"]["file"])
    with ReferenceIndex(d["classified"] / "index.sqlite") as index:
        if when == "search": assert index.build(refs)["indexed"] == 2
        manifest = json.loads(manifest_path.read_text())
        manifest["records"][0]["fields"]["area"]["evidence"] = [{"pointer": "/분류 검증", "quote": "provisional"}]
        save(manifest_path, manifest)
        for row in rows: row["classification_evidence"]["manifest"]["sha256"] = sha(manifest_path)
        if when == "build":
            write_records(refs, rows)
            result = index.build(refs)
            assert result["indexed"] == 0 and "실제 문항 본문" in result["errors"][0]["error"]
        else:
            with index.db:
                index.db.execute("UPDATE track_refs SET record=? WHERE id=?", (json.dumps(rows[0]), rows[0]["id"]))
            with pytest.raises(ValueError, match="실제 문항 본문"):
                index.search(RefQuery(track="psat_verbal", grade=5))
