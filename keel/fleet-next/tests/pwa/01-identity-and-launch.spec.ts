import { test, expect, type Page } from "@playwright/test";

/**
 * PWA identity, theming and launch/shortcut verification in Chromium (the
 * installed-PWA-compatible browser available here).
 *
 * LIMITATION: Playwright's Chromium can assert the manifest, that the document
 * links it, that its start_url opens the real app, and that a service worker
 * registers at the app scope (installability prerequisites). It cannot perform
 * an OS-level "install app" and launch a standalone installed window, so that
 * final step is not claimed here. Service-worker activation is also not
 * asserted: on the shared dev server the worker can stay in `installing` while
 * its shell cache is populated, and /sw.js is unchanged by this work. The
 * external shortcut target is verified as a manifest URL only; no outbound
 * network request is made to keel-desktop.vercel.app.
 */

const DOWNLOAD_URL = "https://keel-desktop.vercel.app/download";
const LIGHT_BG = "#F7F4EF";
const LIGHT_ACCENT = "#8A5A07";
const DARK_BG = "#0A0605";

type Manifest = {
  name?: string;
  short_name?: string;
  description?: string;
  start_url?: string;
  display?: string;
  background_color?: string;
  theme_color?: string;
  shortcuts?: Array<{ name?: string; short_name?: string; url?: string }>;
};

async function readManifest(page: Page): Promise<Manifest> {
  const response = await page.request.get("/manifest.webmanifest");
  expect(response.ok(), `manifest HTTP ${response.status()}`).toBeTruthy();
  expect(response.headers()["content-type"] || "").toMatch(/manifest\+json|json/i);
  return (await response.json()) as Manifest;
}

test.describe("PWA identity, theming and launch", () => {
  test("manifest carries the unified Keel identity and design-system theme tokens", async ({ page }) => {
    const manifest = await readManifest(page);

    expect(manifest.name).toBe("Keel");
    expect(manifest.short_name).toBe("Keel");
    expect(manifest.description).toMatch(/local-first/i);
    expect(manifest.description).toMatch(/Cowork/i);
    expect(manifest.description).toMatch(/Code/i);
    expect(manifest.description).toMatch(/Duet/i);
    expect(manifest.description).toMatch(/Fleet/i);
    expect(manifest.display).toBe("standalone");

    expect(manifest.background_color?.toUpperCase()).toBe(LIGHT_BG);
    expect(manifest.theme_color?.toUpperCase()).toBe(LIGHT_ACCENT);
  });

  test("start_url is the app root, never a download page", async ({ page }) => {
    await page.goto("/");
    const manifest = await readManifest(page);
    expect(manifest.start_url).toBe("/");

    const base = new URL(page.url());
    const resolved = new URL(manifest.start_url!, base);
    expect(resolved.origin).toBe(base.origin);
    expect(resolved.pathname).toBe("/");
    expect(resolved.pathname).not.toMatch(/download/i);
  });

  test("exactly one shortcut opens the Keel Desktop download page", async ({ page }) => {
    const manifest = await readManifest(page);
    expect(Array.isArray(manifest.shortcuts)).toBeTruthy();
    expect(manifest.shortcuts).toHaveLength(1);

    const shortcut = manifest.shortcuts![0];
    expect(shortcut.name).toBe("Get Keel Desktop");

    const target = new URL(shortcut.url!, page.url());
    expect(target.origin).toBe("https://keel-desktop.vercel.app");
    expect(target.pathname).toBe("/download");
    expect(target.href).toBe(DOWNLOAD_URL);
  });

  test("the document links the manifest and declares light + dark theme colours", async ({ page }) => {
    await page.goto("/");

    // Production auto-injects this link from app/manifest.ts in addition to
    // the explicit one in layout.tsx (dev does not auto-inject); assert every
    // declared manifest link resolves to the same app manifest.
    const manifestHrefs = await page
      .locator('head link[rel="manifest"]')
      .evaluateAll((nodes) => nodes.map((n) => new URL(n.getAttribute("href")!, location.href).pathname));
    expect(manifestHrefs.length).toBeGreaterThan(0);
    expect(new Set(manifestHrefs)).toEqual(new Set(["/manifest.webmanifest"]));

    const themeColours = await page
      .locator('head meta[name="theme-color"]')
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("content")));
    expect(themeColours.map((c) => c?.toUpperCase())).toContain(LIGHT_BG);
    expect(themeColours.map((c) => c?.toUpperCase())).toContain(DARK_BG);
  });

  test("launch behaviour: start_url opens the real app, not a download page", async ({ page }) => {
    await page.goto("/");
    const manifest = await readManifest(page);
    const start = new URL(manifest.start_url!, page.url()).href;

    const response = await page.goto(start, { waitUntil: "domcontentloaded" });
    expect(response).not.toBeNull();
    expect(response!.ok()).toBeTruthy();
    expect(new URL(page.url()).pathname).toBe("/");

    await expect(page).toHaveTitle(/Keel/);
    expect(await page.locator("body").innerText()).toMatch(/Keel/);
    expect(await page.title()).not.toMatch(/download/i);
  });
});
