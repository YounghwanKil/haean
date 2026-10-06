"""Synthetic checks for feedback provenance and generation boundaries."""
import hashlib
import json
import sys

import pytest

from haean.cli import main
from haean.corpus import Corpus
from haean.models import Brief
from haean.pipeline import feedback, prepare, recent_feedback, save


def item_run(tmp_path, draft, brief):
    run = tmp_path / "reviewed"
    run.mkdir()
    save(run / "candidate.json", draft.model_dump())
    save(run / "brief.json", brief.model_dump())
    save(run / "status.json", {"state": "awaiting_human_review"})
    return run


def test_item_feedback_cli_preserves_model_origin(tmp_path, draft, brief, monkeypatch, capsys):
    run = item_run(tmp_path, draft, brief)
    source = tmp_path / "opinion.txt"
    text = "조건 누락 의견\n해설도 확인해 주세요.\n"
    source.write_text(text, encoding="utf-8-sig")
    monkeypatch.setattr(sys, "argv", ["haean", "feedback", str(run), "--item", "TEST-001",
                                      "--reviewer", "synthetic model", "--origin", "model",
                                      "--severity", "A", "--file", str(source)])
    main()
    entry = json.loads(capsys.readouterr().out)
    assert entry["origin"] == "model" and entry["text"] == text
    assert entry["candidate_sha256"] == hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest()
    assert json.loads((tmp_path / "feedback.jsonl").read_text()) == entry
    assert json.loads((run / "status.json").read_text())["state"] == "needs_revision"


def test_item_feedback_default_and_legacy_provenance(tmp_path, draft, brief):
    run = item_run(tmp_path, draft, brief)
    entry = feedback(run, "TEST-001", "합성 의견", "tester", "C")
    assert entry["origin"] == "human"
    path = tmp_path / "feedback.jsonl"
    original = path.read_bytes()
    with pytest.raises(ValueError, match="origin"):
        feedback(run, "TEST-001", "합성 의견", "tester", "C", origin="expert")
    assert path.read_bytes() == original
    del entry["origin"]
    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n")
    legacy = path.read_bytes()
    assert recent_feedback(tmp_path, brief.exam, brief.subject)[0]["origin"] == "unknown"
    assert path.read_bytes() == legacy


def corpus_for_exam(tmp_path, exam, subject):
    corpus = Corpus(tmp_path / "corpus.sqlite")
    corpus.add("example", "synthetic", exam, "example", subject,
               {"fields": {"과목": subject}})
    return corpus


def test_local_item_feedback_is_retained_but_not_forwarded(tmp_path, draft, brief):
    run = item_run(tmp_path, draft, brief)
    feedback(run, "TEST-001", "이 문항의 수치를 5로 고쳐 주세요.", "tester", "B")
    path = tmp_path / "feedback.jsonl"
    original = path.read_bytes()
    corpus = corpus_for_exam(tmp_path, brief.exam, brief.subject)
    generated = prepare(corpus, brief, tmp_path)
    assert json.loads((generated / "context.json").read_text())["feedback"] == []
    assert "이 문항의 수치를 5로" not in (generated / "request.md").read_text()
    assert path.read_bytes() == original
    assert recent_feedback(tmp_path, brief.exam, brief.subject)[0]["item_id"] == "TEST-001"


@pytest.mark.parametrize("exam,subject", [("leet", "추리논증"), ("psat5", "자료해석"), ("psat7", "자료해석")])
def test_corpus_feedback_stays_with_requested_exam(tmp_path, exam, subject):
    corpus = corpus_for_exam(tmp_path, exam, subject)
    for source_exam in ("leet", "psat5", "psat7"):
        corpus.add(source_exam, source_exam, source_exam, "feedback", "오류 정답 해설 수정")
    brief = Brief(exam=exam, subject=subject, item_type="합성 유형", topic="합성 자료")
    generated = prepare(corpus, brief, tmp_path / "runs")
    refs = json.loads((generated / "context.json").read_text())["references"]
    selected = [r for r in refs if r["role"] == "feedback"]
    assert len(selected) == 1 and selected[0]["exam"] == exam
