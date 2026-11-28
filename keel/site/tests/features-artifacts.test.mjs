/* Route + behaviour-contract tests for the NEW marketing page at
 * /features/artifacts. The existing app page at /artifacts is intentionally
 * left alone and is checked here for continued presence.
 *
 * Run: node --test keel/site/tests/features-artifacts.test.mjs
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
const HTML_PATH = path.join(SITE, "features", "artifacts.html");
const INDEX_PATH = path.join(SITE, "features", "artifacts", "index.html");
const CSS_PATH = path.join(SITE, "ui", "features-artifacts.css");
const JS_PATH = path.join(SITE, "ui", "features-artifacts.js");
const VERCEL_PATH = path.join(SITE, "vercel.json");
const SERVE_PATH = path.join(REPO, "serve_keel_site.mjs");

const html = fs.readFileSync(HTML_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const js = fs.readFileSync(JS_PATH, "utf8");
const vercel = JSON.parse(fs.readFileSync(VERCEL_PATH, "utf8"));
const serveSource = fs.readFileSync(SERVE_PATH, "utf8");
const rewrites = new Map(vercel.rewrites.map((r) => [r.source, r.destination]));

function count(source, pattern) {
  return (source.match(pattern) || []).length;
}

/* ------------------------------ routes ------------------------------ */

test("vercel.json adds both /features/artifacts rewrites", () => {
  assert.equal(rewrites.get("/features/artifacts"), "/features/artifacts.html");
  assert.equal(rewrites.get("/features/artifacts/"), "/features/artifacts.html");
  const newEntries = vercel.rewrites.filter((r) =>
    r.source.startsWith("/features/artifacts") || r.destination === "/features/artifacts.html");
  assert.equal(newEntries.length, 2, "exactly two new rewrite entries");
});

test("QA server mirrors both new rewrites", () => {
  assert.match(serveSource, /'\/features\/artifacts': '\/features\/artifacts\.html'/);
  assert.match(serveSource, /'\/features\/artifacts\/': '\/features\/artifacts\.html'/);
});

test("the existing /artifacts app route is still present and untouched", () => {
  assert.equal(rewrites.get("/artifacts"), "/artifacts.html");
  assert.equal(rewrites.get("/artifacts/"), "/artifacts.html");
  assert.match(serveSource, /'\/artifacts': '\/artifacts\.html'/);
  assert.match(serveSource, /'\/artifacts\/': '\/artifacts\.html'/);
  assert.ok(fs.existsSync(path.join(SITE, "artifacts.html")), "old app page still exists");
  assert.match(fs.readFileSync(path.join(SITE, "artifacts.html"), "utf8"), /<title>Keel — Artifacts<\/title>/);
  for (const preserved of [
    "/download", "/login", "/pricing", "/product/overview", "/platform/api",
    "/resources/articles", "/cowork", "/keel-code",
  ]) {
    assert.ok(rewrites.has(preserved), `preserved rewrite: ${preserved}`);
  }
  assert.ok(vercel.headers.length > 0, "security/cache headers preserved");
  assert.ok(Array.isArray(vercel.redirects), "redirects array preserved");
  assert.ok(!vercel.redirects.some((r) => r.source.includes("features/artifacts")),
    "no extra redirect was added for the new route");
});

test("the new page exists as a top-level file and a byte-identical index", () => {
  assert.ok(fs.existsSync(HTML_PATH) && fs.statSync(HTML_PATH).isFile());
  assert.ok(fs.existsSync(INDEX_PATH) && fs.statSync(INDEX_PATH).isFile());
  assert.equal(html, fs.readFileSync(INDEX_PATH, "utf8"), "copies are byte-identical");
});

test("sitemap advertises the new clean URL", () => {
  const xml = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");
  assert.match(xml, /<loc>https:\/\/keel-desktop\.vercel\.app\/features\/artifacts<\/loc>/);
  assert.match(xml, /<loc>https:\/\/keel-desktop\.vercel\.app\/artifacts<\/loc>/);
});

/* ------------------------------ content ------------------------------ */

test("hero, brand and breadcrumb copy match the design", () => {
  assert.match(html, /<title>Artifacts — Keel<\/title>/);
  assert.match(html, /Docs, decks, and dashboards that come back yours/);
  assert.match(html, /Turn your ideas and data into polished work with a conversation with Keel\./);
  assert.match(html, /Keep it in one place and pick up where you left off—anytime\./);
  assert.match(html, /Get started/);
  assert.match(html, /See plans/);
  assert.match(html, /Features<\/a>\s*<span aria-hidden="true">\/<\/span>\s*<span aria-current="page">Artifacts<\/span>/);
  for (const label of ["Keel Docs", "Keel Slides", "Keel Sheets", "Keel Master", "Keel Deno", "Keel spreadsheets"]) {
    assert.ok(html.includes(label), `artifact type: ${label}`);
  }
});

test("page sections appear in the requested order", () => {
  const ids = [
    "fa-header", "top", "artifact-types", "how-it-works",
    "show-your-numbers", "pitch-and-launch", "keep-team-aligned", "faq", "fa-footer",
  ];
  let previous = -1;
  for (const id of ids) {
    const at = html.indexOf(`id="${id}"`);
    assert.ok(at > previous, `section ${id} is missing or out of order`);
    previous = at;
  }
  assert.match(html, /Smarter spreadsheets with your own data/);
  assert.match(html, /Build your \[project\] board/);
  assert.match(html, /Pitch and launch an idea/);
  assert.match(html, /Workshop your launch/);
  assert.match(html, /Keep the team aligned/);
  assert.match(html, /Plan your next sprint/);
  assert.match(html, /Edit your work[\s\S]*Work with your team[\s\S]*Figure out[\s\S]*Figure out with your data/);
});

test("FAQ contains the required question, filters and more questions", () => {
  assert.match(html, /Are artifacts available to free plan users\?/);
  for (const filter of ["All about Keel", "Plans and billing", "Getting started"]) {
    assert.ok(html.includes(filter), `FAQ filter: ${filter}`);
  }
  assert.ok(count(html, /data-faq-q\b/g) >= 5, "at least five accordion questions");
  assert.equal(count(html, /data-faq-filter=/g), 3, "three FAQ filters");
});

test("no borrowed branding and no /app links", () => {
  for (const [name, source] of [["HTML", html], ["CSS", css], ["JS", js]]) {
    assert.ok(!/claude/i.test(source), `${name} must be fully rebranded to Keel`);
  }
  assert.ok(!/href="\/app(?:\/|"|#|\?)/i.test(html), "no links to /app");
  assert.ok(!/\bhref="\/app\b/i.test(html), "no /app route anywhere");
  assert.ok(!/data:(?:image|text)\//i.test(html), "no big inline data URIs");
});

test("all CTAs point at existing routes", () => {
  assert.ok(html.includes('href="/login"'), "sign-in path used for Get started / Get Keel");
  assert.ok(html.includes('href="/pricing"'), "See plans path");
  assert.ok(html.includes('href="mailto:hello@keel.dev"'), "contact sales is a real mail link");
});

/* ---------------------------- behaviour ---------------------------- */

test("tabs, FAQ and mega menus have real handlers", () => {
  assert.ok(count(html, /data-showcase-tab=/g) >= 12, "twelve showcase tabs");
  assert.match(js, /function initShowcaseTabs/);
  assert.match(js, /setHidden\(panel/);
  assert.match(js, /aria-selected/);

  assert.match(js, /function initFaq/);
  assert.match(js, /data-faq-filter/);
  assert.match(js, /data-faq-q/);

  assert.match(html, /data-menu="product"/);
  assert.match(html, /id="fa-mega-product"/);
  assert.match(js, /function initMegaNav/);
  assert.match(js, /mouseenter/);
  assert.match(js, /Escape/);
  assert.match(js, /aria-hidden/);

  assert.match(js, /function initLanguage/);
  assert.match(js, /function initMobileMenu/);
});

test("reveal, parallax and reduced-motion contract", () => {
  assert.match(js, /new IntersectionObserver/);
  assert.match(js, /observer\.unobserve/);
  assert.match(js, /prefers-reduced-motion: reduce/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /animation: none !important/);
  assert.match(css, /fa-reveal-ready/);
  assert.match(css, /translateY\(14px\)/);
  assert.match(css, /opacity 220ms ease, transform 220ms ease/);
  assert.match(js, /addEventListener\("scroll", frame, \{ passive: true \}\)/);
  assert.match(js, /requestAnimationFrame/);
  assert.match(js, /data-parallax/);
});

test("styles and script are local and deferred", () => {
  assert.ok(html.includes('href="/ui/features-artifacts.css"'));
  assert.ok(html.includes('<script src="/ui/features-artifacts.js" defer></script>'));
  assert.ok(!/https?:\/\/(?!keel-desktop\.vercel\.app)/.test(html.replace(/xmlns="[^"]+"/g, "")),
    "no third-party runtime assets");
});

/* ---------------------------- live route ---------------------------- */

let serverProcess;
let base;
let serverOutput = "";

async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

before(async () => {
  const port = await freePort();
  serverProcess = spawn(process.execPath, [SERVE_PATH], {
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

test("QA server serves the new clean URL, slash variant and physical index", async () => {
  const expected = /Docs, decks, and dashboards that come back yours/;
  for (const route of ["/features/artifacts", "/features/artifacts/", "/features/artifacts/index.html"]) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200`);
    assert.match(await response.text(), expected, `${route}: wrong page`);
  }
});

test("QA server still serves the old /artifacts app page separately", async () => {
  const response = await fetch(`${base}/artifacts`);
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /<title>Keel — Artifacts<\/title>/);
  assert.ok(!body.includes("Docs, decks, and dashboards that come back yours"),
    "old app page must not be replaced by the marketing page");
});
