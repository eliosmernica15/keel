import { test, expect, openApp, expectBridgeOnline } from "./fixtures";

test("initial launch renders the unified shell and reaches the real bridge", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);

  await expect(page.locator(".keel-brand__name")).toHaveText("Keel");
  await expect(page.getByRole("tab", { name: "Cowork", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.locator("aside[aria-label='Main navigation']")).toBeVisible();
  await expect(page.locator("#main")).toBeVisible();
  await expectBridgeOnline(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toHaveCount(0);
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
});

test("first-run onboarding overlay can be closed immediately", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await page.goto("/");

  const overlay = page.locator(".keel-onboarding-layer");
  await expect(overlay).toBeVisible();
  const dialog = page.getByRole("dialog", { name: "Welcome to Keel" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Step 1 of 8")).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Start with Cowork/ })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Start with Code/ })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Set up Fleet/ })).toBeVisible();
  await page.screenshot({
    path: "tests/e2e/screenshots/onboarding/first-run.png",
    animations: "disabled",
  });

  await dialog.getByRole("button", { name: "Close setup" }).click();
  await expect(overlay).toHaveCount(0);
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("keel-onboarding-done")))
    .toBe("true");
});

test("onboarding choice, skip, resume after reload and Escape completion", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await page.goto("/");

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /Start with Code/ }).click();

  await expect(dialog.getByRole("heading", { name: "How Keel works" })).toBeVisible();
  await expect(dialog.getByText("Step 2 of 8")).toBeVisible();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: code");

  await dialog.getByRole("button", { name: "Skip for now" }).click();
  await expect(dialog.getByRole("heading", { name: "Connect a provider" })).toBeVisible();
  await expect(dialog.getByText("Step 3 of 8")).toBeVisible();

  // D-E2E-006 is fixed: the persisted step survives a reload without a React
  // hydration mismatch, and completion survives a second reload.
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("keel-onboarding:step")))
    .toBe('"provider"');
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Connect a provider" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
  await expectBridgeOnline(page);
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("keel-onboarding-done")))
    .toBe("true");
});
