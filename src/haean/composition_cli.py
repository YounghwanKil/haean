"""User-facing commands for optional whole-exam proposals and explicit binding."""
from pathlib import Path


def add_parser(subparsers):
    parser = subparsers.add_parser("compose", help="LEET·PSAT 5급 40문항 / 7급 25문항 회차 설계·배정표 연결")
    commands = parser.add_subparsers(dest="compose_command", required=True)
    design = commands.add_parser("design", help="형식·내용설계 제안; 모델 호출 없음")
    design.add_argument("profile", type=Path)
    design.add_argument("--out", required=True, type=Path)
    design.add_argument("--seed", type=int, default=0)
    design.add_argument("--options", type=Path, help="트랙별 표본 추출 옵션 JSON")
    design.add_argument("--ledger", type=Path, help="로컬 소재 대장 JSON")
    check = commands.add_parser("check", help="설계·코드·입력의 현재 해시와 구조 확인")
    check.add_argument("design", type=Path)
    bind = commands.add_parser("bind", help="문항 ID·유형·난도·세트 대응을 명시한 배정표 연결")
    bind.add_argument("plan", type=Path)
    bind.add_argument("design", type=Path)
    bind.add_argument("mapping", type=Path)
    bind.add_argument("--out", required=True, type=Path)


def dispatch(args):
    from .composition import design, load_design
    from .composition.profiles import read_json, sha, slot_count
    if args.compose_command == "design":
        try:
            return design(args.profile, args.out, seed=args.seed,
                          options=read_json(args.options) if args.options else None, ledger_path=args.ledger)
        except FileExistsError as exc:
            raise ValueError("기존 회차 설계는 보존합니다. 새 --out 경로를 지정하세요.") from exc
    if args.compose_command == "check":
        value = load_design(args.design)
        return {"valid": True, "track": value["track"], "slots": slot_count(value), "validation": value["validation"],
                "quality_verified": False, "human_approved": False}
    if args.compose_command == "bind":
        from .composition_adapter import bind
        try:
            path = bind(args.plan, args.design, args.mapping, args.out)
        except FileExistsError as exc:
            raise ValueError("기존 연결 패킷은 보존합니다. 새 --out 경로를 지정하세요.") from exc
        return {"packet": str(path), "sha256": sha(path), "human_approved": False}
    raise ValueError("알 수 없는 회차 설계 명령")
