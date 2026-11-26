"""Master Plan v6 feature registry consistency tests."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOWNLOADS = Path(__file__).resolve().parents[1] / "docs" / "plan-sources"
ID_RE = re.compile(r"^[ABC]\d+\.\d+$")


def _registry():
    return json.loads((REPO / "PLAN-INDEX.json").read_text(encoding="utf-8"))


def test_registry_and_parity_are_synchronized():
    assert (REPO / "PLAN-INDEX.json").read_bytes() == \
        (REPO / "parity.json").read_bytes()


def test_all_addendum_feature_ids_are_registered():
    doc = _registry()
    ids = {f["id"] for f in doc["features"]}
    expected = set()
    for name in ("Keel_Plan_v5_Addendum_Missed_Features.md",
                 "Keel_Plan_v5_Addendum_2_More_Features.md"):
        for line in (DOWNLOADS / name).read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("|"):
                continue
            cell = line.strip().strip("|").split("|")[0].strip()
            if ID_RE.match(cell):
                expected.add(cell)
    assert expected and expected <= ids
    assert len(ids) == len(doc["features"])


def test_registry_entries_have_required_fields():
    required = {
        "id", "feature", "source_document", "source_feature_id", "milestone",
        "priority", "status", "source_files", "dependencies",
        "acceptance_criteria", "test_references", "verification_evidence",
        "owner_approval_required", "implementation_tier",
    }
    for feature in _registry()["features"]:
        assert required <= set(feature), feature["id"]
        assert feature["status"] in {
            "not_started", "in_progress", "implemented", "verified", "blocked"}
        assert feature["implementation_tier"] in {
            "operational", "local_module", "descriptor",
            "external_dependency", "owner_gated"}


def test_authoritative_source_hashes_unchanged():
    """Pin the canonical source copies committed in `keel/docs/plan-sources/`.

    These hashes guard the canonical source files against accidental drift.
    """
    expected = {
        "Keel_Master_Plan_v5.md":
            "da1dd5dc81d7f85fadbc5e10143c937e7fc63fd34b86f0f0d3659f7af67d427f",
        "Keel_Plan_v5_Addendum_Missed_Features.md":
            "e4e314a5a0c31f7868e7568d061fb5aebbe809144624479f96537eb0c84b6583",
        "Keel_Plan_v5_Addendum_2_More_Features.md":
            "b42219150271fa9e25dbd28c878beba3608032c17e221fdda73d716f4fc9125a",
    }
    for name, prefix in expected.items():
        digest = hashlib.sha256((DOWNLOADS / name).read_bytes()).hexdigest()
        assert digest.startswith(prefix), f"{name} changed: {digest}"


def test_v6_plan_contains_every_feature_id():
    text = (REPO / "Keel_Master_Plan_v6.md").read_text(encoding="utf-8")
    for feature in _registry()["features"]:
        assert feature["id"] in text
