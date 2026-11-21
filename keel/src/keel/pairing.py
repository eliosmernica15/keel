"""LAN/headless client pairing allowlist and revocation (C1.12).

Explicit opt-in allowlist of client identifiers permitted to reach the local
bridge over the LAN. State is local JSON; the bridge token remains the primary
credential. Pairing never happens silently and can always be revoked.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


class PairingError(RuntimeError):
    pass


def pairing_path(state_root: str) -> Path:
    return Path(state_root) / "pairings.json"


class PairingStore:
    def __init__(self, state_root: str):
        self.path = pairing_path(state_root)

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

    def list_clients(self) -> list[dict]:
        doc = self._load()
        return list(doc.get("clients", {}).values())

    def is_paired(self, client_id: str) -> bool:
        doc = self._load()
        entry = doc.get("clients", {}).get(client_id)
        return isinstance(entry, dict) and not entry.get("revoked")

    def pair(self, label: str = "", *, scope: str = "lan") -> dict:
        if scope not in ("lan", "headless"):
            raise PairingError(f"unknown scope: {scope}")
        client_id = uuid.uuid4().hex[:16]
        entry = {"id": client_id, "label": str(label)[:80], "scope": scope,
                 "paired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
                 "revoked": False}
        doc = self._load()
        doc.setdefault("clients", {})[client_id] = entry
        self._save(doc)
        return entry

    def revoke(self, client_id: str) -> bool:
        doc = self._load()
        entry = doc.get("clients", {}).get(client_id)
        if not isinstance(entry, dict):
            return False
        entry["revoked"] = True
        entry["revoked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save(doc)
        return True
