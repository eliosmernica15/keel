"""Master Plan v6 feature registry consistency tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOWNLOADS = Path(r"C:\Users\Admin\Downloads")
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
        "owner_approval_required",
    }
    for feature in _registry()["features"]:
        assert required <= set(feature), feature["id"]
        assert feature["status"] in {
            "not_started", "in_progress", "implemented", "verified", "blocked"}


def test_v6_plan_contains_every_feature_id():
    text = (REPO / "Keel_Master_Plan_v6.md").read_text(encoding="utf-8")
    for feature in _registry()["features"]:
        assert feature["id"] in text
