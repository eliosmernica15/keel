"""Agent avatars, colors, voices and voice previews (C1.3).

Provides a deterministic style assignment for agents (avatar glyph, accent
color, voice label) and a preview descriptor for the UI. No audio synthesis
happens here; the browser may preview a voice if it has one installed.
"""

from __future__ import annotations

import hashlib

AVATAR_GLYPHS = ("✦", "◆", "▲", "●", "■", "★", "⬢", "◇")
ACCENT_COLORS = ("#6fe3b0", "#7aa2f7", "#e0af68", "#f7768e",
                 "#bb9af7", "#9ece6a", "#ff9e64", "#73daca")
VOICES = ("system-default", "nova", "onyx", "alloy", "shimmer", "verse")


def style_for(agent_id: str) -> dict:
    digest = hashlib.sha256(str(agent_id).encode("utf-8")).digest()
    avatar = AVATAR_GLYPHS[digest[0] % len(AVATAR_GLYPHS)]
    color = ACCENT_COLORS[digest[1] % len(ACCENT_COLORS)]
    voice = VOICES[digest[2] % len(VOICES)]
    return {
        "agent": agent_id,
        "avatar": avatar,
        "color": color,
        "voice": voice,
        "preview": f"{avatar} {agent_id} · {voice}",
    }


def synthesize_preview(agent_id: str) -> dict:
    """Descriptor the UI can use to preview an agent's voice/avatar."""
    style = style_for(agent_id)
    style["sample_text"] = f"Hello, this is {agent_id}."
    return style
