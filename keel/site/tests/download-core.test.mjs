/* Agent A — pure logic tests for /ui/download.js and the committed manifest.
 * Run: node --test keel/site/tests/*.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(SITE, "ui/download.js"), "utf8");

function loadModule() {
  const sandbox = {
    console,
    URL,
    setTimeout,
    clearTimeout,
    location: { href: "https://keel-desktop.vercel.app/download" },
    navigator: { userAgent: "", platform: "" },
    // Non-secret deploy-time config: the fixture's first-party asset host.
    KEEL_DOWNLOAD_HOSTS: "downloads.example.test",
    document: {
      readyState: "loading",
      addEventListener() {},
      getElementById() { return null; },
      createElement() { return {}; },
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.__KEEL_DOWNLOAD__;
}

const API = loadModule();
const SHA = "b".repeat(64);

test("manifest sources are same-origin and try /api first", async () => {
  assert.equal(JSON.stringify(API.MANIFEST_SOURCES), JSON.stringify(["/api/download-manifest", "/download.json"]));
  const seen = [];
  const fetcher = async (url) => {
    seen.push(url);
    if (url === "/api/download-manifest") return { ok: false };
    return { ok: true, json: async () => ({ version: "1.0.0", channels: {} }) };
  };
  const doc = await API.fetchManifest(fetcher);
  assert.deepEqual(seen, ["/api/download-manifest", "/download.json"]);
  assert.equal(doc.version, "1.0.0");
});

test("an invalid first manifest falls through to the committed fallback", async () => {
  const seen = [];
  const fetcher = async (url) => {
    seen.push(url);
    return { ok: true, json: async () => ({ version: "bad", channels: "not-an-object" }) };
  };
  const doc = await API.fetchManifest(fetcher);
  assert.equal(doc, null);
  assert.equal(seen.length, 2);
});

test("availability requires verified_at, size, SHA-256 and a public HTTPS URL", () => {
  const good = {
    available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
    size: 1024, sha256: SHA, url: "https://downloads.example.test/Keel.exe",
  };
  assert.equal(API.isDownloadable(good), true);
  assert.equal(API.isDownloadable({ ...good, verified: false }), false);
  assert.equal(API.isDownloadable({ ...good, available: false }), false);
  assert.equal(API.isDownloadable({ ...good, verified_at: null }), false);
  assert.equal(API.isDownloadable({ ...good, size: 0 }), false);
  assert.equal(API.isDownloadable({ ...good, sha256: "short" }), false);
  assert.equal(API.isDownloadable({ ...good, url: "http://downloads.example.test/a.exe" }), false);
  assert.equal(API.isDownloadable({ ...good, url: "https://user:pass@downloads.example.test/a.exe" }), true);
  assert.equal(API.isDownloadable({ ...good, url: "javascript:alert(1)" }), false);
  assert.equal(API.safeUrl("/relative.bin"), "https://keel-desktop.vercel.app/relative.bin");
});

test("SEC-F-02: only approved first-party hosts pass safeUrl (every variant too)", () => {
  assert.equal(API.safeUrl("https://github.com/example/keel/setup.exe"), "https://github.com/example/keel/setup.exe");
  assert.equal(API.safeUrl("https://objects.githubusercontent.com/asset.exe"), "https://objects.githubusercontent.com/asset.exe");
  assert.equal(API.safeUrl("https://downloads.example.test/Keel.exe"), "https://downloads.example.test/Keel.exe");
  assert.equal(API.safeUrl("https://evil.example/Keel-Setup.exe"), null);
  assert.equal(API.safeUrl("https://downloads.example.test.evil.example/Keel.exe"), null);

  const approved = {
    available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
    size: 1000, sha256: SHA, file: "Keel.exe", arch: "x64",
  };
  assert.equal(API.isDownloadable({ ...approved, url: "https://downloads.example.test/Keel.exe" }), true);
  assert.equal(API.isDownloadable({ ...approved, url: "https://evil.example/Keel.exe" }), false);

  const manifest = {
    version: "1.0.0",
    channels: {
      windows: {
        ...approved, url: "https://downloads.example.test/Keel.exe", base_url: "https://evil.example",
        alternatives: [{ ...approved, arch: "arm64", url: "https://evil.example/Keel-2.exe" }],
      },
    },
  };
  const variants = API.variantsFor(manifest, "windows");
  assert.equal(variants.length, 2);
  assert.equal(variants[0].downloadable, true);
  // A tampered manifest cannot self-authorize its own base_url or alternatives.
  assert.equal(variants[1].downloadable, false);
});

test("SEC-F-02: an approved host can also come from the configured manifest endpoint", async () => {
  const sandbox = {
    console, URL, setTimeout, clearTimeout,
    location: { href: "https://keel-desktop.vercel.app/download" },
    navigator: { userAgent: "", platform: "" },
    KEEL_DOWNLOAD_MANIFEST_URL: "https://releases.keel.example.test/manifest.json",
    document: { readyState: "loading", addEventListener() {}, getElementById() { return null; }, createElement() { return {}; } },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  assert.equal(sandbox.__KEEL_DOWNLOAD__.safeUrl("https://releases.keel.example.test/Keel.exe"),
    "https://releases.keel.example.test/Keel.exe");
  assert.equal(sandbox.__KEEL_DOWNLOAD__.safeUrl("https://evil.example/Keel.exe"), null);
});

test("detection uses userAgentData first and never guesses Intel vs Apple Silicon", async () => {
  const win = await API.detectPlatform({
    userAgent: "Mozilla/5.0 (Windows NT 10.0)", platform: "Win32",
    userAgentData: {
      platform: "Windows", architecture: "x86", bitness: "64",
      getHighEntropyValues: async () => ({ architecture: "x86", bitness: "64", platform: "Windows" }),
    },
  });
  assert.deepEqual({ ...win }, { os: "windows", arch: "x64" });

  const mac = await API.detectPlatform({
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", platform: "MacIntel",
    userAgentData: { platform: "macOS" },
  });
  assert.deepEqual({ ...mac }, { os: "macos", arch: null });

  const arm = await API.detectPlatform({
    userAgent: "Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15", platform: "MacIntel",
    userAgentData: { platform: "macOS", getHighEntropyValues: async () => ({ architecture: "arm", bitness: "64" }) },
  });
  assert.deepEqual({ ...arm }, { os: "macos", arch: "arm64" });

  assert.deepEqual({ ...(await API.detectPlatform({ userAgent: "Mozilla/5.0 (iPhone)", platform: "iPhone" })) }, { os: "ios", arch: null });
  assert.deepEqual({ ...(await API.detectPlatform({ userAgent: "Mozilla/5.0 (Linux; Android 14)", platform: "Linux armv8l" })) }, { os: "android", arch: null });
});

test("committed fallback manifest keeps every unverified platform unavailable", () => {
  const doc = JSON.parse(fs.readFileSync(path.join(SITE, "download.json"), "utf8"));
  assert.equal(API.validManifest(doc), true);
  for (const [name, channel] of Object.entries(doc.channels)) {
    assert.equal(channel.available, false, `${name}.available must stay false`);
    assert.equal(channel.verified, false, `${name}.verified must stay false`);
    assert.equal(channel.url, null, `${name}.url must stay null`);
    assert.equal(channel.sha256, null, `${name}.sha256 must stay null`);
    assert.equal(API.variantsFor(doc, name).every((v) => !v.downloadable), true);
  }
});

test("resolvePrimary covers ready, unavailable, arch-confirm and DEB→RPM fallback", () => {
  const verified = {
    available: true, verified: true, verified_at: "2026-11-25T00:00:00Z",
    size: 1000, sha256: SHA, url: "https://downloads.example.test/app.exe",
    arch: "x64", file: "app.exe",
  };
  const manifest = {
    version: "1.2.3",
    channels: {
      windows: { ...verified },
      macos: {
        ...verified, arch: "arm64", file: "app-arm64.dmg",
        alternatives: [{ ...verified, arch: "x64", file: "app-x64.dmg" }],
      },
      linux: {
        ...verified, available: false, verified: false, verified_at: null, size: null,
        sha256: null, url: null, file: "app.deb",
        alternatives: [{ ...verified, file: "app.rpm" }],
      },
    },
  };

  const windows = API.variantsFor(manifest, "windows");
  assert.equal(API.resolvePrimary(windows, { os: "windows", arch: "x64" }, null, true).state, "ready");
  assert.equal(API.resolvePrimary(windows, { os: "windows", arch: "x64" }, null, false).state, "unavailable");

  const macos = API.variantsFor(manifest, "macos");
  assert.equal(API.resolvePrimary(macos, { os: "macos", arch: "arm64" }, null, true).variant.label, "Apple Silicon");
  assert.equal(API.resolvePrimary(macos, { os: "macos", arch: null }, null, true).state, "arch-confirm");
  assert.equal(API.resolvePrimary(macos, { os: "macos", arch: null }, "macos:x64", true).variant.label, "Intel");

  const linux = API.variantsFor(manifest, "linux");
  const linuxResult = API.resolvePrimary(linux, { os: "linux", arch: "x64" }, null, true);
  assert.equal(linuxResult.state, "ready");
  assert.equal(linuxResult.variant.format, "rpm");
  assert.match(linuxResult.note, /DEB is not published/);
  assert.equal(API.resolvePrimary(linux, { os: "linux", arch: "x64" }, "linux:deb", true).state, "unavailable");
});

test("unsupported platforms are recognized without producing a download", () => {
  assert.equal(API.isUnsupported({ os: "ios", arch: null }), true);
  assert.equal(API.isUnsupported({ os: "android", arch: null }), true);
  assert.equal(API.isUnsupported({ os: "windows", arch: "arm64" }), true);
  assert.equal(API.isUnsupported({ os: "windows", arch: "x64" }), false);
  assert.equal(API.isUnsupported({ os: "macos", arch: "arm64" }), false);
  assert.equal(API.isUnsupported({ os: null, arch: null }), false);
});
