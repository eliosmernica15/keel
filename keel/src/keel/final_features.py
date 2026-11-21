"""Final local feature descriptors from the expanded roadmap.

Everything here is local, dormant, or documentation. Optional integrations
(voice services, remote targets, container desktop) describe user-controlled
capabilities and are never silently enabled.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def voice_handoff(session_id: str, transcript: str) -> dict:
    """A2.1: hand a voice transcript to the same agent/session."""
    return {"session_id": session_id, "task": transcript[:4000],
            "status": "queued", "note": "delivered to the same agent"}


def meeting_recorder(path: str | Path) -> dict:
    """C1.7: local meeting capture descriptor with speaker labels."""
    return {"file": str(path), "transcript": "local",
            "speaker_labels": True, "consent_required": True}


def deep_research(topic: str, sources: list[str]) -> dict:
    """B2.5: saved deep-research result with citation slots."""
    return {"topic": topic, "sources": list(sources)[:50],
            "citations": [], "note": "every claim must cite a source"}


class EncryptedBackups:
    """B4.11: local encrypted backup scheduling metadata (no key storage)."""

    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "backup-schedule.json"

    def schedule(self, interval_h: int, target: str) -> dict:
        entry = {"interval_h": max(1, int(interval_h)), "target": target,
                 "encryption": "user-managed", "last_run": None}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        return entry


def delta_update(channel: str = "stable") -> dict:
    """B4.14: delta update descriptor; beta is strictly opt-in."""
    return {"mode": "delta", "channel": channel if channel == "beta" else "stable",
            "beta_opt_in": channel == "beta"}


def lan_companion() -> dict:
    """B4.8: LAN companion descriptor requiring explicit pairing."""
    return {"transport": "lan-web", "pairing": "required",
            "tls": "pinned-self-signed", "note": "no cloud dependency"}


STRINGS = {"en": {"app": "Keel", "tagline": "Local-first AI workspace"},
           "es": {"app": "Keel", "tagline": "Espacio de trabajo IA local"}}


def localized(key: str, lang: str = "en") -> str:
    """B5.8: shared string catalog lookup."""
    return STRINGS.get(lang, STRINGS["en"]).get(key, key)


def incident_runbook() -> list[str]:
    """C11.3: source-leak response steps."""
    return ["rotate exposed keys", "revoke client tokens",
            "take down affected artifacts", "publish incident notice"]


def obfuscation_status() -> dict:
    """C11.8: deterrent-only, not a security boundary."""
    return {"nuitka_core": False, "bytecode": False,
            "note": "deterrent only; requires owner decision"}


def remote_target(kind: str) -> dict:
    """C4.10: user's own remote target descriptor."""
    if kind not in ("ssh", "wsl", "devcontainer"):
        raise ValueError(f"unknown target: {kind}")
    return {"kind": kind, "requires": "user credentials", "enabled": False}


def browser_devtools() -> list[str]:
    """C4.11: browser devtools tool descriptors."""
    return ["console", "network", "performance", "visual_diff"]


PACKAGE_MANAGERS = ["scoop", "chocolatey", "flatpak", "snap", "aur"]


def composer_accessibility() -> dict:
    """B4.9: optional composer keybindings and accessible font options."""
    return {"vim_keybindings": False, "dyslexia_font": False,
            "opt_in": True, "note": "both are opt-in UI preferences"}


def private_update_mirror(url: str = "") -> dict:
    """B6.4: private org update mirror descriptor (signed manifests only)."""
    return {"url": url, "requires_signed_manifest": True,
            "note": "dormant distribution seam; no hosted service"}


def org_audit_retention(days: int = 90) -> dict:
    """B6.6: per-organization audit export format and retention."""
    return {"format": "keel-audit-v1", "retention_days": max(1, int(days))}


def package_manager_targets() -> list[str]:
    """C1.2: additional binary package-manager targets."""
    return list(PACKAGE_MANAGERS)


def admin_page() -> dict:
    """A3.9: operator admin page descriptor."""
    return {"limits": True, "alerts": True, "health": True,
            "background_jobs": True}


def ci_mode() -> dict:
    """A1.19: headless CI mode descriptor (runs in user's own CI)."""
    return {"command": "keel run -p '...' --output-format stream-json",
            "headless": True, "note": "runs in your own CI, no Keel service"}
