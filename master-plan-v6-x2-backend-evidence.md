# Master Plan v6 — X2.* backend evidence

**Baseline:** `982335d` (branch `agent/b1-x2`, worktree
`C:\Users\Admin\.local\share\opencode\worktree\backend\b1-x2`).
**Scope:** all 16 `not_started` `X2.*` rows in `PLAN-INDEX.json`
(`Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`, section B — coding workflow
extras). All 16 rows were read in full before implementation; no row was
silently dropped.

**Files owned by this deliverable (only these were created/edited):**

- `keel/src/keel/x2_orchestration_backend.py`
- `keel/tests/test_x2_orchestration_backend.py`
- `master-plan-v6-x2-backend-evidence.md` (this file)

No registry, plan index, existing source file, or pre-existing test was
modified.

## Classification summary

| Classification | Count | IDs |
| --- | --- | --- |
| `implemented` | 16 | X2.1–X2.16 |
| `excluded` | 0 | — |

Every ID has a real, stdlib-only backend capability with state, validation,
and guards — not a descriptor stub. Each capability is exercised by at least
one adversarial test. "Excluded" means no backend core exists; none of the 16
qualifies. UI surfaces (buttons, panels, renderer wiring) are deliberately
**not** in this backend deliverable and are listed per ID below; that is a
scope boundary, not a feature omission or an owner gate.

## Per-ID classification and evidence

| ID | Feature | Class | Backend entry points | Adversarial tests | Reasons / scope notes |
| --- | --- | --- | --- | --- | --- |
| X2.1 | Diagnostics feedback after every edit | implemented | `attach_diagnostics`, `collect_diagnostics`, `DiagnosticsLedger.observe/resolve/justify/gate/require_clear` | `test_x2_1_attach_filters_and_preserves_result`, `test_x2_1_ledger_resolve_justify_and_gate` | Appends actionable LSP severities to tool results without mutating them; dedupes, drops junk, degrades on provider crash. Ledger enforces "resolve or justify" with a non-empty reason and persists across restarts. LSP provider is injected — no transport is hard-coded. UI display of the annotations is out of scope. |
| X2.2 | Rename/extract/move via LSP code actions | implemented | `CodeActionRouter.plan/apply`, `_validate_changes`, `_fallback_edit` | `test_x2_2_fallback_and_validation`, `test_x2_2_lsp_provider_validated_and_falls_back_on_malformed` | Validates identifiers, ranges and workspace containment; prefers a validated LSP workspace edit and falls back to text edits with `fallback_used=True` and an explicit verification warning. Malformed or escaping LSP edits are rejected, not trusted. The editor wiring/UI prompt is out of scope. |
| X2.3 | TDD mode (red → implement → green, evidence) | implemented | `TDDRunner.start/record_red/implement/record_green/evidence`, `run_tdd` | `test_x2_3_full_red_green_records_evidence`, `test_x2_3_guards_reject_fake_evidence` | State machine refuses implementation before a *failing* red run and refuses completion after a *failing* green run; rejected attempts are retained in the evidence trail; implementation exceptions are recorded and re-raised; evidence persists to JSON. Mode toggle UI is out of scope. |
| X2.4 | Bug-repro mode (failing reproduction before code change) | implemented | `BugReproGuard.require_repro/confirm_repro/attempt_edit/verify_fix/reopen` | `test_x2_4_no_edit_without_failing_repro` | Gate blocks edits until a run with actual failure detail is confirmed; a passing repro is rejected; fixed state requires a post-edit passing run; `reopen()` prevents reusing an old confirmation. |
| X2.5 | Code review mode with inline comments accepted as tasks | implemented | `parse_unified_diff`, `added_lines`, `CodeReviewEngine.review/accept/dismiss/tasks` | `test_x2_5_review_only_added_lines_and_task_acceptance`, `test_x2_5_reviewer_failure_is_isolated` | Parses unified diffs with correct new-file line numbers, restricts comments to added lines, dedupes, isolates reviewer exceptions, and turns accepted comments into idempotent tasks. Inline rendering in the diff viewer is out of scope. |
| X2.6 | Merge queue, conflict preview, land-when-green | implemented | `preview_conflicts`, `MergeQueue.enqueue/preview/mark_green/land/list` | `test_x2_6_conflict_preview_and_land_gate` | FIFO queue, overlapping-line conflict detection (dict or diff input), and a landing gate requiring a fresh preview plus live green CI. A new preview invalidates stale green; green is ignored while conflicts exist. The "button" itself is UI and out of scope. |
| X2.7 | Test-runner adapters with failure summaries | implemented | `detect_runner`, `summarize`, `_parse_pytest/_parse_unittest/_parse_jest/_parse_go/_parse_cargo/_parse_junit`, `TestSummary.failure_digest` | `test_x2_7_adapters_and_failure_digest`, `test_x2_7_malformed_unknown_and_truncated` | Real parsers for all seven named formats (pytest, unittest, jest/vitest, go test, cargo test, JUnit XML) plus an honest generic fallback. Strips ANSI, bounds output to 200k chars, caps failures, and substitutes a concise digest for raw logs. Malformed XML falls back with a note. |
| X2.8 | Coverage-guided hints (untested changed lines) | implemented | `CoverageHints.hint`, `_ranges`, `_line_set` | `test_x2_8_uncovered_changed_lines` | Intersects changed lines with executed lines, reports contiguous uncovered ranges, flags files with no coverage data, ignores invalid/negative lines and caps hint count. Accepts both raw line lists and coverage.py-style dicts. Hint presentation UI is out of scope. |
| X2.9 | Dependency upgrade assistant (offline changelogs, rollback) | implemented | `DependencyUpgradeAssistant.plan/read_changelog/upgrade_one/run_all/journal` | `test_x2_9_offline_changelog_and_rollback` | Reads changelogs only from a local cache (no network code path), upgrades strictly one at a time with a busy guard, runs tests after each apply, rolls back on failure, optionally verifies rollback, and journals every step. Cache escape names are rejected. |
| X2.10 | Migration assistants as bundled skills with verification | implemented | `MigrationSkill`, `MIGRATION_SKILLS`, `MigrationAssistant.start/complete_step/verify/status` | `test_x2_10_skill_order_and_verification` | Four bundled skills plus custom registration; enforces step order and refuses verification until all steps are done; a missing/false check yields `incomplete`, never `verified`. Skill-packaging UI is out of scope. |
| X2.11 | Notebook-aware editing (`.ipynb` cell diff, run cell, external outputs) | implemented | `NotebookDoc`, `cell_diff`, `NotebookOutputStore`, `run_cell` | `test_x2_11_cell_diff_excludes_outputs`, `test_x2_11_run_cell_stores_outputs_outside_notebook` | Parses notebooks, diffs cell **sources** by index while explicitly excluding outputs/execution_count, and stores run outputs in a separate path-keyed store. Rejects malformed JSON and traversal-style cell ids. Cell UI is out of scope. |
| X2.12 | Commit hygiene (conventional suggestions, secret scan, hook-aware) | implemented | `CommitHygiene.suggest_type/scan_staged_diff/hook_aware/commit_gate` | `test_x2_12_conventional_suggestions_secret_scan_and_hooks` | Suggests conventional types from history frequency with a path/message heuristic fallback, scans added diff lines for five secret patterns with redacted output, and delegates to an existing pre-commit hook (`bypass=False`). A secret finding closes the commit gate. |
| X2.13 | Monorepo task graph awareness | implemented | `MonorepoGraph.package_for_path/affected/scope_tests` | `test_x2_13_affected_packages_and_cycles` | Path-prefix matching with boundary checks (`pkg` does not swallow `pkg2`), transitive dependent propagation, deduped test scoping, and cycle detection that fails closed instead of looping. Workspace config UI is out of scope. |
| X2.14 | "Explain this change/file" with symbol citations | implemented | `SymbolIndex`, `ExplanationBuilder.explain_change/explain_file` | `test_x2_14_citations_and_uncited_lines` | Maps changed lines to real symbol ranges and emits citations, buckets uncited lines instead of inventing symbols, drops malformed index entries, and bounds work. Explanation rendering is UI and out of scope. |
| X2.15 | Language packs (10 languages: guidance, install hints, test detection) | implemented | `LanguagePacks.list/get/detect/detect_test_command/install_hints`, `LANGUAGE_PACKS` | `test_x2_15_packs_detection_and_test_commands` | All ten requested packs (Python, TypeScript, Go, Rust, Java, C/C++, C#, PHP, Ruby, shell) with LSP/compiler hints and marker-based test-command detection. Registry is returned by copy so callers cannot mutate it; unknown packs/extensions fail explicitly. |
| X2.16 | Long-running process supervisor (named jobs, tail/stop/restart, crash output) | implemented | `ProcessSupervisor.start/status/wait/tail/stop/restart/crashes/stop_all` | `test_x2_16_supervisor_jobs_and_crash_surface` | Real `subprocess.Popen` jobs with argv-only commands (no `shell=True`), per-job log files, bounded tail, terminate→kill escalation, restart with original command, and automatic crash records with output tails. Duplicate-name and unknown-job errors are explicit. Terminal UI is out of scope. |

## Deliberate exclusions (scope boundary, not feature omissions)

- **UI surfaces and buttons** for X2.5 (inline viewer), X2.6 (land button),
  X2.11 (notebook cell UI), X2.14 (explanation panel), X2.16 (terminal panel):
  this deliverable owns only the backend. No UI file was edited.
- **Remote LSP / package downloads / cloud services:** injected providers and
  local caches are used instead; no network call exists in the module. Real
  LSP wiring is supplied by the host, not by this backend.
- **Registry/plan edits:** `PLAN-INDEX.json` and generated plans are never hand
  edited; feature statuses were left untouched, so all 16 remain
  `not_started` in the registry pending the integrating agent's registry pass.

## Verification (actual commands and results)

1. Harness-style run (requested invocation):

   `python -c "import sys; sys.path.insert(0,'keel/src'); exec(compile(open('keel/tests/test_x2_orchestration_backend.py',encoding='utf-8').read(),'test_x2_orchestration_backend.py','exec'))"`

   Result: **23 tests passed** (self-runner prints `PASS <name>` per test and
   `23 tests passed`).

2. Pytest collection (with the repository's existing `conftest.py`):

   `python -c "import sys; sys.path.insert(0,'keel/src'); import pytest; raise SystemExit(pytest.main(['keel/tests/test_x2_orchestration_backend.py','-q','-p','no:cacheprovider']))"`

   Result: `.......................` → **23 passed**.

3. Import check:

   `python -c "import sys; sys.path.insert(0,'keel/src'); import keel.x2_orchestration_backend as m; print(len(m.FEATURE_IDS), all(hasattr(m,n) for n in m.__all__))"`

   Result: `16 True`.

Test coverage by ID: X2.1 (2), X2.2 (2), X2.3 (2), X2.4 (1), X2.5 (2),
X2.6 (1), X2.7 (2), X2.8 (1), X2.9 (1), X2.10 (1), X2.11 (2), X2.12 (1),
X2.13 (1), X2.14 (1), X2.15 (1), X2.16 (2), plus one registry-completeness
test (`test_all_feature_ids_are_covered`) = 23.

## Honest limitations

- Classification is `implemented`, not `verified` in the full-application
  sense: the capabilities are exercised through their Python APIs and tests,
  but not yet wired into the CLI/UI runtime owned by other worktrees.
- LSP-backed behavior (X2.1, X2.2) depends on a host-provided provider; the
  backend validates its output and degrades honestly when it is missing or
  broken, but it does not ship an LSP client.
- `ProcessSupervisor` observes child exits when a status/tail/wait/crashes
  method is called; it does not run a permanent OS-level watchdog thread.
