"""keel.fleet — F2 tasks: creation, assignment, lifecycle, authorization.

End-to-end over the real HTTP bridge with a creation-ordered plan adapter.
HTTP flows are driven through /api/fleet/tasks; agent flows drive the same
paths through the tool loop with scripted provider responses.
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


class PlanAdapter:
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
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "30")
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
    return _pending(_rows(server, bot_id))


def _decide(server, bot_id, approval_id, decision):
    return _post(server, f"/api/fleet/bots/{bot_id}/approvals/{approval_id}/decide",
                 {"decision": decision})


def _approve_once(server, bot_id):
    pending = _wait_pending(server, bot_id)
    approval_id = next(iter(pending))
    status, _ = _decide(server, bot_id, approval_id, "once")
    assert status == 200


def _wait_turn_end(server, bot_id, count=1, timeout=10):
    assert _wait(lambda: sum(1 for r in _rows(server, bot_id)
                             if r["kind"] == "turn_end") >= count,
                timeout=timeout)


def _notice_texts(server, bot_id):
    return [r["body"].get("text", "")
            for r in _rows(server, bot_id) if r["kind"] == "notice"]


def _task_tool(name, input, call_id="task_1"):
    return [{"kind": "tool", "name": name, "input": input, "id": call_id}]


# ------------------------------------------------------------ HTTP user flows

def test_user_creates_task_and_agent_gets_notice(bridge):
    agent = _create_bot(bridge, "Owner")
    status, created = _post(bridge, "/api/fleet/tasks", {
        "title": "review the memo",
        "description": "read it and flag errors",
        "priority": "high",
        "assigned_bot_id": agent["id"],
    })
    assert status == 201
    task = created["task"]
    assert task["status"] == "pending"
    assert task["progress"] == 0
    assert task["priority"] == "high"
    assert task["assigned_bot_id"] == agent["id"]
    assert task["created_by"] == "user"

    texts = _notice_texts(bridge, agent["id"])
    assert any("Task assigned by operator" in t and "review the memo" in t
               for t in texts)


def test_task_validation(bridge):
    agent = _create_bot(bridge, "Val")
    status, _ = _post(bridge, "/api/fleet/tasks", {
        "title": "", "assigned_bot_id": agent["id"]})
    assert status == 400
    status, _ = _post(bridge, "/api/fleet/tasks", {
        "title": "x", "priority": "urgent-ish"})
    assert status == 400
    status, _ = _post(bridge, "/api/fleet/tasks", {
        "title": "x", "assigned_bot_id": "nonexistent-agent"})
    assert status == 400


def test_task_lifecycle_via_http(bridge):
    agent = _create_bot(bridge, "Life")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "ship it", "assigned_bot_id": agent["id"]})
    tid = created["task"]["id"]

    status, body = _post(bridge, f"/api/fleet/tasks/{tid}/update",
                         {"status": "in_progress", "progress": 40})
    assert status == 200
    assert body["task"]["status"] == "in_progress"
    assert body["task"]["progress"] == 40

    status, body = _post(bridge, f"/api/fleet/tasks/{tid}/update",
                         {"status": "completed"})
    assert body["task"]["status"] == "completed"
    assert body["task"]["progress"] == 100
    assert body["task"]["completed_at"] is not None

    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    events = [(e["actor"], e["event"]) for e in body["events"]]
    assert ("user", "created") in events
    assert ("user", "status") in events
    assert ("user", "progress") in events

    # reopen + cancel + delete
    _post(bridge, f"/api/fleet/tasks/{tid}/update", {"status": "pending"})
    status, body = _post(bridge, f"/api/fleet/tasks/{tid}/cancel", {})
    assert body["task"]["status"] == "cancelled"
    status, body = _post(bridge, f"/api/fleet/tasks/{tid}/delete", {})
    assert body["deleted"] is True
    status, _ = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert status == 404


def test_task_reassign_and_edit(bridge):
    a = _create_bot(bridge, "Ran-a")
    b = _create_bot(bridge, "Ran-b")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "pass it on", "assigned_bot_id": a["id"]})
    tid = created["task"]["id"]

    status, body = _post(bridge, f"/api/fleet/tasks/{tid}/assign",
                         {"assigned_bot_id": b["id"]})
    assert status == 200
    assert body["task"]["assigned_bot_id"] == b["id"]
    texts = _notice_texts(bridge, b["id"])
    assert any("pass it on" in t for t in texts)

    status, body = _post(bridge, f"/api/fleet/tasks/{tid}/update",
                         {"title": "renamed task", "priority": "low",
                          "description": "new desc"})
    assert body["task"]["title"] == "renamed task"
    assert body["task"]["priority"] == "low"


def test_task_list_filters(bridge):
    a = _create_bot(bridge, "ListA")
    b = _create_bot(bridge, "ListB")
    _, t1 = _post(bridge, "/api/fleet/tasks",
                  {"title": "a's task", "assigned_bot_id": a["id"]})
    _, t2 = _post(bridge, "/api/fleet/tasks",
                  {"title": "b's task", "assigned_bot_id": b["id"]})
    _, t3 = _post(bridge, "/api/fleet/tasks", {"title": "orphan"})

    status, body = _get(bridge, "/api/fleet/tasks?assigned=" + a["id"])
    assert [t["id"] for t in body["tasks"]] == [t1["task"]["id"]]

    status, body = _get(bridge, "/api/fleet/tasks?assigned=unassigned")
    assert [t["id"] for t in body["tasks"]] == [t3["task"]["id"]]

    status, body = _get(bridge, "/api/fleet/tasks?assigned=all")
    assert len(body["tasks"]) == 3

    _post(bridge, f"/api/fleet/tasks/{t2['task']['id']}/update",
          {"status": "completed"})
    status, body = _get(bridge, "/api/fleet/tasks?status=completed")
    assert [t["id"] for t in body["tasks"]] == [t2["task"]["id"]]


# --------------------------------------------------------------- agent flows

def test_agent_creates_task_for_itself(bridge):
    agent = _create_bot(bridge, "Maker")
    PlanAdapter.plans = [
        [_task_tool("create_task", {"title": "gather sources"}),
         [{"kind": "text", "text": "created it"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages",
          {"content": "track this"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"])

    status, body = _get(bridge, f"/api/fleet/tasks?assigned={agent['id']}")
    assert [t["title"] for t in body["tasks"]] == ["gather sources"]
    texts = _notice_texts(bridge, agent["id"])
    assert any("Task created" in t and "gather sources" in t for t in texts)


def test_agent_assigns_task_to_another_agent(bridge):
    a = _create_bot(bridge, "Passer")
    b = _create_bot(bridge, "Taker")
    PlanAdapter.plans = [
        [_task_tool("create_task", {"title": "draft the section",
                                    "assignee": b["id"],
                                    "priority": "high"}),
         [{"kind": "text", "text": "assigned"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages",
          {"content": "hand it off"})
    _approve_once(bridge, a["id"])
    _wait_turn_end(bridge, a["id"])

    status, body = _get(bridge, f"/api/fleet/tasks?assigned={b['id']}")
    assert [t["title"] for t in body["tasks"]] == ["draft the section"]
    texts = _notice_texts(bridge, b["id"])
    assert any("Task assigned" in t and "draft the section" in t for t in texts)


def test_agent_updates_own_task_to_done(bridge):
    agent = _create_bot(bridge, "Finisher")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "existing chore",
                        "assigned_bot_id": agent["id"]})
    tid = created["task"]["id"]

    PlanAdapter.plans = [
        [_task_tool("update_task", {"task_id": tid, "status": "in_progress",
                                    "progress": 50}),
         [{"kind": "text", "text": "halfway"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages",
          {"content": "start the chore"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"])
    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert body["task"]["status"] == "in_progress"
    assert body["task"]["progress"] == 50

    PlanAdapter.plans = [
        [_task_tool("update_task", {"task_id": tid, "status": "completed"}),
         [{"kind": "text", "text": "done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages",
          {"content": "finish the chore"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"], count=2)
    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert body["task"]["status"] == "completed"
    assert body["task"]["progress"] == 100
    events = [(e["actor"], e["event"]) for e in body["events"]]
    assert (agent["id"], "status") in events


def test_agent_cannot_touch_others_tasks(bridge):
    a = _create_bot(bridge, "Mine")
    b = _create_bot(bridge, "Theirs")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "bot b chore", "assigned_bot_id": b["id"]})
    tid = created["task"]["id"]

    PlanAdapter.plans = [
        [_task_tool("update_task", {"task_id": tid, "status": "completed"}),
         [{"kind": "text", "text": "nope"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages", {"content": "close it"})
    _approve_once(bridge, a["id"])
    _wait_turn_end(bridge, a["id"])
    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert body["task"]["status"] == "pending"  # untouched


def test_agent_task_tools_need_approval(bridge):
    agent = _create_bot(bridge, "Cautious")
    PlanAdapter.plans = [
        [_task_tool("create_task", {"title": "quiet task"}),
         [{"kind": "text", "text": "after denial"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages",
          {"content": "make a task"})
    pending = _wait_pending(bridge, agent["id"], timeout=8)
    approval_id = next(iter(pending))
    status, _ = _decide(bridge, agent["id"], approval_id, "never")
    assert status == 200
    _wait_turn_end(bridge, agent["id"])
    status, body = _get(bridge, f"/api/fleet/tasks?assigned={agent['id']}")
    assert body["tasks"] == []


def test_always_allow_policy_for_tasks(bridge):
    agent = _create_bot(bridge, "Handy")
    PlanAdapter.plans = [
        [_task_tool("create_task", {"title": "first task"}),
         [{"kind": "text", "text": "one"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages", {"content": "go 1"})
    pending = _wait_pending(bridge, agent["id"])
    approval_id = next(iter(pending))
    status, _ = _decide(bridge, agent["id"], approval_id, "always")
    assert status == 200
    _wait_turn_end(bridge, agent["id"])

    PlanAdapter.plans = [
        [_task_tool("create_task", {"title": "second task"}),
         [{"kind": "text", "text": "two"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages", {"content": "go 2"})
    _wait_turn_end(bridge, agent["id"], count=2)
    status, body = _get(bridge, f"/api/fleet/tasks?assigned={agent['id']}")
    assert {t["title"] for t in body["tasks"]} == {"first task", "second task"}


# ----------------------------------------------- delegation → task linking

def test_delegation_links_task_end_to_end(bridge):
    a = _create_bot(bridge, "Lead")
    b = _create_bot(bridge, "Research")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "find the numbers",
                        "assigned_bot_id": b["id"]})
    tid = created["task"]["id"]

    PlanAdapter.plans = [
        [_task_tool("send_to_bot", {"bot_slug": "research",
                                    "message": "find the numbers",
                                    "task_id": tid}),
         [{"kind": "text", "text": "lead wraps"}]],
        [[{"kind": "tool", "name": "update_task",
            "input": {"task_id": tid, "status": "completed"},
            "id": "update_1"}],
         [{"kind": "text", "text": "task done"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{a['id']}/messages",
          {"content": "delegate the task"})
    _approve_once(bridge, a["id"])   # approve send_to_bot
    _approve_once(bridge, b["id"])   # approve b's update_task
    _wait_turn_end(bridge, a["id"], timeout=12)

    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert body["task"]["status"] == "completed"
    events = body["events"]
    delegated = [e for e in events if e["event"] == "delegated"]
    assert delegated and delegated[0]["actor"] == a["id"]
    assert "research" in delegated[0]["note"]


def test_create_task_with_bad_assignee(bridge):
    agent = _create_bot(bridge, "BadFix")
    PlanAdapter.plans = [
        [_task_tool("create_task", {"title": "x", "assignee": "ghost-agent"}),
         [{"kind": "text", "text": "end"}]],
    ]
    _post(bridge, f"/api/fleet/bots/{agent['id']}/messages",
          {"content": "try"})
    _approve_once(bridge, agent["id"])
    _wait_turn_end(bridge, agent["id"])
    status, body = _get(bridge, "/api/fleet/tasks?assigned=all")
    assert body["tasks"] == []


# -------------------------------------------------------------- persistence

def test_tasks_survive_restart(bridge, tmp_path):
    agent = _create_bot(bridge, "Persist")
    _, created = _post(bridge, "/api/fleet/tasks",
                       {"title": "survive me", "assigned_bot_id": agent["id"]})
    tid = created["task"]["id"]
    _post(bridge, f"/api/fleet/tasks/{tid}/update",
          {"status": "in_progress", "progress": 30})

    fleet_routes.reset_store_for_tests(bridge.db_path)

    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert status == 200
    assert body["task"]["status"] == "in_progress"
    assert body["task"]["progress"] == 30
    assert body["events"], "event history must survive restarts"
