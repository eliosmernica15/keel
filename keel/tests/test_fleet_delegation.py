"""keel.fleet — F3 agent delegation (send_to_bot) tests.

End-to-end over the real HTTP bridge with a scripted plan-based adapter.
PlanAdapter instances are created in the order the engine calls them
(depth-first through delegation), so a test declares the whole tree up
front as a queue of per-instance plans. Each plan is a list of turns;
each turn is a list of blocks:

    [{"kind": "text", "text": "..."}]
    [{"kind": "tool", "name": "send_to_bot", "input": {...}, "id": "t1"}]

The bridge fixture sets KEEL_FLEET_APPROVAL_TIMEOUT_S=1 and
KEEL_FLEET_DELEGATE_TIMEOUT_S=2 so unanswered cards and delegations
expire quickly; production defaults are 300 and 60.
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
from keel.fleet import echo as fleet_echo
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord, ProviderError, RETRY_RATE_LIMIT


class PlanAdapter:
    """Scripted adapter fed from a creation-ordered queue of plans."""

    plans: list[list | str] = []
    instances: list["PlanAdapter"] = []
    sleep_s: float = 0.0

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests = []
        self.plan = PlanAdapter.plans.pop(0) if PlanAdapter.plans else [
            [{"kind": "text", "text": "end of plan"}]]
        self._turn = 0
        PlanAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        if PlanAdapter.sleep_s:
            time.sleep(PlanAdapter.sleep_s)
        turn = self.plan if isinstance(self.plan, str) else \
            self.plan[min(self._turn, len(self.plan) - 1)]
        if isinstance(turn, str) and turn == "FAIL":
            raise ProviderError("limit hit", RETRY_RATE_LIMIT, 429,
                                retryable=True)
        self._turn += 1
        if len(self.requests) > len(self.plan):
            turn = [{"kind": "text", "text": "end of plan"}]
        for block in turn:
            if block["kind"] == "text":
                yield {"event": "block_start", "index": 0,
                       "block": {"type": "text", "text": ""}}
                yield {"event": "text_delta", "index": 0,
                       "text": block["text"]}
                yield {"event": "block_stop", "index": 0}
                yield {"event": "message_stop", "stop_reason": "end_turn"}
            elif block["kind"] == "tool":
                yield {"event": "block_start", "index": 0,
                       "block": {"type": "tool_use",
                                 "id": block.get("id", "tool_1"),
                                 "name": block["name"],
                                 "input": block["input"]}}
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
    PlanAdapter.plans = []
    PlanAdapter.instances = []
    PlanAdapter.sleep_s = 0.0
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "1")
    monkeypatch.setenv("KEEL_FLEET_DELEGATE_TIMEOUT_S", "2")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: PlanAdapter(OPENROUTER,
                                                          api_key="test-key"))

    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.db_path = db_path
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


import http.client
import socket


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


def _create_bot(server, name, engine="provider", **over):
    status, created = _post(server, "/api/fleet/bots",
                            {"name": name, "engine": engine, **over})
    assert status == 201
    return created["bot"]


def _rows(server, bot_id):
    _, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    return body.get("rows", [])


def _approval_states(rows):
    states = {}
    for row in rows:
        if row["kind"] == "approval" and row["body"].get("approval_id"):
            states[row["body"]["approval_id"]] = row["body"]
    return states


def _pending(rows):
    return {aid: b for aid, b in _approval_states(rows).items()
            if b.get("status") == "pending"}


def _wait_pending(server, bot_id, timeout=8):
    assert _wait(lambda: len(_pending(_rows(server, bot_id))) >= 1,
                timeout=timeout)
    pending = _pending(_rows(server, bot_id))
    return {aid: b for aid, b in pending.items()}


def _decide(server, bot_id, approval_id, decision):
    return _post(server, f"/api/fleet/bots/{bot_id}/approvals/{approval_id}/decide",
                 {"decision": decision})


def _turn_end_count(server, bot_id):
    return sum(1 for r in _rows(server, bot_id) if r["kind"] == "turn_end")


def _send_and_approve(server, bot_id, decision="once"):
    pending = _wait_pending(server, bot_id)
    approval_id = next(iter(pending))
    status, _ = _decide(server, bot_id, approval_id, decision)
    assert status == 200


def _delegation(target_slug, message, call_id="send_1"):
    return [{"kind": "tool", "name": "send_to_bot",
             "input": {"bot_slug": target_slug, "message": message},
             "id": call_id}]


def _wait_turn_end(server, bot_id, count=1, timeout=10):
    assert _wait(lambda: _turn_end_count(server, bot_id) >= count,
                timeout=timeout)


# --------------------------------------------------------------- happy path

def test_delegation_roundtrip(bridge, tmp_path):
    alice = _create_bot(bridge, "Alice")
    sage = _create_bot(bridge, "Sage")
    PlanAdapter.plans = [
        [_delegation("sage", "research the topic"),
         [{"kind": "text", "text": "A wraps up"}]],
        [[{"kind": "text", "text": "Sage's findings: 42"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{alice['id']}/messages",
          {"content": "alice, ask sage"})
    _send_and_approve(bridge, alice["id"], "once")
    _wait_turn_end(bridge, alice["id"], count=1, timeout=10)

    # both conversations recorded the exchange
    alice_rows = _rows(bridge, alice["id"])
    sage_rows = _rows(bridge, sage["id"])
    # callee DM: delegated user row + assistant reply
    sage_user_rows = [r for r in sage_rows if r["kind"] == "message"
                      and r["body"].get("role") == "user"]
    assert len(sage_user_rows) == 1
    assert "research the topic" in sage_user_rows[0]["body"]["content"]
    assert sage_user_rows[0]["body"]["delegated_from"]["id"] == alice["id"]
    sage_replies = [r for r in sage_rows if r["kind"] == "message"
                    and r["body"].get("role") == "assistant"]
    assert sage_replies and "42" in sage_replies[0]["body"]["content"]
    # caller DM: step row for send_to_bot carries the delegate payload
    steps = [r for r in alice_rows if r["kind"] == "step"
             and r["body"].get("name") == "send_to_bot"
             and r["body"].get("delegated")]
    assert steps, "expected a send_to_bot step row with the delegate payload"
    assert steps[0]["body"]["delegated"]["to_id"] == "sage"
    assert "42" in steps[0]["body"]["delegated"]["reply"]


def test_delegation_caller_and_recipient_identity(bridge):
    alice = _create_bot(bridge, "Alice", role="lead")
    bob = _create_bot(bridge, "Bob", role="analyst")
    PlanAdapter.plans = [
        [_delegation("bob", "look into it"),
         [{"kind": "text", "text": "done"}]],
        [[{"kind": "text", "text": "Bob looked into it"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{alice['id']}/messages",
          {"content": "delegate"})
    _send_and_approve(bridge, alice["id"], "once")
    _wait_turn_end(bridge, alice["id"])

    sage_rows = _rows(bridge, bob["id"])
    delegated = next(r for r in sage_rows
                     if r["kind"] == "message" and r["body"].get("delegated_from"))
    assert delegated["body"]["delegated_from"]["id"] == alice["id"]
    # the callee's model received the delegation WITH caller identity
    callee = PlanAdapter.instances[-1]
    first_content = callee.requests[0].messages[0]["content"]
    assert "Alice" in first_content and alice["id"] in first_content


def test_different_models_per_agent(bridge):
    a = _create_bot(bridge, "Ace")
    b = _create_bot(bridge, "Bash")
    _post(bridge, f"/api/fleet/bots/{a['id']}/update",
          {"model": "openrouter/model-a"})
    _post(bridge, f"/api/fleet/bots/{b['id']}/update",
          {"model": "openrouter/model-b"})
    PlanAdapter.plans = [
        [_delegation("bash", "check stuff"),
         [{"kind": "text", "text": "a done"}]],
        [[{"kind": "text", "text": "b done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "once")
    _wait_turn_end(bridge, a["id"])

    assert PlanAdapter.instances[0].requests[0].model == "openrouter/model-a"
    assert PlanAdapter.instances[1].requests[0].model == "openrouter/model-b"


def test_delegation_recorded_in_fleet_audit(bridge):
    a = _create_bot(bridge, "Audit-caller")
    b = _create_bot(bridge, "Audit-callee")
    PlanAdapter.plans = [
        [_delegation("audit-callee", "trace me"),
         [{"kind": "text", "text": "caller wraps"}]],
        [[{"kind": "text", "text": "callee answers"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "once")
    _wait_turn_end(bridge, a["id"])

    audit = fleet_routes.store().list_audit(a["id"], 50)
    assert any(x["event"] == "requested" and x["tool_name"] == "send_to_bot"
               for x in audit), "send_to_bot must appear as a request"
    assert any(x["event"] == "decided" and x["tool_name"] == "send_to_bot"
               and x["decision"] == "once" for x in audit)
    assert any(x["event"] == "outcome" and x["tool_name"] == "send_to_bot"
               for x in audit)
    blob = json.dumps(audit, default=str)
    assert "trace me" not in blob, "audit must not carry raw message text"


# ------------------------------------------------------- authorization (F1)

def test_delegation_requires_operator_approval(bridge):
    a = _create_bot(bridge, "Ana")
    b = _create_bot(bridge, "Ben")
    PlanAdapter.plans = [
        [_delegation("ben", "q"),
         [{"kind": "text", "text": "a done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    # let the card time out: delegation must NOT run
    _wait_turn_end(bridge, a["id"], timeout=10)
    ben_rows = _rows(bridge, b["id"])
    assert not any(r["kind"] == "message" for r in ben_rows), \
        "callee must never start without authorization"


def test_delegation_always_policy_applies_to_caller_only(bridge):
    a = _create_bot(bridge, "Cara")
    b = _create_bot(bridge, "Drew")
    PlanAdapter.plans = [
        [_delegation("drew", "first", "d1"),
         [{"kind": "text", "text": "cara done 1"}]],
        [[{"kind": "text", "text": "drew answer 1"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "always")
    _wait_turn_end(bridge, a["id"])

    # second delegation runs without a card: policy belongs to Cara
    PlanAdapter.plans = [
        [_delegation("drew", "second", "d2"),
         [{"kind": "text", "text": "cara done 2"}]],
        [[{"kind": "text", "text": "drew answer 2"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "again"})
    _wait_turn_end(bridge, a["id"], count=2)
    # Drew cannot delegate under Cara's policy — he gets his own card
    PlanAdapter.plans = [
        [_delegation("cara", "ping back", "d3"),
         [{"kind": "text", "text": "drew done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{b['id']}/messages", {"content": "go"})
    # B's delegation to Cara needs its own authorization decision
    pending = _wait_pending(bridge, b["id"])
    assert pending


# --------------------------------------------------- depth + cycles (F3)

def test_delegation_depth_limit_enforced(bridge):
    a = _create_bot(bridge, "Apex")
    b = _create_bot(bridge, "Branch")
    c = _create_bot(bridge, "Coral")
    d = _create_bot(bridge, "Deep")
    PlanAdapter.plans = [
        [_delegation("branch", "r1"),
         [{"kind": "text", "text": "apex done"}]],
        [_delegation("coral", "r2"),
         [{"kind": "text", "text": "branch done"}]],
        [_delegation("deep", "r3"),
         [{"kind": "text", "text": "coral done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "start"})
    # A approves → B: approve → C; C's delegation card would expire unused
    _send_and_approve(bridge, a["id"], "always")
    _send_and_approve(bridge, b["id"], "always")
    _send_and_approve(bridge, c["id"], "once")
    _wait_turn_end(bridge, a["id"], timeout=12)

    deep_rows = _rows(bridge, d["id"])
    assert not any(r["kind"] == "message" for r in deep_rows), \
        "depth limit must prevent the fourth hop"
    coral_rows = _rows(bridge, c["id"])
    coral_steps = [r for r in coral_rows if r["kind"] == "step"
                   and r["body"].get("name") == "send_to_bot"]
    assert any("depth" in str(s["body"].get("detail", "")) for s in coral_steps)


def test_circular_delegation_refused(bridge):
    a = _create_bot(bridge, "Alpha")
    b = _create_bot(bridge, "Beta")
    PlanAdapter.plans = [
        [_delegation("beta", "go deeper"),
         [{"kind": "text", "text": "alpha done"}]],
        [_delegation("alpha", "back to you"),
         [{"kind": "text", "text": "beta done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "start"})
    _send_and_approve(bridge, a["id"], "always")
    _send_and_approve(bridge, b["id"], "always")
    _wait_turn_end(bridge, a["id"], timeout=12)

    # alpha got exactly one delegated round; beta's circular call failed
    alpha_rows = _rows(bridge, a["id"])
    beta_rows = _rows(bridge, b["id"])
    alpha_delegations = [r for r in alpha_rows if r["kind"] == "message"
                         and r["body"].get("delegated_from")
                         and r["body"]["delegated_from"]["id"] == "beta"]
    assert len(alpha_delegations) == 0, "circular call must not create a nested round"
    beta_steps = [r for r in beta_rows if r["kind"] == "step"
                  and r["body"].get("name") == "send_to_bot"]
    assert beta_steps and any("circular" in str(s["body"].get("detail", ""))
                              for s in beta_steps)


def test_self_delegation_refused(bridge):
    a = _create_bot(bridge, "Solo")
    PlanAdapter.plans = [
        [_delegation("solo", "call myself"),
         [{"kind": "text", "text": "done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "once")
    _wait_turn_end(bridge, a["id"])
    steps = [r for r in _rows(bridge, a["id"]) if r["kind"] == "step"
             and r["body"].get("name") == "send_to_bot"]
    assert any("itself" in str(s["body"].get("detail", "")) for s in steps)


def test_delegation_unknown_agent(bridge):
    a = _create_bot(bridge, "U-one")
    PlanAdapter.plans = [
        [_delegation("ghost", "boo"),
         [{"kind": "text", "text": "done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "once")
    _wait_turn_end(bridge, a["id"])
    steps = [r for r in _rows(bridge, a["id"]) if r["kind"] == "step"
             and r["body"].get("name") == "send_to_bot"]
    assert any("no agent named" in str(s["body"].get("detail", "")) for s in steps)


def test_delegation_denied_card_never_runs_child(bridge):
    b = _create_bot(bridge, "Solo2")
    PlanAdapter.plans = [
        [_delegation("solo2", "self"),
         [{"kind": "text", "text": "done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{b['id']}/messages", {"content": "go"})
    # deny the card instead of approving
    pending = _wait_pending(bridge, b["id"])
    approval_id = next(iter(pending))
    _decide(bridge, b["id"], approval_id, "never")
    _wait_turn_end(bridge, b["id"])
    assert not any(r["kind"] == "message" and r["body"].get("delegated_from")
                   for r in _rows(bridge, b["id"]))


# --------------------------------------------------------------- isolation

def test_private_notes_and_history_never_leak(bridge):
    caller = _create_bot(bridge, "Marta", notes="ALPHA-SECRET-CALLER")
    callee = _create_bot(bridge, "Noah", notes="BETA-SECRET-CALLEE")
    # some prior DM history on both sides
    _post(bridge, f"/api/fleet/bots/{caller['id']}/messages",
          {"content": "CALLER-PRIVATE-HISTORY"})
    _wait_turn_end(bridge, caller["id"])

    PlanAdapter.plans = [
        [_delegation("noah", "look into this"),
         [{"kind": "text", "text": "marta done"}]],
        [[{"kind": "text", "text": "noah findings"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{caller['id']}/messages",
          {"content": "delegate to noah"})
    _send_and_approve(bridge, caller["id"], "once")
    _wait_turn_end(bridge, caller["id"], count=2)

    noah = PlanAdapter.instances[-1]
    blob = json.dumps(noah.requests[0].messages)
    assert "BETA-SECRET-CALLEE" in blob           # own notes: fine
    assert "ALPHA-SECRET-CALLER" not in blob      # caller notes: never
    assert "CALLER-PRIVATE-HISTORY" not in blob   # caller history: never


def test_denial_propagates_through_delegation(bridge, tmp_path):
    caller = _create_bot(bridge, "Olivia")
    callee = _create_bot(bridge, "Pablo")
    target = tmp_path / "never_written.txt"
    # standing never-policy for write_file on the callee only
    fleet_routes.store().set_policy(callee["id"], "write_file", "never")

    PlanAdapter.plans = [
        [_delegation("pablo", "write the file"),
         [{"kind": "text", "text": "olivia wraps"}]],
        [[{"kind": "tool", "name": "write_file",
            "input": {"path": str(target), "content": "x"},
            "id": "w1"}],
         [{"kind": "text", "text": "pablo understood: refused"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{caller['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, caller["id"], "once")
    _wait_turn_end(bridge, caller["id"])

    assert not target.exists()
    pablo_rows = _rows(bridge, callee["id"])
    steps = [r for r in pablo_rows if r["kind"] == "step"
             and r["body"].get("name") == "write_file"]
    assert any(s["body"]["status"] == "error" for s in steps)
    audit = fleet_routes.store().list_audit(callee["id"], 50)
    assert any(a["event"] == "decided" and a["decision"] == "never"
               for a in audit)


# -------------------------------------------------------- reliability (F3)

def test_provider_failure_in_callee_is_graceful(bridge):
    caller = _create_bot(bridge, "Quinn")
    callee = _create_bot(bridge, "Rosa")
    # Quinn delegates; Rosa's turn raises ProviderError inside the loop
    PlanAdapter.plans = [
        [_delegation("rosa", "hello"),
         [{"kind": "text", "text": "quinn wraps"}]],
        "FAIL",
    ]
    _post(bridge, f"/api/fleet/bots/{caller['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, caller["id"], "once")
    _wait_turn_end(bridge, caller["id"], timeout=12)

    # caller still terminates; callee recorded the provider error
    rosa_rows = _rows(bridge, callee["id"])
    assert any(r["kind"] == "notice"
               and "Provider error" in r["body"].get("text", "")
               for r in rosa_rows)
    assert any(r["kind"] == "turn_end"
               and r["body"]["terminal_reason"] == "provider_error"
               for r in rosa_rows)
    steps = [r for r in _rows(bridge, caller["id"]) if r["kind"] == "step"
             and r["body"].get("name") == "send_to_bot"]
    assert any(s["body"]["status"] == "error" for s in steps)


def test_delegation_timeout_returns_error_to_caller(bridge):
    caller = _create_bot(bridge, "Tia")
    callee = _create_bot(bridge, "Uma")
    PlanAdapter.plans = [
        [_delegation("uma", "slow task"),
         [{"kind": "text", "text": "tia wraps"}]],
        [[{"kind": "text", "text": "uma too slow"}]],
    ]
    PlanAdapter.sleep_s = 5.0  # delegate timeout is 2s in tests
    _post(bridge, f"/api/fleet/bots/{caller['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, caller["id"], "once")
    _wait_turn_end(bridge, caller["id"], timeout=10)
    PlanAdapter.sleep_s = 0.0
    # caller got an error tool_result and finished anyway
    steps = [r for r in _rows(bridge, caller["id"]) if r["kind"] == "step"
             and r["body"].get("name") == "send_to_bot"]
    assert any(s["body"]["status"] == "error" for s in steps)
    # no deadlock: caller produced a terminal turn_end
    assert _turn_end_count(bridge, caller["id"]) >= 1


def test_agent_busy_refuses_delegation(bridge):
    caller = _create_bot(bridge, "Vera")
    callee = _create_bot(bridge, "Wes")
    lock = fleet_echo.try_lock(callee["id"])   # simulate Wes mid-turn
    assert lock is not None
    try:
        PlanAdapter.plans = [
            [_delegation("wes", "busy?"), [{"kind": "text", "text": "vera wraps"}]],
        ]
        _post(bridge, f"/api/fleet/bots/{caller['id']}/messages", {"content": "go"})
        _send_and_approve(bridge, caller["id"], "once")
        _wait_turn_end(bridge, caller["id"], timeout=10)
        steps = [r for r in _rows(bridge, caller["id"]) if r["kind"] == "step"
                 and r["body"].get("name") == "send_to_bot"]
        assert steps and any("busy" in str(s["body"].get("detail", ""))
                             for s in steps)
    finally:
        fleet_echo.unlock(callee["id"], lock)


def test_concurrent_delegations_both_complete(bridge):
    p1 = _create_bot(bridge, "Pat")
    p2 = _create_bot(bridge, "Pip")
    _create_bot(bridge, "Tess")
    PlanAdapter.plans = [
        [_delegation("tess", "job pat"), [{"kind": "text", "text": "wraps"}]],
        [_delegation("tess", "job pip"), [{"kind": "text", "text": "wraps"}]],
        [[{"kind": "text", "text": "tess answer"}]],
        [[{"kind": "text", "text": "tess answer"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{p1['id']}/messages", {"content": "go"})
    _post(bridge, f"/api/fleet/bots/{p2['id']}/messages", {"content": "go"})
    pending1 = _wait_pending(bridge, p1["id"])
    pending2 = _wait_pending(bridge, p2["id"])
    _decide(bridge, p1["id"], next(iter(pending1)), "once")
    _decide(bridge, p2["id"], next(iter(pending2)), "once")
    _wait_turn_end(bridge, p1["id"], timeout=10)
    _wait_turn_end(bridge, p2["id"], timeout=10)
    # tess fails fast with agent_busy if both callers arrive mid-turn;
    # the guarantee under test is liveness: both callers complete, at
    # least one delegation lands.
    tess_rows = _rows(bridge, "tess")
    delegated = [r for r in tess_rows if r["kind"] == "message"
                 and r["body"].get("delegated_from")]
    assert len(delegated) >= 1
    assert _turn_end_count(bridge, p1["id"]) >= 1
    assert _turn_end_count(bridge, p2["id"]) >= 1



def test_delegation_rows_survive_restart(bridge, tmp_path):
    a = _create_bot(bridge, "Uma2")
    b = _create_bot(bridge, "Val")
    PlanAdapter.plans = [
        [_delegation("val", "remember this"),
         [{"kind": "text", "text": "uma wraps"}]],
        [[{"kind": "text", "text": "val remembers"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "once")
    _wait_turn_end(bridge, a["id"])
    before_a, before_b = _rows(bridge, a["id"]), _rows(bridge, b["id"])

    fleet_routes.reset_store_for_tests(bridge.db_path)

    assert len(_rows(bridge, a["id"])) == len(before_a)
    assert len(_rows(bridge, b["id"])) == len(before_b)
    callee_rows = _rows(bridge, b["id"])
    user_rows = [r for r in callee_rows if r["kind"] == "message"
                 and r["body"].get("role") == "user"]
    assert user_rows and user_rows[0]["body"]["delegated_from"]["id"] == a["id"]


def test_sse_delivers_delegation_rows(bridge, tmp_path):
    a = _create_bot(bridge, "Wren")
    b = _create_bot(bridge, "Xena")
    PlanAdapter.plans = [
        [_delegation("xena", "ping"), [{"kind": "text", "text": "wren wraps"}]],
        [[{"kind": "text", "text": "xena answers"}]],
    ]
    sock = socket.create_connection(
        ("127.0.0.1", bridge.server_address[1]), timeout=10)
    req = (f"GET /api/fleet/events?t={webapp.token()} HTTP/1.1\r\n"
           f"Host: 127.0.0.1\r\nConnection: close\r\n\r\n").encode()
    sock.sendall(req)
    try:
        _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
        pending = _wait_pending(bridge, a["id"])
        _decide(bridge, a["id"], next(iter(pending)), "once")
        buf = b""
        deadline = time.monotonic() + 10.0
        found_b = False
        while time.monotonic() < deadline and not found_b:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b'"bot_id":"xena"' in buf or b'"bot_id": "xena"' in buf:
                found_b = True
        assert found_b, "SSE never delivered a row for the callee"
    finally:
        sock.close()


def test_delegation_echo_callee(bridge):
    a = _create_bot(bridge, "Yara")
    e = _create_bot(bridge, "Echolia", engine="echo")

    PlanAdapter.plans = [
        [_delegation("echolia", "echo please"), [{"kind": "text", "text": "yara done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "go"})
    _send_and_approve(bridge, a["id"], "once")
    _wait_turn_end(bridge, a["id"], timeout=10)
    echolia_rows = _rows(bridge, e["id"])
    assistant = [r for r in echolia_rows if r["kind"] == "message"
                 and r["body"].get("role") == "assistant"]
    assert assistant and "Echo heard" in assistant[0]["body"]["content"]
