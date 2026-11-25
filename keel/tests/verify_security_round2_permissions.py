"""Round-2 release-gate verification: permission tiers and approval broker.

Deterministic checks for deny/ask/allow ordering, once/always/never decisions,
stale-request protection and the "Python is authoritative" property.
"""

from __future__ import annotations

import pytest

from keel import permissions as perm
from keel import safety
from keel.fleet.approvals import APPROVAL_DECIDED_RACE_MSG, ApprovalBroker


def _rules(deny=(), ask=(), allow=()):
    return (perm.parse_rules("deny", list(deny))[0],
            perm.parse_rules("ask", list(ask))[0],
            perm.parse_rules("allow", list(allow))[0])


def _decide(tool_name="write_file", tool_input=None, *, deny=(), ask=(), allow=(),
            mode=perm.MODE_DEFAULT, interactive=True):
    return perm.evaluate(tool_name=tool_name, tool_input=tool_input or {},
                         rules=_rules(deny, ask, allow), mode=mode,
                         interactive=interactive)


# ---------------------------------------------------------------- Tier 1

def test_deny_beats_allow_regardless_of_rule_order():
    d = _decide(deny=["write_file(*)"], allow=["write_file"],
                tool_input={"path": "notes.txt"})
    assert d.decision == "deny" and d.reason_type == "rule"


def test_ask_rule_is_ask_when_interactive_and_deny_when_not():
    assert _decide(ask=["write_file(*)"], interactive=True).decision == "ask"
    d = _decide(ask=["write_file(*)"], interactive=False)
    assert d.decision == "deny" and d.reason_type == "consent_required"


def test_allow_rule_wins_over_mode_baseline():
    d = _decide(allow=["write_file(*)"], mode=perm.MODE_DONT_ASK,
                tool_input={"path": "notes.txt"})
    assert d.decision == "allow" and d.reason_type == "rule"


def test_dont_ask_mode_never_promotes_deny_to_ask():
    d = _decide(mode=perm.MODE_DONT_ASK, interactive=True,
                tool_input={"path": "notes.txt"})
    assert d.decision == "deny" and d.reason_type == "mode"


def test_unknown_mode_and_unknown_tool_fail_closed():
    with pytest.raises(perm.RuleSyntaxError):
        perm.normalize_mode("anything-goes")
    d = _decide(tool_name="totally_unknown_tool", mode=perm.MODE_BYPASS)
    assert d.decision == "deny"


def test_bare_deny_removes_tool_from_manifest():
    deny = perm.parse_rules("deny", ["write_file"])[0]
    assert "write_file" not in perm.manifest_tools(["write_file", "read_file"], deny)


# ------------------------------------------------------------ broker flow

@pytest.fixture()
def broker(compat_store):
    return compat_store.approvals


@pytest.fixture()
def bot(compat_store):
    return compat_store.create_bot(name="round2", engine="echo")


def _request(broker, bot, tool_name="run_shell", tool_input=None):
    return broker.request(bot=bot, tool_name=tool_name,
                          tool_input=tool_input or {"command": "echo hi"},
                          tool_use_id="toolu-round2")


def test_once_approves_without_standing_policy(broker, bot, compat_store):
    card = _request(broker, bot)
    changed, final, error = broker.decide(bot_id=bot["id"],
                                          approval_id=card["approval_id"],
                                          decision="once")
    assert changed and error is None and final["status"] == "approved"
    assert final["decision"] == "once"
    assert compat_store.get_policy(bot["id"], "run_shell") is None


def test_always_persists_a_standing_grant(broker, bot, compat_store):
    card = _request(broker, bot)
    broker.decide(bot_id=bot["id"], approval_id=card["approval_id"],
                  decision="always")
    assert compat_store.get_policy(bot["id"], "run_shell") == "always"
    decision = broker.policy_outcome(bot=bot, tool_name="run_shell",
                                     tool_input={"command": "echo later"})
    assert decision.decision == "allow" and decision.source == "fleet"


def test_never_persists_a_standing_refusal(broker, bot, compat_store):
    card = _request(broker, bot)
    broker.decide(bot_id=bot["id"], approval_id=card["approval_id"],
                  decision="never")
    assert compat_store.get_policy(bot["id"], "run_shell") == "never"
    decision = broker.policy_outcome(bot=bot, tool_name="run_shell",
                                     tool_input={"command": "echo later"})
    assert decision.decision == "deny"


def test_reject_is_a_oneoff_denial(broker, bot, compat_store):
    card = _request(broker, bot)
    changed, final, error = broker.decide(bot_id=bot["id"],
                                          approval_id=card["approval_id"],
                                          decision="reject")
    assert changed and error is None
    assert final["status"] == "denied" and final["decision"] == "reject"
    assert compat_store.get_policy(bot["id"], "run_shell") is None


def test_invalid_decision_is_refused(broker, bot):
    card = _request(broker, bot)
    ok, _, error = broker.decide(bot_id=bot["id"],
                                 approval_id=card["approval_id"],
                                 decision="allow_everything")
    assert not ok and error is not None
    assert compat_store_pending(broker, bot)


def compat_store_pending(broker, bot):
    return len(broker.store.list_pending_approvals(bot["id"])) == 1


def test_decision_is_scoped_to_its_agent(broker, bot, compat_store):
    other = compat_store.create_bot(name="other", engine="echo")
    card = _request(broker, bot)
    ok, _, error = broker.decide(bot_id=other["id"],
                                 approval_id=card["approval_id"],
                                 decision="once")
    assert not ok and error == "approval_not_found"
    assert compat_store_pending(broker, bot)


def test_stale_request_cannot_be_decided_twice(broker, bot):
    card = _request(broker, bot)
    assert broker.decide(bot_id=bot["id"], approval_id=card["approval_id"],
                         decision="once")[0] is True
    ok, _, error = broker.decide(bot_id=bot["id"],
                                 approval_id=card["approval_id"],
                                 decision="never")
    assert not ok and error == APPROVAL_DECIDED_RACE_MSG


def test_expired_request_is_not_decidable(broker, bot, compat_store):
    card = _request(broker, bot)
    changed, expired = compat_store.expire_approval(card["approval_id"],
                                                    by="timeout")
    assert changed and expired["status"] == "expired"
    ok, _, error = broker.decide(bot_id=bot["id"],
                                 approval_id=card["approval_id"],
                                 decision="once")
    assert not ok and error == APPROVAL_DECIDED_RACE_MSG


def test_decider_never_converts_a_denial(broker, bot):
    """The decider is consulted only for consent_required; a deny stays deny."""
    card = _request(broker, bot)
    broker.decide(bot_id=bot["id"], approval_id=card["approval_id"],
                  decision="never")
    decision = broker.decider(bot)({
        "tool_name": "run_shell", "tool_input": {"command": "echo hi"},
        "tool_use_id": "toolu-again",
    })
    assert decision.decision == "deny"


def test_decider_fails_closed_without_an_answer(broker, bot, monkeypatch):
    monkeypatch.setattr(broker, "timeout_s", 0.02)
    decision = broker.decider(bot)({
        "tool_name": "run_shell", "tool_input": {"command": "echo hi"},
        "tool_use_id": "toolu-timeout",
    })
    assert decision.decision == "deny"


# --------------------------------------------------------------- Tier 2

def test_tier2_refuses_secret_path_even_when_tier1_would_allow():
    d = _decide(allow=["write_file(**)"],
                tool_input={"path": "C:/home/.ssh/id_rsa"})
    assert d.decision == "allow"
    check = safety.tier2_check("write_file", {"path": "C:/home/.ssh/id_rsa"})
    assert check.allowed is False


def test_tier2_refuses_catastrophic_command():
    check = safety.tier2_check("run_shell", {"command": "mkfs.ext4 /dev/sda",
                                             "shell": "posix"})
    assert check.allowed is False
