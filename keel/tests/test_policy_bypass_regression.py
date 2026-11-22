"""Regression: execute capabilities cannot bypass a saved policy by field name."""

from __future__ import annotations

import json

from keel.exec_policy import ExecPolicyStore
from keel.policy_enforcement import command_from

DOC = {
    "prefix_rules": [
        {"pattern": ["danger-bin"], "decision": "forbidden",
         "justification": "denied by regression policy"},
    ],
    "network_rules": [],
}


def test_command_from_covers_argv_code_prompt():
    assert command_from("any", {"argv": ["danger-bin", "--x"]}) == \
        "danger-bin --x"
    assert command_from("any", {"code": "danger-bin x"}) == "danger-bin x"
    assert command_from("any", {"prompt": "danger-bin y"}) == "danger-bin y"


def test_saved_policy_denies_argv_capability(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import CapabilityError, invoke

    store = ExecPolicyStore(tmp_path)
    store.save("default", DOC)
    (tmp_path / "exec-policies" / "default.json").write_text(
        json.dumps(DOC), encoding="utf-8")
    try:
        invoke("core.os.sandbox.run", {"argv": ["danger-bin", "--x"]},
               context={"state_root": str(tmp_path)})
    except CapabilityError as exc:
        assert exc.code == "policy_denied"
    else:
        raise AssertionError("argv capability bypassed execution policy")
