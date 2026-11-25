import { test, expect, openApp, gotoDestination } from "./fixtures";

/**
 * Agent G independent QA — hydration-gate control for the four a11y failures
 * observed in the 2026-11-24 full re-run.
 *
 * tests/a11y/helpers.ts::openAppThemed waits only for server-rendered markup
 * (`.keel-app`, `html[data-theme]`), while tests/e2e/fixtures.ts::openApp also
 * waits for `html[data-reduced-motion]`, which is set by AppProvider's mount
 * effect (lib/state.tsx:107) and is therefore a real hydration gate.
 *
 * These tests repeat the a11y assertions through the robust fixture. Passing
 * here while the a11y suite fails isolates fixture drift, not an app defect.
 */
test("QA control: command palette opens, traps Tab, Escape restores focus", async ({ page }) => {
  await openApp(page);
  const trigger = page.getByRole("button", { name: "Command palette (Ctrl+K)" });
  await trigger.focus();
  const before = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    return `${el.tagName}:${el.getAttribute("aria-label") ?? el.textContent?.trim()}`;
  });
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");

  const inside = () =>
    page.evaluate(() => {
      const panel = document.querySelector("[role='dialog'][aria-label='Command palette']");
      return !!panel && panel.contains(document.activeElement);
    });
  // app/page.tsx:76 focuses the input in setTimeout(...,0); poll instead of
  // sampling immediately so the control is not a race against that timer.
  await page.waitForFunction(() => {
    const panel = document.querySelector("[role='dialog'][aria-label='Command palette']");
    return !!panel && panel.contains(document.activeElement);
  });
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("Tab");
    expect(await inside(), `Tab ${i} escaped the palette`).toBeTruthy();
  }
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Shift+Tab");
    expect(await inside(), `Shift+Tab ${i} escaped the palette`).toBeTruthy();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  const after = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    return `${el.tagName}:${el.getAttribute("aria-label") ?? el.textContent?.trim()}`;
  });
  expect(after).toBe(before);
});

test("QA control: Fleet New agent dialog traps focus and restores on Escape", async ({ page }) => {
  await openApp(page);
  await gotoDestination(page, { id: "fleet", label: "Fleet" });
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: fleet");
  const trigger = page.getByRole("button", { name: "New agent", exact: true }).first();
  await expect(trigger).toBeVisible();
  await trigger.focus();
  const before = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    return `${el.tagName}:${el.getAttribute("aria-label") ?? el.textContent?.trim()}`;
  });
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New agent" });
  await expect(dialog).toBeVisible();
  const inside = () =>
    page.evaluate(() => {
      const panel = document.querySelector("[role='dialog'][aria-label='New agent']");
      return !!panel && panel.contains(document.activeElement);
    });
  // components/ui.tsx:342 focuses the first control in setTimeout(...,0).
  await page.waitForFunction(() => {
    const panel = document.querySelector("[role='dialog'][aria-label='New agent']");
    return !!panel && panel.contains(document.activeElement);
  });
  for (let i = 0; i < 24; i++) {
    await page.keyboard.press("Tab");
    expect(await inside(), `Tab ${i} escaped the dialog`).toBeTruthy();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  const after = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    return `${el.tagName}:${el.getAttribute("aria-label") ?? el.textContent?.trim()}`;
  });
  expect(after).toBe(before);
});

test.describe("QA control at 200% zoom (720x450 CSS viewport)", () => {
  test.use({ viewport: { width: 720, height: 450 } });

  test("sidebar toggle opens then Escape closes", async ({ page }) => {
    await openApp(page);
    await gotoDestination(page, { id: "fleet", label: "Fleet" });
    await expect(page.locator(".keel-statusbar")).toContainText("Surface: fleet");
    const trigger = page.getByRole("button", { name: "Toggle sidebar" });
    await trigger.click();
    await expect(page.locator("aside.keel-sidebar")).toHaveClass(/is-open/);
    await page.keyboard.press("Escape");
    await expect(page.locator("aside.keel-sidebar")).not.toHaveClass(/is-open/);
  });

  test("number shortcuts reach all four work surfaces", async ({ page }) => {
    await openApp(page);
    for (const [key, surface] of [
      ["2", "code"],
      ["3", "duet"],
      ["4", "fleet"],
      ["1", "cowork"],
    ] as const) {
      await page.locator("body").press(key);
      await expect(page.locator(".keel-statusbar")).toContainText(`Surface: ${surface}`);
    }
  });
});
