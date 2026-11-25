import type { Page } from "@playwright/test";

export const VIEWPORTS = [
  { name: "360x800", width: 360, height: 800 },
  { name: "390x844", width: 390, height: 844 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1440x900", width: 1440, height: 900 },
] as const;

export const DESTINATIONS = [
  { id: "cowork", label: "Cowork" },
  { id: "code", label: "Code" },
  { id: "duet", label: "Duet" },
  { id: "fleet", label: "Fleet" },
  { id: "capabilities", label: "Capabilities" },
  { id: "settings", label: "Settings" },
] as const;

export type Destination = (typeof DESTINATIONS)[number];

export interface OpenOptions {
  /** `null` means: deliberately leave keel-theme-v2 absent (system default). */
  theme?: "dark" | "light" | "system" | null;
  /** Inject a probe that records the HTML-parsed theme before React hydrates. */
  capturePaint?: boolean;
}

/**
 * Open the shell with onboarding complete. Unlike the older a11y helper this
 * can leave the theme key absent, which is the case the pre-paint script calls
 * "fall back to system scheme".
 */
export async function openApp(page: Page, opts: OpenOptions = {}): Promise<void> {
  const theme = opts.theme === undefined ? "dark" : opts.theme;
  if (opts.capturePaint) {
    await page.route("**/", async (route) => {
      const response = await route.fetch();
      const body = (await response.text()).replace(
        "</head>",
        `<script>window.__keelPaint = {
  theme: document.documentElement.dataset.theme || null,
  colorScheme: document.documentElement.style.colorScheme || null,
  reducedMotion: document.documentElement.dataset.reducedMotion || null
};</script></head>`,
      );
      await route.fulfill({
        status: response.status(),
        headers: { "content-type": "text/html; charset=utf-8" },
        body,
      });
    });
  }
  await page.addInitScript((value: "dark" | "light" | "system" | null) => {
    try {
      localStorage.setItem("keel-onboarding-done", "true");
      if (value === null) localStorage.removeItem("keel-theme-v2");
      else localStorage.setItem("keel-theme-v2", JSON.stringify(value));
    } catch {
      /* storage disabled */
    }
  }, theme);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".keel-app").waitFor({ state: "visible" });
  // AppProvider applies theme/reduced-motion in a post-mount effect.
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
  await page.locator("html[data-theme]").waitFor({ state: "attached" });
}

export async function paintProbe(page: Page): Promise<{
  theme: string | null; colorScheme: string | null; reducedMotion: string | null;
}> {
  return page.evaluate(() => (window as unknown as {
    __keelPaint: { theme: string | null; colorScheme: string | null; reducedMotion: string | null };
  }).__keelPaint);
}

export async function gotoDestination(page: Page, dest: Destination): Promise<void> {
  const four = ["cowork", "code", "duet", "fleet"];
  if (four.includes(dest.id)) {
    await page.getByRole("tab", { name: dest.label, exact: true }).first().click({ force: true });
  } else {
    const sidebar = page.locator("aside.keel-sidebar");
    if (await page.evaluate(() => window.innerWidth <= 1100)) {
      if (!(await sidebar.evaluate((el) => el.classList.contains("is-open")))) {
        await page.getByRole("button", { name: "Toggle sidebar" }).click();
        await page.waitForTimeout(250);
      }
    }
    await page.locator('aside[aria-label="Main navigation"]')
      .getByRole("button", { name: dest.label, exact: true })
      .click({ force: true });
  }
}
