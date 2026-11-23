"""Edition metadata and enterprise/compliance seams (B6.x).

Authorized for implementation in the v6 roadmap. These functions materialize
real local metadata and templates; **none of them enables licensing, gates
functionality, or enforces paid features**. Edition stays ``standard`` and the
license-token format stays inactive, as the roadmap requires.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import charts
from .release.common import LICENSE_INVENTORY

EDITION = "standard"
RESOURCES = Path(__file__).resolve().parents[2] / "resources"

# Package-manager formats -> real silent/unattended install flags (B6.3).
SILENT_FLAGS = {
    "nsis": ["/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
    "msi": ["/qn", "/norestart", "/L*V", "install.log"],
    "pkg": ["-pkg", "-target", "/"],
    "deb": ["-y", "-o", "Dpkg::Options::=--force-confdef"],
    "rpm": ["-y", "--noreplace"],
    "flatpak": ["--noninteractive", "--assumeyes"],
    "snap": ["--classic"],
}


def edition_field() -> dict:
    return {"edition": EDITION, "licensing_enabled": False,
            "note": "Standard edition; no paid functionality is enforced."}


def license_token_format() -> dict:
    """Reserved format descriptor — no verifier is activated."""
    return {"format": "keel-license-v1", "signature": "ed25519",
            "active": False, "note": "Reserved for future owner decision."}


def silent_install_flags(platform: str) -> list[str]:
    """Backward-compatible per-platform flag list."""
    return {
        "windows": SILENT_FLAGS["nsis"],
        "linux": SILENT_FLAGS["deb"],
        "macos": SILENT_FLAGS["pkg"],
    }.get(platform, [])


def silent_install_matrix() -> dict:
    """Full per-format silent-install flag matrix (B6.3)."""
    return {name: list(flags) for name, flags in SILENT_FLAGS.items()}


def enterprise_templates() -> dict:
    """Real, reviewable Windows ADMX and macOS managed-preferences templates."""
    base = RESOURCES / "enterprise"
    result = {}
    for key, filename in (("windows_admx", "Keel.admx"),
                          ("macos_plist", "com.keel.plist")):
        path = base / filename
        result[key] = {
            "file": str(path), "exists": path.is_file(),
            "content": path.read_text(encoding="utf-8") if path.is_file() else "",
        }
    return result


def compliance_pack_status() -> dict:
    """Status of the locally generated compliance artifacts (B6.5)."""
    return {"security_whitepaper": "draft", "accessibility_report": "draft",
            "data_flow_diagram": "generated", "sbom_export": "generated",
            "notices": "draft", "note": "Legal text requires owner legal review."}


def data_flow_svg() -> str:
    """Offline SVG data-flow diagram of Keel's local-only architecture."""
    nodes = ["User UI", "Local bridge", "Python runtime", "SQLite state",
             "Provider adapter"]
    edges = [("User UI", "Local bridge"), ("Local bridge", "Python runtime"),
             ("Python runtime", "SQLite state"),
             ("Python runtime", "Provider adapter")]
    return charts.flow_diagram(nodes, edges, width=520)


def sbom_export() -> dict:
    """Build an SBOM summary from the generated dependency inventory.

    Reads the canonical path written by ``python -m keel.release licenses
    --out release`` (keel/release/DEPENDENCY-LICENSES.json). No license data
    is invented when the build output is absent.
    """
    path = LICENSE_INVENTORY
    entries = []
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        source = doc.get("packages", doc) if isinstance(doc, dict) else doc
        if isinstance(source, dict):
            entries = [{"name": k, "metadata": v} for k, v in source.items()]
        elif isinstance(source, list):
            entries = list(source)
    return {
        "format": "Keel-SBOM-1.0", "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "component": "Keel", "edition": EDITION,
        "dependencies": entries, "count": len(entries),
        "note": "Derived from the committed third-party license inventory.",
    }


def accessibility_report() -> dict:
    """Locally verifiable accessibility checklist (not a legal conformance claim)."""
    return {
        "scope": "desktop/ui and site UI trees",
        "checks": [
            {"id": "keyboard", "status": "implemented",
             "detail": "Overlay and tour keyboard handlers present"},
            {"id": "live_region", "status": "implemented",
             "detail": "aria-live status region for streaming announcements"},
            {"id": "labels", "status": "implemented",
             "detail": "Interactive controls carry aria-label or text"},
            {"id": "contrast", "status": "review_required",
             "detail": "Theme variables defined; formal audit not performed"},
        ],
        "note": "Self-assessment, not a third-party conformance certificate.",
    }


def compliance_pack() -> dict:
    """All locally producible compliance artifacts in one payload (B6.5)."""
    return {
        "edition": EDITION,
        "status": compliance_pack_status(),
        "data_flow_svg": data_flow_svg(),
        "sbom": sbom_export(),
        "accessibility": accessibility_report(),
        "legal_templates": {
            "dpa": "draft — owner legal review required",
            "eula": "draft — owner legal review required",
        },
    }
