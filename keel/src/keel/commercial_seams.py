"""Dormant commercial seams (B6.x).

These descriptors exist so the product can add editions later without changing
its architecture. Nothing here enables paid features, enforces licensing, or
gates functionality: it only records metadata and shows honest placeholders.
"""

from __future__ import annotations

EDITION = "standard"


def edition_field() -> dict:
    return {"edition": EDITION, "licensing_enabled": False,
            "note": "Dormant seam; no paid functionality is enforced."}


def license_token_format() -> dict:
    """Reserved format descriptor — no verifier is activated."""
    return {"format": "keel-license-v1", "signature": "ed25519",
            "active": False, "note": "Reserved for future owner decision."}


def silent_install_flags(platform: str) -> list[str]:
    return {
        "windows": ["/VERYSILENT", "/NORESTART"],
        "linux": ["--silent"],
        "macos": ["-silent"],
    }.get(platform, [])


def compliance_pack_status() -> dict:
    return {"security_whitepaper": "draft", "accessibility_report": "draft",
            "notices": "draft", "note": "Requires owner legal review."}
