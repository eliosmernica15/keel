#!/usr/bin/env python3
"""CI gate for bundled model/voice/font/asset licenses (Addendum 3 X0.7).

Fails closed when a bundled component is non-commercial, non-redistributable,
has an unverified version/date, or lacks required fields. Unbundled entries
are informational only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "MODEL-AND-VOICE-LICENSES.json"


def main() -> int:
    if not REGISTRY.is_file():
        print(f"FAIL: missing {REGISTRY}")
        return 1
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = doc.get("entries", [])
    policy = doc.get("ci_policy", {})
    errors: list[str] = []
    for e in entries:
        eid = e.get("id", "<unknown>")
        bundled = bool(e.get("bundled"))
        if not e.get("name") or not e.get("license"):
            errors.append(f"{eid}: missing name or license")
            continue
        if not bundled:
            continue
        if e.get("commercial_use_allowed") is not True:
            errors.append(f"{eid}: bundled but commercial_use_allowed is not true")
        if e.get("redistribution_allowed") is not True:
            errors.append(f"{eid}: bundled but redistribution_allowed is not true")
        if not str(e.get("verified_date", "")).strip():
            errors.append(f"{eid}: bundled but verified_date is empty (MUST VERIFY)")
        if e.get("ci_gate") is not True:
            errors.append(f"{eid}: bundled but ci_gate is not true")
    print(f"license registry: {len(entries)} entries, "
          f"{sum(1 for e in entries if e.get('bundled'))} bundled")
    has_rule = (
        policy.get("reject_non_commercial_bundled") is True
        or any("commercial_use_allowed == false" in str(r)
               for r in policy.get("reject_when", []))
    )
    if not has_rule:
        errors.append("ci_policy must reject non-commercial bundled entries")
    if errors:
        print("LICENSE GATE FAILED:")
        for err in errors:
            print("  -", err)
        return 1
    print("LICENSE GATE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
