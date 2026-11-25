import { test, expect, DESTINATIONS, gotoDestination } from "../e2e/fixtures";
import { collectContrast, openAppThemed } from "./helpers";

/**
 * Real computed-style WCAG AA contrast checks. The prior matrix row
 * "Contrast audit — not run" is replaced by these measurements.
 */
for (const theme of ["dark", "light"] as const) {
  test(`${theme} theme: computed text contrast >= AA at all six destinations`, async ({
    page,
    consoleErrors,
  }) => {
    void consoleErrors;
    await openAppThemed(page, theme);
    const all: Array<{
      destination: string; checked: number; unknown: number; minRatio: number;
      violations: number; worst: Array<{ text: string; ratio: number; fg: string; bg: string }>;
    }> = [];

    for (const dest of DESTINATIONS) {
      await gotoDestination(page, dest);
      await page.waitForTimeout(250);
      const result = await collectContrast(page);
      expect(
        result.checked,
        `${theme}/${dest.id}: expected measurable text elements`,
      ).toBeGreaterThan(8);
      all.push({
        destination: dest.id,
        checked: result.checked,
        unknown: result.unknown,
        minRatio: result.minRatio,
        violations: result.violations.length,
        worst: result.violations.slice(0, 8).map((v) => ({
          text: v.text, ratio: v.ratio, fg: v.foreground, bg: v.background,
        })),
      });
    }
    console.log(`CONTRAST ${theme}: ${JSON.stringify(all)}`);
    const failing = all.filter((entry) => entry.violations > 0);
    expect(
      failing,
      `${theme}: ${failing.reduce((n, e) => n + e.violations, 0)} AA contrast violations`,
    ).toEqual([]);
  });
}
