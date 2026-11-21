"""Release feeds and version history (B5.2).

Generates ``latest.json``, a JSON version history and an RSS feed from local
release notes. No publishing or network access happens here.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

VERSIONS = ("0.1.1", "0.1.0")

HISTORY = [
    {"version": "0.1.1", "date": "2026-11-21",
     "notes": "Installer targets for Windows, macOS (Intel/Apple Silicon) and "
              "Linux RPM; Ed25519 signed artifacts; encrypted secret storage; "
              "full hook lifecycle coverage."},
    {"version": "0.1.0", "date": "2026-11-01",
     "notes": "Initial local-first agent runtime with the web bridge, Fleet "
              "multi-agent environment and offline provider catalog."},
]


def latest_json(base_url: str = "") -> dict:
    return {
        "version": VERSIONS[0],
        "tag": f"v{VERSIONS[0]}",
        "published_at": HISTORY[0]["date"],
        "base_url": base_url or None,
        "channels": ["windows", "macos", "linux"],
        "notes": HISTORY[0]["notes"],
    }


def version_history() -> dict:
    return {"versions": HISTORY}


def rss_feed(site_url: str = "http://localhost/") -> str:
    site = site_url.rstrip("/")
    items = []
    for entry in HISTORY:
        title = html.escape(f"Keel {entry['version']}")
        description = html.escape(entry["notes"])
        items.append(
            "    <item>\n"
            f"      <title>{title}</title>\n"
            f"      <link>{site}/download</link>\n"
            f"      <guid>keel-{entry['version']}</guid>\n"
            f"      <pubDate>{entry['date']}</pubDate>\n"
            f"      <description>{description}</description>\n"
            "    </item>")
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<rss version=\"2.0\"><channel>\n"
            "  <title>Keel releases</title>\n"
            f"  <link>{site}/download</link>\n"
            "  <description>Local-first AI workspace release notes.</description>\n"
            + "\n".join(items) + "\n</channel></rss>\n")


def write_feeds(directory: str | Path, *, site_url: str = "") -> list[Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    paths = [
        root / "latest.json",
        root / "version-history.json",
        root / "releases.xml",
    ]
    paths[0].write_text(
        json.dumps(latest_json(site_url), indent=2) + "\n", encoding="utf-8")
    paths[1].write_text(
        json.dumps(version_history(), indent=2) + "\n", encoding="utf-8")
    paths[2].write_text(rss_feed(site_url or "http://localhost/"),
                        encoding="utf-8")
    return paths
