"""Contract tests for the W3.x P0 permission-engine features.

These tests pin the *contracts* in ``keel.permission_contracts`` without
touching the live evaluator (``keel.permissions``). The critical semantic
guard is W3.2: Keel stays first-match (deny -> ask -> allow -> default-ask)
per DECISIONS.md D-001; the last-match evaluator is only a non-authoritative
comparison adapter for the policy simulator.

Feature coverage:
    W3.1  rule shape + default-ask baseline
    W3.2  authoritative first-match vs non-authoritative last-match adapter
    W3.3  wildcards (*, ?, whole value, backslashes, Windows case, shell *)
    W3.4  multi-resource aggregation
    W3.6  external_directory containment / traversal / trusted mode
    W3.7  shell scanner extension (bash/zsh/sh/powershell, cd targets)
    W3.8  default policy (env/key ask list, .env.example exception)
    W3.9  once/always/reject approvals + project-scoped persistence
    W3.10 policy hard-deny floor (policy never grants)
    W3.12 non-interactive fail-closed behaviour
    W3.13 shell-authority documentation warning + allowlist preset
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from keel.permission_contracts import (
    APPROVE_NEVER,
    APPROVE_RULES_ONLY,
    AUTHORITATIVE_EVALUATOR,
    CAUTIOUS_PRESET,
    DEFAULT_EFFECT,
    EFFECT_ALLOW,
    EFFECT_ASK,
    EFFECT_DENY,
    KEEL_IS_AUTHORITATIVE,
    LAST_MATCH_IS_AUTHORITATIVE,
    SHELL_AUTHORITY_WARNING,
    SIMULATOR_NOTE,
    ApprovalReply,
    ApprovalRequest,
    ApprovalStore,
    Effect,
    Evaluation,
    ResourceCheck,
    Rule,
    apply_policy_floor,
    apply_policy_floors,
    check_external_directory,
    default_policy_decision,
    default_policy_rules,
    evaluate_multi,
    evaluate_rules_keel,
    evaluate_rules_last_match,
    is_sensitive_env_read,
    path_is_within,
    resolve_noninteractive,
    scan_shell_command,
    scan_to_checks,
    select_matching_rules,
    simulate,
    wildcard_match,
)


# ---------------------------------------------------------------------------
# W3.1 - rule shape, effects, default-ask baseline
# ---------------------------------------------------------------------------

def test_w31_rule_is_action_resource_effect():
    rule = Rule(action="read", resource="src/*", effect="allow")
    assert rule.action == "read"
    assert rule.resource == "src/*"
    assert rule.effect == "allow"


def test_w31_rule_is_frozen_and_validates_effect():
    rule = Rule("read", "*", "allow")
    with pytest.raises(Exception):
        rule.effect = "deny"  # type: ignore[misc]
    for bad in ("permit", "", None):
        with pytest.raises(ValueError):
            Rule("read", "*", bad)


def test_w31_default_ask_when_no_rules_match():
    evaluation = evaluate_rules_keel(
        [Rule("write", "*.py", "allow")], action="read", resource="README.md"
    )
    assert evaluation.effect is Effect.ASK
    assert evaluation.matched_rule is None
    assert DEFAULT_EFFECT == EFFECT_ASK


def test_w31_effects_constants_are_stable():
    assert (EFFECT_DENY, EFFECT_ASK, EFFECT_ALLOW) == ("deny", "ask", "allow")
    assert {e.value for e in Effect} == {EFFECT_DENY, EFFECT_ASK, EFFECT_ALLOW}


# ---------------------------------------------------------------------------
# W3.2 - authoritative first-match vs non-authoritative last-match adapter
# ---------------------------------------------------------------------------

def test_w32_keel_is_first_match_deny_before_allow():
    # A scoped deny listed BEFORE a broad allow must still win (D-001).
    rules = [
        Rule("execute", "rm *", "deny"),
        Rule("execute", "*", "allow"),
    ]
    assert evaluate_rules_keel(rules, action="execute", resource="rm -rf /").effect is Effect.DENY


def test_w32_last_match_adapter_is_explicitly_non_authoritative():
    assert KEEL_IS_AUTHORITATIVE is True
    assert LAST_MATCH_IS_AUTHORITATIVE is False
    assert LAST_MATCH_IS_AUTHORITATIVE is not KEEL_IS_AUTHORITATIVE
    assert "keel.permissions" in AUTHORITATIVE_EVALUATOR
    assert "non-authoritative" in SIMULATOR_NOTE.lower()


def test_w32_adapter_models_last_match_and_shows_winner():
    rules = [
        Rule("execute", "rm *", "deny"),      # scoped deny listed first
        Rule("execute", "*", "allow"),        # broad allow listed last
    ]
    keel = evaluate_rules_keel(rules, action="execute", resource="rm -rf /")
    adapter = evaluate_rules_last_match(rules, action="execute", resource="rm -rf /")
    assert keel.effect is Effect.DENY
    assert adapter.effect is Effect.ALLOW  # models opencode last-match
    assert adapter.winner is rules[1]
    assert adapter.winner.effect == "allow"
    assert keel.matched_rule is rules[0]


def test_w32_simulate_reports_both_without_changing_live_behaviour():
    rules = [Rule("execute", "rm *", "deny"), Rule("execute", "*", "allow")]
    result = simulate(rules, "execute", "rm -rf /")
    assert result["authoritative_evaluator"] == AUTHORITATIVE_EVALUATOR
    assert result["keel"]["effect"] == EFFECT_DENY
    assert result["last_match"]["effect"] == EFFECT_ALLOW
    assert result["last_match"]["authoritative"] is False


def test_w32_live_permissions_evaluator_still_first_match():
    """Integration guard: the shipped evaluator is unchanged by this work."""
    from keel import permissions

    deny = permissions.parse_rules("deny", ["read_file(/secret/*)"])[0]
    allow = permissions.parse_rules("allow", ["read_file(**)"])[0]
    decision = permissions.evaluate(
        tool_name="read_file",
        tool_input={"path": "/secret/key.txt"},
        rules=(deny, [], allow),
        mode=permissions.MODE_BYPASS,
        interactive=True,
    )
    assert decision.decision == "deny"


def test_w32_select_matching_rules_uses_wildcards():
    rules = [Rule("read", "src/*", "allow"), Rule("write", "src/*", "deny")]
    assert select_matching_rules(rules, "read", "src/a.py") == (rules[0],)
    assert select_matching_rules(rules, "write", "src/a.py") == (rules[1],)


# ---------------------------------------------------------------------------
# W3.3 - wildcards
# ---------------------------------------------------------------------------

def test_w33_star_matches_slashes_and_empty():
    assert wildcard_match("src/*", "src/a/b/c.py")
    assert wildcard_match("src/*", "src/")
    assert wildcard_match("*", "anything/goes/here")


def test_w33_question_matches_exactly_one_character():
    assert wildcard_match("a?c", "abc")
    assert not wildcard_match("a?c", "ac")
    assert not wildcard_match("a?c", "abbc")


def test_w33_whole_value_match():
    assert wildcard_match("npm test", "npm test")
    assert not wildcard_match("npm test", "npm test --watch")
    assert not wildcard_match("cat", "scat")


def test_w33_backslashes_normalized():
    assert wildcard_match(r"config\scripts\*.bat", "config/scripts/run.bat")
    assert wildcard_match("config/main.py", r"config\main.py")


def test_w33_windows_case_insensitivity_is_explicit_and_controllable():
    assert wildcard_match("README.MD", "readme.md", case_sensitive=False)
    assert not wildcard_match("README.MD", "readme.md", case_sensitive=True)
    # Default follows the host (case-insensitive on Windows, where tests run).
    assert wildcard_match("README.MD", "readme.md") is (os.name == "nt")


def test_w33_shell_trailing_star_matches_bare_command():
    assert wildcard_match("npm run *", "npm run build")
    assert wildcard_match("npm run *", "npm run")  # bare command
    assert not wildcard_match("npm run *", "npm")


def test_w33_invalid_pattern_type_is_rejected():
    with pytest.raises(TypeError):
        wildcard_match(None, "value")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# W3.4 - multi-resource aggregation
# ---------------------------------------------------------------------------

def test_w34_any_deny_denies_the_whole_operation():
    rules = (
        Rule("write", "safe.txt", "allow"),
        Rule("write", "secret.txt", "deny"),
        Rule("write", "notes.txt", "allow"),
    )
    result = evaluate_multi(
        [("write", "safe.txt"), ("write", "secret.txt"), ("write", "notes.txt")],
        rules=rules,
    )
    assert result.effect is Effect.DENY
    assert len(result.details) == 3


def test_w34_ask_wins_when_no_deny():
    rules = (Rule("write", "a.txt", "allow"), Rule("write", "b.txt", "ask"))
    assert evaluate_multi([("write", "a.txt"), ("write", "b.txt")], rules=rules).effect is Effect.ASK


def test_w34_all_allowed_returns_allow():
    rules = (Rule("write", "a.txt", "allow"), Rule("write", "b.txt", "allow"))
    assert evaluate_multi([("write", "a.txt"), ("write", "b.txt")], rules=rules).effect is Effect.ALLOW


def test_w34_no_rules_fails_closed_to_ask():
    assert evaluate_multi([("write", "a.txt")]).effect is Effect.ASK


def test_w34_accepts_resource_checks_and_precomputed_evaluations():
    checks = [ResourceCheck("write", "a.txt", (Rule("write", "a.txt", "allow"),))]
    checks.append(Evaluation(Effect.ASK, reason="needs consent"))  # type: ignore[list-item]
    assert evaluate_multi(checks).effect is Effect.ASK


# ---------------------------------------------------------------------------
# W3.6 - external_directory containment and traversal
# ---------------------------------------------------------------------------

def test_w36_path_within_project_is_allowed(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    target = root / "src" / "file.py"
    assert path_is_within(target, root)
    evaluation = check_external_directory(target, project_root=root)
    assert evaluation.effect is Effect.ALLOW


def test_w36_path_outside_project_is_ask_by_default(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside" / "secret.txt"
    evaluation = check_external_directory(outside, project_root=root)
    assert evaluation.effect is Effect.ASK


def test_w36_traversal_is_not_contained(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    traversal = root / ".." / "outside" / "secret.txt"
    assert not path_is_within(traversal, root)
    assert check_external_directory(traversal, project_root=root).effect is Effect.ASK


def test_w36_sibling_prefix_is_not_contained(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    sibling = tmp_path / "proj-evil" / "secret.txt"
    assert not path_is_within(sibling, root)


def test_w36_trusted_mode_allows_external_directory(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "notes.txt"
    assert check_external_directory(outside, project_root=root, mode="trusted").effect is Effect.ALLOW
    assert check_external_directory(outside, project_root=root, mode="balanced").effect is Effect.ASK


def test_w36_configured_deny_on_external_directory_is_respected(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "notes.txt"
    rules = (Rule("external_directory", "*", "deny"),)
    evaluation = check_external_directory(outside, project_root=root, mode="trusted", rules=rules)
    assert evaluation.effect is Effect.DENY


# ---------------------------------------------------------------------------
# W3.7 - shell scanner extension (delegates to shell_ast)
# ---------------------------------------------------------------------------

def test_w37_scan_bash_subcommands_and_cd_targets():
    scan = scan_shell_command("cd /tmp && cat notes.txt", "bash")
    assert scan.ok and scan.error is None
    assert [c.canonical for c in scan.subcommands] == ["cd", "cat"]
    assert scan.cd_targets == ("/tmp",)


def test_w37_scan_zsh_and_sh_map_to_posix_scanner():
    for shell in ("zsh", "sh"):
        scan = scan_shell_command("cd /var && ls -la", shell)
        assert scan.ok
        assert scan.cd_targets == ("/var",)
        assert "ls" in {c.canonical for c in scan.subcommands}


def test_w37_scan_powershell_subcommands_and_cd_targets():
    scan = scan_shell_command(r"Set-Location C:\work; Get-ChildItem -Force", "powershell")
    assert scan.ok and scan.error is None
    assert [c.canonical for c in scan.subcommands] == ["set-location", "get-childitem"]
    assert any("C:\\work" in target for target in scan.cd_targets)


def test_w37_scan_powershell_path_flag_cd_target():
    scan = scan_shell_command(r"Set-Location -Path C:\ops", "pwsh")
    assert scan.ok
    assert scan.cd_targets == (r"C:\ops",)


def test_w37_malformed_command_returns_scanner_error():
    scan = scan_shell_command("echo 'unterminated", "bash")
    assert not scan.ok
    assert scan.error
    assert scan.subcommands == ()


def test_w37_dynamic_command_returns_scanner_error():
    scan = scan_shell_command("echo $(whoami)", "bash")
    assert not scan.ok
    assert "$(" in scan.error


def test_w37_scanner_error_never_yields_an_allow_check():
    scan = scan_shell_command("echo `id`", "bash")
    assert not scan.ok
    assert scan_to_checks(scan) == ()


def test_w37_scan_to_checks_covers_each_subcommand_and_cd_target():
    scan = scan_shell_command("cd /tmp && rm -rf build", "bash")
    checks = scan_to_checks(scan)
    assert any(c.action == "execute" and "rm" in c.resource for c in checks)
    assert any(c.action == "external_directory" and c.resource == "/tmp" for c in checks)


def test_w37_scanned_command_is_compatible_with_existing_scanner_shape():
    from keel import shell_ast

    analysis = shell_ast.analyze("cat file.txt", "posix")
    scan = scan_shell_command("cat file.txt", "bash")
    assert scan.subcommands[0].canonical == analysis.commands[0].canonical
    assert scan.subcommands[0].operations == analysis.commands[0].operations
    assert scan.subcommands[0].args == analysis.commands[0].args


# ---------------------------------------------------------------------------
# W3.8 - default policy (env/key ask list with .env.example exception)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [".env", ".env.local", ".env.production", "config/.env", "config/.env.prod"])
def test_w38_env_reads_ask(path):
    assert is_sensitive_env_read("read", path)
    assert default_policy_decision("read", path).effect is Effect.ASK


def test_w38_env_example_is_excepted():
    assert not is_sensitive_env_read("read", ".env.example")
    assert default_policy_decision("read", ".env.example").effect is Effect.ALLOW
    assert not is_sensitive_env_read("read", "config/.env.example")


def test_w38_key_files_ask_and_ordinary_files_allow():
    for path in ("id_rsa", "certs/server.pem", "deploy.key"):
        assert default_policy_decision("read", path).effect is Effect.ASK
    for path in ("README.md", "src/main.py", "notes.txt"):
        assert default_policy_decision("read", path).effect is Effect.ALLOW


def test_w38_default_rules_include_env_ask_rules():
    rules = default_policy_rules()
    assert any(r.effect == EFFECT_ASK and r.resource in (".env", ".env.*") for r in rules)
    assert any(r.effect == EFFECT_ALLOW and r.resource == "*" for r in rules)


def test_w38_non_read_actions_are_not_env_guarded():
    assert default_policy_decision("write", ".env").effect is Effect.ALLOW


# ---------------------------------------------------------------------------
# W3.9 - approval replies and project-scoped persistence
# ---------------------------------------------------------------------------

def test_w39_once_allows_without_persisting(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    outcome = store.decide(
        ApprovalRequest("execute", "npm test", proposed_pattern="npm test*"),
        ApprovalReply.ONCE,
    )
    assert outcome.decision.effect is Effect.ALLOW
    assert outcome.persisted is False
    assert store.saved_patterns() == ()


def test_w39_always_persists_tool_proposed_pattern(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    outcome = store.decide(
        ApprovalRequest("execute", "npm test", proposed_pattern="npm test*"),
        ApprovalReply.ALWAYS,
    )
    assert outcome.decision.effect is Effect.ALLOW
    assert outcome.persisted is True
    assert len(store.saved_patterns()) == 1
    assert store.path.exists()
    assert store.path.stat().st_size > 0
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == 1


def test_w39_always_without_proposed_pattern_does_not_persist(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    outcome = store.decide(
        ApprovalRequest("execute", "npm test", proposed_pattern=""),
        ApprovalReply.ALWAYS,
    )
    assert outcome.decision.effect is Effect.ALLOW
    assert outcome.persisted is False
    assert store.saved_patterns() == ()


def test_w39_persistence_survives_restart(tmp_path):
    first = ApprovalStore(tmp_path, "project-a")
    first.decide(
        ApprovalRequest("execute", "npm test", proposed_pattern="npm test*"),
        ApprovalReply.ALWAYS,
    )
    restarted = ApprovalStore(tmp_path, "project-a")
    outcome = restarted.decide(ApprovalRequest("execute", "npm test unit"), ApprovalReply.ONCE)
    assert outcome.decision.effect is Effect.ALLOW
    assert "saved" in outcome.decision.reason.lower()
    assert outcome.persisted is False


def test_w39_different_project_scopes_are_isolated(tmp_path):
    a = ApprovalStore(tmp_path, "project-a")
    b = ApprovalStore(tmp_path, "project-b")
    a.decide(ApprovalRequest("execute", "npm test", "npm test*"), ApprovalReply.ALWAYS)
    assert b.saved_patterns() == ()
    assert a.path != b.path


def test_w39_configured_deny_can_never_be_overridden_by_always(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    deny = Rule("execute", "npm test*", "deny")
    outcome = store.decide(
        ApprovalRequest("execute", "npm test", proposed_pattern="npm test*"),
        ApprovalReply.ALWAYS,
        configured_rules=(deny,),
    )
    assert outcome.decision.effect is Effect.DENY
    assert store.saved_patterns() == ()


def test_w39_reject_clears_pending_requests_and_records_feedback(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    r1 = ApprovalRequest("execute", "cmd1", session_id="s1")
    r2 = ApprovalRequest("execute", "cmd2", session_id="s1")
    r3 = ApprovalRequest("execute", "cmd3", session_id="s2")
    for req in (r1, r2, r3):
        store.add_pending(req)
    rejected = store.reject_pending("s1", "stop doing that")
    assert {req.resource for req in rejected} == {"cmd1", "cmd2"}
    assert store.pending_for("s1") == ()
    assert store.pending_for("s2") == (r3,)
    assert store.feedback_for("s1") == "stop doing that"


def test_w39_corrupt_store_fails_closed(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    assert store.saved_patterns() == ()
    outcome = store.decide(ApprovalRequest("execute", "cmd"), ApprovalReply.ONCE)
    assert outcome.decision.effect is Effect.ALLOW  # once is an explicit reply


def test_w39_concurrent_approval_writes_are_lossless(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    count = 12
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            # Distinct instances exercise the cross-instance file lock.
            own = ApprovalStore(tmp_path, "project-a")
            own.decide(
                ApprovalRequest("execute", f"cmd{index}", f"cmd{index}*"),
                ApprovalReply.ALWAYS,
            )
        except BaseException as exc:  # pragma: no cover - diagnostic only
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors
    assert len(store.saved_patterns()) == count


# ---------------------------------------------------------------------------
# W3.10 - policy hard-deny floor
# ---------------------------------------------------------------------------

def test_w310_policy_floor_can_only_restrict():
    allow = Evaluation(Effect.ALLOW, reason="rule allow")
    deny = Evaluation(Effect.DENY, reason="managed policy deny")
    ask = Evaluation(Effect.ASK, reason="ask")

    assert apply_policy_floor(allow, deny).effect is Effect.DENY
    assert apply_policy_floor(allow, ask).effect is Effect.ASK
    assert apply_policy_floor(ask, allow).effect is Effect.ASK
    assert apply_policy_floor(deny, allow).effect is Effect.DENY


def test_w310_policy_never_grants():
    deny = Evaluation(Effect.DENY, reason="config deny")
    allow_policy = Evaluation(Effect.ALLOW, reason="policy allow")
    result = apply_policy_floor(deny, allow_policy)
    assert result.effect is Effect.DENY
    assert result.reason  # retains the authoritative decision's reason


def test_w310_managed_policy_overrides_project_config_by_floor():
    allow = Evaluation(Effect.ALLOW, reason="project allow")
    project = Evaluation(Effect.ASK, reason="project policy ask")
    managed = Evaluation(Effect.DENY, reason="managed policy deny")
    assert apply_policy_floors(allow, project, managed).effect is Effect.DENY
    assert apply_policy_floors(allow, managed, project).effect is Effect.DENY


def test_w310_floor_does_not_mutate_inputs():
    allow = Evaluation(Effect.ALLOW, reason="allow")
    result = apply_policy_floor(allow, Evaluation(Effect.DENY, reason="deny"))
    assert allow.effect is Effect.ALLOW
    assert result is not allow


# ---------------------------------------------------------------------------
# W3.12 - non-interactive fail-closed behaviour
# ---------------------------------------------------------------------------

def test_w312_no_responder_denies_ask():
    ask = Evaluation(Effect.ASK, reason="needs consent")
    result = resolve_noninteractive(ask, approve_mode=APPROVE_NEVER)
    assert result.effect is Effect.DENY
    assert "fail closed" in result.reason.lower() or "no interactive" in result.reason.lower()


def test_w312_configured_deny_always_enforced_noninteractively():
    deny = Evaluation(Effect.DENY, reason="config deny")
    assert resolve_noninteractive(deny, approve_mode=APPROVE_NEVER).effect is Effect.DENY
    assert resolve_noninteractive(deny, approve_mode=APPROVE_RULES_ONLY).effect is Effect.DENY


def test_w312_rules_only_does_not_persist_or_auto_approve_saved_asks():
    ask = Evaluation(Effect.ASK, reason="ask rule", matched_rule=Rule("execute", "x", "ask"))
    assert resolve_noninteractive(ask, approve_mode=APPROVE_RULES_ONLY).effect is Effect.DENY


def test_w312_default_mode_is_never_auto_approve():
    assert APPROVE_NEVER == "never"
    assert APPROVE_RULES_ONLY == "rules-only"
    with pytest.raises(ValueError):
        resolve_noninteractive(Evaluation(Effect.ASK), approve_mode="always")


def test_w312_approval_store_fails_closed_without_responder(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    outcome = store.decide(
        ApprovalRequest("execute", "cmd", "cmd*"),
        ApprovalReply.ONCE,
        non_interactive=True,
    )
    assert outcome.decision.effect is Effect.DENY


# ---------------------------------------------------------------------------
# W3.13 - documentation warning + allowlist preset
# ---------------------------------------------------------------------------

def test_w313_shell_authority_warning_is_present():
    assert "full host authority" in SHELL_AUTHORITY_WARNING.lower()
    assert "allowlist" in SHELL_AUTHORITY_WARNING.lower()
    assert "denylist" in SHELL_AUTHORITY_WARNING.lower()


def test_w313_cautious_preset_is_allowlist_style():
    assert CAUTIOUS_PRESET["style"] == "allowlist"
    assert CAUTIOUS_PRESET["default"] == EFFECT_ASK
    assert CAUTIOUS_PRESET["allowed"]
    assert CAUTIOUS_PRESET["denylist"] == ()
