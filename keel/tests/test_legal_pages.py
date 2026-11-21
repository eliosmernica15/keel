"""B5.5 — privacy, EULA and third-party notices site pages."""

from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


def test_legal_pages_exist():
    for name in ("privacy.html", "eula.html", "notices.html"):
        assert (SITE / name).is_file(), name


def test_privacy_page_states_what_is_not_collected():
    text = (SITE / "privacy.html").read_text(encoding="utf-8")
    assert "does not collect" in text
    assert "telemetry" in text.lower()
    assert "egress" in text.lower()


def test_eula_page_is_draft_and_mentions_version_acceptance():
    text = (SITE / "eula.html").read_text(encoding="utf-8")
    assert "draft" in text.lower()
    assert "version" in text.lower()
    assert "re-prompt" in text


def test_notices_page_lists_licenses():
    text = (SITE / "notices.html").read_text(encoding="utf-8")
    assert "MIT" in text and "Apache" in text
    assert "no reference product names" in text.lower() or "No reference" in text
