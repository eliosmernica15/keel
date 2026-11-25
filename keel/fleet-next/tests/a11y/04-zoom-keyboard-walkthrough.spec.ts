import { test, expect, DESTINATIONS, gotoDestination } from "../e2e/fixtures";
import { collectContrast, openAppThemed } from "./helpers";

// Browser zoom at 200% halves the CSS viewport. Playwright has no native
// zoom control, so the viewport is halved from 1440x900 to 720x450; the
// resulting CSS pixel layout is what a 200%-zoomed browser would paint.
test.use({ viewport: { width: 720, height: 450 } });

test("200% zoom (720x450 CSS viewport): no horizontal overflow on any surface", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  for (const dest of DESTINATIONS) {
    await gotoDestination(page, dest);
    await page.waitForTimeout(200);
    const m = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      bodyScrollWidth: document.body.scrollWidth,
    }));
    expect(
      m.scrollWidth,
      `${dest.id} at 200% zoom: ${JSON.stringify(m)}`,
    ).toBeLessThanOrEqual(m.innerWidth);
  }
});

test("200% zoom keeps text contrast legible and controls operable", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "light");
  await gotoDestination(page, { id: "fleet", label: "Fleet" });
  const result = await collectContrast(page);
  expect(result.violations, JSON.stringify(result.violations.slice(0, 8))).toEqual([]);
  const trigger = page.getByRole("button", { name: "Toggle sidebar" });
  await trigger.click();
  await expect(page.locator("aside.keel-sidebar")).toHaveClass(/is-open/);
  await page.keyboard.press("Escape");
  await expect(page.locator("aside.keel-sidebar")).not.toHaveClass(/is-open/);
});

test("keyboard-only walkthrough reaches all six destinations", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  // Shortcuts 1-4 reach the work surfaces without a pointer.
  const shortcuts: Array<[string, string]> = [
    ["2", "code"], ["3", "duet"], ["4", "fleet"], ["1", "cowork"],
  ];
  for (const [key, surface] of shortcuts) {
    await page.locator("body").press(key);
    await expect(page.locator(".keel-statusbar")).toContainText(`Surface: ${surface}`);
  }
  // Capabilities and Settings are reachable through the command palette.
  for (const [label, id] of [["Capabilities", "capabilities"], ["Settings", "settings"]] as const) {
    await page.keyboard.press("Control+k");
    const input = page.getByRole("textbox", { name: "Search commands" });
    await expect(input).toBeFocused();
    await input.fill(`Open ${label}`);
    await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page.locator(".keel-statusbar")).toContainText(`Surface: ${id}`);
  }
  // Interface shortcuts remain keyboard-only. At this narrow viewport both
  // drawers start closed, so each shortcut must open its own panel.
  await expect(page.locator("aside.keel-sidebar")).not.toHaveClass(/is-open/);
  await page.locator("body").press("[");
  await expect(page.locator("aside.keel-sidebar")).toHaveClass(/is-open/);
  await expect(page.locator("aside.keel-right")).not.toHaveClass(/is-open/);
  await page.locator("body").press("\\");
  await expect(page.locator("aside.keel-right")).toHaveClass(/is-open/);
  console.log("KEYBOARD WALKTHROUGH: 1-4, palette, [, \\ all reached their targets");
});
