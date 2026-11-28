/* Design-clone contract tests for the Keel Tag product page.
 * Run: node --test keel/site/tests/product-tag.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(SITE, "..", "..");
const HTML_PATH = path.join(SITE, "product", "tag.html");
const INDEX_PATH = path.join(SITE, "product", "tag", "index.html");
const CSS_PATH = path.join(SITE, "ui", "tag.css");
const JS_PATH = path.join(SITE, "ui", "tag.js");

const html = fs.readFileSync(HTML_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const js = fs.readFileSync(JS_PATH, "utf8");
const vercel = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
const serverSource = fs.readFileSync(path.join(REPO, "serve_keel_site.mjs"), "utf8");
const sitemap = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");

function indexOfToken(token) {
  const at = html.indexOf(token);
  assert.notEqual(at, -1, `missing section marker: ${token}`);
  return at;
}

test("both HTML entry points exist and are byte-identical", () => {
  assert.ok(fs.existsSync(HTML_PATH), "missing product/tag.html");
  assert.ok(fs.existsSync(INDEX_PATH), "missing product/tag/index.html");
  assert.deepEqual(fs.readFileSync(INDEX_PATH), fs.readFileSync(HTML_PATH),
    "product/tag/index.html differs from product/tag.html");
  assert.match(html, /<title>Keel Tag — Tag Keel in Slack<\/title>/);
  assert.match(html, /<link rel="canonical" href="https:\/\/keel-desktop\.vercel\.app\/product\/tag" \/>/);
});

test("clean-URL rewrites exist in Vercel and the QA server, with real targets", () => {
  const rewrites = new Map(vercel.rewrites.map((item) => [item.source, item.destination]));
  for (const source of ["/product/tag", "/product/tag/"]) {
    assert.equal(rewrites.get(source), "/product/tag.html", `Vercel rewrite missing: ${source}`);
    assert.ok(fs.existsSync(path.join(SITE, "product", "tag.html")),
      `rewrite target missing: /product/tag.html`);
    assert.match(serverSource, new RegExp(
      `'${source.replace(/\//g, "\\/")}':\\s*'\\/product\\/tag\\.html'`),
      `QA server rewrite missing: ${source}`);
  }
  assert.ok(sitemap.includes("https://keel-desktop.vercel.app/product/tag</loc>"),
    "sitemap is missing /product/tag");
});

test("reference sections appear in the intended order", () => {
  const markers = [
    'id="hero"',
    'id="integrations"',
    'id="connect"',
    'id="how-it-works"',
    'id="teams-use"',
    'id="capabilities"',
    'id="marketplace"',
    'id="admins"',
    'id="get-tag"',
    'id="footer"',
  ];
  let previous = -1;
  for (const marker of markers) {
    const at = indexOfToken(marker);
    assert.ok(at > previous, `${marker} is out of order`);
    previous = at;
  }
});

test("reference copy and product mock visuals are present", () => {
  assert.ok(html.includes('<h1 class="c-title">Tag Keel in Slack</h1>'));
  assert.ok(html.includes("Bring Keel into the tools where your team already works."));
  assert.ok(html.includes(">Get started for free</a>"));
  assert.ok(html.includes(">Talk to sales</a>"));
  assert.ok(html.includes("Product</a>") && html.includes('aria-current="page">Keel Tag'));
  assert.ok(html.includes("c-hero-frame") && html.includes("data-parallax"));
  assert.ok(html.includes("t-slack") && html.includes("t-attachments"));

  for (const name of ["Asana", "Atlassian", "Figma"]) {
    assert.ok(html.includes(`>${name}</h3>`), `missing tool: ${name}`);
  }
  assert.ok(html.includes("AI-powered project management"));
  assert.ok(html.includes("Connecting your teammates"));
  assert.ok(html.includes("Connecting you to Microsoft Teams"));
  assert.ok(html.includes(">Learn more</button>"));

  assert.ok(html.includes("Tag Keel in any Slack thread to bring Keel into the conversation."));
  assert.ok(html.includes(">Tag Keel</h3>"));
  assert.ok(html.includes(">For a task that is part of an ongoing thread</h3>"));
  assert.ok(html.includes(">It knows what's going on and can jump back in</h3>"));
  assert.ok(html.includes("Your work, alongside your team, right in Slack."));
  assert.ok(html.includes("Track and manage requests"));

  assert.ok(html.includes("See what Keel can do for your team."));
  for (const capability of [
    "Capture incoming information",
    "Consolidate requests with a next step",
    "Progressive problem discovery",
    "Bring context like insights and files",
    "Routing tasks to specific people",
    "Fully resolve requests",
    "Build a knowledge base of important information",
    "Enterprise-ready control",
  ]) {
    assert.ok(html.includes(`<strong>${capability}</strong>`), `missing capability: ${capability}`);
  }

  assert.ok(html.includes("Keel connects to your favorite tools"));
  assert.ok(html.includes("Explore the marketplace"));
  for (const name of ["GitHub", "Linear", "Notion", "Google Drive", "Zapier", "PagerDuty", "Zendesk"]) {
    assert.ok(html.includes(name), `missing logo: ${name}`);
  }
  assert.ok(html.includes("Admins stay in control"));
  assert.ok(html.includes("Configure the people, projects and agents allowed to use Keel."));
  for (const item of ["Directory sync and approvals", "Audit logged", "Allowed channels"]) {
    assert.ok(html.includes(`>${item}</h3>`), `missing admin item: ${item}`);
  }
  assert.ok(html.includes("Ready for a new way of working?"));
  assert.ok(html.includes("with Enterprise"));

  const capabilities = html.match(/class="t-cap-btn"/g) || [];
  assert.equal(capabilities.length, 8, "eight capability controls expected");
  const switches = html.match(/data-admin-toggle=/g) || [];
  assert.equal(switches.length, 3, "three admin switches expected");
});

test("no old branding and no /app links", () => {
  for (const [name, source] of [["html", html], ["css", css], ["js", js]]) {
    assert.doesNotMatch(source, /claude/i, `${name} still mentions the old brand`);
  }
  assert.doesNotMatch(html, /(?:href|action|src)\s*=\s*["']\/app(?:["'/?#]|$)/i, "no /app link");
  assert.doesNotMatch(js, /["']\/app(?:["'/?#]|$)/, "no /app navigation in JS");
  assert.match(html, /href="\/login"/, "sign-in goes to the real /login route");
});

test("mega menu, mobile menu, tabs, accordion, thread and admin handlers are wired", () => {
  for (const fn of [
    "function initMegaMenus",
    "function initMobileMenu",
    "function initModalControls",
    "function initThread",
    "function initUseTabs",
    "function initCapabilities",
    "function initAdminToggles",
    "function initCopy",
    "function initHelpSearch",
    "function initAnchors",
  ]) {
    assert.match(js, new RegExp(fn.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `missing handler: ${fn}`);
  }
  for (const selector of ["[data-menu]", "[data-modal]", "data-thread-reply", "[data-use-tab]",
                          "[data-cap]", "[data-admin-toggle]"]) {
    assert.ok(js.includes(selector), `missing JS selector: ${selector}`);
  }
  assert.match(js, /function boot\(\)/);
  assert.match(js, /classList\.contains\('tag-page'\)/);
});

test("motion contract: IO reveals, reduced motion, passive rAF scroll", () => {
  assert.match(js, /new IntersectionObserver/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(js, /prefers-reduced-motion: reduce/);
  assert.match(js, /addEventListener\(['"]scroll['"], frame, \{ passive: true \}\)/);
  assert.match(js, /requestAnimationFrame/);
  assert.match(css, /t-reveal-ready[\s\S]{0,240}translateY\(12px\)/);
  assert.match(css, /transition:\s*opacity 200ms ease/);
  assert.match(css, /will-change: opacity, transform/);
  assert.match(css, /html\.t-reveal-ready body\.tag-page \[data-reveal\]/);
});

test("HTML has no inline handlers or scripts; page JS is deferred", () => {
  assert.doesNotMatch(
    html,
    /\son(?:click|change|load|submit|input|focus|blur|keydown|keyup|mouseover|mouseout)\s*=/i,
    "no inline event handlers"
  );
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/i, "no inline script");
  assert.match(html, /<script src="\/ui\/tag\.js" defer><\/script>/);
  assert.match(html, /<link rel="stylesheet" href="\/ui\/tag\.css" \/>/);
});

test("reused local logo assets exist on disk", () => {
  const sources = [...html.matchAll(/src="(\/assets\/[^"]+)"/g)].map((match) => match[1]);
  assert.ok(sources.length > 0, "expected at least one reused local asset");
  for (const source of sources) {
    assert.ok(fs.existsSync(path.join(SITE, source.replace(/^\/+/, ""))), `missing asset: ${source}`);
  }
});
