"""Y1.x P0 MCP / plugin / config contract regressions.

Covers the 14 feature IDs implemented in ``keel.mcp_contracts``:
Y1.2, Y1.3, Y1.4, Y1.5, Y1.6, Y1.7, Y1.8, Y1.9, Y1.16, Y1.17,
Y1.19, Y1.20, Y1.24 and Y1.30.

Every contract is pure: no network, no subprocess, no file application.
Only the injected file reader in ``substitute_config`` touches bytes, and
tests supply it explicitly.
"""

from __future__ import annotations

import pytest

from keel import mcp_contracts as mc


# ---------------------------------------------------------------------------
# Y1.2 - model-dependent tool exposure
# ---------------------------------------------------------------------------


def test_y102_patch_family_gets_patch_not_edit_write():
    tools = mc.tools_for_model(
        "claude-3-5-sonnet", all_tools=["read", "glob", "patch", "edit", "write", "bash"]
    )
    assert "patch" in tools
    assert "edit" not in tools and "write" not in tools
    assert tools == sorted(tools)


def test_y102_other_family_gets_edit_and_write():
    tools = mc.tools_for_model(
        "local/llama3", all_tools=["read", "glob", "patch", "edit", "write", "bash"]
    )
    assert "edit" in tools and "write" in tools
    assert "patch" not in tools


def test_y102_profile_can_deny_and_allow():
    base = ["read", "bash", "patch", "edit", "write"]
    denied = mc.tools_for_model(
        "gpt-4o", all_tools=base, profile=mc.ToolProfile(deny=frozenset({"bash"}))
    )
    assert "bash" not in denied and "patch" in denied
    allowed = mc.tools_for_model(
        "gpt-4o", all_tools=base, profile=mc.ToolProfile(allow=frozenset({"read", "bash"}))
    )
    assert allowed == ["bash", "read"]


def test_y102_family_map_override():
    fam = mc.model_family("vendor-model-x", family_map={"vendor": "local"})
    assert fam == "local"


# ---------------------------------------------------------------------------
# Y1.3 - patch multi-file format parser
# ---------------------------------------------------------------------------


def test_y103_parse_unified_diff_across_two_files():
    text = (
        "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n-old\n+OLD\n ctx\n"
        "--- a/b.txt\n+++ b/b.txt\n@@ -1 +1 @@\n-x\n+Y\n"
    )
    desc = mc.parse_patch(text)
    assert [f.path for f in desc.files] == ["a.txt", "b.txt"]
    assert [f.op for f in desc.files] == ["update", "update"]
    assert desc.files[0].hunks[0].added == 1
    assert desc.files[0].hunks[0].removed == 1
    assert set(desc.affected_paths) == {"a.txt", "b.txt"}
    assert "apply" not in desc.to_dict()  # descriptor only, never an application


def test_y103_parse_add_delete_move_headers():
    text = (
        "*** Add File: new.txt\n@@ -0,0 +1 @@\n+hello\n"
        "*** Delete File: gone.txt\n@@ -1 +0,0 @@\n-bye\n"
        "*** Update File: src/old.py\n*** Move to: src/new.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    desc = mc.parse_patch(text)
    assert [f.op for f in desc.files] == ["add", "delete", "move"]
    assert desc.files[2].path == "src/new.py"
    assert desc.files[2].move_from == "src/old.py"


def test_y103_rejects_malformed_hunk_counts():
    text = "--- a/x\n+++ b/x\n@@ -1,3 +1 @@\n-a\n+A\n"
    with pytest.raises(mc.PatchParseError) as ei:
        mc.parse_patch(text)
    assert ei.value.code == "hunk_count_mismatch"


def test_y103_rejects_empty_patch():
    with pytest.raises(mc.PatchParseError) as ei:
        mc.parse_patch("no diff here\n")
    assert ei.value.code == "no_file_header"


# ---------------------------------------------------------------------------
# Y1.4 - read limits and paging
# ---------------------------------------------------------------------------


def test_y104_page_basic_and_defaults():
    assert mc.READ_MAX_LINES == 2000
    assert mc.READ_MAX_BYTES == 50 * 1024
    lines = [f"line{i}" for i in range(10)]
    result = mc.page(lines, offset=0, limit=3, max_bytes=1_000_000)
    assert result.lines == ("line0", "line1", "line2")
    assert result.next_offset == 3
    assert result.truncated is True
    assert "omitted_lines=7" in result.marker
    assert "next_offset=3" in result.marker


def test_y104_page_no_truncation_when_all_fits():
    result = mc.page(["a", "b"], offset=0, limit=10, max_bytes=100)
    assert result.truncated is False
    assert result.marker is None
    assert result.text == "a\nb"
    assert result.next_offset == 2


def test_y104_page_byte_cap_and_deterministic_marker():
    lines = ["line0", "line1", "line2"]
    r1 = mc.page(lines, 0, 10, 7)
    r2 = mc.page(lines, 0, 10, 7)
    assert r1.lines == ("line0",)
    assert r1.omitted_lines == 2
    assert r1.marker == r2.marker  # deterministic
    assert r1.next_offset == 1


def test_y104_page_long_line_is_truncated_to_byte_budget():
    result = mc.page(["x" * 100], 0, 10, 10)
    assert result.line_truncated is True
    assert result.lines == ("x" * 10,)
    assert "line_truncated=1" in result.marker


def test_y104_page_offset_beyond_end_and_zero_limit():
    r = mc.page(["a"], offset=99, limit=10, max_bytes=100)
    assert r.lines == () and r.truncated is False
    r0 = mc.page(["a", "b"], offset=0, limit=0, max_bytes=100)
    assert r0.lines == () and r0.truncated is True and r0.omitted_lines == 2


def test_y104_page_rejects_bad_arguments():
    for kwargs in ({"offset": -1}, {"limit": 0, "max_bytes": 0}, {"limit": -1}):
        with pytest.raises(mc.PagingError):
            mc.page(["a"], **kwargs)


# ---------------------------------------------------------------------------
# Y1.5 - glob/grep defaults
# ---------------------------------------------------------------------------


def test_y105_defaults_match_registry():
    glob = mc.glob_defaults()
    grep = mc.grep_defaults()
    assert glob["limit"] == 100 and grep["limit"] == 100
    assert glob["timeout_seconds"] == 30 and grep["timeout_seconds"] == 30
    for key in ("literal", "include", "case_sensitive", "hidden"):
        assert key in glob and key in grep


def test_y105_grep_permission_resource_is_pattern_not_path():
    assert mc.grep_permission_resource("TODO") == "TODO"
    assert mc.grep_permission_resource("class Foo") == "class Foo"


def test_y105_resolve_search_options_overrides_and_validates():
    opts = mc.resolve_search_options("grep", {"limit": 5, "literal": True, "hidden": True})
    assert opts["limit"] == 5 and opts["literal"] is True
    assert opts["case_sensitive"] is True  # untouched default
    with pytest.raises(mc.ContractError):
        mc.resolve_search_options("glob", {"limit": 0})
    with pytest.raises(mc.ContractError):
        mc.resolve_search_options("bogus", {})


# ---------------------------------------------------------------------------
# Y1.6 - edit unique match and formatter hook
# ---------------------------------------------------------------------------


def test_y106_unique_match_enforcement():
    ok = mc.check_unique_match("alpha beta gamma", "beta")
    assert ok.ok is True and ok.count == 1
    with pytest.raises(mc.EditMatchError) as missing:
        mc.check_unique_match("abc", "zzz")
    assert missing.value.code == "not_found"
    with pytest.raises(mc.EditMatchError) as ambiguous:
        mc.check_unique_match("aXbXc", "X")
    assert ambiguous.value.code == "ambiguous"
    allowed = mc.check_unique_match("aXbXc", "X", replace_all=True)
    assert allowed.ok is True and allowed.count == 2


def test_y106_empty_old_string_rejected():
    with pytest.raises(mc.EditMatchError) as ei:
        mc.check_unique_match("abc", "")
    assert ei.value.code == "empty_old_string"


def test_y106_formatter_hook_is_validation_only():
    spec = mc.validate_formatter_config({"command": "ruff format {file}", "extensions": ["py"]})
    assert spec.command == "ruff format {file}"
    assert spec.extensions == ("py",)
    assert spec.enabled is True
    off = mc.validate_formatter_config(None)
    assert off.enabled is False
    with pytest.raises(mc.FormatterConfigError):
        mc.validate_formatter_config({"extensions": ["py"]})
    with pytest.raises(mc.FormatterConfigError):
        mc.validate_formatter_config({"command": 42})


# ---------------------------------------------------------------------------
# Y1.7 - shell tool descriptor
# ---------------------------------------------------------------------------


def test_y107_shell_descriptor_fields_and_safety():
    desc = mc.shell_descriptor("echo hi && git push", workdir="/repo", timeout_seconds=120)
    assert desc.command == "echo hi && git push"
    assert desc.cwd == "/repo"
    assert desc.timeout_seconds == 120
    assert desc.background is False and desc.returns_immediately is False
    assert desc.permission_resources == ("shell:echo hi", "shell:git push")
    assert desc.safety["one_permission_per_subcommand"] is True
    assert "no_subprocess" in str(desc.to_dict())


def test_y107_background_and_cd_rejection():
    bg = mc.shell_descriptor("sleep 5", background=True)
    assert bg.background is True and bg.returns_immediately is True
    assert bg.safety["notify_on_finish"] is True
    with pytest.raises(mc.ShellDescriptorError) as ei:
        mc.shell_descriptor("cd /tmp && ls")
    assert ei.value.code == "cd_in_command"


def test_y107_external_workdir_detection():
    desc = mc.shell_descriptor("ls", workdir="/outside", allowed_roots=["/repo"])
    assert desc.external_workdirs == ("/outside",)


# ---------------------------------------------------------------------------
# Y1.8 - webfetch/websearch provider selection (free backends only)
# ---------------------------------------------------------------------------


def test_y108_free_provider_selection_and_random_is_deterministic():
    assert mc.select_websearch_provider("searxng", available=["searxng", "duckduckgo"]) == "searxng"
    a = mc.select_websearch_provider("random", available=["searxng", "duckduckgo"], seed=7)
    b = mc.select_websearch_provider("random", available=["searxng", "duckduckgo"], seed=7)
    assert a == b and a in mc.FREE_WEBSEARCH_PROVIDERS


def test_y108_rejects_paid_and_unavailable_providers():
    with pytest.raises(mc.ProviderPolicyError) as ei:
        mc.select_websearch_provider("google-cse", available=["google-cse"])
    assert ei.value.code == "non_free_provider"
    with pytest.raises(mc.ProviderPolicyError) as ei:
        mc.select_websearch_provider("searxng", available=["duckduckgo"])
    assert ei.value.code == "unavailable"


def test_y108_policy_seam_denies():
    with pytest.raises(mc.ProviderPolicyError) as ei:
        mc.select_websearch_provider(
            "searxng", available=["searxng"], policy=lambda name, kind: False
        )
    assert ei.value.code == "policy_denied"


def test_y108_webfetch_descriptor_validates_without_network():
    d = mc.webfetch_descriptor("https://example.com", format="markdown", max_seconds=120)
    assert d["format"] == "markdown" and d["no_network"] is True
    with pytest.raises(mc.ProviderPolicyError):
        mc.webfetch_descriptor("file:///etc/passwd")
    with pytest.raises(mc.ProviderPolicyError):
        mc.webfetch_descriptor("https://x", format="pdf")
    with pytest.raises(mc.ProviderPolicyError) as ei:
        mc.webfetch_descriptor("https://x", content_type="image/png")
    assert ei.value.code == "binary_rejected"
    with pytest.raises(mc.ProviderPolicyError):
        mc.webfetch_descriptor("https://x", max_seconds=121)


# ---------------------------------------------------------------------------
# Y1.9 - question tool descriptor
# ---------------------------------------------------------------------------


def test_y109_question_descriptor_fields():
    q = mc.question_descriptor(
        "Pick one?", header="Choice", options=[{"label": "A", "value": "a"}, "b"],
        timeout_seconds=15, default="a", client_can_render=True,
    )
    assert q.question == "Pick one?" and q.header == "Choice"
    assert q.mode == "form" and q.ui_available is True
    assert q.free_form_allowed is True and q.cancel_on_dismiss is True
    assert q.options[1] == {"label": "b", "value": "b"}
    assert q.timeout_seconds == 15 and q.default == "a"


def test_y109_client_without_ui_detected():
    q = mc.question_descriptor("Q", options=["a"], client_can_render=False)
    assert q.ui_available is False and q.mode == "text" and q.capability_known is True
    unknown = mc.question_descriptor("Q", options=["a"])
    assert unknown.capability_known is False


def test_y109_approval_seam_and_default_validation():
    q = mc.question_descriptor(
        "Q", options=["a", "b"], approval_policy=lambda desc: True
    )
    assert q.requires_approval is True
    with pytest.raises(mc.QuestionDescriptorError):
        mc.question_descriptor("Q", options=["a"], default="z")
    with pytest.raises(mc.QuestionDescriptorError):
        mc.question_descriptor("Q", options=["a"], timeout_seconds=0)


# ---------------------------------------------------------------------------
# Y1.16 - canonical MCP permission naming
# ---------------------------------------------------------------------------


def test_y1016_canonical_naming():
    assert mc.canonical_mcp_permission("github", "read_file") == "mcp.github.read_file"
    assert mc.canonical_mcp_permission("my server", "read/file") == "mcp.my_server.read_file"
    with pytest.raises(mc.PermissionRuleError):
        mc.canonical_mcp_permission("", "tool")


def test_y1016_rule_resource_star_and_per_server_timeout():
    rule = mc.mcp_permission_rule("github", "read_file", timeout_seconds=45)
    assert rule.action == "mcp.github.read_file"
    assert rule.resource == "*" and rule.effect == "allow"
    assert rule.timeout_seconds == 45
    fallback = mc.mcp_permission_rule("github", "read_file")
    assert fallback.timeout_seconds == mc.MCP_DEFAULT_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Y1.17 - ordered rules, policies layer, deny overrides
# ---------------------------------------------------------------------------


def test_y1017_deny_wins_over_allow_in_either_order():
    allow = mc.PermissionRule("mcp.github.*", "*", "allow")
    deny = mc.PermissionRule("mcp.github.delete", "*", "deny")
    assert mc.evaluate_rules([allow, deny], "mcp.github.delete", "*") == "deny"
    assert mc.evaluate_rules([deny, allow], "mcp.github.delete", "*") == "deny"
    assert mc.evaluate_rules([allow], "mcp.github.read", "*") == "allow"


def test_y1017_last_matching_allow_wins_and_default_deny():
    a = mc.PermissionRule("shell:*", "*", "allow")
    b = mc.PermissionRule("shell:git*", "*", "allow")
    assert mc.evaluate_rules([a, b], "shell:git push", "*") == "allow"
    assert mc.evaluate_rules([], "unknown", "*", default="deny") == "deny"


def test_y1017_policy_layer_outranks_config_but_deny_still_wins():
    cfg = [mc.PermissionRule("mcp.github.*", "*", "allow")]
    policy_deny = [mc.block_extension("mcp", "github")]
    assert mc.evaluate_permissions(
        config_rules=cfg, policy_rules=policy_deny,
        action="mcp.github.read", resource="*",
    ) == "deny"
    cfg_deny = [mc.PermissionRule("mcp.github.*", "*", "deny")]
    policy_allow = [mc.PermissionRule("mcp.github.*", "*", "allow")]
    assert mc.evaluate_permissions(
        config_rules=cfg_deny, policy_rules=policy_allow,
        action="mcp.github.read", resource="*",
    ) == "deny"


def test_y1017_tool_use_rule_and_block_extension():
    r = mc.tool_use_rule("shell", "git push *", "deny")
    assert r.action == "tool.use" and r.resource == "shell:git push *"
    b = mc.block_extension("plugin", "evil")
    assert b.action == "plugin.block" and b.effect == "deny"
    with pytest.raises(mc.PermissionRuleError):
        mc.block_extension("bogus", "x")


# ---------------------------------------------------------------------------
# Y1.19 - config precedence and search order
# ---------------------------------------------------------------------------


def test_y1019_project_beats_user_beats_default():
    eff = mc.effective_config(
        default={"theme": "dark", "model": "base", "nested": {"a": 1, "b": 1}},
        user={"theme": "light", "nested": {"b": 2}},
        project={"model": "project-model"},
    )
    assert eff.config["theme"] == "light"
    assert eff.config["model"] == "project-model"
    assert eff.config["nested"] == {"a": 1, "b": 2}  # deep merge
    assert eff.provenance["theme"] == "user"
    assert eff.provenance["model"] == "project"
    assert eff.provenance["nested.a"] == "default"


def test_y1019_managed_last_and_deny_preserved_across_layers(tmp_path):
    eff = mc.effective_config(
        user={"permissions": [mc.PermissionRule("mcp.x.*", "*", "allow")]},
        managed={"permissions": [mc.PermissionRule("mcp.x.bad", "*", "deny")]},
    )
    rules = eff.config["permissions"]
    assert rules[0].effect == "allow" and rules[1].effect == "deny"
    assert mc.evaluate_rules(rules, "mcp.x.bad", "*") == "deny"


def test_y1019_config_search_order_root_to_cwd(tmp_path):
    deep = tmp_path / "a" / "b"
    order = mc.config_search_order(deep, root=tmp_path)
    scopes = [e["scope"] for e in order]
    assert scopes[0] == "default" and scopes[-1] == "managed"
    project = [e for e in order if e["scope"] == "project"]
    kinds = [e["kind"] for e in project]
    assert kinds == ["direct", "dot_dir", "direct", "dot_dir", "direct", "dot_dir"]
    assert str(tmp_path) in project[0]["path"]


def test_y1019_unknown_scope_rejected():
    with pytest.raises(mc.ContractError):
        mc.merge_config_layers({"bogus": {"x": 1}})


# ---------------------------------------------------------------------------
# Y1.20 - env/file substitution
# ---------------------------------------------------------------------------


def test_y1020_env_substitution_present_and_missing():
    result = mc.substitute_config(
        {"token": "{env:KEEL_TOKEN}", "mix": "x-{env:MISSING_VAR}-y"},
        env={"KEEL_TOKEN": "s3cret"},
    )
    assert result.value["token"] == "s3cret"
    assert result.value["mix"] == "x--y"
    kinds = [w.kind for w in result.warnings]
    assert "missing_env" in kinds
    assert all("s3cret" not in str(w.to_dict()) for w in result.warnings)  # no secret logging


def test_y1020_file_substitution_with_injected_reader(tmp_path):
    secret_file = tmp_path / "key.txt"
    result = mc.substitute_config(
        {"key": "{file:key.txt}"},
        base_dir=tmp_path,
        file_reader=lambda p: "FILEBODY" if p == secret_file else "",
    )
    assert result.value["key"] == "FILEBODY"
    assert result.warnings == ()


def test_y1020_file_substitution_traversal_rejected(tmp_path):
    with pytest.raises(mc.ConfigSubstitutionError) as ei:
        mc.substitute_config(
            {"key": "{file:../outside/secret}"},
            base_dir=tmp_path / "inside",
            file_reader=lambda p: "SECRET",
        )
    assert ei.value.code == "path_outside_base_dir"


def test_y1020_missing_file_warns_empty_and_no_base_dir_errors(tmp_path):
    result = mc.substitute_config(
        {"key": "{file:nope.txt}"}, base_dir=tmp_path, file_reader=lambda p: ""
    )
    assert result.value["key"] == "" and result.warnings[0].kind == "missing_file"
    with pytest.raises(mc.ConfigSubstitutionError):
        mc.substitute_config({"key": "{file:x}"}, file_reader=lambda p: "")


def test_y1020_secret_named_var_warns_without_value():
    result = mc.substitute_config({"v": "{env:API_SECRET}"}, env={})
    assert any(w.kind == "secret_reference" for w in result.warnings)
    assert all("API_SECRET" in w.key or w.kind != "secret_reference" for w in result.warnings)


# ---------------------------------------------------------------------------
# Y1.24 - compaction config validation
# ---------------------------------------------------------------------------


def test_y1024_compaction_defaults_summary():
    cfg = mc.validate_compaction_config(None)
    assert cfg.auto is True and cfg.strategy == "summary"
    assert cfg.keep_tokens == 4000 and 0 <= cfg.buffer < 1


def test_y1024_compaction_validates_values_and_unknown_keys():
    with pytest.raises(mc.CompactionConfigError):
        mc.validate_compaction_config({"buffer": 1.5})
    with pytest.raises(mc.CompactionConfigError):
        mc.validate_compaction_config({"keep": {"tokens": -1}})
    with pytest.raises(mc.CompactionConfigError):
        mc.validate_compaction_config({"strategy": "magic"})
    with pytest.raises(mc.CompactionConfigError):
        mc.validate_compaction_config({"bogus": 1})


def test_y1024_per_model_override_resolution():
    cfg = mc.validate_compaction_config({
        "keep": {"tokens": 1000}, "strategy": "summary",
        "per_model": {
            "openai/gpt-4o": {"strategy": "native", "keep": {"tokens": 500}},
        },
    })
    resolved = cfg.resolve("openai/gpt-4o")
    assert resolved.strategy == "native" and resolved.keep_tokens == 500
    default_resolved = cfg.resolve("local/llama")
    assert default_resolved.strategy == "summary" and default_resolved.keep_tokens == 1000


# ---------------------------------------------------------------------------
# Y1.30 - plugin enable/disable DSL (data only, rejects code)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "plugin; rm -rf /",
    "<script>alert(1)</script>",
    "$(whoami)",
    "a && b",
    "{{ 7*7 }}",
    "eval('x')",
    "plugin|cat /etc/passwd",
])
def test_y1030_dsl_rejects_code_and_unsafe_tags(bad):
    with pytest.raises(mc.PluginDSLError):
        mc.parse_plugin_dsl(bad)


def test_y1030_ordered_disable_then_reenable():
    sel = mc.parse_plugin_dsl(
        "alpha beta -alpha gamma alpha", builtin_plugins=["policy-enforcer"]
    )
    assert sel.is_enabled("beta") is True
    assert sel.is_enabled("alpha") is True  # later entry re-enables
    assert sel.is_enabled("delta") is False
    assert sel.is_enabled("policy-enforcer") is True
    assert sel.enabled(["alpha", "beta", "delta", "policy-enforcer"]) == [
        "alpha", "beta", "policy-enforcer"
    ]


def test_y1030_wildcards_and_builtin_unremovable():
    sel = mc.parse_plugin_dsl("sen.* -*", builtin_plugins=["policy-enforcer", "tier2"])
    assert sel.is_enabled("sen.foo") is True
    assert sel.is_enabled("other") is False
    assert sel.is_enabled("policy-enforcer") is True
    assert sel.is_enabled("tier2") is True
