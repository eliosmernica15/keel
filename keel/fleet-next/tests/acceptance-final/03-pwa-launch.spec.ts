import { expect, test, type Page } from "@playwright/test";

/** PWA download shortcut and app launch/start URL — independent verification. */
type Manifest = {
  name?: string;
  short_name?: string;
  description?: string;
  start_url?: string;
  display?: string;
  background_color?: string;
  theme_color?: string;
  shortcuts?: Array<{ name?: string; url?: string }>;
};

const DOWNLOAD_URL = "https://keel-desktop.vercel.app/download";

async function readManifest(page: Page): Promise<Manifest> {
  // A real document URL is needed to resolve manifest-relative URLs.
  if (page.url() === "about:blank") {
    await page.goto("/", { waitUntil: "domcontentloaded" });
  }
  const response = await page.request.get("/manifest.webmanifest");
  expect(response.ok(), `manifest HTTP ${response.status()}`).toBeTruthy();
  expect(response.headers()["content-type"] || "").toMatch(/manifest\+json|json/i);
  return (await response.json()) as Manifest;
}

test("PWA manifest has one download shortcut and a real app start URL", async ({ page }) => {
  const manifest = await readManifest(page);

  expect(manifest.name).toBe("Keel");
  expect(manifest.short_name).toBe("Keel");
  expect(manifest.display).toBe("standalone");
  expect(manifest.start_url).toBe("/");

  expect(Array.isArray(manifest.shortcuts)).toBeTruthy();
  expect(manifest.shortcuts).toHaveLength(1);
  const shortcut = manifest.shortcuts![0];
  expect(shortcut.name).toBe("Get Keel Desktop");
  expect(shortcut.url).toBe(DOWNLOAD_URL);

  const start = new URL(manifest.start_url!, page.url());
  expect(start.origin).toBe(new URL(page.url()).origin);
  expect(start.pathname).not.toMatch(/download/i);
});

test("launching start_url opens the workspace, never a download page", async ({ page }) => {
  const manifest = await readManifest(page);
  const response = await page.goto(new URL(manifest.start_url!, page.url()).href, { waitUntil: "domcontentloaded" });
  expect(response?.ok()).toBeTruthy();
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page).toHaveTitle(/Keel/);
  expect(new URL(page.url()).pathname).toBe("/");
  expect(await page.title()).not.toMatch(/download/i);
});

test("the document links /manifest.webmanifest (one or more identical hrefs)", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const links = page.locator('head link[rel="manifest"]');
  await expect(links.first()).toBeAttached();
  const count = await links.count();
  const hrefs = await links.evaluateAll((nodes) => nodes.map((n) => n.getAttribute("href")));
  // QA-F-AGENT-003: a manual link and Next's auto-injected link currently
  // duplicate the same href. Same target is harmless for installability but
  // is reported as a hygiene defect in FRONTEND-FINALIZATION-QA.md.
  console.log(`MANIFEST_LINK_COUNT=${count} hrefs=${JSON.stringify(hrefs)}`);
  expect(count).toBeGreaterThanOrEqual(1);
  for (const href of hrefs) {
    expect(new URL(href!, page.url()).pathname).toBe("/manifest.webmanifest");
  }
});

test("a service worker registers for the app scope", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  // PwaRegister registers in a mount effect; wait for real hydration first.
  await expect(page.locator(".keel-app")).toBeVisible();
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
  const diagnostics = await page.evaluate(async () => {
    if (!("serviceWorker" in navigator)) return "no serviceWorker API";
    const registrations = await navigator.serviceWorker.getRegistrations();
    return JSON.stringify(registrations.map((r) => ({
      scope: r.scope,
      active: r.active?.state ?? null,
      installing: r.installing?.state ?? null,
      waiting: r.waiting?.state ?? null,
    })));
  });
  const autoRegistered = diagnostics !== "no serviceWorker API" &&
    (JSON.parse(diagnostics) as Array<{ scope: string }>).some((r) => new URL(r.scope).pathname === "/");
  if (!autoRegistered) {
    const swFetch = await page.evaluate(async () => {
      const r = await fetch("/sw.js", { cache: "no-store" });
      return { status: r.status, type: r.headers.get("content-type") };
    });
    const attempt = await page.evaluate(async () => {
      try {
        const reg = await navigator.serviceWorker.register("/sw.js");
        return { ok: true, scope: reg.scope };
      } catch (error) {
        return { ok: false, error: String(error) };
      }
    });
    console.log(`SW_FALLBACK SW_FETCH=${JSON.stringify(swFetch)} SW_ATTEMPT=${JSON.stringify(attempt)}`);
  }
  console.log(`SW_DIAGNOSTICS=${diagnostics} AUTO_REGISTERED=${autoRegistered}`);
  expect(autoRegistered, `app did not auto-register the service worker: ${diagnostics}`).toBeTruthy();
  // In `next dev` Chromium keeps the registration but reports no active worker
  // (the production PWA suite verifies the active/offline state separately).
  // Here we assert the installability prerequisite: the app itself registers
  // a service worker for the app root scope.
  const registrations = JSON.parse(diagnostics) as Array<{ scope: string }>;
  const root = registrations.find((r) => new URL(r.scope).pathname === "/");
  expect(root, `no SW registration for app scope; diagnostics: ${diagnostics}`).toBeDefined();
  expect(new URL(root!.scope).pathname).toBe("/");
});
