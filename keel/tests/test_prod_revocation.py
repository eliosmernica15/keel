"""PR-14 (credential revocation / disable compromised integration) real local tests.

Every assertion below runs unmodified backend code against a disposable state
directory: real AES-GCM encryption, real settings.json / approvals / pairing /
workflow JSONL state, the real MCP client manager, and the real hash-chained
audit log.  No production module is edited and no network call is made.

The tests deliberately separate two things:

* durable *local* revocation (env + on-disk state + in-process capability gates),
  which is what this module proves; and
* provider-side / live-service revocation, which cannot be proven here because
  it needs real credentials.  ``test_y3_descriptor_is_bookkeeping_only`` also
  records, negatively, that the Y3.9 sign-out descriptor has no durable effect.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from keel import backend_observability as obs
from keel import backend_workflows as bw
from keel import config_contracts as cc
from keel import mcp
from keel import pairing
from keel import secret_store
from keel import settings_store
from keel.fleet import connector_ops
from keel.mcp import McpManager, McpServerConfig, parse_servers

# Captured at import time, before the repository-wide conftest autouse fixture
# swaps settings_store.load for an empty stub.  Restoring the real loader is
# required for these tests to exercise real file-backed state.
_REAL_SETTINGS_LOAD = settings_store.load

SECRET_KEY = "sk-or-v1-" + "A" * 32
MULTI_WORD_SECRET = "trident lunar velvet compass"
BEARER_SECRET = "Bearer abcdef1234567890XYZ"


def _isolate_state(tmp_path: Path, monkeypatch) -> None:
    """Point every module-level state path at this test's temp directory."""
    monkeypatch.setattr(settings_store, "load", _REAL_SETTINGS_LOAD)
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", tmp_path / "settings.json.bak")
    monkeypatch.setattr(settings_store, "_APPLIED_FROM_STORE", set())
    monkeypatch.setattr(connector_ops, "state_root", lambda: tmp_path)
    # Deterministic master key: no OS keyring is installed on this host, so
    # secret_store falls back to KEEL_MASTER_PASSPHRASE (real SHA-256 -> AES-GCM).
    monkeypatch.setenv("KEEL_MASTER_PASSPHRASE", "pr14-unit-master-passphrase")
    monkeypatch.delenv(settings_store.provider_env_var()["openrouter"], raising=False)


# ---------------------------------------------------------------------------
# 1. Provider key: real encryption at rest, real env apply, real removal
# ---------------------------------------------------------------------------


def test_provider_key_revocation_clears_env_and_live_store(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    env_var = settings_store.provider_env_var()["openrouter"]

    settings_store.save_provider_key("openrouter", SECRET_KEY)

    # save_provider_key() calls apply_stored_keys(): the real process env now
    # carries the key, and the file carries only an AES-GCM ciphertext + hint.
    assert os.environ.get(env_var) == SECRET_KEY
    live = tmp_path / "settings.json"
    raw_saved = live.read_text(encoding="utf-8")
    assert SECRET_KEY not in raw_saved
    assert secret_store.ENC_MARKER in raw_saved
    assert settings_store.stored_key("openrouter") == SECRET_KEY
    encrypted_blob = settings_store.get_provider_keys()["openrouter"]["key"]

    assert settings_store.remove_provider_key("openrouter") is True

    assert env_var not in os.environ
    assert settings_store.stored_key("openrouter") is None
    raw_removed = live.read_text(encoding="utf-8")
    assert SECRET_KEY not in raw_removed
    assert encrypted_blob not in raw_removed
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET_KEY not in path.read_text(encoding="utf-8", errors="replace")
    # Honest limit: save() keeps one rolling settings.json.bak, which still
    # holds the old *encrypted* blob; there is no secure-delete.  What is
    # proven here is that plaintext is gone and the live entry is gone.
    # Re-applying a removed key cannot resurrect it.
    assert settings_store.apply_stored_keys() == []
    assert env_var not in os.environ


# ---------------------------------------------------------------------------
# 2. MCP server descriptor: durable removal -> excluded from discovery/call
# ---------------------------------------------------------------------------


def test_mcp_connector_disable_excludes_discovery_and_invocation(tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)

    registered = connector_ops.add_connector(
        "compromised", sys.executable, ["-c", "pass"], {"LEAK_ME": "1"})
    assert "compromised" in [c["name"] for c in registered["connectors"]]

    before = parse_servers(connector_ops.load_settings().get("mcpServers", {}))
    assert [s.name for s in before] == ["compromised"]
    assert McpManager(before).call("mcp__compromised__echo", {})[1].startswith(
        "mcp server not connected")  # no tool schemas without a started client

    # "Disable" here is a durable deletion from the settings source of truth,
    # not a UI flag.
    disabled = connector_ops.remove_connector("compromised")
    assert "compromised" not in [c["name"] for c in disabled["connectors"]]
    assert "compromised" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert parse_servers(connector_ops.load_settings().get("mcpServers", {})) == []

    manager = McpManager(parse_servers(
        connector_ops.load_settings().get("mcpServers", {})))
    assert manager.tool_schemas() == []
    ok, text = manager.call("mcp__compromised__echo", {})
    assert ok is False
    assert "not connected" in text


def test_project_mcp_approval_revoke_denies_activation(tmp_path, monkeypatch):
    approvals_file = tmp_path / "mcp-approvals.json"
    monkeypatch.setattr(mcp, "approvals_path", lambda: approvals_file)
    config = McpServerConfig(name="compromised-project", command=sys.executable,
                             args=("-c", "pass"), scope="project")

    assert mcp.is_approved(config) is False
    mcp.approve(config)
    assert mcp.is_approved(config) is True
    # Same allow-list gate used by fleet/turn_core._mcp_manager().
    assert [s for s in (config,) if s.scope == "user" or mcp.is_approved(s)] == [config]

    assert mcp.revoke("compromised-project") is True
    assert mcp.is_approved(config) is False
    assert approvals_file.is_file()
    assert "compromised-project" not in approvals_file.read_text(encoding="utf-8")
    assert [s for s in (config,) if s.scope == "user" or mcp.is_approved(s)] == []


# ---------------------------------------------------------------------------
# 3. Pairing / capability token: revoke then deny subsequent use
# ---------------------------------------------------------------------------


def test_pairing_revoke_denies_subsequent_use(tmp_path):
    store = pairing.PairingStore(str(tmp_path))
    client_id = store.pair("companion", scope="lan")["id"]

    assert store.is_paired(client_id) is True
    assert pairing.PairingStore(str(tmp_path)).is_paired(client_id) is True  # durable

    assert store.revoke(client_id) is True
    assert store.is_paired(client_id) is False
    assert pairing.PairingStore(str(tmp_path)).is_paired(client_id) is False  # durable

    doc = json.loads((tmp_path / "pairings.json").read_text(encoding="utf-8"))
    assert doc["clients"][client_id]["revoked"] is True
    assert doc["clients"][client_id]["revoked_at"]


def test_approval_token_revoke_denies_subsequent_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    base = {"state_root": str(tmp_path), "operation": "fs_read",
            "scope": "workflow:read", "subject": "pr14",
            "profile": "no_network", "ttl_seconds": 600}

    def request(key: str) -> dict:
        result = bw.run_approval_workflow({**base, "action": "request",
                                           "idempotency_key": key})
        assert result["ok"] is True, result
        return result["result"]

    def use(issued: dict, key: str) -> dict:
        return bw.run_approval_workflow({
            **base, "action": "resolve", "request_id": issued["request_id"],
            "token": issued["token"], "idempotency_key": key})

    def revoke(issued: dict, key: str) -> dict:
        return bw.run_approval_workflow({
            **base, "action": "revoke", "request_id": issued["request_id"],
            "token": issued["token"], "idempotency_key": key})

    # A token that has not been spent is denied with the explicit "revoked"
    # code after revocation.
    unspent = request("pr14-request-unspent")
    revoked = revoke(unspent, "pr14-revoke-unspent")
    assert revoked["ok"] is True and revoked["result"]["revoked"] is True
    denied = use(unspent, "pr14-use-unspent")
    assert denied["ok"] is False and denied["code"] == "revoked"

    # A token that was already spent is denied by the replay guard even after
    # revocation; both paths deny subsequent use, with durable audit events.
    spent = request("pr14-request-spent")
    before = use(spent, "pr14-use-spent")
    assert before["ok"] is True and before["result"]["grant"]["granted"] is True
    assert revoke(spent, "pr14-revoke-spent")["ok"] is True
    after = use(spent, "pr14-use-spent-again")
    assert after["ok"] is False and after["code"] == "replay_denied"

    events_path = tmp_path / "backend-workflows" / "approval-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    assert [event["action"] for event in events] == [
        "request", "revoke", "request", "consume", "revoke"]


# ---------------------------------------------------------------------------
# 4. Audit / observability: redacted and retained
# ---------------------------------------------------------------------------


def test_revocation_audit_is_redacted_and_retained(tmp_path):
    first = obs.record_audit_event(
        "credential.revoked", actor="admin", outcome="success",
        state_root=tmp_path, module="settings_store",
        resource="providerKeys/openrouter",
        detail={"provider": "openrouter", "api_key": SECRET_KEY,
                "secret": MULTI_WORD_SECRET, "note": BEARER_SECRET + " revoked"})
    obs.record_audit_event(
        "integration.disabled", actor="admin", outcome="success",
        state_root=tmp_path, module="connector_ops", resource="mcpServers/compromised")

    dumped = json.dumps(first)
    assert SECRET_KEY not in dumped
    assert MULTI_WORD_SECRET not in dumped
    assert "abcdef1234567890XYZ" not in dumped
    assert first["data"]["detail"]["api_key"] == "[REDACTED]"
    assert first["data"]["detail"]["secret"] == "[REDACTED]"

    raw_log = (tmp_path / obs.LOG_FILENAME).read_text(encoding="utf-8")
    assert SECRET_KEY not in raw_log
    assert MULTI_WORD_SECRET not in raw_log
    assert "abcdef1234567890XYZ" not in raw_log

    chain = obs.verify_chain(tmp_path)
    assert chain.ok is True
    events = obs.read_events(tmp_path, kind=obs.AUDIT_KIND)
    assert chain.event_count == len(events) == 2
    assert [e["data"]["action"] for e in events] == [
        "credential.revoked", "integration.disabled"]


# ---------------------------------------------------------------------------
# 5. Negative evidence: the Y3.9 descriptor is bookkeeping, not revocation
# ---------------------------------------------------------------------------


def test_y3_descriptor_is_bookkeeping_only_not_credential_deletion(
        tmp_path, monkeypatch):
    _isolate_state(tmp_path, monkeypatch)
    env_var = settings_store.provider_env_var()["openrouter"]
    settings_store.save_provider_key("openrouter", SECRET_KEY)
    assert os.environ.get(env_var) == SECRET_KEY

    descriptor = cc.build_revocation(cc.RevocationRequest(
        scope=cc.RevocationScope.ALL_CLIENTS, subject_id="compromised-client",
        reason="incident"))
    assert descriptor.delete_stored_credentials is True
    assert descriptor.sign_out_all_clients is True

    ledger = cc.RevocationLedger()
    effect = ledger.apply(descriptor)
    assert effect.credentials_deleted is True
    assert effect.clients_signed_out is True
    assert ledger.is_revoked("compromised-client") is True
    assert ledger.has_deleted_credentials("compromised-client") is True

    # GAP (documented in BACKEND-INCIDENT-RESPONSE.md §1): the descriptor and
    # ledger only record intent.  No credential is actually deleted and no
    # client session is actually invalidated by this path.
    assert settings_store.stored_key("openrouter") == SECRET_KEY
    assert os.environ.get(env_var) == SECRET_KEY
