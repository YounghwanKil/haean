from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from .corpus import Corpus, nfc
from .models import Brief, Draft, BlindReview, EditorialReview
from .planning import blueprint
from .pipeline import prepare, run_pipeline, save, feedback, prompt
from .codex_runtime import CodexProvider
from .validation import validate, public_item, review_gate, similarity
from .export import export_review


def main():
    parser = argparse.ArgumentParser(description="haean — LEET·PSAT 출제 및 검토")
    parser.add_argument("--db", default="data/corpus.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("import", help="원본을 읽기 전용으로 색인")
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--refresh", action="store_true")
    p = sub.add_parser("import-questions", help="화면 대조한 PDF 문항 전문 패킷 등록; 정답 검증과 별도")
    p.add_argument("packet", type=Path)
    p = sub.add_parser("import-team", help="제공된 팀 자료 파일명에 한해 가져오기")
    p.add_argument("directory", type=Path)
    p.add_argument("--refresh", action="store_true")
    p = sub.add_parser("audit-sources", help="팀 자료·ZIP 전체 목록과 안전한 압축 해제")
    p.add_argument("directory", type=Path)
    p.add_argument("--out", type=Path, default=Path("data/source-audit"))
    p = sub.add_parser("human-checkpoint", help="실제 사람 검토 기록 등록; 납품 승인이 아님")
    p.add_argument("run", type=Path)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--candidate-sha", required=True)
    p.add_argument("--note", required=True)
    for name in ("final-prepare", "final-review"):
        p = sub.add_parser(name)
        p.add_argument("run", type=Path)
        if name == "final-review": p.add_argument("--model", default="gpt-6-astra")
    sub.add_parser("status")
    p = sub.add_parser("role", help="서브에이전트에 전달할 실제 역할 지침")
    p.add_argument("name")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--exam", choices=["leet", "psat5", "psat7", "team"])
    p.add_argument("--limit", type=int, default=6)
    p = sub.add_parser("plan")
    p.add_argument("--exam", choices=["leet", "psat5", "psat7"], required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--since", type=int, default=2024)
    p.add_argument("--until", type=int, default=2026)
    p.add_argument("--exclude-extra", action="store_true")
    p.add_argument("--product", choices=["full", "bridge"], default="full")
    p.add_argument("--out", type=Path)
    for name in ["prepare", "generate"]:
        p = sub.add_parser(name)
        p.add_argument("--exam", choices=["leet", "psat5", "psat7"], required=True)
        p.add_argument("--subject", required=True)
        p.add_argument("--type", dest="item_type", required=True)
        p.add_argument("--topic", required=True)
        p.add_argument("--difficulty", choices=["하", "중", "상"], default="중")
        p.add_argument("--count", type=int, default=1)
        p.add_argument("--set", dest="shared_passage", action="store_true")
        p.add_argument("--runs", default="runs")
        if name == "generate":
            p.add_argument("--model", default="gpt-6-astra")
            p.add_argument("--max-revisions", type=int, default=2)
    p = sub.add_parser("check", help="수동 작성본 검증 및 독립 검토 패킷 생성")
    p.add_argument("run", type=Path)
    p.add_argument("draft", type=Path)
    p = sub.add_parser("review-result", help="수동 독립 검토 결과로 품질 게이트 평가")
    p.add_argument("run", type=Path)
    p.add_argument("blind", type=Path)
    p.add_argument("editorial", type=Path)
    p.add_argument("--candidate-sha", required=True, help="검토자가 읽은 candidate.json의 SHA-256")
    p = sub.add_parser("blind", help="ChatGPT 로그인으로 별도 Codex 세션에서 독립 풀이")
    p.add_argument("run", type=Path)
    p.add_argument("--model", default="gpt-6-astra")
    p = sub.add_parser("export")
    p.add_argument("run", type=Path)
    p = sub.add_parser("feedback")
    p.add_argument("run", type=Path)
    p.add_argument("--item", required=True)
    text_input = p.add_mutually_exclusive_group(required=True)
    text_input.add_argument("--text")
    text_input.add_argument("--file", type=Path, help="UTF-8 텍스트 피드백 파일")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--severity", choices=["A", "B", "C"], required=True)
    p.add_argument("--origin", choices=["human", "model"], default="human")
    p = sub.add_parser("feedback-note", help="공통 텍스트 피드백을 개선 실험 입력으로 보관")
    p.add_argument("--exam", choices=["leet", "psat5", "psat7", "team"], required=True)
    p.add_argument("--subject")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--origin", choices=["human", "model"], default="human")
    text_input = p.add_mutually_exclusive_group(required=True)
    text_input.add_argument("--text")
    text_input.add_argument("--file", type=Path, help="UTF-8 텍스트 피드백 파일")
    p = sub.add_parser("feedback-notes", help="시험·과목에 맞는 원문 피드백 조회")
    p.add_argument("--exam", choices=["leet", "psat5", "psat7", "team"])
    p.add_argument("--subject")
    p.add_argument("--limit", type=int, default=12)
    p = sub.add_parser("exam-build", help="배정표로 모의고사 전체 출제·독립 검토")
    p.add_argument("plan", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--max-revisions", type=int, default=2)
    p.add_argument("--model", default="gpt-6-astra")
    p = sub.add_parser("exam-assemble", help="작성 묶음을 회차 번호대로 모아 검토본 생성")
    p.add_argument("folder", type=Path)
    p = sub.add_parser("evaluate", help="고정 과제에서 Astra 출제·검토·평가 실행")
    p.add_argument("--suite", type=Path, default=Path("evals/pilot.json"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cases", nargs="+")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-revisions", type=int, default=1)
    p.add_argument("--model", default="gpt-6-astra")
    p = sub.add_parser("compare")
    p.add_argument("baseline", type=Path)
    p.add_argument("candidate", type=Path)
    p = sub.add_parser("experiment")
    p.add_argument("name")
    p.add_argument("--baseline", type=Path, required=True)
    p = sub.add_parser("style-prepare")
    p.add_argument("run", type=Path)
    p.add_argument("--item", required=True)
    p.add_argument("--field", choices=["passage", "explanation", "commentary"], required=True)
    p = sub.add_parser("style-check")
    p.add_argument("folder", type=Path)
    p = sub.add_parser("layout-fill", help="기존 HWP 양식에 문항 삽입; 원본 보존")
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--template", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--kind", choices=["questions", "solutions"], default="questions")
    p = sub.add_parser("layout-package")
    p.add_argument("run", type=Path)
    p.add_argument("--question-template", type=Path, required=True)
    p.add_argument("--solution-template", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"haean: {exc}", file=sys.stderr)
        raise SystemExit(2)


def feedback_text(a):
    return a.file.read_text(encoding="utf-8-sig") if a.file else a.text


def dispatch(a):
    if a.command == 'import-questions':
        from .question_sources import import_questions
        return import_questions(Corpus(a.db), a.packet)
    if a.command in {"exam-build", "exam-assemble"}:
        from .full_exam import build, assemble
        if a.command == "exam-assemble": return assemble(a.folder)
        return build(a.plan, a.db, a.out, a.workers, a.max_revisions, a.model)
    if a.command == "audit-sources":
        from .source_audit import audit_sources
        result = audit_sources(team_files(a.directory), a.out)
        return {"inventory": str(a.out / "inventory.json"), "provided_paths": result["provided_paths"], "unique_sources": result["unique_sources"]}
    if a.command in {"human-checkpoint", "final-prepare", "final-review"}:
        from .final_review import human_checkpoint, prepare_final, final_review
        if a.command == "human-checkpoint": return human_checkpoint(a.run, a.reviewer, a.candidate_sha, a.note)
        if a.command == "final-prepare": return prepare_final(a.run)
        return final_review(a.run, CodexProvider(a.model, trace_dir=a.run / "final-traces"))
    if a.command in {"feedback-note", "feedback-notes"}:
        from .feedback_notes import add_note, list_notes
        folder = Path(a.db).parent / "feedback"
        if a.command == "feedback-note":
            return add_note(folder, feedback_text(a), a.exam, a.subject, a.reviewer, a.origin)
        return list_notes(folder, a.exam, a.subject, a.limit)
    if a.command == "role":
        from .roles import role_packet
        return role_packet(a.name)
    if a.command == "layout-fill":
        from .hwp import fill_template
        return fill_template(a.runs, a.template, a.out, a.title, a.start, a.kind)
    if a.command == "layout-package":
        from .layout import package
        return package(a.run, a.question_template, a.solution_template)
    if a.command in {"style-prepare", "style-check"}:
        from .style import style_prepare, style_check
        return style_prepare(a.run, a.item, a.field) if a.command == "style-prepare" else style_check(a.folder)
    if a.command in {"evaluate", "compare", "experiment"}:
        from .evaluation import evaluate_suite, compare, experiment
        if a.command == "compare": return compare(json.loads(a.baseline.read_text()), json.loads(a.candidate.read_text()))
        if a.command == "experiment": return experiment(a.name, a.baseline)
        return evaluate_suite(Corpus(a.db), a.suite, a.out, a.cases, a.repeats, a.max_revisions, a.model)
    if a.command == "blind":
        payload = json.loads((a.run / "blind-input.json").read_text())
        provider = CodexProvider(a.model, trace_dir=a.run / "codex-traces")
        result = provider.call("blind", prompt("blind"), payload, BlindReview)
        save(a.run / "blind-result.json", result.model_dump())
        save(a.run / "blind-usage.json", provider.usage)
        return {"result": str(a.run / "blind-result.json")}
    if a.command == "export": return export_review(a.run)
    if a.command == "feedback":
        return feedback(a.run, a.item, feedback_text(a), a.reviewer, a.severity, getattr(a, "origin", "human"))
    if a.command in {"check", "review-result"}:
        context = json.loads((a.run / "context.json").read_text())
        brief = Brief.model_validate(context["brief"])
        draft = Draft.model_validate_json((a.draft if a.command == "check" else a.run / "candidate.json").read_text())
        if a.command == "review-result" and hashlib.sha256((a.run / "candidate.json").read_bytes()).hexdigest() != a.candidate_sha:
            raise ValueError("검토 대상과 현재 문항의 해시가 다릅니다. 현행 문항을 다시 검토하세요.")
        errors = validate(draft, brief, {r["id"] for r in context["references"]})
        if similarity(draft, context["references"]):
            errors.append("참고자료와 긴 문구가 겹칩니다. 독창성 검토 필요.")
        if a.command == "check":
            # Preserve previous revisions on every manual import.
            history = a.run / "manual-history"
            history.mkdir(exist_ok=True)
            index = len(list(history.glob("*.json")))
            save(history / f"draft-{index:03}.json", draft.model_dump())
            save(a.run / "candidate.json", draft.model_dump())
            candidate_sha = hashlib.sha256((a.run / "candidate.json").read_bytes()).hexdigest()
            (a.run / "candidate.sha256").write_text(candidate_sha + "\n")
            save(a.run / "blind-input.json", {"items": [public_item(i) for i in draft.items]})
            save(a.run / "blind.schema.json", BlindReview.model_json_schema())
            save(a.run / "editorial.schema.json", EditorialReview.model_json_schema())
            (a.run / "blind-instructions.md").write_text(prompt("blind"))
            (a.run / "editorial-instructions.md").write_text(prompt("editor"))
            state = "needs_revision" if errors else "awaiting_independent_review"
        else:
            blind = BlindReview.model_validate_json(a.blind.read_text())
            editorial = EditorialReview.model_validate_json(a.editorial.read_text())
            errors += review_gate(draft, blind, editorial)
            save(a.run / "manual-review.json", {"blind": blind.model_dump(), "editorial": editorial.model_dump(), "errors": errors})
            state = "needs_revision" if errors else "awaiting_human_review"
        save(a.run / "status.json", {"state": state, "human_approved": False, "errors": errors,
                                      "candidate_sha256": hashlib.sha256((a.run / "candidate.json").read_bytes()).hexdigest()})
        return {"state": state, "errors": errors}
    corpus = Corpus(a.db)
    if a.command in {"import", "import-team"}:
        paths = a.paths if a.command == "import" else team_files(a.directory)
        results = [corpus.import_file(p, refresh=getattr(a, "refresh", False)) for p in paths]
        if a.command == "import-team":
            save(Path(a.db).parent / "import-report.json", results)
        return results
    if a.command == "status": return corpus.report()
    if a.command == "search":
        return [{k: r[k] for k in ("id", "exam", "role", "locator", "text")} for r in corpus.search(a.query, a.exam, a.limit)]
    if a.command == "plan":
        result = blueprint(corpus, a.exam, a.subject, a.since, a.until, a.exclude_extra, a.product)
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            save(a.out, result)
        return result
    brief = Brief(**{k: getattr(a, k) for k in Brief.model_fields})
    run = prepare(corpus, brief, a.runs)
    provider = CodexProvider(a.model, trace_dir=run / "codex-traces") if a.command == "generate" else None
    if provider:
        run_pipeline(run, provider, a.max_revisions)
        export_review(run)
    return {"run": str(run), "status": json.loads((run / "status.json").read_text())}


def team_files(directory):
    # Explicit allowlist of filenames supplied in this conversation, normalized on macOS.
    exact = {"Wiki_LEET.zip", "SK문항_대조정리_261006.zip", "폰트모음.zip", "폰트모음 (1).zip",
             "PSAT_5급_기출통계_2017-2026.xlsx", "PSAT_7급_기출통계_2019-2026.xlsx",
             "LEET_추리논증_통합데이터 (5).xlsx", "LEET_추리논증_통합데이터 (5) (1).xlsx",
             "KakaoTalk_Chat_서준원_2026-10-07-00-17-24.csv", "KakaoTalk_Chat_Abyss 연구소_2026-10-07-00-16-15.csv",
             "28추리_서바_03회_해설지_260914_2000_CA검토용_최종.hwp",
             "28추리_서바_03회_문제지_260914_2000_CA검토용_최종.hwp",
             "2028_시대인재LEET_서바이벌_3회_추리논증_CA_의견_최종.xlsx",
             "28추리_서바_03회_해설지_2차검토반영.hwp", "28추리_서바_03회_문제지_2차검토반영.hwp",
             "28추리_서바_3회_검토의견_260907_1930_연구소.hwp",
             "시대LEET_추리논증_40문항해설지양식_250928_2226_v3 (3).hwp",
             "시대LEET_추리논증_40문항(20p)양식_260804_0000_v3.hwp",
             "블라인드 모의고사 정답률 및 검토의견.xlsx",
             "블라인드 모의고사 2회차 문제 확정본(최종).hwpx", "블라인드 모의고사 1회차 문제 확정본(최종).hwp",
             "27추리_전국_01회_해설지_260306_1814_최종마감(인쇄용).hwp",
             "27추리_전국_01회_문제지_260312_1635_최종마감(인쇄용).hwp"}
    return sorted((p for p in directory.iterdir() if nfc(p.name) in exact), key=lambda p: nfc(p.name))


if __name__ == "__main__": main()
