"""E7.x P0 runtime-contract features — descriptor/policy layer (no I/O, no network).

Feature coverage:
    E7.18 sandboxPolicy: one home for default sandbox mode + workspace root
    E7.2  toolResultPruner: model-free pruning via replayable replacements
    E7.20 permissionPresets: sandbox mode + approval policy as one preset event
    E7.21 fs-observation-policy: read-before-edit + stale detection descriptors
    E7.23 web seam: search/fetch providers in one service, stable tool names
    E7.6  workspaceFiles: stat/text/bytes/list/change-feed + path containment
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keel import runtime_contracts as rc

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# registry coverage / aggregate (all six rows in one module)
# ---------------------------------------------------------------------------
def test_feature_ids_are_exactly_the_assigned_e7_p0_rows():
    assert set(rc.FEATURE_IDS) == {
        "E7.2", "E7.6", "E7.18", "E7.20", "E7.21", "E7.23",
    }
    assert len(rc.FEATURE_IDS) == 6


def test_registry_rows_exist_and_are_p0_e7():
    registry = json.loads((REPO / "PLAN-INDEX.json").read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in registry["features"]}
    for fid in rc.FEATURE_IDS:
        row = by_id[fid]
        assert row["id"].startswith("E7.")
        assert row.get("priority") == "P0"
        assert row.get("source_feature_id") == fid
        assert row.get("acceptance_criteria")

    # Any still-not-started E7 P0 row must be covered here (robust to the lead
    # marking rows verified after this change lands).
    not_started = {
        f["id"] for f in registry["features"]
        if f["id"].startswith("E7.")
        and f.get("priority") == "P0"
        and f.get("status") == "not_started"
    }
    assert not_started <= set(rc.FEATURE_IDS)


def test_all_feature_descriptors_are_descriptor_only():
    rows = rc.feature_descriptors()
    assert set(rows) == set(rc.FEATURE_IDS)
    for row in rows.values():
        assert row["layer"] == "descriptor_only"
        assert row["io_performed"] is False
        assert row["network"] is False
        assert row["runtime_claimed"] is False
        assert row["contract"]


# ---------------------------------------------------------------------------
# E7.18 — sandboxPolicy: one home for default mode + workspace root
# ---------------------------------------------------------------------------
def test_e718_default_mode_is_one_explicit_home_and_is_restrictive():
    assert rc.DEFAULT_SANDBOX_MODE is rc.SandboxMode.STRICT
    assert rc.resolve_sandbox(None, "/work").mode is rc.DEFAULT_SANDBOX_MODE


def test_e718_resolve_returns_typed_descriptor_with_normalized_root():
    policy = rc.resolve_sandbox("workspace", "/work/./src/../")
    assert isinstance(policy, rc.SandboxPolicy)
    assert policy.mode is rc.SandboxMode.WORKSPACE
    assert policy.workspace_root == "/work"
    assert policy.enforcement_reported is True
    assert policy.capabilities[rc.CAP_NETWORK] is False
    assert policy.capabilities[rc.CAP_PROCESS_SPAWN] is False


def test_e718_same_mode_and_workspace_is_deterministic():
    a = rc.resolve_sandbox("strict", "/work")
    b = rc.resolve_sandbox("strict", "/work")
    assert a == b


def test_e718_unknown_mode_and_empty_workspace_fail_closed():
    with pytest.raises(rc.SandboxError):
        rc.resolve_sandbox("yolo", "/work")
    with pytest.raises(rc.SandboxError):
        rc.resolve_sandbox("strict", "   ")


def test_e718_no_permissive_fallback_for_bad_mode():
    with pytest.raises(rc.SandboxError) as exc:
        rc.resolve_sandbox("bad-mode", "/work")
    assert "fallback" in str(exc.value).lower() or "unknown" in str(exc.value).lower()


def test_e718_off_mode_is_explicit_opt_in_not_a_default():
    off = rc.resolve_sandbox("off", "/work")
    assert off.mode is rc.SandboxMode.OFF
    assert off.capabilities[rc.CAP_NETWORK] is True
    assert off.capabilities[rc.CAP_WRITE_OUTSIDE] is True


def test_e718_shell_and_fs_share_one_workspace_root():
    policy = rc.resolve_sandbox("workspace", "/work")
    argv = rc.handoff_argv(policy, ["bash", "-c", "pwd"])
    report = rc.enforcement_report(policy)
    assert argv.workspace_root == report["workspace_root"] == policy.workspace_root
    assert argv.argv == ("bash", "-c", "pwd")  # exact argv handed over
    assert argv.spawn is False  # descriptor only, no process launched


def test_e718_deny_cannot_be_widened_by_restrict_or_merge():
    strict = rc.resolve_sandbox("strict", "/work")
    off = rc.resolve_sandbox("off", "/work")
    denied = rc.restrict_sandbox(off, [rc.CAP_NETWORK, rc.CAP_PROCESS_SPAWN])
    assert denied.capabilities[rc.CAP_NETWORK] is False
    assert denied.capabilities[rc.CAP_PROCESS_SPAWN] is False
    assert denied.capabilities[rc.CAP_WRITE_OUTSIDE] is True  # untouched caps survive

    merged = rc.merge_sandbox(strict, off)  # overlay tries to widen
    assert merged.capabilities == strict.capabilities  # intersection, never wider
    assert rc.can_widen_sandbox(strict, off) is False


def test_e718_enforcement_report_names_backend_and_capabilities():
    report = rc.enforcement_report(rc.resolve_sandbox("workspace", "/work"))
    assert report["backend_reported"] is True
    assert report["mode"] == "workspace"
    assert set(report["capabilities"]) == {
        rc.CAP_NETWORK, rc.CAP_PROCESS_SPAWN,
        rc.CAP_WRITE_OUTSIDE, rc.CAP_READ_OUTSIDE,
    }


# ---------------------------------------------------------------------------
# E7.2 — toolResultPruner: model-free, replayable, secret-safe
# ---------------------------------------------------------------------------
def test_e72_small_current_result_is_kept_inline():
    seam = rc.ArtifactSeam()
    report = rc.prune_current_results([
        rc.PrunableResult("t1", "short output"),
    ], seam=seam)
    assert report.pruned_count == 0
    assert report.decisions[0].action is rc.PruneAction.KEEP_INLINE
    assert report.decisions[0].replacement is None
    assert seam.keys() == ()


def test_e72_oversized_current_result_is_replaced_with_replayable_descriptor():
    seam = rc.ArtifactSeam()
    policy = rc.PrunePolicy(max_inline_chars=20, preview_chars=8)
    value = "x" * 100
    report = rc.prune_current_results(
        [rc.PrunableResult("t1", value)], policy=policy, seam=seam)
    assert report.pruned_count == 1
    decision = report.decisions[0]
    assert decision.action is rc.PruneAction.REPLACE
    repl = decision.replacement
    assert repl is not None and repl.replayable is True
    assert repl.kind == "replacement"
    assert repl.original_chars == 100
    assert len(repl.preview) <= 8
    assert seam.get(repl.artifact_key) == value
    assert rc.replay_replacement(repl, seam) == value


def test_e72_historical_results_are_never_pruned():
    seam = rc.ArtifactSeam()
    policy = rc.PrunePolicy(max_inline_chars=5, preview_chars=3)
    report = rc.prune_current_results([
        rc.PrunableResult("old", "Z" * 50, is_current=False),
    ], policy=policy, seam=seam)
    assert report.pruned_count == 0
    assert report.decisions[0].action is rc.PruneAction.KEEP_INLINE
    assert "historical" in report.decisions[0].reason.lower()
    assert seam.keys() == ()


def test_e72_pruning_is_model_free_and_deterministic():
    policy = rc.PrunePolicy(max_inline_chars=10, preview_chars=4)
    items = [rc.PrunableResult("t1", "A" * 60), rc.PrunableResult("t2", "B" * 60)]
    r1 = rc.prune_current_results(items, policy=policy)
    r2 = rc.prune_current_results(items, policy=policy)
    assert r1 == r2
    assert all(d.reason and "model" not in d.reason.lower() for d in r1.decisions)


def test_e72_secrets_are_redacted_in_preview_but_preserved_in_artifact():
    seam = rc.ArtifactSeam()
    policy = rc.PrunePolicy(max_inline_chars=20, preview_chars=200)
    value = "token = sk-abcdefghijklmnopqrstuvwxyz and password=hunter2 secret"
    report = rc.prune_current_results([
        rc.PrunableResult("t1", value, secret_markers=("hunter2",)),
    ], policy=policy, seam=seam)
    repl = report.decisions[0].replacement
    assert repl is not None
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in repl.preview
    assert "hunter2" not in repl.preview
    assert "password=hunter2" not in repl.preview
    assert "[REDACTED]" in repl.preview
    assert repl.secret_redacted is True
    assert "secret" in repl.preview.lower()
    # Full value still preserved in the artifact seam for replay.
    assert seam.get(repl.artifact_key) == value


def test_e72_secret_straddling_preview_boundary_cannot_leak():
    seam = rc.ArtifactSeam()
    policy = rc.PrunePolicy(max_inline_chars=10, preview_chars=12)
    marker = "SUPERSECRETVALUE"
    value = "A" * 11 + marker + "B" * 40
    report = rc.prune_current_results([
        rc.PrunableResult("t1", value, secret_markers=(marker,)),
    ], policy=policy, seam=seam)
    preview = report.decisions[0].replacement.preview
    assert marker not in preview
    assert "SUPER" not in preview  # no partial secret at the cut


def test_e72_artifact_key_is_content_digest_and_replay_requires_a_seam():
    seam = rc.ArtifactSeam()
    policy = rc.PrunePolicy(max_inline_chars=5, preview_chars=3)
    repl = rc.prune_current_results(
        [rc.PrunableResult("t1", "A" * 30)], policy=policy, seam=seam
    ).decisions[0].replacement
    other = rc.prune_current_results(
        [rc.PrunableResult("t1", "A" * 30)], policy=policy, seam=rc.ArtifactSeam()
    ).decisions[0].replacement
    assert repl == other  # key/preview are pure functions of the inputs
    with pytest.raises(rc.PruneError):
        rc.replay_replacement(repl, rc.ArtifactSeam())  # missing artifact


# ---------------------------------------------------------------------------
# E7.20 — permissionPresets: one logged event updates both knobs
# ---------------------------------------------------------------------------
def test_e720_typed_preset_list_bundles_mode_and_approval_policy():
    presets = rc.preset_list()
    assert isinstance(presets, tuple)
    assert [p.name for p in presets] == ["cautious", "balanced", "trusted"]
    for preset in presets:
        assert isinstance(preset, rc.PermissionPreset)
        assert isinstance(preset.sandbox_mode, rc.SandboxMode)
        assert isinstance(preset.approval_policy, rc.ApprovalPolicy)
        assert preset.description


def test_e720_preset_policy_ladder_is_consistent():
    cautious, balanced, trusted = rc.preset_list()
    assert cautious.sandbox_mode is rc.SandboxMode.STRICT
    assert cautious.approval_policy is rc.ApprovalPolicy.ASK_EVERYTHING
    assert balanced.sandbox_mode is rc.SandboxMode.WORKSPACE
    assert trusted.sandbox_mode is rc.SandboxMode.OFF
    assert trusted.approval_policy is rc.ApprovalPolicy.ALLOW_ALL


def test_e720_switch_writes_exactly_one_event_updating_both_knobs():
    state = rc.initial_state("cautious")
    switch = rc.switch_preset(state, "trusted")
    assert len(switch.events) == 1
    event = switch.event
    assert event.kind == "permission_preset_switched"
    assert event.from_preset == "cautious"
    assert event.to_preset == "trusted"
    assert event.sandbox_mode is rc.SandboxMode.OFF
    assert event.approval_policy is rc.ApprovalPolicy.ALLOW_ALL
    assert switch.state.sandbox_mode is rc.SandboxMode.OFF
    assert switch.state.active_preset == "trusted"


def test_e720_switch_preserves_explicit_user_overrides():
    state = rc.initial_state("trusted")
    state = rc.set_override(state, rc.KNOB_SANDBOX_MODE, "strict")
    state = rc.set_override(state, rc.KNOB_APPROVAL_POLICY, "ask_everything")
    switch = rc.switch_preset(state, "balanced")
    # Both knobs were explicitly overridden, so they survive the preset switch.
    assert switch.state.sandbox_mode is rc.SandboxMode.STRICT
    assert switch.state.approval_policy is rc.ApprovalPolicy.ASK_EVERYTHING
    assert len(switch.event.preserved_overrides) == 2
    assert switch.state.active_preset == "balanced"


def test_e720_partial_override_only_preserves_the_overridden_knob():
    state = rc.set_override(rc.initial_state("trusted"), rc.KNOB_SANDBOX_MODE, "strict")
    switch = rc.switch_preset(state, "balanced")
    assert switch.state.sandbox_mode is rc.SandboxMode.STRICT  # preserved
    assert switch.state.approval_policy is rc.ApprovalPolicy.ASK_OUTSIDE_WORKSPACE  # preset
    assert len(switch.event.preserved_overrides) == 1


def test_e720_clearing_override_lets_preset_take_over_again():
    state = rc.set_override(rc.initial_state("trusted"), rc.KNOB_SANDBOX_MODE, "strict")
    state = rc.clear_override(state, rc.KNOB_SANDBOX_MODE)
    assert state.overrides == ()
    switch = rc.switch_preset(state, "balanced")
    assert switch.state.sandbox_mode is rc.SandboxMode.WORKSPACE


def test_e720_invalid_preset_knob_or_value_fails_closed():
    state = rc.initial_state("balanced")
    with pytest.raises(rc.PresetError):
        rc.switch_preset(state, "yolo")
    with pytest.raises(rc.PresetError):
        rc.set_override(state, "theme", "dark")
    with pytest.raises(rc.PresetError):
        rc.set_override(state, rc.KNOB_SANDBOX_MODE, "yolo")


# ---------------------------------------------------------------------------
# E7.21 — fs-observation-policy: read-before-edit + stale detection
# ---------------------------------------------------------------------------
def _obs(path, content, *, mtime_ns=1, size=None, seq=0):
    return rc.Observation(
        path=path,
        content_hash=rc.hash_content(content.encode("utf-8")),
        mtime_ns=mtime_ns,
        size=len(content) if size is None else size,
        seq=seq,
    )


def test_e721_read_before_edit_blocks_unobserved_path():
    check = rc.check_read_before_edit("src/app.py", {})
    assert check.allowed is False
    assert "read" in check.reason.lower()
    assert check.observation is None


def test_e721_read_before_edit_allows_observed_path():
    obs = _obs("src/app.py", "original")
    check = rc.check_read_before_edit("src/app.py", {"src/app.py": obs})
    assert check.allowed is True
    assert check.observation is obs


def test_e721_stale_detection_by_hash_and_mtime():
    observed = _obs("src/app.py", "v1", mtime_ns=10)
    same = _obs("src/app.py", "v1", mtime_ns=10)
    changed_hash = _obs("src/app.py", "v2", mtime_ns=10)
    new_mtime = _obs("src/app.py", "v1", mtime_ns=11)

    assert rc.detect_stale(observed, same).stale is False
    assert rc.detect_stale(observed, changed_hash).stale is True
    assert rc.detect_stale(observed, new_mtime).stale is True


def test_e721_fs_event_gate_dispatch_on_edit_write_read():
    obs = _obs("a.txt", "v1")
    obs_map = {"a.txt": obs}

    read = rc.fs_event_gate("fs.read", "a.txt", observations=obs_map)
    assert read.allowed is True

    edit = rc.fs_event_gate("fs.edit", "a.txt", observations=obs_map)
    assert edit.allowed is True

    missing = rc.fs_event_gate("fs.edit", "b.txt", observations=obs_map)
    assert missing.allowed is False

    stale = rc.fs_event_gate(
        "fs.write", "a.txt", observations=obs_map,
        observed=obs, current=_obs("a.txt", "v2", mtime_ns=12),
    )
    assert stale.allowed is False
    assert stale.stale is True


def test_e721_observation_policy_does_no_fs_io():
    verdict = rc.fs_event_gate("fs.read", "a.txt")
    assert verdict.io_performed is False
    assert rc.check_read_before_edit("a.txt", {}).io_performed is False
    assert rc.detect_stale(_obs("a.txt", "x"), _obs("a.txt", "y")).io_performed is False


def test_e721_hash_content_is_pure_and_content_sensitive():
    assert rc.hash_content(b"same") == rc.hash_content(b"same")
    assert rc.hash_content(b"a") != rc.hash_content(b"b")


def test_e721_unknown_fs_event_fails_closed():
    with pytest.raises(rc.ObservationError):
        rc.fs_event_gate("fs.exec", "a.txt")


# ---------------------------------------------------------------------------
# E7.23 — web seam: one service, stable tool names, free backends only
# ---------------------------------------------------------------------------
def test_e723_default_service_registers_search_and_fetch_providers():
    service = rc.default_web_service()
    assert service.resolve(rc.ProviderKind.SEARCH).name == "searxng"
    assert service.resolve(rc.ProviderKind.FETCH).name == "plain-http"
    assert service.tool_names() == frozenset({rc.WEB_SEARCH_TOOL, rc.WEB_FETCH_TOOL})


def test_e723_tool_names_stay_stable_after_provider_swap():
    service = rc.default_web_service()
    alt = rc.WebProvider("brave-free", rc.ProviderKind.SEARCH, "free-search-api",
                         rc.WEB_SEARCH_TOOL)
    service.register(alt)
    descriptor = service.invoke(rc.ProviderKind.SEARCH, "brave-free", query="keel")
    assert descriptor.tool_name == rc.WEB_SEARCH_TOOL
    assert descriptor.provider == "brave-free"
    assert rc.WEB_SEARCH_TOOL in service.tool_names()


def test_e723_paid_or_unstable_providers_are_rejected():
    service = rc.WebService()
    with pytest.raises(rc.WebSeamError):
        service.register(rc.WebProvider("paid", rc.ProviderKind.SEARCH, "paid-api",
                                        rc.WEB_SEARCH_TOOL, free=False))
    with pytest.raises(rc.WebSeamError):
        service.register(rc.WebProvider("paid2", rc.ProviderKind.SEARCH, "paid-api",
                                        rc.WEB_SEARCH_TOOL, paid_only=True))
    with pytest.raises(rc.WebSeamError):
        service.register(rc.WebProvider("bad", rc.ProviderKind.FETCH, "x",
                                        "custom_fetch_tool"))


def test_e723_unknown_provider_and_kind_fail_closed():
    service = rc.default_web_service()
    with pytest.raises(rc.WebSeamError):
        service.resolve(rc.ProviderKind.SEARCH, "missing")
    with pytest.raises(rc.WebSeamError):
        service.resolve("crawl")


def test_e723_web_descriptors_never_perform_network():
    descriptor = rc.default_web_service().invoke(rc.ProviderKind.FETCH, url="https://x")
    assert descriptor.network is False
    assert descriptor.io_performed is False
    assert descriptor.params == (("url", "https://x"),)


def test_e723_registration_is_idempotent_and_conflicts_rejected():
    service = rc.WebService()
    p = rc.WebProvider("searxng", rc.ProviderKind.SEARCH, "searxng", rc.WEB_SEARCH_TOOL)
    service.register(p)
    service.register(p)  # same descriptor -> idempotent
    with pytest.raises(rc.WebSeamError):
        service.register(rc.WebProvider("searxng", rc.ProviderKind.SEARCH, "other",
                                         rc.WEB_SEARCH_TOOL))


# ---------------------------------------------------------------------------
# E7.6 — workspaceFiles: descriptors + path containment, no FS I/O
# ---------------------------------------------------------------------------
def test_e76_containment_allows_in_root_and_rejects_traversal():
    root = "/work/project"
    assert rc.contained_path(root, "src/app.py") == "/work/project/src/app.py"
    assert rc.contained_path(root, root + "/notes.txt") == "/work/project/notes.txt"
    with pytest.raises(rc.WorkspacePathError):
        rc.contained_path(root, "../secret.txt")
    with pytest.raises(rc.WorkspacePathError):
        rc.contained_path(root, "/etc/passwd")
    with pytest.raises(rc.WorkspacePathError):
        rc.contained_path(root, "a/../../escape")


def test_e76_sibling_prefix_is_not_contained():
    with pytest.raises(rc.WorkspacePathError):
        rc.contained_path("/work/proj", "/work/project/secret.txt")


def test_e76_stat_descriptor_is_typed_and_contained():
    stat = rc.stat_descriptor("/work", "a.txt", size=12, kind="file", mtime_ns=5)
    assert isinstance(stat, rc.FileStat)
    assert stat.path == "/work/a.txt"
    assert stat.size == 12 and stat.kind == "file"
    assert stat.io_performed is False


def test_e76_paged_text_is_deterministic_and_bounded():
    text = "\n".join(f"line{i}" for i in range(25))
    root = "/work"
    p0 = rc.paged_text(root, "a.txt", text, page=0, page_size=10)
    p2 = rc.paged_text(root, "a.txt", text, page=2, page_size=10)
    assert p0.lines == tuple(f"line{i}" for i in range(10))
    assert p0.total_lines == 25 and p0.has_more is True
    assert p2.lines == ("line20", "line21", "line22", "line23", "line24")
    assert p2.has_more is False
    assert p0 == rc.paged_text(root, "a.txt", text, page=0, page_size=10)


def test_e76_byte_window_slices_exact_range():
    data = bytes(range(256))
    window = rc.byte_window("/work", "bin.dat", data, offset=10, length=5)
    assert isinstance(window, rc.ByteWindow)
    assert bytes(window.data) == bytes(range(10, 15))
    assert window.total_bytes == 256
    assert window.offset == 10 and window.length == 5


def test_e76_byte_window_clamps_and_reports_truncation():
    data = b"abcdef"
    window = rc.byte_window("/work", "bin.dat", data, offset=4, length=10)
    assert bytes(window.data) == b"ef"
    assert window.truncated is True


def test_e76_directory_listing_is_typed_and_contained():
    entries = [("a.txt", "file", 3), ("src", "dir", 0)]
    listing = rc.directory_listing("/work", ".", entries)
    assert isinstance(listing, rc.DirectoryListing)
    assert listing.path == "/work"
    assert [e.name for e in listing.entries] == ["a.txt", "src"]
    assert all(isinstance(e, rc.DirEntry) for e in listing.entries)


def test_e76_change_feed_is_ordered_by_seq():
    events = [
        rc.ChangeEvent(seq=2, path="/work/b.txt", kind="modified", mtime_ns=20),
        rc.ChangeEvent(seq=1, path="/work/a.txt", kind="created", mtime_ns=10),
    ]
    feed = rc.change_feed(events)
    assert [e.seq for e in feed] == [1, 2]
    assert feed[0].kind == "created"


def test_e76_all_file_descriptors_report_no_io_and_no_network():
    stat = rc.stat_descriptor("/work", "a.txt", size=1, kind="file")
    page = rc.paged_text("/work", "a.txt", "one\ntwo", page_size=1)
    win = rc.byte_window("/work", "a.txt", b"ab")
    listing = rc.directory_listing("/work", ".", [])
    assert all(d.io_performed is False for d in (stat, page, win, listing))
    assert all(d.network is False for d in (stat, page, win, listing))
