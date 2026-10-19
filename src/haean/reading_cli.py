"""Book-based reading production, separate from reasoning/PSAT Briefs."""
from pathlib import Path


def add_parser(subparsers):
    parser = subparsers.add_parser("reading", help="언어이해 지문별 작성·독립 검토·이어하기·회차 조립")
    commands = parser.add_subparsers(dest="reading_command", required=True)
    prepare = commands.add_parser("prepare", help="지문별 계획을 고정하고 작성 패킷 준비; 모델 호출 없음")
    prepare.add_argument("plan", type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    for name, description in (
        ("check", "1지문·3문항 새 버전 등록 및 학생용 입력 분리"),
        ("editor-prepare", "현행 독립 풀이를 고정하고 편집 검토 준비"),
        ("review-result", "현행 지문·풀이와 연결한 편집 검토 결과 등록"),
    ):
        command = commands.add_parser(name, help=description)
        command.add_argument("run", type=Path)
        command.add_argument("--passage", required=True)
        field = {"check": "draft", "editor-prepare": "blind", "review-result": "editorial"}[name]
        command.add_argument("--" + field, required=True, type=Path)
    status = commands.add_parser("status", help="현재 버전과 미완료 세트를 확인해 이어하기; 모델 호출 없음")
    status.add_argument("run", type=Path)
    assemble = commands.add_parser("assemble", help="계획한 모든 세트의 현행 검토를 확인해 book.json 조립")
    assemble.add_argument("run", type=Path)
    assemble.add_argument("--out", required=True, type=Path)


def dispatch(args):
    from . import reading_production as production
    try:
        if args.reading_command == "prepare":
            return production.prepare(args.plan, args.out)
        if args.reading_command == "check":
            return production.check(args.run, args.passage, args.draft)
        if args.reading_command == "editor-prepare":
            return production.editor_prepare(args.run, args.passage, args.blind)
        if args.reading_command == "review-result":
            return production.review_result(args.run, args.passage, args.editorial)
        if args.reading_command == "status":
            return production.status(args.run)
        if args.reading_command == "assemble":
            return production.assemble(args.run, args.out)
    except FileExistsError as exc:
        raise ValueError("기존 언어이해 실행·출력은 보존합니다. 새 --out 경로를 지정하세요.") from exc
    raise ValueError("알 수 없는 언어이해 생산 명령")
