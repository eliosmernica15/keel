import { expect, test } from "@playwright/test";
import {
  call,
  ok,
  MOCK_BASE,
  PY_BRIDGE_BASE,
  REAL_BASE,
  TOKEN,
  UNCONFIGURED_BASE,
  unique,
} from "./helpers";

test.describe("A — same-origin BFF contract and token isolation", () => {
  test("REAL: direct bridge call without a token is refused; BFF call succeeds", async ({ request }) => {
    const direct = await request.fetch(`${PY_BRIDGE_BASE}/api/fleet/bots`, {
      failOnStatusCode: false,
    });
    expect(direct.status()).toBe(403);
    expect((await direct.json()).refused).toMatch(/token/);

    const viaBff = await call(request, "GET", "bots");
    expect(viaBff.status).toBe(200);
    expect(Array.isArray(viaBff.body.bots)).toBe(true);
  });

  test("REAL: a browser Origin/Referer is stripped so POST is not refused upstream", async ({ request }) => {
    const created = await ok(request, "POST", "bots", {
      name: unique("bff-origin-bot"),
      engine: "echo",
    });
    expect(created.bot.id).toBeTruthy();
    // Forwarding the browser Origin (127.0.0.1:3311) to the bridge
    // (127.0.0.1:8797) would make _origin_ok() reject this POST with 403.
    const result = await call(request, "POST", `bots/${created.bot.id}/cancel`, {}, {
      Origin: "http://evil.example",
      Referer: "http://evil.example/page",
    });
    expect(result.status).toBe(200);
    expect("cancelled" in result.body).toBe(true);
  });

  test("FIXTURE: mock upstream proves token injection and header stripping", async ({ request }) => {
    // FIXTURE only: mock_bridge.py echoes exactly what the BFF sent upstream.
    const result = await call(request, "POST", "echo", { probe: true }, {
      Cookie: `keel_token=wrong-${TOKEN}; session=leak`,
      Origin: "http://evil.example",
      Referer: "http://evil.example/page",
      "X-Custom-Probe": "keep-me",
    }, MOCK_BASE);
    expect(result.status).toBe(200);
    const headers = result.body.headers as Record<string, string>;
    expect(headers["x-keel-token"]).toBe(TOKEN);
    expect(headers["x-custom-probe"]).toBe("keep-me");
    expect(headers.cookie).toBeUndefined();
    expect(headers.origin).toBeUndefined();
    expect(headers.referer).toBeUndefined();
    // The upstream HTTP client legitimately re-adds Host for the target; what
    // must not leak is the *browser's* host (the Next port).
    expect(headers.host).not.toContain("3312");
  });

  test("FIXTURE: unconfigured BFF returns an honest bridge_unavailable envelope", async ({ request }) => {
    // FIXTURE only: a Next process deliberately started without bridge env.
    const result = await call(request, "GET", "bots", undefined, {}, UNCONFIGURED_BASE);
    expect(result.status).toBe(502);
    expect(result.body.error).toBe("bridge_unavailable");
    expect(result.text).not.toContain(TOKEN);
  });

  test("FIXTURE: deterministic upstream statuses are forwarded, not masked", async ({ request }) => {
    const badGateway = await call(request, "GET", "fixture/502", undefined, {}, MOCK_BASE);
    expect(badGateway.status).toBe(502);
    expect(badGateway.body.error).toBe("fixture_gateway");
    const badRequest = await call(request, "GET", "fixture/400", undefined, {}, MOCK_BASE);
    expect(badRequest.status).toBe(400);
    const plainText = await call(request, "GET", "fixture/text", undefined, {}, MOCK_BASE);
    expect(plainText.body).toEqual({ raw: "plain-text-error-from-upstream" });
  });

  test("REAL: path traversal is rejected by the BFF before any upstream call", async ({ request }) => {
    // A literal '..' inside a segment (not a URL-normalised ../) reaches
    // safePath() in route.ts:16 and must return the stable bad_path code.
    const result = await call(request, "GET", "bots/abc..def/rows");
    expect(result.status).toBe(400);
    expect(result.body.error).toBe("bad_path");
  });

  test("REAL: bridge error envelopes pass through unchanged", async ({ request }) => {
    const result = await call(request, "GET", "bots/does-not-exist-4f8c/rows");
    expect(result.status).toBe(404);
    expect(result.body.error).toBe("bot_not_found");
  });

  test("REAL: token never appears in browser HTML, JS/source maps or localStorage", async ({ page, request }) => {
    const leaked: string[] = [];
    page.on("response", async (response) => {
      const url = response.url();
      if (!url.startsWith(REAL_BASE)) return;
      if (!/\.(js|mjs|map|css)(\?|$)/.test(url) && url !== `${REAL_BASE}/`) return;
      try {
        const bytes = await response.body();
        if (bytes.includes(Buffer.from(TOKEN))) leaked.push(url);
      } catch {
        // a response can be cancelled by navigation; ignore
      }
    });

    await page.goto(`${REAL_BASE}/`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);

    const html = await page.content();
    expect(html).not.toContain(TOKEN);
    const storage = await page.evaluate(() => JSON.stringify(Object.entries(localStorage)));
    expect(storage).not.toContain(TOKEN);
    expect(leaked).toEqual([]);

    const apiResult = await call(request, "GET", "bots");
    expect(apiResult.text).not.toContain(TOKEN);
    expect(JSON.stringify(apiResult.headers)).not.toContain(TOKEN);
  });
});
