"""Synthetic reading books only; these checks do not certify exam quality."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from haean.human_review import collect_packet, create_packet
from haean.reading_human_review import source_data


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read(path):
    return json.loads(path.read_bytes())


def synthetic_book(count=2):
    passages = []
    for index in range(count):
        questions = []
        for offset in range(3):
            number = index * 3 + offset + 1
            questions.append({
                "number": number, "stem": f"합성 발문 {number} <em>보존</em>",
                "box": f"합성 보기 {number}\n<script>보기</script>",
                "options": [f"합성 {number}번 선택지 {choice} <b>&</b>" for choice in range(1, 6)],
                "answer": number % 5 + 1,
                "cognitive_task": f"PRIVATE_COGNITION_{number}", "difficulty": "PRIVATE_DIFFICULTY",
                "explanation": f"PRIVATE_EXPLANATION_{number} <script>해설</script>",
                "option_explanations": [f"PRIVATE_OPTION_{number}_{choice}" for choice in range(1, 6)],
                "strongest_counterreading": f"PRIVATE_COUNTERREADING_{number}",
            })
        passages.append({
            "id": f"PRIVATE_PASSAGE_ID_{index}", "title": f"PRIVATE_PASSAGE_TITLE_{index}",
            "domain": "PRIVATE_DOMAIN", "source_domain": "PRIVATE_SOURCE_DOMAIN",
            "paragraphs": [f"합성 공통지문 {index} 첫째 문단 <img src=x>", f"합성 공통지문 {index} 둘째 문단"],
            "sources": [{"title": "PRIVATE_SOURCE_TITLE", "url": "PRIVATE_SOURCE_URL",
                         "verified_scope": "PRIVATE_SOURCE_SCOPE"}],
            "questions": questions,
        })
    return {"title": "PRIVATE_BOOK_TITLE", "minutes": 70, "human_approved": True,
            "passages": passages, "sources": [{"part": "PRIVATE_PART", "sha256": "PRIVATE_SOURCE_SHA"}]}


@pytest.fixture
def book_path(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "book.json"
    write(path, synthetic_book())
    return path


def response_file(packet, tmp_path, *, origin="model"):
    data = read(packet / "review" / "response.json")
    data.update(reviewer="합성 검토자", origin=origin)
    path = tmp_path / "submitted.json"
    write(path, data)
    return path


def test_shared_passages_whitelist_escaping_and_separate_solutions(tmp_path, book_path):
    original = book_path.read_bytes()
    book = read(book_path)
    packet = tmp_path / "packet"
    result = create_packet(book_path.parent, packet)
    assert result["items"] == 6
    assert book_path.read_bytes() == original
    public = read(packet / "student" / "questions.json")
    assert set(public) == {"passages"}
    assert len(public["passages"]) == 2
    student_html = (packet / "student" / "questions.html").read_text()
    for index, passage in enumerate(public["passages"]):
        assert set(passage) == {"range", "paragraphs", "questions"}
        assert passage["range"] == [index * 3 + 1, index * 3 + 3]
        assert passage["paragraphs"] == book["passages"][index]["paragraphs"]
        assert student_html.count(f"합성 공통지문 {index} 첫째 문단") == 1
        assert f"[{index * 3 + 1}～{index * 3 + 3}]" in student_html
        for actual, expected in zip(passage["questions"], book["passages"][index]["questions"]):
            assert set(actual) == {"number", "stem", "box", "options"}
            assert actual == {key: expected[key] for key in actual}
    student_text = "\n".join(path.read_text() for path in (packet / "student").iterdir())
    assert "PRIVATE_" not in student_text
    assert str(book_path) not in student_text
    for key in ("item_id", "source_format", "passage_id", "answer", "explanation", "title", "domain", "sources"):
        assert f'"{key}"' not in student_text
    assert "<script>" not in student_html and "<em>보존</em>" not in student_html
    assert "&lt;script&gt;보기&lt;/script&gt;" in student_html
    assert "&lt;img src=x&gt;" in student_html
    solutions = read(packet / "review" / "solutions.json")["items"]
    mapping = read(packet / "manifest.json")["items"]
    original_questions = [question for passage in book["passages"] for question in passage["questions"]]
    for solution, expected, item in zip(solutions, original_questions, mapping):
        assert solution["number"] == expected["number"]
        assert solution["item_id"] == item["item_id"]
        for key in ("answer", "explanation", "option_explanations", "strongest_counterreading"):
            assert solution[key] == expected[key]
    review_html = (packet / "review" / "solutions.html").read_text()
    assert "PRIVATE_EXPLANATION_1" in review_html and "PRIVATE_COUNTERREADING_1" in review_html
    assert "<script>" not in review_html


def test_mapping_binds_whole_original_bytes_locators_and_packet_only_ids(tmp_path, book_path):
    data = read(book_path)
    data["passages"][0]["questions"][0]["id"] = "PRIVATE_ORIGINAL_ID"
    write(book_path, data)
    binding, entries = source_data(book_path)
    repeated, _ = source_data(book_path)
    assert binding == repeated
    assert len(entries) == 6
    sha = hashlib.sha256(book_path.read_bytes()).hexdigest()
    assert binding["source"] == str(book_path.resolve())
    assert binding["source_format"] == "leet_reading_book"
    assert (binding["exam"], binding["subject"]) == ("leet", "언어이해")
    assert binding["source_files"] == [{"path": str(book_path.resolve()), "sha256": sha}]
    for index, mapping in enumerate(binding["items"]):
        passage_index, question_index = divmod(index, 3)
        assert mapping["number"] == index + 1
        assert mapping["book_path"] == str(book_path.resolve())
        assert mapping["book_sha256"] == sha
        assert mapping["passage_id"] == data["passages"][passage_index]["id"]
        assert mapping["passage_locator"] == f"/passages/{passage_index}"
        assert mapping["question_locator"] == f"/passages/{passage_index}/questions/{question_index}"
        assert mapping["item_id"] == f"reading:{sha}:p{passage_index}:q{question_index}"
        assert mapping["identity_scope"] == "book_version"
        assert not {"run", "parent_run", "candidate_sha256", "parent_candidate_sha256"} & set(mapping)
    assert binding["items"][0]["source_question_id"] == "PRIVATE_ORIGINAL_ID"
    assert all("source_question_id" not in row for row in binding["items"][1:])
    # Even whitespace-only byte changes create a different book version.
    book_path.write_bytes(book_path.read_bytes() + b"\n")
    changed, _ = source_data(book_path)
    assert all(old["item_id"] != new["item_id"] for old, new in zip(binding["items"], changed["items"]))


def test_book_snapshot_is_read_once_and_parsed_once(book_path, monkeypatch):
    import haean.reading_human_review as adapter

    reads, parses = [], []
    original_read, original_loads = Path.read_bytes, json.loads

    def counted_read(path):
        reads.append(path)
        return original_read(path)

    def counted_parse(raw, **kwargs):
        parses.append(raw)
        return original_loads(raw, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    monkeypatch.setattr(adapter.json, "loads", counted_parse)
    source_data(book_path)
    assert reads == [book_path.resolve()]
    assert len(parses) == 1


@pytest.mark.parametrize("passage_count", [1, 3, 10])
def test_pilot_and_full_length_synthetic_books(tmp_path, passage_count):
    path = tmp_path / "book.json"
    write(path, synthetic_book(passage_count))
    packet = tmp_path / "packet"
    assert create_packet(path, packet)["items"] == passage_count * 3
    assert len(read(packet / "student" / "questions.json")["passages"]) == passage_count


def test_optional_metadata_and_box_can_be_absent(tmp_path):
    data = synthetic_book(1)
    passage = data["passages"][0]
    for key in ("title", "domain", "source_domain", "sources"):
        passage.pop(key)
    for question in passage["questions"]:
        for key in ("box", "cognitive_task", "difficulty", "strongest_counterreading"):
            question.pop(key)
    path = tmp_path / "book.json"
    write(path, {"passages": [passage]})
    packet = tmp_path / "packet"
    create_packet(path, packet)
    assert read(packet / "student" / "questions.json")["passages"][0]["questions"][0]["box"] == ""


def test_underline_criterion_preserved_with_other_html_escaped(tmp_path, book_path):
    data = read(book_path)
    passage = data["passages"][0]
    passage["paragraphs"][0] = "첫째 <u>판단 기준</u>과 <u>둘째 기준</u>. <script>alert(1)</script>"
    question = passage["questions"][0]
    question["stem"] = "<u>밑줄 친 부분</u>의 의미로 알맞은 것은?"
    question["box"] = "<보기>\n<u>합성 사례</u> <img src=x onerror=alert(1)>"
    question["options"][0] = "<u>선택지 문구</u> <a href='javascript:alert(1)'>연결</a>"
    question["explanation"] = "<u>근거</u> <script>실행 금지</script>"
    question["option_explanations"][0] = "<u>첫 선택지 판단</u>"
    question["strongest_counterreading"] = "<u>반대 해석</u>"
    write(book_path, data)
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    public = read(packet / "student" / "questions.json")["passages"][0]
    assert public["paragraphs"] == passage["paragraphs"]
    assert public["questions"][0]["stem"] == question["stem"]
    student_html = (packet / "student" / "questions.html").read_text()
    for text in ("판단 기준", "둘째 기준", "밑줄 친 부분", "합성 사례", "선택지 문구"):
        assert f"<u>{text}</u>" in student_html
    assert "&lt;보기&gt;<br>" in student_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in student_html
    assert "<script>" not in student_html and "<img " not in student_html and "<a " not in student_html
    review_html = (packet / "review" / "solutions.html").read_text()
    assert "<u>근거</u>" in review_html and "<u>첫 선택지 판단</u>" in review_html
    assert "<u>반대 해석</u>" in review_html and "<script>" not in review_html


@pytest.mark.parametrize("value", [
    "<u>닫힘 누락", "닫힘 먼저</u>", "<u>중첩<u>부분</u></u>", "<u></u>", "<u> \n </u>",
    "<u class='x'>속성</u>", "<u onclick='alert(1)'>속성</u>", "<U>대문자</U>",
    "<u >공백</u>", "<u/>", "<u", "<u>잘못된 닫힘</ u>",
])
def test_invalid_or_attributed_underline_rejected_before_output(tmp_path, book_path, value):
    data = read(book_path)
    data["passages"][0]["paragraphs"][0] = value
    write(book_path, data)
    with pytest.raises(ValueError, match="밑줄 마크업"):
        create_packet(book_path, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("field", ["stem", "box", "options", "explanation", "option_explanations", "strongest_counterreading"])
def test_question_and_solution_underline_validation_covers_all_rendered_fields(tmp_path, book_path, field):
    data = read(book_path)
    question = data["passages"][0]["questions"][0]
    if isinstance(question[field], list):
        question[field][0] = "<u>닫힘 없음"
    else:
        question[field] = "<u>닫힘 없음"
    write(book_path, data)
    with pytest.raises(ValueError, match="밑줄 마크업"):
        create_packet(book_path, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("location,value", [
    (("passages",), []), (("passages",), {}),
    (("passages", 0, "id"), "  "), (("passages", 0, "id"), 1),
    (("passages", 0, "paragraphs"), []), (("passages", 0, "paragraphs"), [""]),
    (("passages", 0, "paragraphs"), [None]),
    (("passages", 0, "questions"), []),
    (("passages", 0, "questions", 0, "number"), True),
    (("passages", 0, "questions", 0, "number"), "1"),
    (("passages", 0, "questions", 0, "number"), 0),
    (("passages", 0, "questions", 0, "number"), 7),
    (("passages", 0, "questions", 0, "answer"), True),
    (("passages", 0, "questions", 0, "answer"), "1"),
    (("passages", 0, "questions", 0, "answer"), 0),
    (("passages", 0, "questions", 0, "answer"), 6),
    (("passages", 0, "questions", 0, "stem"), " \n"),
    (("passages", 0, "questions", 0, "explanation"), None),
    (("passages", 0, "questions", 0, "box"), []),
    (("passages", 0, "questions", 0, "options"), ["1", "2", "3", "4"]),
    (("passages", 0, "questions", 0, "options"), ["1", "2", "3", "4", ""]),
    (("passages", 0, "questions", 0, "options"), ["1", "2", "3", "4", " 1 "]),
    (("passages", 0, "questions", 0, "option_explanations"), ["a"] * 4),
    (("passages", 0, "questions", 0, "option_explanations"), ["a", "b", "c", "d", " "]),
    (("passages", 0, "questions", 0, "id"), ""),
    (("passages", 0, "questions", 0, "strongest_counterreading"), []),
    (("minutes",), True), (("human_approved",), "true"), (("sources",), "source"),
])
def test_malformed_textual_book_rejected_before_output(tmp_path, book_path, location, value):
    data = read(book_path)
    target = data
    for component in location[:-1]:
        target = target[component]
    target[location[-1]] = value
    write(book_path, data)
    packet = tmp_path / "packet"
    with pytest.raises(ValueError, match="언어이해 book"):
        create_packet(book_path, packet)
    assert not packet.exists()


@pytest.mark.parametrize("kind", ["passage_id", "question_id", "number", "order"])
def test_duplicate_identity_and_out_of_order_numbers_rejected(tmp_path, book_path, kind):
    data = read(book_path)
    first = data["passages"][0]
    if kind == "passage_id":
        data["passages"][1]["id"] = first["id"]
    elif kind == "question_id":
        first["questions"][0]["id"] = "same"
        data["passages"][1]["questions"][2]["id"] = "same"
    elif kind == "number":
        first["questions"][1]["number"] = 1
    else:
        first["questions"].reverse()
    write(book_path, data)
    with pytest.raises(ValueError, match="중복|순서"):
        create_packet(book_path, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("level", ["root", "passage", "question"])
@pytest.mark.parametrize("field", ["figures", "tables", "images", "display_note"])
def test_unhandled_fields_never_silently_disappear(tmp_path, book_path, level, field):
    data = read(book_path)
    target = {"root": data, "passage": data["passages"][0],
              "question": data["passages"][0]["questions"][0]}[level]
    target[field] = [{"text": "public content requiring a renderer"}]
    write(book_path, data)
    with pytest.raises(ValueError, match=f"지원하지 않는 필드: {field}"):
        create_packet(book_path, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("raw", [
    b'{"passages": [], "passages": []}', b'{"minutes": NaN}', b'{"minutes": Infinity}', b'[]',
])
def test_nonstandard_json_and_nonobject_book_rejected(tmp_path, raw):
    path = tmp_path / "book.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        create_packet(path, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


def test_partial_collection_preserves_book_links_unknowns_and_raw_submission(tmp_path, book_path):
    original = book_path.read_bytes()
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    data["items"] = [data["items"][4], data["items"][0]]
    data["items"][0]["completed"] = True
    data["items"][0]["issues"] = [{"severity": "B", "location": "공통지문 [4～6] 첫째 문단",
                                   "quote": "합성 공통지문 1", "problem": "합성 검토 의견",
                                   "proposed_fix": "합성 수정 제안"}]
    write(response, data)
    result = collect_packet(packet, response)
    receipt = read(Path(result["receipt"]))
    assert receipt["source_format"] == "leet_reading_book"
    assert receipt["origin"] == "model" and receipt["partial"] is True
    assert receipt["submitted_items"] == 2 and receipt["completed_items"] == 1
    assert [row["number"] for row in receipt["items"]] == [5, 1]
    mapping = {row["number"]: row for row in read(packet / "manifest.json")["items"]}
    for row in receipt["items"]:
        assert all(row[key] == value for key, value in mapping[row["number"]].items())
        assert not {"parent_run", "candidate_sha256", "parent_candidate_sha256"} & set(row)
        for field in ("prior_answer_seen", "answer", "solve_seconds", "edit_seconds", "option_reasoning"):
            assert row[field] is None
    assert receipt["items"][1]["issues"] is None
    assert receipt["missing_item_ids"] == [mapping[number]["item_id"] for number in [2, 3, 4, 6]]
    for field in ("human_approved", "expert_verified", "difficulty_validated"):
        assert receipt[field] is False
    assert receipt["feedback_application_required"] is True
    destination = Path(result["collection"])
    assert (destination / "response.json").read_bytes() == response.read_bytes()
    digest = (destination / "digest.md").read_text()
    assert mapping[5]["question_locator"] in digest
    assert "parent_run:" not in digest
    assert book_path.read_bytes() == original


def test_collection_idempotence_and_original_file_preservation(tmp_path, book_path):
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    before = {path: path.read_bytes() for path in book_path.parent.iterdir()}
    response = response_file(packet, tmp_path, origin="human")
    first = collect_packet(packet, response)
    destination = Path(first["collection"])
    recorded = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in destination.iterdir()}
    second = collect_packet(packet / "manifest.json", response)
    assert first["duplicate"] is False and second["duplicate"] is True
    assert first["collection"] == second["collection"]
    assert recorded == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in destination.iterdir()}
    assert before == {path: path.read_bytes() for path in book_path.parent.iterdir()}


def test_common_passage_change_invalidates_old_review_and_all_version_ids(tmp_path, book_path):
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    old = read(packet / "manifest.json")["items"]
    response = response_file(packet, tmp_path)
    data = read(book_path)
    data["passages"][0]["paragraphs"][0] += " 합성 공통지문 수정"
    write(book_path, data)
    with pytest.raises(ValueError, match="원본.*해시"):
        collect_packet(packet, response, tmp_path / "collections")
    assert not (tmp_path / "collections").exists()
    new, _ = source_data(book_path)
    assert all(before["item_id"] != after["item_id"] for before, after in zip(old, new["items"]))


def test_source_changed_during_export_rejected_without_output(tmp_path, book_path, monkeypatch):
    import haean.reading_human_review as adapter

    render = adapter.render

    def mutate_after_render(stage, binding, entries):
        render(stage, binding, entries)
        book_path.write_bytes(book_path.read_bytes() + b"\n")

    monkeypatch.setattr(adapter, "render", mutate_after_render)
    with pytest.raises(ValueError, match="원본.*해시"):
        create_packet(book_path, tmp_path / "packet")
    assert not (tmp_path / "packet").exists()


@pytest.mark.parametrize("target", ["student/questions.html", "student/questions.json", "review/solutions.json"])
def test_tampered_render_rejected_before_collection(tmp_path, book_path, target):
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    response = response_file(packet, tmp_path)
    path = packet / target
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="해시"):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()


@pytest.mark.parametrize("field,value", [("number", 2), ("item_id", "invented"),
                                          ("passage_locator", "/passages/1"),
                                          ("question_locator", "/passages/0/questions/1")])
def test_manifest_mapping_tampering_rejected_even_with_recomputed_checksum(tmp_path, book_path, field, value):
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    response = response_file(packet, tmp_path)
    manifest_path = packet / "manifest.json"
    manifest = read(manifest_path)
    manifest["items"][0][field] = value
    write(manifest_path, manifest)
    sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (packet / "manifest.sha256").write_text(sha + "\n")
    with pytest.raises(ValueError, match="결속"):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()


@pytest.mark.parametrize("mutation", ["number", "id", "duplicate"])
def test_response_mapping_must_match_packet(tmp_path, book_path, mutation):
    packet = tmp_path / "packet"
    create_packet(book_path, packet)
    response = response_file(packet, tmp_path)
    data = read(response)
    if mutation == "number":
        data["items"][0]["number"] = 99
    elif mutation == "id":
        data["items"][0]["item_id"] = data["items"][1]["item_id"]
    else:
        data["items"].append(copy.deepcopy(data["items"][0]))
    write(response, data)
    with pytest.raises(ValueError, match="번호|ID"):
        collect_packet(packet, response)
    assert not (packet / "collections").exists()
