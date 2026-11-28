/* Static + local-route verification for the Keel Science product page.
 * Run: node --test keel/site/tests/product-keel-science.test.mjs
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
const HTML_PATH = path.join(SITE, 'product', 'keel-science.html');
const INDEX_PATH = path.join(SITE, 'product', 'keel-science', 'index.html');
const CSS_PATH = path.join(SITE, 'ui', 'keel-science.css');
const JS_PATH = path.join(SITE, 'ui', 'keel-science.js');
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

test('both Keel Science entry points exist and stay identical', () => {
  assert.ok(fs.existsSync(HTML_PATH), 'missing product/keel-science.html');
  assert.ok(fs.existsSync(INDEX_PATH), 'missing product/keel-science/index.html');
  assert.equal(html, index, 'the two entry points must serve the same design');
  assert.match(html, /^<!doctype html>/i, 'HTML document type');
  assert.match(html, /<body class="duet-page science-page">/, 'science page body class');
  assert.match(html, /href="\/ui\/keel-duet-shell\.css"/, 'shared shell stylesheet');
  assert.match(html, /href="\/ui\/keel-science\.css"/, 'science stylesheet');
  assert.match(html, /<script src="\/ui\/keel-science\.js" defer><\/script>/, 'deferred JS');
});

test('no stale Claude branding, no /app links, no inline handlers', () => {
  for (const [name, source] of Object.entries(owned)) {
    assert.doesNotMatch(source, /claude/i, `${name}: stale Claude branding`);
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
    '<section class="s-hero" id="research-home">',
    '<section class="s-built" id="research">',
    '<section class="s-drafts" id="drafts">',
    '<section class="s-existing" id="existing">',
    '<section class="s-workflow" id="workflow">',
    '<section class="s-stories" id="stories">',
    '<section class="s-integrations" id="integrations">',
    '<section class="s-faq" id="faq">',
    '<section class="s-cta s-reveal">',
    '<footer class="l-footer" id="footer">'
  ], 'page structure');
  assert.match(html,
    /<a href="\/">Product<\/a> <span aria-hidden="true">\/<\/span> Keel Science<\/nav>/,
    'breadcrumb reads Product / Keel Science');
});

test('sticky nav has a four-column Product mega menu and real top links', () => {
  const productMega = html.slice(
    html.indexOf('<div class="l-mega" id="mega-product"'),
    html.indexOf('<div class="l-nav-item" data-menu="developers">')
  );
  assert.equal((productMega.match(/class="l-mega-col"/g) || []).length, 4,
    'Product mega menu has four columns');
  assert.match(productMega, /href="\/product\/keel-science">Keel Science</,
    'specialized nav link points to the new product page');
  assert.match(html, /href="\/login">Log in<\/a>/, 'Log in link');
  assert.match(html, /href="mailto:hello@keel\.ai">Contact sales<\/a>/, 'Contact sales link');
  assert.match(html, /class="l-btn l-btn-dark l-btn-sm" href="\/login">Get Keel</, 'Get Keel link');
  assert.doesNotMatch(html, /data-auth="(?:login|sales|email)"/, 'no auth buttons in this page');
});

test('hero reproduces the reference copy, buttons and video card', () => {
  assert.match(html, /<h1 class="s-hero-title">Your research partner for rigorous science<\/h1>/,
    'serif hero heading');
  assert.match(html,
    /The Keel Science app walks with you through every step of the research process, from idea to publication, and is available to everyone\./,
    'hero subtitle');
  assert.match(html, /class="l-btn l-btn-dark" href="\/login">Get started</, 'primary CTA');
  assert.match(html, /data-announcement>Read the announcement</, 'announcement CTA');
  assert.match(html, /class="s-chat-card" id="science-chat"/, 'floating assistant card');
  assert.match(html, /<strong>Keel Science<\/strong>/, 'floating card title');
  assert.match(html, /data-chat-prompt>Help me design an experiment</, 'example prompt');
  assert.match(html, /data-show-reply aria-expanded="false" aria-controls="science-reply">Show reply</,
    'show reply control');
  assert.match(html, /class="s-play" type="button" data-video-play/, 'video play button');
  assert.match(html, /class="s-montage s-reveal"/, 'figure montage');
  assert.ok((html.match(/data-figure=/g) || []).length >= 5, 'research figure cards');
});

test('research workflow copy and both mock sections are present', () => {
  assert.match(html, /<h2 class="s-section-title">Built for scientific research<\/h2>/, 'built heading');
  assert.match(html, /Built to accelerate authentic daily research workflows\./, 'built subtitle');
  ordered(html, [
    'Deeply engage with literature',
    'Follow links to cited papers',
    'Navigate to code in referenced repositories',
    'Extract figures from the paper'
  ], 'research capabilities');
  assert.ok((html.match(/data-paper-tab=/g) || []).length === 3, 'paper mock tabs');
  assert.match(html, /<h2 class="s-section-title">Drafts ready in one day<\/h2>/, 'drafts heading');
  assert.match(html, /data-draft aria-expanded="false" aria-controls="draft-output">Generate a literature review on my topic</,
    'example prompt');
  assert.match(html, /For exploratory research/, 'exploratory note');
  assert.match(html, /For literature reviews and systematic reviews/, 'review note');
  assert.match(html, /For existing work with experiments and figures/, 'existing work heading');
  assert.match(html, /<h2 class="s-section-title">How researchers use Keel Science<\/h2>/, 'workflow heading');
  assert.match(html, /go from a simple question to well-supported insights/, 'workflow subtitle');
  ordered(html, ['Literature search', 'Data analysis', 'Experiment design'], 'workflow tabs');
  assert.match(html, /Simple with Keel visualization/, 'plot caption');
});

test('researcher stories, integrations and seven FAQs match the reference', () => {
  for (const handle of ['@anna', '@dimitris', '@ug']) {
    assert.ok(html.includes(handle), `researcher handle: ${handle}`);
  }
  assert.equal((html.match(/data-story=/g) || []).length, 3, 'three story cards');
  assert.match(html, /Read story <span aria-hidden="true">→<\/span>/, 'Read story links');
  for (const logo of ['arXiv', 'GitHub', 'Zotero', 'Google Scholar', 'Python', 'Jupyter']) {
    assert.ok(html.includes(`data-integration="${logo}"`), `integration: ${logo}`);
  }
  assert.match(html, /href="\/plugins">Explore integrations</, 'integrations link');
  ordered(html, [
    'What is Keel Science?',
    'Who is Keel Science for?',
    'What kinds of tasks is Keel Science best at?',
    'Can I use Keel Science with my own files and data?',
    'Does Keel Science create figures?',
    'How is Keel Science different from a general chatbot?',
    'Is Keel Science available on mobile and desktop?'
  ], 'FAQ order');
  assert.equal((html.match(/class="s-acc-item/g) || []).length, 7, 'seven accordion items');
});

test('dark CTA and five-column footer are present', () => {
  assert.match(html, /<h2 class="s-cta-title">Accelerate your research<\/h2>/, 'CTA heading');
  assert.match(html, /Start research with Keel Science/, 'CTA subtitle');
  assert.match(html, /class="l-btn s-cta-btn" href="\/login">Get started</, 'CTA button');
  ordered(html, [
    '<h2 class="l-footer-h">Products</h2>',
    '<h2 class="l-footer-h">Developers</h2>',
    '<h2 class="l-footer-h">Enterprise</h2>',
    '<h2 class="l-footer-h">Company</h2>',
    '<h2 class="l-footer-h">Terms and policies</h2>'
  ], 'footer columns');
  assert.match(html, /id="languageSelect"/, 'language selector');
  assert.match(html, /class="l-socials"/, 'social row');
});

test('real handlers are wired for every interactive control', () => {
  for (const handler of [
    'function initAnnouncement', 'function initChat', 'function openVideoModal',
    'function initPaperTabs', 'function initWorkflowTabs', 'function initDraft',
    'function initFigures', 'function initStories', 'function initIntegrations',
    'function initModelInfo', 'function initAccordion', 'function initMegaMenus',
    'function initMobileNav', 'function initFooterSearch', 'function initLanguage'
  ]) {
    assert.ok(js.includes(handler), `handler exists: ${handler}`);
  }
  for (const selector of [
    '[data-announcement]', '[data-chat-prompt]', '[data-show-reply]',
    '[data-video-play]', '[data-paper-tab]', '[data-workflow]', '[data-draft]',
    '[data-figure]', '[data-story]', '[data-integration]', '[data-model]',
    '.l-nav-trigger[aria-controls]', "byId('navToggle')", "byId('languageSelect')"
  ]) {
    assert.ok(js.includes(selector), `JS binds ${selector}`);
  }
  assert.match(js, /\.s-acc-btn'/, 'accordion buttons are bound');
  assert.match(js, /setAttribute\('aria-expanded'/, 'ARIA state is updated');
  assert.match(js, /\/login/, 'real login destination');
  assert.match(js, /'\/plugins'/, 'real integrations destination');
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
  assert.match(css, /--science-card-shift/, 'hero card parallax');
});

test('route rewrites, sitemap and QA server resolve both clean URLs', () => {
  const rewrites = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));
  for (const route of ['/product/keel-science', '/product/keel-science/']) {
    assert.equal(rewrites.get(route), '/product/keel-science.html', `rewrite for ${route}`);
    assert.ok(SERVER.includes(`'${route}': '/product/keel-science.html'`),
      `QA server rewrite for ${route}`);
  }
  assert.ok(fs.existsSync(path.join(SITE, 'product', 'keel-science.html')), 'rewrite target exists');
  assert.ok(SITEMAP.includes('https://keel-desktop.vercel.app/product/keel-science'),
    'sitemap includes the new route');
  /* Every pre-existing route and header is preserved. */
  assert.equal(rewrites.get('/product/keel-duet'), '/product/keel-duet.html', 'existing rewrite kept');
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
  for (const route of ['/product/keel-science', '/product/keel-science/']) {
    const response = await fetch(`${base}${route}`);
    const body = await response.text();
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.match(body, /Your research partner for rigorous science/, `${route}: page content`);
    assert.equal(body, html, `${route}: same design as the .html entry point`);
  }
});
