"""Static QA checks for the KEEL public site. Run from the workspace root."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "keel" / "site"

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# 1. JS syntax
for js in sorted((SITE / "ui").glob("*.js")):
    proc = subprocess.run(
        ["node", "--check", str(js)], capture_output=True, text=True
    )
    check(proc.returncode == 0, f"JS syntax error in {js.name}: {proc.stderr.strip()}")

# 2. Required content on the landing page
landing = read(SITE / "index.html")
required = [
    "Question what",
    "Your thinking partner for big ambitions",
    "Continue with Google",
    "Continue with email",
    "Download desktop app",
    "Explore plans",
    "Individual",
    "Team &amp; Enterprise",
    "Try Keel",
    "FAQ",
    "How can we help today",
    "Product",
    "Developers",
    "Enterprise",
    "Resources",
    "Pricing",
    "Contact sales",
]
for needle in required:
    check(needle.lower() in landing.lower(), f"landing missing required content: {needle!r}")

# 3. Pricing tiers and prices
for needle in ["Free", "Pro", "Max", "Ultra", "$0", "$17", "$100", "$200"]:
    check(needle in landing, f"landing missing price/tier: {needle!r}")

# 4. FAQ questions
for needle in [
    "What is Keel and how does it work?",
    "What should I use Keel for?",
    "How much does it cost to use?",
]:
    check(needle.lower() in landing.lower(), f"FAQ question missing: {needle!r}")

# 5. Download page nav dropdowns
dl = read(SITE / "download.html")
for needle in [
    "Build with",
    "For developers",
    "Use Cases",
    "Industries",
    "Insights",
    "Learn",
    "Connect",
    "Overview",
    "API",
    "Download Keel",
]:
    check(needle.lower() in dl.lower(), f"download page missing: {needle!r}")

# 5b. Keel-in-Chrome + Chrome Web Store replica pages
chrome_page = SITE / "keel-in-chrome.html"
store_page = SITE / "chrome-web-store.html"
check(chrome_page.exists(), "missing keel-in-chrome.html")
check(store_page.exists(), "missing chrome-web-store.html")
if chrome_page.exists():
    text = read(chrome_page)
    for needle in [
        "A helping hand across all your tabs",
        "A refreshing way to work on the web",
        "Speed up everyday tasks with Keel in Chrome",
        "Core capabilities",
        "Stay in control",
        "FAQ",
        "Start on the page you're already on",
    ]:
        check(needle.lower() in text.lower(), f"keel-in-chrome page missing: {needle!r}")
if store_page.exists():
    text = read(store_page)
    for needle in ["Add to KEEL", "24,000,000 users", "Search extensions and themes"]:
        check(needle.lower() in text.lower(), f"chrome-web-store page missing: {needle!r}")

# 6. No dead links in HTML
routes = {
    "/", "/app", "/app.html", "/download", "/download.html", "/download.json",
    "/keel-in-chrome", "/chrome-web-store",
    "/privacy", "/terms", "/notices", "/roadmap", "/eula", "/trademark",
    "/requirements", "/sitemap.xml", "/robots.txt", "/manifest.webmanifest",
    "/sw.js", "/api/download-manifest",
}
assets = {"stylesheets": [], "scripts": []}
for html in sorted(SITE.glob("*.html")):
    text = read(html)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text)
    ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', text))
    for href in hrefs:
        if href == "#":
            fail(f"dead href='#' in {html.name}")
        elif href.startswith("#"):
            check(href[1:] in ids, f"missing anchor {href} in {html.name}")
        elif href.startswith(("/", "./", "../")):
            path = href.split("#", 1)[0].split("?", 1)[0]
            if path in routes:
                continue
            target = (SITE / path.lstrip("./")).resolve()
            check(target.exists(), f"missing local target {href} in {html.name}")
        elif href.startswith(("http://", "https://", "mailto:", "tel:")):
            pass
        else:
            # external/relative link we cannot resolve; flag for review
            notes.append(f"unresolved href {href!r} in {html.name}")

# 7. Branding: no "Claude" or "Anthropic" left in the public surfaces
for html in sorted(SITE.glob("*.html")):
    text = read(html)
    for brand in ("Claude", "Anthropic"):
        matches = re.findall(rf"\b{brand}\b", text, re.IGNORECASE)
        if matches:
            fail(f"unrebranded {brand!r} x{len(matches)} in {html.name}")

# 8. /app must be reachable (not redirected away)
vercel = read(SITE / "vercel.json")
check('"/app"' in vercel and "destination" in vercel, "vercel.json lacks /app route")
check('{ "source": "/app", "destination": "/download"' not in vercel,
      "vercel.json still redirects /app to /download")

# 9. Download manifest rule preserved
dljs = read(SITE / "ui" / "download-clone.js")
check("sha256" in dljs or "download.json" in dljs,
      "download-clone.js no longer references the verified manifest rule")

# 10. App surface still uses Keel's own design
app = read(SITE / "app.html")
check("/ui/style.css" in app, "app.html no longer links Keel's style.css")
check("starburst" in app, "app.html lost the Keel starburst symbol")

if notes:
    print("NOTES (review, not failures):")
    for n in notes[:30]:
        print("  -", n)
    if len(notes) > 30:
        print(f"  ... and {len(notes) - 30} more")

if failures:
    print(f"\nFAILED ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)

print("ALL STATIC CHECKS PASSED")
