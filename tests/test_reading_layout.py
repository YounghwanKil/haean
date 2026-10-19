import copy
import json

import pytest

from haean.reading_layout import fill_reading, validate_book


def book():
    return {'passages':[{'paragraphs':['합성 지문'], 'questions':[{'number':p*3+i+1,'stem':'발문','options':['가','나','다','라','마'],'answer':1,'explanation':'근거','option_explanations':['근거']*5} for i in range(3)]} for p in range(10)]}


def test_full_reading_requires_ten_complete_ordered_triplets():
    assert len(validate_book(book()))==10
    for edit in ['count','number','options','answer','explanation']:
        b=book();q=b['passages'][0]['questions'][0]
        if edit=='count':b['passages'].pop()
        elif edit=='number':q['number']=2
        elif edit=='options':q['options']=['같음']*5
        elif edit=='answer':q['answer']=6
        else:q['explanation']=''
        with pytest.raises(ValueError):validate_book(b)


def historical_shaped_book():
    """Synthetic content with the metadata used by the existing full30 book."""
    value = book()
    value.update(title="합성 검토용 회차", minutes=70, human_approved=False,
                 sources=[{"part": "합성 입력", "sha256": "0" * 64}])
    for index, passage in enumerate(value["passages"], 1):
        passage.update(id=f"synthetic-passage-{index}", title="합성 제작 제목", domain="인문",
                       sources=[{"title": "합성 출처", "verified_scope": "합성 내용"}])
        for question in passage["questions"]:
            question.update(box="", cognitive_task="정보 확인·재구성", difficulty="중",
                            strongest_counterreading="합성 반대 해석")
    return value


@pytest.mark.parametrize("kind", ["questions", "solutions"])
def test_historical_shaped_book_remains_valid_without_mutation(kind):
    value = historical_shaped_book()
    original = copy.deepcopy(value)
    assert validate_book(value, kind=kind) == value["passages"]
    assert value == original


def test_question_only_book_does_not_require_authoring_ids_or_solution_metadata():
    value = book()
    original = copy.deepcopy(value)
    assert len(validate_book(value, kind="questions")) == 10
    assert value == original


def reject_before_java(tmp_path, monkeypatch, value, kind, match):
    def unexpected_java(*args, **kwargs):
        pytest.fail("invalid book reached HWP conversion or Java")

    monkeypatch.setattr("haean.reading_layout.execute", unexpected_java)
    monkeypatch.setattr("haean.reading_layout.java_tool", unexpected_java)
    source = tmp_path / "book.json"
    source.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "new-output" / "result.hwp"
    with pytest.raises(ValueError, match=match):
        fill_reading(source, tmp_path / "template.hwp", output, kind=kind)
    assert not output.parent.exists()


@pytest.mark.parametrize("kind", ["questions", "solutions"])
def test_boolean_answer_fails_before_java(tmp_path, monkeypatch, kind):
    value = historical_shaped_book()
    value["passages"][0]["questions"][0]["answer"] = True
    reject_before_java(tmp_path, monkeypatch, value, kind, "answer")


@pytest.mark.parametrize("kind", ["questions", "solutions"])
@pytest.mark.parametrize("level", ["book", "passage", "question"])
def test_unsupported_display_fields_are_not_silently_dropped(tmp_path, monkeypatch, kind, level):
    value = historical_shaped_book()
    target = {"book": value, "passage": value["passages"][0],
              "question": value["passages"][0]["questions"][0]}[level]
    target["figures"] = [{"caption": "생략하면 안 되는 합성 그림"}]
    reject_before_java(tmp_path, monkeypatch, value, kind, "지원하지 않는 필드")


@pytest.mark.parametrize("field", ["title", "domain", "cognitive_task", "difficulty"])
@pytest.mark.parametrize("invalid", ["missing", "blank", "wrong_type"])
def test_missing_solution_metadata_fails_before_java(tmp_path, monkeypatch, field, invalid):
    value = historical_shaped_book()
    passage = value["passages"][0]
    target = passage if field in {"title", "domain"} else passage["questions"][0]
    if invalid == "missing":
        del target[field]
    else:
        target[field] = "  " if invalid == "blank" else []
    reject_before_java(tmp_path, monkeypatch, value, "solutions", field)


def test_duplicate_json_keys_fail_before_java(tmp_path, monkeypatch):
    def unexpected_java(*args, **kwargs):
        pytest.fail("ambiguous JSON reached HWP conversion or Java")

    monkeypatch.setattr("haean.reading_layout.execute", unexpected_java)
    monkeypatch.setattr("haean.reading_layout.java_tool", unexpected_java)
    source = tmp_path / "book.json"
    raw = json.dumps(historical_shaped_book(), ensure_ascii=False)
    source.write_text(raw.replace('"answer": 1', '"answer": 2, "answer": 1', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="중복 JSON 키"):
        fill_reading(source, tmp_path / "template.hwp", tmp_path / "result.hwp")
