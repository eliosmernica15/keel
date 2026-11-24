# Z-row backend implementation evidence (15 `not_started` features)

**Branch:** `agent/b2-z` · **Baseline:** `982335d4085b40be680bb0bd0a31c6e764d7c566`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b2-z`
**Commit SHA:** reported by this subagent in its completion message (the commit
that adds the three files listed below).

## Scope and registry note

`PLAN-INDEX.json` at the assigned baseline contains 16 `Z*` rows: 15 are
`not_started` and `Z4` is already `verified` in `keel/src/keel/repo_contracts.py`
(crash-safe turn journal). Only the 15 `not_started` rows were implemented;
`Z4` was left untouched. All 15 rows are `implementation_tier: local_module`,
so each is implemented as real, offline, stdlib-only backend behaviour in a
single additive module. No frontend, UI widget, browser or network code was
added; `PLAN-INDEX.json` and all pre-existing files are unchanged.

| ID | Registry feature | M | P | Status implemented here |
| --- | --- | --- | --- | --- |
| Z1 | Project environment lockfile | M9 | P1 | `not_started` → backend implemented |
| Z2 | Agent contract tests | M9 | P1 | `not_started` → backend implemented |
| Z3 | Redacted replay export | M4 | P1 | `not_started` → backend implemented |
| Z5 | Capability negotiation handshake | M20 | P1 | `not_started` → backend implemented |
| Z6 | Local-first sync via the user's own folder | M14 | P2 | `not_started` → backend implemented |
| Z7 | Household/OS-user separation | M22 | P2 | `not_started` → backend implemented |
| Z8 | Energy and cost estimator for local runs | M21 | P2 | `not_started` → backend implemented |
| Z9 | Natural-language policy editor | M3 | P1 | `not_started` → backend implemented |
| Z10 | Provider/model drift detector | M21 | P1 | `not_started` → backend implemented |
| Z11 | Dormant-integration health board | M15 | P1 | `not_started` → backend implemented |
| Z12 | Offline signed catalog updates | M22 | P1 | `not_started` → backend implemented |
| Z13 | "Why can't I do X?" explainer | M19 | P1 | `not_started` → backend implemented |
| Z14 | Pre-flight installer report | M22 | P2 | `not_started` → backend implemented |
| Z15 | Prompt-injection regression corpus | M3 | P1 | `not_started` → backend implemented |
| Z16 | Per-project cost budgets and "stop at budget" | M21 | P1 | `not_started` → backend implemented |

## Files owned (only these three were added)

* NEW `keel/src/keel/z_backend.py`
* NEW `keel/tests/test_z_backend.py`
* NEW `master-plan-v6-z-backend-evidence.md` (this file)

## Requirement → implementation map

| ID | Backend surface in `keel.z_backend` | Real behaviour |
| --- | --- | --- |
| Z1 | `hash_file`, `build_lock`, `write_lock`, `load_lock`, `verify_lock`, `regenerate_lock`, `EXTENSION_KINDS`, `LOCK_SCHEMA` | SHA-256 hashes and sizes of real files at install time; pins skill/plugin/MCP/model/prompt version + hash in `.keel/lock.json`; compares on session start, reports `missing`, `mismatches` and warning text; regeneration requires explicit `approved=True`. Unsafe paths fail closed. |
| Z2 | `ContractCase`, `discover_contract_tests`, `load_contract_cases`, `scripted_runner`, `check_tool_allowlist`, `check_refusal`, `check_output_shape`, `run_contract_tests` | Discovers a `tests/` folder inside agent/skill packs, loads `cases` JSON, executes them against a deterministic scripted fixture-model runner (X9.1), and asserts tool allowlist, refusal behaviour and output shape at `install`/`update` stages. Missing cases and runner errors are failures, never silent passes. |
| Z3 | `redact_text`, `redact_record`, `render_replay`, `verify_replay`, `assert_no_network_assets`, `write_replay` | Regex + audit-preview redaction of API keys, emails, home/absolute paths and `secret=` values; recursive record redaction; standalone HTML with inline CSS and a manifest, SHA-256 integrity comment and events digest; tamper detection; no `<script>`, `<link>`, `src=`, `href=`, `url(` or `@import` assets. |
| Z5 | `CLIENT_CAPABILITIES`, `CAPABILITY_FALLBACKS`, `Negotiation`, `parse_client_capabilities`, `negotiate`, `handshake`, `prompt_payload` | Strict parse of the connect-time JSON `capabilities` object; client/server intersection; explicit `disabled`/`unknown` sets and per-capability fallbacks (`question_form` → `text_prompt`, `diff_viewer` → `text_diff`, `image_display` → `text_placeholder`, `plugin_panels` → `plain_list`); JSON-serialisable handshake response; prompts degrade to text when no form support. |
| Z6 | `LocalSync`, `Change`, `SyncError`, `snapshot`, `resolve` | Append-only JSONL change log with checksum + hash chain and strict ordering (tamper detection); last-writer-wins per key with deterministic winner; simultaneous divergent writes remain visible as `conflicts`; `resolve()` appends a strictly newer change; no server and no network. |
| Z7 | `sanitize_user`, `current_os_user`, `user_state_root`, `keychain_entry`, `ManagedPolicy`, `can_download_model`, `household_layout` | Per-OS-user state/workspace/cache directories derived from `USERNAME`/`USER`/`LOGNAME` (with `getpass.getuser()` fallback), path-safe user names, separate keychain entry per user (no secret stored), admin-managed download lock with admin exemption. |
| Z8 | `measure_throughput`, `estimate_energy`, `estimate_local_run`, `energy_summary` | Measured tokens/sec from real token counts and elapsed time; user-entered wattage and `$/kWh` produce joules, kWh and cost via explicit formulas; every result is labelled `is_estimate=True` with its assumptions; local runs have no provider-billing field. |
| Z9 | `PolicyRule`, `propose_rule`, `validate_rule`, `simulate`, `policy_editor`, `TIER2_PROTECTED_TOOLS` | Deterministic NL→JSON rule proposal ("never run git push" → deny `shell` prefix `git push`); shape validation; Tier-2 protected read-only tools and opposite-effect existing rules are rejected; simulator shows exactly which sample actions match; approval is explicit (`approve=True`) and never implied. |
| Z10 | `DriftStore`, `DriftStore.record/latest/detect/weekly_check` | SQLite (stdlib `sqlite3`, file or `:memory:`) storage of tool-call scores per model hash + runtime version; compares with the previous score, reports delta, changed hash/runtime and reasons (`no_baseline`, `score_drop_after_change`, `score_regression`, `stable`); 7-day weekly job runs only when due. |
| Z11 | `Integration`, `probe`, `reprobe_due`, `health_board`, status constants | Probes connectors/channels/MCP servers from local settings with no network; statuses `dormant`/`connecting`/`active`/`error`; reports the exact missing setting names and last probe time; Y4.1-style re-probe schedule and board summary counts. |
| Z12 | RFC 8032 `generate_keypair`, `sign`, `verify`, `make_key_certificate`, `verify_key_certificate`, `make_catalog_bundle`, `verify_bundle`, `import_bundle` | Pure-Python Ed25519 over the Edwards curve with SHA-512 and a cofactored verification check (matches RFC 8032 test vector); root-signed key certificate chain; versioned signed bundles for model catalogs, MCP presets and language packs; verify before import, reject unknown keys, tampering and downgrades; fully offline (USB/feed file). |
| Z13 | `Requirement`, `FeatureSpec`, `register_feature`, `evaluate_requirement`, `explain`, `why_cant_i`, `feature_matrix` | Built-in `requires` lists for features; evaluates flags, settings, permissions, policies and dependency status from a supplied context; returns blockers, observed values and plain-text "why can't I" explanations; unknown feature IDs fail closed. |
| Z14 | `load_manifest`, `build_preflight_report`, `preflight_gate`, `render_report_md` | Parses a build manifest and reports the files it would create/overwrite, protocols it would register, services it would add and registry keys it would write; detects duplicates, unsafe absolute/traversal paths and existing targets; produces a blocking gate and text/markdown report without performing any install action. |
| Z15 | `InjectionCorpus.add/records/replay/summary/export_anonymized` | Opt-in-only local JSONL corpus of blocked prompts; stores SHA-256 hash + redacted text (never raw PII/secrets); replays samples through a caller-supplied local detector and reports detected/missed; anonymized export and category summary; no upload path exists. |
| Z16 | `ProjectBudgets`, `BudgetExceeded`, `set_budget`, `record`, `check`, `summary`, `projects` | Project-scoped JSON ledger: token budget for local runs, USD budget for user-key remote runs; stop-at-budget blocks further records once reached; summary reports usage, remaining amounts and stop state; per-project isolation. |
| Cross-cutting | `_safe_relpath`, `_canonical_json`, `_sha256_json`, `_atomic_write_text`, `_append_jsonl` | Path traversal/absolute-path rejection, canonical JSON for reproducible digests, atomic UTF-8 writes and fsynced append-only ledgers. Malformed or unknown input raises rather than returning fake success. |

## Verification

Run from the worktree root (stdlib-only runner). Python 3.11.9:

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_z_backend.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **90 tests passed** in ~1.1 s.

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_z_backend.py']))"
```

Result: **90 passed, 4 subtests passed** in ~12.4 s (pytest 9.0.2).

Test distribution: scope/stdlib guard 2, Z1 7, Z2 7, Z3 6, Z5 6, Z6 6,
Z7 6, Z8 4, Z9 6, Z10 7, Z11 5, Z12 7, Z13 6, Z14 5, Z15 5, Z16 5.
Every one of the 15 implemented rows has a dedicated test class; the RFC 8032
Ed25519 test vector is pinned by `TestZ12SignedCatalog.test_rfc8032_test_vector`.
`python -m py_compile` succeeds for both new Python files.

## Honest limitations

* This is a host-side backend layer. No daemon, TUI, web page, installer or
  update feed was wired to it; callers must use these APIs explicitly.
* Z9 proposes and simulates rules with deterministic parsing rather than an
  LLM; a real model-based proposer can replace `propose_rule` behind the same
  shape. Z11 probes local settings only, not live remote services.
* Z12 implements full Ed25519 in pure Python with a cofactored check; it does
  not implement a public PKI or a hardware-backed signing key.
* Z3's HTML is an inert export (no JS); it does not provide an interactive
  replay UI. Z13/Z14 render text/markdown, not UI components.
* No registry row was marked `verified` in `PLAN-INDEX.json`; status updates
  remain the lead's/owner's decision.
