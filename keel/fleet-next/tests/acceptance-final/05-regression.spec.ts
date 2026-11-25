import { openApp, gotoTop, gotoSidebar, expectSurface, expect, test,
  testWithExpectedHttpError, routeAcceptanceBridge, FIXTURE_BOTS } from "./fixtures";

/** Independent regression smoke across all six surfaces with real-shaped fixtures. */
test("Cowork, Code, Duet, Fleet, Capabilities and Settings all render with fixture data", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);

  // Cowork home.
  await expectSurface(page, "cowork");
  await expect(page.getByRole("heading", { name: /A calm place to/ })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message Keel" })).toBeVisible();

  // Code and Duet remain honest about the absent trusted project.
  await gotoTop(page, "Code");
  await expectSurface(page, "code");
  await expect(page.locator('main[aria-label="Code workspace"]')).toBeVisible();
  await expect(page.getByText("No project selected")).toBeVisible();

  await gotoTop(page, "Duet");
  await expectSurface(page, "duet");
  await expect(page.locator('main[aria-label="Duet active workspace"]')).toBeVisible();

  // Fleet uses the fixture roster, not invented agents.
  await gotoTop(page, "Fleet");
  await expectSurface(page, "fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
  for (const bot of FIXTURE_BOTS) {
    await expect(page.getByRole("button", { name: `Select ${bot.name}` })).toBeVisible();
  }

  await gotoSidebar(page, "Capabilities");
  await expectSurface(page, "capabilities");
  await expect(page.getByRole("heading", { name: "Capabilities", exact: true })).toBeVisible();

  await gotoSidebar(page, "Settings");
  await expectSurface(page, "settings");
  await expect(page.locator('aside[aria-label="Settings navigation"]')).toBeVisible();
});

testWithExpectedHttpError("an unavailable bridge is reported honestly on Fleet", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page, { botsUnavailable: true });
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByText("Local bridge unavailable.")).toBeVisible();
  await expect(page.getByText(/No offline placeholder data is shown/)).toBeVisible();
  await expect(page.getByRole("button", { name: `Select ${FIXTURE_BOTS[0].name}` })).toHaveCount(0);
});
