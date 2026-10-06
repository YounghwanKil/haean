"""Portable review documents. Native HWP layout is intentionally not simulated."""
import html
import json
from pathlib import Path

from .models import Draft


def export_review(run: Path):
    draft = Draft.model_validate_json((run / "candidate.json").read_text())
    state = json.loads((run / "status.json").read_text())["state"]
    problem, solution = [], []
    esc = html.escape
    def para(text):
        return "<p>" + esc(text).replace("\n", "<br>") + "</p>"
    for i, item in enumerate(draft.items, 1):
        from .figures import render_item
        figure_paths = render_item(item, run/'figures'/str(i)) if item.figures else {}
        def figure_html(placement):
            return ''.join(f'<figure><img style="max-width:100%" src="{esc(str(figure_paths[f.id].relative_to(run)))}" alt="{esc(f.title)}"><figcaption>{esc(f.note)}</figcaption></figure>'
                           for f in item.figures if f.placement == placement)
        block = f"<article><h2>{i}. {esc(item.stem)}</h2>" + para(item.passage)
        block += figure_html('passage')
        for table in item.tables:
            block += f"<h3>{esc(table.title)} ({esc(table.unit)})</h3><table><thead><tr>"
            block += "".join(f"<th>{esc(c)}</th>" for c in table.columns) + "</tr></thead><tbody>"
            for row in table.rows:
                block += "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>"
            block += "</tbody></table>" + para(table.note)
        if item.statements: block += "<aside>" + para("\n".join(item.statements)) + "</aside>"
        block += "<ol>" + "".join(f"<li>{esc(o.text)}{figure_html('option_'+str(o.number))}</li>" for o in item.options) + "</ol></article>"
        problem.append(block)
        solution.append(f"<article><h2>{i}. 정답 {item.answer}</h2>" + para(item.explanation) +
                        para(item.commentary) + "<ul>" + "".join(f"<li>{esc(j.target)}: {esc(j.verdict)} — {esc(j.explanation)}</li>" for j in item.judgments) + "</ul></article>")
    for name, blocks in [("questions", problem), ("solutions", solution)]:
        body = """<!doctype html><html lang="ko"><meta charset="utf-8"><title>해안 검토용</title>
<style>body{font-family:serif;max-width:850px;margin:40px auto;line-height:1.8;color:#17212b}article{padding:24px 0;border-bottom:1px solid #bbb;break-inside:avoid}h2{font-size:19px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #777;padding:6px}aside{border:1px solid #aaa;padding:12px}li{padding:5px}header{font-family:sans-serif;color:#555}@media print{body{margin:0}article{break-inside:auto}}</style>"""
        body += "<header>해안 · 검토용 초안 · " + esc(state) + "</header>" + "".join(blocks) + "</html>"
        (run / f"{name}.html").write_text(body, encoding="utf-8")
    return [str(run / "questions.html"), str(run / "solutions.html")]
