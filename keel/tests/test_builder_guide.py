"""A1.22 — internal AGENTS.md for builder agents."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "AGENTS.md"


def test_builder_guide_exists_with_required_sections():
    text = GUIDE.read_text(encoding="utf-8")
    assert "# AGENTS.md" in text
    assert "## Layout" in text
    assert "## Commands" in text
    assert "## Conventions" in text
    assert "python -m pytest -q" in text
    assert "Never push" in text


def test_guide_is_discoverable_by_instruction_scanner():
    from keel.instructions import discover

    paths = discover(ROOT)
    assert any(path.name == "AGENTS.md" for path in paths)
