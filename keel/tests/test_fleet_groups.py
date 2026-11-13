"""keel.fleet — F3 bounded group conversations.

Groups are 2–3 agents with a shared persistent ledger (`group_rows` in
fleet.db v3). The user's message fans out to each member exactly once per
round; members answer with their own provider/model/permissions; there is
no automatic agent-to-agent fan-out beyond explicit, depth-capped
send_to_bot delegations.
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet import echo as fleet_echo
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


class PlanAdapter:
    """Creation-ordered plan queue (see test_fleet_delegation.py)."""

    plans: list[list] = []
    instances: list["PlanAdapter"] = []

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
        turn = self.plan[min(self._turn, len(self.plan) - 1)]
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
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "1")
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


def _create_group(server, name, bot_ids):
    status, created = _post(server, "/api/fleet/groups",
                            {"name": name, "bot_ids": bot_ids})
    return status, created


def _group_rows(server, gid):
    _, body = _get(server, f"/api/fleet/groups/{gid}")
    return body.get("rows", [])


def _member_messages(server, gid):
    return [r for r in _group_rows(server, gid)
            if r["kind"] == "message" and r["author"] != "user"]


def _wait_group_replies(server, gid, count, timeout=10):
    assert _wait(lambda: len(_member_messages(server, gid)) >= count,
                timeout=timeout)


def _wait_round_done(server, gid, member_count, timeout=10, total=None):
    """Every member emits running + final member_status rows per round;
    `total` is the cumulative count to wait for across rounds."""
    need = total if total is not None else 2 * member_count
    assert _wait(lambda: len([r for r in _group_rows(server, gid)
                              if r["kind"] == "member_status"]) >= need,
                timeout=timeout)


# --------------------------------------------------------------- lifecycle

def test_create_group_validates_participants(bridge):
    a = _create_bot(bridge, "One")
    b = _create_bot(bridge, "Two")
    c = _create_bot(bridge, "Three")
    d = _create_bot(bridge, "Four")

    status, _ = _create_group(bridge, "TooSmall", [a["id"]])
    assert status == 400
    status, _ = _create_group(bridge, "TooBig",
                              [a["id"], b["id"], c["id"], d["id"]])
    assert status == 400
    status, _ = _create_group(bridge, "Dupes", [a["id"], a["id"]])
    assert status == 400
    status, _ = _create_group(bridge, "Ghosts", [a["id"], "nonexistent-bot"])
    assert status == 400

    status, created = _create_group(bridge, "Pod", [a["id"], b["id"], c["id"]])
    assert status == 201
    group = created["group"]
    assert [m["id"] for m in group["members"]] == [a["id"], b["id"], c["id"]]


def test_group_listing_and_detail(bridge):
    a = _create_bot(bridge, "Aone")
    b = _create_bot(bridge, "Atwo")
    _, created = _create_group(bridge, "Desk", [a["id"], b["id"]])
    gid = created["group"]["id"]

    status, body = _get(bridge, "/api/fleet/groups")
    assert status == 200
    assert any(g["id"] == gid for g in body["groups"])

    status, body = _get(bridge, f"/api/fleet/groups/{gid}")
    assert status == 200
    assert body["group"]["name"] == "Desk"
    assert {m["id"] for m in body["group"]["members"]} == {a["id"], b["id"]}
    assert body["rows"], "creation notice should be recorded"


def test_group_delete(bridge):
    a = _create_bot(bridge, "Gone1")
    b = _create_bot(bridge, "Gone2")
    _, created = _create_group(bridge, "Doomed", [a["id"], b["id"]])
    gid = created["group"]["id"]
    status, body = _post(bridge, f"/api/fleet/groups/{gid}/delete", {})
    assert status == 200 and body["deleted"] is True
    status, _ = _get(bridge, f"/api/fleet/groups/{gid}")
    assert status == 404


# ------------------------------------------------------------------ rounds

def test_group_round_each_member_answers_once(bridge):
    a = _create_bot(bridge, "Finn")
    b = _create_bot(bridge, "Gia")
    _, created = _create_group(bridge, "Pair", [a["id"], b["id"]])
    gid = created["group"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "finn says hi"}]],
        [[{"kind": "text", "text": "gia says hi"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "hello both"})
    _wait_group_replies(bridge, gid, 2)
    replies = _member_messages(bridge, gid)
    assert {r["author"] for r in replies} == {a["id"], b["id"]}
    assert all((r["body"].get("content") or "") != "" for r in replies)

    rows = _group_rows(bridge, gid)
    user_rows = [r for r in rows if r["author"] == "user"]
    assert len(user_rows) == 1 and user_rows[0]["body"]["content"] == "hello both"


def test_group_round_records_member_status(bridge):
    a = _create_bot(bridge, "Ike")
    b = _create_bot(bridge, "Ivy")
    _, created = _create_group(bridge, "Duo", [a["id"], b["id"]])
    gid = created["group"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "ike reply"}]],
        [[{"kind": "text", "text": "ivy reply"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "go"})
    _wait_group_replies(bridge, gid, 2)
    statuses = [r for r in _group_rows(bridge, gid)
                if r["kind"] == "member_status"]
    by_bot = {}
    for r in statuses:
        by_bot.setdefault(r["body"]["bot_id"], []).append(r["body"]["status"])
    for bot_id in (a["id"], b["id"]):
        assert by_bot.get(bot_id), f"no status rows for {bot_id}"
        assert "running" in by_bot[bot_id]
        assert by_bot[bot_id][-1] in ("done", "denied")


def test_group_member_private_dms_untouched(bridge):
    a = _create_bot(bridge, "Leo")
    b = _create_bot(bridge, "Lia")
    _, created = _create_group(bridge, "Hush", [a["id"], b["id"]])
    gid = created["group"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "leo secret reply"}]],
        [[{"kind": "text", "text": "lia secret reply"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "quiet please"})
    _wait_group_replies(bridge, gid, 2)
    for member_id in (a["id"], b["id"]):
        dm = _get(bridge, f"/api/fleet/bots/{member_id}/rows")[1].get("rows", [])
        assert not any(r["kind"] == "message" for r in dm), \
            "group rounds must not leak into member DMs"


def test_group_denial_shows_denied_status(bridge, tmp_path):
    a = _create_bot(bridge, "Moe")
    b = _create_bot(bridge, "Max")
    target = tmp_path / "never_in_group.txt"
    _, created = _create_group(bridge, "Deny", [a["id"], b["id"]])
    gid = created["group"]["id"]
    # Max carries a standing never-policy for write_file
    fleet_routes.store().set_policy(b["id"], "write_file", "never")
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "moe is fine"}]],
        [[{"kind": "tool", "name": "write_file",
            "input": {"path": str(target), "content": "x"}, "id": "w1"}],
         [{"kind": "text", "text": "max is done, file not written"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "do the thing"})
    _wait_round_done(bridge, gid, 2)
    statuses = {}
    for r in _group_rows(bridge, gid):
        if r["kind"] == "member_status":
            if r["body"]["status"] in ("done", "denied", "failed", "busy"):
                statuses[r["body"]["bot_id"]] = r["body"]
    assert statuses[a["id"]]["status"] == "done"
    assert statuses[b["id"]]["status"] == "denied"
    assert statuses[b["id"]]["denied_calls"] >= 1
    assert not target.exists()


def test_group_busy_round_rejected(bridge):
    a = _create_bot(bridge, "Busy1")
    b = _create_bot(bridge, "Busy2")
    _, created = _create_group(bridge, "Jam", [a["id"], b["id"]])
    gid = created["group"]["id"]
    from keel.fleet import groups as fleet_groups
    rlock = fleet_groups.group_round_lock(gid)
    assert rlock.acquire(blocking=False)
    try:
        status, body = _post(bridge, f"/api/fleet/groups/{gid}/messages",
                             {"content": "second while busy"})
        assert status == 409
    finally:
        rlock.release()
    # after the round frees up, posting works again
    status, body = _post(bridge, f"/api/fleet/groups/{gid}/messages",
                         {"content": "third, after release"})
    assert status == 202
    _wait_group_replies(bridge, gid, 2)


def test_group_member_busy_skipped(bridge):
    a = _create_bot(bridge, "Cool1")
    b = _create_bot(bridge, "Cool2")
    _, created = _create_group(bridge, "Skip", [a["id"], b["id"]])
    gid = created["group"]["id"]
    held = fleet_echo.try_lock(b["id"])   # simulate b mid-turn elsewhere
    assert held is not None
    try:
        PlanAdapter.plans = [
            [[{"kind": "text", "text": "cool1 answers"}]],
        ]
        _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "hello"})
        _wait(lambda: any(r["kind"] == "member_status"
                          and r["body"]["bot_id"] == b["id"]
                          and r["body"]["status"] == "busy"
                          for r in _group_rows(bridge, gid)), timeout=8)
        _wait_group_replies(bridge, gid, 1)
    finally:
        fleet_echo.unlock(b["id"], held)


def test_group_echo_members(bridge):
    a = _create_bot(bridge, "Fax", engine="echo")
    b = _create_bot(bridge, "Sey", engine="echo")
    _, created = _create_group(bridge, "Echoes", [a["id"], b["id"]])
    gid = created["group"]["id"]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "hi echoes"})
    _wait_group_replies(bridge, gid, 2)
    contents = [r["body"]["content"] for r in _member_messages(bridge, gid)]
    assert all("Echo heard you say" in c for c in contents)


def test_group_rows_survive_restart(bridge, tmp_path):
    a = _create_bot(bridge, "Keep1")
    b = _create_bot(bridge, "Keep2")
    _, created = _create_group(bridge, "Vault", [a["id"], b["id"]])
    gid = created["group"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "keep1 here"}]],
        [[{"kind": "text", "text": "keep2 here"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "persist me"})
    _wait_round_done(bridge, gid, 2)
    before = _group_rows(bridge, gid)

    fleet_routes.reset_store_for_tests(bridge.db_path)

    status, body = _get(bridge, f"/api/fleet/groups/{gid}")
    assert status == 200
    assert body["group"]["name"] == "Vault"
    assert len(body["rows"]) == len(before)
    assert any(r["body"].get("content") == "keep1 here" for r in body["rows"])


def test_group_participant_cap_backend_enforced(bridge):
    a = _create_bot(bridge, "Cap1")
    b = _create_bot(bridge, "Cap2")
    c = _create_bot(bridge, "Cap3")
    d = _create_bot(bridge, "Cap4")
    # 4 agents must be rejected at the backend, not just the UI
    status, body = _post(bridge, "/api/fleet/groups",
                         {"name": "Crowd", "bot_ids": [a["id"], b["id"],
                                                       c["id"], d["id"]]})
    assert status == 400
    status, body = _post(bridge, "/api/fleet/groups",
                         {"name": "Solo", "bot_ids": [a["id"]]})
    assert status == 400


def test_sse_delivers_group_rows(bridge, tmp_path):
    import socket
    a = _create_bot(bridge, "Zed")
    b = _create_bot(bridge, "Yan")
    _, created = _create_group(bridge, "Live", [a["id"], b["id"]])
    gid = created["group"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "zed live"}]],
        [[{"kind": "text", "text": "yan live"}]],
    ]
    sock = socket.create_connection(
        ("127.0.0.1", bridge.server_address[1]), timeout=10)
    req = (f"GET /api/fleet/events?t={webapp.token()} HTTP/1.1\r\n"
           f"Host: 127.0.0.1\r\nConnection: close\r\n\r\n").encode()
    sock.sendall(req)
    try:
        _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "go"})
        buf = b""
        deadline = time.monotonic() + 10.0
        found = False
        while time.monotonic() < deadline and not found:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b'"group_id"' in buf:
                found = True
        assert found, "SSE never delivered a group row"
    finally:
        sock.close()


def test_groups_see_each_others_messages(bridge):
    """Between rounds, a member's next turn must see the shared history."""
    a = _create_bot(bridge, "Hal")
    b = _create_bot(bridge, "Amy")
    _, created = _create_group(bridge, "Recall", [a["id"], b["id"]])
    gid = created["group"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "hal first"}]],
        [[{"kind": "text", "text": "amy first"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "round one"})
    _wait_round_done(bridge, gid, 2)

    PlanAdapter.plans = [
        [[{"kind": "text", "text": "hal second"}]],
        [[{"kind": "text", "text": "amy second"}]],
    ]
    _post(bridge, f"/api/fleet/groups/{gid}/messages", {"content": "round two"})
    _wait_round_done(bridge, gid, 2, timeout=10, total=8)
    hal_adapter = PlanAdapter.instances[2]  # third adapter = hal's second turn
    blob = json.dumps(hal_adapter.requests[0].messages)
    assert "round one" in blob
    assert "amy first" in blob  # shared history is visible to members
    assert "hal second" not in blob  # current turn isn't in its own history
