"""C4.4 — real AST codemods with preview."""

from __future__ import annotations

from functools import partial

from keel.codemod import apply, preview, rename_symbol, replace_call


def test_rename_symbol():
    source = "def old(x):\n    return old(x)\n\nvalue = old(1)\n"
    result = rename_symbol(source, "old", "new")
    assert "def new" in result and "new(x)" in result
    assert "old" not in result


def test_replace_call():
    result = replace_call("x = len(items)\n", "len", "count")
    assert "count(items)" in result


def test_preview_and_apply(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text("def foo():\n    return foo()\n", encoding="utf-8")
    transform = partial(rename_symbol, old="foo", new="bar")
    view = preview(path, transform)
    assert view["changed"] is True and "def bar" in view["diff"]
    assert "def foo" in path.read_text()  # preview does not write
    outcome = apply(path, transform)
    assert outcome["changed"] is True
    assert "def bar" in path.read_text()
