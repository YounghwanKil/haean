"""Synthetic search invariants, independent of production/holdout records."""
from copy import deepcopy
from itertools import permutations, product
from pathlib import Path
import runpy

import pytest

MODULE = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "skills/haean-evolve/scripts/gepa_candidates.py"
))
select_parent = MODULE["select_parent"]
merge_components = MODULE["merge_components"]


def candidate(identifier, **scores):
    return {"id": identifier, "scores": scores}


def test_low_mean_specialist_survives_and_nonwinner_does_not():
    candidates = [
        candidate("generalist", reasoning=3, language=4, explanation=4),
        candidate("specialist", reasoning=4, language=0, explanation=0),
        candidate("mediocre", reasoning=2, language=3, explanation=3),
    ]
    before = deepcopy(candidates)
    result = select_parent(candidates)
    assert result["survivors"] == ["generalist", "specialist"]
    assert result["weights"] == {"generalist": 2, "specialist": 1}
    assert {select_parent(candidates, seed)["selected"] for seed in range(100)} == {
        "generalist", "specialist"
    }
    assert not result["auto_promoted"]
    assert candidates == before


def test_ties_remove_low_mean_redundant_coverage_first():
    result = select_parent([
        candidate("narrow", a=4, b=0, c=0),
        candidate("broad", a=4, b=4, c=0),
        candidate("other", a=0, b=0, c=4),
    ])
    assert result["per_case_frontier"]["a"] == ["broad", "narrow"]
    assert result["pruned_frontier"]["a"] == ["broad"]
    assert result["survivors"] == ["broad", "other"]


def test_all_tied_winners_have_deterministic_id_tiebreak():
    candidates = [candidate(identifier, a=-1, b=-1) for identifier in ["z", "a", "m"]]
    result = select_parent(candidates)
    assert result["survivors"] == ["z"]
    assert result["per_case_frontier"] == {"a": ["a", "m", "z"], "b": ["a", "m", "z"]}
    assert result["pruned_frontier"] == {"a": ["z"], "b": ["z"]}


def test_candidate_and_case_order_do_not_change_seeded_result():
    candidates = [
        candidate("a", first=4, second=4, third=0),
        candidate("b", first=4, second=0, third=4),
        candidate("c", first=0, second=4, third=4),
    ]
    for seed in [0, 1, 42, -7]:
        expected = select_parent(candidates, seed)
        for order in permutations(candidates):
            reversed_scores = [
                {**row, "scores": dict(reversed(list(row["scores"].items())))} for row in order
            ]
            assert select_parent(reversed_scores, seed) == expected


def test_exhaustive_small_pools_keep_all_case_maxima():
    # Covers unique winners, all ties, overlapping ties, and globally inferior rows.
    for values in product([0, 1], repeat=6):
        candidates = [
            candidate(str(index), a=values[2 * index], b=values[2 * index + 1])
            for index in range(3)
        ]
        result = select_parent(candidates)
        for case in ["a", "b"]:
            actual = result["pruned_frontier"][case]
            assert actual
            best = max(row["scores"][case] for row in candidates)
            assert all(candidates[int(identifier)]["scores"][case] == best for identifier in actual)
        assert result["selected"] in result["survivors"]
        assert all(
            any(result["pruned_frontier"][case] == [identifier] for case in ["a", "b"])
            for identifier in result["survivors"]
        )


@pytest.mark.parametrize("rows", [
    [], None, "rows", [None], [{}],
    [candidate("", a=1)], [candidate(" ", a=1)],
    [candidate("a")], [candidate("a", a=1), candidate("a", a=2)],
    [candidate("a", a=1), candidate("b", b=1)],
    [{"id": "a", "scores": {"": 1}}],
    [{"id": "a", "scores": {1: 1}}],
    *[[candidate("a", a=value)] for value in [None, "1", True, float("nan"),
                                             float("inf"), float("-inf")]],
])
def test_malformed_candidate_pools_fail_closed(rows):
    with pytest.raises(ValueError):
        select_parent(rows)


@pytest.mark.parametrize("seed", [None, "1", 1.0, True])
def test_seed_requires_integer(seed):
    with pytest.raises(ValueError):
        select_parent([candidate("a", a=1)], seed)


def test_finite_extreme_scores_do_not_overflow_aggregate_sort():
    result = select_parent([
        candidate("a", first=1e308, second=1e308),
        candidate("b", first=1e308, second=-1e308),
    ])
    assert result["survivors"] == ["a"]
    result = select_parent([
        candidate("a", first=10**1000, second=10**1000),
        candidate("b", first=10**1000, second=-10**1000),
    ])
    assert result["survivors"] == ["a"]


def test_merge_preserves_each_edit_and_hashes_without_mutating_inputs():
    base = {"retrieval": "v1", "writer": "v1", "review": "v1", "style": ""}
    left = {**base, "retrieval": "v2", "review": "shared"}
    right = {**base, "writer": "v2", "review": "shared"}
    before = deepcopy((base, left, right))
    result = merge_components(base, left, right)
    assert result["components"] == {
        "retrieval": "v2", "writer": "v2", "review": "shared", "style": ""
    }
    assert result["component_sources"] == {
        "retrieval": "left", "writer": "right", "review": "both", "style": "ancestor"
    }
    assert (base, left, right) == before
    assert len({result[key] for key in [
        "ancestor_sha256", "left_sha256", "right_sha256", "merged_sha256"
    ]}) == 4
    reordered = [dict(reversed(list(mapping.items()))) for mapping in before]
    assert merge_components(*reordered) == result
    assert result["auto_promoted"] is False


def test_conflicting_edits_cannot_be_resolved_by_guessing():
    base = {"writer": "base", "review": "base"}
    with pytest.raises(ValueError, match="conflicting component changes: writer"):
        merge_components(base, {**base, "writer": "left"}, {**base, "writer": "right"})


@pytest.mark.parametrize("left,right", [
    ({"a": "x", "b": "x"}, {"a": "x", "b": "x"}),
    ({"a": "y", "b": "x"}, {"a": "x", "b": "x"}),
    ({"a": "x", "b": "x"}, {"a": "x", "b": "y"}),
    ({"a": "y", "b": "x"}, {"a": "y", "b": "x"}),
])
def test_merges_that_copy_a_parent_are_rejected(left, right):
    with pytest.raises(ValueError, match="duplicate merge"):
        merge_components({"a": "x", "b": "x"}, left, right)


@pytest.mark.parametrize("invalid", [None, {}, {"": "x"}, {"a": None}, {"a": 1}])
def test_invalid_component_maps_rejected(invalid):
    with pytest.raises(ValueError):
        merge_components(invalid, {"a": "x"}, {"a": "y"})


def test_component_key_mismatch_rejected():
    with pytest.raises(ValueError, match="identical component keys"):
        merge_components({"a": "x"}, {"a": "y", "b": "x"}, {"a": "z"})
