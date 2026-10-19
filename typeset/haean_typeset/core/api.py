# -*- coding: utf-8 -*-
"""하네스용 API. 파일 경로가 아니라 dict 를 주고받는다. 전역 상태가 없어 같은 입력은 늘 같은 결과다.

    from haean_typeset import api
    diags = api.validate(item)                         # 원고 검사(hwpx 안 만듦)
    lined, diags = api.wrap(item)                      # 줄이 정해진 원고(기본: 옛 \\n 지우고 다시 나눔)
    m = api.measure(item, number=None, total=None)     # 분량(줄 수·높이·여유 줄·블록별 줄 수)
    result = api.typeset(exam, "문제지.hwpx")           # 조판
"""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import tempfile

from .diagnostics import Diag
from .measure import measure_plan
from .model import Figure
from .template import TemplateError



class StrictError(Exception):
    """strict=True 인데 오류가 있어 hwpx 를 만들지 않았다. .result 에 진단이 들어 있다."""

    def __init__(self, result):
        super().__init__("오류 %d건으로 조판하지 않았습니다" % sum(d["level"] == "error" for d in result["diagnostics"]))
        self.result = result


def load_profile(profile=None, template_path=None):
    """Return a per-call profile; private templates are always supplied by callers."""
    if not profile:
        from ..profiles import DEFAULT
        profile = DEFAULT
    if isinstance(profile, str):
        mod = importlib.import_module("haean_typeset.profiles.%s" % profile)
        profile = mod.PROFILE
    result = copy.copy(profile)
    # Geometry holds an open template and must never be shared across requests.
    if hasattr(result, "_geo"):
        result._geo = None
    if template_path is not None:
        result.template_path = os.fspath(template_path)
    return result


def _item_key(item, number):
    return number if number is not None else item.get("id")


def validate(item, profile=None, number=None, base_dir=None, template_path=None):
    """원고 검사: 필드·보기/선지 대응·블록 꼴·라벨·그림 파일·수식·꺾쇠. → [Diagnostic]"""
    P = load_profile(profile, template_path)
    if getattr(P, "flow", False):
        return P.validate(item, number, base_dir)
    diag = Diag(_item_key(item, number))
    if P.validate_item(number or 1, item, diag, base_dir):
        P.plan_item(number or 1, item, diag, P.new_ctx(), base_dir)
    return diag.as_list()


def wrap(item, profile=None, rewrap=True, number=None, base_dir=None, template_path=None):
    """줄 나눔. rewrap=True(기본)면 원고의 옛 \\n 을 지우고 다시 나눈다. → (새 원고, [Diagnostic])"""
    P = load_profile(profile, template_path)
    if getattr(P, "flow", False):
        return P.wrap(item, rewrap, number, base_dir)
    diag = Diag(_item_key(item, number))
    src = copy.deepcopy(item)
    if rewrap:
        P.unwrap(src)
    if not P.validate_item(number or 1, src, Diag(), base_dir):
        return src, diag.as_list()
    new = P.wrap_item(number or 1, src, diag, P.new_ctx(), base_dir, check=not rewrap)
    return new, diag.as_list()


def measure(item, profile=None, number=None, total=None, base_dir=None, template_path=None):
    """분량 측정. 줄이 안 정해진 문단은 어절 단위로 나눈 줄 수로 잰다(원고는 고치지 않음).
    number=None 이면 '그 밖' 자리 기준. → Measure"""
    P = load_profile(profile, template_path)
    if getattr(P, "flow", False):
        return P.measure(item, number, total, base_dir)
    ctx = P.new_ctx()
    if not P.validate_item(number or 1, item, Diag(), base_dir):
        return {"lines": 0, "height_pt": 0.0, "capacity_pt": round(P.capacity(number, total), 1),
                "spare_lines": None, "per_block": [], "verdict": "invalid"}
    lined = P.wrap_item(number or 1, item, Diag(), ctx, base_dir, check=False)
    plan = P.plan_item(number or 1, lined, Diag(), ctx, base_dir)
    return measure_plan(plan, P, number, total)


LINE_MODES = ("fit", "force", "none")


def line_mode(value):
    """auto_break 인자 → 줄 모드. True/'force' 강제 줄 나눔(옛 방식), False/'none' 한글에 맡김, 'fit'(기본) 예측 줄 + 자간."""
    if value is True:
        return "force"
    if value is False or value is None:
        return "none"
    if value not in LINE_MODES:
        raise ValueError("줄 모드는 fit · force · none 중 하나입니다: %r" % (value,))
    return value


def line_guide(profile=None, template_path=None):
    """입력(작성) 단계 참고: 그 프로필의 줄당 글자수(빈칸 포함)·단 높이·줄 상한. 글자수를 줄 수로 환산할 때 쓴다."""
    P = load_profile(profile, template_path)
    return P.line_guide() if hasattr(P, "line_guide") else {}


def typeset(exam, out_path, profile=None, title=None, strict=False, base_dir=None, auto_break="fit",
            solution=True, template_path=None, solution_template_path=None):
    """Build with explicit local templates; publish new outputs only after success.

    Templates and existing outputs are never overwritten. Both problem and solution
    files are staged together, so a late strict error leaves neither output behind.
    This API performs structural generation, not native Hancom visual verification.
    """
    if template_path is None:
        raise TemplateError("TEMPLATE_REQUIRED", "로컬 문제지 양식 경로(template_path)가 필요합니다")
    input_hash = hashlib.sha256(json.dumps(exam, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode("utf-8")).hexdigest()
    template = Path(template_path).expanduser().resolve(strict=True)
    if not template.is_file():
        raise TemplateError("TEMPLATE_OPEN", "양식은 파일이어야 합니다")
    P = load_profile(profile or exam.get("profile"), template)
    entries = exam.get("문항") or []
    flat = [item for entry in entries for item in
            (entry.get("문항") or [] if isinstance(entry, dict) and "세트" in entry else [entry])]
    wants_solution = bool(solution and getattr(P, "solution_profile", None)
                          and any(isinstance(item, dict) and item.get("해설") for item in flat))
    solution_template = None
    if wants_solution:
        if solution_template_path is None:
            raise TemplateError("SOLUTION_TEMPLATE_REQUIRED", "로컬 해설 양식 경로(solution_template_path)가 필요합니다")
        solution_template = Path(solution_template_path).expanduser().resolve(strict=True)
        if not solution_template.is_file():
            raise TemplateError("TEMPLATE_OPEN", "해설 양식은 파일이어야 합니다")

    output = Path(out_path).expanduser().absolute()
    solution_output = output.with_name(output.stem + "_해설.hwpx") if output.suffix == ".hwpx" else Path(str(output) + "_해설.hwpx")
    targets = [output] + ([solution_output] if wants_solution else [])
    sources = {template, solution_template} - {None}
    for target in targets:
        if target.resolve() in sources:
            raise ValueError("원본 양식을 덮어쓸 수 없습니다")
        if os.path.lexists(target):
            raise FileExistsError("기존 출력은 덮어쓰지 않습니다: " + str(target))
    output.parent.mkdir(parents=True, exist_ok=True)
    template_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    with tempfile.TemporaryDirectory(prefix=".haean-typeset-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        try:
            result = _typeset(exam, str(staged), profile=P, title=title, strict=strict,
                              base_dir=base_dir, auto_break=auto_break, solution=solution,
                              template_path=str(template),
                              solution_template_path=str(solution_template) if solution_template else None)
        except StrictError as exc:
            exc.result["path"] = None
            exc.result["solution_path"] = None
            raise
        pairs = [(staged, output)]
        if wants_solution:
            pairs.append((Path(result["solution_path"]) if result.get("solution_path") else
                          Path(temporary) / "missing-solution", solution_output))
        if any(not source.is_file() for source, _ in pairs):
            raise TemplateError("OUTPUT_MISSING", "문제지 또는 해설지 생성이 끝나지 않아 결과를 확정하지 않았습니다")
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != template_hashes[str(path)] for path in sources):
            raise TemplateError("TEMPLATE_CHANGED", "조판 중 원본 양식이 바뀌었습니다")
        published = []
        try:
            for source, destination in pairs:
                # link is an atomic no-clobber operation on the same filesystem.
                stat = source.stat()
                os.link(source, destination)
                published.append((destination, stat.st_dev, stat.st_ino))
        except BaseException:
            for destination, device, inode in reversed(published):
                try:
                    stat = destination.lstat()
                    if (stat.st_dev, stat.st_ino) == (device, inode):
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise
    result["path"] = str(output)
    result["solution_path"] = str(solution_output) if wants_solution else None
    result["templates"] = [{"path": str(path), "sha256": template_hashes[str(path)]}
                           for path in (template, solution_template) if path is not None]
    result["input_sha256"] = input_hash
    result.update(native_hancom_verified=False, native_page_count_verified=False,
                  layout_verified=False, delivery_ready=False, pages_are_estimated=True)
    return result


def _typeset(exam, out_path, profile=None, title=None, strict=False, base_dir=None, auto_break="fit",
             solution=True, template_path=None, solution_template_path=None):
    """원고 dict → hwpx. → Result {path, pages, items:[Measure], diagnostics, solution_path}.
    strict=True 면 오류가 하나라도 있으면 파일을 만들지 않고 StrictError.
    auto_break(줄 모드) — 'fit'(기본): 조판기가 어절 단위로 줄을 정하고, 넘치는 줄에 음수 자간을 넣어 한글이 스스로 같은 자리에서
    줄을 접게 한다(강제 줄 나눔 없음 → 양쪽 맞춤 유지). 'force'(=True): 정한 줄을 강제 줄 나눔으로 박는 옛 방식(그 줄은
    양쪽 맞춤이 안 된다). 'none'(=False): 줄을 정하지 않고 한글에 맡긴다(원고 \\n 만 강제 줄 나눔)."""
    mode = line_mode(auto_break)
    P = load_profile(profile or exam.get("profile"))
    if getattr(P, "flow", False):
        return P.typeset_exam(exam, out_path, title=title, strict=strict, base_dir=base_dir, auto_break=mode,
                              solution=solution, template_path=template_path,
                              solution_template_path=solution_template_path)
    items = list(exam.get("문항") or [])
    title = title or exam.get("시험명")
    total = len(items)
    diag = Diag()
    ctx = P.new_ctx()
    ctx.line_mode = mode
    result = {"path": None, "pages": None, "items": [], "diagnostics": None, "solution_path": None,
              "profile": getattr(P, "name", None)}
    if total > P.max_items:
        diag.error("ITEM_COUNT", "문항이 %d개입니다(%d개까지)" % (total, P.max_items), count=total)
        result["diagnostics"] = diag.as_list()
        raise StrictError(result) if strict else ValueError(diag.items[-1]["message"])
    try:
        tpl = P.open_template(ctx, template_path)
    except TemplateError as e:
        diag.error(e.code, str(e))
        result["diagnostics"] = diag.as_list()
        raise StrictError(result) if strict else e
    parts, figures, over, bins = [], [], False, {}
    for n, item in enumerate(items, 1):
        d = Diag(n)
        if not P.validate_item(n, item, d, base_dir):
            diag.extend(d)
            result["items"].append({"number": n, "verdict": "invalid"})
            continue
        lined = P.wrap_item(n, item, d, P.new_ctx(), base_dir, check=True)
        plan = P.plan_item(n, lined if mode != "none" else item, d, ctx, base_dir)
        hplan = plan if mode != "none" else P.plan_item(n, lined, Diag(n), P.new_ctx(), base_dir)
        if mode != "none" and hasattr(P, "fit_lines"):
            P.fit_lines(plan, ctx, item, keep_breaks=(mode == "force"))
        m = measure_plan(hplan, P, n, total)
        m["number"] = n
        m["id"] = item.get("id")
        m["layout"] = plan["layout"]
        result["items"].append(m)
        strict_slot = P.strict_slots(n, total)
        if m["verdict"] == "over":
            over = True
            d.error("ITEM_OVER", "%d줄 · %.0fpt로 단 높이 %.0fpt를 %.1f줄 넘습니다%s"
                    % (m["lines"], m["height_pt"], m["capacity_pt"], -m["spare_lines"],
                       " (줄 수 상한이 작은 자리)" if strict_slot else ""),
                    height=m["height_pt"], capacity=m["capacity_pt"], spare_lines=m["spare_lines"])
        elif m["verdict"] == "tight":
            d.warning("ITEM_TIGHT", "여유가 %.1f줄입니다" % m["spare_lines"], spare_lines=m["spare_lines"])
        for f in P.plan_objects(plan):
            if isinstance(f, Figure):
                if f.abspath not in bins:                      # 같은 그림 파일은 한 번만 넣는다
                    bins[f.abspath] = "image%d" % (len(bins) + 1)
                    figures.append(f)
                f.bin_id = bins[f.abspath]
        parts.append(P.item_xml(n, plan, ctx, n == 1, tpl))
        diag.extend(d)
    pages = P.pages(total)
    if over:
        diag.error("PAGECOUNT_UNRELIABLE", "넘친 문항이 있어 전체 쪽 수를 바꾸지 않았습니다(양식 값 그대로)")
        pages = None
    if figures and tpl.pic_skeleton is None:
        diag.error("TEMPLATE_PICTURE", "양식에서 그림 뼈대(<hp:pic>)를 찾지 못했습니다")
    result["pages"] = pages
    if strict and diag.errors():
        result["diagnostics"] = diag.as_list()
        raise StrictError(result)
    tpl.build(out_path, "".join(parts), figures, title, total, pages, P.check_box(total), diag)
    result["path"] = out_path
    if solution and getattr(P, "solution_profile", None) and any(it.get("해설") for it in items):
        S = load_profile(P.solution_profile)
        sol_out = out_path[:-5] + "_해설.hwpx" if out_path.endswith(".hwpx") else out_path + "_해설.hwpx"
        S.build(items, sol_out, title=title, review=exam.get("총평"), diag=diag,
                template_path=solution_template_path)
        result["solution_path"] = sol_out
    result["diagnostics"] = diag.as_list()
    if strict and diag.errors():
        raise StrictError(result)
    return result
