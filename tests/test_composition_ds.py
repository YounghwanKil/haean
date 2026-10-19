"""Synthetic profiles only: no observed question, policy table or source record is copied."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import random

import pytest

from haean.composition.engines.psat_data import Engine as DataEngine
from haean.composition.engines.psat_situation import Engine as SituationEngine


def data_profile(tag="synthetic-A"):
    """Intentionally broad, invented distributions exercise the 40-slot algorithm."""
    counts = {
        "form": {"G": 20, "F": 20},
        "fam": {"A": 0, "B": 20, "S": 20, "T": 0, "U": 0},
        "type": {"종합": 4, "합성": 36}, "diff": {"하": 40, "중": 0, "상": 0},
        "ans": {str(n): 8 for n in range(1, 6)},
        "data_kind": {"표만": 40}, "entity": {"가상": 40},
        "neg": {"neg": 0}, "nitem": {"4": 20}, "tsize": {"4-2": 20},
    }
    axes = {
        key: {"values": list(values), "by_year": {k: {"2000": v} for k, v in values.items()},
              "labels": {k: k for k in values}, "core": {k: [0, 40] for k in values},
              "all": {k: [0, 40] for k in values}}
        for key, values in counts.items()
    }
    bounds = {"core": [0, 40], "all": [0, 40]}
    rules = {
        "meta": {"years": [2000], "core": [2000], "version": tag}, "axes": axes,
        "answer_table": {"4-2": {"allowed": {str(n): 1 for n in range(1, 6)}, "observed": {str(n): 1 for n in range(1, 6)}}},
        "pairing": {fam: {"합성": 1} for fam in ("B", "S")},
        "structure_freq": {}, "blocks": {key: {} for key in ("fam", "form", "type", "diff", "neg")},
    }
    config = {
        "windows": {"base_year": 2000}, "options": {"heads": "ㄱㄴㄷㄹㅁ", "no_full_for": [4, 5]},
        "codes": {"fam_names": {key: f"합성-{key}" for key in counts["fam"]}, "devices": []},
        "combos": [["B", "G", False], ["S", "F", False]],
        "difficulty_rules": {"manuscript_level": {}, "type_fixed": {}},
        "position_weights": {}, "statement_rules": {}, "form_split": {"T": [1, 2]},
        "fam_form": {"A": ["G"], "B": ["G"], "S": ["F"], "T": ["G", "F"], "U": ["G", "F"]},
        "neg_ratio": {"S": [1, 2], "TF": [1, 2]},
        "bundles": {"fam_weight": {"B": 1, "S": 1}, "first_start": {"core": [9, 9], "all": [9, 9]},
                    "second_start": {"core": [29, 29], "all": [29, 29]}, "gap": {"core": [20, 20], "all": [20, 20]}},
        "device_affinity": {}, "shapes": {"B|G": {"synthetic": 1}, "S|F": {"synthetic": 1}},
        "answer_rules": {"max_run": {"all": 40, "core": 40}, "block_max": bounds,
                         "same_as_prev": bounds, "per_number": bounds},
        "templates": {"B|G|N": f"{tag} 합성 발문", "S|F|N": f"{tag} 합성 발문"}, "forbidden_positions": {},
    }
    cr = {"field_dist": {f"{tag}-분야1": 1, f"{tag}-분야2": 1, f"{tag}-분야3": 1},
          "calc_by_type": {"합성": {"합성 연산": 1}}, "chart_kinds": {"합성 그림": 1}, "m20_materials": []}
    cc = {"adjacency": {"max_same_field_consecutive": 2}, "difficulty_knobs": {"하": {"합성": tag}},
          "traps": [f"{tag} 합성 함정"], "entity": {"가상": tag}, "source_memo_schema": {"출처": "합성"},
          "data_kind": {"표만": "합성 표"}, "devices": {}, "principles": [tag], "approval": ["합성 승인 절차"]}
    return dict(format_rules=rules, rules_config=config, content_rules=cr, content_config=cc)


def situation_profile(tag="synthetic-A"):
    """Invented slot bundles use no historical questions or real policy text."""
    skeleton = {}
    pairs = [[19, 20], [39, 40]]
    for n in range(1, 41):
        principle = "P1" if n % 2 else "P2"
        role = "세트(앞)" if n in (19, 39) else "세트(뒤)" if n in (20, 40) else "단독"
        bundles = []
        for year in (2000, 1999):
            bundles.append({
                "학년도": year, "문항 ID": f"{tag}-{year}-{n}", "T": "합성 판단", "PR": principle,
                "내용영역": tag, "응답 형식": "ㄱㄴㄷ 합답형" if n == 1 else "5지형",
                "발문 ③극성": "옳은 것", "발문 ①근거": "합성 근거", "발문 ②작업": "합성 작업",
                "판단 방식": "논리", "계산 부담(원자료)": "없음", "체감 난도(추정)": "하",
                "세트 여부": role, "has_situation": False, "특수형식": [],
                "보기 진술 수": 3 if n == 1 else 0, "발문": "합성 발문",
            })
        skeleton[str(n)] = {"bundles": bundles, "allowed_principles": [principle]}
    rules = {
        "meta": {"version": tag}, "codes": {"area": {tag: "Z"}, "type": {"합성 판단": "Q"},
                                               "principles": {p: {"name": f"{tag}-{p}"} for p in ("P1", "P2")}},
        "skeleton": {"slots": skeleton, "bundle_sampling": {"year_weights_from_latest": [2, 1], "retry": 3}},
        "sets": {"pairs": pairs}, "difficulty": {"map": {"하": 1}},
        "length": {"by_principle": {p: {"q1": 10, "q3": 20} for p in ("P1", "P2")}, "set_total_target_net": [400, 800]},
        "quotas": {key: {} for key in ("type", "response", "polarity", "judgment", "area", "principle", "difficulty_label")},
        "option_patterns": {"patterns": {"ㄱ / ㄴ / ㄱㄴ / ㄱㄷ / ㄱㄴㄷ": {"statements": 3, "core_count": 1, "count": 1, "id": "synthetic-pattern"}}},
        "answer": {"per_number_range": [7, 9], "max_run": 4},
    }
    cells = {p: {"name": p, "type": "합성 판단", "decision": tag, "model": "합성 모형", "build": "합성 제작",
                 "boundary": "합성 경계", "trap": [f"{tag}-함정"], "proof": ["합성 증명"], "vary": ["합성 변주"],
                 "unit_task": {"합성 작업": [1]}, "unit_narration": {"합성 서술": [1]}, "unit_case": {"합성 사례": [1]}}
             for p in ("P1", "P2")}
    cr = {"meta": {"version": tag}, "cells": cells, "m20_materials": [], "areas": {tag: {"fictional": True}}}
    cc = {"reference_selection": {"design_refs": {"same_principle": 2}, "archetype": "합성 참고 지침"},
          "area_policy": {tag: {"source": "합성 원천", "verify": "합성 확인"}},
          "source_memo_schema": {"fields": ["합성 메모"]}, "ai_overuse_blacklist": {tag: [], "strategy": "합성 전략"},
          "principles": [tag], "set_policy": {"합성": tag}, "approval": ["합성 승인 절차"]}
    return dict(format_rules=rules, content_rules=cr, content_config=cc)


@pytest.fixture(params=[(DataEngine, data_profile), (SituationEngine, situation_profile)], scope="module")
def profile_case(request):
    cls, factory = request.param
    profile = factory()
    engine = cls(**profile)
    design = engine.sample(seed=17)
    return cls, factory, profile, engine, design


def test_synthetic_complete_round_and_pure_inputs(profile_case):
    _, _, profile, engine, design = profile_case
    before_profile, before_design = deepcopy(profile), deepcopy(design)
    ledger = {"entries": [{"area": "unrelated", "material": "합성 대장"}]}
    before_ledger = deepcopy(ledger)
    state = random.getstate()
    content = engine.content(design, ledger=ledger, seed=17)
    assert engine.validate(design) == []
    assert [s["slot"] for s in design["slots"]] == list(range(1, 41))
    assert [s["slot"] for s in content["슬롯"]] == list(range(1, 41))
    assert engine.sample(seed=17) == design
    assert engine.content(design, ledger=ledger, seed=17) == content
    assert profile == before_profile and design == before_design and ledger == before_ledger
    assert random.getstate() == state


def test_profiles_remain_independent_under_parallel_calls(profile_case):
    cls, factory, _, _, _ = profile_case
    profiles = [factory("separate-A"), factory("separate-B")]
    engines = [cls(**profile) for profile in profiles]
    for profile in profiles:
        profile["format_rules"]["meta"]["version"] = "mutated-input"
        profile["content_config"]["principles"].append("mutated-input")
    def run(engine):
        design = engine.sample(seed=23)
        return design, engine.content(design, seed=23)
    expected = [run(engine) for engine in engines]
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(run, engines * 2))
    assert actual == expected * 2
    for n, (design, content) in enumerate(expected):
        tag = "separate-A" if n == 0 else "separate-B"
        assert design["meta"]["rules"] == tag
        assert content.get("회차", content)["원칙"] == [tag]
    expected[0][1].get("회차", expected[0][1])["원칙"].append("output-mutation")
    expected[0][0]["slots"][0]["notes"].append("output-mutation")
    assert run(engines[0]) == actual[0]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reorder", "bad_answer", "missing_field", "grade7"])
def test_invalid_design_fails_before_content(profile_case, mutation):
    cls, _, _, engine, original = profile_case
    design = deepcopy(original)
    answer = "ans" if cls is DataEngine else "answer"
    if mutation == "missing":
        design["slots"].pop()
    elif mutation == "duplicate":
        design["slots"][1]["slot"] = 1
    elif mutation == "reorder":
        design["slots"][:2] = reversed(design["slots"][:2])
    elif mutation == "bad_answer":
        design["slots"][0][answer] = 0
    elif mutation == "missing_field":
        del design["slots"][0]["type"]
    else:
        design["meta"]["exam_grade"] = 7
    assert engine.validate(design)
    with pytest.raises(ValueError, match="형식설계 검증 실패"):
        engine.content(design)


@pytest.mark.parametrize("options", [{"size": 25}, {"grade": 7}, {"exam_grade": 7}, {"unrecognized": True}])
def test_unsupported_scope_options_rejected(profile_case, options):
    engine = profile_case[3]
    with pytest.raises(ValueError):
        engine.sample(**options)


def test_ledger_is_explicit_and_typed(profile_case):
    engine, design = profile_case[3:]
    for ledger in ([], {"entries": "bad"}, {"entries": ["bad"]}):
        with pytest.raises(ValueError, match="소재 대장"):
            engine.content(design, ledger=ledger)


def test_content_required_field_is_checked_before_generation(profile_case):
    cls, _, _, engine, original = profile_case
    design = deepcopy(original)
    key = "fam_name" if cls is DataEngine else "archetype_stem"
    del design["slots"][0][key]
    assert any(key in error for error in engine.validate(design))
    with pytest.raises(ValueError, match="필수 형식 필드 누락"):
        engine.content(design)


def test_no_filesystem_or_pool_access_needed(profile_case, monkeypatch):
    engine, design = profile_case[3:]
    def forbidden(*args, **kwargs):
        raise AssertionError("composition must use only its explicit inputs")
    monkeypatch.setattr("builtins.open", forbidden)
    assert engine.validate(engine.sample(seed=2)) == []
    assert len(engine.content(design)["슬롯"]) == 40


def test_data_combo_answer_and_shared_bundle_material():
    engine = DataEngine(**data_profile())
    design = engine.sample(seed=8)
    content = engine.content(design, seed=8)
    for slot, spec in zip(design["slots"], content["슬롯"]):
        if slot["form"] == "G":
            selected = slot["options"][slot["ans"] - 1]
            assert [unit["보기"] for unit in spec["진술_설계"] if unit["진위"] == "○"] == list(selected)
    for bundle in ("가", "나"):
        pair = [s for s in content["슬롯"] if s["묶음"] == bundle]
        assert len(pair) == 2
        assert pair[0]["소재"]["분야"] == pair[1]["소재"]["분야"]
    broken = deepcopy(design)
    next(s for s in broken["slots"] if s["bundle"])["bundle"] = "broken"
    assert engine.validate(broken)
    broken = deepcopy(design)
    next(s for s in broken["slots"] if s["form"] == "G")["options"] = None
    assert any("선지배열" in error for error in engine.validate(broken))
    with pytest.raises(ValueError, match="선지배열"):
        engine.content(broken)
    with pytest.raises(ValueError, match="tries"):
        engine.sample(tries=0)


def test_situation_latest_sets_and_combo_truth():
    engine = SituationEngine(**situation_profile())
    design = engine.sample(seed=8, mode="latest")
    content = engine.content(design, seed=8)
    assert engine.validate(design) == []
    assert {s["archetype_year"] for s in design["slots"]} == {2000}
    selected = design["slots"][0]["selected_set"]
    units = content["슬롯"][0]["판단_단위_설계"]["단위"]
    assert [u["기호"] for u in units if u["진위"] == "○"] == list(selected)
    broken = deepcopy(design)
    broken["slots"][19]["archetype_year"] = 1999
    assert any("학년도" in error for error in engine.validate(broken))
    with pytest.raises(ValueError, match="mode"):
        engine.sample(mode="unsupported")
