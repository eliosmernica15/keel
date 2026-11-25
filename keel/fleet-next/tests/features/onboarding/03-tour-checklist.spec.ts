import { test, expect, wizard } from "./fixtures";

async function openShellWithChecklist(page: import("@playwright/test").Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("keel-onboarding-done", "true");
    localStorage.removeItem("keel-onboarding:step");
    localStorage.removeItem("keel-onboarding:checklist");
  });
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
}

test("checklist and command palette restart the tour at the tour step", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openShellWithChecklist(page);
  const checklist = page.locator("section[aria-label='Setup checklist']");
  await expect(checklist).toBeVisible();

  // The checklist's tour item is a real action, not a silent page navigation.
  await checklist.getByRole("button", { name: /Take the tour \(optional\)/ }).click();
  await expect(wizard(page).getByRole("heading", { name: "Take the tour" })).toBeVisible();
  await expect(wizard(page).getByText("Step 8 of 8")).toBeVisible();

  // "Restart tour" replays the tour instead of dropping back to Welcome.
  await wizard(page).getByRole("button", { name: "Restart tour" }).click();
  await expect(wizard(page).getByRole("heading", { name: "Take the tour" })).toBeVisible();
  await expect(wizard(page).getByText("Step 8 of 8")).toBeVisible();
  await wizard(page).getByRole("button", { name: "Close setup" }).click();
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);

  // Help command does the same from the command palette.
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette.getByLabel("Search commands").fill("Take the tour");
  await palette.getByRole("button", { name: "Take the tour", exact: true }).click();
  await expect(wizard(page).getByRole("heading", { name: "Take the tour" })).toBeVisible();

  // Tour rows only narrate; they never start a run or an approval.
  const before = bridge.calls.length;
  await wizard(page).getByRole("button", { name: /Inspect tool activity/ }).click();
  await expect(page.locator(".keel-notices")).toContainText("expand the work-log steps to see the tools Keel actually called");
  expect(bridge.calls.slice(before).filter((c) => c.method === "POST")).toHaveLength(0);
});

test("checklist items navigate to real destinations and Review setup reopens the wizard", async ({
  page, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openShellWithChecklist(page);
  const checklist = page.locator("section[aria-label='Setup checklist']");

  await checklist.getByRole("button", { name: /Connect a provider/ }).click();
  await expect(page.locator("aside[aria-label='Main navigation'] .keel-nav-item.is-active")).toHaveText("Settings");

  await checklist.getByRole("button", { name: /Choose a workspace/ }).click();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: code");

  await checklist.getByRole("button", { name: "Review setup" }).click();
  await expect(wizard(page).getByRole("heading", { name: "Welcome to Keel" })).toBeVisible();
  await expect(wizard(page).getByText("Step 1 of 8")).toBeVisible();
});
