"""Fleet provider-backed agent tests.

A fake adapter replaces the provider registry's real HTTP adapter so no
network call is ever made. Everything between the HTTP boundary and the
database (message routing, history injection, step rows, turn_end,
provider error handling) is exercised for real.
"""

from __future__ import annotations

import json
import os

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.providers import registry as provider_registry
from keel.providers.base import (CapabilityRecord, ProviderError,
                                 RETRY_RATE_LIMIT)


class FakeAdapter:
    """Scripted stand-in for a real provider adapter.

    `script` is a class attribute the test sets before posting:
      plain       — a single text block + end_turn
      tool_read   — one read_file tool_use block, then a final text reply
      tool_write  — one write_file tool_use block (must be REFUSED by the
                    permission gate), then end_turn
      provider_error — raises ProviderError(retry_after, 429)
    """

    instances: list["FakeAdapter"] = []
    script: str = "plain"
    tool_path: str = "."
    followup_text: str = "Done."

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests = []
        FakeAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        script = FakeAdapter.script

        if script == "plain":
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0,
                   "text": "Hello, operator."}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "message_stop", "stop_reason": "end_turn"}
            return

        if script == "tool_read":
            if len(self.requests) > 1:
                script = "followup"  # second call: final text after tool_result
            else:
                yield {"event": "block_start", "index": 0,
                       "block": {"type": "tool_use",
                                 "id": "call_fake_read",
                                 "name": "read_file",
                                 "input": {"path": FakeAdapter.tool_path}}}
                yield {"event": "block_stop", "index": 0}
                yield {"event": "message_stop", "stop_reason": "tool_use"}
                return

        if script == "tool_write":
            if len(self.requests) > 1:
                script = "followup"
            else:
                yield {"event": "block_start", "index": 0,
                       "block": {"type": "tool_use",
                                 "id": "call_fake_write",
                                 "name": "write_file",
                                 "input": {"path": FakeAdapter.tool_path,
                                           "content": "must never be written"}}}
                yield {"event": "block_stop", "index": 0}
                yield {"event": "message_stop", "stop_reason": "tool_use"}
                return

        if script == "followup":
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0,
                   "text": FakeAdapter.followup_text}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "message_stop", "stop_reason": "end_turn"}
            return

        if script == "provider_error":
            raise ProviderError("limit hit", RETRY_RATE_LIMIT, 429,
                                retryable=True)

        raise AssertionError(f"unknown script {script!r}")


OPENROUTER = CapabilityRecord(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="openrouter/auto",
    supports_tools=True, supports_streaming=True,
)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    FakeAdapter.instances = []
    FakeAdapter.script = "plain"
    FakeAdapter.tool_path = "."
    # F1: approval cards left unanswered expire quickly in tests (5 minutes in prod)
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "1")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key" if cap.env_var ==
                        "KEEL_OPENROUTER_API_KEY" else "")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *args, **kwargs: FakeAdapter(
                            OPENROUTER, api_key="test-key"))

    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


import http.client
import threading


def _req(server, method, path, body=None, token=None):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=30)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Keel-Token": token or webapp.token(),
               "Content-Type": "application/json"}
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        doc = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        doc = {"raw": raw}
    return resp.status, doc


def _post(server, path, body, token=None):
    return _req(server, "POST", path, body, token)


def _get(server, path, token=None):
    return _req(server, "GET", path, None, token)


def _wait(predicate, timeout=8.0, interval=0.05):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _create_bot(server, name="Agent", engine="provider", **over):
    body = {"name": name, "engine": engine, **over}
    status, created = _post(server, "/api/fleet/bots", body)
    assert status == 201
    return created["bot"]


def _rows(server, bot_id):
    status, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    return body.get("rows", [])


def test_provider_turn_echoes_via_model(bridge):
    bot = _create_bot(bridge, engine="provider")
    status, body = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                         {"content": "hi"})
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    rows = _rows(bridge, bot["id"])
    kinds = [r["kind"] for r in rows]
    assert kinds.count("message") >= 2  # user + assistant
    assert kinds.count("turn_end") == 1
    assistant = next(r for r in rows
                     if r["kind"] == "message" and r["body"]["role"] == "assistant")
    assert "Hello" in assistant["body"]["content"]


def test_notes_are_injected_as_untrusted_context(bridge):
    bot = _create_bot(bridge, engine="provider", notes="be extremely terse")
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "hi"})
    assert status == 202
    assert _wait(lambda: bool(FakeAdapter.instances))
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    adapter = FakeAdapter.instances[0]
    first_message = adapter.requests[0].messages[0]
    content = first_message["content"]
    assert "<fleet-notes" in content
    assert "be extremely terse" in content
    assert "untrusted" in content
    assert "---" in content


def test_history_is_carried_into_second_turn(bridge):
    bot = _create_bot(bridge, engine="provider")
    _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
          {"content": "first thing"})
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
          {"content": "second thing"})
    assert _wait(lambda: sum(1 for r in _rows(bridge, bot["id"])
                             if r["kind"] == "turn_end") >= 2)
    adapter = FakeAdapter.instances[-1]
    same_session_content = adapter.requests[-1].messages[0]["content"]
    assert "first thing" in same_session_content or any(
        "first thing" in (m.get("content") or "")
        for m in adapter.requests[-1].messages)


def test_provider_error_writes_error_row_not_crash(bridge, monkeypatch):
    bot = _create_bot(bridge, engine="provider")

    class ErrorAdapter:
        def __init__(self):
            self.requests = []

        def describe(self):
            return OPENROUTER

        def complete(self, request):
            self.requests.append(request)
            raise ProviderError("limit hit", RETRY_RATE_LIMIT, 429,
                                retryable=True)

    monkeypatch.setattr(provider_registry, "build_adapter",
                        lambda name, *a, **k: ErrorAdapter())
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "boom"})
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    rows = _rows(bridge, bot["id"])
    notices = [r for r in rows if r["kind"] == "notice"]
    assert any("Provider error" in r["body"].get("text", "") for r in notices)
    turn_end = next(r for r in rows if r["kind"] == "turn_end")
    assert turn_end["body"]["terminal_reason"] == "provider_error"


def test_unknown_provider_surfaces_clearly(bridge):
    bot = _create_bot(bridge, engine="provider")
    status, body = _post(bridge, f"/api/fleet/bots/{bot['id']}/update",
                         {"provider": "not-a-provider"})
    assert status == 200
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "hi"})
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    rows = _rows(bridge, bot["id"])
    assert any("not-a-provider" == r["body"].get("provider") or
               "Unknown provider" in r["body"].get("text", "")
               for r in rows + [])
    assert any(r["kind"] == "turn_end"
               and r["body"]["terminal_reason"] == "provider_unknown"
               for r in rows)


def test_notes_and_history_survive_restart(bridge, tmp_path):
    bot = _create_bot(bridge, engine="provider", notes="cairn")
    _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
          {"content": "step one"})
    assert _wait(lambda: sum(1 for r in _rows(bridge, bot["id"])
                             if r["kind"] == "turn_end") >= 1)
    # from a new store handle, confirm data is durable
    from keel.fleet.service import FleetStore
    store = FleetStore(tmp_path / "fleet.db")
    reload_bot = store.get_bot(bot["id"])
    assert reload_bot["notes"] == "cairn"
    msgs = [r for r in store.list_rows(bot["id"])
            if r["kind"] == "message" and r["body"].get("role") == "user"]
    assert any(m["body"]["content"] == "step one" for m in msgs)


def test_per_agent_model_override_is_used(bridge):
    bot = _create_bot(bridge, engine="provider")
    status, body = _post(bridge, f"/api/fleet/bots/{bot['id']}/update",
                         {"provider": "openrouter",
                          "model": "openrouter/test-7b"})
    assert status == 200
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "hi"})
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    adapter = FakeAdapter.instances[0]
    assert adapter.requests[0].model == "openrouter/test-7b"
    rows = _rows(bridge, bot["id"])
    assistant = next(r for r in rows
                     if r["kind"] == "message" and r["body"]["role"] == "assistant")
    assert assistant["body"]["model"] == "openrouter/test-7b"
    assert assistant["body"]["engine"] == "openrouter"


def test_missing_credentials_reports_not_configured(bridge, monkeypatch):
    monkeypatch.setattr("keel.providers.registry._PROVIDERS", {})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "")
    bot = _create_bot(bridge, engine="provider")
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "hi"})
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    rows = _rows(bridge, bot["id"])
    turn_end = next(r for r in rows if r["kind"] == "turn_end")
    assert turn_end["body"]["terminal_reason"] == "not_configured"
    notice = next(r for r in rows if r["kind"] == "notice"
                  and "no provider is configured" in r["body"].get("text", ""))
    assert notice is not None


def test_tool_read_emits_step_rows_and_completes(bridge, tmp_path):
    target = tmp_path / "fact.txt"
    target.write_text("the sky is blue", encoding="utf-8")
    FakeAdapter.script = "tool_read"
    FakeAdapter.tool_path = str(target)
    FakeAdapter.instances = []
    bot = _create_bot(bridge, engine="provider")
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "read the file"})
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])))
    rows = _rows(bridge, bot["id"])
    steps = [r for r in rows if r["kind"] == "step"]
    names = [r["body"]["name"] for r in steps]
    assert "read_file" in names
    done = [r for r in steps
            if r["body"]["name"] == "read_file" and r["body"]["status"] == "done"]
    assert done, "expected a completed read_file step row"
    assistant = [r for r in rows
                 if r["kind"] == "message" and r["body"]["role"] == "assistant"]
    assert assistant, "expected an assistant reply after the tool result"


def test_consequential_tool_is_refused_without_approval(bridge, tmp_path):
    target = tmp_path / "must_not_exist.txt"
    FakeAdapter.script = "tool_write"
    FakeAdapter.tool_path = str(target)
    bot = _create_bot(bridge, engine="provider")
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "write the file"})
    assert status == 202
    # no decision is ever made: the card times out and the write is refused
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])),
                timeout=10)
    assert not target.exists(), "consequential tool ran without permission"
    rows = _rows(bridge, bot["id"])
    approval_rows = [r for r in rows if r["kind"] == "approval"]
    assert any(r["body"].get("status") == "expired" for r in approval_rows)
    notices = [r["body"]["text"] for r in rows if r["kind"] == "notice"]
    assert any("timed out" in text or "Refused" in text for text in notices)
    steps = [r for r in rows if r["kind"] == "step"
             and r["body"]["name"] == "write_file"]
    assert any(s["body"]["status"] == "error" for s in steps)
