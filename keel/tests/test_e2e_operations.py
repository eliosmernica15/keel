"""Operational end-to-end verification (section 3).

Exercises the real Python backend over its HTTP bridge plus real tool paths:
backend startup, session create/export/import, real file workflows, permission
boundaries, provider failure handling, delegation, Cowork documents, backups,
updates and secret-leak checks. Uses deterministic scripted providers where an
external API would otherwise be needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import keel.compat as compat
import keel.settings_store as settings_store
import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.session import Session, SessionConfig
from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.runner import RealTools

TOKEN = "ops-e2e-token"


def _http(port, path, *, method="GET", body=None, token=TOKEN):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-Keel-Token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode()
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """Start the real Python backend on an ephemeral loopback port."""
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", tmp_path / "settings.json.bak")

    def _load():
        path = settings_store.SETTINGS_PATH
        return json.loads(path.read_text()) if path.is_file() else {}

    monkeypatch.setattr(settings_store, "load", _load)
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        yield port, tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _executor():
    return RealTools()


def _session(tmp_path, script, *, allow=(), rules=None):
    cfg = SessionConfig(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
                        bare=True, permission_mode="default",
                        session_id="99999999-9999-4999-9999-999999999999",
                        model="scripted", max_turns=6, seed=7)
    return Session(model_client=ScriptedModel(script, model="scripted"),
                   executor=_executor(), config=cfg,
                   rules=rules or ((), (), tuple(allow)),
                   clock=VirtualClock(), rng=SeededRng(7))


def test_backend_starts_and_rejects_bad_token(backend):
    port, _ = backend
    assert _http(port, "/api/surfaces")[0] == 200
    assert _http(port, "/api/surfaces", token="wrong")[0] == 403


def test_session_create_export_import_via_backend(backend, tmp_path):
    port, workdir = backend
    created = compat.create_session("Operations test")
    sid = created["id"]
    compat._store().append_row(sid, "message", {"role": "user", "content": "hi"})
    status, doc = _http(port, f"/api/v2/sessions/{sid}")
    assert status == 200 and doc["session"]["id"] == sid
    assert doc["messages"][0]["content"] == "hi"

    from keel.session_export import export_bundle, import_bundle, write_bundle, read_bundle
    bundle = export_bundle(compat._store(), sid)
    path = write_bundle(bundle, workdir / "session.json")
    imported = import_bundle(compat._store(), read_bundle(path))
    assert imported["id"] != sid
    assert compat.get_session(imported["id"]) is not None


def test_real_tool_execution_writes_and_trash(tmp_path):
    """Real tool path: write a file, then delete it recoverably."""
    target = tmp_path / "note.txt"
    session = _session(tmp_path, [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target), "content": "hello"}}],
        [{"type": "tool_use", "name": "delete_file",
          "input": {"path": str(target)}}],
        [{"type": "text", "text": "done"}],
    ], allow=("write_file", "delete_file"))
    out = session.run("write then delete")
    assert out.envelope["subtype"] == "success"
    from keel.trash import list_items
    assert not target.exists() and len(list_items()) >= 1


def test_permission_boundary_denies_unallowed_tool(tmp_path):
    target = tmp_path / "blocked.txt"
    session = _session(tmp_path, [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target), "content": "x"}}],
        [{"type": "text", "text": "done"}],
    ])  # no allow rule
    out = session.run("try to write")
    assert not target.exists()
    assert out.envelope.get("permission_denials") or any(
        e.get("subtype") == "permission_denied" for e in out.events)


def test_output_dlp_blocks_secret_in_real_write(tmp_path):
    target = tmp_path / "leak.txt"
    session = _session(tmp_path, [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target),
                    "content": "key=sk-abcdefghijklmnopqrstuvwxyz"}}],
        [{"type": "text", "text": "done"}],
    ], allow=("write_file",))
    session.run("write a secret")
    assert not target.exists(), "DLP must block secrets written to disk"


def test_provider_failure_produces_error_envelope(tmp_path):
    from keel.providers.base import ProviderError, RETRY_RATE_LIMIT

    class Failing:
        def complete(self, messages, tools):
            raise ProviderError("rate limited", RETRY_RATE_LIMIT, 429, True)

    cfg = SessionConfig(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
                        bare=True, model="failing")
    out = Session(model_client=Failing(), executor=_executor(), config=cfg,
                  clock=VirtualClock(), rng=SeededRng(1)).run("hello")
    assert out.envelope["is_error"] is True
    assert out.envelope["errors"][0]["category"] == "rate_limit"


def test_cowork_document_workflow_real_files(backend, tmp_path):
    from keel.documents import (document_answer, read_docx, read_xlsx,
                                spreadsheet_stats, write_docx, write_xlsx)
    doc = write_docx(tmp_path / "report.docx", "Title\nKeel is local-first.")
    assert "local-first" in read_docx(doc)
    sheet = write_xlsx(tmp_path / "budget.xlsx",
                       [["Item", "Cost"], ["A", 5], ["B", 7]])
    grid = read_xlsx(sheet)
    assert spreadsheet_stats(grid)["stats"]["Cost"]["sum"] == 12.0
    hits = document_answer("local-first", read_docx(doc))
    assert hits and hits[0]["offset"] >= 0


def test_encrypted_backup_recovery_workflow(backend, tmp_path):
    from keel.backups import create_backup, restore_backup
    source = tmp_path / "work"
    source.mkdir()
    (source / "data.txt").write_text("important", encoding="utf-8")
    create_backup(source, tmp_path / "backup.json", "pass")
    restored = tmp_path / "recovered"
    files = restore_backup(tmp_path / "backup.json", restored, "pass")
    assert files == ["data.txt"]
    assert (restored / "data.txt").read_text() == "important"


def test_update_policy_and_rollback_available(tmp_path):
    from keel.start_health import record_start
    from keel.release.updater import rollback
    assert record_start(str(tmp_path), "0.1.1", ok=False)["failures"] == 1
    # A rollback with no backup fails safely rather than corrupting state.
    from keel.release.updater import UpdateError
    with pytest.raises(UpdateError):
        rollback(tmp_path / "install", tmp_path / "missing-backup")


def test_no_secret_leaks_into_egress_log(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_EGRESS_LOG", str(tmp_path / "egress.jsonl"))
    from keel.redaction import log_egress, read_egress
    log_egress(str(tmp_path), provider="openrouter", model="m",
               message_count=1, redactions={"openai_key": 1},
               outbound_bytes=10)
    text = (tmp_path / "egress.jsonl").read_text()
    assert "sk-" not in text and "secret" not in text.lower()
    assert read_egress(str(tmp_path))[0]["redactions"]["openai_key"] == 1


def test_fleet_delegation_over_backend(backend):
    """Create a bot via the real backend and verify delegation tooling exists."""
    port, _ = backend
    status, created = _http(port, "/api/fleet/bots", method="POST",
                            body={"name": "Lead", "engine": "provider"})
    assert status == 201
    bot = created["bot"]
    status, doc = _http(port, f"/api/fleet/bots/{bot['id']}")
    assert status == 200 and doc["bot"]["id"] == bot["id"]

    # Real delegation tools are registered in the runtime tool registry.
    from keel.tools.native import NATIVE_TOOL_NAMES
    assert "send_to_bot" in NATIVE_TOOL_NAMES
    assert "create_task" in NATIVE_TOOL_NAMES
    assert "Duet" in NATIVE_TOOL_NAMES
