# Master Plan v6 — E7.x P0 runtime contracts evidence

- Branch: `agent/a6-e7` (baseline `4f64b8e`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\a6-e7`
- New files only (no existing source or test was edited):
  - `keel/src/keel/runtime_contracts.py`
  - `keel/tests/test_runtime_contracts.py`
  - this evidence file
- Implementation tier: `local_module` — descriptor/policy layer, stdlib only.
- Commit SHA for this change: reported in the agent hand-off message (single
  commit containing all three files).

## What was implemented

The E7 family has six `P0` + `not_started` rows (E7.19 is already `verified`);
all six assigned rows are covered by this change. A test reads `PLAN-INDEX.json`
and checks that every assigned ID exists as a P0 E7 row and that no additional
P0-not-started E7 row is left uncovered, so coverage cannot silently drift.

| ID | Runtime contract | Descriptor surface |
|----|------------------|--------------------|
| E7.18 | sandboxPolicy | `SandboxMode`, `DEFAULT_SANDBOX_MODE`, `MODE_CAPABILITIES`, `resolve_sandbox()`, `SandboxPolicy`, `restrict_sandbox()`, `merge_sandbox()`, `can_widen_sandbox()`, `handoff_argv()`, `enforcement_report()` |
| E7.2 | toolResultPruner | `PrunableResult`, `PrunePolicy`, `redact_text()`, `Replacement`, `ArtifactSeam`, `replay_replacement()`, `prune_current_results()`, `PruneDecision`, `PruneReport` |
| E7.20 | permissionPresets | `ApprovalPolicy`, `PermissionPreset`, `PRESETS`, `preset_list()`, `PresetState`, `ExplicitOverride`, `set_override()`, `clear_override()`, `switch_preset()`, `PresetEvent`, `PresetSwitch` |
| E7.21 | fs-observation-policy | `Observation`, `hash_content()`, `check_read_before_edit()`, `detect_stale()`, `FsEvent`, `fs_event_gate()`, `GateVerdict` |
| E7.23 | web seam | `ProviderKind`, `WebProvider`, `WebService`, `WebCallDescriptor`, `WEB_SEARCH_TOOL`, `WEB_FETCH_TOOL`, `default_web_service()` |
| E7.6 | workspaceFiles | `contained_path()`, `FileStat`/`stat_descriptor()`, `TextPage`/`paged_text()`, `ByteWindow`/`byte_window()`, `DirectoryListing`/`directory_listing()`, `ChangeEvent`/`change_feed()` |

`feature_descriptors()` returns one uniform summary row per feature ID with
`layer="descriptor_only"`, `io_performed=False`, `network=False`,
`runtime_claimed=False`.

## Key invariants (tested)

- **E7.18 one home + monotone deny.** `resolve_sandbox(mode, workspace)` is the
  single resolver for the default mode and workspace root; an unknown mode or
  empty workspace raises `SandboxError` instead of falling back to a permissive
  policy (`OFF` is an explicit opt-in, never a default). The same input yields
  an equal descriptor. `restrict_sandbox()` forces named capabilities off;
  `merge_sandbox()` is a logical AND (intersection) that can never grant a
  capability either input denies, and `can_widen_sandbox()` is always `False`.
  `handoff_argv()` preserves the exact argv (no spawn) and shares the same
  workspace root as `enforcement_report()`, so bash/fs/terminals cannot confine
  to different roots.
- **E7.2 model-free, replayable, secret-safe.** Only oversized *current* results
  are pruned; historical results stay inline. A deterministic content-digest
  replacement descriptor points at an in-memory `ArtifactSeam` that keeps the
  full original value, and `replay_replacement()` re-inflates it. Secrets are
  redacted over the whole value (caller markers plus key/token/password/PEM
  patterns) **before** any truncation, so a secret cannot straddle the preview
  boundary; the replacement flags `secret_redacted` rather than truncating
  silently. The preview is always bounded by `preview_chars`. No model call is
  made; re-running produces an equal report.
- **E7.20 one event updates both knobs.** Presets are a typed tuple
  (Cautious/Balanced/Trusted) bundling `SandboxMode` + `ApprovalPolicy`.
  `switch_preset()` emits exactly one `PresetEvent` and updates both knobs, but
  explicit user overrides (recorded via `set_override()`) survive the switch and
  are listed in `preserved_overrides`; clearing an override lets the preset win
  again. Unknown preset/knob/value fails closed.
- **E7.21 observed-state checks.** `check_read_before_edit()` blocks an edit
  with no prior observation; `detect_stale()` flags hash changes or advanced
  mtime. `fs_event_gate()` dispatches on `fs.read`/`fs.edit`/`fs.write`/
  `fs.delete`: reads record an observation, mutations require one and reject a
  stale current state. Observed state is supplied by the caller; no file is
  opened and every verdict reports `io_performed=False`.
- **E7.23 free backends, stable tool names.** `default_web_service()` registers
  SearXNG search and plain HTTP fetch. `WebService.register()` rejects paid
  providers (`free=False` or `paid_only=True`) and any provider whose tool name
  is not the stable `web_search`/`web_fetch`; registration is idempotent for an
  identical descriptor and rejects conflicts. Swapping providers never changes
  the tool name. `invoke()` returns a call descriptor with `network=False` and
  `io_performed=False`.
- **E7.6 descriptor-only file API + containment.** All file helpers are pure
  functions of caller-supplied bytes/text/metadata. `contained_path()` uses
  lexical normalisation (both separators, `.`/`..` collapsed) to reject
  traversal, sibling prefixes and absolute paths outside the root; every
  descriptor carries the contained path and `io_performed=False`. Paging, byte
  windows, listings and the sequence-ordered change feed are deterministic.

## Integration seams (where a consumer would attach this layer)

| Existing surface | Seam |
|------------------|------|
| `keel/src/keel/sandbox_exec.py`, `os_sandbox.py`, `sandbox_policy.py` | `handoff_argv()` describes the exact argv for a backend; `enforcement_report()` is the backend's enforcement-report shape. No process is spawned. |
| `keel/src/keel/toolresult.py`, transcript compaction | `prune_current_results()` is compaction-ladder step 1 (prune, no model call); step 2 (summarize) stays with the caller. `ArtifactSeam` backs "open full output". |
| `keel/src/keel/permissions.py`, `permission_contracts.py` | `preset_list()` / `switch_preset()` are the user-facing bundle; the live first-match evaluator is untouched. |
| `keel/src/keel/file_watcher.py`, fs/* event gate | `fs_event_gate()` is an additional observation precondition (rule 13 hook). |
| `keel/src/keel/webapp.py`, provider catalog | `WebService` is the registry a real injected search/fetch backend resolves from. |
| renderer file tree / viewer | `paged_text()`, `byte_window()`, `directory_listing()`, `change_feed()` back the browse panels. |

No existing module imports this new module: integration is intentionally a
follow-up wiring step, so this change cannot alter current runtime behaviour.

## Tests and results

`keel/tests/test_runtime_contracts.py` — 48 tests covering registry coverage,
the aggregate descriptor-only report, and every invariant listed above.

Command and result (run from the worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_runtime_contracts.py']))"
................................................                         [100%]
48 passed in 0.80s
```

## Limitations / honesty statement

This is a descriptor and policy layer only. It does not open files, stat the
filesystem, spawn processes, open sockets, or call any search/fetch backend.
Runtime wiring through the integration seams above remains separate work, and
the deeper P1 rows in the E7 family are untouched.
