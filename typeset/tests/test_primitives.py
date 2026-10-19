"""Self-contained synthetic checks for reusable typesetting primitives."""
from haean_typeset import api
from haean_typeset.core import latex2eqn
from haean_typeset.core.headeredit import HeaderEditor


def test_wrap_measure_preserve_synthetic_input():
    item = {"id": "SYNTHETIC", "발문": "옳은 것은?",
            "지문": [{"문단": "서로 다른 항목을 차례대로 비교한다. " * 9}],
            "선지": ["가", "나", "다", "라", "마"]}
    before = item["지문"][0]["문단"]
    wrapped, _ = api.wrap(item, "leet_reasoning")
    assert item["지문"][0]["문단"] == before and wrapped is not item
    measure = api.measure(item, "leet_reasoning", number=3, total=40)
    assert measure["height_pt"] > 0 and measure["lines"] > 1
    assert measure["verdict"] in {"ok", "tight", "over"}


def test_equation_numeric_content_and_unknown_commands():
    assert latex2eqn.roundtrip(r"\frac{12}{34} + 56") is None
    unknown = []
    latex2eqn.conv(r"\syntheticunknown{12}", unknown)
    assert unknown
    assert not hasattr(latex2eqn, "_survey")


def test_character_style_variant_keeps_original():
    header = ('<hh:charProperties itemCnt="1"><hh:charPr id="0" height="1100">'
              '<hh:underline type="NONE"/></hh:charPr></hh:charProperties>')
    editor = HeaderEditor(header)
    variant = editor.variant(0, "u")
    assert variant != 0 and editor.variant(0, "u") == variant
    assert '<hh:underline type="NONE"/>' in editor.header
    assert '<hh:underline type="BOTTOM"/>' in editor.header
