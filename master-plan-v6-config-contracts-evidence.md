# Addendum 6 — Config / setup / sign-in contracts (Y3.x P0): implementation evidence

Branch: `agent/a6-y3` (worktree `.../worktree/addenda/a6-y3`)
Baseline: `4f64b8e`, read-only.
Source of requirements: `master-plan-v6-final-matrix.json` (historical 228-row view; canonical is PLAN-INDEX.json) →
the seven **not_started P0** Y3.x rows: Y3.2, Y3.4, Y3.6, Y3.9, Y3.10, Y3.11,
Y3.13 (milestones M2/M3/M4).  They are corroborated by `P0-BATCHES.md` and
`REMAINING-WORK-MATRIX.md`.  All seven are implemented in one additive module.

This workstream is **additive**. No existing source file or test was edited:
`keel/settings.py`, `keel/settings_store.py`, `keel/onboarding.py`,
`keel/start_health.py`, the fleet DB layer, the web app, the CLI and every
pre-existing test are untouched.  The canonical implementation lives in a new
module and is exercised by a new, permanent contract-regression test file.
Integration into the live runtime is a separate lead decision (exact seams
listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/config_contracts.py` | Canonical implementation of all seven Y3.x contracts (stdlib only; no network, subprocess, SQL execution, credential value or filesystem I/O; no import-time side effects; no uuid/rng). |
| `keel/tests/test_config_contracts.py` | 22 permanent contract tests, including every explicitly required guarantee. |
| `master-plan-v6-config-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| Y3.2 | "reuse before building" and "the server is the only DB client" | `ExistingCapability`, `ReuseRequest`, `ReusePolicy`, `ReuseDecision`, `evaluate_reuse`, `DbClientClaim`, `DbClientKind`, `ServerOnlyDbPolicy`, `DbAccessDecision`, `validate_db_client`, `assert_db_client_allowed` + `DbClientViolation` | `test_reuse_before_building_*`, `test_build_requires_justification_*`, `test_server_is_only_db_client_*` (3) |
| Y3.4 | Relay stores every run event so a client can reconnect and replay | `EventType`, `RELAY_REQUIRED_EVENT_TYPES`, `RunEventEnvelope`, `build_event_envelope`, `EventAuditGuarantee`, `CompletenessReport`, `check_event_completeness`, `audit_guarantee`, `EventLedger`, `RelayStorageSeam`, `assert_event_secrets_absent` + `EventContractError` | `test_event_envelope_*`, `test_event_completeness_*`, `test_event_ledger_*`, `test_event_payloads_never_*` (4) |
| Y3.6 | Table ideas / schema additions as data-only descriptors | `Column`, `TableDescriptor`, `SCHEMA_ADDITIONS` (17 tables), `SchemaValidation`, `validate_schema`, `MigrationDescriptor`, `describe_migration`, `SchemaApplySeam` + `SchemaDescriptorError` | `test_schema_descriptor_validity_*`, `test_schema_rejects_*`, `test_revocations_table_*`, `test_migration_is_data_only_*` (4) |
| Y3.9 | Sign out / sign out everywhere / Disconnect (disconnect deletes stored credentials and signs out all clients) | `RevocationScope`, `RevocationRequest`, `TokenRevocationDescriptor`, `build_revocation`, `assert_no_secrets`, `RevocationEffect`, `RevocationLedger` + `RevocationError` | `test_sign_out_semantics_*`, `test_revocation_descriptors_carry_no_*`, `test_revocation_ledger_*` (3) |
| Y3.10 | Local-only sign-in, gated to loopback + env flag; no account/cloud; production refuses the dev bypass | `LocalSignInDescriptor`, `OfflineGuarantee`, `validate_offline_guarantee`, `assert_offline`, `SignInPolicy`, `SignInValidation`, `validate_signin_policy` + `OfflineGuaranteeError` | `test_local_signin_descriptor_*`, `test_signin_rejects_*`, `test_production_refuses_*` (3) |
| Y3.11 | Deterministic mock agent plays scripted runs, clearly labelled, never a real provider | `MockAgentDescriptor`, `assert_never_real_provider`, `MockAgent`, `MockReply`, `MOCK_LABEL` + `MockLabelingError` | `test_mock_labelling_*`, `test_mock_agent_replies_*` (2) |
| Y3.13 | setup script: generate-only, never overwrite, atomic write seam, idempotence | `GeneratedFile`, `GenerationPlan`, `plan_generation`, `WriteSeam`, `InMemoryWriteSeam`, `ApplyReport`, `setup_manual_steps`, `apply_plan`, `setup_once` + `SetupContractError` / `OverwriteError` | `test_setup_never_overwrites_*`, `test_setup_is_idempotent_*`, `test_generated_paths_*` (3) |

Total: **22 tests**, all passing (3 consecutive runs: 0.87 s / 0.71 s / 0.74 s).
`py_compile` clean on both new Python files.

## Design decisions worth the lead's attention

1. **Reuse is the default; building must be justified.** `evaluate_reuse`
   returns `REUSE` when an available `ExistingCapability` covers the request.
   With no covering capability it returns `BUILD` only when a justification is
   recorded, otherwise `REJECTED` — an unconsidered new component cannot be
   silently approved. Unavailable capabilities never satisfy a request (Y3.2).
2. **DB access is fail-closed by role.** `ServerOnlyDbPolicy.allowed_kinds`
   defaults to `(server,)`. A claim that touches the DB is allowed only for the
   server; a browser/client/worker claim is refused with a typed
   `DbClientViolation`. Components that never open the DB are always fine. This
   is a descriptor and a pure validator: it does not touch the real DB layer
   (Y3.2).
3. **Event identity excludes wall-clock time.** `RunEventEnvelope.event_id` is a
   SHA-256 prefix of `(run_id, seq, event_type, payload)` only, so the same event
   reproduces the same id regardless of when it was captured; `occurred_at`
   comes from an injectable clock. `check_event_completeness` distinguishes a
   missing required type from a `seq` gap from a duplicate `event_id`, and
   `EventAuditGuarantee` declares `store_all` / `append_only` / `replayable`.
   `EventLedger` is an in-memory pure accumulator; real persistence stays
   behind the `RelayStorageSeam` whose default method raises. No event is
   actually stored to disk or sent anywhere (Y3.4).
4. **Schema additions are data, never DDL execution.** `SCHEMA_ADDITIONS`
   contains all 17 registry tables (`task_events`, `task_files`,
   `project_proposals`, `knowledge`, `shares`, `notifications`,
   `automation_runs`, `recordings`, `meetings`, `api_keys`, `webhooks`,
   `webhook_deliveries`, `revocations`, `usage_counters`, `ops_events`,
   `ops_heartbeats`, `ops_alerts`). Identifiers are restricted to
   `[A-Za-z_][A-Za-z0-9_]*` and column types to an explicit allowlist, so a
   descriptor cannot smuggle SQL. `revocations` is the sole table with
   `retained_on_erase=True` ("kept even when data is erased"). The schema
   fingerprint is order-independent; `MigrationDescriptor.executes_sql` is a
   hard `False`, and `SchemaApplySeam.apply()` is intentionally unimplemented
   (Y3.6).
5. **Revocation is a semantic descriptor with no secret material.**
   `RevocationScope` maps one-to-one to the three UX actions: `SESSION` →
   revoke this session only; `ALL_SESSIONS` → revoke all tokens; `ALL_CLIENTS`
   (Disconnect) → revoke all tokens **and** delete stored credentials **and**
   sign out all clients. `assert_no_secrets` fails on secret-like field names
   or any supplied secret value. The id commits only to `(scope, subject_id)`;
   applying the same revocation twice has the same effect (Y3.9).
6. **Offline is an explicit, checkable guarantee.** `LocalSignInDescriptor`
   defaults to loopback-only, no account, no cloud, no egress, fully offline.
   `validate_offline_guarantee` / `assert_offline` reject any descriptor that
   adds an online dependency. `validate_signin_policy` encodes the gating from
   the registry note: a dev bypass is legal only on loopback in development and
   makes a production start fail closed (Y3.10).
7. **A mock cannot masquerade.** `MockAgentDescriptor.__post_init__` refuses any
   label without "mock", `real_provider=True`, `is_mock=False`,
   `deterministic=False` or a non-`mock` `provider_kind`, so a mislabelled mock
   is unconstructable. Replies are chosen from the script by a stable hash of
   the prompt and carry `is_mock=True`, the disclosure label and
   `deterministic=True` (Y3.11).
8. **Setup is generate-only and idempotent.** `plan_generation` partitions
   desired files into `create` / `skip_existing` deterministically; `apply_plan`
   writes only missing files through a `WriteSeam`. `on_existing="skip"` is the
   default (no overwrite); `on_existing="error"` raises `OverwriteError` to make
   the guarantee testable as a hard failure. `setup_once` re-plans from the
   seam's current state, so a second run performs zero writes. All generated
   paths must be relative and traversal-free. `WriteSeam.atomic_write` is the
   seam a lead replaces with tmp + fsync + `os.replace`;
   `InMemoryWriteSeam` is the in-process test double. No filesystem I/O happens
   in this module (Y3.13).

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_config_contracts.py']))"
```

Result: `22 passed` (3 consecutive runs: 0.87 s / 0.71 s / 0.74 s).
Python 3.11.9, pytest 9.0.2. No existing test file was modified.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime. To adopt it, the
lead should make these changes (none are required for the tests above to pass):

1. **Build/reuse intake and DB boundary (Y3.2)** — require a `ReuseDecision`
   before creating new modules and call `assert_db_client_allowed` at the point
   where any component would open the fleet/local DB; keep the server-process
   check in `keel/settings.py` / the fleet store rather than widening it to
   browser or worker code.
2. **Relay / `keel/events.py` (Y3.4)** — wrap every emitted run frame in
   `build_event_envelope` with a monotonic per-run `seq`, append through an
   `EventLedger`, and replace `RelayStorageSeam` with a real durable store that
   persists all events. On reconnect send the ordered envelopes and have the
   client verify `check_event_completeness` before replaying. Keep
   `assert_event_secrets_absent` on the emit path.
3. **DB migrations (Y3.6)** — turn `describe_migration(SCHEMA_ADDITIONS)` into a
   review artifact; replace `SchemaApplySeam` with the existing migration
   runner after review. Preserve `revocations` across any "erase user data"
   routine by honouring `retained_on_erase=True`.
4. **Sign-out UI / auth store (Y3.9)** — map the three UI actions to
   `build_revocation` with scopes `SESSION`, `ALL_SESSIONS`, `ALL_CLIENTS`, feed
   descriptors to the real revocation/credential store, and call
   `RevocationLedger.apply` for the observable effect summary. Never log the
   descriptor together with token values.
5. **`keel serve` / web app (Y3.10)** — start from
   `LocalSignInDescriptor()`, validate with `validate_signin_policy` before
   binding, expose the `env_flag` name in the setup output, and refuse to start
   when `environment="production"` and `dev_bypass_enabled=True`.
6. **Agent selection (Y3.11)** — when no real provider is configured, construct
   a `MockAgent` and render `disclose()` in the UI/model-visible transcript so
   scripted runs are always identified as mock. Do not route mock replies
   through real-provider billing or capability paths.
7. **Setup script / `scripts/` (Y3.13)** — implement `WriteSeam.atomic_write`
   with a temporary file in the same directory, `fsync` and `os.replace`; drive
   generation with `setup_once`. Print `required_values` (names only) and
   `manual_steps`. Keep `on_existing="skip"` in the shipped script so a rerun
   never overwrites a user's secrets.

No change to `keel/session_contracts.py` or
`keel/transcript_contracts.py` is required: those modules govern the
event/journal and transcript models; this one governs config/setup/sign-in
policy descriptors.
