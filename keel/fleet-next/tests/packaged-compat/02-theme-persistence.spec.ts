import type { Page } from "@playwright/test";
import { test, expect, openApp, gotoTop, expectSurface } from "./fixtures";

type Theme = "dark" | "light" | "system";

/**
 * Install a pre-paint probe BEFORE layout.tsx's inline theme script runs.
 * It records every theme the document actually adopts, so a wrong first
 * paint (theme flash) cannot be hidden by a later React correction.
 */
async function probeTheme(page: Page, saved: Theme | null): Promise<void> {
  await page.addInitScript((value: Theme | null) => {
    try {
      if (!sessionStorage.getItem("keel-compat-theme-init")) {
        if (value === null) localStorage.removeItem("keel-theme-v2");
        else localStorage.setItem("keel-theme-v2", JSON.stringify(value));
        localStorage.setItem("keel-onboarding-done", "true");
        sessionStorage.setItem("keel-compat-theme-init", "1");
      }
    } catch { /* storage disabled */ }
    const scope = window as unknown as { __themeFrames?: Array<{ theme: string | null; scheme: string }> };
    scope.__themeFrames = [];
    const observeRoot = (): boolean => {
      const root = document.documentElement;
      if (!root) return false;
      const record = () => {
        scope.__themeFrames?.push({
          theme: root.dataset.theme ?? null,
          scheme: root.style.colorScheme,
        });
      };
      record();
      new MutationObserver(record).observe(root, {
        attributes: true,
        attributeFilter: ["data-theme", "style"],
      });
      return true;
    };
    // addInitScript runs before <html> exists. Watch the Document until the
    // element appears, then observe it so the inline pre-paint script in
    // layout.tsx cannot change a theme without being recorded.
    if (!observeRoot()) {
      const rootWatcher = new MutationObserver(() => {
        if (observeRoot()) rootWatcher.disconnect();
      });
      rootWatcher.observe(document, { childList: true });
    }
  }, saved);
}

async function themeFrames(page: Page): Promise<Array<{ theme: string | null; scheme: string }>> {
  return page.evaluate(() => (window as unknown as {
    __themeFrames?: Array<{ theme: string | null; scheme: string }>;
  }).__themeFrames ?? []);
}

for (const saved of ["dark", "light"] as const) {
  test(`saved ${saved} theme paints correctly on first frame and survives reload`, async ({ page, consoleErrors }) => {
    await probeTheme(page, saved);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".keel-app")).toBeVisible();
    await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });

    const first = await themeFrames(page);
    const observed = first.filter((f) => f.theme !== null);
    expect(observed.length, "the pre-paint script must apply a theme before hydration").toBeGreaterThan(0);
    expect(observed[0].theme, `first painted theme must be ${saved}`).toBe(saved);
    expect(observed.every((f) => f.theme === saved), `theme flashed: ${JSON.stringify(first)}`).toBe(true);
    expect(await page.locator("html").getAttribute("data-theme")).toBe(saved);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".keel-app")).toBeVisible();
    expect(await page.locator("html").getAttribute("data-theme")).toBe(saved);
    const afterReload = (await themeFrames(page)).filter((f) => f.theme !== null);
    expect(afterReload.every((f) => f.theme === saved), `theme flashed after reload: ${JSON.stringify(afterReload)}`).toBe(true);
    expect(consoleErrors).toEqual([]);
  });
}

test("system theme follows the OS scheme on a packaged origin without a stored preference", async ({ page, consoleErrors }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await probeTheme(page, null);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  expect(await page.locator("html").getAttribute("data-theme")).toBe("light");

  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  expect(await page.locator("html").getAttribute("data-theme")).toBe("dark");

  await page.emulateMedia({ colorScheme: "light" });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  expect(await page.locator("html").getAttribute("data-theme")).toBe("light");
  expect(consoleErrors).toEqual([]);
});

test("the theme control persists an explicit choice across reloads", async ({ page, consoleErrors }) => {
  await openApp(page, { theme: "dark" });
  await page.getByRole("button", { name: "Toggle context panel" }).click();
  const themeControl = page.getByRole("tablist", { name: "Theme" });
  await expect(themeControl).toBeVisible();
  await themeControl.getByRole("tab", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(consoleErrors).toEqual([]);
});

test("surface, draft and panel preferences survive a reload on the packaged origin", async ({ page, consoleErrors }) => {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expectSurface(page, "fleet");
  await gotoTop(page, "Cowork");
  const composer = page.getByRole("textbox", { name: "Message Keel" });
  await composer.fill("persisted draft across reload");
  await expect(composer).toHaveValue("persisted draft across reload");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: cowork");
  await expect(page.getByRole("textbox", { name: "Message Keel" })).toHaveValue("persisted draft across reload");
  expect(consoleErrors).toEqual([]);
});
