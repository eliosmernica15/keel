/* Design-clone contract tests for the Keel Code product page.
 * Run: node --test keel/site/tests/product-keel-code.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ENTRY_POINTS = [
  path.join(SITE, "product", "keel-code.html"),
  path.join(SITE, "product", "keel-code", "index.html"),
  path.join(SITE, "keel-code", "index.html"),
];
const html = fs.readFileSync(ENTRY_POINTS[0], "utf8");
const css = fs.readFileSync(path.join(SITE, "ui", "keel-code.css"), "utf8");
const js = fs.readFileSync(path.join(SITE, "ui", "keel-code.js"), "utf8");

function indexOfToken(token) {
  const at = html.indexOf(token);
  assert.notEqual(at, -1, `missing section marker: ${token}`);
  return at;
}

test("all Keel Code HTML entry points are byte-identical", () => {
  const canonical = fs.readFileSync(ENTRY_POINTS[0]);
  for (const entry of ENTRY_POINTS.slice(1)) {
    assert.deepEqual(fs.readFileSync(entry), canonical, `${entry} differs from canonical page`);
  }
  assert.match(html, /<title>Keel Code[^<]*Hand Keel the work<\/title>/);
});

test("reference sections appear in the intended order", () => {
  const markers = [
    'id="hero"',
    'class="c-logo-strip"',
    'id="get-started"',
    'id="announcements"',
    'id="take-on"',
    'id="where-you-code"',
    'id="risk"',
    'id="slack"',
    'id="developers"',
    'id="faq"',
    'id="technical"',
    'id="get-code"',
    'id="footer"',
  ];
  let previous = -1;
  for (const marker of markers) {
    const at = indexOfToken(marker);
    assert.ok(at > previous, `${marker} is out of order`);
    previous = at;
  }
});

test("reference copy and hero visual are present", () => {
  assert.ok(html.includes('<h1 class="c-title">Keel Code</h1>'));
  assert.ok(html.includes("Hand Keel a bug fix, test, or multi-day migration."));
  assert.ok(html.includes("Download for macOS"));
  assert.ok(html.includes("Read documentation"));
  assert.ok(html.includes("Available for macOS, Linux, and Windows."));
  assert.ok(html.includes("c-editor-window") && html.includes("c-diff-block"));
  assert.ok(html.includes("Ask before running:") && html.includes("npm test"));
  assert.ok(html.includes("git commit") && html.includes("data-approve") && html.includes("data-deny"));
  assert.ok(html.includes("data-parallax"));

  for (const tab of ["Command line", "Desktop app", "IDE extensions", "Web"]) {
    assert.ok(html.includes(`>${tab}</button>`), `missing demo tab: ${tab}`);
  }
  for (const feature of ["Code onboarding", "Triage issues", "Migrate code", "Try it in Keel"]) {
    assert.ok(html.includes(feature), `missing feature: ${feature}`);
  }
  assert.ok(html.includes("Get started with Keel Code"));
  assert.ok(html.includes("Need help making the decision?"));
  assert.ok(html.includes("curl -fsSL https://keel.ai/install.sh | bash"));
  assert.ok(html.includes("What developers are saying"));
  assert.ok(html.includes("Connects with your favorite command line tools"));
  assert.ok(html.includes("Create what's exciting."));
  assert.ok(html.includes("Download Keel Code"));
  assert.ok(html.includes("Read the documentation"));

  const faqButtons = html.match(/class="l-faq-q"/g) || [];
  assert.equal(faqButtons.length, 6, "FAQ must have six questions");
});

test("no Claude branding and no /app links", () => {
  for (const [name, source] of [["html", html], ["css", css], ["js", js]]) {
    assert.doesNotMatch(source, /claude/i, `${name} still mentions the old brand`);
  }
  assert.doesNotMatch(html, /(?:href|action|src)\s*=\s*["']\/app(?:["'/?#]|$)/i, "no /app link");
  assert.doesNotMatch(js, /["']\/app(?:["'/?#]|$)/, "no /app navigation in JS");
});

test("tabs, accordion and mega-menu handlers are wired", () => {
  assert.match(js, /function initDemos/);
  assert.match(js, /data-demo/);
  assert.match(js, /function initFaq/);
  assert.match(js, /button\.l-faq-q/);
  assert.match(js, /function initMegaMenus/);
  assert.match(js, /\[data-menu\]/);
  assert.match(js, /function initMobileMenu/);
  assert.match(js, /function initCopy/);
  assert.match(js, /function initApproval/);
});

test("motion contract: IO reveals, reduced motion, passive rAF scroll", () => {
  assert.match(js, /new IntersectionObserver/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(js, /prefers-reduced-motion: reduce/);
  assert.match(js, /addEventListener\(['"]scroll['"], frame, \{ passive: true \}\)/);
  assert.match(js, /requestAnimationFrame/);
  assert.match(css, /c-reveal-ready[\s\S]{0,240}translateY\(14px\)/);
  assert.match(css, /transition:\s*opacity 200ms ease/);
});

test("HTML has no inline handlers or inline scripts, and JS is deferred", () => {
  assert.doesNotMatch(
    html,
    /\son(?:click|change|load|submit|input|focus|blur|keydown|keyup|mouseover|mouseout)\s*=/i,
    "no inline event handlers"
  );
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/i, "no inline script");
  assert.match(html, /<script src="\/ui\/keel-code\.js" defer><\/script>/);
});

test("reused local logo assets exist on disk", () => {
  const sources = [...html.matchAll(/src="(\/assets\/[^"]+)"/g)].map((match) => match[1]);
  assert.ok(sources.length > 0, "expected at least one reused local asset");
  for (const source of sources) {
    assert.ok(fs.existsSync(path.join(SITE, source.replace(/^\/+/, ""))), `missing asset: ${source}`);
  }
});
