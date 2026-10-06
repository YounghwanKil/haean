"""Render the same structured graph data supplied to independent solvers."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from .models import Figure


def argument_positions(figure):
    levels = {n.id: 0 for n in figure.nodes}
    for _ in figure.nodes:
        changed = False
        for edge in figure.edges:
            level = max(levels[s] for s in edge.sources)+1
            if level > levels[edge.target]: levels[edge.target] = level; changed = True
        if not changed: break
    if changed: raise ValueError('순환 논증 도식은 자동 배치할 수 없습니다')
    layers = defaultdict(list)
    for node in figure.nodes: layers[levels[node.id]].append(node)
    return {node.id:((i+1)/(len(nodes)+1),-level)
            for level,nodes in layers.items() for i,node in enumerate(nodes)}


def render(figure: Figure, out: Path, geometry=None, show_title=True):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    root = Path(__file__).resolve().parents[2]
    inventory = root/'data/source-audit/selected-fonts.json'
    if inventory.exists():
        for entry in json.loads(inventory.read_text()):
            if 'NanumGothic' in entry['names'] and Path(entry['path']).exists():
                font_manager.fontManager.addfont(entry['path'])
                plt.rcParams['font.family'] = font_manager.FontProperties(fname=entry['path']).get_name()
                break
    plt.rcParams['axes.unicode_minus'] = False
    option = figure.placement.startswith('option_')
    fig, ax = plt.subplots(figsize=(2.6, 2.6) if option else (5.2, 3.6), constrained_layout=True)
    if figure.kind == 'argument':
        from .argument_layout import layout, draw
        argument_positions(figure)  # Refuse cycles before requesting a layout.
        geometry = geometry or layout([figure])
        draw(ax, figure, geometry)
    else:
        x = list(range(len(figure.categories)))
        for index, series in enumerate(figure.series):
            if figure.kind == 'bar':
                width = .8/len(figure.series)
                ax.bar([v-.4+width*(index+.5) for v in x], series.values, width=width,
                       label=series.name, color=str(.25+.6*index/max(1,len(figure.series)-1)), edgecolor='black')
            else: ax.plot(x, series.values, marker=['o','s','^','D'][index%4],
                          linestyle=['-','--',':','-.'][index%4], color='black', label=series.name)
        ax.set_xticks(x, figure.categories); ax.set_xlabel(figure.x_label); ax.set_ylabel(figure.y_label)
        ax.legend(fontsize=8); ax.spines[['top','right']].set_visible(False)
        if all(v >= 0 for s in figure.series for v in s.values): ax.set_ylim(bottom=0)
    if figure.title and show_title: ax.set_title(figure.title, fontsize=11)
    if figure.note and figure.kind != 'argument':
        import textwrap
        fig.supxlabel('\n'.join(textwrap.wrap(figure.note, 58)), fontsize=8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=220); fig.savefig(out.with_suffix('.svg')); plt.close(fig)
    receipt = {'figure': figure.model_dump(), 'png': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
               'visual_verified': False, 'geometry': geometry,
               'nonprinted_layout_note': figure.note if figure.kind == 'argument' else None,
               'note': '지지: 실선 화살표, 반박: 점선 막대 끝. 서로 다른 결합점은 별도 점. 시각 검토 전.'}
    out.with_suffix('.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    return out


def render_item(item, folder):
    arguments = [f for f in item.figures if f.kind=='argument' and f.placement.startswith('option_')]
    geometry = None
    if arguments:
        from .argument_layout import layout
        for figure in arguments: argument_positions(figure)
        geometry = layout(arguments)
    return {f.id: render(f, Path(folder)/f'figure-{index:02d}.png',
                        geometry if f in arguments else None,
                        show_title=not f.placement.startswith('option_'))
            for index, f in enumerate(item.figures, 1)}


def option_grid(item, paths, out):
    import matplotlib.pyplot as plt
    from PIL import Image
    figures = sorted((f for f in item.figures if f.placement.startswith('option_')), key=lambda f: f.placement)
    if not figures: return None
    rows = (len(figures)+1)//2
    fig, axes = plt.subplots(rows, 2, figsize=(5.2, rows*2.6), squeeze=False, constrained_layout=True)
    for ax in axes.flat: ax.axis('off')
    for ax, data in zip(axes.flat, figures):
        ax.imshow(Image.open(paths[data.id]));ax.set_title('①②③④⑤'[int(data.placement[-1])-1], loc='left')
    out = Path(out);fig.savefig(out, dpi=220);plt.close(fig)
    return out
