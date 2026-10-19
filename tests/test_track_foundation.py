"""Synthetic checks for the optional track foundation; no private corpus/model calls."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from haean.tracks import NAMES, all_tracks, get
from haean.tracks.core.model import Draft, public_item
from haean.tracks.core.references import RefQuery, ReferenceIndex, SCHEMA_VERSION
from haean.tracks.core.track import Brief


def brief(track="psat_verbal", grade=7, **kw):
    return Brief(track=track, grade=grade, area="인문", item_type="추론", item_format="일반", discourse="평서문", **kw)


def record(source, *, track="psat_verbal", grade=5, item_id="SYNTHETIC-1", role="item", **kw):
    return {"id": item_id, "track": track, "grade": grade, "role": role,
            "text": "합성 참고 입력", "area": "인문", "item_type": "추론",
            "provenance": {"file": str(source), "locator": "synthetic:row:1",
                           "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "usage": "development"}, **kw}


def packet(tmp_path, rows):
    path = tmp_path / "references.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def source(tmp_path):
    path = tmp_path / "synthetic-source.txt"
    path.write_text("synthetic source, no exam material", encoding="utf-8")
    return path


def test_registry_reports_unconnected_capabilities_without_private_resources():
    tracks = all_tracks()
    assert [t.name for t in tracks] == list(NAMES)
    for track in tracks:
        state = track.status()
        assert state["scope"] == "foundation"
        assert not any(state[key] for key in ("generation_connected", "typeset_connected", "image_file_supported", "quality_improvement_verified"))
        assert not state["composition_available"]
    assert get("leet_reasoning").status()["review_lexicon"] == "not_imported_not_applied"
    with pytest.raises(ValueError):
        get("../other")


@pytest.mark.parametrize("track", ["psat_verbal", "psat_data", "psat_situation"])
def test_all_psat_stage_queries_keep_grade_including_editor(track):
    b = brief(track=track)
    for stage in ("design", "write", "edit"):
        assert all(q.grade == 7 for q in get(track).stage_queries(b, stage).values())
    with pytest.raises(ValidationError, match="급"):
        RefQuery(track=track, role="case")


def test_brief_rejects_duplicate_blank_ids_and_respects_set_size():
    track = get("psat_verbal")
    assert not track.check_brief(brief())
    assert any("중복" in e for e in track.check_brief(brief(count=2, ids=["A", "A"])))
    assert any("공백" in e for e in track.check_brief(brief(ids=[" "])))
    assert any("2문항" in e for e in track.check_brief(brief(count=3, set=True)))
    reading = Brief(track="leet_reading", area="인문", item_type="혼합", item_format="혼합", discourse="평서문", count=3, set=True)
    assert not get("leet_reading").check_brief(reading)
    assert get("leet_reading").max_items() == 30
    assert track.max_items(5) == 40 and track.max_items(7) == 25


def test_readonly_missing_and_old_schema_never_create_or_migrate(tmp_path):
    absent = tmp_path / "absent" / "index.sqlite"
    with pytest.raises(FileNotFoundError):
        ReferenceIndex(absent, readonly=True)
    assert not absent.parent.exists()
    old = tmp_path / "legacy.sqlite"
    with sqlite3.connect(old) as db:
        db.execute("CREATE TABLE refs (track TEXT, id TEXT, PRIMARY KEY(track,id))")
    digest = hashlib.sha256(old.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="스키마"):
        ReferenceIndex(old, readonly=True)
    with pytest.raises(ValueError, match="스키마"):
        ReferenceIndex(old)
    assert hashlib.sha256(old.read_bytes()).hexdigest() == digest


def test_dedicated_index_separates_grades_and_readonly_does_not_write(tmp_path):
    src = source(tmp_path)
    data = packet(tmp_path, [record(src, grade=g) for g in (5, 7)])
    path = tmp_path / "track.sqlite"
    with ReferenceIndex(path) as index:
        assert index.build(data)["indexed"] == 2
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with ReferenceIndex(path, readonly=True) as index:
        for grade in (5, 7):
            result = index.search(RefQuery(track="psat_verbal", grade=grade, k=1))
            assert result["schema_version"] == SCHEMA_VERSION
            assert [r["grade"] for r in result["hits"]] == [grade]
            assert result["hits"][0]["provenance"]["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match="읽기 전용"):
            index.build(data)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_none_grade_duplicates_and_failed_import_preserve_existing_index(tmp_path):
    src = source(tmp_path)
    row = record(src, track="leet_reasoning", grade=None)
    with ReferenceIndex(tmp_path / "track.sqlite") as index:
        assert index.build(packet(tmp_path, [row]))["indexed"] == 1
        duplicate = index.build(packet(tmp_path, [row, row]))
        assert duplicate["indexed"] == 0 and duplicate["errors"]
        assert len(index.search(RefQuery(track="leet_reasoning"))["hits"]) == 1
        assert index.db.execute("SELECT grade FROM track_refs").fetchone()[0] == -1


@pytest.mark.parametrize("failure", ["missing", "hash", "usage", "holdout_file", "holdout_locator", "holdout_tag"])
def test_provenance_is_required_and_holdout_is_rejected(tmp_path, failure):
    src = source(tmp_path)
    row = record(src)
    if failure == "missing":
        del row["provenance"]
    elif failure == "hash":
        row["provenance"]["sha256"] = "0" * 64
    elif failure == "usage":
        row["provenance"]["usage"] = "holdout"
    elif failure == "holdout_tag":
        row["tags"] = ["holdout"]
    else:
        row["provenance"]["file" if failure == "holdout_file" else "locator"] = "HOLDOUT/synthetic"
    with ReferenceIndex(tmp_path / "track.sqlite") as index:
        result = index.build(packet(tmp_path, [row]))
        assert result["indexed"] == 0 and result["errors"]


def test_read_revalidates_record_usage_even_if_database_was_modified(tmp_path):
    src = source(tmp_path)
    row = record(src)
    path = tmp_path / "track.sqlite"
    with ReferenceIndex(path) as index:
        index.build(packet(tmp_path, [row]))
        row["provenance"]["usage"] = "holdout"
        with index.db:
            index.db.execute("UPDATE track_refs SET record = ?", (json.dumps(row),))
    with ReferenceIndex(path, readonly=True) as index:
        with pytest.raises(ValidationError):
            index.search(RefQuery(track="psat_verbal", grade=5))


@pytest.mark.parametrize("source_state", ["changed", "missing"])
def test_search_rechecks_current_source_after_ingest(tmp_path, source_state):
    src = source(tmp_path)
    path = tmp_path / "track.sqlite"
    with ReferenceIndex(path) as index:
        assert index.build(packet(tmp_path, [record(src)]))["indexed"] == 1
    with ReferenceIndex(path, readonly=True) as index:
        result = index.search(RefQuery(track="psat_verbal", grade=5))
        assert result["verified_source_files"] == 1
        assert result["semantic_accuracy_verified"] is False
        if source_state == "changed":
            src.write_text("changed synthetic source", encoding="utf-8")
        else:
            src.unlink()
        with pytest.raises(ValueError, match="참고 자료를 사용할 수 없습니다"):
            index.search(RefQuery(track="psat_verbal", grade=5))


@pytest.mark.parametrize("field,value", [("id", "REPLACED-ID"), ("area", "사회"), ("item_type", "다른 유형")])
def test_search_rejects_sql_payload_identity_or_facet_mismatch(tmp_path, field, value):
    src = source(tmp_path)
    row = record(src)
    path = tmp_path / "track.sqlite"
    with ReferenceIndex(path) as index:
        assert index.build(packet(tmp_path, [row]))["indexed"] == 1
        row[field] = value
        with index.db:
            index.db.execute("UPDATE track_refs SET record = ?", (json.dumps(row),))
    with ReferenceIndex(path, readonly=True) as index:
        with pytest.raises(ValueError, match="ID·분류 값"):
            index.search(RefQuery(track="psat_verbal", grade=5, area="인문", item_type="추론"))


def test_rules_preserve_structure_review_and_reject_path_traversal():
    track = get("leet_reasoning")
    rules = track.rule("editor")
    assert "전 버전 보존" in rules and "오답 함정" in rules
    assert "세부 소재 겹침만" not in rules
    with pytest.raises(ValueError):
        track.rule("../../data/private")
    assert "정답·해설" in track.rule("blind")


def test_lexicon_is_not_implicitly_enabled_by_an_external_file(tmp_path):
    from haean.tracks.leet_reasoning.review_checks import load_lexicon
    path = tmp_path / "synthetic-lexicon.json"
    path.write_text(json.dumps({"entries": [{"초안": "합성", "마감": "표현"}]}))
    assert load_lexicon(path) == []


def test_new_draft_is_explicitly_separate_and_blind_payload_has_no_answers():
    item = {"id": "SYNTHETIC-1", "area": "인문", "item_type": "추론", "item_format": "일반", "discourse": "평서문",
            "difficulty": "중", "topic": "합성", "stem": "옳은 것은?", "passage": [{"kind": "문단", "text": "합성 지문"}],
            "options": [{"text": f"합성 선지 {i}"} for i in range(1, 6)], "answer": 1,
            "solution": {"topic": "합성", "level": 3},
            "design": {"core_judgment": "합성", "answer_condition": "합성", "distractor_paths": ["합성"], "bypass_check": "합성", "reference_use": "없음"},
            "essential_conditions": ["비공개 설계"], "reference_ids": ["비공개 참고"]}
    draft = Draft.model_validate({"design_summary": "합성", "items": [item]})
    public = public_item(draft.items[0])
    assert not {"answer", "solution", "design", "reference_ids", "essential_conditions", "calculations"} & public.keys()
    image_item = {**item, "figures": [{"id": "x", "kind": "image", "path": "/synthetic/no-file.png"}]}
    with pytest.raises(ValidationError):
        Draft.model_validate({"design_summary": "합성", "items": [image_item]})
    from haean.models import Draft as ExistingDraft
    with pytest.raises(ValidationError):
        ExistingDraft.model_validate(draft.model_dump())
