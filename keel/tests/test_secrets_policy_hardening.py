"""Regression tests for the v6 secrets / policy hardening pass.

Every credential-looking value in this module is a synthetic, non-functional
placeholder. No real key, token or password appears in code or test output.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from keel import (exec_policy, policy_enforcement, redaction, secret_providers,
                  secret_store, settings_store)

# Synthetic values only (AWS-style / Slack-style shapes, no live material).
FAKE_AWS_TEMP = "ASIA" + "EXAMPLEKEY123456"
FAKE_AWS_PERM = "AKIA" + "EXAMPLEKEY123456"
FAKE_SLACK_ENTERPRISE = "xoxe-1-2-abcdefghijklmnop"
FAKE_IMPORT_KEY = "imported-fake-key-9876"

POLICY_DOC = {
    "prefix_rules": [
        {"pattern": ["git", "reset", "--hard"], "decision": "forbidden",
         "justification": "destructive"},
    ],
    "network_rules": [
        {"host": "allowed.example.com", "protocol": "https",
         "decision": "allow"},
    ],
}

_REAL_LOAD = settings_store.load
_REAL_SAVE = settings_store.save


def _capture_open_modes(monkeypatch):
    """Record (path, flags, mode) for every os.open while the patch is live."""
    calls = []
    real_open = os.open

    def spy(path, flags, mode=0o777, *args, **kwargs):
        calls.append((os.fspath(path), flags, mode))
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    return calls


@pytest.fixture
def policy_root(tmp_path):
    exec_policy.ExecPolicyStore(tmp_path).save("default", POLICY_DOC)
    return tmp_path


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    # conftest's autouse fixture stubs settings_store.load for MCP isolation;
    # restore the real helpers captured at import time for this suite.
    monkeypatch.setattr(settings_store, "load", _REAL_LOAD)
    monkeypatch.setattr(settings_store, "save", _REAL_SAVE)
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH",
                        tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH",
                        tmp_path / "settings.json.bak")
    monkeypatch.setattr(secret_store, "_master_key", lambda state_dir: b"k" * 32)
    for var in settings_store.provider_env_var().values():
        monkeypatch.setenv(var, "")
    return tmp_path


class _NoKeyring:
    """Deterministic 'no OS keyring' shim for master-key fallback tests."""

    @staticmethod
    def get_password(*args, **kwargs):
        return None

    @staticmethod
    def set_password(*args, **kwargs):
        raise RuntimeError("keyring unavailable")


# --- W1: redaction must cover common, real credential formats ----------------

def test_redaction_masks_aws_temporary_and_long_term_keys():
    text = f"temp={FAKE_AWS_TEMP} long={FAKE_AWS_PERM}"
    clean, counts = redaction.redact_text(text)
    assert FAKE_AWS_TEMP not in clean
    assert FAKE_AWS_PERM not in clean
    assert counts["aws_key"] >= 2
    assert "aws_key" in redaction.check_output_dlp(text)


def test_redaction_masks_slack_enterprise_tokens():
    text = f"token={FAKE_SLACK_ENTERPRISE} done"
    clean, counts = redaction.redact_text(text)
    assert FAKE_SLACK_ENTERPRISE not in clean
    assert counts["slack_token"] == 1


# --- W2: settings import must not persist plaintext secrets -----------------

def test_merge_import_encrypts_imported_provider_keys(isolated_settings):
    result = settings_store.merge_import(
        {"providerKeys": {"google": {"key": FAKE_IMPORT_KEY}}},
        include_keys=True)
    raw = settings_store.SETTINGS_PATH.read_text(encoding="utf-8")
    assert FAKE_IMPORT_KEY not in raw
    entry = json.loads(raw)["providerKeys"]["google"]
    assert entry.get("enc") == secret_store.ENC_MARKER
    assert settings_store.stored_key("google") == FAKE_IMPORT_KEY
    assert FAKE_IMPORT_KEY not in json.dumps(result)


# --- W3/W4: secret-bearing files must be created owner-only -----------------

def test_master_key_file_created_atomically_owner_only(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", _NoKeyring())
    monkeypatch.delenv("KEEL_MASTER_PASSPHRASE", raising=False)
    calls = _capture_open_modes(monkeypatch)

    key = secret_store._master_key(tmp_path / "state")

    target = tmp_path / "state" / "master.key"
    assert target.is_file()
    assert len(key) == 32
    relevant = [c for c in calls if Path(c[0]).name == "master.key"]
    assert relevant, "key file must be created with an explicit 0600 mode"
    assert any(mode == 0o600 and flags & os.O_CREAT
               for _path, flags, mode in relevant)


def test_settings_temp_file_created_atomically_owner_only(
        isolated_settings, monkeypatch):
    calls = _capture_open_modes(monkeypatch)

    settings_store.save({"ui": {"theme": "dark"}})

    tmp_name = settings_store.SETTINGS_PATH.with_suffix(".json.tmp").name
    relevant = [c for c in calls if Path(c[0]).name == tmp_name]
    assert relevant, "settings temp file must be created with an explicit mode"
    assert any(mode == 0o600 for _path, _flags, mode in relevant)


def test_settings_backup_is_hardened(isolated_settings, monkeypatch):
    settings_store.SETTINGS_PATH.write_text("{}", encoding="utf-8")
    chmods = []
    real_chmod = os.chmod

    def spy(path, mode, *args, **kwargs):
        chmods.append((os.fspath(path), mode))
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "chmod", spy)

    settings_store.save({"ui": {}})

    assert any(Path(path).name == settings_store.BACKUP_PATH.name
               and mode == 0o600 for path, mode in chmods)


# --- W5: absolute executable paths must not evade a binding deny ------------

@pytest.mark.parametrize("command", [
    "/usr/bin/git reset --hard",
    "C:\\bin\\git.exe reset --hard",
])
def test_absolute_executable_path_cannot_evade_forbidden_rule(
        policy_root, command):
    decision = policy_enforcement.enforce(
        "run_shell", {"command": command}, state_root=policy_root,
        interactive=False)
    assert decision is not None, f"policy silently skipped for {command!r}"
    assert decision.decision == "deny"


def test_windows_host_executable_tokenization_keeps_command_arguments():
    policy = exec_policy.from_dict(POLICY_DOC)
    evaluation = policy.check("C:\\bin\\git.exe reset --hard",
                              resolve_host_executables=True)
    assert evaluation.is_match
    assert evaluation.decision == exec_policy.FORBIDDEN
    assert evaluation.matched_rules[0].matched_prefix == [
        "git", "reset", "--hard"]


# --- W6: a saved policy's "prompt" default must not fail open ---------------

def test_unlisted_network_host_denied_without_interactive_approval(policy_root):
    decision = policy_enforcement.enforce(
        "web_fetch", {"url": "https://unlisted.example.com/x"},
        state_root=policy_root, interactive=False)
    assert decision is not None
    assert decision.decision == "deny"


def test_unlisted_network_host_asks_with_interactive_approval(policy_root):
    decision = policy_enforcement.enforce(
        "web_fetch", {"url": "https://unlisted.example.com/x"},
        state_root=policy_root, interactive=True)
    assert decision is not None
    assert decision.decision == "ask"


# --- W7: policy file loading / saving must be consistent and private --------

def test_active_policy_handles_file_vanishing_between_check_and_read(
        policy_root, monkeypatch):
    """A policy that disappears before the read must not raise out of the
    permission evaluator (the old is_file()/read_text() pair did)."""
    target = policy_enforcement.policy_path(policy_root)
    real_read_bytes = Path.read_bytes

    def vanished_read(self):
        if self == target:
            try:
                self.unlink()
            except OSError:
                pass
            raise FileNotFoundError(str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", vanished_read)
    assert policy_enforcement.active_policy(policy_root) is None


def test_policy_save_writes_atomically_owner_only(tmp_path, monkeypatch):
    calls = _capture_open_modes(monkeypatch)

    exec_policy.ExecPolicyStore(tmp_path).save("default", POLICY_DOC)

    relevant = [c for c in calls
                if Path(c[0]).name.startswith("default.json.tmp-")]
    assert relevant, "policy save must stage through an owner-only temp file"
    assert any(mode == 0o600 for _path, _flags, mode in relevant)
    assert (tmp_path / "exec-policies" / "default.json").is_file()


def test_provider_config_file_created_owner_only(tmp_path, monkeypatch):
    calls = _capture_open_modes(monkeypatch)

    secret_providers.ProviderConfig(tmp_path).save({"providers": []})

    relevant = [c for c in calls
                if Path(c[0]).name == "secret-providers.json"]
    assert relevant
    assert any(mode == 0o600 for _path, _flags, mode in relevant)
