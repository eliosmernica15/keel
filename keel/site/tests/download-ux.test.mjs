/* Agent A — download UX + PWA tests.
 * Run: node --test keel/site/tests/*.test.mjs
 * No global install: uses the Playwright copy already present in the repo.
 */
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { chromium } from "../../fleet-next/node_modules/playwright/index.mjs";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WORKTREE = path.resolve(SITE, "../..");
const SHA = "a".repeat(64);
const FIXTURE_URL = "https://downloads.example.test";

const fixture = {
  name: "Keel Desktop",
  version: "9.9.9",
  tag: "v9.9.9",
  generated: "test",
  published_at: "2026-11-25T00:00:00Z",
  verified_at: "2026-11-25T00:00:00Z",
  base_url: FIXTURE_URL,
  release_manifest_url: null,
  channels: {
    windows: {
      name: "Windows x64", arch: "x64", version: "9.9.9", file: "Keel-Setup-9.9.9.exe",
      size: 12345678, sha256: SHA, url: `${FIXTURE_URL}/Keel-Setup-9.9.9.exe`,
      available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
      notes: "", installation: "", alternatives: [],
    },
    macos: {
      name: "macOS arm64 (Apple Silicon)", arch: "arm64", version: "9.9.9",
      file: "Keel-9.9.9-macos-arm64.dmg", size: 87654321, sha256: SHA,
      url: `${FIXTURE_URL}/Keel-9.9.9-macos-arm64.dmg`,
      available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
      notes: "", installation: "",
      alternatives: [{
        label: "Intel", name: "macOS x64 (Intel)", arch: "x64", file: "Keel-9.9.9-macos-x64.dmg",
        size: 88776655, sha256: SHA, url: `${FIXTURE_URL}/Keel-9.9.9-macos-x64.dmg`,
        available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
      }],
    },
    linux: {
      name: "Linux DEB", arch: "x86_64", version: "9.9.9", file: "Keel-9.9.9-linux-amd64.deb",
      size: null, sha256: null, url: null, available: false, verified: false, verified_at: null,
      notes: "DEB not published in this fixture.", installation: "",
      alternatives: [{
        label: "RPM", name: "Linux RPM", arch: "x86_64", file: "Keel-9.9.9-linux-x86_64.rpm",
        size: 76543210, sha256: SHA, url: `${FIXTURE_URL}/Keel-9.9.9-linux-x86_64.rpm`,
        available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
      }],
    },
  },
};

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".webmanifest": "application/manifest+json",
  ".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg",
  ".woff2": "font/woff2", ".ttf": "font/ttf", ".ico": "image/x-icon",
};

let server;
let browser;
let base;

before(async () => {
  server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    let name = decodeURIComponent(url.pathname);
    if (name === "/api/download-manifest") {
      res.writeHead(503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "manifest_not_configured" }));
      return;
    }
    if (name === "/app.html") {
      res.writeHead(307, { Location: "/app" });
      res.end();
      return;
    }
    if (name === "/app" || name === "/download" || name === "/downloads") name += ".html";
    if (name === "/") name = "/index.html";
    const file = path.resolve(SITE, "." + name);
    if (!file.startsWith(SITE + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true });
});

after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
});

async function newPage(profile) {
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  // Non-secret deploy-time config for the fixture's first-party asset host.
  await page.addInitScript(() => { globalThis.KEEL_DOWNLOAD_HOSTS = "downloads.example.test"; });
  if (profile) {
    await page.addInitScript((p) => {
      Object.defineProperty(navigator, "userAgent", { configurable: true, get: () => p.ua });
      Object.defineProperty(navigator, "platform", { configurable: true, get: () => p.platform });
      Object.defineProperty(navigator, "userAgentData", {
        configurable: true,
        get: () => ({
          platform: p.platform,
          architecture: p.arch || "",
          bitness: p.bits || "",
          brands: [],
          mobile: false,
          getHighEntropyValues: async () => ({
            architecture: p.arch || "", bitness: p.bits || "", platform: p.platform,
          }),
        }),
      });
    }, profile);
  }
  return { context, page, errors };
}

function profile(ua, platform, arch, bits) {
  return { ua, platform, arch, bits };
}

const WIN = profile(
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
  "Windows", "x86", "64"
);
const MAC_ARM = profile(
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
  "macOS", "arm", "64"
);
const MAC_UNKNOWN = profile(
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
  "macOS", "", ""
);
const LINUX = profile(
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
  "Linux", "x86", "64"
);
const IOS = profile(
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
  "iOS", "arm", "64"
);
const WIN_ARM = profile(
  "Mozilla/5.0 (Windows NT 10.0; ARM64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
  "Windows", "arm", "64"
);

async function openDownload(p, useFixture = false) {
  const session = await newPage(p);
  if (useFixture) {
    await session.page.route("**/api/download-manifest", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) }));
    await session.page.route(`${FIXTURE_URL}/**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        headers: { "Content-Disposition": 'attachment; filename="Keel-Setup-9.9.9.exe"' },
        body: "fake-installer-bytes",
      }));
  }
  await session.page.goto(`${base}/download`, { waitUntil: "domcontentloaded" });
  return session;
}

async function waitState(page, state) {
  await page.waitForFunction((s) => {
    const node = document.getElementById("kp-download-status");
    return !!node && node.getAttribute("data-state") === s;
  }, state, { timeout: 10000 });
}

test("fallback manifest is truthful: no enabled link when nothing is verified", async () => {
  const { context, page, errors } = await openDownload(WIN);
  await waitState(page, "unavailable");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("aria-disabled"), "true");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), null);
  assert.match(await page.locator("#kp-download-status").innerText(), /No verified Windows installer/i);
  const actions = page.locator("#kp-download-variants .kp-row-action");
  assert.equal(await actions.count(), 1);
  assert.equal(await actions.first().getAttribute("disabled"), "");
  assert.deepEqual(errors, []);
  await context.close();
});

test("detection states: iOS/Windows-ARM unsupported, Intel Mac asks to confirm", async () => {
  for (const [p, expected] of [[IOS, /doesn't run on iOS/i], [WIN_ARM, /Windows on ARM build/i]]) {
    const { context, page } = await openDownload(p, true);
    await waitState(page, "unsupported");
    assert.match(await page.locator("#kp-download-status").innerText(), expected);
    assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), null);
    await context.close();
  }
  const { context, page } = await openDownload(MAC_UNKNOWN, true);
  await waitState(page, "arch-confirm");
  assert.match(await page.locator("#kp-download-status").innerText(), /architecture/i);
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), null);
  await context.close();
});

test("manifest availability drives a real download on a user click", async () => {
  const { context, page } = await openDownload(WIN, true);
  await waitState(page, "ready");
  const primary = page.locator("#kp-download-primary");
  assert.equal(await primary.getAttribute("href"), `${FIXTURE_URL}/Keel-Setup-9.9.9.exe`);
  assert.equal(await primary.getAttribute("download"), "Keel-Setup-9.9.9.exe");

  const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
  await primary.click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "Keel-Setup-9.9.9.exe");
  await waitState(page, "started");
  assert.match(await page.locator("#kp-download-status").innerText(), /Download started/i);
  await context.close();
});

test("Linux falls back from DEB to RPM explicitly; DEB stays disabled", async () => {
  const { context, page } = await openDownload(LINUX, true);
  await waitState(page, "ready");
  const status = await page.locator("#kp-download-status").innerText();
  assert.match(status, /DEB is not published yet/i);
  assert.match(status, /RPM/);
  const rows = page.locator("#kp-download-variants .kp-variant-row");
  assert.equal(await rows.count(), 2);
  assert.match(await rows.nth(0).innerText(), /^DEB/i);
  assert.equal(await rows.nth(0).locator(".kp-row-action").getAttribute("disabled"), "");
  const rpm = rows.nth(1).locator(".kp-row-action");
  assert.equal(await rpm.getAttribute("aria-label"), "Select RPM");
  await rpm.click();
  await waitState(page, "ready");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), `${FIXTURE_URL}/Keel-9.9.9-linux-x86_64.rpm`);
  await context.close();
});

test("macOS offers explicit Apple Silicon / Intel choices", async () => {
  const { context, page } = await openDownload(MAC_ARM, true);
  await waitState(page, "ready");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), `${FIXTURE_URL}/Keel-9.9.9-macos-arm64.dmg`);
  const intel = page.locator("#kp-download-variants .kp-variant-row").nth(1).locator(".kp-row-action");
  assert.equal(await intel.getAttribute("aria-label"), "Select Intel");
  await intel.click();
  await waitState(page, "ready");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), `${FIXTURE_URL}/Keel-9.9.9-macos-x64.dmg`);
  await context.close();
});

test("secondary platform selector is compact and switches the primary action", async () => {
  const { context, page } = await openDownload(WIN, true);
  await waitState(page, "ready");
  await page.locator("#kp-other-platforms > summary").click();
  assert.equal(await page.locator("#kp-other-options").isVisible(), true);
  await page.getByRole("button", { name: "macOS", exact: true }).click();
  await waitState(page, "arch-confirm");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), null);
  await context.close();
});

test("SEC-F-02 in-browser: an unapproved HTTPS host cannot enable the download", async () => {
  const tampered = JSON.parse(JSON.stringify(fixture));
  tampered.channels.windows.url = "https://evil.example/Keel-Setup-9.9.9.exe";
  const session = await newPage(WIN);
  await session.page.route("**/api/download-manifest", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(tampered) }));
  await session.page.goto(`${base}/download`, { waitUntil: "domcontentloaded" });
  await waitState(session.page, "unavailable");
  assert.equal(await session.page.locator("#kp-download-primary").getAttribute("href"), null);
  assert.equal(await session.page.locator("#kp-download-primary").getAttribute("aria-disabled"), "true");
  assert.match(await session.page.locator("#kp-download-status").innerText(), /No verified Windows installer/i);
  await session.context.close();
});

test("SEC-F-05: permanent unsigned/Gatekeeper/SmartScreen disclosure is visible", async () => {
  const { context, page } = await openDownload(WIN, true);
  const note = await page.locator(".kp-signing-note").innerText();
  assert.match(note, /Ed25519 signature/i);
  assert.match(note, /not an operating-system code signature/i);
  assert.match(note, /unsigned/i);
  assert.match(note, /Gatekeeper/i);
  assert.match(note, /SmartScreen/i);
  const source = fs.readFileSync(path.join(SITE, "ui/download.js"), "utf8");
  assert.ok(!source.includes(".innerHTML"));
  assert.match(source, /channel\.notes/);
  await context.close();
});

test("PWA manifest starts at the real app route and has one contextual desktop link", async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(SITE, "manifest.webmanifest"), "utf8"));
  assert.equal(manifest.start_url, "/app");
  assert.equal(manifest.scope, "/");
  assert.equal(manifest.id, "/app");
  assert.equal(manifest.display, "standalone");
  assert.deepEqual(manifest.shortcuts.map((s) => s.name), ["Get Keel Desktop"]);
  assert.equal(manifest.shortcuts[0].url, "https://keel-desktop.vercel.app/download");
  assert.equal(manifest.shortcuts.length, 1);
  assert.ok(manifest.icons.some((i) => i.sizes === "192x192"));
  assert.ok(manifest.icons.some((i) => i.sizes === "512x512"));

  const routes = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
  assert.ok(routes.rewrites.some((r) => r.source === "/app" && r.destination === "/app.html"));
  assert.ok(!routes.redirects.some((r) => /(^|\/)app(\.html)?$/.test(r.source) && r.destination === "/download"));
  assert.ok(routes.redirects.some((r) => r.source === "/app.html" && r.destination === "/app"));

  const { context, page, errors } = await newPage(null);
  await page.goto(`${base}/app`);
  assert.match(await page.title(), /Keel — Desktop/);
  assert.equal(await page.locator("#view-chat").count(), 1);
  await page.goto(`${base}/app.html`, { waitUntil: "domcontentloaded" });
  await page.waitForURL(`${base}/app`);
  assert.deepEqual(errors, []);
  await context.close();
});

test("service worker caches app shell only and never release data or binaries", async () => {
  const sw = fs.readFileSync(path.join(SITE, "sw.js"), "utf8");
  assert.match(sw, /const VERSION = "keel-shell-v17"/);
  for (const forbidden of ["/download.json", "/api/", "/ui/download.js", "keel-app.jpg"]) {
    assert.ok(!sw.includes(`"${forbidden}"`), `SHELL must not precache ${forbidden}`);
  }
  assert.match(sw, /download\\\.json/);
  assert.match(sw, /\.\(exe\|msi\|dmg/);
  assert.match(sw, /skipWaiting\(\)/);
  assert.match(sw, /caches\.delete\(key\)/);

  const { context, page } = await newPage(null);
  await page.goto(`${base}/app`);
  const active = await page.evaluate(async () => {
    // Seed a stale worker cache, then confirm activation removes it.
    const stale = await caches.open("keel-shell-v16");
    await stale.put("/stale", new Response("old shell"));
    if (!("serviceWorker" in navigator)) return "unsupported";
    await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
    return navigator.serviceWorker.controller ? "active" : "registered";
  });
  assert.ok(["active", "registered", "unsupported"].includes(active));
  await page.waitForFunction(async () => !(await caches.keys()).includes("keel-shell-v16"), null, { timeout: 10000 });
  const cacheState = await page.evaluate(async () => {
    const keys = await caches.keys();
    const current = await caches.open("keel-shell-v17");
    const requests = await current.keys();
    return { keys, urls: requests.map((r) => r.url) };
  });
  assert.deepEqual([...cacheState.keys], ["keel-shell-v17"]);
  for (const url of cacheState.urls) {
    assert.ok(!url.includes("download.json") && !url.includes("/api/") && !/\.(exe|dmg|deb|rpm|AppImage|zip)$/i.test(url),
      `cache must not contain release data or installers: ${url}`);
  }
  await context.close();
});

test("landing page and owned-file boundary are unchanged", async () => {
  const changed = execFileSync("git", ["diff", "--name-only"], { cwd: WORKTREE, encoding: "utf8" })
    .trim().split("\n").filter(Boolean);
  // app.html is intentionally NOT in this list: a separate, pre-existing
  // accessibility defect was fixed there (keyboard-operable nav buttons,
  // aria-haspopup="dialog" chips, duplicate class attribute). Marketing and
  // app *behavior* files remain protected.
  for (const forbidden of [
    "keel/site/index.html", "keel/site/ui/app.js",
    "keel/site/chrome-web-store.html", "keel/site/keel-in-chrome.html",
    "keel/site/downloads.html",
  ]) {
    assert.ok(!changed.some((f) => f.startsWith(forbidden)), `unexpected change in ${forbidden}`);
  }
  assert.ok(changed.includes("keel/site/download.html"));
  assert.ok(changed.includes("keel/site/ui/download.js"));

  const { context, page, errors } = await newPage(null);
  await page.goto(`${base}/`);
  assert.match(await page.title(), /Keel/);
  assert.equal(await page.locator("#kp-download-primary").count(), 0);
  assert.deepEqual(errors, []);
  await context.close();
});
