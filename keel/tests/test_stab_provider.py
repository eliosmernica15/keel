"""STAB-PROVIDER verification — provider, credential and MCP revocation paths.

Every test here is offline and deterministic. Credentials are synthetic
fixtures, state lives in disposable directories, and no network call or paid
usage is made. Live-provider validation is explicitly *pending*: nothing in
this module claims a successful real-provider call.

Covers the stabilization contract:
  1. provider validation: honest SKIP/FAIL, no fake success, no paid calls;
  2. provider contracts: auth, credentials, timeout, HTTP/rate limit,
     malformed responses, cancellation, partial streams, explicit fallback;
  3. credential lifecycle: encryption at rest, env apply, removal, no
     re-apply after restart, redaction in reports/errors/audit;
  4. MCP disable/removal, approval revocation, pairing/token revocation.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from keel import (  # noqa: E402
    mcp,
    pairing,
    provider_catalog,
    provider_contracts as pc,
    provider_validation as pv,
    secret_providers,
    secret_store,
    settings_store,
)
from keel.providers import registry as reg  # noqa: E402
from keel.providers.base import (  # noqa: E402
    CapabilityRecord,
    ProviderError,
    RETRY_AUTH,
    TurnCancelled,
    UsageRecord,
)

# Synthetic only. Never a real credential.
SYNTHETIC_KEY = "sk-stab-synthetic-Q7w8e9r0t1y2u3i4"
SYNTHETIC_BEARER = "Bearer abcdef1234567890STAB"

# conftest's autouse fixture replaces settings_store.load with an empty stub;
# capture the real functions at import time for the file-backed tests below.
_REAL_LOAD = settings_store.load
_REAL_SAVE = settings_store.save


@pytest.fixture(autouse=True)
def _private_process_environment(monkeypatch):
    """save/apply write os.environ directly; never leak keys into other tests."""
    monkeypatch.setattr(os, "environ", dict(os.environ))


@pytest.fixture
def probe_cap():
    return CapabilityRecord(
        name="stabprobe", base_url="https://stab.invalid/v1",
        env_var="KEEL_STAB_PROBE_KEY", default_model="stab-model",
        supports_tools=True, supports_streaming=True)


def _register(monkeypatch, cap):
    monkeypatch.setattr(reg, "_PROVIDERS", {cap.name: cap})


def _check(checks, name):
    return next(c for c in checks if c["name"] == name)


def _ok_adapter(monkeypatch=None):
    class Adapter:
        def __init__(self, cap, *, api_key=""):
            self.api_key = api_key

        def complete(self, request):
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0, "text": "keel-ok"}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "usage", "usage": UsageRecord(
                input_tokens=3, output_tokens=2)}
            yield {"event": "message_stop", "stop_reason": "end_turn"}

    return Adapter


# ---------------------------------------------------------------------------
# 1. Provider validation workflow — honesty about credentials and errors
# ---------------------------------------------------------------------------


def test_missing_optional_credential_is_truthful_skip(probe_cap, monkeypatch):
    monkeypatch.delenv(probe_cap.env_var, raising=False)
    _register(monkeypatch, probe_cap)
    doc = pv.run_validation(live=True, providers=[probe_cap])
    checks = doc["providers"]["stabprobe"]
    assert _check(checks, "auth_present")["status"] == "SKIP"
    assert _check(checks, "credential_format")["status"] == "SKIP"
    assert _check(checks, "live_provider")["status"] == "SKIP"
    assert doc["configured"] == []
    assert not any(c["status"] == "PASS" and c["name"] in
                   ("auth_present", "streaming_response") for c in checks)


def test_blank_credential_is_not_a_fake_success(probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, "   \t ")
    _register(monkeypatch, probe_cap)
    assert pv.configured_providers() == []
    doc = pv.run_validation(live=True, providers=[probe_cap])
    checks = doc["providers"]["stabprobe"]
    assert _check(checks, "auth_present")["status"] == "SKIP"
    assert "blank" in _check(checks, "auth_present")["detail"]
    assert _check(checks, "live_provider")["status"] == "SKIP"


def test_malformed_configured_credential_fails_without_a_live_call(
        probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, "sk-bad\ncredential")
    _register(monkeypatch, probe_cap)
    calls = []

    def build(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("malformed credential must never be spent")

    monkeypatch.setattr(reg, "build_adapter", build)
    doc = pv.run_validation(live=True, providers=[probe_cap])
    checks = doc["providers"]["stabprobe"]
    assert _check(checks, "credential_format")["status"] == "FAIL"
    assert _check(checks, "live_provider")["status"] == "FAIL"
    assert calls == []
    assert doc["configured"] == ["stabprobe"]


def test_real_provider_error_is_a_failure_and_is_redacted(probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, SYNTHETIC_KEY)

    class Failing:
        def __init__(self, cap, *, api_key=""):
            pass

        def complete(self, request):
            raise ProviderError("denied for " + SYNTHETIC_KEY, RETRY_AUTH, 401)

    doc = pv.run_validation(live=True, providers=[probe_cap],
                            adapter_factory=Failing)
    checks = doc["providers"]["stabprobe"]
    streaming = _check(checks, "streaming_response")
    assert streaming["status"] == "FAIL"
    assert RETRY_AUTH in streaming["detail"]
    assert SYNTHETIC_KEY not in json.dumps(doc)


def test_cancelled_live_check_is_never_reported_as_streaming_success(
        probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, SYNTHETIC_KEY)

    class Cancelling:
        def __init__(self, cap, *, api_key=""):
            pass

        def complete(self, request):
            raise TurnCancelled()

    doc = pv.run_validation(live=True, providers=[probe_cap],
                            adapter_factory=Cancelling)
    checks = doc["providers"]["stabprobe"]
    assert _check(checks, "streaming_response")["status"] == "SKIP"
    assert not any(c["status"] == "PASS" and c["name"] == "streaming_response"
                   for c in checks)


def test_validation_enforces_its_timeout_budget(probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, SYNTHETIC_KEY)

    class Slow:
        def __init__(self, cap, *, api_key=""):
            pass

        def complete(self, request):
            time.sleep(0.4)
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0, "text": "too late"}
            yield {"event": "block_stop", "index": 0}

    doc = pv.run_validation(live=True, providers=[probe_cap],
                            adapter_factory=Slow, timeout_s=0.02)
    checks = doc["providers"]["stabprobe"]
    timeout = _check(checks, "live_timeout")
    assert timeout["status"] == "FAIL"
    assert "0.02" in timeout["detail"]
    assert not any(c["name"] == "streaming_response" and c["status"] == "PASS"
                   for c in checks)


def test_no_live_call_without_the_live_flag(probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, SYNTHETIC_KEY)
    calls = []

    def factory(cap):
        calls.append(cap.name)
        return _ok_adapter()(cap)

    doc = pv.run_validation(live=False, providers=[probe_cap],
                            adapter_factory=factory)
    assert calls == []
    assert _check(doc["providers"]["stabprobe"], "live_provider")["status"] == "SKIP"


def test_mock_adapter_matrix_passes_honestly(probe_cap, monkeypatch):
    monkeypatch.setenv(probe_cap.env_var, SYNTHETIC_KEY)
    doc = pv.run_validation(live=True, providers=[probe_cap],
                            adapter_factory=_ok_adapter())
    checks = doc["providers"]["stabprobe"]
    assert _check(checks, "streaming_response")["status"] == "PASS"
    assert _check(checks, "usage_tracking")["status"] == "PASS"
    assert SYNTHETIC_KEY not in json.dumps(doc)


# ---------------------------------------------------------------------------
# 2. Provider contracts — failure taxonomy, normalization, streams, fallback
# ---------------------------------------------------------------------------


def _pc_cfg(**overrides):
    base = dict(primary="alpha", fallbacks=(), max_attempts=3,
                base_backoff_seconds=0, backoff_factor=2.0,
                max_backoff_seconds=1.0, timeout_seconds=60.0,
                protocols={"alpha": "openai-chat-completions",
                           "backup": "openai-chat-completions"})
    base.update(overrides)
    return pc.ExecutionConfig(**base)


class _Transport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, wire):
        self.calls.append(wire)
        if not self.outcomes:
            raise AssertionError("unexpected transport call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(wire)
        return outcome


def _ok(text="hello"):
    return {"choices": [{"message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2}}


def test_auth_and_invalid_credentials_never_retry_or_fall_back():
    for category in (pc.CATEGORY_AUTH, pc.CATEGORY_CREDENTIAL):
        transport = _Transport(
            pc.ProviderTransportError("denied " + SYNTHETIC_KEY,
                                      category=category))
        result = pc.execute_request(
            _pc_cfg(fallbacks=("backup",)), {"model": "m", "messages": []},
            transport=transport, secrets=[SYNTHETIC_KEY])
        assert result.status == "failed"
        assert result.error.category == category
        assert result.error.retryable is False
        assert result.fallbacks_used == ()
        assert len(transport.calls) == 1
        assert SYNTHETIC_KEY not in json.dumps(result.to_dict())


def test_timeout_and_rate_limit_are_retryable_with_bounded_backoff():
    transport = _Transport(
        TimeoutError("slow"),
        pc.TransportResponse(429, {"error": {"type": "rate_limit_error",
                                            "retry_after": 120}}),
        _ok())
    sleeper = []
    result = pc.execute_request(
        _pc_cfg(), {"model": "m", "messages": []},
        transport=transport, sleep=sleeper.append)
    assert result.status == "ok"
    assert [a.category for a in result.attempts][:2] == [
        pc.CATEGORY_TIMEOUT, pc.CATEGORY_RATE_LIMIT]
    assert sleeper == [0.0, 1.0]  # max_backoff_seconds=1.0 caps 120s


def test_http_normalization_and_malformed_response_never_echo_secrets():
    failure = pc.classify_status(401, payload={
        "error": {"message": "leaked " + SYNTHETIC_KEY}})
    assert failure.category == pc.CATEGORY_AUTH
    assert SYNTHETIC_KEY not in failure.message
    with pytest.raises(pc.ProviderTransportError) as exc:
        pc.normalize_response({"unexpected": SYNTHETIC_KEY})
    assert exc.value.category == pc.CATEGORY_MALFORMED
    assert SYNTHETIC_KEY not in str(exc.value)


def test_stream_nested_error_frame_is_classified_and_redacted():
    event = pc.sanitize_event(
        {"event": "error",
         "error": {"type": "overloaded_error",
                   "message": "busy; key " + SYNTHETIC_KEY}},
        [SYNTHETIC_KEY])
    assert event["kind"] == "error"
    assert event["category"] == pc.CATEGORY_OVERLOADED
    assert event["retryable"] is True
    assert "busy" in event["message"]
    assert SYNTHETIC_KEY not in json.dumps(event)


def test_stream_cancelled_error_event_is_a_normal_stop_after_content():
    def chunks(_wire):
        yield {"event": "text_delta", "text": "partial answer"}
        yield {"event": "error", "category": pc.CATEGORY_CANCELLED,
               "message": "user stopped"}

    result = pc.execute_stream(
        _pc_cfg(fallbacks=("backup",)), {"model": "m", "messages": []},
        transport=_Transport(chunks))
    assert result.status == "cancelled"
    assert result.error is None
    assert result.response.text == "partial answer"
    assert result.fallbacks_used == ()


def test_partial_failure_keeps_text_without_retry_or_fallback():
    def chunks(_wire):
        yield {"event": "text_delta", "text": "partial"}
        raise ConnectionError("wire dropped " + SYNTHETIC_KEY)

    transport = _Transport(chunks)
    result = pc.execute_stream(
        _pc_cfg(fallbacks=("backup",)), {"model": "m", "messages": []},
        transport=transport, secrets=[SYNTHETIC_KEY])
    assert result.status == "partial_failed"
    assert result.response.text == "partial"
    assert result.fallbacks_used == ()
    assert len(transport.calls) == 1
    assert SYNTHETIC_KEY not in json.dumps(result.to_dict())


def test_fallback_happens_only_when_explicitly_configured():
    without = pc.execute_request(
        _pc_cfg(), {"model": "m", "messages": []},
        transport=_Transport(pc.ProviderTransportError(
            "down", category=pc.CATEGORY_UNAVAILABLE)))
    assert without.fallbacks_used == ()
    with_fb = pc.execute_request(
        _pc_cfg(fallbacks=("backup",), max_attempts=1),
        {"model": "m", "messages": []},
        transport=_Transport(pc.ProviderTransportError(
            "down", category=pc.CATEGORY_UNAVAILABLE), _ok("from backup")))
    assert with_fb.status == "ok"
    assert with_fb.provider == "backup"
    assert with_fb.fallbacks_used == ("backup",)


def test_catalog_validates_and_returns_isolated_copies():
    ids = provider_catalog.provider_ids()
    assert ids
    entry = provider_catalog.get_provider(ids[0])
    entry["models"].append("INJECTED")
    assert "INJECTED" not in provider_catalog.model_ids(ids[0])
    info = provider_catalog.catalog_info()
    assert info.provider_count == len(ids)


# ---------------------------------------------------------------------------
# 3. Credential lifecycle — encryption, env, removal, restart, redaction
# ---------------------------------------------------------------------------


@pytest.fixture
def real_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "load", _REAL_LOAD)
    monkeypatch.setattr(settings_store, "save", _REAL_SAVE)
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", tmp_path / "settings.json.bak")
    monkeypatch.setattr(settings_store, "_APPLIED_FROM_STORE", set())
    monkeypatch.setattr(secret_store, "_master_key", lambda state_dir: b"s" * 32)
    for var in settings_store.provider_env_var().values():
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_credentials_are_encrypted_applied_and_removed(real_store):
    env_var = settings_store.provider_env_var()["google"]
    settings_store.save_provider_key("google", SYNTHETIC_KEY)
    assert os.environ.get(env_var) == SYNTHETIC_KEY
    raw = (real_store / "settings.json").read_text(encoding="utf-8")
    assert SYNTHETIC_KEY not in raw
    assert json.loads(raw)["providerKeys"]["google"]["enc"] == secret_store.ENC_MARKER
    assert settings_store.stored_key("google") == SYNTHETIC_KEY

    assert settings_store.remove_provider_key("google") is True
    assert env_var not in os.environ
    assert settings_store.stored_key("google") is None
    assert settings_store.apply_stored_keys() == []
    for path in real_store.rglob("*"):
        if path.is_file():
            assert SYNTHETIC_KEY not in path.read_text(
                encoding="utf-8", errors="replace")


def test_decryption_failure_never_leaks_the_stored_value(tmp_path):
    payload = secret_store.encrypt_secret(SYNTHETIC_KEY, state_dir=tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(secret_store.SecretStoreError) as exc:
        secret_store.decrypt_secret(payload, state_dir=other)
    assert SYNTHETIC_KEY not in str(exc.value)
    assert exc.value.__cause__ is None


def test_secret_provider_chain_reports_presence_without_values(
        tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"export STAB_TEST_KEY={SYNTHETIC_KEY}\n"
        f"QUOTED='{SYNTHETIC_BEARER}'\n", encoding="utf-8")
    chain = secret_providers.ProviderChain([
        secret_providers.EnvFileProvider(env_file)])
    result = chain.resolve("STAB_TEST_KEY")
    assert result["present"] is True
    assert result["value"] is None
    assert SYNTHETIC_KEY not in json.dumps(chain.describe())
    assert chain.resolve("STAB_TEST_KEY", reveal=True)["value"] == SYNTHETIC_KEY
    assert chain.resolve("MISSING")["present"] is False

    config = {"providers": [{"kind": "env-file", "path": str(env_file)}]}
    path = secret_providers.ProviderConfig(str(tmp_path)).save(config)
    assert SYNTHETIC_KEY not in path.read_text(encoding="utf-8")


def test_no_reapply_after_restart_in_a_clean_home(tmp_path):
    """Two fresh interpreters with a clean HOME prove durable removal."""
    clean_home = tmp_path / "home"
    state = tmp_path / "state"
    clean_home.mkdir()
    state.mkdir()
    base_env = dict(os.environ)
    for key in list(base_env):
        if key.startswith("KEEL_") or key in ("HOME", "USERPROFILE"):
            base_env.pop(key)
    base_env.update({"HOME": str(clean_home), "USERPROFILE": str(clean_home),
                     "KEEL_STATE_DIR": str(state),
                     "KEEL_MASTER_PASSPHRASE": "stab-restart-passphrase",
                     "PYTHONPATH": str(_SRC)})

    writer = (
        "from keel import settings_store as s;"
        f"s.save_provider_key('google', {SYNTHETIC_KEY!r});"
        "assert s.remove_provider_key('google') is True;"
        "assert s.stored_key('google') is None"
    )
    reader = (
        "import os;"
        "from keel import settings_store as s;"
        "from keel.providers import registry as r;"
        "assert s.stored_key('google') is None;"
        "assert not os.environ.get(s.provider_env_var()['google'], '');"
        "assert 'google' not in [p['name'] for p in r.list_providers() "
        "if p['configured']]"
    )
    for code in (writer, reader):
        proc = subprocess.run([sys.executable, "-c", code], env=base_env,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, (code, proc.stdout, proc.stderr)
    for path in state.rglob("*"):
        if path.is_file():
            assert SYNTHETIC_KEY not in path.read_text(
                encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 4. MCP disable/removal, approval revocation, pairing revocation
# ---------------------------------------------------------------------------


def test_mcp_removed_server_is_not_discoverable_or_callable(tmp_path, monkeypatch):
    from keel.fleet import connector_ops
    monkeypatch.setattr(settings_store, "load", _REAL_LOAD)
    monkeypatch.setattr(connector_ops, "state_root", lambda: tmp_path)
    connector_ops.add_connector("stab-mcp", sys.executable, ["-c", "pass"], {})
    before = mcp.parse_servers(connector_ops.load_settings().get("mcpServers", {}))
    assert [s.name for s in before] == ["stab-mcp"]

    connector_ops.remove_connector("stab-mcp")
    after = mcp.parse_servers(connector_ops.load_settings().get("mcpServers", {}))
    assert after == []
    manager = mcp.McpManager(after)
    assert manager.tool_schemas() == []
    ok, text = manager.call("mcp__stab-mcp__anything", {})
    assert ok is False and "not connected" in text


def test_project_approval_revocation_denies_activation_and_survives_restart(
        tmp_path):
    approvals_file = tmp_path / "mcp-approvals.json"
    original = mcp.approvals_path
    mcp.approvals_path = lambda: approvals_file
    try:
        config = mcp.McpServerConfig(name="stab-project", command=sys.executable,
                                     args=("-c", "pass"), scope="project")
        assert mcp.is_approved(config) is False
        mcp.approve(config)
        assert mcp.is_approved(config) is True
        assert [s for s in (config,) if s.scope == "user" or mcp.is_approved(s)]
        assert mcp.revoke("stab-project") is True
        # Fresh read from disk: no in-memory cache to resurrect the approval.
        assert mcp.approvals() == {}
        assert mcp.is_approved(config) is False
        assert [s for s in (config,) if s.scope == "user" or mcp.is_approved(s)] == []
    finally:
        mcp.approvals_path = original


def test_pairing_revocation_is_durable(tmp_path):
    store = pairing.PairingStore(str(tmp_path))
    client_id = store.pair("stab-companion", scope="lan")["id"]
    assert pairing.PairingStore(str(tmp_path)).is_paired(client_id) is True
    assert store.revoke(client_id) is True
    assert pairing.PairingStore(str(tmp_path)).is_paired(client_id) is False
    doc = json.loads((tmp_path / "pairings.json").read_text(encoding="utf-8"))
    assert doc["clients"][client_id]["revoked"] is True


def test_http_mcp_error_body_is_redacted(monkeypatch):
    config = mcp.McpServerConfig(name="http", transport="http",
                                 url="https://mcp.invalid/rpc")

    class FakeOpener:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(
                config.url, 401, "Unauthorized", {}, io.BytesIO(
                    b"denied " + SYNTHETIC_BEARER.encode("ascii")))

    import urllib.request
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: FakeOpener())
    server = mcp.HttpMcpServer(config)
    with pytest.raises(mcp.McpError) as exc:
        server.start()
    assert "http 401" in str(exc.value)
    assert "abcdef1234567890STAB" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
