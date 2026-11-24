"""Agent C — deterministic trace of one complete Fleet execution path.

Covers: bot create -> user message -> echo/provider turn -> persisted rows and
SSE row events -> turn_end -> reopen (history). Also pins two observed facts
that matter to the audit: the free-text ``role`` field is metadata only, while
the *permission mode* really does change the permission decision at the tool
boundary.

No network, no user data: an isolated temp SQLite DB and the existing echo
harness / fake-provider patterns are used throughout.
"""

from __future__ import annotations

import http.client
import json
import threading
import time

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet.service import FleetStore
from keel.fleet import turn_core
from keel.permissions import Decision, evaluate
from keel.runner import RealTools
from keel.tools import create_native_registry


# --------------------------------------------------------------------------- helpers

def _req(server, method, path, body=None, token=None):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=30)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Keel-Token": token or webapp.token(),
               "Content-Type": "application/json"}
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        doc = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        doc = {"raw": raw}
    return resp.status, doc


def _post(server, path, body):
    return _req(server, "POST", path, body)


def _get(server, path):
    return _req(server, "GET", path, None)


def _wait(predicate, timeout=8.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def bridge(tmp_path):
    old = fleet_routes._store
    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    fleet_routes._store = old


def _rows(server, bot_id):
    return _get(server, f"/api/fleet/bots/{bot_id}/rows")[1].get("rows", [])


# --------------------------------------------------------------------------- trace

def test_full_execution_path_rows_events_completion_and_history(bridge, tmp_path):
    """One full bot create -> message -> turn -> row/SSE -> reopen trace."""
    status, created = _post(bridge, "/api/fleet/bots", {
        "name": "Trace Bot", "role": "auditor", "engine": "echo"})
    assert status == 201
    bot = created["bot"]
    bot_id = bot["id"]
    assert bot["role"] == "auditor"  # role is stored verbatim (metadata)

    store = fleet_routes.store()
    queue = store.subscribe()  # SSE fan-out captured before the message
    try:
        status, posted = _post(
            bridge, f"/api/fleet/bots/{bot_id}/messages",
            {"content": "trace me"})
        assert status == 202 and posted["queued"] is True
        seq = posted["seq"]

        assert _wait(lambda: any(r["kind"] == "turn_end"
                                 for r in _rows(bridge, bot_id)))
        rows = _rows(bridge, bot_id)
        kinds = [r["kind"] for r in rows]

        # persisted order: creation notice, user row, step running/done x3,
        # assistant message, turn_end.
        assert kinds[0] == "notice"
        assert kinds[1] == "message" and rows[1]["seq"] == seq
        assert rows[1]["body"]["role"] == "user"
        assert kinds.count("step") == 6
        assert kinds.count("message") == 2
        assistant = [r for r in rows if r["kind"] == "message"
                     and r["body"].get("role") == "assistant"]
        assert len(assistant) == 1
        assert assistant[0]["body"]["engine"] == "echo"
        assert "trace me" in assistant[0]["body"]["content"]
        assert kinds[-1] == "turn_end"
        assert rows[-1]["body"]["num_steps"] == 3

        # Every persisted row was also delivered on the SSE fan-out.
        delivered = set()
        while True:
            event = store.poll_subscribed(queue, timeout=0.01)
            if event is None:
                break
            if event.get("type") == "row":
                delivered.add(event["seq"])
        assert {r["seq"] for r in rows if r["seq"] >= seq} <= delivered

        # History survives a fresh store object on the same DB file.
        reopened = FleetStore(db_path=tmp_path / "fleet.db")
        try:
            hist = reopened.list_rows(bot_id, 0, 10_000)
            assert [r["seq"] for r in hist] == [r["seq"] for r in rows]
            assert any(r["kind"] == "message" and
                       r["body"].get("content") == "trace me" for r in hist)
        finally:
            reopened.close()
    finally:
        store.unsubscribe(queue)


def test_role_does_not_change_runtime_behaviour(bridge):
    """Observed: two agents differing only in `role` behave identically."""
    replies = {}
    for name, role in (("Alpha", "researcher"), ("Beta", "reviewer")):
        status, created = _post(bridge, "/api/fleet/bots", {
            "name": name, "role": role, "engine": "echo"})
        assert status == 201
        bot_id = created["bot"]["id"]
        status, _ = _post(bridge, f"/api/fleet/bots/{bot_id}/messages",
                          {"content": "same prompt"})
        assert status == 202
        assert _wait(lambda: any(r["kind"] == "turn_end"
                                 for r in _rows(bridge, bot_id)))
        assistant = [r for r in _rows(bridge, bot_id)
                     if r["kind"] == "message"
                     and r["body"].get("role") == "assistant"]
        replies[role] = assistant[-1]["body"]["content"]
    assert replies["researcher"] == replies["reviewer"]


# --------------------------------------------------------------------------- modes

def test_permission_mode_normalization_is_real_and_bounded():
    """build/plan/autopilot/acceptEdits map to the documented Session modes."""
    assert turn_core._normalize_permission_mode("build") == "default"
    assert turn_core._normalize_permission_mode("plan") == "dontAsk"
    assert turn_core._normalize_permission_mode("autopilot") == "bypassPermissions"
    assert turn_core._normalize_permission_mode("acceptEdits") == "acceptEdits"
    assert turn_core._normalize_permission_mode(None) == "default"
    assert turn_core._normalize_permission_mode("garbage") == "default"


def test_plan_mode_blocks_writes_while_default_mode_asks():
    """Mode separation is enforced at the permission gate, not in the UI.

    A real tool registry is supplied: with ``tool_registry=None`` the fallback
    classification sets do not contain ``write_file`` and the call is treated
    as unknown, so this test would not exercise the mode table at all.

    Note (GAP A-3): ``evaluate`` returns ``"ask"`` for the mode table's
    explicit ``"deny"`` verdict in interactive mode. Session refuses every
    non-allow decision, so the observable effect (plan cannot write) holds;
    only the decision vocabulary is inconsistent.
    """
    rules = ([], [], [])  # no config rules -> mode baseline decides
    write = {"path": "notes.txt", "content": "x"}
    registry = create_native_registry(RealTools())

    plan = evaluate(tool_name="write_file", tool_input=write, rules=rules,
                    mode="dontAsk", interactive=True,
                    tool_registry=registry)
    assert isinstance(plan, Decision)
    assert plan.decision != "allow"  # refused at the gate, no tool execution
    assert plan.reason_type == "mode"  # no consent card is ever created

    default = evaluate(tool_name="write_file", tool_input=write, rules=rules,
                       mode="default", interactive=True,
                       tool_registry=registry)
    assert default.decision == "ask"
    assert default.reason_type == "mode"


def test_mode_table_deny_verdict_uses_deny_vocabulary():
    registry = create_native_registry(RealTools())
    decision = evaluate(
        tool_name="write_file", tool_input={"path": "notes.txt"},
        rules=([], [], []), mode="dontAsk", interactive=True,
        tool_registry=registry)
    assert decision.decision == "deny"
