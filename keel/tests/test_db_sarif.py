"""B2.9/C4.5 — real DB explorer and SARIF conversion."""

from __future__ import annotations

import json
import sqlite3

import pytest

from keel.db_explorer import DBError, DBExplorer
from keel.sarif import finding, from_sarif, to_sarif, write_sarif


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER, text TEXT)")
        conn.execute("INSERT INTO notes VALUES (1, 'hello')")
    return path


def test_db_explorer(db):
    explorer = DBExplorer(db)
    assert explorer.tables() == ["notes"]
    assert explorer.columns("notes")[0]["name"] == "id"
    rows = explorer.query("SELECT * FROM notes")
    assert rows[0]["text"] == "hello"
    with pytest.raises(DBError, match="only SELECT"):
        explorer.query("DELETE FROM notes")
    with pytest.raises(DBError, match="forbidden"):
        explorer.query("SELECT * FROM notes; DROP TABLE notes")


def test_sarif_roundtrip(tmp_path):
    findings = [finding("error", "issue", rule="R1", file="a.py", line=3)]
    doc = to_sarif(findings)
    assert doc["version"] == "2.1.0"
    assert from_sarif(doc)[0]["rule"] == "R1"
    path = write_sarif(doc, tmp_path / "out.sarif")
    assert json.loads(path.read_text())["version"] == "2.1.0"
