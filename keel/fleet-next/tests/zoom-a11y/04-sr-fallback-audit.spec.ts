import {
  test,
  expect,
  DESTINATIONS,
  gotoDestination,
  openAppThemed,
  accessibilityTree,
  semanticAudit,
  focusDescriptor,
  focusIdentity,
} from "./helpers";

/**
 * Screen-reader *fallback* audit. Chromium's accessibility tree is the same
 * platform tree that NVDA/JAWS/VoiceOver read, so it is inspected directly
 * with CDP Accessibility.getFullAXTree. This does not replace a real
 * screen-reader walkthrough (documented in docs/UI-ZOOM-A11Y.md) — it closes
 * the deterministic, automatable part of the criterion.
 */
for (const theme of ["dark", "light"] as const) {
  test(`${theme}: semantic landmarks, headings, names and live regions at all six destinations`, async ({
    page,
    consoleErrors,
  }) => {
    void consoleErrors;
    await openAppThemed(page, theme);
    const rows: Array<Record<string, unknown>> = [];
    for (const dest of DESTINATIONS) {
      await gotoDestination(page, dest);
      const dom = await semanticAudit(page);
      expect(dom.landmarks, `${dest.id}: header/main/footer/nav landmarks`).toEqual({
        header: 1, main: 1, footer: 1, nav: 1,
      });
      expect(dom.headings.length, `${dest.id}: main heading`).toBeGreaterThan(0);
      expect(dom.unnamed, `${dest.id}: accessible names`).toEqual([]);
      expect(dom.live.length, `${dest.id}: DOM live regions`).toBeGreaterThan(0);
      expect(
        dom.live.some((r) => r.live === "polite" || r.role === "status" || r.role === "alert" || r.role === "log"),
        `${dest.id}: a live/status/alert/log region must exist`,
      ).toBeTruthy();

      const ax = await accessibilityTree(page);
      expect(
        ax.some((n) => n.role === "heading" && n.name.length > 0),
        `${dest.id}: AX tree exposes a named heading`,
      ).toBeTruthy();
      const liveNodes = ax.filter((n) => n.live === "polite" || n.live === "assertive");
      expect(liveNodes.length, `${dest.id}: AX live regions`).toBeGreaterThan(0);
      const namedButtons = ax.filter((n) => n.role === "button" && n.name.length > 0);
      expect(namedButtons.length, `${dest.id}: named AX buttons`).toBeGreaterThan(3);
      rows.push({
        destination: dest.id,
        landmarks: dom.landmarks,
        headings: dom.headings.length,
        domLiveRegions: dom.live.length,
        axLiveRegions: liveNodes.map((n) => `${n.role}:${n.live}`),
        controls: dom.controls,
      });
    }
    console.log(`SR_FALLBACK_${theme.toUpperCase()}`, JSON.stringify(rows));
  });
}

test("command palette and modal dialog trap focus in both directions and restore it on Escape", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openAppThemed(page, "dark");

  const trigger = page.getByRole("button", { name: "Command palette (Ctrl+K)" });
  await trigger.focus();
  const before = await focusDescriptor(page);
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await expect(palette).toHaveAttribute("aria-modal", "true");
  const insidePalette = () =>
    page.evaluate(() => {
      const panel = document.querySelector("[role='dialog'][aria-label='Command palette']");
      return !!panel && panel.contains(document.activeElement);
    });
  expect(await insidePalette(), "initial focus enters the palette").toBeTruthy();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    expect(await insidePalette(), `Tab ${i} escaped the palette`).toBeTruthy();
  }
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Shift+Tab");
    expect(await insidePalette(), `Shift+Tab ${i} escaped the palette`).toBeTruthy();
  }
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
  expect(focusIdentity(await focusDescriptor(page)), "palette focus restoration").toBe(
    focusIdentity(before),
  );

  await gotoDestination(page, DESTINATIONS[3]);
  const newAgent = page.getByRole("button", { name: "New agent", exact: true }).first();
  await expect(newAgent).toBeVisible();
  await newAgent.focus();
  const beforeDialog = await focusDescriptor(page);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New agent" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  const insideDialog = () =>
    page.evaluate(() => {
      const panel = document.querySelector("[role='dialog'][aria-label='New agent']");
      return !!panel && panel.contains(document.activeElement);
    });
  expect(await insideDialog(), "initial focus enters the dialog").toBeTruthy();
  for (let i = 0; i < 24; i++) {
    await page.keyboard.press("Tab");
    expect(await insideDialog(), `Tab ${i} escaped the dialog`).toBeTruthy();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(focusIdentity(await focusDescriptor(page)), "dialog focus restoration").toBe(
    focusIdentity(beforeDialog),
  );
});

for (const theme of ["dark", "light"] as const) {
  test(`${theme}: Windows high-contrast / forced-colors mode keeps focus rings and control bounds`, async ({
    page,
    consoleErrors,
  }) => {
    void consoleErrors;
    await page.emulateMedia({ forcedColors: "active" });
    await openAppThemed(page, theme);
    expect(
      await page.evaluate(() => matchMedia("(forced-colors: active)").matches),
      "Chromium must actually be in forced-colors mode",
    ).toBeTruthy();

    const rows: Array<Record<string, unknown>> = [];
    for (const dest of DESTINATIONS) {
      await gotoDestination(page, dest);
      await page.locator("body").press("Tab");
      const ring = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement;
        const s = getComputedStyle(el);
        return {
          tag: el.tagName.toLowerCase(),
          style: s.outlineStyle,
          width: parseFloat(s.outlineWidth),
          color: s.outlineColor,
          forcedColorAdjust: s.forcedColorAdjust,
        };
      });
      expect(ring.style, `${dest.id}: forced-colors outline missing`).not.toBe("none");
      expect(ring.width, `${dest.id}: forced-colors ring too thin`).toBeGreaterThanOrEqual(2);
      const bounds = await page.evaluate(() => {
        const btn = document.querySelector<HTMLElement>(".keel-btn");
        if (!btn) return null;
        const s = getComputedStyle(btn);
        return { width: parseFloat(s.borderTopWidth), style: s.borderTopStyle };
      });
      expect(bounds, `${dest.id}: no button to check forced-colors bounds`).not.toBeNull();
      expect(bounds!.width, `${dest.id}: control border collapsed`).toBeGreaterThanOrEqual(1);
      rows.push({ destination: dest.id, ring, bounds });
    }
    console.log(`FORCED_COLORS_${theme.toUpperCase()}`, JSON.stringify(rows));
  });
}

test("prefers-contrast: more thickens the keyboard focus ring", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await page.emulateMedia({ contrast: "more" });
  await openAppThemed(page, "dark");
  await page.locator("body").press("Tab");
  const width = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    return parseFloat(getComputedStyle(el).outlineWidth);
  });
  expect(width, "contrast-more must keep a visible, thicker ring").toBeGreaterThanOrEqual(2);
  console.log("PREFERS_CONTRAST_MORE", JSON.stringify({ outlineWidth: width }));
});
