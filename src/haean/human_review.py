"""Immutable, answer-separated team review packets and evidence collection.

These records are reviewer submissions, not approvals or expert certificates.
No parent run, checkpoint, feedback rule, or evaluation result is updated here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import tempfile
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import Draft, Item


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class _BriefScope(ReviewModel):
    """Read legacy briefs without rewriting their authoring/difficulty fields."""
    exam: Literal["leet", "psat5", "psat7"]
    subject: Literal["추리논증", "언어논리", "자료해석", "상황판단"]
    count: int = Field(ge=1, le=4)

    @model_validator(mode="after")
    def route(self):
        if (self.exam == "leet") != (self.subject == "추리논증"):
            raise ValueError("LEET 추리논증 또는 PSAT 5·7급 세 과목만 지원합니다")
        return self


Nonempty = Annotated[str, Field(min_length=1)]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Choice = Annotated[int, Field(ge=1, le=5)]


class ReviewIssue(ReviewModel):
    severity: Literal["A", "B", "C"]
    location: Nonempty
    quote: Nonempty
    problem: Nonempty
    proposed_fix: Nonempty

    @field_validator("location", "quote", "problem", "proposed_fix")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("공백만 있는 검토 의견은 사용할 수 없습니다")
        return value


class ItemResponse(ReviewModel):
    number: int = Field(ge=1)
    item_id: Nonempty
    completed: bool
    prior_answer_seen: bool | None = None
    answer: Choice | None = None
    solve_seconds: Seconds | None = None
    option_reasoning: dict[Literal["1", "2", "3", "4", "5"], Nonempty] | None = None
    issues: list[ReviewIssue] | None = None
    edit_seconds: Seconds | None = None

    @field_validator("option_reasoning")
    @classmethod
    def nonblank_reasons(cls, value):
        if value is not None and any(not reason.strip() for reason in value.values()):
            raise ValueError("선택지 판단 근거는 공백일 수 없습니다")
        return value


class ReviewResponse(ReviewModel):
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: Nonempty
    origin: Literal["human", "model"]
    items: list[ItemResponse] = Field(min_length=1)

    @field_validator("reviewer")
    @classmethod
    def nonblank_reviewer(cls, value):
        if not value.strip():
            raise ValueError("검토자를 입력하세요")
        return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _reject_constant(value):
    raise ValueError(f"유한하지 않은 JSON 수치: {value}")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복 JSON 키: {key}")
        result[key] = value
    return result


def _read_json(path: Path):
    return json.loads(path.read_bytes(), parse_constant=_reject_constant,
                      object_pairs_hook=_unique_keys)


def _write_json(path: Path, value):
    path.write_bytes(_json_bytes(value))


def _item_sha(item: Item) -> str:
    return _sha(_json_bytes(item.model_dump()))


def _resolve_run(value, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("run·parent_run 경로가 필요합니다")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    local = (base / path).resolve()
    return local if local.exists() else path.resolve()


def _source_data(source: Path):
    source = source.expanduser().resolve()
    if source.is_dir():
        if (source / "book.json").exists() and any((source / name).exists() for name in ("candidate.json", "assembled.json")):
            raise ValueError("여러 원고 형식이 있습니다. book.json 또는 candidate.json·assembled.json 파일을 직접 지정하세요")
        if (source / "assembled.json").is_file():
            source = source / "assembled.json"
        elif (source / "candidate.json").is_file():
            source = source / "candidate.json"
        elif (source / "book.json").exists():
            source = source / "book.json"
        else:
            raise ValueError("candidate.json·assembled.json·book.json이 있는 경로가 필요합니다")
    if source.name == "book.json":
        from .reading_human_review import source_data
        return source_data(source)
    if source.name not in {"candidate.json", "assembled.json"}:
        raise ValueError("candidate.json·assembled.json 또는 언어이해 book.json을 지정하세요")

    references = {}
    cache = {}

    def remember(path: Path):
        data = path.read_bytes()
        references[str(path)] = {"path": str(path), "sha256": _sha(data)}
        return data

    def load_run(run: Path):
        if run in cache:
            return cache[run]
        candidate = run / "candidate.json"
        brief_path = run / "brief.json"
        remember(candidate)
        remember(brief_path)
        brief_data = _read_json(brief_path)
        if brief_data.get("subject") == "언어이해":
            raise ValueError("언어이해는 candidate 형식이 아닌 book.json을 지정하세요")
        brief = _BriefScope.model_validate({key: brief_data.get(key) for key in ("exam", "subject", "count")})
        draft = Draft.model_validate(_read_json(candidate))
        if len({item.id for item in draft.items}) != len(draft.items):
            raise ValueError(f"문항 ID 중복: {run}")
        if any(not item.id.strip() or item.subject != brief.subject for item in draft.items):
            raise ValueError(f"브리프·문항 과목 또는 ID 불일치: {run}")
        if len(draft.items) != brief.count:
            raise ValueError(f"브리프·문항 수 불일치: {run}")
        status_path = run / "status.json"
        status = {}
        if status_path.exists():
            # Workflow state may change after another reviewer submits feedback.
            # Only candidate/brief bytes and the parent identity bind this packet.
            status = _read_json(status_path)
            if not isinstance(status, dict):
                raise ValueError(f"status 객체가 필요합니다: {run}")
        cache[run] = (draft, brief, status)
        return cache[run]

    remember(source)
    if source.name == "assembled.json":
        assembled = _read_json(source)
        if assembled.get("subject") == "언어이해":
            raise ValueError("언어이해 book은 팀 검토 패킷에서 아직 지원하지 않습니다")
        rows = assembled.get("items")
        if not isinstance(rows, list) or not rows:
            raise ValueError("assembled 문항 매핑이 없습니다")
    else:
        draft, _, state = load_run(source.parent)
        parent = state.get("parent_review_run", str(source.parent))
        rows = [{"number": number, "id": item.id, "run": str(source.parent),
                 "parent_run": parent} for number, item in enumerate(draft.items, 1)]
        assembled = {}

    numbers, ids, mappings, loaded_items = set(), set(), [], []
    routes = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("assembled 문항 매핑은 객체여야 합니다")
        number, item_id = row.get("number"), row.get("id")
        if type(number) is not int or number < 1 or not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("실제 문항 번호·ID가 필요합니다")
        if number in numbers or item_id in ids:
            raise ValueError("문항 번호 또는 ID 중복")
        numbers.add(number)
        ids.add(item_id)
        run = _resolve_run(row.get("run"), source.parent)
        parent = _resolve_run(row.get("parent_run"), source.parent)
        draft, brief, state = load_run(run)
        parent_draft, parent_brief, _ = load_run(parent)
        if (brief.exam, brief.subject) != (parent_brief.exam, parent_brief.subject):
            raise ValueError("편집 뷰·parent 브리프 시험·과목 불일치")
        if state.get("parent_review_run") and _resolve_run(state["parent_review_run"], run) != parent:
            raise ValueError("편집 뷰·assembled parent_run 불일치")
        selected = [item for item in draft.items if item.id == item_id]
        originals = [item for item in parent_draft.items if item.id == item_id]
        if len(selected) != 1 or len(originals) != 1:
            raise ValueError(f"편집 뷰·parent 문항 ID 매핑 불일치: {item_id}")
        item, original = selected[0], originals[0]
        if item.model_dump() != original.model_dump():
            raise ValueError(f"편집 뷰·parent 문항 내용 불일치: {item_id}")
        routes.add((brief.exam, brief.subject))
        mappings.append({"number": number, "item_id": item_id, "run": str(run),
                         "parent_run": str(parent), "item_sha256": _item_sha(item),
                         "candidate_sha256": references[str(run / "candidate.json")]["sha256"],
                         "parent_candidate_sha256": references[str(parent / "candidate.json")]["sha256"],
                         "parent_item_sha256": _item_sha(original),
                         "parent_item_content_matches": True})
        loaded_items.append(item)
    if len(routes) != 1:
        raise ValueError("한 패킷의 시험·과목은 같아야 합니다")
    exam, subject = next(iter(routes))
    if any(assembled.get(key, value) != value for key, value in (("exam", exam), ("subject", subject))):
        raise ValueError("assembled·브리프 시험·과목 불일치")
    # Printed numbers, not array position or a parsed ID, define review identity.
    pairs = sorted(zip(mappings, loaded_items), key=lambda pair: pair[0]["number"])
    return {"source": str(source), "exam": exam, "subject": subject,
            "source_files": sorted(references.values(), key=lambda ref: ref["path"]),
            "items": [pair[0] for pair in pairs]}, [pair[1] for pair in pairs]


def _check_sources(refs):
    for ref in refs:
        path = Path(ref["path"])
        if not path.is_file() or _sha(path.read_bytes()) != ref["sha256"]:
            raise ValueError(f"원본 source/parent 해시가 변경되었습니다: {path}")


def _public_item(number: int, item: Item):
    public = {key: item.model_dump()[key] for key in
              ("stem", "passage", "statements", "tables", "options")}
    # Diagram placement instructions and layout receipts are not printed text.
    public["figures"] = []
    for figure in item.figures:
        visible = figure.model_dump(exclude={"layout_note"})
        if figure.kind == "argument":
            visible["note"] = ""
        public["figures"].append(visible)
    return {"number": number, **public}


def _page(title, blocks):
    return ("<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title><style>"
            "body{font-family:serif;max-width:850px;margin:40px auto;line-height:1.8;color:#17212b}"
            "article{padding:24px 0;border-bottom:1px solid #bbb}h2{font-size:19px}"
            "table{border-collapse:collapse;width:100%}th,td{border:1px solid #777;padding:6px}"
            "aside{border:1px solid #aaa;padding:12px}li{padding:5px}img{max-width:100%}"
            "@media print{body{margin:0}}</style><body>"
            f"<header>{html.escape(title)}</header>{''.join(blocks)}</body></html>")


def _para(value):
    return "<p>" + html.escape(value).replace("\n", "<br>") + "</p>"


def _render(stage: Path, mappings, items):
    student = stage / "student"
    review = stage / "review"
    student.mkdir()
    review.mkdir()
    problems, solutions, public, keys = [], [], [], []
    for mapping, item in zip(mappings, items):
        number = mapping["number"]
        visible = _public_item(number, item)
        public.append(visible)
        paths = {}
        if item.figures:
            from .figures import render_item
            with tempfile.TemporaryDirectory(prefix="haean-review-figures-") as folder:
                # The renderer gets visible fields only, preventing private layout
                # instructions from being embedded in a public SVG or PNG.
                rendering_item = item.model_copy(update={"figures": [
                    figure.model_copy(update={"layout_note": "", "note": "" if figure.kind == "argument" else figure.note})
                    for figure in item.figures]})
                rendered = render_item(rendering_item, Path(folder))
                assets = student / "assets" / str(number)
                assets.mkdir(parents=True)
                for index, (figure_id, image) in enumerate(rendered.items(), 1):
                    for suffix in (".png", ".svg"):
                        target = assets / f"figure-{index:02d}{suffix}"
                        shutil.copyfile(image.with_suffix(suffix), target)
                    paths[figure_id] = f"assets/{number}/figure-{index:02d}.png"

        def figures(placement):
            return "".join(
                f'<figure><img src="{paths[figure.id]}" alt="{html.escape(figure.title)}">'
                f'<figcaption>{html.escape(figure.note if figure.kind != "argument" else "")}</figcaption></figure>'
                for figure in item.figures if figure.placement == placement)

        block = f"<article><h2>{number}. {html.escape(item.stem)}</h2>" + _para(item.passage)
        block += figures("passage")
        for table in item.tables:
            block += f"<h3>{html.escape(table.title)} ({html.escape(table.unit)})</h3><table><thead><tr>"
            block += "".join(f"<th>{html.escape(column)}</th>" for column in table.columns)
            block += "</tr></thead><tbody>"
            block += "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in table.rows)
            block += "</tbody></table>" + _para(table.note)
        if item.statements:
            block += "<aside>" + _para("\n".join(item.statements)) + "</aside>"
        block += figures("statements")
        block += "<ol>" + "".join(f"<li>{html.escape(option.text)}{figures('option_' + str(option.number))}</li>" for option in item.options)
        problems.append(block + "</ol></article>")
        solutions.append(f"<article><h2>{number}. 정답 {item.answer}</h2>" + _para(item.explanation)
                         + "<ul>" + "".join(f"<li>{html.escape(j.target)}: {html.escape(j.verdict)} — {html.escape(j.explanation)}</li>" for j in item.judgments)
                         + "</ul>" + _para(item.commentary) + "</article>")
        keys.append({"number": number, "item_id": item.id, "answer": item.answer,
                     "explanation": item.explanation, "commentary": item.commentary,
                     "judgments": [judgment.model_dump() for judgment in item.judgments]})
    (student / "questions.html").write_text(_page("해안 · 검토용 초안 · 학생용 문제", problems), encoding="utf-8")
    _write_json(student / "questions.json", {"items": public})
    (review / "solutions.html").write_text(_page("해안 · 검토자용 정답·해설", solutions), encoding="utf-8")
    _write_json(review / "solutions.json", {"items": keys})


_INSTRUCTIONS = """# 팀 검토 패킷

학생에게는 student 폴더만 전달합니다. questions.html과 assets를 함께 보관하세요.
review/solutions.html은 정답·해설입니다. 독립 풀이를 마친 뒤 열어보세요.
review/response.json을 복사해 작성하고 원본 패킷과 함께 수집 명령에 전달합니다.

- reviewer와 origin(human 또는 model)은 반드시 직접 입력합니다. 모델 응답을 human으로 표시하지 않습니다.
- number와 item_id를 함께 유지합니다. 순서는 바꿀 수 있고 일부 문항만 제출해도 됩니다.
- completed는 해당 문항의 검토 완료 여부이며 승인 여부가 아닙니다.
- prior_answer_seen은 풀기 전에 정답·해설을 보았는지 기록합니다. 모르면 null입니다.
- answer는 1–5 또는 null, solve_seconds와 edit_seconds는 실제 기록한 초 또는 null입니다.
- option_reasoning은 선택지 번호 1–5를 키로 갖는 근거입니다. 필요한 선택지만 적을 수 있습니다.
- issues는 A/B/C 등급과 location, quote(실제 인용), problem, proposed_fix를 적습니다.
- 미기입은 null로 남깁니다. 0초나 이상 없음으로 바꾸지 않습니다. []는 검토자가 명시한 빈 의견 목록입니다.

수집은 부모 run 및 후보 해시에 검토 원문을 연결합니다. 부모 상태·checkpoint·feedback은 자동 변경하지 않습니다.
의견의 적용·재검토는 별도 작업입니다. completed만으로 전문가 확인·승인·실측 난도 인증이 되지 않습니다.
HTML과 구조화된 그림을 출력했으며 HWP 편집·렌더나 사람의 시각 검증을 뜻하지 않습니다.
"""


def create_packet(source: Path, out: Path) -> dict:
    """Export a new packet; reject an existing destination or divergent view."""
    out = Path(out).expanduser().resolve()
    if out.exists():
        raise ValueError(f"새 출력 폴더가 필요합니다: {out}")
    binding, items = _source_data(Path(source))
    with tempfile.TemporaryDirectory(prefix="haean-review-packet-") as folder:
        stage = Path(folder)
        reading = binding.get("source_format") == "leet_reading_book"
        if reading:
            from .reading_human_review import render
            render(stage, binding, items)
        else:
            _render(stage, binding["items"], items)
        _write_json(stage / "review" / "response.schema.json", ReviewResponse.model_json_schema())
        instructions = _INSTRUCTIONS
        if reading:
            instructions = instructions.replace(
                "수집은 부모 run 및 후보 해시에 검토 원문을 연결합니다. 부모 상태·checkpoint·feedback은 자동 변경하지 않습니다.",
                "수집은 book 해시·공통지문·문항 위치에 검토 원문을 연결합니다. item_id는 이 book 버전의 검토용 식별자이며 원본의 안정 ID가 아닙니다.\n"
                "공통지문 의견은 location에 지문 범위를 적습니다. 지문을 수정하면 연결된 모든 문항을 재검토합니다. 원본·checkpoint·feedback은 자동 변경하지 않습니다.")
            instructions = instructions.replace("HTML과 구조화된 그림을 출력했으며", "텍스트형 언어이해 HTML을 출력했으며")
        (stage / "README.md").write_text(instructions, encoding="utf-8")
        files = [{"path": str(path.relative_to(stage)), "sha256": _sha(path.read_bytes())}
                 for path in sorted(stage.rglob("*")) if path.is_file()]
        manifest = {"version": 1, "kind": "team_review_packet", **binding, "files": files,
                    "human_approved": False, "expert_verified": False,
                    "difficulty_validated": False, "layout_verified": False}
        _write_json(stage / "manifest.json", manifest)
        manifest_sha = _sha((stage / "manifest.json").read_bytes())
        (stage / "manifest.sha256").write_text(manifest_sha + "\n", encoding="utf-8")
        template = {"manifest_sha256": manifest_sha, "reviewer": "", "origin": None,
                    "items": [{"number": row["number"], "item_id": row["item_id"], "completed": False,
                               "prior_answer_seen": None, "answer": None, "solve_seconds": None,
                               "option_reasoning": None, "issues": None, "edit_seconds": None}
                              for row in binding["items"]]}
        _write_json(stage / "review" / "response.json", template)
        _check_sources(binding["source_files"])
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, out)
    return {"packet": str(out), "manifest": str(out / "manifest.json"),
            "manifest_sha256": manifest_sha, "student": str(out / "student" / "questions.html"),
            "solutions": str(out / "review" / "solutions.html"),
            "response": str(out / "review" / "response.json"),
            "schema": str(out / "review" / "response.schema.json"), "items": len(binding["items"])}


def _packet_manifest(packet: Path):
    manifest_bytes = (packet / "manifest.json").read_bytes()
    manifest_sha = _sha(manifest_bytes)
    if (packet / "manifest.sha256").read_text(encoding="utf-8").strip() != manifest_sha:
        raise ValueError("패킷 manifest 해시 불일치")
    manifest = _read_json(packet / "manifest.json")
    if manifest.get("version") != 1 or manifest.get("kind") != "team_review_packet":
        raise ValueError("지원하지 않는 검토 패킷")
    _check_sources(manifest["source_files"])
    binding, _ = _source_data(Path(manifest["source"]))
    if (manifest.get("source_format") != binding.get("source_format")
            or any(manifest.get(key) != value for key, value in binding.items())):
        raise ValueError("패킷의 번호·ID·parent 내용 결속 불일치")
    expected_student = set()
    seen = set()
    for ref in manifest["files"]:
        relative = ref["path"]
        path = (packet / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(packet) or relative in seen:
            raise ValueError("패킷 파일 경로 불일치")
        seen.add(relative)
        if not path.is_file() or _sha(path.read_bytes()) != ref["sha256"]:
            raise ValueError(f"패킷 학생·해설·스키마 파일 해시 불일치: {relative}")
        if relative.startswith("student/"):
            expected_student.add(relative)
    actual_student = {str(path.relative_to(packet)) for path in (packet / "student").rglob("*") if path.is_file()}
    if actual_student != expected_student:
        raise ValueError("학생 폴더 파일 목록이 변경되었습니다")
    return manifest, manifest_sha


def _digest(response: ReviewResponse, receipt: dict) -> str:
    reading = receipt.get("source_format") == "leet_reading_book"
    lines = ["# 수집한 팀 검토", "", f"검토자: {response.reviewer}", f"출처: {response.origin}",
             f"완료 표기: {receipt['completed_items']} / 제출 {len(response.items)}문항", "",
             "미기입은 미기입으로 보존합니다. 아래 기록은 승인·전문가 확인·실측 난도 인증이 아닙니다.",
             ("book 버전에 연결한 의견을 실제 문항에 적용하고, 지문 변경 시 연결된 모든 문항을 재검토해야 합니다." if reading else
              "부모 후보에 연결한 의견을 실제 문항에 적용하고 재검토하는 작업이 남아 있습니다."), ""]
    for item, link in zip(response.items, receipt["items"]):
        lines.extend([f"## {item.number}번 · {item.item_id}", ""])
        if reading:
            lines.extend([f"book_path: {link['book_path']}", f"book_sha256: {link['book_sha256']}",
                          f"passage_id: {link['passage_id']}", f"question_locator: {link['question_locator']}",
                          "identity_scope: book_version (이 버전의 검토용 식별자)"])
        else:
            lines.extend([f"parent_run: {link['parent_run']}", f"parent_candidate_sha256: {link['parent_candidate_sha256']}"])
        lines.extend([
                      f"완료: {item.completed}; 사전 정답 열람: {item.prior_answer_seen}; 선택 답: {item.answer}",
                      f"풀이 초: {item.solve_seconds}; 수정 초: {item.edit_seconds}", ""])
        if item.option_reasoning is not None:
            lines.extend(f"- {number}번 선택지: {reason}" for number, reason in item.option_reasoning.items())
        if item.issues is None:
            lines.append("검토 의견: 미기입")
        elif not item.issues:
            lines.append("검토 의견: 검토자가 빈 목록을 제출함")
        else:
            for issue in item.issues:
                lines.extend([f"- [{issue.severity}] {issue.location}", f"  인용: {issue.quote}",
                              f"  문제: {issue.problem}", f"  수정 제안: {issue.proposed_fix}"])
        lines.append("")
    return "\n".join(lines)


def collect_packet(packet: Path, response: Path, out: Path | None = None) -> dict:
    """Collect immutable submission evidence. ``out`` overrides collections root.

    All source, render, schema, response and mapping checks precede any writes.
    Identical response bytes reuse their SHA-256-named collection directory.
    """
    packet = Path(packet).expanduser().resolve()
    if packet.name == "manifest.json":
        packet = packet.parent
    manifest, manifest_sha = _packet_manifest(packet)
    response_path = Path(response).expanduser().resolve()
    response_bytes = response_path.read_bytes()
    data = json.loads(response_bytes, parse_constant=_reject_constant, object_pairs_hook=_unique_keys)
    submission = ReviewResponse.model_validate(data)
    if submission.manifest_sha256 != manifest_sha:
        raise ValueError("응답과 패킷 manifest 해시가 다릅니다")
    by_number = {row["number"]: row for row in manifest["items"]}
    seen_numbers, seen_ids = set(), set()
    linked = []
    for item in submission.items:
        if item.number in seen_numbers or item.item_id in seen_ids:
            raise ValueError("검토 응답 문항 번호 또는 ID 중복")
        seen_numbers.add(item.number)
        seen_ids.add(item.item_id)
        mapping = by_number.get(item.number)
        if mapping is None or mapping["item_id"] != item.item_id:
            raise ValueError("검토 응답 문항 번호·ID가 패킷과 다릅니다")
        linked.append({**mapping, **item.model_dump(), "feedback_application_required": True})
    response_sha = _sha(response_bytes)
    root = Path(out).expanduser().resolve() if out is not None else packet / "collections"
    if root == packet or root.is_relative_to(packet / "student") or root.is_relative_to(packet / "review"):
        raise ValueError("수집 폴더는 student·review와 분리해야 합니다")
    destination = root / response_sha
    receipt = {"version": 1, "kind": "submitted_team_review", "created_at": datetime.now(timezone.utc).isoformat(),
               "packet": str(packet), "manifest_sha256": manifest_sha, "response_sha256": response_sha,
               "reviewer": submission.reviewer, "origin": submission.origin,
               "submitted_items": len(submission.items),
               "completed_items": sum(item.completed for item in submission.items),
               "missing_item_ids": [row["item_id"] for row in manifest["items"] if row["item_id"] not in seen_ids],
               "partial": len(submission.items) < len(manifest["items"]) or not all(item.completed for item in submission.items),
               "items": linked, "human_approved": False, "expert_verified": False,
               "difficulty_validated": False, "feedback_application_required": True,
               "next": "parent run·후보 해시에 연결된 의견입니다. feedback 적용과 수정·재검토가 별도로 필요합니다. 부모 상태는 바꾸지 않았습니다."}
    if manifest.get("source_format") == "leet_reading_book":
        receipt["source_format"] = "leet_reading_book"
        receipt["next"] = "book 해시·지문·문항 위치에 연결된 의견입니다. 원본은 바꾸지 않았으며 수정·독립 재검토가 필요합니다. 기존 candidate용 feedback/human-checkpoint에 언어이해를 넣지 않습니다."
    digest = _digest(submission, receipt).encode("utf-8")
    receipt["digest_sha256"] = _sha(digest)
    if destination.exists():
        receipt_path = destination / "receipt.json"
        previous = _read_json(receipt_path)
        # Rebuild every semantic field from the preserved response and current
        # verified binding. A receipt cannot promote model input to human input.
        expected = {key: value for key, value in receipt.items() if key != "created_at"}
        recorded = {key: value for key, value in previous.items() if key != "created_at"}
        if ((destination / "response.json").read_bytes() != response_bytes
                or recorded != expected
                or not isinstance(previous.get("created_at"), str)
                or (destination / "digest.md").read_bytes() != digest):
            raise ValueError("기존 수집 기록이 변경되었습니다")
        return {"collection": str(destination), "receipt": str(receipt_path), "duplicate": True,
                "response_sha256": response_sha, "origin": submission.origin,
                "completed_items": receipt["completed_items"], "feedback_application_required": True}
    # Recheck the source after parsing the submission, before creating output.
    _check_sources(manifest["source_files"])
    with tempfile.TemporaryDirectory(prefix="haean-review-collection-") as folder:
        stage = Path(folder)
        (stage / "response.json").write_bytes(response_bytes)
        (stage / "digest.md").write_bytes(digest)
        _write_json(stage / "receipt.json", receipt)
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, destination)
    return {"collection": str(destination), "receipt": str(destination / "receipt.json"),
            "duplicate": False, "response_sha256": response_sha, "origin": submission.origin,
            "completed_items": receipt["completed_items"], "feedback_application_required": True}
