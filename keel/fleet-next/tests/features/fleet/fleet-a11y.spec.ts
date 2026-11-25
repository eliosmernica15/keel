import {
  test, expect, openApp, gotoTop, routeFleetBridge, BOARD_TASKS,
} from "./fixtures";

async function openFleet(page: import("@playwright/test").Page) {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
}

test("Fleet section tabs use roving tabindex and arrow/Home/End keyboard navigation", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page);
  await openFleet(page);

  const agents = page.getByRole("tab", { name: /^Agents/ });
  const groups = page.getByRole("tab", { name: /^Groups/ });
  const board = page.getByRole("tab", { name: /^Board/ });
  const audit = page.getByRole("tab", { name: /Decision history/ });
  await expect(agents).toHaveAttribute("tabindex", "0");
  await expect(board).toHaveAttribute("tabindex", "-1");

  await agents.press("ArrowRight");
  await expect(groups).toBeFocused();
  await expect(groups).toHaveAttribute("tabindex", "0");
  await expect(agents).toHaveAttribute("tabindex", "-1");

  await page.keyboard.press("ArrowRight"); // Tasks
  await page.keyboard.press("ArrowRight"); // Board
  await expect(board).toBeFocused();
  await expect(board).toHaveAttribute("tabindex", "0");
  await expect(page.getByRole("heading", { name: "Task board" })).toBeVisible();

  await page.keyboard.press("End");
  await expect(audit).toBeFocused();
  await expect(page.getByRole("heading", { name: "Decision history" })).toBeVisible();

  await page.keyboard.press("Home");
  await expect(agents).toBeFocused();
  await expect(agents).toHaveAttribute("tabindex", "0");
  // Keyboard focus is visibly outlined, not merely programmatically set.
  await expect(agents).toHaveCSS("outline-style", "solid");
  await expect(agents).toHaveCSS("outline-width", "2px");
});

test("Keyboard-only board status change posts the real update payload with a visible focus ring", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { tasks: BOARD_TASKS });
  await openFleet(page);
  await page.getByRole("tab", { name: /^Board/ }).click();

  const status = page.getByLabel("Move Fix import to status");
  const assignee = page.getByLabel("Assign Fix import");
  await expect(status).toHaveAttribute("aria-label", "Move Fix import to status");
  await expect(assignee).toHaveAttribute("aria-label", "Assign Fix import");

  // Reach the status selector with Shift+Tab (no mouse), verify focus is
  // visible, then change the value from the keyboard only.
  await assignee.evaluate((el) => (el as HTMLElement).focus());
  await page.keyboard.press("Shift+Tab");
  await expect(status).toBeFocused();
  await expect(status).toHaveCSS("outline-style", "solid");
  await expect(status).toHaveCSS("outline-width", "2px");

  await page.keyboard.press("ArrowDown");
  const update = fixture.calls.find((c) => c.path === "tasks/t4/update");
  expect(update?.method).toBe("POST");
  expect(update?.body).toEqual({ status: "cancelled" });
});

test("Keyboard-only board assignment posts the real assign payload", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { tasks: BOARD_TASKS });
  await openFleet(page);
  await page.getByRole("tab", { name: /^Board/ }).click();

  const status = page.getByLabel("Move Publish notes to status");
  const assignee = page.getByLabel("Assign Publish notes");
  await status.evaluate((el) => (el as HTMLElement).focus());
  await page.keyboard.press("Tab");
  await expect(assignee).toBeFocused();
  await expect(assignee).toHaveCSS("outline-style", "solid");

  await page.keyboard.press("ArrowDown");
  const assign = fixture.calls.find((c) => c.path === "tasks/t3/assign");
  expect(assign?.method).toBe("POST");
  expect(assign?.body).toEqual({ assigned_bot_id: "b_beta" });
});

test("Unavailable banners are announced and empty-state actions are keyboard reachable", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, { rows: { b_alpha: [], b_beta: [], b_child: [] } });
  await openFleet(page);

  await page.getByRole("tab", { name: /^Cost/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Not reported by bridge" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "No agent reported any usage rows" })).toBeVisible();

  await page.getByRole("tab", { name: /Delegation map/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Organization hierarchy is unavailable from the bridge." })).toBeVisible();
  const recheck = page.getByRole("button", { name: "Recheck delegation rows" });
  await recheck.evaluate((el) => (el as HTMLElement).focus());
  // Move away and back with the keyboard so :focus-visible applies (the
  // shared global rule covers buttons inside the shared EmptyState).
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(recheck).toBeFocused();
  await expect(recheck).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(recheck).toBeEnabled();
});
