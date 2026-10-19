"""CLI routing checks use synthetic specifications only."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def invoke(*arguments):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    return subprocess.run([sys.executable, "-m", "haean.cli", "track", *map(str, arguments)],
                          env=env, text=True, capture_output=True)


def test_track_list_reports_stage_and_all_products():
    result = invoke("list")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["integration_stage"] == "foundation_and_staged_legacy_authoring"
    assert data["generation_integrated"] is False
    assert data["staged_legacy_generation_integrated"] is True
    tracks = {x["name"]: x for x in data["tracks"]}
    assert set(tracks) == {"leet_reasoning", "leet_reading", "psat_verbal", "psat_data", "psat_situation"}
    assert tracks["psat_data"]["exam_sizes"] == {"5": 40, "7": 25}
    assert tracks["leet_reading"]["set_size"] == 3


def test_track_invalid_grade_exits_nonzero_without_starting_generation(tmp_path):
    path = tmp_path / "brief.json"
    data = dict(track="psat_verbal", grade=None, area="사회", area_detail="경제·경영",
                item_type="일치부합", item_format="일반", discourse="평서문", topic="합성 주제")
    path.write_text(json.dumps(data, ensure_ascii=False))
    result = invoke("brief-check", path)
    assert result.returncode == 1
    assert json.loads(result.stdout)["generation_executed"] is False
    data["grade"] = 5
    path.write_text(json.dumps(data, ensure_ascii=False))
    result = invoke("brief-check", path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["valid"] is True


def test_track_search_missing_index_does_not_create_database(tmp_path):
    query = tmp_path / "query.json"
    query.write_text(json.dumps({"track": "psat_verbal", "grade": 5}))
    absent = tmp_path / "absent" / "index.sqlite"
    result = invoke("ref-search", query, "--index", absent)
    assert result.returncode == 2
    assert not absent.exists()
    assert not absent.parent.exists()


def test_track_import_failure_and_existing_destination_preserve_data(tmp_path):
    records = tmp_path / "invalid.jsonl"
    records.write_text('{"id":"synthetic-without-provenance"}\n')
    output = tmp_path / "new.sqlite"
    result = invoke("ref-build", records, "--out", output)
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["errors"]
    assert not output.exists()
    output.write_bytes(b"preserve existing corpus")
    result = invoke("ref-build", records, "--out", output)
    assert result.returncode == 2
    assert output.read_bytes() == b"preserve existing corpus"


def local_cli(monkeypatch, capsys, *arguments):
    """Exercise the real top-level parser and dispatch without a subprocess."""
    from haean.cli import main
    monkeypatch.setattr(sys, "argv", ["haean-tool", "track", *map(str, arguments)])
    main()
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("revisions,explicit_calls,expected_calls", [(0, None, 5), (2, None, 11), (0, 6, 6)])
def test_staged_attach_and_generate_use_actual_cli_dispatch(tmp_path, monkeypatch, capsys, draft,
                                                           revisions, explicit_calls, expected_calls):
    from test_staged_authoring import Provider, prepared, track_brief, reference_index
    from haean import codex_runtime, execution_provenance
    from haean.pipeline import save

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(execution_provenance, "runtime_sources", lambda: {"synthetic.py": b"fixed CLI runtime"})
    brief = track_brief()
    run = prepared(tmp_path, brief, old_type="기존 조건 유형")
    brief_path, mapping_path = tmp_path / "track.json", tmp_path / "mapping.json"
    save(brief_path, brief.model_dump())
    save(mapping_path, {"legacy_item_type": "기존 조건 유형", "track_item_type": brief.item_type,
                        "rationale": "합성 사례의 조건 방향 판단 대응"})
    index, _ = reference_index(tmp_path)
    provider = Provider(draft)
    constructions = []
    def make_provider(model, **kwargs):
        constructions.append({"model": model, **kwargs})
        provider.model = model
        return provider
    monkeypatch.setattr(codex_runtime, "CodexProvider", make_provider)

    attached = local_cli(monkeypatch, capsys, "attach", run, brief_path, "--index", index,
                         "--type-mapping", mapping_path)
    assert attached["generation_executed"] is False and constructions == []
    assert Path(attached["staged"]) == run / "staged"
    options = ["--max-calls", explicit_calls] if explicit_calls is not None else []
    generated = local_cli(monkeypatch, capsys, "generate", run, "--model", "synthetic-cli-model",
                          "--max-revisions", revisions, "--timeout", 42, *options)
    assert constructions == [{"model": "synthetic-cli-model", "max_calls": expected_calls,
                              "timeout": 42, "trace_dir": run / "codex-traces"}]
    assert generated["state"] == "awaiting_human_review" and generated["human_approved"] is False
    assert generated["draft_format"] == "haean.models.Draft" and generated["native_layout_verified"] is False
    assert generated["items"] == brief.ids
    assert [call[0] for call in provider.calls] == ["material", "design", "generate", "blind", "editor"]
    assert not (tmp_path / "data/corpus.sqlite").exists()


@pytest.mark.parametrize("options", [["--max-calls", "4"], ["--timeout", "0"], ["--max-revisions", "4"]])
def test_staged_cli_invalid_budget_or_parser_option_does_not_create_provider(tmp_path, monkeypatch, capsys, options):
    from test_staged_authoring import prepared
    from haean import codex_runtime
    run = prepared(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("invalid options started Codex")
    monkeypatch.setattr(codex_runtime, "CodexProvider", forbidden)
    with pytest.raises(SystemExit) as error:
        local_cli(monkeypatch, capsys, "generate", run, *options)
    assert error.value.code == 2
    assert not (run / "codex-traces").exists() and not (run / "candidate.json").exists()
    assert capsys.readouterr().err


def test_staged_cli_requires_attachment_and_rejects_reading_before_provider(tmp_path, monkeypatch, capsys):
    from test_staged_authoring import prepared
    from haean import codex_runtime
    from haean.pipeline import save
    run = prepared(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("unsupported run started Codex")
    monkeypatch.setattr(codex_runtime, "CodexProvider", forbidden)
    with pytest.raises(SystemExit) as error:
        local_cli(monkeypatch, capsys, "generate", run)
    assert error.value.code == 2 and "attach" in capsys.readouterr().err
    path = tmp_path / "reading.json"
    save(path, {"track": "leet_reading", "area": "인문", "item_type": "추론", "item_format": "일반", "discourse": "평서문"})
    with pytest.raises(SystemExit) as error:
        local_cli(monkeypatch, capsys, "attach", run, path)
    assert error.value.code == 2 and "언어이해" in capsys.readouterr().err
    assert not (run / "staged").exists()
