import { chromium } from "@playwright/test";
import { test, expect, openAppThemed, zoomMetrics, applyPageScaleFactor } from "./helpers";

// Playwright's runner injects deviceScaleFactor=1 into every browser context;
// clearing it lets the Chromium launch flag below take effect in the test.
test.use({ deviceScaleFactor: undefined });

/**
 * Capability probe for "real 200% browser zoom" on this host.
 *
 * Chromium exposes two zoom-ish controls, but neither reflows the CSS layout
 * the way Ctrl/+ does in a real browser. These tests record the exact
 * behaviour (no CDP error, concrete metrics) instead of claiming otherwise.
 * The reflow-equivalent evidence is kept in 03-css-viewport-proxy.spec.ts.
 */
test("CDP Emulation.setPageScaleFactor(2) is accepted but does not reflow layout", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  const before = await zoomMetrics(page);
  const cdp = await page.context().newCDPSession(page);
  let commandResult = "";
  let commandError = "";
  try {
    commandResult = JSON.stringify(
      await cdp.send("Emulation.setPageScaleFactor", { pageScaleFactor: 2 }),
    );
  } catch (error) {
    commandError = String(error);
  }
  await page.waitForTimeout(80);
  const after = await zoomMetrics(page);
  await cdp.detach();

  console.log(
    "CDP_ZOOM_PROBE",
    JSON.stringify({ command: "Emulation.setPageScaleFactor({pageScaleFactor:2})", commandResult, commandError, before, after }),
  );
  expect(commandError, `CDP command failed: ${commandError}`).toBe("");
  // The command is accepted and halves the *visual* viewport...
  expect(after.vvScale).toBe(2);
  expect(after.vvWidth).toBeCloseTo(after.innerWidth / 2, 0);
  expect(after.vvHeight).toBeCloseTo(after.innerHeight / 2, 0);
  // ...but it leaves the layout viewport, DPR and scroll width untouched.
  expect(after.innerWidth).toBe(before.innerWidth);
  expect(after.dpr).toBe(before.dpr);
  expect(after.scrollWidth).toBe(before.scrollWidth);
});

test("Chromium --force-device-scale-factor=2 raises DPR but keeps CSS layout", async () => {
  // A persistent context plus deviceScaleFactor:undefined is required: the
  // runner otherwise injects deviceScaleFactor=1, which overrides the launch
  // flag and rejects viewport:null with the exact error recorded in the doc.
  const context = await chromium.launchPersistentContext("", {
    headless: true,
    args: ["--force-device-scale-factor=2", "--disable-features=LocalNetworkAccessChecks"],
    viewport: null,
    deviceScaleFactor: undefined,
  });
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    await page.goto(
      "data:text/html,<meta name=viewport content='width=device-width,initial-scale=1'><div style='width:2000px'>wide</div>",
    );
    const before = await zoomMetrics(page);
    await applyPageScaleFactor(page, 2);
    const after = await zoomMetrics(page);
    console.log(
      "FORCE_DSF_PROBE",
      JSON.stringify({ launchArg: "--force-device-scale-factor=2", before, after }),
    );
    expect(before.dpr, "launch flag must actually take effect").toBe(2);
    expect(before.vvScale).toBe(1);
    expect(before.scrollWidth).toBeGreaterThan(before.innerWidth); // layout not reflowed
    expect(after.vvScale).toBe(2);
    expect(after.vvWidth).toBeCloseTo(before.innerWidth / 2, 0);
    expect(after.innerWidth).toBe(before.innerWidth);
  } finally {
    await context.close();
  }
});
