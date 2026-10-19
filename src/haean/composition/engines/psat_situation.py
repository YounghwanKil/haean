"""PSAT 5급 상황판단 40슬롯 형식·내용 설계의 순수 알고리즘.

관측 규칙·정책·소재 기록은 외부 dict로만 주입한다. 인스턴스마다 복사하며
파일, 환경변수, 원격 저장소를 읽지 않는다. 7급 회차 설계는 지원하지 않는다.
"""

import random
from collections import Counter
from copy import deepcopy

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
        self._area_codes = self._rules['codes']['area']
        self._type_codes = self._rules['codes']['type']
        self._principles = self._rules['codes']['principles']
        self._combo_kinds = ('ㄱㄴㄷ 합답형', 'ㄱㄴㄷㄹ 합답형', '인물 합답형')
        self._todo = '__TODO'

    def _type_code(self, area, pr):
        return f"11-{self._area_codes[area]}{pr}"

    def _weights_for(self, bundles, rng_latest, w):
        years = sorted({b["학년도"] for b in bundles}, reverse=True)
        yw = {y: (w[i] if i < len(w) else w[-1]) for i, y in enumerate(years)}
        return [yw[b["학년도"]] for b in bundles]

    def _pick_bundle(self, slot, rng, mode, w):
        S = self._rules["skeleton"]["slots"][str(slot)]
        bs = S["bundles"]
        if mode == "latest":
            return next(b for b in bs if b["학년도"] == max(x["학년도"] for x in bs))
        return rng.choices(bs, weights=self._weights_for(bs, None, w), k=1)[0]

    def _soft_violations(self, slots):
        Q = self._rules["quotas"]; v = []
        def chk(name, key, dist):
            for k, (d, r) in Q[name].items():
                if not in_range(dist.get(k, 0), r):
                    v.append(f"{name} {k} {dist.get(k, 0)} ∉ {r}")
        chk("type", "T", Counter(s["type"] for s in slots))
        chk("response", "응답 형식", Counter(s["response"] for s in slots))
        chk("polarity", "극성", Counter(s["polarity"] for s in slots))
        chk("judgment", "판단", Counter(s["judgment"] for s in slots))
        chk("area", "영역", Counter(s["area"] for s in slots))
        pc = Counter(s["principle"] for s in slots)
        for k, (d, r) in Q["principle"].items():
            if not in_range(pc.get(k, 0), r):
                v.append(f"principle {k} {pc.get(k, 0)} ∉ {r}")
        chk("difficulty_label", "난도", Counter(s["difficulty_label"] for s in slots))
        return v

    def _sample_impl(self, seed=0, mode="sample"):
        rng = random.Random(seed)
        R = self._rules; w = R["skeleton"]["bundle_sampling"]["year_weights_from_latest"]
        pairs = {a: b for a, b in R["sets"]["pairs"]}; pair_of = {b: a for a, b in R["sets"]["pairs"]}
        best = None
        for attempt in range(R["skeleton"]["bundle_sampling"]["retry"] if mode != "latest" else 1):
            slots = []
            chosen_year = {}
            for s in range(1, 41):
                if s in pair_of:                       # 세트 뒤: 앞과 같은 학년도 번들
                    y = chosen_year[pair_of[s]]
                    b = next(x for x in R["skeleton"]["slots"][str(s)]["bundles"] if x["학년도"] == y)
                else:
                    b = self._pick_bundle(s, rng, mode, w)
                    if s in pairs:
                        chosen_year[s] = b["학년도"]
                slots.append({
                    "slot": s, "archetype": b["문항 ID"], "archetype_year": b["학년도"],
                    "type": b["T"], "principle": b["PR"], "principle_name": self._principles[b["PR"]]["name"], "area": b["내용영역"],
                    "type_code": self._type_code(b["내용영역"], b["PR"]), "response": b["응답 형식"], "polarity": b["발문 ③극성"], "stem_basis": b["발문 ①근거"], "stem_task": b["발문 ②작업"],
                    "judgment": b["판단 방식"], "calc_load": b["계산 부담(원자료)"], "difficulty_label": b["체감 난도(추정)"], "difficulty": R["difficulty"]["map"][b["체감 난도(추정)"]],
                    "set_role": b["세트 여부"], "set_id": (f"S{s}-{s+1}" if s in pairs else f"S{pair_of[s]}-{s}" if s in pair_of else None),
                    "has_situation": bool(b["has_situation"]), "special": b["특수형식"], "statement_count": int(b["보기 진술 수"] or 0),
                    "chars_range": [R["length"]["by_principle"][b["PR"]]["q1"], R["length"]["by_principle"][b["PR"]]["q3"]],
                    "archetype_stem": b["발문"], "notes": [],
                })
            viol = self._soft_violations(slots)
            if best is None or len(viol) < len(best[1]):
                best = (slots, viol)
            if not viol:
                break
        slots, viol = best
        # ---- 국소 수리: 위반이 남으면 한 슬롯씩 다른 번들로 바꿔 보며 위반 수를 줄인다(세트·latest 모드 제외)
        if viol and mode != "latest":
            def mk(s_no, b):
                return {**slots[s_no - 1], "archetype": b["문항 ID"], "archetype_year": b["학년도"], "type": b["T"], "principle": b["PR"], "principle_name": self._principles[b["PR"]]["name"],
                        "area": b["내용영역"], "type_code": self._type_code(b["내용영역"], b["PR"]), "response": b["응답 형식"], "polarity": b["발문 ③극성"], "stem_basis": b["발문 ①근거"],
                        "stem_task": b["발문 ②작업"], "judgment": b["판단 방식"], "calc_load": b["계산 부담(원자료)"], "difficulty_label": b["체감 난도(추정)"],
                        "difficulty": R["difficulty"]["map"][b["체감 난도(추정)"]], "has_situation": bool(b["has_situation"]), "special": b["특수형식"],
                        "statement_count": int(b["보기 진술 수"] or 0), "chars_range": [R["length"]["by_principle"][b["PR"]]["q1"], R["length"]["by_principle"][b["PR"]]["q3"]], "archetype_stem": b["발문"]}
            set_slots = set(sum(R["sets"]["pairs"], []))
            for it in range(300):
                cur = self._soft_violations(slots)
                if not cur:
                    break
                cand_slots = [s for s in range(1, 41) if s not in set_slots]
                rng.shuffle(cand_slots)
                improved = False
                for s_no in cand_slots[:12]:
                    for b in R["skeleton"]["slots"][str(s_no)]["bundles"]:
                        trial = list(slots); trial[s_no - 1] = mk(s_no, b)
                        if len(self._soft_violations(trial)) < len(cur):
                            slots = trial; improved = True; break
                    if improved:
                        break
                if not improved:
                    break
            viol = self._soft_violations(slots)
        # ---- 합답 배열·선택 집합·정답
        pats = R["option_patterns"]["patterns"]
        for s in slots:
            if s["response"] in self._combo_kinds:
                cands = [k for k, v in pats.items() if v["statements"] == s["statement_count"]]
                ws = [pats[k]["core_count"] * 2 + pats[k]["count"] for k in cands]
                p = rng.choices(cands, weights=ws, k=1)[0]
                opts = p.split(" / ")
                s["option_pattern"] = p; s["option_pattern_id"] = pats[p]["id"]
                s["selected_set"] = rng.choice(opts)        # 긍정: 참 집합 / 부정: 거짓 집합
                s["answer"] = opts.index(s["selected_set"]) + 1
            else:
                s["option_pattern"] = None; s["option_pattern_id"] = None; s["selected_set"] = None; s["answer"] = None
        pol = R["answer"]
        lo, hi = pol["per_number_range"]
        for attempt in range(3000):
            cnt = Counter(s["answer"] for s in slots if s["answer"])
            free = [s for s in slots if s["answer"] is None]
            rng.shuffle(free)
            trial = {}
            for s in free:
                n = min(range(1, 6), key=lambda x: (cnt[x] + trial.get(x, 0), rng.random()))
                s["_ans"] = n; trial[n] = trial.get(n, 0) + 1
            seq = [s["answer"] or s["_ans"] for s in slots]
            c = Counter(seq)
            if all(lo <= c[n] <= hi for n in range(1, 6)) and max_run(seq) <= pol["max_run"]:
                break
        for s in slots:
            if s["answer"] is None:
                s["answer"] = s.pop("_ans")
            s.pop("_ans", None)
        return {"meta": {"rules": R["meta"]["version"], "seed": seed, "mode": mode, "soft_violations": viol}, "slots": slots}

    def _validate_impl(self, design):
        R = self._rules; S = design["slots"]; errs = []; warns = list(self._soft_violations(S))
        if len(S) != 40 or sorted(s["slot"] for s in S) != list(range(1, 41)):
            errs.append("문번 1~40 고유 위반")
        pats = R["option_patterns"]["patterns"]
        for s in S:
            if not 1 <= int(s["answer"]) <= 5: errs.append(f"슬롯 {s['slot']} 정답 {s['answer']}")
            if s["response"] in self._combo_kinds:
                if s["option_pattern"] not in pats: errs.append(f"슬롯 {s['slot']} 합답 배열 미관측: {s['option_pattern']}")
                else:
                    opts = s["option_pattern"].split(" / ")
                    if s["selected_set"] not in opts: errs.append(f"슬롯 {s['slot']} 선택 집합 {s['selected_set']} ∉ 배열")
                    elif opts.index(s["selected_set"]) + 1 != s["answer"]: errs.append(f"슬롯 {s['slot']} 정답 {s['answer']} ≠ 선택 집합 위치")
                    if pats[s["option_pattern"]]["statements"] != s["statement_count"]: errs.append(f"슬롯 {s['slot']} 보기 수 {s['statement_count']} ≠ 배열 진술 수")
            if s["principle"] not in R["skeleton"]["slots"][str(s["slot"])]["allowed_principles"]:
                warns.append(f"슬롯 {s['slot']} 원리 {s['principle']} 은 같은 문번 core+support 미관측")
            if s["polarity"] not in R["codes"] and s["polarity"] not in ("옳은 것", "옳지 않은 것", "해당하는 것"): errs.append(f"슬롯 {s['slot']} 극성 {s['polarity']}")
        for a, b in R["sets"]["pairs"]:
            sa, sb = S[a - 1], S[b - 1]
            if not (sa["set_id"] and sa["set_id"] == sb["set_id"]): errs.append(f"세트 {a}~{b} set_id 불일치")
            if sa["archetype_year"] != sb["archetype_year"]: errs.append(f"세트 {a}~{b} 원형 학년도 불일치(공통 지문 구조 깨짐)")
            if sa["principle"] == sb["principle"]: warns.append(f"세트 {a}~{b} 두 문항 원리 동일 — 서로 다른 판단 과제인지 확인")
        seq = [s["answer"] for s in S]
        if max_run(seq) > R["answer"]["max_run"]: errs.append(f"정답 연속 {max_run(seq)} > {R['answer']['max_run']}")
        c = Counter(seq); lo, hi = R["answer"]["per_number_range"]
        for n in range(1, 6):
            if not lo <= c[n] <= hi: warns.append(f"정답 {n} {c[n]}개 ∉ [{lo},{hi}]")
        # 구간 분량 편중(soft)
        tot_lo = sum(s["chars_range"][0] for s in S); tot_hi = sum(s["chars_range"][1] for s in S)
        net = R["length"]["set_total_target_net"]
        if tot_hi < net[0] * 0.8 or tot_lo > net[1] * 1.2: warns.append(f"회차 분량 범위 [{tot_lo},{tot_hi}] 가 목표 {net}와 멀다")
        return errs, warns

    # Content specifications retain the upstream slot schema.

    def _wpick(self, dist, rng, exclude=()):
        items = [(k, v[0]) for k, v in dist.items() if k not in exclude]
        if not items:
            return None
        ks, ws = zip(*items)
        return rng.choices(ks, weights=ws, k=1)[0]

    def _m20_index(self):
        by_id = {m["id"]: m for m in self._content_rules["m20_materials"]}
        by_pr, by_area = {}, {}
        for m in self._content_rules["m20_materials"]:
            by_pr.setdefault(m["principle"], []).append(m); by_area.setdefault(m["area"], []).append(m)
        return by_id, by_pr, by_area

    def _range_text(self, s, cell):
        role = {"세트(앞)": " 세트 앞 문항 — 공통 지문의 정보·규범을 대조하는 과제.", "세트(뒤)": " 세트 뒤 문항 — 공통 지문의 규칙을 <상황>에 적용해 값을 구하는 과제. 앞 문항 정답을 누설하지 않게."}.get(s["set_role"], "")
        return (f"{s['area']} · {cell['name']}({s['principle']}) — {cell['decision']} 모델: {cell['model']}. 제작 지시: {cell['build']}"
                f" 응답 형식 {s['response']}, 극성 {s['polarity']}.{role} 구체 소재·수치·조문은 지문에 쓰지 않고 원천 메모에만.")

    def _design_slot(self, s, rng, idx, ledger_entries):
        by_id, by_pr, by_area = idx
        cell = self._content_rules["cells"][s["principle"]]
        arche = by_id.get(s["archetype"])
        pool = [m for m in by_pr.get(s["principle"], []) if not arche or m["id"] != arche["id"]]
        pool.sort(key=lambda m: (-m["year"], m["slot"]))
        design_refs = [m["id"] for m in pool[: self._content_config["reference_selection"]["design_refs"]["same_principle"]]]
        avoid_pr = [f"{m['id']} {m['material']} / {m['avoid']}" for m in pool[:10]]
        recent_area = [f"{m['id']} {m['material']}" for m in sorted(by_area.get(s["area"], []), key=lambda m: -m["year"]) if m["year"] >= max(mm["year"] for mm in self._content_rules["m20_materials"]) - 4][:12]
        avoid_ledger = [f"{e.get('회차')}-{e.get('slot')} {e.get('material')}" for e in ledger_entries if e.get("area") == s["area"] or e.get("principle") == s["principle"]]
        ap = self._content_config["area_policy"][s["area"]]
        calc = None
        if s["judgment"] != "논리" or s["calc_load"] != "없음":
            cd = self._content_config["calc_design"]
            calc = {"판단_방식": s["judgment"], "계산_부담": s["calc_load"], "지시": cd["load_map"].get(s["calc_load"], ""), "연산": cd["ops"], "경계값_함정": cd["boundary_trap"], "증명": cd["proof"]}
        # 판단 단위 설계
        units = []
        if s["response"] in self._combo_kinds:
            n = s["statement_count"]; sel = s["selected_set"]; neg = s["polarity"] == "옳지 않은 것"
            for k in "ㄱㄴㄷㄹ"[:n]:
                true = (k in sel) != neg
                ex = ("결과 후보 대조",); exn = ("결과 후보",)   # 5지 수치 선지용 라벨은 보기 진술에 쓰지 않음
                units.append({"기호": k, "진위": "○" if true else "×", "작업": self._wpick(cell["unit_task"], rng, ex) or cell["name"], "서술": self._wpick(cell["unit_narration"], rng, exn) or "단정문",
                              "사례": self._wpick(cell["unit_case"], rng) or "명시 사례 없음", "오답_경로": None if true else rng.choice(cell["trap"])})
        else:
            neg = s["polarity"] == "옳지 않은 것"
            for i in range(1, 6):
                true = (i == s["answer"]) != neg
                units.append({"기호": f"선지{i}", "진위": "○" if true else "×", "작업": self._wpick(cell["unit_task"], rng) or cell["name"], "오답_경로": None if true else rng.choice(cell["trap"])})
        subj = next(iter(cell.get("block_subject", {"없음": 0})))
        return {
            "slot": s["slot"], "type_code": s["type_code"], "cell": f"{s['area']}|{s['principle']}", "원리이름": cell["name"], "분석유형": cell["type"],
            "소재": {
                "대분류": s["area"], "범위_지시": self._range_text(s, cell), "원천_정책": ap["source"], "확인": ap["verify"], "가상_여부": self._content_rules["areas"][s["area"]]["fictional"],
                "회피": {"원형_기출": f"{arche['id']} {arche['material']} / 판단 포인트: {arche['point']}" if arche else None,
                         "같은_원리_기출_소재": avoid_pr, "같은_영역_최근_소재": recent_area, "대장_사용_소재": avoid_ledger,
                         "AI_편중_블랙리스트": self._content_config["ai_overuse_blacklist"].get(s["area"], [])},
                "원천_메모": {k: self._todo for k in self._content_config["source_memo_schema"]["fields"]},
            },
            "참고_기출": {"원형(같은 문번 최신)": arche["id"] if arche else s["archetype"], "원형_판단포인트(다르게 짤 것)": arche["point"] if arche else None, "원형_모델": arche["model"] if arche else None,
                          "설계_참고(같은 원리)": design_refs, "주의": self._content_config["reference_selection"]["archetype"]},
            "논리_설계": {"판정_기준": cell["decision"], "분류_경계": cell["boundary"], "모델": cell["model"], "제작_지시": cell["build"], "함정_후보": cell["trap"], "필수_증명": cell["proof"], "변주축": cell["vary"],
                          "선택_집합": s["selected_set"], "극성": s["polarity"], "정답_번호": s["answer"],
                          "정답_조건": (f"{'·'.join(s['selected_set'])} {'거짓' if s['polarity']=='옳지 않은 것' else '참'}, 나머지 반대" if s["response"] in self._combo_kinds else f"선지 {s['answer']}만 {'거짓' if s['polarity']=='옳지 않은 것' else '정답'}"),
                          "계산_설계": calc,
                          "우회_점검": ["지문 없이 상식만으로 정답이 나오면 실패", "핵심 판단(모델) 없이 정답이 남지 않는지", "가능/필연 구분: '가능'은 모형 하나, '필연'은 모든 모형", "최적화는 더 좋은 해가 없다는 증명"]},
            "지문_구조": {"블록_기능_시퀀스": (cell.get("block_function_seq") or ["사실-규칙·기준"])[0], "서술": next(iter(cell.get("block_narration", {"평서": 0}))), "주체": subj,
                          "표지": ["<상황>"] if s["has_situation"] else [], "표": "표 결합" in str(s["special"]), "대화": "대화형" in str(s["special"]),
                          "세트": s["set_id"], "세트_역할": s["set_role"], "글자수": s["chars_range"], "인물_기호": "甲乙丙丁戊(한자)·A부처·□□시", "조문": "제○○조(제목) ① ② / 호 1. / 목 가." if s["type"] == "규범 판단" else None},
            "판단_단위_설계": {"응답_형식": s["response"], "합답_배열": s["option_pattern"], "단위": units},
            "발문": {"근거": s["stem_basis"], "작업": s["stem_task"], "극성": s["polarity"], "원형_발문": s["archetype_stem"]},
            "난도": {"체감(승계)": s["difficulty_label"], "해설_난이도": s["difficulty"], "주의": "실측 정답률 없음"},
        }

    def _content_impl(self, design, ledger=None, seed=0):
        rng = random.Random(seed)
        idx = self._m20_index(); entries = (ledger or {}).get("entries", [])
        specs = [self._design_slot(s, rng, idx, entries) for s in design["slots"]]
        set_level = {
            "원칙": self._content_config["principles"], "영역_정책": self._content_config["area_policy"], "세트_정책": self._content_config["set_policy"],
            "영역_배분": dict(Counter(s["area"] for s in design["slots"])), "원리_배분": dict(Counter(s["principle"] for s in design["slots"])),
            "계산_문항": [s["slot"] for s in design["slots"] if s["judgment"] != "논리"], "표_결합_문항": [s["slot"] for s in design["slots"] if "표 결합" in str(s["special"])],
            "회차_내_중복_금지": "같은 화제·인물 설정·제도·판단 포인트가 두 자리에 없음(세트 제외). 법조문 구간은 같은 대분류 연속 허용, 같은 세부 제도·권리 효과 연속 금지.",
            "원천_메모_의무": self._content_config["source_memo_schema"], "AI_중복_회피_전략": self._content_config["ai_overuse_blacklist"]["strategy"], "승인_절차": self._content_config["approval"],
            "참고": {"기출_소재_대장(M20)": f"content_rules.json m20_materials {len(self._content_rules['m20_materials'])}문항", "회차_대장(M30)": "material_ledger.json", "대조기": "material_check.py"},
        }
        return {"meta": {"rules": self._content_rules["meta"]["version"], "seed": seed, "format_seed": design.get("meta", {}).get("seed")}, "회차": set_level, "슬롯": specs}

    def sample(self, seed=0, **options) -> dict:
        """Sample a PSAT 5, 40-slot design using only this instance's profile."""
        options = supported_options(options, ('mode',))
        if options.get("mode", "sample") not in ("sample", "latest"):
            raise ValueError("mode는 sample 또는 latest여야 합니다")
        return deepcopy(self._sample_impl(seed=seed, **options))

    def validate(self, design, **options) -> list[str]:
        """Return hard errors; soft distribution warnings remain in validate_report."""
        return self.validate_report(design, **options)["errors"]

    def validate_report(self, design, **options):
        """Preserve upstream hard errors, soft warnings and informational differences."""
        options = supported_options(options, ())
        errors = format_input_errors(design, 'answer')
        if errors:
            return {"errors": errors, "warnings": [], "infos": []}
        errors = required_slot_errors(design, (
            "archetype", "archetype_year", "type", "principle", "area", "type_code",
            "response", "polarity", "stem_basis", "stem_task", "judgment", "calc_load",
            "difficulty_label", "difficulty", "set_role", "set_id", "has_situation",
            "special", "statement_count", "chars_range", "archetype_stem", "option_pattern",
            "selected_set",
        ))
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
