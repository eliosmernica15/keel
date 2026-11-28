/* Design/QA contract for the /product/overview page.
 * Run: node --test keel/site/tests/product-overview.test.mjs
 *
 * Pure static checks: no server, no browser, no network.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HTML_FILES = [
  path.join(SITE, "product-overview.html"),
  path.join(SITE, "product", "overview", "index.html"),
];
const CSS = path.join(SITE, "ui", "product-overview.css");
const JS = path.join(SITE, "ui", "product-overview.js");

const html = HTML_FILES.map((file) => fs.readFileSync(file, "utf8"));
const css = fs.readFileSync(CSS, "utf8");
const js = fs.readFileSync(JS, "utf8");

/* Every required section in the owner's screenshot, in document order. */
const SECTIONS = [
  ["sticky nav + product mega menu", /class="po-site-header"/, /id="po-menu-product"/],
  ["hero", /class="po-hero"/, /Give Keel more/],
  ["put Keel to work tabs", /id="work"/, /data-work-tab="integrations"/],
  ["four illustrated steps", /class="po-work-steps"/, /Work with Keel right alongside your code/],
  ["customer quote with photo", /class="po-testimonial"/, /class="po-quote-photo"/],
  ["change the way you work", /id="change"/, /Change the way you work/],
  ["hub diagram + filters", /id="capabilities"/, /data-cap-tab="development"/],
  ["marketing scenario", /id="use-case"/, /Q3 campaign rendition/],
  ["FAQ", /id="faq"/, /class="po-faq-q"/],
  ["CTA with email field", /id="get-keel"/, /id="po-ask-input"[^>]*type="email"/],
  ["dark footer", /class="po-footer"/, /class="po-lang"/],
];

test("both HTML entry points exist and are identical", () => {
  assert.ok(HTML_FILES.every((file) => fs.existsSync(file)));
  assert.equal(html[0], html[1], "product-overview.html and product/overview/index.html must match");
});

test("all eleven designed sections exist in order in both HTML files", () => {
  for (let copy = 0; copy < html.length; copy += 1) {
    let cursor = 0;
    for (const [name, startPattern, detailPattern] of SECTIONS) {
      const start = html[copy].search(startPattern);
      assert.ok(start >= cursor, `${copy}: ${name} missing or out of order`);
      assert.match(html[copy].slice(start), detailPattern, `${copy}: ${name} detail missing`);
      cursor = start + 1;
    }
  }
});

test("product mega menu has the four required columns and KEEL product names", () => {
  for (const source of html) {
    assert.match(source, /<p class="po-mega-heading">Products<\/p>/);
    assert.match(source, /<p class="po-mega-heading">Capabilities<\/p>/);
    assert.match(source, /<p class="po-mega-heading">Extensions<\/p>/);
    assert.match(source, /<p class="po-mega-heading">Models<\/p>/);
    for (const name of [
      "Keel Code", "Keel Cowork", "Keel Duet", "Keel Platform", "Keel Tag",
      "Keel Security", "Keel Science", "Mythos", "Fable", "Opus", "Sonnet", "Haiku",
    ]) {
      assert.ok(source.includes(name), `mega menu is missing ${name}`);
    }
  }
});

test("hero floating cards carry the three promised messages and parallax hooks", () => {
  for (const source of html) {
    for (const label of [
      "Bring your own keys", "Freedom to choose your model", "Personalized to you",
    ]) {
      assert.ok(source.includes(label), `hero card missing: ${label}`);
    }
    assert.equal((source.match(/data-parallax=/g) || []).length, 3);
  }
});

test("the four step cards have colored illustration panels with mock visuals", () => {
  for (const source of html) {
    assert.match(source, /po-art-code[\s\S]*po-art-tasks[\s\S]*po-art-diagram[\s\S]*po-art-data/);
    assert.match(source, /Organize thoughts and tasks/);
    assert.match(source, /Diagram complex systems/);
    assert.match(source, /Explore data to find answers/);
  }
});

test("the hub names the requested nodes and the three work filters", () => {
  for (const source of html) {
    for (const node of [
      "Analyze data", "Write and edit", "Search the web", "Build with Keel Code",
      "Capture ideas", "Automate tasks",
    ]) {
      assert.ok(source.includes(node), `hub node missing: ${node}`);
    }
    assert.match(source, /data-cap-tab="all"[\s\S]*data-cap-tab="knowledge"[\s\S]*data-cap-tab="development"/);
  }
});

test("no Claude branding remains anywhere in the four owned files", () => {
  for (const source of [...html, css, js]) {
    assert.ok(!/claude/i.test(source), "owner requires KEEL branding only");
  }
});

test("internal links and anchors resolve to real routes or ids", () => {
  for (let copy = 0; copy < html.length; copy += 1) {
    const ids = new Set([...html[copy].matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
    const hrefs = [...html[copy].matchAll(/\shref="([^"]+)"/g)].map((m) => m[1]);
    assert.ok(hrefs.length > 40, "expected a fully linked page");
    for (const href of hrefs) {
      if (href.startsWith("mailto:") || href.startsWith("http")) continue;
      const [rawPath, hash] = href.split("#");
      if (hash) {
        assert.ok(ids.has(hash), `${copy}: anchor #${hash} has no target`);
      }
      if (!rawPath) continue;
      assert.ok(rawPath.startsWith("/"), `${copy}: internal link must be site-absolute: ${href}`);
      const target = path.join(SITE, rawPath.replace(/^\/+/, ""));
      const candidates = [target, `${target}.html`, path.join(target, "index.html")];
      assert.ok(
        candidates.some((candidate) => {
          try { return fs.statSync(candidate).isFile(); } catch { return false; }
        }),
        `${copy}: link points to a missing route: ${href}`
      );
    }
  }
});

test("script is deferred and nothing uses huge inline data URIs or inline handlers", () => {
  for (const source of html) {
    assert.match(source, /<script src="\/ui\/product-overview\.js" defer><\/script>/);
    assert.ok(!/<script(?![^>]*\bsrc=)/i.test(source), "no inline scripts");
    assert.ok(!/\son(?:click|load|error|mouseover|change|input|submit|scroll)\s*=/i.test(source),
      "no inline event handlers");
    assert.ok(!/data:[^;"']{200,}/.test(source), "no large inline data URIs");
  }
});

test("CSS has a reduced-motion kill switch and scroll-reveal primitives", () => {
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(css, /transition:\s*none\s*!important/);
  assert.match(css, /\[data-reveal\][\s\S]*translateY\(16px\)/);
  assert.match(css, /--po-reveal-delay/);
  assert.match(css, /cubic-bezier\(\.22,\s*\.61,\s*\.36,\s*1\)/);
  assert.match(css, /\.is-scrolled[\s\S]*box-shadow/);
  assert.match(css, /\.po-faq-a[\s\S]*max-height:\s*0[\s\S]*transition:\s*max-height/);
  assert.match(css, /po-mega-in[\s\S]*160ms/);
});

test("JS uses IntersectionObserver, passive rAF-throttled scroll, and no busy loops", () => {
  assert.match(js, /IntersectionObserver/);
  assert.match(js, /observer\.unobserve/);
  assert.match(js, /addEventListener\("scroll",\s*frame,\s*\{\s*passive:\s*true\s*\}\)/);
  assert.match(js, /window\.requestAnimationFrame/);
  assert.match(js, /prefersReducedMotion\(\)/);
  assert.ok(!/setInterval\s*\(/.test(js), "no polling interval");
  assert.ok(!/while\s*\(/.test(js), "no busy loop");
});

test("every interactive control family has a real handler in the script", () => {
  const hooks = [
    "po-nav-trigger", "po-hamburger", "po-work-tab", "po-cap-tab", "po-faq-q",
    "po-role", "po-size", "po-task", "po-view-usecase", "po-auth-open",
    "po-text-link", "po-lang", "po-modal-close", "po-modal-backdrop",
  ];
  for (const hook of hooks) {
    assert.match(js, new RegExp(`\\.${hook}\\b`), `no handler for .${hook}`);
  }
  assert.match(js, /#po-ask-form|po-ask-form/, "CTA form handler missing");
  assert.match(js, /local demo|Local demo/, "honest local form state missing");
});
