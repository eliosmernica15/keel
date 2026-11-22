"""B4.6 / B4.7 — real fleet & observability view data transformations."""

from __future__ import annotations

from keel.views import (cost_per_agent, flame_graph, kanban_board,
                        live_activity, org_chart, prompt_diff, token_waterfall)


def test_kanban_board():
    tasks = [{"id": "a", "status": "todo"}, {"id": "b", "status": "done"},
             {"id": "c", "status": "in_progress"}, {"id": "d", "status": "other"}]
    board = kanban_board(tasks)
    assert board["counts"] == {"todo": 1, "in_progress": 1, "done": 1}
    assert board["unclassified"] == 1
    assert board["completion_pct"] == 33.3


def test_org_chart_nested():
    agents = [
        {"id": "lead", "name": "Lead", "role": "coordinator"},
        {"id": "a", "name": "Alpha", "parent": "lead"},
        {"id": "b", "name": "Beta", "parent": "lead"},
        {"id": "c", "name": "Gamma", "parent": "a"},
        {"id": "orphan", "parent": "missing"},
    ]
    chart = org_chart(agents)
    assert chart["agent_count"] == 5
    assert len(chart["roots"]) == 2  # lead + orphan
    lead = next(r for r in chart["roots"] if r["id"] == "lead")
    assert {c["id"] for c in lead["children"]} == {"a", "b"}
    alpha = next(c for c in lead["children"] if c["id"] == "a")
    assert alpha["children"][0]["id"] == "c"


def test_cost_per_agent():
    usage = [
        {"agent": "a", "input_tokens": 100, "output_tokens": 20, "cost": 0.5},
        {"agent": "a", "input_tokens": 50, "output_tokens": 10, "cost": 0.25},
        {"agent": "b", "input_tokens": 10, "output_tokens": 5, "cost": 0.25},
    ]
    report = cost_per_agent(usage)
    assert report["rows"][0]["agent"] == "a"
    assert report["rows"][0]["turns"] == 2
    assert report["rows"][0]["input_tokens"] == 150
    assert report["total_cost"] == 1.0
    assert abs(sum(r["share_pct"] for r in report["rows"]) - 100) < 0.2


def test_live_activity_sorted_and_limited():
    events = [
        {"ts": "2026-01-01", "kind": "start", "actor": "a"},
        {"ts": "2026-01-03", "kind": "tool", "actor": "b"},
        {"ts": "2026-01-02", "kind": "tool", "actor": "c"},
    ]
    feed = live_activity(events, limit=2)
    assert [e["actor"] for e in feed["timeline"]] == ["b", "c"]
    assert feed["by_kind"] == {"start": 1, "tool": 2}


def test_token_waterfall_svg():
    report = token_waterfall([
        {"label": "t1", "input_tokens": 100, "output_tokens": 20,
         "cached_tokens": 50},
        {"label": "t2", "input_tokens": 200, "output_tokens": 40},
    ])
    assert report["totals"] == {"input": 300, "output": 60, "cached": 50}
    assert report["rows"][0]["total"] == 120
    assert "<svg" in report["svg"]


def test_flame_graph_nesting_and_percentages():
    report = flame_graph([
        {"id": "root", "name": "run", "start": 0, "duration": 10},
        {"id": "child", "name": "tool", "start": 1, "duration": 4,
         "parent": "root"},
        {"id": "grand", "name": "exec", "start": 2, "duration": 2,
         "parent": "child"},
    ])
    assert report["span_count"] == 3
    assert len(report["roots"]) == 1
    root = report["roots"][0]
    assert root["children"][0]["name"] == "tool"
    assert root["children"][0]["children"][0]["name"] == "exec"
    assert root["cumulative_pct"] == 100.0


def test_prompt_diff():
    diff = prompt_diff("line one\nline two\n", "line one\nline changed\nnew\n")
    assert diff["changed"] is True
    assert diff["added"] >= 1 and diff["removed"] >= 1
    assert any(l["kind"] == "added" and l["text"] == "new" for l in diff["lines"])
    assert prompt_diff("same\n", "same\n")["changed"] is False
