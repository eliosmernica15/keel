"""A3.7 — honest registry-driven project status page."""

from __future__ import annotations

import json
from pathlib import Path

from keel.status_page import build_status, render_markdown

REGISTRY = Path(__file__).resolve().parents[2] / "PLAN-INDEX.json"


def test_build_status_from_real_registry():
    status = build_status(REGISTRY)
    assert status["total"] == 228
    assert status["by_status"]["verified"] == 226
    assert status["by_status"]["blocked"] == 2
    assert status["verified_end_to_end"] > 0
    assert {b["id"] for b in status["blocked"]} == {"C11.1", "C11.2"}
    assert all(b["owner_approval_required"] for b in status["blocked"])


def test_unproven_items_are_separated():
    status = build_status(REGISTRY)
    ids = {u["id"] for u in status["unproven"]}
    assert {"B6.2", "B6.3", "B6.5", "B4.8", "B6.6", "C11.8"} <= ids
    # No operational/local module should be counted as unproven.
    assert not any(u["tier"] in ("operational", "local_module")
                   for u in status["unproven"])


def test_status_does_not_double_count():
    status = build_status(REGISTRY)
    assert status["verified_end_to_end"] + status["built_unproven"] + \
        len(status["blocked"]) == status["total"]


def test_markdown_rendering():
    text = render_markdown(build_status(REGISTRY))
    assert "honest project status" in text
    assert "Blocked items" in text
    assert "C11.1" in text and "C11.2" in text
    assert "Built but unproven locally" in text


def test_capability_integration():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    result = invoke("core.status.project", {"registry": str(REGISTRY)},
                    context={})["result"]
    assert result["total"] == 228
    assert "honest project status" in result["markdown"]
