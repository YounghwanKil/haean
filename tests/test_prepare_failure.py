"""A failed source preflight must not create an apparent production run."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from haean.corpus import Corpus
from haean.pipeline import prepare


@pytest.mark.parametrize("command", ["prepare", "generate"])
def test_empty_corpus_cli_fails_before_run_or_codex(tmp_path, command):
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "empty.sqlite"
    Corpus(database).db.close()
    runs = tmp_path / "runs"
    marker = tmp_path / "codex-invoked"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    codex = binaries / "codex"
    codex.write_text('#!/bin/sh\nprintf invoked > "$HAEAN_TEST_CODEX_MARKER"\nexit 99\n')
    codex.chmod(0o755)
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PATH": str(binaries),
           "HAEAN_TEST_CODEX_MARKER": str(marker)}

    result = subprocess.run(
        [sys.executable, "-m", "haean.cli", "--db", str(database), command,
         "--exam", "leet", "--subject", "추리논증", "--type", "조건 추론",
         "--topic", "합성 자료 검색 검사", "--runs", str(runs)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 2
    assert "출제에 사용할 해당 시험 자료가 없습니다" in result.stderr
    assert result.stdout == ""
    assert not runs.exists()
    assert not marker.exists()


def test_retrieval_failure_leaves_existing_runs_untouched(tmp_path, monkeypatch, brief):
    runs = tmp_path / "runs"
    prior = runs / "prior-run"
    prior.mkdir(parents=True)
    evidence = prior / "status.json"
    evidence.write_text('{"state": "awaiting_human_review"}\n')
    before = evidence.read_bytes()

    def failed_retrieval(corpus, requested_brief):
        raise RuntimeError("synthetic retrieval failure")

    monkeypatch.setattr("haean.retrieval.retrieve", failed_retrieval)
    corpus = Corpus(tmp_path / "empty.sqlite")
    try:
        with pytest.raises(RuntimeError, match="synthetic retrieval failure"):
            prepare(corpus, brief, runs)
    finally:
        corpus.db.close()

    assert list(runs.iterdir()) == [prior]
    assert evidence.read_bytes() == before
