"""Real HTTP E2E hardening of the desktop UI's bridge backend.

Every test in this module drives a real threaded HTTP server on an ephemeral
loopback port with real urllib/http.client requests -- no handler is called
directly. It covers the workflows the desktop UI performs (health/capability
discovery, Cowork/Code/Duet/Fleet capability invocation, folder picker,
attachment upload, prompt streaming) and the security properties that must
hold while doing so.

Three regressions are pinned here after being reproduced against baseline
463481e:

1. ``confirm: "false"`` (or any truthy non-boolean) bypassed the confirmation
   gate for write/execute capabilities.
2. A malformed path (embedded NUL) in ``/api/fs/list`` raised an unhandled
   ValueError and dropped the connection instead of returning a JSON error.
3. An invalid/negative Content-Length or a JSON array body on POST routes
   raised unhandled exceptions (dropped connection or an unbounded read).
"""

from __future__ import annotations

import base64
import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import keel.webapp as webapp
from keel import capability_registry  # noqa: F401 - populate the registry
from keel import settings_store

TOKEN = "e2e-bridge-token-9f3c21"


class Bridge:
    """Thin real-HTTP client around a live bridge server."""

    def __init__(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
        monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
        monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
        monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path / "state")
        self.tmp = tmp_path
        self.server = webapp.make_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        time.sleep(0.15)
        self.calls: list[dict] = []

    def req(self, path, *, method="GET", body=None, token=TOKEN, origin=None,
            extra_headers=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Keel-Token"] = token
        if origin:
            headers["Origin"] = origin
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            doc = raw
        self.calls.append({"method": method, "path": path,
                           "body": body, "status": status, "response": doc})
        return status, doc

    def raw(self, path, *, method="POST", body=b"{}", headers=None,
            timeout=5):
        """Send hand-crafted headers (e.g. a malformed Content-Length)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port,
                                          timeout=timeout)
        all_headers = {"X-Keel-Token": TOKEN,
                       "Content-Type": "application/json"}
        if headers is not None:
            all_headers.update(headers)
        try:
            conn.request(method, path, body=body, headers=all_headers)
            response = conn.getresponse()
            raw = response.read().decode("utf-8", errors="replace")
            status, doc = response.status, raw
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError:
                pass
        except Exception as exc:  # a dropped connection is itself a failure
            status, doc = type(exc).__name__, str(exc)
        finally:
            conn.close()
        self.calls.append({"method": method, "path": path,
                           "headers": headers, "status": status,
                           "response": doc})
        return status, doc

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    b = Bridge(tmp_path, monkeypatch)
    try:
        yield b
    finally:
        b.close()


def test_health_token_gating_and_no_leak(bridge):
    status, doc = bridge.req("/api/health", token=None)
    assert status == 403 and doc["error"] == "refused"
    assert TOKEN not in json.dumps(doc)

    status, doc = bridge.req("/api/health", token="not-the-token")
    assert status == 403 and TOKEN not in json.dumps(doc)

    status, doc = bridge.req("/api/health")
    assert status == 200 and doc["ok"] is True and doc["version"]

    status, doc = bridge.req(f"/api/health?t={TOKEN}", token=None)
    assert status == 200 and doc["ok"] is True


def test_capabilities_list_across_product_surfaces(bridge):
    status, doc = bridge.req("/api/capabilities")
    assert status == 200
    caps = doc["capabilities"]
    assert len(caps) >= 150
    by_id = {c["id"]: c for c in caps}
    assert by_id["core.hardware.detect"]["permission"] == "read"
    assert by_id["core.flags.set"]["permission"] == "write"
    assert by_id["code.sandbox.run"]["permission"] == "execute"
    for surface in ("cowork", "code", "duet", "fleet"):
        assert any(c["surface"] == surface for c in caps), surface

    status, filtered = bridge.req("/api/capabilities?surface=fleet")
    assert status == 200 and filtered["capabilities"]
    assert all(c["surface"] == "fleet" for c in filtered["capabilities"])

    assert bridge.req("/api/capabilities", token=None)[0] == 403


def test_read_capability_invoked_without_confirm(bridge):
    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body={"id": "core.hardware.detect",
                                   "params": {}})
    assert status == 200 and doc["ok"] is True
    assert doc["capability"] == "core.hardware.detect"
    assert "os" in doc["result"]

    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body={"id": "cowork.doc.qa",
                                   "params": {
                                       "question": "private local",
                                       "text": "Keel is local-first and private."}})
    assert status == 200 and doc["ok"] is True and doc["result"]["hits"]

    assert bridge.req("/api/capabilities/invoke", method="POST",
                      body={"id": "core.hardware.detect", "params": {}},
                      token=None)[0] == 403


def test_execute_capability_confirmation_gate(bridge):
    payload = {"id": "code.sandbox.run",
               "params": {"code": "print('bridge-e2e')", "timeout_s": 5}}
    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body=payload)
    assert status == 409 and doc["error"] == "confirmation_required"
    assert doc["permission"] == "execute"

    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body={**payload, "confirm": True})
    assert status == 200 and doc["ok"] is True
    assert doc["result"]["stdout"].strip() == "bridge-e2e"

    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body={**payload, "confirm": True},
                             origin="https://evil.test")
    assert status == 403 and TOKEN not in json.dumps(doc)


def test_confirm_must_be_a_real_boolean(bridge):
    """Regression: truthy non-booleans must never satisfy the confirm gate."""
    body = {"id": "core.flags.set",
            "params": {"name": "e2e-confirm", "enabled": True}}
    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body=body)
    assert status == 409 and doc["error"] == "confirmation_required"

    for bad in ("false", "true", 1, ["false"], {"approved": False}):
        status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                                 body={**body, "confirm": bad})
        assert status == 409, f"confirm={bad!r} bypassed the gate: {doc}"
        assert doc["error"] == "confirmation_required"

    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body={**body, "confirm": True})
    assert status == 200 and doc["ok"] is True


def test_workdir_set_reset_and_bad_path(bridge):
    status, doc = bridge.req("/api/workdir", method="POST",
                             body={"path": str(bridge.tmp)})
    assert status == 200 and doc == {"ok": True, "path": str(bridge.tmp)}
    status, doc = bridge.req("/api/workdir")
    assert status == 200 and doc["path"] == str(bridge.tmp)

    missing = bridge.tmp / "no-such-folder"
    status, doc = bridge.req("/api/workdir", method="POST",
                             body={"path": str(missing)})
    assert status == 400 and doc["error"] == "not a directory"
    assert bridge.req("/api/workdir")[1]["path"] == str(bridge.tmp)

    status, doc = bridge.req("/api/workdir", method="POST",
                             body={"path": None})
    assert status == 200 and doc == {"ok": True, "path": None}
    assert bridge.req("/api/workdir")[1]["path"] is None

    assert bridge.req("/api/workdir", method="POST",
                      body={"path": str(bridge.tmp)}, token=None)[0] == 403
    assert bridge.req("/api/workdir", method="POST",
                      body={"path": str(bridge.tmp)},
                      origin="https://evil.test")[0] == 403


def test_fs_list_token_gating_and_traversal_safety(bridge):
    (bridge.tmp / "only-a-directory").mkdir()
    secret = bridge.tmp / "secret.txt"
    secret.write_text("TOP SECRET FILE CONTENT")

    assert bridge.req("/api/fs/list?path=" + urllib.parse.quote(str(bridge.tmp)),
                      token=None)[0] == 403

    status, doc = bridge.req("/api/fs/list?path=" +
                             urllib.parse.quote(str(bridge.tmp)))
    assert status == 200 and doc["ok"] is True
    assert {d["name"] for d in doc["dirs"]} == {"only-a-directory"}
    assert "TOP SECRET FILE CONTENT" not in json.dumps(doc)
    assert doc["roots"]

    # A file is never listed or read through the directory picker.
    status, doc = bridge.req("/api/fs/list?path=" +
                             urllib.parse.quote(str(secret)))
    assert status == 400 and doc["error"] == "not a directory"
    assert "TOP SECRET FILE CONTENT" not in json.dumps(doc)

    # '..' traversal resolves to a real directory but exposes names only.
    status, doc = bridge.req("/api/fs/list?path=" +
                             urllib.parse.quote(str(bridge.tmp / "..")))
    assert status == 200 and doc["ok"] is True
    assert all(set(d) == {"name"} for d in doc["dirs"])
    assert "TOP SECRET FILE CONTENT" not in json.dumps(doc)

    status, doc = bridge.req("/api/fs/list?path=/no/such/directory")
    assert status == 404 and doc["error"] == "not found"
    assert TOKEN not in json.dumps(doc)


def test_fs_list_malformed_path_returns_json_error(bridge):
    """Regression: embedded NUL used to crash the handler connection."""
    status, doc = bridge.req("/api/fs/list?path=" +
                             urllib.parse.quote("C:\\Users\x00"))
    assert status == 400, doc
    assert "error" in doc and TOKEN not in json.dumps(doc)


def test_upload_safe_and_traversal_filenames(bridge):
    uploads = bridge.tmp / "state" / "uploads"
    status, doc = bridge.req("/api/upload", method="POST",
                             body={"name": "note.txt",
                                   "contentB64": base64.b64encode(
                                       b"hello cowork").decode()})
    assert status == 200 and doc["ok"] is True and doc["bytes"] == 12
    safe_path = Path(doc["path"])
    assert safe_path.parent == uploads and safe_path.read_bytes() == b"hello cowork"

    for malicious in ("../../evil.txt", "..\\..\\evil2.txt",
                      "C:\\Windows\\evil3.txt", "..", "....//evil4.txt"):
        status, doc = bridge.req("/api/upload", method="POST",
                                 body={"name": malicious,
                                       "contentB64": base64.b64encode(
                                           b"payload").decode()})
        assert status == 200, doc
        target = Path(doc["path"])
        assert target.parent == uploads, (malicious, target)
        assert ".." not in target.name and target.is_file()
        assert target.read_bytes() == b"payload"
    assert not (bridge.tmp / "evil.txt").exists()
    assert not (bridge.tmp / "evil2.txt").exists()

    assert bridge.req("/api/upload", method="POST",
                      body={"name": "a.txt", "contentB64": "aA=="},
                      token=None)[0] == 403
    assert bridge.req("/api/upload", method="POST",
                      body={"name": "a.txt", "contentB64": "aA=="},
                      origin="https://evil.test")[0] == 403


def test_upload_rejects_invalid_payloads(bridge):
    status, doc = bridge.req("/api/upload", method="POST", body={})
    assert status == 400 and "required" in doc["error"]

    status, doc = bridge.req("/api/upload", method="POST",
                             body={"name": "a.txt", "contentB64": "!!!bad!!!"})
    assert status == 400 and "base64" in doc["error"]

    blob = b"x" * (64 * 1024)
    status, doc = bridge.req("/api/upload", method="POST",
                             body={"name": "large.bin",
                                   "contentB64": base64.b64encode(blob).decode()})
    assert status == 200 and doc["bytes"] == len(blob)
    assert Path(doc["path"]).read_bytes() == blob


def test_post_body_malformed_length_and_shape(bridge):
    """Regression: malformed bodies crashed the handler or hung the socket."""
    status, doc = bridge.raw("/api/capabilities/invoke",
                             headers={"Content-Length": "abc"})
    assert status == 400, doc
    assert TOKEN not in json.dumps(doc)

    status, doc = bridge.raw("/api/capabilities/invoke",
                             headers={"Content-Length": "-1"})
    assert status == 400, doc
    assert TOKEN not in json.dumps(doc)

    status, doc = bridge.req("/api/capabilities/invoke", method="POST",
                             body=["not", "an", "object"])
    assert status == 400 and doc["error"] == "body must be an object"

    status, doc = bridge.req("/api/upload", method="POST",
                             body=["not", "an", "object"])
    assert status == 400 and doc["error"] == "body must be an object"

    status, doc = bridge.req("/api/workdir", method="POST",
                             body=["not", "an", "object"])
    assert status == 400 and doc["error"] == "body must be an object"


def test_product_routes_require_token_and_run_streams(bridge, monkeypatch):
    for path in ("/api/providers", "/api/surfaces", "/api/gateway",
                 "/api/v2/sessions", "/api/settings", "/api/fleet/bots"):
        status, doc = bridge.req(path, token=None)
        assert status == 403, (path, doc)

    for path in ("/api/providers", "/api/surfaces", "/api/gateway",
                 "/api/v2/sessions"):
        status, doc = bridge.req(path)
        assert status == 200, (path, doc)

    script = bridge.tmp / "canned.json"
    script.write_text(json.dumps(
        {"script": [[{"type": "text", "text": "bridge e2e run"}]]}),
        encoding="utf-8")
    monkeypatch.setenv("KEEL_FAKE_SCRIPT", str(script))
    status, doc = bridge.req("/api/run", method="POST",
                             body={"prompt": "say hi", "provider": "auto",
                                   "permission_mode": "default"})
    assert status == 200, doc
    lines = [json.loads(line) for line in doc.splitlines() if line.strip()]
    assert any(event.get("type") == "system" for event in lines)
    assert lines[-1]["type"] == "bridge"
    assert lines[-1]["subtype"] == "done"

    assert bridge.req("/api/run", method="POST", body={"prompt": "x"},
                      token=None)[0] == 403


def test_error_responses_never_contain_token(bridge):
    responses = [
        bridge.req("/api/health", token="wrong-token"),
        bridge.req("/api/capabilities", token="wrong-token"),
        bridge.req("/api/fs/list?path=/bad/path"),
        bridge.req("/api/fs/list?path=" + urllib.parse.quote("C:\\Users\x00")),
        bridge.req("/api/upload", method="POST",
                   body={"name": "x", "contentB64": "bad"}),
        bridge.req("/api/workdir", method="POST",
                   body={"path": str(bridge.tmp / "missing")}),
        bridge.req("/api/capabilities/invoke", method="POST",
                   body={"id": "no.such.capability", "params": {}}),
        bridge.req(f"/api/health?t={TOKEN}&path=bad", token=None),
    ]
    for status, doc in responses:
        assert TOKEN not in json.dumps(doc), (status, doc)
