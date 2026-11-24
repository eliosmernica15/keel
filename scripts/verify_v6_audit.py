#!/usr/bin/env python3
"""Verify consistency of the Master Plan v6 registry and evidence set.

Updated for the complete 865-row registry (all eight specification documents).
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "master-plan-v6-final-matrix.csv",
    "master-plan-v6-final-matrix.json",
    "master-plan-v6-final-report.md",
    "master-plan-v6-architecture-map.md",
    "master-plan-v6-test-evidence.md",
    "master-plan-v6-security-findings.md",
    "master-plan-v6-git-provenance.md",
    "master-plan-v6-agent-execution.md",
]
EXPECTED = 865
BASE_SOURCES = {
    "Keel_Plan_v5_Addendum_Missed_Features.md": 133,
    "Keel_Plan_v5_Addendum_2_More_Features.md": 95,
    "Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md": 132,
    "Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md": 128,
    "Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md": 114,
    "Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md": 123,
    "Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md": 140,
}
BASE_TIERS = {
    "operational": 52, "external_dependency": 3, "descriptor": 3,
}
# Tier is a type, not a progress status: all addenda 3-7 rows are local_module
# unless owner-gated. Progress is tracked in `status` (not_started/verified).
# owner_gated should be 2 base + owner-gated addenda rows, so check >= 2.


def main() -> None:
    errors: list[str] = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"missing evidence file: {name}")

    index = json.loads((ROOT / "PLAN-INDEX.json").read_text(encoding="utf-8"))
    parity = json.loads((ROOT / "parity.json").read_text(encoding="utf-8"))
    if index != parity:
        errors.append("PLAN-INDEX.json != parity.json")

    feats = index["features"]
    if len(feats) != EXPECTED:
        errors.append(f"registry has {len(feats)} rows, expected {EXPECTED}")
    ids = [f["id"] for f in feats]
    if len(ids) != len(set(ids)):
        errors.append("duplicate feature IDs in registry")

    per_source = Counter(f.get("source_document", "") for f in feats)
    for src, n in BASE_SOURCES.items():
        if per_source.get(src) != n:
            errors.append(f"{src}: {per_source.get(src, 0)} rows, expected {n}")

    tiers = Counter(f.get("implementation_tier") for f in feats)
    for tier, n in BASE_TIERS.items():
        if tiers.get(tier) != n:
            errors.append(f"tier {tier}: {tiers.get(tier)} != {n}")
    if tiers.get("owner_gated", 0) < 2:
        errors.append("owner_gated tier missing base rows")
    if "not_started" in tiers:
        errors.append("not_started must be a status, never an implementation_tier")
    # Every verified feature must have source + test references and evidence.
    for f in feats:
        if f.get("status") == "verified" and f["id"].startswith(("E", "X", "Y", "W", "D", "V", "Z")):
            if not f.get("source_files") or not f.get("test_references") or not f.get("verification_evidence"):
                errors.append(f"verified row {f['id']} lacks implementation evidence")

    pct = 100.0 * sum(1 for f in feats if f.get("priority") == "P0") / len(feats)
    if not (22 <= pct <= 30):
        errors.append(f"P0 share {pct:.1f}% outside 22-30% target")

    matrix = json.loads((ROOT / "master-plan-v6-final-matrix.json").read_text(encoding="utf-8"))
    if len(matrix) != EXPECTED:
        errors.append(f"matrix JSON has {len(matrix)} rows, expected {EXPECTED}")
    mat_ids = {r["id"] for r in matrix}
    if mat_ids != set(ids):
        errors.append("matrix IDs differ from registry IDs")
    with (ROOT / "master-plan-v6-final-matrix.csv").open(encoding="utf-8", newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    if len(csv_rows) != EXPECTED or {r["id"] for r in csv_rows} != mat_ids:
        errors.append("CSV matrix rows/IDs differ")

    for name in ["DECISIONS.md", "RISKS.md", "FREE-TIER-REGISTER.md",
                 "MODEL-AND-VOICE-LICENSES.json"]:
        if not (ROOT / name).is_file() and not (ROOT / "keel" / "docs" / name).is_file():
            errors.append(f"missing required governance document: {name}")

    print("registry rows:", len(feats))
    print("source counts:", dict(per_source))
    print("tiers:", dict(tiers))
    print("P0 share: %.1f%%" % pct)
    print("matrix rows:", len(matrix))
    if errors:
        print("CONSISTENCY FAILED:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)
    print("CONSISTENCY OK")


if __name__ == "__main__":
    main()
