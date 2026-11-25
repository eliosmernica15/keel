import { test, expect, openApp } from "./fixtures";

/**
 * The desktop deep link used by the packaged app: /#settings-privacy.
 * Verifies against the production build that the shell opens Settings and the
 * Privacy & data design renders its bridge-backed content.
 */
test("FIXTURE: /#settings-privacy opens the Privacy & data screen", async ({ page }) => {
  await openApp(page);
  await page.goto("/#settings-privacy", { waitUntil: "domcontentloaded" });
  await page.reload(); // fresh load with no persisted surface, as in a new EXE install

  await expect(page.getByRole("heading", { name: "Privacy & data", exact: true }).first())
    .toBeVisible();
  await expect(page.getByText("Usage reported by the bridge", { exact: true }))
    .toBeVisible();
  await expect(page.getByText("Storage, retention and export", { exact: true }))
    .toBeVisible();
  await expect(page.locator('aside[aria-label="Settings navigation"]')
    .getByRole("button", { name: /Privacy & data/ })).toBeVisible();
});

test("FIXTURE: Privacy reload re-queries the bridge through the BFF", async ({ page }) => {
  await openApp(page);
  await page.goto("/#settings-privacy", { waitUntil: "domcontentloaded" });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Privacy & data", exact: true }).first())
    .toBeVisible();

  const calls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/bridge/")) calls.push(r.url());
  });
  await page.getByRole("button", { name: "Reload" }).click();
  await expect.poll(() => calls.some((u) => u.includes("usage"))).toBe(true);
});
