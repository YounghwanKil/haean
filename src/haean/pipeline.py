from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from .corpus import Corpus
from .models import Brief, Draft, BlindReview, EditorialReview
from .validation import public_item, validate, review_gate, similarity


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def prompt(name):
    return files("haean").joinpath("prompts", name + ".md").read_text(encoding="utf-8")


def prepare(corpus: Corpus, brief: Brief, root="runs") -> Path:
    run = Path(root) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True)
    query = f"{brief.subject} {brief.item_type} {brief.topic}"
    refs = corpus.search(query, brief.exam, 6, {"example", "metadata", "wiki"})
    # Metadata labels are authoritative for routing; fuzzy keyword overlap is not.
    candidates = corpus.search(query, brief.exam, 10000, {"example", "metadata"})
    candidates = [r for r in candidates if json.loads(r["meta"]).get("fields", {}).get("과목") == brief.subject]
    candidates.sort(key=lambda r: (json.loads(r["meta"]).get("fields", {}).get("문항유형") != brief.item_type, -r["score"], r["locator"]))
    if candidates: refs = candidates[:6]
    principle_ids = {r["source_id"] for sheet in ("문항 제작 원칙", "자료 기준")
                     for r in corpus.rows(brief.exam, sheet) if r["row"] > 1}
    principles = [dict(r) for r in corpus.db.execute("SELECT * FROM records WHERE exam=?", (brief.exam,)) if r["id"] in principle_ids]
    feedback = corpus.search("오류 정답 해설 수정", "leet", 3, {"feedback"})
    # Always include actual data-derived principles and transferable feedback, with role labels.
    refs = list({r["id"]: r for r in [*refs, *principles, *feedback]}.values())
    if not any(r["exam"] == brief.exam for r in refs):
        raise ValueError("출제에 사용할 해당 시험 자료가 없습니다")
    system = prompt("haean") + "\n" + prompt("leet" if brief.exam == "leet" else "psat")
    packet = {"brief": brief.model_dump(), "references": [
        {k: r[k] for k in ("id", "locator", "exam", "role", "text")} for r in refs],
        "feedback": recent_feedback(root, brief.exam, brief.subject),
        "note": "참고문항 전체가 아닌 검색된 자료. 전문·시각자료 결손을 유의."}
    save(run / "brief.json", brief.model_dump())
    save(run / "context.json", packet)
    save(run / "draft.schema.json", Draft.model_json_schema())
    save(run / "provenance.json", {"prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
                                    "source_ids": [r["id"] for r in refs], "version": "0.1.0"})
    (run / "request.md").write_text(system + "\n\n입력 자료(JSON):\n" + json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    save(run / "status.json", {"state": "prepared", "human_approved": False})
    return run


def recent_feedback(root, exam, subject):
    path = Path(root) / "feedback.jsonl"
    if not path.exists(): return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r["exam"] == exam and r["subject"] == subject][-12:]


class OpenAIProvider:
    def __init__(self, model=None, review_model=None, max_calls=12):
        from openai import OpenAI
        self.model = model or os.getenv("HAEAN_MODEL")
        self.review_model = review_model or os.getenv("HAEAN_REVIEW_MODEL") or self.model
        if not os.getenv("OPENAI_API_KEY") or not self.model:
            raise ValueError("OPENAI_API_KEY와 HAEAN_MODEL을 설정하세요. 키 없이 prepare로 출제 요청을 만들 수 있습니다.")
        self.client = OpenAI(timeout=180, max_retries=2)
        self.max_calls, self.calls, self.usage = max_calls, 0, []

    def call(self, stage, instructions, payload, schema):
        if self.calls >= self.max_calls:
            raise RuntimeError("모델 호출 한도에 도달했습니다")
        self.calls += 1
        model = self.review_model if stage in {"blind", "editor"} else self.model
        response = self.client.responses.parse(
            model=model, instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False), text_format=schema,
            max_output_tokens=16000, store=False,
        )
        self.usage.append({"stage": stage, "model": model, "response_id": response.id,
                           "usage": response.usage.model_dump() if response.usage else None})
        if response.output_parsed is None or response.status != "completed":
            raise RuntimeError(f"{stage}: 모델 응답이 완성되지 않았거나 거절됐습니다 ({response.status})")
        return response.output_parsed


def run_pipeline(run: Path, provider, max_revisions=2):
    if not 0 <= max_revisions <= 3:
        raise ValueError("max_revisions must be 0–3")
    if (run / "draft-r0.json").exists():
        raise ValueError("이미 실행한 run입니다. 새 prepare로 이력을 보존하세요.")
    brief = Brief.model_validate_json((run / "brief.json").read_text())
    context = json.loads((run / "context.json").read_text())
    instructions = prompt("haean") + "\n" + prompt("leet" if brief.exam == "leet" else "psat")
    allowed = {r["id"] for r in context["references"]}
    try:
        draft = provider.call("generate", instructions, context, Draft)
        for revision in range(max_revisions + 1):
            save(run / f"draft-r{revision}.json", draft.model_dump())
            errors = validate(draft, brief, allowed)
            hits = similarity(draft, context["references"])
            if hits: errors.append("참고자료와 긴 문구가 겹칩니다. 독창성 검토 필요.")
            blind = provider.call("blind", prompt("blind"), {"items": [public_item(i) for i in draft.items]}, BlindReview)
            editorial = provider.call("editor", prompt("editor"),
                                      {"brief": brief.model_dump(), "draft": draft.model_dump(),
                                       "blind": blind.model_dump(), "references": context["references"],
                                       "mechanical_errors": errors}, EditorialReview)
            errors.extend(review_gate(draft, blind, editorial))
            review = {"revision": revision, "blind": blind.model_dump(), "editorial": editorial.model_dump(),
                      "errors": errors, "similarity_hits": hits}
            save(run / f"review-r{revision}.json", review)
            if not errors or revision == max_revisions:
                save(run / "candidate.json", draft.model_dump())
                save(run / "status.json", {"state": "needs_revision" if errors else "awaiting_human_review",
                                           "revision": revision, "human_approved": False, "errors": errors,
                                           "candidate_sha256": hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest()})
                return draft
            draft = provider.call("revise", instructions + "\n지적을 반영해 전체 문항을 수정하라. 해설도 현행 지문에 맞게 다시 작성하라.",
                                  {"context": context, "draft": draft.model_dump(), "review": review}, Draft)
    except Exception as exc:
        save(run / "status.json", {"state": "failed", "human_approved": False, "error": type(exc).__name__})
        raise
    finally:
        save(run / "usage.json", getattr(provider, "usage", []))


def feedback(run: Path, item_id: str, text: str, reviewer: str, severity: str):
    if not text.strip() or not reviewer.strip():
        raise ValueError("검토자와 피드백을 입력하세요")
    draft = Draft.model_validate_json((run / "candidate.json").read_text())
    if item_id not in {i.id for i in draft.items}:
        raise ValueError("해당 run에 없는 문항 ID")
    brief = Brief.model_validate_json((run / "brief.json").read_text())
    entry = {"run": run.name, "item_id": item_id, "exam": brief.exam, "subject": brief.subject,
             "reviewer": reviewer, "severity": severity, "text": text,
             "candidate_sha256": hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest(),
             "created_at": datetime.now(timezone.utc).isoformat()}
    with (run.parent / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    status = json.loads((run / "status.json").read_text())
    status.update(human_approved=False)
    if severity in {"A", "B"}: status["state"] = "needs_revision"
    save(run / "status.json", status)
    return entry
