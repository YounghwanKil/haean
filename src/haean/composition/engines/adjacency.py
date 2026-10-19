"""Pure run allocation helpers; all random state is supplied by the caller."""

from collections import Counter


def in_range(x, bounds):
    return bounds[0] <= x <= bounds[1]


def max_run(seq) -> int:
    best = cur = 0
    prev = object()
    for x in seq:
        cur = cur + 1 if x == prev else 1
        best = max(best, cur)
        prev = x
    return best


def arrange_runs(bag, rate: float, max_len: int, rng, tries: int=400) -> list:
    """그룹 다중집합 → 같은 그룹이 이웃하는 비율 ≈ rate(기출 same_group_rate), run 길이 ≤ max_len, 같은 그룹의 두 run 은 붙이지 않는다.
    사회·과학기술·인문(cluster_index > 1)은 같은 분야가 2~3연속으로 붙고, 논리학·수학(< 1)은 교대가 된다."""
    bag = list(bag)
    n = len(bag)
    if n <= 1:
        return bag
    counts = Counter(bag)
    target = max(0, min(round(rate * (n - 1)), sum((c - 1 for c in counts.values()))))
    best, best_gap = (None, None)
    for _ in range(tries):
        runs = [[g] for g, c in counts.items() for _ in range(c)]
        rng.shuffle(runs)
        joins = target
        while joins > 0:
            cands = [(i, j) for i in range(len(runs)) for j in range(i + 1, len(runs)) if runs[i][0] == runs[j][0] and len(runs[i]) + len(runs[j]) <= max_len]
            if not cands:
                break
            i, j = rng.choice(cands)
            runs[i] += runs[j]
            del runs[j]
            joins -= 1
        order = None
        for _ in range(60):
            rng.shuffle(runs)
            if all((a[0] != b[0] for a, b in zip(runs, runs[1:]))):
                order = runs
                break
        if order is None:
            continue
        seq = [g for r in order for g in r]
        gap = abs(sum((a == b for a, b in zip(seq, seq[1:]))) - target) + (10 if max_run(seq) > max_len else 0)
        if best is None or gap < best_gap:
            best, best_gap = (seq, gap)
        if gap == 0:
            break
    return best if best is not None else bag
