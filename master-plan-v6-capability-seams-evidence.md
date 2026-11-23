# Master Plan v6 — D3.x capability seams evidence

- Branch: `agent/a5-seams` (baseline `9201f2a`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\a5-seams`
- New files only (no existing source or test was edited):
  - `keel/src/keel/capability_seams.py`
  - `keel/tests/test_capability_seams.py`
  - this evidence file
- Implementation tier: `local_module` — descriptor/policy layer, stdlib only.
- Commit SHA for this change: reported in the agent hand-off message (single
  commit containing all three files).

## What was implemented

The registry has 23 `D3.*` rows; 10 are `P0` + `not_started`. All 10 are
covered by this change (verified by a test that reads `PLAN-INDEX.json` and
compares against `FEATURE_IDS`, so the coverage cannot silently drift):

| ID | Capability | Descriptor surface |
|----|-----------|--------------------|
| D3.1 | Capability seam | `ServiceDefinition`, `ServiceProvider`, `Consumer`, `CapabilitySeam`, `SeamRegistry`, `seam_checklist()` |
| D3.2 | One provider swap | `ExecutionWorld`, `ProviderKind`, `ProviderConfig`, `resolve_provider()`, `swap_world()`, `resolve_world_bundle()`, `world_manifest()`, `provider_boundary_check()` |
| D3.6 | Human commands | `CommandService`, `CommandRegistration`, `dispatch_descriptor()` |
| D3.7 | Background jobs | `job_tools()` / `JOB_TOOLS` (`job_list`, `job_read`, `job_stop`) |
| D3.8 | Webhook runtime | `webhook_rule()`, `WebhookRuleDescriptor` (trusted rule only) |
| D3.9 | Backends / argv wrapping | `backend_services()`, `sandbox_wrap_argv()`, `SandboxWrapDescriptor` |
| D3.11 | Missing package groups | `PACKAGE_GROUPS`, `PackageDescriptor`, `classify_packages()`, `package_policy()` |
| D3.13 | Spill | `SpillPolicy`, `plan_spill()`, `SpillDescriptor`, `redact_preview()` |
| D3.14 | Guards | `GuardKind`, `GuardRegistry`, `GuardRegistration`, `GuardVerdict`, `group_descriptor()` |
| D3.18 | Workspace + session query | `WorkspaceService`, `WorkspaceEntity`, `SessionQueryService`, `SessionQueryDescriptor` |

`all_p0_descriptors()` returns one uniform summary row per feature ID with
`layer="descriptor_only"`, `io_performed=False`, `network=False`,
`runtime_claimed=False`.

## Key invariants (tested)

- **D3.1 role exclusivity.** Registration is typed by exact class: a
  `ServiceProvider` cannot be registered as a `Consumer`, and a name that is
  active in one role cannot be activated in another. `complete_seams()` only
  reports a seam when all three roles are present for the same definition —
  one or two roles alone is not a seam.
- **D3.2 provider-swap determinism.** `resolve_provider()` is a pure factory:
  params are canonicalised to a sorted tuple, so mapping insertion order does
  not affect the result; equal inputs produce equal descriptors. Swapping
  `local -> ssh` changes every one of the five provider IDs and targets while
  capability contracts stay identical. The manifest lists filesystem, bash,
  PTY and LSP as services that move together. A pure source-text checker
  reports violations when tool sources import `os`/`subprocess` directly.
- **D3.11 classification honesty.** All 16 DeepSeek groups are classified into
  four exact buckets. `spill`/`guard`/`workspace`/`session-query` and other
  pure-data groups are `locally_achievable` *as descriptors only*;
  `extensions` is `owner_gated` (the plan forbids auto-install); `ptc-runtime`
  and `typert` are `unverified` (the plan does not define a contract);
  `liveshare` and `inspector` are `external_dependency` (browser/node carrier
  and a pinned compiled frontend). Every row carries a rationale, and every
  row has `scope="descriptor_only"` and `runtime_claimed=False`.
- **D3.13 spill threshold + redaction.** Output above `threshold_bytes` gets
  a deterministic virtual spill path (content digest) and a preview bounded by
  `preview_bytes`; below the threshold there is no spill path. Secrets are
  redacted with stdlib `re` **before** truncation (caller-provided secrets plus
  patterns for API keys, GitHub tokens, AWS keys, bearer tokens, `password=`
  style assignments and PEM blocks), so a secret straddling the preview
  boundary cannot leak. No file is written; `io_performed=False`.
- **D3.14 guard monotonicity.** Guards form a scope tree. A child may tighten
  (`allow -> deny`) but registration of `allow` under any ancestor with `deny`
  raises `GuardError`; inheritance works through both explicit `parent` links
  and path prefixes. `effective()` independently recomputes the decision, so
  even an out-of-band registration cannot re-enable a denied capability.
  Sibling branches are unaffected.
- **D3.18 session-query containment.** Workspace roots and entity paths are
  normalised with pure string logic (both `/` and `\` accepted, `.`/`..`
  collapsed). Traversal, sibling roots, absolute paths outside the root and
  duplicate IDs are rejected. `browse`/`search`/`export` descriptors all carry
  a contained `path_scope`; attempts to query outside the workspace raise
  `QueryError`. No SQLite connection is opened (`sql=None`,
  `backend="descriptor_only"`).
- **D3.6/7/8/9.** Pure-code commands dispatch with `model_turn=False`; a
  command declaring both `model_turn=True` and `pure_code=True` is rejected.
  Webhook rules require `trusted=True`, signature headers and confirmation
  (the stated dependencies Y5.4 and V9) and set `network=False`. Sandbox argv
  wrapping is a descriptor with `spawn=False`.

## Integration seams (where a consumer would attach this layer)

| Existing surface | Seam |
|------------------|------|
| `keel/src/keel/capability_registry.py` (capability hub / decorator) | `SeamRegistry.complete_seams()` supplies the definition/provider/consumer triple; `seam_checklist()` is the builder-guide data. |
| `keel/src/keel/providers/` | `ProviderDescriptor` is the pure input to a real injected provider factory; `resolve_world_bundle()` is the world-switch contract. |
| `keel/src/keel/toolresult.py` (tool result payloads) | `SpillDescriptor.describe()` carries `spill_path`, `preview`, `open_full_output` for the "open full output" UI. |
| `keel/src/keel/exec_guard.py`, `policy_enforcement.py` | `GuardRegistry.effective()` is an additional monotone denial source before a command/tool executes. |
| `keel/src/keel/fleet/` routes / workspace state | `WorkspaceService` + `SessionQueryService` descriptors back a browse/search/export panel; FTS5 remains a future backend. |
| `keel/src/keel/commands.py` | `CommandService.dispatch_descriptor()` marks commands that never call the model. |
| `keel/src/keel/webhooks.py` | `webhook_rule()` is the trusted-rule precondition descriptor for starting a session. |
| `keel/src/keel/sandbox_exec.py`, `os_sandbox.py` | `sandbox_wrap_argv()` describes argv wrapping before any spawn. |

No existing module imports this new module: integration is intentionally a
follow-up wiring step, so this change cannot alter current runtime behaviour.

## Tests and results

`keel/tests/test_capability_seams.py` — 28 tests covering role exclusivity,
typed registration, provider-swap determinism, boundary checks, package
classification honesty, spill threshold/preview redaction, guard
monotonicity, workspace/session-query containment, and the four remaining P0
descriptor seams.

Command and result (run from the worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_capability_seams.py']))"
............................                                             [100%]
28 passed in 0.83s
```

## Limitations / honesty statement

This is a descriptor and policy layer only. It does not start sessions, open
files, spawn processes, open sockets, or open a database. Deeper P1 rows named
in D3.11 (deliverables UI D3.12, extensions D3.15, feedback/identity/plan/
schedule, quarantine policy D3.20) and the generated/compiled assets
(D3.21/22/23) are classified and referenced, not implemented or claimed here.
Runtime wiring through the integration seams above remains separate work.
