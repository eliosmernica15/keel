import { test, expect } from "@playwright/test";
import { gotoDestination, openApp } from "./helpers";

/** Focused re-check of shared primitives on surfaces the older a11y suite did
 *  not use for them (Settings reset dialog, Code resize separator). */

test("Settings: labelled TextField, visible focus ring and shared Dialog trap/Escape/restore", async ({ page }) => {
  await openApp(page, { theme: "dark" });
  await gotoDestination(page, { id: "settings", label: "Settings" });

  // type="search" maps to the ARIA searchbox role, not textbox.
  const search = page.getByRole("searchbox", { name: "Search settings" });
  await expect(search).toBeVisible();
  const labelInfo = await search.evaluate((el: HTMLInputElement) => ({
    id: el.id,
    htmlFor: !!document.querySelector(`label[for="${CSS.escape(el.id)}"]`),
    labelText: document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent?.trim(),
  }));
  expect(labelInfo.htmlFor, `label binding: ${JSON.stringify(labelInfo)}`).toBe(true);
  expect(labelInfo.labelText).toBe("Search settings");

  await search.focus();
  const ring = await search.evaluate((el) => {
    const s = getComputedStyle(el);
    return { width: parseFloat(s.outlineWidth), style: s.outlineStyle, color: s.outlineColor };
  });
  expect(ring.style).not.toBe("none");
  expect(ring.width, JSON.stringify(ring)).toBeGreaterThan(0);
  console.log(`SETTINGS FOCUS RING: ${JSON.stringify(ring)}`);

  // Settings opens on Providers; the reset panel is a separate nav section.
  await page.locator('aside[aria-label="Settings navigation"]')
    .getByRole("button", { name: "Reset to defaults" })
    .click();
  const trigger = page.getByRole("button", { name: "Preview reset…" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Preview reset" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  const inside = () => page.evaluate(() => {
    const panel = document.querySelector("[role='dialog'][aria-label='Preview reset']");
    return !!panel && panel.contains(document.activeElement);
  });
  expect(await inside(), "initial focus enters the Dialog").toBe(true);
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press("Tab");
    expect(await inside(), `Tab ${i} escaped the shared Dialog`).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  console.log("SETTINGS DIALOG: 20 Tabs trapped, Escape closed, focus restored");
});

test("Code: ResizeHandle is a keyboard-operable separator with live value", async ({ page }) => {
  await openApp(page, { theme: "dark" });
  await gotoDestination(page, { id: "code", label: "Code" });
  const handles = page.locator('[role="separator"][aria-label="Resize project explorer"]');
  await expect(handles).toHaveCount(1);
  const handle = handles.first();
  await expect(handle).toBeFocused().catch(() => undefined);
  await handle.focus();
  const before = Number(await handle.getAttribute("aria-valuenow"));
  const min = Number(await handle.getAttribute("aria-valuemin"));
  const max = Number(await handle.getAttribute("aria-valuemax"));
  expect(Number.isFinite(before) && Number.isFinite(min) && Number.isFinite(max)).toBe(true);
  await page.keyboard.press("ArrowRight");
  const after = Number(await handle.getAttribute("aria-valuenow"));
  expect(after, `ArrowRight must widen within ${min}..${max}`).toBeGreaterThan(before);
  expect(after).toBeLessThanOrEqual(max);
  await page.keyboard.press("Home");
  expect(Number(await handle.getAttribute("aria-valuenow"))).toBe(min);
  console.log(`RESIZE HANDLE: ${before} -> ${after} -> ${min} (range ${min}..${max})`);
});
