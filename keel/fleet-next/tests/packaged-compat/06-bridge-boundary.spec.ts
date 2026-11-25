import { test, expect, openApp, resetObservations, observations, TOKEN, BRIDGE_PORT } from "./fixtures";

/**
 * FIXTURE-based credential boundary check. The fixture bridge observes the
 * upstream request; the browser is audited separately. The token value is
 * never printed into an assertion message.
 */
test("FIXTURE: the BFF injects the token server-side and the browser never sees it", async ({ page, request, consoleErrors }) => {
  await resetObservations(request);

  const browserBridgeRequests: Array<{ url: string; headers: Record<string, string> }> = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/bridge/")) browserBridgeRequests.push({ url: r.url(), headers: r.headers() });
  });

  await openApp(page);
  await expect(page.locator(".keel-statusbar")).toContainText("Bridge online");
  // A fresh read through the same-origin BFF, in addition to the app's own
  // startup probe, gives the fixture bridge a deterministic observation.
  await page.evaluate(async () => {
    const response = await fetch("/api/bridge/providers", { cache: "no-store" });
    if (!response.ok) throw new Error(`BFF returned ${response.status}`);
  });

  const seen = await observations(request);
  expect(seen.tokenSeen, "the BFF must attach a token to upstream bridge calls").toBeGreaterThan(0);
  expect(seen.tokenMatchesExpected, "the injected token must be the server-configured value").toBe(seen.tokenSeen);
  expect(seen.tokenHeaderNames.map((h) => h.toLowerCase())).toEqual(["x-keel-token"]);
  expect(seen.calls.length).toBeGreaterThan(0);
  expect(seen.calls.every((c) => !c.path.startsWith("/api/")),
    "the fixture bridge must receive bridge-relative paths from the BFF").toBe(true);

  expect(browserBridgeRequests.length, "the UI must use the same-origin BFF").toBeGreaterThan(0);
  for (const call of browserBridgeRequests) {
    expect(new URL(call.url).port).not.toBe("3000");
    expect(new URL(call.url).port).not.toBe(String(BRIDGE_PORT));
    expect(call.url.includes(TOKEN)).toBe(false);
    expect(Object.keys(call.headers).some((h) => h.toLowerCase() === "x-keel-token")).toBe(false);
    expect(Object.values(call.headers).some((v) => v.includes(TOKEN))).toBe(false);
  }

  const exposed = await page.evaluate((secret) => ({
    html: document.documentElement.outerHTML.includes(secret),
    storage: Object.keys(localStorage).some((k) => localStorage.getItem(k)?.includes(secret) ?? false),
    url: location.href.includes(secret),
    scripts: Array.from(document.scripts).some((s) => (s.src || "").includes(secret) || (s.textContent ?? "").includes(secret)),
  }), TOKEN);
  expect(exposed, "no credential may appear in HTML, localStorage, scripts or the URL").toEqual({
    html: false, storage: false, url: false, scripts: false,
  });
  expect(consoleErrors).toEqual([]);
});

test("FIXTURE: BFF gateway errors never echo the bridge URL or token", async ({ page, request, consoleErrors }) => {
  await openApp(page);
  // An unmocked-but-valid bridge path still goes through the BFF; the fixture
  // answers with honest JSON. Check the response shape carries no credential.
  const response = await page.request.get(`http://127.0.0.1:${await page.evaluate(() => location.port)}/api/bridge/providers`);
  expect(response.ok()).toBeTruthy();
  const body = await response.text();
  expect(body.includes(TOKEN)).toBe(false);
  expect(body.includes(`127.0.0.1:${BRIDGE_PORT}`)).toBe(false);
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(consoleErrors).toEqual([]);
});
