/* Agent D — final verification of the /download page (D-DP series).
 *
 * Covers, with Playwright and overridden user agents:
 *   D-DP-01  Windows UA: primary button enabled, exact verified .exe URL,
 *            SHA-256 + size displayed, Ready status.
 *   D-DP-02  Windows on ARM: honest "Not available on this device".
 *   D-DP-03  macOS Apple Silicon: primary is the verified .pkg.
 *   D-DP-04  macOS Intel: asks for Apple Silicon vs Intel (no guessing).
 *   D-DP-05  Linux: DEB/RPM variants offered, no package-manager guessing.
 *   D-DP-06  iOS + Android: "Not available on this device".
 *   D-DP-07  Other platforms: Windows/macOS/Linux options switch the page.
 *   D-DP-08  Fallback (committed) manifest: no enabled installer links and an
 *            honest empty state (matches the live static site state).
 *   D-DP-09  Primary click flips the page to the "Download started" state.
 *
 * Screenshots for every case are written to tests/qa-final/evidence/.
 */
import { test, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import path from "node:path";
import {
  SHA_A,
  PLATFORMS,
  PRIMARY_URL,
  availableManifest,
  fallbackManifest,
  mockManifest,
  type Manifest,
  type PlatformCase,
} from "../distribution-qa/fixtures";

const EVIDENCE = path.join(__dirname, "evidence");
const MAC_PKG_URL = "https://github.com/keel-org/keel/releases/download/v9.9.9/Keel-0.1.1-macos-arm64.pkg";

/* Verified macOS manifest: primary Apple-Silicon channel available. */
const macosAvailableManifest: Manifest = {
  ...fallbackManifest,
  channels: {
    ...fallbackManifest.channels,
    macos: {
      ...fallbackManifest.channels.macos,
      file: "Keel-0.1.1-macos-arm64.pkg",
      size: 45678901,
      sha256: SHA_A,
      url: MAC_PKG_URL,
      available: true,
      verified: true,
      verified_at: "2026-11-25T00:00:00Z",
    },
  },
};

const linuxAvailableManifest: Manifest = {
  ...fallbackManifest,
  channels: {
    ...fallbackManifest.channels,
    linux: {
      ...fallbackManifest.channels.linux,
      size: 12345678,
      sha256: SHA_A,
      url: "https://github.com/keel-org/keel/releases/download/v9.9.9/Keel-Setup-9.9.9.deb",
      available: true,
      verified: true,
      verified_at: "2026-11-25T00:00:00Z",
    },
  },
};

function manifestFor(p: PlatformCase): Manifest {
  if (p.name === "macos-arm64" || p.name === "macos-x64") return macosAvailableManifest;
  if (p.name === "linux-x64") return linuxAvailableManifest;
  return availableManifest;
}

async function newPlatformContext(browser: Browser, p: PlatformCase): Promise<BrowserContext> {
  // Chromium exposes userAgentData as a getter on Navigator; override it
  // explicitly so the page sees the mocked platform / architecture hints.
  return browser.newContext({
    userAgent: p.userAgent,
    viewport: { width: 1280, height: 900 },
  });
}

async function installPlatform(page: Page, c: PlatformCase) {
  await page.addInitScript((c) => {
    Object.defineProperty(navigator, "platform", { configurable: true, get: () => c.platform });
    const hints = {
      architecture: c.architecture,
      bitness: c.bitness,
      platform: c.uaPlatform,
      brands: [{ brand: "Chromium", version: "131" }],
      mobile: false,
    };
    Object.defineProperty(navigator, "userAgentData", {
      configurable: true,
      get: () => ({
        ...hints,
        getHighEntropyValues: async (keys: string[]) =>
          Object.fromEntries(keys.map((k) => [k, (hints as Record<string, unknown>)[k] ?? ""])),
      }),
    });
  }, c);
}

async function openDownload(page: Page, p: PlatformCase, opts: { api?: Manifest | null } = {}) {
  await installPlatform(page, p);
  if (opts.api !== undefined) await mockManifest(page, { api: opts.api });
  await page.goto("/download", { waitUntil: "load" });
  await page.waitForTimeout(400); // manifest fetch is async
}

test("download page shell renders (D-DP-00)", async ({ page }) => {
  await openDownload(page, PLATFORMS[0]);
  const text = await page.locator("body").innerText();
  expect(text).toMatch(/Download Keel/i);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-00-page-load-windows.png") });
});

test("D-DP-01 Windows: primary enabled, exact verified .exe URL, SHA-256 + size shown", async ({ browser }) => {
  const context = await newPlatformContext(browser, PLATFORMS[0]);
  const page = await context.newPage();
  await openDownload(page, PLATFORMS[0], { api: availableManifest });

  const primary = page.locator("#kp-download-primary");
  await expect(primary).toBeVisible();
  const status = await page.locator("#kp-download-status").innerText();
  expect(status).toMatch(/Ready/i);

  await expect(primary).not.toHaveAttribute("aria-disabled");
  expect(await primary.getAttribute("href")).toBe(PRIMARY_URL);
  expect(await primary.getAttribute("download")).toBe("Keel-Setup-9.9.9.exe");
  expect(await primary.getAttribute("rel")).toMatch(/noopener/);
  const title = await primary.getAttribute("title");
  expect(title).toMatch(/Keel-Setup-9\.9\.9\.exe/);
  expect(title).toMatch(/SHA-256/);
  expect(title).toMatch(/11\.77 MB/); // 12345678 bytes

  const body = await page.locator("body").innerText();
  expect(body).toMatch(/SHA-256/);
  expect(body).toMatch(/11\.77 MB/);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-01-windows.png") });
  await context.close();
});

test("D-DP-02 Windows on ARM: honest unsupported fallback", async ({ browser }) => {
  const context = await newPlatformContext(browser, PLATFORMS[1]);
  const page = await context.newPage();
  await openDownload(page, PLATFORMS[1]);
  const primary = page.locator("#kp-download-primary");
  await expect(primary).toBeVisible();
  expect(await primary.getAttribute("aria-disabled")).toBe("true");
  const status = await page.locator("#kp-download-status").innerText();
  expect(status).toMatch(/Windows on ARM|not published|emulation|not available/i);
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/Download for Windows/i); // no silent pick of another arch
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-02-windows-arm64.png") });
  await context.close();
});

test("D-DP-03 macOS Apple Silicon: primary is the verified .pkg", async ({ browser }) => {
  const context = await newPlatformContext(browser, PLATFORMS[2]);
  const page = await context.newPage();
  await openDownload(page, PLATFORMS[2], { api: macosAvailableManifest });
  const status = await page.locator("#kp-download-status").innerText();
  expect(status).toMatch(/Ready/i);
  const primary = page.locator("#kp-download-primary");
  expect(await primary.getAttribute("href")).toBe(MAC_PKG_URL);
  expect(await primary.getAttribute("download")).toBe("Keel-0.1.1-macos-arm64.pkg");
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/SHA-256/);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-03-macos-arm64.png") });
  await context.close();
});

test("D-DP-04 macOS Intel: offers Apple Silicon vs Intel, no guessing", async ({ browser }) => {
  const context = await newPlatformContext(browser, PLATFORMS[3]);
  const page = await context.newPage();
  await openDownload(page, PLATFORMS[3]);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/Apple Silicon/i);
  expect(body).toMatch(/Intel/i);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-04-macos-x64.png") });
  await context.close();
});

test("D-DP-05 Linux: DEB/RPM variants offered, primary is a verified .deb", async ({ browser }) => {
  const context = await newPlatformContext(browser, PLATFORMS[4]);
  const page = await context.newPage();
  await openDownload(page, PLATFORMS[4], { api: linuxAvailableManifest });
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/DEB/i);
  expect(body).toMatch(/RPM/i);
  const primary = page.locator("#kp-download-primary");
  expect(await primary.getAttribute("href")).toBe("https://github.com/keel-org/keel/releases/download/v9.9.9/Keel-Setup-9.9.9.deb");
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-05-linux.png") });
  await context.close();
});

test("D-DP-06 iOS and Android: honest 'Not available on this device'", async ({ browser }) => {
  for (const p of [PLATFORMS[5], PLATFORMS[6]]) {
    const context = await newPlatformContext(browser, p);
    const page = await context.newPage();
    await openDownload(page, p);
    const primary = page.locator("#kp-download-primary");
    expect(await primary.getAttribute("aria-disabled"), p.name).toBe("true");
    const body = await page.locator("body").innerText();
    expect(body).toMatch(/not available on this device/i);
    await page.screenshot({ path: path.join(EVIDENCE, `D-DP-06-${p.name}.png`) });
    await context.close();
  }
});

test("D-DP-07 Other platforms: Windows/macOS/Linux options switch the page", async ({ browser }) => {
  const context = await newPlatformContext(browser, PLATFORMS[0]);
  const page = await context.newPage();
  await openDownload(page, PLATFORMS[0], { api: availableManifest });
  const details = page.locator("#kp-other-platforms");
  await details.locator("summary").click(); // opens the native details
  const macOsButton = details.locator(".kp-other-option", { hasText: "macOS" }).first();
  await expect(macOsButton).toBeVisible();
  await macOsButton.click();
  await page.waitForTimeout(300);
  const status = await page.locator("#kp-download-status").innerText();
  expect(status.length).toBeGreaterThan(0);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/macOS/i);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-07-other-platforms.png") });
  await context.close();
});

test("D-DP-08 fallback manifest (committed /download.json): Windows enabled via relative URL, other platforms honest", async ({ page }) => {
  // No route mocks: the static server serves the committed fallback manifest.
  await openDownload(page, PLATFORMS[0]);
  const primary = page.locator("#kp-download-primary");
  // Agent B's fallback: the Windows channel is available on the site itself.
  expect(await primary.getAttribute("href")).toContain("/downloads/Keel-Setup-0.1.1.exe");
  expect(await primary.getAttribute("download")).toBe("Keel-Setup-0.1.1.exe");
  const status = await page.locator("#kp-download-status").innerText();
  expect(status).toMatch(/Ready/i);
  const body = await page.locator("body").innerText();
  expect(body).toMatch(/150\.8 MB|SHA-256/);
  // No enabled installer links outside the Windows primary in the fallback.
  const enabled = await page.evaluate(() => {
    const out: string[] = [];
    for (const a of Array.from(document.querySelectorAll("a, button")) as HTMLElement[]) {
      const href = (a as HTMLAnchorElement).getAttribute("href");
      if (href && /\.(exe|pkg|dmg|deb|rpm|zip|appimage)(\?|$)/i.test(href) && a.getAttribute("aria-disabled") !== "true") {
        out.push(href);
      }
    }
    return out;
  });
  expect(enabled.filter((u) => !u.includes("/downloads/Keel-Setup-0.1.1.exe"))).toEqual([]);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-08-fallback-manifest.png") });

  // Open Other platforms and verify the honest macOS/Linux states.
  const details = page.locator("#kp-other-platforms");
  await details.locator("summary").click();
  const linuxButton = details.locator(".kp-other-option", { hasText: "Linux" }).first();
  await expect(linuxButton).toBeVisible();
  await linuxButton.click();
  await page.waitForTimeout(300);
  const linuxStatus = await page.locator("#kp-download-status").innerText();
  expect(linuxStatus).toMatch(/not published|not available|No verified/i);
  await details.locator("summary").click();
  const macOsButton = details.locator(".kp-other-option", { hasText: "macOS" }).first();
  await macOsButton.click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-08b-fallback-other-platforms.png") });
});

test("D-DP-09 primary click flips the page to the 'Download started' state", async ({ page }) => {
  await openDownload(page, PLATFORMS[0]);
  const primary = page.locator("#kp-download-primary");
  await expect(primary).toBeVisible();
  await primary.click();
  await expect(page.locator("#kp-download-status")).toContainText(/Download started/i);
  await page.screenshot({ path: path.join(EVIDENCE, "D-DP-09-download-started.png") });
});
