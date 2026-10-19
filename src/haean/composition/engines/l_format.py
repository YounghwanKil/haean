"""Instance-owned format algorithms, ported from the local upstream designer.

No rule data, file lookup, environment lookup or external service access.
"""

import json
import random
import re
from collections import Counter, defaultdict
from .adjacency import in_range, max_run


class FormatAlgorithms:

    def _init_format(self):
        self.AREAS = self.RULES['blocks']['order']
        self.TYPES = list(self.RULES['codes']['type'].keys())
        self.A_CODE = self.RULES['codes']['area']
        self.T_CODE = self.RULES['codes']['type']
        self.T_SHORT = self.RULES['codes']['type_short']
        self.P_NAMES = self.RULES['codes']['principle_names']
        self.PATTERNS = {k: self.RULES['option_pattern'][k] for k in ('P1', 'P2', 'P3')}
        self.COMBO = 'ㄱㄴㄷ 합답형'
        self.DIAGRAM = '논증 구조 도식 선택'
        self.FIVE = '5지 진술 선택형'
        self.SPECIAL = '특수 응답형'
        self.SIZES = (40, 20)
        self.HALF_AREAS = {'규범': 6, '인문': 6, '사회': 3, '논리학·수학': 2, '과학기술': 3}

    def _f__key_prefix(self, d, prefix):
        return next(v for k, v in d.items() if k.startswith(prefix))


    def _f_half(self, r):
        """40 기준 범위 [lo, hi] → 20 기준 [lo//2, ceil(hi/2)]."""
        return [r[0] // 2, -(-r[1] // 2)]


    def _f_scaled(self, r, size):
        return list(r) if size == 40 else self._f_half(r)


    def _f_type_code(self, area, typ, pr):
        return f"11-{self.A_CODE[area]}{self.T_CODE[typ]}{pr}"


    def _f_type_name(self, area, typ, pr):
        tn = {"언어 추리": "언어추리", "논쟁 및 반론": "논쟁 및 반론", "논증 분석": "논증 분석",
              "논증 평가 및 문제 해결": "논증 평가", "모형 추리": "모형 추리"}[typ]
        return f"{area} {tn} {self.P_NAMES[str(self.T_CODE[typ])][str(pr)]}"


    def _f_pick_counts(self, quota, total, rng):
        """quota: {key: [default, [lo, hi]]} → 기본값 그대로 쓰되 합이 total이 아니면 범위 안에서 조정."""
        counts = {k: v[0] for k, v in quota.items() if not k.startswith("_")}
        rng_ = {k: v[1] for k, v in quota.items() if not k.startswith("_")}
        diff = total - sum(counts.values())
        keys = list(counts)
        guard = 0
        while diff != 0 and guard < 200:
            guard += 1
            k = rng.choice(keys)
            if diff > 0 and counts[k] < rng_[k][1]:
                counts[k] += 1; diff -= 1
            elif diff < 0 and counts[k] > rng_[k][0]:
                counts[k] -= 1; diff += 1
        if diff != 0:
            raise ValueError(f"쿼터 합 조정 실패: {quota} total={total}")
        return counts


    def _f_expand(self, counts):
        out = []
        for k, n in counts.items():
            out += [k] * n
        return out


    def _f_sample(self, seed=0, variant=None, size=40):
        if size == 20:
            return self._f_sample20(seed, variant)
        if size != 40:
            raise ValueError(f"표준 회차는 {self.SIZES}문항")
        rng = random.Random(seed)
        R = self.RULES
        slots = {i: {"slot": i, "notes": []} for i in range(1, 41)}

        # 1) 영역 블록 (기본 경계 그대로)
        for area, b in R["blocks"]["default"].items():
            lo, hi = b["slots"]
            for i in range(lo, hi + 1):
                slots[i]["area"] = area

        # 2) 영역별 유형 쿼터 → 유형 배정 (슬롯 고정 규칙 먼저)
        SR = R["slot_rules"]
        fixed_type = {}
        fixed_type[1] = (SR["1"]["type_default"], SR["1"]["principle_default"])
        fixed_type[2] = (SR["2"]["type_default"], SR["2"]["principle_default"])
        for s in ("31", "32"):
            fixed_type[int(s)] = ("모형 추리", SR[s]["principle_default"])
        p33, p34 = rng.sample(SR["33"]["principle_allowed"], 2)
        fixed_type[33] = ("모형 추리", p33); fixed_type[34] = ("모형 추리", p34)
        fixed_type[40] = (SR["40"]["type_default"], SR["40"]["principle_default"])
        dslot = SR["diagram"]["slot_default"]
        fixed_type[dslot] = ("논증 분석", "1")
        # 특수 응답형(빈칸·순서·수치·단일 선택) 슬롯은 언어추리(규범·사회) 또는 모형추리(논리) — 2026·2027 전부 그 둘
        for k, detail in R["response_format"]["non_combo_default_detail"].items():
            i = int(k)
            if i not in fixed_type:
                # 순서 나열형(값·순서 지정, 발문 '기타'+표지 지정)은 사례추론 1에서만 관측 → 원리 1 고정. 그 밖은 쿼터에서 아무 원리
                fixed_type[i] = ("언어 추리", "1" if detail == "순서 나열형" else None)

        for area in self.AREAS:
            area_slots = [i for i in range(1, 41) if slots[i]["area"] == area]
            tq = {t: v for t, v in R["type_quota"]["by_area"][area].items() if v[1][1] > 0}
            tcounts = self._f_pick_counts(tq, len(area_slots), rng)
            # 원리 쿼터
            cells = []  # (type, principle)
            for t, n in tcounts.items():
                if n == 0:
                    continue
                pq = R["principle_quota"].get(f"{area}|{t}")
                if pq is None:
                    raise ValueError(f"원리 쿼터 없음: {area}|{t}")
                pq = {k: v for k, v in pq.items() if not k.startswith("_") and isinstance(v, list)}
                pc = self._f_pick_counts(pq, n, rng)
                cells += [(t, p) for p in self._f_expand(pc)]
            # 고정 슬롯부터 소비
            pool = Counter(cells)
            for i in area_slots:
                if i in fixed_type:
                    t, p = fixed_type[i]
                    if p is None:
                        alt = [c for c in pool.elements() if c[0] == t]
                        if not alt:
                            raise ValueError(f"슬롯 {i} 고정 유형 {t}이 영역 쿼터에 없음")
                        p = rng.choice(alt)[1]
                    if pool[(t, p)] > 0:
                        pool[(t, p)] -= 1
                    else:
                        # 고정 요구 셀이 쿼터에 없으면 같은 유형의 다른 원리 하나를 바꿔 넣음
                        alt = [c for c in pool.elements() if c[0] == t]
                        if alt:
                            pool[alt[0]] -= 1
                            slots[i]["notes"].append(f"고정 슬롯을 위해 {alt[0][1]}→{p} 교체")
                        else:
                            raise ValueError(f"슬롯 {i} 고정 유형 {t}이 영역 쿼터에 없음")
                    slots[i]["type"], slots[i]["principle"] = t, p
            rest = list(pool.elements()); rng.shuffle(rest)
            free = [i for i in area_slots if i not in fixed_type]
            if area == "사회":  # soft: 언어추리 앞, 논증평가 뒤
                rest.sort(key=lambda c: 0 if c[0] == "언어 추리" else 1)
            for i, (t, p) in zip(free, rest):
                slots[i]["type"], slots[i]["principle"] = t, p

        # 3) 응답 형식
        for i in slots:
            slots[i]["response"] = self.COMBO
        slots[dslot]["response"] = self.DIAGRAM
        nc_default = R["response_format"]["non_combo_default_detail"]  # {slot: detail}
        for k, detail in nc_default.items():
            i = int(k)
            if variant == "mix" and rng.random() < 0.5:
                slots[i]["response"] = self.FIVE
                slots[i]["response_detail"] = "5지 진술 선택형"
                slots[i]["_neg"] = rng.random() < 0.5
            else:
                slots[i]["response"] = self.SPECIAL
                slots[i]["response_detail"] = detail
        # 4)·5) P 배열 → 진위 집합 → 정답 번호
        self._f_assign_answers(slots, rng, 40)

        # 6) 발문 극성·작업·근거
        for i in slots:
            s = slots[i]
            s["polarity"] = "옳은 것"
            if s["response"] == self.SPECIAL and s.get("response_detail") in R["stem"]["polarity_target_details"]:
                s["polarity"] = "해당하는 것"
            if s["response"] == self.FIVE and s.pop("_neg", False):
                s["polarity"] = "옳지 않은 것"
        if all(slots[i]["polarity"] == "옳은 것" for i in slots):  # 관측 상한 39 → 비긍정 극성 최소 1
            five = [i for i in slots if slots[i]["response"] == self.FIVE]
            if five:
                slots[rng.choice(five)]["polarity"] = "옳지 않은 것"
        # 발문 작업: 회차 쿼터(task_quota_total 기본값)를 유형 호환성·가중치로 배정
        tq = {k: v[0] for k, v in R["stem"]["task_quota_total"].items()}
        tbt = R["stem"]["task_by_type"]
        tbtp = R["stem"].get("task_by_type_principle", {})
        def task_ok(i, task):
            key = f"{slots[i]['type']}|{slots[i]['principle']}"
            allowed = tbtp.get(key) if key in tbtp else tbt[slots[i]["type"]]
            return task in allowed
        slots[dslot]["stem_task"] = "분석"; tq["분석"] -= 1
        pre = {dslot}
        for i in slots:  # 순서 나열형(값·순서 지정)은 2027-03 꼴: 표지 지정 + 기타
            if slots[i].get("response_detail") == "순서 나열형":
                slots[i]["stem_task"] = "기타"; slots[i]["_basis"] = "표지 지정"; tq["기타"] -= 1; pre.add(i)
        # '기타' 작업은 2025~2027 전부 비합답형 → 남은 기타 쿼터는 비합답 슬롯 수까지만
        nc_free = [i for i in slots if slots[i]["response"] != self.COMBO and i not in pre]
        if tq["기타"] > len(nc_free):
            tq["추론"] += tq["기타"] - len(nc_free); tq["기타"] = len(nc_free)
        free_slots = [i for i in slots if i not in pre]
        for attempt in range(500):
            fs = list(free_slots); rng.shuffle(fs); todo = dict(tq); assigned = {}
            # 호환 슬롯이 적은 작업부터
            for task in sorted(todo, key=lambda t: sum(1 for i in fs if task_ok(i, t))):
                for _ in range(todo[task]):
                    cands = [i for i in fs if task_ok(i, task) and (task != "기타" or slots[i]["response"] != self.COMBO)]
                    if not cands:
                        break
                    w = [(tbtp.get(f"{slots[i]['type']}|{slots[i]['principle']}") or tbt[slots[i]["type"]])[task] for i in cands]
                    pick = rng.choices(cands, weights=w, k=1)[0]
                    assigned[pick] = task; fs.remove(pick)
            if len(assigned) == len(free_slots):
                break
        else:
            raise ValueError("발문 작업 배정 실패")
        for i, t in assigned.items():
            slots[i]["stem_task"] = t
        basis_q = R["stem"]["basis_quota"]
        basis_seq = self._f_expand({k: v[0] for k, v in basis_q.items()})
        # 표지 지정은 언어추리·논증평가·논쟁에 우선 배정, 모형추리는 '다음'
        fixed_b = {i: slots[i].pop("_basis") for i in list(slots) if "_basis" in slots[i]}
        for i, b in fixed_b.items():
            slots[i]["stem_basis"] = b; basis_seq.remove(b)
        bbtp = R["stem"].get("basis_by_type_principle", {})
        def basis_ok(i, b):
            key = f"{slots[i]['type']}|{slots[i]['principle']}"
            return b in bbtp[key] if key in bbtp else True
        free_b = [i for i in slots if i not in fixed_b]
        for attempt in range(300):
            rng.shuffle(free_b); seq = list(basis_seq); rng.shuffle(seq)
            seq.sort(key=lambda b: 0 if b != "다음(지문 전체)" else 1)  # 희소한 근거부터
            assign, pool = {}, list(free_b)
            for b in seq:
                cands = [i for i in pool if basis_ok(i, b)]
                if not cands:
                    break
                i = rng.choice(cands); assign[i] = b; pool.remove(i)
            if len(assign) == len(free_b):
                break
        else:
            raise ValueError("발문 근거 배정 실패")
        for i, b in assign.items():
            slots[i]["stem_basis"] = b

        # 7) 판단 방식 · 8) 난이도
        self._f_assign_judgment(slots, rng, 40)
        self._f_assign_difficulty(slots, rng, 40)

        # 9) 글자수 범위·특수형식·코드
        for i in slots:
            s = slots[i]
            lo_, hi_, _, _ = R["length"]["by_area"][s["area"]]
            if str(i) in R["length"]["by_slot"]:
                lo_, hi_ = R["length"]["by_slot"][str(i)]
            s["chars_range"] = [lo_, hi_]
            s["special"] = "[1번특수형]" if i == 1 else "[2번특수형]" if i == 2 else "없음"
            s["type_code"] = self._f_type_code(s["area"], s["type"], s["principle"])
            s["type_name"] = self._f_type_name(s["area"], s["type"], s["principle"])
            s["statement_count"] = 3 if s["response"] == self.COMBO else 0
        return {"meta": {"rules": R["meta"]["version"], "seed": seed, "size": 40}, "slots": [slots[i] for i in range(1, 41)]}


    def _f_assign_answers(self, slots, rng, size):
        """합답형 슬롯에 P 배열·진위 집합을, 모든 슬롯에 정답 번호를 배정한다(slots: {번호: 슬롯}).
        정답 번호 = P 배열에서 진위 집합의 위치. 번호당 개수·연속 상한을 맞출 때까지 다시 뽑는다."""
        R = self.RULES
        order = sorted(slots)
        combo_slots = [i for i in order if slots[i]["response"] == self.COMBO]
        n_combo = len(combo_slots)
        ratio = R["option_pattern"]["ratio_default"]
        pc = {"P1": round(n_combo * ratio["P1"]), "P3": round(n_combo * ratio["P3"])}
        pc["P2"] = n_combo - pc["P1"] - pc["P3"]
        for _ in range(500):
            seq = self._f_expand(pc); rng.shuffle(seq)
            if max_run(seq) <= R["option_pattern"]["max_consecutive_same"]:
                break
        for i, p in zip(combo_slots, seq):
            slots[i]["option_pattern"] = p
        ts_default = self._f__key_prefix(R["answer"], "combo_truth_set_default_for_")
        rr = {k: self._f_scaled(v, size) for k, v in R["answer"]["combo_truth_set_range"].items()}
        ts_counts = {k: (v if size == 40 else min(max(round(v / 2), rr[k][0]), rr[k][1])) for k, v in ts_default.items()}
        diff = n_combo - sum(ts_counts.values())
        guard = 0
        while diff != 0 and guard < 200:
            guard += 1
            k = rng.choice(list(ts_counts))
            if diff > 0 and ts_counts[k] < rr[k][1]:
                ts_counts[k] += 1; diff -= 1
            elif diff < 0 and ts_counts[k] > rr[k][0]:
                ts_counts[k] -= 1; diff += 1
        if diff != 0:
            raise ValueError(f"진위 집합 쿼터 조정 실패(합답형 {n_combo})")
        lo, hi = self._f_scaled(R["answer"]["per_number_range"], size)
        target = size / 5
        best = None
        compat = {t: [p for p in self.PATTERNS if t in self.PATTERNS[p]] for t in ts_counts}
        for attempt in range(3000):
            # 진위 집합을 호환되는 P 배열 슬롯에 배정 (호환 패턴 적은 것부터)
            free = {p: [i for i in combo_slots if slots[i]["option_pattern"] == p] for p in self.PATTERNS}
            for p in free: rng.shuffle(free[p])
            ts = self._f_expand(ts_counts); rng.shuffle(ts)
            ts.sort(key=lambda t: len(compat[t]))
            assign = {}; stuck = False
            for t in ts:
                cands = [p for p in compat[t] if free[p]]
                if not cands:
                    stuck = True; break
                p = max(cands, key=lambda p: (len(free[p]), rng.random()))
                assign[free[p].pop()] = t
            if stuck:
                continue
            ans = {i: self.PATTERNS[slots[i]["option_pattern"]].index(t) + 1 for i, t in assign.items()}
            # 비합답 슬롯: 가장 부족한 번호로
            cnt = Counter(ans.values())
            for i in [s for s in order if slots[s]["response"] != self.COMBO]:
                n = min(range(1, 6), key=lambda x: (cnt[x], rng.random()))
                ans[i] = n; cnt[n] += 1
            seq = [ans[i] for i in order]
            ok = all(lo <= cnt[n] <= hi for n in range(1, 6)) and max_run(seq) <= R["answer"]["max_consecutive_same"]
            score = (0 if ok else 1, max_run(seq), sum(abs(cnt[n] - target) for n in range(1, 6)))
            if best is None or score < best[0]:
                best = (score, dict(ans), dict(assign))
            if ok and max_run(seq) <= R["answer"]["soft_max_consecutive_same"]:
                break
        if best is None:
            raise ValueError("진위 집합 배정 실패")
        _, ans, tsets = best
        for i in order:
            slots[i]["answer"] = ans[i]
            if i in tsets:
                slots[i]["truth_set"] = tsets[i]
            else:
                slots[i]["truth_set"] = None
                slots[i]["option_pattern"] = None


    def _f_assign_judgment(self, slots, rng, size):
        """영역별 계산 포함 쿼터(적격 셀만). 마지막 번호(40번 규칙)는 계산 우선."""
        R = self.RULES
        elig = set(R["judgment_mode"]["calc_eligible_cells"])
        last = max(slots)
        for i in slots:
            slots[i]["judgment"] = "논리"
        calc_slots = []
        for area, (n, r) in R["judgment_mode"]["calc_by_area"].items():
            if size != 40:
                lo_, hi_ = self._f_half(r); n = min(max(n // 2, lo_), hi_)
            cand = [i for i in slots if slots[i]["area"] == area and f"{area}|{slots[i]['type']}|{slots[i]['principle']}" in elig]
            if last in cand and area == "과학기술":  # 마지막 번호 계산 권장
                cand.remove(last); cand = [last] + cand
                chosen = cand[:n]
            else:
                rng.shuffle(cand); chosen = cand[:n]
            if len(chosen) < n:
                slots[min(slots)]["notes"].append(f"{area} 계산 쿼터 {n} 중 {len(chosen)}만 배정(적격 셀 부족)")
            calc_slots += chosen
        for i in calc_slots:
            slots[i]["judgment"] = "논리+계산"
        pure = [i for i in calc_slots if slots[i]["area"] in ("사회", "과학기술", "규범")]
        if pure:
            slots[rng.choice(pure)]["judgment"] = "계산"


    def _f_assign_difficulty(self, slots, rng, size):
        """난이도 쿼터 + 위치 제약(40 기준 번호. 20문항은 source_slot으로 찾는다)."""
        R = self.RULES
        if size == 40:
            dq = {int(k): v[0] for k, v in R["difficulty"]["quota"].items()}
        else:
            dq = {int(k): v[0] / 2 for k, v in R["difficulty"]["quota"].items()}
            base = {k: int(v) for k, v in dq.items()}
            rest = size - sum(base.values())
            for k in sorted(dq, key=lambda k: -(dq[k] - base[k]))[:rest]:
                base[k] += 1
            dq = base
        dseq = self._f_expand(dq)
        pos_rule = R["difficulty"]["position_rules"]

        def allowed(i):
            i = slots[i].get("source_slot", i)
            for k, v in pos_rule.items():
                if "-" in k:
                    a, b = map(int, k.split("-"))
                    if a <= i <= b:
                        return v
                elif int(k) == i:
                    return v
            return [1, 5]
        for attempt in range(2000):
            rng.shuffle(dseq)
            # 어려운 것은 계산·논리·과학 쪽으로 몰리게 정렬 후 제약 체크
            trial = {}
            pool = sorted(dseq, reverse=True)
            hard_pref = sorted(slots, key=lambda i: (-(slots[i]["judgment"] != "논리"), -(slots[i]["area"] in ("논리학·수학", "과학기술")), rng.random()))
            okk = True
            for i in hard_pref:
                lo_, hi_ = allowed(i)
                pick = next((d for d in pool if lo_ <= d <= hi_), None)
                if pick is None:
                    okk = False; break
                pool.remove(pick); trial[i] = pick
            if okk:
                break
        else:
            raise ValueError("난이도 배정 실패: position_rules와 quota가 모순")
        for i in slots:
            slots[i]["difficulty"] = trial[i]


    def _f_sample20(self, seed=0, variant=None, tries=400):
        """같은 seed의 40 설계에서 영역·유형 절반 층화 추출 → 번호 다시 매김 → 정답 재배정 → 20 검증 통과본."""
        rng = random.Random(f"20-{seed}")
        last_errs = []
        for k in range(tries):
            base = self._f_sample(seed if k < tries // 2 else seed * 1009 + k, variant)  # 처음 절반은 같은 40 설계에서
            S = {s["slot"]: s for s in base["slots"]}
            dslot = next(i for i in S if S[i]["response"] == self.DIAGRAM)
            last = max(S)
            required = {1, 2, dslot, last}
            keep = []
            for area in self.AREAS:
                area_slots = [i for i in sorted(S) if S[i]["area"] == area]
                want = self.HALF_AREAS[area]
                by_type = defaultdict(list)
                for i in area_slots:
                    by_type[S[i]["type"]].append(i)
                # 유형별 목표 = 절반(반올림 방향은 무작위), 합을 영역 목표에 맞춤
                goal = {t: len(v) // 2 + (len(v) % 2 and rng.random() < 0.5) for t, v in by_type.items()}
                for i in required & set(area_slots):
                    goal[S[i]["type"]] = max(goal[S[i]["type"]], sum(1 for j in required & set(area_slots) if S[j]["type"] == S[i]["type"]))
                types = list(goal)
                guard = 0
                while sum(goal.values()) != want and guard < 200:
                    guard += 1
                    t = rng.choice(types)
                    floor_t = sum(1 for j in required & set(area_slots) if S[j]["type"] == t)
                    if sum(goal.values()) < want and goal[t] < len(by_type[t]):
                        goal[t] += 1
                    elif sum(goal.values()) > want and goal[t] > floor_t:
                        goal[t] -= 1
                picked = []
                for t, n in goal.items():
                    req = [i for i in by_type[t] if i in required]
                    rest = [i for i in by_type[t] if i not in required]
                    rng.shuffle(rest)
                    picked += req + rest[:max(0, n - len(req))]
                keep += sorted(picked)
            keep.sort()
            if len(keep) != 20 or not required <= set(keep):
                continue
            slots = {}
            for n, i in enumerate(keep, 1):
                s = json.loads(json.dumps(S[i], ensure_ascii=False))
                s["slot"] = n; s["source_slot"] = i
                if i == last:
                    s["notes"].append("마지막 번호: 40번 규칙(과학기술 언4/평4·합답형)")
                slots[n] = s
            try:
                self._f_assign_answers(slots, rng, 20)
                self._f_assign_judgment(slots, rng, 20)
                self._f_assign_difficulty(slots, rng, 20)
            except ValueError as e:
                last_errs = [str(e)]; continue
            design = {"meta": {"rules": self.RULES["meta"]["version"], "seed": seed, "size": 20, "base_seed": base["meta"]["seed"]},
                      "slots": [slots[n] for n in range(1, 21)]}
            errs, _ = self._f_validate(design)
            if not errs:
                return design
            last_errs = errs
        raise ValueError("표준 20문항 설계 실패: " + "; ".join(last_errs[:5]))


    def _f_validate(self, design):
        R = self.RULES; S = design["slots"]; errs = []; warns = []
        size = len(S)
        if size not in self.SIZES:
            return [f"표준 회차는 {self.SIZES}문항인데 {size}문항"], []
        sc = lambda r: self._f_scaled(r, size)
        by = lambda f: Counter(s[f] for s in S)

        # 블록 순서·개수
        seq_area = [s["area"] for s in S]
        order_idx = [self.AREAS.index(a) for a in seq_area]
        if order_idx != sorted(order_idx):
            errs.append("영역 블록 순서 위반(규범→인문→사회→논리학·수학→과학기술)")
        for a, r in R["blocks"]["count_range"].items():
            r = r if size == 40 else [self.HALF_AREAS[a], self.HALF_AREAS[a]]
            if not in_range(by("area")[a], r):
                errs.append(f"{a} 문항 수 {by('area')[a]} ∉ {r}")

        # 유형 쿼터
        for t, (d, r) in R["type_quota"]["total"].items():
            if not in_range(by("type")[t], sc(r)):
                errs.append(f"유형 {t} 총 {by('type')[t]} ∉ {sc(r)}")
        at = Counter((s["area"], s["type"]) for s in S)
        for a, tq in R["type_quota"]["by_area"].items():
            for t, (d, r) in tq.items():
                if not in_range(at[(a, t)], sc(r)):
                    errs.append(f"{a}|{t} {at[(a, t)]} ∉ {sc(r)}")
        # 원리 쿼터 (20문항은 셀 존재만 — 절반 범위는 셀이 너무 잘아 경고)
        atp = Counter((s["area"], s["type"], str(s["principle"])) for s in S)
        for key, pq in R["principle_quota"].items():
            if key.startswith("_") or key.startswith("evidence") or "|" not in key:
                continue
            a, t = key.split("|")
            for p, (d, r) in pq.items():
                if not in_range(atp[(a, t, p)], sc(r)):
                    (errs if size == 40 else warns).append(f"원리 {key}|{p} {atp[(a, t, p)]} ∉ {sc(r)}")
        for s in S:
            key = f"{s['area']}|{s['type']}"
            if key not in R["principle_quota"] or str(s["principle"]) not in R["principle_quota"][key]:
                errs.append(f"슬롯 {s['slot']} 원리 {s['type_code']} 은 기출에 없는 셀")
            if s["type_code"][:2] != "11":
                errs.append(f"슬롯 {s['slot']} 코드 {s['type_code']} 기준·귀속은 11이어야 함")

        # 슬롯 고정 (마지막 번호는 40번 규칙)
        SR = R["slot_rules"]
        s1, s2, sl = S[0], S[1], S[-1]
        if s1["area"] != "규범" or s1["type"] not in SR["1"]["type_allowed"]: errs.append("1번 규범·허용 유형 위반")
        if s1["response"] != self.COMBO or s1["polarity"] != "옳은 것": errs.append("1번은 합답형·옳은 것")
        if s1["difficulty"] not in SR["1"]["difficulty_allowed"]: errs.append(f"1번 난이도 {s1['difficulty']} ∉ {SR['1']['difficulty_allowed']}")
        if s2["area"] != "규범" or s2["type"] not in SR["2"]["type_allowed"]: errs.append("2번 규범·허용 유형 위반")
        if s2["difficulty"] not in SR["2"]["difficulty_allowed"]: errs.append(f"2번 난이도 {s2['difficulty']}")
        if size == 40:
            for i, p in ((31, "5"), (32, "1")):
                if S[i - 1]["type"] != "모형 추리" or str(S[i - 1]["principle"]) != p: errs.append(f"{i}번은 모형추리 원리 {p}")
            for i in (33, 34):
                if str(S[i - 1]["principle"]) not in SR["33"]["principle_allowed"]: errs.append(f"{i}번 원리 ∉ {{2,4}}")
            if {str(S[32]["principle"]), str(S[33]["principle"])} != {"2", "4"}: warns.append("33·34번 원리가 {2,4} 한 쌍이 아님")
        else:
            model = [s for s in S if s["area"] == "논리학·수학"]
            if any(s["type"] != "모형 추리" for s in model): errs.append("논리학·수학 블록은 모형 추리")
            if len({str(s["principle"]) for s in model}) < len(model): warns.append("모형 추리 두 문항의 원리가 같음")
        if sl["area"] != "과학기술" or sl["type"] not in SR["40"]["type_allowed"] or str(sl["principle"]) != "4": errs.append(f"{size}번(마지막) 과학기술 언4/평4 위반")
        if sl["response"] != self.COMBO: errs.append(f"{size}번(마지막) 합답형")
        dia = [s for s in S if s["response"] == self.DIAGRAM]
        if len(dia) != 1: errs.append(f"도식 문항 {len(dia)}개 (1개여야)")
        else:
            d = dia[0]
            lo_d, hi_d = SR["diagram"]["slot_allowed"] if size == 40 else (min(s["slot"] for s in S if s["area"] == "인문"), max(s["slot"] for s in S if s["area"] == "인문"))
            if not (d["area"] == "인문" and d["type"] == "논증 분석" and str(d["principle"]) == "1" and lo_d <= d["slot"] <= hi_d):
                errs.append(f"도식 문항은 인문 논증분석 원리1, 슬롯 [{lo_d}, {hi_d}]")
            if d["stem_task"] != "분석": errs.append("도식 문항 발문 작업은 분석")

        # 응답 형식
        rc = by("response")
        for k, (d, r) in R["response_format"]["quota"].items():
            r = r if k == self.DIAGRAM else sc(r)
            if not in_range(rc[k], r): errs.append(f"응답 {k} {rc[k]} ∉ {r}")
        if rc.get("ㄱㄴㄷㄹ 합답형", 0): errs.append("ㄱㄴㄷㄹ 합답형 금지")
        nca = Counter(s["area"] for s in S if s["response"] != self.COMBO)
        for a, (d, r) in R["response_format"]["non_combo_by_area"].items():
            if not in_range(nca[a], sc(r)): errs.append(f"{a} 비합답 {nca[a]} ∉ {sc(r)}")
        for s in S:
            if s["response"] == self.COMBO and s["statement_count"] != 3: errs.append(f"슬롯 {s['slot']} 합답형 보기 3개")

        # P 배열
        combo = [s for s in S if s["response"] == self.COMBO]; n = len(combo)
        pcnt = Counter(s["option_pattern"] for s in combo)
        for p, r in R["option_pattern"]["ratio_range"].items():
            tol = 0.02 if size == 40 else 1.5 / n  # 20문항은 ±1문항 여유
            if not (r[0] - tol <= pcnt[p] / n <= r[1] + tol): errs.append(f"{p} 비율 {pcnt[p]}/{n}={pcnt[p]/n:.2f} ∉ {r}")
        if max_run([s["option_pattern"] for s in combo]) > R["option_pattern"]["max_consecutive_same"]: errs.append("P 배열 연속 4 초과")
        for s in combo:
            if s["option_pattern"] not in self.PATTERNS: errs.append(f"슬롯 {s['slot']} P 배열 {s['option_pattern']} 금지")
            elif self.PATTERNS[s["option_pattern"]].index(s["truth_set"]) + 1 != s["answer"]:
                errs.append(f"슬롯 {s['slot']} 정답 {s['answer']} ≠ {s['option_pattern']}에서 {s['truth_set']} 위치")

        # 정답
        ac = by("answer"); lo, hi = sc(R["answer"]["per_number_range"])
        for k in range(1, 6):
            if not lo <= ac[k] <= hi: errs.append(f"정답 {k} {ac[k]}개 ∉ [{lo},{hi}]")
        mr = max_run([s["answer"] for s in S])
        if mr > R["answer"]["max_consecutive_same"]: errs.append(f"정답 연속 {mr}")
        elif mr > R["answer"]["soft_max_consecutive_same"]: warns.append(f"정답 연속 {mr} (권장 ≤2)")
        tc = Counter({1: 0, 2: 0, 3: 0})
        for s in combo: tc[len(s["truth_set"])] += 1
        for k, (d, r) in [(k, v) for k, v in R["answer"]["combo_truth_count"].items() if not k.startswith("_")]:
            if not in_range(tc[int(k)], sc(r)): errs.append(f"○ {k}개 정답 {tc[int(k)]} ∉ {sc(r)}")
        tsc = Counter(s["truth_set"] for s in combo)
        for k, r in R["answer"]["combo_truth_set_range"].items():
            if not in_range(tsc[k], sc(r)): warns.append(f"정답 집합 {k} {tsc[k]} ∉ {sc(r)}")

        # 발문
        pol = by("polarity")
        for k, (d, r) in R["stem"]["polarity_quota"].items():
            if not in_range(pol[k], sc(r)): errs.append(f"극성 {k} {pol[k]} ∉ {sc(r)}")
        for s in S:
            if s["response"] == self.COMBO and s["polarity"] != "옳은 것": errs.append(f"슬롯 {s['slot']} 합답형은 옳은 것")
            if s["polarity"] == "옳지 않은 것" and s["response"] != self.FIVE: errs.append(f"슬롯 {s['slot']} 옳지 않은 것은 5지 진술 선택형에서만")
            key = f"{s['type']}|{s['principle']}"
            allowed_t = R["stem"].get("task_by_type_principle", {}).get(key, R["stem"]["task_by_type"][s["type"]])
            if s["stem_task"] not in allowed_t: errs.append(f"슬롯 {s['slot']} {key}에 발문 작업 {s['stem_task']} 기출 0건")
            allowed_b = R["stem"].get("basis_by_type_principle", {}).get(key)
            if allowed_b and s["stem_basis"] not in allowed_b: errs.append(f"슬롯 {s['slot']} {key}에 발문 근거 {s['stem_basis']} 기출 0건")
        bc = by("stem_basis")
        for k, (d, r) in R["stem"]["basis_quota"].items():
            if not in_range(bc[k], sc(r)): errs.append(f"근거 {k} {bc[k]} ∉ {sc(r)}")
        tk = by("stem_task")
        for k, (d, r) in R["stem"]["task_quota_total"].items():
            if not in_range(tk[k], sc(r)): warns.append(f"발문 작업 {k} {tk[k]} ∉ {sc(r)}")

        # 판단 방식
        jc = by("judgment")
        for k, (d, r) in R["judgment_mode"]["quota"].items():
            if not in_range(jc[k], sc(r)): errs.append(f"판단 {k} {jc[k]} ∉ {sc(r)}")
        calc = [s for s in S if s["judgment"] != "논리"]
        ca = Counter(s["area"] for s in calc)
        for a, (d, r) in R["judgment_mode"]["calc_by_area"].items():
            if not in_range(ca[a], sc(r)): errs.append(f"{a} 계산 포함 {ca[a]} ∉ {sc(r)}")
        elig = set(R["judgment_mode"]["calc_eligible_cells"])
        for s in calc:
            if f"{s['area']}|{s['type']}|{s['principle']}" not in elig: warns.append(f"슬롯 {s['slot']} {s['type_code']} 계산 포함은 기출 미관측 셀")

        # 난이도
        dc = by("difficulty")
        for k, (d, r) in R["difficulty"]["quota"].items():
            if not in_range(dc[int(k)], sc(r)): errs.append(f"난이도 {k} {dc[int(k)]} ∉ {sc(r)}")
        bands = R["difficulty"]["bands"]; mid = {int(k): (v[0] + v[1]) / 2 for k, v in bands.items()}
        est = sum(mid[s["difficulty"]] for s in S) / size
        if not in_range(est, R["difficulty"]["mean_target"]): warns.append(f"추정 평균 정답률 {est:.2f} ∉ {R['difficulty']['mean_target']}")

        # 글자수
        tot_lo = sum(s["chars_range"][0] for s in S); tot_hi = sum(s["chars_range"][1] for s in S)
        tgt = [x * size // 40 for x in R["length"]["set_total_target"]]
        if tot_hi < tgt[0] or tot_lo > tgt[1]:
            warns.append(f"회차 총 글자수 범위 [{tot_lo},{tot_hi}]가 목표 {tgt}와 안 겹침")
        return errs, warns
