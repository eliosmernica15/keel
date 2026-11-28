#!/usr/bin/env python3
"""Final QA for the Keel-in-Chrome single-page + real-extension delivery.

Run from anywhere:  python verify_keel_chrome.py

New reality (this script intentionally does NOT check the retired
/chrome-web-store replica page):
  * one marketing landing page, shipped both as keel-in-chrome.html and as a
    physical route index at keel-in-chrome/index.html;
  * real MV3 extension in keel/site/extension, packaged as keel-extension.zip;
  * "Add to Chrome" CTAs carry data-store-install and point at the configured
    Chrome Web Store URL token/URL, resolved by ui/chrome-install.js.

The script is read-only with respect to product files. It only writes
screenshots and Chrome/server logs under the QA shots directory.

Files that other agents may still be adding/removing (ui/chrome-install.js,
keel-in-chrome/index.html, store-assets/store-listing.md) are treated as
optional: if absent, the relevant check is recorded as SKIP with a note
instead of crashing. Core product failures are recorded as FAIL.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "keel" / "site"
EXT = SITE / "extension"
SHOTS = Path(r"C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

# The two physical copies of the single landing page.
LANDING_FILES = (SITE / "keel-in-chrome.html", SITE / "keel-in-chrome" / "index.html")
INSTALL_JS = SITE / "ui" / "chrome-install.js"
LANDING_JS = SITE / "ui" / "chrome-landing.js"
# Files belonging to the retired /chrome-web-store page, deleted by another agent.
OLD_PAGE_FILES = {
    "chrome-web-store.html",
    "chrome-web-store/index.html",
    "ui/chrome-web-store.css",
    "ui/chrome-web-store.js",
}
REVIEW_PAGES = {"keel-in-chrome.html", "keel-in-chrome/index.html"}

RESULTS: list[dict] = []


def record(check: str, ok: bool | None, details, status: str | None = None):
    st = status or ("PASS" if ok else "FAIL")
    RESULTS.append({"check": check, "status": st, "details": details})
    print(f"[{st}] {check}")
    if details:
        for line in str(details).splitlines():
            print("      " + line)


def skip(check: str, details):
    record(check, None, details, status="SKIP")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_opt(path: Path) -> str | None:
    """Read an optional file; return None (never raise) when it is missing."""
    try:
        return read(path)
    except OSError:
        return None


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(SITE)).replace("\\", "/")
    except ValueError:
        return str(path)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# --------------------------------------------------------------------------
# 1. node --check
# --------------------------------------------------------------------------
def check_js_syntax():
    # The retired /chrome-web-store replica (and its JS/CSS) is deliberately
    # out of scope; check 6 only verifies nothing still links to its route.
    js_files = [f for f in sorted((SITE / "ui").glob("*.js")) + sorted(EXT.glob("*.js"))
                if f.name != "chrome-web-store.js"]
    if not js_files:
        skip("1. node --check on all UI + extension JS", "no JS files found under keel/site")
        return
    new_names = {"chrome-landing.js", "chrome-install.js"}
    lines = []
    ok = True
    try:
        for f in js_files:
            p = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            good = p.returncode == 0
            ok &= good
            tag = "NEW" if f.name in new_names else "existing"
            lines.append(f"{tag:8} {f.name:24} {'OK' if good else 'SYNTAX ERROR'}")
            if not good:
                lines.append("        " + (p.stderr or p.stdout).strip().replace("\n", "\n        "))
    except FileNotFoundError:
        skip("1. node --check on all UI + extension JS", "node executable not available on PATH")
        return
    if INSTALL_JS not in js_files:
        lines.append("ui/chrome-install.js: NOT PRESENT YET (optional file, added by another agent)")
    record("1. node --check on all UI + extension JS", ok, "\n".join(lines))


# --------------------------------------------------------------------------
# 2. HTML static checks
# --------------------------------------------------------------------------
def attributes(tag: str) -> dict:
    out = {}
    for m in re.finditer(r'([A-Za-z_:][-\w:.]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', tag):
        val = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5))
        out[m.group(1).lower()] = val or ""
    # valueless (boolean) attributes, e.g. data-store-install, data-auth-open, hidden
    without_values = re.sub(r'[A-Za-z_:][-\w:.]*\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', " ", tag)
    for m in re.finditer(r'\b([A-Za-z_:][-\w:.]*)\b', without_values):
        out[m.group(1).lower()] = ""
    return out


def tags_of(text: str, name: str):
    for m in re.finditer(rf"<{name}\b([^>]*)>", text, re.I):
        yield m, attributes(m.group(0))


def collect_ids(text: str) -> set[str]:
    return {a["id"] for _m, a in tags_of(text, r"[A-Za-z][\w:-]*") if a.get("id")}


def html_files() -> list[Path]:
    candidates = (
        sorted(SITE.glob("*.html"))
        + sorted((SITE / "screenshots").glob("*.html"))
        + sorted((SITE / "keel-in-chrome").glob("index.html"))
    )
    seen, out = set(), []
    for f in candidates:
        if f.resolve() not in seen:
            seen.add(f.resolve())
            out.append(f)
    return out


def check_html_static():
    files = html_files()
    if not files:
        skip("2a. HTML no href='#', anchors resolve, branding, no inline script", "no HTML files found")
        skip("2b. same-origin paths resolve to a file or Vercel rewrite", "no HTML files found")
        return
    id_map = {rel(f): collect_ids(read(f)) for f in files}
    vercel = json.loads(read(SITE / "vercel.json"))
    rewrites = {r["source"] for r in vercel.get("rewrites", [])}
    redirects = {r["source"] for r in vercel.get("redirects", [])}

    empty_hrefs, bad_anchors, unresolved, inline_scripts, branding = [], [], [], [], []

    for f in files:
        text = read(f)
        r = rel(f)
        for m in re.finditer(r'href\s*=\s*(["\'])(.*?)\1', text, re.I):
            href = m.group(2).strip()
            if href == "#":
                empty_hrefs.append(f"{r}:{line_of(text, m.start())}")
            if href.startswith("#"):
                if href[1:] not in id_map.get(r, set()):
                    bad_anchors.append(f"{r}:{line_of(text, m.start())} -> {href} (no id in same file)")
            elif href.startswith("/#"):
                if href[2:] not in id_map.get("index.html", set()):
                    bad_anchors.append(f"{r}:{line_of(text, m.start())} -> {href} (no id in index.html)")
            elif "#" in href and not href.startswith(("http://", "https://", "//")):
                path, frag = href.split("#", 1)
                target_file = path.lstrip("/") or "index.html"
                if target_file.endswith(".html") and frag and (SITE / target_file).exists():
                    if frag not in id_map.get(target_file, set()):
                        bad_anchors.append(f"{r}:{line_of(text, m.start())} -> {href} (no id in {target_file})")
        for attr in ("href", "src"):
            for m in re.finditer(rf"{attr}\s*=\s*([\"'])(.*?)\1", text, re.I):
                val = m.group(2).strip()
                if not val.startswith("/") or val.startswith("//"):
                    continue
                path = val.split("#", 1)[0].split("?", 1)[0]
                if not path or path == "/":
                    continue
                if path in rewrites or path in redirects:
                    continue
                candidate = SITE / path.lstrip("/")
                if candidate.exists() or (SITE / (path.lstrip("/") + ".js")).exists():
                    continue
                if (candidate / "index.html").exists():
                    continue
                unresolved.append(
                    f"{r}:{line_of(text, m.start())} -> {val}"
                    + (" [LANDING]" if r in REVIEW_PAGES else "")
                )
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", text, re.I | re.S):
            tag_attrs = attributes(m.group(0)[: m.group(0).find(">") + 1])
            body = m.group(2).strip()
            script_type = tag_attrs.get("type", "").strip().lower()
            # application/ld+json etc. are inert data blocks, not executable scripts.
            if script_type and script_type not in ("text/javascript", "application/javascript", "module", "text/ecmascript"):
                continue
            if body and not tag_attrs.get("src"):
                inline_scripts.append(f"{r}:{line_of(text, m.start())}")
            elif body and tag_attrs.get("src"):
                inline_scripts.append(f"{r}:{line_of(text, m.start())} (src + inline body)")
        if r in REVIEW_PAGES:
            for m in re.finditer(r"(?i)claude|anthropic", text):
                branding.append(f"{r}:{line_of(text, m.start())}")

    def fmt(title, items, limit=30):
        if not items:
            return title + ": none"
        return title + f" ({len(items)}):\n  " + "\n  ".join(items[:limit]) + (
            f"\n  ... +{len(items)-limit} more" if len(items) > limit else ""
        )

    record(
        "2a. HTML no href='#', anchors resolve, branding, no inline script",
        not (empty_hrefs or bad_anchors or branding or inline_scripts),
        "\n".join(
            [
                fmt("empty href='#'", empty_hrefs),
                fmt("broken #anchors", bad_anchors),
                fmt("Claude/Anthropic in landing copies", branding),
                fmt("inline <script>", inline_scripts),
            ]
        ),
    )

    landing_unresolved = [u for u in unresolved if "[LANDING]" in u]
    other = [u for u in unresolved if "[LANDING]" not in u]
    record(
        "2b. same-origin paths resolve to a file or Vercel rewrite",
        not landing_unresolved,
        "unresolved on the landing copies:\n  "
        + ("\n  ".join(landing_unresolved) if landing_unresolved else "none")
        + "\nunresolved elsewhere (pre-existing / retired page): "
        + f"{len(other)} occurrences; expected to clear when /chrome-web-store assets are removed.",
    )


# --------------------------------------------------------------------------
# 3. /keel-in-chrome route: rewrite + sitemap + physical index + HTML parity
# --------------------------------------------------------------------------
def check_routes():
    vercel = json.loads(read(SITE / "vercel.json"))
    rewrites = {r["source"]: r["destination"] for r in vercel.get("rewrites", [])}
    sitemap = read(SITE / "sitemap.xml")
    lines = []
    ok = True

    rw = rewrites.get("/keel-in-chrome")
    rw_ok = rw in ("/keel-in-chrome.html", "/keel-in-chrome/index.html")
    ok &= rw_ok
    lines.append(f"/keel-in-chrewrite: {rw!r} ({'OK' if rw_ok else 'MISSING/WRONG'})")

    sm_ok = "https://keel-desktop.vercel.app/keel-in-chrome" in sitemap
    ok &= sm_ok
    lines.append(f"sitemap entry for /keel-in-chrome: {'OK' if sm_ok else 'MISSING'}")

    root = SITE / "keel-in-chrome.html"
    physical = SITE / "keel-in-chrome" / "index.html"
    for label, p in (("HTML", root), ("physical route index", physical)):
        present = p.exists()
        ok &= present
        lines.append(f"{label} {rel(p)}: {'OK' if present else 'MISSING'}")

    if root.exists() and physical.exists():
        a, b = read(root), read(physical)
        title_a = re.search(r"<title>(.*?)</title>", a, re.S | re.I)
        title_b = re.search(r"<title>(.*?)</title>", b, re.S | re.I)
        titles_match = bool(title_a and title_b and title_a.group(1) == title_b.group(1))
        canon_a = re.search(r'rel="canonical"[^>]*href="([^"]+)"', a)
        canon_b = re.search(r'rel="canonical"[^>]*href="([^"]+)"', b)
        canonical_match = bool(canon_a and canon_b and canon_a.group(1) == canon_b.group(1))
        scripts_a = set(re.findall(r'<script[^>]+src="([^"]+)"', a))
        scripts_b = set(re.findall(r'<script[^>]+src="([^"]+)"', b))
        scripts_match = scripts_a == scripts_b
        cta_a = len(find_store_ctas(a))
        cta_b = len(find_store_ctas(b))
        cta_match = cta_a == cta_b
        parity = titles_match and canonical_match and scripts_match and cta_match
        ok &= parity
        lines.append(
            f"parity title={titles_match} canonical={canonical_match} "
            f"scripts={scripts_match} add-to-chrome-count={cta_a}/{cta_b} -> {'OK' if parity else 'MISMATCH'}"
        )
        if not scripts_match:
            lines.append(f"  scripts only in HTML: {sorted(scripts_a - scripts_b)}")
            lines.append(f"  scripts only in route index: {sorted(scripts_b - scripts_a)}")
    else:
        lines.append("parity: SKIPPED (one or both landing copies not present yet)")

    record("3. /keel-in-chrome rewrite + sitemap + physical index + HTML parity", ok, "\n".join(lines))


# --------------------------------------------------------------------------
# 4. extension static checks (MV3, wiring, ZIP parity)
# --------------------------------------------------------------------------
def check_extension():
    manifest_path = EXT / "manifest.json"
    if not manifest_path.exists():
        record("4a. manifest JSON / MV3 / referenced files exist", False, "manifest.json missing")
        return
    try:
        manifest = json.loads(read(manifest_path))
        lines = ["manifest.json: valid JSON"]
    except Exception as e:  # noqa: BLE001
        record("4a. manifest JSON / MV3 / referenced files exist", False, f"invalid JSON: {e}")
        return

    mv3 = manifest.get("manifest_version") == 3
    lines.append(f"manifest_version: {manifest.get('manifest_version')} ({'OK' if mv3 else 'NOT MV3'})")

    referenced = []
    for key, val in (("side_panel.default_path", manifest.get("side_panel", {}).get("default_path")),
                     ("background.service_worker", manifest.get("background", {}).get("service_worker"))):
        if val:
            referenced.append((key, val))
    for icon in manifest.get("icons", {}).values():
        referenced.append(("icons", icon))
    for icon in manifest.get("action", {}).get("default_icon", {}).values():
        referenced.append(("action.default_icon", icon))
    for cs in manifest.get("content_scripts", []):
        for js in cs.get("js", []):
            referenced.append(("content_scripts.js", js))
    for key, val, where in (
        ("options_page", manifest.get("options_page"), "options_page"),
        ("options_ui.page", (manifest.get("options_ui") or {}).get("page"), "options_ui"),
    ):
        if val:
            referenced.append((where, val))
    missing = [(k, v) for k, v in referenced if not (EXT / v).exists()]
    lines.append(f"referenced files: {len(referenced)} checked, missing={missing or 'none'}")
    record("4a. manifest JSON / MV3 / referenced files exist", mv3 and not missing, "\n".join(lines))

    # IDs referenced by sidepanel.js must exist in sidepanel.html
    sp_js, sp_html = read_opt(EXT / "sidepanel.js"), read_opt(EXT / "sidepanel.html")
    if sp_js is None or sp_html is None:
        record("4b. every ID referenced in sidepanel.js exists in sidepanel.html", False,
               "sidepanel.js or sidepanel.html missing")
    else:
        html_ids = collect_ids(sp_html)
        ref_ids = set()
        for m in re.finditer(r"(?:getElementById|byId)\(\s*['\"]([\w-]+)['\"]", sp_js):
            ref_ids.add(m.group(1))
        cache_block = re.search(r"\[\s*'newSessionBtn'(.*?)\]\.forEach", sp_js, re.S)
        if cache_block:
            ref_ids.update(re.findall(r"'([A-Za-z][\w]*)'", cache_block.group(0)))
        ref_ids.update(re.findall(r"byId\('tab-' \+ ([A-Z])", sp_js))
        # Newer builds map tab names to explicit IDs (IDs must not contain spaces
        # because aria-labelledby is a space-separated IDREF list). Fall back to
        # the older "tab-" + name convention when the map is absent.
        tab_ids = re.search(r"var TAB_IDS\s*=\s*\{(.*?)\}", sp_js, re.S)
        dynamic_ids = set()
        if tab_ids:
            dynamic_ids = set(re.findall(r":\s*'([^']+)'", tab_ids.group(1)))
        else:
            tabs = re.search(r"var TABS = \[(.*?)\]", sp_js, re.S)
            if tabs:
                dynamic_ids = {"tab-" + t for t in re.findall(r"'([^']+)'", tabs.group(1))}
        ref_ids.discard("tab-")
        ref_ids.discard("A")
        missing_ids = sorted((ref_ids | dynamic_ids) - html_ids)
        record("4b. every ID referenced in sidepanel.js exists in sidepanel.html", not missing_ids,
               f"referenced IDs: {len(ref_ids | dynamic_ids)}; missing: {missing_ids or 'none'}")

    # message types: senders vs handlers
    bg_js, ct_js = read_opt(EXT / "background.js"), read_opt(EXT / "content.js")
    if bg_js is None or ct_js is None or sp_js is None:
        record("4c. every message type sent has a handler", False, "extension JS file missing")
        record("4d. SET_SETTINGS payload shape matches its handler", False, "extension JS file missing")
    else:
        sent_panel = set(re.findall(r"sendMessage\(\s*\{\s*type:\s*'([^']+)'", sp_js))
        handled_bg = set(re.findall(r"case\s*'([^']+)'\s*:", bg_js))
        sent_bg = set(re.findall(r"sendMessage\([^;]*?type:\s*'([^']+)'", bg_js))
        handled_ct = set(re.findall(r"message\.type\s*!==\s*'([^']+)'", ct_js)) | set(
            re.findall(r"message\.type\s*===\s*'([^']+)'", ct_js)
        )
        handled_panel = set(re.findall(r"message\.type\s*===\s*'([^']+)'", sp_js))
        miss_bg = sorted(sent_panel - handled_bg)
        miss_other = sorted(sent_bg - (handled_ct | handled_panel))
        record("4c. every message type sent has a handler", not miss_bg and not miss_other,
               "\n".join([
                   f"panel -> background: {len(sent_panel)} types; unhandled: {miss_bg or 'none'}",
                   f"background -> content/panel: {sorted(sent_bg)}; unhandled: {miss_other or 'none'}",
                   f"background cases: {len(handled_bg)}",
               ]))
        case = re.search(r"case 'SET_SETTINGS':\s*\{(.*?)\n\s*\}", bg_js, re.S)
        case_body = case.group(1) if case else ""
        reads_settings = "payload.settings" in case_body or "message.settings" in case_body
        sends_settings = bool(re.search(r"type:\s*'SET_SETTINGS'\s*,\s*settings\s*:", sp_js))
        setting_bug = sends_settings and not reads_settings
        record("4d. SET_SETTINGS payload shape matches its handler", not setting_bug,
               ("sidepanel.js sends { type:'SET_SETTINGS', settings: patch } but background.js never reads "
                "the nested settings object; settings silently revert."
                if setting_bug else "payload shapes agree"))

    # ZIP integrity and parity with folder
    zip_path = SITE / "keel-extension.zip"
    zlines = []
    if not zip_path.exists():
        record("4e. keel-extension.zip root manifest + parity with extension folder", False, "zip missing")
        return
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            zok = "manifest.json" in names and not any(n.startswith("/") for n in names)
            zlines.append(f"entries: {len(names)}; manifest.json at root: {'manifest.json' in names}")
            folder_files = {str(p.relative_to(EXT)).replace("\\", "/") for p in EXT.rglob("*") if p.is_file()}
            zset = set(names)
            zlines.append(f"zip-only: {sorted(zset - folder_files) or 'none'}")
            zlines.append(f"folder-only: {sorted(folder_files - zset) or 'none'}")
            zok &= zset == folder_files
            diffs = [n for n in sorted(zset & folder_files) if z.read(n) != (EXT / n).read_bytes()]
            zlines.append(f"content mismatches: {diffs or 'none'}")
            zok &= not diffs
            if "manifest.json" in names:
                zok &= z.read("manifest.json") == (EXT / "manifest.json").read_bytes()
    except Exception as e:  # noqa: BLE001 - e.g. mid-write by another agent
        record("4e. keel-extension.zip root manifest + parity with extension folder", False,
               f"cannot inspect zip: {type(e).__name__}: {e}")
        return
    record("4e. keel-extension.zip root manifest + parity with extension folder", bool(zok), "\n".join(zlines))


# --------------------------------------------------------------------------
# 5. control wiring (static) on BOTH landing copies
# --------------------------------------------------------------------------
def check_control_wiring():
    present = [p for p in LANDING_FILES if p.exists()]
    if not present:
        skip("5. buttons/controls wired (static cross-reference)", "neither landing copy is present yet")
        return
    js_files = [LANDING_JS, INSTALL_JS]
    js = "\n".join(read(p) for p in js_files if p.exists())
    if not js:
        skip("5. buttons/controls wired (static cross-reference)", "chrome-landing.js / chrome-install.js not present yet")
        return
    selector_literals = set()
    for m in re.finditer(r"(?:querySelectorAll|querySelector|all|\$)\(\s*(['\"])(.*?)\1", js):
        selector_literals.add(m.group(2))
    for m in re.finditer(r"['\"]([^'\"\r\n]*(?:\[data-|\.)[^'\"\r\n]*)['\"]", js):
        selector_literals.add(m.group(1))
    ids = {s[1:] for s in selector_literals if s.startswith("#") and re.fullmatch(r"#[\w-]+", s)}
    ids |= set(re.findall(r"(?:getElementById|byId)\(\s*['\"]([\w-]+)['\"]", js))
    classes = set()
    for s in selector_literals:
        classes.update(re.findall(r"\.([A-Za-z][\w-]*)", s))
    data_attrs = set(re.findall(r"\[data-([\w-]+)", " ".join(selector_literals))) | set(
        re.findall(r"getAttribute\(\s*['\"]data-([\w-]+)['\"]", js)
    )
    has_submit = "submit" in js
    all_unwired, summary = [], []
    for page in present:
        text = read(page)
        unwired = []
        counts = {"a": 0, "button": 0, "input/select": 0, "form": 0}
        for tag in ("a", "button", "input", "select", "form"):
            for m, a in tags_of(text, tag):
                kind = "a" if tag == "a" else "button" if tag == "button" else "form" if tag == "form" else "input/select"
                counts[kind] += 1
                ln = line_of(text, m.start())
                snippet = re.sub(r"\s+", " ", m.group(0))[:110]
                wired = False
                if tag == "a":
                    wired = bool(a.get("href")) and a["href"] != "#"
                elif tag == "form":
                    wired = has_submit
                else:
                    wired = bool(a.get("id") in ids)
                    wired |= any(c in classes for c in a.get("class", "").split())
                    wired |= any(k.startswith("data-") and k[5:] in data_attrs for k in a)
                    if tag == "input" and a.get("type") == "search":
                        wired |= any(s.startswith("input[type=") for s in selector_literals)
                    if a.get("type") == "submit" and has_submit:
                        wired = True
                if not wired:
                    unwired.append(f"{rel(page)}:{ln} <{tag}> {snippet}")
        summary.append(f"{rel(page)}: " + ", ".join(f"{k}={v}" for k, v in counts.items()) + f"; unwired={len(unwired)}")
        all_unwired.extend(unwired)
    record("5. buttons/controls wired (static cross-reference)", not all_unwired,
           "\n".join(summary)
           + ("\nPOTENTIALLY UNWIRED:\n  " + "\n  ".join(all_unwired) if all_unwired else "\nNo unwired controls found."))


# --------------------------------------------------------------------------
# 5b. Add to Chrome CTA store-install wiring
# --------------------------------------------------------------------------
STORE_TOKEN_RE = re.compile(
    r"(?:__|\{\{)?(?:KEEL_)?(?:CHROME_)?(?:WEB_)?STORE_(?:URL|INSTALL_URL|ITEM_ID|ID)(?:__|\}\})?",
    re.I,
)
STORE_URL_RE = re.compile(r"chromewebstore\.google\.com/detail/", re.I)
PLACEHOLDER_RE = re.compile(r"(?:__[A-Z][A-Z0-9_]+__|\{\{[^}]+\}\}|\$\{[^}]+\})")


def find_store_ctas(text: str):
    """CTAs whose *visible text* reads 'Add to Chrome' (including nested markup)."""
    found = []
    for tag in ("a", "button"):
        for m in re.finditer(rf"<{tag}\b([^>]*)>(.*?)</{tag}\s*>", text, re.I | re.S):
            a = attributes(f"<{tag} {m.group(1)}>")
            visible = re.sub(r"<[^>]+>", "", m.group(2))
            visible = re.sub(r"\s+", " ", visible).strip()
            if re.search(r"add\s+to\s+chrome", visible, re.I):
                found.append((m, a, visible))
    return found


def store_tokens(*texts: str | None) -> set[str]:
    tokens: set[str] = set()
    blob = "\n".join(t for t in texts if t)
    for m in re.finditer(r"['\"]([^'\"\r\n]+)['\"]", blob):
        val = m.group(1)
        if STORE_URL_RE.search(val) or STORE_TOKEN_RE.search(val) or PLACEHOLDER_RE.fullmatch(val):
            tokens.add(val)
    for m in STORE_TOKEN_RE.finditer(blob):
        tokens.add(m.group(0))
    for m in PLACEHOLDER_RE.finditer(blob):
        tokens.add(m.group(0))
    return tokens


def cta_target_ok(attrs: dict, tokens: set[str]) -> bool:
    values = [attrs.get(k, "") for k in ("href", "data-store-install", "data-store-url", "data-href")]
    values = [v for v in values if v]
    for v in values:
        if v == "/keel-extension.zip" or v.endswith("/keel-extension.zip"):
            return True
        if STORE_URL_RE.search(v) or STORE_TOKEN_RE.search(v) or PLACEHOLDER_RE.search(v):
            return True
        if any(tok and tok in v for tok in tokens):
            return True
    return False


def check_store_ctas():
    present = [p for p in LANDING_FILES if p.exists()]
    if not present:
        skip("5b. Add to Chrome CTAs wired to free ZIP download (or store URL)", "neither landing copy is present yet")
        return
    html_texts = [read(p) for p in present]
    js_text = read_opt(INSTALL_JS)
    tokens = store_tokens(js_text, *html_texts)
    lines = [f"configured store tokens/URLs discovered: {sorted(tokens) or 'none'}"]
    all_ctas = []
    for p, text in zip(present, html_texts):
        ctas = find_store_ctas(text)
        if not ctas:
            lines.append(f"{rel(p)}: NO 'Add to Chrome' CTA found (work may still be in progress)")
            continue
        for m, attrs, visible in ctas:
            has_attr = "data-store-install" in attrs
            target_ok = cta_target_ok(attrs, tokens)
            all_ctas.append((p, has_attr, target_ok))
            lines.append(
                f"{rel(p)}:{line_of(text, m.start())} {visible!r} "
                f"data-store-install={'OK' if has_attr else 'MISSING'} "
                f"href={attrs.get('href')!r} target={'OK' if target_ok else 'NOT CONFIGURED'}"
            )
    if not all_ctas:
        skip("5b. Add to Chrome CTAs wired to free ZIP download (or store URL)",
             "no 'Add to Chrome' CTA found in either landing copy (additions pending)")
        return
    lines.append("free install guide present in JS: " +
                 ("OK" if "cl-install-modal" in (js_text or "") else "MISSING"))
    ok = all(has and target for _p, has, target in all_ctas) and "cl-install-modal" in (js_text or "")
    record("5b. Add to Chrome CTAs wired to free ZIP download (or store URL)", ok, "\n".join(lines))


def check_install_script():
    present = [p for p in LANDING_FILES if p.exists()]
    referenced = [rel(p) for p in present if re.search(r'<script[^>]+src="(?:/)?ui/chrome-install\.js"', read(p))]
    if not INSTALL_JS.exists():
        if referenced:
            record("5c. ui/chrome-install.js exists and is loaded by both landing copies", False,
                   f"script referenced by {referenced} but file is missing")
        else:
            skip("5c. ui/chrome-install.js exists and is loaded by both landing copies",
                 "ui/chrome-install.js not present yet (optional file, added by another agent); no page references it")
        return
    lines = [f"ui/chrome-install.js present ({INSTALL_JS.stat().st_size} bytes)"]
    ok = True
    for p in present:
        loaded = bool(re.search(r'<script[^>]+src="(?:/)?ui/chrome-install\.js"', read(p)))
        ok &= loaded
        lines.append(f"{rel(p)} loads it: {'OK' if loaded else 'MISSING <script src>'}")
    if not present:
        lines.append("neither landing copy present yet; load check deferred")
    record("5c. ui/chrome-install.js exists and is loaded by both landing copies", ok, "\n".join(lines))


# --------------------------------------------------------------------------
# 6. no site file references the retired /chrome-web-store route
# --------------------------------------------------------------------------
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".ico", ".pdf", ".zip"}


def check_no_old_route():
    hits, pending = [], []
    for f in sorted(SITE.rglob("*")):
        if not f.is_file() or f.suffix.lower() in BINARY_SUFFIXES:
            continue
        text = read_opt(f)
        if text is None:
            continue
        for m in re.finditer(re.escape("/chrome-web-store"), text):
            entry = f"{rel(f)}:{line_of(text, m.start())}"
            (pending if rel(f) in OLD_PAGE_FILES else hits).append(entry)
    details = [
        "references outside retired files: " + (", ".join(hits) if hits else "none"),
        "references in files pending deletion (chrome-web-store page/assets): " +
        (", ".join(pending) if pending else "none"),
    ]
    record("6. no site file references /chrome-web-store", not hits and not pending, "\n".join(details))


# --------------------------------------------------------------------------
# 7/8. headless Chrome rendering, screenshots, CDP interactions
# --------------------------------------------------------------------------
class CDP:
    def __init__(self):
        self.ws = None
        self.nid = 0
        self.events: list[dict] = []
        self.page = "startup"

    def connect(self, url: str):
        import websocket

        self.ws = websocket.create_connection(url, timeout=20, suppress_origin=True)

    def send(self, method: str, params: dict | None = None, timeout: int = 20):
        self.nid += 1
        mid = self.nid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(0.1, deadline - time.time()))
            try:
                msg = json.loads(self.ws.recv())
            except Exception:  # noqa: BLE001 - websocket timeout
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self.events.append({"_page": self.page, **msg})
        raise TimeoutError(f"CDP timeout: {method}")

    def ev(self, expression: str):
        r = self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True},
        )
        if r.get("exceptionDetails"):
            raise RuntimeError("JS exception: " + json.dumps(r["exceptionDetails"])[:300])
        return r.get("result", {}).get("value")

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:  # noqa: BLE001
                pass


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_http(url: str, timeout: float = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    return False


def browser_checks():
    if not CHROME.exists():
        record("7/8. headless Chrome", False, f"Chrome not found at {CHROME}")
        return
    SHOTS.mkdir(parents=True, exist_ok=True)
    for f in SHOTS.glob("qa-*.png"):
        f.unlink()
    http_port, cdp_port = free_port(), free_port()
    server_log = SHOTS / "qa-http-server.log"
    chrome_log = SHOTS / "qa-chrome-stderr.log"
    profile = SHOTS / "qa-chrome-profile"
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)

    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(http_port), "--directory", str(SITE)],
        stdout=server_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    chrome = None
    cdp = CDP()
    try:
        if not wait_http(f"http://127.0.0.1:{http_port}/keel-in-chrome.html"):
            record("7. serve + render", False, "local http.server never became ready")
            return
        cmd = [
            str(CHROME),
            "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--remote-allow-origins=*", f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={profile}", "--enable-logging=stderr", "--v=0",
            "--window-size=1440,900", "--hide-scrollbars", "about:blank",
        ]
        chrome = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=chrome_log.open("wb"))
        if not wait_http(f"http://127.0.0.1:{cdp_port}/json/version", 25):
            record("7. headless Chrome", False, "DevTools endpoint never became ready; see " + str(chrome_log))
            return
        with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list") as r:
            targets = json.load(r)
        page_target = next((t for t in targets if t.get("type") == "page"), None)
        if not page_target:
            record("7. headless Chrome", False, "no page target")
            return
        cdp.connect(page_target["webSocketDebuggerUrl"])
        for dom in ("Runtime.enable", "Log.enable", "Page.enable", "Network.enable"):
            cdp.send(dom)

        shots: list[Path] = []
        render_lines: list[str] = []

        def set_viewport(width, height, mobile):
            cdp.send("Emulation.setDeviceMetricsOverride",
                     {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})

        def navigate(page):
            cdp.page = page
            cdp.send("Page.navigate", {"url": f"http://127.0.0.1:{http_port}/{page}"})
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    if cdp.ev("document.readyState") == "complete":
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.2)
            time.sleep(0.7)

        def screenshot(name):
            data = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]
            path = SHOTS / f"qa-{name}.png"
            path.write_bytes(base64.b64decode(data))
            shots.append(path)
            return path

        def image_stats(path):
            from PIL import Image, ImageStat

            im = Image.open(path).convert("RGB")
            stat = ImageStat.Stat(im)
            colors = im.resize((120, 120)).getcolors(120 * 120)
            distinct = len(colors) if colors else 120 * 120
            return im.size, distinct, max(stat.stddev)

        results: list[tuple[str, bool | None, str]] = []

        def interact(name, expr, guard=None):
            try:
                if guard and not cdp.ev(guard):
                    results.append((name, None, "SKIP: controls not present in this copy"))
                    return
                res = cdp.ev(expr)
            except Exception as e:  # noqa: BLE001
                results.append((name, False, str(e)[:200]))
                return
            if isinstance(res, dict):
                results.append((name, bool(res.get("ok")), json.dumps(res)[:260]))
            else:
                results.append((name, bool(res), str(res)[:220]))

        # ---- keel-in-chrome.html : desktop render + interactions ----
        navigate("keel-in-chrome.html")
        set_viewport(1440, 900, False)
        time.sleep(0.3)
        info = cdp.ev(
            "({title:document.title, text:document.body.innerText.length,"
            " h1:document.querySelector('h1')&&document.querySelector('h1').textContent,"
            " scripts:[...document.scripts].map(s=>s.src).filter(Boolean)})"
        )
        p = screenshot("keel-in-chrome-desktop")
        size, distinct, std = image_stats(p)
        render_lines.append(
            f"keel-in-chrome desktop: {p} size={p.stat().st_size}B dims={size} distinctColors={distinct} "
            f"maxStdDev={std:.1f} title={info.get('title')!r} bodyText={info.get('text')} h1={info.get('h1')!r}"
        )
        cta_info = cdp.ev(
            "[...document.querySelectorAll('a,button')]"
            ".filter(e=>/add\\s+to\\s+chrome/i.test(e.innerText||e.textContent))"
            ".map(e=>({data:e.hasAttribute('data-store-install'),href:e.getAttribute('href'),"
            "store:e.getAttribute('data-store-install')}))"
        )
        render_lines.append(f"Add to Chrome CTA DOM: {json.dumps(cta_info)[:500]}")

        interactions = [
            ("FAQ accordion", """(()=>{const q=document.querySelector('.kp-faq-q'),i=q.closest('.kp-faq-item');q.click();
                const a=i.classList.contains('open')&&q.getAttribute('aria-expanded')==='true'&&i.querySelector('.kp-faq-a').getAttribute('aria-hidden')==='false';
                q.click();return {ok:a&&!i.classList.contains('open'),opened:a,closed:!i.classList.contains('open')};})()"""),
            ("Hero carousel", """(()=>{document.querySelector('[data-mock-dot="1"]').click();
                return {ok:!document.querySelector('[data-mock-page="1"]').hidden&&!document.querySelector('[data-mock-thread="1"]').hidden&&document.querySelector('[data-mock-page="0"]').hidden&&document.querySelector('[data-mock-dot="1"]').getAttribute('aria-pressed')==='true'};})()"""),
            ("Chat/Convert toggle", """(()=>{document.querySelector('[data-mode="convert"]').click();
                const a=!document.querySelector('[data-mode-view="convert"]').hidden&&document.querySelector('.cl-demo-window').hidden;
                document.querySelector('[data-mode="chat"]').click();
                return {ok:a&&document.querySelector('[data-mode-view="convert"]').hidden&&!document.querySelector('.cl-demo-window').hidden};})()"""),
            ("Workflow demo tabs", """(()=>{document.querySelector('[data-demo-tab="code"]').click();
                const t=document.querySelector('[data-demo-title]').textContent;return {ok:t==='Why is this build failing?',text:t};})()"""),
            ("Capability preview buttons", """(()=>{document.querySelector('[data-cap="panel"]').click();
                const t=document.querySelector('[data-cap-caption]').textContent;return {ok:t==='Your whole setup, in the side panel',text:t};})()"""),
            ("Safety segmented tabs", """(()=>{document.querySelector('[data-safety-tab="habits"]').click();
                return {ok:!document.querySelector('[data-safety-panel="habits"]').hidden&&document.querySelector('[data-safety-panel="builtin"]').hidden};})()"""),
            ("Auth modal", """(()=>{document.querySelector('[data-auth-open]').click();
                const a=!document.getElementById('cl-auth-modal').hidden;document.querySelector('[data-auth-close]').click();
                return {ok:a&&document.getElementById('cl-auth-modal').hidden};})()"""),
            ("Guide modal", """(()=>{document.querySelector('[data-guide="troubleshooting"]').click();
                const a=!document.getElementById('cl-guide-modal').hidden&&document.getElementById('cl-guide-title').textContent.includes('Troubleshooting');
                document.querySelector('[data-guide-close]').click();return {ok:a&&document.getElementById('cl-guide-modal').hidden};})()"""),
            ("Footer link search", """(()=>{const i=document.getElementById('cl-footer-q');i.value='chrome';
                i.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.kp-footer-search').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                const s=document.getElementById('cl-search-status').textContent;return {ok:s.length>0,status:s};})()"""),
            ("Language selector", """(()=>{const s=document.getElementById('cl-language');s.value='ja';
                s.dispatchEvent(new Event('change',{bubbles:true}));const t=document.getElementById('cl-lang-status').textContent;
                return {ok:t.includes('日本語'),text:t};})()"""),
            ("Add to Chrome CTA DOM wiring", """(()=>{const c=[...document.querySelectorAll('a,button')]
                .filter(e=>/add\\s+to\\s+chrome/i.test(e.innerText||e.textContent));
                const modal=!!document.getElementById('cl-install-modal');return {ok:c.length>0&&modal&&c.every(e=>e.hasAttribute('data-store-install')&&/keel-extension\\.zip|chromewebstore\\.google\\.com\\/detail\\/|STORE/i.test((e.getAttribute('href')||'')+' '+(e.getAttribute('data-store-install')||''))),
                count:c.length,modal:modal,details:c.map(e=>({data:e.hasAttribute('data-store-install'),href:e.getAttribute('href'),store:e.getAttribute('data-store-install')}))};})()"""),
        ]
        for name, expr in interactions:
            guard = None
            if name not in ("Add to Chrome CTA DOM wiring",):
                first = re.search(r"querySelector\('([^']+)'\)", expr)
                guard = f"!!document.querySelector('{first.group(1)}')" if first else None
            interact("keel-in-chrome / " + name, expr, guard)

        # ---- mobile viewport: screenshot + mobile menu ----
        set_viewport(390, 844, True)
        time.sleep(0.4)
        p = screenshot("keel-in-chrome-mobile")
        size, distinct, std = image_stats(p)
        render_lines.append(
            f"keel-in-chrome mobile: {p} size={p.stat().st_size}B dims={size} distinctColors={distinct} maxStdDev={std:.1f}"
        )
        interact("keel-in-chrome / mobile nav toggle",
                 """(()=>{const t=document.querySelector('.kp-nav-toggle'),m=document.querySelector('.kp-mobile-menu');
                    t.click();const a=m.classList.contains('open');t.click();return {ok:a&&!m.classList.contains('open')};})()""",
                 "!!document.querySelector('.kp-nav-toggle')")

        # ---- physical route index copy (optional, may be mid-write) ----
        if (SITE / "keel-in-chrome" / "index.html").exists():
            set_viewport(1440, 900, False)
            navigate("keel-in-chrome/index.html")
            set_viewport(1440, 900, False)
            time.sleep(0.3)
            info2 = cdp.ev("({title:document.title,text:document.body.innerText.length})")
            p = screenshot("keel-in-chrome-route-desktop")
            size, distinct, std = image_stats(p)
            render_lines.append(
                f"physical route index desktop: {p} size={p.stat().st_size}B dims={size} "
                f"distinctColors={distinct} maxStdDev={std:.1f} title={info2.get('title')!r} bodyText={info2.get('text')}"
            )
            set_viewport(390, 844, True)
            time.sleep(0.4)
            p = screenshot("keel-in-chrome-route-mobile")
            size, distinct, std = image_stats(p)
            render_lines.append(
                f"physical route index mobile: {p} size={p.stat().st_size}B dims={size} "
                f"distinctColors={distinct} maxStdDev={std:.1f}"
            )
        else:
            render_lines.append("physical route index: SKIPPED (keel-in-chrome/index.html not present yet)")

        blank = []
        for path in shots:
            size, distinct, std = image_stats(path)
            if distinct < 12 or (std < 2.0 and path.stat().st_size < 20000):
                blank.append(f"{path.name} (distinct={distinct}, std={std:.1f}, bytes={path.stat().st_size})")
        expected = 4 if (SITE / "keel-in-chrome" / "index.html").exists() else 2
        record("7. headless Chrome renders landing copies desktop+mobile (non-blank)",
               not blank and len(shots) == expected,
               "\n".join(render_lines)
               + ("\nBLANK/UNRENDERED: " + ", ".join(blank) if blank else f"\nAll {len(shots)} screenshots non-blank."))

        # console errors from CDP + Chrome stderr
        js_errors = []
        for e in cdp.events:
            m = e.get("method", "")
            if m == "Runtime.exceptionThrown":
                d = e.get("params", {}).get("exceptionDetails", {})
                js_errors.append(f"[{e.get('_page')}] exception: {d.get('text')} "
                                 f"{str(d.get('exception',{}).get('description',''))[:160]}")
            elif m == "Runtime.consoleAPICalled" and e.get("params", {}).get("type") == "error":
                js_errors.append(f"[{e.get('_page')}] console.error: " + " ".join(
                    str(a.get("value", a.get("description", ""))) for a in e.get("params", {}).get("args", [])
                )[:200])
            elif m == "Log.entryAdded":
                entry = e.get("params", {}).get("entry", {})
                if entry.get("level") == "error":
                    js_errors.append(f"[{e.get('_page')}] log: {entry.get('text','')[:200]} ({entry.get('url','')})")
            elif m == "Network.loadingFailed" and e.get("params", {}).get("errorText") != "net::ERR_ABORTED":
                js_errors.append(f"[{e.get('_page')}] network: {e.get('params',{}).get('errorText','')}")
        stderr_text = chrome_log.read_text(encoding="utf-8", errors="replace") if chrome_log.exists() else ""
        stderr_hits = [
            ln.strip() for ln in stderr_text.splitlines()
            if re.search(r"(?i)uncaught|console|failed to load resource|severe|error", ln)
            and not re.search(
                r"(?i)gpu|dbus|devtools listening|voice_transcription|fontconfig|registration response|"
                r"sandbox|GCM|policy_logger|network_service|external_registry_loader_win|"
                r"Missing value path for key Software", ln)
        ]
        record("7b. no browser/console errors", not js_errors and not stderr_hits,
               "CDP errors: " + (str(js_errors) if js_errors else "none")
               + "\nchrome --enable-logging=stderr filtered hits: "
               + (str(stderr_hits[:12]) if stderr_hits else "none")
               + "\n(raw stderr log: " + str(chrome_log) + ")")

        failed = [r for r in results if r[1] is False]
        skipped = [r for r in results if r[1] is None]
        record("8. CDP interaction exercises", not failed,
               "\n".join(f"{'OK ' if r[1] else ('SKIP' if r[1] is None else 'BAD')} {r[0]}: {r[2]}" for r in results)
               + f"\n{len(results)-len(failed)-len(skipped)}/{len(results)-len(skipped)} executed interactions OK"
               + (f"; {len(skipped)} skipped" if skipped else ""))
    finally:
        cdp.close()
        if chrome:
            chrome.terminate()
            try:
                chrome.wait(timeout=8)
            except Exception:  # noqa: BLE001
                chrome.kill()
        server.terminate()
        try:
            server.wait(timeout=8)
        except Exception:  # noqa: BLE001
            server.kill()


# --------------------------------------------------------------------------
# 9. publishing input (optional)
# --------------------------------------------------------------------------
def check_publishing_input():
    listing = SITE / "store-assets" / "store-listing.md"
    if not listing.exists():
        skip("9. store-assets/store-listing.md present (publishing input)",
             "not present yet (optional file, added by another agent)")
        return
    text = read(listing)
    record("9. store-assets/store-listing.md present (publishing input)", bool(text.strip()),
           f"present ({len(text)} bytes); see CHROME_EXTENSION_PUBLISHING.md for the upload workflow")


def main():
    print("Keel Chrome single-page + real-extension delivery QA")
    print("root:", ROOT)
    print("site:", SITE)
    print("chrome:", CHROME)
    check_js_syntax()
    check_html_static()
    check_routes()
    check_extension()
    check_control_wiring()
    check_store_ctas()
    check_install_script()
    check_no_old_route()
    check_publishing_input()
    try:
        browser_checks()
    except Exception as e:  # noqa: BLE001
        record("7/8. headless Chrome / CDP", False, f"harness exception: {type(e).__name__}: {e}")
    print("\n===== SUMMARY =====")
    for r in RESULTS:
        print(f"{r['status']:4} {r['check']}")
    fails = [r for r in RESULTS if r["status"] == "FAIL"]
    skips = [r for r in RESULTS if r["status"] == "SKIP"]
    passes = [r for r in RESULTS if r["status"] == "PASS"]
    print(f"\n{len(passes)} PASS; {len(fails)} FAIL; {len(skips)} SKIP "
          f"({len(passes)+len(fails)+len(skips)} checks total)")
    if skips:
        print("Skipped (optional / mid-write files):")
        for r in skips:
            print(f"  - {r['check']}: {str(r['details'])[:160]}")
    print("verdict:", "READY" if not fails else "NOT READY")
    print("screenshots:", SHOTS)


if __name__ == "__main__":
    main()
