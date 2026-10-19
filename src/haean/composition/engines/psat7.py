"""Independent PSAT 7급 composition from four explicit, versioned profiles.

This module reads no files and borrows no grade-5 distributions. Profile quotas
are local editorial constraints, not claims about official exam requirements.
Content blueprints describe work still to be authored and reviewed.
"""

from collections import Counter
from copy import deepcopy
import math
import random


_IDENTITY = {"schema_version", "engine", "exam_grade", "subject"}
_SUBJECTS = {"언어논리", "자료해석", "상황판단"}
_DIFFICULTIES = ("하", "중", "상")
_BLUEPRINT = {"domains", "reasoning_tasks", "distractor_paths", "review_checks", "construction_notes"}
_POLICIES = {"common_passage_policy", "difficulty_policy", "source_policy", "subject_review"}
_SLOT_FIELDS = {"slot", "type", "type_code", "difficulty", "diff", "set_id", "bundle", "set", "response_format"}


def _json_data(value, path="data", ancestors=None):
    """Accept inert JSON-shaped data, including provenance with arbitrary keys."""
    ancestors = set() if ancestors is None else ancestors
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) not in (dict, list):
        raise ValueError(f"{path}: JSON 데이터여야 합니다")
    if id(value) in ancestors:
        raise ValueError(f"{path}: 순환 참조는 지원하지 않습니다")
    ancestors.add(id(value))
    try:
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError(f"{path}: 키는 문자열이어야 합니다")
                _json_data(item, f"{path}.{key}", ancestors)
        else:
            for index, item in enumerate(value):
                _json_data(item, f"{path}[{index}]", ancestors)
    finally:
        ancestors.remove(id(value))


def _fields(value, required, path, optional=()):
    if type(value) is not dict:
        raise ValueError(f"{path}: dict가 필요합니다")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise ValueError(f"{path}: 필수 필드 누락 {sorted(missing)}, 알 수 없는 필드 {sorted(unknown)}")


def _strings(value, path):
    if type(value) is not list or not value or any(type(v) is not str or not v.strip() for v in value):
        raise ValueError(f"{path}: 비어 있지 않은 문자열 배열이 필요합니다")


def _integer(value, path, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{path}: {low}~{high} 정수가 필요합니다")


def _seed(seed):
    if type(seed) is not int:
        raise ValueError("seed는 정수여야 합니다")
    return random.Random(seed)


class Engine:
    """Quota-based 25-slot designs with explicitly declared shared passages."""

    supported_sizes = (25,)
    sample_options = frozenset({"size"})

    def __init__(self, *, format_rules, content_rules, content_config, rules_config, subject):
        if type(subject) is not str or subject not in _SUBJECTS:
            raise ValueError("PSAT 7급 과목은 언어논리·자료해석·상황판단 중 하나여야 합니다")
        self.subject = subject
        self.track = {"언어논리": "psat7_verbal", "자료해석": "psat7_data", "상황판단": "psat7_situation"}[subject]
        supplied = {
            "format_rules": format_rules, "content_rules": content_rules,
            "content_config": content_config, "rules_config": rules_config,
        }
        fields = {
            "format_rules": {"total_slots", "types", "shared_sets", "difficulty_counts"},
            "content_rules": {"types"}, "content_config": _POLICIES,
            "rules_config": {"observations", "editorial_decisions"},
        }
        for role, value in supplied.items():
            _json_data(value, role)
            _fields(value, _IDENTITY | fields[role], role,
                    {"section_preferences"} if role == "format_rules" else ())
            self._identity(value, role)
        self._validate_profiles(**supplied)
        self._format = deepcopy(format_rules)
        self._content = deepcopy(content_rules)
        self._policies = deepcopy(content_config)
        self._config = deepcopy(rules_config)
        self._types = {row["code"]: row for row in self._format["types"]}
        self._fixed = {
            member: (group["id"], code)
            for group in self._format["shared_sets"]
            for member, code in zip(group["members"], group["types"])
        }
        self._sets = {group["id"]: group for group in self._format["shared_sets"]}

    def _identity(self, value, path):
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError(f"{path}: schema_version은 1이어야 합니다")
        if value.get("engine") != "psat7-v1":
            raise ValueError(f"{path}: engine은 psat7-v1이어야 합니다")
        if type(value.get("exam_grade")) is not int or value["exam_grade"] != 7:
            raise ValueError(f"{path}: exam_grade는 7이어야 합니다; 5급 본문은 사용할 수 없습니다")
        if value.get("subject") != self.subject:
            raise ValueError(f"{path}: subject가 요청 과목 {self.subject}와 다릅니다")

    def _validate_profiles(self, *, format_rules, content_rules, content_config, rules_config):
        f = format_rules
        _integer(f["total_slots"], "format_rules.total_slots", 25, 25)
        if type(f["types"]) is not list or not f["types"]:
            raise ValueError("format_rules.types: 유형 배열이 필요합니다")
        codes, labels, counts = set(), set(), {}
        for index, row in enumerate(f["types"]):
            path = f"format_rules.types[{index}]"
            _fields(row, {"code", "label", "count", "response_formats"}, path)
            for field, seen in (("code", codes), ("label", labels)):
                value = row[field]
                if type(value) is not str or not value.strip() or value in seen:
                    raise ValueError(f"{path}.{field}: 고유한 비어 있지 않은 문자열이 필요합니다")
                seen.add(value)
            _integer(row["count"], f"{path}.count", 0, 25)
            _strings(row["response_formats"], f"{path}.response_formats")
            counts[row["code"]] = row["count"]
        if sum(counts.values()) != 25:
            raise ValueError("format_rules.types: 유형 할당량 합계는 25여야 합니다")
        _fields(f["difficulty_counts"], set(_DIFFICULTIES), "format_rules.difficulty_counts")
        for difficulty, count in f["difficulty_counts"].items():
            _integer(count, f"format_rules.difficulty_counts.{difficulty}", 0, 25)
        if sum(f["difficulty_counts"].values()) != 25:
            raise ValueError("format_rules.difficulty_counts: 합계는 25여야 합니다")
        if type(f["shared_sets"]) is not list:
            raise ValueError("format_rules.shared_sets: 배열이 필요합니다")
        ids, members, used = set(), set(), Counter()
        for index, group in enumerate(f["shared_sets"]):
            path = f"format_rules.shared_sets[{index}]"
            _fields(group, {"id", "members", "types"}, path)
            identifier = group["id"]
            if type(identifier) is not str or not identifier.strip() or identifier in ids:
                raise ValueError(f"{path}.id: 고유한 문자열이 필요합니다")
            ids.add(identifier)
            pair = group["members"]
            if type(pair) is not list or len(pair) != 2:
                raise ValueError(f"{path}.members: 인접한 두 문번이 필요합니다")
            for member in pair:
                _integer(member, f"{path}.members", 1, 25)
            if abs(pair[0] - pair[1]) != 1 or members.intersection(pair):
                raise ValueError(f"{path}.members: 세트 문번은 인접하고 중복되지 않아야 합니다")
            members.update(pair)
            _strings(group["types"], f"{path}.types")
            if len(group["types"]) != 2 or any(code not in codes for code in group["types"]):
                raise ValueError(f"{path}.types: 두 문번에 대응하는 알려진 유형 코드가 필요합니다")
            used.update(group["types"])
        if any(used[code] > count for code, count in counts.items()):
            raise ValueError("format_rules.shared_sets: 세트 유형 수가 유형 할당량을 초과합니다")
        preferences = f.get("section_preferences", [])
        if type(preferences) is not list:
            raise ValueError("format_rules.section_preferences: 배열이 필요합니다")
        for index, pref in enumerate(preferences):
            path = f"format_rules.section_preferences[{index}]"
            _fields(pref, {"start", "end", "types"}, path)
            _integer(pref["start"], f"{path}.start", 1, 25)
            _integer(pref["end"], f"{path}.end", pref["start"], 25)
            _strings(pref["types"], f"{path}.types")
            if any(code not in codes for code in pref["types"]):
                raise ValueError(f"{path}.types: 알 수 없는 유형 코드")
        _fields(content_rules["types"], codes, "content_rules.types")
        for code, blueprint in content_rules["types"].items():
            _fields(blueprint, _BLUEPRINT, f"content_rules.types.{code}")
            for field in _BLUEPRINT:
                _strings(blueprint[field], f"content_rules.types.{code}.{field}")
        for field in _POLICIES:
            _strings(content_config[field], f"content_config.{field}")
        if type(rules_config["observations"]) is not dict:
            raise ValueError("rules_config.observations: dict가 필요합니다")
        _strings(rules_config["editorial_decisions"], "rules_config.editorial_decisions")

    def _meta(self, seed):
        return {"schema_version": 1, "engine": "psat7-v1", "exam_grade": 7,
                "subject": self.subject, "size": 25, "total_slots": 25,
                "status": "proposal", "quality_approval": False, "seed": seed}

    def _preference_score(self, number, code):
        return sum(pref["start"] <= number <= pref["end"] and code in pref["types"]
                   for pref in self._format.get("section_preferences", []))

    def sample(self, seed=0, **options):
        unknown = set(options) - self.sample_options
        if unknown:
            raise ValueError(f"지원하지 않는 설계 옵션: {', '.join(sorted(unknown))}")
        if "size" in options:
            _integer(options["size"], "size", 25, 25)
        rng = _seed(seed)
        fixed_counts = Counter(code for _, code in self._fixed.values())
        bag = [code for code, spec in self._types.items()
               for _ in range(spec["count"] - fixed_counts[code])]
        rng.shuffle(bag)
        free = [number for number in range(1, 26) if number not in self._fixed]
        assignment = {number: code for number, (_, code) in self._fixed.items()}
        assignment.update(zip(free, bag))
        # Local swaps improve optional section preferences without changing quotas
        # or fixed sets. Unmet preferences remain warnings, never invalidity.
        pairs = [(a, b) for index, a in enumerate(free) for b in free[index + 1:]]
        rng.shuffle(pairs)
        changed = True
        while changed:
            changed = False
            for a, b in pairs:
                ca, cb = assignment[a], assignment[b]
                gain = (self._preference_score(a, cb) + self._preference_score(b, ca)
                        - self._preference_score(a, ca) - self._preference_score(b, cb))
                if gain > 0:
                    assignment[a], assignment[b] = cb, ca
                    changed = True
        difficulties = [difficulty for difficulty in _DIFFICULTIES
                        for _ in range(self._format["difficulty_counts"][difficulty])]
        rng.shuffle(difficulties)
        slots = []
        for number in range(1, 26):
            code = assignment[number]
            spec = self._types[code]
            set_id = self._fixed[number][0] if number in self._fixed else None
            difficulty = difficulties[number - 1]
            slots.append({"slot": number, "type": spec["label"], "type_code": code,
                          "difficulty": difficulty, "diff": difficulty,
                          "set_id": set_id, "bundle": set_id, "set": set_id is not None,
                          "response_format": rng.choice(spec["response_formats"])})
        return {"meta": self._meta(seed), "slots": slots}

    def validate_report(self, design, **options):
        errors, warnings = [], []
        if options:
            errors.append(f"지원하지 않는 검증 옵션: {', '.join(sorted(options))}")
        try:
            _json_data(design, "design")
            _fields(design, {"meta", "slots"}, "design")
            meta = design["meta"]
            _fields(meta, set(self._meta(0)), "design.meta")
            self._identity(meta, "design.meta")
            _integer(meta["size"], "design.meta.size", 25, 25)
            _integer(meta["total_slots"], "design.meta.total_slots", 25, 25)
            if meta["status"] != "proposal" or meta["quality_approval"] is not False:
                raise ValueError("design.meta: 구성 제안 상태만 허용하며 품질 승인을 기록하지 않습니다")
            _seed(meta["seed"])
            slots = design["slots"]
            if type(slots) is not list or len(slots) != 25:
                raise ValueError("design.slots: 25개 슬롯이 필요합니다")
        except (ValueError, RecursionError) as exc:
            return {"errors": errors + [str(exc)], "warnings": [], "infos": []}
        numbers, type_counts, diff_counts = [], Counter(), Counter()
        for index, row in enumerate(slots):
            path = f"design.slots[{index}]"
            try:
                _fields(row, _SLOT_FIELDS, path)
                number = row["slot"]
                _integer(number, f"{path}.slot", 1, 25)
                numbers.append(number)
                code = row["type_code"]
                if type(code) is not str or code not in self._types:
                    raise ValueError(f"{path}.type_code: 알 수 없는 유형 코드")
                spec = self._types[code]
                if row["type"] != spec["label"]:
                    raise ValueError(f"{path}.type: 유형 코드와 이름이 일치하지 않습니다")
                type_counts[code] += 1
                difficulty = row["difficulty"]
                if type(difficulty) is not str or difficulty not in _DIFFICULTIES or row["diff"] != difficulty:
                    raise ValueError(f"{path}.difficulty/diff: 난도 또는 별칭 불일치")
                diff_counts[difficulty] += 1
                set_id, set_code = self._fixed.get(number, (None, None))
                if (row["set_id"] != set_id or row["bundle"] != set_id
                        or row["set"] is not (set_id is not None)):
                    raise ValueError(f"{path}.set_id/bundle/set: 프로필의 실제 세트 문번과 일치하지 않습니다")
                if set_code is not None and code != set_code:
                    raise ValueError(f"{path}.type_code: 세트의 지정 유형과 일치하지 않습니다")
                if type(row["response_format"]) is not str or row["response_format"] not in spec["response_formats"]:
                    raise ValueError(f"{path}.response_format: 해당 유형에서 허용하지 않는 응답 형식")
            except ValueError as exc:
                errors.append(str(exc))
        if numbers != list(range(1, 26)):
            errors.append("문번 1~25는 중복·누락 없이 오름차순이어야 합니다")
        if type_counts != Counter({code: spec["count"] for code, spec in self._types.items()}):
            errors.append("유형별 슬롯 수가 프로필 할당량과 일치하지 않습니다")
        if diff_counts != Counter(self._format["difficulty_counts"]):
            errors.append("난도별 슬롯 수가 프로필 할당량과 일치하지 않습니다")
        if not errors:
            for pref in self._format.get("section_preferences", []):
                unmet = [row["slot"] for row in slots if pref["start"] <= row["slot"] <= pref["end"]
                         and row["type_code"] not in pref["types"]]
                if unmet:
                    warnings.append(f"편집상 구간 선호 {pref['start']}~{pref['end']} 미충족 문번: {unmet}; 필수 규칙 아님")
        return {"errors": errors, "warnings": warnings,
                "infos": ["PSAT 7급 25문항 구성 제안 검증이며 문항 품질·실측 난도·독창성 승인에 해당하지 않습니다"]}

    def validate(self, design, **options):
        return self.validate_report(design, **options)["errors"]

    def content(self, design, ledger=None, seed=0):
        errors = self.validate(design)
        if errors:
            raise ValueError("형식설계 검증 실패: " + "; ".join(errors))
        rng = _seed(seed)
        if ledger is not None:
            _json_data(ledger, "소재 대장")
            if type(ledger) is not dict or type(ledger.get("entries", [])) is not list:
                raise ValueError("소재 대장은 entries 배열을 가진 dict여야 합니다")
            if any(type(entry) is not dict for entry in ledger.get("entries", [])):
                raise ValueError("소재 대장 entries는 dict 배열이어야 합니다")
        copied_ledger = deepcopy(ledger)
        entries = (copied_ledger or {}).get("entries", [])
        used_domains = {entry[key] for entry in entries
                        for key in ("domain", "field", "area", "분야", "소재영역")
                        if type(entry.get(key)) is str}
        warnings = []
        shared_domains = {}
        for identifier, group in self._sets.items():
            blueprints = [self._content["types"][code] for code in group["types"]]
            common = [domain for domain in blueprints[0]["domains"]
                      if all(domain in blueprint["domains"] for blueprint in blueprints[1:])]
            if common:
                available_common = [domain for domain in common if domain not in used_domains]
                shared_domains[identifier] = rng.choice(available_common or common)
                if not available_common:
                    warnings.append(f"세트 {identifier}: 공통 소재 후보가 모두 명시 대장과 일치하여 기존 영역을 재사용합니다; 추가 소재 검토가 필요합니다")
            else:
                warnings.append(f"세트 {identifier}: 유형별 소재 후보의 교집합이 없어 공통지문 소재 조정이 필요합니다")
        selected_tasks = {}
        slots = []
        for row in design["slots"]:
            blueprint = self._content["types"][row["type_code"]]
            domains = blueprint["domains"]
            matched = [domain for domain in domains if domain in used_domains]
            available = [domain for domain in domains if domain not in used_domains]
            group = self._sets.get(row["set_id"])
            tasks = blueprint["reasoning_tasks"]
            used_tasks = selected_tasks.setdefault(row["set_id"], set()) if group else set()
            remaining_tasks = [task for task in tasks if task not in used_tasks]
            if group and not remaining_tasks:
                warnings.append(f"세트 {row['set_id']}의 {row['type_code']}: 서로 다른 판단 과제가 부족하여 실제 차별 판단 재검토가 필요합니다")
            task = rng.choice(remaining_tasks or tasks)
            used_tasks.add(task)
            selected_domain = shared_domains[row["set_id"]] if row["set_id"] in shared_domains else rng.choice(available or domains)
            if ledger is None:
                avoidance = "대장 미제공: 누적 소재 중복 검사는 수행하지 않음"
            elif selected_domain in used_domains:
                avoidance = ("공통지문 영역을 우선하여 명시 대장에 있는 영역을 재사용; 추가 소재 검토 필요"
                             if row["set_id"] in shared_domains else
                             "모든 후보 영역이 대장과 일치하여 기존 영역을 재사용; 추가 소재 검토 필요")
            elif matched:
                avoidance = "명시 대장과 정확히 일치하는 영역을 후보에서 제외; 원문 중복 여부는 미검증"
            else:
                avoidance = "명시 대장 영역과 정확히 일치하는 후보 없음; 원문 중복 여부는 미검증"
            slots.append({
                "slot": row["slot"], "type": row["type"], "type_code": row["type_code"],
                "논리_설계": {
                    "판단_과제": task,
                    "오답_경로": blueprint["distractor_paths"],
                    "검토_항목": blueprint["review_checks"],
                    "구성_유의": blueprint["construction_notes"],
                    "설계_순서": "판단 구조와 근거를 확정한 뒤 선지를 작성하고 정답 유일성을 검토한다.",
                },
                "소재": {"영역": selected_domain,
                         "영역_후보": domains,
                         "대장_회피": {"상태": avoidance, "기록_수": len(entries), "일치_영역": matched},
                         "출처_정책": self._policies["source_policy"]},
                "난도": {"편집_목표": row["difficulty"], "실측": False,
                         "정책": self._policies["difficulty_policy"]},
                "세트": {"id": row["set_id"], "members": sorted(group["members"]) if group else [],
                         "공통지문": row["set"], "공통_영역": shared_domains.get(row["set_id"]),
                         "정책": self._policies["common_passage_policy"]},
                "응답_형식": row["response_format"],
            })
        return deepcopy({
            "meta": self._meta(seed),
            "회차": {
                "원자료_관측": self._config["observations"],
                "편집_결정": self._config["editorial_decisions"],
                "편집_정책": {key: self._policies[key] for key in sorted(_POLICIES)},
                "warnings": warnings,
                "검토_상태": "구성 제안: 원문 출제·독립 풀이·전문가 확인·실측 난도·독창성 검토는 별도 수행한다.",
                "소재_대장": {"제공됨": ledger is not None, "입력": copied_ledger,
                            "검색_수행": False, "설명": "명시 제공된 기록만 참조하며 RAG 검색을 수행하지 않음"},
            },
            "슬롯": slots,
        })
