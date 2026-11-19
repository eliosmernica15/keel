"""Milestone 3 acceptance tests — v2 runtime wired to the real agent stack.

Every test exercises production code: HTTP bridge -> compat shim ->
fleet.provider_turn -> Fleet.tools/Session -> openai-compatible adapter
-> (fake) network transport. Only the network edge is faked.
"""

import http.client
import json
import os
import sys
import time

import pytest

TOKEN = os.environ.get("KEEL_TOKEN", "tracetoken12345")

def _tool_turn_for(target):
    import compat_fakes as C
    return C.tool_call_turn("write_file",
                            {"path": str(target), "content": "written-by-keel-test"})


def _http(server):
    port = server.server_address[1]
    return http.client.HTTPConnection("127.0.0.1", port, timeout=20)


def _post(server, path, body, token=TOKEN):
    conn = _http(server)
    try:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Keel-Token"] = token
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _get(server, path, token=TOKEN):
    conn = _http(server)
    try:
        headers = {}
        if token is not None:
            headers["X-Keel-Token"] = token
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _delete(server, path, token=TOKEN):
    conn = _http(server)
    try:
        headers = {}
        if token is not None:
            headers["X-Keel-Token"] = token
        conn.request("DELETE", path, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _make_session(server):
    import uuid as _uuid
    status, body = _post(server, "/api/v2/sessions",
                         json.dumps({"title": f"t-{_uuid.uuid4().hex[:10]}"}))
    assert status == 201, body
    return json.loads(body)["id"]


def _wait_for_row(store, sid, kind, predicate=None, timeout=10.0):
    import compat_fakes as C
    return C.wait_for(
        lambda: next(
            (r for r in store.list_rows(sid, 0, 10_000)
             if r["kind"] == kind
             and (predicate is None or predicate(r["body"]))),
            None),
        timeout=timeout)


def _events(server, sid, since=0, timeout=10.0):
    """Read the SSE stream until `done` is seen or the timeout fires."""
    conn = _http(server)
    try:
        conn.request("GET", f"/api/v2/sessions/{sid}/events?since={since}",
                     headers={"X-Keel-Token": TOKEN})
        resp = conn.getresponse()
        buf = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = resp.fp.readline()
            except (TimeoutError, OSError):
                break
            if not line:
                break
            buf += line
            if b'"type": "done"' in buf or b'"type":"done"' in buf:
                break
        events = []
        for block in buf.split(b"\n\n"):
            block = block.strip()
            if block.startswith(b"data: "):
                try:
                    events.append(json.loads(block[6:]))
                except json.JSONDecodeError:
                    pass
        return resp.status, events, buf
    finally:
        conn.close()


# ---------------------------------------------------------------- 1, 2, 3
def test_create_and_message_roundtrip(compat_store, compat_server, monkeypatch):
    import compat_fakes as C
    C.make_fake_adapter(monkeypatch, [C.text_turn("pong from the runtime")])

    sid = _make_session(compat_server)

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         '{"text":"hello"}')
    assert status == 202, body

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done, "turn never completed"

    status, body = _get(compat_server, f"/api/v2/sessions/{sid}/messages")
    assert status == 200
    messages = json.loads(body)["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant"]
    assert messages[0]["content"] == "hello"
    assert messages[1]["content"] == "pong from the runtime"


# ---------------------------------------------------------------- 4, 10
def test_events_stream_in_order_and_replay(compat_store, compat_server, monkeypatch):
    import compat_fakes as C
    C.make_fake_adapter(monkeypatch, [C.text_turn("streaming works")])

    sid = _make_session(compat_server)
    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         '{"text":"stream please"}')
    assert status == 202
    assert _wait_for_row(compat_store, sid, "turn_end"), "turn never completed"

    status, events, raw = _events(compat_server, sid, since=0)
    assert status == 200
    types = [e.get("type") for e in events]
    assert "user" in types
    assert "assistant" in types
    assert "done" in types
    seqs = [e["seq"] for e in events if e.get("seq") is not None]
    assert seqs == sorted(seqs), "event seq not monotonically increasing"

    # replay from the middle: only rows strictly after the cursor
    if len(seqs) >= 2:
        cursor = seqs[0]
        _, replay, _ = _events(compat_server, sid, since=cursor)
        replay_seqs = [e["seq"] for e in replay if e.get("seq") is not None]
        assert all(s > cursor for s in replay_seqs)

    # far-future cursor: definitely no persisted events
    _, empty, _ = _events(compat_server, sid, since=10_000)
    assert empty == []


# ---------------------------------------------------------------- 5, 6, 7, 8
def _run_tool_turn(sid, server, store):
    status, _ = _post(server, f"/api/v2/sessions/{sid}/messages",
                      '{"text": "write the file"}')
    assert status == 202
    approval = _wait_for_row(
        store, sid, "approval",
        predicate=lambda b: b.get("status") == "pending")
    assert approval is not None, "no pending approval card appeared"
    return approval


def test_tool_requires_approval_then_approved_runs(compat_store, compat_server,
                                                   monkeypatch, tmp_path):
    import compat_fakes as C
    target = tmp_path / "keel-tool-test.txt"
    C.make_fake_adapter(monkeypatch, [
        _tool_turn_for(target),
        C.text_turn("tool output above"),
    ])

    sid = _make_session(compat_server)
    _run_tool_turn(sid, compat_server, compat_store)

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/approve", "{}")
    assert status == 200, body
    assert json.loads(body)["status"] == "approved"

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done

    steps = [r for r in compat_store.list_rows(sid, 0, 10_000)
             if r["kind"] == "step"]
    assert any(r["body"].get("status") == "done"
               and r["body"].get("name") == "write_file" for r in steps), steps
    assert target.read_text(encoding="utf-8") == "written-by-keel-test"


def test_tool_rejected_never_executes(compat_store, compat_server, monkeypatch, tmp_path):
    import compat_fakes as C
    target = tmp_path / "keel-tool-test-reject.txt"
    C.make_fake_adapter(monkeypatch, [
        _tool_turn_for(target),
        C.text_turn("understood, not writing it"),
    ])

    sid = _make_session(compat_server)
    _run_tool_turn(sid, compat_server, compat_store)

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/reject", "{}")
    assert status == 200, body
    assert json.loads(body)["status"] == "denied"

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done

    assert not target.exists(), "tool executed despite rejection"
    steps = [r for r in compat_store.list_rows(sid, 0, 10_000)
             if r["kind"] == "step"]
    assert not any(r["body"].get("status") == "done"
                   and r["body"].get("name") == "write_file" for r in steps)


def test_pending_endpoint_lists_approval(compat_store, compat_server, monkeypatch,
                                         tmp_path):
    import compat_fakes as C
    target = tmp_path / "keel-tool-test-pending.txt"
    C.make_fake_adapter(monkeypatch, [
        _tool_turn_for(target),
        C.text_turn("ok"),
    ])

    sid = _make_session(compat_server)
    _post(compat_server, f"/api/v2/sessions/{sid}/messages", '{"text":"echo"}')
    _wait_for_row(compat_store, sid, "approval",
                  predicate=lambda b: b.get("status") == "pending")

    status, body = _get(compat_server, f"/api/v2/sessions/{sid}/pending")
    assert status == 200
    approvals = json.loads(body)["approvals"]
    assert len(approvals) == 1
    assert approvals[0]["tool_name"] == "write_file"


def test_approval_wrong_id_rejected(compat_store, compat_server, monkeypatch,
                                    tmp_path):
    import compat_fakes as C
    target = tmp_path / "keel-tool-test-wrongid.txt"
    C.make_fake_adapter(monkeypatch, [
        _tool_turn_for(target),
        C.text_turn("ok"),
    ])

    sid = _make_session(compat_server)
    _post(compat_server, f"/api/v2/sessions/{sid}/messages", '{"text":"echo"}')
    _wait_for_row(compat_store, sid, "approval",
                  predicate=lambda b: b.get("status") == "pending")

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/approve",
                         '{"approval_id":"bogus-id"}')
    assert status == 404


# ---------------------------------------------------------------- 8, 9
def test_transcript_persists_across_restart(compat_store, compat_server, monkeypatch):
    import compat_fakes as C
    C.make_fake_adapter(monkeypatch, [C.text_turn("persistent words")])

    sid = _make_session(compat_server)
    _post(compat_server, f"/api/v2/sessions/{sid}/messages",
          '{"text":"remember"}')
    assert _wait_for_row(compat_store, sid, "turn_end")

    # simulate a bridge restart: a brand-new store object on the same file
    from keel.fleet.service import FleetStore
    fresh = FleetStore(compat_store._test_db_path)
    try:
        rows = fresh.list_rows(sid, 0, 10_000)
    finally:
        fresh.close()
    kinds = [r["kind"] for r in rows]
    assert kinds.count("message") >= 2  # user + assistant
    assistant = next(r for r in rows
                     if r["kind"] == "message" and r["body"].get("role") == "assistant")
    assert assistant["body"]["content"] == "persistent words"


# ---------------------------------------------------------------- 11
def _fake_error_adapter(monkeypatch, status):
    import compat_fakes as C
    import keel.providers.openai_compatible as oc
    import keel.providers.registry as registry

    def fake_build_adapter(name, *, api_key=None, transport=None):
        return oc.OpenAICompatibleAdapter(
            registry._PROVIDERS["openrouter"],
            api_key="fake-key-not-real",
            transport=C.error_transport(status))

    monkeypatch.setattr(registry, "build_adapter", fake_build_adapter)
    # resolve_chain needs a configured key to pick a provider at all
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fake-key-not-real")


def test_provider_authentication_error_recorded(compat_store, compat_server,
                                                monkeypatch):
    _fake_error_adapter(monkeypatch, 401)

    sid = _make_session(compat_server)
    status, _ = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                      '{"text":"hello"}')
    assert status == 202

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done
    assert done["body"]["terminal_reason"] == "provider_error"
    notices = [r["body"].get("text", "")
               for r in compat_store.list_rows(sid, 0, 10_000)
               if r["kind"] == "notice"]
    assert any("authentication_failed" in n for n in notices), notices


def test_provider_billing_error_recorded(compat_store, compat_server, monkeypatch):
    _fake_error_adapter(monkeypatch, 402)

    sid = _make_session(compat_server)
    status, _ = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                      '{"text":"hello"}')
    assert status == 202

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done
    assert done["body"]["terminal_reason"] == "provider_error"
    notices = [r["body"].get("text", "")
               for r in compat_store.list_rows(sid, 0, 10_000)
               if r["kind"] == "notice"]
    assert any("billing_error" in n for n in notices), notices


# ---------------------------------------------------------------- 11b
def test_concurrent_message_returns_409_busy(compat_store, compat_server, monkeypatch):
    import compat_fakes as C
    import keel.providers.registry as registry
    import threading

    entered = threading.Event()
    release = threading.Event()

    class _BlockingTransport:
        def __call__(self, request):
            body = C.openai_sse(C.text_turn("working on it"))

            def slow_iter():
                entered.set()
                release.wait(timeout=10)
                yield body

            return 200, {}, slow_iter()

    def fake_build_adapter(name, *, api_key=None, transport=None):
        import keel.providers.openai_compatible as oc
        return oc.OpenAICompatibleAdapter(
            registry._PROVIDERS["openrouter"],
            api_key="fake-key-not-real",
            transport=_BlockingTransport())

    monkeypatch.setattr(registry, "build_adapter", fake_build_adapter)
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fake-key-not-real")

    sid = _make_session(compat_server)
    status, _ = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                      '{"text":"first"}')
    assert status == 202
    assert entered.wait(timeout=5), "turn never entered the transport"

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         '{"text":"impatient second message"}')
    assert status == 409
    release.set()


# ---------------------------------------------------------------- 12
def test_cancel_active_run(compat_store, compat_server, monkeypatch):
    import json as _json
    import threading

    import compat_fakes as C
    import keel.providers.registry as registry

    entered = threading.Event()
    release = threading.Event()

    class _BlockingTransport:
        def __call__(self, request):
            body = C.openai_sse(C.text_turn("never gets out"))

            def slow_iter():
                entered.set()
                release.wait(timeout=10)
                yield body

            return 200, {}, slow_iter()

    def fake_build_adapter(name, *, api_key=None, transport=None):
        import keel.providers.openai_compatible as oc
        return oc.OpenAICompatibleAdapter(
            registry._PROVIDERS["openrouter"],
            api_key="fake-key-not-real",
            transport=_BlockingTransport())

    monkeypatch.setattr(registry, "build_adapter", fake_build_adapter)
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fake-key-not-real")

    sid = _make_session(compat_server)
    status, _ = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                      '{"text":"hold on"}')
    assert status == 202
    assert entered.wait(timeout=5), "turn never entered the transport"

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/cancel",
                         "{}")
    assert status == 200, body
    release.set()

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done
    assert done["body"]["terminal_reason"] == "cancelled"


# ---------------------------------------------------------------- 13
def test_unauthorized_and_unknown_sessions(compat_store, compat_server):
    status, _ = _get(compat_server, "/api/v2/sessions", "wrong-token")
    assert status == 403

    for method, path in (("POST", "/api/v2/sessions/nope/messages"),
                         ("POST", "/api/v2/sessions/nope/approve"),
                         ("POST", "/api/v2/sessions/nope/reject"),
                         ("POST", "/api/v2/sessions/nope/cancel")):
        status, _ = _post(compat_server, path, '{"text":"x"}', TOKEN)
        assert status == 404, (method, path)

    for path in ("/api/v2/sessions/nope",
                 "/api/v2/sessions/nope/messages",
                 "/api/v2/sessions/nope/events",
                 "/api/v2/sessions/nope/pending"):
        status, _ = _get(compat_server, path, TOKEN)
        assert status == 404, path

    status, _ = _post(compat_server, "/api/v2/sessions/nope/messages",
                      '{"text":""}')
    assert status in (400, 404)
