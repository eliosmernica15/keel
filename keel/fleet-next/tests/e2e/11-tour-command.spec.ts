import { test, expect } from "./fixtures";

/**
 * Regression guard for the shell fix requested by the lead: the palette's
 * "Take the product tour" command must point onboarding at the tour step
 * BEFORE reopening the overlay. The order is asserted from real localStorage
 * writes captured in the browser, not from source inspection.
 */
test("palette 'Take the product tour' resumes at the tour step before reopening onboarding", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await page.addInitScript(() => {
    const g = globalThis as typeof globalThis & { __storageLog?: Array<[string, string]> };
    g.__storageLog = [];
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      g.__storageLog?.push([key, value]);
      return original.call(this, key, value);
    };
    // Initial state: onboarding already completed.
    g.__storageLog = [];
    original.call(localStorage, "keel-onboarding-done", "true");
    original.call(localStorage, "keel-theme-v2", JSON.stringify("dark"));
  });
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);

  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette.getByRole("button", { name: /Take the product tour/ }).click();

  await expect(palette).toHaveCount(0);
  await expect(page.locator(".keel-onboarding-layer")).toBeVisible();
  await expect(page.getByText(/A short walkthrough of real controls/)).toBeVisible();

  const log = await page.evaluate(() =>
    (globalThis as typeof globalThis & { __storageLog?: Array<[string, string]> }).__storageLog ?? [],
  );
  const stepAt = log.findIndex(([key, value]) => key === "keel-onboarding:step" && value === JSON.stringify("tour"));
  const doneAt = log.findIndex(([key, value]) => key === "keel-onboarding-done" && value === "false");
  console.log(`TOUR COMMAND storage log: ${JSON.stringify(log.filter(([k]) => k.startsWith("keel-onboarding")))}`);
  expect(stepAt, `no tour step write in ${JSON.stringify(log)}`).toBeGreaterThanOrEqual(0);
  expect(doneAt, `no onboarding reopen write in ${JSON.stringify(log)}`).toBeGreaterThanOrEqual(0);
  expect(stepAt, "restartAtStep('tour') must run before restartOnboarding()").toBeLessThan(doneAt);
});
