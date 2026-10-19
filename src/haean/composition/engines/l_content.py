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
        """dist: {key: [count, ratio]} → 가중 추출"""
        items = [(k, v[0]) for k, v in dist.items() if k not in exclude and not k.startswith("_")]
        if not items:
            return None
        ks, ws = zip(*items)
        return rng.choices(ks, weights=ws, k=1)[0]


    def _c_group_of(self, area, subdomain):
        for g, subs in self.CC["subdomain_groups"][area].items():
            if subdomain in subs:
                return g
        return None


    def _c_area_detail(self, area, group, source):
        """해설 내용영역 표기 '대분류(세부)'의 세부(content_config.area_detail). 원천 규칙 → 그룹 규칙 → 기본값 순."""
        rule = self.CC.get("area_detail", {}).get(area, {})
        return rule.get(f"원천:{source}") or rule.get(group) or rule.get("*", "")


    def _c_area_label(self, area, detail):
        return f"{area}({detail})" if detail else area


    def _c_label_of_subdomain(self, area, subdomain, source=""):
        """기출 분류(통합데이터 내용영역 + 세부영역)도 같은 규칙으로: 대분류는 하드코딩된 분류 그대로, 세부영역이 양식 옵션에 포섭되면 괄호."""
        rule = self.CC.get("area_detail", {}).get(area, {})
        if f"세부:{subdomain}" in rule and not rule.get(f"원천:{source}"):
            return self._c_area_label(area, rule[f"세부:{subdomain}"])
        return self._c_area_label(area, self._c_area_detail(area, self._c_group_of(area, subdomain) or "", source))


    def _c_m20_index(self):
        by_cell, by_group, by_id = defaultdict(list), defaultdict(list), {}
        for m in self.CR["m20_materials"]:
            by_cell[m["cell"]].append(m); by_id[m["id"]] = m
            g = self._c_group_of(m["area"], m["subdomain"]) if m["subdomain"] else None
            if g:
                by_group[(m["area"], g)].append(m)
        return by_cell, by_group, by_id


    def _c_adjacency_of(self, area):
        """기출 인접 통계(content_rules areas[area].adjacency_2019plus). 없으면 독립 가정값."""
        return self.CR["areas"][area].get("adjacency_2019plus") or {"same_group_rate": 0.0, "same_group_expected": 0.0, "cluster_index": 1.0,
                                                               "max_group_run": self.CC["adjacency"]["max_same_group_consecutive"], "same_subdomain_rate": 0.0}


    def _c_allocate_groups(self, area, slots, rng):
        """영역 슬롯들에 세부영역 그룹을 비례 배분하고 기출 인접 통계대로 배치한다.
        기출은 같은 분야를 붙여 둔다(사회·과학기술·인문 cluster_index > 1: 경제학 25·26·27, 생명 35·36) — 그 비율로 run 을 만들고,
        논리학·수학처럼 cluster_index < 1 이면 교대 배치. run 길이는 기출 최대(max_group_run) 안. 원리 힌트 슬롯은 먼저 고정."""
        dist = self.CR["areas"][area]["subdomain_dist_2019plus"]
        adj = self._c_adjacency_of(area)
        gw = Counter()
        for sub, (n, _) in dist.items():
            g = self._c_group_of(area, sub)
            if g:
                gw[g] += n
        groups = list(gw); weights = [gw[g] for g in groups]
        n = len(slots)
        total = sum(weights); raw = [w / total * n for w in weights]
        alloc = [int(x) for x in raw]
        for i in sorted(range(len(raw)), key=lambda i: raw[i] - alloc[i], reverse=True)[: n - sum(alloc)]:
            alloc[i] += 1
        bag = []
        for g, k in zip(groups, alloc):
            bag += [g] * k
        fixed = {}
        for s in slots:
            hint = self.CC["group_by_principle_hint"].get(s["_cell"])
            if hint and hint in bag:
                fixed[s["slot"]] = hint; bag.remove(hint)
            elif hint:
                fixed[s["slot"]] = hint
        free = [s for s in slots if s["slot"] not in fixed]
        bag = bag[: len(free)]
        max_run = min(int(adj.get("max_group_run") or self.CC["adjacency"]["max_same_group_consecutive"]), self.CC["adjacency"].get("hard_max_group_run", 3))
        seq = AJ.arrange_runs(bag, float(adj.get("same_group_rate") or 0.0), max_run, rng)
        assign = dict(fixed)
        for s, g in zip(free, seq):
            assign[s["slot"]] = g
        return assign, dict(gw)


    def _c_pick_subdomains(self, area, slots, groups, rng):
        """슬롯마다 세부영역 하나(그룹 안 2019+ 분포 가중). 같은 그룹이 이웃하면 세부영역은 서로 다르게(생명 → 생태학 → 의학),
        세부영역이 하나뿐인 그룹(물리·화학)만 같은 세부영역이 이어진다 — 그때도 세부 소재(화제)는 달라야 한다(작성 단계 검사)."""
        dist = self.CR["areas"][area]["subdomain_dist_2019plus"]
        out = {}
        prev_group, run_used = None, set()
        for s in sorted(slots, key=lambda x: x["slot"]):
            g = groups[s["slot"]]
            if g != prev_group:
                run_used = set()
            cands = {sub: v for sub, v in dist.items() if self._c_group_of(area, sub) == g}
            if not cands:
                cands = {sub: [1, 1] for sub in self.CC["subdomain_groups"][area].get(g, [g])}
            pool = {k: v for k, v in cands.items() if k not in run_used} or cands     # 한 run 안에서는 세부영역을 다 다르게
            sub = self._c_wpick(pool, rng) or next(iter(pool))
            out[s["slot"]] = sub
            run_used.add(sub); prev_group = g
        return out


    def _c_range_text(self, area, group, cell_stats, s):
        """소재 범위 문장 — 고유명사 없이 분야·구성 방식·제외 조건만"""
        t = s["type"]; p = s["principle"]
        frame = self.CC["judgment_frames"].get(f"{self.T_CODE[t]}|{p}", {}).get("frame", "")
        dev = cell_stats.get("device", {})
        if "사례 없음" in frame:
            device = "설명문·정의·수치 관계(사례 블록 없음)"
        else:
            device = "사례결합(<사례>·사실관계)" if dev.get("사례결합", 0) >= 0.3 else "대립구조화(갑·을·병 견해 또는 복수 안)" if dev.get("대립구조화", 0) >= 0.3 else "실험·자료가공(가설-설계-결과)" if dev.get("실험·자료가공", 0) >= 0.3 else "원리형식화(원리1~3·정의문)"
        return f"{area} · {group} 분야 — {frame}. 구성 방식: {device}. 소재는 하위 쟁점 하나로 좁히고, 고유명사·실제 조문번호·학자 실명은 지문에 쓰지 않는다(출처 메모에만)."


    def _c_pick_operators(self, cell_stats, rng, judgment):
        combos = cell_stats.get("operator_combos") or []
        ops = combos[rng.randrange(len(combos))].split(" + ") if combos else ["출처익명화", "원리형식화"]
        byst = defaultdict(list)
        for o in ops:
            byst[self.STAGE.get(o, "기타")].append(o)
        # 변별점 연산자: 그 셀에서 변별점 연산자(요건재정의·수치변경·규칙신설)가 실제로 쓰이는 비율이 0.25 이상일 때만 보장.
        # 아니면(인문·과학 다수) 변형 없이 '문언 변별' — 원리형식화된 정의·조건의 함축·범위에서 갈린다.
        opstat = cell_stats.get("operators", {})
        disc_ratio = sum(opstat.get(k, [0, 0])[1] for k in ("요건재정의", "수치변경", "규칙신설"))
        if not byst["변별점"]:
            if disc_ratio >= 0.25 and "원형유지" not in ops:
                cand = {k: opstat[k] for k in ("요건재정의", "수치변경", "규칙신설") if k in opstat}
                byst["변별점"].append(self._c_wpick(cand, rng))
            else:
                byst["변별점"].append("문언 변별(연산자 없음)")
        if judgment != "논리" and "수치변경" not in byst["변별점"] and opstat.get("수치변경"):
            byst["변별점"].append("수치변경")
        return {k: v for k, v in byst.items() if v}


    def _c_design_slot(self, s, rng, idx, ledger_entries, latest_year, group, source_used, source_cap):
        cell = s["_cell"]; cs = self.CR["cells"].get(cell, {})
        by_cell, by_group, by_id = idx
        t, p = s["type"], s["principle"]; key = f"{self.T_CODE[t]}|{p}"
        frame = self.CC["judgment_frames"].get(key, {"frame": "", "traps": []})
        # ---- 참고·회피 기출
        pool = [by_id[i] for i in cs.get("reference_pool", []) if i in by_id]
        latest_same = [m for m in pool if m["year"] == latest_year]
        ref_slot = s.get("source_slot", s["slot"])  # 20문항은 40 기준 자리로
        archetype = min(latest_same, key=lambda m: abs(int(m["id"][-2:]) - ref_slot)) if latest_same else (pool[0] if pool else None)
        design_refs = [m["id"] for m in pool if not archetype or m["id"] != archetype["id"]][: self.CC["reference_selection"]["design_refs"]["same_cell"]]
        narr = next(iter(cs.get("passage_narration", {"평서": 0})))
        writing_refs = [m["id"] for m in self.CR["m20_materials"] if m["cell"] != cell and m["area"] == s["area"]][-self.CC["reference_selection"]["writing_refs"]["same_narration_or_organization"]:]
        avoid_cell = [f"{m['id']} {m['material']}" for m in pool[:8]]
        avoid_group = [f"{m['id']} {m['material']}" for m in by_group.get((s["area"], group), [])][-12:]
        avoid_ledger = [f"{e.get('회차')}-{e.get('slot')} {e.get('material')}" for e in ledger_entries if e.get("area") == s["area"]]
        # ---- 원천·변형
        fict_ok = any(cell.startswith(pf) for pf in self.CC["fictional"]["allowed_cells_prefix"])
        gs = self.CC["group_sources"][s["area"]]; allowed_src = gs.get(group) or gs.get("*") or []
        excl = set() if fict_ok else {"가상 창작"}
        excl |= set(k for k in cs.get("source", {}) if allowed_src and k not in allowed_src)
        excl |= set(k for k, n in source_used.items() if n >= source_cap.get(k, 99))
        source = self._c_wpick(cs.get("source", {}), rng, exclude=excl) or self._c_wpick(self.CR["areas"][s["area"]]["source"], rng, exclude=excl) or (allowed_src[0] if allowed_src else "가상 창작")
        source_used[source] = source_used.get(source, 0) + 1
        conceal = self._c_wpick(cs.get("concealment", {"중": [1, 1]}), rng)
        ops = self._c_pick_operators(cs, rng, s["judgment"])
        traps = [k for k in cs.get("trap_types", {})] or frame["traps"]
        traps = traps[:3] if traps else frame["traps"][:3]
        # ---- 진술 설계
        stmts = []
        clean = lambda x: re.split(r"\s[—–-]\s", x)[0].strip() if x else x
        person_scheme = clean(self._c_wpick(cs.get("statement_person", {}), rng) or "없음")  # 인물 체계는 문항당 하나
        if s["response"] == self.COMBO:
            rel = self._c_wpick(cs.get("statement_relation", {"같은 틀 병렬": [1, 1]}), rng)
            task_dist = cs.get("statement_task", {}); case_dist = cs.get("statement_case", {})
            base_task = clean(self._c_wpick(task_dist, rng) or "사례 적용 판정")
            for k in "ㄱㄴㄷ":
                true = k in s["truth_set"]
                task = base_task if rel.startswith("같은 틀") else clean(self._c_wpick(task_dist, rng) or base_task)
                stmts.append({"진술": k, "진위": "○" if true else "×",
                              "작업": task, "사례": clean(self._c_wpick(case_dist, rng) or "없음"), "인물": person_scheme,
                              "오답_경로": None if true else rng.choice(traps) if traps else "함축·논리 방향"})
        else:
            rel = "선지 5개 직접 진술" if s["response"] != self.DIAGRAM else "도식 선지"
        calc = None
        if s["judgment"] != "논리":
            cd = self.CC["calc_design"]
            calc = {"연산": cd["ops"], "수치_개수": cd["numbers"], "단계": cd["steps"], "경계값_함정": cd["boundary_trap"], "순수계산": s["judgment"] == "계산",
                    "지시": "계산식은 calculations 필드에 숫자·사칙연산만. 경계값(이상/초과·구간) 함정 1개를 거짓 진술에 심는다."}
        # ---- 지문 구조
        fseq = (cs.get("passage_function_seq") or ["사실-설명 | 사실-설명"])[0]
        subj = next(iter(cs.get("passage_subject", {"없음": 0})))
        labels = [k for k in cs.get("stem_labels", {}) if k != "-"]
        need_labels = []
        if s["stem_basis"] == "표지 지정":
            dflt = self.RULES["stem"].get("default_label_by_area_type", {}).get(f"{s['area']}|{t}", "<견해>")
            need_labels.append((labels[0] if labels else dflt).split(" + ")[0])
        if s["stem_task"] in ("판단", "적용"):
            need_labels.append("<사례>")
        if s["response"] == self.DIAGRAM:
            need_labels.append("ⓐ~ⓝ 기호 문장")
        chars = s["chars_range"]
        comp = self.CR and self.RULES["length"]["component_median"]
        return {
            "slot": s["slot"], "type_code": s["type_code"], "cell": cell, "유형이름": s["type_name"],
            "소재": {
                "대분류": group,
                "내용영역_표기": self._c_area_label(s["area"], self._c_area_detail(s["area"], group, source)),
                "범위_지시": self._c_range_text(s["area"], group, cs, s),
                "원천": source, "가상_창작_허용": fict_ok and source == "가상 창작",
                "사실_출처": self._c_wpick(cs.get("fact_origin", {}), rng),
                "은폐_수준": conceal,
                "변형_연산자": ops,
                "변별점_지시": self.CC["discriminator_rule"]["rule"],
                "판단_장치": "사례결합" if "사례결합" in sum(ops.values(), []) else "대립구조화" if "대립구조화" in sum(ops.values(), []) else "실험·자료가공" if "실험·자료가공" in sum(ops.values(), []) else "없음(설명문)",
                "회피": {"원형_기출": f"{archetype['id']} {archetype['material']}" if archetype else None,
                         "같은_셀_기출_소재": avoid_cell, "같은_대분류_기출_소재": avoid_group, "대장_사용_소재": avoid_ledger,
                         "AI_편중_블랙리스트": self.CC["ai_overuse_blacklist"].get(s["area"], [])},
                "출처_메모": {k: self.TODO for k in self.CC["source_memo_schema"]["fields"]},
            },
            "참고_기출": {"설계_참고(같은 셀)": design_refs, "작성_참고(같은 영역 서술)": writing_refs,
                          "회피_원형": archetype["id"] if archetype else None,
                          "원형_판단포인트(다르게 짤 것)": archetype["discriminator"] if archetype else None,
                          "주의": self.CC["reference_selection"]["design_refs"]["role"]},
            "논리_설계": {"판단_방식": s["judgment"], "핵심_판단_틀": frame["frame"], "진위_집합": s["truth_set"], "정답_번호": s["answer"],
                          "정답_조건": (f"{'·'.join(s['truth_set'])} 참, {'·'.join(k for k in 'ㄱㄴㄷ' if k not in s['truth_set']) or '없음'} 거짓" if s["response"] == self.COMBO else f"선지 {s['answer']}만 {'거짓' if s['polarity']=='옳지 않은 것' else '참'}"),
                          "함정_유형_후보": traps, "계산_설계": calc,
                          "우회_점검": ["지문 없이 상식·배경지식만으로 정답이 나오면 실패", "배경지식(실제 제도·이론)으로 풀면 변별점 진술이 오답이 되어야 함", "진술 하나를 빼도 정답이 유일하게 결정되는지(합답형)"]},
            "지문_구조": {"블록_기능_시퀀스": fseq, "서술": narr, "주체": subj, "표지_필수": [x for x in need_labels if x],
                          "지시기호": s["stem_basis"] == "맥락 지정", "조직_예": cs.get("passage_organization", [])[:2],
                          "글자수": {"총": chars, "지문_중앙값": comp["지문"][s["area"]], "보기·선지_중앙값": comp["보기·선지"][s["area"]], "발문": comp["발문"]}},
            "보기_설계": {"진술_간_관계": rel, "진술": stmts},
            "발문": {"근거": s["stem_basis"], "작업": s["stem_task"], "극성": s["polarity"]},
        }


    def _c_design_set(self, design, ledger=None, seed=0):
        rng = random.Random(seed)
        slots = design["slots"]
        for s in slots:
            s["_cell"] = f"{s['area']}|{s['type']}|{s['principle']}"
        latest_year = max(m["year"] for m in self.CR["m20_materials"])
        idx = self._c_m20_index()
        ledger_entries = (ledger or {}).get("entries", [])
        groups, gw_all, subdomains = {}, {}, {}
        for a in self.AREAS:
            ss = [s for s in slots if s["area"] == a]
            g, gw = self._c_allocate_groups(a, ss, rng)
            groups.update(g); gw_all[a] = gw
            subdomains.update(self._c_pick_subdomains(a, ss, g, rng))
        by_slot = {s["slot"]: s for s in slots}
        neighbors = {}
        for s in slots:
            i = s["slot"]
            neighbors[i] = {"앞": f"{by_slot[i - 1]['area']}·{subdomains.get(i - 1, groups.get(i - 1, ''))}" if i - 1 in by_slot else None,
                            "뒤": f"{by_slot[i + 1]['area']}·{subdomains.get(i + 1, groups.get(i + 1, ''))}" if i + 1 in by_slot else None}
        import math
        specs = []
        for a in self.AREAS:
            ss = [s for s in slots if s["area"] == a]
            cap = {k: math.ceil(v[1] * len(ss)) + 1 for k, v in self.CR["areas"][a]["source"].items()}
            used = {}
            for s in ss:
                sp = self._c_design_slot(s, rng, idx, ledger_entries, latest_year, groups[s["slot"]], used, cap)
                sp["소재"]["세부영역"] = subdomains.get(s["slot"])
                sp["소재"]["인접_회피"] = {**neighbors[s["slot"]], "규칙": self.CC["adjacency"]["material_rule"]}
                specs.append(sp)
        specs.sort(key=lambda x: x["slot"])
        # 회차 수준 점검 지시
        fict = [sp["slot"] for sp in specs if sp["소재"]["원천"] == "가상 창작"]
        alloc_table = {a: dict(Counter(groups[s["slot"]] for s in slots if s["area"] == a)) for a in self.AREAS}
        set_level = {
            "원칙": self.CC["principles"],
            "대분류_배분": alloc_table,
            "대분류_배분_근거(2019+ 세부영역 분포)": {a: dict(sorted(gw_all[a].items(), key=lambda x: -x[1])) for a in self.AREAS},
            "인접_규칙": {"배치": "세부영역 그룹은 기출 인접 통계(areas.adjacency_2019plus)대로 연속(run)으로 묶는다 — 사회·과학기술·인문은 같은 분야를 붙이고(경제학 2~3연속, 생명 2연속), 논리학·수학은 교대",
                      "기출_인접_통계": {a: {k: self._c_adjacency_of(a).get(k) for k in ("same_group_rate", "same_group_expected", "cluster_index", "max_group_run", "same_subdomain_rate")} for a in self.AREAS},
                      "세부영역": "같은 그룹이 이웃하면 세부영역은 서로 다르게(소재.세부영역 — 생명 → 생태학 → 의학). 세부영역이 하나뿐인 그룹만 같은 세부영역이 이어진다",
                      "세부_소재": self.CC["adjacency"]["material_rule"], "참고": self.CC["adjacency"]["separate_pairs_note"]},
            "슬롯_세부영역": {s["slot"]: subdomains.get(s["slot"]) for s in slots},
            "가상_창작": {"슬롯": fict, "상한(논리 밖)": self.CC["fictional"]["max_per_set_outside_logic"], "규칙": self.CC["fictional"]["note"]},
            "계산_문항": [sp["slot"] for sp in specs if sp["논리_설계"]["판단_방식"] != "논리"],
            "회차_내_중복_금지": "같은 화제·인물·사건·실험·법령이 두 자리에 나오지 않는다. 과학사 인물 재사용만 예외.",
            "출처_메모_의무": self.CC["source_memo_schema"],
            "AI_중복_회피_전략": self.CC["ai_overuse_blacklist"]["strategy"],
            "승인_절차": self.CC["approval"],
            "참고": {"기출_소재_대장(M20)": f"content_rules.json m20_materials {len(self.CR['m20_materials'])}문항", "회차_소재_대장(M30)": "material_ledger.json(승인 예정분) + 공유 문항풀(haean tools pool sync)", "대조기": "material_check.py"},
        }
        for s in slots:
            s.pop("_cell", None)
        return {"meta": {"rules": self.CR["meta"]["version"], "seed": seed, "format_seed": design.get("meta", {}).get("seed")}, "회차": set_level, "슬롯": specs}
