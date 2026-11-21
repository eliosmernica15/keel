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


def outbox_path(state_root: str | Path) -> Path:
    return Path(state_root) / "outbox.jsonl"


def deliver_to_outbox(state_root: str | Path, channel: str, message: str,
                      *, destination: str = "") -> DeliveryAttempt:
    """Really persist a message to the local outbox — no fake success.

    This is a genuine local delivery surface: the message is durably written
    with its channel, destination and timestamp, and can be inspected or
    forwarded by an operator. External channels (SMTP, webhook) are separate
    opt-in adapters; this function never claims to have sent anything online.
    """
    import time

    target = outbox_path(state_root)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "channel": channel, "destination": destination,
            "message": str(message)[:10000], "status": "queued_local",
        }
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return DeliveryAttempt(channel, True, f"written to {target}")
    except OSError as exc:
        return DeliveryAttempt(channel, False, f"outbox write failed: {exc}")


def deliver_chain_to_outbox(state_root: str | Path, chain: list[str],
                            message: str, *, destination: str = "") -> list[dict]:
    """Deliver via the fallback chain using the real local outbox sender."""
    attempts = deliver_with_fallback(
        chain, lambda channel: deliver_to_outbox(
            state_root, channel, message, destination=destination))
    return [a.__dict__ for a in attempts]


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
