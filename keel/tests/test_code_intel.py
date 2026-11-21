"""C4.2/C4.3/C4.4 — local code intelligence."""

from __future__ import annotations

from keel.code_intel import (change_risk, dependency_graph, impacted,
                             scan_symbols, structural_search)


def test_scan_symbols(tmp_path):
    (tmp_path / "mod.py").write_text(
        "def foo(): pass\nclass Bar:\n    pass\n", encoding="utf-8")
    symbols = scan_symbols(tmp_path)
    assert "foo" in symbols["mod"] and "Bar" in symbols["mod"]


def test_dependency_graph_and_impact(tmp_path):
    (tmp_path / "base.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "mid.py").write_text("from base import X\n", encoding="utf-8")
    (tmp_path / "top.py").write_text("from mid import X\n", encoding="utf-8")
    graph = dependency_graph(tmp_path)
    assert "base" in graph["mid"]
    assert "base" in impacted(graph, "mid") or "mid" in graph["top"]
    # top depends on mid which depends on base
    assert "top" in impacted(graph, "base")
    risk = change_risk(graph, ["base"])
    assert risk["risk"] > 0 and "top" in risk["impacted"]


def test_structural_search(tmp_path):
    (tmp_path / "a.py").write_text("MARKER = True\n", encoding="utf-8")
    hits = structural_search(tmp_path, "MARKER")
    assert hits and hits[0]["line"] == 1
