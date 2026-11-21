"""C10.2/C10.3/C10.4 — error catalog, contextual help, local feedback."""

from __future__ import annotations

import json

from keel.onboarding import (FeedbackStore, contextual_help, error_info)


def test_error_catalog_has_stable_codes():
    assert error_info("KEEL-E001")["title"]
    assert "Fix:" in contextual_help("KEEL-E003")
    assert error_info("UNKNOWN")["title"] == "Unknown error"


def test_feedback_local_and_export(tmp_path):
    store = FeedbackStore(tmp_path)
    store.add("idea", "Add dark mode")
    target = store.export_redacted(tmp_path / "feedback.json")
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["format"] == "keel-feedback-v1"
    assert doc["entries"][0]["message"] == "Add dark mode"
