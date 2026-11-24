#!/usr/bin/env python3
"""Final QA for the Keel-in-Chrome delivery (static + headless-Chrome/CDP).

Run from anywhere:  python verify_keel_chrome.py

This script is read-only with respect to the product files. It only writes
screenshots and Chrome/server logs under C:\\Users\\Admin\\AppData\\Local\\Temp\\opencode\\qa-shots.
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
NEW_PAGES = ["keel-in-chrome.html", "chrome-web-store.html"]
NAV_FILES = ["index.html", "download.html"]

RESULTS: list[dict] = []


def record(check: str, ok: bool, details):
    RESULTS.append({"check": check, "status": "PASS" if ok else "FAIL", "details": details})
    print(f"[{'PASS' if ok else 'FAIL'}] {check}")
    if details:
        for line in str(details).splitlines():
            print("      " + line)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# --------------------------------------------------------------------------
# 1. node --check
# --------------------------------------------------------------------------
def check_js_syntax():
    js_files = sorted((SITE / "ui").glob("*.js")) + sorted(EXT.glob("*.js"))
    new_js = sorted(SITE / "ui" / f for f in ("chrome-landing.js", "chrome-web-store.js"))
    lines = []
    ok = True
    for f in js_files:
        p = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        good = p.returncode == 0
        ok &= good
        tag = "NEW" if f in new_js else "existing"
        lines.append(f"{tag:8} {f.name:24} {'OK' if good else 'SYNTAX ERROR'}")
        if not good:
            lines.append("        " + (p.stderr or p.stdout).strip().replace("\n", "\n        "))
    record("1. node --check on all UI + extension JS", ok, "\n".join(lines))


# --------------------------------------------------------------------------
# 2. HTML static checks
# --------------------------------------------------------------------------
def attributes(tag: str) -> dict:
    out = {}
    for m in re.finditer(r'([A-Za-z_:][-\w:.]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', tag):
        val = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5))
        out[m.group(1).lower()] = val or ""
    # valueless (boolean) attributes, e.g. data-auth-open, data-close, hidden
    without_values = re.sub(r'[A-Za-z_:][-\w:.]*\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', " ", tag)
    for m in re.finditer(r'\b([A-Za-z_:][-\w:.]*)\b', without_values):
        out[m.group(1).lower()] = ""
    return out


def tags_of(text: str, name: str):
    for m in re.finditer(rf"<{name}\b([^>]*)>", text, re.I):
        yield m, attributes(m.group(0))


def collect_ids(text: str) -> set[str]:
    return {a["id"] for _m, a in tags_of(text, r"[A-Za-z][\w:-]*") if a.get("id")}


def check_html_static():
    html_files = sorted(SITE.glob("*.html")) + sorted((SITE / "screenshots").glob("*.html"))
    # key by path relative to SITE: there is both index.html and screenshots/index.html
    id_map = {str(f.relative_to(SITE)).replace("\\", "/"): collect_ids(read(f)) for f in html_files}
    vercel = json.loads(read(SITE / "vercel.json"))
    rewrites = {r["source"] for r in vercel.get("rewrites", [])}
    redirects = {r["source"] for r in vercel.get("redirects", [])}
    short_names = {p: p + ".html" for p in rewrites if p.endswith(".html")}

    empty_hrefs, bad_anchors, unresolved, inline_scripts, branding = [], [], [], [], []

    for f in html_files:
        text = read(f)
        rel = str(f.relative_to(SITE))
        # href="#"
        for m in re.finditer(r'href\s*=\s*(["\'])(.*?)\1', text, re.I):
            href = m.group(2).strip()
            if href == "#":
                empty_hrefs.append(f"{rel}:{line_of(text, m.start())}")
            if href.startswith("#"):
                if href[1:] not in id_map.get(rel, set()):
                    bad_anchors.append(f"{rel}:{line_of(text, m.start())} -> {href} (no id in same file)")
            elif href.startswith("/#"):
                target = id_map.get("index.html", set())
                if href[2:] not in target:
                    bad_anchors.append(f"{rel}:{line_of(text, m.start())} -> {href} (no id in index.html)")
            elif "#" in href and not href.startswith(("http://", "https://", "//")):
                path, frag = href.split("#", 1)
                target_file = path.lstrip("/") or "index.html"
                if target_file.endswith(".html") and frag and (SITE / target_file).exists():
                    if frag not in id_map.get(target_file, set()):
                        bad_anchors.append(f"{rel}:{line_of(text, m.start())} -> {href} (no id in {target_file})")
        # same-origin routes / paths from href and src
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
                # /foo.html style paths are files; directories with index.html also resolve
                if (candidate / "index.html").exists():
                    continue
                unresolved.append(
                    f"{rel}:{line_of(text, m.start())} -> {val}"
                    + (" [NEW PAGE]" if f.name in NEW_PAGES else "")
                )
        # inline <script> (CSP script-src 'self')
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", text, re.I | re.S):
            tag_attrs = attributes(m.group(0)[: m.group(0).find(">") + 1])
            body = m.group(2).strip()
            script_type = tag_attrs.get("type", "").strip().lower()
            # application/ld+json, application/json etc. are inert data blocks,
            # not executable scripts, and are not blocked by script-src 'self'.
            if script_type and script_type not in ("text/javascript", "application/javascript", "module", "text/ecmascript"):
                continue
            if body and not tag_attrs.get("src"):
                inline_scripts.append(f"{rel}:{line_of(text, m.start())}")
            elif body and tag_attrs.get("src"):
                inline_scripts.append(f"{rel}:{line_of(text, m.start())} (src + inline body)")
        # rebranding, only the two new pages
        if f.name in NEW_PAGES:
            for m in re.finditer(r"(?i)claude|anthropic", text):
                branding.append(f"{rel}:{line_of(text, m.start())}")

    def fmt(title, items, limit=30):
        if not items:
            return title + ": none"
        return title + f" ({len(items)}):\n  " + "\n  ".join(items[:limit]) + (
            f"\n  ... +{len(items)-limit} more" if len(items) > limit else ""
        )

    ok = not (empty_hrefs or bad_anchors or branding or inline_scripts)
    record(
        "2a. HTML no href='#', anchors resolve, branding, no inline script",
        ok,
        "\n".join(
            [
                fmt("empty href='#'", empty_hrefs),
                fmt("broken #anchors", bad_anchors),
                fmt("Claude/Anthropic in new pages", branding),
                fmt("inline <script>", inline_scripts),
            ]
        ),
    )

    new_unresolved = [u for u in unresolved if "[NEW PAGE]" in u]
    all_other = [u for u in unresolved if "[NEW PAGE]" not in u]
    record(
        "2b. same-origin paths resolve to a file or Vercel rewrite",
        not new_unresolved,
        "unresolved on NEW pages:\n  "
        + ("\n  ".join(new_unresolved) if new_unresolved else "none")
        + "\nunresolved elsewhere (pre-existing): "
        + f"{len(all_other)} occurrences, distinct routes: "
        + ", ".join(sorted({u.split(' -> ')[-1].split(' [')[0] for u in all_other})),
    )
    return unresolved


# --------------------------------------------------------------------------
# 3. routes: vercel.json + sitemap.xml
# --------------------------------------------------------------------------
def check_routes():
    vercel = json.loads(read(SITE / "vercel.json"))
    rewrites = {r["source"]: r["destination"] for r in vercel.get("rewrites", [])}
    sitemap = read(SITE / "sitemap.xml")
    lines = []
    ok = True
    for route, dest in (("/keel-in-chrome", "/keel-in-chrome.html"), ("/chrome-web-store", "/chrome-web-store.html")):
        rw = rewrites.get(route) == dest
        sm = f"https://keel-desktop.vercel.app{route}" in sitemap
        ok &= rw and sm
        lines.append(f"{route:20} rewrite={'OK' if rw else 'MISSING/WRONG'}  sitemap={'OK' if sm else 'MISSING'}")
    record("3. Vercel rewrites + sitemap for both new routes", ok, "\n".join(lines))


# --------------------------------------------------------------------------
# 4. extension static checks
# --------------------------------------------------------------------------
def check_extension():
    lines = []
    ok = True
    manifest_path = EXT / "manifest.json"
    try:
        manifest = json.loads(read(manifest_path))
        lines.append("manifest.json: valid JSON")
    except Exception as e:  # noqa: BLE001
        record("4a. manifest JSON / MV3", False, f"invalid JSON: {e}")
        manifest = {}

    mv3 = manifest.get("manifest_version") == 3
    ok &= mv3
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
    ok &= not missing
    lines.append(f"referenced files: {len(referenced)} checked, missing={missing or 'none'}")
    record("4a. manifest JSON / MV3 / referenced files exist", ok and mv3, "\n".join(lines))

    # IDs referenced by sidepanel.js must exist in sidepanel.html
    sp_js = read(EXT / "sidepanel.js")
    sp_html = read(EXT / "sidepanel.html")
    html_ids = collect_ids(sp_html)
    ref_ids = set()
    for m in re.finditer(r"(?:getElementById|byId)\(\s*['\"]([\w-]+)['\"]", sp_js):
        ref_ids.add(m.group(1))
    cache_block = re.search(r"\[\s*'newSessionBtn'(.*?)\]\.forEach", sp_js, re.S)
    if cache_block:
        ref_ids.update(re.findall(r"'([A-Za-z][\w]*)'", cache_block.group(0)))
    ref_ids.update(re.findall(r"byId\('tab-' \+ ([A-Z])", sp_js))  # handled below via TABS
    # tab-N ids are assembled dynamically; verify them from the TABS array.
    tabs = re.search(r"var TABS = \[(.*?)\]", sp_js, re.S)
    dynamic_ids = set()
    if tabs:
        dynamic_ids = {"tab-" + t for t in re.findall(r"'([^']+)'", tabs.group(1))}
    # byId('tab-' + next) is a dynamically assembled id; discard the literal prefix.
    ref_ids.discard("tab-")
    ref_ids.discard("A")
    missing_ids = sorted((ref_ids | dynamic_ids) - html_ids)
    record(
        "4b. every ID referenced in sidepanel.js exists in sidepanel.html",
        not missing_ids,
        f"referenced IDs: {len(ref_ids | dynamic_ids)}; missing: {missing_ids or 'none'}",
    )

    # message types: senders vs handlers
    bg_js = read(EXT / "background.js")
    ct_js = read(EXT / "content.js")
    sent_panel = set(re.findall(r"sendMessage\(\s*\{\s*type:\s*'([^']+)'", sp_js))
    handled_bg = set(re.findall(r"case\s*'([^']+)'\s*:", bg_js))
    sent_bg = set(re.findall(r"sendMessage\([^;]*?type:\s*'([^']+)'", bg_js))
    handled_ct = set(re.findall(r"message\.type\s*!==\s*'([^']+)'", ct_js)) | set(
        re.findall(r"message\.type\s*===\s*'([^']+)'", ct_js)
    )
    handled_panel = set(re.findall(r"message\.type\s*===\s*'([^']+)'", sp_js))
    miss_bg = sorted(sent_panel - handled_bg)
    miss_other = sorted(sent_bg - (handled_ct | handled_panel))
    lines = [
        f"panel -> background: {len(sent_panel)} types; unhandled: {miss_bg or 'none'}",
        f"background -> content/panel: {sorted(sent_bg)}; unhandled: {miss_other or 'none'}",
        f"background cases: {len(handled_bg)}",
    ]
    ok_msg = not miss_bg and not miss_other
    record("4c. every message type sent has a handler", ok_msg, "\n".join(lines))

    # payload-shape sanity for SET_SETTINGS
    case = re.search(r"case 'SET_SETTINGS':\s*\{(.*?)\n\s*\}", bg_js, re.S)
    case_body = case.group(1) if case else ""
    reads_settings = "payload.settings" in case_body or "message.settings" in case_body
    sends_settings = bool(re.search(r"type:\s*'SET_SETTINGS'\s*,\s*settings\s*:", sp_js))
    setting_bug = sends_settings and not reads_settings
    record(
        "4d. SET_SETTINGS payload shape matches its handler",
        not setting_bug,
        (
            "sidepanel.js sends { type:'SET_SETTINGS', settings: patch } but background.js iterates "
            "Object.keys(payload) and only copies boolean top-level fields; payload.settings is never read. "
            "Settings never persist and the UI snaps back to the stored values."
            if setting_bug
            else "payload shapes agree"
        ),
    )

    # zip integrity and parity with folder
    zip_path = SITE / "keel-extension.zip"
    zlines = []
    zok = zip_path.exists()
    if not zok:
        zlines.append("zip missing")
    else:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            zok &= "manifest.json" in names and not any(n.startswith("/") for n in names)
            zlines.append(f"entries: {len(names)}; manifest.json at root: {'manifest.json' in names}")
            folder_files = {str(p.relative_to(EXT)).replace("\\", "/") for p in EXT.rglob("*") if p.is_file()}
            zset = set(names)
            zlines.append(f"zip-only: {sorted(zset - folder_files) or 'none'}")
            zlines.append(f"folder-only: {sorted(folder_files - zset) or 'none'}")
            zok &= zset == folder_files
            diffs = []
            for n in sorted(zset & folder_files):
                if z.read(n) != (EXT / n).read_bytes():
                    diffs.append(n)
            zlines.append(f"content mismatches: {diffs or 'none'}")
            zok &= not diffs
            zok &= z.read("manifest.json") == (EXT / "manifest.json").read_bytes() if "manifest.json" in names else False
    record("4e. keel-extension.zip root manifest + parity with extension folder", bool(zok), "\n".join(zlines))


# --------------------------------------------------------------------------
# 5. control wiring (static)
# --------------------------------------------------------------------------
def check_control_wiring():
    all_unwired = []
    summary = []
    for page in NEW_PAGES:
        html = read(SITE / page)
        js_file = SITE / "ui" / ("chrome-landing.js" if page == "keel-in-chrome.html" else "chrome-web-store.js")
        js = read(js_file)
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
        selectors = selector_literals
        has_submit = "submit" in js
        unwired = []
        counts = {"a": 0, "button": 0, "input/select": 0, "form": 0}
        for tag in ("a", "button", "input", "select", "form"):
            for m, a in tags_of(html, tag):
                kind = "a" if tag == "a" else "button" if tag == "button" else "form" if tag == "form" else "input/select"
                counts[kind] += 1
                ln = line_of(html, m.start())
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
                        wired |= any(s.startswith("input[type=") for s in selectors)
                    if a.get("type") == "submit" and has_submit:
                        wired = True
                if not wired:
                    unwired.append(f"{page}:{ln} <{tag}> {snippet}")
        summary.append(f"{page}: " + ", ".join(f"{k}={v}" for k, v in counts.items()) + f"; unwired={len(unwired)}")
        all_unwired.extend(unwired)
    record(
        "5. buttons/controls wired (static cross-reference)",
        not all_unwired,
        "\n".join(summary)
        + ("\nPOTENTIALLY UNWIRED:\n  " + "\n  ".join(all_unwired) if all_unwired else "\nNo unwired controls found."),
    )


# --------------------------------------------------------------------------
# 6/7. headless Chrome rendering, screenshots, CDP interactions
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
        record("6/7. headless Chrome", False, f"Chrome not found at {CHROME}")
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
            record("6. serve + render", False, "local http.server never became ready")
            return
        cmd = [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={profile}",
            "--enable-logging=stderr",
            "--v=0",
            "--window-size=1440,900",
            "--hide-scrollbars",
            "about:blank",
        ]
        chrome = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=chrome_log.open("wb"))
        if not wait_http(f"http://127.0.0.1:{cdp_port}/json/version", 25):
            record("6. headless Chrome", False, "DevTools endpoint never became ready; see " + str(chrome_log))
            return
        with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list") as r:
            targets = json.load(r)
        page_target = next((t for t in targets if t.get("type") == "page"), None)
        if not page_target:
            record("6. headless Chrome", False, "no page target")
            return
        cdp.connect(page_target["webSocketDebuggerUrl"])
        for dom in ("Runtime.enable", "Log.enable", "Page.enable", "Network.enable"):
            cdp.send(dom)

        shots = []
        render_lines = []

        def set_viewport(width, height, mobile):
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile},
            )

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
            small = im.resize((120, 120))
            colors = small.getcolors(120 * 120)
            distinct = len(colors) if colors else 120 * 120
            return im.size, distinct, max(stat.stddev)

        def interact(name, expr):
            try:
                res = cdp.ev(expr)
            except Exception as e:  # noqa: BLE001
                results.append((name, False, str(e)[:200]))
                return
            if isinstance(res, dict):
                good = bool(res.get("ok"))
                results.append((name, good, json.dumps(res)[:220]))
            else:
                results.append((name, bool(res), str(res)[:220]))

        results: list[tuple[str, bool, str]] = []

        # ---- keel-in-chrome.html : desktop render + desktop interactions ----
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
            f"keel-in-chrome desktop: {p} size={p.stat().st_size}B dims={size} distinctColors={distinct} maxStdDev={std:.1f} "
            f"title={info.get('title')!r} bodyText={info.get('text')} h1={info.get('h1')!r}"
        )
        for name, expr in [
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
        ]:
            interact("keel-in-chrome / " + name, expr)

        # ---- mobile viewport: screenshots + mobile menu ----
        set_viewport(390, 844, True)
        time.sleep(0.4)
        p = screenshot("keel-in-chrome-mobile")
        size, distinct, std = image_stats(p)
        render_lines.append(
            f"keel-in-chrome mobile: {p} size={p.stat().st_size}B dims={size} distinctColors={distinct} maxStdDev={std:.1f}"
        )
        interact(
            "keel-in-chrome / mobile nav toggle",
            """(()=>{const t=document.querySelector('.kp-nav-toggle'),m=document.querySelector('.kp-mobile-menu');
               t.click();const a=m.classList.contains('open');t.click();return {ok:a&&!m.classList.contains('open')};})()""",
        )

        # ---- chrome-web-store.html ----
        set_viewport(1440, 900, False)
        navigate("chrome-web-store.html")
        set_viewport(1440, 900, False)
        time.sleep(0.3)
        info2 = cdp.ev(
            "({title:document.title,text:document.body.innerText.length,h1:document.querySelector('h1')&&document.querySelector('h1').textContent})"
        )
        p = screenshot("chrome-web-store-desktop")
        size, distinct, std = image_stats(p)
        render_lines.append(
            f"chrome-web-store desktop: {p} size={p.stat().st_size}B dims={size} distinctColors={distinct} maxStdDev={std:.1f} "
            f"title={info2.get('title')!r} bodyText={info2.get('text')} h1={info2.get('h1')!r}"
        )
        for name, expr in [
            ("store tabs", """(()=>{document.querySelector('[data-tab="discover"]').click();
                const a=!document.getElementById('panel-discover').hidden&&document.getElementById('panel-extensions').hidden;
                document.querySelector('[data-tab="themes"]').click();const b=!document.getElementById('panel-themes').hidden;
                document.querySelector('[data-goto="extensions"]').click();
                return {ok:a&&b&&!document.getElementById('panel-extensions').hidden};})()"""),
            ("search: no results + clear", """(()=>{const i=document.getElementById('cws-search-input');i.value='zzzzq';
                document.getElementById('cws-search-btn').click();
                const a=!document.getElementById('cws-no-results').hidden&&document.getElementById('cws-listing').hidden;
                document.getElementById('cws-clear-search').click();
                return {ok:a&&document.getElementById('cws-no-results').hidden&&!document.getElementById('cws-listing').hidden};})()"""),
            ("search: matching query", """(()=>{const i=document.getElementById('cws-search-input');i.value='chrome';
                document.getElementById('cws-search-btn').click();
                return {ok:document.getElementById('cws-no-results').hidden&&!document.getElementById('cws-listing').hidden};})()"""),
            ("carousel arrows/dots", """(()=>{document.getElementById('cws-next').click();
                const s=document.querySelectorAll('.cws-slide');const a=s[1].getAttribute('aria-hidden')==='false';
                document.querySelector('[data-slide="2"]').click();const b=s[2].getAttribute('aria-hidden')==='false';
                document.getElementById('cws-prev').click();return {ok:a&&b&&s[1].getAttribute('aria-hidden')==='false'};})()"""),
            ("install modal", """(()=>{document.getElementById('cws-add-btn').click();
                const a=!document.getElementById('cws-install-modal').hidden;
                document.querySelector('[data-close="cws-install-modal"]').click();
                return {ok:a&&document.getElementById('cws-install-modal').hidden};})()"""),
            ("video modal", """(()=>{document.getElementById('cws-play').click();
                const a=!document.getElementById('cws-video-modal').hidden;
                document.querySelector('[data-close="cws-video-modal"]').click();
                return {ok:a&&document.getElementById('cws-video-modal').hidden};})()"""),
            ("account popover", """(()=>{document.getElementById('cws-avatar-btn').click();
                const a=!document.getElementById('cws-avatar-menu').hidden;document.body.click();
                return {ok:a&&document.getElementById('cws-avatar-menu').hidden};})()"""),
            ("ratings tooltip", """(()=>{const b=document.getElementById('cws-ratings-info');
                b.dispatchEvent(new MouseEvent('mouseenter'));const a=!document.getElementById('cws-ratings-tip').hidden;
                b.dispatchEvent(new MouseEvent('mouseleave'));return {ok:a&&document.getElementById('cws-ratings-tip').hidden};})()"""),
            ("share button toast", """(async()=>{document.getElementById('cws-toast').hidden=true;
                document.getElementById('cws-share-btn').click();await new Promise(r=>setTimeout(r,450));
                return {ok:!document.getElementById('cws-toast').hidden,text:document.getElementById('cws-toast').textContent};})()"""),
            ("data-toast menu item", """(()=>{document.getElementById('cws-toast').hidden=true;
                document.querySelector('[data-toast]').click();
                return {ok:!document.getElementById('cws-toast').hidden,text:document.getElementById('cws-toast').textContent};})()"""),
        ]:
            interact("chrome-web-store / " + name, expr)

        set_viewport(390, 844, True)
        time.sleep(0.4)
        p = screenshot("chrome-web-store-mobile")
        size, distinct, std = image_stats(p)
        render_lines.append(
            f"chrome-web-store mobile: {p} size={p.stat().st_size}B dims={size} distinctColors={distinct} maxStdDev={std:.1f}"
        )

        blank = []
        for path in shots:
            size, distinct, std = image_stats(path)
            if distinct < 12 or (std < 2.0 and path.stat().st_size < 20000):
                blank.append(f"{path.name} (distinct={distinct}, std={std:.1f}, bytes={path.stat().st_size})")
        record(
            "6. headless Chrome renders both pages desktop+mobile (non-blank)",
            not blank and len(shots) == 4,
            "\n".join(render_lines) + ("\nBLANK/UNRENDERED: " + ", ".join(blank) if blank else "\nAll 4 screenshots non-blank."),
        )

        # console errors from CDP + Chrome stderr
        js_errors = []
        for e in cdp.events:
            m = e.get("method", "")
            if m == "Runtime.exceptionThrown":
                d = e.get("params", {}).get("exceptionDetails", {})
                js_errors.append(f"[{e.get('_page')}] exception: {d.get('text')} {str(d.get('exception',{}).get('description',''))[:160]}")
            elif m == "Runtime.consoleAPICalled" and e.get("params", {}).get("type") == "error":
                js_errors.append(f"[{e.get('_page')}] console.error: " + " ".join(
                    str(a.get("value", a.get("description", ""))) for a in e.get("params", {}).get("args", [])
                )[:200])
            elif m == "Log.entryAdded":
                entry = e.get("params", {}).get("entry", {})
                if entry.get("level") == "error":
                    js_errors.append(f"[{e.get('_page')}] log: {entry.get('text','')[:200]} ({entry.get('url','')})")
            elif m == "Network.loadingFailed":
                err = e.get("params", {}).get("errorText", "")
                if err != "net::ERR_ABORTED":
                    js_errors.append(f"[{e.get('_page')}] network: {err}")
        stderr_text = ""
        if chrome_log.exists():
            stderr_text = chrome_log.read_text(encoding="utf-8", errors="replace")
        stderr_hits = [
            ln.strip()
            for ln in stderr_text.splitlines()
            if re.search(r"(?i)uncaught|console|failed to load resource|severe|error", ln)
            and not re.search(
                r"(?i)gpu|dbus|devtools listening|voice_transcription|fontconfig|registration response|"
                r"sandbox|GCM|policy_logger|network_service|external_registry_loader_win|"
                r"Missing value path for key Software",
                ln,
            )
        ]
        ok_console = not js_errors and not stderr_hits
        record(
            "6b. no browser/console errors",
            ok_console,
            "CDP errors: " + (str(js_errors) if js_errors else "none")
            + "\nchrome --enable-logging=stderr filtered hits: "
            + (str(stderr_hits[:12]) if stderr_hits else "none")
            + "\n(raw stderr log: " + str(chrome_log) + ")",
        )

        failed = [r for r in results if not r[1]]
        record(
            "7. CDP interaction exercises",
            not failed,
            "\n".join(f"{'OK ' if r[1] else 'BAD'} {r[0]}: {r[2]}" for r in results),
        )
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


def main():
    print("Keel Chrome delivery QA")
    print("root:", ROOT)
    print("site:", SITE)
    print("chrome:", CHROME)
    check_js_syntax()
    check_html_static()
    check_routes()
    check_extension()
    check_control_wiring()
    try:
        browser_checks()
    except Exception as e:  # noqa: BLE001
        record("6/7. headless Chrome / CDP", False, f"harness exception: {type(e).__name__}: {e}")
    print("\n===== SUMMARY =====")
    for r in RESULTS:
        print(f"{r['status']:4} {r['check']}")
    fails = [r for r in RESULTS if r["status"] == "FAIL"]
    print(f"\n{len(RESULTS)-len(fails)}/{len(RESULTS)} checks PASS; {len(fails)} FAIL")
    print("screenshots:", SHOTS)


if __name__ == "__main__":
    main()
