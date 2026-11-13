"""keel.fleet — F4 routines & scheduling.

Cron unit tests (parse/match/DST) + end-to-end over the real HTTP bridge
with scripted provider adapters. The scheduler's daemon never runs in
pytest — tests drive tick() directly with a controlled clock.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet import scheduler as fleet_scheduler
from keel.fleet.cron import CronError, next_run, parse_cron, period_delta, next_runs
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


# ============================================================ cron unit tests

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def test_cron_parse_errors():
    with pytest.raises(CronError):
        parse_cron("* * * *")            # 4 fields
    with pytest.raises(CronError):
        parse_cron("* * * * * *")        # 6 fields
    with pytest.raises(CronError):
        parse_cron("61 * * * *")         # out of range
    with pytest.raises(CronError):
        parse_cron("* * * FOO *")        # bad month name
    with pytest.raises(CronError):
        parse_cron("* * * * MONODAY")    # bad dow
    with pytest.raises(CronError):
        parse_cron("*/0 * * * *")        # zero step


def test_cron_dom_or_dow_when_both_restricted():
    from keel.fleet.cron import matches
    expr = parse_cron("0 9 15 * FRI")
    # both restricted → OR: the 15th (any weekday) matches, Fridays match
    assert matches(expr, datetime(2026, 6, 15, 9, 0, tzinfo=UTC))  # dom matches
    assert matches(expr, datetime(2026, 11, 13, 9, 0, tzinfo=UTC))  # Friday Nov 13 2026, not the 15th
    assert not matches(expr, datetime(2026, 11, 14, 9, 0, tzinfo=UTC))  # Sat 14th: neither


def test_cron_lists_ranges_steps():
    from keel.fleet.cron import matches
    c = parse_cron("0,30 */2 1-15 * *")
    assert matches(c, datetime(2026, 3, 3, 4, 0, tzinfo=UTC))
    assert matches(c, datetime(2026, 3, 3, 4, 30, tzinfo=UTC))
    assert not matches(c, datetime(2026, 3, 3, 5, 0, tzinfo=UTC))   # hour not even
    assert not matches(c, datetime(2026, 3, 20, 4, 0, tzinfo=UTC))  # dom out of range


def test_cron_month_and_dow_names():
    from keel.fleet.cron import matches
    c = parse_cron("0 9 * JAN MON")
    assert matches(c, datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    assert not matches(c, datetime(2026, 2, 2, 9, 0, tzinfo=UTC))


def test_cron_sunday_zero_and_seven():
    from keel.fleet.cron import matches
    c0 = parse_cron("0 9 * * 0")
    c7 = parse_cron("0 9 * * 7")
    sunday = datetime(2026, 11, 15, 9, 0, tzinfo=UTC)
    assert sunday.weekday() == 6
    assert matches(c0, sunday) and matches(c7, sunday)


def test_cron_dom_only_and_dow_only():
    from keel.fleet.cron import matches
    dom_only = parse_cron("0 9 1 * *")
    dow_only = parse_cron("0 9 * * MON")
    assert matches(dom_only, datetime(2026, 3, 1, 9, 0, tzinfo=UTC))
    assert not matches(dom_only, datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    assert matches(dow_only, datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    assert not matches(dow_only, datetime(2026, 3, 3, 9, 0, tzinfo=UTC))


def test_cron_next_run_basic():
    c = parse_cron("*/15 * * * *")
    after = datetime(2026, 11, 12, 12, 3, tzinfo=UTC)
    nxt = next_run(c, after)
    assert nxt == datetime(2026, 11, 12, 12, 15, tzinfo=UTC)


def test_cron_next_run_dom_or_dow_semantics():
    # both restricted → OR: 1st of month OR Mondays
    c = parse_cron("0 0 1 * MON")
    after = datetime(2026, 11, 28, 0, 0, tzinfo=UTC)  # Saturday Nov 28 2026
    nxt = next_run(c, after)
    # Monday Nov 30 00:00 comes via dom/dow before Dec 1
    assert nxt == datetime(2026, 11, 30, 0, 0, tzinfo=UTC)
    after2 = datetime(2026, 11, 30, 0, 1, tzinfo=UTC)
    nxt2 = next_run(c, after2)
    assert nxt2 == datetime(2026, 12, 1, 0, 0, tzinfo=UTC)  # dom before next Monday (Dec 7)


def test_cron_next_run_leap_day():
    c = parse_cron("0 0 29 2 *")
    after = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    nxt = next_run(c, after)
    assert nxt == datetime(2028, 2, 29, 0, 0, tzinfo=UTC)


def test_cron_next_run_month_boundary():
    c = parse_cron("30 23 31 * *")
    after = datetime(2026, 11, 30, 0, 0, tzinfo=UTC)
    nxt = next_run(c, after)
    assert nxt == datetime(2026, 12, 31, 23, 30, tzinfo=UTC)


def test_cron_next_run_dst_spring_forward():
    # 2026-03-08 in America/New_York: 02:30 does not exist — the slot is skipped
    c = parse_cron("30 2 * * *")
    after = datetime(2026, 3, 7, 12, 0, tzinfo=NY)  # Sat noon; next 02:30 is the gap day
    nxt = next_run(c, after)
    assert nxt.day == 9 and nxt.hour == 2 and nxt.minute == 30
    assert nxt.tzinfo is not None
    # and the slot after a normal day is that same day 02:30 if valid
    after2 = datetime(2026, 3, 7, 0, 0, tzinfo=NY)
    nxt2 = next_run(c, after2)
    assert nxt2.day == 7 and nxt2.hour == 2 and nxt2.minute == 30


def test_cron_next_run_dst_fall_back():
    # 2026-11-01 in America/New_York: 01:30 happens twice; cron fires at the first
    c = parse_cron("30 1 * * *")
    after = datetime(2026, 10, 31, 2, 0, tzinfo=NY)
    nxt = next_run(c, after)
    assert nxt.day == 1 and nxt.hour == 1 and nxt.minute == 30
    # fold=0 is the first occurrence (EDT, UTC-4)
    from datetime import timedelta
    assert nxt.utcoffset() == timedelta(hours=-4)
    from keel.fleet.cron import matches
    assert matches(c, nxt)


def test_cron_next_runs_and_period():
    c = parse_cron("0 9 * * *")
    runs = next_runs(c, datetime(2026, 11, 12, 0, 0, tzinfo=UTC), 3)
    assert [r.day for r in runs] == [12, 13, 14]
    assert period_delta(c, datetime(2026, 11, 12, 0, 0, tzinfo=UTC)).days == 1


def test_cron_next_run_timezone_aware():
    c = parse_cron("0 9 * * *")
    ny = next_run(c, datetime(2026, 11, 12, 0, 0, tzinfo=NY))
    assert ny.tzinfo is not None
    assert next_run(c, datetime(2026, 11, 12, 0, 0, tzinfo=NY)) \
        == next_run(c, datetime(2026, 11, 12, 0, 0, tzinfo=NY))


# ===================================================== fixtures (bridge)

class PlanAdapter:
    """Creation-ordered plan queue for scripted provider turns."""

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
        turn = self.plan if isinstance(self.plan, str) else \
            self.plan[min(self._turn, len(self.plan) - 1)]
        if isinstance(turn, str) and turn == "FAIL":
            from keel.providers.base import RETRY_RATE_LIMIT, ProviderError
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
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "30")
    monkeypatch.setenv("KEEL_FLEET_ROUTINE_TIMEOUT_S", "30")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("KEEL_FLEET_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: PlanAdapter(OPENROUTER,
                                                          api_key="test-key"))
    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    fleet_scheduler.reset_daemon_for_tests()
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


def _create_routine(server, bot_id, name, cron_expr="0 9 * * *",
                    timezone="UTC", prompt="do the thing", **over):
    payload = {"name": name, "bot_id": bot_id, "prompt": prompt,
               "cron_expr": cron_expr, "timezone": timezone}
    payload.update(over)
    return _post(server, "/api/fleet/routines", payload)


def _routine_detail(server, routine_id):
    status, body = _get(server, f"/api/fleet/routines/{routine_id}")
    assert status == 200
    return body["routine"]


def _runs(server, routine_id):
    status, body = _get(server, f"/api/fleet/routines/{routine_id}/runs")
    assert status == 200
    return body["runs"]


def _wait_routine_status(server, routine_id, wanted, timeout=10):
    assert _wait(lambda: _routine_detail(server, routine_id)["last_status"] == wanted,
                timeout=timeout)


def _pending_approvals(server, bot_id):
    _, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    rows = body.get("rows", [])
    states = {}
    for row in rows:
        if row["kind"] == "approval" and row["body"].get("approval_id"):
            states[row["body"]["approval_id"]] = row["body"]
    return {aid: b for aid, b in states.items() if b.get("status") == "pending"}


def _decide_approval(server, bot_id, approval_id, decision):
    return _post(server, f"/api/fleet/bots/{bot_id}/approvals/{approval_id}/decide",
                 {"decision": decision})


# ===================================================== routine CRUD over HTTP

def test_create_routine_computes_next_run(bridge):
    bot = _create_bot(bridge, "Chronos")
    status, body = _create_routine(bridge, bot["id"], "Morning brief",
                                   cron_expr="0 9 * * *", timezone="UTC")
    assert status == 201
    routine = body["routine"]
    assert routine["enabled"] == 1
    assert routine["paused"] == 0
    assert routine["next_run_at"] is not None
    # last run info absent until first execution
    assert routine["last_run_at"] is None

    status, body = _get(bridge, "/api/fleet/routines")
    assert any(r["id"] == routine["id"] for r in body["routines"])


def test_create_routine_validation(bridge):
    bot = _create_bot(bridge, "Val")
    status, _ = _create_routine(bridge, "ghost-agent-nope", "x",
                                cron_expr="0 9 * * *")
    assert status == 400
    status, _ = _create_routine(bridge, bot["id"], "bad cron",
                                cron_expr="0 9 * *")
    assert status == 400
    status, _ = _create_routine(bridge, bot["id"], "bad tz",
                                timezone="Not/AZone")
    assert status == 400
    status, _ = _create_routine(bridge, bot["id"], "", cron_expr="0 9 * * *")
    assert status == 400


def test_update_routine_and_next_run_recomputed(bridge):
    bot = _create_bot(bridge, "Morpher")
    _, body = _create_routine(bridge, bot["id"], "Morph", cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    before = body["routine"]["next_run_at"]

    status, body = _post(bridge, f"/api/fleet/routines/{rid}/update",
                         {"cron_expr": "30 15 * * *",
                          "prompt": "new prompt",
                          "name": "Renamed"})
    assert status == 200
    assert body["routine"]["cron_expr"] == "30 15 * * *"
    assert body["routine"]["prompt"] == "new prompt"
    assert body["routine"]["name"] == "Renamed"
    assert body["routine"]["next_run_at"] != before


def test_enable_disable_pause_resume(bridge):
    bot = _create_bot(bridge, "Togglr")
    _, body = _create_routine(bridge, bot["id"], "Toggle",
                              prompt="do it", cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    assert body["routine"]["enabled"] == 1

    status, body = _post(bridge, f"/api/fleet/routines/{rid}/disable", {})
    assert body["routine"]["enabled"] == 0
    status, body = _post(bridge, f"/api/fleet/routines/{rid}/enable", {})
    assert body["routine"]["enabled"] == 1
    status, body = _post(bridge, f"/api/fleet/routines/{rid}/pause",
                         {"reason": "on vacation"})
    assert body["routine"]["paused"] == 1
    assert "vacation" in body["routine"]["pause_reason"]
    # manual run refused while paused
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 409
    status, body = _post(bridge, f"/api/fleet/routines/{rid}/resume", {})
    assert body["routine"]["paused"] == 0


def test_delete_routine(bridge):
    bot = _create_bot(bridge, "Goner")
    _, body = _create_routine(bridge, bot["id"], "Gone", prompt="x",
                              cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    status, body = _post(bridge, f"/api/fleet/routines/{rid}/delete", {})
    assert body["deleted"] is True
    status, _ = _get(bridge, f"/api/fleet/routines/{rid}")
    assert status == 404


# ==================================== manual run + task/library integration

def test_manual_run_creates_task_and_file_and_conversation(bridge, tmp_path):
    bot = _create_bot(bridge, "Scribe")
    # standing Always policy: an unattended routine can save unattended
    fleet_routes.store().set_policy(bot["id"], "save_file", "always")
    _, body = _create_routine(bridge, bot["id"], "Morning brief",
                              prompt="write a brief",
                              cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "save_file",
           "input": {"filename": "brief.md", "content": "# Brief"},
           "id": "s1"}],
         [{"kind": "text", "text": "brief delivered"}]],
    ]
    status, body = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 202

    _wait_routine_status(bridge, rid, "completed", timeout=10)

    # the run row carries the task id
    runs = _runs(bridge, rid)
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"
    assert runs[0]["task_id"]

    # the task completed automatically
    _, body = _get(bridge, f"/api/fleet/tasks/{runs[0]['task_id']}")
    assert body["task"]["status"] == "completed"
    assert body["task"]["progress"] == 100

    # the file landed in the Library, attributed to the routine
    _, body = _get(bridge, f"/api/fleet/library?bot_id={bot['id']}")
    assert [f["name"] for f in body["files"]] == ["brief.md"]
    assert body["files"][0]["routine_id"] == rid

    # the agent's DM shows the routine turn
    _, body = _get(bridge, f"/api/fleet/bots/{bot['id']}/rows")
    rows = body["rows"]
    user_rows = [r for r in rows if r["kind"] == "message"
                 and "[Routine" in r["body"].get("content", "")]
    assert user_rows, "routine turn must appear in the agent conversation"
    assistant = [r for r in rows if r["kind"] == "message"
                 and r["body"].get("role") == "assistant"]
    assert assistant


def test_routine_failed_turn_marks_task_failed(bridge):
    bot = _create_bot(bridge, "Wobbly")
    _, body = _create_routine(bridge, bot["id"], "Doomed run",
                              prompt="do something impossible",
                              cron_expr="0 9 * * *")
    rid = body["routine"]["id"]

    class HardError(PlanAdapter):
        pass

    PlanAdapter.plans = [
        "FAIL",
    ]
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 202
    _wait_routine_status(bridge, rid, "failed", timeout=10)
    runs = _runs(bridge, rid)
    assert runs[0]["task_id"]
    _, body = _get(bridge, f"/api/fleet/tasks/{runs[0]['task_id']}")
    assert body["task"]["status"] == "failed"


def test_routine_blocked_on_card_flips_awaiting_approval(bridge, tmp_path):
    bot = _create_bot(bridge, "Cautious")
    target = tmp_path / "blocked.txt"
    _, body = _create_routine(bridge, bot["id"], "Risky",
                              prompt="write the file",
                              cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "write_file",
           "input": {"path": str(target), "content": "blocked"},
           "id": "w1"}],
         [{"kind": "text", "text": "after denial"}]],
    ]
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 202

    # live flip: the unattended run shows awaiting_approval while the card is open
    assert _wait(lambda: any(r["status"] == "awaiting_approval"
                             for r in _runs(bridge, rid)),
                timeout=10)

    # the operator clicks Don't allow — the turn must refuse the write
    pending = _pending_approvals(bridge, bot["id"])
    approval_id = next(iter(pending))
    status, _ = _decide_approval(bridge, bot["id"], approval_id, "never")
    assert status == 200
    _wait_routine_status(bridge, rid, "failed", timeout=10)
    assert not target.exists()
    runs = _runs(bridge, rid)
    assert "approval denied" in (runs[0]["error"] or "").lower()
    _, body = _get(bridge, f"/api/fleet/tasks/{runs[0]['task_id']}")
    assert body["task"]["status"] == "failed"


def test_routine_approval_timeout_fails_closed(bridge, tmp_path):
    bot = _create_bot(bridge, "Waiter")
    fleet_routes.store().approvals.timeout_s = 0.5
    target = tmp_path / "timeout.txt"
    _, body = _create_routine(bridge, bot["id"], "LateAnswer",
                              prompt="write the file",
                              cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "write_file",
           "input": {"path": str(target), "content": "blocked"},
           "id": "w1"}],
         [{"kind": "text", "text": "done after timeout"}]],
    ]
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 202
    # no operator ever answers: the card expires at 0.5s and the run fails closed
    _wait_routine_status(bridge, rid, "failed", timeout=10)
    assert not target.exists()
    runs = _runs(bridge, rid)
    assert "timed out" in (runs[0]["error"] or "").lower()
    _, body = _get(bridge, f"/api/fleet/tasks/{runs[0]['task_id']}")
    assert body["task"]["status"] == "failed"
    # audit shows the timeout decision
    audit = fleet_routes.store().list_audit(bot["id"], 20)
    assert any(a["event"] == "decided" and a["decision"] == "timeout"
               for a in audit)


def test_routine_approval_always_policy_allows_unattended_run(bridge, tmp_path):
    bot = _create_bot(bridge, "Preapproved")
    target = tmp_path / "preapproved.txt"
    fleet_routes.store().set_policy(bot["id"], "write_file", "always")
    _, body = _create_routine(bridge, bot["id"], "Writer",
                              prompt="write the file",
                              cron_expr="0 9 * * *")
    rid = body["routine"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "tool", "name": "write_file",
           "input": {"path": str(target), "content": "allowed"},
           "id": "w1"}],
         [{"kind": "text", "text": "written"}]],
    ]
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 202
    _wait_routine_status(bridge, rid, "completed", timeout=10)
    assert target.exists()


# ============================================ scheduler tick / missed runs

def test_tick_executes_due_routine(bridge, tmp_path):
    bot = _create_bot(bridge, "Ticker")
    _, body = _create_routine(bridge, bot["id"], "Tickme",
                              prompt="say hi", cron_expr="*/1 * * * *")
    rid = body["routine"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "ticked"}]],
    ]
    # force the routine to be due right now
    past = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 20))
    with fleet_routes.store()._lock:
        fleet_routes.store()._conn.execute(
            "UPDATE fleet_routines SET next_run_at = ? WHERE id = ?",
            (past, rid))
        fleet_routes.store()._conn.commit()

    started = fleet_scheduler.tick(fleet_routes.store())
    assert started, "tick must start the due routine"
    _wait_routine_status(bridge, rid, "completed", timeout=10)


def test_skip_missed_slot_not_executed(bridge):
    bot = _create_bot(bridge, "Skipper")
    _, body = _create_routine(bridge, bot["id"], "Skippable",
                              prompt="should not run",
                              cron_expr="*/1 * * * *")
    rid = body["routine"]["id"]
    past = time.strftime("%Y-%m-%dT%H:%M:%S.000Z",
                         time.gmtime(time.time() - 7200))  # 2 hours overdue
    with fleet_routes.store()._lock:
        fleet_routes.store()._conn.execute(
            "UPDATE fleet_routines SET next_run_at = ? WHERE id = ?",
            (past, rid))
        fleet_routes.store()._conn.commit()

    started = fleet_scheduler.tick(fleet_routes.store())
    assert started == [], "overdue-by-more-than-period must not fire"
    runs = _runs(bridge, rid)
    assert len(runs) == 1
    assert runs[0]["status"] == "skipped_missed"
    # next slot advanced into the future
    assert _routine_detail(bridge, rid)["next_run_at"] > past


def test_tick_advances_past_slot_and_no_duplicate(bridge):
    bot = _create_bot(bridge, "Once")
    _, body = _create_routine(bridge, bot["id"], "FiresOnce",
                              prompt="hi", cron_expr="*/1 * * * *")
    rid = body["routine"]["id"]
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "fired once"}]],
    ]
    past = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 30))
    with fleet_routes.store()._lock:
        fleet_routes.store()._conn.execute(
            "UPDATE fleet_routines SET next_run_at = ? WHERE id = ?",
            (past, rid))
        fleet_routes.store()._conn.commit()
    fleet_scheduler.tick(fleet_routes.store())
    _wait_routine_status(bridge, rid, "completed", timeout=10)
    fleet_scheduler.tick(fleet_routes.store())   # next slot is in the future
    runs = _runs(bridge, rid)
    assert len(runs) == 1, "no duplicate execution for the same slot"


def test_routine_running_claim_blocks_concurrent_ticks(bridge):
    bot = _create_bot(bridge, "Exclusive")
    _, body = _create_routine(bridge, bot["id"], "Locked",
                              prompt="x", cron_expr="*/1 * * * *")
    rid = body["routine"]["id"]
    store = fleet_routes.store()
    assert store.claim_routine(rid) is True
    assert store.claim_routine(rid) is False  # already claimed
    store.release_routine(rid)
    assert store.claim_routine(rid) is True
    store.release_routine(rid)


# =================================================== restart / persistence

def test_routine_survives_restart(bridge, tmp_path):
    bot = _create_bot(bridge, "Persist")
    _, body = _create_routine(bridge, bot["id"], "Stable",
                              prompt="persist me", cron_expr="0 9 * * *",
                              timezone="Europe/Berlin")
    rid = body["routine"]["id"]
    fleet_routes.reset_store_for_tests(bridge.db_path)
    status, body = _get(bridge, f"/api/fleet/routines/{rid}")
    assert status == 200
    assert body["routine"]["timezone"] == "Europe/Berlin"


def test_interrupted_run_swept_on_restart(bridge, tmp_path):
    bot = _create_bot(bridge, "Interrupted")
    _, body = _create_routine(bridge, bot["id"], "CrashTest",
                              prompt="x", cron_expr="*/1 * * * *")
    rid = body["routine"]["id"]
    store = fleet_routes.store()
    tid = store.create_task(title="Routine: CrashTest", assigned_bot_id=bot["id"],
                            created_by=bot["id"])["id"]
    run_id = store.create_routine_run(rid, scheduled_at="2026-11-12T00:00:00.000Z",
                                      task_id=tid)
    store.claim_routine(rid)

    fleet_routes.reset_store_for_tests(bridge.db_path)

    status, body = _get(bridge, f"/api/fleet/routines/{rid}/runs")
    assert body["runs"][0]["status"] == "failed"
    assert "interrupted" in body["runs"][0]["error"]
    status, body = _get(bridge, f"/api/fleet/tasks/{tid}")
    assert body["task"]["status"] == "failed"


# ================================================ providers & gating

def test_manual_run_409_when_disabled_and_when_paused(bridge):
    bot = _create_bot(bridge, "Switch")
    _, body = _create_routine(bridge, bot["id"], "Switchoff",
                              prompt="x", cron_expr="0 9 * * *",
                              enabled=False)
    rid = body["routine"]["id"]
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 409
    _post(bridge, f"/api/fleet/routines/{rid}/enable", {})
    _post(bridge, f"/api/fleet/routines/{rid}/pause",
          {"reason": "hold"})
    status, _ = _post(bridge, f"/api/fleet/routines/{rid}/run", {})
    assert status == 409


def test_routine_runs_with_agent_model(bridge):
    a = _create_bot(bridge, "ModelA")
    b = _create_bot(bridge, "ModelB")
    _post(bridge, f"/api/fleet/bots/{a['id']}/update",
          {"model": "openrouter/model-a"})
    _post(bridge, f"/api/fleet/bots/{b['id']}/update",
          {"model": "openrouter/model-b"})
    _, ra = _create_routine(bridge, a["id"], "RA", prompt="one",
                            cron_expr="0 9 * * *")
    _, rb = _create_routine(bridge, b["id"], "RB", prompt="two",
                            cron_expr="0 10 * * *")
    PlanAdapter.plans = [
        [[{"kind": "text", "text": "from a"}]],
        [[{"kind": "text", "text": "from b"}]],
    ]
    _post(bridge, f"/api/fleet/routines/{ra['routine']['id']}/run", {})
    _wait_routine_status(bridge, ra["routine"]["id"], "completed", timeout=10)
    _post(bridge, f"/api/fleet/routines/{rb['routine']['id']}/run", {})
    _wait_routine_status(bridge, rb["routine"]["id"], "completed", timeout=10)
    # adapters constructed in run order
    assert PlanAdapter.instances[0].requests[0].model == "openrouter/model-a"
    assert PlanAdapter.instances[1].requests[0].model == "openrouter/model-b"


def test_routine_delete_requires_existing_routine(bridge):
    status, _ = _post(bridge, "/api/fleet/routines/r_nonexistent/delete", {})
    assert status == 404
