#!/usr/bin/env python3
"""Verify consistency of the Master Plan v6 final audit evidence set."""
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


def main() -> None:
    errors = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"missing evidence file: {name}")

    index = json.loads((ROOT / "PLAN-INDEX.json").read_text(encoding="utf-8"))
    parity = json.loads((ROOT / "parity.json").read_text(encoding="utf-8"))
    if index != parity:
        errors.append("PLAN-INDEX.json != parity.json")

    matrix = json.loads(
        (ROOT / "master-plan-v6-final-matrix.json").read_text(encoding="utf-8"))
    if len(matrix) != 228:
        errors.append(f"matrix JSON has {len(matrix)} rows, expected 228")

    idx_ids = {f["id"] for f in index["features"]}
    mat_ids = {r["id"] for r in matrix}
    if idx_ids != mat_ids:
        errors.append("matrix IDs differ from registry IDs")

    with (ROOT / "master-plan-v6-final-matrix.csv").open(
            encoding="utf-8", newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    if len(csv_rows) != 228:
        errors.append(f"matrix CSV has {len(csv_rows)} rows, expected 228")
    if {r["id"] for r in csv_rows} != mat_ids:
        errors.append("CSV IDs differ from JSON matrix IDs")

    counts = Counter(r["tier"] for r in matrix)
    expected = {"operational": 52, "local_module": 168,
                "external_dependency": 3, "descriptor": 3, "owner_gated": 2}
    if dict(counts) != expected:
        errors.append(f"tier counts {dict(counts)} != {expected}")

    flagged = {r["id"] for r in matrix if not r["implementation_verified"]}
    expected_flagged = {"B4.8", "B6.6", "C11.8", "B6.2", "B6.3", "B6.5",
                        "C11.1", "C11.2"}
    if flagged != expected_flagged:
        errors.append(f"flagged IDs {flagged} != {expected_flagged}")

    print("evidence files:", len(REQUIRED), "present:",
          sum((ROOT / n).is_file() for n in REQUIRED))
    print("registry count:", len(idx_ids), "matrix rows:", len(matrix))
    print("parity identical:", index == parity)
    print("tier counts:", dict(counts))
    print("verified:", sum(1 for r in matrix if r["implementation_verified"]))
    print("flagged:", sorted(flagged))
    if errors:
        print("CONSISTENCY FAILED:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)
    print("CONSISTENCY OK")


if __name__ == "__main__":
    main()
