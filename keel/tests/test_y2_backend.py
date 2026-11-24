"""Permanent contract-regression specs for the 15 not_started Y2 P1 rows.

One or more tests per registry ID:
Y2.9, Y2.10, Y2.11, Y2.12, Y2.13, Y2.15, Y2.16, Y2.17, Y2.18, Y2.19,
Y2.21, Y2.22, Y2.23, Y2.24, Y2.25.

These specs are additive: they import only ``keel.y2_backend`` and never touch
the live session loop, web app, CLI or any existing test.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

import keel.y2_backend as y


COVERAGE = {
    "Y2.9": ("RowKindRegistry", "CardKind", "EventKind", "DEFAULT_ROW_KIND_REGISTRY"),
    "Y2.10": ("CollabToolRegistry", "should_stay_silent", "request_app_connection"),
    "Y2.11": ("send_to_bot", "SubagentManager", "GroupRoom", "post_to_group"),
    "Y2.12": ("DesktopPool", "ScreenLease", "MAX_DESKTOPS"),
    "Y2.13": ("ResourceManager", "SuspendDecision", "DEFAULT_IDLE_SUSPEND_SECONDS"),
    "Y2.15": ("TokenBucket", "RateLimiter", "InVmExecutor", "RecordingExecutorSeam"),
    "Y2.16": ("CompactionConfig", "plan_compaction", "DEFAULT_MEMORY_BUDGET_CHARS"),
    "Y2.17": ("prompt_cache_key", "safety_identifier", "build_provider_identity"),
    "Y2.18": ("parse_scheduler_flag", "strip_no_scheduler", "NO_SCHEDULER_ENV"),
    "Y2.19": ("RenameCompat", "CompatRenames", "CompatReport"),
    "Y2.21": ("build_project_status", "status_from_plan", "KNOWN_LIMITS"),
    "Y2.22": ("RealtimeSecretIssuer", "HandoffRelay", "tts_preview",
              "stt_dictation_proxy"),
    "Y2.23": ("prepare_audio_fixture", "run_e2e_scenario", "SCENARIO_FULL"),
    "Y2.24": ("SSEStream", "SSEStreamRegistry", "SSEEventKind"),
    "Y2.25": ("RoutineEngine", "parse_cron", "make_routine"),
}


def test_all_fifteen_feature_ids_have_backend_symbols():
    assert len(COVERAGE) == 15
    for feature_id, symbols in COVERAGE.items():
        for symbol in symbols:
            assert hasattr(y, symbol), f"{feature_id} is missing {symbol}"


# ---------------------------------------------------------------------------
# Y2.9 -- card and event row kinds
# ---------------------------------------------------------------------------


def test_row_kind_registry_covers_all_card_and_event_kinds():
    registry = y.DEFAULT_ROW_KIND_REGISTRY
    names = set(registry.names())
    assert names == {
        "system", "user", "assistant", "tool", "reasoning",
        "approval", "question", "connect", "draft",
        "routine_created", "routine_run", "voice_call", "group_created",
        "group_member_added", "group_member_removed", "notice",
    }
    assert set(registry.kinds_for("card")) == {"approval", "question", "connect", "draft"}
    assert "routine_run" in registry.kinds_for(y.RowFamily.EVENT)
    assert registry.kinds_for("notice") == ("notice",)
    assert registry.component_for("connect") == "ConnectCard"
    assert registry.component_for("approval") == "ApprovalCard"
    assert registry.component_for("routine_run") == "EventRow"


def test_row_kind_registry_validates_bodies_and_is_deterministic():
    registry = y.DEFAULT_ROW_KIND_REGISTRY
    row = registry.make_row("connect", {"connector": "github", "reason": "sync"},
                            clock=lambda: 1000.0)
    assert row["id"] == registry.make_row(
        "connect", {"connector": "github", "reason": "sync"},
        clock=lambda: 9999.0)["id"]  # time never participates in identity
    assert row["family"] == "card" and row["component"] == "ConnectCard"
    assert row["body"]["connector"] == "github"
    with pytest.raises(y.RowKindError):
        registry.make_row("connect", {"reason": "missing connector"})
    with pytest.raises(y.RowKindError):
        registry.make_row("not-a-kind", {})
    with pytest.raises(y.RowKindError):
        registry.validate("approval", ["not", "a", "mapping"])


def test_row_kind_registry_supports_extension_without_duplicates():
    custom = y.RowKindRegistry(seed_defaults=True)
    custom.register(y.RowKindSpec("custom", "event", "EventRow", ("id",)))
    assert "custom" in custom.names()
    with pytest.raises(y.RowKindError):
        custom.register(y.RowKindSpec("custom", "card", "ConnectCard"))
    doc = custom.to_dict()
    assert doc["question"]["required_body"] == ["question"]


# ---------------------------------------------------------------------------
# Y2.10 -- stay_silent and request_app_connection tools
# ---------------------------------------------------------------------------


def test_stay_silent_decides_from_group_mentions():
    assert not y.should_stay_silent("hello", "alice").silent
    assert y.should_stay_silent("hello all", "alice", group=True).silent
    assert not y.should_stay_silent("@alice please", "alice", group=True).silent
    assert not y.should_stay_silent("hi", "alice", group=True,
                                    addressed_agents=["alice"]).silent
    assert not y.should_stay_silent("hi", "alice", group=True,
                                    author_id="alice").silent
    with pytest.raises(y.ToolError):
        y.should_stay_silent("hi", "")


def test_request_app_connection_emits_connect_card():
    card = y.request_app_connection("github", "to sync issues",
                                    clock=lambda: 1000.0)
    doc = card.to_dict()
    assert doc["kind"] == "connect"
    assert doc["action"] == "open_connector_form"
    assert doc["form"] == "github"       # opens the connector form
    assert doc["connector"] == "github"
    assert doc["created_at"].endswith("Z")
    with pytest.raises(y.ToolError):
        y.request_app_connection("")


def test_collab_tool_registry_dispatch():
    tools = y.CollabToolRegistry().install_defaults()
    assert set(tools.names()) == {"stay_silent", "request_app_connection"}
    assert tools.schema("stay_silent")["name"] == "stay_silent"
    silent = tools.dispatch("stay_silent", {"message": "hey", "agent_id": "bob"},
                            context={"group": True})
    assert silent.ok and silent.data["silent"] is True
    connect = tools.dispatch("request_app_connection", {"connector": "slack"})
    assert connect.connect_card["form"] == "slack"
    with pytest.raises(y.ToolError):
        tools.dispatch("unknown_tool", {})
    with pytest.raises(y.ToolError):
        tools.dispatch("stay_silent", {"message": "x"})


# ---------------------------------------------------------------------------
# Y2.11 -- send_to_bot, hidden subagents, group rooms
# ---------------------------------------------------------------------------


def test_send_to_bot_message_is_deterministic():
    a = y.send_to_bot("alice", "bob", "review this", clock=lambda: 5.0)
    b = y.send_to_bot("alice", "bob", "review this", clock=lambda: 999.0)
    # Identity never depends on wall-clock time; only the stamp does.
    assert a.id == b.id and a.recipient == "bob" and a.sender == "alice"
    assert a.to_dict()["created_at"].endswith("Z")
    assert a.created_at != b.created_at
    with pytest.raises(y.ToolError):
        y.send_to_bot("", "bob", "x")


def test_hidden_subagents_lifecycle_removes_context_and_screen():
    manager = y.SubagentManager()
    child = manager.spawn("alice", "worker-1",
                          context={"task": "search"}, screen="desktop-2")
    assert child.hidden is True and child.active is True
    assert manager.is_hidden("worker-1")
    assert manager.children("alice") == (child,)
    stopped = manager.stop_subagent("worker-1")
    assert stopped.context == {} and stopped.screen is None
    assert stopped.active is False and stopped.hidden is True
    with pytest.raises(y.ToolError):
        manager.stop_subagent("worker-1")  # already stopped
    assert manager.get("worker-1").active is False
    with pytest.raises(y.ToolError):
        manager.spawn("alice", "worker-1")


def test_group_room_mention_routing_with_three_member_cap():
    room = y.GroupRoom("room-1", ["alice", "bob", "carol", "dave", "erin"])
    routing = y.post_to_group(
        room, "alice", "fyi @bob @carol @dave @erin @nobody")
    assert routing.mentioned == ("bob", "carol", "dave", "erin", "nobody")
    assert routing.responders == ("bob", "carol", "dave")
    assert routing.deferred == ("erin",)
    assert routing.capped is True and routing.reason == "routed"
    assert routing.to_dict()["responders"] == ["bob", "carol", "dave"]
    with pytest.raises(y.ToolError):
        y.post_to_group("not-a-room", "alice", "hi")


def test_group_room_loop_guard_blocks_a_repeating_responder():
    room = y.GroupRoom("room-2", ["alice", "bob"])
    for _ in range(3):
        routed = room.post("alice", "@bob status?")
        assert routed.responders == ("bob",)
    blocked = room.post("alice", "@bob again?")
    assert blocked.responders == () and blocked.reason == "loop_guard"


# ---------------------------------------------------------------------------
# Y2.12 -- screen leasing
# ---------------------------------------------------------------------------


def test_screen_pool_leases_four_desktops_and_fails_on_fifth():
    pool = y.DesktopPool("vm-1")
    assert pool.size == y.MAX_DESKTOPS == 4
    leases = [pool.lease(f"agent-{i}") for i in range(4)]
    assert {lease.desktop_id for lease in leases} == {
        f"desktop-{i}" for i in range(1, 5)}
    assert {lease.vm for lease in leases} == {"vm-1"}
    assert pool.busy_count() == 4 and pool.idle_count() == 0
    with pytest.raises(y.ScreenLeaseError):
        pool.lease("agent-4")
    with pytest.raises(y.ScreenLeaseError):
        pool.release("agent-99")


def test_screen_pool_reuses_least_recently_released_desktop():
    pool = y.DesktopPool()
    leases = [pool.lease(f"agent-{i}") for i in range(4)]
    least_recent = leases[1].desktop_id        # agent-1 released first
    first = pool.release("agent-1")
    assert first.desktop_id == least_recent
    pool.tick()
    second = pool.release("agent-2")
    pool.tick()
    pool.release("agent-3")
    # The first released desktop stays the least-recently-used one.
    new_lease = pool.lease("agent-new")
    assert new_lease.desktop_id == least_recent
    assert pool.lease("agent-new") == new_lease   # idempotent per agent
    snapshot = {d["id"]: d for d in pool.snapshot()}
    assert snapshot[least_recent]["busy"] is True
    assert snapshot[second.desktop_id]["busy"] is False


# ---------------------------------------------------------------------------
# Y2.13 -- idle suspend knobs
# ---------------------------------------------------------------------------


def test_idle_suspend_defaults_and_settings_page():
    manager = y.ResourceManager(clock=lambda: 0.0)
    assert manager.idle_timeout_seconds == 20 * 60 == 1200
    assert manager.sweep_interval_seconds == 60
    assert manager.dry_run is True
    assert manager.settings() == {"idle_suspend_seconds": 1200,
                                  "sweep_interval_seconds": 60,
                                  "dry_run": True}


def test_dry_run_logs_suspend_decisions_without_acting():
    manager = y.ResourceManager(clock=lambda: 0.0)
    manager.register("desktop-1", now=1000.0)
    decisions = manager.sweep(now=2300.0)   # 1300s idle > 1200s
    assert len(decisions) == 1
    assert decisions[0].action == "suspend" and decisions[0].dry_run is True
    assert decisions[0].applied is False
    assert manager.suspended == ()
    assert manager.decisions == decisions


def test_real_sweep_suspends_and_touch_resets_idle():
    manager = y.ResourceManager(dry_run=False, clock=lambda: 0.0)
    manager.register("desktop-1", now=0.0)
    manager.register("desktop-2", now=1200.0)
    decisions = manager.sweep(now=1300.0)
    by_id = {d.resource_id: d for d in decisions}
    assert by_id["desktop-1"].applied is True
    assert by_id["desktop-2"].action == "keep"
    assert manager.suspended == ("desktop-1",)
    manager.touch("desktop-1", now=1400.0)
    assert manager.suspended == ()
    assert manager.sweep(now=1500.0)[0].action == "keep"


# ---------------------------------------------------------------------------
# Y2.15 -- rate-limit awareness + in-VM executor
# ---------------------------------------------------------------------------


def test_token_bucket_burst_then_refill():
    bucket = y.TokenBucket(rate_per_minute=60, capacity=2, clock=lambda: 0.0)
    assert bucket.allow(now=0.0) and bucket.allow(now=0.0)
    assert not bucket.allow(now=0.0)
    assert bucket.retry_after(now=0.0) == pytest.approx(1.0)
    assert bucket.allow(now=1.0)        # 1 token/s refilled

    default = y.TokenBucket(clock=lambda: 0.0)
    assert default.capacity == 600 and default.rate_per_second == 10.0
    with pytest.raises(y.RateLimitError):
        y.TokenBucket(0)


def test_rate_limiter_is_per_computer():
    limiter = y.RateLimiter(rate_per_minute=1, clock=lambda: 0.0)
    assert limiter.check("a", now=0.0).allowed is True
    assert limiter.check("a", now=0.0).allowed is False
    assert limiter.check("b", now=0.0).allowed is True
    assert limiter.check("a", now=0.0).to_dict()["reason"] == "rate limit reached"


def test_in_vm_executor_short_circuits_when_rate_limited():
    seam = y.RecordingExecutorSeam()
    executor = y.InVmExecutor(
        limiter=y.RateLimiter(rate_per_minute=1, clock=lambda: 0.0), seam=seam)
    action = y.DesktopAction("computer-1", "screenshot", {"full": True})
    accepted = executor.submit(action, now=0.0)
    rejected = executor.submit(action, now=0.0)
    assert accepted.status == "accepted"
    assert rejected.status == "rate_limited" and not rejected.to_dict()["status"] == "accepted"
    assert len(seam.actions) == 1       # the limited action never reached the seam
    with pytest.raises(y.RateLimitError):
        executor.submit(y.DesktopAction("", "click"))


# ---------------------------------------------------------------------------
# Y2.16 -- compaction knobs
# ---------------------------------------------------------------------------


def test_compaction_defaults_and_method_validation():
    config = y.CompactionConfig()
    assert config.keep_last_user_turns == 4
    assert config.memory_budget_chars == 4000
    assert config.idle_consolidation_seconds == 600
    assert config.consolidation_sweep_seconds == 60
    assert config.method is y.CompactionMethod.AUTO
    assert config.to_dict()["method"] == "auto"
    with pytest.raises(ValueError):
        y.CompactionConfig(method="magic")


def test_compaction_keeps_last_n_user_turns_and_bounds_memory():
    turns = [
        y.Turn("u1", "user", "question one is fairly long"),
        y.Turn("a1", "assistant", "answer one is also fairly long"),
        y.Turn("u2", "user", "question two"),
        y.Turn("a2", "assistant", "answer two is quite long indeed"),
        y.Turn("u3", "user", "question three"),
        y.Turn("u4", "user", "question four"),
    ]
    config = y.CompactionConfig(trigger_chars=10, memory_budget_chars=20)
    plan = y.plan_compaction(turns, config, last_activity=0.0, now=0.0)
    assert plan.should_compact and plan.reason == "size trigger"
    assert [t.id for t in plan.verbatim_turns] == ["u1", "u2", "u3", "u4"]
    assert "answer one" in plan.summary_text and "question one" not in plan.summary_text
    rendered = plan.render_memory()
    assert len(rendered) <= 20 and rendered.endswith("[truncated]")
    assert plan.to_dict()["verbatim_ids"] == ("u1", "u2", "u3", "u4")


def test_compaction_keeps_only_last_four_user_turns_with_more_than_four():
    turns = [y.Turn("a0", "assistant", "preamble")]
    turns.extend(y.Turn(f"u{i}", "user", f"question {i}") for i in range(1, 7))
    config = y.CompactionConfig(method="summary")
    plan = y.plan_compaction(turns, config, last_activity=0.0, now=0.0)
    assert [t.id for t in plan.verbatim_turns] == ["u3", "u4", "u5", "u6"]
    assert "question 1" in plan.summary_text and "question 2" in plan.summary_text
    assert "question 3" not in plan.summary_text

    none = y.plan_compaction(
        turns, y.CompactionConfig(method="summary", keep_last_user_turns=0),
        last_activity=0.0, now=0.0)
    assert none.verbatim_turns == ()
    assert all(f"question {i}" in none.summary_text for i in range(1, 7))


def test_compaction_idle_consolidation_and_summary_method():
    turns = [y.Turn("u1", "user", "short")]
    idle = y.plan_compaction(
        turns, y.CompactionConfig(idle_consolidation_seconds=60),
        last_activity=0.0, now=120.0)
    assert idle.should_compact and idle.reason == "idle consolidation"
    below = y.plan_compaction(
        turns, y.CompactionConfig(), last_activity=100.0, now=120.0)
    assert not below.should_compact and below.verbatim_turns == ()
    always = y.plan_compaction(
        turns, y.CompactionConfig(method="summary"),
        last_activity=100.0, now=120.0)
    assert always.reason == "summary method" and always.method is y.CompactionMethod.SUMMARY


# ---------------------------------------------------------------------------
# Y2.17 -- prompt cache key per agent+generation
# ---------------------------------------------------------------------------


def test_prompt_cache_key_is_stable_per_agent_and_generation():
    key = y.prompt_cache_key("agent-1", 3, model="gpt-x")
    assert key == y.prompt_cache_key("agent-1", 3, model="gpt-x")
    assert key != y.prompt_cache_key("agent-1", 4, model="gpt-x")
    assert key != y.prompt_cache_key("agent-2", 3, model="gpt-x")
    assert y.local_prefix("agent-1", 3) == "keel:agent-1:3:"


def test_safety_identifier_never_exposes_the_raw_user_id():
    identity = y.build_provider_identity("agent-1", 2, "alice@example.com")
    assert identity.safety_identifier.startswith("user_")
    assert "alice@example.com" not in identity.safety_identifier
    assert y.assert_no_raw_identifier(identity, "alice@example.com") is True
    assert identity.safety_identifier != y.safety_identifier("bob@example.com")
    with pytest.raises(y.Y2BackendError):
        y.safety_identifier("")


# ---------------------------------------------------------------------------
# Y2.18 -- NO_SCHEDULER flag
# ---------------------------------------------------------------------------


def test_no_scheduler_flag_cli_env_and_default():
    assert y.parse_scheduler_flag([], {}) == y.SchedulerConfig(False, "default")
    from_cli = y.parse_scheduler_flag(["serve", "--no-scheduler"], {})
    assert from_cli.enabled and from_cli.source == "cli"
    from_env = y.parse_scheduler_flag([], {y.NO_SCHEDULER_ENV: "true"})
    assert from_env.enabled and from_env.source == "env"
    # CLI takes precedence over the environment.
    assert y.parse_scheduler_flag(["--no-scheduler"],
                                  {y.NO_SCHEDULER_ENV: "false"}).source == "cli"
    assert y.NO_SCHEDULER_ENV == "KEEL_NO_SCHEDULER"


def test_no_scheduler_truth_table_and_helpers():
    for value in ("1", "TRUE", "yes", "on"):
        assert y.parse_scheduler_flag([], {y.NO_SCHEDULER_ENV: value}).enabled
    for value in ("0", "false", "no", "off", ""):
        assert not y.parse_scheduler_flag([], {y.NO_SCHEDULER_ENV: value}).enabled
    with pytest.raises(y.SchedulerFlagError):
        y.parse_scheduler_flag([], {y.NO_SCHEDULER_ENV: "maybe"})
    assert y.strip_no_scheduler(["serve", "--no-scheduler", "--port", "8000"]) == (
        "serve", "--port", "8000")
    assert y.should_run_scheduler(y.SchedulerConfig(True, "cli")) is False
    assert y.should_run_scheduler(y.SchedulerConfig(False, "default")) is True


# ---------------------------------------------------------------------------
# Y2.19 -- backward-compatible rename path
# ---------------------------------------------------------------------------


def test_env_and_cookie_fallbacks(tmp_path):
    compat = y.RenameCompat(tmp_path, y.CompatRenames(
        env={"KEEL_NEW": "KEEL_OLD"},
        cookie_name=("keel_session", "keel_session_old")))
    assert compat.env({"KEEL_NEW": "new"}, "KEEL_NEW") == "new"
    assert compat.env({"KEEL_OLD": "old"}, "KEEL_NEW") == "old"
    assert compat.env({}, "KEEL_NEW", "default") == "default"
    assert compat.cookie({"keel_session": "new"}) == "new"
    assert compat.cookie({"keel_session_old": "old"}) == "old"
    report = compat.report()
    assert report.env_fallbacks == (("KEEL_NEW", "KEEL_OLD"),)
    assert report.cookie_used_old is True
    assert report.to_dict()["db_used_old"] is False


def test_database_path_keeps_old_filename_when_new_is_absent(tmp_path):
    compat = y.RenameCompat(tmp_path)
    assert compat.database_path().name == "keel.db"
    (tmp_path / "keel-old.db").write_text("legacy", encoding="utf-8")
    assert compat.database_path().name == "keel-old.db"
    assert compat.report().db_used_old is True
    (tmp_path / "keel.db").write_text("current", encoding="utf-8")
    assert compat.database_path().name == "keel.db"
    assert compat.report().db_used_old is True  # sticky record of the fallback


def test_compat_symlink_is_guarded(tmp_path):
    base = tmp_path / "app"
    base.mkdir()
    (base / "data").mkdir()
    compat = y.RenameCompat(base)
    created = compat.ensure_symlink()
    report = compat.report()
    assert created == report.symlink_created
    if created:
        assert (base / "data-old").exists()
    else:
        assert report.symlink_error           # e.g. Windows privilege error

    outside = tmp_path / "outside"
    outside.mkdir()
    escape = y.RenameCompat(base, y.CompatRenames(data_dir=("../outside", "link")))
    assert escape.ensure_symlink() is False
    assert "escapes its base" in escape.report().symlink_error


# ---------------------------------------------------------------------------
# Y2.21 -- honest Project status
# ---------------------------------------------------------------------------


def test_project_status_markdown_contains_honest_caveats():
    status = y.build_project_status([
        y.StatusEntry("Y2.1", "transcript rows", "verified", "39 tests"),
        y.StatusEntry("Y2.9", "card kinds", "not_started"),
    ])
    markdown = status.render_markdown()
    assert "## Tested" in markdown
    assert "Built, not proven" in markdown
    assert "## Known limits" in markdown
    assert y.AUDIT_DISCLAIMER in markdown
    assert y.APPROVAL_GAP in markdown
    assert "browser and shell" in markdown
    payload = status.to_about_payload()
    assert payload["entries"][0]["level"] == "tested"
    assert payload["audit_disclaimer"] == y.AUDIT_DISCLAIMER
    assert len(y.KNOWN_LIMITS) >= 3


def test_status_from_plan_maps_registry_statuses():
    status = y.status_from_plan([
        {"id": "A1.1", "feature": "run", "status": "verified"},
        {"id": "Y2.9", "feature": "cards", "status": "not_started"},
        {"id": "X1.1", "status": "built"},
    ])
    levels = [e.level for e in status.entries]
    assert levels == [y.VerificationLevel.TESTED,
                      y.VerificationLevel.PLANNED,
                      y.VerificationLevel.BUILT_UNPROVEN]
    assert y.level_for_status("unknown") is y.VerificationLevel.PLANNED


# ---------------------------------------------------------------------------
# Y2.22 -- voice: realtime secrets, hand_off_task, TTS/STT
# ---------------------------------------------------------------------------


def test_realtime_secret_expiry_revocation_and_redaction():
    issuer = y.RealtimeSecretIssuer(clock=lambda: 0.0)
    secret = issuer.issue("session-1", now=1000.0)
    assert issuer.is_valid(secret, now=1001.0)
    assert not issuer.is_valid(secret, now=1301.0)   # 300s TTL
    assert secret.public_dict()["token"] == "[redacted]"
    other = issuer.issue("session-1", now=1000.0)
    assert other.token != secret.token
    issuer.revoke("session-1")
    assert not issuer.is_valid(other, now=1000.0)
    with pytest.raises(y.VoiceError):
        y.RealtimeSecretIssuer(0)


def test_realtime_secret_token_is_unpredictable_and_never_disclosed():
    issuer = y.RealtimeSecretIssuer(clock=lambda: 0.0)
    secret = issuer.issue("session-1", now=1000.0)
    # The old derivation was guessable from the published session id / issued_at
    # plus a one-based counter; none of those inputs may determine the token.
    guess = y.new_id("realtime", "session-1", 1000.0, 1, length=24)
    assert secret.token != guess
    assert len(secret.token) >= 32
    other_issuer = y.RealtimeSecretIssuer(clock=lambda: 0.0)
    assert other_issuer.issue("session-1", now=1000.0).token != secret.token
    assert secret.token not in json.dumps(secret.public_dict())
    assert secret.token not in json.dumps(secret.to_dict())
    assert secret.public_dict()["token"] == "[redacted]"


def test_realtime_secret_is_valid_rejects_wrong_token():
    """C10: a known session id must not make an arbitrary token valid."""
    issuer = y.RealtimeSecretIssuer(clock=lambda: 0.0)
    issued = issuer.issue("session-A", now=1000.0)
    assert issuer.is_valid(issued, now=1001.0) is True

    wrong = y.RealtimeSecret(
        token="totally-wrong-token",
        session_id=issued.session_id,
        expires_at=issued.expires_at,
        issued_at=issued.issued_at,
    )
    assert issuer.is_valid(wrong, now=1001.0) is False

    # A genuine token from another session cannot be relabelled either.
    other = issuer.issue("session-B", now=1000.0)
    relabelled = y.RealtimeSecret(
        token=other.token,
        session_id="session-A",
        expires_at=other.expires_at,
        issued_at=other.issued_at,
    )
    assert issuer.is_valid(relabelled, now=1001.0) is False
    assert issuer.is_valid(other, now=1001.0) is True

    # A token minted by a different issuer is not registered with this one.
    foreign = y.RealtimeSecretIssuer(clock=lambda: 0.0).issue("session-A", now=1000.0)
    assert issuer.is_valid(foreign, now=1001.0) is False


def test_handoff_task_relays_to_text_loop():
    seam = y.RecordingTextLoopSeam()
    relay = y.HandoffRelay(seam=seam, clock=lambda: 1000.0)
    task = relay.hand_off_task("session-1", "please summarise")
    assert task.status == "queued_for_text_loop"
    assert seam.tasks == (task,)
    assert task.to_dict()["id"] == task.id
    with pytest.raises(y.VoiceError):
        relay.hand_off_task("", "text")


def test_tts_preview_and_stt_proxy_never_fabricate_media():
    preview = y.tts_preview("hello there", voice="nova")
    assert preview.chars == 11 and preview.voice == "nova"
    assert "data" not in preview.to_dict()      # no fabricated audio
    seam = y.RecordingTranscriptionSeam()
    audio = b"real-audio-bytes"
    dictation = y.stt_dictation_proxy(audio, seam=seam)
    assert dictation.byte_size == len(audio)
    assert dictation.sha256 == y.hashlib.sha256(b"real-audio-bytes").hexdigest()
    assert dictation.transcript == ""            # no invented transcript
    assert seam.dictations == (dictation,)
    with pytest.raises(y.VoiceError):
        y.stt_dictation_proxy(b"")


# ---------------------------------------------------------------------------
# Y2.23 -- E2E script with prepared-audio fixture
# ---------------------------------------------------------------------------


def test_prepared_audio_fixture_is_real_deterministic_wav():
    fixture = y.prepare_audio_fixture()
    assert fixture.data[:4] == b"RIFF" and fixture.data[8:12] == b"WAVE"
    assert fixture.sha256 == y.hashlib.sha256(fixture.data).hexdigest()
    assert fixture == y.prepare_audio_fixture()
    assert len(fixture.data) > 44           # real PCM samples, not just a header
    assert fixture.to_dict()["mime_type"] == "audio/wav"
    assert y.voice_harness_fixture().name == "voice-harness.wav"
    with pytest.raises(y.AudioFixtureError):
        y.prepare_audio_fixture(duration_ms=0)


def test_e2e_scenario_requires_audio_and_records_steps():
    assert set(y.E2E_SURFACES) == {
        "chat", "computer_tools", "viewer", "search", "connections", "voice",
        "groups", "settings"}
    with pytest.raises(y.AudioFixtureError):
        y.run_e2e_scenario(y.SCENARIO_FULL, y.RecordingE2EHarness())
    full_harness = y.RecordingE2EHarness()
    report = y.run_e2e_scenario(y.SCENARIO_FULL, full_harness,
                                fixture=y.voice_harness_fixture())
    assert len(report.results) == 8
    assert report.recorded == 8 and report.passed == 0 and report.failed == 0
    assert report.fixture == "voice-harness.wav"
    assert full_harness.executed == y.E2E_FULL_SCENARIO
    assert report.to_dict()["results"][0]["status"] == "recorded"


# ---------------------------------------------------------------------------
# Y2.24 -- per-user SSE stream
# ---------------------------------------------------------------------------


def test_sse_registry_creates_one_stream_per_user_with_typed_events():
    registry = y.SSEStreamRegistry(clock=lambda: 1000.0)
    assert registry.for_user("u1") is registry.for_user("u1")
    assert registry.users() == ("u1",)
    for kind in y.SSEEventKind:
        event = registry.publish("u1", kind, {"value": kind.value})
        assert event.kind is kind
    encoded = event.encode()
    assert encoded.startswith(f"id: {event.id}\nevent: {kind.value}\ndata: ")
    assert encoded.endswith("\n\n")
    assert event.to_dict()["user_id"] == "u1"
    with pytest.raises(y.StreamError):
        registry.publish("u1", "bogus", {})
    registry.close("u1")
    assert registry.users() == ()


def test_sse_reconnect_drain_and_bounded_buffer():
    stream = y.SSEStream("u2", buffer_size=2, clock=lambda: 1000.0)
    for i in range(3):
        stream.publish("row_update", {"n": i})
    assert stream.snapshot()["oldest_id"] == 1
    assert stream.snapshot()["next_id"] == 3
    assert [e.id for e in stream.drain()] == [2, 3]
    assert [e.id for e in stream.drain(since_id=2)] == [3]
    assert stream.drain(since_id=3) == ()


# ---------------------------------------------------------------------------
# Y2.25 -- routines: cron, connector events, check-ins
# ---------------------------------------------------------------------------


def test_cron_parser_validates_and_matches():
    assert y.parse_cron("* * * * *").matches(datetime(2026, 11, 24, 9, 30))
    weekday = y.parse_cron("0 9 * * 1-5")
    assert weekday.matches(datetime(2026, 11, 24, 9, 0))   # Tuesday
    assert not weekday.matches(datetime(2026, 11, 24, 10, 0))
    assert not weekday.matches(datetime(2026, 11, 28, 9, 0))  # Saturday
    stepped = y.parse_cron("*/15 * * * *")
    assert 0 in stepped.minute and 15 in stepped.minute
    for bad in ("0 9 * *", "70 * * * *", "*/0 * * * *", "0 9 * * MON"):
        with pytest.raises(y.RoutineError):
            y.parse_cron(bad)


def test_event_routines_only_fire_from_user_configured_free_connectors():
    engine = y.RoutineEngine(clock=lambda: 0.0)
    routine = y.make_routine("on-ticket", "event", "agent-1",
                             trigger="ticket.created", connector="github")
    engine.register(routine)
    engine.configure_free_connectors(["github"])
    good = y.ConnectorEvent("ticket.created", "github")
    assert engine.evaluate(now=0.0, event=good)[0].due is True
    unconfigured = engine.evaluate(
        now=0.0, event=y.ConnectorEvent("ticket.created", "evil-app"))[0]
    assert unconfigured.due is False
    assert "not user-configured" in unconfigured.reason
    wrong_name = engine.evaluate(
        now=0.0, event=y.ConnectorEvent("other", "github"))[0]
    assert wrong_name.due is False
    fired = engine.fire(engine.evaluate(now=0.0, event=good)[0], now=0.0)
    assert fired.kind is y.RoutineKind.EVENT and fired.to_dict()["routine_id"] == routine.id
    with pytest.raises(y.RoutineError):
        engine.fire(unconfigured)


def test_checkin_cadence_and_cron_fire():
    engine = y.RoutineEngine(clock=lambda: 0.0)
    checkin = y.make_routine("morning", "checkin", "agent-1",
                             interval_seconds=3600)
    engine.register(checkin)
    assert engine.evaluate(now=100.0)[0].due is False
    due = engine.evaluate(now=3700.0)[0]
    assert due.due is True
    engine.fire(due, now=3700.0)
    assert engine.evaluate(now=3800.0)[0].due is False

    cron_engine = y.RoutineEngine(clock=lambda: 0.0)
    cron = y.make_routine("heartbeat", "cron", "agent-1", schedule="* * * * *")
    cron_engine.register(cron)
    trigger = cron_engine.evaluate(now=0.0)[0]
    assert trigger.due is True
    assert cron_engine.fire(trigger, now=0.0).kind is y.RoutineKind.CRON


def test_y2_16_feature_traceability_maps_real_symbols():
    """Y2.16 resolves to real compaction symbols exercised above."""
    pairs = y.FEATURE_TRACEABILITY
    assert set(pairs) == {"Y2.16"}
    names = pairs["Y2.16"]
    assert "plan_compaction" in names
    for name in names:
        obj = getattr(y, name, None)
        assert obj is not None, name
        assert callable(obj) or isinstance(
            obj, (type, int, str, tuple, dict, set, frozenset)), name
