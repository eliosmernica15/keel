"""C1.3 — agent avatars, colors and voice previews."""

from __future__ import annotations

from keel.agent_style import style_for, synthesize_preview


def test_style_is_deterministic():
    assert style_for("sage") == style_for("sage")


def test_style_has_required_fields():
    style = style_for("writer")
    assert style["avatar"] and style["color"].startswith("#")
    assert style["voice"] and style["agent"] == "writer"


def test_preview_includes_sample():
    preview = synthesize_preview("scout")
    assert preview["sample_text"] == "Hello, this is scout."
    assert preview["avatar"] == style_for("scout")["avatar"]
