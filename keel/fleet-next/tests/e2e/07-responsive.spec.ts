import { test, expect, DESTINATIONS, gotoDestination, openApp, type DestinationId } from "./fixtures";

const VIEWPORTS = [
  { name: "360x800", width: 360, height: 800 },
  { name: "390x844", width: 390, height: 844 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1440x900", width: 1440, height: 900 },
] as const;

async function expectDestinationVisible(
  page: import("@playwright/test").Page,
  id: DestinationId,
) {
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

for (const vp of VIEWPORTS) {
  test.describe(`viewport ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const dest of DESTINATIONS) {
      test(`${dest.id}: screenshot and no document-level horizontal overflow`, async ({
        page,
        consoleErrors,
      }) => {
        void consoleErrors;
        await openApp(page);
        await gotoDestination(page, dest);
        // Let bridge data settle before capturing a truthful screenshot.
        await page.waitForTimeout(350);

        const metrics = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
        }));
        expect(
          metrics.scrollWidth,
          `${vp.name} ${dest.id}: document.scrollWidth must not exceed innerWidth ` +
            `(${metrics.scrollWidth} > ${metrics.innerWidth})`,
        ).toBeLessThanOrEqual(metrics.innerWidth);

        // Capture evidence first: even if a destination has a visibility
        // defect (e.g. D-E2E-005 at 1024), the screenshot still documents it.
        await page.screenshot({
          path: `tests/e2e/screenshots/${vp.name}/${dest.id}.png`,
          animations: "disabled",
        });
        await expectDestinationVisible(page, dest.id);
      });
    }
  });
}
