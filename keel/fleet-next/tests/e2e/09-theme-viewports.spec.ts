import { test, expect, DESTINATIONS, gotoDestination, type DestinationId } from "./fixtures";
import { openAppThemed } from "../a11y/helpers";

const VIEWPORTS = [
  { name: "360x800", width: 360, height: 800 },
  { name: "390x844", width: 390, height: 844 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1440x900", width: 1440, height: 900 },
] as const;

async function expectDestinationVisible(page: import("@playwright/test").Page, id: DestinationId) {
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
      break;
  }
}

/** 6 viewports x 6 destinations x 2 themes = 72 real screenshots. */
for (const theme of ["dark", "light"] as const) {
  for (const vp of VIEWPORTS) {
    test.describe(`${theme} @ ${vp.name}`, () => {
      test.use({ viewport: { width: vp.width, height: vp.height }, colorScheme: theme });

      for (const dest of DESTINATIONS) {
        test(`${dest.id}: screenshot, no overflow, correct theme`, async ({ page, consoleErrors }) => {
          void consoleErrors;
          await openAppThemed(page, theme);
          await gotoDestination(page, dest);
          await page.waitForTimeout(350);

          const metrics = await page.evaluate(() => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            theme: document.documentElement.dataset.theme,
          }));
          expect(metrics.theme, `${theme}/${vp.name}/${dest.id}: wrong rendered theme`).toBe(theme);
          expect(
            metrics.scrollWidth,
            `${theme}/${vp.name}/${dest.id}: overflow ${JSON.stringify(metrics)}`,
          ).toBeLessThanOrEqual(metrics.innerWidth);

          await page.screenshot({
            path: `tests/e2e/screenshots/themes/${theme}/${vp.name}/${dest.id}.png`,
            animations: "disabled",
          });
          await expectDestinationVisible(page, dest.id);
        });
      }
    });
  }
}
