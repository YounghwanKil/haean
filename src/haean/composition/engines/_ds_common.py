"""Pure boundaries shared by the two PSAT 5 composition engines."""

from copy import deepcopy


def in_range(value, bounds):
    return bounds[0] <= value <= bounds[1]


def max_run(sequence):
    best = current = 0
    previous = object()
    for value in sequence:
        current = current + 1 if value == previous else 1
        best = max(best, current)
        previous = value
    return best


def copied_rules(**rules):
    for role, value in rules.items():
        if not isinstance(value, dict):
            raise ValueError(f"{role}: 외부 규칙은 dict여야 합니다")
    return {role: deepcopy(value) for role, value in rules.items()}


def supported_options(options, allowed):
    """Reject unsupported grades/sizes rather than truncate a 40-slot design."""
    options = deepcopy(options)
    for key, expected in (("grade", 5), ("exam_grade", 5), ("size", 40)):
        if key in options:
            value = options.pop(key)
            if type(value) is not int or value != expected:
                raise ValueError("현재 PSAT 회차 엔진은 5급 40문항만 지원합니다. 7급 회차는 미지원입니다")
    unexpected = sorted(set(options) - set(allowed))
    if unexpected:
        raise ValueError(f"지원하지 않는 설계 옵션: {', '.join(unexpected)}")
    return options


def format_input_errors(design, answer_key):
    if not isinstance(design, dict) or not isinstance(design.get("slots"), list):
        return ["형식설계는 slots 배열을 가진 dict여야 합니다"]
    meta = design.get("meta", {})
    if not isinstance(meta, dict):
        return ["형식설계 meta는 dict여야 합니다"]
    for key, expected in (("grade", 5), ("exam_grade", 5), ("size", 40)):
        if key in meta and (type(meta[key]) is not int or meta[key] != expected):
            return ["현재 PSAT 회차 엔진은 5급 40문항만 지원합니다"]
    slots = design["slots"]
    if len(slots) != 40 or any(not isinstance(slot, dict) for slot in slots):
        return ["문번 1~40의 슬롯 dict 40개가 필요합니다"]
    numbers = [slot.get("slot") for slot in slots]
    if any(type(number) is not int for number in numbers) or numbers != list(range(1, 41)):
        return ["문번 1~40은 중복·누락 없이 오름차순이어야 합니다"]
    return [f"슬롯 {slot['slot']} 정답은 1~5의 정수여야 합니다"
            for slot in slots if type(slot.get(answer_key)) is not int or not 1 <= slot[answer_key] <= 5]


def copied_ledger(ledger):
    ledger = {} if ledger is None else deepcopy(ledger)
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries", []), list):
        raise ValueError("소재 대장은 entries 배열을 가진 dict여야 합니다")
    if any(not isinstance(entry, dict) for entry in ledger.get("entries", [])):
        raise ValueError("소재 대장 entries는 dict 배열이어야 합니다")
    return ledger


def required_slot_errors(design, fields):
    errors = []
    for slot in design["slots"]:
        missing = sorted(set(fields) - set(slot))
        if missing:
            errors.append(f"슬롯 {slot['slot']} 필수 형식 필드 누락: {', '.join(missing)}")
    return errors
