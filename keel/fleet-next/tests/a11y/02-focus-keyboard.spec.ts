import { test, expect, DESTINATIONS, gotoDestination } from "../e2e/fixtures";
import { collectUnnamedControls, focusDescriptor, openAppThemed } from "./helpers";

test("skip link is the first tab stop and keyboard focus stays visible", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  await page.locator("body").press("Tab");
  const first = await focusDescriptor(page);
  expect(first.tag).toBe("a");
  expect(first.text).toContain("Skip to main content");

  const ring = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    const s = getComputedStyle(el);
    return { outlineWidth: s.outlineWidth, outlineStyle: s.outlineStyle };
  });
  expect(
    ring.outlineStyle !== "none" && parseFloat(ring.outlineWidth) > 0,
    `focus ring missing: ${JSON.stringify(ring)}`,
  ).toBeTruthy();

  const seen: string[] = [];
  for (let i = 0; i < 18; i++) {
    await page.keyboard.press("Tab");
    const d = await focusDescriptor(page);
    seen.push(`${d.tag}:${d.label || d.text}`);
    expect(d.visible, `focused element out of view at step ${i}: ${JSON.stringify(d)}`).toBeTruthy();
    expect(
      d.tabindex === null || d.tabindex <= 0,
      `positive tabindex reached at step ${i}: ${JSON.stringify(d)}`,
    ).toBeTruthy();
  }
  expect(new Set(seen).size).toBeGreaterThan(6);
  console.log(`FOCUS ORDER: ${JSON.stringify(seen)}`);
});

test("command palette traps Tab in both directions, Escape closes and restores focus", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  const trigger = page.getByRole("button", { name: "Command palette (Ctrl+K)" });
  await trigger.focus();
  const before = await focusDescriptor(page);
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");

  const inside = async () => page.evaluate(() => {
    const panel = document.querySelector("[role='dialog'][aria-label='Command palette']");
    return !!panel && panel.contains(document.activeElement);
  });
  await page.waitForTimeout(80);
  expect(await inside(), "initial palette focus must enter the dialog").toBeTruthy();
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
  const after = await focusDescriptor(page);
  expect(after, `focus not restored: before=${JSON.stringify(before)} after=${JSON.stringify(after)}`).toEqual(before);
});

test("shared Dialog traps focus, Escape closes and restores focus (Fleet New agent)", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  await gotoDestination(page, { id: "fleet", label: "Fleet" });
  const trigger = page.getByRole("button", { name: "New agent", exact: true }).first();
  await expect(trigger).toBeVisible();
  await trigger.focus();
  const before = await focusDescriptor(page);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New agent" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");

  const inside = async () => page.evaluate(() => {
    const panel = document.querySelector("[role='dialog'][aria-label='New agent']");
    return !!panel && panel.contains(document.activeElement);
  });
  expect(await inside(), "initial dialog focus must enter the dialog").toBeTruthy();
  for (let i = 0; i < 24; i++) {
    await page.keyboard.press("Tab");
    expect(await inside(), `Tab ${i} escaped the dialog`).toBeTruthy();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  const after = await focusDescriptor(page);
  expect(after, `focus not restored: before=${JSON.stringify(before)} after=${JSON.stringify(after)}`).toEqual(before);
});

test("all destinations expose landmarks and programmatically named controls", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  for (const dest of DESTINATIONS) {
    await gotoDestination(page, dest);
    await expect(page.locator("header.keel-topbar")).toBeVisible();
    await expect(page.locator("main#main")).toBeVisible();
    await expect(page.locator("footer.keel-statusbar")).toBeVisible();
    await expect(page.locator("nav[aria-label='Surfaces']")).toBeVisible();
    const unnamed = await collectUnnamedControls(page);
    expect(unnamed, `${dest.id}: ${JSON.stringify(unnamed.slice(0, 10))}`).toEqual([]);
  }
});
