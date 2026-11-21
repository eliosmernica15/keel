"""Minimal terminal UI renderer (A1.3).

Renders transcript events as plain text for a TUI front-end. Keel's Python
runtime stays authoritative; the TUI is one more view over the same events,
usable when no browser is available.
"""

from __future__ import annotations

from typing import Iterable


def render_events(events: Iterable[dict], *, width: int = 80) -> str:
    lines = []
    for event in events:
        kind = event.get("type")
        subtype = event.get("subtype", "")
        if kind == "user":
            content = event.get("message", {}).get("content", "")
            lines.append(f"> {_flatten(content)[:width]}")
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    lines.append(block.get("text", "")[:width])
                elif block.get("type") == "tool_use":
                    lines.append(f"[tool {block.get('name', '?')}]")
        elif kind == "result":
            lines.append(f"--- {subtype} ---")
        elif subtype == "informational":
            lines.append(f"* {event.get('content', '')[:width]}")
    return "\n".join(lines)


def _flatten(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", ""))
                        for part in content if isinstance(part, dict))
    return str(content)
