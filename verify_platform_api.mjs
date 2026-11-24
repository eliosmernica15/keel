#!/usr/bin/env node
/**
 * verify_platform_api.mjs
 * Dependency-free integrity + wiring verifier for the KEEL Platform page.
 *   node verify_platform_api.mjs
 */
import { readFileSync, existsSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SITE = join(ROOT, "keel", "site");
const HTML_PATH = join(SITE, "platform", "api.html");
const JS_PATH = join(SITE, "ui", "platform-api.js");
const CSS_PATH = join(SITE, "ui", "platform-api.css");
const VERCEL_PATH = join(SITE, "vercel.json");

const problems = [];
const notes = [];
const ok = (m) => notes.push("  ok  " + m);
const bad = (m) => problems.push("FAIL  " + m);

for (const p of [HTML_PATH, JS_PATH, CSS_PATH, VERCEL_PATH]) {
  if (!existsSync(p)) bad(`missing ${p.replace(ROOT + "\\", "")}`);
}
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}

const html = readFileSync(HTML_PATH, "utf8");
const js = readFileSync(JS_PATH, "utf8");
const css = readFileSync(CSS_PATH, "utf8");
const vercel = JSON.parse(readFileSync(VERCEL_PATH, "utf8"));

/* ---------- brand + baseline ---------- */
if (/claude|anthropic/i.test(html)) bad("HTML still contains Claude/Anthropic branding");
else ok("HTML is fully KEEL-branded");
if (!/<body class="pa-body"/.test(html)) bad("body.pa-body missing");
if (!/\/ui\/platform-api\.css/.test(html)) bad("stylesheet not linked");
if (!/\/ui\/platform-api\.js/.test(html)) bad("script not linked");
if (!/Skip to content/.test(html)) bad("skip link missing");
if (!/pa-modal/.test(html) || !/pa-toast/.test(html)) bad("modal/toast markup missing");

/* ---------- required structure ---------- */
const requiredIds = [
  "pa-header", "pa-main", "pa-progress", "pa-progress-fill", "pa-hamburger",
  "pa-mobile-menu", "pa-explore", "pa-explore-toggle", "pa-explore-list",
  "pa-top", "pa-models", "pa-design", "pa-agents", "pa-enterprise", "pa-cost",
  "pa-console", "pa-customers", "pa-cta", "pa-hub", "pa-hub-detail",
  "pa-flow-detail", "pa-console-detail", "pa-console-output", "pa-console-prompt-text",
  "pa-run", "pa-quotes", "pa-quote-prev", "pa-quote-next", "pa-quote-count",
  "pa-quote-dots", "pa-modal", "pa-modal-title", "pa-auth-form", "pa-contact-form",
  "pa-email", "pa-work-email", "pa-footer-search", "pa-footer-q", "pa-search-results", "pa-toast",
];
for (const id of requiredIds) {
  if (!new RegExp(`id="${id}"`).test(html)) bad(`missing id #${id}`);
}
ok(`checked ${requiredIds.length} required ids`);

for (const cls of [
  "pa-nav-trigger", "pa-mega", "pa-model-card", "pa-hub-node", "pa-flow-node",
  "pa-cost-tab", "pa-cost-panel", "pa-console-tab", "pa-quote-slide", "pa-footer-col",
  "pa-copy", "pa-hub-detail", "pa-btn", "pa-explore-link",
]) {
  if (!html.includes(cls)) bad(`missing class .${cls}`);
}

/* ---------- duplicate ids ---------- */
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
const dupes = ids.filter((v, i) => ids.indexOf(v) !== i);
if (dupes.length) bad(`duplicate ids: ${[...new Set(dupes)].join(", ")}`);
else ok(`${ids.length} unique ids`);

/* ---------- aria-controls targets ---------- */
for (const m of html.matchAll(/aria-controls="([^"]+)"/g)) {
  if (!new RegExp(`id="${m[1]}"`).test(html)) bad(`aria-controls points at missing #${m[1]}`);
}

/* ---------- dead links ---------- */
const anchors = [...html.matchAll(/<a\b[^>]*>/g)].map((m) => m[0]);
let dead = 0;
for (const a of anchors) {
  const href = (a.match(/\bhref="([^"]*)"/) || [])[1];
  const interactive = /\bdata-pa-/.test(a);
  if (href === undefined || href === "" || href === "#") {
    if (!interactive) { dead++; bad(`dead anchor: ${a.slice(0, 100)}`); }
  }
}
if (!dead) ok(`${anchors.length} anchors: no dead links`);

/* ---------- local assets exist ---------- */
const refs = new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]));
let missingAssets = 0;
for (const ref of refs) {
  const p = join(SITE, ref.replace(/^\//, ""));
  if (!existsSync(p)) { missingAssets++; bad(`missing asset ${ref}`); }
}
if (!missingAssets) ok(`${refs.size} local assets all present`);

/* ---------- route wiring ---------- */
const rw = (vercel.rewrites || []).find((r) => r.source === "/platform/api");
if (!rw || rw.destination !== "/platform/api.html") bad("vercel.json missing /platform/api rewrite");
else ok("/platform/api rewrite present");
const rd = (vercel.redirects || []).find((r) => r.source === "/platform/api.html");
if (!rd) bad("vercel.json missing .html -> clean URL redirect");
else ok("platform/api.html redirect present");

/* ---------- CSS scoping ---------- */
if (!css.includes("pa-body")) bad("CSS is not scoped to body.pa-body");
if (!css.includes("prefers-reduced-motion")) bad("CSS missing reduced-motion support");
if (!/@media[^{]*max-width/.test(css)) bad("CSS missing responsive breakpoints");

/* ---------- JS wiring ---------- */
const jsChecks = [
  "pa-nav-trigger", "aria-expanded", "pa-hamburger", "pa-explore-toggle", "pa-progress-fill",
  "pa-model-detail", "pa-hub-detail", "pa-flow-detail", "pa-cost-tab", "pa-console-tab",
  "pa-run", "pa-quote-next", "pa-quote-prev", "pa-footer-search", "pa-modal", "pa-toast",
  "clipboard", "Escape", "keel_logged_in",
];
const missingWiring = jsChecks.filter((token) => !js.includes(token));
if (missingWiring.length) bad(`JS missing wiring for: ${missingWiring.join(", ")}`);
else ok(`JS references all ${jsChecks.length} key hooks`);

try {
  execFileSync(process.execPath, ["--check", JS_PATH], { stdio: "pipe" });
  ok("node --check platform-api.js passes");
} catch (e) {
  bad("node --check failed: " + String(e.stderr || e.message).slice(0, 300));
}

/* ---------- report ---------- */
console.log(notes.join("\n"));
if (problems.length) {
  console.error("\n" + problems.join("\n"));
  console.error(`\n${problems.length} problem(s) found.`);
  process.exit(1);
}
console.log("\nALL CHECKS PASSED — KEEL Platform page is wired and branded.");
