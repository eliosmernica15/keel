import {
  test,
  expect,
  DESTINATIONS,
  gotoDestination,
  openAppThemed,
  zoomMetrics,
  semanticAudit,
  focusDescriptor,
} from "./helpers";

/**
 * True reflow-equivalent evidence for native Ctrl+ / Cmd+ browser zoom.
 *
 * Spec 01 proves that CDP pageScaleFactor and --force-device-scale-factor do
 * NOT change the CSS layout viewport. Chromium's native 200% zoom halves the
 * CSS viewport (1440x900 -> 720x450), so this file keeps that deterministic
 * proxy and now covers BOTH themes, all six destinations, focus and controls.
 */
test.use({ viewport: { width: 720, height: 450 } });

for (const theme of ["dark", "light"] as const) {
  test(`${theme}: 720x450 CSS viewport (200% reflow proxy) — all six destinations`, async ({
    page,
    consoleErrors,
  }) => {
    void consoleErrors;
    await openAppThemed(page, theme);
    const rows: Array<Record<string, unknown>> = [];
    for (const dest of DESTINATIONS) {
      await gotoDestination(page, dest);
      await page.waitForTimeout(120);
      const m = await zoomMetrics(page);
      expect(m.innerWidth, "proxy viewport must be 720 CSS px").toBe(720);
      expect(
        m.scrollWidth,
        `${theme}/${dest.id}: document overflow: ${JSON.stringify(m)}`,
      ).toBeLessThanOrEqual(m.innerWidth);
      expect(
        m.bodyScrollWidth,
        `${theme}/${dest.id}: body overflow: ${JSON.stringify(m)}`,
      ).toBeLessThanOrEqual(m.innerWidth);
      const audit = await semanticAudit(page);
      expect(audit.unnamed, `${dest.id}: unnamed controls`).toEqual([]);
      expect(audit.controls, `${dest.id}: controls`).toBeGreaterThan(5);

      await page.locator("body").press("Tab");
      const focused = await focusDescriptor(page);
      expect(focused.visible, `${dest.id}: focus off-screen`).toBeTruthy();
      expect(focused.ring, `${dest.id}: focus ring missing`).not.toBe("");
      rows.push({
        destination: dest.id,
        innerWidth: m.innerWidth,
        scrollWidth: m.scrollWidth,
        controls: audit.controls,
        firstFocus: `${focused.tag}:${focused.label || focused.text}`,
      });
    }
    console.log(`ZOOM_PROXY_${theme.toUpperCase()}`, JSON.stringify(rows));
  });
}
