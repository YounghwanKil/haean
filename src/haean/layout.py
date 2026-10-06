import hashlib
from pathlib import Path
from .models import Draft
from .pipeline import save


def package(run: Path, question_template: Path, solution_template: Path):
    draft = Draft.model_validate_json((run / "candidate.json").read_text())
    templates = {}
    for label, p in [("questions", question_template), ("solutions", solution_template)]:
        if not p.is_file() or p.suffix.lower() not in {".hwp", ".hwpx"}:
            raise ValueError("실제 HWP/HWPX 템플릿 경로가 필요합니다")
        templates[label] = {"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    output = run / "layout-manifest.json"
    result = {"version": "haean-layout-v1", "candidate": str((run / "candidate.json").resolve()),
              "candidate_sha256": hashlib.sha256((run / "candidate.json").read_bytes()).hexdigest(),
              "templates": templates, "item_count": len(draft.items),
              "adapter_status": "awaiting_java_interface", "layout_verified": False,
              "tables": [{"item_id": i.id, "count": len(i.tables)} for i in draft.items],
              "required_checks": ["문항·정답 번호", "표·단위·수식", "선지·보기", "글꼴·다단·페이지", "템플릿 대비 렌더 검토"]}
    save(output, result)
    return result
