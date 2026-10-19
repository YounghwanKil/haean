"""Text-only LEET reading books in immutable team-review packets.

The book is the source of truth. Packet IDs identify a JSON locator in one
hashed book version; they are not original authoring IDs or parent-run IDs.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re

from .human_review import _page, _para, _reject_constant, _sha, _unique_keys, _write_json


SOURCE_FORMAT = "leet_reading_book"
_BOOK_FIELDS = {"title", "minutes", "human_approved", "passages", "sources"}
_PASSAGE_FIELDS = {"id", "title", "domain", "paragraphs", "sources", "questions", "source_domain"}
_QUESTION_FIELDS = {
    "id", "number", "stem", "box", "options", "answer", "cognitive_task", "difficulty",
    "explanation", "option_explanations", "strongest_counterreading",
}
_UNDERLINE_TAG = re.compile(r"<\s*/?\s*u(?=[\s>/]|$)[^>]*(?:>|$)", re.IGNORECASE)


def _validate_underline(value, location):
    """Only exact, balanced, nonnested <u> spans carry authored formatting."""
    start = None
    for match in _UNDERLINE_TAG.finditer(value):
        tag = match.group()
        if tag == "<u>" and start is None:
            start = match.end()
        elif tag == "</u>" and start is not None and value[start:match.start()].strip():
            start = None
        else:
            raise ValueError(f"언어이해 book의 {location}에 잘못된 밑줄 마크업이 있습니다")
    if start is not None:
        raise ValueError(f"언어이해 book의 {location}에 닫히지 않은 밑줄 마크업이 있습니다")


def _inline(value):
    # Source validation permits only exact <u> and </u> tags. Everything else,
    # including script/img markup and angle-bracketed Korean labels, is text.
    return "".join(part if part in {"<u>", "</u>"} else html.escape(part)
                   for part in re.split(r"(<u>|</u>)", value)).replace("\n", "<br>")


def _paragraph(value):
    return "<p>" + _inline(value) + "</p>"


def _object(value, allowed, location):
    if not isinstance(value, dict):
        raise ValueError(f"언어이해 book의 {location}은 객체여야 합니다")
    extra = set(value) - allowed
    if extra:
        # Unknown display fields must never silently disappear from a packet.
        raise ValueError(f"언어이해 book의 {location}에 지원하지 않는 필드: {', '.join(sorted(extra))}")
    return value


def _text(value, location, *, blank=False, inline=False):
    if not isinstance(value, str) or (not blank and not value.strip()):
        raise ValueError(f"언어이해 book의 {location}은 {'문자열' if blank else '비어 있지 않은 문자열'}이어야 합니다")
    if inline:
        _validate_underline(value, location)
    return value


def _texts(value, location, *, count=None):
    if not isinstance(value, list) or not value or (count is not None and len(value) != count):
        expected = f"{count}개의 문자열" if count is not None else "하나 이상의 문자열"
        raise ValueError(f"언어이해 book의 {location}에는 {expected} 목록이 필요합니다")
    for index, text in enumerate(value):
        _text(text, f"{location}/{index}", inline=True)
    return value


def _metadata(value, string_fields, location):
    for key in string_fields:
        if key in value:
            _text(value[key], f"{location}/{key}", blank=True)
    if "sources" in value:
        sources = value["sources"]
        if not isinstance(sources, list) or any(not isinstance(entry, (str, dict)) for entry in sources):
            raise ValueError(f"언어이해 book의 {location}/sources는 문자열 또는 객체의 목록이어야 합니다")


def source_data(book_path: Path):
    """Read and validate one immutable book snapshot, retaining source locators."""
    source = Path(book_path).expanduser().resolve()
    raw = source.read_bytes()
    book_sha = _sha(raw)
    book = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_keys)
    _object(book, _BOOK_FIELDS, "root")
    _metadata(book, ("title",), "root")
    if "minutes" in book and (type(book["minutes"]) is not int or book["minutes"] < 1):
        raise ValueError("언어이해 book의 minutes는 양의 정수여야 합니다")
    if "human_approved" in book and type(book["human_approved"]) is not bool:
        raise ValueError("언어이해 book의 human_approved는 불리언이어야 합니다")
    passages = book.get("passages")
    if not isinstance(passages, list) or not passages:
        raise ValueError("언어이해 book에는 하나 이상의 passages가 필요합니다")

    passage_ids, question_ids, numbers = set(), set(), set()
    paired = []
    for passage_index, passage in enumerate(passages):
        passage_locator = f"/passages/{passage_index}"
        _object(passage, _PASSAGE_FIELDS, passage_locator)
        passage_id = _text(passage.get("id"), f"{passage_locator}/id")
        if passage_id.strip() in passage_ids:
            raise ValueError("언어이해 book의 지문 ID 중복")
        passage_ids.add(passage_id.strip())
        _metadata(passage, ("title", "domain", "source_domain"), passage_locator)
        paragraphs = _texts(passage.get("paragraphs"), f"{passage_locator}/paragraphs")
        questions = passage.get("questions")
        if not isinstance(questions, list) or len(questions) != 3:
            raise ValueError(f"언어이해 book의 {passage_locator}에는 정확히 3개 questions가 필요합니다")
        for question_index, question in enumerate(questions):
            question_locator = f"{passage_locator}/questions/{question_index}"
            _object(question, _QUESTION_FIELDS, question_locator)
            number = question.get("number")
            if type(number) is not int or number < 1:
                raise ValueError(f"언어이해 book의 {question_locator}/number는 1 이상의 정수여야 합니다")
            if number in numbers:
                raise ValueError("언어이해 book의 문항 번호 중복")
            numbers.add(number)
            if type(question.get("answer")) is not int or not 1 <= question["answer"] <= 5:
                raise ValueError(f"언어이해 book의 {question_locator}/answer는 1~5 정수여야 합니다")
            for field in ("stem", "explanation"):
                _text(question.get(field), f"{question_locator}/{field}", inline=True)
            if "box" in question:
                _text(question["box"], f"{question_locator}/box", blank=True, inline=True)
            options = _texts(question.get("options"), f"{question_locator}/options", count=5)
            if len({option.strip() for option in options}) != 5:
                raise ValueError(f"언어이해 book의 {question_locator}/options에 중복 선택지가 있습니다")
            _texts(question.get("option_explanations"), f"{question_locator}/option_explanations", count=5)
            _metadata(question, ("cognitive_task", "difficulty", "strongest_counterreading"), question_locator)
            if "strongest_counterreading" in question:
                _validate_underline(question["strongest_counterreading"], f"{question_locator}/strongest_counterreading")
            mapping = {
                "number": number,
                "item_id": f"reading:{book_sha}:p{passage_index}:q{question_index}",
                "source_format": SOURCE_FORMAT,
                "book_path": str(source),
                "book_sha256": book_sha,
                "passage_id": passage_id,
                "passage_locator": passage_locator,
                "question_locator": question_locator,
                "identity_scope": "book_version",
            }
            if "id" in question:
                question_id = _text(question["id"], f"{question_locator}/id")
                if question_id.strip() in question_ids:
                    raise ValueError("언어이해 book의 원본 문항 ID 중복")
                question_ids.add(question_id.strip())
                mapping["source_question_id"] = question_id
            paired.append((mapping, {"passage_index": passage_index, "paragraphs": paragraphs,
                                     "question": question}))
    if [mapping["number"] for mapping, _ in paired] != list(range(1, len(paired) + 1)):
        raise ValueError("언어이해 book의 문항 번호는 지문·문항 순서대로 1부터 전체 문항 수까지 이어져야 합니다")
    binding = {"source": str(source), "source_format": SOURCE_FORMAT, "exam": "leet", "subject": "언어이해",
               "source_files": [{"path": str(source), "sha256": book_sha}],
               "items": [mapping for mapping, _ in paired]}
    return binding, [entry for _, entry in paired]


def render(stage: Path, binding, flat_entries):
    """Render shared passages once; construct student output from a whitelist."""
    student, review = stage / "student", stage / "review"
    student.mkdir()
    review.mkdir()
    groups, solutions, keys = {}, [], []
    for mapping, entry in zip(binding["items"], flat_entries, strict=True):
        question = entry["question"]
        number = mapping["number"]
        group = groups.setdefault(entry["passage_index"], {
            "range": [number, number], "paragraphs": entry["paragraphs"], "questions": [],
        })
        group["range"][1] = number
        group["questions"].append({"number": number, "stem": question["stem"],
                                   "box": question.get("box", ""), "options": question["options"]})
        key = {"number": number, "item_id": mapping["item_id"], "answer": question["answer"],
               "explanation": question["explanation"], "option_explanations": question["option_explanations"],
               "strongest_counterreading": question.get("strongest_counterreading", "")}
        keys.append(key)
        solutions.append(
            f'<article><h2>{number}. 정답 {key["answer"]}</h2>'
            + _para(f'패킷 문항 ID: {key["item_id"]}') + _paragraph(key["explanation"])
            + "<ol>" + "".join(f"<li>{_inline(reason)}</li>" for reason in key["option_explanations"])
            + "</ol><h3>가장 강한 반대 해석</h3>" + _paragraph(key["strongest_counterreading"]) + "</article>"
        )
    problems = []
    for group in groups.values():
        first, last = group["range"]
        label = f"{first}～{last}"
        block = f"<section><h2>[{label}] 다음 글을 읽고 물음에 답하시오.</h2>"
        block += "".join(_paragraph(paragraph) for paragraph in group["paragraphs"])
        for question in group["questions"]:
            block += f'<article><h2>{question["number"]}. {_inline(question["stem"])}</h2>'
            if question["box"]:
                block += "<aside>" + _paragraph(question["box"]) + "</aside>"
            block += "<ol>" + "".join(f"<li>{_inline(option)}</li>" for option in question["options"])
            block += "</ol></article>"
        problems.append(block + "</section>")
    (student / "questions.html").write_text(_page("해안 · 검토용 초안 · 학생용 문제", problems), encoding="utf-8")
    _write_json(student / "questions.json", {"passages": list(groups.values())})
    (review / "solutions.html").write_text(_page("해안 · 검토자용 정답·해설", solutions), encoding="utf-8")
    _write_json(review / "solutions.json", {"items": keys})
