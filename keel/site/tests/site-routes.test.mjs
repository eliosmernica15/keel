/* Route/config tests for the friendly Keel site URLs.
 * Run: node --test keel/site/tests/site-routes.test.mjs
 * The QA server is the real serve_keel_site.mjs, so local behaviour is checked
 * against the same rewrite map that production mirrors.
 */
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(SITE, "..", "..");
const SERVER = path.join(REPO, "serve_keel_site.mjs");
const VERCEL = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
const REWRITE_BY_SOURCE = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));

const EXPECTED_REWRITES = {
  "/cowork": "/product/cowork.html",
  "/keel-code": "/product/keel-code.html",
  "/product/keel-duet": "/product/keel-duet.html",
  "/product/overview": "/product-overview.html",
  "/platform/api": "/platform/api.html",
  "/pricing": "/pricing.html",
  "/resources/articles": "/resources/articles/index.html",
  "/resources/articles/introducing-keel-ship": "/resources/articles/introducing-keel-ship/index.html",
  "/resources/articles/introducing-keel-code": "/resources/articles/introducing-keel-code/index.html",
  "/resources/articles/keel-ship-session-format": "/resources/articles/keel-ship-session-format/index.html",
};

const PHYSICAL_INDEXES = [
  "cowork",                       // new short-route redirect stub
  "keel-code",                    // new short-route redirect stub
  "product/cowork",
  "product/keel-code",
  "product/keel-duet",
  "product/overview",
  "platform/api",
  "resources/articles",           // new article index
  "resources/articles/introducing-keel-ship",
  "resources/articles/introducing-keel-code",
  "resources/articles/keel-ship-session-format",
  // chrome-web-store was retired by the upstream direct-install extension flow.
  "keel-in-chrome",
];

const ARTICLES = [
  "introducing-keel-ship",
  "introducing-keel-code",
  "keel-ship-session-format",
];

function localPath(route) {
  return path.join(SITE, route.replace(/^\/+/, ""));
}

function hasPhysicalRoute(route) {
  if (route === "/") return fs.existsSync(path.join(SITE, "index.html"));
  const file = localPath(route);
  if (fs.existsSync(file) && fs.statSync(file).isFile()) return true;
  return fs.existsSync(path.join(file, "index.html"));
}

async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

let serverProcess;
let base;
let serverOutput = "";

before(async () => {
  const port = await freePort();
  serverProcess = spawn(process.execPath, [SERVER], {
    cwd: REPO,
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverProcess.stdout.on("data", (chunk) => { serverOutput += String(chunk); });
  serverProcess.stderr.on("data", (chunk) => { serverOutput += String(chunk); });
  const deadline = Date.now() + 10000;
  while (!serverOutput.includes("Keel QA server") && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 25));
    if (serverProcess.exitCode !== null) break;
  }
  assert.match(serverOutput, /Keel QA server/, "QA server did not start");
  base = `http://127.0.0.1:${port}`;
});

after(async () => {
  if (serverProcess && serverProcess.exitCode === null) {
    serverProcess.kill();
    await new Promise((resolve) => serverProcess.once("exit", resolve));
  }
});

test("vercel.json keeps clean rewrites for every fixed route", () => {
  for (const [source, destination] of Object.entries(EXPECTED_REWRITES)) {
    assert.equal(REWRITE_BY_SOURCE.get(source), destination, `rewrite for ${source}`);
  }
});

test("every Vercel rewrite target exists on disk", () => {
  for (const { source, destination } of VERCEL.rewrites) {
    assert.match(destination, /^\//, `${source}: destination must be site-absolute`);
    const target = localPath(destination);
    const file = destination.endsWith("/") ? path.join(target, "index.html") : target;
    assert.ok(fs.existsSync(file) && fs.statSync(file).isFile(),
      `${source}: rewrite target missing: ${destination}`);
  }
});

test("every physical route index exists", () => {
  for (const route of PHYSICAL_INDEXES) {
    const index = path.join(SITE, route, "index.html");
    assert.ok(fs.existsSync(index) && fs.statSync(index).isFile(), `missing route index: ${route}/index.html`);
  }
});

test("every clean route resolves with a trailing slash too", () => {
  const sources = new Set(VERCEL.rewrites.map((item) => item.source));
  for (const { source } of VERCEL.rewrites) {
    if (source.endsWith("/")) continue;
    const physical = path.join(SITE, source.replace(/^\//, ""), "index.html");
    const hasSlashRewrite = sources.has(`${source}/`);
    const hasIndex = fs.existsSync(physical) && fs.statSync(physical).isFile();
    assert.ok(hasSlashRewrite || hasIndex,
      `${source}/ has neither a rewrite nor a physical index`);
  }
});

test("static assets are cacheable instead of revalidating on every visit", () => {
  const cacheRules = VERCEL.headers.filter((h) =>
    h.headers.some((entry) => entry.key.toLowerCase() === "cache-control"));
  for (const prefix of ["/ui/(.*)", "/assets/(.*)", "/screenshots/(.*)"]) {
    const rule = cacheRules.find((h) => h.source === prefix);
    assert.ok(rule, `${prefix}: missing cache-control header`);
    const value = rule.headers.find((e) => e.key.toLowerCase() === "cache-control").value;
    assert.match(value, /max-age=[1-9]/, `${prefix}: assets must be cached`);
  }
});

test("short routes serve the full product page design, not a redirect stub", () => {
  for (const [route, title] of [
    ["cowork", "KEEL Cowork"],
    ["keel-code", "Keel Code"],
  ]) {
    const html = fs.readFileSync(path.join(SITE, route, "index.html"), "utf8");
    const canonical = fs.readFileSync(
      path.join(SITE, "product", route === "cowork" ? "cowork" : "keel-code", "index.html"),
      "utf8");
    assert.equal(html, canonical, `${route}: short route must match the product page design`);
    assert.ok(html.includes(`<title>${title}`) || html.includes(title),
      `${route}: product page title present`);
    assert.ok(!html.includes("Moving to "), `${route}: no redirect stub`);
    assert.ok(!html.includes("route-redirect.js"), `${route}: no redirect script`);
  }
});

test("article clean URLs have top-level .html copies of their tracked pages", () => {
  for (const article of ARTICLES) {
    const copy = path.join(SITE, "resources", "articles", `${article}.html`);
    const index = path.join(SITE, "resources", "articles", article, "index.html");
    assert.ok(fs.existsSync(copy) && fs.statSync(copy).isFile(), `missing copy: ${article}.html`);
    assert.equal(fs.readFileSync(copy, "utf8"), fs.readFileSync(index, "utf8"), `${article}: copy matches index`);
  }
});

test("sitemap URLs have a matching rewrite or physical route", () => {
  const xml = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");
  const locs = [...xml.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/g)].map((m) => m[1]);
  assert.ok(locs.length > 0, "sitemap has no URLs");
  for (const loc of locs) {
    const url = new URL(loc);
    assert.equal(url.host, "keel-desktop.vercel.app", `sitemap host: ${loc}`);
    const route = url.pathname;
    assert.ok(REWRITE_BY_SOURCE.has(route) || hasPhysicalRoute(route),
      `sitemap URL has no route: ${loc}`);
  }
  for (const route of ["/cowork", "/keel-code", "/resources/articles", "/platform/api", "/pricing"]) {
    assert.ok(locs.includes(`https://keel-desktop.vercel.app${route}`), `sitemap missing fixed URL: ${route}`);
  }
});

test("article index lists the three articles using the shared stylesheet", () => {
  const html = fs.readFileSync(path.join(SITE, "resources", "articles", "index.html"), "utf8");
  assert.ok(html.includes('href="/ui/article.css"'), "uses existing article.css");
  assert.ok(!/<script(?![^>]*\bsrc=)|<style[\s>]/i.test(html), "no inline code");
  for (const article of ARTICLES) {
    assert.ok(html.includes(`href="/resources/articles/${article}"`), `links ${article}`);
  }
  const imgs = [...html.matchAll(/src="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
  for (const img of imgs) {
    assert.ok(fs.existsSync(localPath(img)), `missing article image: ${img}`);
  }
});

test("QA server resolves all fixed routes locally", async () => {
  for (const route of Object.keys(EXPECTED_REWRITES)) {
    const response = await fetch(`${base}${route}`);
    const body = await response.text();
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.ok(body.length > 100, `${route}: unexpected empty response`);
  }
});

test("QA server resolves the three previously-404 URLs with real content", async () => {
  const expected = {
    "/cowork": /KEEL Cowork \| KEEL/,
    "/keel-code": /<title>Keel Code[^<]*Hand Keel the work<\/title>/,
    "/resources/articles/introducing-keel-ship": /Introducing Keel Ship \| Keel/,
  };
  for (const [route, title] of Object.entries(expected)) {
    const response = await fetch(`${base}${route}`);
    const body = await response.text();
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.match(body, title, `${route}: unexpected page`);
  }
});

test("QA server also serves the full product design at physical short routes", async () => {
  for (const [route, title] of [["/cowork/index.html", "KEEL Cowork"], ["/keel-code/index.html", "Keel Code"]]) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    const body = await response.text();
    assert.ok(body.includes(title), `${route}: product design title missing`);
    assert.ok(!body.includes("Moving to "), `${route}: still a redirect stub`);
  }
});
