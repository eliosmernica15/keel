"""Static QA checks for the KEEL public site. Run from the worktree root."""
from __future__ import annotations

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


for js in sorted((SITE / "ui").glob("*.js")):
    proc = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    check(proc.returncode == 0, f"JS syntax error in {js.name}: {proc.stderr.strip()}")

landing = read(SITE / "index.html")
required = [
    "Question what", "Your thinking partner for big ambitions",
    "Continue with Google", "Continue with email", "Download desktop app",
    "Explore plans", "Individual", "Team &amp; Enterprise", "Try Keel", "FAQ",
    "How can we help today", "Product", "Developers", "Enterprise",
    "Resources", "Pricing", "Contact sales",
]
for needle in required:
    check(needle.lower() in landing.lower(), f"landing missing: {needle!r}")
for needle in ["Free", "Pro", "Max", "Ultra", "$0", "$17", "$100", "$200"]:
    check(needle in landing, f"landing missing price/tier: {needle!r}")
for needle in [
    "What is Keel and how does it work?", "What should I use Keel for?",
    "How much does it cost to use?",
]:
    check(needle.lower() in landing.lower(), f"FAQ missing: {needle!r}")

dl = read(SITE / "download.html")
for needle in ["Build with", "For developers", "Use Cases", "Industries",
               "Insights", "Learn", "Connect", "Download Keel"]:
    check(needle.lower() in dl.lower(), f"download page missing: {needle!r}")

routes = {
    "/", "/app", "/app.html", "/download", "/download.html", "/download.json",
    "/privacy", "/terms", "/notices", "/roadmap", "/eula", "/trademark",
    "/requirements", "/login", "/new", "/plugins", "/projects", "/artifacts",
    "/sitemap.xml", "/robots.txt", "/manifest.webmanifest",
    "/sw.js", "/api/download-manifest",
}
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
            notes.append(f"unresolved href {href!r} in {html.name}")

for html in sorted(SITE.glob("*.html")):
    text = read(html)
    for brand in ("Claude", "Anthropic"):
        matches = re.findall(rf"\b{brand}\b", text, re.IGNORECASE)
        if matches:
            fail(f"unrebranded {brand!r} x{len(matches)} in {html.name}")

login = read(SITE / "login.html")
for needle in ["Question what", "Continue with Google", "Continue with Apple",
               "Enter your email", "Continue with email", "Explore plans",
               "Max and Ultra", "Frequently asked questions"]:
    check(needle.lower() in login.lower(), f"login page missing: {needle!r}")

new = read(SITE / "new.html")
for needle in ["You're here", "New", "Search", "Projects", "Artifacts", "Plugins",
               "Keel harness build plan", "Recent artifacts", "Elios"]:
    check(needle.lower() in new.lower(), f"new page missing: {needle!r}")

pl = read(SITE / "plugins.html")
for needle in ["Plugins", "Your plugins", "Most used", "Popular workflows",
               "Trending", "Categories", "Google Drive", "Add"]:
    check(needle.lower() in pl.lower(), f"plugins page missing: {needle!r}")
pr = read(SITE / "projects.html")
for needle in ["Projects", "Looking to start a project?", "New project",
               "Upload materials"]:
    check(needle.lower() in pr.lower(), f"projects page missing: {needle!r}")
ar = read(SITE / "artifacts.html") + read(SITE / "ui" / "artifacts.js")
for needle in ["Artifacts", "Make something new", "Docs", "Slides", "Design",
               "GPT-6.2 vs Fable 5.2 Prompts"]:
    check(needle.lower() in ar.lower(), f"artifacts page missing: {needle!r}")

vercel = read(SITE / "vercel.json")
check('{ "source": "/login", "destination": "/login.html" }' in vercel,
      "vercel.json does not route /login")
check('{ "source": "/new", "destination": "/new.html" }' in vercel,
      "vercel.json does not route /new")
check('{ "source": "/plugins", "destination": "/plugins.html" }' in vercel,
      "vercel.json does not route /plugins")
check('{ "source": "/projects", "destination": "/projects.html" }' in vercel,
      "vercel.json does not route /projects")
check('{ "source": "/artifacts", "destination": "/artifacts.html" }' in vercel,
      "vercel.json does not route /artifacts")
check('{ "source": "/app", "destination": "/app.html" }' in vercel,
      "vercel.json does not route /app to the app")
check('{ "source": "/app", "destination": "/download"' not in vercel,
      "vercel.json still redirects /app to /download")

dljs = read(SITE / "ui" / "download-clone.js")
check("sha256" in dljs or "download.json" in dljs,
      "download-clone.js lost the verified manifest rule")

app = read(SITE / "app.html")
check("/ui/style.css" in app, "app.html no longer links Keel's style.css")
check("starburst" in app, "app.html lost the Keel starburst symbol")

if notes:
    print("NOTES:")
    for n in notes[:30]:
        print("  -", n)

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("ALL STATIC CHECKS PASSED")
