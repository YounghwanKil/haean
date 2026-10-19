"""Synthetic-only regression profiles: no source exams, labels or private JSON."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from haean.composition.engines.leet_reasoning import Engine as LeetEngine
from haean.composition.engines.psat_verbal import Engine as VerbalEngine


COMBO = "ㄱㄴㄷ 합답형"
DIAGRAM = "논증 구조 도식 선택"
FIVE = "5지 진술 선택형"


def quota(n, lo=0, hi=40):
    return [n, [lo, hi]]


def patterns():
    return {
        **{p: ["ㄱ", "ㄴ", "ㄷ", "ㄱㄴ", "ㄱㄷ"] for p in ("P1", "P2", "P3")},
        "ratio_default": {"P1": 0.3, "P2": 0.4, "P3": 0.3},
        "ratio_range": {p: [0, 1] for p in ("P1", "P2", "P3")},
        "max_consecutive_same": 40,
    }


def content_profile(areas, tag):
    materials = [
        {"id": f"synthetic-{i:02}", "year": 1, "slot": i, "area": area,
         "cell": f"{area}|synthetic|1", "subdomain": "합성 하위영역",
         "material": f"합성 소재 {tag}-{i}", "discriminator": "합성 판단"}
        for i, area in enumerate(areas, 1)
    ]
    source = {f"합성 원천 {tag}": [1, 1.0]}
    rules = {
        "meta": {"version": f"content-{tag}"}, "cells": {}, "m20_materials": materials,
        "areas": {area: {
            "source": source,
            "subdomain_dist_2019plus": {"합성 하위영역": [1, 1.0]},
            "subdomain_dist_all": {"합성 하위영역": [1, 1.0]},
            "adjacency_2019plus": {"same_group_rate": 1.0, "max_group_run": 40},
            "adjacency_all": {"same_group_rate": 1.0, "max_group_run": 40},
        } for area in areas},
    }
    config = {
        "principles": [f"합성 프로필 {tag}"],
        "subdomain_groups": {area: {f"그룹 {tag}": ["합성 하위영역"]} for area in areas},
        "group_by_principle_hint": {}, "judgment_frames": {},
        "adjacency": {"max_same_group_consecutive": 40, "hard_max_group_run": 40,
                      "material_rule": "합성 소재 배정", "separate_pairs_note": "합성 메모"},
        "fictional": {"allowed_cells_prefix": [], "max_per_set_outside_logic": 0, "note": "합성"},
        "group_sources": {area: {"*": [f"합성 원천 {tag}"]} for area in areas},
        "reference_selection": {"design_refs": {"same_cell": 2, "role": "합성 참고"},
                                "writing_refs": {"same_narration_or_organization": 2}},
        "discriminator_rule": {"rule": f"합성 조건 {tag}"},
        "source_memo_schema": {"fields": ["합성 출처"]},
        "ai_overuse_blacklist": {"strategy": "합성 검사"},
        "approval": {"status": "synthetic-only"}, "set_rule": {"rule": "공통 합성 소재"},
    }
    return rules, config


def leet_profile(tag="A"):
    areas = ["규범", "인문", "사회", "논리학·수학", "과학기술"]
    blocks = [(1, 12), (13, 24), (25, 30), (31, 34), (35, 40)]
    language, analysis, model = "언어 추리", "논증 분석", "모형 추리"
    types = [language, analysis, model]
    assigned_types = [language, analysis, language, model, language]
    codes = {t: i for i, t in enumerate(types, 1)}
    fq = {
        "meta": {"version": f"format-{tag}"},
        "codes": {"area": {a: i for i, a in enumerate(areas, 1)}, "type": codes,
                  "type_short": {t: t for t in types},
                  "principle_names": {str(i): {str(p): f"합성 원리 {p}" for p in range(1, 6)} for i in codes.values()}},
        "blocks": {"order": areas, "default": {a: {"slots": list(b)} for a, b in zip(areas, blocks)},
                   "count_range": {a: [b[1]-b[0]+1]*2 for a, b in zip(areas, blocks)}},
        "type_quota": {"total": {language: quota(24), analysis: quota(12), model: quota(4)},
                       "by_area": {a: {t: quota(b[1]-b[0]+1)} for a, t, b in zip(areas, assigned_types, blocks)}},
        "principle_quota": {
            f"규범|{language}": {"1": quota(12)}, f"인문|{analysis}": {"1": quota(12)},
            f"사회|{language}": {"1": quota(6)},
            f"논리학·수학|{model}": {p: quota(1) for p in ("1", "2", "4", "5")},
            f"과학기술|{language}": {"4": quota(6)},
        },
        "slot_rules": {
            **{str(i): {"type_default": language, "principle_default": "1", "type_allowed": [language], "difficulty_allowed": [3]} for i in (1, 2)},
            "31": {"principle_default": "5"}, "32": {"principle_default": "1"},
            "33": {"principle_allowed": ["2", "4"]},
            "40": {"type_default": language, "principle_default": "4", "type_allowed": [language]},
            "diagram": {"slot_default": 13, "slot_allowed": [13, 24]},
        },
        "response_format": {"non_combo_default_detail": {}, "non_combo_by_area": {},
                            "quota": {COMBO: quota(39), DIAGRAM: quota(1, 1, 1)}},
        "option_pattern": patterns(),
        "answer": {"combo_truth_set_default_for_synthetic": {"ㄱ": 8, "ㄴ": 8, "ㄷ": 8, "ㄱㄴ": 8, "ㄱㄷ": 7},
                   "combo_truth_set_range": {t: [0, 40] for t in patterns()["P1"]},
                   "combo_truth_count": {str(i): quota(0) for i in (1, 2, 3)},
                   "per_number_range": [0, 40], "max_consecutive_same": 40, "soft_max_consecutive_same": 40},
        "stem": {"polarity_target_details": [], "polarity_quota": {"옳은 것": quota(40)},
                 "task_quota_total": {"분석": quota(1), "추론": quota(39), "기타": quota(0)},
                 "task_by_type": {t: {"분석": 1, "추론": 1, "기타": 1} for t in types},
                 "basis_quota": {"다음(지문 전체)": quota(40)}},
        "judgment_mode": {"calc_eligible_cells": [], "calc_by_area": {}, "quota": {"논리": quota(40)}},
        "difficulty": {"quota": {"3": quota(40)}, "position_rules": {}, "bands": {"3": [0.4, 0.6]}, "mean_target": [0, 1]},
        "length": {"by_area": {a: [100, 200, 50, 250] for a in areas}, "by_slot": {},
                   "set_total_target": [4000, 8000], "component_median": {
                       "지문": {a: 100 for a in areas}, "보기·선지": {a: 50 for a in areas}, "발문": 10}},
    }
    cr, cc = content_profile(areas, tag)
    return {"format_rules": fq, "content_rules": cr, "content_config": cc,
            "rules_config": {"synthetic": [tag]}, "labels": {"items": {"synthetic": tag}}}


def verbal_profile(tag="A"):
    area, typ, tp = "합성영역", "일치부합", "일치부합|1"
    stem = "다음 글의 합성 조건에 맞는 것은?"
    fq = {
        "meta": {"version": f"format-{tag}"},
        "codes": {"area": {area: 1}, "type": {typ: 1}, "type_short": {typ: typ},
                  "principle_names": {"1": {"1": "합성 원리"}}},
        "option_pattern": patterns(),
        "skeleton": {"sets": [[19, 20], [39, 40]], "mutations": [0, 0], "base_years": [1],
                     "mutation_weight": {"core": 1, "support": 1},
                     "slots": {str(i): {"by_year": {"1": tp}, "core": {tp: 1}, "support": {}} for i in range(1, 41)}},
        "type_quota": {"total": {typ: quota(40)}}, "principle_quota": {tp: quota(40)},
        "taxonomy": {"majors": {f"합성 대유형 {tag}": [typ]}, "set_type": "합성세트", "major_quota": {}, "subtype_quota": {}},
        "area": {"quota": {area: quota(40)}, "max_consecutive": 40, "cells_allowed": {f"{area}|{tp}": {"all": 1}}},
        "response_format": {"quota": {FIVE: quota(40)}, "forbidden": [], "by_type_principle": {tp: {FIVE: 1}}},
        "answer": {"combo_truth_set_weight": {}, "per_number_range": [0, 40], "max_consecutive_same": 40, "soft_max_consecutive_same": 40},
        "stem": {"pool": {f"{tp}|{FIVE}|단독": {stem: 1}},
                 "meta": {stem: {"근거": "맥락 지정", "작업": "확인", "극성": "옳은 것", "단서": "-"}},
                 "polarity_quota": {"옳은 것": quota(40)}},
        "judgment_mode": {"calc_included_total": quota(0), "calc_eligible": []},
        "difficulty": {"quota": {"3": quota(40)}, "by_type_mean": {typ: 3}, "strict": True},
        "length": {"by_type_principle": {tp: [100, 200, 50, 250]}, "set_total_target": [4000, 8000],
                   "component_median": {"지문": {typ: 100}, "보기·선지": {typ: 50}, "발문": 10}},
    }
    cr, cc = content_profile([area], tag)
    return {"format_rules": fq, "content_rules": cr, "content_config": cc,
            "rules_config": {"synthetic": [tag]}, "labels": {"items": {"synthetic": tag}}}


@pytest.fixture(params=[(LeetEngine, leet_profile), (VerbalEngine, verbal_profile)], ids=["leet", "verbal"])
def case(request):
    return request.param


def test_full_synthetic_round_trip_and_input_output_independence(case):
    cls, factory = case
    inputs = factory()
    original = deepcopy(inputs)
    engine = cls(**inputs)
    design = engine.sample(seed=7)
    assert len(design["slots"]) == 40
    assert engine.validate(design) == []
    assert engine.validate_report(design)["errors"] == []
    design_before = deepcopy(design)
    ledger = {"entries": [{"area": design["slots"][0]["area"], "material": "합성 누적 소재", "slot": 99}]}
    ledger_before = deepcopy(ledger)
    content = engine.content(design, ledger=ledger, seed=7)
    assert [s["slot"] for s in content["슬롯"]] == list(range(1, 41))
    assert all(s["논리_설계"]["정답_번호"] == d["answer"] for s, d in zip(content["슬롯"], design["slots"]))
    assert design == design_before and ledger == ledger_before and inputs == original
    inputs["content_config"]["principles"].append("changed input")
    inputs["format_rules"]["meta"]["version"] = "changed input"
    inputs["labels"]["items"].clear()
    content["회차"]["원칙"].append("changed output")
    design["slots"][0]["chars_range"][0] = -1
    assert engine.sample(seed=7) == design_before
    fresh = engine.content(design_before, ledger=ledger, seed=7)
    assert fresh["회차"]["원칙"] == ["합성 프로필 A"]
    assert engine.labels["items"] == {"synthetic": "A"}


def test_concurrent_profiles_do_not_share_rules_or_results(case):
    cls, factory = case
    engines = [cls(**factory(tag)) for tag in ("A", "B")]
    def run(index):
        engine = engines[index % 2]
        design = engine.sample(seed=13)
        return design, engine.content(design, seed=13)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run, range(8)))
    for index, (design, content) in enumerate(results):
        tag = ("A", "B")[index % 2]
        assert design["meta"]["rules"] == f"format-{tag}"
        assert content["meta"]["rules"] == f"content-{tag}"
        assert content["회차"]["원칙"] == [f"합성 프로필 {tag}"]
        assert all(s["소재"]["원천"] == f"합성 원천 {tag}" for s in content["슬롯"])
        assert (design, content) == results[index % 2]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "code", "answer", "malformed"])
def test_invalid_formats_cannot_reach_content(case, mutation):
    cls, factory = case
    engine = cls(**factory())
    design = engine.sample()
    if mutation == "missing": design["slots"].pop()
    elif mutation == "duplicate": design["slots"][-1]["slot"] = 1
    elif mutation == "reordered": design["slots"].reverse()
    elif mutation == "code": design["slots"][0]["type_code"] = "11-invalid"
    elif mutation == "answer": design["slots"][0]["answer"] = True
    else: design["slots"][0].pop("difficulty")
    assert engine.validate(design)
    with pytest.raises(ValueError, match="content blocked by format validation"):
        engine.content(design)


def test_unsupported_options_and_missing_content_are_explicit(case):
    cls, factory = case
    profile = factory()
    engine = cls(**profile)
    with pytest.raises(ValueError, match="unsupported"):
        engine.sample(exam_grade=7)
    assert engine.validate({"slots": []}, unknown=True)
    profile["content_rules"]["m20_materials"] = []
    empty = cls(**profile)
    with pytest.raises(ValueError, match="m20_materials is empty"):
        empty.content(empty.sample())


@pytest.mark.parametrize("change", ["duplicate", "missing", "unresolved"])
def test_content_reference_defects_are_not_silently_dropped(case, change):
    cls, factory = case
    profile = factory()
    rules = profile["content_rules"]
    if change == "duplicate":
        rules["m20_materials"].append(deepcopy(rules["m20_materials"][0]))
    elif change == "missing":
        rules["m20_materials"][0].pop("id")
    else:
        rules["cells"]["synthetic-cell"] = {"reference_pool": ["unknown-reference"]}
    engine = cls(**profile)
    with pytest.raises(ValueError, match="reference"):
        engine.content(engine.sample())


def test_verbal_set_source_inheritance_and_negative_option_truth():
    profile = verbal_profile()
    engine = VerbalEngine(**profile)
    content = engine.content(engine.sample(), seed=3)
    for a, b in engine.SETS:
        left, right = content["슬롯"][a-1], content["슬롯"][b-1]
        for field in ("대분류", "원천", "변형_연산자", "사실_출처"):
            assert left["소재"][field] == right["소재"][field]
    broken = engine.sample()
    broken["slots"][0]["set"] = True
    assert any("set membership" in e for e in engine.validate(broken))
    single = {"stem": "합성 조건과 상충하는 것은?", "polarity": "옳은 것", "answer": 3, "type": "합성유형"}
    import random
    options = engine._c_option_plan(single, [], random.Random(0))
    assert [o["정오"] for o in options] == ["○", "○", "×", "○", "○"]
