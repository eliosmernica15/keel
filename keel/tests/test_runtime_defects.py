"""Regression tests for runtime tool/MCP defects found during recovery."""

from __future__ import annotations

from pathlib import Path

from keel.runner import RealTools


def test_list_dir_non_recursive_returns_entries_and_ignores_noise(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "__pycache__").mkdir()

    text, payload = RealTools().invoke("list_dir", {"path": str(tmp_path)})

    assert str(tmp_path / "a.txt") in text
    assert ".git" not in text
    assert "node_modules" not in text
    assert "__pycache__" not in text
    assert payload["numEntries"] == 1
    assert payload["truncated"] is False


def test_list_dir_recursive_applies_same_ignore_rules(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("x", encoding="utf-8")

    _, payload = RealTools().invoke(
        "list_dir", {"path": str(tmp_path), "recursive": True})

    assert any(e.endswith("a.txt") for e in payload["entries"])
    assert not any("node_modules" in e for e in payload["entries"])


def test_session_module_exposes_http_mcp_server_type():
    from keel import session
    from keel.mcp import HttpMcpServer

    assert session.HttpMcpServer is HttpMcpServer
