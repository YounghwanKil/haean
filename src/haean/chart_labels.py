"""Place line-chart value labels against rendered lines, markers and labels."""


def place_line_labels(fig, ax, points, fontsize):
    from matplotlib.path import Path
    from matplotlib.transforms import Bbox

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    # Keep the geometry measured here stable during PNG/SVG export.
    fig.set_layout_engine(None)
    paths, markers = [], []
    for line in ax.lines:
        path = line.get_path().transformed(line.get_transform())
        paths.append(Path(path.vertices, path.codes))
        radius = (line.get_markersize() / 2 + 2) * fig.dpi / 72
        markers.extend(Bbox.from_extents(x-radius, y-radius, x+radius, y+radius)
                       for x, y in path.vertices)
    occupied, result = [], []
    candidates = [(0, 8), (0, -8), (0, 18), (0, -18),
                  (12, 8), (-12, 8), (12, -8), (-12, -8)]
    for series, category, x, y in points:
        choices = []
        for order, (dx, dy) in enumerate(candidates):
            text = ax.annotate(f'{y:g}', (x, y), xytext=(dx, dy),
                textcoords='offset points', ha='center',
                va='bottom' if dy > 0 else 'top', fontsize=fontsize)
            box = text.get_window_extent(renderer).expanded(1.08, 1.15)
            hits = sum(p.intersects_bbox(box, filled=False) for p in paths)
            hits += sum(box.overlaps(b) for b in markers + occupied)
            outside = not (ax.bbox.contains(box.x0, box.y0) and ax.bbox.contains(box.x1, box.y1))
            choices.append(((int(outside), hits, order), (dx, dy)))
            text.remove()
        score, (dx, dy) = min(choices)
        text = ax.annotate(f'{y:g}', (x, y), xytext=(dx, dy),
            textcoords='offset points', ha='center',
            va='bottom' if dy > 0 else 'top', fontsize=fontsize)
        occupied.append(text.get_window_extent(renderer).expanded(1.08, 1.15))
        result.append({'series': series, 'category': category, 'value': y,
                       'offset_points': [dx, dy], 'outside_axes': bool(score[0]),
                       'geometry_conflicts': int(score[1])})
    return result
