# Remaining E5.x backend contracts — evidence

Branch `agent/b2-e5`, baseline `982335d`. New files only (no existing file
edited): `keel/src/keel/e5_backend.py`, `keel/tests/test_e5_backend.py`, this
document.

This change implements the backend half of the **13 `not_started` E5.x rows**
in `PLAN-INDEX.json`. Every one of those rows has `implementation_tier:
local_module`, so the deliverable is a stdlib-only module of descriptors,
pure computations and policies that the desktop shell, release pipeline and
updater can import and that tests can check adversarially. There is no network,
no subprocess, no filesystem write and no real credential in the module.

Implemented IDs: **E5.2, E5.3, E5.5, E5.6, E5.7, E5.8, E5.10, E5.11, E5.13,
E5.16, E5.17, E5.18, E5.19** (11 × P1, 1 × P2 [E5.17], plus E5.19 P1/M26).

## 1. P0 rows verified (already implemented — no edit)

The six E5 P0 rows were re-checked in `keel/src/keel/desktop_contracts.py` and
`keel/tests/test_desktop_contracts.py`; all are present and green (30 passed in
this worktree, before this change):

| ID | Contract | Status |
| --- | --- | --- |
| E5.1 | `framed_transport_descriptor`, `encode_frame`/`decode_frames`, `assert_no_listening_port` | verified |
| E5.4 | `single_instance_lock_descriptor`, `SingleInstanceGuard`, shared/desktop-only state | verified |
| E5.9 | `plugin_install_decision`, `INSTALL_TIME_HOOKS` | verified |
| E5.12 | `target_build_layout`, `assert_target_confined`, `shared_cache_entry`, `verify_shared_cache` | verified |
| E5.14 | `find_upload_secrets`, `packaging_env`, `build_completion_record` | verified |
| E5.15 | `authorize_upload`, `UploadPlan`, `channel_metadata_name`, `assert_no_deletes` | verified |

They are deliberately untouched: this change owns only the three files listed
above.

## 2. What each new row now has

| ID | Contracts in `keel.e5_backend` | Property enforced |
| --- | --- | --- |
| E5.2 | `release_identity()`, `assert_release_identity()`, `VERSION_RE`, `INDEPENDENT_VERSION_FIELDS` | Shell and backend carry one exact semver-ish version; a backend upgrade is a desktop release. A split version, a `single_version=False`, an `updates_one_side_only=True`, or any independent version column fails closed. |
| E5.3 | `bundled_runtime_descriptor()`, `assert_bundled_runtime()` | Backend runs on the bundled embedded Python and bundled-seed site-packages only. System Python, package-manager state, system site-packages and the shell's own runtime are explicit forbidden flags that fail closed when set. |
| E5.5 | `activation_descriptor()`, `ActivationJournal`, `plan_activation()`, `execute_activation()`, `recover_activation()`, `TransactionLock`, `assert_transaction_owner()`, `is_transaction_stale()` | Staging → full health check → swap only after success; one rollback profile and a journal. Recovery combines the journal with directories that actually exist (missing committed profile → rollback; incomplete staging → discard). The lock records the worker as owner; an orphaned worker that still answers a liveness probe is **not** stale. |
| E5.6 | `seed_manifest()`, `assert_seed_manifest()`, `seed_shard_for()`, `verify_seed_shard()`, `offline_install_gate()`, `first_run_extraction_descriptor()` | Exactly 16 uncompressed, deterministic shards: assignment is by SHA-256 of the member name, members are sorted, and each shard carries a digest of its canonical member list. Verification re-derives the whole manifest, checks shard membership and (optionally) exact coverage of the expected packages. Shipping requires a successful offline install. |
| E5.7 | `update_unit_descriptor()`, `assert_update_unit()`, `update_schedule()`, `UpdateCheckCoordinator`, `update_install_plan()` | One signed unit binds shell + matching backend seed + runtime. Check starts 10 s after window open plus a manual "Check for updates…" item with native confirmation; concurrent requests are coalesced. Install order is verify → stop backend → install → reconcile next launch; an injected signature verifier must return true before any install step is produced. |
| E5.8 | `plugin_manager_surface()`, `authorize_plugin_operation()`, `PLUGIN_MANAGER_OPERATIONS`, `FORBIDDEN_PLUGIN_CAPABILITIES` | Separate renderer, only structured `list`/`install`/`remove`/`update` operations. Capability fields (filesystem, raw IPC, shell, arbitrary args, `path`, `argv`, `cmd`, `cwd`, `env`, `eval`, …) and path/shell-metacharacter values are rejected. |
| E5.10 | `locale_payload()`, `assert_locale_payload()`, `i18n_gate_scope()`, `SHELL_LOCALE_SURFACES` | Menus, native dialogs and the plugin window resolve the same key set from one payload; missing translations fall back to English, missing English copy is reported, non-shared or fallback-less payloads are rejected. The i18n gate scope includes desktop shell sources. |
| E5.11 | `dev_home_descriptor()`, `dev_debug_ports()`, `devtools_descriptor()`, `effective_dev_config()` | Data/project/browser data live under a disposable dev home; debug ports are read from env and range-validated (1–65535); DevTools auto-open is a toggle. `effective_dev_config(packaged=True, …)` discards every dev override so a packaged app cannot be turned into a dev build. |
| E5.13 | `validate_app_id()`, `validate_release_prerequisites()`, `RELEASE_CREDENTIAL_NAMES` | Reverse-DNS app-id format, control characters in identity/credential values, and incomplete credential sets are all hard failures before a build starts (`release --dry-run` semantics). |
| E5.16 | `update_environment()`, `assert_distinct_update_origins()`, `UPDATE_ENVIRONMENTS` | Test and production feeds are named environments with distinct channels **and** distinct origins. Origins are compared as scheme+host+port, so the same host with a different path is still rejected as a shared origin. |
| E5.17 | `signing_plan()`, `assert_signing_steps_complete()`, `redact_diagnostics()`, `assert_signing_pin_not_persisted()` | Ordered per-target steps: hardened runtime + timestamp on every embedded executable, deep strict verify, DMG notarize+staple, Windows EV token. Verification rejects an unexpected signing authority and any failed step. PIN persistence is rejected and diagnostics are redacted. This is the verification pattern only — no paid certificate is used. |
| E5.18 | `linux_release_targets()`, `assert_linux_release_targets()`, `LINUX_RELEASE_FORMATS` | Keel keeps Linux with exactly AppImage/DEB/RPM; the reference dsh limitation is recorded as `reference_dsh_supports_linux=False` and a contradicting descriptor is rejected. |
| E5.19 | `known_limitations_section()`, `assert_known_limitations_complete()`, `KNOWN_LIMITATION_TOPICS` | Renders the desktop README / About > Known limits text covering server-dependent features, shared vs separate state, and production-env release qualification. Missing sections/topics fail closed. |

## 3. Adversarial coverage (`keel/tests/test_e5_backend.py`, 77 tests)

Each feature has both a happy-path contract test and negative cases:

- **Fail-closed validation:** split/independent versions; system/shell runtime flags;
  failed health checks and missing rollback profiles; tampered shard counts,
  compression, digests and dropped members; incomplete/unsigned update units;
  forbidden plugin request fields and shell metacharacters; missing/partial locale
  copy; malformed app ids and incomplete credential sets; shared update origins;
  unexpected signing authorities and persisted PINs; incomplete Linux format sets;
  incomplete known-limitations text.
- **Injected side effects prove ordering:** the activation health check records
  that it was called with the *staged* profile exactly once; the update signature
  verifier is called once and only after structural checks, and a false result
  yields no install operations; the transaction liveness probe distinguishes a
  live orphaned worker from a stale worker.
- **Determinism:** the seed manifest is rebuilt from shuffled input and compared
  byte-for-byte; shard assignment and canonical digests are re-derived.

## 4. Test commands and results

Run from the worktree root with `sys.path` inserted (an editable install in the
environment points at the original clone, which does not contain the new module):

```
python -c "import sys; sys.path.insert(0, r'<worktree>\keel\src'); import pytest; sys.exit(pytest.main(['-q','keel/tests/test_e5_backend.py']))"
```

- New suite: **77 passed**.
- New suite + existing P0 contracts suite: **107 passed** (77 + 30).
- Full `keel/tests` suite with the worktree source path: see section 5.

## 5. Scope / owner actions (deliberate limitations)

These are pure backend descriptors and policies, as required by the
`local_module` tier. Realising them end-to-end still requires the owning teams
to bind them to the Electron shell, the release jobs and the updater: call
`assert_release_identity` when composing a release, launch the backend with the
bundled runtime via `assert_bundled_runtime`, drive real profile swaps through
`execute_activation`/`recover_activation`, build seeds with `seed_manifest` and
gate them with `offline_install_gate`, feed the updater from `update_schedule`
and `update_install_plan`, route plugin IPC through
`authorize_plugin_operation`, load shell copy through `locale_payload`, apply
`effective_dev_config` only to dev builds, run `validate_release_prerequisites`
in `release --dry-run`, configure feeds via `assert_distinct_update_origins`,
run the signing checklist in CI when a certificate exists, keep the Linux
formats in the release matrix, and publish `known_limitations_section()` in the
desktop README and About view. No credentials, network endpoints or deployment
actions were introduced here.

## Per-ID traceability: ID → implementing symbols → behavioral test

`keel/src/keel/e5_backend.py` exposes the explicit declaration
`feature_traceability_declaration()` — a tuple of `(ID, symbols)` pairs whose
string literals map each of the 13 IDs to real symbols defined in that module.
It is intentionally a function-local tuple-of-pairs rather than a module-level
registry so that `backend_hub.verify('e5_backend')` keeps its AST fallback and
still reports the docstring-only E5 IDs as *not declared* (see
`keel/tests/test_backend_hub_integration.py`). The per-ID rows below name the
concrete symbols and the concrete behavioral test functions in
`keel/tests/test_e5_backend.py`; this is the cross-check consumed by
`scripts/verify_backend_operation.py`.

| ID | Implementing symbols (`keel.e5_backend`) | Behavioral test function |
| --- | --- | --- |
| E5.2 | `release_identity`, `assert_release_identity` | `test_e5_2_shell_and_backend_share_one_exact_version`, `test_e5_2_adversarial_split_identity_rejected` |
| E5.3 | `bundled_runtime_descriptor`, `assert_bundled_runtime` | `test_e5_3_bundled_runtime_descriptor_is_self_consistent`, `test_e5_3_adversarial_system_or_shell_runtime_rejected` |
| E5.5 | `activation_descriptor`, `ActivationJournal`, `execute_activation`, `recover_activation`, `TransactionLock` | `test_e5_5_health_check_probes_staged_profile_and_gates_swap`, `test_e5_5_recovery_combines_journal_with_actual_directories` |
| E5.6 | `seed_manifest`, `assert_seed_manifest`, `offline_install_gate` | `test_e5_6_seed_manifest_is_deterministic_and_uncompressed`, `test_e5_6_offline_install_gate_and_first_run_descriptor` |
| E5.7 | `update_unit_descriptor`, `assert_update_unit`, `update_schedule`, `update_install_plan` | `test_e5_7_update_unit_binds_all_three_components`, `test_e5_7_install_plan_verifies_before_stopping_backend` |
| E5.8 | `plugin_manager_surface`, `authorize_plugin_operation` | `test_e5_8_surface_lists_only_structured_operations`, `test_e5_8_valid_operations_authorized` |
| E5.10 | `locale_payload`, `assert_locale_payload`, `i18n_gate_scope` | `test_e5_10_localized_payload_shared_with_english_fallback`, `test_e5_10_adversarial_payload_rejected` |
| E5.11 | `dev_home_descriptor`, `dev_debug_ports`, `devtools_descriptor`, `effective_dev_config` | `test_e5_11_dev_home_is_disposable_and_scoped`, `test_e5_11_devtools_toggle_and_packaged_override_isolation` |
| E5.13 | `validate_app_id`, `validate_release_prerequisites` | `test_e5_13_valid_app_ids`, `test_e5_13_release_prerequisites_ready_when_complete` |
| E5.16 | `update_environment`, `assert_distinct_update_origins` | `test_e5_16_named_environments_have_distinct_origins`, `test_e5_16_adversarial_shared_origin_rejected` |
| E5.17 | `signing_plan`, `assert_signing_steps_complete`, `redact_diagnostics`, `assert_signing_pin_not_persisted` | `test_e5_17_signing_plan_covers_required_steps`, `test_e5_17_diagnostics_redacted_and_pin_never_persisted` |
| E5.18 | `linux_release_targets`, `assert_linux_release_targets` | `test_e5_18_linux_formats_declared_and_validated`, `test_e5_18_adversarial_format_set_rejected` |
| E5.19 | `known_limitations_section`, `assert_known_limitations_complete` | `test_e5_19_section_documents_every_required_topic`, `test_e5_19_adversarial_incomplete_section_rejected` |

The earlier per-row table named symbols only; this table adds the concrete test
function column required for the evidence gate. No ID or status was changed.
