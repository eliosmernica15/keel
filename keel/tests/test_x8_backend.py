"""Permanent backend-contract specs for the 15 not_started X8.* rows.

One or more tests per not_started X8 registry ID implemented in
``keel.x8_backend``: X8.3 - X8.17.  X8.1 and X8.2 are re-verified here because
their canonical implementation already lives in ``keel.builder_contracts`` and
is reused by X8.14 / X8.15.

These specs are additive: they import only ``keel.x8_backend`` (plus the
existing ``keel.builder_contracts`` for the two already-done contracts) and
never mutate the live settings store, the registry, the filesystem or any
existing test.  Every store is purely in memory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import keel.builder_contracts as bc
import keel.x8_backend as x


# ---------------------------------------------------------------------------
# X8.1 / X8.2 -- already implemented in builder_contracts.py (verify, reuse)
# ---------------------------------------------------------------------------


def test_x8_1_and_x8_2_contracts_still_valid_and_reused():
    catalog = bc.validate_catalog()
    assert catalog.ok is True
    assert catalog.component_count == 9
    assert catalog.variant_count == 37
    manifest = bc.catalog_manifest()
    assert manifest["variant_count"] == len(manifest["variants"])

    assert bc.validate_tokens(bc.DEFAULT_TOKENS).ok is True
    assert bc.tokens_json() == bc.tokens_json()
    assert bc.lint_source("color: #4c8dff;").clean is False
    # X8.14 / X8.15 must treat builder_contracts as the token source of truth.
    assert x.validate_tokens is bc.validate_tokens
    assert x.DEFAULT_TOKENS is bc.DEFAULT_TOKENS


# ---------------------------------------------------------------------------
# X8.3 -- density modes, per-pane zoom, saved layouts
# ---------------------------------------------------------------------------


def test_x8_3_density_zoom_and_saved_layout_store():
    assert x.DensityMode.COMPACT.value == "compact"
    assert x.normalize_zoom(1.234) == 1.23
    with pytest.raises(x.LayoutError):
        x.normalize_zoom(0.4)
    layout = x.SavedLayout(
        "focus", x.LayoutState(x.DensityMode.COMPACT,
                               (x.PaneZoom("chat", 1.25),)))
    store = x.LayoutStore([x.DEFAULT_LAYOUT, layout])
    assert store.names() == ("default", "focus")
    assert store.get("focus") == layout
    assert store.get("focus").state.density is x.DensityMode.COMPACT
    assert store.document()["count"] == 2
    assert store.document()["fingerprint"] == x.LayoutStore(
        [x.DEFAULT_LAYOUT, layout]).document()["fingerprint"]
    assert store.remove("focus") is True
    assert store.get("focus") is None
    assert store.remove("focus") is False


def test_x8_3_layout_validation_fails_closed():
    with pytest.raises(x.LayoutError):
        x.PaneZoom("chat", "large")
    with pytest.raises(x.LayoutError):
        x.LayoutState(panes=(x.PaneZoom("a"), x.PaneZoom("a")))
    with pytest.raises(x.LayoutError):
        x.SavedLayout("../bad", x.LayoutState())
    assert x.validate_layout_state(x.LayoutState()) is True


# ---------------------------------------------------------------------------
# X8.4 -- notification center / activity feed with filters
# ---------------------------------------------------------------------------


def test_x8_4_activity_feed_notifications_filters_and_unread_counts():
    feed = x.ActivityFeed()
    approval = feed.emit(x.NotificationKind.APPROVAL, "Approval needed",
                         "Tool wants to write", "appr-1")
    failure = feed.emit("error", "Job failed", "run 7", "job-7")
    assert feed.unread_count() == 2
    feed.mark_read(approval.id)
    assert feed.unread_count() == 1
    assert [n.id for n in feed.query(
        x.NotificationFilter(kinds={x.NotificationKind.ERROR}))] == [failure.id]
    assert [n.id for n in feed.query(
        x.NotificationFilter(query="write"))] == [approval.id]
    assert [n.id for n in feed.query(
        x.NotificationFilter(statuses={x.NotificationStatus.READ}))] == [approval.id]
    assert feed.archive(failure.id).status is x.NotificationStatus.ARCHIVED
    assert feed.unread_count() == 0
    document = feed.document()
    assert document["fingerprint"] == document["fingerprint"]
    assert document["notifications"] == feed.document()["notifications"]
    assert document["fingerprint"] == x.content_hash(document["notifications"])[:16]


def test_x8_4_notification_inputs_fail_closed():
    with pytest.raises(x.NotificationError):
        x.NotificationFilter(limit=0)
    with pytest.raises(x.NotificationError):
        x.ActivityFeed().get("unknown")
    with pytest.raises(x.NotificationError):
        x.ActivityFeed().emit("approval", "", "body")


# ---------------------------------------------------------------------------
# X8.5 -- actionable OS notifications (plan/validate; no toast is rendered)
# ---------------------------------------------------------------------------


def test_x8_5_actionable_notification_plans_only_supported_actions():
    notification = x.ActionableNotification(
        "n-1", (x.NotificationAction.APPROVE, x.NotificationAction.DENY,
                x.NotificationAction.OPEN_TASK), "appr-1", "task-9")
    command = x.plan_notification_action(notification, "approve", "win32")
    assert command.action is x.NotificationAction.APPROVE
    assert command.target == "appr-1" and command.supported is True
    assert command.fingerprint == x.plan_notification_action(
        notification, "approve", "win32").fingerprint
    assert x.plan_notification_action(notification, "open_task", "linux").target \
        == "task-9"
    with pytest.raises(x.ActionError):
        x.plan_notification_action(notification, "approve", "linux")
    with pytest.raises(x.ActionError):
        x.plan_notification_action(notification, "approve", "unknown-os")


def test_x8_5_actionable_notification_fail_closed():
    with pytest.raises(x.ActionError):
        x.ActionableNotification("n", (x.NotificationAction.APPROVE,))
    with pytest.raises(x.ActionError):
        x.ActionableNotification("n", (x.NotificationAction.OPEN_TASK,))
    notification = x.ActionableNotification(
        "n", (x.NotificationAction.APPROVE,), "appr-1")
    with pytest.raises(x.ActionError):
        x.plan_notification_action(notification, "deny", "win32")


# ---------------------------------------------------------------------------
# X8.6 -- tray snapshot and kill switch (no native window is created)
# ---------------------------------------------------------------------------


def test_x8_6_tray_snapshot_aggregates_running_agents_and_pending_approvals():
    agents = [x.AgentRun("a1", x.AgentStatus.RUNNING),
              x.AgentRun("a2", x.AgentStatus.IDLE),
              x.AgentRun("a1", x.AgentStatus.RUNNING)]
    snapshot = x.build_tray_snapshot(
        agents, [x.ApprovalRef("ap2", "Two"), x.ApprovalRef("ap1", "One")])
    assert snapshot.running_agents == ("a1",)
    assert [a.approval_id for a in snapshot.pending_approvals] == ["ap1", "ap2"]
    assert snapshot.quick_ask_enabled is True
    assert snapshot.fingerprint == x.build_tray_snapshot(
        agents, [x.ApprovalRef("ap2", "Two"),
                 x.ApprovalRef("ap1", "One")]).fingerprint


def test_x8_6_kill_switch_always_requires_confirmation():
    command = x.kill_switch("a1", "user requested")
    assert x.validate_kill_switch(command) is True
    assert command.to_dict()["requires_confirmation"] is True
    with pytest.raises(x.TrayError):
        x.KillSwitchCommand("a1", "reason", False)
    with pytest.raises(x.TrayError):
        x.KillSwitchCommand("", "reason")


# ---------------------------------------------------------------------------
# X8.7 -- selection actions
# ---------------------------------------------------------------------------


def test_x8_7_selection_action_routing_and_document():
    selection = x.TextSelection("choose this text", "file.py", 2, 7)
    command = x.plan_selection_action(selection, x.SelectionAction.ADD_TO_CONTEXT)
    assert command.target == "context:main"
    assert x.plan_selection_action(selection, "save_to_vault").target == "vault:notes"
    assert x.plan_selection_action(selection, "ask_about").target == "agent:primary"
    assert x.plan_selection_action(selection, "ask_about", "agent:special").target \
        == "agent:special"
    document = x.selection_document(command)
    assert document["command"]["target"] == "context:main"
    assert command.fingerprint == x.plan_selection_action(
        selection, x.SelectionAction.ADD_TO_CONTEXT).fingerprint
    assert document == x.selection_document(command)


def test_x8_7_selection_validation_fails_closed():
    with pytest.raises(x.SelectionError):
        x.TextSelection("   ")
    with pytest.raises(x.SelectionError):
        x.TextSelection("abc", end=9)
    with pytest.raises(x.SelectionError):
        x.TextSelection("abc", start=-1)
    with pytest.raises(x.SelectionError):
        x.plan_selection_action("not a selection", "ask_about")


# ---------------------------------------------------------------------------
# X8.8 -- thread outline / pins / jump-to-tool-call / timeline
# ---------------------------------------------------------------------------


def test_x8_8_thread_index_outline_jump_and_timeline():
    messages = [
        x.Message("m1", 1, "user", "hi", heading="Goal"),
        x.Message("m2", 2, "assistant", "working",
                  tool_calls=(x.ToolCall("t1", "shell"),)),
        x.Message("m3", 3, "user", "done"),
    ]
    index = x.build_thread_index(messages, (x.Pin("m1", "remember"),))
    assert index.jump_to_tool_call("t1") == 2
    assert [e.seq for e in index.timeline()] == [1, 2, 3]
    assert [e.kind for e in index.outline] == ["heading", "tool"]
    assert index.fingerprint == x.build_thread_index(
        messages, (x.Pin("m1", "remember"),)).fingerprint
    assert index == x.build_thread_index(messages, (x.Pin("m1", "remember"),))


def test_x8_8_thread_index_fail_closed():
    messages = [x.Message("m1", 1, "user"), x.Message("m2", 2, "assistant")]
    with pytest.raises(x.ThreadError):
        x.build_thread_index(messages, (x.Pin("missing"),))
    with pytest.raises(x.ThreadError):
        x.build_thread_index([x.Message("m1", 1, "user"),
                              x.Message("m1", 2, "assistant")])
    with pytest.raises(x.ThreadError):
        x.Message("m", 1, "user", tool_calls=("not-a-tool-call",))
    index = x.build_thread_index(messages)
    with pytest.raises(x.ThreadError):
        index.jump_to_tool_call("nope")


# ---------------------------------------------------------------------------
# X8.9 -- side-by-side session compare
# ---------------------------------------------------------------------------


def test_x8_9_compare_sessions_reports_models_branches_and_turn_diffs():
    left = x.SessionRecord("s1", "model-a", "main", (
        x.Turn(1, "user", "hi"), x.Turn(2, "assistant", "old")))
    right = x.SessionRecord("s2", "model-b", "feature", (
        x.Turn(1, "user", "hi"), x.Turn(2, "assistant", "new"),
        x.Turn(3, "user", "more")))
    report = x.compare_sessions(left, right)
    assert report.added_turns == (3,)
    assert report.removed_turns == ()
    assert report.changed_turns == (2,)
    assert report.model_changed and report.branch_changed
    assert report.identical is False
    assert x.comparison_document(report)["comparison"]["left_id"] == "s1"
    assert report.fingerprint == x.compare_sessions(left, right).fingerprint
    assert x.compare_sessions(left, left).identical is True


def test_x8_9_compare_inputs_fail_closed():
    valid = x.SessionRecord("s", "m", "b")
    with pytest.raises(x.CompareError):
        x.compare_sessions(valid, "not a session")
    with pytest.raises(x.CompareError):
        x.SessionRecord("", "m", "b")
    with pytest.raises(x.CompareError):
        x.SessionRecord("s", "m", "b", (x.Turn(1, "a", "x"),
                                       x.Turn(1, "a", "y")))


# ---------------------------------------------------------------------------
# X8.10 -- citation chips: resolve source file / page / line
# ---------------------------------------------------------------------------


def test_x8_10_citation_resolves_source_lines_deterministically():
    source = {"src/keel/app.py": ["line1", "line2", "line3", "line4"]}
    citation = x.Citation("src/keel/app.py", page=1, line=2, end_line=3)
    preview = x.resolve_citation(citation, source)
    assert preview.lines == ("line2", "line3")
    assert preview.excerpt == "line2\nline3"
    assert preview.end_line == 3 and preview.total_lines == 4
    assert preview.fingerprint == x.resolve_citation(citation, source).fingerprint
    assert len(citation.id) == 12
    assert citation.id == x.Citation("src/keel/app.py", 1, 2, 3).id


def test_x8_10_citation_validation_fails_closed():
    source = {"src/keel/app.py": ["line1"]}
    with pytest.raises(x.CitationError):
        x.Citation("../secret")
    with pytest.raises(x.CitationError):
        x.Citation("C:/secret")
    with pytest.raises(x.CitationError):
        x.resolve_citation(x.Citation("src/keel/app.py", line=3), source)
    with pytest.raises(x.CitationError):
        x.Citation("src/keel/app.py", line=2, end_line=1)
    with pytest.raises(x.CitationError):
        x.resolve_citation(x.Citation("missing.py"), source)


# ---------------------------------------------------------------------------
# X8.11 -- inline diff, file preview, open-in-dock action
# ---------------------------------------------------------------------------


def test_x8_11_line_diff_and_unified_render_are_real_and_deterministic():
    report = x.line_diff("a\nb\nc\n", "a\nB\nc\n", context=0, path="f.txt")
    assert report.added == 1 and report.removed == 1
    assert report.clean is False and len(report.hunks) == 1
    assert report.hunks[0].old_start == 2
    rendered = x.render_unified(report)
    assert "-b" in rendered and "+B" in rendered and "@@ -2,1 +2,1 @@" in rendered
    assert rendered == x.render_unified(report)
    assert report.fingerprint == x.line_diff("a\nb\nc\n", "a\nB\nc\n",
                                             context=0, path="f.txt").fingerprint
    assert x.line_diff("a\n", "a\n").clean is True
    insertion = x.line_diff("a\n", "a\nb\n", context=0)
    assert insertion.added == 1 and insertion.removed == 0
    assert insertion.hunks[0].new_start == 2


def test_x8_11_file_preview_and_open_in_dock_action():
    source = {"f.txt": ["a", "b", "c"]}
    preview = x.build_file_preview("f.txt", source, 2, 3)
    assert preview.lines == ("b", "c") and preview.truncated is True
    assert preview.to_dict()["path"] == "f.txt"
    dock = x.open_in_dock(preview)
    assert dock.path == "f.txt" and dock.label == "Open f.txt in dock"
    assert x.build_file_preview("f.txt", source).lines == ("a", "b", "c")
    with pytest.raises(x.CitationError):
        x.build_file_preview("../f.txt", source)
    with pytest.raises(x.DiffError):
        x.build_file_preview("missing.txt", source)


# ---------------------------------------------------------------------------
# X8.12 -- crash recovery: draft checkpoint service
# ---------------------------------------------------------------------------


def test_x8_12_recovery_store_restores_latest_draft_after_a_crash():
    store = x.RecoveryStore()
    store.checkpoint(x.DraftSnapshot("s1", "half-written draft", 5, 1))
    store.checkpoint(x.DraftSnapshot("s1", "new draft", 3, 2))
    result = store.recover("s1", current_seq=2)
    assert result.restored is True
    assert result.text == "new draft" and result.cursor == 3
    assert result.checkpoint_seq == 2 and result.stale is False
    assert store.recover("s1", current_seq=5).stale is True
    assert store.recover("unknown").restored is False


def test_x8_12_recovery_is_latest_wins_and_fails_closed():
    store = x.RecoveryStore()
    store.checkpoint(x.DraftSnapshot("s1", "newer", 2, 5))
    store.checkpoint(x.DraftSnapshot("s1", "older", 1, 1))
    assert store.recover("s1").text == "newer"
    assert store.session_ids() == ("s1",)
    assert store.clear("s1") is True and store.session_ids() == ()
    with pytest.raises(x.RecoveryError):
        x.DraftSnapshot("s1", "text", cursor=99)
    with pytest.raises(x.RecoveryError):
        store.checkpoint("not a snapshot")


# ---------------------------------------------------------------------------
# X8.13 -- undo toast backend: transactional undo
# ---------------------------------------------------------------------------


def test_x8_13_undo_stack_returns_compensating_commands_and_fails_closed():
    stack = x.UndoStack()
    action = x.build_undo_action("delete", "Remove file",
                                 ("restore file",), "file.txt")
    token = stack.push(action)
    result = stack.undo(token)
    assert result.undone is True
    assert result.commands == ("restore file",)
    assert result.kind is x.DestructiveKind.DELETE
    assert result.fingerprint == x.UndoResult(
        result.action_id, result.kind, result.commands).fingerprint
    with pytest.raises(x.UndoError):
        stack.undo(token)


def test_x8_13_undo_stack_is_bounded_fifo_and_requires_inverse():
    stack = x.UndoStack(max_size=2)
    tokens = [stack.push(x.build_undo_action("revoke", f"r{i}",
                                            ("reinstate",), str(i)))
              for i in range(3)]
    assert len(stack.pending()) == 2
    with pytest.raises(x.UndoError):
        stack.undo(tokens[0])
    assert stack.undo(tokens[2]).undone is True
    with pytest.raises(x.UndoError):
        x.build_undo_action("delete", "x", ())
    with pytest.raises(x.UndoError):
        stack.push("not an action")


# ---------------------------------------------------------------------------
# X8.14 -- theme editor backend: contrast + import/export
# ---------------------------------------------------------------------------


def test_x8_14_contrast_checker_uses_wcag_thresholds():
    assert x.contrast_ratio("#000000", "#ffffff") == 21.0
    black_on_white = x.check_contrast("#000000", "#ffffff")
    assert black_on_white.level == "AAA"
    assert black_on_white.aa_pass and black_on_white.aaa_pass
    assert x.check_contrast("#ffffff", "#ffffff").level == "FAIL"
    assert x.wcag_level(3.0, large_text=True) == "AA"
    assert x.wcag_level(4.5) == "AA"
    assert x.wcag_level(7.0) == "AAA"
    assert black_on_white.fingerprint == x.check_contrast(
        "#000000", "#ffffff").fingerprint
    with pytest.raises(x.ThemeError):
        x.contrast_ratio("nope", "#ffffff")


def test_x8_14_theme_import_export_round_trips_through_x8_2_tokens():
    exported = x.export_theme(bc.DEFAULT_TOKENS)
    assert exported == x.export_theme(bc.DEFAULT_TOKENS)
    theme = x.import_theme(exported)
    assert theme.tokens == bc.DEFAULT_TOKENS
    assert theme.fingerprint == bc.validate_tokens(bc.DEFAULT_TOKENS).fingerprint
    assert theme.to_dict()["fingerprint"] == theme.fingerprint
    with pytest.raises(x.ThemeError):
        x.import_theme("not json")
    with pytest.raises(x.ThemeError):
        x.import_theme('{"color": {}}')


# ---------------------------------------------------------------------------
# X8.15 -- accessibility preferences
# ---------------------------------------------------------------------------


def test_x8_15_sound_is_off_by_default_and_motion_can_be_collapsed():
    defaults = x.resolve_preferences()
    assert defaults.sound_enabled is False
    assert defaults.sound_cues == frozenset()
    assert defaults.effective_reduced_motion is False
    assert x.apply_motion_preference(bc.DEFAULT_TOKENS, defaults)["motion"] \
        == bc.DEFAULT_TOKENS["motion"]

    enabled = x.resolve_preferences({"sound_enabled": True,
                                     "sound_cues": ["approval"],
                                     "reduced_motion": True})
    assert x.SoundCue.APPROVAL in enabled.sound_cues
    motion = x.apply_motion_preference(bc.DEFAULT_TOKENS, enabled)
    assert motion["motion"]["fast"] == "0ms"
    assert motion["motion"]["easing"] == "linear"
    assert bc.DEFAULT_TOKENS["motion"]["fast"] == "120ms"  # source untouched
    doc = x.preference_document(defaults)
    assert doc["fingerprint"] == x.preference_document(defaults)["fingerprint"]


def test_x8_15_preference_overrides_fail_closed():
    with pytest.raises(x.PreferenceError):
        x.resolve_preferences({"unknown": 1})
    with pytest.raises(x.PreferenceError):
        x.resolve_preferences({"sound_enabled": "yes"})
    with pytest.raises(x.PreferenceError):
        x.resolve_preferences({"sound_cues": ["not-a-cue"]})
    assert x.resolve_preferences({"system_reduced_motion": True}
                                 ).effective_reduced_motion is True


# ---------------------------------------------------------------------------
# X8.16 -- multi-monitor window/dock memory
# ---------------------------------------------------------------------------


def test_x8_16_display_layout_store_remembers_positions_per_display():
    store = x.DisplayLayoutStore()
    store.register(x.DisplayInfo("D1", 1920, 1080, primary=True))
    store.register(x.DisplayInfo("D2", 1280, 800, origin_x=1920))
    store.set_position("D1", x.WindowRect(10, 10, 800, 600))
    store.set_position("D2", x.WindowRect(1930, 20, 400, 300))
    store.assign_dock("left", "D2")
    snapshot = store.snapshot()
    assert [d.display_id for d in snapshot.displays] == ["D1", "D2"]
    assert [key for key, _rect in snapshot.positions] == ["D1", "D2"]
    assert snapshot.docks == (x.DockAssignment("left", "D2"),)
    assert snapshot.fingerprint == store.snapshot().fingerprint
    assert snapshot == store.snapshot()


def test_x8_16_display_layout_validation_fails_closed():
    store = x.DisplayLayoutStore()
    store.register(x.DisplayInfo("D2", 1280, 800, origin_x=1920))
    with pytest.raises(x.DisplayError):
        store.set_position("D2", x.WindowRect(0, 0, 400, 300))
    with pytest.raises(x.DisplayError):
        store.assign_dock("right", "missing")
    with pytest.raises(x.DisplayError):
        x.DisplayInfo("D3", 0, 800)
    with pytest.raises(x.DisplayError):
        x.WindowRect(0, 0, -1, 100)


# ---------------------------------------------------------------------------
# X8.17 -- copy deck written once and reused
# ---------------------------------------------------------------------------


def test_x8_17_copy_deck_is_single_source_with_placeholders():
    validation = x.validate_copy_deck()
    assert validation.ok is True and validation.entry_count == len(x.COPY_DECK)
    assert x.lookup_copy("empty.session.title") == "A fresh start"
    assert x.lookup_copy("greeting.personalized.title", name="Ada") \
        == "Hello, Ada"
    document = x.copy_deck_document()
    assert document["fingerprint"] == validation.fingerprint
    assert document == x.copy_deck_document()


def test_x8_17_copy_deck_coverage_and_placeholder_failures():
    with pytest.raises(x.CopyDeckError):
        x.lookup_copy("greeting.personalized.title")
    with pytest.raises(x.CopyDeckError):
        x.lookup_copy("does.not.exist")
    report = x.coverage_report(
        {"onboarding": ["onboarding.welcome.title"], "bad": ["missing.key"]})
    assert report["covered"] is False
    assert report["missing"] == ["missing.key"]
    assert x.coverage_report({"ok": ["empty.session.title"]})["covered"] is True
    broken = dict(x.COPY_DECK)
    broken["broken"] = "hello {name} {name"
    assert x.validate_copy_deck(broken).ok is False


# ---------------------------------------------------------------------------
# cross-cutting: determinism, purity, no frontend artifacts
# ---------------------------------------------------------------------------


def test_all_x8_fingerprints_are_reproducible():
    assert x.LayoutStore([x.DEFAULT_LAYOUT]).document()["fingerprint"] == \
        x.LayoutStore([x.DEFAULT_LAYOUT]).document()["fingerprint"]
    feed = x.ActivityFeed()
    feed.emit("info", "t", "b")
    assert feed.document()["fingerprint"] == feed.document()["fingerprint"]
    snapshot = x.build_tray_snapshot([], [])
    assert snapshot.fingerprint == x.build_tray_snapshot([], []).fingerprint
    assert x.line_diff("a", "b").fingerprint == x.line_diff("a", "b").fingerprint
    assert x.check_contrast("#000", "#fff").fingerprint == \
        x.check_contrast("#000", "#fff").fingerprint
    assert x.validate_copy_deck().fingerprint == x.validate_copy_deck().fingerprint
    assert x.RecoveryStore().document()["fingerprint"] == \
        x.RecoveryStore().document()["fingerprint"]
    assert x.UndoStack().document()["fingerprint"] == \
        x.UndoStack().document()["fingerprint"]


def test_module_is_stdlib_only_side_effect_free_and_contract_only():
    source = (Path(x.__file__).parent / "x8_backend.py").read_text(encoding="utf-8")
    for forbidden in ("import socket", "import subprocess", "import urllib",
                      "import requests", "os.system", "open(", "Path("):
        assert forbidden not in source
    assert "from keel.builder_contracts import" in source
    assert "__all__" in source
    # No frontend/visual artifact is constructed here.
    for frontend in ("class Button", "class Dialog", "render_css",
                     "QSystemTrayIcon", "notify-send"):
        assert frontend not in source
