/* Tests for the new /keel-for-microsoft-365 page.
 * Run: node --test keel/site/tests/m365.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(SITE, "..", "..");
const HTML_PATH = path.join(SITE, "keel-for-microsoft-365.html");
const INDEX_PATH = path.join(SITE, "keel-for-microsoft-365", "index.html");
const CSS_PATH = path.join(SITE, "ui", "m365.css");
const JS_PATH = path.join(SITE, "ui", "m365.js");
const SERVER = path.join(REPO, "serve_keel_site.mjs");

const html = fs.readFileSync(HTML_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const js = fs.readFileSync(JS_PATH, "utf8");
const vercel = JSON.parse(fs.readFileSync(path.join(SITE, "vercel.json"), "utf8"));
const serverSource = fs.readFileSync(SERVER, "utf8");
const sitemap = fs.readFileSync(path.join(SITE, "sitemap.xml"), "utf8");
const rewriteBySource = new Map(vercel.rewrites.map((r) => [r.source, r.destination]));

function localPath(href) {
  return path.join(SITE, href.replace(/^\/+/, ""));
}
function routeExists(href) {
  const file = localPath(href);
  if (fs.existsSync(file) && fs.statSync(file).isFile()) return true;
  if (fs.existsSync(path.join(file, "index.html"))) return true;
  return rewriteBySource.has(href);
}
function references(source) {
  return [...source.matchAll(/(?:href|src)="([^"]+)"/g)].map((m) => m[1]);
}

test("top-level HTML and physical route index are byte-identical", () => {
  assert.ok(fs.readFileSync(HTML_PATH).equals(fs.readFileSync(INDEX_PATH)),
    "keel-for-microsoft-365.html and keel-for-microsoft-365/index.html differ");
});

test("clean URL and trailing-slash rewrite are added in both configs", () => {
  assert.equal(rewriteBySource.get("/keel-for-microsoft-365"), "/keel-for-microsoft-365.html");
  assert.equal(rewriteBySource.get("/keel-for-microsoft-365/"), "/keel-for-microsoft-365.html");
  assert.match(serverSource, /['"]\/keel-for-microsoft-365['"]:\s*['"]\/keel-for-microsoft-365\.html['"]/);
  assert.match(serverSource, /['"]\/keel-for-microsoft-365\/['"]:\s*['"]\/keel-for-microsoft-365\.html['"]/);
  for (const source of ["/keel-for-microsoft-365", "/keel-for-microsoft-365/"]) {
    assert.ok(fs.existsSync(localPath(rewriteBySource.get(source))), `missing rewrite target: ${source}`);
  }
  for (const route of ["/login", "/download", "/keel-in-chrome", "/privacy"]) {
    assert.ok(rewriteBySource.has(route), `existing rewrite was removed: ${route}`);
  }
  const sources = vercel.rewrites.map((r) => r.source);
  assert.equal(new Set(sources).size, sources.length, "duplicate rewrite sources");
  const headerSources = vercel.headers.map((h) => h.source);
  for (const source of ["/(.*)", "/download.json", "/sw.js", "/ui/(.*)", "/assets/(.*)", "/screenshots/(.*)", "/store-assets/(.*)"]) {
    assert.ok(headerSources.includes(source), `existing header rule removed: ${source}`);
  }
});

test("sitemap lists the new clean URL", () => {
  const locs = [...sitemap.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/g)].map((m) => m[1]);
  assert.ok(locs.includes("https://keel-desktop.vercel.app/keel-for-microsoft-365"));
});

test("sections appear in the screenshot order", () => {
  const markers = [
    'id="m365-hero-title"',
    'id="m365-use-title"',
    'id="m365-trust-title"',
    'id="m365-customers-title"',
    'id="space"',
    'id="m365-cap-title"',
    'id="faq"',
    'id="get-started"',
  ];
  let previous = -1;
  for (const marker of markers) {
    const at = html.indexOf(marker);
    assert.ok(at > previous, `missing or out-of-order section: ${marker}`);
    previous = at;
  }
});

test("breadcrumb, hero copy, sticky note and both hero buttons match the reference", () => {
  assert.ok(html.includes("Keel for Microsoft 365"), "breadcrumb present");
  assert.ok(html.includes('class="m365-crumb" aria-current="page">Keel for Microsoft 365<'), "breadcrumb marked as current page");
  assert.ok(html.includes('id="m365-hero-title">Work without the window shuffle<'));
  assert.ok(html.includes("Keel is available inside Word, Excel, PowerPoint, and Outlook. Start your task in the app and take it with you."));
  assert.ok(html.includes("Get Keel for Microsoft 365"));
  assert.ok(html.includes("Sign in to Outlook"));
  assert.ok(html.includes('class="m365-note"'), "orange sticky-note mock present");
  assert.ok(html.includes('class="m365-squiggle"'), "handwritten squiggle present");
  for (const app of ["Word", "Excel", "PowerPoint", "Outlook"]) {
    assert.ok(html.includes(app), `app chip: ${app}`);
  }
});

test("navigation has four Product mega columns and the top links", () => {
  assert.equal((html.match(/class="m365-mega-col"/g) || []).length, 4);
  assert.ok(html.includes("data-m365-mega-trigger"));
  for (const label of ["Log in", "Contact sales", "Get Keel"]) {
    assert.ok(html.includes(label), `top link missing: ${label}`);
  }
  assert.ok(html.includes('href="/login">Log in<'), "log in uses the existing /login route");
  assert.ok(html.includes('href="/requirements">Contact sales<'));
  assert.ok(html.includes('href="/keel-for-microsoft-365">Keel for Microsoft 365<'));
});

test("use section has the video mock and four task cards", () => {
  assert.ok(html.includes("How teams use Keel for Microsoft 365"));
  assert.ok(html.includes("Create and review files with Keel in Microsoft 365"));
  assert.ok(html.includes('data-m365-dialog-open="story"'), "play mock opens a real storyboard");
  const tasks = [
    "Type a prompt to create a file",
    "Clean up your inbox with prompts",
    "Build a monthly tracker without a formula",
    "Draft your response in Keel",
  ];
  for (const title of tasks) assert.ok(html.includes(title), `task card missing: ${title}`);
  assert.equal((html.match(/class="m365-task-card m365-reveal"/g) || []).length, 4);
});

test("trust section has three items and the floating admin card demo", () => {
  assert.ok(html.includes("The Keel you trust, inside Microsoft 365"));
  for (const title of ["Every action is visible", "Your examples and knowledge", "Enterprise security"]) {
    assert.ok(html.includes(title), `trust item missing: ${title}`);
  }
  assert.ok(html.includes("Microsoft 365 admin controls"));
  assert.ok(html.includes('data-m365-dialog-open="admin">Show demo<'));
});

test("three named testimonials have quotes and story links", () => {
  assert.ok(html.includes("What customers are saying"));
  for (const company of ["Deloitte", "Rackspace", "Thomson"]) {
    assert.ok(html.includes(`class="m365-quote-company">${company}<`), `testimonial missing: ${company}`);
  }
  assert.equal((html.match(/Read the full story/g) || []).length, 3);
  for (const link of html.match(/<a class="m365-learn" href="([^"]+)">Read the full story/g) || []) {
    assert.ok(link.includes('href="/resources/articles"'), "story links use an existing route");
  }
});

test("large whitespace section is kept before the capabilities section", () => {
  const spaceAt = html.indexOf('id="space"');
  const capAt = html.indexOf('id="m365-cap-title"');
  assert.ok(spaceAt > 0 && capAt > spaceAt);
  assert.ok(/\.m365-space\s*\{[^}]*min-height:\s*190px/.test(css), "breathing room is deliberately large");
});

test("six core capability cards are present", () => {
  assert.ok(html.includes("Core capabilities across the apps you use every day"));
  for (const title of [
    "Connect to available Microsoft apps",
    "Appointments through your calendar",
    "Write and document with the conversation",
    "Type multiple tabs in Excel",
    "Type with voice or text to format a form",
    "Access workspaces",
  ]) assert.ok(html.includes(title), `capability missing: ${title}`);
  assert.equal((html.match(/class="m365-cap-card m365-reveal"/g) || []).length, 6);
});

test("FAQ has the four required questions as working accordion buttons", () => {
  const questions = [...html.matchAll(/<button class="m365-faq-q"[^>]*><span>([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(questions, [
    "Where is this available?",
    "How does Keel change my Office experience?",
    "Can I add Keel to the app without changing my tenant?",
    "Can Keel work in Excel without me being in Teams?",
  ]);
  for (const id of ["m365-faq-a-1", "m365-faq-a-2", "m365-faq-a-3", "m365-faq-a-4"]) {
    assert.ok(html.includes(`aria-controls="${id}"`) && html.includes(`id="${id}"`), `FAQ pair ${id}`);
  }
});

test("dark CTA and footer carry the remaining actions and language selector", () => {
  assert.ok(html.includes("Get started with Keel for Microsoft 365"));
  assert.equal((html.match(/data-m365-dialog-open="docs"/g) || []).length, 1);
  assert.ok(html.includes("Read the docs"));
  assert.ok(html.includes("data-m365-language"));
  assert.ok(html.includes('id="m365-lang-status"'));
  for (const column of ["Products", "Capabilities", "Extensions", "Resources", "Company", "Legal"]) {
    assert.ok(html.includes(`<h3>${column}</h3>`), `footer column missing: ${column}`);
  }
});

test("no Claude branding and no /app links", () => {
  for (const [name, source] of [["html", html], ["css", css], ["js", js]]) {
    assert.ok(!/claude/i.test(source), `${name} still mentions the original brand`);
  }
  assert.ok(!/\/app(?:["'\/])/.test(html), "no /app links (use /login)");
});

test("every absolute link, stylesheet and script resolves locally", () => {
  const local = [...new Set(references(html).filter((href) => href.startsWith("/")))];
  assert.ok(local.length > 0, "page has local references");
  for (const href of local) {
    const target = href.split("#")[0].split("?")[0];
    assert.ok(routeExists(target), `broken local reference: ${href}`);
  }
  assert.ok(html.includes('href="/ui/m365.css"'));
  assert.ok(html.includes('<script src="/ui/m365.js" defer></script>'));
  for (const url of [...css.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1])) {
    if (url.startsWith("data:")) continue;
    assert.ok(routeExists(url.replace(/^["']|["']$/g, "")), `missing CSS asset: ${url}`);
  }
});

test("only local deferred assets; no inline code or data URIs", () => {
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), "no inline script");
  assert.ok(!/<style[\s>]/i.test(html), "no inline stylesheet");
  assert.ok(!/data:image/i.test(html + css), "no large inline data URIs");
  const scripts = [...html.matchAll(/<script[^>]*src="([^"]+)"[^>]*>/g)].map((m) => m[0]);
  assert.equal(scripts.length, 1, "one external script");
  assert.ok(scripts[0].includes("defer"));
  assert.ok(scripts[0].includes('src="/ui/m365.js"'));
});

test("every dialog trigger has an honest local template with real next steps", () => {
  const kinds = [...new Set([...html.matchAll(/data-m365-dialog-open="([^"]+)"/g)].map((m) => m[1]))];
  assert.deepEqual(kinds.sort(), ["admin", "docs", "get", "outlook", "story"]);
  for (const kind of kinds) {
    assert.ok(html.includes(`id="m365-tpl-${kind}"`), `missing dialog template: ${kind}`);
  }
  const get = html.slice(html.indexOf('id="m365-tpl-get"'), html.indexOf('id="m365-tpl-outlook"'));
  assert.ok(get.includes("Nothing is installed"), "get dialog is honest about install state");
  assert.ok(get.includes('href="/login"') && get.includes('href="/requirements"'), "get dialog links to real routes");
  assert.ok(!html.includes("installation successful"), "no fake install success");
  assert.ok(!html.includes("You're signed in"), "no fake sign-in success");
  assert.ok(html.includes("No video file is bundled"), "storyboard is labelled as storyboard");
});

test("interaction handlers are wired for menu, dialogs, demo, story, FAQ, reveal and scroll", () => {
  for (const needle of [
    "[data-m365-mega-trigger]", "[data-m365-nav-toggle]", "[data-m365-dialog-open]",
    "[data-m365-dialog-close]", "[data-m365-story-step]", "[data-m365-demo-tab]",
    "[data-m365-faq]", "[data-m365-language]", "aria-expanded", "IntersectionObserver",
    "requestAnimationFrame", "{ passive: true }", "prefers-reduced-motion",
  ]) assert.ok(js.includes(needle), `handler missing: ${needle}`);
  assert.ok(!js.includes("setInterval"), "no busy-loop timer");
  assert.ok(!/\balert\s*\(/.test(js), "no browser alert()");
});

test("scroll motion is small, short and has a reduced-motion kill switch", () => {
  assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"));
  const reveal = css.match(/\.m365-reveal\s*\{([^}]+)\}/);
  assert.ok(reveal, "reveal rule present");
  assert.ok(reveal[1].includes("translate3d(0, 14px, 0)"), "reveal moves at most 14px");
  for (const duration of reveal[1].match(/(\d+)ms/g) || []) {
    assert.ok(Number.parseInt(duration, 10) <= 220, `reveal too slow: ${duration}`);
  }
  assert.ok(css.includes("transform: none !important"), "reduced motion resets transforms");
  assert.ok(css.includes("scroll-behavior: auto"), "reduced motion disables smooth scrolling");
});

async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

test("QA server serves both clean URLs with the real page", async () => {
  const port = await freePort();
  const child = spawn(process.execPath, [SERVER], {
    cwd: REPO,
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout.on("data", (chunk) => { output += String(chunk); });
  child.stderr.on("data", (chunk) => { output += String(chunk); });
  try {
    const deadline = Date.now() + 10000;
    while (!output.includes("Keel QA server") && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 25));
      if (child.exitCode !== null) break;
    }
    assert.match(output, /Keel QA server/, "QA server did not start");
    for (const route of ["/keel-for-microsoft-365", "/keel-for-microsoft-365/"]) {
      const response = await fetch(`http://127.0.0.1:${port}${route}`);
      const body = await response.text();
      assert.equal(response.status, 200, `${route}: expected 200`);
      assert.match(body, /Work without the window shuffle/, `${route}: wrong page`);
      assert.ok(body.includes("/ui/m365.css") && body.includes("/ui/m365.js"), `${route}: assets linked`);
    }
  } finally {
    if (child.exitCode === null) {
      child.kill();
      await new Promise((resolve) => child.once("exit", resolve));
    }
  }
});
