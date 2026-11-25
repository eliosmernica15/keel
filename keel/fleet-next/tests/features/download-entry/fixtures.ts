import { test as base, expect, type Page } from "@playwright/test";

export const test = base;
export { expect };

/**
 * Open the unified application shell with first-run onboarding already done.
 * Bridge calls are answered with minimal real-shaped envelopes so the shell's
 * mount probe and the Cowork event stream stay finite and offline.
 */
export async function openApp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("keel-onboarding-done", "true");
    } catch {
      /* storage disabled */
    }
  });

  await page.route("**/api/bridge/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/bridge\/?/, "");
    if (path === "events") {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
        body: ": ping\n\n",
      });
      return;
    }
    if (path === "providers") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ providers: [], session_keys: [] }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
}
