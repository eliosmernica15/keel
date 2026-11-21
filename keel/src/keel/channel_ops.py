"""Channel delivery fallback, webhook subscriptions and troubleshooting (A5.x).

All local-only: fallback chains are evaluated in-process, webhook subscriptions
are stored locally with rotatable secrets, and troubleshooting checklists are
static guidance surfaced when a channel fails.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DeliveryAttempt:
    channel: str
    ok: bool
    detail: str


def deliver_with_fallback(chain: list[str], send: object,
                          *, max_attempts: int | None = None) -> list[DeliveryAttempt]:
    """Try each channel in order until one succeeds."""
    attempts = []
    for channel in chain[:max_attempts or len(chain)]:
        try:
            result = send(channel)
            ok = bool(result) if not isinstance(result, tuple) else bool(result[0])
            detail = result[1] if isinstance(result, tuple) and len(result) > 1 else ""
            attempts.append(DeliveryAttempt(channel, ok, str(detail)))
            if ok:
                break
        except Exception as exc:
            attempts.append(DeliveryAttempt(channel, False, str(exc)))
    return attempts


class SubscriptionStore:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "webhook-subscriptions.json"

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

    def register(self, name: str, url: str, events: list[str]) -> dict:
        entry = {"name": name, "url": url, "events": list(events),
                 "secret": secrets.token_urlsafe(24)}
        doc = self._load()
        doc[name] = entry
        self._save(doc)
        return entry

    def list(self) -> list[dict]:
        return list(self._load().values())

    def rotate(self, name: str) -> str | None:
        doc = self._load()
        entry = doc.get(name)
        if not isinstance(entry, dict):
            return None
        entry["secret"] = secrets.token_urlsafe(24)
        self._save(doc)
        return entry["secret"]

    def remove(self, name: str) -> bool:
        doc = self._load()
        if name not in doc:
            return False
        doc.pop(name)
        self._save(doc)
        return True


TROUBLESHOOTING = {
    "email": ["Verify IMAP host and port", "Check app password, not account password",
              "Confirm the mailbox is not over quota"],
    "calendar": ["Check ICS URL is reachable", "Verify calendar permissions",
                 "Confirm device clock is accurate"],
    "webhook": ["Confirm HTTPS URL", "Verify signature secret matches",
                "Check receiver returns 2xx"],
}


def checklist(channel: str) -> list[str]:
    return TROUBLESHOOTING.get(channel, ["Check credentials", "Check network",
                                          "Review local diagnostics bundle"])
