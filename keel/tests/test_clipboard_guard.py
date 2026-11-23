"""X5.9 clipboard/screen guard + X5.1/X5.5/X5.6 P0 policy descriptors.

All tests are pure: no real clipboard, screen, filesystem or network access.
Adversarial focus: no approval -> deny, tainted content flagged, no fabrication.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import keel.clipboard_guard as cg
from keel.clipboard_guard import (
    APPROVAL_EMPTY_APPROVER,
    APPROVAL_EMPTY_ID,
    APPROVAL_EXPIRED,
    APPROVAL_NOT_YET_VALID,
    APPROVAL_PURPOSE_MISMATCH,
    APPROVAL_SOURCE_MISMATCH,
    ChangeJournal,
    ClipboardScreenGuard,
    DESCRIPTOR_TAMPERED,
    EMPTY_PURPOSE,
    MassChangeGuard,
    MutationEvent,
    NO_APPROVAL,
    ProjectFlags,
    SensitiveProjectPolicy,
    TAINTED_CONTENT,
    TAINTED_SOURCE,
    TAINT_REQUIRES_ACK,
    UNKNOWN_SOURCE,
    Approval,
    fingerprint,
)


def _guard() -> ClipboardScreenGuard:
    return ClipboardScreenGuard(now=lambda: 1000)


def _approval(**overrides: object) -> Approval:
    values: dict[str, object] = {
        "approver": "owner",
        "source": "clipboard",
        "purpose": "paste",
        "approval_id": "appr-0001",
        "issued_at": 900,
        "expires_at": 2000,
    }
    values.update(overrides)
    return Approval(**values)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# X5.9 — explicit approval
# ---------------------------------------------------------------------------


def test_x59_no_approval_denies() -> None:
    decision = _guard().request(
        source="clipboard", purpose="paste", content="hello"
    )
    assert decision.allowed is False
    assert NO_APPROVAL in decision.reasons
    # Descriptor is still produced (no silent capture) and is content-free.
    assert decision.descriptor.content_fingerprint == fingerprint("hello")


def test_x59_explicit_approval_allows_clean_clipboard() -> None:
    decision = _guard().request(
        source="clipboard",
        purpose="paste",
        content="hello",
        approval=_approval(),
    )
    assert decision.allowed is True
    assert decision.reasons == ()
    assert decision.descriptor.tainted is False
    assert decision.descriptor.classification == "public"
    assert decision.descriptor.approved is True


def test_x59_expired_approval_denies() -> None:
    decision = _guard().request(
        source="clipboard",
        purpose="paste",
        content="hello",
        approval=_approval(expires_at=999),
    )
    assert decision.allowed is False
    assert APPROVAL_EXPIRED in decision.reasons


def test_x59_not_yet_valid_approval_denies() -> None:
    decision = _guard().request(
        source="clipboard",
        purpose="paste",
        content="hello",
        approval=_approval(issued_at=1001),
    )
    assert decision.allowed is False
    assert APPROVAL_NOT_YET_VALID in decision.reasons


def test_x59_scope_mismatch_denies() -> None:
    guard = _guard()
    wrong_source = guard.request(
        source="clipboard",
        purpose="paste",
        content="hello",
        approval=_approval(source="screen"),
    )
    wrong_purpose = guard.request(
        source="clipboard",
        purpose="paste",
        content="hello",
        approval=_approval(purpose="summarize"),
    )
    assert APPROVAL_SOURCE_MISMATCH in wrong_source.reasons
    assert APPROVAL_PURPOSE_MISMATCH in wrong_purpose.reasons
    assert wrong_source.allowed is False and wrong_purpose.allowed is False


def test_x59_missing_approver_or_id_denies() -> None:
    guard = _guard()
    no_approver = guard.request(
        source="clipboard",
        purpose="paste",
        content="x",
        approval=_approval(approver="   "),
    )
    no_id = guard.request(
        source="clipboard",
        purpose="paste",
        content="x",
        approval=_approval(approval_id=""),
    )
    assert APPROVAL_EMPTY_APPROVER in no_approver.reasons
    assert APPROVAL_EMPTY_ID in no_id.reasons
    assert no_approver.allowed is False and no_id.allowed is False


# ---------------------------------------------------------------------------
# X5.9 — fail closed
# ---------------------------------------------------------------------------


def test_x59_unknown_source_fails_closed() -> None:
    decision = _guard().request(
        source="kernel_memory",
        purpose="paste",
        content="x",
        approval=_approval(source="kernel_memory"),
    )
    assert decision.allowed is False
    assert UNKNOWN_SOURCE in decision.reasons
    assert decision.descriptor.tainted is False  # unknown source is not trusted


def test_x59_empty_purpose_fails_closed() -> None:
    decision = _guard().request(
        source="clipboard",
        purpose="   ",
        content="x",
        approval=_approval(purpose="   "),
    )
    assert decision.allowed is False
    assert EMPTY_PURPOSE in decision.reasons


def test_x59_tampered_approved_flag_cannot_grant() -> None:
    guard = _guard()
    descriptor = guard.describe(
        source="clipboard", purpose="paste", content="x", approval=_approval()
    )
    forged = replace(descriptor, approved=True)
    decision = guard.evaluate(forged, None)  # no real approval presented
    assert NO_APPROVAL in decision.reasons
    assert decision.allowed is False


def test_x59_unsupported_schema_denies() -> None:
    guard = _guard()
    descriptor = guard.describe(source="clipboard", purpose="paste", content="x")
    decision = guard.evaluate(replace(descriptor, schema="other/v9"), _approval())
    assert decision.allowed is False
    assert cg.UNSUPPORTED_SCHEMA in decision.reasons


# ---------------------------------------------------------------------------
# X5.9 — tainted-source rules
# ---------------------------------------------------------------------------


def test_x59_screen_source_is_tainted_and_flagged() -> None:
    decision = _guard().request(
        source="screen",
        purpose="summarize",
        content="a screenshot",
        approval=_approval(source="screen", purpose="summarize"),
    )
    assert decision.descriptor.tainted is True
    assert TAINTED_SOURCE in decision.descriptor.taint_reasons
    assert decision.descriptor.classification == "internal"
    assert decision.allowed is False
    assert TAINT_REQUIRES_ACK in decision.reasons


def test_x59_secret_content_is_flagged_and_denied() -> None:
    content = "token: sk-abcdefghijklmnopqrstuvwxyz012345"
    decision = _guard().request(
        source="clipboard",
        purpose="paste",
        content=content,
        approval=_approval(),
    )
    assert decision.descriptor.tainted is True
    assert any(r.startswith(TAINTED_CONTENT) for r in decision.descriptor.taint_reasons)
    assert decision.descriptor.classification == "secret"
    assert decision.allowed is False
    assert TAINT_REQUIRES_ACK in decision.reasons


def test_x59_private_key_block_flagged() -> None:
    decision = _guard().request(
        source="clipboard",
        purpose="paste",
        content="-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...",
        approval=_approval(),
        taint_acknowledgement="acknowledged",
    )
    assert decision.descriptor.classification == "secret"
    assert any("private_key_block" in r for r in decision.descriptor.taint_reasons)
    assert decision.allowed is True  # explicit ack present


def test_x59_taint_label_flagged() -> None:
    decision = _guard().request(
        source="clipboard",
        purpose="paste",
        content="hello",
        labels=["secret", "pii"],
        approval=_approval(),
    )
    assert decision.descriptor.tainted is True
    assert decision.descriptor.classification == "secret"
    assert decision.allowed is False


def test_x59_acknowledged_taint_allows_but_still_flags() -> None:
    decision = _guard().request(
        source="screen",
        purpose="summarize",
        content="a screenshot",
        approval=_approval(source="screen", purpose="summarize"),
        taint_acknowledgement="  Acknowledged ",
    )
    assert decision.allowed is True
    assert decision.descriptor.tainted is True  # flag survives the grant
    assert TAINTED_SOURCE in decision.descriptor.taint_reasons


def test_x59_weak_acknowledgement_is_not_a_grant() -> None:
    decision = _guard().request(
        source="screen",
        purpose="summarize",
        content="x",
        approval=_approval(source="screen", purpose="summarize"),
        taint_acknowledgement="yes-ish",
    )
    assert decision.allowed is False
    assert TAINT_REQUIRES_ACK in decision.reasons


# ---------------------------------------------------------------------------
# X5.9 — deterministic descriptors / no fabrication / no silent capture
# ---------------------------------------------------------------------------


def test_x59_descriptors_are_deterministic() -> None:
    guard = _guard()
    first = guard.describe(
        source="clipboard",
        purpose="paste",
        requested_by="agent",
        content="hello",
        labels=["pii", "secret"],
        approval=_approval(),
    )
    second = guard.describe(
        source="clipboard",
        purpose="paste",
        requested_by="agent",
        content="hello",
        labels=["secret", "pii"],
        approval=_approval(),
    )
    assert first.to_json() == second.to_json()
    assert first.to_json() == json.dumps(
        first.to_dict(), sort_keys=True, separators=(",", ":")
    )


def test_x59_absent_content_is_never_fabricated() -> None:
    descriptor = _guard().describe(source="clipboard", purpose="paste")
    assert descriptor.content_provided is False
    assert descriptor.content_length is None
    assert descriptor.content_fingerprint is None


def test_x59_fingerprint_is_exact_sha256() -> None:
    assert fingerprint("hello") == hashlib.sha256(b"hello").hexdigest()
    assert fingerprint("hello") == fingerprint("hello")
    assert fingerprint("hello") != fingerprint("hellp")


def test_x59_verify_descriptor_rejects_forged_fingerprint() -> None:
    guard = _guard()
    good = guard.describe(source="clipboard", purpose="paste", content="hello")
    assert guard.verify_descriptor(good, content="hello") is True
    forged = replace(good, content_fingerprint="0" * 64)
    assert guard.verify_descriptor(forged, content="hello") is False
    decision = guard.evaluate(forged, _approval(), verify_content="hello")
    assert DESCRIPTOR_TAMPERED in decision.reasons
    assert decision.allowed is False


def test_x59_verify_descriptor_rejects_tampered_taint() -> None:
    guard = _guard()
    real = guard.describe(source="screen", purpose="summarize", content="note")
    laundered = replace(
        real, tainted=False, taint_reasons=(), classification="public"
    )
    assert guard.verify_descriptor(laundered, content="note") is False
    decision = guard.evaluate(
        laundered,
        _approval(source="screen", purpose="summarize"),
        verify_content="note",
    )
    assert DESCRIPTOR_TAMPERED in decision.reasons
    assert decision.allowed is False


def test_x59_no_raw_content_leaks_into_decision_json() -> None:
    secret = "super-secret-value-1234567890"
    decision = _guard().request(
        source="clipboard", purpose="paste", content=secret, approval=_approval()
    )
    assert secret not in decision.to_json()
    assert decision.to_json() == json.dumps(
        decision.to_dict(), sort_keys=True, separators=(",", ":")
    )


def test_x59_module_has_no_os_clipboard_screen_or_network_imports() -> None:
    source = Path(cg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {
        "pyperclip",
        "pyautogui",
        "PIL",
        "ctypes",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "win32clipboard",
    }
    assert imports.isdisjoint(forbidden), imports & forbidden


# ---------------------------------------------------------------------------
# X5.1 — sensitive-project mode
# ---------------------------------------------------------------------------


def test_x51_sensitive_project_blocks_all_remote_kinds() -> None:
    flags = ProjectFlags(sensitive_project=True)
    for kind in ("remote_llm", "mcp", "connector", "webhook", "mystery"):
        assert SensitiveProjectPolicy.remote_allowed(flags, kind) is False


def test_x51_sensitive_project_allows_only_explicitly_local() -> None:
    flags = ProjectFlags(sensitive_project=True)
    assert SensitiveProjectPolicy.remote_allowed(flags, "local") is True
    assert SensitiveProjectPolicy.remote_allowed(flags, "builtin") is True
    assert SensitiveProjectPolicy.remote_allowed(flags, "local_model") is True


def test_x51_badge_and_non_sensitive_project() -> None:
    assert SensitiveProjectPolicy.badge(ProjectFlags(sensitive_project=True)) == "\N{LOCK}"
    assert SensitiveProjectPolicy.badge(ProjectFlags()) == ""
    assert SensitiveProjectPolicy.remote_allowed(ProjectFlags(), "remote_llm") is True


# ---------------------------------------------------------------------------
# X5.5 — mass-change guard
# ---------------------------------------------------------------------------


def test_x55_within_limit_is_not_a_breach() -> None:
    events = [
        MutationEvent(path=f"/repo/f{i}.py", action="modify", at=1000)
        for i in range(3)
    ]
    decision = MassChangeGuard(limit=3).evaluate(events, now=1000)
    assert decision.breached is False
    assert decision.count == 3
    assert decision.snapshot_digest is None
    assert decision.pause_agent is False


def test_x55_breach_pauses_and_snapshots() -> None:
    events = [
        MutationEvent(path=f"/repo/f{i}.py", action="modify", at=1000)
        for i in range(4)
    ]
    guard = MassChangeGuard(limit=3)
    decision = guard.evaluate(events, now=1000)
    assert decision.breached is True
    assert decision.pause_agent is True
    assert decision.snapshot_required is True
    assert decision.snapshot_digest is not None
    assert len(decision.snapshot_digest) == 64
    assert "mass_change_limit_exceeded" in decision.reasons
    assert guard.evaluate(events, now=1000).to_json() == decision.to_json()


def test_x55_out_of_window_and_non_counted_actions_ignored() -> None:
    guard = MassChangeGuard(limit=1)
    old = [MutationEvent(path=f"/old/{i}", action="delete", at=100) for i in range(10)]
    reads = [MutationEvent(path="/x", action="read", at=1000) for _ in range(10)]
    assert guard.evaluate(old, now=1000).count == 0
    assert guard.evaluate(reads, now=1000).count == 0
    assert guard.evaluate(old + reads, now=1000).breached is False


# ---------------------------------------------------------------------------
# X5.6 — filesystem change journal
# ---------------------------------------------------------------------------


def test_x56_records_reviews_and_reverts_as_a_set() -> None:
    journal = ChangeJournal()
    journal.record("t1", "/b.py", "delete", 2)
    journal.record("t1", "/a.py", "modify", 1)
    journal.record("t2", "/c.py", "create", 3)

    assert journal.paths("t1") == ("/a.py", "/b.py")
    assert [e.seq for e in journal.review("t1")] == [1, 2]
    plan = journal.revert_plan("t1")
    assert [e.path for e in plan] == ["/a.py", "/b.py"]  # reverse of record order
    assert [e.seq for e in plan] == [2, 1]
    assert all(e.task_id == "t1" for e in plan)
    assert [e.path for e in journal.review("t2")] == ["/c.py"]


def test_x56_journal_is_deterministic_and_has_no_apply_api() -> None:
    journal = ChangeJournal()
    journal.record("t1", "/a", "create", 1)
    assert journal.to_json("t1") == journal.to_json("t1")
    assert not any(name in dir(journal) for name in ("apply", "revert_all", "write"))
