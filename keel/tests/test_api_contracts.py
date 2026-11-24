"""Shared API-contract helpers + characterization of current surface formats.

The helpers in ``keel.api_contracts`` are additive, so today's endpoints have
not adopted them yet. This file therefore does two things:

1. Unit-tests the canonical envelope helpers directly.
2. Probes the *real* web bridge / capability hub / CLI and pins their current
   response shapes, then records (in ``ADOPTION_NEEDED``) exactly which surfaces
   the lead must migrate. All assertions here pass against the baseline; the
   conformance audit test fails loudly only if a surface silently drifts.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the module under test from *this worktree's* src tree. In environments
# where `keel` is installed from a different checkout, `keel.__path__` may not
# contain the new module, so fall back to a direct file load.
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from keel.api_contracts import (  # noqa: F401
        CANONICAL_VERSION,
        CAPABILITY_ERROR_CODES,
        DEFAULT_ERROR_STATUS,
        ERROR_STATUS,
        classify_envelope,
        error_envelope,
        from_capability_error,
        http_status_for_code,
        is_canonical_envelope,
    )
except ImportError:  # pragma: no cover - environment-dependent fallback
    _spec = importlib.util.spec_from_file_location(
        "keel.api_contracts", _SRC / "keel" / "api_contracts.py")
    assert _spec is not None and _spec.loader is not None
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["keel.api_contracts"] = _module
    _spec.loader.exec_module(_module)
    CANONICAL_VERSION = _module.CANONICAL_VERSION
    CAPABILITY_ERROR_CODES = _module.CAPABILITY_ERROR_CODES
    DEFAULT_ERROR_STATUS = _module.DEFAULT_ERROR_STATUS
    ERROR_STATUS = _module.ERROR_STATUS
    classify_envelope = _module.classify_envelope
    error_envelope = _module.error_envelope
    from_capability_error = _module.from_capability_error
    http_status_for_code = _module.http_status_for_code
    is_canonical_envelope = _module.is_canonical_envelope

import keel  # noqa: E402
import keel.webapp as webapp  # noqa: E402
from keel.capabilities import CapabilityError  # noqa: E402
from keel.cli.main import main as cli_main  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Helper unit tests
# ---------------------------------------------------------------------------

def test_constants_are_stable_and_complete():
    assert CANONICAL_VERSION == "1.0"
    assert CAPABILITY_ERROR_CODES == {
        "not_found", "permission_denied", "policy_denied", "bad_params",
        "handler_error",
    }
    assert DEFAULT_ERROR_STATUS == 400
    for code in CAPABILITY_ERROR_CODES:
        assert code in ERROR_STATUS


def test_error_envelope_shape_and_default_status():
    env = error_envelope("not_found", "unknown capability: x")
    assert env == {
        "ok": False,
        "error": {
            "code": "not_found",
            "message": "unknown capability: x",
            "status": 404,
        },
        "api_contract_version": CANONICAL_VERSION,
    }
    assert is_canonical_envelope(env)


def test_error_envelope_coerces_code_and_message():
    env = error_envelope(404, 12345)
    assert env["error"]["code"] == "404"
    assert env["error"]["message"] == "12345"
    assert is_canonical_envelope(env)


def test_error_envelope_status_override_and_details_and_extra():
    env = error_envelope(
        "handler_error", "boom", status=500,
        details={"capability": "x.y", "attempt": 2}, surface="cli",
    )
    assert env["error"]["status"] == 500
    assert env["error"]["details"] == {"capability": "x.y", "attempt": 2}
    assert env["surface"] == "cli"
    assert is_canonical_envelope(env)


def test_error_envelope_unknown_code_uses_default_status():
    assert error_envelope("mystery")["error"]["status"] == 400
    assert error_envelope("mystery", status=503)["error"]["status"] == 503


def test_error_envelope_rejects_invalid_details_and_status():
    with pytest.raises(TypeError):
        error_envelope("bad_request", details=["not", "a", "dict"])
    with pytest.raises(ValueError):
        error_envelope("bad_request", status=99)
    with pytest.raises(ValueError):
        error_envelope("bad_request", status=700)


def test_http_status_for_code_covers_all_contract_codes():
    assert http_status_for_code("not_found") == 404
    assert http_status_for_code("permission_denied") == 403
    assert http_status_for_code("policy_denied") == 403
    assert http_status_for_code("bad_params") == 400
    assert http_status_for_code("handler_error") == 500
    assert http_status_for_code("refused") == 403
    assert http_status_for_code("confirmation_required") == 409
    assert http_status_for_code("unlisted", default=418) == 418


def test_is_canonical_envelope_rejects_malformed_shapes():
    canonical = error_envelope("bad_request", "bad")
    assert is_canonical_envelope(canonical)
    bad_shapes = [
        None, 42, "error", [],
        {},                                   # missing ok/error
        {"ok": True, "error": canonical["error"]},
        {"ok": False},                        # missing error
        {"ok": False, "error": "flat"},       # legacy flat
        {"ok": False, "error": {}},
        {"ok": False, "error": {"code": "", "message": "m", "status": 400}},
        {"ok": False, "error": {"code": "c", "status": 400}},
        {"ok": False, "error": {"code": "c", "message": "m"}},
        {"ok": False, "error": {"code": "c", "message": "m", "status": True}},
        {"ok": False, "error": {"code": "c", "message": "m", "status": 99}},
        {"ok": False, "error": {"code": "c", "message": "m", "status": 400,
                                "details": "not a dict"}},
    ]
    for shape in bad_shapes:
        assert not is_canonical_envelope(shape), shape


def test_is_canonical_envelope_tolerates_extra_top_level_keys():
    env = error_envelope("refused", "no", request_id="abc")
    assert env["request_id"] == "abc"
    assert env["api_contract_version"] == CANONICAL_VERSION
    assert is_canonical_envelope(env)
    # A hand-built envelope without the version marker is still canonical.
    minimal = {"ok": False, "error": {"code": "c", "message": "m", "status": 400}}
    assert is_canonical_envelope(minimal)


def test_from_capability_error_maps_every_code():
    for code in sorted(CAPABILITY_ERROR_CODES):
        exc = CapabilityError(f"boom [{code}]", code=code)
        env = from_capability_error(exc, surface="web")
        assert env["error"]["code"] == code
        assert env["error"]["message"] == f"boom [{code}]"
        assert env["error"]["status"] == http_status_for_code(code)
        assert env["surface"] == "web"
        assert is_canonical_envelope(env)
    # unknown exceptions degrade to the generic capability_error code
    env = from_capability_error(RuntimeError("plain"))
    assert env["error"]["code"] == "capability_error"


def test_classify_envelope():
    assert classify_envelope(error_envelope("bad_request")) == "canonical"
    assert classify_envelope({"ok": True, "result": 1}) == "success"
    assert classify_envelope({"error": "flat"}) == "legacy_flat"
    assert classify_envelope({"error": "flat", "code": "not_found"}) == "legacy_flat"
    assert classify_envelope({"error": {"code": "x"}}) == "legacy_other"
    assert classify_envelope(None) == "unknown"


# ---------------------------------------------------------------------------
# 2. Live probes of current surface formats
# ---------------------------------------------------------------------------

class _Bridge:
    def __init__(self, port: int):
        self.port = port

    def _request(self, path, *, method="GET", body=None, token="contract-token",
                 origin=None):
        headers = {"X-Keel-Token": token, "Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def get(self, path, **kw):
        return self._request(path, **kw)

    def post(self, path, body, **kw):
        return self._request(path, method="POST", body=body, **kw)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", "contract-token")
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        yield _Bridge(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _cli(argv, *, stream="stdout"):
    out = io.StringIO()
    ctx = contextlib.redirect_stdout if stream == "stdout" else contextlib.redirect_stderr
    with ctx(out):
        rc = cli_main(argv)
    return rc, out.getvalue()


def test_version_is_consistent_across_health_package_and_cli(bridge):
    """Exact version values: health body, keel.__version__, CLI --version."""
    status, body = bridge.get("/api/health")
    assert status == 200
    assert body["ok"] is True
    assert body["version"] == keel.__version__ == "0.1.1"
    rc, out = _cli(["--version"])
    assert rc == 0
    assert out.strip() == "keel 0.1.1"
    assert out.strip().split()[-1] == body["version"]


def test_current_auth_failure_is_legacy_flat(bridge):
    status, body = bridge.get("/api/health", token="wrong")
    assert status == 403
    assert body == {"error": "refused", "reason": "bad token or origin"}
    assert not is_canonical_envelope(body)
    assert classify_envelope(body) == "legacy_flat"


def test_current_capability_not_found_has_flat_error_plus_code(bridge):
    status, body = bridge.post("/api/capabilities/invoke", {"id": "no.such.cap"})
    assert status == 404
    assert body["code"] == "not_found"
    assert isinstance(body["error"], str) and "no.such.cap" in body["error"]
    assert not is_canonical_envelope(body)  # `error` is prose, not a nested object
    assert classify_envelope(body) == "legacy_flat"


def test_current_confirmation_required_carries_code_as_message(bridge):
    status, body = bridge.post(
        "/api/capabilities/invoke",
        {"id": "core.flags.set", "params": {"name": "x", "enabled": True}})
    assert status == 409
    assert body["error"] == "confirmation_required"
    assert "code" not in body  # machine code is smuggled into `error`
    assert not is_canonical_envelope(body)


def test_current_success_envelope_is_not_an_error_envelope(bridge):
    status, body = bridge.post(
        "/api/capabilities/invoke",
        {"id": "core.hardware.detect", "params": {}})
    assert status == 200
    assert body["ok"] is True and "result" in body
    assert classify_envelope(body) == "success"
    assert not is_canonical_envelope(body)


def test_current_generic_not_found_is_legacy_flat(bridge):
    status, body = bridge.get("/ui/does-not-exist.js")
    assert status == 404
    assert body == {"error": "not_found"}
    assert not is_canonical_envelope(body)


def test_current_cli_capability_error_is_plain_text():
    rc, err = _cli(["capability", "invoke", "no.such.cap"], stream="stderr")
    assert rc == 1
    assert err.strip() == "unknown capability: no.such.cap"
    # No JSON at all -> cannot be a canonical envelope.
    with pytest.raises(json.JSONDecodeError):
        json.loads(err)
    assert classify_envelope({"error": err.strip()}) == "legacy_flat"


# ---------------------------------------------------------------------------
# 3. Conformance audit: surfaces that still need adoption by the lead
# ---------------------------------------------------------------------------

#: (surface/path -> (current status, current shape)). Every entry here is a
#: concrete, test-observed migration the lead must perform to reach the
#: canonical envelope. Kept as data so the evidence doc and this test agree.
ADOPTION_NEEDED = {
    "GET /api/health | unauthenticated": (
        403, "flat {'error': 'refused', 'reason': ...}"),
    "POST /api/capabilities/invoke | not_found": (
        404, "flat {'error': <prose>, 'code': 'not_found'}"),
    "POST /api/capabilities/invoke | confirmation_required": (
        409, "flat {'error': 'confirmation_required', ...} without `code`"),
    "POST /api/capabilities/invoke | bad origin": (
        403, "flat {'error': 'refused', ...} (inner 'bad origin' branch unreachable)"),
    "GET /ui/<missing> and other 4xx routes": (
        404, "flat {'error': 'not_found'}"),
    "CLI capability invoke | all error paths": (
        "exit 1", "raw text '<code>: <message>' on stderr, no JSON"),
}


def test_conformance_audit_confirms_current_nonconformance(bridge):
    """Pin the audit table to observed responses so drift is caught."""
    observed = {}

    status, body = bridge.get("/api/health", token="wrong")
    observed["GET /api/health | unauthenticated"] = (
        status, classify_envelope(body))
    assert status == ADOPTION_NEEDED["GET /api/health | unauthenticated"][0]

    status, body = bridge.post("/api/capabilities/invoke", {"id": "no.such.cap"})
    observed["POST /api/capabilities/invoke | not_found"] = (
        status, classify_envelope(body))
    assert status == ADOPTION_NEEDED["POST /api/capabilities/invoke | not_found"][0]

    status, body = bridge.post(
        "/api/capabilities/invoke",
        {"id": "core.flags.set", "params": {"name": "x"}})
    observed["POST /api/capabilities/invoke | confirmation_required"] = (
        status, classify_envelope(body))
    assert status == ADOPTION_NEEDED[
        "POST /api/capabilities/invoke | confirmation_required"][0]

    status, body = bridge.post(
        "/api/capabilities/invoke", {"id": "core.hardware.detect"},
        origin="https://evil.test")
    observed["POST /api/capabilities/invoke | bad origin"] = (
        status, classify_envelope(body))
    assert status == ADOPTION_NEEDED["POST /api/capabilities/invoke | bad origin"][0]

    status, body = bridge.get("/ui/nope.js")
    observed["GET /ui/<missing> and other 4xx routes"] = (
        status, classify_envelope(body))
    assert status == ADOPTION_NEEDED["GET /ui/<missing> and other 4xx routes"][0]

    rc, err = _cli(["capability", "invoke", "no.such.cap"], stream="stderr")
    observed["CLI capability invoke | all error paths"] = (
        f"exit {rc}", "raw text" if not err.strip().startswith("{") else "json")
    assert observed["CLI capability invoke | all error paths"][0] == "exit 1"

    assert set(observed) == set(ADOPTION_NEEDED)
    # None of the current error responses is canonical yet.
    for key, (_status, shape) in observed.items():
        if key.startswith("CLI"):
            assert shape == "raw text"
        else:
            assert shape in ("legacy_flat", "legacy_other"), (key, shape)
