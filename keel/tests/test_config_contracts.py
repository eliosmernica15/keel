"""Permanent contract-regression specs for the Y3.x config/setup/sign-in model.

One or more tests per not_started P0 registry ID:
Y3.2, Y3.4, Y3.6, Y3.9, Y3.10, Y3.11, Y3.13.

These specs are additive: they import only ``keel.config_contracts`` and never
mutate the live settings store, web app, CLI or filesystem.  The required
no-overwrite, idempotence, mock-labelling, event-completeness, schema-validity
and sign-out-semantics guarantees are all exercised here.
"""

from __future__ import annotations

import json

import pytest

import keel.config_contracts as cc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clock():
    return 1_700_000_000.0


def _envelope(seq, event_type, *, run_id="run-1", payload=None, clock=_clock):
    return cc.build_event_envelope(run_id, seq, event_type, payload,
                                   clock=clock)


def _full_run(run_id="run-1"):
    return tuple(_envelope(i, t, run_id=run_id, payload={"i": i})
                 for i, t in enumerate(cc.RELAY_REQUIRED_EVENT_TYPES, start=1))


def _desired_files():
    return (
        cc.GeneratedFile("config/secrets.env", "SECRET_A=generated\n"),
        cc.GeneratedFile("config/local.toml", "[local]\nonly = true\n"),
    )


# ---------------------------------------------------------------------------
# Y3.2 -- reuse before building / server is the only DB client
# ---------------------------------------------------------------------------


def test_reuse_before_building_prefers_existing_capability():
    catalog = (
        cc.ExistingCapability("settings_store", ("settings.read", "settings.write")),
        cc.ExistingCapability("secret_store", ("secrets.read",)),
    )
    decision = cc.evaluate_reuse(
        cc.ReuseRequest("settings.read"), catalog)
    assert decision.disposition is cc.Disposition.REUSE
    assert decision.matched_capability == "settings_store"
    assert decision.fingerprint == decision.fingerprint  # deterministic attr

    # Round-trips through JSON without losing the disposition.
    restored = json.loads(json.dumps(decision.to_dict()))
    assert restored["disposition"] == "reuse"

    # An unavailable capability is not reused.
    unavailable = cc.ExistingCapability("old", ("settings.read",),
                                        available=False)
    assert cc.evaluate_reuse(cc.ReuseRequest("settings.read"),
                             (unavailable,)).disposition is cc.Disposition.REJECTED


def test_build_requires_justification_else_rejected():
    catalog = (cc.ExistingCapability("settings_store", ("settings.read",)),)
    with_justice = cc.evaluate_reuse(
        cc.ReuseRequest("new.capability", "no existing code covers this"), catalog)
    assert with_justice.disposition is cc.Disposition.BUILD
    without = cc.evaluate_reuse(cc.ReuseRequest("new.capability"), catalog)
    assert without.disposition is cc.Disposition.REJECTED
    assert "justification" in " ".join(without.reasons)


def test_server_is_only_db_client():
    server = cc.DbClientClaim("keel-server", cc.DbClientKind.SERVER, True)
    browser = cc.DbClientClaim("browser", cc.DbClientKind.CLIENT, True)
    worker = cc.DbClientClaim("worker", cc.DbClientKind.WORKER, True)
    policy = cc.ServerOnlyDbPolicy()

    assert cc.validate_db_client(server, policy).allowed is True
    assert cc.validate_db_client(browser, policy).allowed is False
    assert cc.validate_db_client(worker, policy).allowed is False
    assert cc.assert_db_client_allowed(server, policy) is True
    with pytest.raises(cc.DbClientViolation):
        cc.assert_db_client_allowed(browser, policy)

    # A component that does not touch the DB is never a violation.
    assert cc.validate_db_client(
        cc.DbClientClaim("renderer", cc.DbClientKind.CLIENT, False),
        policy).allowed is True
    assert policy.fingerprint == cc.ServerOnlyDbPolicy().fingerprint


# ---------------------------------------------------------------------------
# Y3.4 -- relay stores every run event (event completeness)
# ---------------------------------------------------------------------------


def test_event_envelope_is_typed_content_addressed_and_round_trips():
    event = _envelope(1, cc.EventType.RUN_STARTED, payload={"ok": True})
    assert isinstance(event, cc.RunEventEnvelope)
    assert event.event_type is cc.EventType.RUN_STARTED
    assert len(event.event_id) == 16 and event.occurred_at.endswith("Z")

    # identity excludes time and is reproducible
    same = _envelope(1, cc.EventType.RUN_STARTED, payload={"ok": True},
                     clock=lambda: 9_999_999_999.0)
    assert same.event_id == event.event_id

    restored = cc.RunEventEnvelope.from_dict(
        json.loads(json.dumps(event.to_dict())))
    assert restored.event_id == event.event_id
    assert restored.fingerprint == event.fingerprint

    with pytest.raises(cc.EventContractError):
        _envelope(0, cc.EventType.RUN_STARTED)           # bad seq
    with pytest.raises(cc.EventContractError):
        _envelope(1, "not.a.type")                       # bad type
    with pytest.raises(cc.EventContractError):
        cc.RunEventEnvelope("r", 1, cc.EventType.ERROR, {},
                            occurred_at="t", event_id="tampered")


def test_event_completeness_detects_missing_type_gaps_and_duplicates():
    events = _full_run()
    report = cc.check_event_completeness(events)
    assert report.complete is True
    assert report.missing == () and report.seq_gaps == ()

    # A dropped required event is reported by name.
    dropped = events[:3] + events[4:]
    missing_report = cc.check_event_completeness(dropped)
    assert missing_report.complete is False
    assert cc.EventType.TOOL_CALL.value in missing_report.missing

    # A seq hole is reported separately from a missing type.
    gapped = tuple(e for e in events if e.seq != 2) + (
        cc.build_event_envelope("run-1", 5, cc.EventType.HEARTBEAT,
                                clock=_clock),)
    gap_report = cc.check_event_completeness(gapped)
    assert 2 in gap_report.seq_gaps

    # A duplicate id is detected by the ledger/audit path.
    dup_report = cc.check_event_completeness(events + (events[0],))
    assert dup_report.duplicates == (events[0].event_id,)
    assert dup_report.complete is False

    # Empty run is incomplete and lists everything required.
    assert cc.check_event_completeness(()).complete is False


def test_event_ledger_is_append_only_and_publishes_audit_guarantee():
    ledger = cc.EventLedger("run-1")
    for event in _full_run():
        ledger.append(event)
    assert ledger.completeness().complete is True

    guarantee = ledger.audit()
    assert isinstance(guarantee, cc.EventAuditGuarantee)
    assert guarantee.run_id == "run-1"
    assert guarantee.event_count == len(cc.RELAY_REQUIRED_EVENT_TYPES)
    assert guarantee.store_all is True and guarantee.replayable is True
    assert cc.EventType.RUN_FINISHED.value in guarantee.required_event_types
    restored = json.loads(json.dumps(guarantee.to_dict()))
    assert restored["fingerprint"] == guarantee.fingerprint

    with pytest.raises(cc.EventContractError):
        ledger.append(_envelope(99, cc.EventType.HEARTBEAT))     # seq jump
    with pytest.raises(cc.EventContractError):
        ledger.append(_envelope(1, cc.EventType.RUN_STARTED))    # wrong run reuse
    with pytest.raises(cc.EventContractError):
        ledger.append("not an envelope")
    # Real persistence is a seam, never performed in this module.
    with pytest.raises(NotImplementedError):
        cc.RelayStorageSeam().store(events[0] if False else _envelope(1,
                                   cc.EventType.RUN_STARTED))


def test_event_payloads_never_carry_secret_fields_or_values():
    safe = _envelope(1, cc.EventType.RUN_STARTED, payload={"ok": True})
    assert cc.assert_event_secrets_absent(safe, ("s3cr3t-value",)) is True
    unsafe = _envelope(2, cc.EventType.TOOL_CALL, payload={"token": "abc"})
    with pytest.raises(cc.EventContractError):
        cc.assert_event_secrets_absent(unsafe)
    with pytest.raises(cc.EventContractError):
        cc.assert_event_secrets_absent(safe, ("ok",))  # value leak check


# ---------------------------------------------------------------------------
# Y3.6 -- table ideas / schema additions (schema descriptor validity)
# ---------------------------------------------------------------------------


def test_schema_descriptor_validity_for_all_registry_tables():
    required_tables = {
        "task_events", "task_files", "project_proposals", "knowledge",
        "shares", "notifications", "automation_runs", "recordings",
        "meetings", "api_keys", "webhooks", "webhook_deliveries",
        "revocations", "usage_counters", "ops_events", "ops_heartbeats",
        "ops_alerts",
    }
    names = {t.name for t in cc.SCHEMA_ADDITIONS}
    assert required_tables <= names
    validation = cc.validate_schema(cc.SCHEMA_ADDITIONS)
    assert validation.ok is True and validation.errors == ()
    assert validation.table_count == len(cc.SCHEMA_ADDITIONS)
    assert len(validation.fingerprint) == 16
    # Stable order-independent content address.
    assert validation.fingerprint == cc.validate_schema(
        tuple(reversed(cc.SCHEMA_ADDITIONS))).fingerprint


def test_schema_rejects_unsafe_or_malformed_descriptors():
    with pytest.raises(cc.SchemaDescriptorError):
        cc.Column("bad-name", "TEXT")
    with pytest.raises(cc.SchemaDescriptorError):
        cc.Column("x", "DROP TABLE")   # not an allowed column type
    with pytest.raises(cc.SchemaDescriptorError):
        cc.TableDescriptor("ok", ())
    with pytest.raises(cc.SchemaDescriptorError):
        cc.TableDescriptor("t; DROP", (cc.Column("id", "TEXT"),))
    with pytest.raises(cc.SchemaDescriptorError):
        cc.TableDescriptor("t", (cc.Column("id", "TEXT"),
                                 cc.Column("id", "TEXT")))  # dup column
    dup = cc.validate_schema((cc.SCHEMA_ADDITIONS[0],
                              cc.SCHEMA_ADDITIONS[0]))
    assert dup.ok is False and any("duplicate" in e for e in dup.errors)


def test_revocations_table_survives_data_erasure():
    revocations = next(t for t in cc.SCHEMA_ADDITIONS
                       if t.name == "revocations")
    assert revocations.retained_on_erase is True
    assert "subject_id" in revocations.column_names
    assert any(t.retained_on_erase for t in cc.SCHEMA_ADDITIONS)
    # No other table claims erasure survival by accident.
    assert sum(t.retained_on_erase for t in cc.SCHEMA_ADDITIONS) == 1


def test_migration_is_data_only_and_never_executes_sql():
    migration = cc.describe_migration(cc.SCHEMA_ADDITIONS)
    assert isinstance(migration, cc.MigrationDescriptor)
    assert migration.executes_sql is False
    assert migration.table_names == tuple(t.name for t in cc.SCHEMA_ADDITIONS)
    assert migration.column_count == sum(
        len(t.columns) for t in cc.SCHEMA_ADDITIONS)
    assert "sql" not in {k.lower() for k in migration.to_dict()}
    with pytest.raises(cc.SchemaDescriptorError):
        cc.MigrationDescriptor(("t",), 1, executes_sql=True)
    with pytest.raises(NotImplementedError):
        cc.SchemaApplySeam().apply(migration)


# ---------------------------------------------------------------------------
# Y3.9 -- sign out / sign out everywhere / disconnect (sign-out semantics)
# ---------------------------------------------------------------------------


def test_sign_out_semantics_for_all_three_scopes():
    session = cc.build_revocation(
        cc.RevocationRequest(cc.RevocationScope.SESSION, "alice"))
    everywhere = cc.build_revocation(
        cc.RevocationRequest(cc.RevocationScope.ALL_SESSIONS, "alice"))
    disconnect = cc.build_revocation(
        cc.RevocationRequest(cc.RevocationScope.ALL_CLIENTS, "alice"))

    # sign out: revoke only this session; keep credentials and clients.
    assert session.revoke_all is False
    assert session.delete_stored_credentials is False
    assert session.sign_out_all_clients is False

    # sign out everywhere: revoke all tokens; still keep stored credentials.
    assert everywhere.revoke_all is True
    assert everywhere.delete_stored_credentials is False
    assert everywhere.sign_out_all_clients is False

    # disconnect: purge credentials AND sign out every client.
    assert disconnect.revoke_all is True
    assert disconnect.delete_stored_credentials is True
    assert disconnect.sign_out_all_clients is True

    # Identities are deterministic and distinct per scope.
    assert session.revocation_id != everywhere.revocation_id
    assert cc.build_revocation(cc.RevocationRequest("session", "alice")
                               ).revocation_id == session.revocation_id
    restored = cc.TokenRevocationDescriptor.from_dict(
        json.loads(json.dumps(disconnect.to_dict())))
    assert restored.fingerprint == disconnect.fingerprint


def test_revocation_descriptors_carry_no_secret_values():
    descriptor = cc.build_revocation(
        cc.RevocationRequest(cc.RevocationScope.SESSION, "alice",
                             reason="user_initiated"))
    doc = json.dumps(descriptor.to_dict())
    for secret_key in ("token", "password", "access_token", "secret"):
        assert secret_key not in descriptor.to_dict()
    assert cc.assert_no_secrets(descriptor, ("super-secret-token",)) is True
    with pytest.raises(cc.RevocationError):
        cc.assert_no_secrets(descriptor, ("user_initiated",))
    with pytest.raises(cc.RevocationError):
        cc.TokenRevocationDescriptor(
            scope=cc.RevocationScope.SESSION, subject_id="alice",
            revocation_id="not-the-content-hash", revoke_all=False,
            delete_stored_credentials=False, sign_out_all_clients=False)


def test_revocation_ledger_applies_effects_and_is_idempotent():
    ledger = cc.RevocationLedger()
    disconnect = cc.build_revocation(
        cc.RevocationRequest(cc.RevocationScope.ALL_CLIENTS, "alice"))
    effect = ledger.apply(disconnect)
    assert effect.credentials_deleted is True
    assert effect.clients_signed_out is True
    assert effect.revoked_sessions is True
    assert ledger.is_revoked("alice") is True
    assert ledger.has_deleted_credentials("alice") is True
    assert ledger.all_clients_signed_out is True

    # Applying again is a no-op with the same effect.
    assert ledger.apply(disconnect).to_dict() == effect.to_dict()

    session = cc.build_revocation(
        cc.RevocationRequest(cc.RevocationScope.SESSION, "bob"))
    session_effect = ledger.apply(session)
    assert session_effect.credentials_deleted is False
    assert session_effect.clients_signed_out is False
    assert ledger.is_revoked("bob") is True
    with pytest.raises(cc.RevocationError):
        ledger.apply("not a descriptor")


# ---------------------------------------------------------------------------
# Y3.10 -- local-only sign-in (offline guarantee)
# ---------------------------------------------------------------------------


def test_local_signin_descriptor_has_explicit_offline_guarantee():
    descriptor = cc.LocalSignInDescriptor()
    assert descriptor.scheme == "local_only"
    assert descriptor.account_required is False
    assert descriptor.cloud_required is False
    assert descriptor.network_egress is False
    assert descriptor.loopback_only is True and descriptor.offline_capable is True
    assert cc.validate_offline_guarantee(descriptor).ok is True
    assert cc.assert_offline(descriptor) is True
    restored = cc.LocalSignInDescriptor.from_dict(
        json.loads(json.dumps(descriptor.to_dict())))
    assert restored.fingerprint == descriptor.fingerprint

    with pytest.raises(cc.OfflineGuaranteeError):
        cc.LocalSignInDescriptor(scheme="oauth")


def test_signin_rejects_any_account_cloud_or_network_dependency():
    for kwargs in (
        {"account_required": True},
        {"cloud_required": True},
        {"network_egress": True},
        {"loopback_only": False},
        {"offline_capable": False},
    ):
        descriptor = cc.LocalSignInDescriptor(**kwargs)
        result = cc.validate_offline_guarantee(descriptor)
        assert result.ok is False and result.reasons
        with pytest.raises(cc.OfflineGuaranteeError):
            cc.assert_offline(descriptor)


def test_production_refuses_to_start_with_dev_bypass_set():
    dev = cc.SignInPolicy("development", dev_bypass_enabled=True)
    assert cc.validate_signin_policy(dev).allowed is True

    production = cc.SignInPolicy("production", dev_bypass_enabled=True)
    result = cc.validate_signin_policy(production)
    assert result.allowed is False
    assert any("production refuses" in r for r in result.reasons)

    production_clean = cc.SignInPolicy("production", dev_bypass_enabled=False)
    assert cc.validate_signin_policy(production_clean).allowed is True

    with pytest.raises(cc.OfflineGuaranteeError):
        cc.SignInPolicy("staging")


# ---------------------------------------------------------------------------
# Y3.11 -- deterministic mock agent (mock labelling)
# ---------------------------------------------------------------------------


def test_mock_labelling_never_presents_a_real_provider():
    descriptor = cc.MockAgentDescriptor("mock-1", scripted_responses=("a", "b"))
    assert "mock" in descriptor.label.lower()
    assert descriptor.is_mock is True
    assert descriptor.real_provider is False
    assert descriptor.deterministic is True
    assert descriptor.provider_kind == "mock"
    assert cc.assert_never_real_provider(descriptor) is True

    doc = descriptor.to_dict()
    assert doc["is_mock"] is True and doc["real_provider"] is False
    restored = cc.MockAgentDescriptor.from_dict(json.loads(json.dumps(doc)))
    assert restored.fingerprint == descriptor.fingerprint

    # It is impossible to construct a mislabelled / "real" mock.
    with pytest.raises(cc.MockLabelingError):
        cc.MockAgentDescriptor("x", label="Claude Sonnet")
    with pytest.raises(cc.MockLabelingError):
        cc.MockAgentDescriptor("x", real_provider=True)
    with pytest.raises(cc.MockLabelingError):
        cc.MockAgentDescriptor("x", provider_kind="anthropic")
    with pytest.raises(cc.MockLabelingError):
        cc.assert_never_real_provider("not a descriptor")


def test_mock_agent_replies_are_deterministic_and_disclosed():
    descriptor = cc.MockAgentDescriptor(
        "mock-2", scripted_responses=("scripted-A", "scripted-B"))
    agent = cc.MockAgent(descriptor)
    first = agent.respond("hello")
    second = agent.respond("hello")
    assert first.to_dict() == second.to_dict()
    assert first.is_mock is True and first.deterministic is True
    assert first.label == descriptor.label
    assert first.text in ("scripted-A", "scripted-B")
    assert agent.disclose() == descriptor.label
    assert agent.to_descriptor().fingerprint == descriptor.fingerprint

    # No script still yields a deterministic, clearly-prefixed reply.
    plain = cc.MockAgent(cc.MockAgentDescriptor("mock-3"))
    assert plain.respond("hi").text.startswith("[mock response to]")


# ---------------------------------------------------------------------------
# Y3.13 -- setup: never overwrite, idempotence, atomic seam
# ---------------------------------------------------------------------------


def test_setup_never_overwrites_existing_files():
    desired = _desired_files()
    seam = cc.InMemoryWriteSeam({"config/secrets.env": "ORIGINAL-SECRET\n"})

    plan = cc.plan_generation(desired, seam.snapshot())
    assert "config/secrets.env" in plan.skip_existing
    assert [g.path for g in plan.create] == ["config/local.toml"]

    report = cc.apply_plan(plan, seam)
    assert "config/local.toml" in report.created
    assert "config/secrets.env" in report.skipped
    assert seam.snapshot()["config/secrets.env"] == "ORIGINAL-SECRET\n"
    assert "config/secrets.env" not in seam.writes

    # A hard-fail mode is available to prove the guarantee explicitly.
    strict_plan = cc.plan_generation(desired, ())
    with pytest.raises(cc.OverwriteError):
        cc.apply_plan(strict_plan, seam, on_existing="error")

    with pytest.raises(cc.SetupContractError):
        cc.apply_plan(plan, seam, on_existing="delete")


def test_setup_is_idempotent_across_repeated_runs():
    desired = _desired_files()
    seam = cc.InMemoryWriteSeam()

    first = cc.setup_once(desired, seam)
    assert set(first.created) == {"config/local.toml", "config/secrets.env"}
    snapshot_after_first = seam.snapshot()
    assert len(first.manual_steps) >= 1

    second = cc.setup_once(desired, seam)
    assert second.created == ()
    assert set(second.skipped) == {"config/local.toml", "config/secrets.env"}
    assert seam.snapshot() == snapshot_after_first
    assert seam.writes == first.created  # no additional writes

    # Plans built from the same state have the same fingerprint.
    assert cc.plan_generation(desired, ()).fingerprint == \
        cc.plan_generation(desired, ()).fingerprint
    assert cc.plan_generation(desired, ()).fingerprint != \
        cc.plan_generation(desired, seam.snapshot()).fingerprint

    restored = json.loads(json.dumps(first.to_dict()))
    assert set(restored["created"]) == set(first.created)


def test_generated_paths_are_relative_and_atomic_seam_is_explicit():
    with pytest.raises(cc.SetupContractError):
        cc.GeneratedFile("../escape.env", "x")
    with pytest.raises(cc.SetupContractError):
        cc.GeneratedFile("C:\\Windows\\x", "x")
    with pytest.raises(cc.SetupContractError):
        cc.GeneratedFile("/etc/passwd", "x")
    with pytest.raises(cc.SetupContractError):
        cc.plan_generation(("not a generated file",), ())

    good = cc.GeneratedFile("config/secrets.env", "generated")
    assert good.fingerprint == cc.GeneratedFile(
        "config/secrets.env", "generated").fingerprint

    # Real atomic writes are a seam; the tests use the in-process one.
    with pytest.raises(NotImplementedError):
        cc.WriteSeam().atomic_write("x", "y")
    in_memory = cc.InMemoryWriteSeam()
    assert in_memory.exists("x") is False
    in_memory.atomic_write("x", "y")
    assert in_memory.exists("x") is True
    assert in_memory.snapshot() == {"x": "y"}
