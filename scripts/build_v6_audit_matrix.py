#!/usr/bin/env python3
"""Generate the Master Plan v6 final feature matrix (CSV + JSON).

Reads the canonical PLAN-INDEX.json, verifies that every source-file and
test-file reference actually exists on disk, and emits:

  master-plan-v6-final-matrix.json
  master-plan-v6-final-matrix.csv

The generator is deliberately mechanical: it does not invent verification.
``implementation_verified`` is True only when the tier is one that represents
real local functionality AND every referenced source file exists. Owner-gated
and external-dependency items are never marked verified.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "PLAN-INDEX.json"

VERIFIED_TIERS = {"operational", "local_module"}


def resolve(rel: str) -> Path:
    """Resolve a registry path relative to the repo root, tolerating both
    root-relative and keel/-relative spellings."""
    candidates = [ROOT / rel]
    if not rel.startswith("keel/") and not rel.startswith("keel\\"):
        candidates.append(ROOT / "keel" / rel)
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def split_refs(value) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(str(item).split())
        return out
    return str(value or "").split()


def main() -> None:
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    features = doc["features"]
    rows = []
    for f in features:
        src = [resolve(s) for s in split_refs(f.get("source_files"))]
        tests = [resolve(t) for t in split_refs(f.get("test_references"))]
        src_ok = all(p.exists() for p in src) if src else False
        test_ok = all(p.exists() for p in tests) if tests else False
        tier = f.get("implementation_tier")
        status = f.get("status")
        verified = (
            tier in VERIFIED_TIERS
            and status == "verified"
            and src_ok
            and test_ok
        )
        notes = []
        if not src_ok:
            notes.append("source_file_missing")
        if not test_ok:
            notes.append("test_file_missing")
        if tier == "descriptor":
            notes.append("dormant_owner_directed")
        if tier == "external_dependency":
            notes.append("external_validation_pending")
        if tier == "owner_gated":
            notes.append("owner_blocked")
        rows.append({
            "id": f.get("id"),
            "feature": f.get("feature"),
            "tier": tier,
            "status": status,
            "milestone": f.get("milestone"),
            "priority": f.get("priority"),
            "source_files": "; ".join(str(p.relative_to(ROOT)) for p in src),
            "test_references": "; ".join(str(p.relative_to(ROOT)) for p in tests),
            "owner_approval_required": bool(f.get("owner_approval_required")),
            "implementation_verified": verified,
            "notes": ", ".join(notes),
        })

    json_path = ROOT / "master-plan-v6-final-matrix.json"
    csv_path = ROOT / "master-plan-v6-final-matrix.csv"
    json_path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter
    print("features:", len(rows))
    print("tiers:", dict(Counter(r["tier"] for r in rows)))
    print("statuses:", dict(Counter(r["status"] for r in rows)))
    print("verified:", sum(1 for r in rows if r["implementation_verified"]))
    print("flagged:", [(r["id"], r["notes"]) for r in rows if r["notes"]])


if __name__ == "__main__":
    main()
