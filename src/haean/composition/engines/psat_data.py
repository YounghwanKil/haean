"""PSAT 5급 자료해석 40슬롯 형식·내용 설계의 순수 알고리즘.

관측 규칙·정책·소재 기록은 외부 dict로만 주입한다. 인스턴스마다 복사하며
파일, 환경변수, 원격 저장소를 읽지 않는다. 7급 회차 설계는 지원하지 않는다.
"""

import random
import re
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations

from ._ds_common import (
    copied_ledger, copied_rules, format_input_errors, in_range, max_run,
    required_slot_errors, supported_options,
)

class Engine:

    def __init__(self, *, format_rules: dict, content_rules: dict, content_config: dict,
                 rules_config: dict | None = None, labels: dict | None = None):
        inputs = copied_rules(format_rules=format_rules, content_rules=content_rules, content_config=content_config, rules_config={} if rules_config is None else rules_config, labels={} if labels is None else labels)
        self._rules = inputs['format_rules']
        self._content_rules = inputs['content_rules']
        self._content_config = inputs['content_config']
        self._config = inputs['rules_config']
        self._labels = inputs['labels']
        self._axes = self._rules['axes']
        self._years = [str(y) for y in self._rules['meta']['years']]
        self._core = [str(y) for y in self._rules['meta']['core']]
        self._base = str(self._config['windows']['base_year'])
        self._circ = '①②③④⑤'
        self._heads = self._config['options']['heads']
        self._fams = list(self._config['codes']['fam_names'])
        self._devices = self._config['codes']['devices']
        self._total_axes = ('form', 'fam', 'type', 'diff', 'ans', 'data_kind', 'entity')
        self._count_axes = ('neg',) + tuple(('dev_' + d for d in self._devices))
        self._all_axes = self._total_axes + ('neg', 'nitem', 'tsize') + tuple(('dev_' + d for d in self._devices))
        self._combos = {tuple(c) for c in self._config['combos']}
        self._answer_table = {k: {'allowed': {int(a): n for a, n in v['allowed'].items()}, 'observed': {int(a): n for a, n in v['observed'].items()}} for k, v in self._rules['answer_table'].items()}
        self._pairing = {f: {t: n for t, n in c.items() if t != '종합'} for f, c in self._rules['pairing'].items()}
        self._diff_level = self._config['difficulty_rules']['manuscript_level']
        self._frames = {int(k): v for k, v in self._rules.get('option_frames', {}).get('frames', {}).items()}
        self._statement_rules = self._derive_statement_rules()
        self._block_rules = [(axis, w, code, rule, sum(rule['recent_sum']) or 1) for axis, w in self._config['position_weights'].items() for code, rule in self._rules['blocks'][axis].items()]

    def _block_of(self, slot):
        return (slot - 1) // 10

    def _largest_remainder(self, vals, total):
        base = {k: int(v) for k, v in vals.items()}
        rest = total - sum(base.values())
        order = sorted(vals, key=lambda k: (-(vals[k] - base[k]), -vals[k]))
        for k in order[:max(0, rest)]:
            base[k] += 1
        return base

    def _axis_codes(self, axis):
        return [str(v) for v in self._axes[axis]["values"]]

    def _preset_counts(self, axis, preset, custom=None):
        """축 하나의 목표 개수 {코드: n}. neg·dev_*는 {'neg'|'Y': n}."""
        by = self._axes[axis]["by_year"]
        if preset in ("core", "all"):
            preset = "avg:3" if preset == "core" else "avg:8"
        if preset.startswith("year:"):
            y = preset[5:]
            if y not in self._years:
                raise ValueError(f"{axis}: {y}년은 프리셋에 없음({self._years[0]}~{self._years[-1]})")
            return {c: by[c][y] for c in self._axis_codes(axis)}
        if preset.startswith("avg:"):
            n = int(preset[4:]); ys = self._years[-n:]
            mean = {c: sum(by[c][y] for y in ys) / n for c in self._axis_codes(axis)}
            if axis in self._total_axes:
                return self._largest_remainder(mean, 40)
            if axis in ("nitem", "tsize"):
                return mean  # 상위 축에 맞춰 나중에 정수화
            return {c: round(v) for c, v in mean.items()}
        if preset == "custom":
            if not custom or axis not in custom:
                raise ValueError(f"{axis}=custom 이면 --custom JSON에 \"{axis}\" 값이 있어야 합니다")
            return {str(k): v for k, v in custom[axis].items()}
        raise ValueError(f"프리셋 꼴: year:YYYY · avg:n · core · all · custom (받음 {preset})")

    def _resolve(self, presets=None, custom=None):
        """축별 목표 개수. 하위 축(항목 수·정답 크기)은 상위 축에 비율로 맞춘다."""
        presets = dict(presets or {})
        P = {a: presets.get(a, f"year:{self._base}") for a in self._all_axes}
        T = {a: self._preset_counts(a, P[a], custom) for a in self._all_axes}
        for a in self._total_axes:
            T[a] = {k: int(v) for k, v in T[a].items()}
            if sum(T[a].values()) != 40:
                raise ValueError(f"{a} 합계 {sum(T[a].values())} ≠ 40")
        nG = T["form"]["G"]
        # 항목 수 → ㄱㄴㄷ형 수에 맞춤
        raw = {k: float(v) for k, v in T["nitem"].items()}
        if sum(raw.values()) == 0:
            raw = {k: float(sum(self._axes["nitem"]["by_year"][k].values())) for k in raw}
        s = sum(raw.values())
        T["nitem"] = self._largest_remainder({k: v / s * nG for k, v in raw.items()}, nG)
        # 정답 크기 → 항목 수별 문항 수에 맞춤 (그 해 0건이면 8개년 비율)
        ts = {}
        for n, cnt in T["nitem"].items():
            keys = [k for k in T["tsize"] if k.startswith(f"{n}-")]
            sub = {k: float(T["tsize"][k]) for k in keys}
            if cnt and sum(sub.values()) == 0:
                sub = {k: float(sum(self._axes["tsize"]["by_year"][k].values())) for k in keys}
            tot = sum(sub.values())
            ts.update(self._largest_remainder({k: (v / tot * cnt if tot else 0) for k, v in sub.items()}, cnt) if cnt else {k: 0 for k in keys})
        T["tsize"] = ts
        for a in self._count_axes:
            T[a] = int(list(T[a].values())[0])
        # 충돌 검사
        f = T["fam"]; G = T["form"]["G"]
        lo, hi = f["B"] + f["A"], f["B"] + f["A"] + f["T"] + f["U"]
        errs = []
        if not lo <= G <= hi:
            errs.append(f"ㄱㄴㄷ형 {G}는 (보기형+추가 자료형) {lo} 이상, 여기에 (전환형+밑줄형)을 더한 {hi} 이하여야 합니다")
        if T["neg"] > f["S"] + f["T"] + f["U"]:
            errs.append(f"부정 발문 {T['neg']}이 5지형 설명형·전환형·밑줄형 수를 넘습니다")
        if T["type"].get("종합", 0) != 4:
            errs.append(f"해설서 유형 종합은 4(묶음 2×2)여야 합니다(받음 {T['type'].get('종합')})")
        if T["diff"]["상"] < T["type"].get("수리퀴즈", 0):
            errs.append("수리퀴즈는 모두 상인데 상 개수가 모자랍니다")
        if T["diff"]["하"] < T["type"].get("추가", 0) + 1:
            errs.append("추가 자료형(하)과 1번(하)을 채울 하 개수가 모자랍니다")
        if errs:
            raise ValueError("프리셋 충돌: " + "; ".join(errs))
        return P, T

    def _subsets(self, nitem):
        items = self._heads[:nitem]
        out = []
        for k in range(1, nitem + 1):
            if k == nitem and nitem in self._config["options"]["no_full_for"]:
                continue
            out += ["".join(c) for c in combinations(items, k)]
        return out

    def _sort_key(self, s):
        return (len(s), [self._heads.index(ch) for ch in s])

    def _structure(self, arr, nitem):
        c = Counter(len(s) for s in arr)
        s = "".join(f"{ch}{c[k]}" for k, ch in ((1, "s"), (2, "p"), (3, "t")) if c.get(k) and not (nitem == 3 and k == 3))
        if nitem == 3 and c.get(3):
            s += "a"
        return f"{nitem}:{s}"

    def _options(self, nitem, tsize, ans, true=None, limit=None):
        """규칙 1~3을 지키는 선지 배열 후보(구조 빈도순). true를 주면 정답 선지까지 고정."""
        freq = {k: v["all"] for k, v in self._rules["structure_freq"].items()}
        out = []
        for arr in combinations(self._subsets(nitem), 5):  # combinations는 입력 순서를 지킨다 → 정렬 규칙 자동 충족
            if len(arr[ans - 1]) != tsize or (true and arr[ans - 1] != true):
                continue
            out.append(list(arr))
        out.sort(key=lambda a: (-freq.get(self._structure(a, nitem), 0), a))
        return out[:limit] if limit else out

    def _option_errors(self, arr, nitem, tsize, ans):
        errs = []
        if len(arr) != 5:
            return [f"선지 {len(arr)}개(5개여야)"]
        sets = ["".join(sorted(re.findall(r"[ㄱ-ㅁ]", s), key=self._heads.index)) for s in arr]
        if any(not s or any(ch not in self._heads[:nitem] for ch in s) for s in sets):
            errs.append("선지에 항목 밖 기호")
        if len(set(sets)) != 5:
            errs.append("같은 선지가 둘 이상")
        if [self._sort_key(s) for s in sets] != sorted(self._sort_key(s) for s in sets):
            errs.append("선지 순서 규칙 위반(단일→쌍→삼중→전체, 같은 크기는 ㄱ순)")
        if nitem in self._config["options"]["no_full_for"] and any(len(s) == nitem for s in sets):
            errs.append(f"{nitem}항목형에 전체 선지 금지")
        if tsize and len(sets[ans - 1]) != tsize:
            errs.append(f"정답 {self._circ[ans - 1]} 자리 선지 크기 {len(sets[ans - 1])} ≠ 정답 크기 {tsize}")
        for ch in self._heads[:nitem]:
            if all(ch in s for s in sets):
                errs.append(f"보기 {ch}이 다섯 선지 전부에 들어 있음(풀지 않아도 되는 보기 — 8개년 0건)")
        return errs

    def _window_range(self, by_year, years, kind="range"):
        """연도별 관측값 {연도: 값} → 창(years) 안의 범위. kind: range → [floor(최소), ceil(최대)] · max → ceil(최대) · min → floor(최소). 값이 없으면 None."""
        import math
        vals = [by_year[y] for y in years if y in by_year and by_year[y] is not None]
        if not vals:
            return None
        if kind == "max":
            return math.ceil(max(vals))
        if kind == "min":
            return math.floor(min(vals))
        return [math.floor(min(vals)), math.ceil(max(vals))]

    def _derive_statement_rules(self, rules=None, cfg=None):
        """회차 보기·정답 패턴의 범위를 관측값(format_rules.statement_observed · option_frames.by_year)에서 만든다 — 손으로 적지 않는다.
        all = 8개년(meta.years) 범위, core = 핵심 창(meta.core) 범위. rules_config.statement_rules 는 정책(등급·여유·가중)만."""
        R, C = rules or self._rules, cfg or self._config
        so, by = R.get("statement_observed", {}), R.get("option_frames", {}).get("by_year", {})
        pol = dict(C.get("statement_rules", {}))
        years, core = [str(y) for y in R["meta"]["years"]], [str(y) for y in R["meta"]["core"]]
        if not so or not by:
            return pol
        ratio = {y: v[0] / v[1] for y, v in so["g_true"].items() if v and v[1]}
        out = {k: v for k, v in pol.items() if not k.startswith("_")}
        out["g_true_ratio"] = {**pol.get("g_true_ratio", {}), "warn": [round(min(ratio[y] for y in years if y in ratio), 2), round(max(ratio[y] for y in years if y in ratio), 2)]}
        out["ans_without_g"] = {"core": self._window_range(so["ans_without_g"], core), "all": self._window_range(so["ans_without_g"], years)}
        out["ans_gd_max"] = {"core": self._window_range(so["ans_gd"], core, "max"), "all": self._window_range(so["ans_gd"], years, "max")}
        out["frame_repeat_max"] = {"core": self._window_range(by["max_repeat"], core, "max"), "all": self._window_range(by["max_repeat"], years, "max")}
        out["distinct_frames_min"] = self._window_range(by["distinct"], years, "min") - int(pol.get("distinct_frames_slack", 0))
        out["distinct_frames_observed_min"] = self._window_range(by["distinct"], years, "min")
        return out

    def _frame_key(self, arr):
        return "|".join(arr)

    def _pick_options(self, rng, nitem, tsize, ans, used=None, true=None):
        """정답 자리(ans)에 크기 tsize인 선지가 오는 관측 틀 중에서 빈도 가중 추출. 같은 회차에서 이미 쓴 틀은 감점.
        관측 틀이 없는 짝(항목 수·정답 크기·정답 번호)은 규칙 1~3을 지키는 조합 생성(options)에서 고른다."""
        used = used if used is not None else Counter()
        pen = self._statement_rules.get("frame_reuse_penalty", 0.25)
        cands = [(f["frame"], f["all"] + 0.5) for f in self._frames.get(nitem, [])
                 if len(f["frame"][ans - 1]) == tsize and (true is None or f["frame"][ans - 1] == true)
                 and not self._option_errors(f["frame"], nitem, tsize, ans)]
        if not cands:
            pool = [a for a in self._options(nitem, tsize, ans, true=true, limit=40) if not self._option_errors(a, nitem, tsize, ans)]
            if not pool:
                return self._options(nitem, tsize, ans, true=true, limit=1)[0]
            cands = [(a, 1.0) for a in pool]
        weights = [w * (pen ** used.get(self._frame_key(a), 0)) for a, w in cands]
        pick = self._wsample(rng, [a for a, _ in cands], weights, 1)[0]
        used[self._frame_key(pick)] += 1
        return list(pick)

    def _statement_issues(self, S, level="all"):
        """회차 단위 ㄱㄴㄷ형 보기·정답 패턴 → (오류, 경고). 기준은 rules_config.statement_rules(8개년 관측 범위)."""
        E, W = [], []
        G = [s for s in S if s["form"] == "G" and s.get("options")]
        if not G or not self._statement_rules:
            return E, W
        sets = {s["slot"]: ["".join(sorted(re.findall(r"[ㄱ-ㅁ]", str(o)), key=self._heads.index)) for o in s["options"]] for s in G}
        ans_set = {n: st[s["ans"] - 1] if 0 < s["ans"] <= len(st) else "" for s in G for n, st in ((s["slot"], sets[s["slot"]]),)}
        g_true = sum(1 for v in ans_set.values() if "ㄱ" in v)
        ratio = g_true / len(G)
        r = self._statement_rules["g_true_ratio"]["warn"]   # 틀 × 정답 자리에서 따라 나오는 값 — 경고만
        if not in_range(ratio, r): W.append(f"ㄱ 참 비율 {g_true}/{len(G)}={ratio:.2f} ∉ 8개년 {r}(선지 틀·정답 분포를 먼저 본다)")
        without = sum(1 for v in ans_set.values() if "ㄱ" not in v)
        r = self._statement_rules["ans_without_g"]
        if not in_range(without, r["all"]): E.append(f"정답에 ㄱ 없는 문항 {without}개 ∉ 8개년 {r['all']}")
        elif not in_range(without, r["core"]): W.append(f"정답에 ㄱ 없는 문항 {without}개 ∉ 핵심 {r['core']}")
        gd = sum(1 for v in ans_set.values() if v == "ㄱㄷ")
        if gd > self._statement_rules["ans_gd_max"]["all"]: E.append(f"정답 'ㄱ, ㄷ' {gd}개 > 8개년 최대 {self._statement_rules['ans_gd_max']['all']}")
        elif gd > self._statement_rules["ans_gd_max"]["core"]: W.append(f"정답 'ㄱ, ㄷ' {gd}개 > 핵심 최대 {self._statement_rules['ans_gd_max']['core']}")
        frames = Counter(self._frame_key(st) for st in sets.values())
        top, n = frames.most_common(1)[0]
        if n > self._statement_rules["frame_repeat_max"]["all"]: E.append(f"같은 선지 틀 {top} {n}회(8개년 최대 {self._statement_rules['frame_repeat_max']['all']})")
        elif n > self._statement_rules["frame_repeat_max"]["core"]: W.append(f"같은 선지 틀 {top} {n}회(핵심 최대 {self._statement_rules['frame_repeat_max']['core']})")
        if len(G) >= 15 and len(frames) < self._statement_rules.get("distinct_frames_min", 10):
            W.append(f"서로 다른 선지 틀 {len(frames)}가지(8개년 최소 {self._statement_rules.get('distinct_frames_observed_min', '?')})")
        groups = defaultdict(list)
        for s in S:
            if s.get("bundle"):
                groups[s["bundle"]].append(s)
        for b, items in groups.items():
            if len(items) == 2 and items[0]["fam"] == items[1]["fam"]:
                W.append(f"묶음 {b}({items[0]['slot']}·{items[1]['slot']}번) 두 문항 발문 계열이 같음({items[0]['fam']}) — 2020~2026 14묶음 0건")
        return E, W

    def _wsample(self, rng, items, weights, k):
        """가중 비복원 추출."""
        items, weights, out = list(items), list(weights), []
        for _ in range(min(k, len(items))):
            tot = sum(weights)
            if tot <= 0:
                i = rng.randrange(len(items))
            else:
                r, acc, i = rng.random() * tot, 0.0, 0
                for i, w in enumerate(weights):
                    acc += w
                    if acc >= r:
                        break
            out.append(items.pop(i)); weights.pop(i)
        return out

    def _match_types(self, free, types, rng):
        """문항 ↔ 유형 자리 완전 매칭(관측된 짝만). 순서는 짝 빈도 가중 무작위. 실패하면 None."""
        import math
        owner = [None] * len(types)          # 유형 자리 → 문항 번호
        def key(i, t):
            w = self._pairing.get(free[i]["fam"], {}).get(t, 0)
            return -math.log(rng.random() + 1e-12) / w if w else None
        def augment(i, seen):
            cands = [(key(i, t), k) for k, t in enumerate(types) if self._pairing.get(free[i]["fam"], {}).get(t) and k not in seen]
            for _, k in sorted(cands):
                seen.add(k)
                if owner[k] is None or augment(owner[k], seen):
                    owner[k] = i
                    return True
            return False
        order = list(range(len(free))); rng.shuffle(order)
        order.sort(key=lambda i: len(self._pairing.get(free[i]["fam"], {})))
        for i in order:
            if not augment(i, set()):
                return None
        out = [None] * len(free)
        for k, i in enumerate(owner):
            out[i] = types[k]
        return out

    def _build_items(self, T, rng):
        """번호 없이 40문항의 속성 묶음을 만든다(묶음 4문항 포함)."""
        f = T["fam"]; G = T["form"]["G"]
        need = G - f["B"] - f["A"]
        for _ in range(500):
            eT = f["T"] * self._config["form_split"]["T"][0] / self._config["form_split"]["T"][1]
            gT = min(f["T"], max(0, need - f["U"], int(eT + rng.random())))
            gU = need - gT
            if not 0 <= gU <= f["U"]:
                continue
            uF = f["U"] - gU
            if uF <= T["neg"] <= f["S"] + (f["T"] - gT) + uF:
                break
        else:
            raise ValueError("전환형·밑줄형의 ㄱㄴㄷ/5지 나누기 실패(부정 발문 수와 맞지 않음)")
        items = []
        for fam, n in f.items():
            forms = self._config["fam_form"][fam]
            for k in range(n):
                form = forms[0] if len(forms) == 1 else ("G" if k < (gT if fam == "T" else gU) else "F")
                items.append({"fam": fam, "form": form, "neg": False})
        # 부정: 5지 밑줄형 먼저, 나머지는 설명형·5지 전환형에 비율대로
        for it in items:
            if it["fam"] == "U" and it["form"] == "F":
                it["neg"] = True
        r = T["neg"] - sum(it["neg"] for it in items)
        pool = [it for it in items if (it["fam"] == "S") or (it["fam"] == "T" and it["form"] == "F")]
        wS = self._config["neg_ratio"]["S"][0] / self._config["neg_ratio"]["S"][1]; wT = self._config["neg_ratio"]["TF"][0] / self._config["neg_ratio"]["TF"][1]
        for it in self._wsample(rng, pool, [wS if it["fam"] == "S" else wT for it in pool], r):
            it["neg"] = True
        # 묶음 4문항(계열 가중) + 해설서 유형(계열과 관측된 짝만, 짝 빈도 가중). 완전 매칭이 될 때까지 묶음을 다시 고른다
        bw = self._config["bundles"]["fam_weight"]
        rest_types = []
        for t, n in T["type"].items():
            if t != "종합":
                rest_types += [t] * n
        for _ in range(300):
            for it in items:
                it.pop("type", None)
            bundle = self._wsample(rng, items, [bw.get(it["fam"], 0) + 0.01 for it in items], 4)
            if max(Counter(it["fam"] for it in bundle).values()) >= 3:
                continue   # 묶음 두 문항은 발문 계열이 다르다(2020~2026 14묶음 0건) — 3개 이상 같은 계열이면 짝을 못 나눈다
            for it in bundle:
                it["type"] = "종합"
            free = [it for it in items if "type" not in it]
            got = self._match_types(free, rest_types, rng)
            if got is not None:
                for it, t in zip(free, got):
                    it["type"] = t
                break
        else:
            raise ValueError("해설서 유형 배정 실패: 계열과 관측된 짝이 모자람(프리셋의 계열·유형 조합을 확인)")
        # 난이도: 추가=하, 수리퀴즈=상, 나머지 무작위
        diffs = []
        for d, n in T["diff"].items():
            diffs += [d] * n
        fixed = self._config["difficulty_rules"]["type_fixed"]
        for it in items:
            if it["type"] in fixed:
                it["diff"] = fixed[it["type"]]; diffs.remove(it["diff"])
        rng.shuffle(diffs)
        for it in items:
            if "diff" not in it:
                it["diff"] = diffs.pop()
        # 항목 수·정답 크기(ㄱㄴㄷ형). 5항목은 밑줄형에만 관측
        pairs = []
        for k, n in T["tsize"].items():
            pairs += [tuple(map(int, k.split("-")))] * n
        G_items = [it for it in items if it["form"] == "G"]
        rng.shuffle(pairs)
        pairs.sort(key=lambda p: -p[0])
        G_items.sort(key=lambda it: 0 if it["fam"] == "U" else 1)
        for it, (n, ts) in zip(G_items, pairs):
            it["nitem"], it["tsize"] = n, ts
        for it in items:
            it.setdefault("nitem", None); it.setdefault("tsize", None)
        # 자료 구성: 없음 → 전환형 우선, 표+그림 → 표와 그림 유형 우선
        kinds = dict(T["data_kind"])
        for it in sorted(items, key=lambda it: (it["fam"] != "T", rng.random())):
            if kinds.get("없음", 0) and it["fam"] == "T" and it["type"] != "종합":
                it["data_kind"] = "없음"; kinds["없음"] -= 1
        for it in sorted(items, key=lambda it: (it["type"] != "표그림", rng.random())):
            if "data_kind" not in it and kinds.get("표+그림", 0) and it["type"] == "표그림":
                it["data_kind"] = "표+그림"; kinds["표+그림"] -= 1
        rest = []
        for k, n in kinds.items():
            rest += [k] * n
        rng.shuffle(rest)
        rest.sort(key=lambda k: k == "없음")
        for it in items:
            if "data_kind" not in it:
                it["data_kind"] = rest.pop(0)
        # 주체
        ents = []
        for k, n in T["entity"].items():
            ents += [k] * n
        rng.shuffle(ents)
        for it, e in zip(items, ents):
            it["entity"] = e
        # 장치
        for it in items:
            it["devices"] = []
        aff = self._config["device_affinity"]
        for d in self._devices:
            n = T["dev_" + d]
            A = aff.get(d, {})
            def score(it):
                if it["data_kind"] in A.get("not_data_kind", []):
                    return 0.0
                s = 0.3 + A.get("fam", {}).get(it["fam"], 0) + A.get("type", {}).get(it["type"], 0) + A.get("data_kind", {}).get(it["data_kind"], 0)
                if d == "보고서" and it["fam"] in ("U", "A", "K"):
                    s += 50
                if d == "복수자료" and it["data_kind"] == "표+그림":
                    s += 50
                return s
            cands = [it for it in items if score(it) > 0]
            for it in self._wsample(rng, cands, [score(it) for it in cands], n):
                it["devices"].append(d)
        # 선지 형태
        for it in items:
            sh = self._config["shapes"][f"{it['fam']}|{it['form']}"]
            it["shape"] = self._wsample(rng, list(sh), list(sh.values()), 1)[0]
        return items

    def _bundle_positions(self, rng, level="core"):
        B = self._config["bundles"]
        for _ in range(1000):
            s1 = rng.randint(*B["first_start"][level]); s2 = rng.randint(*B["second_start"][level])
            if s2 >= s1 + 2 and in_range(s2 - s1, B["gap"][level]) and s2 + 1 <= 40:
                return s1, s2
        raise ValueError("묶음 위치를 정하지 못함")

    def _bundle_fits(self, pairs_at):
        """묶음 문항(움직일 수 없음)의 계열·형식·부정이 그 블록의 8개년·핵심 범위를 넘지 않는지 → (오류 수, 경고 수)"""
        cnt = Counter()
        for start, pair in pairs_at:
            for k, it in enumerate(pair):
                b = self._block_of(start + k)
                for axis in ("fam", "form", "neg"):
                    v = self._axis_value(it, axis)
                    if v is not None:
                        cnt[(axis, v, b)] += 1
        e = w = 0
        for (axis, v, b), n in cnt.items():
            rule = self._rules["blocks"][axis].get(v)
            if rule and n > rule["all"][b][1]:
                e += 1
            elif rule and n > rule["core"][b][1]:
                w += 1
        return e, w

    def _bundle_layout(self, bund, rng):
        """묶음 위치와 짝 나누기: 묶음 문항이 놓일 블록 범위를 넘지 않는 것 중 경고가 적은 것."""
        best = None
        splits = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]
        for _ in range(200):
            s1, s2 = self._bundle_positions(rng)
            a, b = rng.choice(splits)
            p1, p2 = [bund[i] for i in a], [bund[i] for i in b]
            if p1[0]["fam"] == p1[1]["fam"] or p2[0]["fam"] == p2[1]["fam"]:
                continue   # 한 묶음 안 두 문항은 계열이 다르게
            if rng.random() < 0.5:
                p1, p2 = p2, p1
            rng.shuffle(p1); rng.shuffle(p2)
            e, w = self._bundle_fits([(s1, p1), (s2, p2)])
            if best is None or (e, w) < best[0]:
                best = ((e, w), (s1, s2, p1, p2))
            if (e, w) == (0, 0):
                break
        return best[1]

    def _block_penalty(self, order):
        """order: 번호 1~40의 문항 목록. 낮을수록 좋다(8개년 범위 밖 100, 핵심 밖 4w, 2024~26 블록 비율과의 차이)."""
        cnt = defaultdict(lambda: [0, 0, 0, 0])
        for i, it in enumerate(order):
            b = i // 10
            cnt[("diff", it["diff"])][b] += 1; cnt[("fam", it["fam"])][b] += 1; cnt[("form", it["form"])][b] += 1
            cnt[("type", it["type"])][b] += 1
            if it["neg"]:
                cnt[("neg", "neg")][b] += 1
        pen = 0.0
        for axis, w, code, rule, rs in self._block_rules:
            c = cnt.get((axis, code), (0, 0, 0, 0)); tot = sum(c)
            for b in range(4):
                if not rule["all"][b][0] <= c[b] <= rule["all"][b][1]:
                    pen += 100
                elif not rule["core"][b][0] <= c[b] <= rule["core"][b][1]:
                    pen += 10
                pen += w * 0.15 * (c[b] - tot * rule["recent_sum"][b] / rs) ** 2
        if order[0]["diff"] != "하":
            pen += 200
        pen += 6 * sum(1 for it in order[:20] if it["diff"] == "상")
        pen += 200 * max(0, sum(1 for it in order[:10] if it["diff"] == "상") - 1)
        pen += 200 * sum(1 for it in order[30:] if it["fam"] == "A")
        return pen

    def _axis_value(self, it, axis):
        if axis == "neg":
            return "neg" if it["neg"] else None
        return str(it[axis])

    def _block_ok(self, it, b):
        """이 문항이 블록 b에 놓여도 8개년 범위(상한 0)를 어기지 않는지(계열·형식·유형 기준)."""
        for axis in ("fam", "form", "type"):
            rule = self._rules["blocks"][axis].get(self._axis_value(it, axis))
            if rule and rule["all"][b][1] == 0:
                return False
        return True

    def _initial_fill(self, order, free, rest, rng):
        """놓을 수 있는 블록이 적은 문항부터 자리를 잡는다. 1번은 하."""
        slots = {b: [i for i in free if i // 10 == b] for b in range(4)}
        for b in slots:
            rng.shuffle(slots[b])
        items = sorted(rest, key=lambda it: (sum(self._block_ok(it, b) for b in range(4)), rng.random()))
        if 0 in free:
            first = next((it for it in items if it["diff"] == "하" and self._block_ok(it, 0)), None)
            if first:
                items = [x for x in items if x is not first]
                order[0] = first; slots[0].remove(0)
        for it in items:
            ok = [b for b in range(4) if slots[b] and self._block_ok(it, b)] or [b for b in range(4) if slots[b]]
            b = max(ok, key=lambda b: (len(slots[b]), rng.random()))
            order[slots[b].pop()] = it

    def _place(self, items, rng, iters=6000):
        bund = [it for it in items if it["type"] == "종합"]
        rest = [it for it in items if it["type"] != "종합"]
        best = None
        for attempt in range(12):
            if attempt >= 4 and best[0] < 100:   # 8개년 범위 위반이 없으면 4회로 충분
                break
            s1, s2, pair1, pair2 = self._bundle_layout(bund, rng)
            rng.shuffle(rest)
            order = [None] * 40
            for a, b in ((s1, pair1), (s2, pair2)):
                order[a - 1], order[a] = b
            free = [i for i in range(40) if order[i] is None]
            self._initial_fill(order, free, rest, rng)
            cur = self._block_penalty(order)
            run_best = (cur, [dict(x) for x in order])
            T0 = 5.0
            fixed = self._config["difficulty_rules"]["type_fixed"]
            for n in range(iters):
                if rng.random() < 0.6:   # 자리 바꾸기(묶음 밖)
                    i, j = rng.sample(free, 2)
                    order[i], order[j] = order[j], order[i]
                    kind = "pos"
                else:                    # 난이도 바꾸기(추가=하·수리퀴즈=상 고정 문항 제외) — 난이도는 위치 경향을 따른다
                    i, j = rng.sample(range(40), 2)
                    if order[i]["type"] in fixed or order[j]["type"] in fixed:
                        continue
                    order[i]["diff"], order[j]["diff"] = order[j]["diff"], order[i]["diff"]
                    kind = "diff"
                p = self._block_penalty(order)
                temp = T0 * (1 - n / iters) + 0.01
                if p <= cur or rng.random() < pow(2.718, (cur - p) / temp):
                    cur = p
                    if p < run_best[0]:
                        run_best = (p, [dict(x) for x in order])
                elif kind == "pos":
                    order[i], order[j] = order[j], order[i]
                else:
                    order[i]["diff"], order[j]["diff"] = order[j]["diff"], order[i]["diff"]
            if best is None or run_best[0] < best[0]:
                best = (run_best[0], run_best[1], (s1, s2))
        return best[1], best[2]

    def _assign_answers(self, order, T, rng, tries=6000):
        target = {int(k): v for k, v in T["ans"].items()}
        AR = self._config["answer_rules"]
        best = None
        idx = list(range(40))
        for _ in range(tries):
            left = dict(target); ans = [None] * 40
            # 선택지가 적은 자리부터
            def allowed(i):
                it = order[i]
                if it["form"] == "G":
                    obs = self._answer_table[f"{it['nitem']}-{it['tsize']}"]["observed"]
                    return [a for a in obs if obs[a] > 0]
                return [1, 2, 3, 4, 5]
            seq = sorted(idx, key=lambda i: (len(allowed(i)), rng.random()))
            ok = True
            for i in seq:
                al = [a for a in allowed(i) if left.get(a, 0) > 0]
                if not al:
                    ok = False; break
                it = order[i]
                if it["form"] == "G":
                    obs = self._answer_table[f"{it['nitem']}-{it['tsize']}"]["observed"]
                    w = [obs[a] + 0.5 for a in al]
                else:
                    w = [left[a] for a in al]
                a = self._wsample(rng, al, w, 1)[0]
                ans[i] = a; left[a] -= 1
            if not ok:
                continue
            run = max_run(ans)
            same = sum(1 for a, b in zip(ans, ans[1:]) if a == b)
            bmax = max(Counter(ans[b * 10:(b + 1) * 10]).most_common(1)[0][1] for b in range(4))
            score = (max(0, run - AR["max_run"]["all"]) * 100 + max(0, bmax - AR["block_max"]["all"][1]) * 100
                     + (0 if in_range(same, AR["same_as_prev"]["all"]) else 50)
                     + max(0, run - AR["max_run"]["core"]) * 5 + (0 if in_range(same, AR["same_as_prev"]["core"]) else 5))
            if best is None or score < best[0]:
                best = (score, ans)
            if score == 0:
                break
        if best is None:
            raise ValueError("정답 배치 실패: 정답 크기와 정답 번호 쿼터가 맞지 않음")
        for it, a in zip(order, best[1]):
            it["ans"] = a

    def _stem_for(self, it):
        key = f"{it['fam']}|{it['form']}|{'Y' if it['neg'] else 'N'}"
        t = self._config["templates"][key]
        return t

    def _sample_impl(self, seed=0, presets=None, custom=None, tries=8):
        """검증 오류 0인 설계를 낸다. 첫 시도는 random.Random(seed), 오류가 남으면 seed에서 이어지는 시도로 다시 뽑는다."""
        last = None
        for k in range(tries):
            d = self._sample_once(random.Random(seed if k == 0 else f"{seed}-{k}"), seed, presets, custom)
            E, _, _ = self._validate_impl(d)
            if not E:
                if k:
                    d["meta"]["retry"] = k
                return d
            last = (d, E)
        last[0]["meta"]["errors"] = last[1]
        return last[0]

    def _sample_once(self, rng, seed, presets, custom):
        P, T = self._resolve(presets, custom)
        items = self._build_items(T, rng)
        order, (s1, s2) = self._place(items, rng)
        self._assign_answers(order, T, rng)
        slots = []
        used = Counter()   # 회차 안에서 쓴 선지 틀(반복 감점)
        for n, it in enumerate(order, 1):
            b = "가" if n in (s1, s1 + 1) else "나" if n in (s2, s2 + 1) else None
            s = {"slot": n, "bundle": b, "fam": it["fam"], "fam_name": self._config["codes"]["fam_names"][it["fam"]], "form": it["form"],
                 "neg": it["neg"], "type": it["type"], "diff": it["diff"], "nitem": it["nitem"], "tsize": it["tsize"], "ans": it["ans"],
                 "shape": it["shape"], "data_kind": it["data_kind"], "devices": sorted(it["devices"], key=self._devices.index),
                 "entity": it["entity"], "stem": self._stem_for(it), "options": None, "notes": []}
            if it["form"] == "G":
                s["options"] = self._pick_options(rng, it["nitem"], it["tsize"], it["ans"], used)
            slots.append(s)
        return {"meta": {"rules": self._rules["meta"]["version"], "seed": seed, "size": 40, "presets": P}, "slots": slots}

    def _totals(self, S):
        t = {
            "form": Counter(s["form"] for s in S), "fam": Counter(s["fam"] for s in S), "type": Counter(s["type"] for s in S),
            "diff": Counter(s["diff"] for s in S), "ans": Counter(str(s["ans"]) for s in S), "data_kind": Counter(s["data_kind"] for s in S),
            "entity": Counter(s["entity"] for s in S), "nitem": Counter(str(s["nitem"]) for s in S if s["form"] == "G"),
            "tsize": Counter(f"{s['nitem']}-{s['tsize']}" for s in S if s["form"] == "G"),
            "neg": Counter({"neg": sum(1 for s in S if s["neg"])}),
        }
        for d in self._devices:
            t["dev_" + d] = Counter({"Y": sum(1 for s in S if d in s.get("devices", []))})
        return t

    def _validate_impl(self, design, presets=None, custom=None, skip=()):
        """→ (errors, warnings, infos). skip: 검사하지 않을 축(기출 되돌려 적용 때 엑셀에 없는 축)."""
        S = design["slots"]; E, W, I = [], [], []
        if len(S) != 40:
            return [f"문항 {len(S)}개(40개여야)"], [], []
        # 결합
        for s in S:
            if (s["fam"], s["form"], bool(s["neg"])) not in self._combos:
                E.append(f"{s['slot']}번 계열·형식·부정 결합 {s['fam']}·{s['form']}·{'부정' if s['neg'] else '긍정'}은 8개년에 없음")
        # 묶음
        groups = defaultdict(list)
        for s in S:
            if s.get("bundle"):
                groups[s["bundle"]].append(s["slot"])
        starts = sorted(min(v) for v in groups.values())
        if len(groups) != 2 or any(len(v) != 2 or max(v) - min(v) != 1 for v in groups.values()):
            E.append(f"공통 자료 묶음은 2개, 각 연속 2문항(받음 {dict(groups)})")
        else:
            B = self._config["bundles"]
            for name, val, lv in (("첫 묶음 시작", starts[0], "first_start"), ("둘째 묶음 시작", starts[1], "second_start"),
                                  ("두 묶음 간격", starts[1] - starts[0], "gap")):
                if not in_range(val, B[lv]["all"]): E.append(f"{name} {val} ∉ {B[lv]['all']}")
                elif not in_range(val, B[lv]["core"]): W.append(f"{name} {val} ∉ 핵심 {B[lv]['core']}")
        n_comp = sum(1 for s in S if s["type"] == "종합")
        if n_comp != 4: E.append(f"해설서 유형 종합 {n_comp}개(4개여야)")
        for s in S:
            if (s["type"] == "종합") != bool(s.get("bundle")):
                W.append(f"{s['slot']}번 종합은 묶음 문항(결합 경고)")
        # 합계
        tot = self._totals(S)
        for axis in self._all_axes:
            if axis in skip:
                continue
            for c in self._axis_codes(axis) if axis not in self._count_axes else ["neg" if axis == "neg" else "Y"]:
                if axis in self._count_axes:
                    core, alls, label = self._axes[axis]["core"][list(self._axes[axis]["core"])[0]], self._axes[axis]["all"][list(self._axes[axis]["all"])[0]], axis
                else:
                    core, alls, label = self._axes[axis]["core"][c], self._axes[axis]["all"][c], f"{axis} {self._axes[axis]['labels'][c]}"
                v = tot[axis].get(c, 0)
                if not in_range(v, alls): E.append(f"합계 {label} {v} ∉ 8개년 {alls}")
                elif not in_range(v, core): W.append(f"합계 {label} {v} ∉ 핵심 {core}")
        # ㄱㄴㄷ 세부
        for s in S:
            if s["form"] != "G":
                if s.get("nitem"): E.append(f"{s['slot']}번 5지형에 항목 수")
                continue
            key = f"{s['nitem']}-{s['tsize']}"
            if key not in self._answer_table:
                E.append(f"{s['slot']}번 {s['nitem']}항목·정답 크기 {s['tsize']}는 불가(전체 선지 금지 등)"); continue
            if s["ans"] not in self._answer_table[key]["allowed"]:
                E.append(f"{s['slot']}번 {key} 정답 {self._circ[s['ans'] - 1]} 불가(정답 자리 크기)")
            elif not self._answer_table[key]["observed"].get(s["ans"]):
                W.append(f"{s['slot']}번 {key}·{self._circ[s['ans'] - 1]}은 8개년 미관측 짝(결합 경고)")
            if s.get("options"):
                for e in self._option_errors(s["options"], s["nitem"], s["tsize"], s["ans"]):
                    E.append(f"{s['slot']}번 선지배열: {e}")
        # 회차 단위 보기·정답 패턴(ㄱ 없는 정답·'ㄱ,ㄷ' 쏠림·틀 반복·묶음 계열 — ㄱ 참 비율은 경고)
        se, sw = self._statement_issues(S)
        E += se; W += sw
        # 블록 위치
        order = [{"diff": s["diff"], "fam": s["fam"], "form": s["form"], "neg": s["neg"], "type": s["type"]} for s in S]
        for axis, B in self._rules["blocks"].items():
            if axis in skip:
                continue
            for code, rule in B.items():
                for b in range(4):
                    n = sum(1 for it in order[b * 10:(b + 1) * 10] if self._axis_value(it, axis) == code)
                    lab = f"{b * 10 + 1}~{b * 10 + 10}번 {axis} {code}"
                    if not in_range(n, rule["all"][b]): E.append(f"블록 위치 {lab} {n} ∉ 8개년 {rule['all'][b]}")
                    elif not in_range(n, rule["core"][b]): W.append(f"블록 위치 {lab} {n} ∉ 핵심 {rule['core'][b]}")
        if "diff" not in skip:
            if S[0]["diff"] != "하": E.append("1번은 하(8개년 8/8)")
            front = [s["slot"] for s in S[:10] if s["diff"] == "상"]
            if len(front) >= 2: E.append(f"1~10번 상 {len(front)}개")
            early = [s["slot"] for s in S[:20] if s["diff"] == "상"]
            if early: W.append(f"상은 21번 이후 권장(현재 {early})")
            for s in S:
                fixed = self._config["difficulty_rules"]["type_fixed"].get(s["type"])
                if fixed and s["diff"] != fixed: W.append(f"{s['slot']}번 {s['type']}은 8개년 모두 {fixed}")
        for fam, (a, b) in self._config["forbidden_positions"].items():
            for s in S[a - 1:b]:
                if s["fam"] == fam: E.append(f"{s['slot']}번 {self._config['codes']['fam_names'][fam]}은 {a}~{b}번 8개년 0건")
        # 정답
        AR = self._config["answer_rules"]
        ans = [s["ans"] for s in S]
        c = Counter(ans)
        for k in range(1, 6):
            if not in_range(c[k], AR["per_number"]["all"]): E.append(f"정답 {self._circ[k - 1]} {c[k]}개 ∉ {AR['per_number']['all']}")
        for b in range(4):
            m = Counter(ans[b * 10:(b + 1) * 10]).most_common(1)[0][1]
            if m > AR["block_max"]["all"][1]: E.append(f"{b * 10 + 1}~{b * 10 + 10}번 한 정답 {m}개(4개 이하)")
        run = max_run(ans)
        if run > AR["max_run"]["all"]: E.append(f"같은 정답 {run}연속")
        elif run > AR["max_run"]["core"]: W.append(f"같은 정답 {run}연속(핵심 ≤{AR['max_run']['core']})")
        same = sum(1 for x, y in zip(ans, ans[1:]) if x == y)
        if not in_range(same, AR["same_as_prev"]["all"]): E.append(f"앞 문항과 같은 정답 {same}회 ∉ {AR['same_as_prev']['all']}")
        elif not in_range(same, AR["same_as_prev"]["core"]): W.append(f"앞 문항과 같은 정답 {same}회 ∉ 핵심 {AR['same_as_prev']['core']}")
        # 결합 경고: 계열×유형 짝, 장치
        for s in S:
            if s["type"] != "종합" and not self._pairing.get(s["fam"], {}).get(s["type"]):
                W.append(f"{s['slot']}번 {s['fam']}·{s['type']}는 8개년 미관측 짝")
            if "devices" in s and "dev_보고서" not in skip:
                if s["fam"] in ("U", "A", "K") and "보고서" not in s["devices"]:
                    W.append(f"{s['slot']}번 {self._config['codes']['fam_names'][s['fam']]}인데 글 자료(보고서) 없음")
                if s["data_kind"] == "없음" and "빈칸" in s["devices"]:
                    W.append(f"{s['slot']}번 자료 구성 없음인데 표 안 빈칸")
                if s["data_kind"] == "표+그림" and "복수자료" not in s["devices"]:
                    W.append(f"{s['slot']}번 표+그림인데 복수자료 아님")
        # 정보: 프리셋과 다른 칸
        if presets is not None:
            P, Tg = self._resolve(presets, custom)
            for axis in self._total_axes:
                for k, v in Tg[axis].items():
                    if tot[axis].get(str(k), 0) != v:
                        I.append(f"{axis} {k}: 설계 {tot[axis].get(str(k), 0)} ≠ 프리셋 {v}")
        return E, W, I

    # Content specifications retain the upstream slot schema.

    def _allocate_fields(self, slots, rng):
        """§15.1 8개년 분포 비례로 소재 분야를 배분. 묶음 두 문항은 한 분야, 같은 분야 연속 ≤ 2."""
        units = []  # 묶음은 한 단위
        k = 0
        while k < len(slots):
            if slots[k].get("bundle") and k + 1 < len(slots) and slots[k + 1].get("bundle") == slots[k]["bundle"]:
                units.append([slots[k]["slot"], slots[k + 1]["slot"]]); k += 2
            else:
                units.append([slots[k]["slot"]]); k += 1
        dist = {f: n for f, n in self._content_rules["field_dist"].items() if not f.startswith("기타")}
        tot = sum(dist.values())
        alloc = self._largest_remainder({f: n / tot * len(units) for f, n in dist.items()}, len(units))
        bag = [f for f, n in alloc.items() for _ in range(n)]
        best = None
        for _ in range(500):
            rng.shuffle(bag)
            seq = [f for u, f in zip(units, bag) for _ in u]
            run = max_run(seq)
            if best is None or run < best[0]:
                best = (run, list(bag))
            if run <= self._content_config["adjacency"]["max_same_field_consecutive"]:
                break
        out = {}
        for u, f in zip(units, best[1]):
            for s in u:
                out[s] = f
        return out, alloc

    def _m20_index(self):
        by_field = {}
        for m in self._content_rules["m20_materials"]:
            by_field.setdefault(m["field"], []).append(m)
        return by_field

    def _design_slot(self, s, field, rng, by_field, ledger_entries):
        calc = self._content_rules["calc_by_type"].get(s["type"], {})
        calc_pick = self._wsample(rng, list(calc), list(calc.values()), min(2, len(calc))) if calc else []
        chart = None
        if s["data_kind"] in ("그림만", "표+그림"):
            ck = self._content_rules["chart_kinds"]; chart = self._wsample(rng, list(ck), list(ck.values()), 1)[0]
        same = [m for m in by_field.get(field, []) if m["year"] >= self._rules["meta"]["core"][0]]
        same_type = [m for m in same if m["type"] == s["type"]]
        avoid = [f"{m['id']} {m['material']} ({m['keywords']})" for m in (same_type + [m for m in same if m not in same_type])[:8]]
        avoid_ledger = [f"{e.get('회차')}-{e.get('slot')} {e.get('material')}" for e in ledger_entries if e.get("area") in (field, None)][:8]
        knobs = self._content_config["difficulty_knobs"][s["diff"]]
        cands = sorted(self._content_rules["m20_materials"], key=lambda m: (-m["year"], m["slot"]))
        refs = ([m["id"] for m in cands if m["type"] == s["type"] and m["form"] == s["form"]] or [m["id"] for m in cands if m["type"] == s["type"]])[:3]
        if s["form"] == "G":
            true = s["options"][s["ans"] - 1]
            statements = []
            for h in self._heads[:s["nitem"]]:
                ok = h in true
                how = (f"참 — {calc_pick[-1] if calc_pick else '계산'}으로 닫히게" if ok
                       else f"거짓 — 함정 '{rng.choice(self._content_config['traps'])}' 또는 경계값 근처 계산으로 틀리게")
                statements.append({"보기": h, "진위": "○" if ok else "×", "설계": how})
        else:
            statements = [{"선지": self._circ[k], "역할": ("정답" if k + 1 == s["ans"] else "오답"),
                           "설계": ("발문이 부정이면 이 선지만 틀림" if s["neg"] else "이 선지만 맞음") if k + 1 == s["ans"] else rng.choice(self._content_config["traps"]) + " 함정 후보"}
                          for k in range(5)]
        return {
            "slot": s["slot"], "묶음": s.get("bundle"), "계열": f"{s['fam']} {s['fam_name']}", "해설서유형": s["type"], "난이도": s["diff"],
            "소재": {"분야": field, "주체": s["entity"], "주체_지침": self._content_config["entity"][s["entity"]],
                    "범위": f"{field} 분야의 {'가상' if s['entity'] == '가상' else '실제'} 통계 — 세부 소재는 후보 3개를 material_check로 대조해 고른다",
                    "출처_메모": self._content_config["source_memo_schema"]},
            "자료_설계": {"자료구성": s["data_kind"], "지침": self._content_config["data_kind"][s["data_kind"]], "그래프_종류": chart,
                         "장치": {d: self._content_config["devices"][d] for d in s["devices"]}},
            "계산_설계": {"계산_성격(기출 분포에서)": calc_pick, "판정은 재계산식으로 닫는다": True},
            "난이도_손잡이": knobs,
            "진술_설계": statements,
            "참고_기출": {"설계_참고(같은 해설서유형·형식, 최신)": refs, "주의": "자료 구성·계산 구조만 참고. 소재·수치·진술 재사용 금지"},
            "회피": {"같은_분야_최근_기출": avoid, "문항풀·대장_소재": avoid_ledger},
        }

    def _content_impl(self, design, ledger=None, seed=0):
        rng = random.Random(seed)
        slots = design["slots"]
        fields, alloc = self._allocate_fields(slots, rng)
        by_field = self._m20_index()
        entries = (ledger or {}).get("entries", [])
        specs = []
        shared = {}
        for s in slots:
            sp = self._design_slot(s, fields[s["slot"]], rng, by_field, entries)
            if s.get("bundle"):
                if s["bundle"] in shared:   # 묶음 둘째 문항: 같은 소재·자료 구성
                    sp["소재"] = dict(shared[s["bundle"]]["소재"]); sp["소재"]["묶음"] = "앞 문항과 같은 자료"
                else:
                    shared[s["bundle"]] = sp
            specs.append(sp)
        return {
            "원칙": self._content_config["principles"],
            "분야_배분": dict(Counter(fields.values()).most_common()),
            "분야_배분_근거(8개년 소재 분야)": self._content_rules["field_dist"],
            "실제_주체_문항": [s["slot"] for s in slots if s["entity"] == "실제"],
            "회차_내_중복_금지": "같은 통계표·같은 기관 자료·같은 소재가 두 자리에 나오지 않는다(묶음 두 문항은 예외: 같은 자료).",
            "승인_절차": self._content_config["approval"],
            "슬롯": specs,
        }

    def sample(self, seed=0, **options) -> dict:
        """Sample a PSAT 5, 40-slot design using only this instance's profile."""
        options = supported_options(options, ('presets', 'custom', 'tries'))
        tries = options.get("tries", 8)
        if type(tries) is not int or tries < 1:
            raise ValueError("tries는 1 이상의 정수여야 합니다")
        return deepcopy(self._sample_impl(seed=seed, **options))

    def validate(self, design, **options) -> list[str]:
        """Return hard errors; soft distribution warnings remain in validate_report."""
        return self.validate_report(design, **options)["errors"]

    def validate_report(self, design, **options):
        """Preserve upstream hard errors, soft warnings and informational differences."""
        options = supported_options(options, ('presets', 'custom', 'skip'))
        errors = format_input_errors(design, 'ans')
        if errors:
            return {"errors": errors, "warnings": [], "infos": []}
        errors = required_slot_errors(design, (
            "fam", "fam_name", "form", "neg", "type", "diff", "nitem", "tsize",
            "shape", "data_kind", "devices", "entity", "stem", "options",
        ))
        if not errors:
            for slot in design["slots"]:
                for axis in self._total_axes:
                    key = str(slot[axis])
                    if key not in self._axis_codes(axis):
                        errors.append(f"슬롯 {slot['slot']} 알 수 없는 {axis}: {key}")
                if type(slot["neg"]) is not bool:
                    errors.append(f"슬롯 {slot['slot']} neg는 bool이어야 합니다")
                if (not isinstance(slot["devices"], list)
                        or any(device not in self._devices for device in slot["devices"])):
                    errors.append(f"슬롯 {slot['slot']} devices가 규칙에 없습니다")
                if slot["form"] == "G":
                    if (type(slot["nitem"]) is not int or type(slot["tsize"]) is not int
                            or not 1 <= slot["tsize"] <= slot["nitem"] <= len(self._heads)):
                        errors.append(f"슬롯 {slot['slot']} 항목 수·정답 크기가 잘못되었습니다")
                    if (not isinstance(slot["options"], list) or len(slot["options"]) != 5
                            or any(not isinstance(option, str) for option in slot["options"])):
                        errors.append(f"슬롯 {slot['slot']} 합답형 선지배열 5개가 필요합니다")
        if errors:
            return {"errors": errors, "warnings": [], "infos": []}
        try:
            result = self._validate_impl(deepcopy(design), **options)
        except (KeyError, TypeError, ValueError, IndexError) as error:
            return {"errors": [f"형식설계 또는 규칙 필드 오류: {error}"], "warnings": [], "infos": []}
        return {"errors": result[0], "warnings": result[1], "infos": result[2] if len(result) == 3 else []}

    def content(self, design, ledger=None, seed=0) -> dict:
        """Validate the complete design before producing a detached content specification."""
        errors = self.validate(design)
        if errors:
            raise ValueError("형식설계 검증 실패: " + "; ".join(errors))
        return deepcopy(self._content_impl(deepcopy(design), copied_ledger(ledger), seed))
