"""keel.fleet — F1 approval cards & permission policies.

End-to-end over real HTTP against an ephemeral bridge with a real SQLite
fleet.db. The provider model is scripted (FakeAdapter); everything between
the model and the tool-execution gate — risk classification, the Fleet
approval broker, standing policies, the audit log — is the production path.

Environment note: KEEL_FLEET_APPROVAL_TIMEOUT_S=1 makes unanswered cards
expire after one second so tests stay fast. Production default is 300.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord, ProviderError, RETRY_RATE_LIMIT


class FakeAdapter:
    """Scripted stand-in for a provider adapter (see test_fleet_provider.py).

    task_write — a three-step script: parent calls `Task`, the subagent calls
                 `write_file`, then the model wraps up on both levels.
    """

    instances: list["FakeAdapter"] = []
    script: str = "plain"
    tool_path: str = "."
    followup_text: str = "Done."

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests = []
        FakeAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        script = FakeAdapter.script
        n = len(self.requests)

        if script in ("plain", "followup"):
            text = "Hello, operator." if script == "plain" else FakeAdapter.followup_text
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0, "text": text}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "message_stop", "stop_reason": "end_turn"}
            return

        if script == "tool_write":
            if n > 1:
                yield from FakeAdapter._text(self, FakeAdapter.followup_text)
                return
            yield from FakeAdapter._tool("write_file", "call_fake_write",
                                    {"path": FakeAdapter.tool_path,
                                     "content": "must never be written"})
            return

        if script == "task_write":
            if n == 1:
                yield from FakeAdapter._tool("Task", "call_fake_task",
                                        {"description": "write the file",
                                         "prompt": "write the file now"})
                return
            if n == 2:
                yield from FakeAdapter._tool("write_file", "call_fake_write",
                                        {"path": FakeAdapter.tool_path,
                                         "content": "must never be written"})
                return
            yield from FakeAdapter._text(self, FakeAdapter.followup_text)
            return

        raise AssertionError(f"unknown script {script!r}")

    @staticmethod
    def _text(adapter, text):
        yield {"event": "block_start", "index": 0,
               "block": {"type": "text", "text": ""}}
        yield {"event": "text_delta", "index": 0, "text": text}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "message_stop", "stop_reason": "end_turn"}

    @staticmethod
    def _tool(name, call_id, tool_input):
        yield {"event": "block_start", "index": 0,
               "block": {"type": "tool_use", "id": call_id,
                         "name": name, "input": tool_input}}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "message_stop", "stop_reason": "tool_use"}


OPENROUTER = CapabilityRecord(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="openrouter/auto",
    supports_tools=True, supports_streaming=True,
)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    FakeAdapter.instances = []
    FakeAdapter.script = "plain"
    FakeAdapter.tool_path = "."
    FakeAdapter.followup_text = "Done."
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "1")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: FakeAdapter(OPENROUTER,
                                                          api_key="test-key"))

    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.db_path = db_path  # stash for restart simulation
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


import http.client


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


def _post(server, path, body, token=None):
    return _req(server, "POST", path, body, token)


def _get(server, path, token=None):
    return _req(server, "GET", path, None, token)


def _wait(predicate, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _create_bot(server, name="Agent", engine="provider", **over):
    status, created = _post(server, "/api/fleet/bots",
                            {"name": name, "engine": engine, **over})
    assert status == 201
    return created["bot"]


def _rows(server, bot_id):
    status, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    return body.get("rows", [])


def _approval_states(rows):
    """Latest state per approval_id (rows are appended; last one wins)."""
    states = {}
    for row in rows:
        if row["kind"] != "approval":
            continue
        body = row["body"]
        aid = body.get("approval_id")
        if aid:
            states[aid] = (body, row)
    return states


def _pending(rows):
    return {aid: body for aid, (body, _) in _approval_states(rows).items()
            if body.get("status") == "pending"}


def _wait_turn_end(server, bot_id, timeout=10, count=1):
    assert _wait(lambda: sum(1 for r in _rows(server, bot_id)
                             if r["kind"] == "turn_end") >= count,
                timeout=timeout)


def _wait_pending(server, bot_id, count=1, timeout=10):
    assert _wait(lambda: len(_pending(_rows(server, bot_id))) >= count,
                timeout=timeout)
    return _pending(_rows(server, bot_id))


def _wait_pending_tool(server, bot_id, tool_name, timeout=10):
    assert _wait(lambda: any(b.get("tool_name") == tool_name
                             for b in _pending(_rows(server, bot_id)).values()),
                timeout=timeout)
    pending = _pending(_rows(server, bot_id))
    return next(aid for aid, b in pending.items()
                if b.get("tool_name") == tool_name)


def _decide(server, bot_id, approval_id, decision):
    return _post(server, f"/api/fleet/bots/{bot_id}/approvals/{approval_id}/decide",
                 {"decision": decision})


def _post_user_message(server, bot_id, text):
    return _post(server, f"/api/fleet/bots/{bot_id}/messages",
                 {"content": text})


# ---------------------------------------------------------------- allow once

def test_allow_once_writes_file_and_asks_again_next_turn(bridge, tmp_path):
    target = tmp_path / "once.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="OnceBot")
    _post_user_message(bridge, bot["id"], "write it")

    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    status, body = _decide(bridge, bot["id"], approval_id, "once")
    assert status == 200
    assert body["approval"]["status"] == "approved"
    _wait_turn_end(bridge, bot["id"])
    assert target.exists()
    rows = _rows(bridge, bot["id"])
    state = _approval_states(rows)[approval_id][0]
    assert state["status"] == "approved"
    assert state["decision"] == "once"

    # second turn: same tool must ask again (once is single invocation only)
    _post_user_message(bridge, bot["id"], "write it again")
    pending = _wait_pending(bridge, bot["id"])
    assert len(pending) == 1
    assert next(iter(pending)) != approval_id


def test_always_allow_persists_policy(bridge, tmp_path):
    target = tmp_path / "always.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="AlwaysBot")
    _post_user_message(bridge, bot["id"], "write it")

    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    status, _ = _decide(bridge, bot["id"], approval_id, "always")
    assert status == 200
    _wait_turn_end(bridge, bot["id"])
    assert target.exists()

    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/policies")
    assert status == 200
    tools = {p["tool_name"]: p["decision"] for p in body["policies"]}
    assert tools.get("write_file") == "always"

    # second turn auto-allowed: no new card, file written again
    _post_user_message(bridge, bot["id"], "write it again")
    _wait_turn_end(bridge, bot["id"], timeout=10, count=2)
    rows = _rows(bridge, bot["id"])
    assert len(_pending(rows)) == 0
    assert len(_approval_states(rows)) == 1  # only the first card exists


def test_dont_allow_persists_never_policy(bridge, tmp_path):
    target = tmp_path / "never.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="NeverBot")
    _post_user_message(bridge, bot["id"], "write it")

    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    status, _ = _decide(bridge, bot["id"], approval_id, "never")
    assert status == 200
    _wait_turn_end(bridge, bot["id"])
    assert not target.exists()

    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/policies")
    tools = {p["tool_name"]: p["decision"] for p in body["policies"]}
    assert tools.get("write_file") == "never"

    # second turn: auto-denied by standing policy — NO new card
    _post_user_message(bridge, bot["id"], "write it again")
    _wait_turn_end(bridge, bot["id"], timeout=10, count=2)
    rows = _rows(bridge, bot["id"])
    assert len(_pending(rows)) == 0
    assert len(_approval_states(rows)) == 1  # the one card, now "denied"
    assert not target.exists()
    notices = [r["body"]["text"] for r in rows if r["kind"] == "notice"]
    assert any("Never policy" in t for t in notices)


# --------------------------------------------------------------- isolation

def test_policies_do_not_leak_across_agents(bridge, tmp_path):
    never_bot = _create_bot(bridge, name="StrictBot")
    free_bot = _create_bot(bridge, name="LooseBot")
    FakeAdapter.script = "tool_write"
    never_path = tmp_path / "strict.txt"
    FakeAdapter.tool_path = str(never_path)
    _post_user_message(bridge, never_bot["id"], "write it")
    pending = _wait_pending(bridge, never_bot["id"])
    approval_id = next(iter(pending))
    _decide(bridge, never_bot["id"], approval_id, "never")
    _wait_turn_end(bridge, never_bot["id"])
    assert not never_path.exists()

    # the other agent is unaffected: its call asks in its own chat
    free_path = tmp_path / "loose.txt"
    FakeAdapter.tool_path = str(free_path)
    _post_user_message(bridge, free_bot["id"], "write it")
    pending = _wait_pending(bridge, free_bot["id"])
    assert len(pending) == 1
    status, body = _get(bridge, f"/api/fleet/bots/{free_bot['id']}/policies")
    assert body["policies"] == []


def test_revocation_restores_asking(bridge, tmp_path):
    target = tmp_path / "revoke.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="RevokeBot")
    _post_user_message(bridge, bot["id"], "write it")
    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    _decide(bridge, bot["id"], approval_id, "never")
    _wait_turn_end(bridge, bot["id"])

    status, body = _post(bridge, f"/api/fleet/bots/{bot['id']}/policies/revoke",
                         {"tool_name": "write_file"})
    assert status == 200
    assert body["revoked"] is True
    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/policies")
    assert body["policies"] == []

    # next call asks again instead of auto-denying
    _post_user_message(bridge, bot["id"], "write it again")
    pending = _wait_pending(bridge, bot["id"])
    assert len(pending) == 1


# ------------------------------------------------------------ timeout path

def test_card_unanswered_expires_to_denied(bridge, tmp_path):
    """No decision is ever posted — this is also what happens when a client
    disconnects or vanishes. The card expires and the tool is refused."""
    target = tmp_path / "timeout.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="TimeoutBot")
    _post_user_message(bridge, bot["id"], "write it")
    _wait_pending(bridge, bot["id"])
    _wait_turn_end(bridge, bot["id"], timeout=10)
    assert not target.exists()
    rows = _rows(bridge, bot["id"])
    states = _approval_states(rows)
    assert any(b.get("status") == "expired" for b, _ in states.values())
    notices = [r["body"]["text"] for r in rows if r["kind"] == "notice"]
    assert any("timed out" in t for t in notices)


# ------------------------------------------------------- restart semantics

def test_pending_approvals_are_refused_on_restart(bridge, tmp_path):
    target = tmp_path / "restart.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="RestartBot")
    _post_user_message(bridge, bot["id"], "write it")
    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))

    # simulate a server restart against the same fleet.db
    fleet_routes.reset_store_for_tests(bridge.db_path)

    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/rows")
    states = _approval_states(body["rows"])
    assert states[approval_id][0]["status"] == "expired"
    assert states[approval_id][0]["decision"] == "restart"

    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/audit")
    audit = body["audit"]
    restart_entries = [a for a in audit if a["event"] == "decided"
                       and a["decision"] == "restart"]
    assert restart_entries, "restart sweep must record an audit entry"
    # the tool never ran
    assert not target.exists()


def test_policies_survive_restart(bridge, tmp_path):
    target = tmp_path / "persist_policy.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="PersistBot")
    _post_user_message(bridge, bot["id"], "write it")
    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    _decide(bridge, bot["id"], approval_id, "always")
    _wait_turn_end(bridge, bot["id"])

    fleet_routes.reset_store_for_tests(bridge.db_path)

    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/policies")
    assert {p["tool_name"]: p["decision"]
            for p in body["policies"]}.get("write_file") == "always"


# ------------------------------------------------- subagent cannot bypass

def test_subagent_tools_go_through_the_same_gate(bridge, tmp_path):
    target = tmp_path / "subagent.txt"
    FakeAdapter.script = "task_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="TaskBot")
    _post_user_message(bridge, bot["id"], "delegate the write")

    # first gate: the Task tool itself asks
    pending = _wait_pending(bridge, bot["id"])
    task_approval = next(iter(pending))
    status, body = _decide(bridge, bot["id"], task_approval, "once")
    assert status == 200

    # second gate: the subagent's write_file asks in the same chat
    write_approval = _wait_pending_tool(bridge, bot["id"], "write_file")
    status, body = _decide(bridge, bot["id"], write_approval, "once")
    assert status == 200
    _wait_turn_end(bridge, bot["id"])
    assert target.exists()


def test_subagent_write_refused_when_denied(bridge, tmp_path):
    target = tmp_path / "subagent_denied.txt"
    FakeAdapter.script = "task_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="DenyTaskBot")
    _post_user_message(bridge, bot["id"], "delegate the write")

    pending = _wait_pending(bridge, bot["id"])
    task_approval = next(iter(pending))
    _decide(bridge, bot["id"], task_approval, "once")

    write_approval = _wait_pending_tool(bridge, bot["id"], "write_file")
    _decide(bridge, bot["id"], write_approval, "never")
    _wait_turn_end(bridge, bot["id"])
    assert not target.exists()


# ------------------------------------------------------------ audit trail

def test_audit_records_decisions_without_raw_arguments(bridge, tmp_path):
    target = tmp_path / "audited.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="AuditBot")
    _post_user_message(bridge, bot["id"], "write it")
    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    _decide(bridge, bot["id"], approval_id, "once")
    _wait_turn_end(bridge, bot["id"])

    status, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/audit?limit=100")
    assert status == 200
    audit = body["audit"]
    assert audit, "audit must not be empty"

    # the raw arguments must not appear anywhere in the audit trail
    blob = json.dumps(audit, default=str)
    assert "must never be written" not in blob
    assert str(target) not in blob

    events = [a["event"] for a in audit]
    assert "requested" in events
    assert "decided" in events
    assert "outcome" in events

    fingerprints = {a["fingerprint"] for a in audit if a["fingerprint"]}
    assert all(re.fullmatch(r"[0-9a-f]{16}|policy", fp) for fp in fingerprints)

    linked = [a for a in audit if a.get("approval_id") == approval_id]
    assert any(a["event"] == "decided" and a["decision"] == "once" for a in linked)
    assert any(a["event"] == "outcome" and a["outcome"] == "executed" for a in linked)


def test_fleet_approvals_never_override_tier_2(bridge, tmp_path):
    """A fleet approval grants only what Keel would otherwise consent to —
    Tier 2 (here: writes to secret-bearing paths) still vetoes."""
    target = tmp_path / ".env"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="Tier2Bot")
    _post_user_message(bridge, bot["id"], "write it")

    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    status, _ = _decide(bridge, bot["id"], approval_id, "once")
    assert status == 200
    _wait_turn_end(bridge, bot["id"])

    assert not target.exists(), "Tier 2 must refuse a fleet-approved .env write"
    rows = _rows(bridge, bot["id"])
    steps = [r for r in rows if r["kind"] == "step"
             and r["body"].get("name") == "write_file"]
    assert any("tier-2" in str(s["body"].get("detail", "")) for s in steps)


# --------------------------------------------------------------- endpoint

def test_decide_endpoint_semantics(bridge, tmp_path):
    target = tmp_path / "endpoint.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, name="EndpointBot")

    status, body = _decide(bridge, bot["id"], "nonexistent-id", "once")
    assert status == 404

    status, body = _post(bridge, f"/api/fleet/bots/{bot['id']}/approvals/nonexistent/decide",
                         {"decision": "yolo"})
    assert status == 400

    _post_user_message(bridge, bot["id"], "write it")
    pending = _wait_pending(bridge, bot["id"])
    approval_id = next(iter(pending))
    status, _ = _decide(bridge, bot["id"], approval_id, "once")
    assert status == 200
    # decision is final: a second click is a 409, not another executor run
    status, body = _decide(bridge, bot["id"], approval_id, "always")
    assert status == 409
    assert body["approval"]["status"] == "approved"


# ------------------------------------------- backend gate, HTTP not required

def test_session_boundary_denies_without_decider_allow(bridge, tmp_path):
    """Directly at the tool boundary: a decider that always denies must
    stop the tool from executing, no HTTP involved."""
    from keel.runner import RealTools
    from keel.session import Session, SessionConfig
    from keel.permissions import Decision
    from keel.providers.model_client import ProviderModelClient

    target = tmp_path / "boundary.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    FakeAdapter.instances = []

    adapter = FakeAdapter(OPENROUTER, api_key="x")
    client = ProviderModelClient(adapter, model="openrouter/auto")
    config = SessionConfig(
        cwd=str(tmp_path), state_root=str(tmp_path / "state"), bare=True,
        permission_mode="default", session_id="boundary-test",
        model="openrouter/auto", max_turns=3,
        approval_decider=lambda ctx: Decision(
            "deny", "fleet_approval", "declined by operator via Fleet card",
            "fleet", "card:test", None, False),
    )
    session = Session(model_client=client, executor=RealTools(), config=config,
                      clock=None, rng=None)
    outcome = session.run("write the file")
    assert outcome.envelope["subtype"] == "success"
    assert not target.exists()


def test_session_boundary_allows_with_decider_allow(bridge, tmp_path):
    from keel.runner import RealTools
    from keel.session import Session, SessionConfig
    from keel.permissions import Decision
    from keel.providers.model_client import ProviderModelClient

    target = tmp_path / "boundary_allow.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    FakeAdapter.instances = []

    adapter = FakeAdapter(OPENROUTER, api_key="x")
    client = ProviderModelClient(adapter, model="openrouter/auto")
    config = SessionConfig(
        cwd=str(tmp_path), state_root=str(tmp_path / "state"), bare=True,
        permission_mode="default", session_id="boundary-test-allow",
        model="openrouter/auto", max_turns=3,
        approval_decider=lambda ctx: Decision(
            "allow", "fleet_approval", "approved once by operator via Fleet card",
            "fleet", "card:test", None, False),
    )
    session = Session(model_client=client, executor=RealTools(), config=config,
                      clock=None, rng=None)
    outcome = session.run("write the file")
    assert outcome.envelope["subtype"] == "success"
    assert target.exists()
