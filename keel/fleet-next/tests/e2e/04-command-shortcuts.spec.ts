import { test, expect, openApp, expectSurface } from "./fixtures";

test("Ctrl+K opens, filters and executes a command palette action", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);

  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  const search = palette.getByRole("textbox", { name: "Search commands" });
  await expect(search).toBeFocused();

  // QA-006: palette results are real buttons inside a role="group", not
  // listbox options. D-E2E-004 is fixed: the typed query now persists.
  await search.fill("Fleet");
  const goToFleet = palette.getByRole("button", { name: "Go to Fleet" });
  await expect(goToFleet).toBeVisible();
  await expect(palette.getByRole("button", { name: "Go to Cowork" })).toHaveCount(0);
  await goToFleet.click();
  await expect(palette).toHaveCount(0);
  await expectSurface(page, "fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();

  // No-match state and Escape are real, testable palette states.
  await page.keyboard.press("Control+k");
  await palette.getByRole("textbox", { name: "Search commands" }).fill("no-such-command-zzz");
  await expect(palette.getByText("No matching commands")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
});

test("keyboard shortcuts 1-4 switch surfaces and [ / \\ toggle panels", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);

  const surfaces = [
    ["1", "cowork"],
    ["2", "code"],
    ["3", "duet"],
    ["4", "fleet"],
  ] as const;
  for (const [key, id] of surfaces) {
    await page.keyboard.press(key);
    await expectSurface(page, id);
  }

  const sidebar = page.locator("aside.keel-sidebar");
  const right = page.locator("aside.keel-right");
  await expect(sidebar).toHaveClass(/is-open/);
  await page.keyboard.press("[");
  await expect(sidebar).not.toHaveClass(/is-open/);
  await page.keyboard.press("[");
  await expect(sidebar).toHaveClass(/is-open/);

  await expect(right).toHaveClass(/is-open/);
  await page.keyboard.press("\\");
  await expect(right).not.toHaveClass(/is-open/);
  await page.keyboard.press("\\");
  await expect(right).toHaveClass(/is-open/);
});

test("number shortcuts do not fire while typing in the composer", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);
  await page.keyboard.press("4");
  await expectSurface(page, "fleet");
  await page.keyboard.press("1");
  await expectSurface(page, "cowork");

  const composer = page.getByRole("textbox", { name: "Message Keel" });
  await composer.click();
  await page.keyboard.press("2");
  await expect(composer).toHaveValue(/2/);
  await expectSurface(page, "cowork");
});
