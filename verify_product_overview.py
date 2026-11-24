#!/usr/bin/env python3
"""Independent QA gate for the KEEL /product/overview replica.

Checks structure, branding, link integrity, asset references, JS syntax and
Vercel routing. Uses only the Python standard library.

    python verify_product_overview.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "keel" / "site"
PAGE = SITE / "product-overview.html"
CSS = SITE / "ui" / "product-overview.css"
JS = SITE / "ui" / "product-overview.js"
VERCEL = SITE / "vercel.json"

KNOWN_ROUTES = {
    "/", "/download", "/app", "/product/overview", "/product-overview.html",
    "/product/keel-code", "/product/keel-duet", "/keel-in-chrome", "/chrome-web-store",
    "/privacy", "/terms", "/notices", "/roadmap", "/eula", "/trademark",
    "/requirements", "/download.json", "/manifest.webmanifest", "/sw.js",
    "/sitemap.xml", "/robots.txt", "/assets/img/keel-app.jpg",
}

REQUIRED_TOKENS = [
    "po-site-header", "po-main-nav", "po-mega", "po-mobile-menu", "po-hero-title",
    "po-hero-actions", "po-value-grid", "po-work", "po-persona-tab",
    "po-chat-card", "po-output-card", "po-testimonial", "po-change",
    "po-capabilities", "po-cap-search", "po-cap-tab", "po-hub", "po-hub-node",
    "po-usecase", "po-role", "po-task", "po-faq-q", "po-faq-a", "po-cta",
    "po-ask-form", "po-footer", "po-footer-link", "po-modal", "po-toast",
]

REQUIRED_IDS = [
    "po-header", "po-mobile-menu", "po-cap-search", "po-cap-empty", "po-hub",
    "po-cap-detail", "po-usecase-heading", "po-usecase-stage", "po-ask-form",
    "po-ask-input", "po-ask-result", "po-footer-search", "po-footer-search-result",
    "po-auth-modal", "po-auth-form", "po-auth-email", "po-toast",
]


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.classes: set[str] = set()
        self.hrefs: list[str] = []
        self.srcs: list[str] = []
        self.script_srcs: list[str] = []
        self.link_hrefs: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        d = {k.lower(): (v or "") for k, v in attrs}
        if d.get("id"):
            self.ids.add(d["id"])
        for c in d.get("class", "").split():
            if c:
                self.classes.add(c)
        if d.get("href"):
            self.hrefs.append(d["href"])
        if d.get("src"):
            self.srcs.append(d["src"])
        if tag == "script" and d.get("src"):
            self.script_srcs.append(d["src"])
        if tag == "link" and d.get("href"):
            self.link_hrefs.append(d["href"])


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors, warnings, passed = [], [], []

    missing = [p for p in (PAGE, CSS, JS, VERCEL) if not p.exists()]
    if missing:
        for e in ("Missing files: " + ", ".join(str(p.relative_to(ROOT)) for p in missing),):
            print("FAIL:", e)
        return 1
    passed.append("all four primary files present")

    html, css, js = read(PAGE), read(CSS), read(JS)

    for label, text in (("HTML", html), ("CSS", css), ("JS", js)):
        for brand in ("Claude", "Anthropic", "claude", "anthropic"):
            if brand in text:
                errors.append(f"{label} contains forbidden brand string '{brand}'")
    if not any("laude" in e or "nthropic" in e for e in errors):
        passed.append("brand purity (no Claude/Anthropic strings)")

    c = Collector()
    c.feed(html)
    missing_classes = [t for t in REQUIRED_TOKENS if t not in c.classes]
    (errors if missing_classes else passed).append(
        "missing required classes: " + ", ".join(missing_classes) if missing_classes
        else f"all {len(REQUIRED_TOKENS)} required classes present"
    )
    missing_ids = [i for i in REQUIRED_IDS if i not in c.ids]
    (errors if missing_ids else passed).append(
        "missing required IDs: " + ", ".join(missing_ids) if missing_ids
        else f"all {len(REQUIRED_IDS)} required IDs present"
    )
    for token in ("/ui/product-overview.css", "/ui/product-overview.js"):
        if token not in html:
            errors.append(f"page does not reference {token}")

    dead = [h for h in c.hrefs if h.strip() in ("#", "", "javascript:void(0)")]
    (errors if dead else passed).append(
        f"dead hrefs found: {dead[:10]}" if dead else "no dead href=\"#\" links"
    )
    anchors = {h[1:] for h in c.hrefs if h.startswith("#") and len(h) > 1}
    unresolved = sorted(a for a in anchors if a not in c.ids)
    (errors if unresolved else passed).append(
        "unresolved same-page anchors: " + ", ".join(unresolved) if unresolved
        else f"all {len(anchors)} same-page anchors resolve"
    )

    local_refs = [h for h in c.hrefs + c.srcs + c.link_hrefs + c.script_srcs
                  if h.startswith("/") and not h.startswith("//")]
    bad_refs = []
    for ref in sorted(set(local_refs)):
        path_part = ref.split("#", 1)[0].split("?", 1)[0]
        if path_part in KNOWN_ROUTES:
            continue
        if not (SITE / path_part.lstrip("/")).exists():
            bad_refs.append(ref)
    (errors if bad_refs else passed).append(
        "broken local refs: " + ", ".join(bad_refs[:20]) if bad_refs
        else f"all {len(set(local_refs))} local refs resolve"
    )

    try:
        result = subprocess.run(["node", "--check", str(JS)], capture_output=True,
                                text=True, timeout=60)
        (passed if result.returncode == 0 else errors).append(
            "node --check ui/product-overview.js passed" if result.returncode == 0
            else "node --check failed: " + (result.stderr or result.stdout)[:800]
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        warnings.append(f"could not run node --check: {exc}")

    try:
        cfg = json.loads(read(VERCEL))
        hit = any(r.get("source") == "/product/overview" and
                  r.get("destination") == "/product-overview.html"
                  for r in cfg.get("rewrites", []))
        (passed if hit else errors).append(
            "Vercel rewrite /product/overview present" if hit
            else "Vercel rewrite for /product/overview missing"
        )
    except json.JSONDecodeError as exc:
        errors.append(f"vercel.json invalid JSON: {exc}")

    hooks = {
        "mega dropdown aria": 'aria-expanded' in html and 'po-nav-trigger' in html,
        "persona tabs wired": 'data-persona' in html and 'data-persona' in js,
        "capability tabs wired": 'data-cap-tab' in html and 'data-cap-tab' in js,
        "use-case role/task wired": 'data-role' in html and 'data-task' in html,
        "FAQ accordion aria": 'aria-controls' in html and 'po-faq-q' in js,
        "auth localStorage": 'keel_logged_in' in js,
        "no network calls in JS": not re.search(r"\b(fetch|XMLHttpRequest|WebSocket)\s*\(", js),
    }
    for name, ok in hooks.items():
        (passed if ok else errors).append(name if ok else f"failed hook check: {name}")

    print("=" * 68)
    print("KEEL /product/overview QA gate")
    print("=" * 68)
    for p in passed:
        print("PASS:", p)
    for w in warnings:
        print("WARN:", w)
    for e in errors:
        print("FAIL:", e)
    print("-" * 68)
    print(f"{len(passed)} passed, {len(warnings)} warned, {len(errors)} failed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
