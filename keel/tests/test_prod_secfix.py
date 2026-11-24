"""Regression tests for the production security review (3 HIGH + 3 MEDIUM).

H-1  SSRF via unvalidated HTTP redirects
H-2  SSRF via DNS-rebinding TOCTOU between validation and connect
H-3  Tier-2 envelope bypass via symlink / Windows junction
M-4  Share artifacts leak tokens outside the shared DLP vocabulary
M-5  Caller-chosen state_root permits arbitrary directory creation
M-6  JSONL ledgers have no tamper-evident chain
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from keel import backend_workflows as bw
from keel import runner, safety
from keel import w7_x1_y5_d1_backend as w7

SECRET = "LOCAL-ONLY-METADATA-secret-9182"


# ---------------------------------------------------------------------------
# Shared local HTTP server (redirect targets are configurable per test)
# ---------------------------------------------------------------------------

@pytest.fixture
def hostile_server():
    state = {"redirect_to": "/secret"}
    port = [0]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            target = state["redirect_to"]
            if self.path in ("/redirect", "/loop"):
                body = b"redirecting"
                self.send_response(302)
                self.send_header("Location",
                                 "http://127.0.0.1:%d%s" % (port[0], target)
                                 if target.startswith("/") else target)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = SECRET.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port[0] = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"port": port[0], "state": state}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _fetch(url):
    return runner.RealTools()._web_fetch({"url": url})


# ---------------------------------------------------------------------------
# H-1 — redirects must be re-validated and bounded
# ---------------------------------------------------------------------------

def test_h1_redirect_to_loopback_is_refused(hostile_server, monkeypatch):
    port = hostile_server["port"]
    original_resolve = socket.getaddrinfo
    original_connect = socket.socket.connect
    attempted = []

    def public_dns(host, p, *args, **kwargs):
        if host in ("127.0.0.1", "::1", "localhost"):
            return original_resolve(host, p, *args, **kwargs)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 ("93.184.216.34", p or 0))]

    def reroute(self, address):
        attempted.append(address)
        # Public host is actually our local test service in this simulation.
        return original_connect(self, ("127.0.0.1", port))

    monkeypatch.setattr(socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(runner, "_ssrf_getaddrinfo", public_dns)
    monkeypatch.setattr(socket.socket, "connect", reroute)

    with pytest.raises(ValueError, match="local address"):
        _fetch("http://rebind.example.com:%d/redirect" % port)
    assert attempted and SECRET not in str(attempted)


def test_h1_redirect_chain_is_bounded(hostile_server, monkeypatch):
    """An endless chain of *valid* public redirects stops at the hop cap."""
    port = hostile_server["port"]
    hostile_server["state"]["redirect_to"] = (
        "http://rebind.example.com:%d/loop" % port)
    original_resolve = socket.getaddrinfo
    original_connect = socket.socket.connect
    hops = []

    def public_dns(host, p, *args, **kwargs):
        if host in ("127.0.0.1", "::1", "localhost"):
            return original_resolve(host, p, *args, **kwargs)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 ("93.184.216.34", p or 0))]

    def reroute(self, address):
        hops.append(address)
        return original_connect(self, ("127.0.0.1", port))

    monkeypatch.setattr(socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(runner, "_ssrf_getaddrinfo", public_dns)
    monkeypatch.setattr(socket.socket, "connect", reroute)

    with pytest.raises(ValueError, match="too many redirects"):
        _fetch("http://rebind.example.com:%d/loop" % port)
    assert len(hops) == runner._MAX_SSRF_REDIRECTS + 1


def test_h1_non_http_redirect_is_refused(hostile_server, monkeypatch):
    port = hostile_server["port"]
    hostile_server["state"]["redirect_to"] = "file:///etc/passwd"
    original_resolve = socket.getaddrinfo
    original_connect = socket.socket.connect

    def public_dns(host, p, *args, **kwargs):
        if host in ("127.0.0.1", "::1", "localhost"):
            return original_resolve(host, p, *args, **kwargs)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 ("93.184.216.34", p or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(runner, "_ssrf_getaddrinfo", public_dns)
    monkeypatch.setattr(socket.socket, "connect",
                        lambda self, address: original_connect(
                            self, ("127.0.0.1", port)))

    with pytest.raises(ValueError, match="http or https"):
        _fetch("http://rebind.example.com:%d/redirect" % port)


# ---------------------------------------------------------------------------
# H-2 — validate and connect use the same address
# ---------------------------------------------------------------------------

class _PinProbe(OSError):
    pass


def test_h2_rebinding_resolver_is_called_once_and_connection_is_pinned(monkeypatch):
    calls = []
    addresses = []

    def hostile_dns(host, port):
        calls.append((host, port))
        ip = "93.184.216.34" if len(calls) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]

    def observe(self, address):
        addresses.append(address)
        raise _PinProbe("stop before network I/O")

    monkeypatch.setattr(runner, "_ssrf_getaddrinfo", hostile_dns)
    monkeypatch.setattr(socket.socket, "connect", observe)

    with pytest.raises(urllib.error.URLError):
        _fetch("http://rebind.example.com:18939/secret")

    # A single resolution, and the only connect target is the *validated* IP.
    assert len(calls) == 1, calls
    assert addresses and all(ip == "93.184.216.34" for ip, _ in addresses), addresses


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "0.0.0.0", "224.0.0.1", "::1", "fc00::1",
    "fe80::1", "::ffff:127.0.0.1", "not-an-ip",
])
def test_h2_ssrf_ip_filter_rejects_internal_ranges(address):
    assert runner._ssrf_ip_allowed(address) is False


def test_h2_ssrf_ip_filter_allows_public_unicast():
    assert runner._ssrf_ip_allowed("93.184.216.34") is True
    assert runner._ssrf_ip_allowed("8.8.8.8") is True


# ---------------------------------------------------------------------------
# H-3 — Tier-2 classification follows symlinks / junctions
# ---------------------------------------------------------------------------

@pytest.fixture
def junction_to_secret(tmp_path):
    hidden = tmp_path / "hidden" / ".ssh"
    hidden.mkdir(parents=True)
    (hidden / "notes.txt").write_text("PRIVATE-CONTENT-abcdefg", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    link = workspace / "innocuous"

    made = False
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/j", str(link), str(hidden)],
                                capture_output=True, text=True)
        made = result.returncode == 0
    if not made:
        try:
            os.symlink(hidden, link, target_is_directory=True)
            made = True
        except (OSError, NotImplementedError):
            pass
    if not made:
        pytest.skip("symlink/junction creation is not supported here")
    return link / "notes.txt"


def test_h3_tier2_classifies_resolved_target(junction_to_secret):
    verdict = safety.tier2_check("read_file", {"path": str(junction_to_secret)})
    assert verdict.allowed is False
    assert "secret-bearing path" in verdict.reason


def test_h3_read_file_through_junction_is_blocked(junction_to_secret):
    with pytest.raises(ValueError, match="tier-2 refused|path refused"):
        runner.RealTools().invoke("read_file", {"path": str(junction_to_secret)})


def test_h3_safe_path_rejects_symlink_escape_outside_root(tmp_path, monkeypatch):
    outside = tmp_path / "outside-data"     # deliberately not secret-named
    outside.mkdir()
    (outside / "data.txt").write_text("other project", encoding="utf-8")
    workspace = tmp_path / "workspace2"
    workspace.mkdir()
    link = workspace / "link"
    made = False
    if os.name == "nt":
        made = subprocess.run(["cmd", "/c", "mklink", "/j", str(link), str(outside)],
                              capture_output=True, text=True).returncode == 0
    if not made:
        try:
            os.symlink(outside, link, target_is_directory=True)
            made = True
        except (OSError, NotImplementedError):
            pass
    if not made:
        pytest.skip("symlink/junction creation is not supported here")

    with pytest.raises(ValueError, match="escapes the authorized root"):
        runner.RealTools()._safe_path(str(link / "data.txt"))


def test_h3_resolution_is_always_applied(monkeypatch):
    """Deterministic fallback: classification must use the resolved path."""
    original = safety.resolved_path
    monkeypatch.setattr(
        safety, "resolved_path",
        lambda path: original(path) if ".ssh" not in str(path)
        else Path("/home/user/.ssh/id_rsa"))
    assert safety._classify_target("workspace/innocuous/notes.txt") is None
    assert safety._classify_target("workspace/.ssh/notes.txt") == "secret-bearing path"


# ---------------------------------------------------------------------------
# M-4 — a single DLP vocabulary for public share artifacts
# ---------------------------------------------------------------------------

def test_m4_share_view_redacts_shared_secret_vocabulary():
    text = (
        "JWT=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefghij "
        "aws=AKIAIOSFODNN7EXAMPLE "
        "router=sk-or-v1-abcdefghijklmnopqrstuvwxyz "
        "pem=-----BEGIN RSA PRIVATE KEY-----\\nMIIE\\n-----END RSA PRIVATE KEY----- "
        "auth=Bearer abcdef1234567890 "
        "The secret is purple monkey dishwasher 4242"
    )
    view = w7.public_share_view(
        {"messages": [{"role": "user", "content": text}],
         "tool_calls": [{"args": text}]},
        preview_chars=2000)
    rendered = w7.render_share_html(view)
    for needle in ("eyJhbGciOiJIUzI1NiJ9", "AKIAIOSFODNN7EXAMPLE", "sk-or-v1-",
                   "BEGIN RSA PRIVATE KEY", "Bearer abcdef1234567890",
                   "purple monkey dishwasher"):
        assert needle not in view["text"], needle
        assert needle not in rendered, needle
        assert all(needle not in item for item in view["tool_previews"]), needle


# ---------------------------------------------------------------------------
# M-5 — state_root confinement
# ---------------------------------------------------------------------------

@pytest.fixture
def confined_state(tmp_path, monkeypatch):
    base = tmp_path / "state"
    base.mkdir()
    monkeypatch.setenv("KEEL_STATE_DIR", str(base))
    return base


def test_m5_caller_cannot_choose_an_outside_state_root(confined_state, tmp_path):
    outside = tmp_path / "OUTSIDE"
    result = bw.run_approval_workflow({
        "state_root": str(outside), "action": "request",
        "request_id": "x", "idempotency_key": "outside"})
    assert result["code"] == "bad_state_root"
    assert not outside.exists()
    assert not (outside / "backend-workflows" / "approval-events.jsonl").exists()


def test_m5_subdirectory_of_trusted_base_is_allowed(confined_state):
    project = confined_state / "project-a"
    result = bw.run_approval_workflow({
        "state_root": str(project), "action": "request",
        "request_id": "y", "idempotency_key": "inside"})
    assert result["code"] == "ok"
    assert (project / "backend-workflows" / "approval-events.jsonl").is_file()


# ---------------------------------------------------------------------------
# M-6 — tamper-evident hash chain
# ---------------------------------------------------------------------------

def test_m6_records_carry_a_hash_chain(tmp_path):
    path = tmp_path / "chain.jsonl"
    for index in range(3):
        bw._append_jsonl(path, {"writer": index})
    records = bw._read_jsonl(path)
    assert [r["seq"] for r in records] == [1, 2, 3]
    assert [r["sequence"] for r in records] == [1, 2, 3]
    assert records[0]["prev_hash"] == "0" * 64
    for previous, record in zip(records, records[1:]):
        assert record["prev_hash"] == previous["hash"]
    assert len({r["hash"] for r in records}) == 3


def test_m6_forged_append_is_rejected(tmp_path):
    path = tmp_path / "chain.jsonl"
    bw._append_jsonl(path, {"writer": 1})
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"sequence": 999, "record_id": "forged", "ok": true}\n')
    with pytest.raises(bw.WorkflowError) as exc:
        bw._read_jsonl(path)
    assert exc.value.code == "ledger_integrity"
    with pytest.raises(bw.WorkflowError):
        bw._append_jsonl(path, {"writer": "after"})


def test_m6_modified_and_truncated_records_are_rejected(tmp_path):
    path = tmp_path / "chain.jsonl"
    for index in range(3):
        bw._append_jsonl(path, {"writer": index})
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    altered = [json.loads(line) for line in lines]
    altered[1]["payload"] = "tampered"
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in altered) + "\n",
                    encoding="utf-8")
    with pytest.raises(bw.WorkflowError, match="hash mismatch"):
        bw._read_jsonl(path)

    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(bw.WorkflowError):
        bw._read_jsonl(path)


def test_m6_legacy_plaintext_ledger_is_rejected(tmp_path):
    path = tmp_path / "legacy.jsonl"
    path.write_text('{"sequence": 1, "writer": "old"}\n', encoding="utf-8")
    with pytest.raises(bw.WorkflowError, match="unauthenticated legacy"):
        bw._read_jsonl(path)
