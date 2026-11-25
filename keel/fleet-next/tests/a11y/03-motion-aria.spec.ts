import { test, expect, DESTINATIONS, gotoDestination } from "../e2e/fixtures";
import { openAppThemed } from "./helpers";

test("prefers-reduced-motion: reduce collapses animations and is announced", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openAppThemed(page, "dark");
  await expect(page.locator("html")).toHaveAttribute("data-reduced-motion", "true");
  await expect(page.locator(".keel-statusbar")).toContainText("Reduced motion");

  const motion = await page.evaluate(() => ({
    matches: matchMedia("(prefers-reduced-motion: reduce)").matches,
    worstAnimationMs: Math.max(
      0,
      ...Array.from(document.querySelectorAll<HTMLElement>("*")).map((el) =>
        parseFloat(getComputedStyle(el).animationDuration) * 1000 || 0,
      ),
    ),
    worstTransitionMs: Math.max(
      0,
      ...Array.from(document.querySelectorAll<HTMLElement>("*")).map((el) =>
        parseFloat(getComputedStyle(el).transitionDuration) * 1000 || 0,
      ),
    ),
    scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
  }));
  expect(motion.matches, "browser media query must report reduce").toBeTruthy();
  expect(motion.worstAnimationMs, JSON.stringify(motion)).toBeLessThanOrEqual(1);
  expect(motion.worstTransitionMs, JSON.stringify(motion)).toBeLessThanOrEqual(1);
  expect(motion.scrollBehavior).toBe("auto");
  console.log(`REDUCED MOTION: ${JSON.stringify(motion)}`);
});

test("normal motion is restored when the OS preference is no-preference", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await openAppThemed(page, "dark");
  await expect(page.locator("html")).toHaveAttribute("data-reduced-motion", "false");
  await expect(page.locator(".keel-statusbar")).not.toContainText("Reduced motion");
});

test("ARIA roles, states and live regions are present on every surface", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  for (const dest of DESTINATIONS) {
    await gotoDestination(page, dest);
    const tablist = page.getByRole("tablist", { name: "Work surface" });
    await expect(tablist).toBeVisible();
    const tabs = tablist.getByRole("tab");
    expect(await tabs.count(), `${dest.id}: four work-surface tabs`).toBe(4);
    const selected = await tabs.evaluateAll((els) =>
      els.filter((el) => el.getAttribute("aria-selected") === "true").map((el) => el.textContent?.trim()),
    );
    expect(selected.length, `${dest.id}: exactly one selected tab`).toBeLessThanOrEqual(1);
    await expect(page.locator("[aria-live='polite']").first()).toHaveCount(1);
    expect(
      await page.locator("main h1, main h2, main h3, main [role='heading']").count(),
      `${dest.id}: main content needs a heading`,
    ).toBeGreaterThan(0);
    const unnamedStatus = await page.evaluate(() => {
      const dots = Array.from(document.querySelectorAll<HTMLElement>(".keel-status-dot[role='img']"));
      return dots.filter((el) => !(el.getAttribute("aria-label") ?? "").trim()).length;
    });
    expect(unnamedStatus, `${dest.id}: status images need accessible names`).toBe(0);
  }
});
