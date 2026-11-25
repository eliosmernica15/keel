import { openApp, gotoTop, gotoSidebar, expectSurface, expect, test,
  routeAcceptanceBridge } from "./fixtures";

/** Accessibility and keyboard/focus acceptance, independent of other suites' helpers. */
const focusInfo = (page: import("@playwright/test").Page) => page.evaluate(() => {
  const el = document.activeElement as HTMLElement | null;
  return {
    tag: el?.tagName.toLowerCase() ?? "",
    label: el?.getAttribute("aria-label") ?? "",
    text: (el?.textContent ?? "").trim().slice(0, 80),
  };
});

test("skip link is the first tab stop with a visible focus ring", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);
  await page.locator("body").press("Tab");

  const first = await focusInfo(page);
  expect(first.tag).toBe("a");
  expect(first.text).toContain("Skip to main content");

  const ring = await page.evaluate(() => {
    const s = getComputedStyle(document.activeElement as HTMLElement);
    return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) };
  });
  expect(ring.style !== "none" && ring.width > 0, `focus ring missing: ${JSON.stringify(ring)}`).toBeTruthy();
});

test("command palette traps focus, Escape closes and restores the trigger focus", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);

  const trigger = page.getByRole("button", { name: "Command palette (Ctrl+K)" });
  await trigger.focus();
  const before = await focusInfo(page);

  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");

  const inside = () => page.evaluate(() => {
    const panel = document.querySelector("[role='dialog'][aria-label='Command palette']");
    return !!panel && panel.contains(document.activeElement);
  });
  expect(await inside(), "initial focus must enter the palette").toBeTruthy();
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press("Tab");
    expect(await inside(), `Tab ${i} escaped the palette`).toBeTruthy();
  }
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Shift+Tab");
    expect(await inside(), `Shift+Tab ${i} escaped the palette`).toBeTruthy();
  }

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(await focusInfo(page), "focus must return to the trigger").toEqual(before);
});

test("number shortcuts switch surfaces without a mouse", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);

  await page.keyboard.press("2");
  await expectSurface(page, "code");
  await page.keyboard.press("3");
  await expectSurface(page, "duet");
  await page.keyboard.press("4");
  await expectSurface(page, "fleet");
  await page.keyboard.press("1");
  await expectSurface(page, "cowork");
});

test("all destinations expose landmarks and a live status region", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);

  const destinations = [
    ["cowork", "Cowork"], ["code", "Code"], ["duet", "Duet"],
    ["fleet", "Fleet"], ["capabilities", "Capabilities"], ["settings", "Settings"],
  ] as const;
  for (const [id, label] of destinations) {
    if (["cowork", "code", "duet", "fleet"].includes(id)) await gotoTop(page, label);
    else await gotoSidebar(page, label);
    await expectSurface(page, id);
    await expect(page.locator("header.keel-topbar")).toBeVisible();
    await expect(page.locator("main#main")).toBeVisible();
    await expect(page.locator("footer.keel-statusbar")).toBeVisible();
    await expect(page.locator("nav[aria-label='Surfaces']")).toBeVisible();
  }
  // The notice region is intentionally empty/hidden until a notice is posted;
  // assert it exists in the DOM rather than requiring it to be visible.
  await expect(page.locator('[aria-live="polite"]').first()).toHaveCount(1);
});

test("Fleet rewind dialog restores focus to its trigger on Escape", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);
  await gotoTop(page, "Fleet");

  await page.getByRole("button", { name: "Select Alpha" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const drawer = page.getByRole("dialog", { name: "Alpha details" });
  await drawer.getByRole("tab", { name: "Activity / History" }).click();

  const trigger = drawer.getByRole("button", { name: /Rewind transcript/ });
  await trigger.focus();
  const before = await focusInfo(page);
  await trigger.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(await focusInfo(page), "rewind trigger focus must be restored").toEqual(before);
});
