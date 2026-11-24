# Addendum — Y3 backend behavior (remaining `not_started` Y3.* IDs): implementation evidence

Branch: `agent/b2-y3` (worktree `.../worktree/backend/b2-y3`)
Baseline: `982335d4085b40be680bb0bd0a31c6e764d7c566` (read-only)
Source of requirements: `PLAN-INDEX.json` (865-row registry). It has 21 `Y3.*`
rows: 7 `verified` P0 rows + **14 `not_started` P1 rows**. This workstream
implements real backend behavior for all fourteen `not_started` IDs and
verifies the seven already-implemented P0 rows.

This workstream is **additive**. No existing source file or test was edited.
The canonical implementation lives in one new module, exercised by one new
permanent test file, and this document is the third owned file. Runtime
integration into the live web app / CLI / fleet layer is a separate lead
decision; the exact seams are listed at the end.

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/y3_backend.py` | Canonical stdlib-only backend behavior for all 14 `not_started` Y3 IDs. No network, socket, subprocess, SQL execution, credential value or filesystem I/O; no import-time side effects; no uuid/RNG. Runtime side effects stay behind injectable seams. |
| `keel/tests/test_y3_backend.py` | 31 permanent tests: at least one per implemented ID (2–3 for most), plus one test that verifies the seven P0 rows in `keel.config_contracts`. Loads modules from this worktree's `src` so it is independent of any other editable install. |
| `master-plan-v6-y3-backend-evidence.md` | This document. |

## Implemented features (14)

| ID | Registry requirement (priority / milestone) | Primary symbols | Tests |
| --- | --- | --- | --- |
| Y3.1 | "offer only what works" (P1/M19) | `Requirement`, `OptionState`, `FeatureOption`, `Availability`, `evaluate_availability`, `visible_options`, `assert_no_dead_options` + `AvailabilityError` | `test_y3_1_*` (3) |
| Y3.3 | Versioned, idempotent, resumable provisioning steps (P1/M19) | `SetupStep`, `ProvisioningRegistry`, `StepResult`, `StepRunnerSeam`, `InMemoryStepRunner`, `ProvisioningReport`, `run_provisioning` + `ProvisioningError` | `test_y3_3_*` (3) |
| Y3.5 | Per-user concurrency limit sized to machine; extra tasks queue and auto-start (P1/M4, dep B1.7) | `HardwareProfile`, `concurrency_limit`, `Task`, `QueueState`, `PerUserQueue`, `ConcurrencyManager` + `ConcurrencyError` | `test_y3_5_*` (3) |
| Y3.7 | Scheduler tick duties, one `tick()` with idempotency keys; ticks safe to overlap (P1/M14) | `TickJob`, `TICK_JOBS`, `DueWork`, `TickOutcome`, `TickReport`, `IdempotencyLedger`, `TickGuard`, `tick` + `SchedulerError` | `test_y3_7_*` (3) |
| Y3.8 | Device-approval pairing: short code, approve elsewhere, app polls, 30-min expiry, cancel/retry (P1/M20, deps C1.12/B4.8) | `PairingState`, `PAIRING_TTL_SECONDS`, `PairingSession`, `PairingBroker` + `PairingError` | `test_y3_8_*` (3) |
| Y3.12 | Invite gate for `keel serve`: paired-client list owned by first admin client (P1/M20) | `ServeMode`, `PairedClient`, `InviteGate` + `InviteError` | `test_y3_12_*` (2) |
| Y3.14 | First run offers existing Ollama/llama.cpp models first; show disk/RAM cost before pulling (P1/M19) | `ModelResource`, `ModelProbeSeam`, `StaticModelProbe`, `CandidateModel`, `ResourceOffer`, `estimate_cost`, `plan_first_run`, `assert_reuse_first`, `assert_cost_disclosed` + `FirstRunError` | `test_y3_14_*` (2) |
| Y3.15 | Settings structure: General, Models, Permissions, Security, Connectors, Channels, Memory, Data & privacy, Admin (P1/M19) | `SettingSection`, `SETTINGS_TREE`, `REQUIRED_SETTING_SECTIONS`, `validate_settings_tree`, `section_for_key` + `SettingsTreeError` | `test_y3_15_*` (2) |
| Y3.16 | Public `/api/v1` + outgoing webhooks + operator page, with Keel-specific `/api/keel/v1` (P1/M20, deps A3.1/A3.9) | `PUBLIC_API_PREFIX`, `KEEL_API_PREFIX`, `RouteDescriptor`, `API_SURFACES`, `build_route`, `validate_route`, `is_keel_specific` + `RouteError` | `test_y3_16_*` (2) |
| Y3.17 | Agent-proposed project updates require approval (`project_proposals`) (P1/M13) | `ProposalState`, `DiffLine`, `ProjectProposal`, `ProposalApplySeam`, `RecordingApplySeam`, `ProposalLedger` + `ProposalError` | `test_y3_17_*` (2) |
| Y3.18 | Large task files on compute side; local cache with `KEEL_DATA_DIR` and eviction (P1/M4, dep X7.10) | `DATA_DIR_ENV`, `DEFAULT_DATA_DIR`, `resolve_data_dir`, `assert_compute_side`, `CachedFile`, `LocalCache` + `CacheError` | `test_y3_18_*` (2) |
| Y3.19 | Brand strings in one config file and assets in one folder; fork must rename (P1/M19) | `BrandConfig`, `BRAND`, `brand_string`, `forked_brand`, `assert_single_brand_source` + `BrandError` | `test_y3_19_*` (1) |
| Y3.20 | Docs set incl. `security-model.md` with explicit "cannot protect against" list (P1/M1) | `REQUIRED_DOCS`, `SECURITY_MODEL_LIMITS`, `DocDescriptor`, `DOCS_SET`, `validate_docs_set`, `assert_security_model_complete` + `DocsError` | `test_y3_20_*` (1) |
| Y3.21 | Prominent "agent runs as administrator / can be misled" first-run warning + permission preset explanation (P1/M19) | `ADMIN_WARNING`, `PERMISSION_PRESET_EXPLANATIONS`, `FirstRunWarning`, `FIRST_RUN_WARNINGS`, `assert_admin_warning_present`, `assert_presets_explained`, `AcknowledgementLedger` + `WarningError` | `test_y3_21_*` (1) |

Total for the fourteen new features: **30 tests**, all passing. The 31st test
verifies the P0 rows below.

## Verification of the seven Y3 P0 rows in `config_contracts.py`

These were already implemented in the P0 addendum and are **not** reimplemented
here. A guard test (`test_p0_y3_rows_verified_in_config_contracts`) loads the
worktree's `keel/src/keel/config_contracts.py` and asserts every documented
symbol still exists:

| ID | Symbols verified | Baseline test file | Result |
| --- | --- | --- | --- |
| Y3.2 | `ReusePolicy`, `ServerOnlyDbPolicy`, `evaluate_reuse`, `validate_db_client` | `keel/tests/test_config_contracts.py` | 22 passed |
| Y3.4 | `RunEventEnvelope`, `EventAuditGuarantee`, `EventLedger`, `check_event_completeness` | same | (same run) |
| Y3.6 | `Column`, `TableDescriptor`, `SCHEMA_ADDITIONS`, `validate_schema` | same | (same run) |
| Y3.9 | `RevocationScope`, `TokenRevocationDescriptor`, `build_revocation`, `RevocationLedger` | same | (same run) |
| Y3.10 | `LocalSignInDescriptor`, `validate_offline_guarantee`, `validate_signin_policy` | same | (same run) |
| Y3.11 | `MockAgentDescriptor`, `MockAgent`, `assert_never_real_provider` | same | (same run) |
| Y3.13 | `GeneratedFile`, `GenerationPlan`, `apply_plan`, `setup_once` | same | (same run) |

The P0 test file was re-run against the worktree source: **22 passed**.

## Design decisions worth the lead's attention

1. **Nothing is "wired in" by this change.** Every behavior is a real, pure
   implementation with an injectable seam at the I/O boundary. The default
   `StepRunnerSeam.run`, `ModelProbeSeam.detect`, `ProposalApplySeam.apply` and
   (in `config_contracts`) `WriteSeam` / `RelayStorageSeam` methods raise
   `NotImplementedError`; a lead replaces them at the integration point. The
   in-memory variants exist only for deterministic tests.
2. **Y3.1 is fail-closed.** An unavailable option is either hidden or shown
   with the exact missing requirement text; `assert_no_dead_options` rejects a
   misleading "available" state and a reasonless explain. A `Requirement` that
   is unsatisfied must carry `missing_detail`.
3. **Y3.3 identity is purely version-driven.** `steps_due()` compares a step's
   version to the recorded version, so a bump re-runs only that step; failed
   steps remain "due" and are picked up by the next call (resume), while a
   fully completed set produces an empty plan (idempotence). No wall-clock
   value enters a step id.
4. **Y3.5 sizing is deterministic.** Slots = `max(1, (RAM - 2GB)//6GB +
   VRAM//6GB)`, with a floor of one. Each user gets an independent FIFO queue;
   finishing a task immediately auto-starts the next pending task.
5. **Y3.7 uses content-addressed idempotency keys.** Each job's key is a
   SHA-256 prefix of `(job, now, sorted(items))`. A second tick with the same
   key reports `deduplicated=True` and processes nothing. `TickGuard` makes
   ticks safe to overlap by refusing a concurrent tick.
6. **Y3.8 has no account.** Codes are 6 uppercase hex chars derived from a
   nonce + creation time; expiry is exactly 30 minutes; `poll` is read-only
   apart from expiry, and `retry` keeps the attempt count on a fresh code.
7. **Y3.12 only applies to `keel serve`.** Single-client mode pairs freely;
   serve mode gives the first client admin ownership of the invite list, and
   every later pair/revoke must be requested by that owner (the owner cannot
   revoke itself).
8. **Y3.14 disclosure is enforced, not documented.** Creation offers are
   built from a deterministic size estimate, and `assert_cost_disclosed`
   raises when a create offer omits a positive disk/RAM cost.
9. **Y3.16 keeps a version prefix mandatory.** `validate_route` rejects any
   prefix that is not `/api/vN` or `/api/keel/vN`; the declared surfaces cover
   public API, Keel-specific API, outgoing webhook deliveries and the operator
   page.
10. **Y3.17 cannot bypass approval.** A proposal starts `PENDING`;
    `ProposalLedger.apply` raises unless the state is `APPROVED`, and the real
    diff application happens through `ProposalApplySeam`.
11. **Y3.18 keeps bytes compute-side.** `LocalCache` stores only metadata and
    requires `compute://` / `relay://` URIs; a local path is rejected. Eviction
    is LRU (lowest `last_used`, then key) and `KEEL_DATA_DIR` is read from an
    injectable env mapping at call time.
12. **Y3.19/Y3.20/Y3.21 are single-source guarantees.** A fork renames from
    the one `BrandConfig`; duplicate brand literals are rejected. The docs
    descriptor set requires all 11 named documents and the security-model
    check requires six explicit limitation topics. The first-run warning and
    every permission preset explanation are present and acknowledgement-gated.

## Test run record

Command (from the worktree root), with the worktree `src` placed first on the
path so the new module is used rather than any other editable install:

```
python -c "import sys; sys.path.insert(0,'keel/src'); \
import pytest; raise SystemExit(pytest.main(['keel/tests/test_y3_backend.py','-q']))"
```

Result: **31 passed** (3 consecutive runs: 6.08 s / 3.47 s / 5.85 s).
`python -m py_compile` is clean on both new Python files.
P0 regression: `keel/tests/test_config_contracts.py` — **22 passed**.
