"""Added behavioural regressions for previously descriptor-only backend IDs.

These tests are **additive**: none replaces an existing test.  They target the
ID -> implementation mappings that the old descriptor-only tests merely
counted (``FEATURE_BEHAVIORS``, ``FEATURE_IMPLEMENTATIONS``, ``FEATURE_IDS`` /
``FEATURE_SURFACES``), resolve the *real* symbol through the mapping and execute
it with concrete inputs, pinning an exact output or typed error.

Each test is a mutation guard: replacing its target implementation with a no-op
(or a constant-returning stub) changes the asserted concrete value and fails
the test.  See the mutation-check record in the commit message.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from keel import e7_runtime_backend as e7
from keel import small_groups_backend as sg
from keel import x2_orchestration_backend as x2
from keel import y1_config_backend as y1
from keel import y4_d4_x7_backend as y4


def _y4_symbol(feature_id: str, name: str):
    """Resolve a real symbol *through* the FEATURE_BEHAVIORS ID mapping."""
    assert name in y4.FEATURE_BEHAVIORS[feature_id]
    return getattr(y4, name)


# ---------------------------------------------------------------------------
# Y4 / D4 / X7 -- dispatch through FEATURE_BEHAVIORS
# ---------------------------------------------------------------------------


def test_y4_1_behavior_map_executes_reviver_state_transition():
    reviver_cls = _y4_symbol("Y4.1", "McpServerReviver")
    reviver = reviver_cls(["wiki"], probe_interval_s=300)
    assert reviver.phase("wiki") is y4.ServerPhase.ACTIVE
    assert reviver.mark_dormant("wiki") is y4.ServerPhase.DORMANT
    revived = reviver.reload("wiki")
    assert (revived.instant, revived.phase, "revived" in revived.detail) == (
        True, y4.ServerPhase.ACTIVE, True)


def test_y4_5_behavior_map_executes_bridge_keyed_wake_and_sequence():
    bridge_cls = _y4_symbol("Y4.5", "SupervisedBridge")
    bridge = bridge_cls()
    with pytest.raises(y4.BackendError):
        bridge.deliver({"event": "ping"})
    bridge.start("https://tunnel.example/hook", key="k")
    assert bridge.wake_if_keyed("wrong") is False
    assert bridge.wake_if_keyed("k") is True
    first = bridge.deliver({"event": "ping"})
    second = bridge.deliver({"event": "ping"})
    assert (first["seq"], second["seq"], len(first["id"])) == (1, 2, 12)


def test_d4_13_behavior_map_executes_port_selection_and_conflict():
    select_port = _y4_symbol("D4.13", "select_port")
    port_mode = _y4_symbol("D4.13", "PortMode")
    desktop = select_port(port_mode.DESKTOP)
    assert (desktop.port, desktop.source) == (0, "os_assigned")
    conflict = select_port(port_mode.WEB, occupied=[8739])
    assert conflict.conflict is True
    assert "already in use" in conflict.message


def test_x7_1_behavior_map_executes_target_matrix_verification():
    verify = _y4_symbol("X7.1", "verify_target_matrix")
    targets = _y4_symbol("X7.1", "BUILD_TARGETS")
    assert verify(targets) == ()
    issues = verify([y4.PlatformTarget("linux", "arm64")])
    assert len(issues) == 6
    assert {i.code for i in issues} == {"missing_build_target"}


def test_x7_8_behavior_map_executes_download_integrity_tamper_detection():
    verify_download = _y4_symbol("X7.8", "verify_download")
    data = b"installer-bytes"
    digest = hashlib.sha256(data).hexdigest()
    ok = verify_download(data, digest, filename="keel.exe", expected_size=len(data))
    assert (ok.ok, ok.reason) == (True, "integrity verified")
    assert verify_download(data, "0" * 64).reason == "sha256 mismatch"
    assert verify_download(data, digest, expected_size=1).reason == "size mismatch"


# ---------------------------------------------------------------------------
# Small groups -- dispatch through FEATURE_IMPLEMENTATIONS
# ---------------------------------------------------------------------------


def test_w5_5_registry_dispatch_pins_model_precedence():
    resolve = sg.FEATURE_IMPLEMENTATIONS["W5.5"]
    assert resolve("cli", "agent", "session") == "cli"
    assert resolve(None, "agent", "session") == "agent"
    assert resolve(None, None, "session") == "session"
    assert resolve() is None


def test_x9_6_registry_dispatch_pins_pseudo_localization():
    localize = sg.FEATURE_IMPLEMENTATIONS["X9.6"]
    assert localize("Hello world") == "\u27e6H\u00e9ll\u00f3 w\u00f3rld\u27e7"
    assert localize("Hello world", expand=False) == "H\u00e9ll\u00f3 w\u00f3rld"


def test_y6_3_registry_dispatch_pins_repo_surface_gate():
    descriptor = sg.FEATURE_IMPLEMENTATIONS["Y6.3"]
    good = descriptor("Cowork, Code, Duet and Fleet in one app",
                      "https://keel-desktop.vercel.app")
    assert (good["valid"], good["surfaces"]) == (
        True, ["Cowork", "Code", "Duet", "Fleet"])
    bad = descriptor("Only Cowork and Code", "https://elsewhere.test")
    assert bad["valid"] is False
    assert set(bad["missing_surfaces"]) == {"Duet", "Fleet"}


# ---------------------------------------------------------------------------
# X2 -- dispatch through the FEATURE_IDS index
# ---------------------------------------------------------------------------


def test_x2_7_feature_index_executes_test_summary_pipeline():
    assert "X2.7" in x2.FEATURE_IDS
    raw = ("\x1b[31mFAILED tests/test_a.py::test_x - AssertionError\x1b[0m\n"
           "1 failed, 5 passed, 2 skipped in 0.4s\n")
    summary = x2.summarize(raw, "pytest")
    assert (summary.runner, summary.failed, summary.passed, summary.skipped) == (
        "pytest", 1, 5, 2)
    digest = summary.failure_digest()
    assert "test_x" in digest and "\x1b" not in digest
    assert x2.strip_ansi("\x1b[1mhello\x1b[0m") == "hello"
    assert x2.detect_runner("garbage", "unknown") == "unknown"


def test_x2_13_feature_index_executes_monorepo_affected_graph():
    assert "X2.13" in x2.FEATURE_IDS
    graph = x2.MonorepoGraph({
        "pkg": {"paths": ["packages/pkg"], "depends_on": [], "test_command": "pytest pkg"},
        "pkg2": {"paths": ["packages/pkg2"], "depends_on": ["pkg"], "test_command": "pytest pkg2"},
        "app": {"paths": ["apps/app"], "depends_on": ["pkg2"], "test_command": "pytest app"},
        "other": {"paths": ["apps/other"], "depends_on": [], "test_command": "pytest other"},
    })
    assert graph.affected(["packages/pkg/mod.py"]) == ["app", "pkg", "pkg2"]
    assert graph.package_for_path("packages/pkg2/mod.py") == "pkg2"
    with pytest.raises(x2.BackendError):
        x2.MonorepoGraph({"a": {"depends_on": ["b"]}, "b": {"depends_on": ["a"]}})


# ---------------------------------------------------------------------------
# E7 -- dispatch through FEATURE_SURFACES
# ---------------------------------------------------------------------------


def test_e7_1_feature_surface_executes_token_meter_replay():
    assert "E7.1" in e7.FEATURE_SURFACES
    meter = e7.TokenMeter()
    first = meter.fold("s1", 10, 2)
    second = meter.fold("s1", 3, 4)
    assert (first.revision, first.total_tokens) == (1, 12)
    assert (second.revision, second.total_tokens) == (2, 19)
    assert second == meter.replay("s1")
    with pytest.raises(e7.ValidationError):
        meter.fold("s1", -1, 0)


def test_e7_30_feature_surface_executes_auth_flow_single_attempt():
    assert "E7.30" in e7.FEATURE_SURFACES
    registry = e7.AuthFlowRegistry()
    registry.register("creds.json", "oauth-plugin", "digest-1")
    attempt = registry.begin("creds.json")
    with pytest.raises(e7.FlowBusyError):
        registry.begin("creds.json")
    with pytest.raises(e7.ValidationError):
        registry.complete("creds.json", "sk-abcdefghijklmnopqrstuvwxyz")
    result = registry.complete("creds.json", "vault://ref/1")
    assert (attempt, result.attempt, result.credential_ref) == (
        "attempt-1", "attempt-1", "vault://ref/1")


# ---------------------------------------------------------------------------
# Y1 -- concrete behaviour assertions for descriptor-adjacent IDs
# ---------------------------------------------------------------------------


def test_y1_1_code_mode_descriptor_filters_and_guards_script():
    desc = y1.code_mode_descriptor(
        ["read", "mcp__evil__x", "mcp__good__y"],
        server_switches={"evil": False, "good": True})
    assert (desc.available, desc.tools, desc.fetch, desc.fallback) == (
        True, ("read", "mcp__good__y"), True, "")
    denied = y1.code_mode_descriptor(["read"], denied=True)
    assert (denied.available, denied.tools, denied.fetch, denied.fallback) == (
        False, (), False, "tool_list")
    with pytest.raises(y1.CodeModeError) as ei:
        y1.validate_code_script("eval('1+1')")
    assert ei.value.code == "unsafe_token"


def test_y1_14_browser_transfer_gate_returns_concrete_cap():
    assert y1.validate_browser_transfer_size(5 * 1024 * 1024) == 5 * 1024 * 1024
    with pytest.raises(y1.BrowserContractError) as ei:
        y1.validate_browser_transfer_size(5 * 1024 * 1024 + 1)
    assert ei.value.code == "out_of_range"
