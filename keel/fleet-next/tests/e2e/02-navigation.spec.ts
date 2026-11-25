import {
  test,
  expect,
  DESTINATIONS,
  openApp,
  expectBridgeOnline,
  gotoTop,
  gotoSidebar,
  expectSurface,
  type DestinationId,
} from "./fixtures";

async function expectDestination(page: import("@playwright/test").Page, id: DestinationId) {
  switch (id) {
    case "cowork":
      await expect(page.getByRole("heading", { name: /A calm place to/ })).toBeVisible();
      break;
    case "code":
      await expect(page.locator('main[aria-label="Code workspace"]')).toBeVisible();
      break;
    case "duet":
      await expect(page.locator('main[aria-label="Duet active workspace"]')).toBeVisible();
      break;
    case "fleet":
      await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
      break;
    case "capabilities":
      await expect(page.getByRole("heading", { name: "Capabilities", exact: true })).toBeVisible();
      break;
    case "settings":
      await expect(page.locator('aside[aria-label="Settings navigation"]')).toBeVisible();
      await expect(page.locator("#main h1").first()).toBeVisible();
      break;
  }
}

test("top bar navigates all four work surfaces (global destinations use the sidebar)", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);
  await expectBridgeOnline(page);

  // The shell intentionally exposes four work surfaces in the top bar;
  // Capabilities and Settings are global destinations in the sidebar.
  await expect(page.getByRole("tablist", { name: "Work surface" }).getByRole("tab")).toHaveCount(4);

  for (const dest of DESTINATIONS.filter((d) => ["cowork", "code", "duet", "fleet"].includes(d.id))) {
    await gotoTop(page, dest.label);
    await expectDestination(page, dest.id);
    await expectSurface(page, dest.id);
    await expect(page.getByRole("tablist", { name: "Work surface" }).getByRole("tab", { name: dest.label, exact: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  }
});

test("sidebar navigates to all six destinations", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openApp(page);
  await expectBridgeOnline(page);

  for (const dest of DESTINATIONS) {
    await gotoSidebar(page, dest.label);
    await expectDestination(page, dest.id);
    if (["cowork", "code", "duet", "fleet"].includes(dest.id)) {
      await expectSurface(page, dest.id);
    }
    await expect(
      page
        .locator('aside[aria-label="Main navigation"]')
        .getByRole("button", { name: dest.label, exact: true }),
    ).toHaveClass(/is-active/);
  }
});

test("active surface survives a reload", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expectSurface(page, "fleet");
  await page.reload();
  await expect(page.locator(".keel-app")).toBeVisible();
  await expectSurface(page, "fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
});
