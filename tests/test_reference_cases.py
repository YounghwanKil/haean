"""Historical feedback snapshots, not answer keys or current expert reviews."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from haean.reference_cases import export, originality_texts
from haean.staged_authoring import _source_files, attach, run_staged, validate_staged
from haean.tracks.core.references import ReferenceIndex, RefQuery
from test_staged_authoring import Provider, prepared, track_brief


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def selection(tmp_path):
    source = tmp_path / "history.txt"
    source.write_text("버전 초안\n서로 다른 세 창고에는 붉은 상자와 푸른 상자와 흰 상자를 각각 하나씩 배치한다.\n"
                      "붉은 상자는 동쪽 창고에 있을 수 없으며 흰 상자의 창고와 푸른 상자의 창고가 서로 이웃하지 않는다. 창고의 이름은 동쪽과 남쪽과 북쪽이며 모든 상자는 크기가 같고 어느 창고에도 상자를 둘 이상 배치할 수 없다.\n"
                      "정답과 해설은 아직 검증되지 않음.\n"
                      "검토자 갑: 이웃 관계의 정의가 없어 결론을 확정할 수 없다.\n"
                      "검토자 을: 같은 조건이 이미 충분하다고 생각한다.\n"
                      "부분 수정: 동쪽 창고의 다음은 남쪽 창고라는 문장을 추가한다.\n", encoding="utf-8")
    data = source.read_bytes()
    def span(start, end):
        return {"file": source.name, "sha256": sha(data), "start_line": start, "end_line": end,
                "excerpt_sha256": sha(b"".join(data.splitlines(keepends=True)[start-1:end]))}
    row = {"case_key": "synthetic-history-question-1", "family_id": "synthetic-history-family-1",
           "track": "psat_situation", "grade": 7, "area": "생활·일상(가상)", "item_type": "조건 추론",
           "item_format": "일반", "discourse": "평서문", "stem_type": "", "source": "합성 수정 이력",
           "year": None, "number": 1, "status": "partially_resolved",
           "before": {"version_label": "초안 v1 (원자료 표기)",
                      "author": {"origin": "unknown", "label": "초안 작성자 미상"},
                      "text": span(1, 4), "public_text": span(2, 3)},
           "reviewers": [{"origin": "human_reported", "label": "제공 문서의 검토자 갑", "text": span(5, 5)},
                         {"origin": "unknown", "label": "제공 문서의 검토자 을", "text": span(6, 6)}],
           "after": {"kind": "delta", "version_label": "수정 메모 v2", "text": span(7, 7),
                     "public_text": None, "author": {"origin": "model", "label": "합성 수정자"}}}
    manifest = {"schema_version": 1, "usage": "development", "origin": "model", "actual_model": None,
                "human_approved": False, "semantic_accuracy_verified": False, "records": [row]}
    path = tmp_path / "selection.json"
    write(path, manifest)
    return path


def exported(selection):
    out = selection.parent / "exported"
    result = export(selection, out)
    return out, result, json.loads((out / "refs.jsonl").read_text())


def index_for(selection):
    out, result, row = exported(selection)
    path = selection.parent / "index.sqlite"
    with ReferenceIndex(path) as index:
        built = index.build(out / "refs.jsonl")
    assert built["errors"] == [] and built["indexed"] == 1
    return path, out, row


def query(**overrides):
    return RefQuery(**({"track": "psat_situation", "grade": 7, "role": "case",
                       "area": "생활·일상(가상)", "k": 4} | overrides))


def test_exact_snapshots_filters_uncertainty_and_projections(selection):
    originals = {p: p.read_bytes() for p in selection.parent.iterdir()}
    path, out, row = index_for(selection)
    with ReferenceIndex(path, readonly=True) as index:
        found = index.search(query())
        assert len(found["hits"]) == 1 and found["missing"]
        assert index.search(query(grade=5))["hits"] == []
        assert index.search(query(role="item"))["hits"] == []
        assert index.search(query(area="경제·금융"))["hits"] == []
    assert all(p.read_bytes() == data for p, data in originals.items())
    assert row["answer"] is None and row["item"] is None and row["answer_verified"] is False
    body = json.loads(row["text"])
    assert body["curation"] == {"origin": "model", "actual_model": None}
    assert body["reviewers"][0]["origin"] == "human_reported"
    assert body["attribution_scope"] == "reported_source_labels_not_authenticated_expert_identity"
    assert body["status"] == "partially_resolved" and body["after"]["kind"] == "delta"
    assert len(body["reviewers"]) == 2 and body["human_approved"] is False
    projections = originality_texts(row)
    assert len(projections) == 1
    assert "검토자" not in projections[0]["text"] and "정답과 해설" not in projections[0]["text"]
    sources = _source_files({"edit": {"review_cases": found}})
    assert set(sources) == {str(out / "selection.json"), *[p["file"] for p in row["review_case_evidence"]["source_files"].values()]}


@pytest.mark.parametrize("mutation", ["role", "answer", "approved", "text", "facet", "identity", "strip_evidence", "strip_both_markers"])
def test_record_promotion_and_tampering_rejected(selection, mutation):
    out, _, row = exported(selection)
    if mutation == "role": row["role"] = "item"
    elif mutation == "answer": row["answer"] = 3; row["answer_verified"] = True
    elif mutation == "approved": row["review_case_evidence"]["human_approved"] = True
    elif mutation == "text": row["text"] += " 새 결론"
    elif mutation == "facet": row["area"] = "경제·금융"
    elif mutation == "identity": row["id"] = "other"
    elif mutation == "strip_evidence": row["review_case_evidence"] = None
    elif mutation == "strip_both_markers": row["review_case_evidence"] = None; row["tags"] = []
    (out / "refs.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n")
    with ReferenceIndex(selection.parent / "bad.sqlite") as index:
        result = index.build(out / "refs.jsonl")
    assert result["indexed"] == 0 and result["errors"]


@pytest.mark.parametrize("mutation", ["span", "source", "manifest"])
def test_changed_snapshot_rejected_at_search(selection, mutation):
    path, out, row = index_for(selection)
    if mutation == "source":
        target = Path(next(iter(row["review_case_evidence"]["source_files"].values()))["file"])
        target.write_text(target.read_text() + "changed")
    else:
        target = out / "selection.json"
        manifest = load(target)
        if mutation == "span": manifest["records"][0]["before"]["public_text"]["start_line"] = 1
        else: manifest["origin"] = "human"
        write(target, manifest)
    with ReferenceIndex(path, readonly=True) as index, pytest.raises(ValueError):
        index.search(query())


@pytest.mark.parametrize("mutation", ["hash", "excerpt", "out_of_range", "outside_public", "other_public_file",
                                    "duplicate_family", "duplicate_id", "delta_public", "full_without_public", "holdout", "holdout_symlink"])
def test_bad_selection_rejected_before_output(selection, mutation):
    manifest = load(selection)
    row = manifest["records"][0]
    if mutation == "hash": row["before"]["text"]["sha256"] = "0" * 64
    elif mutation == "excerpt": row["before"]["text"]["excerpt_sha256"] = "0" * 64
    elif mutation == "out_of_range": row["before"]["text"]["end_line"] = 999
    elif mutation == "outside_public": row["before"]["public_text"] = row["reviewers"][0]["text"]
    elif mutation == "other_public_file":
        copy_path = selection.parent / "copy.txt"
        copy_path.write_bytes((selection.parent / "history.txt").read_bytes())
        row["before"]["public_text"]["file"] = copy_path.name
    elif mutation in {"duplicate_family", "duplicate_id"}:
        other = copy.deepcopy(row)
        other["case_key" if mutation == "duplicate_family" else "family_id"] += "-other"
        manifest["records"].append(other)
    elif mutation == "delta_public": row["after"]["public_text"] = row["after"]["text"]
    elif mutation == "full_without_public": row["after"]["kind"] = "full"
    elif mutation.startswith("holdout"):
        folder = selection.parent / "holdout"; folder.mkdir()
        hidden = folder / "source.txt"; hidden.write_bytes((selection.parent / "history.txt").read_bytes())
        if mutation == "holdout_symlink":
            link = selection.parent / "innocent.txt"; link.symlink_to(hidden)
            row["before"]["text"]["file"] = str(link)
        else: row["before"]["text"]["file"] = str(hidden)
    write(selection, manifest)
    out = selection.parent / "rejected"
    with pytest.raises((ValueError, OSError)):
        export(selection, out)
    assert not out.exists()


def test_duplicate_family_across_exports_rejected(selection):
    first, _, _ = exported(selection)
    manifest = load(selection)
    manifest["records"][0]["case_key"] = "same-family-other-case"
    write(selection, manifest)
    second = selection.parent / "second"
    export(selection, second)
    with ReferenceIndex(selection.parent / "duplicates.sqlite") as index:
        result = index.build([first / "refs.jsonl", second / "refs.jsonl"])
    assert any("family_id" in e["error"] for e in result["errors"])


def two_cases(selection):
    manifest = load(selection)
    other = copy.deepcopy(manifest["records"][0])
    other["case_key"] += "-second"
    other["family_id"] += "-second"
    manifest["records"].append(other)
    write(selection, manifest)


def test_complete_line_truncation_cannot_hide_selected_case(selection):
    two_cases(selection)
    out = selection.parent / "exported"
    export(selection, out)
    lines = (out / "refs.jsonl").read_bytes().splitlines(keepends=True)
    (out / "refs.jsonl").write_bytes(lines[0])
    with ReferenceIndex(selection.parent / "truncated.sqlite") as index:
        result = index.build(out / "refs.jsonl")
    assert result["indexed"] == 0
    assert any("전체 사례 집합" in e["error"] for e in result["errors"])


def test_interrupted_write_never_publishes_partial_refs(selection, monkeypatch):
    two_cases(selection)
    real_open = Path.open
    class BrokenWriter:
        def __init__(self, file): self.file = file
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def write(self, data):
            self.file.write(data.splitlines(keepends=True)[0])
            raise OSError("synthetic disk interruption")
    def interrupted(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        return BrokenWriter(stream) if path.name == ".refs.jsonl.pending" else stream
    monkeypatch.setattr(Path, "open", interrupted)
    out = selection.parent / "interrupted"
    with pytest.raises(OSError, match="synthetic"):
        export(selection, out)
    assert not (out / "refs.jsonl").exists()
    assert (out / ".refs.jsonl.pending").exists()


def test_export_never_overwrites_source_or_output(selection):
    old = selection.read_bytes()
    with pytest.raises(ValueError, match="덮어쓰지"):
        export(selection, selection)
    out, _, _ = exported(selection)
    with pytest.raises(ValueError, match="덮어쓰지"):
        export(selection, out)
    assert selection.read_bytes() == old


def test_full_after_projection_is_separate_from_delta(selection):
    manifest = load(selection)
    row = manifest["records"][0]
    row["after"] = {"kind": "full", **copy.deepcopy(row["before"])}
    write(selection, manifest)
    _, _, record = exported(selection)
    assert len(originality_texts(record)) == 2


def test_cli_export_build_search_and_attach(selection):
    from test_track_cli import invoke
    out = selection.parent / "cli-export"
    result = invoke("review-export", "--selection", selection, "--out", out)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["records"] == 1
    db = selection.parent / "cli.sqlite"
    built = invoke("ref-build", out / "refs.jsonl", "--out", db)
    assert built.returncode == 0, built.stderr
    assert json.loads(built.stdout)["indexed"] == 1
    query_file = selection.parent / "query.json"
    write(query_file, query().model_dump())
    found = invoke("ref-search", query_file, "--index", db)
    assert found.returncode == 0, found.stderr
    assert len(json.loads(found.stdout)["hits"]) == 1
    brief_file = selection.parent / "brief.json"
    write(brief_file, track_brief().model_dump())
    run = prepared(selection.parent)
    attached = invoke("attach", run, brief_file, "--index", db)
    assert attached.returncode == 0, attached.stderr
    refs = load(run / "staged/references.json")
    assert len(refs["edit"]["review_cases"]["hits"]) == 1


def test_staged_feedback_reaches_writer_revision_editor_never_blind(selection, draft, monkeypatch):
    from haean import execution_provenance
    monkeypatch.setattr(execution_provenance, "runtime_sources", lambda: {"synthetic.py": b"fixed"})
    path, out, record = index_for(selection)
    run = prepared(selection.parent)
    attach(run, track_brief(), index_path=path)
    normal = Provider(draft)
    def hook(stage, payload, _):
        if stage == "generate":
            result = normal.call(stage, "", payload, type(draft))
            result.items[0].difficulty = "상"
            return result
    provider = Provider(draft, hook)
    run_staged(run, provider, max_revisions=1)
    for stage, instructions, payload in provider.calls:
        serialized = json.dumps(payload, ensure_ascii=False)
        if stage in {"generate", "revise", "editor"}:
            assert "historical_review_case" in serialized and "검토자 갑" in serialized
            assert "상반 의견" in serialized
        elif stage == "blind":
            assert set(payload) == {"items"}
            assert "historical_review_case" not in serialized and "검토자 갑" not in serialized
    manifest = load(run / "staged/snapshot-review/manifest.json")
    captured = {v["path"] for v in manifest["inputs"].values()}
    assert set(_source_files(load(run / "staged/references.json"))) <= captured
    contract = load(run / "staged/contract.json")
    candidate = type(draft).model_validate(load(run / "candidate.json"))
    candidate.items[0].passage = originality_texts(record)[0]["text"]
    assert any("긴 문구" in e for e in validate_staged(candidate, contract))


def test_attached_source_snapshot_mutation_stops_before_provider(selection, draft, monkeypatch):
    from haean import execution_provenance
    monkeypatch.setattr(execution_provenance, "runtime_sources", lambda: {"synthetic.py": b"fixed"})
    path, out, record = index_for(selection)
    run = prepared(selection.parent)
    attach(run, track_brief(), index_path=path)
    source = Path(next(iter(record["review_case_evidence"]["source_files"].values()))["file"])
    source.write_bytes(source.read_bytes() + b"tamper")
    provider = Provider(draft)
    with pytest.raises(ValueError, match="입력이 변경|스냅샷"):
        run_staged(run, provider, max_revisions=0)
    assert provider.calls == []
