"""B5.3 — system requirements, model-size guide and first-run guide."""

from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "site" / "requirements.html"


def test_requirements_page_covers_all_platforms():
    text = PAGE.read_text(encoding="utf-8")
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in text


def test_model_size_guide_and_first_run():
    text = PAGE.read_text(encoding="utf-8")
    assert "model size" in text.lower()
    assert "first run" in text.lower()
    assert "SHA-256" in text
    assert "Gatekeeper" in text
