"""A1.2 — attach a CLI client to a running Keel daemon."""

from __future__ import annotations

import threading
import time

import pytest

from keel import attach, compat, webapp
from keel.cli.main import main
from keel.fleet import routes as fleet_routes


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", "attach-test-token")
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        yield port, "attach-test-token"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_attach_lists_sessions_and_reads_history(daemon):
    port, token = daemon
    created = compat.create_session("Attach test")
    sid = created["id"]
    sessions = attach.list_sessions(port, token)
    assert any(session["id"] == sid for session in sessions)
    detail = attach.session_detail(sid, port, token)
    assert detail["session"]["id"] == sid
    assert isinstance(detail["messages"], list)


def test_attach_rejects_bad_token(daemon):
    port, _ = daemon
    with pytest.raises(attach.AttachError, match="daemon returned"):
        attach.list_sessions(port, "wrong-token")


def test_cli_attach_commands(daemon, capsys):
    port, token = daemon
    created = compat.create_session("CLI attach")
    sid = created["id"]
    assert main(["attach", "--port", str(port), "--token", token]) == 0
    assert sid in capsys.readouterr().out
    assert main(["attach", sid, "--port", str(port), "--token", token]) == 0
    assert "messages" in capsys.readouterr().out
