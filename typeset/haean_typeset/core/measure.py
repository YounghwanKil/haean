# -*- coding: utf-8 -*-
"""문항 분량 측정. 높이 계산식과 단 높이는 프로필이 준다."""

TIGHT_LINES = 2.0          # 여유 줄이 이보다 적으면 'tight'


def measure_plan(plan, profile, number=None, total=None):
    """→ Measure dict.
    number=None 이면 '그 밖' 자리(프로필 기본 단 높이) 기준."""
    h = profile.item_height(plan)
    cap = profile.capacity(number, total)
    line = profile.line_pt
    spare = (cap - h) / line
    per_block = [{"src": list(p.src), "lines": p.n_lines(), "kind": p.kind} for p in profile.plan_paras(plan)]
    per_block += [{"src": list(x.src), "height_pt": round(getattr(x, "height", 0) or getattr(x, "height_pt", 0), 1),
                   "kind": x.kind} for x in profile.plan_objects(plan)]
    return {
        "lines": sum(b["lines"] for b in per_block if "lines" in b),
        "height_pt": round(h, 1),
        "capacity_pt": round(cap, 1),
        "spare_lines": round(spare, 1),
        "per_block": per_block,
        "verdict": "over" if spare < 0 else "tight" if spare < TIGHT_LINES else "ok",
    }
