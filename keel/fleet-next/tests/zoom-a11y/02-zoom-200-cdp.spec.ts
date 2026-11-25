import fs from "node:fs";
import path from "node:path";
import {
  test,
  expect,
  DESTINATIONS,
  gotoDestination,
  openAppThemed,
  zoomMetrics,
  applyPageScaleFactor,
  semanticAudit,
  focusDescriptor,
  type Theme,
} from "./helpers";

const EVIDENCE_DIR = path.join(__dirname, "evidence");

/**
 * Real Chromium zoom-emulation path: CDP Emulation.setPageScaleFactor(2).
 * Spec 01 records that this halves the visual viewport (1440 -> 720 CSS px)
 * without changing the layout viewport; these tests verify the live app under
 * that genuine browser zoom state in BOTH themes at ALL SIX destinations.
 */
for (const theme of ["dark", "light"] as const) {
  test(`${theme} @ 200% CDP page scale: six destinations — no overflow, visible focus, reachable controls`, async ({
    page,
    consoleErrors,
  }) => {
    void consoleErrors;
    await openAppThemed(page, theme);
    await applyPageScaleFactor(page, 2);

    const rows: Array<Record<string, unknown>> = [];
    for (const dest of DESTINATIONS) {
      await gotoDestination(page, dest);
      await page.waitForTimeout(120);
      const m = await zoomMetrics(page);
      // Zoom is genuinely active for this assertion (not just a proxy).
      expect(m.vvScale, `${dest.id}: CDP scale not applied`).toBe(2);
      expect(m.vvWidth, `${dest.id}: visual viewport not halved`).toBeCloseTo(m.innerWidth / 2, 0);
      // No horizontal overflow of the document or the body.
      expect(
        m.scrollWidth,
        `${theme}/${dest.id} document overflow: ${JSON.stringify(m)}`,
      ).toBeLessThanOrEqual(m.innerWidth);
      expect(
        m.bodyScrollWidth,
        `${theme}/${dest.id} body overflow: ${JSON.stringify(m)}`,
      ).toBeLessThanOrEqual(m.innerWidth);

      const audit = await semanticAudit(page);
      expect(audit.landmarks, `${dest.id}: landmarks`).toEqual({
        header: 1, main: 1, footer: 1, nav: 1,
      });
      expect(audit.unnamed, `${dest.id}: unnamed controls`).toEqual([]);
      expect(audit.controls, `${dest.id}: control count`).toBeGreaterThan(5);

      // Keyboard focus is visible at the zoomed scale.
      await page.locator("body").press("Tab");
      const focused = await focusDescriptor(page);
      expect(focused.visible, `${dest.id}: focused element off-screen`).toBeTruthy();
      expect(focused.ring, `${dest.id}: no visible focus ring`).not.toBe("");
      expect(
        focused.tabindex === null || focused.tabindex <= 0,
        `${dest.id}: positive tabindex reached`,
      ).toBeTruthy();

      rows.push({
        destination: dest.id,
        innerWidth: m.innerWidth,
        visualWidth: m.vvWidth,
        scale: m.vvScale,
        scrollWidth: m.scrollWidth,
        bodyScrollWidth: m.bodyScrollWidth,
        controls: audit.controls,
        unnamed: audit.unnamed.length,
        firstFocus: `${focused.tag}:${focused.label || focused.text}`,
        focusRing: focused.ring,
      });
    }
    console.log(`ZOOM200_CDP_${theme.toUpperCase()}`, JSON.stringify(rows));

    // Controls stay reachable without a pointer: keyboard-only navigation and
    // the sidebar drawer both work under the zoomed visual viewport.
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await expect(palette).toBeVisible();
    const input = page.getByRole("textbox", { name: "Search commands" });
    await expect(input).toBeFocused();
    await input.fill("Go to Cowork");
    await expect(page.getByRole("dialog", { name: "Command palette" })).toContainText("Go to Cowork");
    await page.keyboard.press("Enter");
    await expect(page.locator(".keel-statusbar")).toContainText("Surface: cowork");
    // Toggle the sidebar through the same keyboard-only command palette so
    // the assertion does not depend on which element owns focus after a palette
    // command closes. The initial state can be open or closed (persisted), so
    // assert that the command flips it and flips it back.
    const sidebar = page.locator("aside.keel-sidebar");
    const isOpen = async () => (await sidebar.getAttribute("class"))?.includes("is-open") ?? false;
    const initial = await isOpen();
    for (let i = 0; i < 2; i++) {
      await page.keyboard.press("Control+k");
      const toggle = page.getByRole("textbox", { name: "Search commands" });
      await expect(toggle).toBeFocused();
      await toggle.fill("Toggle sidebar");
      await expect(page.getByRole("dialog", { name: "Command palette" })).toContainText("Toggle sidebar");
      await page.keyboard.press("Enter");
      expect(await isOpen(), `sidebar toggle pass ${i + 1} did not change state`).toBe(!initial === (i === 0));
    }

    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCE_DIR, `zoom200-cdp-${theme}.png`) });
  });
}
