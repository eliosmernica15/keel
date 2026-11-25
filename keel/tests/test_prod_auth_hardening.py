"""Production-hardening regressions and guarantees for auth/authz.

Scope (production candidate e6e7efc), owned modules only:

* ``keel.permissions``       -- Tier-1 evaluator; saved-execution-policy hard floor.
* ``keel.policy_enforcement`` -- command/URL policy boundary and confirm semantics.
* ``keel.permission_contracts`` -- ApprovalStore project/session isolation and
  cross-instance, cross-process write locking.

Two PRE-FIX defects are pinned here and must regress if reintroduced:

1. An explicit config ``allow`` (or ``ask``) rule returned from the Tier-1
   rule loop BEFORE the saved execution policy was consulted. A broad/exact
   allow rule therefore widened a ``forbidden`` exec policy, contradicting the
   binding-policy contract documented in ``permissions.evaluate`` itself.
2. ``ApprovalStore._file_lock`` caught only ``FileExistsError``. Windows
   raises ``PermissionError`` for the O_EXCL create race, which propagated and
   lost the approval write under multi-process contention.

The remaining tests are production-grade guarantees (fail-closed credentials,
deny-wins ordering, project/session isolation, revocation, alternate transports,
concurrent policy changes and 30-thread stress).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from keel import permissions as p
from keel.exec_policy import ExecPolicyStore
from keel.permission_contracts import (
    ApprovalReply,
    ApprovalRequest,
    ApprovalStore,
    Effect,
    Rule,
)

SRC = str(Path(__file__).resolve().parents[1] / "src")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _save_policy(tmp_path: Path, monkeypatch, doc: dict) -> None:
    """Persist the default exec policy and point settings at this state root."""
    ExecPolicyStore(tmp_path).save("default", doc)
    monkeypatch.setattr("keel.settings.default_state_root", lambda: str(tmp_path))


def _forbidden_policy(tmp_path: Path, monkeypatch, *, command=None, host=None) -> None:
    doc = {"prefix_rules": [], "network_rules": []}
    if command:
        doc["prefix_rules"].append(
            {"pattern": command.split(), "decision": "forbidden"})
    if host:
        doc["network_rules"].append(
            {"host": host, "protocol": "https", "decision": "forbidden"})
    _save_policy(tmp_path, monkeypatch, doc)


def _allowed_policy(tmp_path: Path, monkeypatch, command="ls") -> None:
    _save_policy(tmp_path, monkeypatch, {
        "prefix_rules": [{"pattern": command.split(), "decision": "allow"}],
        "network_rules": [],
    })


def _rules(*, allow=(), ask=(), deny=()):
    return (
        p.parse_rules("deny", list(deny))[0],
        p.parse_rules("ask", list(ask))[0],
        p.parse_rules("allow", list(allow))[0],
    )


# ---------------------------------------------------------------------------
# P0-1: config allow/ask rules must NOT widen a forbidden exec policy
# ---------------------------------------------------------------------------

def test_config_allow_rule_cannot_widen_forbidden_exec_policy(tmp_path, monkeypatch):
    """REGRESSION: exact allow rule used to short-circuit policy enforcement."""
    _forbidden_policy(tmp_path, monkeypatch, command="git reset --hard")
    allow = p.parse_rules("allow", ["run_shell(git reset --hard)"])[0][0]
    decision = p.evaluate(
        tool_name="run_shell", tool_input={"command": "git reset --hard"},
        rules=([], [], [allow]), mode=p.MODE_BYPASS, interactive=True)
    assert decision.decision == "deny"
    assert decision.source == "policy"
    assert "execution policy forbids" in decision.reason


def test_config_allow_rule_cannot_widen_forbidden_egress_policy(tmp_path, monkeypatch):
    """REGRESSION: WebFetch allow rule used to bypass the egress hard floor."""
    _forbidden_policy(tmp_path, monkeypatch, host="evil.test")
    allow = p.parse_rules("allow", ["web_fetch(domain:evil.test)"])[0][0]
    decision = p.evaluate(
        tool_name="web_fetch", tool_input={"url": "https://evil.test/exfil"},
        rules=([], [], [allow]), mode=p.MODE_BYPASS, interactive=True)
    assert decision.decision == "deny"
    assert decision.source == "policy"
    assert "egress policy forbids" in decision.reason


def test_config_ask_rule_cannot_widen_forbidden_policy(tmp_path, monkeypatch):
    """REGRESSION: an ask rule used to return 'ask' before policy was consulted."""
    _forbidden_policy(tmp_path, monkeypatch, command="git reset --hard")
    ask = p.parse_rules("ask", ["run_shell(git reset --hard)"])[0][0]
    decision = p.evaluate(
        tool_name="run_shell", tool_input={"command": "git reset --hard"},
        rules=([], [ask], []), mode=p.MODE_BYPASS, interactive=True)
    assert decision.decision == "deny"
    assert decision.source == "policy"


def test_config_deny_rule_still_precedes_policy_floor(tmp_path, monkeypatch):
    """GUARANTEE: D-001 config deny wins even before a policy allow."""
    _allowed_policy(tmp_path, monkeypatch, command="ls")
    # Keel prefix rules match literal tokens, so use an exact deny specifier.
    deny = p.parse_rules("deny", ["run_shell(ls -la)"])[0][0]
    decision = p.evaluate(
        tool_name="run_shell", tool_input={"command": "ls -la"},
        rules=([deny], [], []), mode=p.MODE_BYPASS, interactive=True)
    assert decision.decision == "deny"
    assert decision.source == "config"


def test_policy_allow_still_overrides_mode_baseline(tmp_path, monkeypatch):
    """GUARANTEE: no regression of the explicit-allow-over-mode contract."""
    _allowed_policy(tmp_path, monkeypatch, command="ls")
    decision = p.evaluate(
        tool_name="run_shell", tool_input={"command": "ls -la"},
        rules=_rules(), mode=p.MODE_DONT_ASK, interactive=False)
    assert decision.decision == "allow"
    assert decision.source == "policy"


def test_policy_prompt_fails_closed_without_responder(tmp_path, monkeypatch):
    """GUARANTEE: 'prompt' denies non-interactively and asks interactively."""
    _save_policy(tmp_path, monkeypatch, {
        "prefix_rules": [{"pattern": ["cp"], "decision": "prompt"}],
        "network_rules": [],
    })
    closed = p.evaluate(tool_name="run_shell", tool_input={"command": "cp a b"},
                        rules=_rules(), mode=p.MODE_BYPASS, interactive=False)
    assert closed.decision == "deny" and "consent" in closed.reason
    opened = p.evaluate(tool_name="run_shell", tool_input={"command": "cp a b"},
                        rules=_rules(), mode=p.MODE_BYPASS, interactive=True)
    assert opened.decision == "ask" and opened.source == "policy"


def test_concurrent_policy_change_is_observed_without_stale_cache(tmp_path, monkeypatch):
    """GUARANTEE: policy is re-read per evaluation, so a concurrent change binds."""
    _allowed_policy(tmp_path, monkeypatch, command="ls")
    first = p.evaluate(tool_name="run_shell", tool_input={"command": "ls -la"},
                       rules=_rules(), mode=p.MODE_DONT_ASK, interactive=False)
    assert first.decision == "allow"
    # Simulate a policy change made by another process between tool calls.
    _forbidden_policy(tmp_path, monkeypatch, command="ls -la")
    second = p.evaluate(tool_name="run_shell", tool_input={"command": "ls -la"},
                        rules=_rules(), mode=p.MODE_BYPASS, interactive=True)
    assert second.decision == "deny" and second.source == "policy"


def test_alternate_command_and_url_fields_cannot_bypass_policy(tmp_path, monkeypatch):
    """GUARANTEE: every command/URL carrying field reaches the policy boundary."""
    _forbidden_policy(tmp_path, monkeypatch, command="rm -rf /tmp/x")
    for tool_input in (
        {"command": "rm -rf /tmp/x"},
        {"cmd": "rm -rf /tmp/x"},
        {"argv": ["rm", "-rf", "/tmp/x"]},
        {"code": "rm -rf /tmp/x"},
        {"prompt": "rm -rf /tmp/x"},
    ):
        decision = p.evaluate(tool_name="run_tests", tool_input=tool_input,
                              rules=_rules(), mode=p.MODE_BYPASS, interactive=False)
        assert decision.decision == "deny", tool_input
        assert decision.source == "policy"
    _forbidden_policy(tmp_path, monkeypatch, host="blocked.test")
    decision = p.evaluate(tool_name="web_fetch",
                          tool_input={"endpoint": "https://blocked.test/x"},
                          rules=_rules(), mode=p.MODE_BYPASS, interactive=False)
    assert decision.decision == "deny" and decision.source == "policy"


# ---------------------------------------------------------------------------
# allowed_permissions / confirm semantics (read-only verification of entry points)
# ---------------------------------------------------------------------------

def test_capability_allowed_permissions_separation():
    """GUARANTEE: invoke() enforces allowed_permissions on every entry point."""
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import CapabilityError, get, invoke

    assert get("core.hardware.detect").permission == "read"
    assert get("core.flags.set").permission == "write"
    with pytest.raises(CapabilityError) as exc:
        invoke("core.flags.set", {"name": "x", "enabled": True},
               allowed_permissions={"read"})
    assert exc.value.code == "permission_denied"
    with pytest.raises(CapabilityError):
        invoke("core.hardware.detect", {}, allowed_permissions={"execute"})


def test_policy_confirm_semantics_in_enforce(tmp_path, monkeypatch):
    """GUARANTEE: confirm only grants a recorded approval, never a default."""
    from keel import policy_enforcement as pe

    _save_policy(tmp_path, monkeypatch, {
        "prefix_rules": [{"pattern": ["cp"], "decision": "prompt"}],
        "network_rules": [],
    })
    path = str(tmp_path)
    assert pe.enforce("run_shell", {"command": "cp a b"}, state_root=path,
                      interactive=False).decision == "deny"
    assert pe.enforce("run_shell", {"command": "cp a b"}, state_root=path,
                      interactive=True).decision == "ask"
    assert pe.enforce("run_shell", {"command": "cp a b"}, state_root=path,
                      interactive=True, confirmed=True).decision == "allow"
    assert pe.enforce("run_shell", {"command": "cp a b"}, state_root=path,
                      interactive=False, confirmed=True).decision == "allow"


# ---------------------------------------------------------------------------
# P0-2: ApprovalStore cross-instance / cross-process write locking
# ---------------------------------------------------------------------------

def test_approval_store_30_threads_lossless(tmp_path):
    """GUARANTEE: >=30 concurrent cross-instance writes lose nothing."""
    count = 30
    barrier = threading.Barrier(count + 1)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            store = ApprovalStore(tmp_path, "project-a")
            barrier.wait(timeout=30)
            store.decide(
                ApprovalRequest("execute", f"th{index:02d}", f"th{index:02d}*"),
                ApprovalReply.ALWAYS)
        except BaseException as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=30)
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors[:3]
    patterns = set(ApprovalStore(tmp_path, "project-a").saved_patterns())
    for index in range(count):
        assert ("execute", f"th{index:02d}*") in patterns
    assert not list(tmp_path.glob("*.tmp")), "atomic-write temp files leaked"


def test_approval_store_30_processes_lossless(tmp_path):
    """REGRESSION: O_EXCL lock races dropped writes under multi-process load."""
    count = 30
    sentinel = tmp_path / "go.flag"
    code = """
import sys, time, os
sys.path.insert(0, sys.argv[1])
while not os.path.exists(sys.argv[4]):
    time.sleep(0.005)
from keel.permission_contracts import ApprovalStore, ApprovalRequest, ApprovalReply
s = ApprovalStore(sys.argv[2], 'project-a')
s.decide(ApprovalRequest('execute', 'mp-' + sys.argv[3],
                         'mp-' + sys.argv[3]), ApprovalReply.ALWAYS)
"""
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code, SRC, str(tmp_path), f"{i:03d}", str(sentinel)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for i in range(count)
    ]
    sentinel.touch()
    errors = []
    for proc in procs:
        _, stderr = proc.communicate(timeout=90)
        if proc.returncode != 0:
            errors.append(stderr.decode("utf-8", "replace")[-500:])
    assert not errors, errors[:3]
    patterns = set(ApprovalStore(tmp_path, "project-a").saved_patterns())
    for index in range(count):
        assert ("execute", f"mp-{index:03d}") in patterns
    assert not list(tmp_path.glob("*.tmp")), "atomic-write temp files leaked"


# ---------------------------------------------------------------------------
# ApprovalStore isolation / tampering / revocation / fail-closed guarantees
# ---------------------------------------------------------------------------

def test_approval_store_project_isolation(tmp_path):
    a = ApprovalStore(tmp_path, "project-a")
    b = ApprovalStore(tmp_path, "project-b")
    a.decide(ApprovalRequest("execute", "npm test", "npm test*"), ApprovalReply.ALWAYS)
    assert b.saved_patterns() == ()
    assert a.path != b.path
    # A cross-project request must not be granted by the other project's allow.
    outcome = b.decide(ApprovalRequest("execute", "npm test"), ApprovalReply.ONCE)
    assert "saved" not in outcome.decision.reason.lower()


def test_approval_store_pending_isolation_across_sessions(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    store.add_pending(ApprovalRequest("execute", "cmd-s1", session_id="s1"))
    store.add_pending(ApprovalRequest("execute", "cmd-s2", session_id="s2"))
    rejected = store.reject_pending("s1", "no")
    assert [r.resource for r in rejected] == ["cmd-s1"]
    assert store.pending_for("s1") == ()
    assert [r.resource for r in store.pending_for("s2")] == ["cmd-s2"]
    assert store.feedback_for("s1") == "no"
    assert store.feedback_for("s2") == ""


def test_approval_store_configured_deny_is_a_hard_floor(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    deny = Rule("execute", "rm -rf*", "deny")
    outcome = store.decide(
        ApprovalRequest("execute", "rm -rf /", "rm -rf*"),
        ApprovalReply.ALWAYS, configured_rules=(deny,))
    assert outcome.decision.effect is Effect.DENY
    assert store.saved_patterns() == ()
    assert outcome.persisted is False


def test_approval_store_revoked_pattern_is_not_reused(tmp_path):
    """GUARANTEE: deleting a persisted allow (revocation) stops reuse at once."""
    store = ApprovalStore(tmp_path, "project-a")
    store.decide(ApprovalRequest("execute", "deploy", "deploy*"), ApprovalReply.ALWAYS)
    granted = store.decide(ApprovalRequest("execute", "deploy now"), ApprovalReply.ONCE)
    assert "saved" in granted.decision.reason.lower()
    # Revoke by removing the persisted approval (as a revoke workflow would).
    import json
    doc = json.loads(store.path.read_text(encoding="utf-8"))
    doc["allow_patterns"] = []
    store.path.write_text(json.dumps(doc), encoding="utf-8")
    after = store.decide(ApprovalRequest("execute", "deploy now"), ApprovalReply.ONCE)
    assert "saved" not in after.decision.reason.lower()
    assert after.decision.effect is Effect.ALLOW  # explicit once, nothing saved
    assert store.saved_patterns() == ()


def test_approval_store_corrupt_or_tampered_file_fails_closed(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    assert store.saved_patterns() == ()
    outcome = store.decide(ApprovalRequest("execute", "cmd"), ApprovalReply.ONCE)
    assert outcome.decision.effect is Effect.ALLOW  # explicit once, nothing persisted
    assert store.saved_patterns() == ()


def test_approval_store_noninteractive_never_auto_grants(tmp_path):
    store = ApprovalStore(tmp_path, "project-a")
    outcome = store.decide(
        ApprovalRequest("execute", "cmd", "cmd*"), ApprovalReply.ONCE,
        non_interactive=True)
    assert outcome.decision.effect is Effect.DENY
    assert outcome.persisted is False
