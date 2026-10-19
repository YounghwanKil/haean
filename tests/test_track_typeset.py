"""Synthetic native-model conversion tests; no templates, corpus, or model calls."""
import builtins
import copy
import hashlib
import importlib
import json
import subprocess
import sys

import pytest

from haean.track_typeset import TrackTypesetError, to_manuscript
from haean.tracks.core.model import Draft
from haean.tracks.core.track import Brief


def item(ident="SYNTHETIC-1", **changes):
    data = {
        "id": ident, "area": "인문", "item_type": "추론", "item_format": "일반", "discourse": "평서문",
        "difficulty": "상", "topic": "합성 주제", "stem": "합성 발문  0.50%·5ㆍ7~9",
        "passage": [{"kind": "문단", "text": "합성  문단: 01, 2.50 kg, ~와 ～, <b>글</b>"}],
        "options": [{"text": f"합성 선지 {i}  0.{i}0"} for i in range(1, 6)], "answer": 2,
        "solution": {"topic": "합성 제재", "level": 1, "comment_title": "합성 논평",
                     "comment": ["합성 논평 첫 문단", "합성 논평 둘째 문단"],
                     "option_judgments": [{"mark": "○" if i == 2 else "×", "explanation": [f"합성 설명 {i}", "합성 보충"],
                                           "trap": "PRIVATE_TRAP"} for i in range(1, 6)]},
        "design": {"core_judgment": "PRIVATE_DESIGN", "answer_condition": "PRIVATE_CONDITION",
                   "distractor_paths": ["PRIVATE_DISTRACTOR"], "bypass_check": "PRIVATE_BYPASS", "reference_use": "PRIVATE_USE"},
        "essential_conditions": ["PRIVATE_ESSENTIAL"], "reference_ids": ["PRIVATE_REFERENCE"],
        "calculations": [{"label": "PRIVATE_CALC", "expression": "1+1", "expected": "2", "unit": "kg", "evidence": "PRIVATE_EVIDENCE"}],
    }
    data.update(changes)
    return data


def packet(items=None, *, track="psat_data", grade=5, is_set=False, sets=None, ids=None):
    items = items or [item()]
    reading, reasoning = track == "leet_reading", track == "leet_reasoning"
    b = Brief(track=track, grade=grade, area="기타" if track == "psat_data" else "인문",
              item_type="혼합" if is_set else ("언어 추리" if reasoning else "단순확인" if track == "psat_data" else "추론"),
              item_format="혼합" if is_set else "일반", discourse="평서문", count=len(items), set=is_set, ids=ids or [])
    if reading and not is_set:
        b = b.model_copy(update={"item_type": "정보 확인·재구성"})
    d = Draft.model_validate({"design_summary": "PRIVATE_SUMMARY", "items": items, "sets": sets or []})
    return d, b


def convert_error(draft, brief, code, **kwargs):
    with pytest.raises(TrackTypesetError) as error:
        to_manuscript(draft, brief, **kwargs)
    assert error.value.code == code
    assert error.value.path


def test_preserves_text_order_ids_numbers_and_explanation_paragraphs_without_mutation():
    draft, brief = packet([item("Z-9"), item("A-1")], ids=["Z-9", "A-1"])
    before = copy.deepcopy(draft.model_dump())
    result = to_manuscript(draft, brief, title="합성 시험명  2026")
    assert result["profile"] == "psat5_data"
    assert result["시험명"] == "합성 시험명  2026"
    assert [q["id"] for q in result["문항"]] == ["Z-9", "A-1"]
    for source, actual in zip(draft.items, result["문항"]):
        assert actual["발문"] == source.stem
        assert actual["지문"] == [{"문단": source.passage[0].text}]
        assert actual["선지"] == [c.text for c in source.options]
        assert actual["해설"]["난이도"] == 1  # Never derive stars from Item.difficulty=상.
        assert actual["해설"]["논평"]["글"] == source.solution.comment
        assert [j["설명"] for j in actual["해설"]["정오판단"]] == [j.explanation for j in source.solution.option_judgments]
    assert draft.model_dump() == before
    assert to_manuscript(draft, brief, title="합성 시험명  2026") == result
    result["문항"][0]["해설"]["정오판단"][0]["설명"].append("출력에만 추가")
    assert draft.model_dump() == before
    assert "PRIVATE_" not in json.dumps(result)


def test_student_only_excludes_answers_explanations_and_all_production_metadata():
    draft, brief = packet()
    result = to_manuscript(draft, brief, include_solutions=False)
    q = result["문항"][0]
    assert set(q) == {"id", "발문", "선지", "지문"}
    assert "PRIVATE_" not in json.dumps(result)
    assert "해설" not in q and "정답" not in q
    assert draft.items[0].answer == 2 and draft.items[0].solution.comment


@pytest.mark.parametrize("track,grade,area,typ,profile", [
    ("leet_reasoning", None, "인문", "언어 추리", "leet_reasoning"),
    ("psat_verbal", 5, "인문", "추론", "psat5_language"),
    ("psat_data", 5, "기타", "단순확인", "psat5_data"),
    ("psat_situation", 5, "생활·일상(가상)", "규범 판단", "psat5_situation"),
])
def test_each_standalone_profile_uses_explicit_grade_and_preserves_metadata(track, grade, area, typ, profile):
    draft, _ = packet([item(area=area, item_type=typ)])
    brief = Brief(track=track, grade=grade, area=area, item_type=typ, item_format="일반", discourse="평서문")
    out = to_manuscript(draft, brief)
    assert out["profile"] == profile
    assert out["문항"][0]["해설"]["내용영역"] == area
    assert out["문항"][0]["해설"]["문항유형"] == typ


def table(**changes):
    value = {"kind": "표", "rows": [
        [{"text": "합성 머리 01", "colspan": 2}, {"text": "0.50%", "rowspan": 2}],
        [{"text": "2.500"}, {"text": ""}]],
        "title": "합성 표", "unit": "(단위: 천 원)", "note": "※ 합성 주석  0", "header_row": False,
        "col_widths": [1, 2, 3], "align": ["L", "C", "R"]}
    value.update(changes)
    return value


@pytest.mark.parametrize("header", [False, True])
def test_table_preserves_spans_explicit_header_units_widths_alignment_and_empty_cell(header):
    source = table(header_row=header)
    draft, brief = packet([item(passage=[source])])
    out = to_manuscript(draft, brief)["문항"][0]["지문"][0]
    assert out == {"표": [[{"글": "합성 머리 01", "가로": 2}, {"글": "0.50%", "세로": 2}], ["2.500", ""]],
                   "머리행": header, "제목": source["title"], "단위": source["unit"], "주석": source["note"],
                   "열폭": [1, 2, 3], "정렬": ["L", "C", "R"]}


@pytest.mark.parametrize("rows", [
    [[{"text": "a"}, {"text": "b"}], [{"text": "c"}]],  # hole
    [[{"text": "a", "rowspan": 3}]],  # row overflow
    [[{"text": "a"}, {"text": "b", "rowspan": 2}], [{"text": "c", "colspan": 2}]],  # overlap
    [[{"text": "a"}], [{"text": "b"}, {"text": "c"}]],  # column overflow
    [[]],
])
def test_invalid_table_grids_fail_instead_of_clipping_or_filling(rows):
    draft, brief = packet([item(passage=[table(rows=rows, col_widths=[], align=[])])])
    convert_error(draft, brief, "TABLE_GRID")


@pytest.mark.parametrize("changes,code", [
    ({"col_widths": [1]}, "TABLE_WIDTHS"), ({"col_widths": [1, 0, 3]}, "TABLE_WIDTHS"),
    ({"col_widths": [1, float("nan"), 3]}, "TABLE_WIDTHS"), ({"align": ["L"]}, "TABLE_ALIGN"),
])
def test_table_metadata_cannot_be_silently_ignored(changes, code):
    draft, brief = packet([item(passage=[table(**changes)])])
    convert_error(draft, brief, code)


def test_reasoning_table_styles_and_unconsumed_fields_fail():
    draft, brief = packet([item(passage=[table()])], track="leet_reasoning", grade=None)
    convert_error(draft, brief, "TABLE_STYLE_UNSUPPORTED")
    draft, brief = packet([item(passage=[{"kind": "문단", "text": "합성", "title": "사라질 제목"}])])
    convert_error(draft, brief, "UNCONSUMED_FIELD")


@pytest.mark.parametrize("track,grade,block", [
    ("leet_reasoning", None, {"kind": "주석", "text": "합성"}),
    ("leet_reasoning", None, {"kind": "상자", "title": "합성", "children": [{"kind": "문단", "text": "합성"}]}),
    ("psat_data", 5, {"kind": "조건", "label": "1", "text": "합성"}),
])
def test_profile_specific_unsupported_blocks_fail(track, grade, block):
    draft, brief = packet([item(passage=[block])], track=track, grade=grade)
    convert_error(draft, brief, "BLOCK_UNSUPPORTED")


def test_psat_box_and_label_structure_are_kept():
    blocks = [{"kind": "상자", "title": "합성 상황", "children": [
        {"kind": "발언", "label": "갑", "text": "합성  발언"},
        {"kind": "목", "label": "가", "text": "합성 항목"},
        {"kind": "표", "rows": [[{"text": "001"}]], "header_row": False}]}]
    draft, brief = packet([item(passage=blocks)])
    assert to_manuscript(draft, brief)["문항"][0]["지문"] == [{"상자": "합성 상황", "내용": [
        {"라벨": "갑", "글": "합성  발언"}, {"목": "가", "글": "합성 항목"}, {"표": [["001"]], "머리행": False}]}]


def test_psat_shared_passage_once_own_blocks_per_item_and_set_identity():
    records = [item(ident, set_id="SET-Z", own_blocks=[{"kind": "문단", "text": "합성 고유 " + ident}])
               for ident in ("Q-9", "Q-1")]
    draft, brief = packet(records, is_set=True, ids=["Q-9", "Q-1"], sets=[{"set_id": "SET-Z", "guide": "합성  세트 안내"}])
    entry = to_manuscript(draft, brief)["문항"][0]
    assert entry["세트"]["id"] == "SET-Z"
    assert entry["세트"]["안내"] == "합성  세트 안내"
    assert entry["세트"]["지문"] == [{"문단": draft.items[0].passage[0].text}]
    assert [q["id"] for q in entry["문항"]] == ["Q-9", "Q-1"]
    assert [q["지문"] for q in entry["문항"]] == [[{"문단": "합성 고유 Q-9"}], [{"문단": "합성 고유 Q-1"}]]


def test_shared_passages_with_identical_text_but_different_table_structure_fail():
    records = [item("Q1", set_id="S", passage=[table(header_row=False)]),
               item("Q2", set_id="S", passage=[table(header_row=True)])]
    draft, brief = packet(records, is_set=True)
    convert_error(draft, brief, "SHARED_PASSAGE")


def test_reading_three_item_set_keeps_summary_but_student_version_drops_it():
    records = [item(f"Q{i}", set_id="S", item_type="정보 확인·재구성") for i in range(3)]
    draft, brief = packet(records, track="leet_reading", grade=None, is_set=True,
                          sets=[{"set_id": "S", "summary": ["합성 총평 첫째", "합성 총평 둘째"]}])
    out = to_manuscript(draft, brief)
    assert out["profile"] == "leet_verbal"
    assert out["문항"][0]["세트"]["해설"]["지문총평"] == draft.sets[0].summary
    assert "해설" not in to_manuscript(draft, brief, include_solutions=False)["문항"][0]["세트"]
    draft.items[1].solution.level = 2
    convert_error(draft, brief, "SET_SOLUTION")


def test_psat_summary_cannot_be_discarded_by_the_solution_renderer():
    draft, brief = packet([item("Q1", set_id="S"), item("Q2", set_id="S")], is_set=True,
                          sets=[{"set_id": "S", "summary": ["합성 총평"]}])
    convert_error(draft, brief, "SET_SUMMARY_UNSUPPORTED")
    assert to_manuscript(draft, brief, include_solutions=False)


@pytest.mark.parametrize("track,grade,is_set,count,code", [
    ("psat_data", 7, False, 1, "PROFILE_UNSUPPORTED"),
    ("psat_data", None, False, 1, "PROFILE_UNSUPPORTED"),
    ("leet_reasoning", None, True, 2, "BRIEF_INVALID"),
    ("leet_reading", None, False, 1, "BRIEF_INVALID"),
])
def test_unsupported_profiles_and_set_policies_are_explicit(track, grade, is_set, count, code):
    records = [item(f"Q{i}", set_id="S" if is_set else "") for i in range(count)]
    draft, brief = packet(records, track=track, grade=grade, is_set=is_set)
    convert_error(draft, brief, code)


def test_duplicate_identifiers_brief_order_and_unused_set_info_fail():
    draft, brief = packet([item("Q"), item("Q")])
    convert_error(draft, brief, "IDENTIFIER")
    draft, brief = packet([item("Q2"), item("Q1")], ids=["Q1", "Q2"])
    convert_error(draft, brief, "ITEM_ORDER")
    draft, brief = packet(sets=[{"set_id": "UNUSED"}])
    convert_error(draft, brief, "SET_INFO")


def test_figures_and_image_maps_are_rejected_without_file_access():
    figure = {"id": "F", "placement": "option_1", "kind": "argument", "title": "합성 그림", "x_label": "", "y_label": "",
              "categories": [], "series": [], "nodes": [{"id": "N", "label": "합성 노드"}], "edges": [], "note": "PRIVATE_NOTE"}
    draft, brief = packet([item(figures=[figure], options=[{"text": f"소실하면 안 되는 글 {i}", "figure_id": "F"} for i in range(5)])])
    convert_error(draft, brief, "FIGURE_UNSUPPORTED")
    draft, brief = packet()
    convert_error(draft, brief, "FIGURE_UNSUPPORTED", figure_paths={("SYNTHETIC-1", "F"): "/does/not/exist.png"})


def test_statement_and_option_judgments_keep_distinct_targets_and_private_traps_out():
    source = item(statements=[{"text": "합성 명제 A"}, {"text": "합성 명제 B"}])
    source["solution"]["statement_judgments"] = [{"mark": "○", "explanation": ["합성 명제 설명"], "trap": "PRIVATE_TRAP"}] * 2
    draft, brief = packet([source])
    out = to_manuscript(draft, brief)["문항"][0]
    assert len(out["해설"]["정오판단"]) == 2 and len(out["해설"]["선지판단"]) == 5
    assert out["보기"] == [s["text"] for s in source["statements"]]
    assert "PRIVATE_" not in json.dumps(out)


def test_material_bogi_uses_option_judgments_and_reading_single_bogi_is_not_misclassified():
    draft, brief = packet([item(statements=[{"text": "합성 사례"}])])
    sol = to_manuscript(draft, brief)["문항"][0]["해설"]
    assert sol["정오판단"] == [] and len(sol["선지판단"]) == 5
    records = [item(f"Q{i}", set_id="S", statements=[{"text": "합성 인용"}]) for i in range(3)]
    draft, brief = packet(records, track="leet_reading", grade=None, is_set=True)
    sol = to_manuscript(draft, brief)["문항"][0]["문항"][0]["해설"]
    assert len(sol["정오판단"]) == 5 and "선지판단" not in sol


def test_incomplete_solution_is_not_silently_trimmed_but_student_conversion_remains_possible():
    source = item()
    source["solution"]["comment"] = []
    draft, brief = packet([source])
    convert_error(draft, brief, "COMMENT_EMPTY")
    assert to_manuscript(draft, brief, include_solutions=False)


def test_no_implicit_legacy_or_dict_conversion_and_no_file_network_subprocess_side_effects(monkeypatch):
    draft, brief = packet()
    convert_error(draft.model_dump(), brief, "MODEL_TYPE")

    def forbidden(*args, **kwargs):
        raise AssertionError("conversion performed an external operation")

    # Import all registry dependencies before disallowing application I/O.
    importlib.import_module("haean.tracks.psat_data")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    import socket
    monkeypatch.setattr(socket, "socket", forbidden)
    assert to_manuscript(draft, brief)


def test_module_import_does_not_require_optional_typesetter_or_matplotlib():
    code = """
import importlib.abc, sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'haean_typeset', 'matplotlib', 'PIL'}:
            raise AssertionError('optional dependency imported: ' + fullname)
sys.meta_path.insert(0, BlockOptional())
import haean.track_typeset
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_real_cli_writes_preserved_manuscript_and_student_projection_without_mutating_inputs(tmp_path):
    draft, brief = packet([item(passage=[table(), {"kind": "문단", "text": "합성  보충 001.50 kg"}])])
    brief_path, draft_path = tmp_path / "brief.json", tmp_path / "draft.json"
    brief_path.write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    draft_path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
    before = {p: p.read_bytes() for p in (brief_path, draft_path)}
    base = [sys.executable, "-m", "haean.cli", "track", "manuscript", str(brief_path), str(draft_path)]
    for student in (False, True):
        out = tmp_path / ("student.json" if student else "instructor.json")
        command = base + ["--out", str(out), "--title", "합성 CLI 시험명"] + (["--student-only"] if student else [])
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout)
        assert receipt["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
        assert receipt["brief_sha256"] == hashlib.sha256(before[brief_path]).hexdigest()
        assert receipt["draft_sha256"] == hashlib.sha256(before[draft_path]).hexdigest()
        assert receipt["student_only"] is student
        assert receipt["native_layout_verified"] is False and receipt["human_approved"] is False
        manuscript = json.loads(out.read_text())
        q = manuscript["문항"][0]
        assert manuscript["시험명"] == "합성 CLI 시험명"
        assert q["id"] == draft.items[0].id and q["발문"] == draft.items[0].stem
        assert q["선지"] == [c.text for c in draft.items[0].options]
        assert q["지문"][0]["머리행"] is False
        assert q["지문"][0]["표"][0][1] == {"글": "0.50%", "세로": 2}
        assert q["지문"][0]["단위"] == "(단위: 천 원)"
        assert q["지문"][1] == {"문단": "합성  보충 001.50 kg"}
        assert ("정답" in q) is (not student) and ("해설" in q) is (not student)
        if not student:
            assert q["정답"] == 2
            assert q["해설"]["논평"]["글"] == draft.items[0].solution.comment
        assert "PRIVATE_" not in json.dumps(manuscript)
        assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize("target", ["existing", "brief", "draft"])
def test_real_cli_preserves_existing_out_and_input_aliases(tmp_path, target):
    draft, brief = packet()
    brief_path, draft_path, existing = tmp_path / "brief.json", tmp_path / "draft.json", tmp_path / "existing.json"
    brief_path.write_text(brief.model_dump_json(), encoding="utf-8")
    draft_path.write_text(draft.model_dump_json(), encoding="utf-8")
    existing.write_bytes(b"existing manuscript must remain byte-identical\n")
    paths = {"existing": existing, "brief": brief_path, "draft": draft_path}
    before = {p: p.read_bytes() for p in paths.values()}
    result = subprocess.run([sys.executable, "-m", "haean.cli", "track", "manuscript",
                             str(brief_path), str(draft_path), "--out", str(paths[target]), "--student-only"],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "덮어쓰지" in result.stderr + result.stdout
    assert {p: p.read_bytes() for p in paths.values()} == before
