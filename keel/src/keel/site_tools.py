"""Static site helpers (B5.x, B4.2): offline docs index, status page, deep links."""

from __future__ import annotations

import json
import re
from pathlib import Path


def build_docs_index(root: str | Path) -> dict:
    """Build a simple static search index over markdown/html docs."""
    root = Path(root)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in (".md", ".html") or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        words = set(re.findall(r"[a-zA-Z0-9_-]{3,}", text.lower()))
        entries.append({"path": str(path.relative_to(root)),
                        "words": sorted(words)[:200]})
    return {"format": "keel-docs-index-v1", "entries": entries}


def status_page(feeds_ok: bool, mirrors_ok: bool) -> dict:
    return {"update_feed": "operational" if feeds_ok else "degraded",
            "mirrors": "operational" if mirrors_ok else "degraded",
            "note": "static status derived from local checks"}


def parse_deep_link(url: str) -> dict | None:
    """Parse keel://open?path=... style deep links."""
    if not url.startswith("keel://"):
        return None
    body = url[len("keel://"):]
    action, _, query = body.partition("?")
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            params[key] = value
    return {"action": action, "params": params}
