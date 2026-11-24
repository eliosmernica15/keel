"""Production-hardening regressions for MCP, plugins and extensions.

Scope of this suite:

* contract-level trust boundaries (manifest validation, forbidden capabilities,
  unsigned extensions, SSRF-safe server URLs, protocol compatibility);
* the permission gate: native tools and discovered MCP capabilities must use
  the *same* ordered-rule evaluator, with no self-granting at discovery time;
* runtime lifecycle (failure, reconnect, disable, cleanup) exercised against
  the real ``keel.mcp`` manager with in-process fakes -- no real network and
  no real subprocess is spawned by these tests.

Every test is deterministic and stdlib-only.  The module never imports or
executes a plugin/manifest implementation; ``implementation`` strings stay
inert data, as in the contracts themselves.
"""

from __future__ import annotations

import collections
import json

import pytest

import keel.mcp as runtime_mcp
import keel.permissions as runtime_permissions
import keel.plugin_contracts as pc
from keel import mcp_contracts as mc
from keel.mcp import McpManager, McpServer, McpServerConfig


# ---------------------------------------------------------------------------
# helpers for the lifecycle tests (in-process, no OS process is created)
# ---------------------------------------------------------------------------


def _rpc(req_id: int, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n"


def _rpc_error(req_id: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id,
                       "error": {"code": -32603, "message": message}}) + "\n"


class _FakeStdio:
    def __init__(self, lines=()):
        self._lines = collections.deque(lines)
        self.closed = False

    def write(self, _data):
        if self.closed:
            raise OSError("stdin closed")

    def flush(self):
        if self.closed:
            raise OSError("stdin closed")

    def readline(self):
        return self._lines.popleft() if self._lines else ""

    def close(self):
        self.closed = True


class _FakeProc:
    def __init__(self, lines=(), *, exit_code=None):
        self.stdin = _FakeStdio()
        self.stdout = _FakeStdio(lines)
        self._rc = exit_code
        self.killed = False

    def poll(self):
        return self._rc

    def kill(self):
        self.killed = True
        self._rc = -9


# ===========================================================================
# 1. Permission escalation: the ask rule must NOT be widened to allow
# ===========================================================================


def test_config_ask_is_not_escalated_to_allow_without_policy_rules():
    """A discovered capability carrying `ask` must stay `ask`.

    Before the fix ``evaluate_permissions`` used ``default="allow"`` for the
    policy layer; with no policy rules that produced an implicit allow which
    silently overrode a config `ask`.  That is a real privilege escalation.
    """
    rules = [mc.PermissionRule("mcp.github.*", "*", "ask")]
    assert mc.evaluate_permissions(
        config_rules=rules, policy_rules=[],
        action="mcp.github.read_file", resource="*",
    ) == "ask"


def test_config_ask_survives_an_unrelated_policy_rule():
    rules = [mc.PermissionRule("mcp.github.*", "*", "ask")]
    policy = [mc.PermissionRule("mcp.other.*", "*", "allow")]
    assert mc.evaluate_permissions(
        config_rules=rules, policy_rules=policy,
        action="mcp.github.read_file", resource="*",
    ) == "ask"


def test_explicit_policy_ask_is_not_downgraded_by_config_allow():
    config = [mc.mcp_permission_rule("github", "push", effect="allow")]
    policy = [mc.PermissionRule("mcp.github.push", "*", "ask")]
    assert mc.evaluate_permissions(
        config_rules=config, policy_rules=policy,
        action="mcp.github.push", resource="*",
    ) == "ask"


def test_explicit_deny_still_wins_in_either_layer():
    config = [mc.mcp_permission_rule("github", "push", effect="allow")]
    policy = [mc.block_extension("mcp", "github")]
    assert mc.evaluate_permissions(
        config_rules=config, policy_rules=policy,
        action="mcp.github.push", resource="*",
    ) == "deny"
    config_deny = [mc.mcp_permission_rule("github", "push", effect="deny")]
    policy_allow = [mc.PermissionRule("mcp.github.push", "*", "allow")]
    assert mc.evaluate_permissions(
        config_rules=config_deny, policy_rules=policy_allow,
        action="mcp.github.push", resource="*",
    ) == "deny"


# ===========================================================================
# 2. Error isolation and typed failures in the permission gate
# ===========================================================================


@pytest.mark.parametrize("bad_rule", [
    {"action": "mcp.x.*"},                       # missing resource/effect
    {"action": "mcp.x.*", "resource": "*"},      # missing effect
    {"resource": "*", "effect": "allow"},        # missing action
    "not-a-rule",
    42,
])
def test_malformed_rules_raise_typed_permission_error(bad_rule):
    """A malformed rule must not leak a raw KeyError/TypeError into a session."""
    with pytest.raises(mc.PermissionRuleError):
        mc.evaluate_permissions(
            config_rules=[mc.PermissionRule("mcp.ok.*", "*", "allow"), bad_rule],
            action="mcp.ok.read", resource="*",
        )


def test_rule_timeout_is_type_checked():
    with pytest.raises(mc.PermissionRuleError):
        mc.PermissionRule("mcp.x.*", "*", "allow", timeout_seconds="30")
    with pytest.raises(mc.PermissionRuleError):
        mc.PermissionRule("mcp.x.*", "*", "allow", timeout_seconds=0)
    assert mc.PermissionRule("mcp.x.*", "*", "allow", timeout_seconds=5).timeout_seconds == 5


def test_plugin_part_from_dict_raises_typed_error():
    """Malformed descriptor data must fail as PartDescriptorError, not ValueError."""
    with pytest.raises(pc.PartDescriptorError):
        pc.PluginPart.from_dict({"id": "x", "kind": "not-a-kind"})
    with pytest.raises(pc.PartDescriptorError):
        pc.PluginPart.from_dict({"id": "x", "config": []})


# ===========================================================================
# 3. Compatibility / version checks
# ===========================================================================


def test_protocol_version_compatibility():
    assert mc.check_protocol_compatibility("2024-11-05") == "2024-11-05"
    with pytest.raises(mc.McpCompatibilityError):
        mc.check_protocol_compatibility("1999-01-01")
    with pytest.raises(mc.McpCompatibilityError):
        mc.check_protocol_compatibility("../../etc/passwd")
    with pytest.raises(mc.McpCompatibilityError):
        mc.check_protocol_compatibility(123)


def test_protocol_version_policy_seam():
    with pytest.raises(mc.McpCompatibilityError):
        mc.check_protocol_compatibility(
            "2024-11-05", policy=lambda version, kind: False)


# ===========================================================================
# 4. SSRF via MCP server URL
# ===========================================================================


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://127.0.0.1:8080/admin",
    "http://[::1]/",
    "http://10.0.0.5/internal",
    "http://192.168.1.1/",
    "file:///etc/passwd",
    "http://user:secret@public.example/",
    "https://public.example/#fragment",
    "",
])
def test_mcp_server_url_blocks_ssrf_targets(url):
    with pytest.raises(mc.McpUrlError):
        mc.validate_mcp_server_url(url)


def test_mcp_server_url_allows_explicit_public_endpoint():
    parsed = mc.validate_mcp_server_url("https://mcp.example.com:443/v1")
    assert parsed.scheme == "https"
    assert parsed.host == "mcp.example.com"
    assert parsed.private is False


def test_mcp_server_url_explicit_allowlist_and_policy():
    parsed = mc.validate_mcp_server_url(
        "https://internal.example/", allowed_hosts=["internal.example"])
    assert parsed.host == "internal.example"
    with pytest.raises(mc.McpUrlError):
        mc.validate_mcp_server_url(
            "https://other.example/", allowed_hosts=["internal.example"])
    with pytest.raises(mc.McpUrlError):
        mc.validate_mcp_server_url(
            "https://public.example/", policy=lambda url, kind: False)


# ===========================================================================
# 5. Discovery: no self-granting, forbidden capabilities, name collisions
# ===========================================================================


def test_discovered_capabilities_do_not_self_grant():
    tools = [{"name": "delete_all", "description": "dangerous",
              "inputSchema": {"type": "object"}}]
    # No rule at all: fail closed.
    denied = mc.register_discovered_capabilities("evil", tools,
                                                 config_rules=[], policy_rules=[])
    assert [c.decision for c in denied] == ["deny"]
    assert not any(c.exposed for c in denied)

    # A native-tool allow must not grant an MCP capability.
    native_only = mc.register_discovered_capabilities(
        "evil", tools,
        config_rules=[mc.tool_use_rule("shell", "*", "allow")],
        policy_rules=[],
    )
    assert not native_only[0].exposed
    assert native_only[0].action == "mcp.evil.delete_all"

    # Only an explicit MCP rule exposes it; `ask` stays unexposed.
    allowed = mc.register_discovered_capabilities(
        "evil", tools,
        config_rules=[mc.mcp_permission_rule("evil", "delete_all")],
    )
    assert allowed[0].exposed is True
    asked = mc.register_discovered_capabilities(
        "evil", tools,
        config_rules=[mc.mcp_permission_rule("evil", "delete_all", effect="ask")],
    )
    assert asked[0].decision == "ask" and asked[0].exposed is False


def test_discovered_forbidden_capability_is_never_exposed():
    tools = [{"name": "sampling", "inputSchema": {}},
             {"name": "echo", "inputSchema": {}}]
    caps = mc.register_discovered_capabilities(
        "srv", tools,
        config_rules=[mc.PermissionRule("mcp.srv.*", "*", "allow")],
        forbidden={"sampling"},
    )
    by_tool = {c.tool: c for c in caps}
    assert by_tool["sampling"].decision == "deny"
    assert by_tool["sampling"].exposed is False
    assert by_tool["echo"].exposed is True


def test_malformed_discovery_entries_are_isolated():
    tools = [{"name": "ok", "inputSchema": {}}, "junk", {}, {"name": ""}]
    caps = mc.register_discovered_capabilities(
        "srv", tools, config_rules=[mc.mcp_permission_rule("srv", "*")])
    assert [c.tool for c in caps] == ["ok"]


def test_permission_name_collision_is_rejected():
    with pytest.raises(mc.PermissionRuleError):
        mc.assert_unique_mcp_permissions([("a/b", "tool"), ("a_b", "tool")])
    # Distinct canonical names are accepted.
    assert mc.assert_unique_mcp_permissions(
        [("github", "read_file"), ("github", "write_file")]) == (
            "mcp.github.read_file", "mcp.github.write_file")


# ===========================================================================
# 6. Malicious manifests, forbidden capabilities and unsigned extensions
# ===========================================================================


def _valid_manifest(**overrides):
    base = {
        "id": "github-mcp",
        "version": "1.2.3",
        "kind": "mcp",
        "publisher": "trusted-vendor",
        "trust": "signed",
        "signature": "deadbeefcafe1234",
        "capabilities": ["tools", "resources"],
        "dependencies": [],
    }
    base.update(overrides)
    return base


def test_valid_signed_manifest():
    manifest = pc.validate_extension_manifest(
        _valid_manifest(), trusted_publishers=["trusted-vendor"])
    assert manifest.id == "github-mcp"
    assert manifest.capabilities == ("tools", "resources")
    assert "signature" not in manifest.to_dict()["capabilities"]


@pytest.mark.parametrize("manifest,code", [
    ({"id": "evil; rm -rf /", "version": "1.0.0"}, "bad_id"),
    ({"id": "../escape"}, "bad_id"),
    ({"version": "latest"}, "bad_version"),
    ({"kind": "kernel-module"}, "bad_kind"),
    ({"capabilities": ["tools", "sampling"]}, "forbidden_capability"),
    ({"capabilities": ["tools", "EXEC"]}, "forbidden_capability"),
    ({"command": "python server.py; curl evil"}, "unsafe_command"),
    ({"dependencies": ["github-mcp"]}, "self_dependency"),
])
def test_malicious_manifest_is_rejected(manifest, code):
    with pytest.raises(pc.ManifestError) as ei:
        pc.validate_extension_manifest(_valid_manifest(**manifest))
    assert ei.value.code == code


@pytest.mark.parametrize("overrides", [
    {"trust": "untrusted"},
    {"trust": "signed", "signature": ""},
    {"trust": "signed", "signature": None},
])
def test_unsigned_or_untrusted_extension_is_rejected(overrides):
    with pytest.raises(pc.ExtensionTrustError):
        pc.validate_extension_manifest(_valid_manifest(**overrides))


def test_untrusted_publisher_is_rejected():
    with pytest.raises(pc.ExtensionTrustError):
        pc.validate_extension_manifest(
            _valid_manifest(), trusted_publishers=["another-vendor"])


def test_manifest_policy_can_deny():
    with pytest.raises(pc.ExtensionTrustError):
        pc.validate_extension_manifest(
            _valid_manifest(), policy=lambda manifest, kind: False)


# ===========================================================================
# 7. Dependency validation in the plugin registry
# ===========================================================================


def test_registry_rejects_unknown_and_cyclic_dependencies():
    registry = pc.default_registry()
    broken = pc.PluginPart(
        id="broken", kind=pc.PartKind.TOOL_REGISTRY,
        implementation="pkg:Tool", tier=pc.ServiceTier.EXTENSION,
        dependencies=("does-not-exist",))
    registry.register(broken)
    with pytest.raises(pc.DependencyError):
        registry.validate_dependencies()

    cyc = pc.default_registry()
    cyc.register(pc.PluginPart(
        id="a", kind=pc.PartKind.MODEL_ADAPTER, implementation="pkg:a",
        tier=pc.ServiceTier.EXTENSION, dependencies=("b",)))
    cyc.register(pc.PluginPart(
        id="b", kind=pc.PartKind.MODEL_ADAPTER, implementation="pkg:b",
        tier=pc.ServiceTier.EXTENSION, dependencies=("a",)))
    with pytest.raises(pc.DependencyError):
        cyc.validate_dependencies()


def test_registry_validates_canonical_dependencies():
    assert isinstance(pc.default_registry().validate_dependencies(), tuple)


# ===========================================================================
# 8. Permission parity probe: native tools and MCP capabilities share a gate
# ===========================================================================


def test_permission_parity_probe_native_and_mcp_capability():
    """One gate, two names.  Both tool classes are decided by the same rules.

    The probe checks both layers:

    * contract layer -- ``mc.evaluate_permissions`` is the single evaluator
      used for ``tool.use`` and ``mcp.<server>.<tool>`` actions;
    * production layer -- ``keel.permissions.evaluate`` receives the MCP
      mapped name ``mcp__server__tool`` and a native name through the exact
      same function; an explicit deny wins for both, and an unmapped MCP
      capability fails closed even in ``bypassPermissions`` mode.
    """
    deny_native = mc.tool_use_rule("shell", "git push", "deny")
    ask_mcp = mc.mcp_permission_rule("github", "push", effect="ask")
    rules = [deny_native, ask_mcp]

    native = mc.evaluate_permissions(
        config_rules=rules, action="tool.use", resource="shell:git push")
    capability = mc.evaluate_permissions(
        config_rules=rules, action="mcp.github.push", resource="*")
    assert native == "deny"
    assert capability == "ask"  # would have been "allow" before the fix

    deny_rules, _ = runtime_permissions.parse_rules(
        "deny", ["run_shell", "mcp__github__push"])
    _, ask_rules = runtime_permissions.parse_rules(
        "ask", ["mcp__github__push"])
    native_runtime = runtime_permissions.evaluate(
        tool_name="run_shell", tool_input={"command": "git push"},
        rules=(deny_rules, [], []), mode="bypassPermissions",
        interactive=True)
    mcp_runtime = runtime_permissions.evaluate(
        tool_name="mcp__github__push", tool_input={},
        rules=(deny_rules, ask_rules, []), mode="bypassPermissions",
        interactive=True)
    assert native_runtime.decision == "deny"
    assert mcp_runtime.decision == "deny"  # deny rules beat ask and bypass

    unmapped = runtime_permissions.evaluate(
        tool_name="mcp__github__push", tool_input={},
        rules=([], [], []), mode="bypassPermissions", interactive=True)
    assert unmapped.decision == "deny"  # no self-granting at discovery time


# ===========================================================================
# 9. Lifecycle: failure, reconnect, disable while connected, cleanup
# ===========================================================================


def test_server_start_failure_kills_process_and_is_isolated(monkeypatch):
    proc = _FakeProc([_rpc_error(1, "initialize refused")])
    monkeypatch.setattr(runtime_mcp.subprocess, "Popen", lambda *a, **k: proc)
    client = McpServer(McpServerConfig(name="bad", command="unused"), timeout=1.0)
    with pytest.raises(runtime_mcp.McpError):
        client.start()
    assert proc.killed is True
    assert client.running is False
    assert client.health() is False


def test_server_reconnect_after_failure(monkeypatch):
    bad = _FakeProc([_rpc_error(1, "temporary outage")])
    good_lines = [
        _rpc(1, {"capabilities": {"tools": {}}}),
        _rpc(2, {"tools": [{"name": "ping", "inputSchema": {}}]}),
    ]
    good = _FakeProc(good_lines)
    procs = iter([bad, good])
    monkeypatch.setattr(runtime_mcp.subprocess, "Popen", lambda *a, **k: next(procs))
    client = McpServer(McpServerConfig(name="flaky", command="unused"), timeout=1.0)
    with pytest.raises(runtime_mcp.McpError):
        client.start()
    assert client.reconnect() is True
    assert client.running is True
    assert [t["name"] for t in client.tools] == ["ping"]
    client.shutdown()
    assert client.running is False
    assert good.killed is True


def test_disable_while_connected_excludes_discovery_and_cleans_up(monkeypatch):
    """A disabled server is not started again; active clients are shut down."""
    good_lines = [
        _rpc(1, {"capabilities": {"tools": {}}}),
        _rpc(2, {"tools": [{"name": "ping", "inputSchema": {}}]}),
    ]
    monkeypatch.setattr(
        runtime_mcp.subprocess, "Popen",
        lambda *a, **k: _FakeProc(list(good_lines)),
    )
    selection = mc.parse_plugin_dsl("active -disabled")
    configured = ["disabled", "active"]
    enabled = selection.enabled(configured)
    assert enabled == ["active"]

    manager = McpManager([McpServerConfig(name=name, command="unused")
                          for name in enabled])
    statuses = manager.start_all()
    assert [s["name"] for s in statuses] == ["active"]
    assert "disabled" not in manager._clients

    # Simulate a connection opened before the disable decision.
    class _TrackedClient:
        def __init__(self, name):
            self.config = McpServerConfig(name=name, command="unused")
            self.shutdown_called = False

        def shutdown(self):
            self.shutdown_called = True

    stale = _TrackedClient("disabled")
    manager._clients["disabled"] = stale
    manager.shutdown_all()
    assert stale.shutdown_called is True
    assert manager._clients == {}


def test_shutdown_is_error_isolated_and_idempotent():
    """One failing shutdown must not leak the other clients or raise."""
    calls = []

    class _Boom:
        config = McpServerConfig(name="boom", command="unused")

        def shutdown(self):
            calls.append("boom")
            raise RuntimeError("cleanup failed")

    class _Good:
        config = McpServerConfig(name="good", command="unused")

        def shutdown(self):
            calls.append("good")

    manager = McpManager([])
    manager._clients = {"boom": _Boom(), "good": _Good()}
    manager.shutdown_all()  # must not raise
    assert set(calls) == {"boom", "good"}
    assert manager._clients == {}

    proc = _FakeProc([])
    client = McpServer(McpServerConfig(name="x", command="unused"))
    client._proc = proc
    client.shutdown()
    client.shutdown()  # idempotent
    assert proc.killed is True
    assert proc.stdin.closed is True


# ===========================================================================
# 10. Secret handling in configs
# ===========================================================================


def test_substituted_secret_is_redacted_before_dump():
    config = {
        "mcpServers": {"srv": {"headers": {
            "Authorization": "Bearer {env:KEEL_API_TOKEN}"}}},
        "note": "sk-abcdefghijklmnop",
    }
    result = mc.substitute_config(config, env={"KEEL_API_TOKEN": "s3cret-token"})
    assert result.value["mcpServers"]["srv"]["headers"][
        "Authorization"] == "Bearer s3cret-token"
    assert any(w.kind == "secret_reference" for w in result.warnings)
    assert all("s3cret-token" not in str(w.to_dict()) for w in result.warnings)

    redacted = pc.redact_config(result.value)
    assert "s3cret-token" not in json.dumps(redacted)
    assert "sk-abcdefghijklmnop" not in json.dumps(redacted)
    with pytest.raises(pc.SecretLeakError):
        pc.assert_no_secrets(json.dumps(result.value), secrets=["s3cret-token"])
