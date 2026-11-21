"""Rich rendering primitives for the UI (B4.5).

Provides detection and safe scaffolding for Markdown, Mermaid, LaTeX and
image/PDF previews, with an explicit HTML-escaping step so agent output can
never inject markup. Actual visual rendering happens in the browser.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_FENCE = re.compile(r"```([a-zA-Z0-9+-]*)\n(.*?)```", re.S)
_INLINE_MATH = re.compile(r"\$([^$\n]+)\$")
_BLOCK_MATH = re.compile(r"\$\$(.+?)\$\$", re.S)
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass
class RichBlock:
    kind: str          # text | code | mermaid | latex | image
    content: str
    meta: str = ""


def detect_blocks(text: str) -> list[RichBlock]:
    blocks: list[RichBlock] = []
    pos = 0
    for match in _FENCE.finditer(text):
        if match.start() > pos:
            blocks.extend(_detect_inline(text[pos:match.start()]))
        lang = match.group(1).lower()
        body = match.group(2)
        if lang == "mermaid":
            blocks.append(RichBlock("mermaid", body, lang))
        elif lang in ("latex", "tex", "math"):
            blocks.append(RichBlock("latex", body, lang))
        else:
            blocks.append(RichBlock("code", body, lang))
        pos = match.end()
    if pos < len(text):
        blocks.extend(_detect_inline(text[pos:]))
    return blocks


def _detect_inline(text: str) -> list[RichBlock]:
    blocks: list[RichBlock] = []
    for m in _BLOCK_MATH.finditer(text):
        blocks.append(RichBlock("latex", m.group(1), "block"))
    for m in _INLINE_MATH.finditer(text):
        blocks.append(RichBlock("latex", m.group(1), "inline"))
    for m in _IMAGE.finditer(text):
        blocks.append(RichBlock("image", m.group(2), m.group(1)))
    if not blocks and text.strip():
        blocks.append(RichBlock("text", text))
    return blocks


def render_preview(text: str) -> str:
    """Return escaped HTML scaffold with copy buttons for rich blocks."""
    parts = []
    for block in detect_blocks(text):
        escaped = html.escape(block.content)
        parts.append(
            f'<div class="rich-block rich-{html.escape(block.kind)}" '
            f'data-lang="{html.escape(block.meta)}">'
            f'<button type="button" class="copy-block">copy</button>'
            f'<pre>{escaped}</pre></div>')
    return "\n".join(parts)


def is_pdf(name: str) -> bool:
    return name.lower().endswith(".pdf")


def is_image(name: str) -> bool:
    return name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))
