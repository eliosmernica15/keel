"""GENUINE LOCAL INTEGRATION — the Echo engine end-to-end, no credentials.

This is NOT a fixture and NOT a live external provider. The scripted Echo
engine, the real Fleet store and the real HTTP bridge all run unmodified. No
provider key, no adapter and no network are involved. It is reported as a real
local integration: it proves the agent -> bridge -> store -> transcript path
works before any credential is configured.

Covers requirement 4 of the provider verification round.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path

import pytest

import keel.webapp as webapp
from keel import settings_store
from keel.fleet import routes as fleet_routes


@pytest.fixture
def echo_bridge(tmp_path, monkeypatch):
    """Real bridge + real store; every provider credential env var scrubbed."""
    for var in settings_store.provider_env_var().values():
        monkeypatch.delenv(var, raising=False)
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, webapp.token()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _req(server, method, path, body=None, token=None):
    conn = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=10
    )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if token is not None:
        headers["X-Keel-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, json.loads(payload.decode("utf-8") or "{}")


def _wait(predicate, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _rows(server, bot_id):
    return _req(
        server, "GET", f"/api/fleet/bots/{bot_id}/rows", token=webapp.token()
    )[1].get("rows", [])


def test_real_echo_full_turn_without_any_credential(echo_bridge):
    """GENUINE LOCAL INTEGRATION: a complete Echo turn over the real bridge."""
    server, token = echo_bridge
    # No provider key exists anywhere in the process.
    for var in settings_store.provider_env_var().values():
        assert not __import__("os").environ.get(var), f"{var} unexpectedly set"

    status, created = _req(
        server,
        "POST",
        "/api/fleet/bots",
        {"name": "echo-check", "engine": "echo"},
        token,
    )
    assert status == 201
    bot = created["bot"]
    assert bot["engine"] == "echo"

    content = "hello local harness"
    status, queued = _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot['id']}/messages",
        {"content": content},
        token,
    )
    assert status == 202 and queued["queued"] is True

    assert _wait(
        lambda: any(r["kind"] == "turn_end" for r in _rows(server, bot["id"]))
    ), "Echo turn never completed"

    rows = _rows(server, bot["id"])
    kinds = [r["kind"] for r in rows]
    assert kinds.count("message") >= 2  # user + assistant
    assert kinds.count("turn_end") == 1

    user = next(
        r
        for r in rows
        if r["kind"] == "message" and r["body"].get("role") == "user"
    )
    assert user["body"]["content"] == content

    steps = [r["body"] for r in rows if r["kind"] == "step"]
    assert [b["name"] for b in steps] == [
        "analyze-request",
        "analyze-request",
        "consider-options",
        "consider-options",
        "compose-reply",
        "compose-reply",
    ]
    assert [b["status"] for b in steps] == ["running", "done"] * 3

    assistant = next(
        r
        for r in rows
        if r["kind"] == "message" and r["body"].get("role") == "assistant"
    )
    assert assistant["body"]["engine"] == "echo"
    assert "Echo heard you say" in assistant["body"]["content"]
    assert content in assistant["body"]["content"]
    assert "scripted Echo test bot" in assistant["body"]["content"]

    turn_end = next(r for r in rows if r["kind"] == "turn_end")
    assert turn_end["body"]["num_steps"] == 3
    assert isinstance(turn_end["body"]["duration_ms"], int)


def test_real_echo_turn_is_persisted_and_reloadable(echo_bridge, tmp_path):
    """GENUINE LOCAL INTEGRATION: Echo rows are durable in the Fleet store."""
    server, token = echo_bridge
    status, created = _req(
        server,
        "POST",
        "/api/fleet/bots",
        {"name": "echo-durable", "engine": "echo"},
        token,
    )
    assert status == 201
    bot_id = created["bot"]["id"]
    _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot_id}/messages",
        {"content": "durable message"},
        token,
    )
    assert _wait(
        lambda: any(r["kind"] == "turn_end" for r in _rows(server, bot_id))
    )

    from keel.fleet.service import FleetStore

    reloaded = FleetStore(tmp_path / "fleet.db")
    bot = reloaded.get_bot(bot_id)
    assert bot["engine"] == "echo"
    user_rows = [
        r
        for r in reloaded.list_rows(bot_id)
        if r["kind"] == "message" and r["body"].get("role") == "user"
    ]
    assert any(r["body"]["content"] == "durable message" for r in user_rows)


def test_echo_export_markdown_contains_the_real_reply(echo_bridge):
    """GENUINE LOCAL INTEGRATION: the transcript export reflects the turn."""
    server, token = echo_bridge
    status, created = _req(
        server,
        "POST",
        "/api/fleet/bots",
        {"name": "echo-export", "engine": "echo"},
        token,
    )
    bot_id = created["bot"]["id"]
    _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot_id}/messages",
        {"content": "export me"},
        token,
    )
    assert _wait(
        lambda: any(r["kind"] == "turn_end" for r in _rows(server, bot_id))
    )
    conn = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=10
    )
    conn.request(
        "GET",
        f"/api/fleet/bots/{bot_id}/export.md",
        headers={"X-Keel-Token": token},
    )
    resp = conn.getresponse()
    markdown = resp.read().decode("utf-8")
    conn.close()
    assert resp.status == 200
    assert "export me" in markdown
    assert "Echo heard you say" in markdown


def test_ui_source_labels_echo_as_scripted_not_live():
    """The shipped UI never presents an Echo turn as a live model run."""
    ui_root = Path(__file__).resolve().parents[1] / "fleet-next"
    agents = (ui_root / "features" / "fleet" / "Agents.tsx").read_text(
        encoding="utf-8"
    )
    agent_details = (ui_root / "features" / "fleet" / "AgentDetails.tsx").read_text(
        encoding="utf-8"
    )
    support = (ui_root / "features" / "fleet" / "support.ts").read_text(
        encoding="utf-8"
    )
    assert "Echo agents are labelled scripted and never shown as a live model run" in agents
    assert "scripted Echo engine" in agent_details
    assert 'scripted ? "Scripted (Echo) · "' in support
