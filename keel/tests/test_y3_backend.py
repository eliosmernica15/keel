"""Permanent contract-regression specs for the remaining Y3.* backend features.

One or more tests per not_started Y3 registry ID (14 features):
Y3.1, Y3.3, Y3.5, Y3.7, Y3.8, Y3.12, Y3.14, Y3.15, Y3.16, Y3.17,
Y3.18, Y3.19, Y3.20, Y3.21.  A final section verifies that the seven Y3 P0
rows already implemented in ``keel.config_contracts`` are still present.

These specs are additive: they import only ``keel.y3_backend`` (plus
``keel.config_contracts`` for the P0 verification) and touch neither the live
web app, CLI, settings store, filesystem nor any network socket.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the module under test from *this worktree's* src tree.  In environments
# where `keel` is installed from a different checkout, `keel.__path__` does not
# contain the new module, so fall back to a direct file load.
_SRC = Path(__file__).resolve().parents[1] / "src"
_Y3_PATH = _SRC / "keel" / "y3_backend.py"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _load_module(name: str, path: Path):
    try:
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() == path.resolve():
            return module
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


y3 = _load_module("keel.y3_backend", _Y3_PATH)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clock_factory():
    state = {"now": 1_700_000_000.0}

    def clock():
        return state["now"]

    return clock, state


# ---------------------------------------------------------------------------
# Y3.1 -- "offer only what works"
# ---------------------------------------------------------------------------


def test_y3_1_available_and_hidden_options():
    ok = y3.FeatureOption(
        "local_model", "Local model",
        (y3.Requirement("model_installed", True),))
    hidden = y3.FeatureOption(
        "gpu_only", "GPU feature",
        (y3.Requirement("gpu", False, "a CUDA GPU is not installed"),
         y3.Requirement("driver", False, "GPU driver v550+ is required")),
        explain_when_unavailable=False)

    assert y3.evaluate_availability(ok).state is y3.OptionState.AVAILABLE
    hidden_result = y3.evaluate_availability(hidden)
    assert hidden_result.state is y3.OptionState.HIDDEN
    assert hidden_result.missing == ("a CUDA GPU is not installed",
                                     "GPU driver v550+ is required")
    assert tuple(a.option_key for a in y3.visible_options([ok, hidden])) == (
        "local_model",)


def test_y3_1_unavailable_option_explains_exact_missing_requirement():
    option = y3.FeatureOption(
        "cloud_sync", "Cloud sync",
        (y3.Requirement("account", False, "no account is configured"),))
    availability = y3.evaluate_availability(option)
    assert availability.state is y3.OptionState.EXPLAIN
    assert availability.missing == ("no account is configured",)
    assert availability.to_dict()["state"] == "explain"


def test_y3_1_rejects_dead_options_and_reasonless_requirements():
    with pytest.raises(y3.AvailabilityError):
        y3.Requirement("x", False)  # unsatisfied without a missing detail
    with pytest.raises(y3.AvailabilityError):
        y3.assert_no_dead_options([
            y3.Availability("broken", y3.OptionState.AVAILABLE, ("needs X",))])
    with pytest.raises(y3.AvailabilityError):
        y3.assert_no_dead_options([
            y3.Availability("broken", y3.OptionState.EXPLAIN)])
    y3.assert_no_dead_options([
        y3.evaluate_availability(y3.FeatureOption("ok", "OK")),
        y3.evaluate_availability(y3.FeatureOption(
            "no", "No", (y3.Requirement("r", False, "needs r"),))),
    ])


# ---------------------------------------------------------------------------
# Y3.3 -- versioned, idempotent, resumable provisioning steps
# ---------------------------------------------------------------------------


def _registry():
    return y3.ProvisioningRegistry([
        y3.SetupStep("create_dirs", 1, "create directories"),
        y3.SetupStep("probe_models", 2, "probe local models"),
        y3.SetupStep("register_tools", 1, "register built-in tools"),
    ])


def test_y3_3_version_bump_reruns_only_that_step():
    registry = _registry()
    done = {"create_dirs": 1, "probe_models": 1, "register_tools": 1}
    runner = y3.InMemoryStepRunner()
    report = y3.run_provisioning(registry, done, runner)
    assert report.planned == ("probe_models@2",)
    assert report.completed == ("probe_models@2",)
    assert report.remaining == ()
    assert runner.attempts == ("probe_models@2",)
    assert report.new_completed["probe_models"] == 2


def test_y3_3_resumable_after_failure_and_idempotent_on_next_launch():
    registry = _registry()
    fail = y3.InMemoryStepRunner(fail_keys={"probe_models"})
    first = y3.run_provisioning(registry, {}, fail)
    assert "probe_models@2" in first.failed
    assert first.remaining == ("probe_models@2",)

    retry = y3.InMemoryStepRunner()
    second = y3.run_provisioning(registry, first.new_completed, retry)
    assert second.planned == ("probe_models@2",)
    assert second.remaining == ()
    assert second.new_completed == {"create_dirs": 1, "probe_models": 2,
                                    "register_tools": 1}

    third = y3.run_provisioning(registry, second.new_completed,
                                y3.InMemoryStepRunner())
    assert third.planned == ()  # idempotent: no work on the next launch


def test_y3_3_rejects_invalid_steps_and_duplicate_keys():
    with pytest.raises(y3.ProvisioningError):
        y3.SetupStep("Bad-Key", 1, "x")
    with pytest.raises(y3.ProvisioningError):
        y3.SetupStep("good", 0, "x")
    with pytest.raises(y3.ProvisioningError):
        y3.ProvisioningRegistry([y3.SetupStep("same", 1, "a"),
                                 y3.SetupStep("same", 2, "b")])


# ---------------------------------------------------------------------------
# Y3.5 -- per-user concurrency limit and queue
# ---------------------------------------------------------------------------


def test_y3_5_concurrency_sized_from_ram_and_vram():
    assert y3.concurrency_limit(y3.HardwareProfile(ram_gb=2)) == 1
    # (RAM - reserved)//6 + VRAM//6, with a floor of one slot.
    assert y3.concurrency_limit(y3.HardwareProfile(ram_gb=16, vram_gb=8)) == 3
    assert y3.concurrency_limit(y3.HardwareProfile(ram_gb=64, vram_gb=24)) == 14


def test_y3_5_extra_tasks_queue_and_auto_start():
    queue = y3.PerUserQueue(2)
    for key in ("a", "b", "c", "d"):
        queue.submit(y3.Task(key))
    assert queue.state().running == ("a", "b")
    assert queue.state().pending == ("c", "d")
    queue.finish("a")
    assert queue.state().running == ("b", "c")
    assert queue.state().pending == ("d",)
    queue.cancel("d")
    assert queue.state().pending == ()
    with pytest.raises(y3.ConcurrencyError):
        queue.finish("not-running")


def test_y3_5_per_user_queues_are_isolated():
    manager = y3.ConcurrencyManager(y3.HardwareProfile(ram_gb=14),
                                    overrides={"alice": 1, "bob": 2})
    manager.submit("alice", y3.Task("a1"))
    manager.submit("alice", y3.Task("a2"))
    manager.submit("bob", y3.Task("b1"))
    manager.submit("bob", y3.Task("b2"))
    assert manager.state("alice") == y3.QueueState(1, ("a1",), ("a2",))
    assert manager.state("bob") == y3.QueueState(2, ("b1", "b2"), ())
    with pytest.raises(y3.ConcurrencyError):
        manager.submit("", y3.Task("x"))


# ---------------------------------------------------------------------------
# Y3.7 -- scheduler tick duties
# ---------------------------------------------------------------------------


def _work():
    return y3.DueWork(
        automations=("auto-1",), triggers=("trig-1",),
        webhooks=("wh-1",), task_costs=("run-1",),
        idle_folders=("tmp-1",), alerts=("alert-1",))


def test_y3_7_tick_runs_all_seven_duties_with_idempotency_keys():
    report = y3.tick(_work(), now="2026-01-01T00:00:00Z")
    assert tuple(o.job for o in report.outcomes) == y3.TICK_JOBS
    assert report.for_job(y3.TickJob.FIRE_AUTOMATIONS).processed == ("auto-1",)
    assert report.for_job(y3.TickJob.HEARTBEAT).processed == ("heartbeat",)
    assert report.for_job(y3.TickJob.CHECK_ALERTS).processed == ("alert-1",)
    keys = [o.idempotency_key for o in report.outcomes]
    assert len(keys) == 7 and len(set(keys)) == 7
    assert all(len(k) == 16 for k in keys)


def test_y3_7_repeated_tick_deduplicates_and_guard_blocks_overlap():
    ledger = y3.IdempotencyLedger()
    stamp = "2026-01-01T00:00:00Z"
    first = y3.tick(_work(), now=stamp, ledger=ledger)
    second = y3.tick(_work(), now=stamp, ledger=ledger)
    assert all(o.deduplicated for o in second.outcomes)
    assert all(o.processed == () for o in second.outcomes)
    assert [o.idempotency_key for o in first.outcomes] == [
        o.idempotency_key for o in second.outcomes]

    guard = y3.TickGuard()
    guard.acquire()
    with pytest.raises(y3.SchedulerError):
        y3.tick(_work(), now=stamp, guard=guard)
    guard.release()
    assert y3.tick(_work(), now=stamp, guard=guard).outcomes


def test_y3_7_tick_requires_now():
    with pytest.raises(y3.SchedulerError):
        y3.tick(_work(), now="")


# ---------------------------------------------------------------------------
# Y3.8 -- device-approval pairing flow
# ---------------------------------------------------------------------------


def test_y3_8_pairing_lifecycle_and_short_code():
    clock, state = _clock_factory()
    broker = y3.PairingBroker(clock)
    session = broker.create("phone-nonce")
    assert len(session.code) == 6
    assert session.state is y3.PairingState.PENDING
    assert broker.poll(session.code).state is y3.PairingState.PENDING
    approved = broker.approve(session.code, "admin-client")
    assert approved.state is y3.PairingState.APPROVED
    assert approved.approved_by == "admin-client"
    assert broker.poll(session.code).state is y3.PairingState.APPROVED
    with pytest.raises(y3.PairingError):
        broker.approve(session.code, "admin-client")  # wrong state
    assert session.to_dict()["state"] == "pending"


def test_y3_8_expiry_at_thirty_minutes_and_retry():
    clock, state = _clock_factory()
    broker = y3.PairingBroker(clock)
    session = broker.create("cli-nonce")
    state["now"] += y3.PAIRING_TTL_SECONDS + 1
    assert broker.poll(session.code).state is y3.PairingState.EXPIRED
    retried = broker.retry(session.code, "cli-nonce-2")
    assert retried.code != session.code
    assert retried.state is y3.PairingState.PENDING
    assert retried.attempts == 2


def test_y3_8_cancel_and_deny_states():
    clock, _ = _clock_factory()
    broker = y3.PairingBroker(clock)
    cancelled = broker.cancel(broker.create("n1").code)
    assert cancelled.state is y3.PairingState.CANCELLED
    denied = broker.deny(broker.create("n2").code)
    assert denied.state is y3.PairingState.DENIED
    with pytest.raises(y3.PairingError):
        broker.poll("UNKNOWN")


# ---------------------------------------------------------------------------
# Y3.12 -- invite gate
# ---------------------------------------------------------------------------


def test_y3_12_first_admin_owns_paired_client_list():
    gate = y3.InviteGate(y3.ServeMode.SERVE)
    first = gate.pair("admin-1", "Admin")
    assert first.admin is True
    assert gate.owner == "admin-1"
    with pytest.raises(y3.InviteError):
        gate.pair("intruder", requested_by="someone-else")
    gate.pair("phone-1", "Phone", requested_by="admin-1")
    assert gate.is_allowed("phone-1")
    assert not gate.is_allowed("intruder")
    gate.revoke("phone-1", requested_by="admin-1")
    assert not gate.is_allowed("phone-1")
    with pytest.raises(y3.InviteError):
        gate.revoke("admin-1", requested_by="admin-1")


def test_y3_12_single_client_mode_has_no_gate():
    gate = y3.InviteGate("single")
    assert gate.mode is y3.ServeMode.SINGLE
    gate.pair("only-client")
    assert gate.owner is None
    assert gate.is_allowed("only-client")
    gate.pair("another")  # no approval needed in single mode
    assert gate.is_allowed("another")


# ---------------------------------------------------------------------------
# Y3.14 -- first-run offers existing resources first
# ---------------------------------------------------------------------------


def _candidates():
    return (
        y3.CandidateModel("llama3", "ollama", 8.0, 4.0),
        y3.CandidateModel("tinyllama", "llamacpp", 1.1, 8.0),
    )


def test_y3_14_existing_resources_offered_before_new_downloads():
    probe = y3.StaticModelProbe([
        y3.ModelResource("llama3", "ollama"),
        y3.ModelResource("mistral", "llamacpp"),
    ])
    offers = y3.plan_first_run(_candidates(), probe)
    assert [o.model for o in offers] == ["llama3", "mistral", "tinyllama"]
    assert [o.action for o in offers] == ["reuse", "reuse", "create"]
    y3.assert_reuse_first(offers)
    with pytest.raises(y3.FirstRunError):
        y3.assert_reuse_first(reversed(offers))


def test_y3_14_cost_shown_before_creating_and_enforced():
    probe = y3.StaticModelProbe([])
    offers = y3.plan_first_run(_candidates(), probe)
    assert all(o.action == "create" for o in offers)
    assert all(o.disk_cost_mb > 0 and o.ram_cost_mb > 0 for o in offers)
    assert offers[0].disk_cost_mb > offers[1].disk_cost_mb
    y3.assert_cost_disclosed(offers)
    with pytest.raises(y3.FirstRunError):
        y3.assert_cost_disclosed([
            y3.ResourceOffer("create", "x", "ollama", 0, 0)])
    assert y3.estimate_cost(8.0, 4.0) == (5200, 4800)


# ---------------------------------------------------------------------------
# Y3.15 -- settings structure
# ---------------------------------------------------------------------------


def test_y3_15_required_sections_present_and_keys_resolve():
    ids = y3.validate_settings_tree()
    assert set(ids) == set(y3.REQUIRED_SETTING_SECTIONS)
    assert len(ids) == 9
    assert y3.section_for_key("data_dir") == "data_privacy"
    assert y3.section_for_key("invite_list") == "admin"
    with pytest.raises(y3.SettingsTreeError):
        y3.section_for_key("unknown_key")


def test_y3_15_rejects_duplicate_and_missing_sections():
    with pytest.raises(y3.SettingsTreeError):
        y3.validate_settings_tree([
            y3.SettingSection("general", "General"),
            y3.SettingSection("general", "Duplicate")])
    with pytest.raises(y3.SettingsTreeError):
        y3.validate_settings_tree([y3.SettingSection("general", "General")])


# ---------------------------------------------------------------------------
# Y3.16 -- public API / webhooks / operator page
# ---------------------------------------------------------------------------


def test_y3_16_versioned_public_and_keel_specific_routes():
    public = y3.build_route("public_api", "runs")
    keel = y3.build_route("keel_api", "operator")
    assert public.path == "/api/v1/runs"
    assert keel.path == "/api/keel/v1/operator"
    assert not y3.is_keel_specific(public)
    assert y3.is_keel_specific(keel)
    assert all(y3._VERSIONED_RE.match(r.prefix) for r in y3.API_SURFACES)
    assert any(r.surface == "webhooks" and r.method == "POST"
               for r in y3.API_SURFACES)


def test_y3_16_rejects_unversioned_routes():
    with pytest.raises(y3.RouteError):
        y3.build_route("public_api", "runs", prefix="/api")
    with pytest.raises(y3.RouteError):
        y3.build_route("public_api", "runs", prefix="/runs")
    with pytest.raises(y3.RouteError):
        y3.build_route("public_api", "runs", method="FETCH")


# ---------------------------------------------------------------------------
# Y3.17 -- project update proposals require approval
# ---------------------------------------------------------------------------


def _diff():
    return (y3.DiffLine("serve.py", "-", "old line"),
            y3.DiffLine("serve.py", "+", "new line"))


def test_y3_17_proposals_start_pending_and_require_approval():
    ledger = y3.ProposalLedger()
    proposal = ledger.submit("Fix listener", _diff())
    assert proposal.state is y3.ProposalState.PENDING
    assert ledger.list() == (proposal,)
    seam = y3.RecordingApplySeam()
    with pytest.raises(y3.ProposalError):
        ledger.apply(proposal.id, seam)
    assert seam.applied == []

    ledger.approve(proposal.id, "human-approver")
    assert ledger.apply(proposal.id, seam).startswith("applied:")
    assert ledger.get(proposal.id).state is y3.ProposalState.APPLIED
    assert seam.applied == [proposal.id]


def test_y3_17_reject_and_validation():
    ledger = y3.ProposalLedger()
    rejected = ledger.submit("Reject me", _diff())
    ledger.reject(rejected.id)
    assert rejected.state is y3.ProposalState.PENDING  # frozen original
    assert ledger.get(rejected.id).state is y3.ProposalState.REJECTED
    with pytest.raises(y3.ProposalError):
        ledger.apply(rejected.id, y3.RecordingApplySeam())
    with pytest.raises(y3.ProposalError):
        ledger.submit("no diff", ())
    with pytest.raises(y3.ProposalError):
        ledger.approve(rejected.id, "")
    with pytest.raises(y3.ProposalError):
        y3.DiffLine("x.py", "?", "bad op")


# ---------------------------------------------------------------------------
# Y3.18 -- compute-side files, KEEL_DATA_DIR, local cache eviction
# ---------------------------------------------------------------------------


def test_y3_18_data_dir_env_override_default():
    assert y3.resolve_data_dir({}) == ".keel/data"
    assert y3.resolve_data_dir({"KEEL_DATA_DIR": "D:/keel-data"}) == "D:/keel-data"


def test_y3_18_lru_cache_eviction_and_remote_only_references():
    cache = y3.LocalCache(capacity_bytes=10, data_dir="D:/keel-data")
    cache.put("a", "compute://host/a.bin", 4)
    cache.put("b", "relay://host/b.bin", 4)
    assert cache.used_bytes == 8
    cache.get("a")  # 'a' becomes most-recently-used
    cache.put("c", "compute://host/c.bin", 4)
    assert [e.key for e in cache.snapshot()] == ["a", "c"]
    assert cache.evict_one() in ("a", "c")
    with pytest.raises(y3.CacheError):
        cache.put("local", "C:/Users/me/big.bin", 1)
    with pytest.raises(y3.CacheError):
        cache.put("too-big", "compute://host/x.bin", 11)


# ---------------------------------------------------------------------------
# Y3.19 -- brand strings in one place
# ---------------------------------------------------------------------------


def test_y3_19_single_brand_source_and_fork_rename():
    assert y3.brand_string("app_name") == "Keel"
    assert y3.BRAND.logo_asset.endswith("keel-logo.svg")
    with pytest.raises(y3.BrandError):
        y3.brand_string("nonexistent")
    fork = y3.forked_brand("Skiff", "assets/brand/skiff-logo.svg")
    assert fork.product_name == "Skiff"
    assert y3.brand_string("setup_title", fork) == "Set up Skiff"
    assert fork.strings["admin_warning"].startswith("The agent runs as administrator")
    y3.assert_single_brand_source()
    with pytest.raises(y3.BrandError):
        y3.assert_single_brand_source(other_literals=("Welcome to Keel",))


# ---------------------------------------------------------------------------
# Y3.20 -- docs set incl. security-model limits
# ---------------------------------------------------------------------------


def test_y3_20_required_docs_and_security_model_limits():
    assert tuple(d.name for d in y3.DOCS_SET) == y3.REQUIRED_DOCS
    assert y3.validate_docs_set(y3.REQUIRED_DOCS) == tuple(sorted(y3.REQUIRED_DOCS))
    with pytest.raises(y3.DocsError):
        y3.validate_docs_set(["README.md"])

    text = ("Keel cannot protect against prompt injection or malicious content "
            "it reads. The agent runs as administrator, so there are no "
            "sandbox escape guarantees against compromised dependencies or "
            "social engineering.")
    y3.assert_security_model_complete(text)
    with pytest.raises(y3.DocsError):
        y3.assert_security_model_complete("Keel is very secure.")
    with pytest.raises(y3.DocsError):
        y3.assert_security_model_complete("")


# ---------------------------------------------------------------------------
# Y3.21 -- administrator warning
# ---------------------------------------------------------------------------


def test_y3_21_warning_and_permission_preset_explanation():
    y3.assert_admin_warning_present()
    y3.assert_presets_explained()
    assert "can be misled by content it reads" in y3.ADMIN_WARNING
    with pytest.raises(y3.WarningError):
        y3.assert_admin_warning_present([
            y3.FirstRunWarning("other", "Other", "Nothing special here")])

    ledger = y3.AcknowledgementLedger()
    with pytest.raises(y3.WarningError):
        ledger.require_admin_acknowledged()
    ledger.acknowledge("admin-privilege")
    assert ledger.is_acknowledged("admin-privilege")
    ledger.require_admin_acknowledged()


# ---------------------------------------------------------------------------
# Verification of the seven Y3 P0 rows already in keel.config_contracts
# ---------------------------------------------------------------------------


def test_p0_y3_rows_verified_in_config_contracts():
    """Guard against accidental removal of the P0 implementation."""
    cc = _load_module("_y3_p0_config_contracts",
                      _SRC / "keel" / "config_contracts.py")

    expected = {
        "Y3.2": ("ReusePolicy", "ServerOnlyDbPolicy", "evaluate_reuse",
                 "validate_db_client"),
        "Y3.4": ("RunEventEnvelope", "EventAuditGuarantee", "EventLedger",
                 "check_event_completeness"),
        "Y3.6": ("Column", "TableDescriptor", "SCHEMA_ADDITIONS",
                 "validate_schema"),
        "Y3.9": ("RevocationScope", "TokenRevocationDescriptor",
                 "build_revocation", "RevocationLedger"),
        "Y3.10": ("LocalSignInDescriptor", "validate_offline_guarantee",
                  "validate_signin_policy"),
        "Y3.11": ("MockAgentDescriptor", "MockAgent", "assert_never_real_provider"),
        "Y3.13": ("GeneratedFile", "GenerationPlan", "apply_plan", "setup_once"),
    }
    for feature_id, symbols in expected.items():
        for symbol in symbols:
            assert hasattr(cc, symbol), f"{feature_id}: missing {symbol}"
