"""The public website must be download-only, not a source/browser-mirror portal."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

FORBIDDEN_TEXT = (
    "github.com",
    "/app",
    "live mirror",
    "web mirror",
    "git clone",
    "docs/HOSTING.md",
    "licensing-and-provenance-review.md",
    "agent-evidence",
    "claude-code-evidence",
    "prompt-pattern-analysis",
    "FINAL-APPROVAL-GATE",
)


def _public_text_files() -> list[Path]:
    return sorted(
        p for p in SITE.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {".html", ".js", ".json", ".xml", ".txt", ".css"}
        and "node_modules" not in p.parts
    )


def test_landing_page_has_no_source_or_mirror_journey():
    text = (SITE / "index.html").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in FORBIDDEN_TEXT:
        assert needle.lower() not in lowered, f"index.html still contains {needle!r}"
    assert 'href="/download"' in text
    assert 'href="/download.json"' in text


def test_no_public_site_file_links_to_github_or_internal_docs():
    for path in _public_text_files():
        lowered = path.read_text(encoding="utf-8", errors="replace").lower()
        assert "github.com" not in lowered, f"github link in {path}"
        for needle in (
            "licensing-and-provenance-review.md",
            "agent-evidence",
            "claude-code-evidence",
            "prompt-pattern-analysis",
            "final-approval-gate",
            "implementation-plan.md",
            "security-plan.md",
        ):
            assert needle not in lowered, f"{needle} in {path}"


def test_browser_mirror_is_not_publicly_routable():
    vercel = json.loads((SITE / "vercel.json").read_text(encoding="utf-8"))
    rewrites = vercel.get("rewrites", [])
    assert not any(r.get("destination", "").startswith("/app") for r in rewrites)
    redirects = vercel.get("redirects", [])
    app_redirects = [r for r in redirects if r.get("source") in {"/app", "/app.html"}]
    assert len(app_redirects) == 2
    assert all(r.get("destination") == "/download" for r in app_redirects)

    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "/app" not in sitemap
    robots = (SITE / "robots.txt").read_text(encoding="utf-8")
    assert "Disallow: /app" in robots
    assert "Disallow: /app.html" in robots


def test_download_manifest_proxy_requires_first_party_configuration():
    source = (SITE / "api" / "download-manifest.js").read_text(encoding="utf-8")
    assert "github.com" not in source.lower()
    assert "KEEL_DOWNLOAD_MANIFEST_URL" in source
    assert "manifest_not_configured" in source


def test_download_manifest_is_sanitized():
    text = (SITE / "download.json").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in ("github", "r2", "ci run", "docs/hosting", "44527352992"):
        assert needle not in lowered, f"download.json still contains {needle!r}"
    doc = json.loads(text)
    assert doc["version"] == "0.1.1"
    assert all(not ch["url"] and not ch["available"] for ch in doc["channels"].values())


def test_desktop_bridge_renderer_is_preserved():
    """site/app.html is the packaged Electron UI; it must not be deleted."""
    app = (SITE / "app.html").read_text(encoding="utf-8")
    assert '<script src="/ui/app.js">' in app
    assert 'id="settings-panel"' in app
    assert "github.com" not in app.lower()
    renderer = (SITE / "ui" / "app.js").read_text(encoding="utf-8")
    assert "git clone" not in renderer.lower()
    assert "REPO" not in renderer
