import { test, expect, openApp, gotoTop, gotoSidebar, expectSurface, BRIDGE_PORT, TOKEN } from "./fixtures";

/** The electron-style runtime: Next standalone server.js, not `next start`. */

test("standalone server.js serves every unified surface with assets and a live BFF", async ({ page, request, consoleErrors }) => {
  let documentResponse: { status: () => number; headers: () => Record<string, string> } | null = null;
  page.on("response", (r) => {
    if (new URL(r.url()).pathname === "/" && !documentResponse) documentResponse = r;
  });
  await openApp(page);
  const response = documentResponse as unknown as { status: () => number; headers: () => Record<string, string> } | null;
  expect(response?.status()).toBe(200);
  const port = new URL(page.url()).port;
  expect(port).not.toBe("3000");
  expect(port).not.toBe(String(BRIDGE_PORT));

  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("default-src 'self'");
  expect(csp).not.toContain("unsafe-eval");

  await expect(page.locator(".keel-app")).toBeVisible();
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
  await expect(page.locator(".keel-statusbar")).toContainText("Bridge online");

  for (const [label, id] of [["Code", "code"], ["Duet", "duet"], ["Fleet", "fleet"]] as const) {
    await gotoTop(page, label);
    await expectSurface(page, id);
  }
  await gotoSidebar(page, "Capabilities");
  await expect(page.locator("#keel-surface-panel")).toHaveAttribute("aria-label", "capabilities");
  await gotoSidebar(page, "Settings");
  await expect(page.locator("#keel-surface-panel")).toHaveAttribute("aria-label", "settings");
  await gotoTop(page, "Cowork");
  await expectSurface(page, "cowork");

  for (const asset of ["/icon.svg", "/icon-192.png", "/sw.js", "/manifest.webmanifest"]) {
    expect((await request.get(`http://127.0.0.1:${port}${asset}`)).ok(), `${asset} missing in standalone runtime`).toBeTruthy();
  }
  expect(consoleErrors).toEqual([]);
});

test("standalone runtime keeps the token server-side and applies the saved theme before paint", async ({ page, consoleErrors }) => {
  await openApp(page, { theme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  const exposed = await page.evaluate((secret) => ({
    html: document.documentElement.outerHTML.includes(secret),
    storage: Object.keys(localStorage).some((k) => localStorage.getItem(k)?.includes(secret) ?? false),
    url: location.href.includes(secret),
  }), TOKEN);
  expect(exposed).toEqual({ html: false, storage: false, url: false });
  expect(consoleErrors).toEqual([]);
});
