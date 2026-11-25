import { test, expect } from "@playwright/test";
import { createRequire } from "node:module";
import path from "node:path";
import fs from "node:fs";

const require = createRequire(__filename);
const ROOT = path.resolve(__dirname, "../../..");
const HANDLER = path.join(ROOT, "site/api/download-manifest.js");

type MockRes = {
  statusCode: number;
  headers: Record<string, string>;
  body: string;
  status(s: number): MockRes;
  setHeader(k: string, v: string): void;
  json(o: unknown): MockRes;
  send(s: string): MockRes;
};

function mockRes(): MockRes {
  const res: MockRes = {
    statusCode: 200,
    headers: {},
    body: "",
    status(s) { this.statusCode = s; return this; },
    setHeader(k, v) { this.headers[k] = v; },
    json(o) { this.body = JSON.stringify(o); return this; },
    send(s) { this.body = s; return this; },
  };
  return res;
}

async function invoke(method: string, manifestUrl: string | undefined) {
  const handler = require(HANDLER) as (req: { method: string }, res: MockRes) => Promise<void>;
  const previous = process.env.KEEL_DOWNLOAD_MANIFEST_URL;
  if (manifestUrl === undefined) delete process.env.KEEL_DOWNLOAD_MANIFEST_URL;
  else process.env.KEEL_DOWNLOAD_MANIFEST_URL = manifestUrl;
  const res = mockRes();
  try {
    await handler({ method }, res);
  } finally {
    if (previous === undefined) delete process.env.KEEL_DOWNLOAD_MANIFEST_URL;
    else process.env.KEEL_DOWNLOAD_MANIFEST_URL = previous;
  }
  return res;
}

function withFetch(fn: typeof fetch) {
  const original = globalThis.fetch;
  globalThis.fetch = fn;
  return () => { globalThis.fetch = original; };
}

test.describe("distribution: real /api/download-manifest handler contract", () => {
  test("rejects non-GET methods with 405 Allow: GET", async () => {
    const res = await invoke("POST", undefined);
    expect(res.statusCode).toBe(405);
    expect(res.headers.Allow).toBe("GET");
  });

  test("503 when no upstream is configured (honest empty site)", async () => {
    const res = await invoke("GET", undefined);
    expect(res.statusCode).toBe(503);
    expect(JSON.parse(res.body).error).toBe("manifest_not_configured");
  });

  test("503 for a non-HTTPS or malformed upstream URL", async () => {
    expect((await invoke("GET", "http://example.invalid/m.json")).statusCode).toBe(503);
    expect(JSON.parse((await invoke("GET", "http://example.invalid/m.json")).body).error).toBe("manifest_url_insecure");
    expect((await invoke("GET", "not a url")).statusCode).toBe(503);
  });

  test("502 when upstream is unreachable or non-OK", async () => {
    const restore = withFetch(async () => new Response("nope", { status: 500 }));
    try {
      const res = await invoke("GET", "https://example.invalid/m.json");
      expect(res.statusCode).toBe(502);
      expect(JSON.parse(res.body).error).toBe("manifest_unreachable");
    } finally { restore(); }
  });

  test("502 for oversized, non-JSON and schema-invalid upstream bodies", async () => {
    const cases: Array<[string, string, string]> = [
      ["x".repeat(256 * 1024 + 1), "502", "manifest_too_large"],
      ["{not json", "502", "manifest_not_json"],
      [JSON.stringify({ version: "1" }), "502", "manifest_invalid"],
    ];
    for (const [body, , error] of cases) {
      const restore = withFetch(async () => new Response(body, { status: 200 }));
      try {
        const res = await invoke("GET", "https://example.invalid/m.json");
        expect(res.statusCode).toBe(502);
        expect(JSON.parse(res.body).error).toBe(error);
      } finally { restore(); }
    }
  });

  test("200 with byte-identical body, JSON content type and short revalidation TTL", async () => {
    const body = JSON.stringify({ name: "Keel Desktop", version: "9.9.9", channels: { windows: { available: false } } });
    const restore = withFetch(async () => new Response(body, { status: 200 }));
    try {
      const res = await invoke("GET", "https://example.invalid/m.json");
      expect(res.statusCode).toBe(200);
      expect(res.body).toBe(body);
      expect(res.headers["Content-Type"]).toBe("application/json; charset=utf-8");
      expect(res.headers["Cache-Control"]).toMatch(/max-age=60/);
    } finally { restore(); }
  });

  test("handler source contains no embedded credential or source-repo URL", () => {
    const src = fs.readFileSync(HANDLER, "utf8");
    expect(src).not.toMatch(/ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|PRIVATE KEY/);
    expect(src).not.toMatch(/github\.com\/.*\/blob\//);
  });
});
