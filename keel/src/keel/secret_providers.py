"""A4.7 — real local secret providers chosen by the user.

Providers beyond the OS keychain: a local ``.env`` file, an explicit user-owned
command (e.g. ``pass show``), and process environment. They resolve credential
values for local use without a hosted secret service.

Security posture: provider listings and diagnostics never include secret
values. ``resolve(reveal=False)`` reports presence only; revealing a value is
an explicit caller choice. Command providers are opt-in, run with ``shell=False``
and a timeout, and only ever receive the requested key as an argument. This
module stores no plaintext of its own.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

MAX_SECRET = 16_384
_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


class EnvProvider:
    name = "env"

    def describe(self) -> dict:
        return {"name": self.name, "kind": "env", "configured": True}

    def get(self, key: str) -> str | None:
        return os.environ.get(key) or None


class EnvFileProvider:
    name = "env-file"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def describe(self) -> dict:
        return {"name": self.name, "kind": "file",
                "configured": self.path.is_file(), "path": str(self.path)}

    def get(self, key: str) -> str | None:
        if not self.path.is_file():
            return None
        for line in self.path.read_text(encoding="utf-8",
                                        errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == key:
                return _clean(value) or None
        return None


class CommandProvider:
    name = "command"

    def __init__(self, command: list[str], *, timeout_s: float = 10):
        if not command or not isinstance(command, (list, tuple)):
            raise ValueError("command must be a non-empty list")
        self.command = [str(c) for c in command]
        self.timeout_s = float(timeout_s)

    def describe(self) -> dict:
        return {"name": self.name, "kind": "exec", "configured": True,
                "command": self.command, "shell": False,
                "note": "runs a user-specified program; receives only the key"}

    def get(self, key: str) -> str | None:
        if not _KEY.fullmatch(key):
            raise ValueError("invalid secret key")
        try:
            result = subprocess.run(
                self.command + [key], capture_output=True, shell=False,
                timeout=self.timeout_s, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", errors="replace").strip()[:MAX_SECRET] or None


class ProviderChain:
    """Resolve a key from the first provider that supplies a non-empty value."""

    def __init__(self, providers: list):
        self.providers = list(providers)

    def describe(self) -> list[dict]:
        return [p.describe() for p in self.providers]

    def resolve(self, key: str, *, reveal: bool = False) -> dict:
        if not _KEY.fullmatch(key):
            raise ValueError("invalid secret key")
        for provider in self.providers:
            value = provider.get(key)
            if value:
                return {
                    "key": key, "source": provider.name, "present": True,
                    "value": value if reveal else None,
                    "length": len(value),
                    "note": "value revealed" if reveal else
                            "presence only; pass reveal=True to obtain value",
                }
        return {"key": key, "source": None, "present": False,
                "value": None, "length": 0}


def chain_from_config(config: dict) -> ProviderChain:
    """Build a chain from a serializable provider configuration."""
    providers = []
    for entry in config.get("providers", []):
        kind = str(entry.get("kind", ""))
        if kind == "env":
            providers.append(EnvProvider())
        elif kind == "env-file":
            providers.append(EnvFileProvider(entry["path"]))
        elif kind == "command":
            providers.append(CommandProvider(entry["command"],
                                             timeout_s=entry.get("timeout_s", 10)))
        else:
            raise ValueError(f"unsupported provider kind: {kind}")
    return ProviderChain(providers)


class ProviderConfig:
    """Persist a user's provider choice in local state (no secret values)."""

    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "secret-providers.json"

    def save(self, config: dict) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config, indent=2) + "\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(self.path), flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        return self.path

    def load(self) -> dict:
        if not self.path.is_file():
            return {"providers": []}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"providers": []}
        return doc if isinstance(doc, dict) else {"providers": []}
