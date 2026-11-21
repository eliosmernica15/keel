"""Secret provider choices (A4.7) and channel install sources (A5.2).

Descriptors only: secret providers list where a user may keep credentials
(env, file, command, keychain) without reading them here; channel installs are
recorded from git URLs or local links and stay dormant until approved.
"""

from __future__ import annotations

import json
from pathlib import Path

SECRET_PROVIDERS = {
    "keychain": {"kind": "system", "note": "OS keyring via keyring library"},
    "env": {"kind": "env", "note": "KEEL_* environment variables"},
    "env-file": {"kind": "file", "note": "Local .env file, gitignored"},
    "command": {"kind": "exec", "note": "User command (e.g. pass), opt-in"},
}


def secret_provider(name: str) -> dict:
    return SECRET_PROVIDERS.get(name, {"kind": "unknown", "note": "unsupported"})


class ChannelInstalls:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "channel-installs.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def add(self, name: str, source: str) -> dict:
        if not (source.startswith("git+") or source.startswith("file://")
                or Path(source).is_absolute()):
            raise ValueError("source must be a git URL or local path")
        entry = {"name": name, "source": source, "approved": False}
        doc = self._load()
        doc[name] = entry
        self._save(doc)
        return entry

    def list(self) -> list[dict]:
        return list(self._load().values())
