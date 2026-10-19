"""Pure, explicit conversion of native track models to HWPX manuscript dictionaries.

This does not accept legacy ``haean.models.Draft`` objects, render figures, read
templates, write files, run a model, or certify the resulting document's layout.
The optional typesetter is deliberately not imported. Unsupported structures fail
before a manuscript is returned; the caller retains the original Draft as its
production record. Figure assets are not supported by this initial contract.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .tracks import get as get_track
from .tracks.core.model import Block, Draft, Item, Judge, LABELLED
from .tracks.core.track import Brief

CONTRACT_VERSION = "haean-track-typeset-v1"
_PROFILES = {
    ("leet_reasoning", None): "leet_reasoning",
    ("leet_reading", None): "leet_verbal",
    ("psat_verbal", 5): "psat5_language",
    ("psat_data", 5): "psat5_data",
    ("psat_situation", 5): "psat5_situation",
}
_COMMON_BLOCKS = {"문단", "소제목", "발언", "나열", "조문", "항", "호", "표"}
_REASONING_BLOCKS = _COMMON_BLOCKS | {"조건", "실험", "원리", "목록", "의안"}
_FLOW_BLOCKS = _COMMON_BLOCKS | {"상자", "목", "주석"}


class TrackTypesetError(ValueError):
    """An unsupported or lossy conversion, with a stable code and source path."""

    def __init__(self, code: str, message: str, path: str = ""):
        self.code, self.path, self.message = code, path, message
        super().__init__(f"[{code}] {path + ': ' if path else ''}{message}")


def _fail(code, message, path):
    raise TrackTypesetError(code, message, path)


def _identifier(value: str, path: str):
    if not value or value != value.strip():
        _fail("IDENTIFIER", "식별자는 비거나 앞뒤 공백을 포함할 수 없습니다", path)


def _active_fields(block: Block, allowed: set[str], path: str):
    for name, field in Block.model_fields.items():
        if name in allowed or name == "kind":
            continue
        if getattr(block, name) != field.get_default(call_default_factory=True):
            _fail("UNCONSUMED_FIELD", "이 블록에서 출력되지 않는 필드에 값이 있습니다", f"{path}.{name}")


def _table(block: Block, profile: str, path: str) -> dict:
    _active_fields(block, {"rows", "title", "unit", "note", "header_row", "col_widths", "align"}, path)
    rows = block.rows
    ncols = sum(c.colspan for c in rows[0])
    if not ncols:
        _fail("TABLE_GRID", "표 첫 행은 한 칸 이상이어야 합니다", path)
    occupied: set[tuple[int, int]] = set()
    result = []
    for r, row in enumerate(rows):
        c, output_row = 0, []
        for cell in row:
            while (r, c) in occupied:
                c += 1
            if c + cell.colspan > ncols or r + cell.rowspan > len(rows):
                _fail("TABLE_GRID", "병합 셀이 표 범위를 벗어납니다", f"{path}.rows[{r}]")
            for rr in range(r, r + cell.rowspan):
                for cc in range(c, c + cell.colspan):
                    if (rr, cc) in occupied:
                        _fail("TABLE_GRID", "병합 셀들이 겹칩니다", f"{path}.rows[{r}]")
                    occupied.add((rr, cc))
            if cell.colspan == cell.rowspan == 1:
                output_row.append(cell.text)
            else:
                output_cell = {"글": cell.text}
                if cell.colspan != 1:
                    output_cell["가로"] = cell.colspan
                if cell.rowspan != 1:
                    output_cell["세로"] = cell.rowspan
                output_row.append(output_cell)
            c += cell.colspan
        if any((r, cc) not in occupied for cc in range(ncols)):
            _fail("TABLE_GRID", "표에 정의되지 않은 빈 칸이 있습니다", f"{path}.rows[{r}]")
        result.append(output_row)
    if profile == "leet_reasoning" and (block.col_widths or block.align):
        _fail("TABLE_STYLE_UNSUPPORTED", "추리논증 프로필은 지정 열폭·정렬을 보존하지 못합니다", path)
    if block.col_widths and (len(block.col_widths) != ncols or
                             any(not math.isfinite(w) or w <= 0 for w in block.col_widths)):
        _fail("TABLE_WIDTHS", "열폭은 열 수와 같은 개수의 유한한 양수여야 합니다", path)
    if block.align and len(block.align) != ncols:
        _fail("TABLE_ALIGN", "정렬 수가 표 열 수와 다릅니다", path)
    out = {"표": result, "머리행": block.header_row}
    for key, value in (("제목", block.title), ("단위", block.unit), ("주석", block.note)):
        if value:
            out[key] = value
    if block.col_widths:
        out["열폭"] = list(block.col_widths)
    if block.align:
        out["정렬"] = list(block.align)
    return out


def _block(block: Block, profile: str, path: str) -> dict:
    allowed = _REASONING_BLOCKS if profile == "leet_reasoning" else _FLOW_BLOCKS
    if block.kind not in allowed:
        _fail("BLOCK_UNSUPPORTED", f"{profile}에서 {block.kind} 블록을 지원하지 않습니다", path)
    if block.kind == "표":
        return _table(block, profile, path)
    if block.kind == "상자":
        _active_fields(block, {"title", "children"}, path)
        return {"상자": block.title,
                "내용": [_block(child, profile, f"{path}.children[{n}]")
                       for n, child in enumerate(block.children)]}
    _active_fields(block, {"text", "label"} if block.kind in LABELLED else {"text"}, path)
    if block.kind in LABELLED and block.label != block.label.strip():
        _fail("LABEL", "라벨 앞뒤 공백은 조판에서 보존되지 않습니다", path)
    if block.kind == "발언":
        if profile == "leet_reasoning" and not re.fullmatch(r"[가-힣](?: ?\d+)?|[A-Z]\d*", block.label):
            _fail("LABEL_UNSUPPORTED", "추리논증 양식에서 지원하지 않는 발언 라벨입니다", path)
        return {"라벨": block.label, "글": block.text}
    if block.kind in LABELLED:
        return {block.kind: block.label, "글": block.text}
    return {block.kind: block.text}


def _judges(judges: list[Judge]) -> list[dict]:
    return [{"판정": j.mark, "설명": list(j.explanation)} for j in judges]


def _solution(item: Item, profile: str, path: str) -> dict:
    solution = item.solution
    if solution.comment_title and not solution.comment:
        _fail("COMMENT_EMPTY", "논평 제목만 있고 본문이 없습니다", path)
    sj, oj = solution.statement_judgments, solution.option_judgments
    if sj and (not item.statements or len(sj) != len(item.statements)):
        _fail("JUDGE_COUNT", "보기 판정 수가 보기 수와 다릅니다", path)
    if oj and len(oj) != 5:
        _fail("JUDGE_COUNT", "선지 판정은 5개여야 합니다", path)
    # Reading solutions distinguish multiple judged statements from a single
    # quoted/material box. Their current renderer cannot represent one judgment.
    if profile == "leet_verbal" and sj and len(item.statements) < 2:
        _fail("JUDGE_UNSUPPORTED", "언어이해의 단일 보기 명제판정은 지원하지 않습니다", path)
    area = item.area + (f"({item.area_detail})" if item.area_detail else "")
    out = {"제재": solution.topic, "난이도": solution.level,
           "내용영역": area, "문항유형": item.item_type}
    if solution.comment:
        out["논평"] = ({"제목": solution.comment_title, "글": list(solution.comment)}
                     if solution.comment_title else list(solution.comment))
    if sj:
        out["정오판단"] = _judges(sj)
        if oj:
            out["선지판단"] = _judges(oj)
    elif item.statements and oj and profile != "leet_verbal":
        combo = all(re.fullmatch(r"[ㄱ-ㅇ](\s*,\s*[ㄱ-ㅇ])*", c.text.strip()) for c in item.options)
        if combo:
            _fail("JUDGE_UNSUPPORTED", "조합 선지는 보기 명제판정이 필요합니다", path)
        out["정오판단"], out["선지판단"] = [], _judges(oj)
    else:
        if profile == "leet_verbal" and oj and len(item.statements) == 5:
            _fail("JUDGE_UNSUPPORTED", "5개 보기의 선지판정은 현 언어이해 엔진에서 대상을 구별하지 못합니다", path)
        out["정오판단"] = _judges(oj)
    return out


def _item(item: Item, profile: str, include_solutions: bool, in_set: bool) -> dict:
    path = f"items[{item.id}]"
    if item.figures or any(s.figure_id for s in item.statements) or any(c.figure_id for c in item.options):
        _fail("FIGURE_UNSUPPORTED", "이 어댑터는 그림·그림 선지와 자산 경로 주입을 아직 지원하지 않습니다", path)
    if any(c.width_pt != 0 for c in item.options):
        _fail("UNCONSUMED_FIELD", "글 선지의 width_pt는 출력되지 않습니다", path)
    if item.option_layout:
        _fail("LAYOUT_UNSUPPORTED", "그림 선지 배치는 현재 어댑터에서 지원하지 않습니다", path)
    if item.flow and profile == "leet_reasoning":
        _fail("LAYOUT_UNSUPPORTED", "추리논증 프로필은 문항 flow 힌트를 소비하지 않습니다", path)
    if len(item.statements) > 5:
        _fail("STATEMENT_COUNT", "현재 하네스 호환 계약은 보기를 최대 5개 지원합니다", path)
    for n, statement in enumerate(item.statements):
        if re.match(r"^\s*[ㄱ-ㅇ]\s*\.\s*", statement.text):
            _fail("PREFIX", "보기 본문에 자동 머리(ㄱ.)를 포함할 수 없습니다", f"{path}.statements[{n}]")
    for n, choice in enumerate(item.options):
        if re.match(r"^\s*[①-⑤]", choice.text):
            _fail("PREFIX", "선지 본문에 자동 번호(①)를 포함할 수 없습니다", f"{path}.options[{n}]")
    blocks = item.own_blocks if in_set else item.passage
    field = "own_blocks" if in_set else "passage"
    out = {"id": item.id, "발문": item.stem,
           "선지": [choice.text for choice in item.options]}
    if blocks:
        out["지문"] = [_block(b, profile, f"{path}.{field}[{n}]") for n, b in enumerate(blocks)]
    if item.statements:
        out["보기"] = [s.text for s in item.statements]
    if item.flow:
        out[item.flow] = True
    if include_solutions:
        out["정답"] = item.answer
        out["해설"] = _solution(item, profile, path + ".solution")
    return out


def to_manuscript(
    draft: Draft,
    brief: Brief,
    *,
    include_solutions: bool = True,
    title: str = "",
    figure_paths: Mapping[tuple[str, str], str] | None = None,
) -> dict:
    """Return an independent manuscript; raise before returning on any loss.

    Only native track Draft/Brief instances are accepted. ``include_solutions``
    controls answers as well as explanations. Production design, reference IDs,
    calculations, judgment traps, and design summaries never enter the manuscript.
    ``figure_paths`` is reserved: non-empty mappings and all figures are rejected.
    Success proves a structural conversion, not generation/review/native rendering.
    """
    if not isinstance(draft, Draft) or not isinstance(brief, Brief):
        _fail("MODEL_TYPE", "native tracks.core.model.Draft와 tracks.core.track.Brief가 필요합니다", "input")
    if not isinstance(include_solutions, bool) or not isinstance(title, str):
        _fail("ARGUMENT", "include_solutions는 bool, title은 str이어야 합니다", "input")
    if figure_paths is not None and (not isinstance(figure_paths, Mapping) or figure_paths):
        _fail("FIGURE_UNSUPPORTED", "검증된 그림 자산 주입은 아직 지원하지 않습니다", "figure_paths")
    # Revalidate copies, including mutable nested lists. Never normalize the caller's
    # objects or implicitly convert a legacy schema into a native track model.
    draft = Draft.model_validate(draft.model_dump())
    brief = Brief.model_validate(brief.model_dump())
    profile = _PROFILES.get((brief.track, brief.grade))
    if profile is None:
        _fail("PROFILE_UNSUPPORTED", f"지원하지 않는 트랙/급수입니다: {brief.track}/{brief.grade}", "brief")
    track = get_track(brief.track)
    errors = track.check_brief(brief)
    if errors:
        _fail("BRIEF_INVALID", "; ".join(errors), "brief")
    if len(draft.items) != brief.count:
        _fail("ITEM_COUNT", "Draft 문항 수와 Brief.count가 다릅니다", "items")
    ids = [item.id for item in draft.items]
    for n, ident in enumerate(ids):
        _identifier(ident, f"items[{n}].id")
    if len(set(ids)) != len(ids):
        _fail("IDENTIFIER", "문항 ID가 중복됩니다", "items")
    if brief.ids and brief.ids != ids:
        _fail("ITEM_ORDER", "Brief.ids와 Draft 문항 ID·순서가 다릅니다", "items")
    for item in draft.items:
        if item.set_id:
            _identifier(item.set_id, f"items[{item.id}].set_id")
        if item.own_blocks and not item.set_id:
            _fail("OWN_BLOCKS", "세트 밖의 own_blocks는 지원하지 않습니다", f"items[{item.id}]")
    infos = {}
    for info in draft.sets:
        _identifier(info.set_id, "sets.set_id")
        if info.set_id in infos:
            _fail("SET_INFO", "SetInfo의 set_id가 중복됩니다", "sets")
        infos[info.set_id] = info
    set_ids = {item.set_id for item in draft.items}
    if brief.set:
        if len(set_ids) != 1 or "" in set_ids:
            _fail("SET_ID", "세트 문항은 동일한 non-empty set_id를 써야 합니다", "items")
    elif set_ids != {""}:
        _fail("SET_UNSUPPORTED", "이 Brief는 공통지문 세트를 허용하지 않습니다", "items")
    if set(infos) - set_ids:
        _fail("SET_INFO", "쓰이지 않는 SetInfo가 있습니다", "sets")
    if not brief.set:
        entries = [_item(i, profile, include_solutions, False) for i in draft.items]
    else:
        first = draft.items[0]
        passage = [b.model_dump() for b in first.passage]
        if any([b.model_dump() for b in i.passage] != passage for i in draft.items[1:]):
            _fail("SHARED_PASSAGE", "세트의 공통지문 구조·내용이 서로 다릅니다", "items.passage")
        info = infos.get(first.set_id)
        head = {"id": first.set_id,
                "지문": [_block(b, profile, f"sets[{first.set_id}].passage[{n}]")
                       for n, b in enumerate(first.passage)]}
        if info and info.guide:
            head["안내"] = info.guide
        if include_solutions and profile == "leet_verbal":
            metadata = {(i.solution.topic, i.solution.level, i.area, i.area_detail) for i in draft.items}
            if len(metadata) != 1:
                _fail("SET_SOLUTION", "언어이해 세트의 제재·별점·내용영역이 서로 다릅니다", "items.solution")
            head["해설"] = {"제재": first.solution.topic, "난이도": first.solution.level,
                          "내용영역": first.area + (f"({first.area_detail})" if first.area_detail else "")}
            if info and info.summary:
                head["해설"]["지문총평"] = list(info.summary)
        elif include_solutions and info and info.summary:
            _fail("SET_SUMMARY_UNSUPPORTED", "PSAT 해설 프로필은 세트 지문총평을 출력하지 않습니다", "sets.summary")
        entries = [{"세트": head, "문항": [_item(i, profile, include_solutions, True) for i in draft.items]}]
    out = {"profile": profile, "문항": entries}
    if title:
        out["시험명"] = title
    return out
