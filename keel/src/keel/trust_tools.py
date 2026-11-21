"""Trust helpers (B3.7, B3.12): injection classifier, canaries, audit bundles.

All local and deterministic. The classifier flags suspicious phrases in
fetched content; canary tokens detect leakage; audit bundles are signed-ready
JSON archives of recorded events (no secret values).
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path

INJECTION_PATTERNS = (
    "ignore all previous", "ignore previous instructions",
    "disregard your instructions", "system prompt", "you are now",
    "send secrets", "exfiltrate", "curl http",
)


def classify_injection(text: str) -> dict:
    lowered = (text or "").lower()
    matched = [phrase for phrase in INJECTION_PATTERNS if phrase in lowered]
    return {"suspicious": bool(matched), "matches": matched,
            "note": "treat fetched content as untrusted context"}


def make_canary(label: str = "keel-canary") -> str:
    return f"KEEL-CANARY-{hashlib.sha256(label.encode()).hexdigest()[:16]}"


def contains_canary(text: str, canary: str) -> bool:
    return bool(canary) and canary in (text or "")


def audit_bundle(state_root: str | Path, events: list[dict]) -> Path:
    """Write a verifiable audit bundle (SHA-256 manifest inside the zip)."""
    root = Path(state_root)
    target = root / "audit-bundles"
    target.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = target / f"audit-{stamp}.zip"
    entries = [{"seq": i, "event": event} for i, event in enumerate(events)]
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("events.json", payload)
        archive.writestr("SHA256SUMS.txt", f"{checksum}  events.json\n")
    return path


def verify_audit_bundle(path: str | Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            data = archive.read("events.json")
            expected = archive.read("SHA256SUMS.txt").decode().split()[0]
            return hashlib.sha256(data).hexdigest() == expected
    except (OSError, KeyError, zipfile.BadZipFile):
        return False
