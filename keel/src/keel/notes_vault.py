"""C1.8 — Notes vault extras: backlinks, graph view, daily notes, templates.

A local Markdown vault with ``[[wiki links]]`` and ``#tags``. It computes real
backlinks (including links to notes that don't exist yet), a navigable graph
with an offline SVG, tag indexes, orphan detection, dated daily notes and
template rendering. No hosted service or account is required. The earlier
``content_skills.backlinks`` only handled a plain in-memory dict.
"""

from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path

from . import charts

_LINK = re.compile(r"\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]")
_TAG = re.compile(r"(?<![\w/])#([A-Za-z][A-Za-z0-9_/-]*)")
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,80}")

TEMPLATES = {
    "daily": ("# {{date}}\n\n## Today\n\n- \n\n## Notes\n\n"
              "Tags: #daily\n"),
    "meeting": ("# {{title}}\n\nDate: {{date}}\n\n"
                "## Attendees\n\n- \n\n## Agenda\n\n- \n\n## Decisions\n\n- \n"),
    "project": ("# {{title}}\n\nStatus: active\nCreated: {{date}}\n\n"
                "## Goals\n\n- \n\n## Links\n\n- [[]]\n"),
}


def render_template(template: str, *, title: str = "",
                    day: str | None = None) -> str:
    day = day or _date.today().isoformat()
    return (template.replace("{{title}}", title)
            .replace("{{date}}", day)
            .replace("{{today}}", day))


class Vault:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not _NAME.fullmatch(name):
            raise ValueError("invalid note name")
        return self.root / f"{name}.md"

    def notes(self) -> dict[str, str]:
        return {p.stem: p.read_text(encoding="utf-8", errors="replace")
                for p in sorted(self.root.glob("*.md"))}

    def write(self, name: str, text: str) -> Path:
        path = self._path(name)
        path.write_text(text, encoding="utf-8")
        return path

    def links(self) -> dict[str, list[str]]:
        """Map each note to the note names it links to (deduplicated)."""
        out = {}
        for name, text in self.notes().items():
            seen = []
            for match in _LINK.finditer(text):
                target = match.group(1).strip()
                if target and target not in seen:
                    seen.append(target)
            out[name] = seen
        return out

    def backlinks(self) -> dict:
        graph = self.links()
        existing = set(self.notes())
        back: dict[str, list[str]] = {}
        for source, targets in graph.items():
            for target in targets:
                back.setdefault(target, []).append(source)
        return {
            "backlinks": back,
            "missing": sorted(t for t in back if t not in existing),
        }

    def tags(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for name, text in self.notes().items():
            for tag in dict.fromkeys(m.group(1) for m in _TAG.finditer(text)):
                result.setdefault(tag, []).append(name)
        return {tag: names for tag, names in sorted(result.items())}

    def orphans(self) -> list[str]:
        graph = self.links()
        back = self.backlinks()["backlinks"]
        return sorted(
            name for name in self.notes()
            if not graph.get(name) and not back.get(name))

    def graph(self) -> dict:
        """Return nodes/edges plus an offline SVG for the vault graph."""
        existing = set(self.notes())
        back = self.backlinks()
        nodes = sorted(existing | set(back["backlinks"]))
        edges = []
        for source, targets in self.links().items():
            for target in targets:
                edges.append((source, target))
        return {
            "nodes": [{"id": n, "exists": n in existing} for n in nodes],
            "edges": [{"source": s, "target": t} for s, t in edges],
            "svg": charts.flow_diagram(nodes, edges, width=460),
        }

    def daily(self, day: str | None = None, *, template: str = "daily",
              create: bool = True) -> dict:
        day = day or _date.today().isoformat()
        if not _NAME.fullmatch(day):
            raise ValueError("invalid date")
        path = self._path(day)
        existed = path.is_file()
        if not existed and create:
            body = render_template(TEMPLATES.get(template, TEMPLATES["daily"]),
                                   title=day, day=day)
            path.write_text(body, encoding="utf-8")
        return {"name": day, "path": str(path), "created": not existed,
                "content": path.read_text(encoding="utf-8") if path.is_file() else ""}

    def apply_template(self, name: str, template: str, *, title: str = "",
                       day: str | None = None) -> Path:
        body = render_template(TEMPLATES.get(template, template),
                               title=title or name, day=day)
        return self.write(name, body)
