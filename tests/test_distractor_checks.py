"""Synthetic comparison examples; no original questions or conversations."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from haean.distractor_checks import check_distractors


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def packet(tmp_path, draft):
    candidate = tmp_path / "candidate.json"
    sidecar = tmp_path / "sidecar.json"
    document = draft.model_dump()
    item = document["items"][0]
    item["id"] = "SYNTHETIC-DATA-1"
    item["subject"] = "자료해석"
    item["options"][0]["text"] = "합성 비율은 기준값보다 크다."
    write_json(candidate, document)
    data = {"candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(), "checks": [{
        "item_id": item["id"], "target": "1", "statement_text": item["options"][0]["text"],
        "source_locator": "합성 자료의 분자와 분모", "misread_description": "분모를 다르게 읽음",
        "normal": {"left": "60/100", "operator": ">", "right": "1/2"},
        "misread": {"left": "60/80", "operator": ">", "right": "1/2"},
    }]}
    write_json(sidecar, data)
    return candidate, sidecar, document, data


def run(packet, *, update_candidate=False):
    candidate, sidecar, document, data = packet
    if update_candidate:
        write_json(candidate, document)
        data["candidate_sha256"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    write_json(sidecar, data)
    return check_distractors(candidate, sidecar)


def test_different_values_can_leave_truth_unchanged(packet):
    report = run(packet)
    result = report["checks"][0]
    assert result["normal"]["left_exact"] == "3/5"
    assert result["misread"]["left_exact"] == "3/4"
    assert result["normal"]["truth"] is result["misread"]["truth"] is True
    assert result["truth_changed"] is False
    assert result["normal_matches_authored_verdict"] is True
    assert report["sidecar_sha256"] == hashlib.sha256(packet[1].read_bytes()).hexdigest()
    assert "최종 정답" in report["limitations"][0]


@pytest.mark.parametrize("operator,normal_truth,misread_truth", [
    (">", False, True), (">=", True, True), ("<", False, False),
    ("<=", True, False), ("==", True, False), ("!=", False, True),
])
def test_exact_equality_boundary_and_all_comparisons(packet, operator, normal_truth, misread_truth):
    check = packet[3]["checks"][0]
    for kind in ("normal", "misread"):
        check[kind].update(operator=operator, right="0.6")
    result = run(packet)["checks"][0]
    assert result["normal"]["right_exact"] == "3/5"
    assert result["normal"]["truth"] is normal_truth
    assert result["misread"]["truth"] is misread_truth
    assert result["truth_changed"] is (normal_truth != misread_truth)


def test_two_ratio_comparison_and_authored_mismatch_are_advisory(packet):
    check = packet[3]["checks"][0]
    for kind in ("normal", "misread"):
        check[kind]["right"] = "(30 + 40)/100"
    result = run(packet)["checks"][0]
    assert result["normal"]["right_exact"] == "7/10"
    assert result["truth_changed"] is True
    assert result["authored_verdict"] == "참"
    assert result["authored_verdict_comparison"] == "mismatch"
    assert result["normal_matches_authored_verdict"] is False


@pytest.mark.parametrize("normal,misread,boundary,exact", [
    ("1.0000000000000001", "1", "1", "10000000000000001/10000000000000000"),
    ("1e-400", "0", "0", "1/" + "1" + "0" * 400),
])
def test_decimal_source_precision_can_change_option_truth(packet, normal, misread, boundary, exact):
    row = packet[3]["checks"][0]
    row["normal"].update(left=normal, right=boundary)
    row["misread"].update(left=misread, right=boundary)
    result = run(packet)["checks"][0]
    assert result["normal"]["left_exact"] == exact
    assert result["normal"]["truth"] is True
    assert result["misread"]["truth"] is False
    assert result["truth_changed"] is True


def test_extreme_decimal_exponent_rejected_before_fraction_allocation(packet):
    packet[3]["checks"][0]["normal"]["left"] = "1e-999999999999999999"
    with pytest.raises(ValueError, match="Exponent magnitude too large"):
        run(packet)


def test_indeterminate_authored_verdict_remains_non_boolean(packet):
    packet[2]["items"][0]["judgments"][0]["verdict"] = "판단불가"
    result = run(packet, update_candidate=True)["checks"][0]
    assert result["normal"]["truth"] is True
    assert result["authored_truth"] is None
    assert result["normal_matches_authored_verdict"] is None
    assert result["authored_verdict_comparison"] == "not_boolean"


@pytest.mark.parametrize("case", ["stale_sha", "unknown_item", "duplicate_item", "unknown_target",
                                 "duplicate_target", "wrong_option_text"])
def test_binding_errors_reject_instead_of_producing_comparisons(packet, case):
    item = packet[2]["items"][0]
    row = packet[3]["checks"][0]
    if case == "stale_sha":
        packet[0].write_bytes(packet[0].read_bytes() + b"\n")
    elif case == "unknown_item":
        row["item_id"] = "MISSING"
    elif case == "duplicate_item":
        packet[2]["items"].append(item.copy())
    elif case == "unknown_target":
        row["target"] = "missing"
    elif case == "duplicate_target":
        item["judgments"].append(item["judgments"][0].copy())
    else:
        row["statement_text"] = item["options"][1]["text"]
    with pytest.raises(ValueError):
        run(packet, update_candidate=case in {"duplicate_item", "duplicate_target"})


@pytest.mark.parametrize("label,expected", [("ㄱ. ", "explicit_label"), ("", "declared_only"),
                                           ("ㄴ. ", None)])
def test_statement_text_and_explicit_label_binding(packet, label, expected):
    item = packet[2]["items"][0]
    text = label + "합성 수치가 기준보다 크다."
    item["statements"] = [text]
    item["judgments"].append({**item["judgments"][0], "target": "ㄱ"})
    packet[3]["checks"][0].update(target="ㄱ", statement_text=text)
    if expected is None:
        with pytest.raises(ValueError, match="statement label"):
            run(packet, update_candidate=True)
    else:
        binding = run(packet, update_candidate=True)["checks"][0]["statement_binding"]
        assert binding == {"field": "statements", "index": 0, "target_link": expected}


@pytest.mark.parametrize("field,value", [("left", "1/0"), ("right", "2**3"),
                                       ("left", "1+"), ("operator", "is"), ("left", True)])
def test_expression_or_operator_error_rejects_entire_sidecar(packet, field, value):
    packet[3]["checks"][0]["misread"][field] = value
    with pytest.raises(ValueError):
        run(packet)


@pytest.mark.parametrize("raw", ["null", "{", '{"checks": [], "checks": []}', '{"checks": NaN}'])
def test_invalid_json_sidecar_is_rejected(packet, raw):
    packet[1].write_text(raw)
    with pytest.raises(ValueError):
        check_distractors(packet[0], packet[1])


def test_cli_outputs_json_and_preserves_all_inputs_on_success_and_error(packet):
    folder = packet[0].parent
    (folder / "status.json").write_text('{"state":"unchanged"}')
    script = Path(__file__).resolve().parents[1] / "scripts" / "haean-tool"
    command = [str(script), "--db", str(folder / "unused.sqlite"), "distractor-check",
               str(packet[0]), str(packet[1])]
    for invalid in (False, True):
        if invalid:
            packet[3]["checks"][0]["misread"]["left"] = "1/0"
            write_json(packet[1], packet[3])
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        result = subprocess.run(command, capture_output=True, text=True)
        if invalid:
            assert result.returncode == 2
            assert not result.stdout
            assert "invalid arithmetic expression" in result.stderr
        else:
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["checks"][0]["truth_changed"] is False
            assert not result.stderr
        assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
