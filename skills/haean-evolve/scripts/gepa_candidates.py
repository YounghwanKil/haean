"""Candidate utilities inspired by GEPA; no evaluation or promotion occurs here.

Official reference: gepa-ai/gepa at 8f287de942f41a6d1e0e7e5b2d576247c4bedee9,
gepa_utils.py, strategies/candidate_selector.py and proposer/merge.py.
This is an independent stdlib implementation of case-winner coverage selection
and a deliberately stricter, conflict-rejecting component merge.

The caller must first verify product, split, evaluation conditions, eligibility,
repeat coverage, and candidate genealogy. Scores are larger-is-better. These
functions do not authenticate those facts or claim better question quality.
"""
from collections.abc import Mapping, Sequence
from fractions import Fraction
import hashlib
import json
import math
import random


def _name(value, description):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be a nonempty string")
    return value


def select_parent(candidates, seed=0):
    """Select an exploratory parent while preserving every case's best score.

    Each input row has a unique string ``id`` and nonempty ``scores`` mapping
    from case IDs to finite int/float scores. All rows must cover exactly the
    same cases. Unrelated row metadata is ignored and inputs are never mutated.

    Candidates with redundant winner coverage are considered for removal from
    lowest mean to highest; equal means use ascending ID. A candidate is removed
    only while another survivor still wins *every* case it wins. Survivors are
    sampled with integer weights equal to their number of winning cases. Thus
    a specialist can survive despite a lower mean than another candidate.

    This is not standard vector-Pareto pruning, a final ranking, or promotion.
    Sorting both cases and IDs makes seeded selection independent of input order.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError("candidates must be a nonempty sequence")
    if not candidates:
        raise ValueError("candidates must not be empty")
    rows = {}
    expected_cases = None
    for row in candidates:
        if not isinstance(row, Mapping):
            raise ValueError("each candidate must be a mapping")
        identifier = _name(row.get("id"), "candidate id")
        if identifier in rows:
            raise ValueError(f"duplicate candidate id: {identifier}")
        scores = row.get("scores")
        if not isinstance(scores, Mapping) or not scores:
            raise ValueError(f"candidate {identifier} needs nonempty scores")
        validated = {}
        for case, score in scores.items():
            _name(case, "case id")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValueError(f"score for {identifier}/{case} must be numeric")
            if isinstance(score, float) and not math.isfinite(score):
                raise ValueError(f"score for {identifier}/{case} must be finite")
            validated[case] = score
        cases = set(validated)
        if expected_cases is not None and cases != expected_cases:
            raise ValueError("all candidates must have exactly the same cases")
        expected_cases = cases
        rows[identifier] = validated

    identifiers = sorted(rows)
    cases = sorted(expected_cases)
    frontier = {}
    for case in cases:
        best = max(rows[identifier][case] for identifier in identifiers)
        frontier[case] = [
            identifier for identifier in identifiers if rows[identifier][case] == best
        ]
    covered = {
        identifier: [case for case in cases if identifier in frontier[case]]
        for identifier in identifiers
    }
    # Exact rational arithmetic avoids overflow and order-dependent floating sums.
    means = {
        identifier: sum((Fraction(score) for score in rows[identifier].values()), Fraction())
        / len(cases)
        for identifier in identifiers
    }
    survivors = {identifier for identifier in identifiers if covered[identifier]}
    remaining = {case: len(frontier[case]) for case in cases}
    for identifier in sorted(survivors, key=lambda item: (means[item], item)):
        if all(remaining[case] > 1 for case in covered[identifier]):
            survivors.remove(identifier)
            for case in covered[identifier]:
                remaining[case] -= 1

    survivors = sorted(survivors)
    weights = {identifier: len(covered[identifier]) for identifier in survivors}
    ticket = random.Random(seed).randrange(sum(weights.values()))
    selected = survivors[-1]
    for identifier in survivors:
        if ticket < weights[identifier]:
            selected = identifier
            break
        ticket -= weights[identifier]
    return {
        "per_case_frontier": frontier,
        "pruned_frontier": {
            case: [identifier for identifier in frontier[case] if identifier in weights]
            for case in cases
        },
        "survivors": survivors,
        "weights": weights,
        "selected": selected,
        "seed": seed,
        "auto_promoted": False,
        "note": "Exploratory parent selection only; no candidate promotion or quality claim.",
    }


def _components(value, label):
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{label} must be a nonempty component mapping")
    result = {}
    for name, text in value.items():
        _name(name, f"{label} component name")
        if not isinstance(text, str):
            raise ValueError(f"{label}/{name} component must be text")
        result[name] = text
    return result


def _digest(components):
    serialized = json.dumps(
        components, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def merge_components(ancestor, left, right):
    """Build an unpromoted candidate from two changes to a common base.

    Unchanged components are preserved, one-sided changes are retained, and an
    identical edit in both parents is retained once. Unlike official GEPA, a
    component changed differently by both parents is rejected, not resolved by
    aggregate score. The caller must verify ancestry and reject duplicates of
    any *other* archived candidates; this utility rejects either-parent copies.
    """
    ancestor = _components(ancestor, "ancestor")
    left = _components(left, "left")
    right = _components(right, "right")
    if set(ancestor) != set(left) or set(ancestor) != set(right):
        raise ValueError("ancestor and both parents must have identical component keys")
    merged, sources = {}, {}
    for key in sorted(ancestor):
        base, first, second = ancestor[key], left[key], right[key]
        if first == second:
            merged[key] = first
            sources[key] = "ancestor" if first == base else "both"
        elif first == base:
            merged[key], sources[key] = second, "right"
        elif second == base:
            merged[key], sources[key] = first, "left"
        else:
            raise ValueError(f"conflicting component changes: {key}")
    if merged == left or merged == right:
        raise ValueError("duplicate merge: result equals a parent")
    return {
        "components": merged,
        "component_sources": sources,
        "ancestor_sha256": _digest(ancestor),
        "left_sha256": _digest(left),
        "right_sha256": _digest(right),
        "merged_sha256": _digest(merged),
        "auto_promoted": False,
        "note": "Conflict-free component proposal only; evaluate before any promotion.",
    }
