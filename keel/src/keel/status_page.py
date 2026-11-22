"""A3.7 — honest, registry-driven project status page.

Generates a status document directly from the canonical ``PLAN-INDEX.json`` so
it cannot drift from actual verification state. It distinguishes features that
are genuinely verified end-to-end (operational/local modules with passing test
references) from built-but-unproven descriptors and external dependencies, and
lists blocked items with their precise gate. No claim is upgraded without
evidence in the registry.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PROVEN_TIERS = frozenset({"operational", "local_module"})
UNPROVEN_TIERS = frozenset({"descriptor", "external_dependency"})


def _registry_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "PLAN-INDEX.json",
                      here.parents[3] / "PLAN-INDEX.json"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("PLAN-INDEX.json not found")


def load_registry(path: str | Path | None = None) -> dict:
    doc = json.loads(_registry_path(path).read_text(encoding="utf-8"))
    if not isinstance(doc.get("features"), list):
        raise ValueError("registry has no features list")
    return doc


def build_status(path: str | Path | None = None) -> dict:
    registry = load_registry(path)
    features = registry["features"]
    by_status = Counter(f.get("status", "unknown") for f in features)
    by_tier = Counter(f.get("implementation_tier", "unknown") for f in features)
    by_priority = Counter(f.get("priority", "unknown") for f in features)

    proven = [f for f in features
              if f.get("status") == "verified"
              and f.get("implementation_tier") in PROVEN_TIERS
              and f.get("test_references")]
    unproven = [f for f in features
                if f.get("status") == "verified"
                and f.get("implementation_tier") in UNPROVEN_TIERS]
    blocked = [f for f in features if f.get("status") == "blocked"]

    return {
        "total": len(features),
        "by_status": dict(by_status),
        "by_tier": dict(by_tier),
        "by_priority": dict(by_priority),
        "verified_end_to_end": len(proven),
        "built_unproven": len(unproven),
        "proven_ids": [f["id"] for f in proven],
        "unproven": [{"id": f["id"], "tier": f.get("implementation_tier"),
                      "feature": f.get("feature", "")[:120]}
                     for f in unproven],
        "blocked": [{"id": f["id"], "feature": f.get("feature", "")[:160],
                     "owner_approval_required":
                         f.get("owner_approval_required", False)}
                    for f in blocked],
        "honesty_note": (
            "verified = tests and real-runtime checks pass per the registry; "
            "built_unproven = descriptor/external-dependency items that need "
            "an external environment or owner decision; blocked = owner-gated"),
    }


def render_markdown(status: dict) -> str:
    lines = [
        "# Keel — honest project status",
        "",
        f"**Features in registry:** {status['total']}",
        f"**Verified end-to-end:** {status['verified_end_to_end']}",
        f"**Built but unproven locally:** {status['built_unproven']}",
        f"**Blocked (owner/external):** {len(status['blocked'])}",
        "",
        "## By implementation tier",
        "",
        "| Tier | Count |",
        "| --- | ---: |",
    ]
    for tier, count in sorted(status["by_tier"].items()):
        lines.append(f"| {tier} | {count} |")
    lines += ["", "## Blocked items", ""]
    for item in status["blocked"]:
        gate = "owner decision" if item["owner_approval_required"] else "external"
        lines.append(f"- **{item['id']}** ({gate}): {item['feature']}")
    lines += ["", "## Built but unproven locally", ""]
    for item in status["unproven"]:
        lines.append(f"- **{item['id']}** ({item['tier']}): {item['feature']}")
    lines += ["", "_" + status["honesty_note"] + "_", ""]
    return "\n".join(lines)
