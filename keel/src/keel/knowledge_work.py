"""Knowledge-work tool descriptors (B2.x): HTTP tester, diagrams, OCR, macros."""

from __future__ import annotations

import json
import re
from pathlib import Path


def http_request_spec(method: str, url: str, *, body: str = "",
                      headers: dict | None = None) -> dict:
    return {"method": method.upper(), "url": url, "body": body,
            "headers": dict(headers or {}), "approval_required": True}


def mermaid_to_svg_stub(source: str) -> dict:
    """Describe a Mermaid diagram for offline rendering by the UI."""
    nodes = re.findall(r"\b([A-Za-z]\w*)\s*\[", source)
    return {"format": "mermaid", "nodes": sorted(set(nodes)),
            "source": source[:4000]}


def ocr_descriptor(path: str, *, engine: str = "tesseract") -> dict:
    return {"file": path, "engine": engine,
            "note": "Requires user-installed OCR engine; output is local."}


class MacroRecorder:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "macros.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def record(self, name: str, steps: list[dict]) -> dict:
        doc = self._load()
        entry = {"name": name, "steps": list(steps)[:100]}
        doc[name] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return entry


TEMPLATE_GALLERY = {
    "code-review": "Review this change for bugs and style. Cite file:line.",
    "weekly-report": "Summarise this week's work into bullets.",
    "bug-report": "Describe the bug, steps to reproduce, expected vs actual.",
}


def template(name: str) -> str:
    return TEMPLATE_GALLERY.get(name, "")
