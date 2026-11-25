import { test, expect, openApp } from "./fixtures";

test("dark, light and system themes switch and persist across reload", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await page.emulateMedia({ colorScheme: "dark" });
  await openApp(page);

  const html = page.locator("html");
  const themeTab = (name: string) =>
    page.locator(".keel-right").getByRole("tab", { name, exact: true });

  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(themeTab("Dark")).toHaveAttribute("aria-selected", "true");

  await themeTab("Light").click();
  await expect(html).toHaveAttribute("data-theme", "light");
  await expect(page.locator(".keel-statusbar")).toContainText("Theme: light");
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("keel-theme-v2")))
    .toBe('"light"');
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await themeTab("System").click();
  await expect(html).toHaveAttribute("data-theme", "dark"); // emulated OS = dark
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("keel-theme-v2")))
    .toBe('"system"');

  await page.emulateMedia({ colorScheme: "light" });
  await expect(html).toHaveAttribute("data-theme", "light"); // follows OS change live
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "light");

  await themeTab("Dark").click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
});

test("top bar theme toggle flips dark/light and persists", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
