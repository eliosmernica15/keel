"""D3.x P0 capability seams — descriptor/policy layer (no I/O, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keel import capability_seams as cs

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# registry coverage / aggregate
# ---------------------------------------------------------------------------
def test_feature_ids_match_all_p0_not_started_d3_rows():
    registry = json.loads((REPO / "PLAN-INDEX.json").read_text(encoding="utf-8"))
    expected = {f["id"] for f in registry["features"]
                if f["id"].startswith("D3.")
                and f.get("priority") == "P0"
                and f.get("status") == "not_started"}
    assert expected == set(cs.FEATURE_IDS)
    assert len(cs.FEATURE_IDS) == 10


def test_aggregate_descriptors_are_descriptor_only():
    rows = cs.all_p0_descriptors()
    assert set(rows) == set(cs.FEATURE_IDS)
    for row in rows.values():
        assert row["layer"] == "descriptor_only"
        assert row["io_performed"] is False
        assert row["network"] is False
        assert row["runtime_claimed"] is False
        assert row["contract"]


# ---------------------------------------------------------------------------
# D3.1 — three roles, typed registration, role exclusivity
# ---------------------------------------------------------------------------
def test_seam_needs_all_three_roles():
    registry = cs.SeamRegistry()
    definition = cs.ServiceDefinition(
        "fs", "keel.providers.FilesystemProvider", ("read", "write"))
    provider = cs.ServiceProvider("fs.local", "fs", "keel.local_fs")
    consumer = cs.Consumer("file-tools", "fs", "tools.file.read")

    registry.register("definition", definition)
    registry.register("provider", provider)
    assert registry.complete_seams() == ()          # one/two roles are not a seam

    registry.register("consumer", consumer)
    seams = registry.complete_seams()
    assert len(seams) == 1
    assert seams[0].name == "fs"
    assert seams[0].describe()["roles_active"] == ["consumer", "definition", "provider"]


def test_typed_registration_rejects_wrong_type():
    registry = cs.SeamRegistry()
    with pytest.raises(cs.SeamError, match="typed registration"):
        registry.register("consumer", cs.ServiceProvider("p", "fs", "impl"))
    with pytest.raises(cs.SeamError, match="typed registration"):
        registry.register("definition", "not-a-definition")
    with pytest.raises(cs.SeamError, match="expected a SeamRole"):
        registry.register("bogus", cs.Consumer("c", "fs"))


def test_role_exclusivity_one_name_one_active_role():
    registry = cs.SeamRegistry()
    registry.register(cs.SeamRole.DEFINITION,
                      cs.ServiceDefinition("shared", "iface"))
    with pytest.raises(cs.SeamError, match="role exclusivity"):
        registry.register(cs.SeamRole.CONSUMER, cs.Consumer("shared", "shared"))
    assert registry.role_of("shared") is cs.SeamRole.DEFINITION

    # Idempotent re-registration of the same object in the same role is safe.
    registry.register("definition", registry.get("definition", "shared"))


def test_seam_checklist_names_all_three_roles():
    checklist = cs.seam_checklist()
    assert checklist["roles"] == ["definition", "provider", "consumer"]
    assert checklist["required_types"] == {
        "definition": "ServiceDefinition",
        "provider": "ServiceProvider",
        "consumer": "Consumer",
    }
    assert checklist["io_performed"] is False


# ---------------------------------------------------------------------------
# D3.2 — provider swap determinism / no direct OS APIs
# ---------------------------------------------------------------------------
def test_resolve_provider_is_pure_and_deterministic():
    config = cs.ProviderConfig(cs.ProviderKind.FILESYSTEM, cs.ExecutionWorld.SSH,
                               {"host": "sandbox", "root": "work"})
    first = cs.resolve_provider(cs.ProviderKind.FILESYSTEM, config)
    second = cs.resolve_provider(cs.ProviderKind.FILESYSTEM, config)
    assert first == second
    assert first.describe() == second.describe()
    assert first.io_performed is False
    assert first.provider_id.startswith("filesystem.ssh.")
    assert first.target == "ssh://sandbox/work"
    assert "read" in first.capabilities

    # Param insertion order must not change the descriptor.
    reordered = cs.ProviderConfig(
        cs.ProviderKind.FILESYSTEM, cs.ExecutionWorld.SSH,
        [("root", "work"), ("host", "sandbox")])
    assert cs.resolve_provider(cs.ProviderKind.FILESYSTEM, reordered) == first
    assert cs.resolve_provider(cs.ProviderKind.FILESYSTEM, {"kind": "filesystem",
                               "world": "ssh", "params": {"host": "sandbox",
                               "root": "work"}}) == first


def test_one_world_swap_moves_every_provider():
    local = cs.resolve_world_bundle(cs.ExecutionWorld.LOCAL)
    remote = cs.resolve_world_bundle(cs.ExecutionWorld.SSH)
    assert {d.kind for d in local} == set(cs.ProviderKind)
    assert len(local) == len(remote) == 5
    for a, b in zip(local, remote):
        assert a.kind is b.kind
        assert a.provider_id != b.provider_id          # every provider swapped
        assert a.target != b.target
        assert a.capabilities == b.capabilities        # contract is unchanged
        assert a.moves_with_world and b.moves_with_world

    config = cs.ProviderConfig(cs.ProviderKind.SUBPROCESS, cs.ExecutionWorld.LOCAL,
                               {"host": "sandbox"})
    swapped = cs.swap_world(config, "ssh")
    assert swapped.world is cs.ExecutionWorld.SSH
    assert swapped.params == config.params             # config is not mutated
    assert config.world is cs.ExecutionWorld.LOCAL
    manifest = cs.world_manifest("ssh")
    assert {"filesystem", "bash", "pty", "lsp"} <= set(manifest["moved_services"])


def test_provider_boundary_check_and_kind_validation():
    report = cs.provider_boundary_check({
        "tools.file": "from .providers import fs\nfs.read(path)\n",
        "tools.exec": "from .providers import subprocess\nsubprocess.spawn(argv)\n",
    })
    assert report["clean"] is True and report["violations"] == []
    bad = cs.provider_boundary_check({
        "tools.legacy": "import os\nimport subprocess\n",
    })
    assert bad["clean"] is False and bad["violations"] == ["tools.legacy"]
    with pytest.raises(ValueError):
        cs.resolve_provider("subprocess", cs.ProviderConfig("filesystem"))


# ---------------------------------------------------------------------------
# D3.11 — package classification honesty
# ---------------------------------------------------------------------------
def test_package_groups_cover_the_deepseek_list():
    packages = cs.classify_packages()
    assert {p.group for p in packages} == set(cs.PACKAGE_GROUPS)
    assert len(packages) == 16
    assert {"deliverables", "spill", "attachment", "guard", "extensions",
            "feedback", "identity", "workspace", "plan", "schedule",
            "ptc-runtime", "session-query", "typert", "liveshare",
            "inspector", "experimental"} == set(cs.PACKAGE_GROUPS)


def test_package_classification_is_honest():
    packages = cs.classify_packages()
    classes = {p.classification for p in packages}
    assert classes == set(cs.PackageClassification)

    assert cs.package_by_group("spill").classification is \
        cs.PackageClassification.LOCALLY_ACHIEVABLE
    assert cs.package_by_group("liveshare").classification is \
        cs.PackageClassification.EXTERNAL_DEPENDENCY
    assert cs.package_by_group("inspector").classification is \
        cs.PackageClassification.EXTERNAL_DEPENDENCY
    assert cs.package_by_group("extensions").classification is \
        cs.PackageClassification.OWNER_GATED
    assert cs.package_by_group("ptc-runtime").classification is \
        cs.PackageClassification.UNVERIFIED
    assert cs.package_by_group("typert").classification is \
        cs.PackageClassification.UNVERIFIED

    # No group is claimed as running: local means "pure descriptor/policy".
    for package in packages:
        assert package.scope == "descriptor_only"
        assert package.runtime_claimed is False
        assert package.purpose and package.rationale
        if package.classification in (cs.PackageClassification.EXTERNAL_DEPENDENCY,
                                      cs.PackageClassification.OWNER_GATED,
                                      cs.PackageClassification.UNVERIFIED):
            assert package.external_requirement   # honest about what is missing
        else:
            assert package.external_requirement == ""
    with pytest.raises(cs.PackageError):
        cs.package_by_group("not-a-package")


# ---------------------------------------------------------------------------
# D3.13 — spill threshold + preview redaction
# ---------------------------------------------------------------------------
def test_spill_below_threshold_is_not_spilled():
    policy = cs.SpillPolicy(threshold_bytes=64, preview_bytes=16)
    result = cs.plan_spill("hello world", name="stdout", policy=policy)
    assert result.spilled is False
    assert result.spill_path == ""
    assert result.preview == "hello world"
    assert result.total_bytes == 11
    assert result.io_performed is False
    assert result.describe()["open_full_output"] is None


def test_spill_above_threshold_is_deterministic_and_bounded():
    policy = cs.SpillPolicy(threshold_bytes=32, preview_bytes=24)
    payload = "A" * 200 + "TAIL"
    first = cs.plan_spill(payload, name="big", policy=policy)
    second = cs.plan_spill(payload, name="big", policy=policy)
    assert first == second
    assert first.spilled is True
    assert first.spill_path.startswith(".keel/spill/big-")
    assert first.spill_path.endswith(".txt")
    assert len(first.preview.encode("utf-8")) <= policy.preview_bytes
    assert first.preview_bytes == len(first.preview.encode("utf-8"))
    assert first.preview_truncated is True
    assert first.describe()["open_full_output"] == "spill_path"


def test_preview_never_contains_full_secret_data():
    policy = cs.SpillPolicy(threshold_bytes=100, preview_bytes=64)
    # One secret at the start, one far past the preview window, one straddling.
    payload = "TOKEN_A=supersecret_alpha " + "B" * 300 + \
              "TOKEN_B=supersecret_beta " + "C" * 300 + "supersecret_gamma_tail"
    secrets = ["supersecret_alpha", "supersecret_beta", "supersecret_gamma"]
    result = cs.plan_spill(payload, policy=policy, secrets=secrets)
    for secret in secrets:
        assert secret not in result.preview
    assert result.redaction_count >= 3
    assert "supersecret_alpha" not in result.preview[:result.preview_bytes]


def test_preview_redacts_pattern_secrets_and_custom_patterns():
    text = ("sk-abcdefgh1234567890 ok "
            "Authorization: Bearer abcdefgh1234567890 "
            "password=hunter2secret END")
    preview, count = cs.redact_preview(text)
    assert "sk-abcdefgh1234567890" not in preview
    assert "abcdefgh1234567890" not in preview
    assert "hunter2secret" not in preview
    assert count >= 3
    assert cs.redact_preview(text) == (preview, count)

    custom, custom_count = cs.redact_preview(
        "case-1234", patterns=[r"case-\d+"])
    assert "case-1234" not in custom and custom_count == 1


def test_spill_policy_is_validated():
    with pytest.raises(cs.SpillError):
        cs.SpillPolicy(threshold_bytes=0)
    with pytest.raises(cs.SpillError):
        cs.SpillPolicy(threshold_bytes=10, preview_bytes=11)
    with pytest.raises(cs.SpillError):
        cs.plan_spill("x", policy={"threshold_bytes": 10})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# D3.14 — guard monotonic deny
# ---------------------------------------------------------------------------
def test_parent_deny_cannot_be_enabled_by_child():
    guards = cs.GuardRegistry()
    guards.register("root", cs.GuardKind.TOOL, cs.GuardDecision.DENY,
                    reason="policy")
    with pytest.raises(cs.GuardError, match="monotonic deny"):
        guards.register("root/child", cs.GuardKind.TOOL, cs.GuardDecision.ALLOW,
                        reason="trying to re-enable")
    assert guards.effective("root/child", "tool").decision is cs.GuardDecision.DENY
    assert guards.can_enable("root/child", "tool") is False


def test_deny_inherits_through_scope_path_and_grandchildren():
    guards = cs.GuardRegistry()
    guards.register("root", "loop", "deny", reason="doom-loop")
    with pytest.raises(cs.GuardError):
        guards.register("root/child/grandchild", "loop", "allow")
    verdict = guards.effective("root/child/grandchild", "loop")
    assert verdict.decision is cs.GuardDecision.DENY
    assert verdict.source == "root"
    assert verdict.reason == "doom-loop"
    assert set(verdict.chain) >= {"root/child", "root"}

    # Explicit parent links obey the same rule.
    guards.register("other", "tool", "deny")
    with pytest.raises(cs.GuardError):
        guards.register("linked", "tool", "allow", parent="other")


def test_sibling_branch_can_enable_what_another_branch_denied():
    guards = cs.GuardRegistry()
    guards.register("team/a", cs.GuardKind.TOOL, "deny")
    registration = guards.register("team/b", cs.GuardKind.TOOL, "allow")
    assert registration.decision is cs.GuardDecision.ALLOW
    assert guards.can_enable("team/b/child", cs.GuardKind.TOOL) is True
    assert guards.deny_sources(cs.GuardKind.TOOL) == ("team/a",)


def test_guard_can_tighten_but_never_relax_at_same_scope():
    guards = cs.GuardRegistry()
    guards.register("root/x", cs.GuardKind.STEP_LIMIT, "allow")
    guards.register("root/x", cs.GuardKind.STEP_LIMIT, "deny", reason="limit 5")
    with pytest.raises(cs.GuardError, match="denied at this scope"):
        guards.register("root/x", cs.GuardKind.STEP_LIMIT, "allow")
    assert guards.effective("root/x", "step_limit").source == "root/x"
    # Re-registering the same deny is idempotent.
    again = guards.register("root/x", "step_limit", "deny", reason="limit 5")
    assert again.decision is cs.GuardDecision.DENY


def test_guard_plugin_group_descriptor():
    guards = cs.GuardRegistry()
    guards.register("root", "mass_change", "deny")
    group = guards.group_descriptor()
    assert group["feature_id"] == "D3.14"
    assert group["group"] == "guard"
    assert group["kinds"] == ["loop", "tool", "mass_change", "step_limit"]
    assert "monotonic deny" in group["rule"]
    assert group["deny_sources"]["mass_change"] == ["root"]
    assert group["io_performed"] is False


# ---------------------------------------------------------------------------
# D3.18 — workspace entities + session-query containment
# ---------------------------------------------------------------------------
@pytest.fixture()
def workspace():
    service = cs.WorkspaceService("workspaces/demo", "ws-demo")
    service.add_entity("proj-1", "Demo", "workspaces/demo/project", "project")
    service.add_entity("sess-1", "Sessions", "workspaces/demo/project/sessions")
    return service


def test_workspace_entity_rejects_traversal_and_outside_root(workspace):
    with pytest.raises(cs.QueryError, match="containment"):
        workspace.add_entity("bad", "Escape", "../../etc/passwd")
    with pytest.raises(cs.QueryError, match="containment"):
        workspace.add_entity("bad", "Sibling", "workspaces/other/project")
    with pytest.raises(cs.QueryError, match="containment"):
        workspace.add_entity("bad", "Absolute", "C:/Windows/System32")
    with pytest.raises(cs.QueryError, match="duplicate"):
        workspace.add_entity("proj-1", "Again", "workspaces/demo/again")
    with pytest.raises(cs.QueryError, match="root"):
        cs.WorkspaceService("../escape")

    entity = workspace.workspace().entities[0]
    assert entity.path == "project"
    assert entity.kind is cs.EntityKind.PROJECT
    assert workspace.contains("workspaces/demo/project/sessions/a.json") is True
    assert workspace.contains("workspaces/demo/../secret") is False


def test_session_query_containment_for_browse_search_export(workspace):
    queries = cs.SessionQueryService(workspace)
    for escaped in ("../../etc", "workspaces/other", "workspaces/demo/../../x",
                    "C:/Windows"):
        with pytest.raises(cs.QueryError, match="escaped workspace root"):
            queries.search("hello", path=escaped)
        with pytest.raises(cs.QueryError):
            queries.browse(path=escaped)
        with pytest.raises(cs.QueryError):
            queries.export("json", path=escaped)

    inside = "workspaces/demo/project/sessions"
    browse = queries.browse(path=inside)
    search = queries.search("error", path=inside, limit=7)
    export = queries.export("jsonl", path=inside)
    assert browse.kind is cs.QueryKind.BROWSE
    assert search.path_scope == "project/sessions"
    assert ("term", "error") in search.filters
    assert search.limit == 7
    assert export.kind is cs.QueryKind.EXPORT and export.export_format == "jsonl"
    assert browse.workspace_id == "ws-demo"


def test_session_query_descriptors_are_db_free(workspace):
    queries = cs.SessionQueryService(workspace)
    described = queries.search("hello").describe()
    assert described["backend"] == "descriptor_only"
    assert described["sql"] is None
    assert described["io_performed"] is False
    assert described["path_scope"] == "."
    with pytest.raises(cs.QueryError, match="export format"):
        queries.export("exe")


# ---------------------------------------------------------------------------
# D3.6 / D3.7 / D3.8 / D3.9 — remaining P0 descriptor seams
# ---------------------------------------------------------------------------
def test_commands_dispatch_without_a_model_turn():
    commands = cs.CommandService()
    commands.register("/undo", "keel.commands:undo")
    commands.register("compact", "keel.commands:compact")
    result = commands.dispatch_descriptor("/undo")
    assert result["model_turn"] is False
    assert result["dispatch_without_model_turn"] is True
    assert result["pure_code"] is True
    with pytest.raises(cs.SeamError, match="model turn"):
        commands.register("ask-model", "keel.model:ask", model_turn=True)
    with pytest.raises(cs.SeamError, match="unknown command"):
        commands.dispatch_descriptor("missing")


def test_job_tools_are_declared_as_read_stop_tools():
    tools = cs.job_tools()
    assert tuple(t.name for t in tools) == cs.JOB_TOOLS == \
        ("job_list", "job_read", "job_stop")
    assert all(t.feature_id == "D3.7" and t.io_performed is False for t in tools)


def test_webhook_rule_requires_trust_signature_and_confirmation():
    rule = cs.webhook_rule("deploy", signature_headers=["x-hub-signature-256"],
                           adapters=["github-adapter"])
    described = rule.describe()
    assert described["trusted"] is True
    assert described["network"] is False
    assert described["confirmation_required"] is True
    assert described["dependencies"] == ["Y5.4", "V9"]
    assert "x-hub-signature-256" in described["signature_headers"]
    with pytest.raises(cs.SeamError, match="untrusted"):
        cs.webhook_rule("bad", trusted=False)
    with pytest.raises(cs.SeamError, match="signature"):
        cs.webhook_rule("bad", signature_headers=[])
    with pytest.raises(cs.SeamError, match="confirmation"):
        cs.webhook_rule("bad", confirmation_required=False)


def test_backends_are_separate_and_sandbox_only_wraps_argv():
    assert tuple(s.name for s in cs.backend_services()) == \
        ("shell", "terminals", "sandbox")
    wrapped = cs.sandbox_wrap_argv(["bash", "-c", "echo hi"], policy="strict")
    assert wrapped.wrapped_argv == (
        "keel-sandbox", "--policy", "strict", "--", "bash", "-c", "echo hi")
    assert wrapped.argv == ("bash", "-c", "echo hi")
    assert wrapped.spawn is False
    assert wrapped.describe()["feature_id"] == "D3.9"
    with pytest.raises(cs.SeamError, match="empty argv"):
        cs.sandbox_wrap_argv([])
