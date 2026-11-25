import { test, expect } from "@playwright/test";
import { gotoDestination, openApp } from "./helpers";

/**
 * Visual inspection of the fresh 1280/1440 shots showed the shell Context
 * panel and the Code/Duet feature right panel open simultaneously, leaving the
 * editor only a sliver. These measurements turn that observation into a
 * reproducible, quantified defect.
 */
for (const vp of [
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1440x900", width: 1440, height: 900 },
]) {
  test(`${vp.name}: Code editor keeps a usable minimum width`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await openApp(page, { theme: "dark" });
    await gotoDestination(page, { id: "code", label: "Code" });
    await page.waitForTimeout(250);
    const m = await page.evaluate(() => {
      const w = (sel: string) => {
        const el = document.querySelector(sel);
        return el ? Math.round(el.getBoundingClientRect().width) : null;
      };
      const empty = document.querySelector('main[aria-label="Code workspace"] .keel-empty');
      return {
        viewport: window.innerWidth,
        canvas: w(".keel-canvas"),
        shellRight: w("aside.keel-right"),
        codeMain: w('main[aria-label="Code workspace"]'),
        codeRight: w('aside[aria-label="Code context panels"]'),
        emptyBox: empty ? Math.round(empty.getBoundingClientRect().width) : null,
      };
    });
    console.log(`LAYOUT code ${vp.name}: ${JSON.stringify(m)}`);
    expect(
      m.codeMain,
      `editor squeezed to ${m.codeMain}px at ${vp.name}: ${JSON.stringify(m)}`,
    ).toBeGreaterThanOrEqual(320);
  });
}
