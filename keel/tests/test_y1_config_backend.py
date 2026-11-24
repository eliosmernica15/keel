"""Permanent contract tests for ``keel.y1_config_backend``.

Covers all 25 ``not_started`` Y1 rows in PLAN-INDEX.json:
Y1.1, Y1.10-Y1.15, Y1.18, Y1.21-Y1.23, Y1.25-Y1.29, Y1.31-Y1.39.

Adversarial coverage includes path traversal, unsafe HTML/script tags,
permission-gate denial, SSRF-style URLs, config precedence conflicts and
ambiguous or Tier-2-touching edits. Every contract is pure: no network, no
subprocess, no secret values and no file writes.
"""

from __future__ import annotations

from datetime import date

import pytest

from keel import y1_config_backend as y


def _err(excinfo, code: str) -> None:
    assert excinfo.value.code == code


def _offline_dns(host: str) -> tuple[str, ...]:
    """Deterministic, offline resolver for allow-listed documentation names.

    The production default uses ``socket.getaddrinfo``; tests inject this stub
    so that no test performs a real DNS lookup or outbound fetch.
    """
    public = {
        "trusted.example": "93.184.216.34",
        "docs.example": "93.184.216.34",
        "public.example": "8.8.8.8",
        "example.test": "8.8.8.8",
    }
    try:
        return (public[host.lower()],)
    except KeyError as exc:
        raise RuntimeError(f"offline resolver has no record for {host!r}") from exc


# ---------------------------------------------------------------------------
# Y1.1 - Code Mode / execute tool
# ---------------------------------------------------------------------------


def test_y101_descriptor_filters_server_switches_and_keeps_fetch():
    desc = y.code_mode_descriptor(
        ["read", "mcp__evil__x", "mcp__good__y"],
        server_switches={"evil": False, "good": True},
    )
    assert desc.available is True
    assert desc.tools == ("read", "mcp__good__y")
    assert desc.fetch is True
    assert desc.fallback == ""
    assert set(desc.globals) == {"fetch", "tools"}


def test_y101_denial_falls_back_to_direct_tool_list():
    desc = y.code_mode_descriptor(["read"], denied=True)
    assert desc.available is False
    assert desc.tools == ()
    assert desc.fetch is False
    assert desc.fallback == "tool_list"


@pytest.mark.parametrize("script", ["import os\nfetch('x')", "setTimeout(f, 10)", "eval('1+1')"])
def test_y101_script_guard_rejects_imports_timers_and_dynamic_code(script):
    with pytest.raises(y.CodeModeError) as ei:
        y.validate_code_script(script)
    _err(ei, "unsafe_token")


def test_y101_script_guard_rejects_unsafe_tag():
    with pytest.raises(y.CodeModeError) as ei:
        y.validate_code_script("fetch('<script>alert(1)</script>')")
    _err(ei, "unsafe_tag")


def test_y101_nested_calls_still_pass_the_permission_gate():
    desc = y.code_mode_descriptor(["read", "write"])
    allowed = y.authorize_code_mode_call("read", desc, lambda action, tool: True)
    assert allowed == {"tool": "read", "gate": "allow", "executed": False}
    with pytest.raises(y.CodeModeError) as ei:
        y.authorize_code_mode_call("write", desc, lambda action, tool: {"effect": "deny"})
    _err(ei, "nested_permission_denied")
    with pytest.raises(y.CodeModeError) as ei:
        y.authorize_code_mode_call("bash", desc, lambda action, tool: True)
    _err(ei, "tool_not_exposed")


# ---------------------------------------------------------------------------
# Y1.10 - skill loader advertised-list gate
# ---------------------------------------------------------------------------


def test_y1010_advertised_or_user_named_only():
    assert y.can_load_skill("review", ["review", "pptx"]).matched_by == "advertised"
    assert y.can_load_skill("custom", [], ["custom"]).matched_by == "user"
    assert y.can_load_skill("evil", ["review"]).allowed is False
    with pytest.raises(y.SkillGateError) as ei:
        y.require_skill("evil", ["review"])
    _err(ei, "not_advertised")


@pytest.mark.parametrize("skill_id", ["../secret", "a/b", "<script>x</script>"])
def test_y1010_rejects_traversal_and_unsafe_ids(skill_id):
    with pytest.raises(y.SkillGateError) as ei:
        y.can_load_skill(skill_id, [skill_id])
    assert ei.value.code in ("unsafe_id", "unsafe_tag")


# ---------------------------------------------------------------------------
# Y1.11 - subagent semantics
# ---------------------------------------------------------------------------


def test_y1011_background_session_id_and_notifications():
    launch = y.spawn_subagent("parent-1", "review the patch")
    assert launch.background is True
    assert launch.session_id.startswith("ses_")
    assert y.spawn_subagent("parent-1", "review the patch").session_id == launch.session_id
    idle = y.subagent_notification(launch, "idle")
    round2 = y.subagent_notification(launch, "round", round_number=2)
    assert idle["type"] == "subagent.idle" and idle["round"] == 0
    assert round2["sessionID"] == launch.session_id and round2["round"] == 2


def test_y1011_depth_limit_and_followup_same_child():
    launch = y.spawn_subagent("p", "task", config_depth=2)
    with pytest.raises(y.SubagentError) as ei:
        y.spawn_subagent(launch.session_id, "nested", depth=2, config_depth=2)
    _err(ei, "depth_exceeded")
    known = {launch.session_id: launch}
    follow = y.subagent_followup(launch, known, "continue")
    assert follow["continue"] is True and follow["sessionID"] == launch.session_id
    with pytest.raises(y.SubagentError) as ei:
        y.subagent_followup(launch, {}, "continue")
    _err(ei, "unknown_child_session")
    with pytest.raises(y.SubagentError):
        y.subagent_notification(launch, "idle", round_number=3)


# ---------------------------------------------------------------------------
# Y1.12 - session utilities as tools
# ---------------------------------------------------------------------------


def test_y1012_rename_descriptor():
    tool = y.session_rename_tool("Sprint work", session_id="ses_1")
    assert tool["tool"] == "session_rename"
    assert tool["arguments"]["title"] == "Sprint work"
    with pytest.raises(y.SessionToolError) as ei:
        y.session_rename_tool("<script>alert(1)</script>")
    _err(ei, "unsafe_tag")


def test_y1012_move_takes_effect_at_safe_boundary():
    plan = y.session_move_tool("projects/new", allowed_root="/work", current_directory="projects/old")
    assert plan.effective_at == "safe_boundary" and plan.applied_now is False
    assert plan.directory == "/work/projects/new"
    with pytest.raises(y.SessionToolError) as ei:
        y.session_move_tool("/etc/passwd", allowed_root="/work")
    _err(ei, "absolute_path")


# ---------------------------------------------------------------------------
# Y1.13 - worktree tools
# ---------------------------------------------------------------------------


def test_y1013_create_uses_edit_permission_and_plugin_strategy():
    plan = y.worktree_create(
        "feat", "worktrees", allowed_root="/repo",
        strategy="mirror", strategies={"mirror": lambda: None},
    )
    assert plan.permission == "edit" and plan.permission_resource == "worktree:feat"
    assert plan.strategy == "mirror" and plan.directory == "/repo/worktrees"
    assert y.WORKTREE_TOOLS == ("worktree_create", "worktree_list", "worktree_remove")


def test_y1013_remove_requires_force_and_edit_permission():
    with pytest.raises(y.WorktreeError) as ei:
        y.worktree_remove("feat", dirty=True)
    _err(ei, "force_required")
    with pytest.raises(y.WorktreeError) as ei:
        y.worktree_remove("feat", permission_check=lambda action, resource: False)
    _err(ei, "permission_denied")
    plan = y.worktree_remove("feat", dirty=True, force=True, permission_check=lambda a, r: True)
    assert plan.discard_changes is True


def test_y1013_rejects_traversal_and_unregistered_strategy():
    with pytest.raises(y.WorktreeError) as ei:
        y.worktree_create("../evil", "wt", allowed_root="/repo")
    _err(ei, "unsafe_id")
    with pytest.raises(y.WorktreeError) as ei:
        y.worktree_create("feat", "wt", allowed_root="/repo", strategy="unknown")
    _err(ei, "unknown_strategy")


# ---------------------------------------------------------------------------
# Y1.14 - browser tool namespace
# ---------------------------------------------------------------------------


def test_y1014_deny_removes_whole_catalog():
    catalog = y.browser_tool_catalog()
    assert len(catalog) == 14
    assert catalog[0] == "browser.tabs.open" and catalog[-1] == "browser.lighthouse"
    assert y.browser_tool_catalog(denied=["browser"]) == ()
    assert y.browser_tool_catalog(denied=["browser.*"]) == ()
    assert y.browser_tool_catalog(allowed=["browser.network"]) == ("browser.network",)


def test_y1014_transfer_cap_consent_and_untrusted_pages():
    assert y.validate_browser_transfer_size(5 * 1024 * 1024) == 5 * 1024 * 1024
    with pytest.raises(y.BrowserContractError) as ei:
        y.validate_browser_transfer_size(5 * 1024 * 1024 + 1)
    _err(ei, "out_of_range")
    with pytest.raises(y.BrowserContractError) as ei:
        y.lighthouse_descriptor()
    _err(ei, "lighthouse_consent_required")
    assert y.lighthouse_descriptor(consent=True, license_ack=True)["tool"] == "browser.lighthouse"
    page = y.browser_page_content("<script>evil()</script><b>text</b>", source_url="https://example.test")
    assert page["trust"] == "untrusted"
    assert "&lt;script&gt;" in page["text"] and "<script>" not in page["text"]
    assert page["instructions"] == []


def test_y1014_rejects_javascript_and_private_targets():
    with pytest.raises(y.BrowserContractError) as ei:
        y.validate_browser_url("javascript:alert(1)")
    assert ei.value.code in ("unsafe_tag", "unsupported_scheme")
    with pytest.raises(y.BrowserContractError) as ei:
        y.validate_browser_url("http://127.0.0.1/admin")
    _err(ei, "unsafe_host")


def test_y1014_rejects_non_decimal_ip_spellings():
    for url in (
        "http://0x7f000001/x",        # hexadecimal integer
        "http://017700000001/x",      # octal integer
        "http://2130706433/x",        # decimal integer
        "http://127.1/x",             # short form
        "http://0x7f.0.0.1/x",        # hexadecimal components
        "http://[::1]/x",             # IPv6 loopback
    ):
        with pytest.raises(y.BrowserContractError) as ei:
            y.validate_browser_url(url)
        _err(ei, "unsafe_host")


def test_y1014_rejects_dns_names_resolving_to_private_addresses():
    """C5: DNS names that point at loopback must be denied, not passed through."""
    def resolving_to_loopback(host: str) -> tuple[str, ...]:
        return {
            "localtest.me": ("127.0.0.1",),
            "127.0.0.1.nip.io": ("127.0.0.1",),
        }[host.lower()]

    for url in ("http://localtest.me/x", "http://127.0.0.1.nip.io/x"):
        with pytest.raises(y.BrowserContractError) as ei:
            y.validate_browser_url(url, dns_resolver=resolving_to_loopback)
        _err(ei, "unsafe_host")
    # A name that resolves to a mix of public and private addresses is denied too.
    with pytest.raises(y.BrowserContractError) as ei:
        y.validate_browser_url(
            "https://mixed.example/x",
            dns_resolver=lambda host: ("8.8.8.8", "10.0.0.5"),
        )
    _err(ei, "unsafe_host")


def test_y1014_dns_failure_or_empty_answer_fails_closed():
    def unavailable(host: str) -> tuple[str, ...]:
        raise RuntimeError("DNS temporarily unavailable")

    for resolver in (unavailable, lambda host: ()):
        with pytest.raises(y.BrowserContractError) as ei:
            y.validate_browser_url("https://public.example/x", dns_resolver=resolver)
        _err(ei, "unsafe_host")


def test_y1014_public_dns_name_allowed_and_literals_skip_resolution():
    assert y.validate_browser_url(
        "https://example.test/x", dns_resolver=_offline_dns
    ) == "https://example.test/x"

    def must_not_resolve(host: str) -> tuple[str, ...]:
        raise AssertionError("IP literals must use the no-I/O fast path")

    # IP-literal forms are already checked by address arithmetic: no DNS call.
    with pytest.raises(y.BrowserContractError) as ei:
        y.validate_browser_url("http://127.0.0.1/x", dns_resolver=must_not_resolve)
    _err(ei, "unsafe_host")
    # Structural rejections happen before resolution as well.
    with pytest.raises(y.BrowserContractError) as ei:
        y.validate_browser_url("javascript:alert(1)", dns_resolver=must_not_resolve)
    assert ei.value.code in ("unsafe_tag", "unsupported_scheme")


def test_default_dns_resolver_delegates_to_stdlib_without_real_lookup(monkeypatch):
    """The default seam resolves; the stub keeps this test fully offline."""
    import socket

    calls = []

    def fake_getaddrinfo(host, port, *, type):  # noqa: A002 - stdlib signature
        calls.append((host, port, type))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert list(y._default_dns_resolver("public.example")) == ["8.8.8.8"]
    assert calls == [("public.example", None, socket.SOCK_STREAM)]

    # No injected resolver -> the guard uses the default seam (stubbed here).
    assert y.validate_browser_url("https://public.example/x") == "https://public.example/x"
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Y1.15 - experimental_image_generate
# ---------------------------------------------------------------------------


def test_y1015_hidden_without_local_provider():
    job = y.image_generate_descriptor(providers=[], save_path="out.png", allowed_root="/repo")
    assert job.available is False and job.reason == "no_local_provider"
    job = y.image_generate_descriptor(
        providers=["local-diffusion"], save_path="out.png", allowed_root="/repo",
        references=["a.png", "b.png"],
    )
    assert job.available is True and job.background is True
    assert job.notification == "on_completion" and job.save_path == "/repo/out.png"


def test_y1015_rejects_traversal_extension_and_reference_flood():
    with pytest.raises(y.ImageJobError) as ei:
        y.image_generate_descriptor(providers=["local-diffusion"], save_path="../evil.png", allowed_root="/repo")
    _err(ei, "unsafe_path")
    with pytest.raises(y.ImageJobError) as ei:
        y.image_generate_descriptor(providers=["local-diffusion"], save_path="out.exe", allowed_root="/repo")
    _err(ei, "unsupported_extension")
    with pytest.raises(y.ImageJobError) as ei:
        y.image_generate_descriptor(
            providers=["local-diffusion"], save_path="out.png", allowed_root="/repo",
            references=[f"r{i}.png" for i in range(9)],
        )
    _err(ei, "too_many_references")


# ---------------------------------------------------------------------------
# Y1.18 - managed config locations
# ---------------------------------------------------------------------------


def test_y1018_platform_paths_and_highest_precedence():
    assert y.managed_config_locations("linux")[0].path == "/etc/opencode"
    mac = y.managed_config_locations("macos")
    assert any(loc.kind == "plist" for loc in mac)
    win = y.managed_config_locations("windows", env={"ProgramData": "C:\\ProgramData"})
    assert win[0].path == "C:\\ProgramData\\opencode"
    with pytest.raises(y.ManagedConfigError) as ei:
        y.managed_config_locations("windows")
    _err(ei, "managed_env_missing")
    assert y.managed_value({"project": "p", "managed": "m", "user": "u"}) == ("m", "managed")


def test_y1018_rejects_env_traversal_and_unknown_os():
    with pytest.raises(y.ManagedConfigError) as ei:
        y.managed_config_locations("win32", env={"ProgramData": "C:\\ProgramData\\..\\evil"})
    _err(ei, "unsafe_env_path")
    with pytest.raises(y.ManagedConfigError) as ei:
        y.managed_config_locations("plan9")
    _err(ei, "unsupported_os")


# ---------------------------------------------------------------------------
# Y1.21 - update modes
# ---------------------------------------------------------------------------


def test_y1021_modes_and_global_only_precedence():
    assert y.resolve_update_mode("disable")[0] == "disable"
    assert y.resolve_update_mode("auto")[0] == "auto"
    mode, ignored = y.resolve_update_mode("auto", scope="project")
    assert mode == "notify" and ignored is True
    plan = y.update_plan("auto", server_running=True)
    assert plan.install is True and plan.restart is False
    assert y.update_plan("auto", scope="project").install is False
    with pytest.raises(y.UpdateConfigError) as ei:
        y.resolve_update_mode("nightly")
    _err(ei, "invalid_update_mode")


# ---------------------------------------------------------------------------
# Y1.22 - snapshots toggle and watcher.ignore
# ---------------------------------------------------------------------------


def test_y1022_snapshot_default_and_override():
    assert y.snapshots_enabled() is True
    assert y.snapshots_enabled({"snapshots": False}) is False
    with pytest.raises(y.WatchConfigError) as ei:
        y.snapshots_enabled({"snapshots": "yes"})
    _err(ei, "invalid_type")


def test_y1022_ignore_globs_and_adversarial_patterns():
    patterns = y.validate_watcher_ignore(["node_modules/**", "*.tmp"])
    assert y.watcher_ignored("node_modules/pkg/a.js", patterns) is True
    assert y.watcher_ignored("src/a.py", patterns) is False
    for bad in ("../secret", "/etc/passwd", "<script>x</script>"):
        with pytest.raises(y.WatchConfigError):
            y.validate_watcher_ignore([bad])


# ---------------------------------------------------------------------------
# Y1.23 - media.image and tool_output limits
# ---------------------------------------------------------------------------


def test_y1023_documented_defaults():
    media = y.resolve_media_limits()
    output = y.resolve_tool_output_limits()
    assert (media.max_width, media.max_height, media.max_base64_bytes) == (2000, 2000, 5 * 1024 * 1024)
    assert (output.max_lines, output.max_bytes) == (2000, 50 * 1024)


def test_y1023_resize_base64_cap_and_output_clipping():
    assert y.resize_dimensions(4000, 2000) == (2000, 1000, True)
    assert y.resize_dimensions(100, 50)[2] is False
    assert y.validate_base64_size(5 * 1024 * 1024) == 5 * 1024 * 1024
    with pytest.raises(y.LimitConfigError) as ei:
        y.validate_base64_size(5 * 1024 * 1024 + 1)
    _err(ei, "out_of_range")
    chunk = y.clip_tool_output("a\nb\nc", y.ToolOutputLimits(2, 100))
    assert chunk.truncated is True and chunk.omitted_lines == 1
    assert "omitted_lines=1" in chunk.marker
    with pytest.raises(y.LimitConfigError):
        y.resolve_tool_output_limits({"maxLines": 0})


# ---------------------------------------------------------------------------
# Y1.25 - cache warming
# ---------------------------------------------------------------------------


def test_y1025_off_by_default_and_schedule():
    policy = y.cache_policy()
    assert policy.warming is False
    assert y.warm_due(policy, last_warm=0.0, now=10**6) is False
    active = y.CachePolicy(ttl_seconds=10, warming=True, keep_alive="5m", prewarm_prefix=True)
    assert y.warm_due(active, last_warm=0.0, now=9.0) is False
    assert y.warm_due(active, last_warm=0.0, now=10.0) is True
    assert y.warming_plan(active)["actions"] == ("keep_alive", "prewarm_system_prompt_prefix")


def test_y1025_remote_warming_needs_opt_in_and_cost():
    active = y.CachePolicy(ttl_seconds=10, warming=True)
    with pytest.raises(y.CacheConfigError) as ei:
        y.warming_plan(active, remote=True)
    _err(ei, "remote_opt_in_required")
    with pytest.raises(y.CacheConfigError) as ei:
        y.warming_plan(active, remote=True, opt_in=True)
    _err(ei, "cost_disclosure_required")
    plan = y.warming_plan(active, remote=True, opt_in=True, cost_shown=True)
    assert plan["cost_shown"] is True and plan["transient_request"] is True


# ---------------------------------------------------------------------------
# Y1.26 - references
# ---------------------------------------------------------------------------


def test_y1026_named_paths_and_repositories():
    refs = y.parse_references(
        {
            "docs": {"description": "Docs", "path": "docs"},
            "upstream": {"description": "Upstream", "repository": "acme/repo", "branch": "main"},
        },
        allowed_root="/repo", cache_root="/cache",
    )
    assert y.reference_by_name("docs", refs).path == "/repo/docs"
    assert y.reference_by_name("upstream", refs).branch == "main"
    assert all(r.read_only and r.cache_path.startswith("/cache/") for r in refs)
    assert tuple(r.name for r in y.search_references("doc", refs)) == ("docs",)


def test_y1026_exactly_one_source_traversal_and_unknown_name():
    with pytest.raises(y.ReferenceError) as ei:
        y.parse_references({"x": {"description": "x", "path": "p", "repository": "a/b"}},
                           allowed_root="/repo", cache_root="/cache")
    _err(ei, "exactly_one_source")
    with pytest.raises(y.ReferenceError) as ei:
        y.parse_references({"x": {"description": "x", "path": "../../etc"}},
                           allowed_root="/repo", cache_root="/cache")
    _err(ei, "unsafe_path")
    with pytest.raises(y.ReferenceError) as ei:
        y.reference_by_name("missing", ())
    _err(ei, "unknown_reference")


# ---------------------------------------------------------------------------
# Y1.27 - skills config directories and URLs
# ---------------------------------------------------------------------------


def test_y1027_directories_and_allowlisted_url_discovery():
    sources = y.parse_skill_sources(
        ["skills/local", "https://trusted.example/skills"],
        allowed_hosts=["trusted.example"],
        dns_resolver=_offline_dns,
    )
    assert sources[0].kind == "directory" and sources[0].requires_signature is False
    assert sources[1].kind == "url" and sources[1].requires_signature is True
    assert sources[1].discovery_url == "https://trusted.example/.well-known/skills/"
    check = y.skill_pack_signature_check({"signature": "abc", "algorithm": "ed25519"})
    assert check["verified"] is False and check["verification_performed"] is False
    assert check["reason"] == "verification_unavailable"


def test_y1027_rejects_http_unlisted_hosts_credentials_and_traversal():
    for bad, host, code in (
        ("http://trusted.example/skills", ["trusted.example"], "unsupported_scheme"),
        ("https://evil.example/skills", ["trusted.example"], "host_not_allowed"),
        ("https://user@trusted.example/skills", ["trusted.example"], "credentials_in_url"),
    ):
        with pytest.raises(y.SkillSourceError) as ei:
            y.parse_skill_sources([bad], allowed_hosts=host)
        _err(ei, code)
    with pytest.raises(y.SkillSourceError) as ei:
        y.parse_skill_sources(["../skills"])
    _err(ei, "unsafe_path")
    with pytest.raises(y.SkillSourceError) as ei:
        y.skill_pack_signature_check({"signature": "", "algorithm": "md5"})
    _err(ei, "signature_check_failed")


def test_y1027_rejects_allowlisted_dns_name_resolving_to_loopback():
    """The resolver seam must be honoured by every URL-taking Y1 contract."""
    with pytest.raises(y.SkillSourceError) as ei:
        y.parse_skill_sources(
            ["https://localtest.me/skills"],
            allowed_hosts=["localtest.me"],
            dns_resolver=lambda host: ("127.0.0.1",),
        )
    _err(ei, "unsafe_host")


def test_y1027_signature_check_only_verifies_with_a_real_verifier():
    manifest = {"signature": "garbage", "algorithm": "ed25519",
                "material": "payload", "key": "public-key"}
    assert y.skill_pack_signature_check(manifest)["verified"] is False

    calls = []

    def accepting(algorithm, signature, material, key):
        calls.append((algorithm, signature, material, key))
        return signature == "garbage" and material == "payload" and key == "public-key"

    checked = y.skill_pack_signature_check(manifest, verifier=accepting)
    assert checked["verified"] is True and checked["verification_performed"] is True
    assert calls == [("ed25519", "garbage", "payload", "public-key")]

    rejecting = y.skill_pack_signature_check(manifest, verifier=lambda *a: False)
    assert rejecting["verified"] is False and rejecting["reason"] == "signature_mismatch"


# ---------------------------------------------------------------------------
# Y1.28 - instructions files, globs and HTTP(S) URLs
# ---------------------------------------------------------------------------


def test_y1028_files_globs_and_tainted_urls():
    sources = y.parse_instruction_sources(
        ["AGENTS.md", "docs/*.md", "https://docs.example/agent.md"],
        allowed_hosts=["docs.example"],
        dns_resolver=_offline_dns,
    )
    assert [s.kind for s in sources] == ["file", "glob", "url"]
    assert [s.tainted for s in sources] == [False, False, True]
    context = y.instruction_context(sources)
    assert context["fetched"] is False and len(context["tainted"]) == 1


def test_y1028_rejects_ssrf_and_traversal():
    for bad in ("http://127.0.0.1/admin", "file:///etc/passwd", "http://169.254.169.254/latest"):
        with pytest.raises(y.InstructionSourceError):
            y.parse_instruction_sources([bad], allowed_hosts=["127.0.0.1", "169.254.169.254"])
    with pytest.raises(y.InstructionSourceError) as ei:
        y.parse_instruction_sources(["../../etc/passwd"])
    _err(ei, "unsafe_path")


def test_y1028_rejects_allowlisted_dns_name_resolving_to_loopback():
    with pytest.raises(y.InstructionSourceError) as ei:
        y.parse_instruction_sources(
            ["https://localtest.me/agent.md"],
            allowed_hosts=["localtest.me"],
            dns_resolver=lambda host: ("127.0.0.1",),
        )
    _err(ei, "unsafe_host")


# ---------------------------------------------------------------------------
# Y1.29 - plugin management CLI
# ---------------------------------------------------------------------------


def test_y1029_sources_pin_policy_and_commands():
    exact = y.parse_plugin_source("@keel/core@1.2.3", private_sources=["@keel/"])
    assert exact.kind == "npm" and exact.pinned is True
    assert y.update_plugin_plan(exact)["action"] == "none"
    gh = y.parse_plugin_source("github:acme/tools#dev::path:plugins/x", private_sources=["acme/"])
    assert gh.branch == "dev" and gh.subdirectory == "plugins/x" and gh.pinned is False
    assert y.update_plugin_plan(gh)["installed_version_unchanged"] is True
    assert y.plugin_command("list", builtin=True)["builtin"] is True
    assert y.plugin_command("add", "@keel/core@1.2.3", private_sources=["@keel/"])["action"] == "add"


def test_y1029_rejects_shell_injection_public_sources_and_branch_traversal():
    with pytest.raises(y.PluginCommandError) as ei:
        y.parse_plugin_source("npm; curl evil", allow_public=True)
    _err(ei, "unsafe_token")
    with pytest.raises(y.PluginCommandError) as ei:
        y.parse_plugin_source("public-pkg")
    _err(ei, "public_source_blocked")
    with pytest.raises(y.PluginCommandError) as ei:
        y.parse_plugin_source("github:acme/tools#../evil", allow_public=True)
    _err(ei, "unsafe_branch")
    with pytest.raises(y.PluginCommandError) as ei:
        y.plugin_command("destroy")
    _err(ei, "unknown_action")


# ---------------------------------------------------------------------------
# Y1.31 - three plugin surfaces
# ---------------------------------------------------------------------------


def test_y1031_manifests_surfaces_and_extensions_page():
    manifest = y.parse_plugin_manifest(
        {"name": "panel", "surfaces": ["gui", "server"], "panels": ["Main"], "hot_reload": True}
    )
    assert manifest.surfaces == ("gui", "server") and manifest.hot_reload is True
    assert y.tui_plugin_ids({"plugins": ["tui-only"]}) == ("tui-only",)
    state = y.extensions_page_state([manifest], failed=["panel"])[0]
    assert state["enabled"] is False and state["reload_available"] is True
    plan = y.hot_reload_plan(["plugins/panel/a.js"], watched_dirs={"panel": "plugins/panel"})
    assert plan == ({"plugin": "panel", "action": "reload", "reason": "file_changed"},)
    assert y.update_plugin_plan(y.PluginSource("npm", "x", "^1.0", "", "", False))["action"] == "check_only"


def test_y1031_rejects_unknown_surface_and_surface_mismatch():
    with pytest.raises(y.PluginManifestError) as ei:
        y.parse_plugin_manifest({"name": "p", "surfaces": ["web"]})
    _err(ei, "unknown_surface")
    with pytest.raises(y.PluginManifestError) as ei:
        y.parse_plugin_manifest({"name": "p", "surfaces": ["server"], "panels": ["Main"]})
    _err(ei, "surface_mismatch")
    with pytest.raises(y.PluginManifestError) as ei:
        y.hot_reload_plan(["../secret"], watched_dirs={"p": "plugins"})
    _err(ei, "unsafe_path")


# ---------------------------------------------------------------------------
# Y1.32 - location_idle_timeout
# ---------------------------------------------------------------------------


def test_y1032_idle_unload_and_busy_guards():
    assert y.should_unload(idle_minutes=20, timeout_minutes=15, state=y.IdleState()) is True
    assert y.should_unload(idle_minutes=20, timeout_minutes=15,
                           state=y.IdleState(running_sessions=1)) is False
    assert y.should_unload(idle_minutes=20, timeout_minutes=15,
                           state=y.IdleState(background_jobs=1)) is False
    assert y.should_unload(idle_minutes=100, timeout_minutes=0, state=y.IdleState()) is False
    assert y.unload_plan(should_unload_now=True)["unload"] == ("lsp", "watchers")


def test_y1032_rejects_invalid_timeout():
    for bad in (-1, float("nan"), True, "15"):
        with pytest.raises(y.IdleConfigError):
            y.validate_idle_timeout(bad)


# ---------------------------------------------------------------------------
# Y1.33 - experimental.todo flag
# ---------------------------------------------------------------------------


def test_y1033_todowrite_is_opt_in_todo_stays():
    tools = ["todo", "todowrite", "read"]
    off = y.todo_tool_exposure({"experimental": {"todo": False}}, tools)
    assert off["flag"] is False and "todowrite" in off["hidden"]
    assert "todo" in off["exposed"] and off["todo_always_available"] is True
    on = y.todo_tool_exposure({"todo": True}, tools)
    assert on["flag"] is True and "todowrite" in on["exposed"]


def test_y1033_rejects_non_boolean_flag():
    with pytest.raises(y.ExperimentalFlagError) as ei:
        y.todo_tool_exposure({"experimental": {"todo": "true"}}, ["todo"])
    _err(ei, "invalid_type")


# ---------------------------------------------------------------------------
# Y1.34 - model overrides and provider transport
# ---------------------------------------------------------------------------


def test_y1034_overrides_and_websocket_transport():
    catalog = {"m1": {"id": "m1", "limit": {"context": 100, "output": 20}}}
    result = y.apply_model_overrides(
        catalog, {"m1": {"name": "Fast", "limit": {"context": 200, "output": 40}}}
    )
    assert result["m1"]["name"] == "Fast"
    assert result["m1"]["limit"] == {"context": 200, "output": 40}
    assert catalog["m1"]["limit"] == {"context": 100, "output": 20}
    assert y.provider_transport({"settings": {"transport": "websocket"}})["transport"] == "websocket"


def test_y1034_rejects_unknown_model_bad_limits_and_unsafe_transport():
    with pytest.raises(y.ModelConfigError) as ei:
        y.apply_model_overrides({}, {"ghost": {}})
    _err(ei, "unknown_model")
    with pytest.raises(y.ModelConfigError) as ei:
        y.apply_model_overrides({"m": {}}, {"m": {"limit": {"context": 10, "output": 20}}})
    _err(ei, "output_exceeds_context")
    for bad in ("ftp", "<script>x</script>"):
        with pytest.raises(y.ModelConfigError):
            y.validate_transport(bad)


# ---------------------------------------------------------------------------
# Y1.35 - config_edit tool
# ---------------------------------------------------------------------------


def test_y1035_proposal_is_a_diff_and_requires_approval():
    proposal = y.propose_config_edit('{"theme": "dark"}\n', [("dark", "light")])
    assert proposal.target == "keel.jsonc" and proposal.requires_approval is True
    assert proposal.applies is False and "-{\"theme\": \"dark\"}" in proposal.diff
    assert "+{\"theme\": \"light\"}" in proposal.diff
    assert not any(name in dir(proposal) for name in ("apply", "write", "save"))


def test_y1035_blocks_tier2_ambiguous_and_traversal_edits():
    with pytest.raises(y.ConfigEditError) as ei:
        y.propose_config_edit('{"auth": "x"}\n', [("x", "y")])
    _err(ei, "tier2_blocked")
    with pytest.raises(y.ConfigEditError) as ei:
        y.propose_config_edit("1 1", [("1", "2")])
    _err(ei, "ambiguous_match")
    with pytest.raises(y.ConfigEditError) as ei:
        y.propose_config_edit("{}", [("{}", "[]")], target="../keel.jsonc")
    _err(ei, "unsafe_path")
    with pytest.raises(y.ConfigEditError) as ei:
        y.propose_config_edit("a", [("missing", "x")])
    _err(ei, "missing_match")


def test_y1035_tier2_gate_checks_the_full_resulting_document():
    current = (
        '{\n'
        '  "auth": {\n'
        '    "a": "1",\n'
        '    "b": "2",\n'
        '    "c": "3",\n'
        '    "d": "4",\n'
        '    "setting": "OLDVALUE"\n'
        '  },\n'
        '  "theme": "dark"\n'
        '}\n'
    )
    # The Tier-2 key is five lines above the changed line, so it never
    # appears in the unified diff (three lines of context).
    with pytest.raises(y.ConfigEditError) as ei:
        y.propose_config_edit(current, [("OLDVALUE", "NEWVALUE")])
    _err(ei, "tier2_blocked")

    # Editing outside the Tier-2 value remains allowed.
    proposal = y.propose_config_edit(current, [("dark", "light")])
    assert proposal.applies is False and "light" in proposal.diff


# ---------------------------------------------------------------------------
# Y1.36 - migrate / troubleshooting docs
# ---------------------------------------------------------------------------


def test_y1036_docs_generated_and_escaped():
    pages = y.build_docs_pages([
        {"code": "E1", "message": "<script>alert(1)</script>", "remedy": "Restart the server"},
        {"code": "E2", "message": "Bad flag", "remedy": "Use --safe"},
    ])
    assert tuple(p.route for p in pages) == ("/docs/migrate-from-v1", "/docs/troubleshooting")
    assert "&lt;script&gt;" in pages[1].body and "<script>" not in pages[1].body
    assert "Restart the server" in pages[0].body


def test_y1036_rejects_duplicate_codes_and_empty_catalog():
    with pytest.raises(y.DocsContractError) as ei:
        y.build_docs_pages([{"code": "E1"}, {"code": "E1"}])
    _err(ei, "invalid_or_duplicate_code")
    with pytest.raises(y.DocsContractError) as ei:
        y.build_docs_pages([])
    _err(ei, "empty_catalog")


# ---------------------------------------------------------------------------
# Y1.37 - install script and release channels
# ---------------------------------------------------------------------------


def test_y1037_per_user_target_channel_formulas_and_cleanup_tip():
    plan = y.install_plan("stable", "brew", home="/home/me")
    assert plan.target_dir == "/home/me/.opencode/bin" and plan.per_user is True
    assert "# preview only" in plan.script_preview
    assert y.install_plan("beta", "aur", home="/home/me", cleanup_older_than=2,
                          existing_versions=["1.0.0", "2.1.0"]).cleanup_tip.count("1.0.0") == 1
    assert "install stable binary into /home/me/.opencode/bin" in plan.script_preview


def test_y1037_rejects_system_dirs_injection_and_channel_mismatch():
    with pytest.raises(y.InstallPlanError) as ei:
        y.install_plan("stable", "brew", home="/usr/local")
    _err(ei, "system_install_dir")
    with pytest.raises(y.InstallPlanError) as ei:
        y.install_plan("stable", "brew", home="/home/me; rm -rf /")
    _err(ei, "unsafe_home")
    with pytest.raises(y.InstallPlanError) as ei:
        y.install_plan("stable", "aur", home="/home/me")
    _err(ei, "channel_method_mismatch")
    with pytest.raises(y.InstallPlanError):
        y.install_plan("nightly", "script", home="/home/me")


# ---------------------------------------------------------------------------
# Y1.38 - repo hygiene
# ---------------------------------------------------------------------------


def test_y1038_reviewed_allowlist_and_repo_status():
    today = date(2026, 1, 1)
    entries = y.validate_gitleaks_allowlist(
        [{"pattern": "EXAMPLE_TOKEN", "reason": "documented sample", "expiry": "2027-01-01", "reviewed": True}],
        today=today,
    )
    assert entries[0].reviewed is True
    status = y.repo_hygiene_status([".husky/pre-commit", ".gitleaksignore", "CHANGELOG.md"])
    assert status["present"][".gitleaksignore"] is True and "oxlint" in status["missing"]
    assert y.task_graph_order({"b": ["a"], "a": []}) == ("a", "b")


def test_y1038_rejects_expired_unreviewed_and_cycles():
    today = date(2026, 1, 1)
    with pytest.raises(y.HygieneError) as ei:
        y.validate_gitleaks_allowlist(
            [{"pattern": "X", "reason": "a long enough reason", "expiry": "2025-01-01", "reviewed": True}],
            today=today,
        )
    _err(ei, "expired_allowlist")
    with pytest.raises(y.HygieneError) as ei:
        y.validate_gitleaks_allowlist(
            [{"pattern": "X", "reason": "short", "expiry": "2027-01-01", "reviewed": True}],
            today=today,
        )
    assert ei.value.code in ("empty_value", "too_long")
    with pytest.raises(y.HygieneError) as ei:
        y.task_graph_order({"a": ["b"], "b": ["a"]})
    _err(ei, "task_cycle")


# ---------------------------------------------------------------------------
# Y1.39 - non-affiliation notice
# ---------------------------------------------------------------------------


def test_y1039_notice_states_non_affiliation():
    notice = y.non_affiliation_notice("Keel", "AnomalyCo", year=2026)
    assert "not affiliated with" in notice and "AnomalyCo" in notice
    assert y.validate_trademarks_doc(notice, "AnomalyCo") is True


def test_y1039_escapes_tags_and_requires_clause():
    notice = y.non_affiliation_notice("<script>Keel</script>", "Upstream")
    assert "&lt;script&gt;" in notice and "<script>" not in notice
    with pytest.raises(y.TrademarkError) as ei:
        y.validate_trademarks_doc("Just a fork.", "Upstream")
    _err(ei, "missing_non_affiliation")
