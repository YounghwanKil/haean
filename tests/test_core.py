import json
from fractions import Fraction

import pytest
from pydantic import ValidationError

from haean.models import Brief, BlindReview, EditorialReview, Calculation
from haean.planning import allocate, blueprint
from haean.validation import arithmetic, validate, public_item, review_gate
from haean.corpus import Corpus
from haean.pipeline import save, run_pipeline, feedback
from haean.export import export_review


def reviews(draft, correct=True):
    return BlindReview.model_validate({"solutions": [{"item_id": draft.items[0].id,
        "answer": 1 if correct else 2, "uniquely_answerable": True,
        "option_reasons": ["근거"] * 5, "missing_conditions": []}], "issues": []}), EditorialReview(issues=[], summary="테스트 검토")


def test_allocation_exact_and_deterministic():
    assert sum(allocate({"가": 9, "나": 8, "다": 5, "라": 3}, 40).values()) == 40
    assert allocate({"가": 1, "나": 1, "다": 1}, 25) == {"가": 9, "나": 8, "다": 8}
    with pytest.raises(ValueError): allocate({"가": 0}, 25)


def test_grade_collision_and_extra_session(tmp_path):
    c = Corpus(tmp_path / "db")
    for exam in ["psat5", "psat7"]:
        for i, session in enumerate(["2024", "2025", "2025 추가채용", "2026"]):
            fields = {"통합 문항 ID": "2026-VL-01", "연도": int(session[:4]), "회차": session,
                      "과목": "언어논리", "문항유형": "독해", "문항 번호": 1}
            c.add(exam, str(i), exam, "metadata", json.dumps(fields), {"sheet": "문항 데이터", "fields": fields})
    p = blueprint(c, "psat7", "언어논리")
    assert p["observations"] == 4 and p["session_count"] == 4 and p["total"] == 25
    assert blueprint(c, "psat7", "언어논리", exclude_extra=True)["session_count"] == 3
    assert blueprint(c, "psat5", "언어논리")["total"] == 40


def test_route_rejects_wrong_exam():
    with pytest.raises(ValidationError): Brief(exam="leet", subject="자료해석", item_type="계산", topic="통계")


def test_safe_exact_arithmetic():
    assert arithmetic("(0.3-0.1)/0.2") == Fraction(1)
    assert arithmetic("1/3") == Fraction(1, 3)
    for expression in ["__import__('os').system('echo unsafe')", "2**999999", "[1][0]", "True"]:
        with pytest.raises(ValueError): arithmetic(expression)
    with pytest.raises(ZeroDivisionError): arithmetic("1/0")


def test_schema_and_source_gate(draft, brief):
    assert not validate(draft, brief, {"source-1"})
    assert validate(draft, brief, set())
    draft.items[0].judgments.pop()
    assert any("판단 누락" in e for e in validate(draft, brief, {"source-1"}))


def test_missing_quotation_and_wrong_calculation(draft, brief):
    draft.items[0].explanation = '"문자가 발송되면 반드시 예약이 승인된다"라고 하였으므로'
    draft.items[0].calculations = [Calculation(label="비율", expression="10/100", expected="1", unit="비율", evidence="표")]
    errors = validate(draft, brief, {"source-1"})
    assert any("해설 인용" in e for e in errors)
    assert any("계산 불일치" in e for e in errors)


def test_blind_payload_has_no_answer_or_design(draft):
    public = public_item(draft.items[0])
    assert not {"answer", "explanation", "judgments", "source_ids", "difficulty_basis", "calculations"} & public.keys()


def test_mismatch_and_ambiguous_answer_block(draft):
    b, e = reviews(draft, False)
    assert review_gate(draft, b, e)
    b.solutions[0].answer = 1
    b.solutions[0].uniquely_answerable = False
    assert review_gate(draft, b, e)
    b.solutions = []
    assert review_gate(draft, b, e)


def test_revision_rechecks_and_never_auto_approves(tmp_path, draft, brief):
    save(tmp_path / "brief.json", brief.model_dump())
    save(tmp_path / "context.json", {"references": [{"id": "source-1", "text": "다른 예시"}],
         "exam_contract":"개별 배정 난도 우선", "exam_assignment":[{"id":"TEST-001","item_type":"조건 추론"}]})
    class Provider:
        usage = []
        calls = []
        def call(self, stage, instructions, payload, schema):
            self.calls.append(stage)
            if stage in {"generate", "revise"}: return draft
            if stage == "blind":
                assert "answer" not in payload["items"][0]
                assert 'exam_contract' not in payload
                return reviews(draft, self.calls.count("blind") > 1)[0]
            assert payload['exam_contract']=='개별 배정 난도 우선'
            return reviews(draft)[1]
    p = Provider()
    run_pipeline(tmp_path, p)
    status = json.loads((tmp_path / "status.json").read_text())
    assert p.calls == ["generate", "blind", "editor", "revise", "blind", "editor"]
    assert status["state"] == "awaiting_human_review" and status["human_approved"] is False
    assert (tmp_path / "draft-r0.json").exists() and (tmp_path / "review-r1.json").exists()
    with pytest.raises(ValueError): run_pipeline(tmp_path, p)


def test_failed_provider_preserves_state(tmp_path, brief):
    save(tmp_path / "brief.json", brief.model_dump())
    save(tmp_path / "context.json", {"references": []})
    class Fail:
        def call(self, *args): raise RuntimeError("refused")
    with pytest.raises(RuntimeError): run_pipeline(tmp_path, Fail())
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "failed"


def test_export_escapes_and_splits_answers(tmp_path, draft):
    draft.items[0].passage += '<script>alert(1)</script>'
    save(tmp_path / "candidate.json", draft.model_dump())
    save(tmp_path / "status.json", {"state": "awaiting_human_review"})
    export_review(tmp_path)
    q = (tmp_path / "questions.html").read_text()
    assert "<script>" not in q and "&lt;script&gt;" in q
    assert "정답 1" not in q
    assert "정답 1" in (tmp_path / "solutions.html").read_text()


def test_feedback_invalidates_candidate(tmp_path, draft, brief):
    run = tmp_path / "one"
    run.mkdir()
    save(run / "candidate.json", draft.model_dump())
    save(run / "brief.json", brief.model_dump())
    save(run / "status.json", {"state": "awaiting_human_review"})
    entry = feedback(run, "TEST-001", "필수 조건 누락", "tester", "A")
    assert entry["candidate_sha256"]
    assert json.loads((run / "status.json").read_text())["state"] == "needs_revision"
    with pytest.raises(ValueError): feedback(run, "missing", "의견", "tester", "B")


def test_stale_manual_review_rejected(tmp_path, draft, brief):
    from argparse import Namespace
    from haean.cli import dispatch
    save(tmp_path / "context.json", {"brief": brief.model_dump(), "references": [{"id": "source-1", "text": "예시"}]})
    save(tmp_path / "candidate.json", draft.model_dump())
    with pytest.raises(ValueError, match="해시"):
        dispatch(Namespace(command="review-result", run=tmp_path, candidate_sha="old"))
