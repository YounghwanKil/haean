"""Explicit entry point for the staged subject-track integration.

The legacy authoring, wiki and evaluation commands retain their contracts.
This module exposes the audited foundation; it does not claim that the new
generation pipeline or typesetter has been validated.
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


def dispatch(args):
    from .tracks import all_tracks, get
    from .tracks.core.track import Brief
    operation = args.track_command
    if operation == "list":
        return {
            "integration_stage": "foundation",
            "generation_integrated": False,
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
                "새 트랙은 명세·스키마·지침·참고 검색 연결 단계입니다. 출제·평가·조판 완료가 아닙니다.",
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
