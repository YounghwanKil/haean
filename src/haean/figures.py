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


def chart_geometry(figures):
    """One numeric scale for comparable option charts; reject conflicting explicit axes."""
    explicit = {(getattr(f, 'y_min', None), getattr(f, 'y_max', None), tuple(getattr(f, 'y_ticks', [])))
                for f in figures if getattr(f, 'y_min', None) is not None}
    if len(explicit)>1: raise ValueError('그래프 선택지의 명시 축 범위·눈금이 다릅니다')
    if explicit:
        low, high, ticks = next(iter(explicit))
    else:
        from matplotlib.ticker import MaxNLocator
        values=[v for f in figures for series in f.series for v in series.values]
        low, high=min(0,min(values)),max(0,max(values))
        if low==high: high=low+1
        ticks=MaxNLocator(nbins=5).tick_values(low,high).tolist()
        low,high=ticks[0],ticks[-1]
    if any(not low <= v <= high for f in figures for series in f.series for v in series.values):
        raise ValueError('공통 그래프 축 밖의 수치가 있습니다')
    return {'y_min':low,'y_max':high,'y_ticks':list(ticks)}


def configure_font(figure):
    """Use team fonts or an installed Korean font; never silently emit tofu."""
    import re
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    root = Path(__file__).resolve().parents[2]
    inventory = root/'data/source-audit/selected-fonts.json'
    if inventory.exists():
        for entry in json.loads(inventory.read_text()):
            if 'NanumGothic' in entry['names'] and Path(entry['path']).exists():
                font_manager.fontManager.addfont(entry['path'])
                name = font_manager.FontProperties(fname=entry['path']).get_name()
                plt.rcParams['font.family'] = name
                return {'family': name, 'path': entry['path']}
    labels = [figure.title, figure.x_label, figure.y_label, *figure.categories,
              *(s.name for s in figure.series), *(n.label for n in figure.nodes)]
    if figure.kind != 'argument': labels.append(figure.note)
    if re.search(r'[\u1100-\u11ff\u3130-\u318f\u3200-\u32ff\u4e00-\u9fff\uac00-\ud7a3]', ''.join(labels)):
        for family in ['NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR', 'AppleGothic', 'Malgun Gothic']:
            try: path = font_manager.findfont(family, fallback_to_default=False)
            except ValueError: continue
            plt.rcParams['font.family'] = family
            return {'family': family, 'path': path}
        raise ValueError('한국어 그래프 폰트가 없습니다. NanumGothic 또는 Noto Sans CJK KR을 설치하세요. Linux: sudo apt install fonts-nanum')
    plt.rcParams['font.family'] = 'DejaVu Sans'
    return {'family': 'DejaVu Sans', 'path': font_manager.findfont('DejaVu Sans')}


def render(figure: Figure, out: Path, geometry=None, show_title=True):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    font = configure_font(figure)
    plt.rcParams['axes.unicode_minus'] = False
    option = figure.placement.startswith('option_')
    numeric_option=option and figure.kind!='argument'
    size=(5.2,2.4) if numeric_option else (2.6,2.6) if option else (5.2,3.6)
    fig, ax = plt.subplots(figsize=size, constrained_layout=True)
    if figure.kind == 'argument':
        from .argument_layout import layout, draw
        argument_positions(figure)  # Refuse cycles before requesting a layout.
        geometry = geometry or layout([figure])
        draw(ax, figure, geometry)
    else:
        x = list(range(len(figure.categories)))
        for index, series in enumerate(figure.series):
            points=x
            if figure.kind == 'bar':
                width = .8/len(figure.series)
                points=[v-.4+width*(index+.5) for v in x]
                ax.bar(points, series.values, width=width,
                       label=series.name, color=str(.25+.6*index/max(1,len(figure.series)-1)), edgecolor='black')
            else: ax.plot(x, series.values, marker=['o','s','^','D'][index%4],
                          linestyle=['-','--',':','-.'][index%4], color='black', label=series.name)
            if getattr(figure,'show_values',False):
                for xpos,value in zip(points,series.values):
                    ax.annotate(f'{value:g}',(xpos,value),xytext=(0,5),textcoords='offset points',ha='center',fontsize=12 if numeric_option else 10)
        ax.set_xticks(x, figure.categories); ax.set_xlabel(figure.x_label,fontsize=12 if numeric_option else 10); ax.set_ylabel(figure.y_label,fontsize=12 if numeric_option else 10)
        ax.tick_params(labelsize=12 if numeric_option else 10)
        if numeric_option:
            ax.legend(fontsize=11,loc='lower center',bbox_to_anchor=(.5,1.02),ncol=min(3,len(figure.series)),frameon=False)
        else: ax.legend(fontsize=9,loc='upper right')
        ax.spines[['top','right']].set_visible(False)
        geometry=geometry or chart_geometry([figure])
        if geometry['y_ticks']: ax.set_yticks(geometry['y_ticks'])
        ax.set_ylim(geometry['y_min'],geometry['y_max'])
    if figure.title and show_title:
        import textwrap
        ax.set_title('\n'.join(textwrap.wrap(figure.title, 14 if option else 30)), fontsize=11)
    if figure.note and figure.kind != 'argument':
        import textwrap
        fig.supxlabel('\n'.join(textwrap.wrap(figure.note, 58)), fontsize=8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=220); fig.savefig(out.with_suffix('.svg')); plt.close(fig)
    receipt = {'figure': figure.model_dump(), 'png': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
               'visual_verified': False, 'geometry': geometry, 'font': font,
               'nonprinted_layout_note': getattr(figure,'layout_note','') or (figure.note if figure.kind == 'argument' else None),
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
    charts=defaultdict(list)
    for f in item.figures:
        if f.kind!='argument' and f.placement.startswith('option_'):
            charts[(f.kind,tuple(f.categories),f.x_label,f.y_label)].append(f)
    scales={f.id:chart_geometry(group) for group in charts.values() for f in group}
    return {f.id: render(f, Path(folder)/f'figure-{index:02d}.png',
                        geometry if f in arguments else scales.get(f.id),
                        show_title=not f.placement.startswith('option_'))
            for index, f in enumerate(item.figures, 1)}


def option_grid(item, paths, out):
    import matplotlib.pyplot as plt
    from PIL import Image
    figures = sorted((f for f in item.figures if f.placement.startswith('option_')), key=lambda f: f.placement)
    if not figures: return None
    columns=1 if all(f.kind!='argument' for f in figures) else 2
    rows = (len(figures)+columns-1)//columns
    fig, axes = plt.subplots(rows, columns, figsize=(5.2, rows*(2.4 if columns==1 else 2.6)), squeeze=False, constrained_layout=True)
    for ax in axes.flat: ax.axis('off')
    for ax, data in zip(axes.flat, figures):
        ax.imshow(Image.open(paths[data.id]));ax.set_title('①②③④⑤'[int(data.placement[-1])-1], loc='left')
    out = Path(out);fig.savefig(out, dpi=220);plt.close(fig)
    return out
