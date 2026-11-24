# Addendum 3 — X8 UI/UX depth (backend contracts): implementation evidence

Branch: `agent/b2-x8` (worktree `.../worktree/backend/b2-x8`).
Baseline: `982335d` (read-only; no existing source file, test, registry row or
stylesheet was edited).
Source of requirements: `PLAN-INDEX.json` (canonical 865-row registry), the 15
**not_started** X8 rows X8.3–X8.17 from
`Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`, Section H "UI/UX depth (use
Keel theme tokens only)". X8.1 and X8.2 are `verified` P0 rows whose canonical
implementation already lives in `keel.builder_contracts.py`; they are
re-verified and reused here, not re-implemented.

This workstream is **additive and honest**: one new module plus one new
permanent test file. No frontend UI/visual component was built. Integration
into the live runtime is a separate lead decision (seams listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/x8_backend.py` | Canonical implementation of the backend contracts for all 15 rows. Stdlib only; no network, subprocess, filesystem I/O, SQL, credential value or import-time side effect. No uuid/rng: all ids/fingerprints are deterministic SHA-256 prefixes of canonical JSON bytes. Reuses `keel.builder_contracts` as the single token source of truth. |
| `keel/tests/test_x8_backend.py` | 33 permanent backend-contract tests (2 per X8.3–X8.17 row, 1 re-verification of X8.1/X8.2, 2 cross-cutting purity/determinism checks). |
| `master-plan-v6-x8-backend-evidence.md` | This document: per-ID classification, reasons, test results and integration seams. |

## Per-ID classification

Every one of the 15 rows has a genuine backend state/data/processing concern,
so **no row was classified wholly `excluded=frontend-only`**. Each row is
therefore `implemented (backend contract only)`, and the *visual / interaction
scope* that is genuinely frontend-only is named per row and explicitly
excluded from this module. The next section gives that scope with reasons.

| ID | Registry requirement | Classification | Backend symbols implemented | Tests |
| --- | --- | --- | --- | --- |
| X8.3 | Density modes (compact/comfortable), per-pane zoom, saved layouts | implemented (backend contract only) | `DensityMode`, `ZOOM_MIN/MAX/DEFAULT`, `normalize_zoom`, `PaneZoom`, `LayoutState`, `SavedLayout`, `DEFAULT_LAYOUT`, `LayoutStore`, `validate_layout_state` + `LayoutError` | `test_x8_3_density_zoom_and_saved_layout_store`, `test_x8_3_layout_validation_fails_closed` (2) |
| X8.4 | Notification center / activity feed with filters | implemented (backend contract only) | `NotificationKind`, `NotificationStatus`, `Notification`, `NotificationFilter`, `ActivityFeed` + `NotificationError` | `test_x8_4_activity_feed_notifications_filters_and_unread_counts`, `test_x8_4_notification_inputs_fail_closed` (2) |
| X8.5 | Actionable OS notifications (approve/deny/open where supported) | implemented (backend contract only) | `NotificationAction`, `ACTION_CAPABILITIES`, `supported_actions`, `ActionableNotification`, `ActionCommand`, `plan_notification_action` + `ActionError` | `test_x8_5_actionable_notification_plans_only_supported_actions`, `test_x8_5_actionable_notification_fail_closed` (2) |
| X8.6 | Tray / menu-bar mini window state, kill switch | implemented (backend contract only) | `AgentStatus`, `AgentRun`, `ApprovalRef`, `TraySnapshot`, `build_tray_snapshot`, `KillSwitchCommand`, `kill_switch`, `validate_kill_switch` + `TrayError` | `test_x8_6_tray_snapshot_aggregates_running_agents_and_pending_approvals`, `test_x8_6_kill_switch_always_requires_confirmation` (2) |
| X8.7 | Selection actions: ask about this / add to context / save to vault | implemented (backend contract only) | `SelectionAction`, `MAX_SELECTION_CHARS`, `SELECTION_ACTION_TARGETS`, `TextSelection`, `SelectionCommand`, `plan_selection_action`, `selection_document` + `SelectionError` | `test_x8_7_selection_action_routing_and_document`, `test_x8_7_selection_validation_fails_closed` (2) |
| X8.8 | Thread tools: outline, pins, jump-to-tool-call, timeline | implemented (backend contract only) | `ToolCall`, `Message`, `Pin`, `OutlineEntry`, `TimelineEntry`, `ThreadIndex`, `build_thread_index` + `ThreadError` | `test_x8_8_thread_index_outline_jump_and_timeline`, `test_x8_8_thread_index_fail_closed` (2) |
| X8.9 | Side-by-side session compare (two models/branches, before/after) | implemented (backend contract only) | `Turn`, `SessionRecord`, `ComparisonReport`, `compare_sessions`, `comparison_document` + `CompareError` | `test_x8_9_compare_sessions_reports_models_branches_and_turn_diffs`, `test_x8_9_compare_inputs_fail_closed` (2) |
| X8.10 | Citation chips with source file/page/line preview | implemented (backend contract only) | `Citation`, `CitationPreview`, `resolve_citation`, `_safe_path` + `CitationError` | `test_x8_10_citation_resolves_source_lines_deterministically`, `test_x8_10_citation_validation_fails_closed` (2) |
| X8.11 | Inline diff / file preview with "open in dock" | implemented (backend contract only) | `DiffRow`, `DiffHunk`, `DiffReport`, `line_diff`, `render_unified`, `FilePreview`, `build_file_preview`, `OpenInDockAction`, `open_in_dock` + `DiffError` | `test_x8_11_line_diff_and_unified_render_are_real_and_deterministic`, `test_x8_11_file_preview_and_open_in_dock_action` (2) |
| X8.12 | Renderer crash recovers session view without losing draft text | implemented (backend contract only) | `DraftSnapshot`, `RecoveryResult`, `RecoveryStore` + `RecoveryError` | `test_x8_12_recovery_store_restores_latest_draft_after_a_crash`, `test_x8_12_recovery_is_latest_wins_and_fails_closed` (2) |
| X8.13 | Undo toast pattern for destructive actions | implemented (backend contract only) | `DestructiveKind`, `UndoableAction`, `UndoResult`, `build_undo_action`, `UndoStack` + `UndoError` | `test_x8_13_undo_stack_returns_compensating_commands_and_fails_closed`, `test_x8_13_undo_stack_is_bounded_fifo_and_requires_inverse` (2) |
| X8.14 | Live theme editor (tokens), contrast checker, theme JSON I/O | implemented (backend contract only) | `HEX_COLOR_RE`, `contrast_ratio`, `wcag_level`, `ContrastReport`, `check_contrast`, `ThemeDocument`, `import_theme`, `export_theme` + `ThemeError` (delegates token validation to X8.2) | `test_x8_14_contrast_checker_uses_wcag_thresholds`, `test_x8_14_theme_import_export_round_trips_through_x8_2_tokens` (2) |
| X8.15 | Optional sound cues (off by default), reduced-motion honoring | implemented (backend contract only) | `SoundCue`, `AccessibilityPreferences`, `resolve_preferences`, `apply_motion_preference`, `preference_document` + `PreferenceError` (delegates tokens to X8.2) | `test_x8_15_sound_is_off_by_default_and_motion_can_be_collapsed`, `test_x8_15_preference_overrides_fail_closed` (2) |
| X8.16 | Multi-monitor window positions per display, docks per screen | implemented (backend contract only) | `DisplayInfo`, `WindowRect`, `DockAssignment`, `DisplaySnapshot`, `DisplayLayoutStore` + `DisplayError` | `test_x8_16_display_layout_store_remembers_positions_per_display`, `test_x8_16_display_layout_validation_fails_closed` (2) |
| X8.17 | Empty-state / onboarding copy deck written once and reused | implemented (backend contract only) | `COPY_DECK`, `CopyDeckValidation`, `validate_copy_deck`, `lookup_copy`, `coverage_report`, `copy_deck_document` + `CopyDeckError` | `test_x8_17_copy_deck_is_single_source_with_placeholders`, `test_x8_17_copy_deck_coverage_and_placeholder_failures` (2) |

Already implemented (verified here, not re-implemented):

| ID | Where it lives | Re-verification |
| --- | --- | --- |
| X8.1 | `keel.builder_contracts.LOCAL_COMPONENT_CATALOG` / `catalog_manifest` | `test_x8_1_and_x8_2_contracts_still_valid_and_reused` asserts 9 components / 37 variants and a resolving manifest |
| X8.2 | `keel.builder_contracts.DEFAULT_TOKENS` / `validate_tokens` / `lint_source` | Same test asserts token validation, canonical JSON and hard-code lint; X8.14/X8.15 import these symbols directly |

## Excluded (frontend-only) scope per ID — with reasons

These are the visual/interaction responsibilities deliberately **not** built
here. Implementing them would mean widgets, CSS, native OS APIs or browser
APIs, which are outside a backend contract/service workstream.

| ID | Excluded as frontend-only | Reason |
| --- | --- | --- |
| X8.3 | Rendering compact/comfortable spacing, CSS zoom transforms, the layout-settings screen | The backend owns the validated state and saved-layout documents; applying density/zoom to pixels is the renderer's job. |
| X8.4 | The notification-center panel, badges and filter chips | The backend emits, filters and counts notifications; the panel is presentation. |
| X8.5 | The OS toast itself and its native approve/deny buttons | `plan_notification_action` validates and routes the *command* and checks platform capability, but raising a native notification is a desktop/browser API call. |
| X8.6 | The tray/menu-bar mini window, icons and dock animations | `TraySnapshot` aggregates the data the tray would show and `kill_switch` returns a confirmation-gated command; drawing the tray is native UI. |
| X8.7 | Text selection capture, context menus and highlight overlay | The backend validates the selected payload and routes the action to agent/context/vault targets; capturing the selection is UI. |
| X8.8 | The minimap, outline gutter, pinned-message badge and scrubber widget | `ThreadIndex` computes outline entries, pins, jump targets and the timeline; drawing the navigation affordances is UI. |
| X8.9 | The two-pane diff/compare view | `compare_sessions` computes the deterministic model/branch/turn report; side-by-side layout is UI. |
| X8.10 | The chip, its hover/focus popover and click target | `resolve_citation` validates/normalizes the path/page/line and slices the source excerpt; the chip and hover are UI. |
| X8.11 | Inline syntax-highlighted diff rendering and the dock panel | `line_diff`/`build_file_preview` produce real hunks, line numbers and a dock action descriptor; painting them is UI. |
| X8.12 | The React/native error boundary and the restored view itself | The acceptance criterion is about *not losing the draft*, which the `RecoveryStore` checkpoint/recovery service guarantees; the boundary component is UI. |
| X8.13 | The toast, its timer and the Undo button | `UndoStack` owns compensating commands, fail-closed tokens and FIFO eviction; showing the toast is UI. |
| X8.14 | The live-editing controls and color picker | The backend computes WCAG contrast and validates/serializes theme JSON; the editor widgets are UI. |
| X8.15 | Actually playing audio and applying CSS `prefers-reduced-motion` | The backend enforces sound-off-by-default and can collapse motion tokens to `0ms`; playback and CSS are renderer concerns. |
| X8.16 | Native screen enumeration and window move/dock detach drag | The backend remembers validated per-display rectangles and dock assignments; calling the OS window manager is native UI. |
| X8.17 | The empty-state/onboarding screens themselves | `COPY_DECK` is the single authored source with coverage/placeholder checks; screens consume it via `lookup_copy`. |

## Design decisions worth the lead's attention

1. **Backend only, no widgets.** No module creates a window, toast, tray icon,
   stylesheet, animation or DOM node. Each row is represented by data types,
   pure functions and in-memory stores whose `document()`/`to_dict()` output can
   be persisted by the existing settings store.
2. **Deterministic ids and fingerprints.** There is no uuid/rng. Notification
   ids, undo tokens, citation ids and every `fingerprint` are SHA-256 prefixes
   of canonical, sorted-key JSON bytes (`content_hash`). Repeated calls return
   identical documents, so a lead can diff generated artifacts.
3. **Fail closed on destructive/unsafe input.** A `KillSwitchCommand` cannot be
   constructed with `requires_confirmation=False`; an `UndoableAction` cannot
   omit its compensating steps; an unknown OS platform or an action not offered
   by the notification is rejected; a `..`/absolute path is rejected by
   `_safe_path`; window rectangles must fit inside a registered display.
4. **Real processing, not stubs.** `line_diff` is an actual LCS-based line diff
   using `difflib.SequenceMatcher` with context hunks and original line numbers;
   `compare_sessions` computes added/removed/changed turn sets; `check_contrast`
   implements the WCAG 2.1 relative-luminance formula and AA/AAA thresholds
   (including large-text thresholds); `resolve_citation` slices real source
   lines from a supplied source map.
5. **X8.1/X8.2 stay the single source of truth for styling.** X8.14 imports
   `validate_tokens`/`DEFAULT_TOKENS` from `keel.builder_contracts`, and X8.15's
   `apply_motion_preference` derives from the same canonical tokens without
   mutating them. No style literal is duplicated in this module.
6. **"Written once, reused everywhere" for copy (X8.17).** The deck is a single
   constant, `lookup_copy` substitutes validated placeholders, and
   `coverage_report` detects screens that reference keys that were never
   authored.
7. **Draft survival (X8.12) is latest-wins.** `RecoveryStore.checkpoint`
   refuses to overwrite a newer checkpoint with an older one, and `recover`
   reports a `stale` flag when the renderer's current sequence is ahead of the
   checkpoint. Empty recovery returns `restored=False` with empty text rather
   than inventing content.

## Test results

Command (from the worktree root — the established pattern for this repo):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_x8_backend.py']))"
```

Result: **`33 passed`**.
`python -m py_compile keel/src/keel/x8_backend.py` is clean. Python 3.11.9,
pytest 9.0.2. No existing test file was modified; none of the 33 tests touches
the live settings store, the registry, the filesystem or the network.

Note on invocation: running `python -m pytest` from inside `keel/` resolves
`keel` to a globally installed copy in the parent workspace, so the root-level
`sys.path.insert(0,'keel/src')` command above is the correct way to exercise
this worktree.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime or registry. To
adopt it, a lead would:

- **X8.3/X8.16:** persist `LayoutStore.document()` and
  `DisplayLayoutStore.snapshot().to_dict()` through the settings store; have the
  renderer read them at startup instead of keeping private UI state.
- **X8.4/X8.5:** feed `ActivityFeed.emit` from the approval/job/error event
  bus; publish `plan_notification_action(...).to_dict()` to the desktop layer,
  which decides whether the OS supports the action and renders the toast.
- **X8.6:** build `TraySnapshot` from the live agent/approval state and route
  `kill_switch(...)` through the existing confirmation/permission gate.
- **X8.7/X8.8/X8.10/X8.11:** call `plan_selection_action`, `build_thread_index`,
  `resolve_citation` and `line_diff`/`open_in_dock` from the message view's
  controller; the view consumes the returned documents.
- **X8.12:** checkpoint the composer draft on each edit; call `recover` on
  renderer mount so the acceptance criterion ("without losing the draft
  composer text") is met end to end.
- **X8.13:** wrap every archive/delete/revoke handler in `UndoStack.push` and
  execute `undo(token).commands` when the toast's Undo action fires.
- **X8.14/X8.15:** render `check_contrast` results in the theme editor, use
  `import_theme`/`export_theme` for theme JSON I/O, and feed
  `apply_motion_preference` plus `preference_document` into the style pipeline.
- **X8.17:** render screens from `lookup_copy` and gate new screens with
  `coverage_report` in CI.

Commit: see `git log -1` on `agent/b2-x8`. No push, publish or repo-visibility
change was performed.
