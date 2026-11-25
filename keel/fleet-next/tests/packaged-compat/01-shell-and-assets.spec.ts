import { test, expect, openApp, gotoTop, gotoSidebar, expectSurface, APP_PORT, BRIDGE_PORT, TOKEN } from "./fixtures";

/** All seven unified surfaces must work on a production build at a non-3000 port. */
test("every unified surface opens on the packaged loopback origin with the bridge online", async ({ page, consoleErrors }) => {
  await openApp(page);

  await expect(page.locator(".keel-statusbar")).toContainText("Bridge online");
  await expectSurface(page, "cowork");

  for (const [label, id] of [
    ["Code", "code"],
    ["Duet", "duet"],
    ["Fleet", "fleet"],
  ] as const) {
    await gotoTop(page, label);
    await expectSurface(page, id);
    await expect(page.locator("#keel-surface-panel")).toBeVisible();
  }
  for (const [label, id] of [["Capabilities", "capabilities"], ["Settings", "settings"]] as const) {
    await gotoSidebar(page, label);
    // Capabilities/Settings are destinations, not work surfaces: the status
    // bar keeps the last work surface while the panel heading changes.
    await expect(page.locator("#keel-surface-panel")).toHaveAttribute("aria-label", id);
  }
  await gotoTop(page, "Cowork");
  await expectSurface(page, "cowork");
  await expect(page.locator(".keel-app")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("local assets, CSP and the same-origin BFF all hold on the non-3000 origin", async ({ page, request, consoleErrors }) => {
  const responses: Array<{ url: string; status: number }> = [];
  page.on("response", (r) => responses.push({ url: r.url(), status: r.status() }));

  const navigation = await page.goto("/", { waitUntil: "domcontentloaded" });
  expect(navigation?.status()).toBe(200);
  expect(new URL(page.url()).port).toBe(String(APP_PORT));
  await expect(page.locator(".keel-app")).toBeVisible();
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });

  const csp = navigation?.headers()["content-security-policy"] ?? "";
  expect(csp, `production CSP missing on loopback origin: ${csp}`).toContain("default-src 'self'");
  expect(csp, "development-only unsafe-eval leaked into the production CSP").not.toContain("unsafe-eval");
  expect(navigation?.headers()["x-content-type-options"]).toBe("nosniff");

  // CSS actually applied (not merely present in the DOM) proves the hashed
  // local stylesheet was not blocked by CSP on this port.
  const background = await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(background).not.toBe("rgba(0, 0, 0, 0)");

  for (const asset of ["/icon.svg", "/icon-192.png", "/icon-512.png", "/sw.js", "/manifest.webmanifest"]) {
    const response = await request.get(`http://127.0.0.1:${APP_PORT}${asset}`);
    expect(response.ok(), `${asset} failed on the packaged origin`).toBeTruthy();
  }

  // Every observed browser request stays on the app origin; no absolute
  // localhost:3000 or direct-bridge URL is introduced by the frontend.
  const foreign = responses.filter((r) => new URL(r.url).origin !== `http://127.0.0.1:${APP_PORT}`);
  expect(foreign, `off-origin requests: ${JSON.stringify(foreign)}`).toEqual([]);
  const bridgeDirect = responses.filter((r) => r.url.includes(`127.0.0.1:${BRIDGE_PORT}`));
  expect(bridgeDirect, "browser must reach the bridge only through the same-origin BFF").toEqual([]);

  // The bundle must not embed the server-only bridge credential.
  const scripts = await page.locator('script[src]').evaluateAll((nodes) =>
    nodes.map((n) => (n as HTMLScriptElement).getAttribute("src")).filter((v): v is string => Boolean(v)));
  expect(scripts.length).toBeGreaterThan(0);
  for (const src of scripts) {
    const response = await request.get(new URL(src, page.url()).href);
    expect(response.ok(), `${src} could not be loaded`).toBeTruthy();
    const source = await response.text();
    expect(source.includes(TOKEN), `bridge token leaked in ${src}`).toBe(false);
    expect(source.includes(`127.0.0.1:${BRIDGE_PORT}`), `bridge URL leaked in ${src}`).toBe(false);
  }
  expect(consoleErrors).toEqual([]);
});

test("production hydration is clean on the packaged origin", async ({ page, consoleErrors }) => {
  await openApp(page);
  await expect(page.getByRole("textbox", { name: "Message Keel" })).toBeVisible();
  await expect(page.locator(".keel-statusbar")).toContainText("Bridge online");
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
