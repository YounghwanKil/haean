"""Instance-owned format algorithms, ported from the local upstream designer.

No rule data, file lookup, environment lookup or external service access.
"""

import random
import re
from collections import Counter, defaultdict
from .adjacency import in_range, max_run


class FormatAlgorithms:

    def _init_format(self):
        self.AREAS = list(self.RULES['codes']['area'].keys())
        self.TYPES = list(self.RULES['codes']['type'].keys())
        self.A_CODE = self.RULES['codes']['area']
        self.T_CODE = self.RULES['codes']['type']
        self.T_SHORT = self.RULES['codes']['type_short']
        self.P_NAMES = self.RULES['codes']['principle_names']
        self.PATTERNS = {k: self.RULES['option_pattern'][k] for k in ('P1', 'P2', 'P3')}
        self.COMBO = 'ㄱㄴㄷ 합답형'
        self.N = 40
        self.SETS = self.RULES['skeleton']['sets']
        self.SET_OF = {i: tuple(p) for p in self.SETS for i in p}
        self.NEG_RX = re.compile('(않은|않는|없는|아닌|틀린|부적절한|상충하는)\\s*(것|곳|사람|경우|항목)?[은는을를이가]?\\s*(모두\\s*고르면|고른 것은)?\\s*\\?\\s*$')
        self.PINS = self.RULES['skeleton'].get('pins', {})
        self.ZONES = self.RULES['skeleton'].get('zone_types', {})
        self.SET_PAIR = self.RULES['skeleton'].get('set_pair', {})
        self.SUB = self.RULES.get('subarea')
        self.STYLE = self.RULES.get('style_caps')
        self.MAJOR_OF = {sub: major for major, subs in self.RULES['taxonomy']['majors'].items() for sub in subs}
        self.SET_TYPE = self.RULES['taxonomy']['set_type']
        self.SET_MAJOR = self.RULES['taxonomy'].get('set_major', '세트형')

    def _f_type_code(self, area, typ, pr):
        return f"11-{self.A_CODE[area]}{self.T_CODE[typ]}{pr}"


    def _f_type_name(self, area, typ, pr):
        return f"{area} {typ} {self.P_NAMES[str(self.T_CODE[typ])][str(pr)]}"


    def _f_wchoice(self, d, rng, exclude=()):
        items = [(k, v) for k, v in d.items() if k not in exclude and v > 0]
        if not items:
            return None
        ks, ws = zip(*items)
        return rng.choices(ks, weights=ws, k=1)[0]


    def _f_split_tp(self, tp):
        t, p = tp.split("|"); return t, p


    def _f_sub_display(self, lab):
        """세부영역 라벨의 해설 표기 — 괄호 보충 제거('공직 상황(가상)' → '공직 상황'). 해설 내용영역은 '인문(역사)'·'논리(공직 상황)' 꼴(core areas.split 규칙)."""
        return re.sub(r"\(.*?\)", "", str(lab or "")).strip()


    def _f_sub_from_display(self, name):
        """해설 표기 → 통합데이터 세부영역 라벨(역변환). 모르면 입력 그대로."""
        if not self.SUB or not name:
            return name
        for lab in self.SUB["labels"]:
            if lab == name or self._f_sub_display(lab) == name:
                return lab
        return name


    def _f_area_label(self, area, sub):
        return f"{area}({self._f_sub_display(sub)})" if sub else area


    def _f_negative(self, stem, polarity=None):
        """부정 발문 판정 — 극성 라벨('옳지 않은 것') 또는 발문 꼬리 문구(…없는/않는/아닌/상충하는 것은?). 원고 생성(emitter·content)과 검수(manuscript_check)가 같은 기준을 쓴다.
        기출 400문항 대조: 라벨과 어긋나는 것은 '약화하지 않는 것은?'·'상충하는 것은?'(라벨 옳은 것, 판정은 부정)뿐."""
        return polarity == "옳지 않은 것" or bool(self.NEG_RX.search(stem or ""))


    def _f_pin_ok(self, i, tp):
        """슬롯 i 의 (유형|원리)가 핀(core 교집합 + manual)에 맞는가."""
        p = self.PINS.get(str(i))
        if not p:
            return True
        t = self._f_split_tp(tp)[0]
        if p.get("type") and t not in p["type"]: return False
        if p.get("type_principle") and tp not in p["type_principle"]: return False
        return True


    def _f_zone_allowed(self, i, tp):
        """구간 유형 울타리(zone_types.allowed)."""
        t = self._f_split_tp(tp)[0]
        for z in self.ZONES.values():
            if i in z["slots"]:
                return any(a == t or a == tp for a in z["allowed"])
        return True


    def _f_zone_errors(self, cells):
        errs = []
        for name, z in self.ZONES.items():
            tps = {i: cells[i] for i in z["slots"] if i in cells}
            for i, tp in tps.items():
                if not any(a == self._f_split_tp(tp)[0] or a == tp for a in z["allowed"]): errs.append(f"슬롯 {i} {tp} ∉ 구간 '{name}' 허용 {z['allowed']}")
            tc = Counter(self._f_split_tp(tp)[0] for tp in tps.values())
            for t, n in z.get("min", {}).items():
                if tc[t] < n: errs.append(f"구간 '{name}' {t} {tc[t]} < {n}")
            for t, n in z.get("max", {}).items():
                if tc[t] > n: errs.append(f"구간 '{name}' {t} {tc[t]} > {n}")
        return errs


    def _f_set_pair_errors(self, cells):
        """두 세트 사이 규칙: (앞,뒤) 유형원리 쌍 상이 · 뒤 문항 중 강화·약화 ≥1 · 앞 문항 ≠ 강화·약화."""
        errs = []
        if not self.SET_PAIR or len(self.SETS) < 2:
            return errs
        pairs = [(cells[a], cells[b]) for a, b in self.SETS]
        if self.SET_PAIR.get("distinct_type_pairs") and len(set(pairs)) < len(pairs): errs.append(f"두 세트의 (앞,뒤) 유형원리 쌍이 같음 {pairs[0]}")
        backs = [self._f_split_tp(cells[b])[0] for _, b in self.SETS]
        EV = self.SET_PAIR.get("evaluation_types", ["강화·약화"]); nb = sum(1 for b in backs if b in EV)
        if nb < self.SET_PAIR.get("back_has_evaluation_min", 0): errs.append(f"세트 뒤 문항 중 평가형({'/'.join(EV)}) {nb} < {self.SET_PAIR['back_has_evaluation_min']}")
        if self.SET_PAIR.get("front_not_evaluation") and any(self._f_split_tp(cells[a])[0] in self.SET_PAIR.get("front_forbidden_types", ["강화·약화"]) for a, _ in self.SETS): errs.append("세트 앞 문항이 강화·약화(10개년 0건)")
        return errs


    def _f_skeleton(self, rng, base):
        """기준 골격(기본 최신 연도) + 3~6 슬롯 변형. 변형 후보 = mutation_source 연도의 같은 문번 셀(가중) ∩ 핀 ∩ 구간 울타리."""
        SK = self.RULES["skeleton"]["slots"]; W = self.RULES["skeleton"]["mutation_weight"]
        tq = self.RULES["type_quota"]["total"]; pq = {k: v for k, v in self.RULES["principle_quota"].items() if not k.startswith("_")}
        base_cells = {i: SK[str(i)]["by_year"][str(base)] for i in range(1, self.N + 1)}
        lo, hi = self.RULES["skeleton"]["mutations"]
        msrc = self.RULES["skeleton"].get("mutation_source")
        for attempt in range(600):
            cells = dict(base_cells); notes = {}
            m = rng.randint(lo, hi)
            for i in rng.sample(range(1, self.N + 1), self.N):
                if len(notes) >= m:
                    break
                alt = Counter()
                if msrc:
                    for y, w in zip(msrc["years"], msrc["weights"]):
                        tp = SK[str(i)]["by_year"].get(str(y))
                        if tp: alt[tp] += w
                else:
                    for k, n in SK[str(i)]["core"].items(): alt[k] += n * W["core"]
                    for k, n in SK[str(i)]["support"].items(): alt[k] += n * W["support"]
                alt = Counter({k: v for k, v in alt.items() if self._f_pin_ok(i, k) and self._f_zone_allowed(i, k) and k in pq})
                # 바꾼 뒤에도 유형(하위유형 9종)·셀 쿼터가 범위 안이어야 받는다 — 규칙은 그대로, 탐색만 단계별로 거른다(v2 축은 칸이 잘아 끝에서 한 번에 보면 대부분 기각)
                tc = Counter(self._f_split_tp(c)[0] for c in cells.values()); pc = Counter(cells.values())
                def keeps(k):
                    t0, t1 = self._f_split_tp(cells[i])[0], self._f_split_tp(k)[0]
                    tc2, pc2 = tc.copy(), pc.copy(); tc2[t0] -= 1; tc2[t1] += 1; pc2[cells[i]] -= 1; pc2[k] += 1
                    if not (all(in_range(tc2[t], tq[t][1]) for t in {t0, t1}) and all(in_range(pc2[c], pq[c][1]) for c in {cells[i], k} if c in pq)):
                        return False
                    trial = {**cells, i: k}
                    return not self._f_zone_errors(trial) and not self._f_set_pair_errors(trial)
                alt = Counter({k: v for k, v in alt.items() if k == cells[i] or keeps(k)})
                new = self._f_wchoice(alt, rng, exclude=(cells[i],))
                if new:
                    notes[i] = f"골격 {base} {cells[i]} → {new}"; cells[i] = new
            tc = Counter(self._f_split_tp(c)[0] for c in cells.values()); pc = Counter(cells.values())
            if all(in_range(tc[t], tq[t][1]) for t in self.TYPES) and all(in_range(pc[k], pq[k][1]) for k in pq) and all(c in pq for c in cells.values()) \
                    and not self._f_zone_errors(cells) and not self._f_set_pair_errors(cells):
                return cells, notes
        raise ValueError(f"골격 변형 실패(base {base})")


    def _f__rule_slots(self, r):
        s = r.get("slots", [])
        return list(s) if isinstance(s, list) else []


    def _f__labels_of(self, key):
        """slot_rules 의 min/max 키 → 세부영역 라벨 집합('science' 는 과학 묶음)."""
        if key == "science": return set(self.SUB["science"])
        return {key}


    def _f_assign_subareas(self, rng, cells):
        """세부영역 배정(세트는 한 단위). 후보 = (세부영역|유형|원리) core+support 관측 셀 ∩ 논리 영역↔논리퀴즈 ∩ slot_rules(hard는 구성으로 보장, soft는 점수).
        가중치 = 그 문번의 core 관측×2 + support×1 + 0.5, 쿼터 초과분은 감점. 역사 구분(한국사/세계사)은 1·2번 한국사 고정 + 총량 범위."""
        cells_ok = self.SUB["cells_allowed"]; amap = self.SUB["area_map"]; quota = self.SUB["quota"]; labels = self.SUB["labels"]; by_slot = self.SUB["by_slot"]
        logic_subs = {l for l in labels if amap[l] == "논리"}
        rules = self.SUB.get("slot_rules", [])
        units, seen = [], set()
        for i in range(1, self.N + 1):
            if i in seen: continue
            u = list(self.SET_OF.get(i, (i,))); seen.update(u); units.append(u)
        # 제약이 센 슬롯부터: require/allowed/hard → 세트 → 나머지
        def prio(u):
            i = u[0]; sc = 0
            for r in rules:
                if i in self._f__rule_slots(r):
                    sc += (3 if r.get("require") else 0) + (2 if r.get("allowed") else 0) + (1 if r.get("hard") else 0)
            return (-sc, -len(u), rng.random())
        aq = self.RULES["area"]["quota"]
        best, best_score = None, None
        for attempt in range(1500):
            order = sorted(units, key=prio)
            out, counts, acount = {}, Counter(), Counter(); ok = True
            for u in order:
                is_logic = all(self._f_split_tp(cells[i])[0] == "논리퀴즈" for i in u)
                cand = {}
                for lab in labels:
                    if (lab in logic_subs) != is_logic: continue
                    if not all(f"{lab}|{cells[i]}" in cells_ok for i in u): continue
                    a = amap[lab]
                    if a != "논리" and acount[a] + len(u) > aq[a][1][1] + 1: continue   # 내용영역 쿼터 상한(검증기 ±1)
                    bad = False
                    for r in rules:
                        rs = set(self._f__rule_slots(r))
                        if not any(i in rs for i in u): continue
                        if r.get("require") and lab != r["require"]: bad = True
                        if r.get("allowed") and lab not in r["allowed"]: bad = True
                        for k, n in r.get("max", {}).items():
                            have = sum(1 for j in rs if j in out and out[j] in self._f__labels_of(k))
                            if lab in self._f__labels_of(k) and have + sum(1 for i in u if i in rs) > n: bad = True
                        for k, n in r.get("min", {}).items():
                            have = sum(1 for j in rs if j in out and out[j] in self._f__labels_of(k))
                            left = sum(1 for j in rs if j not in out)
                            if have < n and left <= n - have and lab not in self._f__labels_of(k): bad = True
                    if bad: continue
                    w = sum(by_slot[str(i)]["core"].get(lab, 0) * 2 + by_slot[str(i)]["support"].get(lab, 0) for i in u) + 0.5
                    if counts[lab] + len(u) > quota[lab][1][1]: w *= 0.05
                    cand[lab] = w
                lab = self._f_wchoice(cand, rng)
                if lab is None:
                    ok = False; break
                for i in u: out[i] = lab
                counts[lab] += len(u); acount[amap[lab]] += len(u)
            if not ok:
                continue
            # 점수: soft 쿼터(core 범위 밖) + 세부영역 연속 초과 + 내용영역 쿼터·연속 초과(검증기 오류이므로 크게)
            score = 0
            for a, (d, r) in aq.items():
                if a != "논리" and not (r[0] - 1 <= acount[a] <= r[1] + 1): score += 20
            for lab in labels:
                lo_, hi_ = quota[lab][1]
                if counts[lab] < lo_ or counts[lab] > hi_: score += 1
            score += 3 * len(self._f_subarea_run_errors(out))
            if max_run([amap[out[i]] for i in range(1, self.N + 1)]) > self.RULES["area"]["max_consecutive"]: score += 20
            if best is None or score < best_score:
                best, best_score = dict(out), score
            if score == 0:
                break
        if best is None:
            raise ValueError("세부영역 배정 실패")
        return best


    def _f_subarea_run_errors(self, sub):
        """같은 세부영역 연속 ≤ max_consecutive(역사는 1~4번 구간에서 예외 상한)."""
        errs = []
        mx = self.SUB.get("max_consecutive", 3); exc = self.SUB.get("max_consecutive_exception", {})
        seq = [sub.get(i) for i in range(1, self.N + 1)]
        i = 0
        while i < self.N:
            j = i
            while j + 1 < self.N and seq[j + 1] == seq[i]: j += 1
            run = j - i + 1; lab = seq[i]; lim = mx
            e = exc.get(lab) if lab else None
            if e and e["slots"][0] <= i + 1 and j + 1 <= e["slots"][1]: lim = e["max"]
            if lab and run > lim: errs.append(f"세부영역 {lab} {i + 1}~{j + 1}번 {run}연속 > {lim}")
            i = j + 1
        return errs


    def _f_assign_history_kind(self, rng, sub):
        """역사 슬롯의 한국사/세계사: slot_rules 의 history_kind(1·2번 한국사) 고정, 나머지는 core 관측 비율로 뽑되 한국사 총량 범위 안."""
        hk = self.SUB.get("history_kind") or {}
        hist = self.SUB["history"]; slots = [i for i in range(1, self.N + 1) if sub.get(i) == hist]
        if not hk or not slots:
            return {}
        fixed = {}
        for r in self.SUB.get("slot_rules", []):
            if r.get("require") == hist and r.get("history_kind"):
                for i in self._f__rule_slots(r):
                    if i in slots: fixed[i] = r["history_kind"]
        lo_, hi_ = self.SUB.get("history_total", {}).get("한국사", [0, 99])
        bys = hk.get("by_slot_core", {})
        for attempt in range(200):
            out = dict(fixed)
            for i in slots:
                if i in out: continue
                obs = Counter(bys.get(str(i), {}).values())
                w = {"한국사": obs.get("한국사", 0) + 1, "세계사": obs.get("세계사", 0) + 1}
                out[i] = self._f_wchoice(w, rng)
            k = sum(v == "한국사" for v in out.values())
            if lo_ <= k <= hi_:
                return out
        return out


    def _f_assign_areas(self, rng, cells, base):
        A = self.RULES["area"]; allowed = A["cells_allowed"]; aq = A["quota"]
        logic_slots = [i for i, c in cells.items() if self._f_split_tp(c)[0] == "논리퀴즈"]
        units = []  # 세트는 한 단위
        seen = set()
        for i in range(1, self.N + 1):
            if i in seen or i in logic_slots:
                continue
            u = list(self.SET_OF.get(i, (i,))); seen.update(u); units.append(u)
        n_free = sum(len(u) for u in units)
        # 영역 목표 수: 기준 골격 연도 관측 → core 범위 안에서 총합 맞춤
        target = {a: aq[a][0] for a in self.AREAS if a != "논리"}
        diff = n_free - sum(target.values())
        keys = [a for a in target if aq[a][1][1] > 0]
        guard = 0
        while diff and guard < 200:
            guard += 1; a = rng.choice(keys)
            if diff > 0 and target[a] < aq[a][1][1] + 1: target[a] += 1; diff -= 1
            elif diff < 0 and target[a] > max(0, aq[a][1][0] - 1): target[a] -= 1; diff += 1
        for attempt in range(800):
            left = dict(target); out = {i: "논리" for i in logic_slots}; ok = True
            order = sorted(units, key=lambda u: (len([a for a in left if all(f"{a}|{cells[i]}" in allowed for i in u)]), rng.random()))
            for u in order:
                cand = {a: sum(allowed.get(f"{a}|{cells[i]}", {}).get("all", 0) for i in u) for a in left if left[a] >= len(u) and all(f"{a}|{cells[i]}" in allowed for i in u)}
                a = self._f_wchoice(cand, rng)
                if a is None:
                    ok = False; break
                for i in u: out[i] = a
                left[a] -= len(u)
            if not ok:
                continue
            seq = [out[i] for i in range(1, self.N + 1)]
            if max_run(seq) <= A["max_consecutive"]:
                return out
        raise ValueError("영역 배정 실패")


    def _f_assign_response(self, rng, cells):
        """응답 형식: (유형·원리)별 관측 분포에서 뽑되, 응답 핀(13 5지·34 합답 등 core 교집합)은 그대로."""
        RF = self.RULES["response_format"]; q = RF["quota"]; forb = set(RF["forbidden"])
        for attempt in range(600):
            out = {}
            for i, c in cells.items():
                pin = self.PINS.get(str(i), {}).get("response")
                d = {k: v for k, v in RF["by_type_principle"].get(c, {}).items() if k not in forb and (not pin or k in pin)}
                out[i] = self._f_wchoice(d, rng) or (pin[0] if pin else "5지 진술 선택형")
            cnt = Counter(out.values())
            if all(in_range(cnt.get(f, 0), q[f][1]) for f in q if f not in forb) and all(f in q for f in cnt):
                return out
        raise ValueError("응답 형식 배정 실패")


    def _f_all_true_counts(self, slots):
        """합답 정답이 ㄱㄴㄷ 전부인 슬롯 수 (전체, 강화·약화)."""
        full = [i for i in slots if slots[i].get("truth_set") == "ㄱㄴㄷ"]
        return len(full), sum(1 for i in full if slots[i]["type"] == "강화·약화")


    def _f_assign_patterns_answers(self, rng, slots):
        combo = [i for i in range(1, self.N + 1) if slots[i]["response"] == self.COMBO]
        ratio = self.RULES["option_pattern"]["ratio_default"]; nc = len(combo)
        pc = {"P1": round(nc * ratio["P1"]), "P3": max(1, round(nc * ratio["P3"])) if nc >= 6 else round(nc * ratio["P3"])}
        pc["P2"] = nc - pc["P1"] - pc["P3"]
        seq = []
        for _ in range(500):
            seq = [p for p, k in pc.items() for _ in range(k)]; rng.shuffle(seq)
            if not seq or max_run(seq) <= self.RULES["option_pattern"]["max_consecutive_same"]:
                break
        for i, p in zip(combo, seq):
            slots[i]["option_pattern"] = p
        tsw = self.RULES["answer"]["combo_truth_set_weight"]
        lo, hi = self.RULES["answer"]["per_number_range"]
        cap_all = self.RULES["answer"].get("combo_all_true_max", 99); cap_eval = self.RULES["answer"].get("combo_all_true_max_evaluation", 99)
        best = None
        for attempt in range(4000):
            ans = {}
            for i in combo:
                pat = self.PATTERNS[slots[i]["option_pattern"]]
                t = self._f_wchoice({k: tsw.get(k, 0) + 1 for k in pat}, rng)
                ans[i] = (t, pat.index(t) + 1)
            cnt = Counter(a for _, a in ans.values())
            full = {i: a for i, (_, a) in ans.items()}
            for i in [s for s in range(1, self.N + 1) if s not in full]:
                n = min(range(1, 6), key=lambda x: (cnt[x], rng.random())); full[i] = n; cnt[n] += 1
            seq_a = [full[i] for i in range(1, self.N + 1)]
            n_all = sum(1 for i, (t, _) in ans.items() if t == "ㄱㄴㄷ"); n_eval = sum(1 for i, (t, _) in ans.items() if t == "ㄱㄴㄷ" and slots[i]["type"] == "강화·약화")
            ok = all(lo <= cnt[n] <= hi for n in range(1, 6)) and max_run(seq_a) <= self.RULES["answer"]["max_consecutive_same"] and n_all <= cap_all and n_eval <= cap_eval
            score = (0 if ok else 1, max_run(seq_a), sum(abs(cnt[n] - 8) for n in range(1, 6)))
            if best is None or score < best[0]:
                best = (score, full, {i: t for i, (t, _) in ans.items()})
            if ok and max_run(seq_a) <= self.RULES["answer"]["soft_max_consecutive_same"]:
                break
        _, full, ts = best
        for i in range(1, self.N + 1):
            slots[i]["answer"] = full[i]
            slots[i]["truth_set"] = ts.get(i)
            if i not in ts:
                slots[i]["option_pattern"] = None


    def _f_to_set_stem(self, k):
        """세트 문항 발문은 '위 글…'. 단독 발문을 세트 꼴로 바꾼다."""
        if k.startswith("위 글") or "위 글" in k:
            return k
        if k.startswith("다음 글"):
            return "위 글" + k[len("다음 글"):]
        if k.startswith("다음 "):
            return "위 글을 토대로 할 때 " + k[len("다음 "):]
        return k


    def _f_stem_pool(self, slot):
        pool = self.RULES["stem"]["pool"]; tp = f"{slot['type']}|{slot['principle']}"
        mode = "세트" if slot["set"] else "단독"
        for key in (f"{tp}|{slot['response']}|{mode}", f"{tp}|{slot['response']}|단독", f"{tp}|{slot['response']}|세트"):
            if key in pool:
                d = dict(pool[key])
                if mode == "세트":
                    d = {self._f_to_set_stem(k): v for k, v in d.items()}
                return d
        any_ = {}
        for k, v in pool.items():
            if k.startswith(tp + "|"):
                for s, w in v.items():
                    s = self._f_to_set_stem(s) if mode == "세트" else s
                    any_[s] = any_.get(s, 0) + w
        return any_


    def _f_meta_of(self, stem):
        M = self.RULES["stem"]["meta"]
        m = M.get(stem)
        if m is None and stem.startswith("위 글을 토대로 할 때 "):
            m = M.get("다음 " + stem[len("위 글을 토대로 할 때 "):])
        if m is None and stem.startswith("위 글"):
            m = M.get("다음 글" + stem[len("위 글"):])
        return m or {"근거": "맥락 지정", "작업": "기타", "극성": "옳은 것", "응답": "단일 선택", "단서": "-"}


    def _f_assign_stems(self, rng, slots):
        polq = self.RULES["stem"]["polarity_quota"]
        for attempt in range(400):
            for i in range(1, self.N + 1):
                s = slots[i]; d = self._f_stem_pool(s)
                if s["response"] == self.COMBO:
                    d = {k: v for k, v in d.items() if "<보기>" in k and self._f_meta_of(k)["극성"] == "옳은 것"} or d
                s["stem"] = self._f_wchoice(d, rng)
            pol = Counter(self._f_meta_of(slots[i]["stem"])["극성"] for i in slots)
            if all(in_range(pol.get(k, 0), polq[k][1]) for k in polq):
                break
        for i in slots:
            m = self._f_meta_of(slots[i]["stem"])
            slots[i].update({"polarity": m["극성"], "stem_basis": m["근거"], "stem_task": m["작업"], "stem_proviso": m["단서"]})


    def _f_assign_judgment(self, rng, slots):
        q = self.RULES["judgment_mode"]["calc_included_total"]; elig = set(self.RULES["judgment_mode"]["calc_eligible"])
        for i in slots: slots[i]["judgment"] = "논리"
        cand = [i for i in slots if f"{slots[i]['type']}|{slots[i]['principle']}" in elig]
        rng.shuffle(cand)
        n = min(len(cand), max(q[1][0], min(q[0], q[1][1])))
        for i in cand[:n]: slots[i]["judgment"] = "논리+계산"


    def _f_assign_difficulty(self, rng, slots):
        """난도(추정척도 2·3·4). '상'(4)은 core에서 상이 관측된 자리(difficulty.high_slots)에만, 개수는 쿼터 기본값(high_count 범위). 나머지는 유형 평균 순."""
        D = self.RULES["difficulty"]
        dq = {int(k): v[0] for k, v in D["quota"].items()}
        tm = D["by_type_mean"]
        high_slots = set(D.get("high_slots") or [])
        n_high = dq.get(4, 0)
        lo_, hi_ = D.get("high_count", [0, self.N])
        n_high = max(lo_, min(hi_, n_high))
        key = lambda i: -(tm.get(slots[i]["type"], 3) + (0.4 if slots[i]["judgment"] != "논리" else 0) + rng.random() * 0.8)
        if high_slots:
            cand = sorted([i for i in slots if i in high_slots], key=key)
            high = set(cand[:n_high])
        else:
            high = set(sorted(slots, key=key)[:n_high])
        rest = [i for i in sorted(slots, key=key) if i not in high]
        bag = [2] * dq.get(2, 0) + [3] * dq.get(3, 0)
        while len(bag) < len(rest): bag.append(3)
        bag = sorted(bag[:len(rest)], reverse=True)   # 어려운 순서대로 3 → 2
        for i in high: slots[i]["difficulty"] = 4
        for i, d in zip(rest, bag): slots[i]["difficulty"] = d


    def _f_sample(self, seed=0, base=None):
        rng = random.Random(seed)
        base = base or self.RULES["skeleton"].get("base_default") or rng.choice(self.RULES["skeleton"]["base_years"])
        cells, mut = self._f_skeleton(rng, base)
        if self.SUB:
            subs = self._f_assign_subareas(rng, cells)
            areas = {i: self.SUB["area_map"][subs[i]] for i in subs}
            hk = self._f_assign_history_kind(rng, subs)
        else:
            subs, hk = {}, {}
            areas = self._f_assign_areas(rng, cells, base)
        resp = self._f_assign_response(rng, cells)
        slots = {}
        for i in range(1, self.N + 1):
            t, p = self._f_split_tp(cells[i])
            slots[i] = {"slot": i, "area": areas[i], "subarea": subs.get(i), "history_kind": hk.get(i), "type": t, "principle": p, "set": i in self.SET_OF, "response": resp[i],
                        "option_pattern": None, "truth_set": None, "notes": [mut[i]] if i in mut else []}
        self._f_assign_patterns_answers(rng, slots)
        self._f_assign_stems(rng, slots)
        for s in slots.values():
            s["major"], s["subtype"] = self.MAJOR_OF[s["type"]], s["type"]   # 엔진 유형(v3)
            s["book_type"] = self.SET_TYPE if s.get("set") else s["type"]; s["book_major"] = self.SET_MAJOR if s.get("set") else s["major"]
        self._f_assign_judgment(rng, slots)
        self._f_assign_difficulty(rng, slots)
        L = self.RULES["length"]
        for i, s in slots.items():
            r = L["by_type_principle"].get(f"{s['type']}|{s['principle']}", [700, 1100, 300, 1500]); basis = "총(발문+지문+보기/선지)"
            if i in self.SET_OF and L.get("set_common_passage"):
                r = L["set_common_passage"]; basis = "세트 공통 지문(공백 포함)"      # 세트 슬롯 = 공통 지문 글자수
            elif str(i) in L.get("by_slot", {}):
                r = L["by_slot"][str(i)]; basis = "총(자리별 core 관측)"           # 13·14·33·34 자리별
            s["chars_range"] = r[:2]; s["chars_basis"] = basis
            s["special"] = ("[세트앞]" if self.SET_OF[i][0] == i else "[세트뒤]") if i in self.SET_OF else "없음"
            s["type_code"] = self._f_type_code(s["area"], s["type"], s["principle"])
            s["type_name"] = self._f_type_name(s["area"], s["type"], s["principle"])
            s["statement_count"] = 3 if s["response"] == self.COMBO else 0
        return {"meta": {"rules": self.RULES["meta"]["version"], "seed": seed, "skeleton_base": base, "exam": "PSAT 5급 언어논리"},
                "slots": [slots[i] for i in range(1, self.N + 1)]}


    def _f_subarea_errors(self, S):
        """세부영역 축 검사 → (오류, 경고). 슬롯에 subarea 가 없으면 빈 결과."""
        errs, warns = [], []
        if not self.SUB or not all(s.get("subarea") for s in S):
            return errs, warns
        sub = {s["slot"]: s["subarea"] for s in S}
        amap = self.SUB["area_map"]
        for s in S:
            if s["subarea"] not in amap: errs.append(f"슬롯 {s['slot']} 세부영역 {s['subarea']} 미관측")
            elif amap[s["subarea"]] != s["area"]: errs.append(f"슬롯 {s['slot']} 세부영역 {s['subarea']} ↔ 내용영역 {s['area']} 불일치")
            if f"{s['subarea']}|{s['type']}|{s['principle']}" not in self.SUB["cells_allowed"]: errs.append(f"슬롯 {s['slot']} {s['subarea']}|{s['type']}|{s['principle']} 기출(core+support) 미관측 셀")
        for r in self.SUB.get("slot_rules", []):
            rs = self._f__rule_slots(r); bucket = errs if r.get("hard") else warns
            if r.get("require"):
                for i in rs:
                    if sub.get(i) != r["require"]: bucket.append(f"슬롯 {i} 세부영역 {sub.get(i)} ≠ {r['require']}")
            if r.get("allowed"):
                for i in rs:
                    if sub.get(i) not in r["allowed"]: bucket.append(f"슬롯 {i} 세부영역 {sub.get(i)} ∉ {r['allowed']}")
            for k, n in r.get("min", {}).items():
                have = sum(1 for i in rs if sub.get(i) in self._f__labels_of(k))
                if have < n: bucket.append(f"{rs[0]}~{rs[-1]}번 {k} {have} < {n}")
            for k, n in r.get("max", {}).items():
                have = sum(1 for i in rs if sub.get(i) in self._f__labels_of(k))
                if have > n: bucket.append(f"{rs[0]}~{rs[-1]}번 {k} {have} > {n}")
        cnt = Counter(sub.values())
        for lab, (d, r) in self.SUB["quota"].items():
            if not (r[0] - 1 <= cnt.get(lab, 0) <= r[1] + 1): warns.append(f"세부영역 {lab} {cnt.get(lab, 0)} ∉ {r}±1")
        warns += self._f_subarea_run_errors(sub)
        ht = self.SUB.get("history_total", {})
        hk = {s["slot"]: s.get("history_kind") for s in S if s.get("history_kind")}
        if ht.get("역사") and not in_range(cnt.get(self.SUB["history"], 0), ht["역사"]): (errs if ht.get("hard") else warns).append(f"역사 {cnt.get(self.SUB['history'], 0)} ∉ {ht['역사']}")
        if hk and ht.get("한국사") and not in_range(sum(v == "한국사" for v in hk.values()), ht["한국사"]): (errs if ht.get("hard") else warns).append(f"한국사 {sum(v == '한국사' for v in hk.values())} ∉ {ht['한국사']}")
        for r in self.SUB.get("slot_rules", []):
            if r.get("history_kind") and hk:
                for i in self._f__rule_slots(r):
                    if hk.get(i) and hk[i] != r["history_kind"]: (errs if r.get("hard") else warns).append(f"슬롯 {i} 역사 구분 {hk[i]} ≠ {r['history_kind']}")
        if self.SUB.get("set_same_subarea"):
            for a, b in self.SETS:
                if sub.get(a) != sub.get(b): errs.append(f"{a}~{b} 세트 세부영역 불일치")
        return errs, warns


    def _f_validate(self, design):
        R = self.RULES; S = design["slots"]; errs, warns = [], []
        if len(S) != self.N:
            return [f"슬롯 {len(S)}개 (40이어야)"], []
        by = lambda f: Counter(s[f] for s in S)
        for t, (d, r) in R["type_quota"]["total"].items():
            if not in_range(by("type")[t], r): errs.append(f"유형 {t} {by('type')[t]} ∉ {r}")
        pc = Counter(f"{s['type']}|{s['principle']}" for s in S)
        for k, v in R["principle_quota"].items():
            if k.startswith("_"): continue
            if not in_range(pc[k], v[1]): errs.append(f"원리 {k} {pc[k]} ∉ {v[1]}")
        for k in pc:
            if k not in R["principle_quota"]: errs.append(f"원리 {k} 기출(core+support)에 없음")
        ac = by("area")
        for a, (d, r) in R["area"]["quota"].items():
            lo_, hi_ = r if a != "논리" else r
            if a != "논리" and not (r[0] - 1 <= ac[a] <= r[1] + 1): errs.append(f"영역 {a} {ac[a]} ∉ {r}±1")
        for s in S:
            cell = f"{s['area']}|{s['type']}|{s['principle']}"
            if cell not in R["area"]["cells_allowed"]: errs.append(f"슬롯 {s['slot']} {cell} 기출 미관측 셀")
            if (s["type"] == "논리퀴즈") != (s["area"] == "논리"): errs.append(f"슬롯 {s['slot']} 논리퀴즈 ↔ 논리 영역 불일치")
            if s["type_code"][:2] != "11": errs.append(f"슬롯 {s['slot']} 코드 {s['type_code']}")
        if max_run([s["area"] for s in S]) > R["area"]["max_consecutive"]: errs.append(f"같은 영역 {max_run([s['area'] for s in S])}연속 > {R['area']['max_consecutive']}")
        # 자리 핀 · 구간 유형 · 세트 쌍 · 세부영역 · 난도 자리 · 전부 정답 상한 (2026-10-18)
        cells = {s["slot"]: f"{s['type']}|{s['principle']}" for s in S}
        for s in S:
            p = self.PINS.get(str(s["slot"]))
            if not p: continue
            if not self._f_pin_ok(s["slot"], cells[s["slot"]]): errs.append(f"슬롯 {s['slot']} {cells[s['slot']]} 핀 위반 {p.get('type_principle') or p.get('type')}")
            if p.get("response") and s["response"] not in p["response"]: errs.append(f"슬롯 {s['slot']} 응답 {s['response']} 핀 위반 {p['response']}")
        errs += self._f_zone_errors(cells)
        errs += self._f_set_pair_errors(cells)
        se, sw = self._f_subarea_errors(S); errs += se; warns += sw
        D = R["difficulty"]
        if D.get("high_slots"):
            bad = [s["slot"] for s in S if s["difficulty"] == 4 and s["slot"] not in D["high_slots"]]
            if bad: (errs if D.get("high_zone_hard") else warns).append(f"'상' 난도가 core 상 관측 자리 밖: {bad}")
            n4 = sum(s["difficulty"] == 4 for s in S); hc = D.get("high_count")
            if hc and not in_range(n4, hc): warns.append(f"'상' {n4}개 ∉ {hc}")
        n_all = sum(1 for s in S if s.get("truth_set") == "ㄱㄴㄷ"); n_eval = sum(1 for s in S if s.get("truth_set") == "ㄱㄴㄷ" and s["type"] == "강화·약화")
        if n_all > R["answer"].get("combo_all_true_max", 99): errs.append(f"합답 전부 정답(ㄱㄴㄷ) {n_all} > {R['answer']['combo_all_true_max']}")
        if n_eval > R["answer"].get("combo_all_true_max_evaluation", 99): errs.append(f"강화·약화 합답 전부 정답 {n_eval} > {R['answer']['combo_all_true_max_evaluation']}")
        # 세트
        for a, b in self.SETS:
            x, y = S[a - 1], S[b - 1]
            if not (x["set"] and y["set"]): errs.append(f"{a}~{b} 세트 표시 없음")
            if x["area"] != y["area"]: errs.append(f"{a}~{b} 세트 영역 불일치")
            if "위 글" not in x["stem"] or "위 글" not in y["stem"]: errs.append(f"{a}~{b} 세트 발문에 '위 글' 없음")
            if f"{x['type']}|{x['principle']}" == f"{y['type']}|{y['principle']}": warns.append(f"{a}~{b} 세트 두 문항이 같은 원리(판단 과제 겹침 주의)")
        for s in S:
            if s["set"] and s["slot"] not in self.SET_OF: errs.append(f"슬롯 {s['slot']} 세트 위치 아님")
        # 응답 형식
        rc = by("response")
        for f, (d, r) in R["response_format"]["quota"].items():
            if f in R["response_format"]["forbidden"]: continue
            if not in_range(rc.get(f, 0), r): errs.append(f"응답 {f} {rc.get(f, 0)} ∉ {r}")
        for f in rc:
            if f in R["response_format"]["forbidden"] or f not in R["response_format"]["quota"]: errs.append(f"응답 형식 {f} 금지·미관측")
        # 합답 배열·정답
        combo = [s for s in S if s["response"] == self.COMBO]
        pcnt = Counter(s["option_pattern"] for s in combo)
        for p, r in R["option_pattern"]["ratio_range"].items():
            if combo and not (r[0] - 0.1 <= pcnt[p] / len(combo) <= r[1] + 0.1): warns.append(f"{p} 비율 {pcnt[p]}/{len(combo)} ∉ {r}±.1")
        if combo and max_run([s["option_pattern"] for s in combo]) > R["option_pattern"]["max_consecutive_same"]: errs.append("합답 배열 연속 초과")
        for s in combo:
            if s["option_pattern"] not in self.PATTERNS: errs.append(f"슬롯 {s['slot']} 배열 {s['option_pattern']} 금지")
            elif self.PATTERNS[s["option_pattern"]].index(s["truth_set"]) + 1 != s["answer"]: errs.append(f"슬롯 {s['slot']} 정답 ≠ 진위 집합 위치")
            if s["statement_count"] != 3: errs.append(f"슬롯 {s['slot']} 합답 보기 3개")
            if s["polarity"] != "옳은 것": errs.append(f"슬롯 {s['slot']} 합답형은 옳은 것")
        acn = by("answer"); lo, hi = R["answer"]["per_number_range"]
        for k in range(1, 6):
            if not lo <= acn[k] <= hi: errs.append(f"정답 {k} {acn[k]}개 ∉ [{lo},{hi}]")
        mr = max_run([s["answer"] for s in S])
        if mr > R["answer"]["max_consecutive_same"]: errs.append(f"정답 연속 {mr}")
        elif mr > R["answer"]["soft_max_consecutive_same"]: warns.append(f"정답 연속 {mr} (권장 ≤{R['answer']['soft_max_consecutive_same']})")
        # 유형 체계 v2 쿼터(경고) — 대분류·하위유형이 core 관측 범위 안인지
        TXR = R.get("taxonomy")
        if TXR:
            for key, field in (("major_quota", "major"), ("subtype_quota", "subtype")):
                cnt = Counter(self.MAJOR_OF[s["type"]] if field == "major" else s["type"] for s in S)
                for k, (d, r) in TXR[key].items():
                    if not in_range(cnt.get(k, 0), r): warns.append(f"[유형v3] {k} {cnt.get(k, 0)} ∉ {r}")
        # 발문
        pol = by("polarity")
        for k, (d, r) in R["stem"]["polarity_quota"].items():
            if not in_range(pol.get(k, 0), r): errs.append(f"극성 {k} {pol.get(k, 0)} ∉ {r}")
        for s in S:
            if s["stem"] not in self._f_stem_pool(s): errs.append(f"슬롯 {s['slot']} 발문이 그 셀·형식 기출 발문 풀에 없음")
            if s["response"] == self.COMBO and "<보기>에서 모두 고르면?" not in s["stem"]: errs.append(f"슬롯 {s['slot']} 합답형 발문 꼬리")
        # 판단·난이도·글자수
        calc = sum(s["judgment"] != "논리" for s in S); q = R["judgment_mode"]["calc_included_total"][1]
        if not in_range(calc, q): errs.append(f"계산 포함 {calc} ∉ {q}")
        for s in S:
            if s["judgment"] != "논리" and f"{s['type']}|{s['principle']}" not in R["judgment_mode"]["calc_eligible"]: warns.append(f"슬롯 {s['slot']} 계산 포함 미관측 셀")
        dc = by("difficulty")
        for k, (d, r) in R["difficulty"]["quota"].items():
            if not in_range(dc.get(int(k), 0), r): (errs if R["difficulty"]["strict"] else warns).append(f"난이도(추정) {k} {dc.get(int(k), 0)} ∉ {r}")
        tl = sum(s["chars_range"][0] for s in S); th = sum(s["chars_range"][1] for s in S); tt = R["length"]["set_total_target"]
        if th < tt[0] or tl > tt[1]: warns.append(f"회차 글자수 범위 [{tl},{th}] ↔ 목표 {tt}")
        return errs, warns
