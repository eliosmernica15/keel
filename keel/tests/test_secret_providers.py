"""A4.7 — real local secret providers with value-safe diagnostics."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from keel.secret_providers import (CommandProvider, EnvFileProvider,
                                   EnvProvider, ProviderChain, ProviderConfig,
                                   chain_from_config)

ROOT = Path(__file__).resolve().parents[1]


def test_env_provider(monkeypatch):
    monkeypatch.setenv("KEEL_TEST_SECRET", "s3cret")
    assert EnvProvider().get("KEEL_TEST_SECRET") == "s3cret"
    assert EnvProvider().get("MISSING_XYZ") is None


def test_env_file_provider(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nexport KEEL_A=alpha\nKEEL_B=\"quoted value\"\n"
        "KEEL_C='single'\nMALFORMED\n", encoding="utf-8")
    provider = EnvFileProvider(env)
    assert provider.describe()["configured"] is True
    assert provider.get("KEEL_A") == "alpha"
    assert provider.get("KEEL_B") == "quoted value"
    assert provider.get("KEEL_C") == "single"
    assert provider.get("KEEL_MISSING") is None


def test_command_provider(tmp_path):
    # Use a harmless local command that echoes the key it receives.
    script = tmp_path / "provider.cmd"
    script.write_text("@echo %~1\n", encoding="utf-8")
    provider = CommandProvider(["cmd", "/c", str(script)], timeout_s=5)
    assert provider.describe()["shell"] is False
    assert provider.get("KEEL_KEY") == "KEEL_KEY"


def test_chain_presence_only_by_default():
    class Static:
        name = "static"

        def describe(self):
            return {"name": "static", "kind": "test", "configured": True}

        def get(self, key):
            return "topsecret" if key == "FOUND" else None

    chain = ProviderChain([Static()])
    result = chain.resolve("FOUND")
    assert result["present"] is True and result["source"] == "static"
    assert result["value"] is None and result["length"] == 9
    revealed = chain.resolve("FOUND", reveal=True)
    assert revealed["value"] == "topsecret"
    assert chain.resolve("MISSING")["present"] is False


def test_chain_from_config_and_persistence(tmp_path):
    env = tmp_path / ".env"
    env.write_text("KEEL_FROM_FILE=filevalue\n", encoding="utf-8")
    config = {"providers": [
        {"kind": "env-file", "path": str(env)},
        {"kind": "env"},
    ]}
    store = ProviderConfig(tmp_path)
    store.save(config)
    assert "secret values" not in store.path.read_text(encoding="utf-8")
    chain = chain_from_config(store.load())
    result = chain.resolve("KEEL_FROM_FILE")
    assert result["present"] is True and result["source"] == "env-file"
    assert result["value"] is None


def test_invalid_key_rejected():
    chain = ProviderChain([EnvProvider()])
    try:
        chain.resolve("bad key")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid key accepted")


def test_capability_never_reveals():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    result = invoke("core.secrets.has", {"key": "PATH"},
                    context={})["result"]
    assert "value" not in result
    assert result["present"] is True


def test_cli_secrets(tmp_path):
    state = tmp_path / "state"
    env = {**os.environ, "KEEL_STATE_DIR": str(state),
           "KEEL_CLI_SECRET": "cli-value"}
    listed = subprocess.run(
        [sys.executable, "-m", "keel", "secrets", "providers"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)
    has = subprocess.run(
        [sys.executable, "-m", "keel", "secrets", "has", "KEEL_CLI_SECRET"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert has.returncode == 0 and "cli-value" not in has.stdout
    got = subprocess.run(
        [sys.executable, "-m", "keel", "secrets", "get", "KEEL_CLI_SECRET"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert got.returncode == 0 and got.stdout.strip() == "cli-value"
