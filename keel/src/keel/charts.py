"""Offline diagram and chart rendering (B2.11, C13.5).

Produces SVG directly with the standard library — Mermaid-style flow diagrams,
bar charts and sparklines — for the offline documentation/observability views.
No browser or external renderer is required.
"""

from __future__ import annotations

import html


def _svg(width: int, height: int, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">{body}</svg>')


def bar_chart(values: list[float], labels: list[str] | None = None, *,
              width: int = 400, height: int = 200) -> str:
    if not values:
        return _svg(width, height, "")
    maximum = max(1.0, max(values))
    count = len(values)
    gap = width / max(1, count)
    bar_width = gap * 0.7
    parts = []
    for index, value in enumerate(values):
        bar_height = (value / maximum) * (height - 40)
        x = index * gap + (gap - bar_width) / 2
        y = height - 20 - bar_height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" fill="#6fe3b0"/>')
        if labels and index < len(labels):
            parts.append(
                f'<text x="{x + bar_width / 2:.1f}" y="{height - 5}" '
                f'font-size="9" text-anchor="middle">'
                f'{html.escape(str(labels[index]))}</text>')
    return _svg(width, height, "".join(parts))


def sparkline(values: list[float], *, width: int = 120,
              height: int = 30) -> str:
    if not values:
        return _svg(width, height, "")
    minimum, maximum = min(values), max(values)
    span = maximum - minimum or 1.0
    step = width / max(1, len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - 2 - ((value - minimum) / span) * (height - 4):.1f}"
        for i, value in enumerate(values))
    return _svg(width, height,
                f'<polyline points="{points}" fill="none" stroke="#7aa2f7" '
                f'stroke-width="2"/>')


def flow_diagram(nodes: list[str], edges: list[tuple[str, str]], *,
                 width: int = 400, node_height: int = 30) -> str:
    parts = []
    positions = {name: 20 + i * (node_height + 10)
                 for i, name in enumerate(nodes)}
    for name, y in positions.items():
        parts.append(
            f'<rect x="20" y="{y}" width="140" height="{node_height}" '
            f'rx="6" fill="#292e3d" stroke="#6fe3b0"/>'
            f'<text x="90" y="{y + 19}" font-size="11" fill="#fff" '
            f'text-anchor="middle">{html.escape(name)}</text>')
    for source, target in edges:
        if source in positions and target in positions:
            y1 = positions[source] + node_height
            y2 = positions[target]
            parts.append(
                f'<line x1="90" y1="{y1}" x2="90" y2="{y2}" '
                f'stroke="#888" stroke-width="1.5" marker-end="url(#arrow)"/>')
    defs = ('<defs><marker id="arrow" markerWidth="6" markerHeight="6" '
            'refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" '
            'fill="#888"/></marker></defs>')
    height = max(60, 40 + len(nodes) * (node_height + 10))
    return _svg(width, height, defs + "".join(parts))
