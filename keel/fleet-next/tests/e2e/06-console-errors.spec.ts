import { test, expect, DESTINATIONS, openApp, expectBridgeOnline, gotoDestination } from "./fixtures";

test("no pageerror or console.error while visiting every destination", async ({
  page,
  consoleErrors,
}) => {
  await openApp(page);
  await expectBridgeOnline(page);

  for (const dest of DESTINATIONS) {
    await gotoDestination(page, dest);
    await expect(page.locator("#main")).toBeVisible();
    // Allow lazy bridge loads/SSE connection attempts to surface errors.
    await page.waitForTimeout(400);
  }

  expect(consoleErrors, `browser errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});
