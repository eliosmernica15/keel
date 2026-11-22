"""B4.6 / B4.7 — real Fleet and Observability view data transformations.

Turns ordinary fleet/telemetry records into the concrete data structures the
UI views need: a kanban board, an agent org chart, per-agent cost ranking, a
live-activity timeline, a token waterfall (with an offline SVG), a flame graph
and a structured prompt diff. These are deterministic local transformations —
no external service, no rendering engine. The earlier ``fleet_views`` /
``observability_views`` helpers only returned capability flags.
"""

from __future__ import annotations

import difflib
from collections import Counter, defaultdict

from . import charts

KANBAN_COLUMNS = ("todo", "in_progress", "done")


def kanban_board(tasks: list[dict]) -> dict:
    """Group tasks into kanban columns with counts and coverage."""
    buckets: dict[str, list[dict]] = {c: [] for c in KANBAN_COLUMNS}
    other = 0
    for task in tasks or []:
        status = str(task.get("status", "todo"))
        if status in buckets:
            buckets[status].append(task)
        else:
            other += 1
    columns = [
        {"id": c, "title": c.replace("_", " ").title(),
         "count": len(buckets[c]), "tasks": buckets[c]}
        for c in KANBAN_COLUMNS]
    total = sum(len(v) for v in buckets.values())
    return {
        "columns": columns,
        "counts": {c["id"]: c["count"] for c in columns},
        "total": total,
        "unclassified": other,
        "completion_pct": round(100 * len(buckets["done"]) / total, 1)
        if total else 0.0,
    }


def org_chart(agents: list[dict]) -> dict:
    """Build a nested reporting tree from agents carrying a ``parent`` id."""
    nodes: dict[str, dict] = {}
    for agent in agents or []:
        aid = str(agent.get("id", ""))
        if not aid:
            continue
        nodes[aid] = {
            "id": aid,
            "name": str(agent.get("name", aid)),
            "role": str(agent.get("role", "agent")),
            "parent": agent.get("parent"),
            "children": [],
        }
    roots: list[dict] = []
    for aid, node in nodes.items():
        parent = node["parent"]
        if parent and str(parent) in nodes and str(parent) != aid:
            nodes[str(parent)]["children"].append(node)
        else:
            roots.append(node)
    return {"roots": roots, "agent_count": len(nodes)}


def cost_per_agent(usage: list[dict]) -> dict:
    """Rank agents by total cost, with token totals and share of spend."""
    totals: dict[str, dict] = defaultdict(
        lambda: {"agent": "", "input_tokens": 0, "output_tokens": 0,
                 "cost": 0.0, "turns": 0})
    for row in usage or []:
        agent = str(row.get("agent", "unknown"))
        entry = totals[agent]
        entry["agent"] = agent
        entry["input_tokens"] += int(row.get("input_tokens", 0) or 0)
        entry["output_tokens"] += int(row.get("output_tokens", 0) or 0)
        entry["cost"] += float(row.get("cost", 0.0) or 0.0)
        entry["turns"] += 1
    rows = sorted(totals.values(), key=lambda e: e["cost"], reverse=True)
    grand = sum(e["cost"] for e in rows)
    for entry in rows:
        entry["cost"] = round(entry["cost"], 6)
        entry["share_pct"] = round(100 * entry["cost"] / grand, 1) if grand else 0.0
    return {"rows": rows, "total_cost": round(grand, 6), "agents": len(rows)}


def live_activity(events: list[dict], *, limit: int = 50) -> dict:
    """Return a newest-first activity timeline and per-kind counts."""
    ordered = sorted(events or [], key=lambda e: str(e.get("ts", "")),
                     reverse=True)[:max(1, int(limit))]
    counts = Counter(str(e.get("kind", "event")) for e in events or [])
    return {"timeline": ordered, "count": len(ordered),
            "by_kind": dict(sorted(counts.items()))}


def token_waterfall(turns: list[dict]) -> dict:
    """Per-turn input/output/cached token breakdown plus an inline SVG."""
    rows = []
    for turn in turns or []:
        inp = int(turn.get("input_tokens", 0) or 0)
        out = int(turn.get("output_tokens", 0) or 0)
        cached = int(turn.get("cached_tokens", 0) or 0)
        rows.append({
            "label": str(turn.get("label", "turn")),
            "input_tokens": inp, "output_tokens": out,
            "cached_tokens": cached, "total": inp + out,
        })
    totals = {
        "input": sum(r["input_tokens"] for r in rows),
        "output": sum(r["output_tokens"] for r in rows),
        "cached": sum(r["cached_tokens"] for r in rows),
    }
    svg = charts.bar_chart([r["total"] for r in rows],
                           [r["label"] for r in rows])
    return {"rows": rows, "totals": totals, "svg": svg}


def flame_graph(spans: list[dict]) -> dict:
    """Nest overlapping spans by parent to build a flame-graph tree."""
    items = sorted((dict(s) for s in (spans or [])),
                   key=lambda s: (float(s.get("start", 0)),
                                  -float(s.get("duration", 0))))
    by_id: dict[str, dict] = {}
    parent_of: dict[str, object] = {}
    roots: list[dict] = []
    for index, span in enumerate(items):
        sid = str(span.get("id", index))
        node = {
            "id": sid, "name": str(span.get("name", "span")),
            "start": float(span.get("start", 0)),
            "duration": float(span.get("duration", 0)),
            "children": [],
        }
        by_id[sid] = node
        parent_of[sid] = span.get("parent")
    for sid, node in by_id.items():
        parent = parent_of[sid]
        if parent is not None and str(parent) in by_id and str(parent) != sid:
            by_id[str(parent)]["children"].append(node)
        else:
            roots.append(node)

    def cumulative(n: dict) -> float:
        return n["duration"] + sum(cumulative(c) for c in n["children"])

    total = sum(cumulative(r) for r in roots) or 1.0

    def width(n: dict) -> dict:
        n["self_pct"] = round(100 * n["duration"] / total, 2)
        n["cumulative_pct"] = round(100 * cumulative(n) / total, 2)
        for c in n["children"]:
            width(c)
        return n

    return {"roots": [width(r) for r in roots],
            "total_duration": round(total, 3), "span_count": len(items)}


def prompt_diff(before: str, after: str, *, context: int = 2) -> dict:
    """Structured line diff of two prompts with added/removed counts."""
    a = (before or "").splitlines()
    b = (after or "").splitlines()
    lines: list[dict] = []
    for line in difflib.unified_diff(a, b, n=context, lineterm=""):
        if line.startswith(("---", "+++")):
            continue
        kind = "added" if line.startswith("+") else (
            "removed" if line.startswith("-") else "context")
        lines.append({"kind": kind, "text": line[1:] if line[:1] in "+- " else line})
    return {
        "lines": lines,
        "added": sum(1 for l in lines if l["kind"] == "added"),
        "removed": sum(1 for l in lines if l["kind"] == "removed"),
        "changed": any(l["kind"] in ("added", "removed") for l in lines),
    }
