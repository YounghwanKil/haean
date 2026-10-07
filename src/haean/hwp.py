"""Fill an existing HWP master with hwplib; inspect through pinned hwp-cli."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .models import Draft
from .pipeline import save

ROOT = Path(__file__).resolve().parents[2]


def shared_layout(items, start=1):
    """Collapse only a complete adjacent pair with identical shared text/tables."""
    groups = {}
    for number, item in enumerate(items, start):
        if item.shared_passage_id:
            groups.setdefault(item.shared_passage_id, []).append((number, item))
    result = {}
    for identifier, group in groups.items():
        if len(group) == 1: continue  # A single-item review still prints all its context.
        if len(group) != 2 or group[1][0] != group[0][0]+1:
            raise ValueError('공통지문 양식은 인접한 두 문항이 필요합니다: '+identifier)
        left, right = group[0][1], group[1][1]
        if left.passage != right.passage or left.tables != right.tables:
            raise ValueError('공통지문·표 불일치: '+identifier)
        result[group[0][0]] = {'first': True, 'pair': [group[0][0], group[1][0]], 'id': identifier}
        result[group[1][0]] = {'first': False, 'pair': [group[0][0], group[1][0]], 'id': identifier}
    return result


def execute(*args, timeout=120):
    binary = ROOT / 'data/bin/hwp'
    if not binary.is_file(): raise ValueError('먼저 ./haean setup-layout 을 실행하세요')
    process = subprocess.run([str(binary), *map(str, args)], capture_output=True, text=True,
                             timeout=timeout, env={**os.environ, 'HWP_FONT_DIR': str(ROOT / 'data/fonts')})
    if process.returncode: raise RuntimeError(process.stderr[-4000:] or process.stdout[-4000:])
    return process.stdout


def java_tool(name, *args):
    import shutil
    java = shutil.which('java')
    mac_java = Path('/opt/homebrew/opt/openjdk/bin/java')
    if mac_java.exists(): java = str(mac_java)
    if not java or not (ROOT / 'data/bin/hwplib-1.1.11.jar').exists():
        raise ValueError('JDK와 ./haean setup-layout 설치가 필요합니다')
    cp = os.pathsep.join([str(ROOT / 'data/bin/hwplib-1.1.11.jar'), str(ROOT / 'data/bin')])
    p = subprocess.run([java, '-cp', cp, name, *map(str, args)], capture_output=True, text=True, timeout=120)
    if p.returncode: raise RuntimeError(p.stderr[-3000:])


def fill_template(runs: list[Path], template: Path, output: Path, title: str, start=1, kind="questions", total_pages=None, page_starts=None):
    """Fill an existing 40-slot blank master. Missing slots stay explicitly pending."""
    import base64
    if kind not in {'questions', 'solutions'}: raise ValueError('지원되지 않는 양식 종류')
    if total_pages is not None and (kind != 'questions' or not 1 <= total_pages <= 999):
        raise ValueError('전체 쪽 수 보정은 문제지의 1–999쪽만 지원합니다')
    if not title.strip(): raise ValueError('시험지 제목이 필요합니다')
    if output.exists(): raise ValueError('기존 출력은 덮어쓰지 않습니다. 새 출력 경로를 지정하세요')
    if output.resolve() == template.resolve(): raise ValueError('원본 템플릿을 덮어쓸 수 없습니다')
    items, briefs, versions = [], [], []
    for run in runs:
        items += Draft.model_validate_json((run / 'candidate.json').read_text()).items
        briefs.append(json.loads((run / 'brief.json').read_text()))
        versions.append({'run': str(run.resolve()), 'candidate_sha256': hashlib.sha256((run / 'candidate.json').read_bytes()).hexdigest()})
    if not items or start < 1 or start + len(items) - 1 > 40: raise ValueError('1–40번 슬롯 범위가 필요합니다')
    if len({(b['exam'], b['subject']) for b in briefs}) != 1: raise ValueError('다른 시험·과목을 한 시험지에 섞을 수 없습니다')
    shared = shared_layout(items, start) if kind == 'questions' else {}
    page_starts = sorted(set(page_starts or []))
    if page_starts and (kind != 'questions' or any(n <= 1 or n < start or n >= start+len(items) for n in page_starts)):
        raise ValueError('새 쪽 시작은 출력에 포함된 2번 이후 문제에만 지정할 수 있습니다')
    if any(n in shared and not shared[n]['first'] for n in page_starts):
        raise ValueError('공통지문의 두 번째 문항만 새 쪽으로 분리할 수 없습니다')
    output.parent.mkdir(parents=True, exist_ok=True)
    ir = output.with_suffix('.template.json')
    execute('convert', template.resolve(), '--to', 'json', '-o', ir)
    doc = json.loads(ir.read_text())
    styles = {s['name']: i for i, s in enumerate(doc['header']['styles'])}
    required = ['문제', '박스내용(들여쓰기)', '보기내용(내어쓰기)', '선택지', '표-가운데'] if kind == 'questions' else ['글 주제', '정답원문자', '해설정보표내부', '정오판단_설명', '정오판단_선지', '코멘트내용 8pt']
    for name in required:
        if name not in styles: raise ValueError('템플릿 스타일 없음: '+name)
    enc = lambda t: base64.b64encode(t.encode()).decode()
    operations = ['R\t'+enc('2026학년도 시대인재 LEET 시험지명 X회')+'\t'+enc(title),
                  'R\t'+enc('추리논증')+'\t'+enc(briefs[0]['subject'])]
    if kind == 'questions' and briefs[0]['exam'].startswith('psat'):
        operations.append('R\t'+enc('제2교시')+'\t'+enc('모의고사'))
    if total_pages is not None: operations.append('N\t'+str(total_pages))
    def op(code, slot, style, value, *extra):
        operations.append('\t'.join([code, str(slot), str(styles[style]), enc(value), *map(str, extra)]))
    if kind == 'solutions':
        operations.append('R\t'+enc('2027학년도 시대인재 LEET 시험지명 X회')+'\t'+enc(title))
    for slot, item in enumerate(items, start):
        if kind == 'solutions':
            op('H', slot, '글 주제', item.topic)
            op('A', slot, '정답원문자', '①②③④⑤'[item.answer-1])
            op('M', slot, '해설정보표내부', '\x1f'.join([item.difficulty, item.domain, item.item_type]))
            op('T', slot, '정오판단_설명', item.explanation)
            for judgment in item.judgments:
                label = '①②③④⑤'[int(judgment.target)-1] if judgment.target in {'1','2','3','4','5'} else judgment.target
                op('T', slot, '정오판단_선지', label + ' (' + judgment.verdict + ')')
                op('T', slot, '정오판단_설명', judgment.explanation)
            # Commentary can contain source corrections and reviewer history.
            # Keep it in candidate.json, not the student-facing solution.
            continue
        group = shared.get(slot)
        if group and group['first']:
            a, b = group['pair']
            op('J', slot, '문제', f'[{a}~{b}] 다음 글과 자료를 읽고 물음에 답하시오.' if item.tables else f'[{a}~{b}] 다음 글을 읽고 물음에 답하시오.')
            op('Q', slot, '문제', item.stem)
        else:
            op('S', slot, '문제', item.stem)
        if group and not group['first']:
            op('X', slot, '박스내용(들여쓰기)', '', 'column' if any(f.placement in {'passage','statements'} for f in item.figures) else 'flow')
        else:
            op('P', slot, '박스내용(들여쓰기)', item.passage + ''.join('\n'+t.title+' ('+t.unit+')'+('\n'+t.note if t.note else '') for t in item.tables))
        op('B', slot, '보기내용(내어쓰기)', '\n'.join(item.statements))
        opts = [('①②③④⑤'[o.number-1] if o.text.strip() == '①②③④⑤'[o.number-1] else f'{"①②③④⑤"[o.number-1]} {o.text}') for o in item.options]
        rows = ['\t'.join(opts[:3]), '\t'.join(opts[3:])] if max(map(len, opts)) < 18 else opts
        diagram_only=all(o.text.strip() == '①②③④⑤'[o.number-1] for o in item.options) and {f.placement for f in item.figures if f.placement.startswith('option_')} == {f'option_{n}' for n in range(1,6)}
        op('O', slot, '선택지', '\x1e'.join(rows), 'diagram_only' if diagram_only else 'text')
        for table in item.tables:
            if group and not group['first']: continue
            values = [str(v) for row in [table.columns, *table.rows] for v in row]
            if any('\x1f' in v for v in values): raise ValueError('표 셀에 예약 구분자가 있습니다')
            op('G', slot, '표-가운데', '\x1f'.join(values), len(table.columns))
        if item.figures:
            from .figures import render_item, option_grid
            folder = output.parent/(output.stem+'-figures')/str(slot)
            paths = render_item(item, folder)
            for figure in item.figures:
                if figure.placement in {'passage', 'statements'}: op('I', slot, '표-가운데', str(paths[figure.id].resolve()), figure.placement)
            grid = option_grid(item, paths, folder/'options.png')
            if grid: op('I', slot, '표-가운데', str(grid.resolve()), 'options')
    operations.extend('D\t'+str(n) for n in page_starts)
    spec = output.with_suffix('.fill.tsv'); spec.write_text('\n'.join(operations)+'\n')
    java_tool('HaeanFill' if kind == 'questions' else 'HaeanSolutions', template.resolve(), spec.resolve(), output.resolve())
    reread = output.with_suffix('.txt'); execute('convert', output, '-o', reread)
    content = ''.join(reread.read_text().split())
    missing = []
    for item in items:
        values = [item.stem, item.passage, *item.statements, *[o.text for o in item.options],
                  *[v for t in item.tables for row in [t.columns, *t.rows] for v in row]]
        if kind == 'solutions': values = [item.explanation, *[j.explanation for j in item.judgments]]
        if any(''.join(v.split()) not in content for v in values): missing.append(item.id)
    if missing: raise ValueError('출력 재읽기에서 내용 누락: '+str(missing))
    result = {'engine': 'hwplib 1.1.11', 'template': str(template.resolve()),
              'template_sha256': hashlib.sha256(template.read_bytes()).hexdigest(), 'inputs': versions,
              'hwp': str(output), 'kind': kind, 'title': title, 'subject': briefs[0]['subject'],
              'filled_slots': list(range(start, start+len(items))), 'capacity': 40,
              'answer_key': {str(n): item.answer for n, item in enumerate(items, start)},
              'answer_grid_and_boxes_reread_verified': kind == 'solutions',
              'editorial_commentary_included': False,
              'printed_total_pages': total_pages if total_pages is not None else (20 if kind == 'questions' else None),
              'page_start_slots': page_starts,
              'native_page_count_verified': False,
              'shared_passage_pairs': [s['pair'] for s in shared.values() if s['first']],
              'figure_count': sum(len(i.figures) for i in items), 'figures_visually_verified': False,
              'unfilled_slots': [i for i in range(1,41) if i not in range(start,start+len(items))],
              'native_hancom_verified': False, 'layout_verified': False, 'delivery_ready': False,
              'note': '기존 40문항 양식에 내용 삽입. 미작성 슬롯은 남아 있으며 7급 25문항/브릿지20 회차 확정본이 아님.'}
    save(output.with_suffix('.receipt.json'), result)
    return result
