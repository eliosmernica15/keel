"""D3.* P1/P2 backend behaviour — stdlib only, no I/O, no network, no UI."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from keel import capability_seams as cs
from keel import d3_backend as db

REPO = Path(__file__).resolve().parents[2]
PLAN = json.loads((REPO / "PLAN-INDEX.json").read_text(encoding="utf-8"))


def _d3_ids(priority: str) -> set[str]:
    return {row["id"] for row in PLAN["features"]
            if row["id"].startswith("D3.") and row.get("priority") == priority}


# ---------------------------------------------------------------------------
# coverage / aggregate / verified P0 references
# ---------------------------------------------------------------------------
def test_feature_ids_are_exactly_the_p1_and_p2_d3_rows():
    expected = _d3_ids("P1") | _d3_ids("P2")
    assert expected == set(db.FEATURE_IDS)
    assert len(db.FEATURE_IDS) == 13
    assert set(db.FEATURE_IDS).isdisjoint(_d3_ids("P0"))


def test_all_backend_descriptors_are_honest_and_complete():
    rows = db.all_backend_descriptors()
    assert set(rows) == set(db.FEATURE_IDS)
    for row in rows.values():
        assert row["feature_id"] in db.FEATURE_IDS
        assert row["layer"] == "stdlib_backend"
        assert row["runtime_claimed"] is True       # in-process logic really runs
        assert row["io_performed"] is False         # but no OS/DB I/O happened
        assert row["network"] is False
        assert row["frontend"] is False
        assert row["contract"]


def test_verified_p0_references_point_at_real_capability_seams_symbols():
    p0 = _d3_ids("P0")
    refs = db.verified_p0_references()
    assert set(refs) == p0
    for feature_id, ref in refs.items():
        assert (REPO / ref["source"]).is_file()
        assert (REPO / ref["test"]).is_file()
        for symbol in ref["symbols"]:
            assert hasattr(cs, symbol), f"{feature_id}: missing {symbol}"


# ---------------------------------------------------------------------------
# D3.3 — subagent providers behind one interface
# ---------------------------------------------------------------------------
def test_subagent_kinds_share_one_activation_interface():
    registry = db.SubagentRegistry()
    registry.register(db.SubagentProvider("child", db.SubagentKind.CHILD))
    registry.register(db.SubagentProvider("delegate", db.SubagentKind.DELEGATED,
                                          remote=True))
    registry.register(db.SubagentProvider("specialist", "external", remote=True))

    child = registry.activate("child", "fix the bug")
    delegate = registry.activate("delegate", "review the patch")
    external = registry.activate("specialist", "translate the docs")
    assert child.interface == delegate.interface == external.interface
    assert child.interface == db.SUBAGENT_INTERFACE
    assert child.fresh_child is True and child.delegates_turn is False
    assert delegate.fresh_child is False and delegate.delegates_turn is True
    assert external.delegates_turn is True
    assert all(not item.spawn and not item.io_performed
               for item in (child, delegate, external))
    assert child.describe()["kind"] == "child"
    assert len(registry.describe()["providers"]) == 3


def test_subagent_registry_rejects_broken_contracts():
    with pytest.raises(db.SubagentError, match="must implement"):
        db.SubagentProvider("bad", db.SubagentKind.CHILD, interface="other.Interface")
    with pytest.raises(db.SubagentError, match="remote flag"):
        db.SubagentProvider("bad", db.SubagentKind.EXTERNAL, remote=False)
    registry = db.SubagentRegistry()
    with pytest.raises(db.SubagentError, match="requires a SubagentProvider"):
        registry.register("not a provider")
    provider = db.SubagentProvider("child", "child")
    registry.register(provider)
    with pytest.raises(db.SubagentError, match="duplicate"):
        registry.register(provider)
    with pytest.raises(db.SubagentError, match="unknown"):
        registry.activate("missing", "task")
    with pytest.raises(db.D3BackendError, match="task"):
        registry.activate("child", "   ")


# ---------------------------------------------------------------------------
# D3.4 — agent teams
# ---------------------------------------------------------------------------
def test_teams_are_enabled_per_root_session():
    service = db.TeamService()
    with pytest.raises(db.TeamError, match="not enabled"):
        _ = service.board
    board = service.enable("root-1")
    assert service.enable("root-1") is board
    assert service.describe()["enabled"] is True
    assert board.root_session_id == "root-1"
    with pytest.raises(db.TeamError, match="already enabled"):
        service.enable("root-2")


def test_team_task_policy_and_owner_transitions():
    board = db.TeamService().enable("root-1")
    board.join("alice", "id-alice")
    board.join("bob", "id-bob")
    task = board.add_task("t1", "write tests", owner="alice")
    assert task.state is db.TaskState.TODO
    with pytest.raises(db.TeamError, match="reserved"):
        board.claim("t1", "bob")
    claimed = board.claim("t1", "alice")
    assert claimed.state is db.TaskState.IN_PROGRESS
    with pytest.raises(db.TeamError, match="only the owner"):
        board.complete("t1", "bob")
    done = board.complete("t1", "alice")
    assert done.state is db.TaskState.DONE
    assert board.describe()["tasks"][0]["state"] == "done"
    with pytest.raises(db.TeamError, match="duplicate"):
        board.add_task("t1", "again")
    with pytest.raises(db.TeamError, match="already"):
        board.claim("t1", "alice")
    with pytest.raises(db.TeamError, match="not a member"):
        board.add_task("t2", "x", owner="nobody")
    with pytest.raises(db.TeamError, match="unknown task"):
        board.claim("missing", "alice")
    with pytest.raises(db.TeamError, match="duplicate team member"):
        board.join("alice", "other-id")


def test_team_messaging_discovery_inbox_and_interruption():
    board = db.TeamService().enable("root-1")
    board.join("alice", "id-alice", role="lead")
    board.join("bob", "id-bob")
    assert [m.name for m in board.discover("alice")] == ["bob"]
    board.send("alice", "bob", "please review", db.MessageKind.TASK)
    board.send("alice", db.BROADCAST, "standing by")
    inbox = board.inbox("bob")
    assert [m.seq for m in inbox] == [1, 2]
    assert board.inbox("alice") == ()           # own messages are not inbox items
    wait = board.wait_descriptor("bob", timeout_s=5)
    assert wait["pending"] == 2 and wait["blocking"] is False
    assert wait["io_performed"] is False
    with pytest.raises(db.TeamError, match="positive"):
        board.wait_descriptor("bob", timeout_s=0)
    assert board.is_interrupted("bob") is False
    notice = board.interrupt("alice", "bob")
    assert notice.kind is db.MessageKind.INTERRUPT
    assert board.is_interrupted("bob") is True
    board.clear_interrupt("bob")
    assert board.is_interrupted("bob") is False
    with pytest.raises(db.TeamError, match="not a member"):
        board.send("alice", "carol", "hello")


# ---------------------------------------------------------------------------
# D3.5 — agent presets and isolate realms
# ---------------------------------------------------------------------------
def test_preset_isolate_rows_get_session_scoped_instances():
    service = db.PresetService()
    service.register(db.AgentPreset("reviewer", (
        db.ServiceRow("filesystem"),
        db.ServiceRow("memory", db.Realm.ISOLATE),
    )))
    first = service.resolve("reviewer", "session-1")
    second = service.resolve("reviewer", "session-2")
    assert first.capabilities == ("filesystem", "memory")
    assert first.instances[0][1] == second.instances[0][1] == "shared/filesystem"
    assert first.instances[1][1] == "reviewer/session-1/memory"
    assert second.instances[1][1] == "reviewer/session-2/memory"
    assert first.instances[1][1] != second.instances[1][1]
    assert first.scope == "one_session" and first.io_performed is False
    assert first.describe()["instances"][1][2] == "isolate"


def test_preset_validation_rejects_empty_duplicate_and_unknown():
    with pytest.raises(db.PresetError, match="at least one"):
        db.AgentPreset("empty", ())
    with pytest.raises(db.PresetError, match="duplicate service rows"):
        db.AgentPreset("dupe", (db.ServiceRow("a"), db.ServiceRow("a")))
    service = db.PresetService()
    with pytest.raises(db.PresetError, match="requires an AgentPreset"):
        service.register("preset")
    service.register(db.AgentPreset("p", (db.ServiceRow("a"),)))
    with pytest.raises(db.PresetError, match="duplicate agent preset"):
        service.register(db.AgentPreset("p", (db.ServiceRow("b"),)))
    with pytest.raises(db.PresetError, match="unknown agent preset"):
        service.resolve("missing", "s")
    with pytest.raises(db.D3BackendError, match="Realm"):
        db.ServiceRow("a", "bogus-realm")


# ---------------------------------------------------------------------------
# D3.10 — fs/* events on top of providers
# ---------------------------------------------------------------------------
def test_fs_policy_listeners_run_tier2_first_and_can_veto():
    bus = db.FsEventBus()
    bus.register("default", 1, (db.FsEvent.BEFORE_WRITE,), lambda req: None)
    bus.register("policy", 2, ("fs/before_write",), lambda req: "veto")
    verdict = bus.dispatch(db.FsRequest(db.FsEvent.BEFORE_WRITE, "secrets.env"))
    assert verdict.allowed is False
    assert verdict.chain == ("policy",)     # tier 2 ran first and short-circuited
    assert verdict.veto_source == "policy"
    assert verdict.reasons == ("policy",)
    assert verdict.describe()["io_performed"] is False
    # When nobody vetoes, the full waterfall order is visible: tier 2, then 1.
    ordered = db.FsEventBus()
    ordered.register("default", 1, (db.FsEvent.BEFORE_WRITE,), lambda req: None)
    ordered.register("policy", 2, (db.FsEvent.BEFORE_WRITE,), lambda req: None)
    allowed = ordered.dispatch(db.FsRequest(db.FsEvent.BEFORE_WRITE, "out.txt"))
    assert allowed.allowed is True and allowed.chain == ("policy", "default")
    # A listener not subscribed to the event is never invoked.
    clean = bus.dispatch(db.FsRequest(db.FsEvent.BEFORE_READ, "notes.md"))
    assert clean.allowed is True and clean.chain == ()


def test_fs_event_bus_validation_and_allow_path():
    bus = db.FsEventBus()
    bus.register("allow", 2, (db.FsEvent.AFTER_WRITE,), lambda req: "allow")
    verdict = bus.dispatch(db.FsRequest("fs/after_write", "out.txt"))
    assert verdict.allowed is True and verdict.veto_source is None
    with pytest.raises(db.FsPolicyError, match="tier must be"):
        bus.register("bad", 3, (db.FsEvent.BEFORE_READ,), lambda req: None)
    with pytest.raises(db.FsPolicyError, match="duplicate"):
        bus.register("allow", 1, (db.FsEvent.BEFORE_READ,), lambda req: None)
    with pytest.raises(db.FsPolicyError, match="callable"):
        bus.register("bad", 1, (db.FsEvent.BEFORE_READ,), "veto")
    with pytest.raises(db.FsPolicyError, match="at least one"):
        bus.register("bad", 1, (), lambda req: None)
    bus.register("bad", 1, (db.FsEvent.BEFORE_READ,), lambda req: "ban")
    with pytest.raises(db.FsPolicyError, match="invalid decision"):
        bus.dispatch(db.FsRequest(db.FsEvent.BEFORE_READ, "x"))
    with pytest.raises(db.FsPolicyError, match="requires an FsRequest"):
        bus.dispatch("not a request")


# ---------------------------------------------------------------------------
# D3.12 — deliverables
# ---------------------------------------------------------------------------
def test_deliverables_attach_per_turn_and_render_result_cards():
    service = db.DeliverableService()
    service.attach("turn-1", "report.md", "file", path="out/report.md",
                   content="# report")
    service.attach("turn-1", "summary", db.DeliverableKind.SUMMARY,
                   detail="two files changed")
    service.attach("turn-2", "other", "file", content=b"binary")
    names = [d.name for d in service.for_turn("turn-1")]
    assert names == ["report.md", "summary"]
    card = service.card("turn-1", "report.md")
    assert card["open_action"] == "out/report.md"
    assert card["export_action"] == "export:report.md"
    assert card["frontend_rendered"] is False
    assert service.for_turn("turn-1")[0].sha256 == hashlib.sha256(
        b"# report").hexdigest()
    assert service.describe()["deliverable_count"] == 3
    assert service.describe()["turns"] == ["turn-1", "turn-2"]


def test_deliverable_validation():
    service = db.DeliverableService()
    with pytest.raises(db.DeliverableError, match="path or content"):
        service.attach("t", "f", "file")
    with pytest.raises(db.DeliverableError, match="detail or content"):
        service.attach("t", "s", "summary")
    service.attach("t", "f", "file", path="x")
    with pytest.raises(db.DeliverableError, match="duplicate"):
        service.attach("t", "f", "summary", detail="x")
    with pytest.raises(db.DeliverableError, match="unknown deliverable"):
        service.card("t", "missing")
    with pytest.raises(db.D3BackendError, match="deliverable name"):
        service.attach("t", "  ", "file", path="x")


# ---------------------------------------------------------------------------
# D3.15 — extensions never auto-install
# ---------------------------------------------------------------------------
def test_extensions_require_explicit_owner_approval():
    service = db.ExtensionService()
    proposal = service.propose("p1", "skill", "skills/review.md", "---\nname: review")
    assert proposal.state is db.ProposalState.PROPOSED
    assert proposal.describe()["auto_installed"] is False
    with pytest.raises(db.ExtensionError, match="never auto-install"):
        service.application("p1")
    approved = service.approve("p1", "owner")
    assert approved.state is db.ProposalState.APPROVED
    application = service.application("p1")
    assert application["performed"] is False and application["writes"] is False
    assert application["requires_explicit_approval"] is True
    with pytest.raises(db.ExtensionError, match="already resolved"):
        service.approve("p1", "owner")
    service.propose("p2", "command", "/undo", "diff")
    with pytest.raises(db.D3BackendError, match="approver"):
        service.approve("p2", "   ")


def test_extension_reject_and_proposal_digests():
    first = db.ExtensionService()
    second = db.ExtensionService()
    a = first.propose("a", "agent", "agents/reviewer.md", "new content")
    b = second.propose("b", "command", "commands/x.md", "new content")
    c = second.propose("c", "command", "commands/x.md", "other content")
    assert a.diff_sha256 == b.diff_sha256
    assert a.diff_sha256 != c.diff_sha256
    rejected = first.reject("a", "owner", "not now")
    assert rejected.state is db.ProposalState.REJECTED
    assert rejected.reason == "not now"
    with pytest.raises(db.ExtensionError, match="never auto-install"):
        first.application("a")
    with pytest.raises(db.ExtensionError, match="duplicate"):
        first.propose("a", "skill", "x", "diff")
    with pytest.raises(db.ExtensionError, match="unknown"):
        first.application("missing")
    assert first.describe()["writes"] is False


# ---------------------------------------------------------------------------
# D3.16 — feedback
# ---------------------------------------------------------------------------
def test_feedback_records_summaries_and_stays_local():
    service = db.FeedbackService()
    service.record("m1", "up", "helpful")
    service.record("m1", db.Sentiment.DOWN, "too slow")
    service.record("m2", "up")
    assert [r.seq for r in service.for_message("m1")] == [1, 2]
    summary = service.summary()
    assert (summary["total"], summary["up"], summary["down"]) == (3, 2, 1)
    assert summary["transmitted"] is False
    assert summary["eval_feed"] == "local_eval_only"
    assert summary["storage"] == "local"
    assert service.describe()["io_performed"] is False
    with pytest.raises(db.D3BackendError, match="Sentiment"):
        service.record("m3", "sideways")
    with pytest.raises(db.FeedbackError, match="2000"):
        service.record("m3", "up", "x" * 2001)


# ---------------------------------------------------------------------------
# D3.17 — anonymous identity
# ---------------------------------------------------------------------------
def test_install_identity_is_local_deterministic_and_never_transmitted():
    first = db.identity_from_seed("machine-secret")
    second = db.identity_from_seed("machine-secret")
    assert first == second
    assert first.install_id == db.derive_install_id("machine-secret")
    assert first.install_id.startswith("local-")
    assert first.telemetry is False and first.transmitted is False
    assert first.describe()["purpose"] == "local_keys_only"
    assert "install_id" not in first.public_view()
    with pytest.raises(db.IdentityError, match="never sent"):
        first.export_for_transmission()
    assert db.identity_from_seed("other").install_id != first.install_id
    a, b = db.generate_identity(), db.generate_identity()
    assert a.install_id != b.install_id
    assert a.source == "generated"


def test_identity_rejects_transmission_flags_and_bad_ids():
    with pytest.raises(db.IdentityError, match="never be transmitted"):
        db.InstallIdentity("local-abc", "generated", transmitted=True)
    with pytest.raises(db.IdentityError, match="never be transmitted"):
        db.InstallIdentity("local-abc", "generated", telemetry=True)
    with pytest.raises(db.IdentityError, match="local- namespace"):
        db.InstallIdentity("telemetry-id", "generated")
    with pytest.raises(db.IdentityError, match="unknown identity source"):
        db.InstallIdentity("local-abc", "cloud")
    with pytest.raises(db.IdentityError, match="must not be empty"):
        db.derive_install_id("")


# ---------------------------------------------------------------------------
# D3.19 — plan log and schedule
# ---------------------------------------------------------------------------
def test_plan_log_replay_rebuilds_the_checklist():
    log = db.PlanLog()
    log.append("plan/add", "step1", "gather evidence")
    log.append(db.PlanEventKind.ADD, "step2", "write tests")
    log.append(db.PlanEventKind.DONE, "step1")
    log.append(db.PlanEventKind.NOTE, "step2", "blocked on review")
    replayed = db.PlanLog.replay(log.events())
    assert replayed.events() == log.events()
    assert replayed.checklist() == log.checklist()
    assert [(s.id, s.done) for s in replayed.checklist()] == [
        ("step1", True), ("step2", False)]
    assert replayed.describe()["replayable"] is True


def test_plan_log_rejects_invalid_events_and_replay():
    log = db.PlanLog()
    with pytest.raises(db.PlanError, match="step text"):
        log.append("plan/add", "s1")
    with pytest.raises(db.PlanError, match="unknown plan step"):
        log.append("plan/done", "s1")
    log.append("plan/add", "s1", "first")
    with pytest.raises(db.PlanError, match="duplicate plan step"):
        log.append("plan/add", "s1", "again")
    with pytest.raises(db.PlanError, match="needs text"):
        log.append("plan/note", "s1")
    with pytest.raises(db.PlanError, match="contiguous"):
        db.PlanLog.replay([db.PlanEvent(2, db.PlanEventKind.ADD, "s1", "text")])
    with pytest.raises(db.PlanError, match="requires contiguous, typed"):
        db.PlanLog.replay(["not an event"])


def test_schedule_follow_up_due_fire_and_pending():
    service = db.ScheduleService()
    now = datetime(2026, 1, 1, 0, 0)
    item = service.schedule("f1", "follow up on review", hours=2, now=now)
    assert item.due_at == "2026-01-01T02:00:00"
    assert item.created_at == "2026-01-01T00:00:00"
    assert service.is_due("f1", now) is False
    assert len(service.pending(now)) == 1
    with pytest.raises(db.ScheduleError, match="not due yet"):
        service.fire("f1", now)
    assert service.is_due("f1", "2026-01-01T02:00:00") is True
    assert service.pending("2026-01-01T03:00:00") == ()
    fired = service.fire("f1", "2026-01-01T03:00:00")
    assert fired.fired is True
    assert service.describe()["follow_ups"][0]["fired"] is True
    assert service.describe()["timer"] is False
    with pytest.raises(db.ScheduleError, match="already fired"):
        service.fire("f1", "2026-01-01T04:00:00")


def test_schedule_validation():
    service = db.ScheduleService()
    now = datetime(2026, 1, 1)
    with pytest.raises(db.ScheduleError, match="positive"):
        service.schedule("x", "bad", hours=0, now=now)
    service.schedule("x", "ok", hours=1, now=now)
    with pytest.raises(db.ScheduleError, match="duplicate"):
        service.schedule("x", "again", hours=1, now=now)
    with pytest.raises(db.ScheduleError, match="unknown"):
        service.is_due("missing", now)
    with pytest.raises(db.ScheduleError, match="invalid datetime"):
        service.is_due("x", "yesterday")


# ---------------------------------------------------------------------------
# D3.20 — experimental/ quarantine
# ---------------------------------------------------------------------------
def test_quarantine_layout_accepts_documented_packages():
    policy = db.ProductPackagePolicy((
        db.PackageEntry("liveshare", True),
        db.PackageEntry("workspace", False, product_use="workspace UI"),
        db.PackageEntry("imports", False, classification="infrastructure"),
    ))
    report = policy.check_layout((
        "keel/experimental/liveshare/codec.py",
        "src/keel/workspace/service.py",
        "src/keel/imports/__init__.py",
    ))
    assert report["clean"] is True and report["violations"] == []
    assert report["flags"] == ["X6.10"]
    assert report["writes"] is False
    assert policy.classify("liveshare").experimental is True
    assert policy.describe()["namespace"] == "keel/experimental"


def test_quarantine_rejects_misplaced_and_unclassified_packages():
    policy = db.ProductPackagePolicy((
        db.PackageEntry("liveshare", True),
        db.PackageEntry("workspace", False, product_use="workspace UI"),
    ))
    report = policy.check_layout((
        "src/liveshare/carrier.py",              # experimental outside quarantine
        "keel/experimental/workspace/x.py",      # product package in quarantine
        "keel/experimental/",                    # no package segment
        "keel/experimental/unknown/x.py",        # no policy entry
    ))
    assert report["clean"] is False
    assert len(report["violations"]) == 4
    with pytest.raises(db.QuarantineError, match="product use"):
        policy.add(db.PackageEntry("nope", False))
    with pytest.raises(db.QuarantineError, match="invalid package name"):
        policy.add(db.PackageEntry("../escape", True))
    with pytest.raises(db.QuarantineError, match="duplicate policy entry"):
        policy.add(db.PackageEntry("liveshare", True))
    with pytest.raises(db.QuarantineError, match="no policy entry"):
        policy.classify("unknown")


# ---------------------------------------------------------------------------
# D3.21 — generated provider metadata staleness check
# ---------------------------------------------------------------------------
def test_metadata_check_rejects_stale_data_without_writing():
    sources = {"catalog.py": "PROVIDERS = ['openai']\n"}
    metadata = {"openai": db.generate_metadata("openai", "1", sources)}
    report = db.check_metadata(metadata, {"openai": sources})
    assert report["fresh"] is True and report["reject_stale"] is True
    assert report["writes"] is False and report["rewrites"] is False
    assert db.assert_metadata_fresh(metadata, {"openai": sources})["fresh"] is True

    changed = {"catalog.py": "PROVIDERS = ['openai', 'anthropic']\n"}
    stale = db.check_metadata(metadata, {"openai": changed})
    assert stale["fresh"] is False
    assert stale["providers"][0]["reason"] == "digest_mismatch"
    assert stale["writes"] is False
    with pytest.raises(db.MetadataError, match="stale generated"):
        db.assert_metadata_fresh(metadata, {"openai": changed})
    missing = db.check_metadata({}, {"openai": sources})
    assert missing["providers"][0]["reason"] == "missing_metadata"
    extra = db.check_metadata(metadata, {})
    assert extra["providers"][0]["reason"] == "no_source_inputs"


def test_canonical_digest_is_order_independent_and_unambiguous():
    one = {"b.py": "B", "a.py": "A"}
    two = {"a.py": "A", "b.py": "B"}
    assert db.canonical_digest(one) == db.canonical_digest(two)
    assert db.canonical_digest(one) != db.canonical_digest({"a.py": "A", "b.py": "C"})
    assert db.canonical_digest({"ab": "c"}) != db.canonical_digest({"a": "bc"})


# ---------------------------------------------------------------------------
# D3.22 — inspector seam (backend only)
# ---------------------------------------------------------------------------
def test_inspector_build_is_pinned_offline_and_published():
    spec = db.InspectorBuildSpec(db.PinnedSource("inspector-ui", "1.2.3", "a" * 64))
    plan = db.inspector_build_plan(spec)
    assert [step["step"] for step in plan["steps"]] == [
        "verify_pin", "compile_local", "package_asset"]
    assert all(step["network"] is False for step in plan["steps"])
    assert plan["network"] is False and plan["browser_download"] is False
    assert plan["backend_only"] is True
    assert plan["published_contains_built_frontend"] is True
    assert spec.describe()["frontend_rendered"] is False


def test_inspector_rejects_unpinned_or_network_dependencies():
    with pytest.raises(db.InspectorError, match="sha256"):
        db.PinnedSource("inspector-ui", "1.0", "not-a-digest")
    source = db.PinnedSource("inspector-ui", "1.0", "a" * 64)
    with pytest.raises(db.InspectorError, match="offline"):
        db.InspectorBuildSpec(source, offline=False)
    with pytest.raises(db.InspectorError, match="offline"):
        db.InspectorBuildSpec(source, browser_download=True)
    dirty = db.check_offline_build({
        "build.sh": "curl https://example.test/inspector.tgz\n",
        "fetch.js": "fetch('https://example.test/asset')",
        "clean.sh": "python -m compileall src\n",
    })
    assert dirty["violations"] == ["build.sh", "fetch.js"]
    assert dirty["clean"] is False and dirty["network"] is False
    assert db.check_offline_build({"clean.sh": "npm run build --offline"})["clean"] is True
    with pytest.raises(db.InspectorError, match="InspectorBuildSpec"):
        db.inspector_build_plan("not a spec")


# ---------------------------------------------------------------------------
# D3.23 — Live Share wire codecs (no browser carrier, no cloud relay)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", db.WIRE_KINDS)
def test_wire_frames_round_trip_for_every_kind(kind):
    codec = db.WireCodec()
    frame = codec.encode(kind, {"seq": 7, "text": "héllo"})
    decoded = codec.decode(frame)
    assert decoded["v"] == db.WIRE_VERSION
    assert decoded["kind"] == kind
    assert decoded["payload"] == {"seq": 7, "text": "héllo"}
    assert frame.startswith(db.WIRE_MAGIC)
    with pytest.raises(db.WireError, match="unknown wire kind"):
        codec.encode("bogus", {})


def _frame(body: bytes) -> bytes:
    return (db.WIRE_MAGIC + len(body).to_bytes(4, "big") + body
            + hashlib.sha256(body).digest()[:8])


def test_wire_codec_rejects_corrupt_frames():
    with pytest.raises(db.WireError, match="bytes"):
        db.decode_message("not bytes")
    with pytest.raises(db.WireError, match="truncated"):
        db.decode_message(b"short")
    with pytest.raises(db.WireError, match="magic"):
        db.decode_message(b"NOPE!" + db.encode_message("hello", {"a": 1})[5:])
    good = db.encode_message("hello", {"a": 1})
    with pytest.raises(db.WireError, match="length mismatch"):
        db.decode_message(good + b"x")
    flipped = bytearray(good)
    flipped[-1] ^= 0xFF
    with pytest.raises(db.WireError, match="checksum"):
        db.decode_message(bytes(flipped))
    with pytest.raises(db.WireError, match="valid JSON"):
        db.decode_message(_frame(b"not json"))
    with pytest.raises(db.WireError, match="unsupported wire version"):
        db.decode_message(_frame(b'{"v": 99, "kind": "hello", "payload": {}}'))
    with pytest.raises(db.WireError, match="unknown wire kind"):
        db.decode_message(_frame(b'{"v": 1, "kind": "bogus", "payload": {}}'))


def test_wire_descriptor_has_no_frontend_or_relay():
    descriptor = db.WireCodec().describe()
    assert descriptor["read_only"] is True
    assert descriptor["lan_only"] is True
    assert descriptor["cloud_relay"] is False
    assert descriptor["browser_carrier_implemented"] is False
    assert descriptor["network"] is False and descriptor["io_performed"] is False
