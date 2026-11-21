"""A1.16 — session import/export and statistics."""

from __future__ import annotations

import json

import pytest

from keel.cli.main import main
from keel.compat import create_session
from keel.fleet import routes as fleet_routes
from keel.session_export import (SessionExportError, export_bundle,
                                 import_bundle, read_bundle, statistics,
                                 write_bundle)


@pytest.fixture
def store(tmp_path):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    return fleet_routes.store()


def test_export_import_roundtrip(store, tmp_path):
    session = create_session("Original")
    sid = session["id"]
    store.append_row(sid, "message", {"role": "user", "content": "hello"})
    bundle = export_bundle(store, sid)
    assert bundle["format"] == "keel-session-v1"
    path = write_bundle(bundle, tmp_path / "session.json")
    loaded = read_bundle(path)
    imported = import_bundle(store, loaded)
    assert imported["id"] != sid
    assert imported["name"].startswith("Imported")
    rows = store.list_rows(imported["id"], after_seq=0, limit=100)
    assert any(row.get("body", {}).get("content") == "hello" for row in rows)


def test_statistics_counts_rows_and_tokens(store):
    sid = create_session("Stats")["id"]
    store.append_row(sid, "message", {"role": "user", "content": "hi"})
    store.append_row(sid, "turn_end", {"usage": {"input_tokens": 10,
                                                 "output_tokens": 5}})
    stats = statistics(store, sid)
    assert stats["rows"] >= 2
    assert stats["tokens"] == 15
    assert stats["by_kind"]["message"] == 1


def test_bad_bundle_and_unknown_session(store, tmp_path):
    with pytest.raises(SessionExportError, match="unknown session"):
        export_bundle(store, "missing")
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(SessionExportError, match="not a Keel session bundle"):
        read_bundle(bad)


def test_cli_session_commands(store, tmp_path, capsys):
    sid = create_session("CLI session")["id"]
    path = tmp_path / "bundle.json"
    assert main(["session", "export", sid, "--file", str(path)]) == 0
    assert path.is_file()
    capsys.readouterr()
    assert main(["session", "stats", sid]) == 0
    assert json.loads(capsys.readouterr().out)["session_id"] == sid
    assert main(["session", "import", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["name"].startswith("Imported")
