import { test, expect } from "@playwright/test";
import { openApp, paintProbe } from "./helpers";

/**
 * Agent F finalization round: Obsidian & Gold identity, all three theme modes,
 * the pre-first-paint theme script and live system-scheme changes. These are
 * the gaps the earlier audit explicitly listed as "implemented (unverified)".
 */

const tokens = () => {
  const cs = getComputedStyle(document.documentElement);
  const get = (name: string) => cs.getPropertyValue(name).trim().toLowerCase();
  return {
    theme: document.documentElement.dataset.theme,
    colorScheme: document.documentElement.style.colorScheme,
    outer: get("--outer"),
    accent: get("--accent"),
    text: get("--text"),
    muted: get("--muted"),
    ok: get("--ok"),
    warn: get("--warn"),
    danger: get("--danger"),
    info: get("--info"),
    bodyFont: getComputedStyle(document.body).fontFamily,
    skipBg: getComputedStyle(document.querySelector(".keel-skip-link")!).backgroundColor,
    skipColor: getComputedStyle(document.querySelector(".keel-skip-link")!).color,
    bodyBgImage: getComputedStyle(document.body).backgroundImage,
  };
};

for (const [theme, expected] of [
  ["dark", { accent: "#e6d54c", outer: "#0a0605", text: "#f2f0ea", skipBg: "rgb(230, 213, 76)" }],
  ["light", { accent: "#8a5a07", outer: "#e9e9e7", text: "#141414", skipBg: "rgb(138, 90, 7)" }],
] as const) {
  test(`${theme}: Obsidian & Gold tokens are the single source of truth`, async ({ page }) => {
    await openApp(page, { theme });
    const t = await page.evaluate(tokens);
    expect(t.theme).toBe(theme);
    expect(t.colorScheme).toBe(theme);
    expect(t.accent).toBe(expected.accent);
    expect(t.outer).toBe(expected.outer);
    expect(t.text).toBe(expected.text);
    expect(t.skipBg, "skip link / primary action carries the gold signal").toBe(expected.skipBg);
    // Gold is a signal, not wallpaper: the large canvas is never a flat gold fill.
    expect(t.bodyBgImage).not.toContain("rgb(230, 213, 76)");
    expect(t.bodyFont).toContain("Inter");
    console.log(`IDENTITY ${theme}: ${JSON.stringify(t)}`);
  });
}

test("theme=system follows prefers-color-scheme and reacts to live OS changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await openApp(page, { theme: "system" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light", { timeout: 5_000 });
  await expect(page.locator(".keel-statusbar")).toContainText(/Surface:/);

  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark", { timeout: 5_000 });
  const t = await page.evaluate(tokens);
  expect(t.accent).toBe("#e6d54c");
  console.log(`SYSTEM THEME: light -> dark, accent=${t.accent}`);
});

test("saved light theme is painted before first paint even when the OS is dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await openApp(page, { theme: "light", capturePaint: true });
  const paint = await paintProbe(page);
  const after = await page.evaluate(() => ({
    theme: document.documentElement.dataset.theme,
    colorScheme: document.documentElement.style.colorScheme,
  }));
  expect(paint, "inline themeInit must run while parsing <head>").not.toBeNull();
  expect(paint.theme).toBe("light");
  expect(paint.colorScheme).toBe("light");
  expect(after).toEqual({ theme: "light", colorScheme: "light" });
  console.log(`PRE-PAINT: ${JSON.stringify(paint)} after=${JSON.stringify(after)}`);
});

test("reduced motion is applied before first paint from the OS preference", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openApp(page, { theme: "light", capturePaint: true });
  const paint = await paintProbe(page);
  expect(paint.reducedMotion).toBe("true");
  await expect(page.locator("html")).toHaveAttribute("data-reduced-motion", "true");
  console.log(`PRE-PAINT MOTION: ${JSON.stringify(paint)}`);
});

test("no saved theme: system scheme is honoured before AND after hydration", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await openApp(page, { theme: null, capturePaint: true });
  const paint = await paintProbe(page);
  const after = await page.evaluate(() => document.documentElement.dataset.theme);
  console.log(`NO STORED THEME: paint=${JSON.stringify(paint)} after=${after}`);
  expect(paint.theme, "pre-paint script falls back to the system scheme").toBe("light");
  expect(
    after,
    "AppProvider must not override the system fallback with a hard-coded dark default",
  ).toBe("light");
});

test("Settings: theme segmented control uses roving tabindex and arrow keys", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await openApp(page, { theme: "dark" });
  await page.locator('aside[aria-label="Main navigation"]')
    .getByRole("button", { name: "Settings", exact: true })
    .click({ force: true });
  // Settings opens on its first section; the theme control lives in Appearance.
  await page.locator('aside[aria-label="Settings navigation"]')
    .getByRole("button", { name: "Appearance", exact: true })
    .click();
  const list = page.getByRole("tablist", { name: "Theme" });
  await expect(list).toBeVisible();
  const tabs = list.getByRole("tab");
  expect(await tabs.count()).toBe(3);
  const tabindexes = await tabs.evaluateAll((els) =>
    els.map((el) => el.getAttribute("tabindex")),
  );
  expect(tabindexes).toEqual(["0", "-1", "-1"]);
  await tabs.first().focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowRight");
  await expect(tabs.nth(2)).toBeFocused();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator(".keel-statusbar")).toContainText(/Surface: settings/);
  console.log("SEGMENTED THEME: dark -> light -> system via ArrowRight");
});
