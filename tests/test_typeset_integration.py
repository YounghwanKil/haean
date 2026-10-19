"""Synthetic HWPX integration; no private template, exam, font or network fixture."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import copy
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET

import pytest

from haean_typeset import api
from haean_typeset.core import api as core_api
from haean_typeset.profiles.leet_reasoning import ids as I
from haean_typeset.profiles.leet_reasoning import layout as L


def manuscript():
    return {"시험명": "합성 구조 검사", "문항": [{
        "id": "SYNTHETIC-001", "발문": "옳은 것은?",
        "지문": [{"문단": "가 항목은 <u>12</u>이고 나 항목은 34이다."},
                 {"표": [["항목", "수량"], ["가", "12"], ["나", "34"]], "단위": "개"}],
        "선지": ["12", "23", "34", "45", "56"], "정답": 3,
    }]}


def synthetic_template(path, title=True):
    """Minimal generated ZIP for structural engine tests, not a deliverable template."""
    chars = []
    for number in range(45):
        height = I.EXPECT.get(("charPr", number), ("height", 1100))[1]
        chars.append(f'<hh:charPr id="{number}" height="{height}"><hh:spacing hangul="0" latin="0"/>'
                     '<hh:underline type="NONE"/></hh:charPr>')
    paras = []
    for number in range(65):
        attr, value = I.EXPECT.get(("paraPr", number), ("intent", 0))
        paras.append(f'<hh:paraPr id="{number}"><hc:{attr} value="{value}"/></hh:paraPr>')
    namespaces = 'xmlns:hh="urn:synthetic:hh" xmlns:hc="urn:synthetic:hc" xmlns:hp="urn:synthetic:hp"'
    header = (f'<hh:head {namespaces}><hh:charProperties itemCnt="45">' + "".join(chars)
              + '</hh:charProperties><hh:paraProperties itemCnt="65">' + "".join(paras)
              + '</hh:paraProperties></hh:head>')
    name = L.TITLE_PLACEHOLDER if title else "합성 머리말"
    section = (f'<hs:sec xmlns:hs="urn:synthetic:hs" {namespaces}>'
               f'<hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>{name}</hp:t>'
               '<hp:t>40문항</hp:t></hp:run></hp:p>'
               '<hp:p paraPrIDRef="2" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
               '<hp:run charPrIDRef="6"><hp:t>20</hp:t></hp:run></hp:p>'
               '<hp:p paraPrIDRef="7" styleIDRef="2"><hp:run charPrIDRef="0">'
               '<hp:t>SYNTHETIC-OLD-BODY</hp:t></hp:run></hp:p></hs:sec>')
    with zipfile.ZipFile(path, "x") as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/content.hpf", '<opf:package xmlns:opf="urn:synthetic:opf"><opf:manifest/></opf:package>')
        archive.writestr("Contents/section0.xml", section)
        archive.writestr("Preview/PrvText.txt", "SYNTHETIC-OLD-BODY")
    return path


def test_synthetic_template_roundtrip_and_input_provenance(tmp_path):
    template = synthetic_template(tmp_path / "private.hwpx")
    before = template.read_bytes()
    exam = manuscript()
    original = copy.deepcopy(exam)
    output = tmp_path / "out.hwpx"
    result = api.typeset(exam, output, template_path=template, strict=True, solution=False)
    with zipfile.ZipFile(output) as archive:
        section = archive.read("Contents/section0.xml").decode()
        parsed = ET.fromstring(section)
        text = "".join(parsed.itertext())
        assert "12" in text and "34" in text and "개" in text
        assert "SYNTHETIC-OLD-BODY" not in text
        assert "SYNTHETIC-OLD-BODY" not in archive.read("Preview/PrvText.txt").decode()
        assert "<hp:tbl" in section
    assert exam == original and template.read_bytes() == before
    assert result["templates"] == [{"path": str(template.resolve()), "sha256": hashlib.sha256(before).hexdigest()}]
    assert len(result["input_sha256"]) == 64 and result["pages_are_estimated"]
    assert result["native_hancom_verified"] is False and result["delivery_ready"] is False


def test_late_strict_diagnostic_leaves_no_partial_output(tmp_path):
    template = synthetic_template(tmp_path / "private.hwpx", title=False)
    output = tmp_path / "out.hwpx"
    with pytest.raises(api.StrictError) as caught:
        api.typeset(manuscript(), output, template_path=template, strict=True, solution=False)
    assert "TEMPLATE_TITLE" in {d["code"] for d in caught.value.result["diagnostics"]}
    assert caught.value.result["path"] is None and caught.value.result["solution_path"] is None
    assert not output.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["private.hwpx"]


@pytest.mark.parametrize("same_as_template", [False, True])
def test_existing_output_and_original_are_preserved(tmp_path, same_as_template):
    template = synthetic_template(tmp_path / "private.hwpx")
    output = template if same_as_template else tmp_path / "out.hwpx"
    if not same_as_template:
        output.write_bytes(b"existing output")
    original = output.read_bytes()
    with pytest.raises((FileExistsError, ValueError)):
        api.typeset(manuscript(), output, template_path=template, solution=False)
    assert output.read_bytes() == original


def test_missing_template_and_solution_template_are_explicit(tmp_path):
    with pytest.raises(api.TemplateError, match="template_path"):
        api.typeset(manuscript(), tmp_path / "out.hwpx")
    template = synthetic_template(tmp_path / "private.hwpx")
    exam = manuscript()
    exam["문항"][0]["해설"] = {"제재": "합성", "난이도": 1}
    with pytest.raises(api.TemplateError) as caught:
        api.typeset(exam, tmp_path / "out.hwpx", template_path=template)
    assert caught.value.code == "SOLUTION_TEMPLATE_REQUIRED"
    assert not (tmp_path / "out.hwpx").exists()


class SyntheticFlow:
    flow = True
    name = "synthetic"
    template_path = None
    solution_profile = True
    _geo = "must not be shared"

    def typeset_exam(self, exam, out_path, **kwargs):
        assert self._geo is None
        Path(out_path).write_bytes(b"new question")
        solution = str(Path(out_path).with_name(Path(out_path).stem + "_해설.hwpx"))
        Path(solution).write_bytes(b"new solution")
        return {"path": out_path, "solution_path": solution, "items": [], "diagnostics": [], "pages": 1}


def test_publishing_pair_rolls_back_if_second_destination_appears(tmp_path, monkeypatch):
    template = synthetic_template(tmp_path / "private.hwpx")
    exam = manuscript()
    exam["문항"][0]["해설"] = {"제재": "합성", "난이도": 1}
    output = tmp_path / "out.hwpx"
    solution = tmp_path / "out_해설.hwpx"
    real_link = core_api.os.link

    def race(source, destination):
        if Path(destination) == solution:
            solution.write_bytes(b"other writer")
        return real_link(source, destination)

    monkeypatch.setattr(core_api.os, "link", race)
    with pytest.raises(FileExistsError):
        api.typeset(exam, output, profile=SyntheticFlow(), template_path=template,
                    solution_template_path=template, strict=True)
    assert not output.exists() and solution.read_bytes() == b"other writer"
    assert not list(tmp_path.glob(".haean-typeset-*"))


def test_psat_external_geometry_isolated_for_parallel_diagnostics(tmp_path, monkeypatch):
    from haean_typeset.profiles.psat_common import engine
    from haean_typeset.profiles.psat5_data import PROFILE

    class Geometry:
        def __init__(self, style, path):
            assert path is not None
            self.path = str(path)

    monkeypatch.setattr(engine, "Geometry", Geometry)
    monkeypatch.setattr(engine.PsatProfile, "validate", lambda self, *args: [{"template": self.geo().path}])
    monkeypatch.setattr(engine.PsatProfile, "measure", lambda self, *args: {"template": self.geo().path})
    monkeypatch.setattr(engine.PsatProfile, "wrap", lambda self, item, *args: (copy.deepcopy(item), [{"template": self.geo().path}]))
    paths = [tmp_path / "one.hwpx", tmp_path / "two.hwpx"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda path: api.validate({}, "psat5_data", template_path=path), paths))
    assert [r[0]["template"] for r in results] == [str(p) for p in paths]
    assert api.measure({}, "psat5_data", template_path=paths[0])["template"] == str(paths[0])
    assert api.wrap({}, "psat5_data", template_path=paths[1])[1][0]["template"] == str(paths[1])
    assert PROFILE.template_path is None and PROFILE._geo is None


def test_cli_rejects_existing_reports_before_generation(tmp_path):
    from haean_typeset.core.cli import main
    template = synthetic_template(tmp_path / "private.hwpx")
    src = tmp_path / "input.json"
    src.write_text(json.dumps(manuscript(), ensure_ascii=False))
    report = tmp_path / "out_점검.json"
    report.write_text("original report")
    with pytest.raises(SystemExit) as caught:
        main([str(src), "-o", str(tmp_path / "out.hwpx"), "--template", str(template), "--no-solution"])
    assert caught.value.code == 2
    assert report.read_text() == "original report" and not (tmp_path / "out.hwpx").exists()
