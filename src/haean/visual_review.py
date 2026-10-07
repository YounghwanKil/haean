"""Attach student-visible figure renders to isolated Codex review sessions."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from threading import RLock

from .models import Figure

_RENDER_LOCK = RLock()  # Matplotlib uses process-global font/figure state.


def label_option_image(source: Path, number: int) -> Path:
    """Preserve the full chart and add its answer number to the review attachment."""
    import json
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    receipt = json.loads(source.with_suffix('.json').read_text())
    font = ImageFont.truetype(receipt['font']['path'], 42)
    with Image.open(source) as chart:
        image = ImageOps.expand(chart.convert('RGB'), border=(0, 72, 0, 0), fill='white')
    ImageDraw.Draw(image).text((24, 8), f'({number})', font=font, fill='black')
    target = source.with_name(f'{source.stem}-option-{number}.png')
    image.save(target)
    return target


def review_images(stage, payload, folder: Path):
    with _RENDER_LOCK:
        return _review_images(stage, payload, folder)


def _review_images(stage, payload, folder: Path):
    # Generation and revision remain text/structured-data operations. Never turn
    # arbitrary paths in a retrieved document into CLI image attachments.
    if stage not in {"blind", "editor"}: return [], []
    items = payload.get("items", []) if stage == "blind" else payload.get("draft", {}).get("items", [])
    if not any(item.get("figures") for item in items): return [], []
    from .figures import render_item, option_grid
    paths, manifest = [], []
    for index, item in enumerate(items, 1):
        figures = []
        for data in item.get("figures", []):
            data = {**data, "layout_note": ""}
            if data.get("kind") == "argument": data["note"] = ""
            figures.append(Figure.model_validate(data))
        if not figures: continue
        public = SimpleNamespace(figures=figures)
        directory = folder / f"item-{index:03d}"
        rendered = render_item(public, directory)
        options = [f for f in figures if f.placement.startswith("option_")]
        use_grid = options and all(f.kind == "argument" for f in options)
        attachments = []
        if use_grid:
            grid = option_grid(public, rendered, directory / "option-grid.png")
            attachments.append((grid, options))
        for figure in figures:
            if use_grid and figure in options: continue
            path = rendered[figure.id]
            if figure.placement.startswith('option_'):
                path = label_option_image(path, int(figure.placement[-1]))
            attachments.append((path, [figure]))
        for path, group in attachments:
            paths.append(path)
            manifest.append({"image_index": len(paths), "item_id": item["id"],
                             "figure_ids": [f.id for f in group],
                             "placements": [f.placement for f in group],
                             "file": str(path.relative_to(folder)),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if len(paths) > 20:
        raise ValueError("검토 이미지가 20개를 넘습니다. 문항 묶음을 나누세요. 이미지를 생략하지 않았습니다.")
    return paths, manifest


IMAGE_INSTRUCTIONS = """
첨부 이미지는 아래 문항의 수험생용 도식·그래프를 실제로 렌더한 것이다.
첨부 순서와 문항 ID·그림 ID·배치 위치는 rendered_images에 있다.
개별 그래프 위의 (1)~(5)는 응답 선택지 번호다. HWP에서는 양식의 선택지 번호와 결합한다.
구조 데이터와 실제 이미지의 연결·수치·축·범례·기호·잘림을 함께 확인하라.
이미지에서 구분할 수 없는 핵심 표시는 확인 불가로 보고하라.
이 검토는 PNG 범위이며 HWP/PDF 인쇄 배치나 실제 인쇄 크기를 검증한 것이 아니다.
"""
