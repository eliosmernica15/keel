/* Static + local-route verification for the Keel for Google Workspace page.
 * Run: node --test keel/site/tests/gworkspace.test.mjs
 * The page must match the supplied reference structure, use only real routes,
 * keep both HTML entry points in sync, and wire real in-page behaviour.
 */
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO = path.resolve(SITE, '..', '..');
const HTML_PATH = path.join(SITE, 'keel-for-google-workspace.html');
const INDEX_PATH = path.join(SITE, 'keel-for-google-workspace', 'index.html');
const CSS_PATH = path.join(SITE, 'ui', 'gworkspace.css');
const JS_PATH = path.join(SITE, 'ui', 'gworkspace.js');
const VERCEL = JSON.parse(fs.readFileSync(path.join(SITE, 'vercel.json'), 'utf8'));
const SERVER = fs.readFileSync(path.join(REPO, 'serve_keel_site.mjs'), 'utf8');
const SITEMAP = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');

const html = fs.readFileSync(HTML_PATH, 'utf8');
const index = fs.readFileSync(INDEX_PATH, 'utf8');
const css = fs.readFileSync(CSS_PATH, 'utf8');
const js = fs.readFileSync(JS_PATH, 'utf8');
const owned = { html, index, css, js };

function ordered(source, needles, label) {
  let cursor = -1;
  for (const needle of needles) {
    const found = source.indexOf(needle, cursor + 1);
    assert.notEqual(found, -1, `${label}: missing ${JSON.stringify(needle)}`);
    cursor = found;
  }
}

test('both Google Workspace entry points exist and stay byte-identical', () => {
  assert.ok(fs.existsSync(HTML_PATH), 'missing keel-for-google-workspace.html');
  assert.ok(fs.existsSync(INDEX_PATH), 'missing keel-for-google-workspace/index.html');
  assert.equal(html, index, 'the two entry points must serve the same design');
  assert.match(html, /^<!doctype html>/i, 'HTML document type');
  assert.match(html, /<body class="duet-page gworkspace-page">/, 'page body class');
  assert.match(html, /href="\/ui\/keel-duet-shell\.css"/, 'shared shell stylesheet');
  assert.match(html, /href="\/ui\/gworkspace\.css"/, 'page stylesheet');
  assert.match(html, /<script src="\/ui\/gworkspace\.js" defer><\/script>/, 'deferred JS');
  assert.match(html,
    /<link rel="canonical" href="https:\/\/keel-desktop\.vercel\.app\/keel-for-google-workspace" \/>/,
    'canonical URL');
  assert.match(html, /<title>Keel for Google Workspace — Expertise in every app<\/title>/,
    'page title');
});

test('no stale branding, no /app links, no inline handlers or data URIs', () => {
  for (const [name, source] of Object.entries(owned)) {
    assert.doesNotMatch(source, /claude/i, `${name}: stale branding`);
  }
  assert.doesNotMatch(html, /\/app(?=["'/]|$)/, 'no /app links; use /login');
  assert.doesNotMatch(html, /href="\/app/, 'no app links');
  const inlineHandler = /\s(?:onclick|onload|onerror|onchange|onsubmit|onmouseover|onfocus|onblur|onkeydown)\s*=/i;
  assert.doesNotMatch(html, inlineHandler, 'no inline event handlers in HTML');
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)|<style[\s>]/i, 'no inline script or style blocks');
  assert.doesNotMatch(html, /data:image/i, 'no inline data URIs in markup');
  assert.doesNotMatch(css, /data:image/i, 'no inline data URIs in CSS');
});

test('reference sections appear in order with the right breadcrumb', () => {
  ordered(html, [
    '<header class="l-header s-header">',
    '<nav class="s-crumbs l-container"',
    '<section class="s-hero" id="workspace-home">',
    '<section class="s-trust" id="trust">',
    '<section class="s-capabilities" id="capabilities">',
    '<section class="s-faq" id="faq">',
    '<section class="s-cta" id="get-started">',
    '<footer class="l-footer" id="footer">'
  ], 'page structure');
  assert.match(html, /<nav class="s-crumbs l-container" aria-label="Breadcrumb">.*?Keel for Google Workspace<\/nav>/,
    'breadcrumb ends with Keel for Google Workspace');
});

test('sticky nav has a four-column Product mega menu and real top links', () => {
  const productMega = html.slice(
    html.indexOf('<div class="l-mega" id="mega-product"'),
    html.indexOf('<div class="l-nav-item" data-menu="developers">')
  );
  assert.equal((productMega.match(/class="l-mega-col"/g) || []).length, 4,
    'Product mega menu has four columns');
  assert.match(productMega,
    /href="\/keel-for-google-workspace" aria-current="page">Keel for Google Workspace<\/a>/,
    'Extensions → Keel for Google Workspace is the current page');
  assert.match(html, /class="l-nav-link" href="\/login">Log in<\/a>/, 'Log in link');
  assert.match(html, /class="l-nav-link" href="mailto:hello@keel\.ai">Contact sales<\/a>/,
    'Contact sales link');
  assert.match(html, /class="l-btn l-btn-dark l-btn-sm" href="\/login">Get Keel<\/a>/,
    'Get Keel link');
  assert.match(html, /<a href="\/keel-for-google-workspace">Keel for Google Workspace<\/a>/,
    'mobile menu includes this page');
});

test('hero reproduces the reference copy, Sheets mock and try button', () => {
  assert.match(html, /<p class="s-eyebrow">Keel for Google Workspace \(Beta\)<\/p>/,
    'beta eyebrow');
  assert.match(html, /<h1 class="s-hero-title">Expertise in every app<\/h1>/,
    'serif hero heading');
  assert.match(html,
    /Put Keel to work in Google Docs, Sheets, and Slides, on your files directly in Keel\. Craft, analyze, and build on the file you have open\. Accept or edit any change\./,
    'hero subtitle');
  assert.match(html,
    /<button class="l-btn l-btn-dark" type="button" data-try>Try Keel for Google Workspace<\/button>/,
    'hero try button');
  assert.match(html, /<span class="s-sheet-title">Q3 2020 budget vs actuals<\/span>/,
    'Q3 2020 budget vs actuals mock');
  assert.match(html, /data-cell="D2" data-value="\+6,400"/, 'variance cell');
  assert.match(html, /data-cell="E3"/, 'notes cell');
  assert.match(html, /<aside class="s-keel-panel" aria-label="Keel side panel">/,
    'Keel side panel');
  assert.equal((html.match(/data-sheet-tab=/g) || []).length, 3, 'three sheet tabs');
  assert.equal((html.match(/data-panel-tab=/g) || []).length, 2, 'two Keel panel tabs');
});

test('trust section has three items and the floating admin card', () => {
  for (const heading of ['Review your edits', 'Keep your formatting', 'Admin controls, built in']) {
    assert.ok(html.includes(`<h3>${heading}</h3>`), `trust item: ${heading}`);
  }
  assert.match(html, /<h2 class="s-section-title">The Keel you trust, inside Google Workspace<\/h2>/,
    'trust heading');
  assert.match(html, /<p class="s-admin-kicker">Google Workspace admin controls<\/p>/,
    'orange card kicker');
  assert.match(html, /<p class="s-admin-copy">Keel can only access files users explicitly share\.<\/p>/,
    'orange card copy');
  assert.match(html, /data-admin-demo aria-controls="adminDialog">Show demo<\/button>/,
    'Show demo button');
});

test('capabilities section keeps four cards with real learn-more disclosures', () => {
  assert.match(html,
    /<h2 class="s-section-title">Core capabilities across the apps you use every day<\/h2>/,
    'capabilities heading');
  for (const heading of [
    'Bring in your tools', 'Turn workflows into skills',
    'Set your preferences', 'Bring in reference files'
  ]) {
    assert.ok(html.includes(`<h3>${heading}</h3>`), `capability: ${heading}`);
  }
  assert.equal((html.match(/data-learn=/g) || []).length, 4, 'four learn-more controls');
  assert.equal((html.match(/>Learn more <span aria-hidden="true">→<\/span><\/button>/g) || []).length,
    4, 'four Learn more labels');
  assert.match(html, /class="s-capabilities" id="capabilities"/, 'generous capabilities section');
});

test('FAQ accordion covers all six listed questions', () => {
  assert.equal((html.match(/class="s-acc-item/g) || []).length, 6, 'six FAQ items');
  for (const question of [
    'What is Keel for Google Workspace?',
    'How does this compare to the Keel for Microsoft 365 app?',
    'How do I install it?',
    'Where can I access Keel?',
    'How is data handled?',
    'Where can I get support?'
  ]) {
    assert.ok(html.includes(`<span class="s-acc-q">${question}</span>`), `FAQ: ${question}`);
  }
  assert.match(html, /class="s-acc-item is-open s-reveal"/, 'first FAQ item expanded');
});

test('dark call to action, footer columns and language selector are present', () => {
  assert.match(html, /<h2>Get started with Keel for Google Workspace<\/h2>/, 'CTA heading');
  assert.match(html, /<section class="s-cta" id="get-started">/, 'dark CTA section');
  ordered(html, [
    '<h2 class="l-footer-h">Products</h2>',
    '<h2 class="l-footer-h">Extensions</h2>',
    '<h2 class="l-footer-h">Developers</h2>',
    '<h2 class="l-footer-h">Company</h2>',
    '<h2 class="l-footer-h">Terms and policies</h2>'
  ], 'footer columns');
  assert.match(html, /id="languageSelect"/, 'language selector');
  assert.match(html, /class="l-socials"/, 'social row');
  assert.match(html, /id="footerSearch"/, 'footer search');
  assert.match(html, /KEEL 2026 All rights reserved\. Keel for Google Workspace is a Beta extension\./,
    'signature');
});

test('try dialog offers honest next steps, not a fake sign-in', () => {
  const dialog = html.slice(html.indexOf('<div class="l-modal gw-modal" id="tryDialog"'),
    html.indexOf('<!-- ==================== admin demo dialog'));
  assert.match(dialog, /href="\/login">Sign in to Keel<\/a>/, 'real login step');
  assert.match(dialog, /href="\/download">Install the desktop app<\/a>/, 'real download step');
  assert.match(dialog, /Ask your Google Workspace admin to enable the Keel add-on/,
    'admin setup step');
  assert.match(dialog, /Marketplace listing is not part of this repository yet/,
    'no invented marketplace link');
  assert.doesNotMatch(dialog, /type="email"/, 'no fake account form');
});

test('every link resolves to a real route, anchor or mail destination', () => {
  const rewrites = new Set(VERCEL.rewrites.map((r) => r.source));
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
  const hrefs = [...html.matchAll(/\b(?:href|src)="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(hrefs.length > 40, 'found links to check');
  for (const raw of hrefs) {
    if (raw.startsWith('mailto:')) continue;
    if (/^https?:\/\//.test(raw)) continue;
    if (raw.startsWith('#')) {
      assert.ok(ids.has(raw.slice(1)), `${raw}: in-page anchor exists`);
      continue;
    }
    assert.ok(raw.startsWith('/'), `${raw}: must be a site-absolute link`);
    const clean = raw.split('#')[0].replace(/\/$/, '') || '/';
    if (rewrites.has(clean) || rewrites.has(`${clean}/`)) continue;
    const file = path.join(SITE, clean.replace(/^\/+/, ''));
    assert.ok(fs.existsSync(file) || fs.existsSync(`${file}.html`) ||
      fs.existsSync(path.join(file, 'index.html')), `${raw}: missing local target`);
  }
});

test('real handlers are wired for every interactive control', () => {
  for (const handler of [
    'function initScrollLinks', 'function initSheetCells', 'function initSheetTabs',
    'function initPanelTabs', 'function initSuggestions', 'function initPreviewReset',
    'function initModals', 'function initTryButtons', 'function initAdminDemo',
    'function initLearnMore', 'function initAccordion', 'function initMegaMenus',
    'function initMobileNav', 'function initFooterSearch', 'function initLanguage',
    'function initReveals', 'function initScrollEffects'
  ]) {
    assert.ok(js.includes(handler), `handler exists: ${handler}`);
  }
  for (const selector of [
    '[data-scroll]', '[data-sheet-tab]', '[data-panel-tab]', '[data-accept]',
    '[data-edit]', '[data-save]', '[data-cancel]', '[data-reset-sheet]',
    '[data-try]', '[data-admin-demo]', '[data-admin-step]', '[data-learn]',
    '.s-acc-btn', '.l-nav-trigger[aria-controls]', "byId('navToggle')",
    "byId('footerSearch')", "byId('languageSelect')"
  ]) {
    assert.ok(js.includes(selector), `JS binds ${selector}`);
  }
  assert.match(js, /setAttribute\('aria-expanded'/, 'disclosure ARIA state is updated');
  assert.match(js, /setAttribute\('aria-selected'/, 'tab ARIA state is updated');
  assert.match(js, /setAttribute\('aria-pressed'/, 'demo checklist ARIA state is updated');
  assert.match(js, /textContent = targetValue/, 'accepted changes update the mock');
  assert.match(js, /openModal\('tryDialog'\)/, 'try buttons open the honest dialog');
  assert.match(js, /openModal\('adminDialog'\)/, 'admin demo opens its dialog');
});

test('motion is subtle, rAF throttled and reduced-motion aware', () => {
  assert.match(js, /IntersectionObserver/, 'IntersectionObserver reveals');
  assert.match(js, /requestAnimationFrame/, 'rAF throttled scroll work');
  assert.match(js, /addEventListener\('scroll', onScroll, \{ passive: true \}\)/,
    'passive scroll listener');
  assert.doesNotMatch(js, /setInterval/, 'no busy loops');
  assert.match(js, /prefers-reduced-motion/, 'JS reduced-motion kill switch');
  assert.match(js, /window\.matchMedia/, 'reads motion preference');
  assert.match(css, /\.s-reveal/, 'reveal styles');
  assert.match(css, /transition: opacity \.2s ease, transform \.2s ease/, '200ms reveal <= 220ms');
  assert.match(css, /translateY\(12px\)/, '12px reveal <= 14px');
  assert.doesNotMatch(css, /transition:[^;]*max-height/, 'accordion does not animate layout');
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/, 'CSS reduced-motion kill switch');
  assert.match(css, /\.l-header\.is-scrolled/, 'sticky nav shadow');
  assert.match(css, /--gw-shift/, 'hero mock parallax uses a transform variable');
});

test('route rewrites, sitemap and QA server resolve both clean URLs', () => {
  const rewrites = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));
  for (const route of ['/keel-for-google-workspace', '/keel-for-google-workspace/']) {
    assert.equal(rewrites.get(route), '/keel-for-google-workspace.html',
      `rewrite for ${route}`);
    assert.ok(SERVER.includes(`'${route}': '/keel-for-google-workspace.html'`),
      `QA server rewrite for ${route}`);
  }
  assert.ok(fs.existsSync(HTML_PATH), 'rewrite target exists');
  assert.ok(SITEMAP.includes('https://keel-desktop.vercel.app/keel-for-google-workspace'),
    'sitemap includes the new route');
  /* Every pre-existing route and header is preserved. */
  assert.equal(rewrites.get('/artifacts'), '/artifacts.html', 'existing rewrite kept');
  assert.equal(rewrites.get('/features/artifacts'), '/features/artifacts.html', 'existing rewrite kept');
  assert.equal(rewrites.get('/product/design'), '/product/design.html', 'existing rewrite kept');
  assert.equal(rewrites.get('/pricing'), '/pricing.html', 'existing rewrite kept');
  assert.ok(VERCEL.rewrites.length >= 63, 'all pre-existing rewrites kept');
  assert.ok(VERCEL.headers.some((h) => h.headers.some((e) =>
    e.key === 'Content-Security-Policy')), 'security headers kept');
  assert.ok(VERCEL.headers.length >= 7, 'all pre-existing header rules kept');
});

async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

let serverProcess;
let base;
let serverOutput = '';

before(async () => {
  const port = await freePort();
  serverProcess = spawn(process.execPath, [path.join(REPO, 'serve_keel_site.mjs')], {
    cwd: REPO,
    env: { ...process.env, PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  serverProcess.stdout.on('data', (chunk) => { serverOutput += String(chunk); });
  serverProcess.stderr.on('data', (chunk) => { serverOutput += String(chunk); });
  const deadline = Date.now() + 10000;
  while (!serverOutput.includes('Keel QA server') && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 25));
    if (serverProcess.exitCode !== null) break;
  }
  assert.match(serverOutput, /Keel QA server/, 'QA server did not start');
  base = `http://127.0.0.1:${port}`;
});

after(async () => {
  if (serverProcess && serverProcess.exitCode === null) {
    serverProcess.kill();
    await new Promise((resolve) => serverProcess.once('exit', resolve));
  }
});

test('QA server serves the page at both clean URLs', async () => {
  for (const route of ['/keel-for-google-workspace', '/keel-for-google-workspace/']) {
    const response = await fetch(`${base}${route}`);
    const body = await response.text();
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.match(body, /Expertise in every app/, `${route}: page content`);
    assert.equal(body, html, `${route}: same design as the .html entry point`);
  }
});

test('QA server serves the shared assets used by the page', async () => {
  for (const asset of [
    '/ui/gworkspace.css', '/ui/gworkspace.js', '/ui/keel-duet-shell.css',
    '/ui/icons/icon-192.png'
  ]) {
    const response = await fetch(`${base}${asset}`);
    assert.equal(response.status, 200, `${asset}: expected 200, got ${response.status}`);
  }
});
