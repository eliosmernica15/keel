#!/usr/bin/env node
/* Static QA for the KEEL Cowork page. Reads local files only; no writes, no network.
 * Run from the workspace root: node verify_cowork_ui.mjs
 */
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = process.cwd();
const SITE = join(ROOT, 'keel', 'site');

let passes = 0;
let failures = 0;

function check(name, ok, detail = '') {
  if (ok) {
    passes++;
    console.log(`PASS ${name}`);
  } else {
    failures++;
    console.log(`FAIL ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

function source(rel) {
  const full = resolve(ROOT, rel);
  if (!existsSync(full)) return null;
  return readFileSync(full, 'utf8');
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const hasId = (src, id) => new RegExp(`\\bid\\s*=\\s*["']${escapeRe(id)}["']`).test(src);
const hasWord = (src, word) => new RegExp(`\\b${escapeRe(word)}\\b`).test(src);
const hasAttr = (src, attr) => new RegExp(`\\b${escapeRe(attr)}(\\s|=|\\s*/?>)`).test(src);
const hasAttrValue = (src, attr, value) =>
  new RegExp(`\\b${escapeRe(attr)}\\s*=\\s*["'][^"']*\\b${escapeRe(value)}\\b[^"']*["']`, 'i').test(src);

/* Remove things that are explicitly allowed to carry URLs before scanning. */
function stripAllowedUrls(src, isHtml) {
  let s = src.replace(/\sxmlns(?::[\w-]+)?\s*=\s*["'][^"']*["']/gi, '');
  if (isHtml) {
    s = s.replace(/<meta\b[^>]*>/gi, ''); // canonical/site URLs in meta head tags
    s = s.replace(/<link\b[^>]*\brel\s*=\s*["'][^"']*canonical[^"']*["'][^>]*>/gi, '');
  }
  return s.replace(/https?:\/\/(?:www\.)?w3\.org\/[^\s"'<>)]*/gi, '');
}
function externalUrls(src, isHtml) {
  return stripAllowedUrls(src, isHtml).match(/https?:\/\/[^\s"'<>)]+/gi) || [];
}
function forbiddenBrand(src) {
  return /\b(?:Claude|Anthropic)\b/i.test(src);
}

console.log('KEEL Cowork UI / routing QA');
console.log('(workspace root: ' + ROOT + ')\n');

/* --- Files exist ---------------------------------------------------------- */
const html = source('keel/site/product/cowork.html');
const css = source('keel/site/ui/cowork.css');
const js = source('keel/site/ui/cowork.js');
const vercel = source('keel/site/vercel.json');
const sitemap = source('keel/site/sitemap.xml');
const server = source('serve_keel_site.mjs');

check('cowork.html exists', html !== null);
check('cowork.css exists', css !== null);
check('cowork.js exists', js !== null);
check('vercel.json exists', vercel !== null);
check('sitemap.xml exists', sitemap !== null);
check('serve_keel_site.mjs exists', server !== null);

/* --- HTML: section IDs and global DOM hooks -------------------------------- */
if (html) {
  const SECTION_IDS = [
    'main-content', 'cw-header', 'hero', 'capabilities', 'tasks', 'plugins',
    'blog', 'usecase', 'control', 'pricing', 'faq', 'get-started',
  ];
  for (const id of SECTION_IDS) check(`HTML section id #${id}`, hasId(html, id));

  const DOM_HOOKS = [
    'cw-body', 'cw-skip', 'cw-page', 'cw-header', 'cw-brand', 'cw-mobile-menu',
    'cw-news', 'cw-footer', 'cw-cookie', 'cw-toast', 'contact-modal',
    'auth-modal', 'video-modal',
  ];
  const missingDom = DOM_HOOKS.filter((h) => !hasWord(html, h));
  check('HTML global DOM hooks', missingDom.length === 0, missingDom.join(', '));

  const DATA_ATTRS = [
    'data-nav', 'data-action', 'data-task', 'data-prompt', 'data-view',
    'data-carousel', 'data-persona', 'data-plan', 'data-faq', 'data-form', 'data-lang',
  ];
  const missingAttrs = DATA_ATTRS.filter((a) => !hasAttr(html, a));
  check('HTML data-* attribute hooks', missingAttrs.length === 0, missingAttrs.join(', '));

  const DATA_VALUES = [
    ['data-nav', ['product', 'developers', 'enterprise']],
    ['data-action', ['open-auth', 'open-contact', 'dismiss-news', 'open-video', 'cookie-accept', 'cookie-decline']],
    ['data-task', ['reports', 'sheets', 'review', 'notes']],
    ['data-view', ['slides', 'data']],
    ['data-carousel', ['plugins', 'quotes']],
    ['data-persona', ['marketing', 'sales', 'legal']],
    ['data-plan', ['individual', 'team']],
    ['data-form', ['contact', 'footer-search']],
  ];
  for (const [attr, values] of DATA_VALUES) {
    const missing = values.filter((v) => !hasAttrValue(html, attr, v));
    check(`HTML ${attr} values`, missing.length === 0, missing.join(', '));
  }

  check('HTML has no forbidden brand strings', !forbiddenBrand(html));
}

/* --- CSS selectors --------------------------------------------------------- */
if (css) {
  for (const selector of ['.cw-body', '.cw-header', '.cw-hero', '.cw-footer']) {
    check(`CSS defines ${selector}`, css.includes(selector));
  }
}

/* --- JS behavior hooks ----------------------------------------------------- */
if (js) {
  const HOOKS = [
    'dismiss-news', 'open-contact', 'open-auth', 'open-video',
    'carousel', 'faq', 'footer-search', 'cookie-accept', 'cookie-decline',
  ];
  for (const hook of HOOKS) {
    check(`JS handles ${hook}`, js.toLowerCase().includes(hook.toLowerCase()));
  }
}

/* --- Routing --------------------------------------------------------------- */
if (vercel) {
  let config = null;
  try {
    config = JSON.parse(vercel);
    check('vercel.json is valid JSON', true);
  } catch (err) {
    check('vercel.json is valid JSON', false, err.message);
  }
  if (config) {
    const rewrites = Array.isArray(config.rewrites) ? config.rewrites : [];
    const redirects = Array.isArray(config.redirects) ? config.redirects : [];
    check(
      'vercel.json rewrite /product/cowork -> /product/cowork.html',
      rewrites.some((r) => r && r.source === '/product/cowork' && r.destination === '/product/cowork.html')
    );
    check(
      'vercel.json redirect /product/cowork.html -> /product/cowork',
      redirects.some((r) => r && r.source === '/product/cowork.html' && r.destination === '/product/cowork')
    );
  }
}

if (sitemap) {
  const entry = sitemap.match(/<url>\s*<loc>[^<]*\/product\/cowork<\/loc>[\s\S]*?<\/url>/);
  check('sitemap.xml includes /product/cowork', Boolean(entry));
  if (entry) {
    check('sitemap cowork lastmod is 2026-11-24', entry[0].includes('<lastmod>2026-11-24</lastmod>'));
    check('sitemap cowork priority is 0.9', entry[0].includes('<priority>0.9</priority>'));
  }
}

if (server) {
  check(
    'serve_keel_site.mjs maps /product/cowork -> /product/cowork.html',
    /['"]\/product\/cowork['"]\s*:\s*['"]\/product\/cowork\.html['"]/.test(server)
  );
}

/* --- No external requests in page source ----------------------------------- */
const SOURCES = [
  ['cowork.html', html, true],
  ['cowork.css', css, false],
  ['cowork.js', js, false],
];
for (const [name, src, isHtml] of SOURCES) {
  if (src === null) continue;
  const urls = externalUrls(src, isHtml);
  check(`${name} has no external http(s) URLs`, urls.length === 0, urls.slice(0, 5).join(' '));
  check(`${name} has no forbidden brand strings`, !forbiddenBrand(src));
}

/* --- Local SVG artwork ----------------------------------------------------- */
const SVGS = [
  'cw-mark.svg', 'cw-app-window.svg',
  'cw-cap-1.svg', 'cw-cap-2.svg', 'cw-cap-3.svg', 'cw-cap-4.svg', 'cw-cap-5.svg', 'cw-cap-6.svg',
  'cw-browser.svg', 'cw-amplitude.svg', 'cw-microsoft.svg', 'cw-deck.svg', 'cw-data.svg', 'cw-plugins.svg',
  'cw-article-browser.svg', 'cw-article-enterprise.svg', 'cw-article-plugins.svg',
  'cw-video-marketing.svg', 'cw-video-sales.svg', 'cw-video-legal.svg',
  'cw-partner-1.svg', 'cw-partner-2.svg', 'cw-partner-3.svg',
  'cw-quote-1.svg', 'cw-quote-2.svg', 'cw-quote-3.svg', 'cw-quote-4.svg', 'cw-quote-5.svg',
];
for (const name of SVGS) {
  const svg = source(`keel/site/assets/img/${name}`);
  if (svg === null) {
    check(`asset ${name}`, false, 'missing');
    continue;
  }
  const problems = [];
  if (!/<svg\b/i.test(svg)) problems.push('no <svg> root');
  if (!/\bviewBox\s*=/.test(svg)) problems.push('no viewBox');
  if (!/<title\b/i.test(svg)) problems.push('no <title>');
  if (externalUrls(svg, false).length) problems.push('external URL');
  if (forbiddenBrand(svg)) problems.push('forbidden brand string');
  check(`asset ${name}`, problems.length === 0, problems.join(', '));
}

/* Every cw-* SVG referenced by the page or script must exist on disk. */
const referenced = new Set();
for (const src of [html, css, js]) {
  if (!src) continue;
  for (const match of src.matchAll(/assets\/img\/(cw-[a-z0-9-]+\.svg)/gi)) referenced.add(match[1]);
}
const missingRefs = [...referenced].filter((name) => !existsSync(join(SITE, 'assets', 'img', name)));
check('all referenced cw-* SVGs exist', missingRefs.length === 0, missingRefs.join(', '));

/* --- Summary --------------------------------------------------------------- */
console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
