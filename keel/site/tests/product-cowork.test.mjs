/* Design-clone contract tests for /product/cowork.
 * Run: node --test keel/site/tests/product-cowork.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => fs.readFileSync(path.join(SITE, rel), "utf8");

const PAGE = read("product/cowork.html");
const INDEX = read("product/cowork/index.html");
const SHORT = read("cowork/index.html");
const CSS = read("ui/cowork.css");
const JS = read("ui/cowork.js");

const SECTION_IDS = [
  "hero", "capabilities", "tasks", "plugins", "stories", "film", "control", "get-started", "cw-footer"
];

function indexOfId(html, id) {
  return html.indexOf(`id="${id}"`);
}

test("all entry points are byte-identical", () => {
  assert.equal(PAGE, INDEX, "product/cowork.html and product/cowork/index.html must match");
  assert.equal(PAGE, SHORT, "cowork/index.html short route must match the product page");
});

test("sections appear in the reference order", () => {
  let previous = -1;
  for (const id of SECTION_IDS) {
    const at = indexOfId(PAGE, id);
    assert.ok(at >= 0, `missing section: #${id}`);
    assert.ok(at > previous, `#${id} is out of order`);
    previous = at;
  }
});

test("reference copy is present and rebranded to Keel", () => {
  const copy = [
    "The work behind your best work",
    "KEEL Cowork completes tasks you can steer from anywhere.",
    "Download for macOS",
    "Talk to sales",
    "Works with a paid plan. Rolling out on web, mobile.",
    "Set up a project for this task",
    "Set up a folder and let Keel work inside it",
    "Core capabilities",
    "Cowork is your teammate for the work that fills your day.",
    "KEEL Cowork takes on your tasks",
    "Say what, not how",
    "See the work as it happens",
    "Your work follows you",
    "KEEL works when you don't",
    "More than one thing at a time",
    "A built-in browser for Cowork",
    "A checklist to accomplish your task",
    "Power through tedious tasks",
    "Schedule reports",
    "Build spreadsheets",
    "Review in bulk",
    "Analyze notes",
    "Schedule recurring reports, ready for review",
    "Customize KEEL with plugins",
    "Explore plugins",
    "Skills", "Connectors", "Sub-agents",
    "Customize Cowork with plugins",
    "Brand voice", "Tribe AI", "Monthly close", "KEEL Labs", "Support triage",
    "Launched faster with automation",
    "Built for teams with complex operations",
    "Keel Cowork doesn't just answer, takes action.",
    "Keel Cowork for marketing",
    "Stay in control",
    "Read our safety guide",
    "Watch demo",
    "You decide what KEEL can access",
    "KEEL asks before acting",
    "For Teams &amp; Enterprise",
    "Runs where your data lives",
    "We're just getting started",
    "Keep your data yours",
    "SOC 2", "HIPAA", "GDPR",
    "Get started with Keel",
    "Choose a plan, then start using Keel Cowork.",
    "Individual", "Team &amp; Enterprise", "$17", "$100", "$200", "Try Keel",
    "Log in", "Contact sales", "Get Keel"
  ];
  for (const phrase of copy) {
    assert.ok(PAGE.includes(phrase), `missing copy: ${phrase}`);
  }
});

test("no legacy branding and no /app links", () => {
  assert.ok(!/claude|anthropic/i.test(PAGE), "legacy branding leaked into the page");
  assert.ok(!/claude|anthropic/i.test(JS), "legacy branding leaked into the script");
  assert.ok(!/(?:href|src|action)\s*=\s*["']\/app(?:["'/#?]|\/)/i.test(PAGE), "no /app links allowed");
  assert.ok(!PAGE.includes('href="#"'), "no placeholder anchors");
});

test("no inline event handlers or inline scripts", () => {
  assert.ok(!/\bon(?:click|load|error|submit|change|input|mouseover|mouseenter|keydown|focus|blur)\s*=\s*["']/i.test(PAGE),
    "inline event handlers are not allowed");
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(PAGE), "external script tag required");
  assert.ok(PAGE.includes('<script src="/ui/cowork.js" defer></script>'), "cowork.js must be deferred");
  assert.ok(PAGE.includes('<link rel="stylesheet" href="/ui/cowork.css" />'), "cowork.css must be linked");
});

test("navigation, tabs and accordion handlers are wired up in JS", () => {
  const hooks = [
    "data-nav", "cw-mega", "cw-hamburger", "cw-mobile-menu",
    "data-window-tab", "data-window-panel",
    "data-task", "data-view", "data-check-progress",
    "data-plan", "data-plan-panel", "data-faq",
    "data-action", "open-contact", "open-video", "data-form=\"contact\"", "data-lang"
  ];
  for (const hook of hooks) {
    assert.ok(JS.includes(hook), `JS is missing handler hook: ${hook}`);
  }
  assert.ok(JS.includes("IntersectionObserver"), "scroll reveals need IntersectionObserver");
  assert.ok(JS.includes("requestAnimationFrame"), "scroll listeners must be rAF-throttled");
  assert.ok(JS.includes("passive: true"), "scroll listeners must be passive");
});

test("motion budget and reduced-motion kill switch", () => {
  assert.match(CSS, /@media\s*\(prefers-reduced-motion:\s*reduce\)/, "reduced-motion media query missing");
  assert.match(CSS, /data-reveal[^{]*\{[^}]*transform:\s*translate3d\(0,\s*14px,\s*0\)/, "reveal travel must be <= 16px");
  assert.match(CSS, /transition:\s*opacity\s*\.2s ease,\s*transform\s*\.2s ease/, "reveal must finish in <= 220ms");
  assert.ok(!/animation:\s*[a-z-]+\s+(?:[3-9]|[1-9][0-9])(\.\d+)?s/i.test(CSS), "no long running animations");
  assert.ok(JS.includes("prefers-reduced-motion"), "JS must honour reduced motion");
});

test("all local images exist on disk", () => {
  const sources = [
    ...PAGE.matchAll(/src="(\/assets\/[^"]+)"/g),
    ...CSS.matchAll(/url\('(\/assets\/[^']+)'\)/g)
  ].map((match) => match[1]);
  assert.ok(sources.length > 10, "expected the page to reuse local artwork");
  for (const source of sources) {
    assert.ok(fs.existsSync(path.join(SITE, source.replace(/^\//, ""))), `missing local asset: ${source}`);
  }
});
