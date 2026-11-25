import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../../.."); // keel/
const SITE = path.join(ROOT, "site");

async function waitForActiveSW(page: import("@playwright/test").Page) {
  await page.waitForFunction(
    () =>
      "serviceWorker" in navigator &&
      navigator.serviceWorker.getRegistration().then((r) => r?.active?.state === "activated"),
    null,
    { timeout: 20_000 }
  );
}

test.describe("distribution: PWA routing, contextual link, offline shell and updates", () => {
  test("site manifest start_url opens the real app, never /download", async ({ page }) => {
    await page.goto("/download");
    const manifestResponse = await page.evaluate(async () => {
      const r = await fetch("/manifest.webmanifest");
      return { ok: r.ok, status: r.status, body: await r.json() };
    });
    expect(manifestResponse.ok, `manifest HTTP ${manifestResponse.status}`).toBeTruthy();
    const manifest = manifestResponse.body;
    expect(manifest.start_url).not.toMatch(/download/i);
    const start = new URL(manifest.start_url, page.url()).href;
    const response = await page.request.get(start);
    expect(response.ok()).toBeTruthy();
    expect(new URL(response.url()).pathname).toBe("/app");
    const html = await response.text();
    expect(html).toMatch(/Keel - Desktop &amp; Code|<title>Keel/);
    expect(html).not.toMatch(/<title>Download Keel/);
  });

  test("vercel routing never redirects /app to /download", async () => {
    const vercel = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
    for (const rule of [...(vercel.rewrites || []), ...(vercel.redirects || [])]) {
      if (!/^\/app(\.html)?$/.test(rule.source)) continue;
      expect(rule.destination, `${rule.source} -> ${rule.destination}`).not.toMatch(/\/download(\.html)?$/);
    }
    expect(vercel.rewrites).toContainEqual({ source: "/download", destination: "/download.html" });
  });

  test("fleet-next PWA manifest does not start on /download", async () => {
    const source = fs.readFileSync(path.join(ROOT, "fleet-next/app/manifest.ts"), "utf8");
    expect(source).not.toMatch(/start_url:\s*["']\/download/);
    expect(source).toMatch(/start_url:/);
  });

  test("in-app contextual link targets /download exactly once", async ({ page }) => {
    await page.goto("/app");
    const links = await page.evaluate(() =>
      Array.from(document.querySelectorAll("a"))
        .filter((a) => new URL((a as HTMLAnchorElement).href, location.href).pathname === "/download")
        .map((a) => ({ href: (a as HTMLAnchorElement).href, text: (a.textContent || "").trim(), id: a.id }))
    );
    expect(links.length, JSON.stringify(links)).toBe(1);
    const target = new URL(links[0].href);
    expect(target.pathname).toBe("/download");
    expect(["https://keel-desktop.vercel.app", new URL(page.url()).origin]).toContain(target.origin);
    await expect(page.locator(`#${links[0].id || "nav-download"}`)).toBeVisible();
  });

  test("offline shell: cached landing page opens with the network down", async ({ page, context }) => {
    await page.goto("/app");
    await waitForActiveSW(page);
    await context.setOffline(true);
    try {
      const response = await page.goto("/", { waitUntil: "domcontentloaded" });
      expect(response).not.toBeNull();
      expect(await page.title()).toMatch(/Keel/);
      expect(await page.locator("body").innerText()).toMatch(/Keel/);
    } finally {
      await context.setOffline(false);
    }
  });

  test("no installer or release-manifest binary is stored in the SW cache", async ({ page, context }) => {
    await page.goto("/app");
    await waitForActiveSW(page);
    const cached = await page.evaluate(async () => {
      // A same-origin installer is the adversarial case: a cross-origin asset
      // is skipped by the origin guard, but a same-origin one must not be kept.
      const r = await fetch("/qa-installer.exe");
      await r.arrayBuffer();
      await fetch("/download.json", { cache: "no-store" });
      await fetch("/api/download-manifest", { cache: "no-store" });
      await new Promise((resolve) => setTimeout(resolve, 700));
      const cache = await caches.open((await caches.keys())[0]);
      return {
        keys: await caches.keys(),
        installer: !!(await cache.match("/qa-installer.exe")),
        manifest: !!(await cache.match("/download.json")),
        api: !!(await cache.match("/api/download-manifest")),
      };
    });
    expect(cached.keys.some((k) => /shell/i.test(k))).toBeTruthy();
    expect(cached.installer, "installer binary must never be cached by the app SW").toBe(false);
    expect(cached.manifest, "release manifest must never be cached by the app SW").toBe(false);
    expect(cached.api, "manifest API must never be cached by the app SW").toBe(false);
  });

  test("SW update installs a new version and removes the old cache", async ({ page }) => {
    await page.goto("/app");
    await waitForActiveSW(page);
    const before = await page.evaluate(() => caches.keys());

    // The QA server can serve a newer sw.js on demand (test scaffolding only).
    const control = await page.request.get("/__qa_set_sw_version?v=99");
    expect(control.ok()).toBeTruthy();
    try {
      await page.evaluate(async () => {
        const reg = await navigator.serviceWorker.getRegistration();
        await reg?.update();
      });
      await page.waitForFunction(
        () => caches.keys().then((keys) => keys.some((k) => k.includes("v99"))),
        null,
        { timeout: 20_000 }
      );
      const after = await page.evaluate(() => caches.keys());
      expect(after).toContain("keel-shell-v99");
      expect(after).not.toContain(before.find((k) => k.includes("v16")) ?? "__none__");
    } finally {
      await page.request.get("/__qa_set_sw_version?v=");
    }
  });
});
