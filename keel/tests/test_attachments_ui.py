"""A1.9 — composer image paste/drag and fuzzy @file search."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import keel.webapp as webapp

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "site" / "ui" / "app.js"
STYLE = ROOT / "site" / "ui" / "style.css"


def test_fuzzy_match_is_subsequence():
    assert webapp._fuzzy_match("rdme", "README.md")
    assert webapp._fuzzy_match("apjs", "app.js")
    assert not webapp._fuzzy_match("zzz", "app.js")


def test_search_files_finds_project_files(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    found = webapp._search_files("app", limit=10)
    assert "src/app.py" in found
    assert all(not name.startswith(".git/") for name in found)


def test_composer_paste_and_drop_wired():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'addEventListener("paste"' in js
    assert 'addEventListener("drop"' in js
    assert "clipboardData" in js and "dataTransfer" in js
    assert "/api/files/search" in js
    assert "function insertAtFile" in js


def test_css_has_drag_and_at_menu_styles():
    css = STYLE.read_text(encoding="utf-8")
    assert ".composer.drag-over" in css
    assert ".at-menu" in css


def test_app_js_syntax():
    result = subprocess.run(
        ["node", "--check", str(APP_JS)], cwd=ROOT,
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
