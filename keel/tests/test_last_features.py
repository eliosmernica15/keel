"""Final 6 roadmap features."""

from __future__ import annotations

from keel.last_features import (headless_ops_doc, image_generation,
                                integration_guides, local_task_executor,
                                screenshot_gallery, site_tools)


def test_ops_doc_and_site_tools():
    doc = headless_ops_doc()
    assert "KEEL_TOKEN" in doc and "127.0.0.1" in doc
    tools = site_tools()
    assert tools["secrets_manager"] is True and tools["analytics"] is False


def test_image_and_gallery():
    assert image_generation()["enabled"] is False
    assert screenshot_gallery()["source"] == "e2e-runs"


def test_executor_and_guides():
    assert local_task_executor()["approval_required"] is True
    assert "imap" in integration_guides()
