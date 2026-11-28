/* Tests for the rebuilt /keel-in-chrome page.
 * Run: node --test keel/site/tests/keel-in-chrome.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HTML_PATH = path.join(SITE, "keel-in-chrome.html");
const INDEX_PATH = path.join(SITE, "keel-in-chrome", "index.html");
const CSS_PATH = path.join(SITE, "ui", "keel-in-chrome.css");
const JS_PATH = path.join(SITE, "ui", "chrome-install.js");

const html = fs.readFileSync(HTML_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const js = fs.readFileSync(JS_PATH, "utf8");
const vercel = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
const rewrites = new Set(vercel.rewrites.flatMap((r) => [r.source, `${r.source}/`]));

function localPath(href) {
  return path.join(SITE, href.replace(/^\/+/, ""));
}
function routeExists(href) {
  const file = localPath(href);
  if (fs.existsSync(file) && fs.statSync(file).isFile()) return true;
  if (fs.existsSync(path.join(file, "index.html"))) return true;
  return rewrites.has(href);
}
function references(source) {
  return [...source.matchAll(/(?:href|src)="([^"]+)"/g)].map((m) => m[1]);
}

test("top-level HTML and physical route index are byte-identical", () => {
  const top = fs.readFileSync(HTML_PATH);
  const index = fs.readFileSync(INDEX_PATH);
  assert.ok(top.equals(index), "keel-in-chrome.html and keel-in-chrome/index.html differ");
});

test("sections appear in the screenshot order", () => {
  const markers = [
    'id="kic-hero-title"',
    'id="work-on-web"',
    'id="everyday-tasks"',
    'id="capabilities"',
    'id="use-in-chrome"',
    'id="faq"',
    "Start on the page you're already on",
  ];
  let previous = -1;
  for (const marker of markers) {
    const at = html.indexOf(marker);
    assert.ok(at > previous, `missing or out-of-order section: ${marker}`);
    previous = at;
  }
});

test("hero copy, buttons and floating install card match the reference", () => {
  assert.ok(html.includes("A helping hand across all your tabs"));
  assert.ok(html.includes("Keel in Chrome is now available to everyone on the Free plan and above. Try it out today on the web."));
  for (const label of ["Add to Chrome", "See how it works", "Keel in Chrome installation successful", "Open side panel"]) {
    assert.ok(html.includes(label), `hero label missing: ${label}`);
  }
  assert.ok(html.includes('href="#work-on-web"'), "see-how-it-works is a working anchor");
  const toast = html.match(/<div class="kic-install-toast"[^>]*>/);
  assert.ok(toast && toast[0].includes('aria-hidden="true"'), "success card is clearly an illustration");
});

test("navigation has the four-column Product mega menu and top links", () => {
  assert.equal((html.match(/class="kic-mega-col"/g) || []).length, 4);
  assert.ok(html.includes("data-kic-mega-trigger"));
  for (const label of ["Log in", "Contact sales", "Get Keel"]) {
    assert.ok(html.includes(label), `top link missing: ${label}`);
  }
  assert.ok(html.includes('href="/login">Log in<'), "log in goes to /login");
});

test("demo heading, tabs, task cards, capabilities and use items are present", () => {
  assert.ok(html.includes("A refreshing new way to work on the web"));
  assert.ok(html.includes("Your partner for all things web, right where you are"));
  assert.ok(html.includes("From browser research to docs"));
  assert.ok(html.includes('data-kic-tab="chat"') && html.includes('data-kic-tab="cowork"'));
  assert.ok(html.includes("Core capabilities"));
  assert.ok(html.includes("Block the site that says &#39;use AI&#39;") || html.includes("Block the site that says 'use AI'"));

  const tasks = [
    "Add multiple items to cart",
    "Find when flight prices drop",
    "Get explanations of complex topics",
    "Summarize multiple pages in one tab",
    "Type in notes with your voice",
    "Clean up your inbox",
  ];
  assert.equal((html.match(/class="kic-card kic-reveal"/g) || []).length, 6, "six large task cards");
  for (const title of tasks) assert.ok(html.includes(title), `task card missing: ${title}`);
  assert.equal((html.match(/class="kic-small-card kic-reveal"/g) || []).length, 3, "three smaller cards");

  for (const item of [
    "Install the extension", "Log in", "Ask anything",
    "Three steps to get started: In your browser",
    "Use with Cowork on websites", "Keep tabs organized with Projects", "Log in once and use everywhere",
  ]) assert.ok(html.includes(item), `capability/use item missing: ${item}`);
});

test("FAQ contains the five required questions as working accordion buttons", () => {
  const questions = [...html.matchAll(/<button class="kic-faq-q"[^>]*><span>([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(questions, [
    "How to use Keel in Chrome on any website?",
    "How do I use the Keel in Chrome side panel?",
    "What is the difference between Cowork and Desktop app?",
    "Can I use Keel in Chrome on my phone?",
    "Does it work with multiple tabs?",
  ]);
  for (const id of ["kic-faq-a-1", "kic-faq-a-2", "kic-faq-a-3", "kic-faq-a-4", "kic-faq-a-5"]) {
    assert.ok(html.includes(`aria-controls="${id}"`) && html.includes(`id="${id}"`), `FAQ pair ${id}`);
  }
});

test("no Claude branding, no /app links, no retired chrome-web-store route", () => {
  for (const [name, source] of [["html", html], ["css", css], ["js", js]]) {
    assert.ok(!/claude/i.test(source), `${name} still mentions Claude`);
  }
  assert.ok(!/\/app(?:["'\/])/.test(html), "no /app links (use /login)");
  assert.ok(!/chrome-web-store/i.test(html), "no link to the retired chrome-web-store route");
});

test("every absolute link, stylesheet, script and icon resolves on disk", () => {
  const local = [...new Set(references(html).filter((href) => href.startsWith("/")))];
  assert.ok(local.length > 0, "page has local references");
  for (const href of local) {
    const target = href.split("#")[0].split("?")[0];
    if (target === "/") continue;
    assert.ok(routeExists(target), `broken local reference: ${href}`);
  }
  assert.ok(html.includes('href="/ui/keel-in-chrome.css"'));
  assert.ok(html.includes('src="/ui/chrome-install.js"'));
  assert.ok(fs.existsSync(CSS_PATH) && fs.existsSync(JS_PATH));
  for (const url of [...css.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1])) {
    if (url.startsWith("data:")) continue;
    assert.ok(routeExists(url.replace(/^["']|["']$/g, "")), `missing CSS asset: ${url}`);
  }
});

test("install action is a real download plus guide, never a fake success", () => {
  const installers = [...html.matchAll(/<a[^>]*data-store-install[^>]*>/g)].map((m) => m[0]);
  assert.ok(installers.length >= 4, "every primary CTA offers the install action");
  for (const tag of installers) assert.ok(tag.includes('href="/keel-extension.zip"'), "installer targets the MV3 ZIP");
  assert.ok(js.includes('window.KEEL_INSTALL_MODE = "download"'));
  assert.ok(js.includes("load it unpacked") && js.includes("Nothing is installed automatically"));
  assert.ok(!/alert\(/.test(js), "no browser alert()");
  assert.ok(!html.includes("You're signed in"), "no fake sign-in success state");
});

test("interaction handlers are wired for menu, tabs, accordion, reveal and scroll", () => {
  for (const needle of [
    "[data-kic-mega-trigger]", "[data-kic-nav-toggle]", "[data-kic-tab]", "[data-kic-mode]",
    "[data-kic-faq]", "[data-kic-language]", "aria-expanded", "IntersectionObserver",
    "requestAnimationFrame", "{ passive: true }", "data-store-install",
  ]) assert.ok(js.includes(needle), `handler missing: ${needle}`);
  assert.ok(!js.includes("setInterval"), "no busy-loop timer");
});

test("scroll motion is small, short and has a reduced-motion kill switch", () => {
  assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"));
  const reveal = css.match(/\.kic-reveal\s*\{([^}]+)\}/);
  assert.ok(reveal, "reveal rule present");
  assert.ok(reveal[1].includes("translate3d(0, 14px, 0)"), "reveal moves at most 14px");
  for (const duration of reveal[1].match(/(\d+)ms/g) || []) {
    assert.ok(Number.parseInt(duration, 10) <= 220, `reveal too slow: ${duration}`);
  }
  assert.ok(css.includes("transform: none !important"), "reduced motion resets transforms");
  assert.ok(css.includes("scroll-behavior: auto"), "reduced motion disables smooth scrolling");
});

test("only local, deferred external assets; no inline code or data URIs", () => {
  assert.ok(html.includes('<script src="/ui/chrome-install.js" defer></script>'));
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), "no inline script");
  assert.ok(!/<style[\s>]/i.test(html), "no inline stylesheet");
  assert.ok(!/data:image/i.test(html + css), "no large inline data URIs");
});
