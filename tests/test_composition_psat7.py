"""Public synthetic profiles: no real questions or private source text."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import random

import pytest

from haean.composition.engines.psat7 import Engine


def psat7_profile(subject="언어논리", tag="synthetic"):
    identity = {"schema_version": 1, "engine": "psat7-v1", "exam_grade": 7, "subject": subject}
    subjects = {
        "언어논리": ("V", "합성 주장 비교", "주장의 양립 가능성을 합성 문장으로 판단", "논거 범위를 바꿈"),
        "자료해석": ("D", "합성 비율 비교", "합성 표의 기준량을 맞춰 비율을 비교", "분모를 바꿈"),
        "상황판단": ("S", "합성 조건 적용", "합성 규칙의 예외 조건을 사례에 적용", "예외 적용 시점을 바꿈"),
    }
    prefix, label, task, trap = subjects[subject]
    codes = [f"{prefix}{i}" for i in range(3)]
    return {
        "subject": subject,
        "format_rules": {**identity, "total_slots": 25,
            "types": [
                {"code": codes[0], "label": f"{label}-A", "count": 13, "response_formats": ["5지 단일선택", "ㄱㄴㄷ 합답형"]},
                {"code": codes[1], "label": f"{label}-B", "count": 12, "response_formats": ["5지 단일선택"]},
                {"code": codes[2], "label": f"{label}-C", "count": 0, "response_formats": ["5지 단일선택"]},
            ],
            "shared_sets": [
                {"id": "synthetic-shared-first", "members": [3, 4], "types": [codes[0], codes[1]]},
                {"id": "synthetic-shared-last", "members": [24, 25], "types": [codes[1], codes[1]]},
            ],
            "difficulty_counts": {"하": 6, "중": 14, "상": 5},
            "section_preferences": [{"start": 1, "end": 5, "types": [codes[0]]}],
        },
        "content_rules": {**identity, "types": {
            code: {"domains": [f"{tag}-합성영역1", f"{tag}-합성영역2"],
                   "reasoning_tasks": [f"{task}-{code}", f"{task}의 반례 확인-{code}"],
                   "distractor_paths": [f"{trap}-{code}"],
                   "review_checks": [f"{subject}-{code} 합성 검토"],
                   "construction_notes": [f"{tag}-{code} 합성 작성 유의"]}
            for code in codes}},
        "content_config": {**identity,
            "common_passage_policy": ["두 합성 문항은 같은 사실을 공유하며 독립적으로 풀리게 한다"],
            "difficulty_policy": ["합성 난도는 편집 목표이며 실측값이 아님"],
            "source_policy": [f"{tag} 합성 출처 정책"],
            "subject_review": [f"{subject} 합성 과목 검토"],
        },
        "rules_config": {**identity,
            "observations": {"provenance": "invented fixture", "period": "synthetic only", "raw": [tag]},
            "editorial_decisions": ["합성 할당량과 세트 위치는 이 테스트의 편집 선택"],
        },
    }


@pytest.fixture(params=["언어논리", "자료해석", "상황판단"])
def profile_case(request):
    profile = psat7_profile(request.param)
    return profile, Engine(**profile)


def test_quota_sample_has_real_sets_and_no_answer_allocation(profile_case):
    profile, engine = profile_case
    design = engine.sample(seed=17, size=25)
    assert engine.sample(seed=17) == design
    assert engine.sample(seed=18) != design
    assert engine.validate(design) == []
    assert len(design["slots"]) == 25
    assert [row["slot"] for row in design["slots"]] == list(range(1, 26))
    assert Counter(row["type_code"] for row in design["slots"]) == Counter({
        row["code"]: row["count"] for row in profile["format_rules"]["types"]})
    assert Counter(row["difficulty"] for row in design["slots"]) == profile["format_rules"]["difficulty_counts"]
    expected_sets = {group["id"]: group for group in profile["format_rules"]["shared_sets"]}
    actual_sets = {}
    for row in design["slots"]:
        assert row["diff"] == row["difficulty"]
        assert row["bundle"] == row["set_id"]
        assert row["set"] is (row["set_id"] is not None)
        assert not {"answer", "ans", "true", "truth_pattern", "option_pattern"}.intersection(row)
        allowed = next(spec for spec in profile["format_rules"]["types"] if spec["code"] == row["type_code"])
        assert row["type"] == allowed["label"]
        assert row["response_format"] in allowed["response_formats"]
        if row["set"]:
            actual_sets.setdefault(row["set_id"], {"members": [], "types": []})
            actual_sets[row["set_id"]]["members"].append(row["slot"])
            actual_sets[row["set_id"]]["types"].append(row["type_code"])
    assert actual_sets == {key: {"members": value["members"], "types": value["types"]}
                           for key, value in expected_sets.items()}
    assert design["meta"]["exam_grade"] == 7
    assert design["meta"]["subject"] == profile["subject"]
    assert design["meta"]["quality_approval"] is False


def test_content_uses_each_subject_blueprints_and_matches_design(profile_case):
    profile, engine = profile_case
    design = engine.sample(seed=4)
    content = engine.content(design, seed=4)
    assert content == engine.content(design, seed=4)
    assert len(content["슬롯"]) == 25
    for row, spec in zip(design["slots"], content["슬롯"]):
        assert (spec["slot"], spec["type"], spec["type_code"]) == (row["slot"], row["type"], row["type_code"])
        blueprint = profile["content_rules"]["types"][row["type_code"]]
        assert spec["논리_설계"]["판단_과제"] in blueprint["reasoning_tasks"]
        assert spec["논리_설계"]["오답_경로"] == blueprint["distractor_paths"]
        assert spec["논리_설계"]["검토_항목"] == blueprint["review_checks"]
        assert spec["논리_설계"]["구성_유의"] == blueprint["construction_notes"]
        assert spec["응답_형식"] == row["response_format"]
        assert spec["난도"]["편집_목표"] == row["difficulty"]
        assert spec["난도"]["실측"] is False
        assert spec["세트"]["id"] == row["set_id"]
        assert spec["세트"]["공통지문"] is row["set"]
        if row["set"]:
            assert row["slot"] in spec["세트"]["members"]
        assert "대장 미제공" in spec["소재"]["대장_회피"]["상태"]
    assert content["회차"]["원자료_관측"] == profile["rules_config"]["observations"]
    assert content["회차"]["편집_결정"] == profile["rules_config"]["editorial_decisions"]
    assert content["회차"]["소재_대장"]["검색_수행"] is False


def test_explicit_ledger_avoidance_and_mutable_inputs_are_detached(profile_case):
    profile, engine = profile_case
    design = engine.sample(seed=5)
    ledger = {"entries": [{"domain": "synthetic-합성영역1", "note": ["inert user data"]}]}
    original_profile, original_design, original_ledger = deepcopy(profile), deepcopy(design), deepcopy(ledger)
    state = random.getstate()
    content = engine.content(design, ledger=ledger, seed=5)
    assert random.getstate() == state
    assert (profile, design, ledger) == (original_profile, original_design, original_ledger)
    assert all(row["소재"]["영역"] == "synthetic-합성영역2" for row in content["슬롯"])
    assert content["회차"]["소재_대장"]["입력"] == ledger
    expected = deepcopy(content)
    content["회차"]["소재_대장"]["입력"]["entries"][0]["note"].append("changed output")
    content["슬롯"][0]["논리_설계"]["오답_경로"].append("changed output")
    content["슬롯"][2]["세트"]["members"].append(100)
    profile["format_rules"]["types"][0]["count"] = 99
    profile["content_config"]["source_policy"].append("changed input")
    profile["content_rules"]["types"][next(iter(profile["content_rules"]["types"]))]["reasoning_tasks"].clear()
    assert engine.content(design, ledger=ledger, seed=5) == expected
    assert engine.sample(seed=5) == original_design
    assert ledger == original_ledger


def test_concurrent_profiles_do_not_share_state():
    engines = [Engine(**psat7_profile(subject, tag=f"synthetic-{index}"))
               for index, subject in enumerate(("언어논리", "자료해석", "상황판단"))]
    def run(engine):
        design = engine.sample(seed=2)
        return design, engine.content(design, seed=2)
    expected = [run(engine) for engine in engines]
    with ThreadPoolExecutor(max_workers=3) as pool:
        actual = list(pool.map(run, engines * 2))
    assert actual == expected * 2
    for index, (_, content) in enumerate(expected):
        assert all(row["소재"]["영역"].startswith(f"synthetic-{index}-") for row in content["슬롯"])


def test_section_preferences_are_soft_even_when_infeasible():
    profile = psat7_profile()
    profile["format_rules"]["section_preferences"] = [{"start": 1, "end": 25, "types": ["V0"]}]
    engine = Engine(**profile)
    report = engine.validate_report(engine.sample(seed=0))
    assert report["errors"] == []
    assert report["warnings"] and "필수 규칙 아님" in report["warnings"][0]


def test_shared_passages_share_domain_and_use_distinct_available_tasks():
    engine = Engine(**psat7_profile())
    content = engine.content(engine.sample(seed=9), seed=9)
    for first, second in ((content["슬롯"][2], content["슬롯"][3]),
                          (content["슬롯"][23], content["슬롯"][24])):
        assert first["소재"]["영역"] == second["소재"]["영역"] == first["세트"]["공통_영역"]
        assert first["세트"] == second["세트"]
    assert content["슬롯"][23]["논리_설계"]["판단_과제"] != content["슬롯"][24]["논리_설계"]["판단_과제"]
    assert content["회차"]["warnings"] == []


def test_different_types_in_shared_passage_avoid_repeating_common_tasks():
    profile = psat7_profile()
    tasks = ["공유된 합성 판단 과제 하나", "공유된 합성 판단 과제 둘"]
    for code in ("V0", "V1"):
        profile["content_rules"]["types"][code]["reasoning_tasks"] = list(tasks)
    engine = Engine(**profile)
    content = engine.content(engine.sample(seed=0), seed=0)
    first, second = content["슬롯"][2:4]
    assert first["type_code"] != second["type_code"]
    assert {first["논리_설계"]["판단_과제"], second["논리_설계"]["판단_과제"]} == set(tasks)
    assert content["회차"]["warnings"] == []


def test_reused_shared_domain_is_not_reported_as_ledger_avoidance():
    profile = psat7_profile()
    profile["content_rules"]["types"]["V0"]["domains"] = ["기존공통영역", "신규A"]
    profile["content_rules"]["types"]["V1"]["domains"] = ["기존공통영역", "신규B"]
    engine = Engine(**profile)
    ledger = {"entries": [{"domain": "기존공통영역"}]}
    content = engine.content(engine.sample(seed=0), ledger=ledger, seed=0)
    for row in content["슬롯"][2:4]:
        assert row["소재"]["영역"] == row["세트"]["공통_영역"] == "기존공통영역"
        assert "재사용" in row["소재"]["대장_회피"]["상태"]
        assert "제외" not in row["소재"]["대장_회피"]["상태"]
    assert any("synthetic-shared-first" in warning and "재사용" in warning
               for warning in content["회차"]["warnings"])


def test_missing_shared_domain_or_distinct_task_is_review_warning_not_fabrication():
    profile = psat7_profile()
    blueprints = profile["content_rules"]["types"]
    blueprints["V0"]["domains"] = ["합성 한 영역"]
    blueprints["V1"]["domains"] = ["합성 다른 영역"]
    blueprints["V1"]["reasoning_tasks"] = ["명시된 단 하나의 합성 과제"]
    engine = Engine(**profile)
    content = engine.content(engine.sample(seed=9), seed=9)
    assert content["슬롯"][23]["논리_설계"]["판단_과제"] == "명시된 단 하나의 합성 과제"
    assert content["슬롯"][24]["논리_설계"]["판단_과제"] == "명시된 단 하나의 합성 과제"
    assert content["슬롯"][2]["세트"]["공통_영역"] is None
    assert any("소재 조정" in warning for warning in content["회차"]["warnings"])
    assert any("실제 차별 판단 재검토" in warning for warning in content["회차"]["warnings"])


@pytest.mark.parametrize("role", ["format_rules", "content_rules", "content_config", "rules_config"])
@pytest.mark.parametrize("key,value", [("exam_grade", 5), ("exam_grade", True), ("engine", "psat5-v1"),
                                      ("schema_version", True), ("schema_version", 2), ("subject", "자료해석")])
def test_every_body_identity_is_checked(role, key, value):
    profile = psat7_profile()
    profile[role][key] = value
    with pytest.raises(ValueError):
        Engine(**profile)


@pytest.mark.parametrize("mutation", [
    "unknown_field", "unknown_type_field", "wrong_quota", "bool_quota", "duplicate_code", "duplicate_label",
    "empty_response", "bad_response", "missing_blueprint", "extra_blueprint", "empty_tasks", "unknown_blueprint_field",
    "overlapping_sets", "distant_set", "repeated_member", "bool_member", "unknown_set_type", "set_over_capacity",
    "duplicate_set_id", "wrong_set_arity", "difficulty_count", "bool_difficulty", "unknown_difficulty",
    "missing_policy", "empty_policy", "observations_list", "empty_editorial", "unknown_preference", "preference_range",
])
def test_infeasible_or_malformed_profiles_fail_closed(mutation):
    profile = psat7_profile()
    f, c = profile["format_rules"], profile["content_rules"]
    if mutation == "unknown_field": f["official_answer_quota"] = {"1": 5}
    elif mutation == "unknown_type_field": f["types"][0]["answer"] = 1
    elif mutation == "wrong_quota": f["types"][0]["count"] = 12
    elif mutation == "bool_quota": f["types"][0]["count"] = True
    elif mutation == "duplicate_code": f["types"][1]["code"] = "V0"
    elif mutation == "duplicate_label": f["types"][1]["label"] = f["types"][0]["label"]
    elif mutation == "empty_response": f["types"][0]["response_formats"] = []
    elif mutation == "bad_response": f["types"][0]["response_formats"] = [" "]
    elif mutation == "missing_blueprint": del c["types"]["V0"]
    elif mutation == "extra_blueprint": c["types"]["other"] = deepcopy(c["types"]["V0"])
    elif mutation == "empty_tasks": c["types"]["V0"]["reasoning_tasks"] = []
    elif mutation == "unknown_blueprint_field": c["types"]["V0"]["execute"] = "raise Exception"
    elif mutation == "overlapping_sets": f["shared_sets"][1]["members"] = [4, 5]
    elif mutation == "distant_set": f["shared_sets"][0]["members"] = [1, 3]
    elif mutation == "repeated_member": f["shared_sets"][0]["members"] = [3, 3]
    elif mutation == "bool_member": f["shared_sets"][0]["members"] = [True, 2]
    elif mutation == "unknown_set_type": f["shared_sets"][0]["types"] = ["V0", "other"]
    elif mutation == "set_over_capacity": f["shared_sets"][0]["types"] = ["V0", "V2"]
    elif mutation == "duplicate_set_id": f["shared_sets"][1]["id"] = f["shared_sets"][0]["id"]
    elif mutation == "wrong_set_arity": f["shared_sets"][0]["types"] = ["V0"]
    elif mutation == "difficulty_count": f["difficulty_counts"]["하"] = 0
    elif mutation == "bool_difficulty": f["difficulty_counts"]["하"] = True
    elif mutation == "unknown_difficulty": f["difficulty_counts"]["극상"] = 0
    elif mutation == "missing_policy": del profile["content_config"]["subject_review"]
    elif mutation == "empty_policy": profile["content_config"]["source_policy"] = []
    elif mutation == "observations_list": profile["rules_config"]["observations"] = []
    elif mutation == "empty_editorial": profile["rules_config"]["editorial_decisions"] = []
    elif mutation == "unknown_preference": f["section_preferences"][0]["types"] = ["other"]
    elif mutation == "preference_range": f["section_preferences"][0]["start"] = 26
    with pytest.raises(ValueError):
        Engine(**profile)


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "reorder", "bool_slot", "bad_slot", "non_dict_slot", "unknown_slot_field", "missing_slot_field",
    "unknown_type", "bad_type", "wrong_label", "wrong_quota", "difficulty", "diff_alias", "difficulty_quota",
    "set_id", "bundle_alias", "set_boolean", "set_types", "response_format", "bad_meta", "approval", "grade5", "size40",
])
def test_invalid_design_returns_errors_and_blocks_content(mutation):
    engine = Engine(**psat7_profile())
    design = engine.sample(seed=11)
    row = design["slots"][0]
    if mutation == "missing": design["slots"].pop()
    elif mutation == "duplicate": design["slots"][1]["slot"] = 1
    elif mutation == "reorder": design["slots"][:2] = reversed(design["slots"][:2])
    elif mutation == "bool_slot": row["slot"] = True
    elif mutation == "bad_slot": row["slot"] = []
    elif mutation == "non_dict_slot": design["slots"][0] = None
    elif mutation == "unknown_slot_field": row["answer"] = 1
    elif mutation == "missing_slot_field": del row["set_id"]
    elif mutation == "unknown_type": row["type_code"] = "other"
    elif mutation == "bad_type": row["type_code"] = []
    elif mutation == "wrong_label": row["type"] = "other"
    elif mutation == "wrong_quota": row.update(type_code="V2", type="합성 주장 비교-C", response_format="5지 단일선택")
    elif mutation == "difficulty": row["difficulty"] = []
    elif mutation == "diff_alias": row["diff"] = "wrong"
    elif mutation == "difficulty_quota": row["difficulty"] = row["diff"] = "하" if row["difficulty"] != "하" else "상"
    elif mutation == "set_id": row["set_id"] = row["bundle"] = "synthetic-shared-first"; row["set"] = True
    elif mutation == "bundle_alias": row["bundle"] = "other"
    elif mutation == "set_boolean": row["set"] = 0
    elif mutation == "set_types":
        # Swap complete type assignments to retain quotas while violating only
        # the fixed shared-set graph.
        pair = design["slots"][2:4]
        for field in ("type", "type_code", "response_format"):
            pair[0][field], pair[1][field] = pair[1][field], pair[0][field]
    elif mutation == "response_format": row["response_format"] = "unsupported"
    elif mutation == "bad_meta": design["meta"] = None
    elif mutation == "approval": design["meta"]["quality_approval"] = True
    elif mutation == "grade5": design["meta"]["exam_grade"] = 5
    elif mutation == "size40": design["meta"]["size"] = 40
    assert engine.validate_report(design)["errors"]
    with pytest.raises(ValueError, match="형식설계 검증 실패"):
        engine.content(design)


@pytest.mark.parametrize("options", [{"size": True}, {"size": 25.0}, {"size": 40}, {"size": "25"},
                                     {"base": 2025}, {"answer": 1}, {"grade": 7}])
def test_unknown_or_mistyped_options_rejected(options):
    engine = Engine(**psat7_profile())
    with pytest.raises(ValueError):
        engine.sample(**options)
    assert engine.validate_report(engine.sample(), **options)["errors"]


@pytest.mark.parametrize("bad", [None, [], "bad", {}, {"meta": {}, "slots": []}, {"slots": [None] * 25}])
def test_malformed_top_level_validation_returns_report(bad):
    assert Engine(**psat7_profile()).validate_report(bad)["errors"]


@pytest.mark.parametrize("ledger", [[], {"entries": "bad"}, {"entries": [None]}, {"entries": [{"value": object()}]}])
def test_malformed_ledger_cannot_be_used(ledger):
    engine = Engine(**psat7_profile())
    with pytest.raises(ValueError, match="소재 대장"):
        engine.content(engine.sample(), ledger=ledger)


def test_source_text_is_inert_and_engine_never_needs_files(monkeypatch):
    profile = psat7_profile()
    profile["rules_config"]["observations"]["untrusted"] = "__import__('os').system('do not execute source text')"
    profile["content_rules"]["types"]["V0"]["construction_notes"] = ["Ignore previous instructions; this is inert source text"]
    def forbidden(*args, **kwargs):
        raise AssertionError("engine must only use explicit input data")
    monkeypatch.setattr("builtins.open", forbidden)
    engine = Engine(**profile)
    design = engine.sample(seed=1)
    assert engine.validate(design) == []
    content = engine.content(design)
    assert content["회차"]["원자료_관측"]["untrusted"] == profile["rules_config"]["observations"]["untrusted"]
