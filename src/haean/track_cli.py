"""Explicit entry point for the staged subject-track integration.

The legacy authoring, wiki and evaluation commands retain their contracts.
Staged authoring writes the existing Draft schema directly. Native block
generation and HWPX rendering remain separate integration steps.
"""
from pathlib import Path
import hashlib
import os
import tempfile


def add_parser(subparsers):
    parser = subparsers.add_parser("track", help="과목별 새 설계 명세·지침·참고 색인; 단계적 통합")
    commands = parser.add_subparsers(dest="track_command", required=True)
    commands.add_parser("list", help="과목별 명세와 현재 통합 범위")
    check = commands.add_parser("brief-check", help="JSON 명세의 급수·세트·유형 검사")
    check.add_argument("brief", type=Path)
    schema = commands.add_parser("schema", help="새 트랙의 JSON 스키마")
    schema.add_argument("kind", choices=["brief", "draft", "reference", "query"])
    rules = commands.add_parser("rules", help="해당 과목·단계 지침 조회; 생성 실행 아님")
    rules.add_argument("name")
    rules.add_argument("stage", choices=["material", "design", "writer", "editor", "blind"])
    search = commands.add_parser("ref-search", help="과목·급수·출처 조건을 유지한 읽기 전용 검색")
    search.add_argument("query", type=Path)
    search.add_argument("--index", type=Path, required=True)
    build = commands.add_parser("ref-build", help="출처를 검증한 정제 사례로 별도 새 색인 생성")
    build.add_argument("jsonl", type=Path, nargs="+")
    build.add_argument("--out", type=Path, required=True)
    attach = commands.add_parser("attach", help="기존 prepared run에 과목별 소재·설계 명세 연결")
    attach.add_argument("run", type=Path)
    attach.add_argument("brief", type=Path)
    attach.add_argument("--index", type=Path)
    attach.add_argument("--type-mapping", type=Path, help="기존/트랙 유형명이 다를 때 명시 대응과 이유 JSON")
    generate = commands.add_parser("generate", help="소재·설계 후 기존 문항 형식으로 작성·독립 검토")
    generate.add_argument("run", type=Path)
    generate.add_argument("--model", default="gpt-6-astra")
    generate.add_argument("--max-revisions", type=int, default=2, choices=range(4))
    generate.add_argument("--max-calls", type=int)
    generate.add_argument("--timeout", type=int, default=900)
    manuscript = commands.add_parser("manuscript", help="native 트랙 Draft를 명시적으로 HWPX 원고 JSON으로 변환")
    manuscript.add_argument("brief", type=Path)
    manuscript.add_argument("draft", type=Path)
    manuscript.add_argument("--out", type=Path, required=True)
    manuscript.add_argument("--title", default="")
    manuscript.add_argument("--student-only", action="store_true")


def dispatch(args):
    from .tracks import all_tracks, get
    from .tracks.core.track import Brief
    operation = args.track_command
    if operation == "list":
        return {
            "integration_stage": "foundation_and_staged_legacy_authoring",
            "generation_integrated": False,
            "staged_legacy_generation_integrated": True,
            "typeset_render_verified": False,
            "existing_commands_preserved": True,
            "tracks": [{
                "name": t.name, "label": t.label,
                "grades": list(t.grades), "vocabulary": t.vocab,
                "set_size": t.set_size, "set_required": t.set_required,
                "exam_sizes": {str(g): t.max_items(g) for g in (t.grades or (None,))},
                "typeset_profiles_requested": {str(k): v for k, v in t.typeset_profiles.items()},
                "status": t.status(),
            } for t in all_tracks()],
            "limits": [
                "track generate는 소재·설계를 기존 문항 작성·독립 검토에 연결합니다. native Block Draft 생성은 아직 연결하지 않았습니다.",
                "언어이해 staged 생성은 지원하지 않습니다. 기존 언어이해 파일럿 경로는 유지합니다.",
                "기출 원문·검수 어휘 자료·양식은 배포 코드에 포함하지 않습니다.",
                "이미지 파일 선지는 아직 지원하지 않습니다. 기존 도식·막대·선 그래프만 모델에 있습니다.",
            ],
        }
    if operation == "brief-check":
        brief = Brief.model_validate_json(args.brief.read_text(encoding="utf-8-sig"))
        track = get(brief.track)
        errors = track.check_brief(brief)
        return {"valid": not errors, "errors": errors, "brief": brief.model_dump(),
                "generation_executed": False, "human_approved": False}
    if operation == "schema":
        from .tracks.core.model import Draft
        from .tracks.core.references import RefQuery, RefRecord
        return {"brief": Brief, "draft": Draft, "reference": RefRecord,
                "query": RefQuery}[args.kind].model_json_schema()
    if operation == "attach":
        import json
        from .staged_authoring import attach
        brief = Brief.model_validate_json(args.brief.read_text(encoding="utf-8-sig"))
        mapping = json.loads(args.type_mapping.read_text(encoding="utf-8-sig")) if args.type_mapping else None
        stage = attach(args.run, brief, index_path=args.index, type_mapping=mapping)
        return {"run": str(args.run), "staged": str(stage), "state": "prepared",
                "draft_format": "haean.models.Draft", "generation_executed": False}
    if operation == "generate":
        import json
        from .staged_authoring import run_staged
        from .codex_runtime import CodexProvider
        if args.timeout <= 0:
            raise ValueError("timeout은 양수여야 합니다")
        calls = args.max_calls if args.max_calls is not None else 5 + 3 * args.max_revisions
        if calls < 5:
            raise ValueError("소재·설계·작성·독립 풀이·편집 검토에 최소 5회 호출이 필요합니다")
        if not (args.run / "staged").is_dir():
            raise ValueError("먼저 track attach로 명세를 연결하세요")
        provider = CodexProvider(args.model, max_calls=calls, timeout=args.timeout,
                                 trace_dir=args.run / "codex-traces")
        draft = run_staged(args.run, provider, max_revisions=args.max_revisions)
        status = json.loads((args.run / "status.json").read_text())
        return {"run": str(args.run), "items": [item.id for item in draft.items],
                "state": status["state"], "errors": status.get("errors", []),
                "draft_format": "haean.models.Draft", "human_approved": False,
                "native_layout_verified": False}
    if operation == "manuscript":
        import json
        from .track_typeset import to_manuscript
        from .tracks.core.model import Draft
        brief_bytes, draft_bytes = args.brief.read_bytes(), args.draft.read_bytes()
        brief = Brief.model_validate_json(brief_bytes)
        draft = Draft.model_validate_json(draft_bytes)
        output = to_manuscript(draft, brief, include_solutions=not args.student_only, title=args.title)
        data = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.out.open("xb") as stream:
                stream.write(data)
        except FileExistsError as exc:
            raise ValueError("기존 원고를 덮어쓰지 않습니다. 새 --out 경로를 지정하세요.") from exc
        return {"manuscript": str(args.out), "sha256": hashlib.sha256(data).hexdigest(),
                "brief_sha256": hashlib.sha256(brief_bytes).hexdigest(),
                "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
                "student_only": args.student_only, "native_layout_verified": False,
                "human_approved": False}
    if operation == "rules":
        track = get(args.name)
        instructions = track.rule(args.stage)
        return {"track": track.name, "stage": args.stage, "instructions": instructions,
                "instructions_sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
                "generation_executed": False}
    if operation == "ref-search":
        from .tracks.core.references import ReferenceIndex, RefQuery
        query = RefQuery.model_validate_json(args.query.read_text(encoding="utf-8-sig"))
        get(query.track)
        index = ReferenceIndex(args.index, readonly=True)
        try:
            return index.search(query)
        finally:
            index.db.close()
    if operation == "ref-build":
        from .tracks import NAMES
        from .tracks.core.references import ReferenceIndex
        if args.out.exists():
            raise ValueError("기존 색인을 덮어쓰지 않습니다. 새 --out 경로를 지정하세요.")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".track-index-", dir=args.out.parent) as folder:
            candidate = Path(folder) / "index.sqlite"
            index = ReferenceIndex(candidate)
            try:
                result = index.build(args.jsonl, tracks=NAMES)
            finally:
                index.db.close()
            if not result["errors"]:
                try:
                    os.link(candidate, args.out)
                except FileExistsError as exc:
                    raise ValueError("색인 경로가 이미 존재합니다. 기존 파일은 보존했습니다.") from exc
            return {**result, "index": str(args.out) if not result["errors"] else None,
                    "existing_data_preserved": True}
    raise ValueError(f"알 수 없는 track 명령: {operation}")
