"""CLI routing checks use synthetic specifications only."""
import json
import os
from pathlib import Path
import subprocess
import sys


def invoke(*arguments):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    return subprocess.run([sys.executable, "-m", "haean.cli", "track", *map(str, arguments)],
                          env=env, text=True, capture_output=True)


def test_track_list_reports_stage_and_all_products():
    result = invoke("list")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["integration_stage"] == "foundation"
    assert data["generation_integrated"] is False
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
