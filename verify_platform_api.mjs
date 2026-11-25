#!/usr/bin/env node
/** Dependency-free integrity + wiring verifier for the rebuilt KEEL Platform page. */
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SITE = join(ROOT, "keel", "site");
const HTML_PATH = join(SITE, "platform", "api.html");
const INDEX_PATH = join(SITE, "platform", "api", "index.html");
const JS_PATH = join(SITE, "ui", "platform-api.js");
const CSS_PATH = join(SITE, "ui", "platform-api.css");
const VERCEL_PATH = join(SITE, "vercel.json");

const problems = [], notes = [];
const ok = (m) => notes.push("  ok  " + m);
const bad = (m) => problems.push("FAIL  " + m);

for (const p of [HTML_PATH, INDEX_PATH, JS_PATH, CSS_PATH, VERCEL_PATH]) {
  if (!existsSync(p)) bad(`missing ${p.replace(ROOT + "\\", "")}`);
}
if (problems.length) { console.error(problems.join("\n")); process.exit(1); }

const html = readFileSync(HTML_PATH, "utf8");
const index = readFileSync(INDEX_PATH, "utf8");
const js = readFileSync(JS_PATH, "utf8");
const css = readFileSync(CSS_PATH, "utf8");
const vercel = JSON.parse(readFileSync(VERCEL_PATH, "utf8"));

if (html !== index) bad("platform/api/index.html is not identical to api.html");
else ok("api.html and directory index are identical");

if (/claude|anthropic/i.test(html)) bad("HTML still contains Claude/Anthropic branding");
else ok("HTML fully KEEL-branded");
if (!/<body class="pa-body"/.test(html)) bad("body.pa-body missing");
if (!/\/ui\/platform-api\.css/.test(html)) bad("stylesheet not linked");
if (!/\/ui\/platform-api\.js/.test(html)) bad("script not linked");
if (!/Skip to content/.test(html)) bad("skip link missing");
if (!/pa-modal/.test(html) || !/pa-toast/.test(html)) bad("modal/toast missing");

/* Exact content from the reference screenshot */
const content = [
  "Build frontier agents", "KEEL models for every job", "Fable 5.2", "Opus 5.5",
  "Sonnet 5.5", "Haiku 5.5", "APIs designed for KEEL", "BETA",
  "Power your most ambitious workflows with KEEL Managed Agents",
  "Extend and customize what KEEL can do.", "KEEL Marketplace",
  "Built for enterprise workloads", "Control cost and performance",
  "Observe and manage your agents with the KEEL Console",
  "See why businesses build on the KEEL Platform", "Trusted by",
  "Build on the KEEL Platform", "Get the developer newsletter"
];
const missingContent = content.filter((s) => !html.includes(s));
if (missingContent.length) bad(`missing reference content: ${missingContent.join(" | ")}`);
else ok(`all ${content.length} reference headings/labels present`);
for (const price of ["$0.20 / MTok", "$10 / MTok", "$8 / MTok", "$40 / MTok", "$0.01 / MTok", "$2.50 / MTok"]) {
  if (!html.includes(price)) bad(`missing model price ${price}`);
}

const requiredIds = [
  "pa-progress", "pa-progress-fill", "pa-header", "pa-hamburger", "pa-mobile-menu",
  "pa-explore-toggle", "pa-explore-panel", "pa-page-outline", "pa-main", "pa-top",
  "pa-models", "pa-model-banner", "pa-batch-toggle", "pa-design", "pa-agents",
  "pa-agent-features", "pa-customize", "pa-marketplace", "pa-enterprise", "pa-cost",
  "pa-console", "pa-console-request", "pa-console-prompt", "pa-customers", "pa-quotes",
  "pa-quote-count", "pa-quote-dots", "pa-quote-prev", "pa-quote-next", "pa-resources",
  "pa-cta", "pa-newsletter-form", "pa-newsletter-email", "pa-footer-search", "pa-footer-q",
  "pa-search-results", "pa-modal", "pa-modal-title", "pa-modal-desc", "pa-auth-form",
  "pa-google", "pa-email", "pa-contact-form", "pa-name", "pa-work-email", "pa-message",
  "pa-ask-form", "pa-ask-q", "pa-ask-results", "pa-toast",
  "pa-menu-product", "pa-menu-developers", "pa-menu-enterprise", "pa-menu-resources", "pa-menu-pricing"
];
for (const id of requiredIds) if (!new RegExp(`id="${id}"`).test(html)) bad(`missing id #${id}`);
ok(`checked ${requiredIds.length} required ids`);

for (const cls of ["pa-nav-trigger", "pa-mega", "pa-model-card", "pa-quote-slide", "pa-footer-col", "pa-copy", "pa-glyph", "pa-btn", "pa-explore-action"]) {
  if (!html.includes(cls)) bad(`missing class .${cls}`);
}

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
const dupes = ids.filter((v, i) => ids.indexOf(v) !== i);
if (dupes.length) bad(`duplicate ids: ${[...new Set(dupes)].join(", ")}`);
else ok(`${ids.length} unique ids`);

for (const m of html.matchAll(/aria-controls="([^"]+)"/g)) {
  if (!new RegExp(`id="${m[1]}"`).test(html)) bad(`aria-controls points at missing #${m[1]}`);
}

const anchors = [...html.matchAll(/<a\b[^>]*>/g)].map((m) => m[0]);
let dead = 0;
for (const a of anchors) {
  const href = (a.match(/\bhref="([^"]*)"/) || [])[1];
  if ((href === undefined || href === "" || href === "#") && !/\bdata-pa-/.test(a)) {
    dead++; bad(`dead anchor: ${a.slice(0, 90)}`);
  }
}
if (!dead) ok(`${anchors.length} anchors: no dead links`);

const refs = new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]));
let missingAssets = 0;
for (const ref of refs) if (!existsSync(join(SITE, ref.replace(/^\//, "")))) { missingAssets++; bad(`missing asset ${ref}`); }
if (!missingAssets) ok(`${refs.size} local assets all present`);

const slides = (html.match(/data-pa-slide="/g) || []).length;
const dots = (html.match(/data-pa-quote-dot="/g) || []).length;
if (slides !== 19 || dots !== 19) bad(`testimonials need 19 slides + 19 dots (got ${slides}/${dots})`);
else ok("19 testimonials with 19 dots");

const rw = (vercel.rewrites || []).find((r) => r.source === "/platform/api");
if (!rw || rw.destination !== "/platform/api.html") bad("vercel.json missing /platform/api rewrite");
else ok("/platform/api rewrite present");
const rd = (vercel.redirects || []).find((r) => r.source === "/platform/api.html");
if (!rd) bad("vercel.json missing .html redirect");
else ok("platform/api.html redirect present");

if (!css.includes("pa-body")) bad("CSS not scoped to body.pa-body");
if (!css.includes("prefers-reduced-motion")) bad("CSS missing reduced motion");
if (!/@media[^{]*max-width/.test(css)) bad("CSS missing responsive breakpoints");
if (!css.includes("#b9cdc5") && !/185,\s*205,\s*197/.test(css)) bad("CSS missing sage console panel colour");

const jsHooks = ["pa-nav-trigger", "aria-expanded", "pa-explore-toggle", "pa-explore-panel", "pa-batch-toggle",
  "pa-model-detail", "pa-quote-next", "pa-quote-dot", "pa-newsletter-form", "pa-footer-search",
  "pa-modal", "pa-toast", "clipboard", "Escape", "keel_logged_in", "pa-ask-form", "pa-video"];
const missingHooks = jsHooks.filter((t) => !js.includes(t));
if (missingHooks.length) bad(`JS missing hooks: ${missingHooks.join(", ")}`);
else ok(`JS references all ${jsHooks.length} key hooks`);

try { execFileSync(process.execPath, ["--check", JS_PATH], { stdio: "pipe" }); ok("node --check platform-api.js passes"); }
catch (e) { bad("node --check failed: " + String(e.stderr || e.message).slice(0, 300)); }

console.log(notes.join("\n"));
if (problems.length) { console.error("\n" + problems.join("\n")); console.error(`\n${problems.length} problem(s) found.`); process.exit(1); }
console.log("\nALL CHECKS PASSED — rebuilt KEEL Platform page matches the reference structure.");
