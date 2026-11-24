"""Production hardening: real HTTP boundary tests for keel.webapp.

Every request goes through an in-process ``ThreadingHTTPServer`` bound to
127.0.0.1.  No backend, capability or policy function is mocked: only process
state (HOME / KEEL_STATE_DIR / the ephemeral port) is redirected to pytest's
temporary directory, exactly as production operators do with KEEL_STATE_DIR.

The tests cover the two mutating JSON routes that matter in production
(``POST /api/capabilities/invoke`` and ``POST /api/backend-workflows/<name>``)
plus the shared auth, body-parsing, status-mapping, replay, cancellation and
streaming boundaries of the bridge.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import keel.webapp as webapp
from keel import backend_workflows as bw
from keel import settings
from keel.exec_policy import ExecPolicyStore

SRC = Path(__file__).resolve().parents[1] / "src"
_DEFAULT = object()


class Api:
    def __init__(self, server: object, root: Path):
        self.server = server
        self.root = root
        self.port = server.server_address[1]


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Api:
    """Real bridge on an ephemeral port with an isolated state root."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: str(tmp_path))
    monkeypatch.setattr(webapp, "_WORKDIR", None)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Api(server, tmp_path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _raw_request(api: Api, payload: bytes, *, timeout: int = 15) -> str:
    """Send a hand-crafted HTTP request with full header control."""
    with socket.create_connection(("127.0.0.1", api.port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
        chunks: list[bytes] = []
        try:
            while True:
                part = sock.recv(8192)
                if not part:
                    break
                chunks.append(part)
                if sum(len(c) for c in chunks) > 131072:
                    break
        except (socket.timeout, OSError):
            pass
    return b"".join(chunks).decode("utf-8", "replace")


def _request(
    api: Api,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    raw: bytes | None = None,
    token: object = _DEFAULT,
    headers: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict, str]:
    """Return (status, parsed JSON body, raw text) for one real HTTP call."""
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json")
    if token is not _DEFAULT:
        if token is not None:
            hdrs["X-Keel-Token"] = token  # type: ignore[assignment]
    else:
        hdrs["X-Keel-Token"] = webapp.token()
    if raw is None:
        raw = b"{}" if body is None and method in ("POST", "DELETE") else b""
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=timeout)
    try:
        conn.request(method, path, body=raw, headers=hdrs)
        response = conn.getresponse()
        text = response.read().decode("utf-8", "replace")
        status = response.status
    except (http.client.HTTPException, OSError, socket.timeout) as exc:
        # A dropped socket is a failure of the boundary, not a test crash: the
        # assertions below report it as status 0 with a readable explanation.
        return 0, {}, f"<transport error: {type(exc).__name__}: {exc}>"
    finally:
        conn.close()
    try:
        doc = json.loads(text)
    except ValueError:
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    return status, doc, text


def _post(api: Api, path: str, body: dict, **kw) -> tuple[int, dict, str]:
    return _request(api, "POST", path, body=body, **kw)


def _ledger(api: Api, name: str) -> list[dict]:
    path = api.root / "backend-workflows" / f"{name}-results.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Auth and authorization on the real boundary
# ---------------------------------------------------------------------------

def test_missing_and_invalid_token_refused(api: Api):
    routes = (
        ("/api/capabilities/invoke", {"id": "core.hardware.detect"}),
        ("/api/backend-workflows/request", {"confirm": True, "params": {}}),
    )
    for path, body in routes:
        for token in (None, "definitely-not-the-token"):
            status, doc, _ = _post(api, path, body, token=token)
            assert status == 403, (path, token, status, doc)
            assert doc.get("error") == "refused"


def test_hostile_nonascii_token_is_refused_not_a_dropped_socket(api: Api):
    # secrets.compare_digest(str, str) raises TypeError for non-ASCII input.
    # A credential is attacker-controlled, so the auth gate must fail closed
    # with the normal JSON 403 instead of crashing the request handler.
    status, doc, text = _request(api, "GET", "/api/health", token="\u00e4\u00e4")
    assert status == 403, (status, text)
    assert doc.get("error") == "refused"

    status, doc, text = _post(
        api, "/api/capabilities/invoke",
        {"id": "core.hardware.detect"}, token="\u00e4")
    assert status == 403, (status, text)
    assert doc.get("error") == "refused"


def test_origin_mismatch_refused_on_mutating_routes(api: Api):
    for path, body in (
        ("/api/capabilities/invoke", {"id": "core.hardware.detect"}),
        ("/api/backend-workflows/request", {"confirm": True, "params": {}}),
    ):
        status, _, _ = _post(api, path, body,
                             headers={"Origin": "https://evil.example"})
        assert status == 403

    status, doc, _ = _post(
        api, "/api/capabilities/invoke", {"id": "prod.api.unknown"},
        headers={"Origin": f"http://127.0.0.1:{api.port}"})
    assert status == 404  # valid origin reaches the real (unknown-cap) backend
    assert doc.get("code") == "not_found"


def test_confirm_gate_is_strict_boolean(api: Api):
    for bad in (None, False, 1, 0, "true", "false", []):
        body = {"id": "core.flags.set",
                "params": {"name": "x", "enabled": True}}
        if bad is not None:
            body["confirm"] = bad
        status, doc, _ = _post(api, "/api/capabilities/invoke", body)
        assert status == 409, (bad, status, doc)
        assert doc.get("error") == "confirmation_required"

        body = {"params": {}}
        if bad is not None:
            body["confirm"] = bad
        status, doc, _ = _post(api, "/api/backend-workflows/request", body)
        assert status == 409, (bad, status, doc)
        assert doc.get("error") == "confirmation_required"

    assert _ledger(api, "request") == []


# ---------------------------------------------------------------------------
# Hostile bodies: parsing, size limits, non-standard JSON
# ---------------------------------------------------------------------------

def test_malformed_json_and_non_object_body_are_400(api: Api):
    for raw in (b"{not json", b"[]", b"42", b'"text"', b"null"):
        status, doc, _ = _post(api, "/api/backend-workflows/request", {},
                               raw=raw)
        assert status == 400, (raw, status, doc)
        assert "error" in doc


def test_deeply_nested_json_is_400_not_a_dropped_connection(api: Api):
    # json.loads raises RecursionError (not JSONDecodeError) on deep nesting;
    # an uncaught exception closes the socket without any HTTP response.
    raw = b"[" * 3000 + b"]" * 3000
    status, doc, text = _post(api, "/api/backend-workflows/request", {},
                              raw=raw)
    assert status == 400, (status, text[:200])
    assert doc.get("error") == "invalid json"


def test_non_finite_json_constants_are_rejected(api: Api):
    for raw in (b'{"confirm":true,"params":{"x":NaN}}',
                b'{"confirm":true,"params":{"x":Infinity}}',
                b'{"confirm":true,"params":{"x":-Infinity}}'):
        status, doc, text = _post(api, "/api/capabilities/invoke", {}, raw=raw)
        assert status == 400, (raw, status, text[:200])
        assert doc.get("error") == "invalid json"

    # A settings write must not persist / echo non-standard JSON either.
    status, _, text = _post(api, "/api/settings", {},
                            raw=b'{"ui":{"bad":NaN}}')
    assert status == 400
    assert "NaN" not in text


def test_invalid_content_length_is_400(api: Api):
    for value in ("abc", "-1", "-999"):
        payload = (
            f"POST /api/backend-workflows/request HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{api.port}\r\n"
            f"X-Keel-Token: {webapp.token()}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {value}\r\n\r\n{{}}"
        ).encode("ascii")
        text = _raw_request(api, payload)
        assert " 400 " in text.splitlines()[0], text[:200]


def test_oversized_payload_is_413(api: Api):
    status, doc, _ = _post(
        api, "/api/backend-workflows/request",
        {"confirm": True, "params": {"blob": "A" * 400_000}})
    assert status == 413
    assert doc.get("error") == "params too large"
    assert _ledger(api, "request") == []


# ---------------------------------------------------------------------------
# Canonical status mapping, policy denial and auditable policy errors
# ---------------------------------------------------------------------------

def test_capability_policy_denial_maps_403(api: Api):
    ExecPolicyStore(api.root).save("default", {
        "prefix_rules": [
            {"pattern": ["git", "reset", "--hard"], "decision": "forbidden",
             "justification": "destructive"}],
        "network_rules": [],
    })
    status, doc, _ = _post(api, "/api/capabilities/invoke", {
        "id": "core.os.sandbox.run", "confirm": True,
        "params": {"argv": ["git", "reset", "--hard"]}})
    assert status == 403, (status, doc)
    assert doc.get("code") == "policy_denied"

    audit = api.root / "capability-audit.jsonl"
    records = [json.loads(line) for line in
               audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(r.get("code") == "policy_denied" and
               r.get("surface") == "web" for r in records)


def test_read_capability_needs_confirm_when_policy_prompts(api: Api):
    # TUI pre-flights a saved `prompt` rule and asks the user even for a
    # read-tier capability.  HTTP must apply the same rule before invoking.
    ExecPolicyStore(api.root).save("default", {
        "prefix_rules": [
            {"pattern": ["cp"], "decision": "prompt",
             "justification": "file copy needs consent"}],
        "network_rules": []})
    body = {"id": "core.ci.kickoff", "params": {"prompt": "cp a b"}}
    status, doc, _ = _post(api, "/api/capabilities/invoke", body)
    assert status == 409, (status, doc)
    assert doc.get("error") == "confirmation_required"

    status, doc, _ = _post(api, "/api/capabilities/invoke",
                           {**body, "confirm": True})
    assert status == 200, (status, doc)
    assert doc.get("ok") is True


def test_workflow_permission_denial_maps_403(api: Api):
    note = api.root / "secret.md"
    note.write_text("sensitive runbook", encoding="utf-8")
    status, doc, _ = _post(api, "/api/backend-workflows/request", {
        "confirm": True,
        "params": {"state_root": str(api.root), "project_root": str(api.root),
                   "file_path": str(note), "deny_rules": ["read_file"],
                   "idempotency_key": "http-denied-read"}})
    assert status == 403, (status, doc)
    assert doc.get("code") == "permission_denied"
    assert "sensitive runbook" not in json.dumps(doc)


def test_workflow_bad_params_400_unknown_workflow_404(api: Api):
    status, doc, _ = _post(api, "/api/backend-workflows/request",
                           {"confirm": True, "params": [1, 2, 3]})
    assert status == 400
    assert doc.get("code") == "bad_params"

    status, doc, _ = _post(api, "/api/backend-workflows/nope",
                           {"confirm": True, "params": {}})
    assert status == 404
    assert doc.get("error") == "unknown_workflow"


def test_malformed_saved_policy_is_json_error_and_audited(api: Api):
    # The CLI already degrades cleanly on a corrupt policy (policy_error).
    # The HTTP surface must do the same instead of dropping the connection.
    policy = api.root / "exec-policies" / "default.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("not json at all", encoding="utf-8")

    status, doc, text = _post(api, "/api/capabilities/invoke", {
        "id": "core.hardware.detect", "confirm": True, "params": {}})
    assert status == 400, (status, text[:200])
    assert doc.get("code") == "policy_error"

    audit = api.root / "capability-audit.jsonl"
    records = [json.loads(line) for line in
               audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(r.get("code") == "policy_error" and
               r.get("surface") == "web" for r in records)


def test_workflow_lock_timeout_is_structured_json(api: Api, monkeypatch):
    # Keep the real cross-process lock; only shorten its wait so the test does
    # not stall for the production 15-second budget.
    monkeypatch.setattr(bw, "_LOCK_TIMEOUT_SECONDS", 0.2)
    lock = api.root / "backend-workflows" / "request-results.jsonl.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held by another process\n", encoding="utf-8")

    status, doc, text = _post(api, "/api/backend-workflows/request",
                              {"confirm": True, "params": {}}, timeout=20)
    assert status == 400, (status, text[:200])
    assert doc.get("code") == "lock_timeout"
    assert doc.get("ok") is False


# ---------------------------------------------------------------------------
# Idempotency, concurrency and cancellation
# ---------------------------------------------------------------------------

def test_replay_denied_and_single_ledger_record(api: Api):
    body = {"confirm": True,
            "params": {"state_root": str(api.root),
                       "idempotency_key": "http-replay-key"}}
    first = _post(api, "/api/backend-workflows/approval", body)
    assert first[0] == 200 and first[1].get("ok") is True, first

    second = _post(api, "/api/backend-workflows/approval", body)
    assert second[0] == 400
    assert second[1].get("code") == "replay_denied"
    assert len(_ledger(api, "approval")) == 1


def test_concurrent_identical_requests_only_one_wins(api: Api):
    body = {"confirm": True,
            "params": {"state_root": str(api.root),
                       "idempotency_key": "http-concurrent-key"}}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: _post(api, "/api/backend-workflows/approval", body),
            range(8)))

    codes = [result[1].get("code") for result in results]
    statuses = [result[0] for result in results]
    assert statuses.count(200) == 1, (statuses, codes)
    assert codes.count("replay_denied") == 7, codes
    assert len(_ledger(api, "approval")) == 1


def test_kill_switch_cancels_and_revokes_old_token(
        api: Api, monkeypatch: pytest.MonkeyPatch):
    original = webapp.token()
    monkeypatch.setattr(webapp, "_TOKEN", original)  # restore after the test
    status, doc, _ = _post(api, "/api/kill-switch", {})
    assert status == 200 and doc.get("ok") is True
    assert isinstance(doc.get("cancelled"), int)
    new_token = doc.get("token")
    assert isinstance(new_token, str) and new_token != original

    assert _request(api, "GET", "/api/health", token=original)[0] == 403
    assert _request(api, "GET", "/api/health", token=new_token)[0] == 200


# ---------------------------------------------------------------------------
# Streaming, versioning and cross-surface consistency
# ---------------------------------------------------------------------------

def test_bypass_permissions_requires_accept_risk(api: Api):
    status, doc, _ = _post(api, "/api/run", {
        "prompt": "say hi", "permission_mode": "bypassPermissions"})
    assert status == 403
    assert "accept_risk" in doc.get("error", "")


def test_streaming_run_emits_done_marker(
        api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "canned.json"
    script.write_text(json.dumps(
        {"script": [[{"type": "text", "text": "prod api works"}]]}),
        encoding="utf-8")
    monkeypatch.setenv("KEEL_FAKE_SCRIPT", str(script))
    monkeypatch.setenv("PYTHONPATH", str(SRC) + os.pathsep +
                       os.environ.get("PYTHONPATH", ""))
    status, _, text = _post(api, "/api/run", {
        "prompt": "say hi", "provider": "auto",
        "permission_mode": "default"}, timeout=120)
    assert status == 200, text[:300]
    events = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert events[-1].get("type") == "bridge"
    assert events[-1].get("subtype") == "done"


def test_legacy_health_and_error_body_remain_compatible(api: Api):
    status, doc, _ = _request(api, "GET", "/api/health")
    assert status == 200 and doc.get("ok") is True
    assert isinstance(doc.get("version"), str) and doc["version"]

    status, doc, _ = _request(api, "GET", "/api/health", token=None)
    assert status == 403 and doc.get("error") == "refused"


def test_cli_policy_error_matches_http_rule(api: Api):
    policy = api.root / "exec-policies" / "default.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("not json at all", encoding="utf-8")
    env = dict(os.environ)
    env.update(HOME=str(api.root), USERPROFILE=str(api.root),
               KEEL_STATE_DIR=str(api.root),
               PYTHONPATH=str(SRC) + os.pathsep + env.get("PYTHONPATH", ""))
    result = subprocess.run(
        [sys.executable, "-m", "keel", "capability", "invoke",
         "core.hardware.detect"],
        cwd=str(api.root), env=env, capture_output=True, text=True,
        timeout=120)
    assert result.returncode == 1
    assert "policy_error" in result.stderr
