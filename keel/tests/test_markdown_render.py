"""B4.5 — rich rendering detection and safe HTML scaffold."""

from __future__ import annotations

from keel.markdown_render import (detect_blocks, is_image, is_pdf,
                                  render_preview)


def test_detect_fenced_blocks():
    text = "intro\n```mermaid\ngraph TD; A-->B;\n```\n```python\nprint(1)\n```"
    blocks = detect_blocks(text)
    assert any(b.kind == "mermaid" for b in blocks)
    assert any(b.kind == "code" and b.meta == "python" for b in blocks)


def test_detect_latex_and_images():
    blocks = detect_blocks("E = mc^2 inline and $$x^2$$ and ![alt](a.png)")
    assert any(b.kind == "latex" for b in blocks)
    assert any(b.kind == "image" and b.content == "a.png" for b in blocks)


def test_render_escapes_html():
    out = render_preview("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "copy-block" in out


def test_file_type_helpers():
    assert is_pdf("report.PDF")
    assert is_image("shot.png") and not is_image("doc.pdf")
