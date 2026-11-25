import { test, expect } from "@playwright/test";
import { DESTINATIONS, VIEWPORTS, gotoDestination, openApp } from "./helpers";

/**
 * Fresh screenshots for every documented viewport × surface × theme. Existing
 * 09-theme-viewports.spec.ts does the same in the e2e suite; this QA-owned copy
 * re-captures this round into tests/quality/screenshots so the images inspected
 * here are provably current, not last round's artefacts.
 */
for (const theme of ["dark", "light"] as const) {
  for (const vp of VIEWPORTS) {
    test.describe(`${theme} @ ${vp.name}`, () => {
      test.use({ viewport: { width: vp.width, height: vp.height }, colorScheme: theme });

      for (const dest of DESTINATIONS) {
        test(`${dest.id}: fresh shot, no overflow, correct theme`, async ({ page }) => {
          await openApp(page, { theme });
          await gotoDestination(page, dest);
          await page.waitForTimeout(350);
          const metrics = await page.evaluate(() => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            scrollHeight: document.documentElement.scrollHeight,
            innerHeight: window.innerHeight,
            theme: document.documentElement.dataset.theme,
            surface: document.querySelector(".keel-statusbar")?.textContent ?? "",
          }));
          expect(metrics.theme, `${theme}/${vp.name}/${dest.id}: wrong theme`).toBe(theme);
          expect(
            metrics.scrollWidth,
            `${theme}/${vp.name}/${dest.id}: horizontal overflow ${JSON.stringify(metrics)}`,
          ).toBeLessThanOrEqual(metrics.innerWidth);
          expect(
            metrics.surface,
            `${theme}/${vp.name}/${dest.id}: wrong surface`,
          ).toContain(`Surface: ${dest.id}`);

          const dir = `tests/quality/screenshots/${theme}/${vp.name}`;
          await page.screenshot({ path: `${dir}/${dest.id}.png`, animations: "disabled" });
          console.log(`SHOT ${theme}/${vp.name}/${dest.id}: ${JSON.stringify(metrics)}`);
        });
      }
    });
  }
}
