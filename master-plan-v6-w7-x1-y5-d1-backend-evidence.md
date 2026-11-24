# Master Plan v6 — W7/X1/Y5/D1 Backend Evidence (Agent b3-mixed2)

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\backend\b3-mixed2`
- Branch: `agent/b3-mixed2` (local only, no push)
- Baseline SHA: `73b2a90`
- Environment: Python 3.11.9, pytest 9.0.2
- Test command run from `keel/` with
  `PYTHONPATH=<worktree>\keel\src` so the worktree copy of `keel` is imported
  (not the editable install of the main checkout), and
  `PYTHONIOENCODING=utf-8` so emoji-bearing reaction tests render on Windows.
- No network calls, subprocesses, hosted accounts, new dependencies or
  third-party packages are used. All behavior is stdlib-only and local.
- Files owned by this agent (3 only):
  - `keel/src/keel/w7_x1_y5_d1_backend.py`
  - `keel/tests/test_w7_x1_y5_d1_backend.py`
  - this evidence document

## Scope

`PLAN-INDEX.json` has 57 rows with prefixes `W7.*`, `X1.*`, `Y5.*`, `D1.*`:
26 are `verified` P0 rows (already implemented by prior agents) and 31 are
`not_started`. The 26 verified rows were **verified/documented, not
reimplemented**; the 31 not-started rows are implemented here.

## 1. Prior P0 rows — verification (no code changes)

All 26 verified rows were audited programmatically against the registry:
- 26/26 rows list `test_references`;
- 41/41 referenced `source_files` exist on disk in this worktree;
- zero missing sources.

They remain in their original modules:

| Prefix | Verified IDs | Existing implementation modules |
|---|---|---|
| D1 | D1.1, D1.4, D1.5, D1.10, D1.12 | `runtime_contracts.py`, `plugin_contracts.py`, `config_contracts.py`, `command_contracts.py` |
| W7 | W7.1, W7.3–W7.6, W7.8, W7.10, W7.13, W7.14, W7.16, W7.17, W7.19 | `security_contracts.py` |
| X1 | X1.1–X1.5, X1.7, X1.8, X1.13 | `model_dialects.py`, `edit_formats.py`, `repo_map.py`, `steering.py` |
| Y5 | Y5.4 | `repo_contracts.py` |

Their acceptance tests continue to live in the corresponding
`keel/tests/test_<module>.py` files; this agent did not modify them.

## 2. Implemented not-started rows (31)

Every helper below is real backend logic in the single new module
`keel/src/keel/w7_x1_y5_d1_backend.py`; parentheses give the primary symbol(s)
and the test that exercises it.

### W7.* — web/daemon security (8)

| ID | Requirement realized | Symbols | Test |
|---|---|---|---|
| W7.2 | Live-view owner-only + `Cache-Control: no-store` | `live_view_headers`, `live_view_url`, `authorize_live_view` | `test_w7_2_owner_only_live_view` |
| W7.7 | Browser-bound sealed sign-in (SameSite=Strict, pairing) | `seal_value`, `unseal_value`, `cookie_header`, `browser_fingerprint`, `BrowserBoundSignIn` | `test_w7_7_browser_bound_signin` |
| W7.9 | CSRF origin check, bearer routes exempt | `check_csrf_origin` | `test_w7_9_csrf_origin_check` |
| W7.11 | Streaming body cap, bounded multipart, capped recordings | `StreamingBodyLimiter`, `bounded_multipart`, `cap_recording` | `test_w7_11_streaming_body_and_upload_bounds` |
| W7.12 | Generic client errors + request id; detail to server log | `generic_error`, `log_error_detail` | `test_w7_12_generic_errors_and_server_log` |
| W7.15 | 144-bit share tokens; redacted public view + HTML export | `new_share_token`, `public_share_view`, `render_share_html` | `test_w7_15_share_tokens_and_public_redaction` |
| W7.18 | Atomic check-then-increment spend caps | `AtomicSpendLedger`, `SpendLimitExceeded` | `test_w7_18_atomic_spend_ledger` |
| W7.20 | Deployment hygiene checklist + support policy | `deployment_hygiene_report`, `redact_keys_for_display`, `support_policy` | `test_w7_20_deployment_hygiene` |

Security notes: HMAC seals use `hmac.compare_digest` for constant-time checks
and an expiry; share tokens use `secrets.token_urlsafe(18)` = 144 bits; the
spend ledger performs check-and-increment under a single `threading.Lock`
(a 50-thread race test confirms exactly 10 of 10 allowed charges succeed);
owner checks, CSRF origin checks and pairing completion all use constant-time
comparisons and fail closed.

### X1.* — model/tool intelligence (8)

| ID | Requirement realized | Symbols | Test |
|---|---|---|---|
| X1.6 | Apply-model sketch merge with diff-size guard | `apply_model_merge` | `test_x1_6_apply_model_merge_guard` |
| X1.9 | Few-shot exemplars only for low probe scores | `exemplars_for_probe` | `test_x1_9_few_shot_exemplars` |
| X1.10 | Self-consistency voting with judge tie-break, gated by level | `self_consistency_vote`, `VoteResult` | `test_x1_10_self_consistency_vote` |
| X1.11 | Streaming partial-JSON args; execute only when valid/complete | `PartialJSONParser` | `test_x1_11_streaming_partial_json_parser` |
| X1.12 | Parallel read-only calls, serialized writes, dependency check | `ToolCall`, `plan_tool_batches` | `test_x1_12_parallel_tool_batches` |
| X1.14 | Mid-session model switch + dialect re-render + context warning | `switch_model`, `render_history`, `context_fit_warning` | `test_x1_14_model_switch_mid_session` |
| X1.15 | Versioned per-model prompt profiles | `prompt_profile`, `model_family`, `PROMPT_PROFILES` | `test_x1_15_per_model_prompt_profiles` |
| X1.16 | Model health check driving reliability badge | `model_health_check` | `test_x1_16_model_health_check` |

### Y5.* — channel plugins, webhooks, operations (8)

| ID | Requirement realized | Symbols | Test |
|---|---|---|---|
| Y5.1 | `plugin.json` validation + `channels.<id>` / `plugins.load.paths` | `validate_plugin_manifest`, `config_namespace` | `test_y5_1_plugin_manifest_and_namespace` |
| Y5.2 | Git URL one-liner with `prepare` auto-build; `--link` dev mode | `parse_install_source` | `test_y5_2_install_from_git_url` |
| Y5.3 | Webhook subscription lifecycle with retained signing secret | `WebhookSubscriptionManager`, `create_webhook_subscription` | `test_y5_3_webhook_subscription_lifecycle` |
| Y5.5 | Reaction map incl. skin-tone variants + removable react action | `REACTION_MAP`, `map_reaction`, `react_action` | `test_y5_5_reaction_mapping` |
| Y5.6 | Chat-id mapping cache under credentials dir + documented reset | `ChatIdCache` | `test_y5_6_chat_id_cache` |
| Y5.7 | `status` / `gateway start` commands | `channel_status`, `gateway_start` | `test_y5_7_status_and_gateway_commands` |
| Y5.8 | Troubleshooting by exact error strings | `TROUBLESHOOTING`, `troubleshoot` | `test_y5_8_troubleshooting_exact_strings` |
| Y5.9 | Linq/iMessage/RCS/SMS marked "Blocked for free" | `EXCLUDED_CHANNELS`, `channel_availability` | `test_y5_9_excluded_channels` |

Webhook subscriptions generate a 32-byte URL-safe signing secret, validate the
event list against `SUPPORTED_EVENTS` (8 named events), require HTTPS by default,
and persist atomically under the credentials dir; the programmatic helper
`create_webhook_subscription` is the exported creation entry point.

### D1.* — plugins, profiles, bundles, entrypoints (7)

| ID | Requirement realized | Symbols | Test |
|---|---|---|---|
| D1.2 | Reversible registrations + disposer + leak detector | `ReversibleEffectScope`, `Disposer`, `detect_effect_leaks` | `test_d1_2_reversible_effects_and_leak_detector` |
| D1.3 | Named profiles/bundles with 5 shipped templates | `resolve_profile`, `register_bundle`, `Profile` | `test_d1_3_profiles_bundles_and_config_rows` |
| D1.6 | Config-only HMR toggle per profile | `hmr_enabled`, `hmr_config` | `test_d1_6_hmr_toggle_per_profile` |
| D1.7 | Entrypoint classifier + CI gate rejecting bypasses | `classify_entrypoint`, `verify_application_entrypoints` | `test_d1_7_entrypoint_gate` |
| D1.8 | SDK wheel naming + enforced `--profile sdk`/explicit home argv | `sdk_wheel_name`, `sdk_launch_args`, `validate_sdk_args` | `test_d1_8_sdk_runtime_launch` |
| D1.9 | `plugin` reserved as a command | `RESERVED_COMMANDS`, `validate_profile_name` | `test_d1_9_reserved_command` |
| D1.11 | Isolated per-profile install transactions with rollback log | `PluginTransaction`, `TxStep` | `test_d1_11_plugin_install_transaction` |

`ReversibleEffectScope` unwinds effects LIFO on `unload()`; `leaked()` /
`detect_effect_leaks()` is the acceptance leak detector.

### Y3.8 — device-approval pairing flow (1)

`PLAN-INDEX.json` attributes Y3.8 to this module (source
`src/keel/w7_x1_y5_d1_backend.py`, test `tests/test_w7_x1_y5_d1_backend.py`,
evidence this document), even though the ID prefix is Y3. The module declares
it in the AST-visible `FEATURE_TRACEABILITY` dict; the symbols below are real
definitions on `BrowserBoundSignIn`, and both named tests exercise the actual
sealed-pairing behavior (client/browser binding, non-empty code, kind mismatch).

| ID | Requirement realized | Symbols | Test |
| --- | --- | --- | --- |
| Y3.8 | Device-approval pairing: short code, approval elsewhere, bound to initiating client/browser | `BrowserBoundSignIn`, `BrowserBoundSignIn.bind_pairing`, `BrowserBoundSignIn.complete_pairing` | `test_y3_8_browser_bound_pairing`, `test_w7_7_browser_bound_signin` |

## 3. Test evidence

Targeted run (from `keel/`):

```
python -m pytest tests/test_w7_x1_y5_d1_backend.py -q -o faulthandler_timeout=120
................................                                         [100%]
32 passed in 3.95s
```

32 tests = 31 feature tests + 1 registry guard
(`test_all_31_not_started_feature_ids_are_covered`) that asserts every target
feature ID appears in both the module and the test file.

Full-suite regression run (from `keel/`):

```
python -m pytest -q -o faulthandler_timeout=120
```

Result: PENDING_BACKEND_FULL_SUITE_RESULT

## 4. Limits and honesty

- These are local backend behaviors and descriptors. Where a feature names an
  external system (vendor calls, git hosting, channel gateways, Electron shell,
  browser UI), the module provides the enforced contract/check/plan **backend**
  only; no network request is made and no UI is implemented — consistent with
  the "backend only" assignment.
- The spend ledger simulates a DB transaction with an in-process lock rather
  than a real SQL driver; the atomic check-then-increment contract and its
  concurrency guarantee are what is implemented and tested.
- No `PLAN-INDEX.json` / `parity.json` / generated plan edits were made here;
  registry status flips belong to the integration agent after review.
