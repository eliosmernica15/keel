"""Backend behaviour tests for the Master Plan v6 small feature groups.

One test per implemented feature (54) plus registry/owner-gate coverage
checks. Standard library only on the implementation side; pytest is used as
the test runner exactly as in the rest of the suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from keel.small_groups_backend import (
    FEATURE_IMPLEMENTATIONS,
    GROUP_PREFIXES,
    OWNER_GATED,
    AllowlistMatcher,
    ApprovalService,
    AudioPrivacyPolicy,
    BackgroundCommandRunner,
    BenchmarkGate,
    BlobCaps,
    BargeInController,
    BrowserSnapshotLane,
    CommandTemplateStore,
    ComputerAccessGuard,
    ConfidenceLabeler,
    ConductorRouter,
    CoverageGate,
    DecisionLog,
    FirstRunNotice,
    FixtureFormatPolicy,
    GoalsService,
    HookContractError,
    HookRunner,
    JsonlPersistence,
    LocalVisionTool,
    MemoryLedger,
    McpConformanceRunner,
    McpPanelService,
    McpPermissionActions,
    MilestoneSplitter,
    ModelReference,
    MutationReport,
    PersistenceProviderRegistry,
    ProjectionRegistry,
    RequestSeriesLogger,
    RiskRegister,
    ScopeCreepGuard,
    SessionAgentPin,
    SessionPersistence,
    SoakMonitor,
    StorePolicy,
    TestResolver,
    TitleProviderRegistry,
    TokenAccountingCheck,
    TurnClaimGate,
    VcrRecorder,
    VideoTooling,
    VoiceCommandGrammar,
    WakeWordController,
    apply_agent_fields,
    assert_missing_config_exits_nonzero,
    build_palette_entries,
    built_entrypoint_smoke,
    choose_tool,
    expand_command_prompt,
    expand_path_actions,
    generate_weekly_report,
    normalize_agent_config,
    normalize_question,
    pseudo_localize,
    repo_descriptor,
    resolve_default_agent,
    resolve_model_precedence,
    rtl_smoke,
    simulate_permission,
    stream_tts_sentences,
    web_server_config,
)

# ---------------------------------------------------------------------------
# X4
# ---------------------------------------------------------------------------


def test_x4_1_barge_in_interrupt_and_half_duplex():
    full = BargeInController(full_duplex_capable=True)
    full.start_tts("hello there")
    result = full.speech_detected()
    assert result["interrupted"] is True and result["fallback"] is False
    assert full.playing is False and full.interruptions == 1

    weak = BargeInController(full_duplex_capable=False)
    assert weak.mode == "half_duplex"
    weak.start_tts("still talking")
    fallback = weak.speech_detected()
    assert fallback["interrupted"] is False and fallback["fallback"] is True
    assert weak.playing is True
    weak.tts_finished()
    assert weak.playing is False


def test_x4_2_streaming_tts_sentences():
    chunks = ["Hello. Wor", "ld. How are", " you? Fine!"]
    assert stream_tts_sentences(chunks) == ["Hello.", "World.", "How are you?", "Fine!"]
    assert stream_tts_sentences(["no terminator here"]) == ["no terminator here"]


def test_x4_3_wake_word_license_and_hard_mute():
    good = WakeWordController("snowboy", "MIT")
    assert good.verify_engine_license()["acceptable"] is True
    assert good.set_enabled(True)["indicator"] == "listening"
    assert good.detect_wake_word()["detected"] is True
    muted = good.hard_mute()
    assert muted["muted"] is True and good.detect_wake_word()["detected"] is False
    with pytest.raises(ValueError):
        good.set_enabled(True)  # hard mute cannot be overridden
    bad = WakeWordController("mystery", "proprietary")
    with pytest.raises(ValueError):
        bad.set_enabled(True)


def test_x4_4_local_vision_tool(tmp_path):
    tool = LocalVisionTool()
    tool.register_model("vlm", "/models/vlm.gguf", "Apache-2.0")
    image = tmp_path / "shot.png"
    image.write_bytes(b"png")
    result = tool.analyze("vlm", image, "what is this?")
    assert result["tool"] == "local_vision"
    assert result["network_access"] is False
    assert result["license_shown"] is True
    assert result["request"]["question"] == "what is this?"
    with pytest.raises(ValueError):
        tool.analyze("vlm", tmp_path / "notes.txt")


def test_x4_5_video_tooling_commands_and_srt():
    video = VideoTooling("/usr/bin/ffmpeg")
    frame = video.extract_frame("in.mp4", 3.5, "frame.png")
    assert frame[:3] == ["/usr/bin/ffmpeg", "-y", "-ss"] and frame[-1] == "frame.png"
    assert "-vn" in video.extract_audio("in.mp4", "audio.m4a")
    subs = video.subtitles_from_stt(
        [{"start": 0, "end": 1.25, "text": "hi"}, {"start": 60, "end": 61, "text": "later"}],
        "out.srt",
    )
    assert "00:00:00,000 --> 00:00:01,250" in subs["srt"]
    assert "00:01:00,000 --> 00:01:01,000" in subs["srt"]
    with pytest.raises(ValueError):
        VideoTooling("").extract_audio("in", "out")


def test_x4_6_voice_command_grammar_and_confirmation():
    grammar = VoiceCommandGrammar()
    assert grammar.parse("please write a poem")["kind"] == "dictation"
    assert grammar.parse("Approve!")["kind"] == "command"
    assert grammar.execute("deny")["needs_confirmation"] is True
    assert grammar.execute("deny", "confirm")["executed"] is True
    assert grammar.execute("stop everything", "confirm")["action"] == "stop everything"
    assert grammar.execute("free dictation")["executed"] is False


def test_x4_7_audio_privacy_rules():
    policy = AudioPrivacyPolicy()  # store_recordings defaults to False
    started = policy.start_recording("Standup")
    assert started["visible"] is True and started["stored"] is False
    assert "Standup" in started["consent_reminder"]
    assert policy.pause_recording()["state"] == "paused"
    assert policy.stop_recording()["state"] == "idle"
    storing = AudioPrivacyPolicy(store_recordings=True)
    assert storing.start_recording("Demo")["stored"] is True


# ---------------------------------------------------------------------------
# D2
# ---------------------------------------------------------------------------


def test_d2_2_hook_modes_and_waterfall_contract():
    runner = HookRunner()

    def first(ctx):
        return ctx.next()

    def last(ctx):
        return "done"

    runner.register("pre-step", "waterfall", first, name="first")
    runner.register("pre-step", "waterfall", last, name="last", short_circuit=True)
    assert runner.run("pre-step", "payload") == "done"

    serial = HookRunner()
    serial.register("stream", "serial", lambda value: value + 1)
    serial.register("stream", "serial", lambda value: value + 1)
    assert serial.run("stream", 0) == 2

    parallel = HookRunner()
    parallel.register("tool", "parallel", lambda value: value + "a")
    parallel.register("tool", "parallel", lambda value: value + "b")
    assert parallel.run("tool", "x") == ["xa", "xb"]

    broken = HookRunner()
    broken.register("request", "waterfall", lambda ctx: "bad", name="bad")
    with pytest.raises(HookContractError):
        broken.run("request", {})


def test_d2_4_first_claim_closes_turn_when_rejected_or_empty():
    gate = TurnClaimGate()
    assert gate.evaluate({"status": "rejected", "text": "x"}) == {
        "open": False,
        "step": False,
        "reason": "rejected",
    }
    assert gate.evaluate({"status": "accepted", "text": "  "})["reason"] == "empty"
    assert gate.evaluate(None)["reason"] == "no_claim"
    assert gate.evaluate("a real claim")["step"] is True


def test_d2_6_request_series_and_retries():
    logger = RequestSeriesLogger()
    logger.request({"n": 1}, key="ctx-a")
    assert logger.series == 1 and len(logger.headers()) == 1
    retry = logger.request({"n": 1}, key="ctx-a", retry=True)
    assert retry["type"] == "request_retry" and logger.series == 1
    assert len(logger.headers()) == 1  # retry did not repeat assembly
    logger.request({"n": 2}, key="ctx-b")  # surface replacement -> new series
    assert logger.series == 2 and len(logger.headers()) == 2
    with pytest.raises(ValueError):
        logger.request({}, key="wrong", retry=True)


def test_d2_12_projection_registry_snapshot():
    registry = ProjectionRegistry()
    registry.register(
        "tasks", [], lambda state, event: state + [event["title"]] if event["type"] == "task" else state
    )
    registry.commit({"type": "task", "title": "write tests"})
    snapshot = registry.snapshot("tasks")
    assert snapshot == ["write tests"]
    snapshot.append("mutated by client")
    assert registry.snapshot("tasks") == ["write tests"]
    assert registry.event_count == 1
    with pytest.raises(ValueError):
        registry.register("tasks", [], lambda state, event: state)


def test_d2_14_persistence_provider_interface(tmp_path):
    store = JsonlPersistence(tmp_path / "sessions")
    assert isinstance(store, SessionPersistence)
    store.create("s1")
    store.append_event("s1", {"type": "message"})
    store.append_event("s1", {"type": "tool"})
    assert len(store.open("s1")) == 2
    assert store.stat("s1")["events"] == 2
    assert store.list() == ["s1"]
    exported = store.export("s1", tmp_path / "export.json")
    assert "\"message\"" in open(exported, encoding="utf-8").read()
    with pytest.raises(ValueError):
        store.create("../escape")

    registry = PersistenceProviderRegistry()
    registry.register("jsonl", store, default=True)
    assert registry.get() is store and registry.names() == ["jsonl"]


def test_d2_17_title_provider_and_goals_survive_compaction():
    titles = TitleProviderRegistry()
    titles.register(lambda events: next((e["text"] for e in events if e["type"] == "user"), "Untitled"))
    assert titles.title([{"type": "user", "text": "Fix bug"}]) == "Fix bug"
    with pytest.raises(ValueError):
        titles.register(lambda events: "second")

    goals = GoalsService()
    goals.set_objective("ship the backend")
    goals.observe({"type": "compact"})
    goals.observe({"type": "message"})
    assert goals.current() == "ship the backend" and goals.compacted() == 1
    with pytest.raises(ValueError):
        goals.set_objective("   ")


# ---------------------------------------------------------------------------
# E4
# ---------------------------------------------------------------------------


def test_e4_3_coverage_gate_philosophy():
    report = {
        "files": {
            "src/a.py": {"covered": 8, "total": 10},
            "src/pwsh.py": {"covered": 0, "total": 5, "env_dependent": True},
            "src/dead.py": {"covered": 0, "total": 4},
        }
    }
    local = CoverageGate(ci=False, env_dependent_files={"src/pwsh.py"}).evaluate(report)
    assert "src/pwsh.py" in local["exempted"]
    assert "src/dead.py" in local["dead_code_candidates"]
    assert local["line_coverage_necessary"] is True
    assert local["line_coverage_sufficient"] is False
    ci = CoverageGate(ci=True, env_dependent_files={"src/pwsh.py"}).evaluate(report)
    assert ci["exempted"] == []
    assert "src/pwsh.py" in ci["dead_code_candidates"]


def test_e4_3_empty_coverage_report_cannot_pass_gate():
    for empty in ({}, {"files": {}},
                  {"files": {"src/a.py": {"covered": 0, "total": 0}}}):
        result = CoverageGate().evaluate(empty)
        assert result["passed"] is False
        assert result["has_coverage_data"] is False
        assert result["percent"] == 0.0
    # A real measurement still passes when it clears the threshold.
    real = CoverageGate().evaluate(
        {"files": {"src/a.py": {"covered": 9, "total": 10}}})
    assert real["passed"] is True and real["has_coverage_data"] is True


def test_e4_4_benchmark_budgets():
    gate = BenchmarkGate()
    gate.set_budget("session_open", max_seconds=1.0, max_heap_mb=64.0, max_scale_factor=2.0)
    gate.record("session_open", 0.5, 32.0, 1.2)
    assert gate.evaluate("session_open")["passed"] is True
    gate.record("session_open", 2.0, 128.0, 4.0)
    assert gate.evaluate("session_open")["violations"] == ["time", "heap", "scaling"]
    gate.set_budget("diag", 1.0, 1.0)
    gate.record("diag", 99.0, 99.0, diagnostic_only=True)
    assert gate.evaluate("diag")["gate"] is False
    assert gate.required_checks() == ["session_open"]


def test_e4_6_fixture_envelope_policy():
    policy = FixtureFormatPolicy(current_version="v2")
    events = [{"type": "a", "sequence": 99, "time": 123.0, "text": "hi"}]
    assert policy.strip_envelopes(events) == [{"type": "a", "text": "hi"}]
    replayed = policy.replay({"version": "v2", "events": events})
    assert replayed == [{"type": "a", "text": "hi", "sequence": 1, "time": 0.0}]
    policy.register_historical("v1", "owner@example.org", "keel-session-v1")
    historical = policy.replay(
        {"version": "v1", "events": [{"type": "a", "sequence": 7, "time": 9.0}]}
    )
    assert historical == [{"type": "a", "sequence": 7, "time": 9.0}]
    assert policy.historical("v1")["owner"] == "owner@example.org"


def test_e4_7_browser_snapshot_lane():
    lane = BrowserSnapshotLane(ci=False)
    plan = lane.plan(["model_picker", "chat"])
    assert plan[0]["engines"] == ["chromium", "webkit"]
    assert plan[1]["engines"] == ["chromium"]
    assert lane.validate(plan) is True
    ci_plan = BrowserSnapshotLane(ci=True).plan(["chat"])
    assert ci_plan[0]["mode"] == "replay"
    assert BrowserSnapshotLane(ci=True).validate(ci_plan) is True
    assert lane.validate([{"widget": "model_picker", "engines": ["chromium"], "mode": "live"}]) is False


def test_e4_13_built_entrypoint_smoke(tmp_path):
    script = tmp_path / "entry.py"
    script.write_text(
        "import os, sys\n"
        "if '--config' in sys.argv:\n"
        "    path = sys.argv[sys.argv.index('--config') + 1]\n"
        "    sys.exit(0 if os.path.exists(path) else 1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    assert built_entrypoint_smoke([sys.executable], script)["returncode"] == 0
    missing = tmp_path / "missing-config.json"
    result = assert_missing_config_exits_nonzero([sys.executable], script, missing)
    assert result["returncode"] == 1
    with pytest.raises(AssertionError):
        assert_missing_config_exits_nonzero([sys.executable], script, script)


def test_e4_14_test_resolution(tmp_path):
    source = tmp_path / "src"
    built = tmp_path / "build"
    (source / "pkg").mkdir(parents=True)
    (built / "pkg").mkdir(parents=True)
    (source / "pkg" / "mod.py").write_text("", encoding="utf-8")
    resolver = TestResolver(source, built)
    assert resolver.assert_source_only("pkg.mod")["origin"] == "source"
    (built / "pkg" / "mod.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        resolver.resolve("pkg.mod")
    (source / "pkg" / "mod.py").unlink()
    assert resolver.resolve("pkg.mod")["built_mode"] is True
    with pytest.raises(AssertionError):
        resolver.assert_source_only("pkg.mod")


# ---------------------------------------------------------------------------
# W9
# ---------------------------------------------------------------------------


def test_w9_1_mcp_panel_states():
    panel = McpPanelService()
    panel.register("fs", protocol="stdio", timeout_s=15)
    assert panel.state("fs")["state"] == "disconnected"
    assert panel.connect("fs")["state"] == "needs_auth"
    auth = panel.authenticate("fs", "keel://callback")
    assert auth["state"] == "connected" and auth["callback_url"] == "keel://callback"
    assert panel.mark_error("fs", "boom")["state"] == "error"
    panel.disable("fs")
    assert panel.connect("fs")["state"] == "disabled"
    panel.set_config("fs", timeout_s=30, protocol="http")
    assert panel.snapshot()["fs"]["timeout_s"] == 30
    with pytest.raises(ValueError):
        panel.register("bad", protocol="ftp")


def test_w9_2_approval_actions_and_pending_cancel():
    service = ApprovalService()
    for index in range(3):
        service.submit(f"r{index}", "shell", "rm -rf *")
    assert service.decide("r0", "once")["decision"] == "once"
    always = service.decide("r1", "always", pattern="git status")
    assert service.saved_pattern("shell") == "git status"
    rejected = service.decide("r2", "reject", feedback="too risky")
    assert rejected["cancelled"] == []  # only r2 remained pending
    service.submit("r3", "shell", "x")
    service.submit("r4", "shell", "y")
    assert set(service.decide("r3", "reject")["cancelled"]) == {"r4"}


def test_w9_3_agent_editor_config_and_simulation():
    config = normalize_agent_config(
        {
            "mode": "primary",
            "model": "openai/gpt-4#high",
            "step_limit": 5,
            "color": "#112233",
            "hidden": True,
            "permissions": ["read:*", "shell.ls"],
            "subagent_allowlist": ["reviewer"],
        }
    )
    assert config["model"]["variant"] == "high" and config["step_limit"] == 5
    assert simulate_permission(config, "read:file") is True
    assert simulate_permission(config, "shell.rm") is False
    with pytest.raises(ValueError):
        normalize_agent_config({"model": "openai/gpt-4", "color": "red"})


def test_w9_4_command_palette_preview():
    entries = build_palette_entries(
        [{"name": "review", "prompt": "Review $1 with $ARGUMENTS", "description": "review code"}]
    )
    assert entries[0]["hints"] == ["$1", "$ARGUMENTS"]
    preview = expand_command_prompt("Review $1 with $ARGUMENTS", ["file.py", "carefully"])
    assert preview["preview"] == "Review file.py with file.py carefully"
    assert preview["first"] == "file.py"


def test_w9_5_first_run_notice(tmp_path):
    notice = FirstRunNotice(tmp_path / "state" / "first-run.json")
    assert notice.is_first_run() is True
    assert "review approvals" in notice.safety_notice()["points"][0]
    assert any("loopback" in item for item in notice.known_limits())
    assert notice.mark_seen()["seen"] is True and notice.is_first_run() is False


def test_w9_6_loopback_web_config_banner():
    config = web_server_config(port=0, ssh_user="alice", ssh_host="host.test")
    assert config["loopback"] is True and "ssh -L" in config["ssh_hint_banner"]
    assert "alice@host.test" in config["ssh_hint_banner"]
    with pytest.raises(ValueError):
        web_server_config(host="0.0.0.0")


# ---------------------------------------------------------------------------
# X9
# ---------------------------------------------------------------------------


def test_x9_2_vcr_record_replay_scrubs_secrets(tmp_path):
    recorder = VcrRecorder(tmp_path / "cassette.jsonl")
    request = {"method": "POST", "url": "https://api.test/v1", "body": "key sk-abcdefgh1234"}
    response = {"status": 200, "headers": {"Authorization": "Bearer secret-token"}, "body": "ok"}
    entry = recorder.record(request, response)
    assert "[REDACTED]" in entry["request"]["body"]
    assert entry["response"]["headers"]["Authorization"] == "[REDACTED]"
    replayed = recorder.replay(request)
    assert replayed == entry["response"]
    assert recorder.replay({"method": "GET", "url": "other"}) is None


def test_x9_4_mcp_conformance_against_sample_servers():
    runner = McpConformanceRunner()
    reports = {report["server"]: report for report in runner.run_samples()}
    assert reports["sample-stdio"]["passed"] is True
    assert reports["sample-http"]["passed"] is True
    assert reports["hostile-huge"]["results"]["output_within_limit"] is False
    assert reports["hostile-hang"]["results"]["within_timeout"] is False
    assert reports["hostile-schema"]["results"]["schema_valid"] is False
    assert len(runner.sample_servers()) == 5


def test_x9_6_pseudo_localization_and_rtl():
    pseudo = pseudo_localize("Hello")
    assert pseudo.startswith("⟦") and "é" in pseudo
    assert "é" in pseudo_localize("Hello", expand=False)
    rtl = rtl_smoke("مرحبا")
    assert rtl["ok"] is True and rtl["markers"] == ["RLI", "PDI"]
    assert rtl["rendered"].startswith("\u202b")


def test_x9_8_token_accounting_accuracy():
    check = TokenAccountingCheck(tolerance=0.10)
    assert check.evaluate(100, 105)["within_tolerance"] is True
    bad = check.evaluate(100, 150)
    assert bad["within_tolerance"] is False and bad["delta"] == 50


def test_x9_9_long_session_soak_monitor():
    monitor = SoakMonitor()
    monitor.sample(0, 100 * 1_048_576, 10 * 1_048_576, 8.0)
    monitor.sample(5000, 120 * 1_048_576, 30 * 1_048_576, 12.0)
    summary = monitor.summary()
    assert summary["samples"] == 2 and summary["event_span"] == 5000
    assert summary["memory_growth_mb"] == 20.0
    assert monitor.check()["passed"] is True
    monitor.sample(10000, 300 * 1_048_576, 30 * 1_048_576, 40.0)
    result = monitor.check()
    assert result["passed"] is False
    assert "memory" in result["violations"] and "frame_time" in result["violations"]


def test_x9_10_mutation_report_dashboard():
    report = MutationReport()
    report.add("permission_gate", "m1", True)
    report.add("permission_gate", "m2", False)
    report.add("command_analyzer", "m3", True)
    assert report.score("permission_gate") == 50.0
    payload = report.dashboard_payload()
    assert payload["visibility"] == "private"
    assert payload["targets"]["command_analyzer"]["score"] == 100.0
    with pytest.raises(ValueError):
        report.add("unknown", "m4", True)


# ---------------------------------------------------------------------------
# W6
# ---------------------------------------------------------------------------


def test_w6_2_confidence_labels():
    labeler = ConfidenceLabeler()
    assert labeler.render(labeler.label("Paris is in France", "high", True)).startswith("[high]")
    for label in ("moderate", "low", "unknown"):
        assert labeler.label("claim", label)["confidence"] == label
    with pytest.raises(ValueError):
        labeler.label("web claim", "unknown", factual_web_claim=True)
    with pytest.raises(ValueError):
        labeler.label("claim", "maybe")


def test_w6_4_conductor_specialist_routing():
    router = ConductorRouter()
    router.set_conductor("conductor")
    with pytest.raises(ValueError):
        router.set_conductor("other")
    assert router.route(False)["agent"] == "conductor"
    router.register_specialist("codex")
    assert router.route(True)["role"] == "specialist"
    router.assign_writer("tree-a", "writer-1")
    with pytest.raises(ValueError):
        router.assign_writer("tree-a", "writer-2")
    assert router.verify_after_specialist(True, True)["verified"] is True
    with pytest.raises(ValueError):
        router.verify_after_specialist(True, False)


def test_w6_5_control_plane_tool_routing():
    assert choose_tool("dom", True)["tool"] == "browser"
    assert choose_tool("desktop", True)["tool"] == "local_desktop"
    assert choose_tool("desktop", False)["tool"] == "cloud"
    enriched = choose_tool("accessibility", True, accessibility_available=True)
    assert enriched["enrichment"] is True
    assert "PERSONA.md" in choose_tool("other", True)["hint"]


def test_w6_6_memory_ledger_requires_approval(tmp_path):
    ledger = MemoryLedger(tmp_path / "MEMORY.md")
    proposal = ledger.propose("use PostgreSQL")
    assert proposal["needs_approval"] is True
    with pytest.raises(PermissionError):
        ledger.write(proposal["fact"], approved=False)
    written = ledger.write(proposal["fact"], approved=True)
    assert "use PostgreSQL" in written
    assert "use PostgreSQL" in ledger.read()


# ---------------------------------------------------------------------------
# W8
# ---------------------------------------------------------------------------


def test_w8_1_allowlist_patterns():
    matcher = AllowlistMatcher(["admin@example.org", "@example.com", "device-lab-*"])
    assert matcher.matches("admin@example.org") is True  # exact
    assert matcher.matches("anyone@EXAMPLE.COM") is True  # @domain pattern
    assert matcher.matches("device-lab-042") is True  # device prefix pattern
    assert matcher.matches("stranger@other.test") is False


def test_w8_2_blob_caps():
    caps = BlobCaps()
    assert caps.check("recording", 1_000)["accepted"] is True
    oversized = caps.check("screenshot", 6_000_000)
    assert oversized["accepted"] is False and oversized["cap_bytes"] == 5_000_000
    assert BlobCaps(screenshot=10).check("screenshot", 5)["accepted"] is True
    with pytest.raises(ValueError):
        caps.check("unknown", 1)


def test_w8_3_computer_access_guard():
    guard = ComputerAccessGuard(["home", "box-1", "box-2"], core_desktop_id="home")
    assert guard.validate(["box-1"])["valid"] is True
    assert guard.validate(["box-9"])["unknown"] == ["box-9"]
    assert guard.mutate("box-1", {"name": "renamed"}) == {"name": "renamed"}
    with pytest.raises(PermissionError):
        guard.mutate("home", {"name": "nope"})
    with pytest.raises(ValueError):
        guard.mutate("box-9", {})


def test_w8_4_shared_question_form():
    opencode = normalize_question(
        "opencode_question", {"questions": [{"id": "q1", "question": "Proceed?", "type": "confirm"}]}
    )
    elicitation = normalize_question(
        "mcp_elicitation",
        {"requestedSchema": {"properties": {"q2": {"title": "Pick one", "type": "string"}}}},
    )
    assert opencode["form"] == elicitation["form"] == "question_card"
    assert opencode["questions"][0]["id"] == "q1"
    assert elicitation["questions"][0]["id"] == "q2"
    with pytest.raises(ValueError):
        normalize_question("other", {})


# ---------------------------------------------------------------------------
# W2
# ---------------------------------------------------------------------------


def test_w2_5_agent_fields_and_disabled_builtin():
    builtins = {
        "build": {"capabilities": ["primary"]},
        "old": {"capabilities": ["primary"]},
    }
    result = apply_agent_fields(
        builtins,
        {
            "build": {"hidden": True, "color": "#abcdef"},
            "old": {"disabled": True},
        },
    )
    assert "old" not in result
    assert result["build"]["hidden"] is True
    assert result["build"]["hidden_is_visibility_only"] is True
    assert result["build"]["color"] == "#abcdef"


def test_w2_7_default_agent_chain_and_session_pin():
    agents = {
        "reviewer": {"hidden": False, "capabilities": ["primary"]},
        "helper": {"hidden": True, "capabilities": ["primary"]},
    }
    assert resolve_default_agent(None, agents) == "reviewer"  # no build -> first visible
    agents["build"] = {"capabilities": []}
    assert resolve_default_agent(None, agents) == "build"
    assert resolve_default_agent("reviewer", agents) == "reviewer"

    pins = SessionAgentPin()
    pins.bind("s1", "reviewer")
    assert pins.agent_for("s1") == "reviewer"  # changing the default does not alter sessions
    assert resolve_default_agent("build", agents) == "build"
    assert pins.agent_for("s1") == "reviewer"
    with pytest.raises(ValueError):
        resolve_default_agent(None, {"hidden": {"hidden": True, "capabilities": []}})


def test_w2_10_model_reference_forms():
    ref = ModelReference.parse("openai/gpt-4#high")
    assert (ref.provider, ref.model, ref.variant) == ("openai", "gpt-4", "high")
    assert ref.to_string() == "openai/gpt-4#high"
    obj = ModelReference.from_object(
        {"provider": "local", "model": "llama", "variant": "low", "temperature": 0.2}
    )
    assert obj.to_dict() == {
        "provider": "local",
        "model": "llama",
        "variant": "low",
        "temperature": 0.2,
    }
    with pytest.raises(ValueError):
        ModelReference.parse("no-slash")


# ---------------------------------------------------------------------------
# W5
# ---------------------------------------------------------------------------


def test_w5_5_model_precedence():
    assert resolve_model_precedence("cmd", "agent", "session") == "cmd"
    assert resolve_model_precedence(None, "agent", "session") == "agent"
    assert resolve_model_precedence(None, None, "session") == "session"
    assert resolve_model_precedence() is None


def test_w5_6_background_child_command_reporting():
    runner = BackgroundCommandRunner()
    assert runner.run("p1", "c0", lambda: "x")["background"] is False
    assert runner.run("p1", "c1", lambda: 42, subagent=True)["status"] == "ok"

    def fail():
        raise RuntimeError("boom")

    failed = runner.run("p1", "c2", fail, subagent=True)
    assert failed["status"] == "error" and failed["result"] == "boom"
    report = runner.report_to_parent("p1")
    assert {item["command_id"] for item in report} == {"c1", "c2"}


def test_w5_7_templates_keep_at_path_raw(tmp_path):
    store = CommandTemplateStore(tmp_path / "templates.json")
    store.store("analyze", "Read @secret.txt and summarize")
    assert store.has_at_path("analyze") is True
    rendered = store.render("analyze", attachments=["composer.png"])
    assert rendered["prompt"] == "Read @secret.txt and summarize"
    assert rendered["attachments"] == ["composer.png"]
    assert rendered["expanded_at_path"] is False
    assert "@secret.txt" in open(store.path, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# X0
# ---------------------------------------------------------------------------


def test_x0_2b_milestone_split():
    splitter = MilestoneSplitter()
    assert splitter.split("M17") == ["M17-voice", "M17-documents", "M17-meetings"]
    assert splitter.split("M11")[0] == "M11-code-intel-core"
    assert splitter.split("M22")[-1] == "M22-stores"
    assert splitter.remap({"milestone": "M17", "id": "x"})["milestone"] == "M17-voice"
    assert splitter.split("M5") == ["M5"]


def test_x0_5_store_distribution_policy():
    policy = StorePolicy()
    policy.register("flathub", accepts_proprietary_freeware=True, requires_public_manifest=True)
    policy.register("microsoft-store", accepts_proprietary_freeware=True, requires_public_manifest=False)
    policy.register("some-linux-store", accepts_proprietary_freeware=False, requires_public_manifest=False)
    result = policy.evaluate()
    assert result["allowed"] == ["microsoft-store"]
    assert "flathub" in result["dropped"] and "some-linux-store" in result["dropped"]
    assert "aur-binary" in result["retained_binary_sources"]


def test_x0_9_risk_register_and_rollback():
    register = RiskRegister()
    register.add_risk("M1", "late licence finding", "medium", "high", "owner", "review early")
    register.set_rollback("M1", "revert to previous signed release")
    assert register.validate(["M1"])["complete"] is True
    incomplete = register.validate(["M1", "M2"])
    assert "M2:risk" in incomplete["missing"] and "M2:rollback" in incomplete["missing"]
    assert register.report()["risks"][0]["owner"] == "owner"
    with pytest.raises(ValueError):
        register.add_risk("M3", "x", "unlikely", "high", "owner", "y")


# ---------------------------------------------------------------------------
# X10
# ---------------------------------------------------------------------------


def test_x10_3_decision_log(tmp_path):
    log = DecisionLog(tmp_path / "DECISIONS.json")
    entry = log.add("D1", "Keep offline?", "Yes", when="2026-01-02")
    assert entry["kind"] == "decision_log" and entry["date"] == "2026-01-02"
    assert log.list()[0]["id"] == "D1"
    with pytest.raises(ValueError):
        log.add("D99", "bad id", "no")
    with pytest.raises(ValueError):
        log.add("D1", "duplicate", "no")


def test_x10_5_weekly_report(tmp_path):
    index = tmp_path / "PLAN-INDEX.json"
    base = {
        "id": "A1",
        "status": "verified",
        "verification_evidence": "ok",
    }
    features = [
        dict(base),
        {"id": "A2", "status": "verified", "verification_evidence": ""},
        {"id": "A3", "status": "not_started"},
        {"id": "A4", "status": "verified", "verification_evidence": "ok", "ci_status": "failing"},
    ]
    index.write_text(json.dumps({"features": features}), encoding="utf-8")
    report = generate_weekly_report(index)
    assert report["total"] == 4
    assert report["counts"]["verified"] == 3
    assert report["counts"]["not_started"] == 1
    assert report["stale_evidence"] == ["A2"]
    assert report["failing_rows"] == ["A4"]


def test_x10_6_scope_creep_guard(tmp_path):
    guard = ScopeCreepGuard(tmp_path / "INBOX.md")
    result = guard.capture("Add a new chart type", "M19")
    assert result["inline_build"] is False
    assert len(guard.entries()) == 1
    assert "M19" in guard.entries()[0]
    with pytest.raises(ValueError):
        guard.capture("", "M19")


# ---------------------------------------------------------------------------
# W3
# ---------------------------------------------------------------------------


def test_w3_11_mcp_permission_actions():
    assert McpPermissionActions.list_action() == "keel_list_mcp_resources"
    assert McpPermissionActions.read_action() == "keel_read_mcp_resource"
    assert McpPermissionActions.tool_action("filesystem", "read") == "keel_filesystem_read"
    assert McpPermissionActions.list_resource("filesystem") == "filesystem"
    resource = McpPermissionActions.read_resource("filesystem", "file:///tmp/a")
    assert resource == "filesystem:file:///tmp/a"
    assert McpPermissionActions.parse_resource(resource) == {
        "server": "filesystem",
        "uri": "file:///tmp/a",
    }
    assert McpPermissionActions.parse_resource("filesystem")["uri"] is None


def test_w3_5_path_expansion_only_for_path_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows expanduser source
    config = expand_path_actions(
        {
            "path": "~/config.json",
            "cwd": "$HOME/work",
            "command": "echo $HOME",
            "shell": "ls ~",
        }
    )
    assert Path(config["path"]) == tmp_path / "config.json"
    assert Path(config["cwd"]) == tmp_path / "work"
    assert config["command"] == "echo $HOME"  # shell resource stays raw
    assert config["shell"] == "ls ~"
    assert config["command_raw"] == "echo $HOME"


# ---------------------------------------------------------------------------
# Y6
# ---------------------------------------------------------------------------


def test_y6_3_repo_descriptor():
    good = repo_descriptor(
        "Cowork, Code, Duet and Fleet in one app", "https://keel-desktop.vercel.app"
    )
    assert good["valid"] is True and good["missing_surfaces"] == []
    bad = repo_descriptor("Only Cowork and Code", "https://elsewhere.test")
    assert bad["valid"] is False
    assert set(bad["missing_surfaces"]) == {"Duet", "Fleet"}


# ---------------------------------------------------------------------------
# Registry / owner-gate coverage
# ---------------------------------------------------------------------------


def test_x4_d2_e4_w9_x9_w6_w8_w2_w5_x0_x10_w3_y6_registry_dispatches_real_behavior():
    """Behavioural replacement for the old count-/-callable-only registry guard.

    The previous test only checked ID counts and that every registry value was
    callable.  A dict of 54 no-op lambdas passed it.  Here the registry itself
    is the system under test: for every group prefix we fetch the *registered*
    symbol and execute it with concrete inputs, pinning the exact result.
    """
    probes = {
        "X4": lambda: FEATURE_IMPLEMENTATIONS["X4.2"](["a", "b", "c"]),
        "D2": lambda: _serial_hook_run_result(),
        "E4": lambda: FEATURE_IMPLEMENTATIONS["E4.3"]().evaluate(
            {"files": {"a.py": {"covered": 9, "total": 10}}})["passed"],
        "W9": lambda: FEATURE_IMPLEMENTATIONS["W9.3"](
            {"mode": "primary", "model": "openai/gpt-4#high"})["model"]["variant"],
        "X9": lambda: FEATURE_IMPLEMENTATIONS["X9.6"]("Hello world"),
        "W6": lambda: (FEATURE_IMPLEMENTATIONS["W6.5"]("browser", True, True)["tool"],
                       FEATURE_IMPLEMENTATIONS["W6.2"]().label("claim", "moderate")["confidence"]),
        "W8": lambda: FEATURE_IMPLEMENTATIONS["W8.1"](["admin@example.org"]).matches(
            "admin@example.org"),
        "W2": lambda: FEATURE_IMPLEMENTATIONS["W2.7"](
            "configured", {"configured": {}, "other": {}}),
        "W5": lambda: FEATURE_IMPLEMENTATIONS["W5.5"](
            "cli-model", "agent-model", "session-model"),
        "X0": lambda: FEATURE_IMPLEMENTATIONS["X0.2b"]().split("M17"),
        "X10": lambda: _scope_creep_result(),
        "W3": lambda: FEATURE_IMPLEMENTATIONS["W3.5"]({"path": "a.txt"})["path"],
        "Y6": lambda: FEATURE_IMPLEMENTATIONS["Y6.3"](
            "Cowork, Code, Duet and Fleet in one app",
            "https://keel-desktop.vercel.app")["valid"],
    }
    expected = {
        "X4": ["abc"],
        "D2": 2,
        "E4": True,
        "W9": "high",
        "X9": "\u27e6H\u00e9ll\u00f3 w\u00f3rld\u27e7",
        "W6": ("local_desktop", "moderate"),
        "W8": True,
        "W2": "configured",
        "W5": "cli-model",
        "X0": ["M17-voice", "M17-documents", "M17-meetings"],
        "X10": False,
        "W3": "a.txt",
        "Y6": True,
    }
    assert set(probes) == set(GROUP_PREFIXES) == set(expected)
    for prefix in GROUP_PREFIXES:
        assert probes[prefix]() == expected[prefix], prefix


def _serial_hook_run_result():
    runner = FEATURE_IMPLEMENTATIONS["D2.2"]()
    runner.register("stream", "serial", lambda value: value + 1)
    runner.register("stream", "serial", lambda value: value + 1)
    return runner.run("stream", 0)


def _scope_creep_result():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        guard = FEATURE_IMPLEMENTATIONS["X10.6"](Path(tmp) / "INBOX.md")
        return guard.capture("Add a chart", "M19")["inline_build"]


def test_owner_gated_y6_4_is_documented_not_implemented():
    assert "Y6.4" in OWNER_GATED
    assert OWNER_GATED["Y6.4"]["implemented"] is False
    assert "owner" in OWNER_GATED["Y6.4"]["reason"].lower()
    assert "Y6.4" not in FEATURE_IMPLEMENTATIONS
