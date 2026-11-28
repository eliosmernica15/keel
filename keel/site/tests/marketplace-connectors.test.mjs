/* Route, content and behaviour-contract tests for the new destination at
 * /marketplace/connectors-plugins. Run:
 *   node --test keel/site/tests/marketplace-connectors.test.mjs
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
const HTML_PATH = path.join(SITE, "marketplace", "connectors-plugins.html");
const INDEX_PATH = path.join(SITE, "marketplace", "connectors-plugins", "index.html");
const CSS_PATH = path.join(SITE, "ui", "marketplace-connectors.css");
const JS_PATH = path.join(SITE, "ui", "marketplace-connectors.js");
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

function sectionOf(id) {
  const start = html.indexOf(`id="${id}"`);
  assert.ok(start !== -1, `missing section: ${id}`);
  const next = html.indexOf('<section class="mc-section"', start + 1);
  return html.slice(start, next === -1 ? html.length : next);
}

/* ------------------------------ routes ------------------------------ */

test("vercel.json adds exactly the two new clean rewrites", () => {
  assert.equal(rewrites.get("/marketplace/connectors-plugins"),
    "/marketplace/connectors-plugins.html");
  assert.equal(rewrites.get("/marketplace/connectors-plugins/"),
    "/marketplace/connectors-plugins.html");
  const newEntries = vercel.rewrites.filter((r) =>
    r.source.startsWith("/marketplace/connectors-plugins") ||
    r.destination === "/marketplace/connectors-plugins.html");
  assert.equal(newEntries.length, 2, "exactly two new rewrite entries");
});

test("QA server mirrors both new rewrites", () => {
  assert.match(serveSource,
    /'\/marketplace\/connectors-plugins': '\/marketplace\/connectors-plugins\.html'/);
  assert.match(serveSource,
    /'\/marketplace\/connectors-plugins\/': '\/marketplace\/connectors-plugins\.html'/);
});

test("all pre-existing routes, headers and redirects are preserved", () => {
  for (const preserved of [
    "/download", "/downloads", "/login", "/new", "/plugins", "/projects",
    "/artifacts", "/features/artifacts", "/pricing", "/product/overview",
    "/platform/api", "/resources/articles", "/cowork", "/keel-code",
  ]) {
    assert.ok(rewrites.has(preserved), `preserved rewrite: ${preserved}`);
  }
  assert.equal(rewrites.get("/login"), "/login.html");
  assert.equal(rewrites.get("/plugins"), "/plugins.html");
  assert.equal(rewrites.get("/features/artifacts"), "/features/artifacts.html");
  assert.ok(vercel.headers.length > 0, "security/cache headers preserved");
  assert.ok(Array.isArray(vercel.redirects) && vercel.redirects.length > 0,
    "redirects preserved");
  assert.ok(!vercel.redirects.some((r) =>
    r.source.includes("marketplace/connectors-plugins")),
    "no extra redirect was added for the new route");
  assert.match(serveSource, /'\/plugins': '\/plugins\.html'/);
  assert.match(serveSource, /'\/login': '\/login\.html'/);
});

test("the page exists as a top-level file and byte-identical index", () => {
  assert.ok(fs.existsSync(HTML_PATH) && fs.statSync(HTML_PATH).isFile());
  assert.ok(fs.existsSync(INDEX_PATH) && fs.statSync(INDEX_PATH).isFile());
  assert.equal(html, fs.readFileSync(INDEX_PATH, "utf8"), "copies are byte-identical");
});

test("sitemap advertises the new clean URL", () => {
  const xml = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");
  assert.match(xml,
    /<loc>https:\/\/keel-desktop\.vercel\.app\/marketplace\/connectors-plugins<\/loc>/);
  assert.match(xml, /<loc>https:\/\/keel-desktop\.vercel\.app\/plugins<\/loc>/);
});

/* ------------------------------ content ------------------------------ */

test("brand, navigation and secondary marketplace nav match the design", () => {
  assert.match(html, /<title>Connectors and plugins - Keel Marketplace<\/title>/);
  assert.match(html, /Keel <span class="mc-wordmark-secondary">Marketplace<\/span>/);
  for (const label of ["Product", "Developers", "Enterprise", "Resources", "Pricing",
    "Log in", "Contact sales", "Get Keel"]) {
    assert.ok(html.includes(`>${label}<`) || html.includes(`">${label}</a>`),
      `top nav link: ${label}`);
  }
  for (const label of ["Home", "Connectors and plugins", "Agents and products",
    "Service partners"]) {
    assert.ok(html.includes(`>${label}</a>`), `secondary nav link: ${label}`);
  }
  assert.ok(html.includes('id="mc-nav-search"'), "secondary nav search icon");
});

test("hero copy and both submit CTAs are present", () => {
  assert.match(html, /<h1 class="mc-hero-title" id="mc-hero-title">Connectors and plugins<\/h1>/);
  assert.match(html, /Bring the tools you already use into every Keel conversation\./);
  assert.match(html, /<use href="#mc-store" \/>/, "store/basket icon");
  assert.match(html, /data-submit="connector">Submit a connector</);
  assert.match(html, /data-submit="plugin">Submit a plugin</);
});

test("directory controls and all thirteen category checkboxes are present", () => {
  assert.match(html, /placeholder="Search connectors"/);
  assert.match(html, /<option value="recommended" selected>Recommended<\/option>/);
  assert.match(html, /<option value="name">Name A–Z<\/option>/);
  assert.match(html, /<option value="newest">Newest<\/option>/);
  assert.match(html, /Show all 725/);
  const categories = [
    "Commerce &amp; shopping", "Communication", "Customer health",
    "Data &amp; analytics", "Developer tools", "Education", "Financial services",
    "Health", "Legal", "Media &amp; entertainment", "Nonprofit", "Other", "Productivity",
  ];
  for (const category of categories) {
    assert.ok(html.includes(`name="mc-category" value="${category}"`),
      `category checkbox: ${category}`);
  }
  assert.equal(count(html, /name="mc-category"/g), 13, "exactly 13 category filters");
  assert.match(html, /<legend class="mc-filter-legend">Category<\/legend>/);
});

test("all four card sections appear in order with the right card counts", () => {
  const ids = ["mc-top-connectors", "mc-top-plugins", "mc-new-connectors", "mc-all-connectors"];
  let previous = -1;
  for (const id of ids) {
    const at = html.indexOf(`id="${id}"`);
    assert.ok(at > previous, `section ${id} missing or out of order`);
    previous = at;
  }
  assert.equal(count(sectionOf("mc-top-connectors"), /class="mc-card mc-reveal"/g), 12);
  assert.equal(count(sectionOf("mc-top-plugins"), /class="mc-card mc-reveal"/g), 6);
  assert.equal(count(sectionOf("mc-new-connectors"), /class="mc-card mc-reveal"/g), 5);
  assert.equal(count(sectionOf("mc-all-connectors"), /class="mc-card mc-reveal"/g), 18);
  assert.match(html, /<h2 class="mc-section-title" id="mc-top-heading">Top connectors<\/h2>/);
  assert.match(html, /<h2 class="mc-section-title" id="mc-plugins-heading">Top plugins<\/h2>/);
  assert.match(html, /<h2 class="mc-section-title" id="mc-new-heading">New connectors<\/h2>/);
  assert.match(html, /<h2 class="mc-section-title" id="mc-all-heading">All connectors<\/h2>/);
  assert.equal(count(sectionOf("mc-top-plugins"), /class="mc-badge"/g), 0);
  assert.equal(count(sectionOf("mc-new-connectors"), /class="mc-badge">New<\/span>/g), 5);
});

test("every named connector, plugin and new item from the design is present", () => {
  const top = ["Google Drive", "Gmail", "Google Calendar", "Canva", "Notion",
    "Microsoft 365", "Figma", "Slack", "Atlassian MCP", "HubSpot", "Asana", "Linear"];
  const plugins = ["Frontend Design", "Superpowers", "Code Review", "Context7",
    "Code Simplifier", "Playwright"];
  const fresh = ["Harvest", "Copy Any Design", "Instant Website", "Domain for Any...", "Litter"];
  const all = ["Google Drive", "Gmail", "Google Calendar", "Microsoft 365", "Canva",
    "Notion", "Slack", "Zoho Mail", "Atlassian MCP"];
  for (const [name, section, list] of [
    ["Top connectors", "mc-top-connectors", top],
    ["Top plugins", "mc-top-plugins", plugins],
    ["New connectors", "mc-new-connectors", fresh],
  ]) {
    const body = sectionOf(section);
    for (const item of list) {
      assert.ok(body.includes(`data-name="${item}"`), `${name}: ${item}`);
      assert.ok(body.includes(`class="mc-card-name">${item}<`), `${name} card title: ${item}`);
    }
  }
  const allBody = sectionOf("mc-all-connectors");
  for (const item of all) {
    const at = allBody.indexOf(`data-name="${item}"`);
    assert.ok(at !== -1, `All connectors: ${item}`);
    const extraAt = allBody.indexOf('data-extra="true"');
    if (extraAt !== -1) assert.ok(at < extraAt, `${item} must be in the first nine`);
  }
  assert.match(allBody, /id="mc-view-more"/);
  assert.equal(count(allBody, /data-expanded="false"/g), 1);
  assert.equal(count(allBody, /data-extra="true"/g), 9, "nine more cards behind View more");
  assert.equal(count(allBody, /data-extra="true" hidden>/g), 9,
    "the extra cards are hidden in the markup before JavaScript runs");
});

test("no duplicate ids shadow the search input or dialog targets", () => {
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length, "every id is unique");
  assert.match(html, /<input id="mc-search" type="search"/);
  assert.ok(!/<symbol id="mc-search"/.test(html), "the icon symbol uses its own id");
});

test("all cards carry searchable descriptions, categories and an add action", () => {
  const total = count(html, /class="mc-card mc-reveal"/g);
  assert.equal(total, 41);
  assert.equal(count(html, /data-desc="/g), total, "each card has a description");
  assert.equal(count(html, /data-categories="/g), total, "each card has categories");
  assert.equal(count(html, /data-name="/g), total, "each card has a name");
  assert.equal(count(html, /class="mc-add"/g), total, "each card has a + action");
  assert.equal(count(html, /data-add="/g), total, "each + is wired to the install dialog");
});

test("footer is dark, has link columns and a working language selector", () => {
  assert.match(html, /<footer class="mc-footer" id="mc-footer">/);
  assert.match(css, /body\.mc-page \.mc-footer \{[\s\S]*?background: var\(--mc-footer\)/);
  assert.ok(count(html, /class="mc-footer-col"/g) >= 5, "five footer columns");
  assert.match(html, /id="mc-lang-button"/);
  assert.match(html, /id="mc-lang-menu"/);
  assert.match(html, /data-lang="English"/);
  assert.match(js, /function initLanguage/);
});

test("no borrowed branding, no /app links and no third-party runtime assets", () => {
  for (const [name, source] of [["HTML", html], ["CSS", css], ["JS", js]]) {
    assert.ok(!/claude/i.test(source), `${name} must be fully rebranded to Keel`);
  }
  assert.ok(!/href="\/app(?:\/|"|#|\?)/i.test(html), "no links to /app");
  assert.ok(!/\bhref="\/app\b/i.test(html), "no /app route anywhere");
  assert.ok(!/data:(?:image|text)\//i.test(html), "no inline data URIs");
  const external = html.replace(/xmlns="[^"]+"/g, "")
    .match(/(?:href|src)="https?:\/\/(?!keel-desktop\.vercel\.app)[^"]*"/g) || [];
  assert.equal(external.length, 0, "no third-party href/src assets");
  assert.ok(!/<script(?![^>]*\bsrc=)/i.test(html), "no inline scripts");
});

test("every other link points to a real local route or mailto", () => {
  for (const href of [
    "/", "/login", "/pricing", "/product/overview", "/platform/api",
    "/features/artifacts", "/plugins", "/resources/articles", "/keel-code",
    "/cowork", "/download", "/roadmap", "/notices", "/requirements",
    "/projects", "/keel-in-chrome", "/marketplace/connectors-plugins",
  ]) {
    assert.ok(html.includes(`href="${href}"`), `real route: ${href}`);
    const route = href === "/" ? "/" : href.replace(/\/$/, "");
    assert.ok(rewrites.has(route) || fs.existsSync(path.join(SITE, route.replace(/^\//, ""))),
      `route resolves: ${href}`);
  }
  assert.ok(html.includes('href="mailto:hello@keel.dev"'), "contact is a real mail link");
});

/* ---------------------------- behaviour ---------------------------- */

test("search, category filters and sorting have real change handlers", () => {
  assert.match(js, /function initFilters/);
  assert.match(js, /input\.addEventListener\("input", applyVisibility\)/);
  assert.match(js, /box\.addEventListener\("change", applyVisibility\)/);
  assert.match(js, /select\.addEventListener\("change"/);
  assert.match(js, /card\.hidden = !\(fit && \(!extra \|\| expanded\)\)/,
    "visibility is driven by search, category and reveal state");
  assert.match(js, /haystack\.indexOf\(term\)/);
  assert.match(js, /onCard\.indexOf\(category\)/);
  assert.match(js, /function sortCards/);
  assert.match(js, /mode === "name"/);
  assert.match(js, /mode === "newest"/);
  assert.match(js, /grid\.appendChild\(fragment\)/);
});

test("add + opens an honest install dialog with download and login actions", () => {
  assert.match(html, /<dialog class="mc-dialog" id="mc-install-dialog"/);
  assert.match(html, /Install this connector in the Keel desktop app/);
  assert.ok(!/installed successfully|install complete|added successfully/i.test(html),
    "dialog must never claim a fake install");
  assert.match(html, /has not been installed/);
  assert.match(html, /href="\/download">Download Keel</);
  assert.match(html, /href="\/login">Log in</);
  assert.match(js, /qsa\("\[data-add\]"\)/);
  assert.match(js, /function openDialog/);
  assert.match(js, /showModal\(\)/);
});

test("submit CTAs open a real local-only form with a mailto fallback", () => {
  assert.match(js, /function initSubmitDialog/);
  assert.match(js, /qsa\("\[data-submit\]"\)/);
  assert.match(js, /form\.addEventListener\("submit"/);
  assert.match(js, /window\.localStorage\.setItem\(STORAGE_KEY/);
  assert.match(js, /Nothing was sent to Keel/);
  assert.match(js, /mailto:hello@keel\.dev/);
  assert.match(html, /id="mc-submit-status"/);
  assert.match(html, /Save on this device/);
  assert.match(html, /Send your submission by email instead/);
});

test("View more reveals the remaining cards", () => {
  assert.match(js, /function initViewMore/);
  assert.match(js, /grid\.setAttribute\("data-expanded"/);
  assert.match(js, /refreshCards\(\)/);
  assert.match(html, /id="mc-view-more"[^>]*aria-expanded="false"/);
});

test("reveals use IntersectionObserver, passive rAF scroll and a reduced-motion kill switch", () => {
  assert.match(js, /new IntersectionObserver/);
  assert.match(js, /observer\.unobserve/);
  assert.match(js, /observer\.disconnect/);
  assert.match(js, /prefers-reduced-motion: reduce/);
  assert.match(js, /addEventListener\("scroll", frame, \{ passive: true \}\)/);
  assert.match(js, /requestAnimationFrame/);
  assert.match(js, /classList\.toggle\("is-scrolled"/);
  assert.ok(!/setInterval|while\s*\(true\)|for\s*\(\s*;;/.test(js), "no busy loops");
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /animation: none !important/);
  assert.match(css, /transition: none !important/);
  assert.match(css, /mc-reveal-ready/);
  assert.match(css, /translateY\(14px\)/);
  assert.match(css, /opacity 220ms ease, transform 220ms ease/);
});

test("styles and script are local and deferred", () => {
  assert.ok(html.includes('href="/ui/marketplace-connectors.css"'));
  assert.ok(html.includes('<script src="/ui/marketplace-connectors.js" defer></script>'));
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

test("QA server serves the clean URL, slash variant and physical index", async () => {
  const expected = /Bring the tools you already use into every Keel conversation\./;
  for (const route of [
    "/marketplace/connectors-plugins",
    "/marketplace/connectors-plugins/",
    "/marketplace/connectors-plugins/index.html",
  ]) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200`);
    assert.match(await response.text(), expected, `${route}: wrong page`);
  }
});

test("QA server still serves the separate /plugins and /login routes", async () => {
  for (const route of ["/plugins", "/login"]) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200`);
    const body = await response.text();
    assert.ok(!body.includes("Bring the tools you already use into every Keel conversation."),
      `${route}: must not be replaced by the marketplace page`);
  }
});
