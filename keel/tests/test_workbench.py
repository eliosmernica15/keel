"""B2.x — prompt library, spec mode, DB explorer, notebook."""

from __future__ import annotations

import sqlite3

from keel.workbench import (PromptLibrary, notebook_cells, spec_plan,
                            sqlite_tables)


def test_prompt_library(tmp_path):
    library = PromptLibrary(tmp_path)
    library.add("greet", "Hello {{name}}", ["name"])
    assert library.render("greet", {"name": "Ada"}) == "Hello Ada"
    assert library.render("missing", {}) == ""


def test_spec_plan():
    plan = spec_plan("build feature")
    assert plan["approval_required"] is True and len(plan["steps"]) == 4


def test_sqlite_tables_readonly(tmp_path):
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT)")
    assert "notes" in sqlite_tables(db)


def test_notebook_cells():
    cells = notebook_cells("# Title\n\ntext here\n```python\nprint(1)\n```")
    assert any(c["kind"] == "code" for c in cells)
    assert any(c["kind"] == "text" for c in cells)
