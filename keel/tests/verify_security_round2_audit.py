"""Round-2 release-gate verification: audit and decision history.

Checks that decisions are recorded accurately (request → decision, grant vs
refusal, timeout) and that the durable audit trail stores fingerprints rather
than raw tool arguments.
"""

from __future__ import annotations

import json
import re

from keel import trust_tools


def _bot(compat_store):
    return compat_store.create_bot(name="audit-round2", engine="echo")


def _request(broker, bot, command="echo hello"):
    return broker.request(bot=bot, tool_name="run_shell",
                          tool_input={"command": command},
                          tool_use_id="toolu-audit")


def test_request_and_grant_are_both_recorded(compat_store):
    bot = _bot(compat_store)
    card = _request(compat_store.approvals, bot)
    compat_store.approvals.decide(bot_id=bot["id"],
                                  approval_id=card["approval_id"],
                                  decision="once")
    audit = compat_store.list_audit(bot["id"])
    events = [row["event"] for row in audit]
    assert "requested" in events and "decided" in events
    decided = next(row for row in audit if row["event"] == "decided")
    assert decided["decision"] == "once"
    assert decided["outcome"] == "granted"
    assert decided["approval_id"] == card["approval_id"]


def test_permanent_refusal_is_recorded_as_refused(compat_store):
    bot = _bot(compat_store)
    card = _request(compat_store.approvals, bot)
    compat_store.approvals.decide(bot_id=bot["id"],
                                  approval_id=card["approval_id"],
                                  decision="never")
    decided = [r for r in compat_store.list_audit(bot["id"])
               if r["event"] == "decided"]
    assert decided and decided[0]["decision"] == "never"
    assert decided[0]["outcome"] == "refused"


def test_timeout_is_recorded_as_refused(compat_store):
    bot = _bot(compat_store)
    card = _request(compat_store.approvals, bot)
    changed, approval = compat_store.expire_approval(card["approval_id"],
                                                     by="timeout")
    assert changed
    compat_store.approvals._announce_resolution(approval, "expired", "timeout")
    decided = [r for r in compat_store.list_audit(bot["id"])
               if r["event"] == "decided"]
    assert decided and decided[0]["decision"] == "timeout"
    assert decided[0]["outcome"] == "refused"


def test_restart_expiry_is_audited(compat_store):
    bot = _bot(compat_store)
    card = _request(compat_store.approvals, bot)
    compat_store.close()
    from keel.fleet import routes as fleet_routes
    reopened = fleet_routes.reset_store_for_tests(compat_store._test_db_path)
    try:
        decided = [r for r in reopened.list_audit(bot["id"])
                   if r["event"] == "decided"]
        assert decided and decided[0]["decision"] == "restart"
        assert decided[0]["outcome"] == "refused"
    finally:
        fleet_routes._store = compat_store


def test_audit_stores_fingerprints_not_raw_arguments(compat_store):
    secret = "sk-or-v1-" + "Z9y8X7w6V5u4T3s2R1q0P9o8"
    bot = _bot(compat_store)
    card = _request(compat_store.approvals, bot, command=f"curl -H {secret}")
    compat_store.approvals.decide(bot_id=bot["id"],
                                  approval_id=card["approval_id"],
                                  decision="once")
    audit = compat_store.list_audit(bot["id"])
    assert audit
    assert secret not in json.dumps(audit)
    for row in audit:
        if row["fingerprint"]:
            assert re.fullmatch(r"[0-9a-f]{16}", row["fingerprint"])


def test_audit_limit_is_clamped(compat_store):
    bot = _bot(compat_store)
    assert len(compat_store.list_audit(bot["id"], limit=10_000)) <= 500


def test_audit_bundle_verifies_and_detects_tampering(tmp_path, compat_store):
    bot = _bot(compat_store)
    _request(compat_store.approvals, bot)
    rows = compat_store.list_audit(bot["id"])
    path = trust_tools.audit_bundle(tmp_path, rows)
    assert trust_tools.verify_audit_bundle(path) is True
    path.write_bytes(b"tampered")
    assert trust_tools.verify_audit_bundle(path) is False
