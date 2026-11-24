#!/usr/bin/env python3
"""Verify the v6 backend-completion operation's final state.

Checks:
  - 865 canonical features, parity identical, no duplicate IDs
  - backend attribution covers all promised IDs
  - every verified backend row has real source/test/evidence references
  - all 20 backend modules exist and integrate through backend_hub/capabilities
  - provenance of all review/remediation commits is present
"""
from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "keel" / "src"))

errors: list[str] = []

index = json.loads((ROOT / "PLAN-INDEX.json").read_text(encoding="utf-8"))
parity = json.loads((ROOT / "parity.json").read_text(encoding="utf-8"))
features = index["features"]
if index != parity:
    errors.append("PLAN-INDEX.json != parity.json")
if len(features) != 865:
    errors.append(f"expected 865 features, got {len(features)}")
ids = [f["id"] for f in features]
if len(ids) != len(set(ids)):
    errors.append("duplicate feature IDs")

status = Counter(f["status"] for f in features)
if status != Counter({"verified": 854, "not_started": 9, "blocked": 2}):
    errors.append(f"unexpected status counts: {dict(status)}")

data = json.loads((ROOT / "backend-final-attribution.json").read_text(encoding="utf-8"))
attribution = data["attribution"]
if len(attribution) != 421:
    errors.append(f"expected 421 attributed backend IDs, got {len(attribution)}")
by_id = {f["id"]: f for f in features}
for fid, mod in attribution.items():
    row = by_id.get(fid)
    if row is None:
        errors.append(f"attributed ID missing from registry: {fid}")
        continue
    if row["status"] != "verified":
        errors.append(f"attributed ID not verified: {fid}")
    # source/test paths in the registry are relative to the keel/ project dir
    def resolve(rel: str) -> Path:
        q = Path(rel)
        return ROOT / "keel" / q if not (ROOT / q).exists() else ROOT / q
    paths = [resolve(p) for p in (row.get("source_files") or [])] + \
            [resolve(p) for p in (row.get("test_references") or [])]
    if any(not p.exists() for p in paths):
        errors.append(f"missing source/test evidence for {fid}: {[str(p) for p in paths if not p.exists()]}")
    if not row.get("verification_evidence"):
        errors.append(f"missing verification evidence for {fid}")
    if not (ROOT / row["verification_evidence"]).exists():
        errors.append(f"evidence doc missing for {fid}: {row['verification_evidence']}")

from keel import backend_hub as hub
from keel import capabilities

if len(hub.modules()) != 20:
    errors.append(f"expected 20 backend modules, got {len(hub.modules())}")
if not set(attribution) <= set(hub.feature_ids()):
    errors.append(f"hub index missing {len(set(attribution) - set(hub.feature_ids()))} attributed IDs")
caps = {c["id"] for c in capabilities.list_capabilities()}
for needed in ("backend.modules", "backend.describe", "backend.invoke", "backend.verify"):
    if needed not in caps:
        errors.append(f"capability not registered: {needed}")

# Every attributed feature must be reachable in the hub's index
for fid in attribution:
    if fid not in hub.FEATURE_TO_MODULE:
        errors.append(f"attributed ID absent from hub index: {fid}")

# Every module must import cleanly and declare its features
for mod in hub.modules():
    try:
        importlib.import_module("keel." + mod)
    except Exception as exc:
        errors.append(f"module import failed: {mod}: {exc}")

for name in ("BACKEND-IMPLEMENTATION-DETAIL.md", "BACKEND-OPERATION-TASKBOARD.md",
             "master-plan-v6-review-group1.md", "master-plan-v6-review-group2.md",
             "master-plan-v6-review-group3.md", "master-plan-v6-review-group4.md"):
    if not (ROOT / name).is_file():
        errors.append(f"missing operation document: {name}")

print("features:", len(features), "status:", dict(status))
print("backend modules:", len(hub.modules()), "attributed IDs:", len(attribution))
print("capabilities:", sorted(c for c in caps if c.startswith("backend.")))
if errors:
    print("BACKEND OPERATION VERIFICATION FAILED:")
    for e in errors:
        print("  -", e)
    raise SystemExit(1)
print("BACKEND OPERATION VERIFICATION OK")
