"""B2.8 — Notebook/REPL tool for local data analysis with inline charts.

Turns a markdown notebook (prose plus ``python`` fenced cells) into a real,
executed document. Code cells run together in the hardened Python sandbox
(``sandbox_exec.run_python``) with per-cell stdout capture and error isolation;
``chart(...)`` calls emit chart specs that are rendered to inline SVG offline
via :mod:`keel.charts`. Notebooks can be persisted, listed and deleted
(recoverably) in a local state root. No network, external engine or credential
is required.

Honest limits: the sandbox is a Python-level boundary (see
``sandbox_policy.sandbox_status``), not OS-level containment. Cells share one
interpreter across the notebook, so variables persist between cells like a
real REPL; a failure in one cell is isolated and reported, not fatal.
"""

from __future__ import annotations

import html
import json
import re
import secrets
from pathlib import Path

from . import charts
from .sandbox_exec import run_python

_FENCE = re.compile(r"^```(python|py)?\s*\n(.*?)^```\s*$", re.M | re.S)


def parse_notebook(source: str) -> list[dict]:
    """Split notebook source into ordered text/code cells.

    Fenced `` ```python `` / `` ```py `` / plain `` ``` `` blocks are code;
    the intervening prose is text. This supersedes the earlier keyword
    heuristic in ``workbench.notebook_cells``.
    """
    cells: list[dict] = []
    pos = 0
    for match in _FENCE.finditer(source):
        prose = source[pos:match.start()]
        if prose.strip():
            cells.append({"kind": "text", "source": prose.strip()})
        cells.append({"kind": "code", "source": match.group(2).strip()})
        pos = match.end()
    tail = source[pos:]
    if tail.strip():
        cells.append({"kind": "text", "source": tail.strip()})
    return cells


def notebook_cells(source: str) -> list[dict]:
    """Backward-compatible alias used by ``workbench`` and its tests."""
    return parse_notebook(source)


_RUNNER = r'''import io as __io
import json as __json
import contextlib as __ctx

__G = {"__name__": "__main__", "__builtins__": __builtins__}
__charts = []

def __chart(kind, values, labels=None, **opts):
    __charts.append({"kind": str(kind), "values": [float(v) for v in values],
                     "labels": [str(x) for x in labels] if labels else None,
                     "options": opts})

__G["chart"] = __chart
__cells = __CELLS__
__results = []

for __cell in __cells:
    if __cell["kind"] == "text":
        __results.append({"kind": "text", "source": __cell["source"],
                          "outputs": [], "charts": [], "error": None})
        continue
    __buf = __io.StringIO()
    __err = None
    try:
        with __ctx.redirect_stdout(__buf), __ctx.redirect_stderr(__buf):
            exec(compile(__cell["source"], "<cell>", "exec"), __G)
    except BaseException as __exc:
        __err = type(__exc).__name__ + ": " + str(__exc)
    __results.append({"kind": "code", "source": __cell["source"],
                      "outputs": [{"type": "stream", "text": __buf.getvalue()}],
                      "charts": [], "error": __err})

for __r in reversed(__results):
    if __r["kind"] == "code":
        __r["charts"] = __charts
        break

print("__TOKEN__" + __json.dumps({"results": __results}))
'''


def _render_chart(spec: dict, *, width: int = 400, height: int = 200) -> str:
    kind = spec.get("kind", "bar")
    values = spec.get("values", [])
    labels = spec.get("labels")
    opts = spec.get("options") or {}
    width = int(opts.get("width", width))
    height = int(opts.get("height", height))
    if kind in ("sparkline", "line"):
        return charts.sparkline(values, width=width,
                                height=int(opts.get("height", 40)))
    if kind in ("flow", "graph"):
        nodes = [str(v) for v in values]
        edges = [(a, b) for a, b in zip(nodes, nodes[1:])]
        return charts.flow_diagram(nodes, edges, width=width)
    return charts.bar_chart(values, labels, width=width, height=height)


def render_markdown(results: list[dict]) -> str:
    parts: list[str] = []
    for cell in results:
        if cell["kind"] == "text":
            parts.append(cell["source"])
            continue
        parts.append("```python\n" + cell["source"] + "\n```")
        for out in cell.get("outputs", []):
            if out.get("text"):
                parts.append(out["text"].rstrip())
        if cell.get("error"):
            parts.append("**error:** " + cell["error"])
        for spec in cell.get("charts", []):
            parts.append(f"[inline chart: {spec.get('kind', 'bar')}]")
    return "\n\n".join(parts)


def render_html(results: list[dict]) -> str:
    parts: list[str] = []
    for cell in results:
        if cell["kind"] == "text":
            parts.append("<div class='nb-text'>" + html.escape(cell["source"])
                         + "</div>")
            continue
        parts.append("<pre class='nb-code'>" + html.escape(cell["source"])
                     + "</pre>")
        for out in cell.get("outputs", []):
            if out.get("text"):
                parts.append("<pre class='nb-out'>"
                             + html.escape(out["text"].rstrip()) + "</pre>")
        if cell.get("error"):
            parts.append("<pre class='nb-error'>"
                         + html.escape(str(cell["error"])) + "</pre>")
        for spec in cell.get("charts", []):
            parts.append("<div class='nb-chart'>"
                         + _render_chart(spec) + "</div>")
    return "\n".join(parts)


def execute_notebook(source: str, *, timeout_s: float = 15.0) -> dict:
    """Execute a notebook and return structured cells plus rendered views."""
    cells = parse_notebook(source)
    code_cells = [c for c in cells if c["kind"] == "code"]
    token = "__KEEL_NB_" + secrets.token_hex(8) + "__"
    script = (_RUNNER.replace("__CELLS__", json.dumps(cells))
              .replace("__TOKEN__", token))
    result = run_python(script, timeout_s=timeout_s)
    marker = None
    for line in result.stdout.splitlines():
        if line.startswith(token):
            marker = line[len(token):]
            break
    results = cells
    charts_count = 0
    if marker:
        try:
            parsed = json.loads(marker)
            results = parsed.get("results", cells)
            charts_count = sum(len(c.get("charts", [])) for c in results)
        except (ValueError, TypeError):
            pass
    errors = [c["error"] for c in results
              if c.get("kind") == "code" and c.get("error")]
    ok = (not result.timed_out and not errors
          and (not result.stderr.strip() or "sandbox:" not in result.stderr))
    return {
        "ok": ok,
        "cells": results,
        "cell_count": len(cells),
        "code_cell_count": len(code_cells),
        "chart_count": charts_count,
        "errors": errors,
        "timed_out": result.timed_out,
        "sandbox_stderr": result.stderr[:2000],
        "markdown": render_markdown(results),
        "html": render_html(results),
    }


class NotebookStore:
    """Persist notebooks in a local state root with recoverable deletion."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "notebooks"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            raise ValueError("invalid notebook name")
        return self.root / f"{name}.json"

    def save(self, name: str, source: str) -> dict:
        path = self._path(name)
        doc = {"name": name, "source": source, "version": 1}
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return doc

    def load(self, name: str) -> str:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return json.loads(path.read_text(encoding="utf-8"))["source"]

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))

    def delete(self, name: str) -> dict:
        from .trash import move_to_trash

        return move_to_trash(self._path(name))
