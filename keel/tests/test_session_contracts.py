"""Permanent contract-regression specs for the D2.x session/event model.

One or more tests per registry ID (D2.1, D2.3, D2.5, D2.7, D2.8, D2.9,
D2.10, D2.11, D2.13, D2.15, D2.16).  These specs are additive: they import
only ``keel.session_contracts`` and never mutate the live session loop.
"""

from __future__ import annotations

import os
import zlib
from dataclasses import FrozenInstanceError

import pytest

import keel.session_contracts as sc


# ---------------------------------------------------------------------------
# D2.1 -- event domains and typed Event records
# ---------------------------------------------------------------------------


def test_event_domains_and_typed_record():
    session = sc.make_event(1, "user/message", {"role": "user", "content": "hi"})
    agent = sc.make_event(2, "agent/inject", {"text": "note"}, agent_id="a1")
    provider = sc.make_event(3, "fs/read", {"path": "x"})
    ui = sc.make_event(4, "ui/render", {"frame": 1})
    assert session.domain is sc.EventDomain.SESSION
    assert agent.domain is sc.EventDomain.AGENT
    assert provider.domain is sc.EventDomain.PROVIDER
    assert ui.domain is sc.EventDomain.UI
    assert provider.domain in sc.TRANSIENT_DOMAINS
    assert session.payload_hash == sc.content_hash(session.payload)
    assert session.to_dict()["payload_hash"] == session.payload_hash
    assert sc.Event.from_dict(session.to_dict()) == session
    with pytest.raises(ValueError):
        sc.make_event(0, "", {})


def test_payload_hash_is_content_only_and_stable():
    a = sc.make_event(1, "user/message", {"b": 2, "a": 1})
    b = sc.make_event(99, "user/message", {"a": 1, "b": 2})
    assert a.payload_hash == b.payload_hash
    assert len(a.payload_hash) == 64


def test_event_bus_broadcast_and_agent_isolation():
    bus = sc.EventBus()
    session_seen: list[sc.Event] = []
    a1_seen: list[sc.Event] = []
    a2_seen: list[sc.Event] = []
    bus.subscribe(sc.EventDomain.SESSION, lambda e: session_seen.append(e))
    bus.subscribe(sc.EventDomain.SESSION, lambda e: session_seen.append(e))
    bus.subscribe(sc.EventDomain.AGENT, lambda e: a1_seen.append(e), agent_id="a1")
    bus.subscribe(sc.EventDomain.AGENT, lambda e: a2_seen.append(e), agent_id="a2")

    bus.publish(sc.make_event(0, "turn/start", {"turn_index": 0}))
    bus.publish(sc.make_event(0, "agent/inject", {"text": "x"}, agent_id="a1"))
    assert len(session_seen) == 2          # broadcast to every SESSION listener
    assert len(a1_seen) == 1 and len(a2_seen) == 0  # per-agent only


def test_event_bus_intercept_and_transient_not_durable():
    journal = sc.SessionJournal()
    bus = sc.EventBus(journal)
    bus.subscribe(sc.EventDomain.SESSION,
                  lambda e: sc.replace(e, payload={**e.payload, "x": 1}))
    out = bus.publish(sc.make_event(0, "user/message", {"content": "hi"}))
    assert out.payload["x"] == 1
    assert len(journal.events()) == 1
    bus.publish(sc.make_event(0, "fs/read", {"path": "x"}))
    bus.publish(sc.make_event(0, "ui/render", {"frame": 1}))
    bus.publish(sc.make_event(0, "agent/inject", {"text": "t"}, agent_id="a1"))
    assert len(journal.events()) == 1      # transient/agent events never persisted


# ---------------------------------------------------------------------------
# D2.3 -- turn / step model and grouping
# ---------------------------------------------------------------------------


def test_lifecycle_vocabulary_complete():
    for stage in ("turn/start", "input/claim", "model/selection",
                  "prompt/assemble", "hook/pre-step", "step/start",
                  "call/prepare", "assistant-stream", "assistant/message",
                  "assistant/attempt", "tool/call", "hook/pre-execute",
                  "tool/execute", "hook/post-execute", "tool/result",
                  "step/end", "hook/turn-stop", "turn/end"):
        assert stage in sc.TURN_LIFECYCLE
    assert sc.TURN_LIFECYCLE[0] == "turn/start"
    assert sc.TURN_LIFECYCLE[-1] == "turn/end"


def test_group_events_into_turns_and_steps():
    j = sc.SessionJournal()
    j.start_turn(0)
    j.start_step(0, turn_index=0)
    j.add_tool_call("t1", "echo", {"a": 1}, turn_index=0, step_index=0)
    j.add_tool_result("t1", "ok", turn_index=0, step_index=0)
    j.end_step(0)
    j.end_turn(0)
    turns = sc.group_into_turns(j.events())
    assert len(turns) == 1
    step = turns[0].steps[0]
    assert step.index == 0 and step.turn_index == 0
    assert step.tool_calls[0].tool_use_id == "t1"
    assert not step.failed


def test_group_into_turns_zero_step_turn_and_interrupted():
    j = sc.SessionJournal()
    j.start_turn(0)
    j.end_turn(0)
    j.start_turn(1)                       # interrupted: no turn/end
    j.start_step(0, turn_index=1)
    j.end_step(0)
    complete = sc.group_into_turns(j.events())
    assert len(complete) == 1
    repaired = sc.group_into_turns(j.events(), repair_interrupted=True)
    assert len(repaired) == 2
    assert repaired[1].steps[0].index == 0


# ---------------------------------------------------------------------------
# D2.5 -- per-agent inbox with inject() and deterministic wake ordering
# ---------------------------------------------------------------------------


def test_inbox_inject_waits_for_waking_message():
    registry = sc.InboxRegistry()
    box = registry.inbox("a1")
    inj = box.inject("context", sc.InjectionSource.AGENT_MESSAGE)
    assert inj.state is sc.InjectionState.WAITING
    assert len(box.pending()) == 1
    assert not sc.build_request(model="", system=None, messages=[],
                                tool_schemas=[]).injections
    admitted = registry.admit("a1")
    assert len(admitted) == 1
    assert admitted[0].state is sc.InjectionState.ADMITTED
    assert box.pending() == ()


def test_injection_wake_order_is_deterministic():
    registry = sc.InboxRegistry()
    registry.inject("b", "first", sc.InjectionSource.USER)
    registry.inject("a", "second", sc.InjectionSource.HOOK)
    assert registry.wake_order() == ("b", "a")
    registry.inject("a", "third", sc.InjectionSource.TOOL_RESULT)
    assert registry.wake_order() == ("b", "a")       # earliest wake token wins
    admitted = registry.admit("a")
    assert [i.text for i in admitted] == ["second", "third"]
    assert registry.wake_order() == ("b",)
    assert admitted[0].tainted is False
    assert admitted[1].tainted is True               # tool-result source taints


def test_admitted_injection_is_logged_and_model_visible():
    journal = sc.SessionJournal()
    registry = sc.InboxRegistry(journal)
    registry.inject("a1", "from subagent", sc.InjectionSource.SUBAGENT_SETTLED)
    # Reuse the same journal for both so replay sees the injection event.
    journal.snapshot_model("m", [])
    journal.add_user("q")
    inj = registry.admit("a1")[0]
    req = sc.build_request(model="m", system=None,
                           messages=[{"role": "user", "content": "q"}],
                           tool_schemas=[], injections=[inj], step_index=0)
    journal.admit_request(req)
    journal.start_turn(0)
    journal.start_step(0, turn_index=0)
    journal.end_step(0)
    journal.end_turn(0)
    rebuilt = journal.model_visible_events()
    assert len(rebuilt) == 1
    assert any(m.get("content") == "from subagent"
               and m.get("tainted") is True for m in rebuilt[0].messages)


# ---------------------------------------------------------------------------
# D2.7 -- system prompt as logged history
# ---------------------------------------------------------------------------


def test_system_prompt_logged_history_and_empty_clears():
    j = sc.SessionJournal()
    assert j.system_prompt() is None
    j.set_system_prompt("Be brief.")
    assert j.system_prompt() == "Be brief."
    j.set_system_prompt("")
    assert j.system_prompt() is None
    logged = [e for e in j.events() if e.kind == "system/message"]
    assert len(logged) == 2                    # clearing is itself an event
    assert logged[0].payload_hash != logged[1].payload_hash


# ---------------------------------------------------------------------------
# D2.8 -- cancellation during prompt preparation commits nothing
# ---------------------------------------------------------------------------


def test_cancellation_during_prepare_commits_nothing():
    j = sc.SessionJournal()
    cancel = __import__("threading").Event()
    cancel.set()
    with pytest.raises(sc.CancelledDuringPrepare):
        with sc.StepPreparation(j, cancel.is_set) as prep:
            prep.system("system text").user("user text")
    assert j.events() == ()
    assert j.system_prompt() is None


def test_successful_prepare_commits_all_staged():
    j = sc.SessionJournal()
    with sc.StepPreparation(j, lambda: False) as prep:
        prep.system("sys").user("hello")
    assert [e.kind for e in j.events()] == ["system/message", "user/message"]
    assert j.system_prompt() == "sys"


# ---------------------------------------------------------------------------
# D2.9 -- synthetic missing tool results
# ---------------------------------------------------------------------------


def test_failed_step_records_synthetic_missing_results():
    j = sc.SessionJournal()
    j.snapshot_model("m", [])
    j.add_user("x")
    j.start_turn(0)
    j.start_step(0, turn_index=0)
    j.add_tool_call("t1", "echo", {}, turn_index=0, step_index=0)
    committed = j.close_failed_step(0, reason="provider error")
    j.end_turn(0)
    synthetic = [e for e in j.events()
                 if e.kind == "tool/result" and e.payload.get("synthetic")]
    assert len(synthetic) == 1
    assert synthetic[0].payload["tool_use_id"] == "t1"
    assert any(e.kind == "step/end" and e.payload["failed"] for e in j.events())
    rebuilt = j.model_visible_events()
    assert len(rebuilt) == 1
    assert any(m.get("tool_use_id") == "t1" for m in rebuilt[0].messages)
    assert committed[-1].kind == "step/end"


def test_repair_missing_tool_results_is_pure():
    calls = [sc.make_event(1, "tool/call", {"tool_use_id": "a", "name": "n"}),
             sc.make_event(2, "tool/call", {"tool_use_id": "b", "name": "n"})]
    result = sc.make_event(3, "tool/result", {"tool_use_id": "a"})
    built = sc.repair_missing_tool_results(
        [*calls, result], reason="cancelled")
    assert len(built) == 1
    assert built[0].payload["tool_use_id"] == "b"
    assert built[0].payload["reason"] == "cancelled"
    assert all(e.seq == 0 for e in built)      # staged, not committed


# ---------------------------------------------------------------------------
# D2.10 -- live stream frames vs durable settled message
# ---------------------------------------------------------------------------


def test_stream_frames_settle_into_durable_message():
    ticks = iter([1.0, 1.01, 1.02, 1.03])
    stream = sc.StreamBuffer(clock=lambda: next(ticks))
    stream.start()
    stream.chunk("he")
    stream.chunk("llo")
    stream.end()
    compact = stream.compact()
    assert [f["k"] for f in compact] == ["start", "chunk", "chunk", "end"]
    assert compact[1]["ms"] == 10
    j = sc.SessionJournal()
    settled = sc.settle_assistant(j, "hello", stream)
    assert settled.payload["stream"] == compact
    assert stream.frames() == ()


def test_attempts_do_not_enter_model_history():
    j = sc.SessionJournal()
    j.snapshot_model("m", [])
    j.add_user("q")
    j.record_attempt("failed", reason="boom")
    j.record_attempt("retried")
    j.record_attempt("cancelled")
    req = sc.build_request(model="m", system=None,
                           messages=[{"role": "user", "content": "q"}],
                           tool_schemas=[], step_index=0)
    j.admit_request(req)
    j.start_turn(0)
    j.start_step(0, turn_index=0)
    j.end_step(0)
    j.end_turn(0)
    rebuilt = j.model_visible_events()
    assert len(rebuilt) == 1
    assert list(rebuilt[0].messages) == [{"role": "user", "content": "q"}]
    assert sum(1 for e in j.events() if e.kind == "assistant/attempt") == 3
    with pytest.raises(ValueError):
        j.record_attempt("unknown")


# ---------------------------------------------------------------------------
# D2.11 -- model-visible <=> logged; exact request bytes
# ---------------------------------------------------------------------------


def test_replay_reproduces_exact_request_hash():
    j = sc.SessionJournal()
    j.set_system_prompt("sys")
    schema = {"name": "echo", "description": "d",
              "input_schema": {"type": "object"}}
    j.snapshot_model("m1", [schema])
    j.add_user("hello")
    req = sc.build_request(model="m1", system="sys",
                           messages=[{"role": "user", "content": "hello"}],
                           tool_schemas=[schema], turn_index=0, step_index=0)
    j.admit_request(req)
    j.start_turn(0)
    j.start_step(0, turn_index=0)
    j.end_step(0)
    j.end_turn(0)
    rebuilt = j.model_visible_events()
    assert len(rebuilt) == 1
    assert rebuilt[0].canonical_bytes() == req.canonical_bytes()
    assert rebuilt[0].request_hash == req.request_hash


def test_invisible_new_field_raises():
    sc.register_model_visible_field("trace_id", ("trace/annotation",))
    try:
        j = sc.SessionJournal()
        req = sc.build_request(model="", system=None, messages=[],
                               tool_schemas=[])
        with pytest.raises(sc.InvisibleModelInputError, match="trace_id"):
            sc.assert_request_is_reconstructible(
                req, j.events(), extra_fields=("trace_id",))
        j.append(sc.make_event(0, "trace/annotation", {"value": "t"}))
        sc.assert_request_is_reconstructible(
            req, j.events(), extra_fields=("trace_id",))
        with pytest.raises(sc.InvisibleModelInputError, match="not registered"):
            sc.assert_request_is_reconstructible(
                req, j.events(), extra_fields=("unregistered",))
    finally:
        sc.MODEL_VISIBLE_FIELDS.pop("trace_id", None)


def test_unlogged_projection_raises_on_admit():
    j = sc.SessionJournal()
    j.add_user("x")
    req = sc.build_request(model="m", system=None,
                           messages=[{"role": "user", "content": "x"}],
                           tool_schemas=[])
    with pytest.raises(sc.InvisibleModelInputError, match="model"):
        j.admit_request(req)
    assert len(j.events()) == 1               # nothing committed on failure


def test_transient_domains_are_not_model_visible():
    j = sc.SessionJournal()
    j.append(sc.make_event(0, "fs/read", {"path": "x"}))
    j.append(sc.make_event(0, "agent/inject", {"text": "t"}, agent_id="a1"))
    assert j.model_visible_events() == ()


# ---------------------------------------------------------------------------
# D2.13 -- versioning and adjacent migrations
# ---------------------------------------------------------------------------


def _events():
    return [sc.make_event(1, "user/message", {"role": "user", "content": "x"}),
            sc.make_event(2, "turn/start", {"turn_index": 0}, turn_index=0),
            sc.make_event(3, "turn/end", {"turn_index": 0}, turn_index=0)]


def test_version_migration_chain_and_non_adjacent_rejection():
    events = _events()
    with pytest.raises(sc.NonAdjacentMigrationError):
        sc.migrate_adjacent(events, 1, 3)
    with pytest.raises(sc.NonAdjacentMigrationError):
        sc.migrate_adjacent(events, 1, 1)
    chained = sc.migrate_events(events, 1, 3)
    assert len(chained) == len(events)
    assert all(e.payload_hash == sc.content_hash(e.payload) for e in chained)
    assert sc.migrate_events(events, 2, 3)[0].payload_hash == events[0].payload_hash


def test_header_stat_list_picks_highest_readable(tmp_path):
    events = _events()
    sc.write_session(sc.session_path(tmp_path, "s1", 1), events,
                     session_id="s1", version=1)
    sc.write_session(sc.session_path(tmp_path, "s1", 2), events,
                     session_id="s1", version=2)
    sc.write_session(sc.session_path(tmp_path, "s1", 4), events,
                     session_id="s1", version=4)     # unreadable generation
    stat = sc.stat_session(sc.session_path(tmp_path, "s1", 1))
    assert stat.version == 1 and stat.readable
    stats = sc.list_sessions(tmp_path)
    assert stats["s1"].version == 2
    assert stats["s1"].event_count == len(events)
    with pytest.raises(sc.UnsupportedVersionError):
        sc.read_session(sc.session_path(tmp_path, "s1", 4))


def test_read_open_translates_in_memory(tmp_path):
    events = _events()
    path = sc.session_path(tmp_path, "s3", 1)
    sc.write_session(path, events, session_id="s3", version=1)
    version, translated = sc.read_session(path)
    assert version == 1
    assert sc.CURRENT_VERSION == 3
    assert translated[0].payload_hash == events[0].payload_hash
    assert path.read_bytes().startswith(b'{"format":"keel-session","version":1')


def test_write_successor_preserves_source_and_refuses_overwrite(tmp_path):
    events = _events()
    source = sc.session_path(tmp_path, "s2", 1)
    sc.write_session(source, events, session_id="s2", version=1)
    before = source.read_bytes()
    successor = sc.write_successor(source, sc.migrate_events(events, 1, 2))
    assert successor.name.endswith(".v2.jsonl")
    assert source.read_bytes() == before         # source never renamed/overwritten
    with pytest.raises(sc.GenerationExistsError):
        sc.write_session(successor, events, session_id="s2", version=2)


def test_interrupted_turn_repair_is_bounded_and_released_only():
    events = [
        sc.make_event(1, "turn/start", {"turn_index": 0}, turn_index=0),
        sc.make_event(2, "user/message", {"role": "user", "content": "x"}),
    ]
    repaired = sc.migrate_adjacent(events, 2, 3)
    assert any(e.kind == "turn/end"
               and e.payload.get("reason") == "released_restart"
               for e in repaired)
    unchanged = sc.migrate_adjacent(events, 2, 3, released_restart=False)
    assert not any(e.kind == "turn/end" for e in unchanged)
    two_open = events + [
        sc.make_event(3, "turn/start", {"turn_index": 1}, turn_index=1)]
    with pytest.raises(sc.UnboundedRestartRepairError):
        sc.migrate_adjacent(two_open, 2, 3)


def test_compressed_session_with_registered_codec(tmp_path):
    sc.register_codec(".zstd", zlib.compress, zlib.decompress)
    try:
        path = sc.session_path(tmp_path, "c1", 1, compressed=True)
        sc.write_session(path, _events(), session_id="c1", version=1)
        assert path.name.endswith(".zstd")
        assert sc.stat_session(path).event_count == len(_events())
        version, events = sc.read_session(path)
        assert version == 1 and len(events) == len(_events())
    finally:
        sc._CODECS.pop(".zstd", None)


def test_unsupported_compression_typed_error():
    sc._CODECS.pop(".zstd", None)
    with pytest.raises(sc.UnsupportedCompressionError):
        sc.codec_for("session.v1.jsonl.zstd")


# ---------------------------------------------------------------------------
# D2.15 -- fork at a turn boundary
# ---------------------------------------------------------------------------


def _fork_journal():
    j = sc.SessionJournal()
    j.start_turn(0)
    j.start_step(0, turn_index=0)
    j.add_tool_call("t", "echo", {}, turn_index=0, step_index=0)
    j.add_tool_result("t", "ok", turn_index=0, step_index=0)
    j.end_step(0)
    j.end_turn(0)
    j.append(sc.make_event(0, "fs/read", {"path": "x"},
                           published_by="provider"))
    j.start_turn(1)
    j.start_step(1, turn_index=1)
    j.end_step(1)
    j.end_turn(1)
    return j


def test_fork_at_turn_boundary_is_deterministic():
    j = _fork_journal()
    first = sc.fork(j, 1, seed=7, session_id="branch")
    second = sc.fork(j, 1, seed=7, session_id="branch")
    assert first == second
    assert first.events == second.events
    assert first.event_id("step") == second.event_id("step")
    assert first.inherited_event_count == len(first.events)
    assert [e.seq for e in first.events] == list(range(1, len(first.events) + 1))
    assert first.next_seq == len(first.events) + 1


def test_fork_filters_non_agent_loop_events_and_rejects_non_boundary():
    j = _fork_journal()
    forked = sc.fork(j, 1)
    assert all(e.published_by == sc.AGENT_LOOP for e in forked.events)
    assert all(e.domain is not sc.EventDomain.PROVIDER for e in forked.events)
    assert forked.at_turn == 1
    with pytest.raises(sc.NotATurnBoundaryError):
        sc.fork(j, 2)
    assert sc.fork(j, 0).inherited_event_count < forked.inherited_event_count


# ---------------------------------------------------------------------------
# D2.16 -- working directories are metadata only
# ---------------------------------------------------------------------------


def _dir_context():
    return sc.DirectoryContext(project_root="/proj", working_dir="/proj",
                               write_roots=("/proj",), process_cwd="/proj")


def test_working_dir_is_metadata_only():
    ctx = _dir_context()
    before_cwd = os.getcwd()
    new = ctx.with_working_dir("/scratch/work", label="scratch",
                               purpose="execution")
    assert new.working_dir == "/scratch/work"
    assert new.project_root == ctx.project_root
    assert new.write_roots == ctx.write_roots
    assert new.process_cwd == ctx.process_cwd
    assert new.project_id == ctx.project_id
    assert os.getcwd() == before_cwd
    report = ctx.validate_change("/scratch/work")
    assert report["project_identity_unchanged"] is True
    assert report["write_roots_unchanged"] is True
    assert report["process_cwd_unchanged"] is True
    assert new.execution_path("a.txt") == os.path.normpath("/scratch/work/a.txt")


def test_working_dir_validation_and_immutability():
    ctx = _dir_context()
    with pytest.raises(sc.WorkingDirectoryError):
        ctx.with_working_dir("")
    with pytest.raises(sc.WorkingDirectoryError):
        ctx.with_working_dir("bad\x00path")
    with pytest.raises(sc.WorkingDirectoryError):
        ctx.with_working_dir("/x", purpose="sandbox")
    with pytest.raises(FrozenInstanceError):
        ctx.write_roots = ("/other",)
