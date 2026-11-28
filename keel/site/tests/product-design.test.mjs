/* Static + local-route verification for the Keel Design product page.
 * Run: node --test keel/site/tests/product-design.test.mjs
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
const HTML_PATH = path.join(SITE, 'product', 'design.html');
const INDEX_PATH = path.join(SITE, 'product', 'design', 'index.html');
const CSS_PATH = path.join(SITE, 'ui', 'product-design.css');
const JS_PATH = path.join(SITE, 'ui', 'product-design.js');
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

test('both Keel Design entry points exist and stay byte-identical', () => {
  assert.ok(fs.existsSync(HTML_PATH), 'missing product/design.html');
  assert.ok(fs.existsSync(INDEX_PATH), 'missing product/design/index.html');
  assert.equal(html, index, 'the two entry points must serve the same design');
  assert.match(html, /^<!doctype html>/i, 'HTML document type');
  assert.match(html, /<body class="duet-page design-page">/, 'design page body class');
  assert.match(html, /href="\/ui\/keel-duet-shell\.css"/, 'shared shell stylesheet');
  assert.match(html, /href="\/ui\/product-design\.css"/, 'design stylesheet');
  assert.match(html, /<script src="\/ui\/product-design\.js" defer><\/script>/, 'deferred JS');
  assert.match(html, /<link rel="canonical" href="https:\/\/keel-desktop\.vercel\.app\/product\/design" \/>/,
    'canonical URL');
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
});

test('reference sections appear in order', () => {
  ordered(html, [
    '<header class="l-header s-header">',
    '<nav class="s-crumbs l-container"',
    '<section class="d-hero" id="design-home">',
    '<section class="d-frontier" id="frontier">',
    '<section class="d-compare" id="brand-control">',
    '<section class="d-compare d-compare-alt" id="output">',
    '<section class="d-stories" id="stories">',
    '<section class="d-faq" id="faq">',
    '<footer class="l-footer" id="footer">'
  ], 'page structure');
  assert.match(html,
    /<a href="\/">Product<\/a> <span aria-hidden="true">\/<\/span> Keel Design<\/nav>/,
    'breadcrumb reads Product / Keel Design');
});

test('sticky nav has a four-column Product mega menu with Capabilities → Design', () => {
  const productMega = html.slice(
    html.indexOf('<div class="l-mega" id="mega-product"'),
    html.indexOf('<div class="l-nav-item" data-menu="developers">')
  );
  assert.equal((productMega.match(/class="l-mega-col"/g) || []).length, 4,
    'Product mega menu has four columns');
  assert.match(productMega, /<p class="l-mega-title">Capabilities<\/p>/, 'Capabilities column');
  assert.match(productMega, /href="\/product\/design">Design<\/a>/, 'Capabilities → Design link');
  assert.match(productMega, /href="\/product\/design">Keel Design<\/a>/, 'Products → Keel Design link');
  assert.match(html, /href="\/login">Log in<\/a>/, 'Log in link');
  assert.match(html, /href="mailto:hello@keel\.ai">Contact sales<\/a>/, 'Contact sales link');
  assert.match(html, /class="l-btn l-btn-dark l-btn-sm" href="\/login">Get Keel</, 'Get Keel link');
  assert.match(html, /href="\/product\/design">Keel Design<\/a>\s*<a href="\/requirements">Developers<\/a>/,
    'mobile menu includes Keel Design');
});

test('hero reproduces the reference copy, layered mock cards and CTAs', () => {
  assert.match(html, /<h1 class="d-hero-title">Design your ideas with Keel<\/h1>/, 'serif hero heading');
  assert.match(html,
    /Generate, iterate on, and ship design work with AI—all inside the tools you already know\./,
    'hero subtitle');
  assert.match(html, /class="l-btn l-btn-dark" href="\/login">Get started</, 'primary CTA');
  assert.match(html, /class="d-stage-card d-graph-card d-parallax" data-depth="0\.6"/, 'graph card');
  assert.match(html, /class="d-graph-art"/, 'network / graph visualization');
  assert.match(html, /<strong>Let's chat<\/strong>/, 'chat panel title');
  assert.match(html, /What would you like to make\?/, 'chat prompt');
  assert.match(html, /data-hero-chat aria-expanded="false" aria-controls="d-chat-reply"/, 'chat action');
  assert.match(html, /<span>Keel design system<\/span>/, 'design system card');
  assert.match(html, /Now you can use Keel Design from inside any compatible design tool/, 'tool note');
  assert.match(html, /href="\/download">Learn more<\/a>/, 'Learn more link');
});

test('frontier intelligence tabs, Skillbook mock and caption match the reference', () => {
  assert.match(html, /<h2 class="d-section-title">Frontier intelligence for every type of design work<\/h2>/,
    'frontier heading');
  assert.equal((html.match(/data-design-tab=/g) || []).length, 3, 'three work tabs');
  ordered(html, [
    'data-design-tab="product">Product</button>',
    'data-design-tab="marketing">Marketing</button>',
    'data-design-tab="brand">Brand</button>'
  ], 'tab order');
  assert.match(html, /class="d-peach-frame"/, 'peach-framed mock');
  assert.equal((html.match(/<div class="d-skillbook">/g) || []).length, 3, 'Skillbook panels');
  assert.match(html, /<span>Skillbook<\/span>/, 'Skillbook label');
  assert.match(html, /Run your next competition to grow your business/, 'caption');
  assert.match(html, /Explore more directions in less time/, 'caption description');
});

test('both Keel Code comparison sections keep their prompts and numbered details', () => {
  assert.match(html, /<h2 class="d-section-title">Keep designs on-brand with Keel Code<\/h2>/, 'brand heading');
  assert.match(html, /<h2 class="d-section-title">From the prototype to the final output<\/h2>/, 'output heading');
  assert.equal((html.match(/data-code-prompt=/g) || []).length, 2, 'two code prompts');
  assert.match(html, /data-code-prompt="brand" aria-expanded="false" aria-controls="d-code-brand"/, 'brand prompt');
  assert.match(html, /Bring a product to life<\/button>/, 'brand prompt copy');
  assert.match(html, /From prompt to high-fidelity output<\/button>/, 'output prompt copy');
  assert.equal((html.match(/class="d-steps"/g) || []).length, 2, 'two numbered detail lists');
  assert.equal((html.match(/<li><strong>/g) || []).length, 6, 'three bullets per list');
  assert.match(html, />Explore Keel Code <span aria-hidden="true">→<\/span><\/a>/, 'Keel Code link');
  assert.match(html, /class="d-compare d-compare-alt" id="output"/, 'generous second comparison section');
});

test('four testimonial cards and 14 FAQs are present in order', () => {
  for (const brand of ['Adobe', 'Canva', 'Figma', 'Wix']) {
    assert.ok(html.includes(`<p class="d-story-brand">${brand}</p>`), `story: ${brand}`);
  }
  assert.equal((html.match(/data-story=/g) || []).length, 4, 'four story cards');
  assert.equal((html.match(/Read the full story/g) || []).length, 4, 'four full-story links');
  assert.match(html, /class="d-acc-item is-open"/, 'first FAQ expanded by default');
  ordered(html, [
    'How can I start using Keel Design?',
    'How should I write prompts so Keel Design gets the best result?',
    'Which design tools does Keel Design work in?',
    'Can Keel Design use my existing design system?',
    'What kinds of design work is Keel Design best at?',
    'Can I edit and iterate on the designs Keel Design makes?',
    'Does Keel Design generate code?',
    'Is Keel Design available to everyone?',
    'How does Keel Design handle my files and data?',
    'Can teams share designs made with Keel Design?',
    'Does Keel Design work on mobile?',
    'Can I use Keel Design in the Keel desktop app?',
    'Are artifacts available to my Enterprise organization?',
    'What is next for Keel Design?'
  ], 'FAQ order');
  assert.equal((html.match(/class="d-acc-item/g) || []).length, 14, 'fourteen FAQ items');
});

test('dark footer keeps five columns, language selector and real search', () => {
  ordered(html, [
    '<h2 class="l-footer-h">Products</h2>',
    '<h2 class="l-footer-h">Developers</h2>',
    '<h2 class="l-footer-h">Enterprise</h2>',
    '<h2 class="l-footer-h">Company</h2>',
    '<h2 class="l-footer-h">Terms and policies</h2>'
  ], 'footer columns');
  assert.match(html, /id="languageSelect"/, 'language selector');
  assert.match(html, /class="l-socials"/, 'social row');
  assert.match(html, /id="d-footer-search"/, 'footer FAQ search');
  assert.match(html, /KEEL 2026 All rights reserved\. Keel Design is a product of Keel\./, 'signature');
});

test('every link resolves to a real route, anchor or mail destination', () => {
  const rewrites = new Set(VERCEL.rewrites.map((r) => r.source));
  const hrefs = [...html.matchAll(/\b(?:href|src)="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(hrefs.length > 30, 'found links to check');
  for (const raw of hrefs) {
    if (raw.startsWith('#') || raw.startsWith('mailto:') || /^https?:\/\//.test(raw)) continue;
    assert.ok(raw.startsWith('/'), `${raw}: must be a site-absolute link`);
    const route = raw.split('#')[0].split('?')[0].replace(/\/$/, '') || '/';
    if (rewrites.has(route) || rewrites.has(`${route}/`)) continue;
    const file = path.join(SITE, route.replace(/^\/+/, ''));
    assert.ok(fs.existsSync(file) || fs.existsSync(`${file}.html`) ||
      fs.existsSync(path.join(file, 'index.html')), `${raw}: missing local target`);
  }
});

test('real handlers are wired for every interactive control', () => {
  for (const handler of [
    'function initDesignTabs', 'function initNavDemos', 'function initHeroChat',
    'function initCodePrompts', 'function initStories', 'function initAccordion',
    'function initMegaMenus', 'function initMobileNav', 'function initFooterSearch',
    'function initLanguage', 'function initReveals', 'function initScrollEffects'
  ]) {
    assert.ok(js.includes(handler), `handler exists: ${handler}`);
  }
  for (const selector of [
    '[data-design-tab]', '[data-model]', '[data-hero-chat]', '[data-chat-chip]',
    '[data-code-prompt]', '[data-story]', '.l-nav-trigger[aria-controls]',
    "byId('navToggle')", "byId('languageSelect')"
  ]) {
    assert.ok(js.includes(selector), `JS binds ${selector}`);
  }
  assert.match(js, /\.d-acc-btn'/, 'accordion buttons are bound');
  assert.match(js, /setAttribute\('aria-expanded'/, 'ARIA state is updated');
  assert.match(js, /scrollToElement\(byId\('frontier'\)\)/, 'nav shortcuts reach the frontier section');
  assert.match(js, /byId\('d-chat-reply'\)/, 'hero chat reply is bound');
});

test('motion is subtle, rAF throttled and reduced-motion aware', () => {
  assert.match(js, /IntersectionObserver/, 'IntersectionObserver reveals');
  assert.match(js, /requestAnimationFrame/, 'rAF throttled scroll work');
  assert.match(js, /addEventListener\('scroll', onScroll, \{ passive: true \}\)/, 'passive scroll listener');
  assert.doesNotMatch(js, /setInterval/, 'no busy loops');
  assert.match(js, /prefers-reduced-motion/, 'JS reduced-motion kill switch');
  assert.match(js, /window\.matchMedia/, 'reads motion preference');
  assert.match(css, /\.s-reveal/, 'reveal styles');
  assert.match(css, /transition: opacity \.2s ease, transform \.2s ease/, '200ms reveal <= 220ms');
  assert.match(css, /translateY\(12px\)/, '12px reveal <= 14px');
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/, 'CSS reduced-motion kill switch');
  assert.match(css, /\.l-header\.is-scrolled/, 'sticky nav shadow');
  assert.match(css, /--d-shift/, 'hero card parallax');
});

test('route rewrites, sitemap and QA server resolve both clean URLs', () => {
  const rewrites = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));
  for (const route of ['/product/design', '/product/design/']) {
    assert.equal(rewrites.get(route), '/product/design.html', `rewrite for ${route}`);
    assert.ok(SERVER.includes(`'${route}': '/product/design.html'`),
      `QA server rewrite for ${route}`);
  }
  assert.ok(fs.existsSync(path.join(SITE, 'product', 'design.html')), 'rewrite target exists');
  assert.ok(SITEMAP.includes('https://keel-desktop.vercel.app/product/design'),
    'sitemap includes the new route');
  /* Every pre-existing route and header is preserved. */
  assert.equal(rewrites.get('/product/keel-duet'), '/product/keel-duet.html', 'existing rewrite kept');
  assert.equal(rewrites.get('/features/artifacts'), '/features/artifacts.html', 'existing rewrite kept');
  assert.ok(VERCEL.headers.some((h) => h.headers.some((e) =>
    e.key === 'Content-Security-Policy')), 'security headers kept');
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

test('QA server serves the new page at both clean URLs', async () => {
  for (const route of ['/product/design', '/product/design/']) {
    const response = await fetch(`${base}${route}`);
    const body = await response.text();
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.match(body, /Design your ideas with Keel/, `${route}: page content`);
    assert.equal(body, html, `${route}: same design as the .html entry point`);
  }
});

test('QA server serves the shared assets used by the page', async () => {
  for (const asset of ['/ui/product-design.css', '/ui/product-design.js', '/ui/keel-duet-shell.css']) {
    const response = await fetch(`${base}${asset}`);
    assert.equal(response.status, 200, `${asset}: expected 200, got ${response.status}`);
  }
});
