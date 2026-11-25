/* QA-owned static server for the published `keel/site` tree.
 *
 * It reproduces the parts of vercel.json that affect the distribution journey
 * (redirects, rewrites, response headers) so browser tests exercise the REAL
 * site files rather than a reimplementation. It never writes to the site tree.
 * The download-manifest API is deliberately NOT emulated here: its real
 * handler is exercised directly in 05-api-contract.spec.ts, and browser tests
 * mock only the network responses at the page boundary with page.route().
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE = path.resolve(process.env.KEEL_QA_SITE_DIR || path.resolve(HERE, "../../../site"));
const PORT = Number(process.env.KEEL_QA_PORT || 3310);

const config = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
const redirects = config.redirects || [];
const rewrites = config.rewrites || [];
const globalHeaders = (config.headers || []).find((h) => h.source === "/(.*)")?.headers || [];

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".zip": "application/zip",
};

function matchRule(rules, pathname) {
  const hit = rules.find((r) => r.source === pathname);
  return hit ? hit.destination : null;
}

let swVersionOverride = "";

const server = http.createServer((req, res) => {
  let pathname;
  try {
    pathname = new URL(req.url, `http://127.0.0.1:${PORT}`).pathname;
  } catch {
    res.writeHead(400).end("bad request");
    return;
  }

  // QA-only control: change the SW version served by /sw.js so an update
  // check can be driven deterministically. Never written to the site tree.
  if (pathname === "/__qa_set_sw_version") {
    swVersionOverride = new URL(req.url, `http://127.0.0.1:${PORT}`).searchParams.get("v") || "";
    res.writeHead(200, { "Content-Type": "text/plain", "Cache-Control": "no-store" }).end(swVersionOverride || "reset");
    return;
  }

  // Vercel order: redirects first (browser-visible), then rewrites (internal).
  const redirect = matchRule(redirects, pathname);
  if (redirect) {
    res.writeHead(307, { Location: redirect, ...Object.fromEntries(globalHeaders.map((h) => [h.key, h.value])) }).end();
    return;
  }
  const rewritten = matchRule(rewrites, pathname) || pathname;

  let rel = decodeURIComponent(rewritten).replace(/^\/+/, "");
  if (rel === "") rel = "index.html";
  const file = path.resolve(SITE, rel);
  if (file !== SITE && !file.startsWith(SITE + path.sep)) {
    res.writeHead(403).end("forbidden");
    return;
  }

  let body;
  try {
    body = fs.readFileSync(file);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain" }).end("not found");
    return;
  }

  const headers = {
    "Content-Type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream",
    "Cache-Control": "no-store",
    ...Object.fromEntries(globalHeaders.map((h) => [h.key, h.value])),
  };

  // Update-behaviour test: serve a different SW version on demand without
  // touching the source file. This is test scaffolding, not a product change.
  const requestedVersion = process.env.KEEL_QA_SW_VERSION || swVersionOverride;
  if (pathname === "/sw.js" && requestedVersion) {
    body = Buffer.from(
      body.toString("utf8").replace(/keel-shell-v\d+/, `keel-shell-v${requestedVersion}`)
    );
  }
  // Deterministic installer fixture for the no-installer-caching checks.
  if (pathname === "/qa-installer.exe") {
    body = Buffer.from("QA-FAKE-INSTALLER-DO-NOT-CACHE");
    headers["Content-Type"] = "application/octet-stream";
  }

  res.writeHead(200, headers).end(body);
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`distribution-qa static server on http://127.0.0.1:${PORT} serving ${SITE}\n`);
});
