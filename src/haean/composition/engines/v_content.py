"""Instance-owned content algorithms from the local upstream designer.

Instructions in returned specs belong to this profile; they are not general
authoring policy or evidence of item quality, originality or expert approval.
"""

import random
import re
import math
from collections import Counter, defaultdict
from . import adjacency as AJ
from .adjacency import max_run


class ContentAlgorithms:

    def _init_content(self):
        self.TODO = '__TODO'
        self.STAGE = {'출처익명화': '은폐', '시공간이식': '은폐', '용어치환': '은폐', '요건축약': '압축', '원리형식화': '압축', '요건재정의': '변별점', '수치변경': '변별점', '규칙신설': '변별점', '대립구조화': '장치', '사례결합': '장치', '실험·자료가공': '장치', '원형유지': '원형'}

    def _c_wpick(self, dist, rng, exclude=()):
        items = [(k, v[0] if isinstance(v, list) else v) for k, v in dist.items() if k not in exclude and not k.startswith("_")]
        if not items:
            return None
        ks, ws = zip(*items)
        return rng.choices(ks, weights=ws, k=1)[0]


    def _c_group_of(self, area, sub):
        for g, subs in self.CC["subdomain_groups"].get(area, {}).items():
            if sub in subs:
                return g
        return None


    def _c_m20_index(self):
        by_cell, by_group, by_id = defaultdict(list), defaultdict(list), {}
        for m in self.CR["m20_materials"]:
            by_cell[m["cell"]].append(m); by_id[m["id"]] = m
            g = self._c_group_of(m["area"], m["subdomain"])
            if g:
                by_group[(m["area"], g)].append(m)
        return by_cell, by_group, by_id


    def _c_allocate_groups(self, area, slots, rng):
        """영역 슬롯(세트는 한 단위)에 세부영역 그룹을 비례 배분."""
        if not slots:
            return {}, {}
        dist = self.CR["areas"][area]["subdomain_dist_all"]
        gw = Counter()
        for sub, (n, _) in dist.items():
            g = self._c_group_of(area, sub)
            if g: gw[g] += n
        units = []
        seen = set()
        for s in slots:
            if s["slot"] in seen: continue
            u = [x for x in slots if x["slot"] in self.SET_OF.get(s["slot"], (s["slot"],))]
            seen.update(x["slot"] for x in u); units.append(u)
        groups = list(gw); weights = [gw[g] for g in groups]; n = len(units)
        total = sum(weights); raw = [w / total * n for w in weights]
        alloc = [int(x) for x in raw]
        for i in sorted(range(len(raw)), key=lambda i: raw[i] - alloc[i], reverse=True)[: n - sum(alloc)]:
            alloc[i] += 1
        bag = [g for g, k in zip(groups, alloc) for _ in range(k)]
        assign = {}
        adj = self.CR["areas"][area].get("adjacency_all")
        if adj:
            # 언어논리는 영역이 번호 전체에 섞여 있으므로 '물리적으로 이웃한 같은 영역 쌍'에만 기출 비율을 맞춘다:
            # 같은 그룹이 이웃하는 쌍 수 ≈ same_group_rate × (이웃 쌍 수), 물리적 연속 ≤ min(기출 최대, hard_max_group_run)
            max_len = min(int(adj.get("max_group_run") or 2), self.CC["adjacency"].get("hard_max_group_run", 3))
            heads = [u[0]["slot"] for u in units]
            span = {u[0]["slot"]: (min(x["slot"] for x in u), max(x["slot"] for x in u)) for u in units}
            pairs = [(a, b) for a, b in zip(heads, heads[1:]) if span[b][0] == span[a][1] + 1]
            target = round(float(adj.get("same_group_rate") or 0.0) * len(pairs))
            best, best_gap = None, None
            for attempt in range(400):
                rng.shuffle(bag)
                trial = {}
                for u, g in zip(units, bag):
                    hint = self.CC["group_by_principle_hint"].get(f"{u[0]['area']}|{u[0]['type']}|{u[0]['principle']}")
                    for x in u: trial[x["slot"]] = hint or g
                same = sum(trial[a] == trial[b] for a, b in pairs)
                run = 1; longest = 1
                for a, b in pairs:
                    run = run + 1 if trial[a] == trial[b] else 1
                    longest = max(longest, run)
                gap = abs(same - target) + (10 if longest > max_len else 0)
                if best is None or gap < best_gap:
                    best, best_gap = dict(trial), gap
                if gap == 0:
                    break
            return best, dict(gw)
        for attempt in range(300):
            rng.shuffle(bag); assign = {}
            for u, g in zip(units, bag):
                hint = self.CC["group_by_principle_hint"].get(f"{u[0]['area']}|{u[0]['type']}|{u[0]['principle']}")
                for x in u: assign[x["slot"]] = hint or g
            order = [assign[s["slot"]] for s in sorted(slots, key=lambda s: s["slot"]) if self.SET_OF.get(s["slot"], (s["slot"],))[0] == s["slot"]]
            if max_run(order) <= self.CC["adjacency"]["max_same_group_consecutive"]:
                break
        return assign, dict(gw)


    def _c_range_text(self, area, group, cs, s):
        frame = self.CC["judgment_frames"].get(f"{self.T_CODE[s['type']]}|{s['principle']}", {}).get("frame", "")
        dev = cs.get("device", {})
        device = ("원형유지(설명문·사료 서술, 실재 사실 그대로)" if dev.get("원형유지", 0) >= 0.5 else
                  "실험·자료가공(가설-설계-결과)" if dev.get("실험·자료가공", 0) >= 0.3 else
                  "대립구조화(갑·을·병 또는 A·B 견해)" if dev.get("대립구조화", 0) >= 0.3 else
                  "사례결합(<사례>·<상황>)" if dev.get("사례결합", 0) >= 0.3 else "원리형식화(정의·조건문)")
        hk = f" · {s['history_kind']}" if s.get("history_kind") else ""
        return (f"{area} · {group}{hk} — {frame}. 구성 방식: {device}. 하위 쟁점 하나로 좁힌다. "
                "역사·제도·사료·과학 실험·법령은 실명과 실제 고유명사를 그대로 쓴다(기출 원형유지: 봉평비·법흥왕·『경국대전』·문익점). "
                "철학·사회이론의 입장은 실명(공자·노자)이나 기호(철학자 A·B, 갑·을, ㉠[주장])로 세운다. '한 연구(진)'·'한 철학자'·'한 고대 국가' 같은 무표지 익명은 지문당 1회 이하(출처 메모 필수).")


    def _c_pick_operators(self, cs, rng, judgment):
        combos = cs.get("operator_combos") or []
        ops = [o.strip() for o in combos[rng.randrange(len(combos))].split("+")] if combos else ["원형유지", "요건축약"]
        byst = defaultdict(list)
        for o in ops:
            byst[self.STAGE.get(o, "기타")].append(o)
        if not byst["변별점"]:
            byst["변별점"].append("문언 변별(귀속·양화·인과 방향, 연산자 없음)")
        if judgment != "논리" and "수치변경" not in byst["변별점"] and cs.get("operators", {}).get("수치변경"):
            byst["변별점"].append("수치변경")
        return {k: v for k, v in byst.items() if v}


    def _c_option_plan(self, s, traps, rng):
        """5지형 선지 ①~⑤ 정오·오답 경로. 극성이 '옳지 않은 것'이면 정답 선지만 거짓."""
        neg = self._f_negative(s.get("stem"), s["polarity"])
        out = []
        for k in range(1, 6):
            is_ans = k == s["answer"]
            true = (not is_ans) if neg else is_ans
            out.append({"선지": "①②③④⑤"[k - 1], "정오": "○" if true else "×", "정답": is_ans,
                        "오답_경로": None if true else (rng.choice(traps) if traps else "시점·주체·대상 귀속")})
        if s["type"] in ("일치부합", "추론", "사례 찾기·적용") or s.get("set"):
            od = self.CC.get("option_design", {}); lo, hi = od.get("answer_combo_share", {}).get("target", [0.45, 0.6])
            n_none = 0
            for o in out:   # 선지 라벨(개념데이터 v3.5): 맞는 진술 = 직접/조합, 틀린 진술 = 바꿔치기 위주·근거없음 ≤2
                if o["정오"] == "○":
                    o["선지_라벨"] = "조합" if rng.random() < (lo + hi) / 2 else "직접"
                elif n_none < 2 and rng.random() < 0.2:
                    o["선지_라벨"] = "근거없음"; n_none += 1
                else:
                    o["선지_라벨"] = "바꿔치기"
        return out


    def _c_design_slot(self, s, rng, idx, ledger_entries, latest_year, group, source_used, source_cap, inherit=None):
        cell = f"{s['area']}|{s['type']}|{s['principle']}"; cs = self.CR["cells"].get(cell, {})
        by_cell, by_group, by_id = idx
        key = f"{self.T_CODE[s['type']]}|{s['principle']}"
        frame = self.CC["judgment_frames"].get(key, {"frame": "", "traps": []})
        pool = [by_id[i] for i in cs.get("reference_pool", []) if i in by_id]
        latest_same = [m for m in pool if m["year"] == latest_year]
        archetype = min(latest_same, key=lambda m: abs(m["slot"] - s["slot"])) if latest_same else (pool[0] if pool else None)
        n_refs = self.CC["reference_selection"]["design_refs"]["same_cell"]
        design_refs = [m["id"] for m in pool if not archetype or m["id"] != archetype["id"]][:n_refs]
        writing_refs = [m["id"] for m in reversed(self.CR["m20_materials"]) if m["cell"] != cell and m["area"] == s["area"]][:self.CC["reference_selection"]["writing_refs"]["same_narration_or_organization"]]
        avoid_cell = [f"{m['id']} {m['material']}" for m in pool[:8]]
        avoid_group = [f"{m['id']} {m['material']}" for m in by_group.get((s["area"], group), [])][-12:]
        avoid_ledger = [f"{e.get('회차')}-{e.get('slot')} {e.get('material')}" for e in ledger_entries if e.get("area") == s["area"]]
        if inherit:  # 세트 둘째 문항
            src, conceal, ops = inherit["원천"], inherit["은폐_수준"], inherit["변형_연산자"]
        else:
            fict_ok = any(cell.startswith(pf) for pf in self.CC["fictional"]["allowed_cells_prefix"])
            gs = self.CC["group_sources"].get(s["area"], {}); allowed_src = gs.get(group) or gs.get("*") or []
            excl = set() if fict_ok else {"가상 창작"}
            excl |= {k for k in cs.get("source", {}) if allowed_src and k not in allowed_src}
            excl |= {k for k, n in source_used.items() if n >= source_cap.get(k, 99)}
            src = self._c_wpick(cs.get("source", {}), rng, exclude=excl) or self._c_wpick(self.CR["areas"][s["area"]]["source"], rng, exclude=excl) or (allowed_src[0] if allowed_src else "가상 창작")
            source_used[src] = source_used.get(src, 0) + 1
            conceal = self._c_wpick(cs.get("concealment", {"중": [1, 1]}), rng)
            ops = self._c_pick_operators(cs, rng, s["judgment"])
        traps = list(cs.get("trap_types", {}))[:3] or frame["traps"][:3]
        clean = lambda x: re.split(r"\s[—–-]\s", x)[0].strip() if x else x
        if s["response"] == self.COMBO:
            rel = self._c_wpick(cs.get("statement_relation", {"같은 틀 병렬": [1, 1]}), rng)
            base_task = clean(self._c_wpick(cs.get("statement_task", {}), rng) or "내용 일치")
            person = clean(self._c_wpick(cs.get("statement_person", {}), rng) or "없음")
            plan = [{"진술": k, "진위": "○" if k in s["truth_set"] else "×",
                     "작업": base_task if str(rel).startswith("같은 틀") else clean(self._c_wpick(cs.get("statement_task", {}), rng) or base_task),
                     "사례": clean(self._c_wpick(cs.get("statement_case", {}), rng) or "없음"), "인물": person,
                     "오답_경로": None if k in s["truth_set"] else (rng.choice(traps) if traps else "함축·논리 방향")} for k in "ㄱㄴㄷ"]
            if s["type"] == "강화·약화":   # 오답 보기 판단불가:방향뒤집기 ≈ 1:1 (2024~26 해설서)
                for x in plan:
                    if x["진위"] == "×": x["보기_라벨"] = rng.choice(["판단불가", "방향뒤집기"])
            stmt = {"진술_간_관계": rel, "진술": plan}
        else:
            stmt = {"진술_간_관계": "선지 5개 직접 진술" if s["response"].startswith("5지") or "빈칸" in s["response"] else s["response"],
                    "선지": self._c_option_plan(s, traps, rng)}
        calc = None
        if s["judgment"] != "논리":
            cd = self.CC["calc_design"]
            calc = {"연산": cd["ops"], "수치_개수": cd["numbers"], "단계": cd["steps"], "경계값_함정": cd["boundary_trap"], "지시": cd["note"]}
        fseq = (cs.get("passage_function_seq") or ["사실-설명 | 사실-설명"])[0]
        comp = self.RULES["length"]["component_median"]
        return {
            "slot": s["slot"], "type_code": s["type_code"], "cell": cell, "유형이름": s["type_name"],
            "소재": {"대분류": group, "세부영역": s.get("subarea"), "역사구분": s.get("history_kind"),
                     "범위_지시": self._c_range_text(s["area"], group, cs, s) if not inherit else f"세트 공통 지문 — {inherit['대분류']} 소재를 첫 문항({inherit['slot']}번)과 공유",
                     "원천": src, "가상_창작_허용": src == "가상 창작", "사실_출처": inherit["사실_출처"] if inherit else self._c_wpick(cs.get("fact_origin", {}), rng),
                     "은폐_수준": conceal, "변형_연산자": ops, "변별점_지시": self.CC["discriminator_rule"]["rule"],
                     "회피": {"원형_기출": f"{archetype['id']} {archetype['material']}" if archetype else None, "같은_셀_기출_소재": avoid_cell,
                              "같은_대분류_기출_소재": avoid_group, "대장_사용_소재": avoid_ledger, "AI_편중_블랙리스트": self.CC["ai_overuse_blacklist"].get(s["area"], [])},
                     "출처_메모": {k: self.TODO for k in self.CC["source_memo_schema"]["fields"]}},
            "참고_기출": {"설계_참고(같은 셀)": design_refs, "작성_참고(같은 영역 서술)": writing_refs, "회피_원형": archetype["id"] if archetype else None,
                          "원형_판단포인트(다르게 짤 것)": archetype["discriminator"] if archetype else None, "혼동_지점_예(같은 셀 기출)": cs.get("confusion_examples", [])[:3],
                          "주의": self.CC["reference_selection"]["design_refs"]["role"]},
            "논리_설계": {"판단_방식": s["judgment"], "핵심_판단_틀": frame["frame"], "진위_집합": s["truth_set"], "정답_번호": s["answer"],
                          "정답_조건": (f"{'·'.join(s['truth_set'])} 참, {'·'.join(k for k in 'ㄱㄴㄷ' if k not in s['truth_set']) or '없음'} 거짓" if s["response"] == self.COMBO
                                      else f"선지 {s['answer']}만 {'거짓' if self._f_negative(s.get('stem'), s['polarity']) else '참'}"),
                          "함정_유형_후보": traps, "계산_설계": calc,
                          "우회_점검": ["지문 없이 상식·배경지식만으로 정답이 나오면 실패", "지문에 없는 비교·평가를 보태야 정답이 되면 실패", "진술(선지) 하나를 빼도 정답이 유일한지"]},
            "지문_구조": {"블록_기능_시퀀스": fseq, "서술": next(iter(cs.get("passage_narration", {"평서": 0}))), "주체": next(iter(cs.get("passage_subject", {"없음": 0}))),
                          "조직_예": cs.get("passage_organization", [])[:2], "세트": s["set"],
                          "글자수": {"범위": s["chars_range"], "기준": s.get("chars_basis", "총(발문+지문+보기/선지)"), "지문_중앙값": comp["지문"][s["type"]], "보기·선지_중앙값": comp["보기·선지"][s["type"]], "발문": comp["발문"]}},
            "보기_설계" if s["response"] == self.COMBO else "선지_설계": stmt,
            "발문": {"문장": s["stem"], "근거": s["stem_basis"], "작업": s["stem_task"], "극성": s["polarity"], "단서": s["stem_proviso"]},
        }


    def _c_design_set(self, design, ledger=None, seed=0):
        rng = random.Random(seed)
        slots = design["slots"]
        latest_year = max(m["year"] for m in self.CR["m20_materials"])
        idx = self._c_m20_index(); ledger_entries = (ledger or {}).get("entries", [])
        groups, gw_all = {}, {}
        if all(s.get("subarea") for s in slots):
            # 2026-10-18: 세부영역은 형식 설계가 자리별로 배정한다(1·2번 역사, 1~5 과학 0, 13·33·34 공직/기호 …). 내용 설계는 그 안에서 세부 소재만 고른다.
            for s in slots:
                groups[s["slot"]] = self._c_group_of(s["area"], s["subarea"]) or s["subarea"]
            for a in self.AREAS:
                gw_all[a] = dict(Counter(groups[s["slot"]] for s in slots if s["area"] == a))
        else:
            for a in self.AREAS:
                g, gw = self._c_allocate_groups(a, [s for s in slots if s["area"] == a], rng)
                groups.update(g); gw_all[a] = gw
        specs, firsts = [], {}
        for a in self.AREAS:
            ss = [s for s in slots if s["area"] == a]
            if not ss: continue
            cap = {k: math.ceil(v[1] * len(ss)) + 1 for k, v in self.CR["areas"].get(a, {"source": {}})["source"].items()}
            used = {}
            for s in ss:
                pair = self.SET_OF.get(s["slot"])
                inherit = None
                if pair and s["slot"] == pair[1] and pair[0] in firsts:
                    f = firsts[pair[0]]; inherit = {**f["소재"], "slot": pair[0]}
                sp = self._c_design_slot(s, rng, idx, ledger_entries, latest_year, groups[s["slot"]], used, cap, inherit)
                if pair and s["slot"] == pair[0]:
                    firsts[s["slot"]] = sp
                specs.append(sp)
        specs.sort(key=lambda x: x["slot"])
        set_level = {
            "원칙": self.CC["principles"],
            "대분류_배분": {a: dict(Counter(groups[s["slot"]] for s in slots if s["area"] == a)) for a in self.AREAS},
            "대분류_배분_근거(전체 세부영역 분포)": {a: dict(sorted(gw_all[a].items(), key=lambda x: -x[1])) for a in self.AREAS if gw_all.get(a)},
            "인접_규칙": {"배치": "세부영역 그룹은 기출 인접 통계(areas.adjacency_all — build_rules 재생성 뒤)가 있으면 그 비율대로 같은 분야를 붙이고, 없으면 같은 그룹 최대 2연속",
                      "세부_소재": self.CC["adjacency"].get("material_rule", "이웃한 두 문항은 세부 소재(화제·인물·사건·문헌)가 달라야 한다"),
                      "참고": self.CC["adjacency"]["separate_pairs_note"]},
            "세트": self.CC["set_rule"]["rule"],
            "가상_창작": {"슬롯": [sp["slot"] for sp in specs if sp["소재"]["원천"] == "가상 창작"], "규칙": self.CC["fictional"]["note"]},
            "계산_문항": [sp["slot"] for sp in specs if sp["논리_설계"]["판단_방식"] != "논리"],
            "회차_내_중복_금지": "같은 화제·인물·사건·실험이 두 자리에 나오지 않는다(세트 두 문항은 예외).",
            "출처_메모_의무": self.CC["source_memo_schema"], "AI_중복_회피_전략": self.CC["ai_overuse_blacklist"]["strategy"], "승인_절차": self.CC["approval"],
            "참고": {"기출_소재_대장(M20)": f"content_rules.json m20_materials {len(self.CR['m20_materials'])}문항", "회차_소재_대장(M30)": "material_ledger.json + 공유 문항풀(haean tools pool sync)", "대조기": "material_check.py"},
        }
        return {"meta": {"rules": self.CR["meta"]["version"], "seed": seed, "format_seed": design.get("meta", {}).get("seed")}, "회차": set_level, "슬롯": specs}
