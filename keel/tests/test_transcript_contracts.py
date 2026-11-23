"""Permanent contract-regression specs for the Y2.x transcript/history model.

One or more tests per not_started P0 registry ID:
Y2.1, Y2.2, Y2.3, Y2.4, Y2.5, Y2.6, Y2.7, Y2.8, Y2.14, Y2.20.

These specs are additive: they import only ``keel.transcript_contracts`` and
never mutate the live session loop, web app or CLI.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re

import pytest

import keel.transcript_contracts as tc


def _body(text: str) -> dict:
    return {"text": text}


def _tool_body(use_id: str, phase: str, text: str = "ok") -> dict:
    return {"tool_use_id": use_id, "phase": phase, "name": "read_file",
            "text": text}


# ---------------------------------------------------------------------------
# Y2.1 -- typed transcript rows, stable ids, seq, revisions, append-only
# ---------------------------------------------------------------------------


def test_row_kinds_and_strict_row_validation():
    assert {k.value for k in tc.RowKind} == {
        "system", "user", "assistant", "tool", "reasoning"}
    store = tc.TranscriptStore("s1")
    for kind in tc.RowKind:
        body = (_tool_body("u1", "call") if kind is tc.RowKind.TOOL
                else {"reasoning": "r"} if kind is tc.RowKind.REASONING
                else _body(kind.value))
        row = store.append(kind, body)
        assert row.kind is kind
        assert isinstance(row, tc.TranscriptRow)
    with pytest.raises(tc.InvalidRowError):
        store.append("not-a-kind", _body("x"))
    with pytest.raises(tc.InvalidRowError):
        store.append(tc.RowKind.USER, ["not", "a", "dict"])
    with pytest.raises(tc.InvalidRowError):
        store.append(tc.RowKind.TOOL, {"phase": "call"})  # no tool_use_id
    with pytest.raises(tc.InvalidRowError):
        store.append(tc.RowKind.TOOL, {"tool_use_id": "u9", "phase": "maybe"})
    with pytest.raises(tc.InvalidRowError):
        store.append(tc.RowKind.REASONING, {"text": "no reasoning blob"})


def test_stable_id_seq_timestamps_and_provenance_across_rewrite():
    store = tc.TranscriptStore("s2", clock=lambda: 1_700_000_000.0)
    prov = tc.Provenance(source="user", actor="alice", channel="cli")
    row = store.append(tc.RowKind.USER, _body("hello"), provenance=prov)
    assert (row.seq, row.updated_seq, row.generation) == (1, 1, 1)
    assert re.fullmatch(r"[0-9a-f]{16}", row.id)
    assert row.created_at.endswith("Z") and row.updated_at.endswith("Z")
    assert row.provenance == prov
    rewritten = store.rewrite(row.seq, _body("hello!"))
    assert rewritten.id == row.id
    assert rewritten.seq == row.seq
    assert rewritten.created_at == row.created_at
    assert rewritten.updated_seq > row.updated_seq
    assert rewritten.content_hash != row.content_hash
    assert store.rows() == (rewritten,)


def test_upsert_by_seq_on_reconnect_never_deletes_or_regresses():
    store = tc.TranscriptStore("s3")
    a = store.append(tc.RowKind.ASSISTANT, _body("streaming"))
    b = store.rewrite(a.seq, _body("streaming more"))
    c = store.append(tc.RowKind.USER, _body("next"))
    snapshot = store.rows()
    merged = tc.apply_snapshot(snapshot, (a,))
    assert merged == snapshot                    # stale frame loses
    assert len(merged) == 2
    merged2 = tc.apply_snapshot(snapshot[:1], (b, c))
    assert merged2 == (b, c)                     # newest frame wins, rows added
    assert [r.seq for r in merged2] == [1, 2]


def test_generation_reset_and_snapshot_round_trip():
    store = tc.TranscriptStore("s4")
    store.append(tc.RowKind.USER, _body("first conversation"))
    new_generation = store.reset_generation()
    assert new_generation == 2
    row = store.append(tc.RowKind.USER, _body("second conversation"))
    assert row.generation == 2 and row.seq == 2
    snap = store.snapshot()
    restored = tc.TranscriptStore.restore(json.loads(json.dumps(snap)))
    assert restored.rows() == store.rows()
    assert restored.revision == store.revision
    assert restored.generation == 2


def test_append_only_validation_rejects_mutations():
    store = tc.TranscriptStore("s5")
    a = store.append(tc.RowKind.USER, _body("a"))
    b = store.append(tc.RowKind.USER, _body("b"))
    with pytest.raises(tc.AppendOnlyViolation):
        tc.validate_append(store.rows(), a)                     # reused seq
    with pytest.raises(tc.AppendOnlyViolation):
        tc.validate_rows((a, dataclasses.replace(a, seq=5,
                                                 updated_seq=5)))  # reused id
    with pytest.raises(tc.AppendOnlyViolation):
        tc.validate_append(store.rows(), a, revision=99)        # wrong revision
    stale = tc.TranscriptRow(a.seq, a.id, a.updated_seq, a.kind, a.body,
                             a.created_at, a.created_at, a.provenance)
    with pytest.raises(tc.AppendOnlyViolation):
        tc.validate_rewrite(a, stale)
    with pytest.raises(tc.AppendOnlyViolation):
        tc.validate_rewrite(a, dataclasses.replace(a, id="other-id",
                                                   updated_seq=99))


def test_replay_hashes_are_byte_stable():
    store = tc.TranscriptStore("s6")
    store.append(tc.RowKind.USER, _body("héllo"),
                 provenance=tc.Provenance(source="user"))
    before = [r.content_hash for r in store.rows()]
    snap = json.dumps(store.snapshot(), sort_keys=True, ensure_ascii=False)
    after = [r.content_hash for r in tc.TranscriptStore.restore(json.loads(snap)).rows()]
    assert before == after


# ---------------------------------------------------------------------------
# Y2.2 -- separate model history, UI redaction, model-visible <=> logged
# ---------------------------------------------------------------------------


def _history_store() -> tc.TranscriptStore:
    store = tc.TranscriptStore("history")
    store.append(tc.RowKind.SYSTEM, _body("be helpful"))
    store.append(tc.RowKind.USER, _body("list files"))
    store.append(tc.RowKind.REASONING, {"reasoning": "need a  tool  call\n"})
    store.append(tc.RowKind.TOOL, _tool_body("u1", "call"))
    store.append(tc.RowKind.TOOL, _tool_body("u1", "result", "a.txt"))
    store.append(tc.RowKind.ASSISTANT, _body("a.txt"))
    invisible = store.append(tc.RowKind.USER, _body("transient note"),
                             model_visible=False)
    assert invisible.model_visible is False
    return store


def test_split_history_separates_model_items_from_ui_rows():
    split = tc.split_history(_history_store().rows())
    assert [item.role for item in split.model_items] == [
        "system", "user", "assistant", "tool", "tool", "assistant"]
    assert all(isinstance(r, tc.UiRow) for r in split.ui_rows)
    assert not any(r.redacted for r in split.ui_rows)
    assert split.reconciliation.ok
    assert all(item.seq in {r.row.seq for r in split.ui_rows}
               for item in split.model_items)


def test_ui_redaction_never_touches_model_history():
    rows = _history_store().rows()
    clean = tc.split_history(rows)
    redacted = tc.split_history(rows, ui_redactions={2: "[redacted]"})
    assert [i.content_hash for i in clean.model_items] == [
        i.content_hash for i in redacted.model_items]
    ui = next(r for r in redacted.ui_rows if r.row.seq == 2)
    assert ui.redacted is True and ui.display_content == "[redacted]"
    assert rows[1].body["text"] == "list files"
    assert clean.reconciliation.ok and redacted.reconciliation.ok


def test_model_visible_iff_logged_reconciliation():
    store = tc.TranscriptStore("recon")
    row = store.append(tc.RowKind.USER, _body("logged"))
    item = tc.model_item_from_row(row)
    with pytest.raises(tc.HistoryReconciliationError):
        tc.assert_reconciled((item,), ())
    with pytest.raises(tc.HistoryReconciliationError):
        tc.assert_reconciled((), (row,))
    tampered = tc.ModelItem(item.seq, item.source_id, item.role,
                            "different content", item.generation)
    result = tc.reconcile((tampered,), (row,))
    assert not result.ok and result.hash_mismatches == (item.seq,)
    tc.assert_reconciled((item,), (row,))


def test_reasoning_blob_is_passed_back_unchanged():
    blob = "chain  \n\tthought with 'quotes' and ünicode"
    store = tc.TranscriptStore("reason")
    row = store.append(tc.RowKind.REASONING, {"reasoning": blob})
    item = tc.model_item_from_row(row)
    assert item.reasoning == blob
    assert item.role == "assistant"
    assert item.content_hash == tc.content_hash({
        "role": item.role, "content": "", "reasoning": blob,
        "phase": "", "tool_use_id": "", "images": (),
        "generation": item.generation,
    })
    split = tc.split_history(store.rows())
    assert split.model_items[0].reasoning == blob


# ---------------------------------------------------------------------------
# Y2.3 -- last N screenshots inline, local refs only, no fabrication
# ---------------------------------------------------------------------------


def _screenshot(path, payload: bytes) -> tc.ScreenshotDescriptor:
    path.write_bytes(payload)
    return tc.describe_screenshot(str(path))


def test_descriptor_is_built_from_real_file_bytes(tmp_path):
    desc = _screenshot(tmp_path / "shot.png", b"png-bytes-1")
    assert desc.sha256 == hashlib.sha256(b"png-bytes-1").hexdigest()
    assert desc.byte_size == len(b"png-bytes-1")
    assert desc.local_path.endswith("shot.png")
    doc = json.dumps(desc.to_dict())
    assert "base64" not in doc and "data:" not in doc
    assert tc.ScreenshotDescriptor.from_dict(desc.to_dict()) == desc
    tc.assert_real_screenshot(desc)


@pytest.mark.parametrize("ref", [
    "http://example.com/a.png", "https://example.com/a.png",
    "ftp://example.com/a.png", "data:image/png;base64,AAAA",
    "//server/share/a.png", "\\\\server\\share\\a.png", "",
])
def test_only_local_file_refs_are_accepted(ref):
    assert tc.is_local_ref(ref) is False
    with pytest.raises(tc.ScreenshotReferenceError):
        tc.describe_screenshot(ref)


def test_local_paths_include_windows_and_relative_forms():
    assert tc.is_local_ref("C:\\tmp\\shot.png")
    assert tc.is_local_ref("/tmp/shot.png")
    assert tc.is_local_ref("shots/shot.png")


def test_missing_file_and_tampered_descriptor_are_rejected(tmp_path):
    with pytest.raises(tc.ScreenshotNotFoundError):
        tc.describe_screenshot(str(tmp_path / "missing.png"))
    desc = _screenshot(tmp_path / "shot.png", b"real")
    with pytest.raises(tc.ScreenshotContractError):
        dataclasses.replace(desc, sha256="0" * 64)
    with pytest.raises(tc.ScreenshotContractError):
        dataclasses.replace(desc, byte_size=999)


def test_ring_keeps_last_three_inline_and_prunes_older_images(tmp_path):
    ring = tc.ScreenshotRing()                       # default N=3
    assert ring.capacity == tc.DEFAULT_INLINE_SCREENSHOTS == 3
    descs = []
    for i in range(5):
        desc = _screenshot(tmp_path / f"s{i}.png", f"shot-{i}".encode())
        ring.add(desc)
        descs.append(desc)
    assert ring.inline_ids() == tuple(d.id for d in descs[-3:])
    items = tuple(tc.ModelItem(i + 1, f"row-{i}", "user", "look",
                               images=(descs[i].id,)) for i in range(5))
    report = ring.prune(items)
    assert report.kept_ids == tuple(d.id for d in descs[-3:])
    assert report.omitted_ids == tuple(d.id for d in descs[:2])
    assert all(len(i.images) <= 1 for i in report.items)
    assert all(not i.images or i.images[0] in ring.inline_ids()
               for i in report.items)
    assert all(b"shot-" not in json.dumps(i.to_dict()).encode()
               for i in report.items)              # no image bytes invented


def test_ring_capacity_is_configurable_and_bounded(tmp_path):
    ring = tc.ScreenshotRing(capacity=2)
    descs = []
    for i in range(4):
        desc = _screenshot(tmp_path / f"c{i}.png", f"cap-{i}".encode())
        ring.add(desc)
        descs.append(desc)
    assert len(ring.descriptors()) == 2
    assert ring.evicted_count == 2
    assert ring.inline_ids() == tuple(d.id for d in descs[-2:])
    empty = tc.ScreenshotRing(capacity=0)
    empty.add(descs[0])
    assert empty.inline_ids() == ()
    with pytest.raises(tc.ScreenshotContractError):
        tc.ScreenshotRing(capacity=-1)


# ---------------------------------------------------------------------------
# Y2.4 -- orphaned tool-call repair with an honest missing-result marker
# ---------------------------------------------------------------------------


def _orphan_store() -> tuple[tc.TranscriptStore, tc.TranscriptRow]:
    store = tc.TranscriptStore("orphans")
    store.append(tc.RowKind.ASSISTANT, _body("using tools"))
    good = store.append(tc.RowKind.TOOL, _tool_body("done", "call"))
    store.append(tc.RowKind.TOOL, _tool_body("done", "result", "fine"))
    orphan = store.append(tc.RowKind.TOOL, _tool_body("lost", "call"))
    return store, good


def test_find_orphan_tool_calls():
    store, good = _orphan_store()
    orphans = tc.find_orphan_tool_calls(store.rows())
    assert [o.tool_use_id for o in orphans] == ["lost"]
    assert good.body["tool_use_id"] == "done"


def test_repair_appends_honest_synthetic_result():
    store, _ = _orphan_store()
    repaired = tc.repair_orphaned_tool_calls(store)
    assert len(repaired) == 1
    row = repaired[0]
    body = row.body
    assert body["tool_use_id"] == "lost"
    assert body["phase"] == "result"
    assert body["synthetic"] is True
    assert body["honest_marker"] == "interrupted"
    assert body["status"] == "unknown"
    assert "no result" in body["content"].lower()
    assert row.provenance.synthetic is True
    assert row.model_visible is True
    assert tc.find_orphan_tool_calls(store.rows()) == ()


def test_repair_is_idempotent_and_never_claims_success():
    store, _ = _orphan_store()
    tc.repair_orphaned_tool_calls(store)
    assert tc.repair_orphaned_tool_calls(store) == ()
    assert len(store.rows()) == 5
    doc = json.dumps(store.rows()[-1].to_dict()).lower()
    assert "success" not in doc
    assert '"status": "ok"' not in doc
    assert "exit_code" not in doc


# ---------------------------------------------------------------------------
# Y2.14 -- credential-free VNC relay descriptor + server-side input filter
# ---------------------------------------------------------------------------


def _credentials() -> tc.VncCredentials:
    return tc.VncCredentials(host="10.0.0.5", port=5900,
                             username="admin", password="s3cr3t-pass")


def test_vnc_descriptor_never_contains_credentials():
    creds = _credentials()
    relay = tc.VncRelay(creds, session_id="s-vnc")
    desc = relay.descriptor()
    doc = json.dumps(desc.to_dict())
    for secret in (creds.password, creds.username, creds.host):
        assert secret not in doc
    exposed = set(desc.to_dict())
    assert not exposed.intersection({"password", "username", "host", "token",
                                     "credentials"})
    assert tc.assert_credential_free(desc, creds) is True


def test_vnc_watch_mode_drops_input_on_the_server():
    creds = _credentials()
    seam = tc.RecordingSeam()
    relay = tc.VncRelay(creds, mode=tc.RelayMode.WATCH, seam=seam)
    events = (tc.VncInputEvent("keyboard", {"key": "a"}),
              tc.VncInputEvent("pointer", {"x": 1}),
              tc.VncInputEvent("clipboard", {"text": "x"}))
    assert relay.receive_input(events) == ()
    assert seam.forwarded == ()
    takeover = tc.VncRelay(creds, mode=tc.RelayMode.TAKEOVER, seam=seam)
    assert takeover.receive_input(events) == events
    assert len(seam.forwarded) == 3


def test_vnc_descriptor_shape_and_validation():
    relay = tc.VncRelay(_credentials(), session_id="s-vnc")
    desc = relay.descriptor()
    assert desc.endpoint.startswith("/relay/vnc/")
    assert desc.mode is tc.RelayMode.WATCH
    assert desc.frame_only is True and desc.input_allowed is False
    assert re.fullmatch(r"[0-9a-f]{16}", desc.fingerprint)
    assert desc.to_dict()["mode"] == "watch"
    with pytest.raises(tc.VncRelayError):
        tc.VncCredentials(host="x", port=70000, username="u", password="p")
    with pytest.raises(tc.VncRelayError):
        tc.VncRelay(_credentials(), mode="admin")


# ---------------------------------------------------------------------------
# Y2.20 -- least-exposure defaults, allowlist, explicit share opt-in
# ---------------------------------------------------------------------------


def test_exposure_defaults_are_private_and_local():
    policy = tc.ExposurePolicy()
    assert policy.bind_host == "127.0.0.1"
    assert policy.auth_enabled is True
    assert policy.dev_login_enabled is False
    assert policy.signups_enabled is False
    assert policy.allowlist == ()
    assert policy.transcript_visibility is tc.Visibility.PRIVATE
    assert policy.screenshot_visibility is tc.Visibility.PRIVATE
    assert tc.validate_exposure(policy).allowed is True
    assert tc.effective_dev_login(policy) is False


def test_public_bind_requires_auth_and_allowlist():
    public = tc.ExposurePolicy(bind_host="0.0.0.0", auth_enabled=False)
    decision = tc.validate_exposure(public)
    assert decision.allowed is False
    assert any("auth" in r for r in decision.reasons)
    assert any("allowlist" in r for r in decision.reasons)
    safe = tc.ExposurePolicy(bind_host="0.0.0.0", auth_enabled=True,
                             allowlist=("@example.com",))
    assert tc.validate_exposure(safe).allowed is True
    assert tc.effective_dev_login(tc.ExposurePolicy(
        bind_host="0.0.0.0", dev_login_enabled=True)) is False


def test_allowlist_accepts_emails_and_domains_only():
    normalized = tc.normalize_allowlist([
        "Bob@Example.COM", "@example.com", "bob@example.com"])
    assert normalized == ("@example.com", "bob@example.com")
    assert tc.allowlist_matches("@example.com", "alice@example.com")
    assert tc.allowlist_matches("bob@example.com", "bob@example.com")
    assert not tc.allowlist_matches("@example.com", "alice@other.org")
    with pytest.raises(tc.AllowlistEntryError):
        tc.normalize_allowlist(["not-an-email"])
    with pytest.raises(tc.AllowlistEntryError):
        tc.normalize_allowlist(["@"])


def test_signup_refused_on_public_url_until_allowlist_is_set():
    public = tc.ExposurePolicy(bind_host="public.example", signups_enabled=True)
    assert tc.authorize_signup(public, "alice@example.com") is False
    allowed = tc.replace(public, allowlist=("@example.com",))
    assert tc.authorize_signup(allowed, "alice@example.com") is True
    assert tc.authorize_signup(allowed, "alice@other.org") is False
    assert tc.authorize_signup(tc.ExposurePolicy(), "alice@example.com") is False


def test_sharing_requires_explicit_opt_in():
    policy = tc.ExposurePolicy()
    with pytest.raises(tc.ExposureViolation):
        tc.can_expose(policy, "transcripts")
    with pytest.raises(tc.ExposureViolation):
        tc.can_expose(policy, "screenshots")
    shared = tc.share_transcripts(policy)
    assert policy.transcript_visibility is tc.Visibility.PRIVATE
    assert shared.transcript_visibility is tc.Visibility.SHARED
    assert tc.can_expose(shared, "transcripts") is True
    assert tc.can_expose(tc.share_screenshots(policy), "screenshots") is True
    public_shared = tc.ExposurePolicy(bind_host="0.0.0.0",
                                      transcript_visibility=tc.Visibility.SHARED)
    assert tc.validate_exposure(public_shared).allowed is False
    env = tc.env_reference()
    assert env["KEEL_BIND"] == "127.0.0.1"
    assert env["KEEL_SHARE_TRANSCRIPTS"] == "false"
    assert env["KEEL_SHARE_SCREENSHOTS"] == "false"


# ---------------------------------------------------------------------------
# Y2.5 -- per-agent serial queue and approval expiry
# ---------------------------------------------------------------------------


def test_serial_queue_runs_one_turn_per_agent():
    queue = tc.SerialTurnQueue()
    t1 = queue.enqueue("agent-a", "turn-1")
    t2 = queue.enqueue("agent-a", "turn-2")
    assert queue.start("agent-a") == t1
    assert queue.start("agent-a") is None
    other = queue.enqueue("agent-b", "turn-b")
    assert queue.start("agent-b") == other
    assert queue.finish("agent-a") == t1
    assert queue.start("agent-a") == t2


def test_user_message_expires_pending_approval():
    queue = tc.SerialTurnQueue()
    turn = queue.enqueue("agent-a", "turn-1")
    queue.start("agent-a")
    queue.request_approval("agent-a")
    assert queue.user_message("agent-a") == ("turn-1",)
    assert queue.snapshot("agent-a")["running"] is None
    assert queue.snapshot("agent-a")["expired"] == ("turn-1",)


# ---------------------------------------------------------------------------
# Y2.6 -- pending-turn persistence across restarts
# ---------------------------------------------------------------------------


def test_pending_turn_survives_restart(tmp_path):
    path = tmp_path / "pending_turns.json"
    pending = tc.PendingTurn("session-1", "turn-1", 2,
                             ({"tool_use_id": "u1", "name": "ask"},))
    tc.PendingTurnFileStore(path).save(pending)
    assert tc.PendingTurnFileStore(path).load("session-1") == (pending,)
    resumed = tc.PendingTurnFileStore(path).resume("session-1", "turn-1")
    assert resumed.status == "resumed" and resumed.answer == ""
    assert tc.PendingTurnFileStore(path).load("session-1") == (resumed,)


def test_pending_turn_rejects_invalid_state():
    with pytest.raises(tc.PendingTurnError):
        tc.PendingTurn("s", "", 1, ())
    with pytest.raises(tc.PendingTurnError):
        tc.PendingTurn("s", "t", 1, (), status="unknown")
    with pytest.raises(tc.PendingTurnError):
        tc.PendingTurn.from_dict({"session_id": "s"})


# ---------------------------------------------------------------------------
# Y2.7 -- Allow / Always allow / Don't allow
# ---------------------------------------------------------------------------


def test_approval_buttons_and_no_retry_instruction():
    card = tc.ApprovalCard("shell", "u1")
    policy = tc.ApprovalPolicyStore()
    once = tc.resolve_approval(card, tc.ApprovalChoice.ALLOW)
    assert once.execute is True and once.no_retry is False
    always = tc.resolve_approval(card, tc.ApprovalChoice.ALWAYS_ALLOW, policy)
    assert always.execute is True and policy.is_always_allowed("shell")
    assert "shell" in always.stored_tools
    denied = tc.resolve_approval(card, tc.ApprovalChoice.DONT_ALLOW, policy)
    assert denied.execute is False and denied.no_retry is True
    assert "do not retry" in denied.instruction.lower()
    assert denied.stored_tools == ()


# ---------------------------------------------------------------------------
# Y2.8 -- read-only connector classification by explicit flag, slug fallback
# ---------------------------------------------------------------------------


def test_connector_tool_classification_manifest_slug_meta_and_batch():
    explicit = tc.classify_connector_tool(
        "crm_DELETE", manifest_flags={"readOnly": True})
    assert explicit.read_only is True and explicit.basis == "manifest"
    assert explicit.warning == ""
    slug = tc.classify_connector_tool("github_LIST_REPOS")
    assert slug.read_only is True and slug.basis == "slug"
    assert "warning" in slug.warning.lower()
    meta = tc.classify_connector_tool("shell_GET_STATUS")
    assert meta.needs_approval is True and meta.basis == "meta"
    write = tc.classify_connector_tool("crm_UPDATE_CONTACT")
    assert write.read_only is False and write.needs_approval is True
    batch = tc.classify_connector_tool("batch_run", inner_tools=("crm_DELETE",))
    assert batch.needs_approval is True
    warned: list[str] = []
    tc.classify_connector_tool("db_GET", warn=warned.append)
    assert warned and "slug" in warned[0].lower()
