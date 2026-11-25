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

# A bundled component must carry a license identifier a reviewer has recognised.
# Anything else fails closed: adding a new identifier here requires an explicit
# review of that license's commercial-use and redistribution terms.
KNOWN_BUNDLED_LICENSES = {
    "MIT", "MIT-0", "MIT-CMU", "BSD-2-Clause", "BSD-3-Clause",
    "Apache-2.0", "MPL-2.0", "ISC", "PSF-2.0", "CC0-1.0",
    "OFL-1.1", "SIL Open Font License 1.1",
}
UNKNOWN_MARKERS = {"", "UNKNOWN", "N/A", "NA", "NONE", "TBD", "MUST VERIFY",
                   "NOT APPLICABLE", "VARIES"}


def _is_unknown_license(value: object) -> bool:
    """True when a license field does not state a concrete, reviewed license."""
    text = str(value or "").strip().upper()
    return (not text or text in UNKNOWN_MARKERS
            or text.startswith(("VARIES", "NOT APPLICABLE")))


def main() -> int:
    if not REGISTRY.is_file():
        print(f"FAIL: missing {REGISTRY}")
        return 1
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = doc.get("entries", [])
    policy = doc.get("ci_policy", {})
    errors: list[str] = []
    unknown_unbundled: list[str] = []
    for e in entries:
        eid = e.get("id", "<unknown>")
        bundled = bool(e.get("bundled"))
        license_name = str(e.get("license") or "").strip()
        if not e.get("name") or not license_name:
            errors.append(f"{eid}: missing name or license")
            continue
        if _is_unknown_license(license_name):
            # Explicitly surfaced, never silently accepted. An entry whose
            # exact license is unknown must be unbundled and fail closed.
            if bundled:
                errors.append(f"{eid}: bundled but license is unknown/unreviewed")
            if (e.get("commercial_use_allowed") is True
                    or e.get("redistribution_allowed") is True):
                errors.append(f"{eid}: unknown license but usage rights granted")
            unknown_unbundled.append(eid)
            continue
        if not bundled:
            continue
        if license_name not in KNOWN_BUNDLED_LICENSES:
            errors.append(f"{eid}: bundled license not in reviewed allowlist: "
                          f"{license_name}")
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
    print("unbundled entries with UNKNOWN license (informational, blocked from "
          f"bundling): {', '.join(unknown_unbundled) or 'none'}")
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
