/* Agent B — device-specific download UX tests for /download.
 * Fixture-based: the manifest is the committed keel/site/download.json, served
 * by a local static server. Run: node --test keel/site/tests/download-device.test.mjs
 *
 * Verifies, per device (Windows/macOS/Linux):
 *   - the primary download button is enabled and points at the device's channel;
 *   - the status reflects the detected device;
 *   - SHA-256 + size are shown.
 */
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../../fleet-next/node_modules/playwright/index.mjs";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST = JSON.parse(fs.readFileSync(path.join(SITE, "download.json"), "utf8"));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css",
  ".json": "application/json",
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
const LINUX = profile(
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
  "Linux", "x86", "64"
);

async function newPage(deviceProfile) {
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
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
          architecture: p.arch || "",
          bitness: p.bits || "",
          platform: p.platform,
        }),
      }),
    });
  }, deviceProfile);
  return { context, page, errors };
}

async function openDownload(deviceProfile) {
  const session = await newPage(deviceProfile);
  await session.page.goto(`${base}/download`, { waitUntil: "domcontentloaded" });
  return session;
}

async function waitState(page, state) {
  await page.waitForFunction((s) => {
    const node = document.getElementById("kp-download-status");
    return !!node && node.getAttribute("data-state") === s;
  }, state, { timeout: 10000 });
}

test("committed manifest: Windows .exe is the verified channel (fixture-based)", () => {
  const win = MANIFEST.channels.windows;
  assert.equal(win.file, "Keel-Setup-0.1.1.exe");
  assert.equal(win.available, true);
  assert.equal(win.verified, true);
  assert.ok(/^\d{4}-\d{2}-\d{2}/.test(String(win.verified_at)), "windows.verified_at must be a date");
  assert.ok(Number.isFinite(Number(win.size)) && Number(win.size) > 0, "windows.size must be positive");
  assert.match(String(win.sha256), /^[0-9a-f]{64}$/i, "windows.sha256 must be a full hash");
  assert.match(win.url, /^https:\/\/github\.com\/eliosmernica15\/keel\/releases\/download\/v0\.1\.1\/Keel-Setup-0\.1\.1\.exe$/);
});

test("Windows device: primary enabled → .exe URL, status reflects device, size + SHA-256 shown", async () => {
  const { context, page, errors } = await openDownload(WIN);
  await waitState(page, "ready");
  const primary = page.locator("#kp-download-primary");
  assert.equal(await primary.getAttribute("href"), "https://github.com/eliosmernica15/keel/releases/download/v0.1.1/Keel-Setup-0.1.1.exe");
  assert.equal(await primary.getAttribute("download"), "Keel-Setup-0.1.1.exe");
  assert.equal(await primary.getAttribute("aria-disabled"), null);
  assert.equal(await primary.evaluate((el) => !el.hasAttribute("aria-disabled") && el.hasAttribute("href")), true);

  const status = await page.locator("#kp-download-status").innerText();
  assert.match(status, /Windows/i, "status must reflect the detected Windows device");
  assert.match(status, /SHA-256/i);

  const variantsText = await page.locator("#kp-download-variants").innerText();
  assert.match(variantsText, /150\.8 MB/);
  assert.match(variantsText, /SHA-256 verified/i);

  const title = await primary.getAttribute("title");
  assert.match(title, /150\.8 MB/);
  assert.match(title, /SHA-256 verified/i);

  // Clicking the primary starts the download of the .exe.
  const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
  await primary.click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "Keel-Setup-0.1.1.exe");
  await waitState(page, "started");
  assert.match(await page.locator("#kp-download-status").innerText(), /Download started/i);

  assert.deepEqual(errors, []);
  await context.close();
});

test("macOS device: page reflects macOS; primary stays disabled (honest placeholder); .pkg is the macOS channel", async () => {
  const { context, page } = await openDownload(MAC_ARM);
  await waitState(page, "unavailable");
  const primary = page.locator("#kp-download-primary");
  assert.equal(await primary.getAttribute("href"), null);
  assert.equal(await primary.getAttribute("aria-disabled"), "true");
  const status = await page.locator("#kp-download-status").innerText();
  assert.match(status, /macOS/i);
  const variantsText = await page.locator("#kp-download-variants").innerText();
  assert.match(variantsText, /Keel-0\.1\.1-macos-arm64\.pkg/, "the macOS placeholder must name the .pkg build");
  const macosChannel = MANIFEST.channels.macos;
  assert.match(String(macosChannel.file), /\.pkg$/);
  assert.equal(macosChannel.available, false);
  await context.close();
});

test("Linux device: page reflects Linux; no verified Linux installer is offered", async () => {
  const { context, page } = await openDownload(LINUX);
  await waitState(page, "unavailable");
  assert.equal(await page.locator("#kp-download-primary").getAttribute("href"), null);
  assert.equal(await page.locator("#kp-download-primary").getAttribute("aria-disabled"), "true");
  const status = await page.locator("#kp-download-status").innerText();
  assert.match(status, /Linux/i);
  await context.close();
});
