/* Route + behaviour-contract tests for the NEW marketplace destination at
 * /marketplace/plugins ("Capabilities → Plugins"). The existing app page at
 * /plugins is intentionally left alone and is checked here for continued
 * presence.
 *
 * Run: node --test keel/site/tests/marketplace-plugins.test.mjs
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
const HTML_PATH = path.join(SITE, "marketplace", "plugins.html");
const INDEX_PATH = path.join(SITE, "marketplace", "plugins", "index.html");
const CSS_PATH = path.join(SITE, "ui", "marketplace-plugins.css");
const JS_PATH = path.join(SITE, "ui", "marketplace-plugins.js");
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

const PLUGIN_NAMES = [
  "Frontend Design", "Superpowers", "Code Review", "Context7", "Code Simplifier",
  "Playwright", "GitHub", "Keel and Management", "Feature Dev", "Security Guidance",
  "Vercel", "TypeScript LSP", "Ralph Loop", "Keel Code Setup", "Commit Commands",
  "Figma", "Supabase", "PR Review Toolkit", "Pyright LSP", "Chrome DevTools",
  "Telegram", "Atlassian MCP", "Slack", "Serena",
];

/* ------------------------------ routes ------------------------------ */

test("vercel.json adds exactly the two /marketplace/plugins rewrites", () => {
  assert.equal(rewrites.get("/marketplace/plugins"), "/marketplace/plugins.html");
  assert.equal(rewrites.get("/marketplace/plugins/"), "/marketplace/plugins.html");
  const newEntries = vercel.rewrites.filter((r) =>
    r.source.startsWith("/marketplace/plugins") || r.destination === "/marketplace/plugins.html");
  assert.equal(newEntries.length, 2, "exactly two new rewrite entries");
});

test("QA server mirrors both new rewrites", () => {
  assert.match(serveSource, /'\/marketplace\/plugins': '\/marketplace\/plugins\.html'/);
  assert.match(serveSource, /'\/marketplace\/plugins\/': '\/marketplace\/plugins\.html'/);
});

test("the existing /plugins route and all other config remain intact", () => {
  assert.equal(rewrites.get("/plugins"), "/plugins.html");
  assert.equal(rewrites.get("/plugins/"), "/plugins.html");
  assert.match(serveSource, /'\/plugins': '\/plugins\.html'/);
  assert.match(serveSource, /'\/plugins\/': '\/plugins\.html'/);

  const oldPage = fs.readFileSync(path.join(SITE, "plugins.html"), "utf8");
  assert.match(oldPage, /<title>Keel — Plugins<\/title>/);
  assert.ok(fs.existsSync(path.join(SITE, "ui", "plugins.css")), "old plugins.css untouched");
  assert.ok(fs.existsSync(path.join(SITE, "ui", "plugins.js")), "old plugins.js untouched");

  for (const preserved of [
    "/download", "/login", "/pricing", "/product/overview", "/platform/api",
    "/resources/articles", "/cowork", "/keel-code", "/features/artifacts",
  ]) {
    assert.ok(rewrites.has(preserved), `preserved rewrite: ${preserved}`);
  }
  assert.ok(vercel.headers.length > 0, "security/cache headers preserved");
  assert.ok(Array.isArray(vercel.redirects), "redirects array preserved");
  assert.ok(!vercel.redirects.some((r) => r.source.includes("marketplace")),
    "no extra redirect was added for the new route");
});

test("the new page exists as a top-level file and a byte-identical index", () => {
  assert.ok(fs.existsSync(HTML_PATH) && fs.statSync(HTML_PATH).isFile());
  assert.ok(fs.existsSync(INDEX_PATH) && fs.statSync(INDEX_PATH).isFile());
  assert.equal(html, fs.readFileSync(INDEX_PATH, "utf8"), "copies are byte-identical");
});

test("sitemap advertises the new clean URL without dropping the old one", () => {
  const xml = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");
  assert.match(xml, /<loc>https:\/\/keel-desktop\.vercel\.app\/marketplace\/plugins<\/loc>/);
  assert.match(xml, /<loc>https:\/\/keel-desktop\.vercel\.app\/plugins<\/loc>/);
});

/* ------------------------------ content ------------------------------ */

test("brand, navigation and hero copy match the design", () => {
  assert.match(html, /<title>Plugins — Keel Marketplace<\/title>/);
  assert.match(html, /<a[^>]*aria-label="Keel Marketplace home"[^>]*>/);
  assert.ok(html.includes("Keel Marketplace"), "brand present");
  assert.match(html, /Add new capabilities to Keel/);
  assert.match(html, /Browse plugins that bundle tools, skills, and integrations for one-click installation\./);
  assert.match(html, /<button[^>]*data-open-submit[^>]*>Submit a plugin<\/button>/);
  assert.match(html, /<a href="\/product\/overview">Capabilities<\/a>[\s\S]*<span aria-current="page">Plugins<\/span>/);

  for (const label of [
    "Product", "Developers", "Enterprise", "Resources", "Pricing", "Log in",
    "Contact sales", "Get Keel", "Home", "Connectors and plugins",
    "Agents and products", "Service partners",
  ]) {
    assert.ok(html.includes(label), `navigation label: ${label}`);
  }
  assert.match(html, /<button[^>]*data-search-jump[^>]*aria-label="Search plugins"/);
});

test("search, filter sidebar, full card grid and View more are present", () => {
  assert.match(html, /placeholder="Search plugins"/);
  assert.match(html, /data-plugin-search/);
  assert.match(html, /<legend>Works with<\/legend>/);
  assert.equal(count(html, /data-works-filter/g), 2, "two Works with checkboxes");
  assert.ok(html.includes('value="Keel"') && html.includes('value="Keel Code"'));
  assert.equal(count(html, /data-plugin(?=\s)/g), PLUGIN_NAMES.length, "one button per plugin");
  for (const name of PLUGIN_NAMES) {
    assert.ok(html.includes(`data-name="${name}"`), `plugin card: ${name}`);
    assert.ok(html.includes(`<span class="mp-card-name">${name}</span>`), `plugin label: ${name}`);
    assert.ok(html.includes(`data-slug=`), "cards carry a real slug");
  }
  assert.match(html, /<button[^>]*data-view-more[^>]*>View more<\/button>/);
});

test("dark footer carries columns and a language selector", () => {
  assert.match(html, /<footer class="mp-footer">/);
  for (const heading of ["Products", "Capabilities", "Resources", "Company"]) {
    assert.ok(html.includes(`<h2>${heading}</h2>`), `footer column: ${heading}`);
  }
  assert.match(html, /<select data-language aria-label="Language">/);
  assert.match(html, /<option value="en" selected>English<\/option>/);
});

test("no borrowed branding, no /app links and no inline data URIs", () => {
  for (const [name, source] of [["HTML", html], ["CSS", css], ["JS", js]]) {
    assert.ok(!/claude/i.test(source), `${name} must be fully rebranded to Keel`);
  }
  assert.ok(!/href="\/app(?:\/|"|#|\?)/i.test(html), "no links to /app");
  assert.ok(!/\bhref="\/app\b/i.test(html), "no /app route anywhere");
  assert.ok(!/data:(?:image|text)\//i.test(html), "no big inline data URIs");
});

test("all CTAs point at real, existing routes", () => {
  assert.ok(html.includes('href="/login"'), "login path used by Log in / Get Keel");
  assert.ok(html.includes('href="/download"'), "download path used by detail action");
  assert.ok(html.includes('href="/plugins"'), "connectors point at the existing plugins page");
  assert.ok(html.includes('href="/marketplace/plugins"'), "clean self-link used in nav/footer");
  assert.ok(html.includes('href="/pricing"'), "pricing path");
  assert.ok(html.includes('href="mailto:hello@keel.dev"'), "contact sales is a real mail link");
  assert.ok(!/href="#(?:\s|")/.test(html), "no dead hash links");
});

/* ---------------------------- behaviour ---------------------------- */

test("search, Works with filters and View more have real handlers", () => {
  assert.match(js, /function initSearchAndFilters/);
  assert.match(js, /input\.addEventListener\("input", render\)/);
  assert.match(js, /check\.addEventListener\("change", render\)/);
  assert.match(js, /function matches\(card, query, selected\)/);
  assert.match(js, /data-works-with/);
  assert.match(js, /split\("\|"\)/);
  assert.ok(html.includes('data-works-with="Keel|Keel Code"'), "multi-target card tags are pipe-delimited");
  assert.match(js, /name\.indexOf\(query\)[\s\S]*description\.indexOf\(query\)/);
  assert.match(js, /VISIBLE_LIMIT = 12/);
  assert.match(js, /more\.addEventListener\("click", function \(\) \{\s*expanded = true/);
  assert.match(js, /setHidden\(more, expanded \|\| matched <= VISIBLE_LIMIT\)/);
  assert.match(js, /count\.textContent = "Showing " \+ shown/);
});

test("card detail dialog offers an honest action, never a fake install", () => {
  assert.match(js, /function openDetail\(card\)/);
  assert.match(js, /qsa\("\[data-plugin\]"\)\.forEach/);
  assert.match(html, /data-detail-dialog/);
  assert.match(html, /data-action-download/);
  assert.match(html, /data-action-login/);
  assert.match(html, /data-action-local/);
  assert.match(html, /Download the app/);
  assert.match(html, /<a class="mp-btn mp-btn-dark" href="\/login">Log in<\/a>/);
  assert.match(js, /"keel plugins add " \+ slug/);
  assert.match(js, /navigator\.clipboard\.writeText/);
  assert.match(html, /No plugin is installed or enabled by opening this dialog\./);
  assert.ok(!/(?:successfully installed|installed successfully|added successfully|installation complete)/i.test(html + js),
    "no fake success message");
  assert.match(js, /event\.key === "Escape"/);
});

test("submit form stores an explicit local-only state and a real mailto", () => {
  assert.match(html, /data-open-submit/);
  assert.match(html, /data-submit-form/);
  assert.match(html, /<h2 id="mp-submit-title">Submit a plugin<\/h2>/);
  assert.match(html, /Local only — nothing sent/);
  assert.match(js, /function initSubmitForm/);
  assert.match(js, /event\.preventDefault\(\)/);
  assert.match(js, /status: "local-only"/);
  assert.match(js, /window\.localStorage\.setItem\(STORAGE_KEY/);
  assert.match(js, /mailto:plugins@keel\.dev\?subject=/);
  assert.match(js, /Nothing was sent to Keel/);
});

test("reveal, sticky header and reduced-motion contract", () => {
  assert.match(js, /new IntersectionObserver/);
  assert.match(js, /observer\.unobserve/);
  assert.match(js, /mp-reveal-ready/);
  assert.match(js, /"\(prefers-reduced-motion: reduce\)"/);
  assert.match(js, /prefersReducedMotion\(\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /animation: none !important/);
  assert.match(css, /transition: opacity 200ms ease, transform 200ms ease/);
  assert.match(css, /translate3d\(0, 12px, 0\)/);
  assert.match(js, /addEventListener\("scroll", frame, \{ passive: true \}\)/);
  assert.match(js, /requestAnimationFrame/);
  assert.match(js, /classList\.toggle\("is-scrolled", y > 12\)/);
  assert.ok(!/setInterval\s*\(/.test(js), "no busy loops");
});

test("styles and script are local and deferred", () => {
  assert.ok(html.includes('href="/ui/marketplace-plugins.css"'));
  assert.ok(html.includes('<script src="/ui/marketplace-plugins.js" defer></script>'));
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
  for (const route of ["/marketplace/plugins", "/marketplace/plugins/", "/marketplace/plugins/index.html"]) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200`);
    const body = await response.text();
    assert.match(body, /Add new capabilities to Keel/, `${route}: wrong page`);
    assert.match(body, /<title>Plugins — Keel Marketplace<\/title>/, `${route}: wrong title`);
  }
});

test("QA server still serves the separate app page at /plugins", async () => {
  const response = await fetch(`${base}/plugins`);
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /<title>Keel — Plugins<\/title>/);
  assert.ok(!body.includes("Add new capabilities to Keel"),
    "old app page must not be replaced by the marketplace page");
});
