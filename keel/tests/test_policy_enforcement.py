"""A1.6/B3.4 — execution policy is enforced at real runtime boundaries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from keel import settings
from keel.exec_policy import ExecPolicyStore

ROOT = Path(__file__).resolve().parents[1]

POLICY = {
    "prefix_rules": [
        {"pattern": ["git", "reset", "--hard"], "decision": "forbidden",
         "justification": "destructive"},
        {"pattern": ["rm", "-rf"], "decision": "forbidden",
         "justification": "recursive delete"},
        {"pattern": ["ls"], "decision": "allow", "justification": "read only"},
        {"pattern": ["cp"], "decision": "prompt", "justification": "file copy"},
    ],
    "network_rules": [
        {"host": "allowed.example.com", "protocol": "https",
         "decision": "allow"},
        {"host": "blocked.example.com", "protocol": "https",
         "decision": "forbidden", "justification": "egress denied"},
    ],
}


@pytest.fixture
def active(tmp_path, monkeypatch):
    store = ExecPolicyStore(tmp_path)
    store.save("default", POLICY)
    monkeypatch.setattr(settings, "default_state_root", lambda: str(tmp_path))
    return tmp_path


def _rules():
    from keel.permissions import parse_rules

    return (parse_rules("deny", [])[0], parse_rules("ask", [])[0],
            parse_rules("allow", [])[0])


def _evaluate(name, tool_input, *, mode="bypassPermissions", interactive=False):
    from keel.permissions import evaluate

    return evaluate(tool_name=name, tool_input=tool_input, rules=_rules(),
                    mode=mode, interactive=interactive)


def test_dormant_without_saved_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "default_state_root", lambda: str(tmp_path))
    result = _evaluate("run_shell", {"command": "git reset --hard"})
    assert result.decision in ("allow", "ask", "deny")  # normal mode path
    assert result.source != "policy"


def test_forbidden_command_denied_even_in_bypass(active):
    for tool, field in (("run_shell", "command"),
                        ("run_tests", "command"),
                        ("run_build", "command"),
                        ("background_shell", "command")):
        result = _evaluate(tool, {field: "git reset --hard"})
        assert result.decision == "deny", tool
        assert result.source == "policy"


def test_alternate_command_fields_and_inline_shell(active):
    for tool_input in ({"cmd": "rm -rf /tmp/x"},
                       {"shellCommand": "rm -rf /tmp/x"},
                       {"text": "!rm -rf /tmp/x"}):
        result = _evaluate("inline_shell", tool_input)
        assert result.decision == "deny", tool_input


def test_prompt_requires_consent(active):
    noninteractive = _evaluate("run_shell", {"command": "cp a b"})
    assert noninteractive.decision == "deny"
    assert "consent" in noninteractive.reason
    interactive = _evaluate("run_shell", {"command": "cp a b"},
                            interactive=True)
    assert interactive.decision == "ask"
    assert interactive.source == "policy"


def test_explicit_allow_overrides_mode_baseline(active):
    result = _evaluate("run_shell", {"command": "ls -la"},
                       mode="dontAsk", interactive=False)
    assert result.decision == "allow"
    assert result.source == "policy"


def test_config_deny_still_precedes_policy(active):
    from keel.permissions import evaluate, parse_rules

    deny = parse_rules("deny", ["run_shell"])[0]
    rules = (deny, parse_rules("ask", [])[0], parse_rules("allow", [])[0])
    result = evaluate(tool_name="run_shell", tool_input={"command": "ls"},
                      rules=rules, mode="default", interactive=False)
    assert result.decision == "deny" and result.source == "config"


def test_noninteractive_workflow_path_enforced(active):
    from keel.permissions import evaluate_noninteractive

    result = evaluate_noninteractive("run_shell",
                                     {"command": "git reset --hard"},
                                     project_root=str(ROOT))
    assert result.decision == "deny" and result.source == "policy"


def test_egress_denied_host_at_permission_boundary(active):
    result = _evaluate("web_fetch",
                       {"url": "https://blocked.example.com/x"})
    assert result.decision == "deny" and result.source == "policy"
    allowed = _evaluate("web_fetch",
                        {"url": "https://allowed.example.com/x"})
    assert allowed.decision == "allow" and allowed.source == "policy"


def test_capability_hub_enforces_policy(active):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import CapabilityError, invoke

    with pytest.raises(CapabilityError) as exc:
        invoke("code.sandbox.run", {"code": "x", "command": "rm -rf /tmp/x"},
               context={"state_root": str(active)})
    assert exc.value.code == "policy_denied"


def test_policy_management_capabilities_are_not_self_blocked(active):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    result = invoke("core.execpolicy.evaluate",
                    {"command": "git reset --hard"},
                    context={"state_root": str(active)})
    assert result["result"]["decision"] == "forbidden"


def test_cli_activate_and_active(active):
    env = {**os.environ, "KEEL_STATE_DIR": str(active)}
    listed = subprocess.run([sys.executable, "-m", "keel", "execpolicy", "list"],
                            cwd=ROOT, capture_output=True, text=True,
                            timeout=60, env=env)
    assert "default" in listed.stdout
    state = subprocess.run([sys.executable, "-m", "keel", "execpolicy", "active"],
                           cwd=ROOT, capture_output=True, text=True,
                           timeout=60, env=env)
    assert json.loads(state.stdout)["active"] is True
