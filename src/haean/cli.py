from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from .corpus import Corpus, nfc
from .models import Brief, Draft, BlindReview, EditorialReview
from .planning import blueprint
from .pipeline import prepare, run_pipeline, save, feedback, prompt, review_prompt
from .codex_runtime import CodexProvider
from .validation import validate, public_item, review_gate, similarity
from .export import export_review


def main():
    parser = argparse.ArgumentParser(description="haean — LEET·PSAT 출제 및 검토")
    parser.add_argument("--db", default="data/corpus.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)
    from .track_cli import add_parser
    add_parser(sub)
    from .composition_cli import add_parser as add_composition_parser
    add_composition_parser(sub)
    from .reading_cli import add_parser as add_reading_parser
    add_reading_parser(sub)
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
            p.add_argument("--compact-reference-audit", action="store_true",
                           help="검증 원문을 보존하고 writer/editor의 선택 참고 중복 감사 map만 축약")
    p = sub.add_parser("check", help="수동 작성본 검증 및 독립 검토 패킷 생성")
    p.add_argument("run", type=Path)
    p.add_argument("draft", type=Path)
    p = sub.add_parser("shortcut-review", help="정답 비공개 짧은 풀이와 핵심 판단 대조; 선택 검토 2회")
    p.add_argument("run", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="gpt-6-astra")
    p = sub.add_parser("distractor-check", help="SHA로 연결한 정상·오독 비교식 점검; 선택 검토 보조지")
    p.add_argument("candidate", type=Path)
    p.add_argument("sidecar", type=Path)
    p = sub.add_parser("editor-prepare", help="독립 풀이를 고정하고 새 편집 검토 패킷 준비")
    p.add_argument("run", type=Path)
    p.add_argument("--blind", required=True, type=Path)
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
    p = sub.add_parser("review-packet", help="사람 검토용 문제·해설·응답 양식을 버전에 고정해 분리")
    p.add_argument("source", type=Path, help="candidate run, assembled.json 회차 또는 언어이해 book.json")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("review-collect", help="버전·문항 번호를 대조해 검토 응답 원문 수집; 자동 승인 아님")
    p.add_argument("packet", type=Path)
    p.add_argument("response", type=Path)
    p = sub.add_parser("feedback")
    p.add_argument("run", type=Path)
    p.add_argument("--item", required=True)
    text_input = p.add_mutually_exclusive_group(required=True)
    text_input.add_argument("--text")
    text_input.add_argument("--file", type=Path, help="UTF-8 텍스트 피드백 파일")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--severity", choices=["A", "B", "C"], required=True)
    p.add_argument("--origin", choices=["human", "model"], default="human")
    p.add_argument("--candidate-sha", help="검토자가 읽은 candidate.json의 SHA-256; 출력물 의견에는 지정")
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
    p = sub.add_parser("exam-ref-bind", help="선택한 정제 참고 전문을 새 회차 계획에 연결; 모델 호출 없음")
    p.add_argument("plan", type=Path)
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("exam-build", help="배정표로 모의고사 전체 출제·독립 검토")
    p.add_argument("plan", type=Path)
    p.add_argument("--composition-packet", type=Path, help="compose bind로 검증한 선택 회차 설계 패킷")
    p.add_argument("--compact-reference-audit", action="store_true")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--max-revisions", type=int, default=2)
    p.add_argument("--model", default="gpt-6-astra")
    p = sub.add_parser("exam-assemble", help="작성 묶음을 회차 번호대로 모아 검토본 생성")
    p.add_argument("folder", type=Path)
    p = sub.add_parser("exam-status", help="모델 호출 없이 회차의 저장된 진행 단계와 오류 조회")
    p.add_argument("folder", type=Path)
    p = sub.add_parser("exam-revision-request", help="원 검토본을 보존하고 번호·버전에 연결한 수정 요청 저장; 모델 호출 없음")
    p.add_argument("folder", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--slots", type=int, nargs="+", required=True, metavar="NUMBER")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--file", type=Path, help="검토한 수정 의견의 UTF-8 텍스트 파일")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--origin", choices=["human", "model", "unknown"], required=True)
    p.add_argument("--severity", choices=["A", "B", "C"], default="C")
    p = sub.add_parser("exam-resume", help="기존 이력을 보존하고 미완료 묶음만 새 실행에서 재개")
    p.add_argument("folder", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--replacement", type=Path, action="append", default=[])
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--max-revisions", type=int, default=2)
    p.add_argument("--model", default="gpt-6-astra")
    p.add_argument("--compact-reference-audit", action="store_true",
                   help="이번 재개 호출에만 적용; 부모 실행 옵션을 자동 상속하지 않음")
    p.add_argument("--slots", type=int, nargs="+", metavar="NUMBER",
                   help="지정 번호가 속한 미완료 묶음만 재개; 기존 묶음의 모든 번호를 지정")
    p.add_argument("--revision-request", type=Path, action="append", default=[],
                   help="명시 수정 요청 JSON; --slots 필수, 등급과 별개로 새 수정부터 시작")
    p = sub.add_parser("evaluate", help="고정 과제에서 Astra 출제·검토·평가 실행")
    p.add_argument("--suite", type=Path, default=Path("evals/pilot.json"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cases", nargs="+")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-revisions", type=int, default=1)
    p.add_argument("--model", default="gpt-6-astra")
    p = sub.add_parser("evaluate-run", help="저장된 문항 버전을 원본 변경 없이 새 평가 계약으로 평가")
    p.add_argument("run", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--revision", type=int, help="생략하면 현 candidate, 지정하면 보존된 draft-rN/review-rN")
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
    p.add_argument("--total-pages", type=int, help="한글 렌더에서 확인한 문제지 전체 쪽 수로 바탕쪽 분모 보정; 재렌더 확인 필요")
    p.add_argument("--page-start", type=int, action="append", default=[], help="해당 문제를 새 쪽에서 시작; 실제 배치 검토 후 지정, 반복 가능")
    p.add_argument("--exam-size", type=int, choices=[25, 40], help="전체 회차 슬롯 수; 정확한 문항 수 필요, 25는 PSAT7 전용")
    p.add_argument("--continuous", action="store_true", help="두 번째 작성 문항부터 강제 단 넘김 없이 이어 배치; 실제 한글 재검수 필요")
    p = sub.add_parser("layout-package")
    p.add_argument("run", type=Path)
    p.add_argument("--question-template", type=Path, required=True)
    p.add_argument("--solution-template", type=Path, required=True)
    p = sub.add_parser("wiki", help="로컬 근거 기반 위키 관리")
    p.add_argument("operation", choices=["init", "put", "lint", "search"])
    p.add_argument("--root", type=Path, default=Path("data/wiki"))
    p.add_argument("--packet", type=Path)
    p.add_argument("--query")
    for command in ('novelty-index', 'novelty-check'):
        p = sub.add_parser(command, help='누적 생성물·언어이해 book 기록 및 재사용 후보 대조; 독창성 판정 아님')
        p.add_argument('runs', nargs='+', type=Path, help='표준 run·production 또는 언어이해 book.json·production·attempt')
        p.add_argument('--passage-id', help='언어이해 입력에서 지문 하나만 선택; 생략하면 전체 입력')
        p.add_argument('--catalog', type=Path, default=Path('data/generated.sqlite'))
        if command == 'novelty-check':
            p.add_argument('--out', type=Path, required=True)
    for command in ('novelty-memory', 'novelty-get'):
        p = sub.add_parser(command, help='생성 기억 색인 조회·선택 문항 원문 회수')
        p.add_argument('--catalog', type=Path, default=Path('data/generated.sqlite'))
        p.add_argument('--exam', required=True, choices=['leet', 'psat5', 'psat7'])
        p.add_argument('--subject', required=True)
        p.add_argument('--out', type=Path)
        if command == 'novelty-memory':
            p.add_argument('--offset', type=int, default=0)
            p.add_argument('--limit', type=int, default=40)
        else:
            p.add_argument('--item', action='append', required=True)
            p.add_argument('--all-versions', action='store_true')
    p = sub.add_parser('novelty-review', help='선택 원문쌍을 별도 Codex 1회로 검토; 현행 승인·상태 변경 없음')
    p.add_argument('run', type=Path, help='1–4문항 run 또는 언어이해 book.json·production·attempt (한 지문×3문항)')
    p.add_argument('--passage-id', help='언어이해 다지문 입력에서 검토할 지문 ID; 한 세트 입력은 생략 가능')
    p.add_argument('--out', required=True, type=Path, help='원 run 밖의 새 출력 폴더')
    p.add_argument('--neighbors', type=int, default=1)
    p.add_argument('--history', type=Path, default=Path('data/generated.sqlite'))
    p.add_argument('--model', default='gpt-6-astra')
    p = sub.add_parser("verify-source-profiles", help="원문 ID·해시·삽입 필드 읽기 전용 검증; 의미 판정 아님")
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path, help="새 보고서 경로; 기존 파일 덮어쓰기 금지")
    args = parser.parse_args()
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if args.command == "verify-source-profiles" and not result["valid"]:
            raise SystemExit(1)
        if args.command == "track" and args.track_command == "brief-check" and not result["valid"]:
            raise SystemExit(1)
        if args.command == "track" and args.track_command == "ref-build" and result["errors"]:
            raise SystemExit(1)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"haean: {exc}", file=sys.stderr)
        raise SystemExit(2)


def feedback_text(a):
    return a.file.read_text(encoding="utf-8-sig") if a.file else a.text


def dispatch(a):
    if a.command == "reading":
        from .reading_cli import dispatch as reading_dispatch
        return reading_dispatch(a)
    if a.command == "shortcut-review":
        from .shortcut_review import shortcut_review
        return shortcut_review(a.run, a.out, model=a.model)
    if a.command == "distractor-check":
        from .distractor_checks import check_distractors
        return check_distractors(a.candidate, a.sidecar)
    if a.command == "compose":
        from .composition_cli import dispatch as composition_dispatch
        return composition_dispatch(a)
    if a.command == "track":
        from .track_cli import dispatch as track_dispatch
        return track_dispatch(a)
    if a.command == "verify-source-profiles":
        from .source_identity import verify
        return verify(a.input, a.out)
    if a.command == 'novelty-review':
        from .novelty_review import novelty_review
        return novelty_review(a.run, a.out, neighbors=a.neighbors, history=a.history, model=a.model,
                              passage_id=a.passage_id)
    if a.command in {'novelty-memory', 'novelty-get'}:
        from . import novelty
        if a.command == 'novelty-memory':
            result = novelty.memory_index(a.catalog, a.exam, a.subject, a.offset, a.limit)
        else:
            result = novelty.memory_get(a.catalog, a.exam, a.subject, a.item, a.all_versions)
        if a.out:
            save(a.out, result)
        return result
    if a.command in {'novelty-index', 'novelty-check'}:
        from . import novelty
        rows = novelty.records(a.runs, passage_id=a.passage_id)
        if a.command == 'novelty-index':
            return novelty.remember(a.catalog, rows)
        previous = novelty.history(a.catalog)
        result = novelty.audit(rows, previous)
        result['catalog_missing_or_empty'] = not previous
        save(a.out, result)
        return result
    if a.command == 'exam-status':
        from .production_status import production_status
        return production_status(a.folder)
    if a.command == 'exam-revision-request':
        from .revision_request import create_request
        text = a.file.read_text(encoding='utf-8') if a.file is not None else a.text
        return create_request(a.folder, a.out, slots=a.slots, text=text,
                              reviewer=a.reviewer, origin=a.origin, severity=a.severity)
    if a.command == "wiki":
        from . import wiki
        if a.operation == "put":
            if not a.packet: raise ValueError("--packet is required")
            return wiki.put(a.root, a.packet)
        if a.operation == "search":
            if not a.query: raise ValueError("--query is required")
            return wiki.search(a.root, a.query)
        return getattr(wiki, a.operation)(a.root)
    if a.command == 'exam-resume':
        from .exam_resume import resume
        return resume(a.folder, a.db, a.out, a.workers, a.max_revisions, a.model, a.replacement,
                      **({'slots': a.slots} if a.slots is not None else {}),
                      **({'revision_requests': a.revision_request} if a.revision_request else {}),
                      **({'compact_reference_audit': True} if a.compact_reference_audit else {}))
    if a.command == 'exam-ref-bind':
        from .exam_references import bind_exam_references
        plan = bind_exam_references(a.plan, a.index, a.selection, a.out)
        return {"plan": str(plan), "coverage": str(plan.parent / "coverage.json"),
                "references": str(plan.parent / "references.json"),
                "generation_executed": False, "quality_verified": False}
    if a.command == 'import-questions':
        from .question_sources import import_questions
        return import_questions(Corpus(a.db), a.packet)
    if a.command in {"exam-build", "exam-assemble"}:
        from .full_exam import build, assemble
        if a.command == "exam-assemble": return assemble(a.folder)
        return build(a.plan, a.db, a.out, a.workers, a.max_revisions, a.model,
                     composition_packet=a.composition_packet,
                     **({'compact_reference_audit': True} if a.compact_reference_audit else {}))
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
        return fill_template(a.runs, a.template, a.out, a.title, a.start, a.kind, a.total_pages, a.page_start, a.exam_size, a.continuous)
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
    if a.command == "evaluate-run":
        from .evaluation_run import evaluate_run
        return evaluate_run(a.run, a.out, revision=a.revision, model=a.model)
    if a.command == "blind":
        from .review_evidence import (current_binding, review_inputs, json_sha256, codex_blind_envelope,
                                     preserve_review_files, invalidate_editor_review, prepare_editor_review)
        binding = current_binding(a.run, "blind")
        brief, _, public = review_inputs(a.run)
        payload = json.loads((a.run / "blind-input.json").read_text())
        if json_sha256(payload) != json_sha256(public):
            raise ValueError("review_input_binding_mismatch: blind-input이 현행 수험생용 문항과 다릅니다. 새 check가 필요합니다")
        prior_inputs = set((a.run / "codex-traces").glob("*-blind.input.json"))
        provider = CodexProvider(a.model, trace_dir=a.run / "codex-traces")
        result = provider.call("blind", review_prompt("blind", brief), payload, BlindReview)
        envelope = codex_blind_envelope(a.run, binding, result, a.model, prior_inputs)
        preserve_review_files(a.run, ["blind-result.json", "blind-usage.json"])
        invalidate_editor_review(a.run)
        save(a.run / "blind-result.json", envelope)
        save(a.run / "blind-usage.json", provider.usage)
        return {"result": str(a.run / "blind-result.json"),
                "editorial": prepare_editor_review(a.run, a.run / "blind-result.json")}
    if a.command == "editor-prepare":
        from .review_evidence import prepare_editor_review
        return prepare_editor_review(a.run, a.blind)
    if a.command == "export": return export_review(a.run)
    if a.command in {"review-packet", "review-collect"}:
        from .human_review import create_packet, collect_packet
        if a.command == "review-packet": return create_packet(a.source, a.out)
        return collect_packet(a.packet, a.response)
    if a.command == "feedback":
        return feedback(a.run, a.item, feedback_text(a), a.reviewer, a.severity, getattr(a, "origin", "human"),
                        expected_sha=getattr(a, "candidate_sha", None))
    if a.command in {"check", "review-result"}:
        context = json.loads((a.run / "context.json").read_text())
        brief = Brief.model_validate(context["brief"])
        draft = Draft.model_validate_json((a.draft if a.command == "check" else a.run / "candidate.json").read_text())
        if a.command == "review-result" and hashlib.sha256((a.run / "candidate.json").read_bytes()).hexdigest() != a.candidate_sha:
            raise ValueError("검토 대상과 현재 문항의 해시가 다릅니다. 현행 문항을 다시 검토하세요.")
        from .authoring_sources import supplied_source_ids
        errors = validate(draft, brief, supplied_source_ids(context), context.get("exam_assignment"))
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
            (a.run / "blind-instructions.md").write_text(review_prompt("blind", brief))
            (a.run / "editorial-instructions.md").write_text(review_prompt("editor", brief))
            from .review_evidence import prepare_review_request
            prepare_review_request(a.run)
            state = "needs_revision" if errors else "awaiting_independent_review"
        else:
            from .review_evidence import load_bound_review, verify_editor_blind_pair, preserve_review_files
            blind, blind_evidence = load_bound_review(a.blind, a.run, "blind")
            editorial, editorial_evidence = load_bound_review(a.editorial, a.run, "editor")
            verify_editor_blind_pair(a.run, a.blind, blind_evidence, a.editorial, editorial_evidence)
            candidate_sha = a.candidate_sha
            if hashlib.sha256((a.run / "candidate.json").read_bytes()).hexdigest() != candidate_sha:
                raise ValueError("검토 결과 확인 중 문항이 바뀌었습니다. 현행 문항을 다시 검토하세요.")
            errors += review_gate(draft, blind, editorial)
            preserve_review_files(a.run, ["manual-review.json"])
            save(a.run / "manual-review.json", {"blind": blind.model_dump(), "editorial": editorial.model_dump(),
                 "errors": errors, "candidate_sha256": a.candidate_sha,
                 "source_paths": {"blind": str(a.blind.resolve()), "editorial": str(a.editorial.resolve())},
                 "evidence": {"blind": blind_evidence, "editorial": editorial_evidence}})
            state = "needs_revision" if errors else "awaiting_human_review"
        save(a.run / "status.json", {"state": state, "human_approved": False, "errors": errors,
                                      "candidate_sha256": candidate_sha})
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
    if a.command == "generate":
        provenance = json.loads((run / "provenance.json").read_text())
        save(run / "provenance.json", {**provenance, "compact_reference_audit": a.compact_reference_audit})
    provider = CodexProvider(a.model, trace_dir=run / "codex-traces") if a.command == "generate" else None
    if provider:
        run_pipeline(run, provider, a.max_revisions,
                     **({'compact_reference_audit': True} if a.compact_reference_audit else {}))
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
