import { test, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import {
  PLATFORMS,
  PRIMARY_URL,
  availableManifest,
  dishonestManifest,
  fallbackManifest,
  mockManifest,
  type Manifest,
  type PlatformCase,
} from "./fixtures";

const SITE_ORIGIN = "https://keel-desktop.vercel.app";

async function newPlatformContext(browser: Browser, p: PlatformCase): Promise<BrowserContext> {
  // Chromium exposes userAgentData as a getter on Navigator; override it
  // explicitly so the page sees the mocked platform / architecture hints.
  return browser.newContext({
    userAgent: p.userAgent,
    viewport: { width: 1280, height: 900 },
  });
}

async function installPlatform(page: Page, p: PlatformCase) {
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
    // The detection line is transient; record every status announcement so
    // the assertion can see "Detected ..." as well as the final state.
    (window as unknown as { __qaStatusLog: string[] }).__qaStatusLog = [];
    new MutationObserver(() => {
      const s = document.getElementById("kp-download-status");
      if (!s || !s.textContent) return;
      const log = (window as unknown as { __qaStatusLog: string[] }).__qaStatusLog;
      if (log[log.length - 1] !== s.textContent) log.push(s.textContent);
    }).observe(document.documentElement, { subtree: true, childList: true, characterData: true });
  }, p);
}

/** Exercise the page's own detection function with a synthetic navigator. */
async function detectWithPage(page: Page, p: PlatformCase): Promise<{ os: string | null; arch: string | null }> {
  return page.evaluate(async (c) => {
    const api = (window as unknown as {
      __KEEL_DOWNLOAD__?: {
        detectPlatform: (nav: unknown) => Promise<{ os: string | null; arch: string | null }>;
      };
    }).__KEEL_DOWNLOAD__;
    if (!api) throw new Error("download module did not export detectPlatform");
    const hints: Record<string, string> = {
      architecture: c.architecture,
      bitness: c.bitness,
      platform: c.uaPlatform,
    };
    return api.detectPlatform({
      userAgent: c.userAgent,
      platform: c.platform,
      userAgentData: {
        platform: c.uaPlatform,
        architecture: c.architecture,
        bitness: c.bitness,
        getHighEntropyValues: async (keys: string[]) =>
          Object.fromEntries(keys.map((k) => [k, hints[k] || ""])),
      },
    });
  }, p);
}

async function openDownload(
  page: Page,
  p: PlatformCase,
  opts: { api?: Manifest | null; apiStatus?: number; fallback?: Manifest | null } = {}
) {
  await installPlatform(page, p);
  await mockManifest(page, opts);
  await page.goto("/download", { waitUntil: "load" });
  await expect(page.locator("body")).not.toHaveText(/^\s*$/);
  // Manifest fetching is async; give the module one settled microtask turn.
  await page.waitForTimeout(400);
  return page.locator("body").innerText();
}

async function installedDownloadLinks(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const root = document.querySelector("main") || document.body;
    return Array.from(root.querySelectorAll("a"))
      .filter((a) => {
        const el = a as HTMLAnchorElement;
        if (el.getAttribute("aria-disabled") === "true") return false;
        if (/not (currently )?available/i.test(el.textContent || "")) return false;
        const href = el.href;
        if (!href || href.startsWith("#")) return false;
        if (new URL(href, location.href).pathname === "/download") return false;
        // Installer action or an explicit download CTA, not site navigation.
        return /\.(exe|dmg|appimage|deb|rpm|zip)(\?|$)/i.test(href) ||
               /^Download (for |from )/i.test((el.textContent || "").trim()) ||
               /Download for (Windows|macOS|Linux)/i.test(el.textContent || "");
      })
      .map((a) => (a as HTMLAnchorElement).href);
  });
}

test.describe("distribution: /download page and manifest honesty", () => {
  test("renders a download page with a version and a detection status", async ({ page }) => {
    const text = await openDownload(page, PLATFORMS[0]);
    expect(text).toMatch(/Download Keel/i);
    expect(text).toMatch(/v9\.9\.9|9\.9\.9/);
    const status = await page.locator("#kp-download-status").innerText();
    expect(status).toMatch(/verified|manifest|detected|availability/i);
  });

  for (const p of PLATFORMS) {
    test(`OS/architecture detection: ${p.name}`, async ({ browser }) => {
      const context = await newPlatformContext(browser, p);
      const page = await context.newPage();
      await openDownload(page, p);
      const detected = await detectWithPage(page, p);
      const expected: Record<string, { os: string; arch: string | null }> = {
        "windows-x64": { os: "windows", arch: "x64" },
        "windows-arm64": { os: "windows", arch: "arm64" },
        "macos-arm64": { os: "macos", arch: "arm64" },
        "macos-x64": { os: "macos", arch: "x64" },
        "linux-x64": { os: "linux", arch: "x64" }, // package format is never guessed
        ios: { os: "ios", arch: null },
        android: { os: "android", arch: null },
      };
      expect(detected, `detection result for ${p.name}`).toEqual(expected[p.name]);
      const status = await page.locator("#kp-download-status").innerText();
      expect(status.length).toBeGreaterThan(0);
      if (p.name === "ios" || p.name === "android" || p.name === "windows-arm64") {
        expect(status).toMatch(/not published|doesn't run|not supported|emulation/i);
      }
      await context.close();
    });
  }

  test("architecture fallback: UA hints hide, UA string still detects Windows x64", async ({ browser }) => {
    const p = { ...PLATFORMS[0], architecture: "", bitness: "" };
    const context = await newPlatformContext(browser, p);
    const page = await context.newPage();
    await openDownload(page, p);
    expect(await detectWithPage(page, p)).toEqual({ os: "windows", arch: "x64" });
    await context.close();
  });

  test("architecture fallback: Intel Mac gets an explicit Apple Silicon / Intel choice", async ({ browser }) => {
    const context = await newPlatformContext(browser, PLATFORMS[3]);
    const page = await context.newPage();
    const text = await openDownload(page, PLATFORMS[3]);
    expect(text).toMatch(/Apple Silicon/i);
    expect(text).toMatch(/Intel/i);
    await context.close();
  });

  test("Linux offers an explicit DEB vs RPM choice (no package-manager guessing)", async ({ browser }) => {
    const context = await newPlatformContext(browser, PLATFORMS[4]);
    const page = await context.newPage();
    const text = await openDownload(page, PLATFORMS[4]);
    expect(text).toMatch(/DEB/i);
    expect(text).toMatch(/RPM/i);
    await context.close();
  });

  test("manifest failure: API 503 falls back to the committed manifest", async ({ page }) => {
    const text = await openDownload(page, PLATFORMS[0], { api: null, apiStatus: 503 });
    expect(text).toMatch(/9\.9\.9/);
    expect(text).not.toMatch(/Download manifest unavailable/i);
    expect(await installedDownloadLinks(page)).toEqual([]);
  });

  test("manifest failure: both sources unavailable shows an honest empty state", async ({ page }) => {
    const text = await openDownload(page, PLATFORMS[0], { api: null, apiStatus: 503, fallback: null });
    expect(text).toMatch(/manifest unavailable|not yet publicly available/i);
    expect(await installedDownloadLinks(page)).toEqual([]);
  });

  test("unavailable packages cannot be downloaded", async ({ page }) => {
    await openDownload(page, PLATFORMS[0]);
    const links = await installedDownloadLinks(page);
    expect(links, "no enabled installer links from the fallback manifest").toEqual([]);
    const body = await page.locator("body").innerText();
    expect(body).toMatch(/not published|no verified|unavailable/i);
  });

  test("dishonest manifest (size 0 / short sha / http URL) enables no download", async ({ page }) => {
    await openDownload(page, PLATFORMS[0], { api: dishonestManifest });
    const links = await installedDownloadLinks(page);
    expect(links).toEqual([]);
    for (const url of ["http://example.invalid/Keel-Setup.exe", "https://example.invalid/Keel.dmg"]) {
      expect(await page.locator(`a[href="${url}"]`).count()).toBe(0);
    }
  });

  test("primary action uses the exact verified manifest URL", async ({ page }) => {
    await openDownload(page, PLATFORMS[0], { api: availableManifest });
    const links = await installedDownloadLinks(page);
    expect(links).toContain(PRIMARY_URL);
    const primary = page.locator(`a[href="${PRIMARY_URL}"]`);
    await expect(primary).toHaveCount(1);
    await expect(primary).toBeVisible();
    await expect(primary).toHaveAttribute("rel", /noopener/);
    const label = (await primary.innerText()).trim();
    expect(label).toMatch(/Download/i);
  });
});
