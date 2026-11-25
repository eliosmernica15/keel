import type { Page } from "@playwright/test";
import { test, expect, openApp, APP_PORT, DOWNLOAD_URL } from "./fixtures";

type Manifest = {
  name?: string;
  short_name?: string;
  start_url?: string;
  display?: string;
  icons?: Array<{ src?: string }>;
  shortcuts?: Array<{ name?: string; url?: string }>;
};

async function readManifest(page: Page): Promise<{ manifest: Manifest; responseUrl: string }> {
  const response = await page.request.get(`http://127.0.0.1:${APP_PORT}/manifest.webmanifest`);
  expect(response.ok(), `manifest HTTP ${response.status()}`).toBeTruthy();
  expect(response.headers()["content-type"] ?? "").toMatch(/manifest\+json|json/i);
  return { manifest: (await response.json()) as Manifest, responseUrl: response.url() };
}

test("exactly one safe Get Keel Desktop link works on the packaged origin", async ({ page, consoleErrors }) => {
  await openApp(page);

  const control = page.getByRole("link", { name: "Get Keel Desktop" });
  await expect(control).toBeVisible();
  await expect(control).toHaveAttribute("href", DOWNLOAD_URL);
  await expect(control).toHaveAttribute("target", "_blank");
  const rel = (await control.getAttribute("rel") ?? "").split(/\s+/).filter(Boolean);
  expect(rel).toEqual(expect.arrayContaining(["noopener", "noreferrer"]));

  const matches = await page.evaluate(() => Array.from(document.querySelectorAll("a"))
    .filter((a) => /Get Keel Desktop/i.test(a.textContent || a.getAttribute("aria-label") || "")).length);
  expect(matches).toBe(1);
  await expect(page.getByRole("button", { name: "Get Keel Desktop" })).toHaveCount(0);

  // FIXTURE: intercept the external host; no real outbound request is made.
  await page.context().route("https://keel-desktop.vercel.app/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>Keel download (fixture)</title>" }));
  await control.focus();
  const [popup] = await Promise.all([page.waitForEvent("popup"), control.press("Enter")]);
  await popup.waitForLoadState("domcontentloaded");
  expect(popup.url()).toBe(DOWNLOAD_URL);
  await popup.close();
  expect(consoleErrors).toEqual([]);
});

test("PWA manifest start URL and download shortcut are portable to any loopback port", async ({ page, consoleErrors }) => {
  await openApp(page);
  const { manifest, responseUrl } = await readManifest(page);

  expect(manifest.name).toBe("Keel");
  expect(manifest.display).toBe("standalone");
  expect(manifest.start_url).toBe("/");
  expect(manifest.shortcuts).toHaveLength(1);
  expect(manifest.shortcuts![0].name).toBe("Get Keel Desktop");
  expect(manifest.shortcuts![0].url).toBe(DOWNLOAD_URL);

  const start = new URL(manifest.start_url!, responseUrl);
  expect(start.origin).toBe(`http://127.0.0.1:${APP_PORT}`);
  expect(start.pathname).toBe("/");
  expect(start.port).not.toBe("3000");

  for (const icon of manifest.icons ?? []) {
    expect(icon.src).toMatch(/^\//);
    const response = await page.request.get(new URL(icon.src!, responseUrl).href);
    expect(response.ok(), `manifest icon ${icon.src} missing`).toBeTruthy();
  }

  const link = page.locator('head link[rel="manifest"]').first();
  await expect(link).toBeAttached();
  expect(new URL((await link.getAttribute("href"))!, page.url()).pathname).toBe("/manifest.webmanifest");
  expect(consoleErrors).toEqual([]);
});

test("the service worker registers for the app root scope on the packaged origin", async ({ page, consoleErrors }) => {
  await openApp(page);
  await page.waitForFunction(async () => {
    if (!("serviceWorker" in navigator)) return false;
    const registrations = await navigator.serviceWorker.getRegistrations();
    return registrations.some((r) => new URL(r.scope).pathname === "/" && new URL(r.scope).port !== "3000");
  });
  expect(consoleErrors).toEqual([]);
});
