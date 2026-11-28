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
  "chrome-web-store",
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

test("short-route stubs redirect to the product pages without inline code", () => {
  for (const [route, destination] of [["cowork", "/product/cowork"], ["keel-code", "/product/keel-code"]]) {
    const html = fs.readFileSync(path.join(SITE, route, "index.html"), "utf8");
    assert.ok(html.includes(`<meta http-equiv="refresh" content="0; url=${destination}" />`), `${route}: meta refresh`);
    assert.ok(html.includes(`rel="canonical" href="https://keel-desktop.vercel.app${destination}"`), `${route}: canonical`);
    assert.ok(html.includes(`data-redirect="${destination}"`), `${route}: JS redirect target`);
    assert.ok(html.includes('src="/ui/route-redirect.js"'), `${route}: external redirect script`);
    assert.ok(html.includes(`href="${destination}"`), `${route}: accessible link`);
    assert.ok(!/<script(?![^>]*\bsrc=)|<style[\s>]|\son(click|load|error)=\s*["']/i.test(html), `${route}: no inline code`);
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

test("QA server also serves the physical short-route stubs", async () => {
  for (const [route, destination] of [["/cowork/index.html", "/product/cowork"], ["/keel-code/index.html", "/product/keel-code"]]) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.match(await response.text(), new RegExp(`data-redirect="${destination.replace(/\//g, "\\/")}"`));
  }
});
