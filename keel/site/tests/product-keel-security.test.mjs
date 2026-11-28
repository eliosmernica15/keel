/* Static + local-route verification for the Keel Security product page.
 * Run: node --test keel/site/tests/product-keel-security.test.mjs
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
const HTML_PATH = path.join(SITE, 'product', 'keel-security.html');
const INDEX_PATH = path.join(SITE, 'product', 'keel-security', 'index.html');
const CSS_PATH = path.join(SITE, 'ui', 'keel-security.css');
const JS_PATH = path.join(SITE, 'ui', 'keel-security.js');
const VERCEL = JSON.parse(fs.readFileSync(path.join(SITE, 'vercel.json'), 'utf8'));
const SERVER = path.join(REPO, 'serve_keel_site.mjs');

const html = fs.readFileSync(HTML_PATH, 'utf8');
const index = fs.readFileSync(INDEX_PATH, 'utf8');
const css = fs.readFileSync(CSS_PATH, 'utf8');
const js = fs.readFileSync(JS_PATH, 'utf8');
const owned = { html, index, css, js };
const rewriteBySource = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));

function ordered(source, needles, label) {
  let cursor = -1;
  for (const needle of needles) {
    const found = source.indexOf(needle, cursor + 1);
    assert.notEqual(found, -1, `${label}: missing ${JSON.stringify(needle)}`);
    cursor = found;
  }
}

test('both Keel Security entry points exist and stay byte-identical', () => {
  assert.ok(fs.existsSync(HTML_PATH), 'missing product/keel-security.html');
  assert.ok(fs.existsSync(INDEX_PATH), 'missing product/keel-security/index.html');
  assert.equal(html, index, 'the two entry points must serve the same design');
  assert.match(html, /^<!doctype html>/i, 'HTML document type');
  assert.match(html, /<body class="security-page">/, 'security page body class');
  assert.match(html, /href="\/ui\/keel-security\.css"/, 'page stylesheet');
  assert.match(html, /<script src="\/ui\/keel-security\.js" defer><\/script>/, 'deferred JS');
  assert.match(html, /href="https:\/\/keel-desktop\.vercel\.app\/product\/keel-security"/, 'canonical URL');
});

test('no Claude or Anthropic branding, no /app links, no dead inline code', () => {
  for (const [name, source] of Object.entries(owned)) {
    assert.doesNotMatch(source, /claude/i, `${name}: stale Claude branding`);
    assert.doesNotMatch(source, /anthropic/i, `${name}: stale Anthropic branding`);
  }
  assert.doesNotMatch(html, /\/app(?=["'/]|$)/, 'no /app links; use /login');
  assert.doesNotMatch(html, /href="#"/, 'no href="#" placeholders');
  const inlineHandler = /\s(?:onclick|onload|onerror|onchange|onsubmit|onmouseover|onfocus|onblur|onkeydown)\s*=/i;
  assert.doesNotMatch(html, inlineHandler, 'no inline event handlers');
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)|<style[\s>]/i, 'no inline script or style blocks');
  assert.doesNotMatch(html, /data:image/i, 'no inline data URIs in markup');
  assert.doesNotMatch(css, /data:image/i, 'no inline data URIs in CSS');
});

test('reference sections appear in the supplied order', () => {
  ordered(html, [
    '<header class="ks-header" id="siteHeader">',
    '<nav class="ks-crumbs ks-container" aria-label="Breadcrumb">',
    '<section class="ks-hero" id="hero">',
    '<section class="ks-flow" id="data-flow"',
    '<section class="ks-usage" id="how-teams-use">',
    '<section class="ks-proof" id="built-for">',
    '<section class="ks-resources" id="security-resources">',
    '<section class="ks-faq" id="faq">',
    '<footer class="ks-footer" id="footer">'
  ], 'page structure');
  assert.match(html, />Product<\/a> <span aria-hidden="true">\/<\/span> Security research<\/nav>/,
    'breadcrumb reads Product / Security research');
});

test('sticky nav has a four-column Product mega menu and real top links', () => {
  const productMega = html.slice(
    html.indexOf('<div class="ks-mega" id="mega-product"'),
    html.indexOf('<div class="ks-nav-item" data-menu="developers">')
  );
  assert.equal((productMega.match(/class="ks-mega-col"/g) || []).length, 4,
    'Product mega menu has four columns');
  const topLinks = html.slice(html.indexOf('<a class="ks-nav-link" href="/login">'),
    html.indexOf('</nav>', html.indexOf('<a class="ks-nav-link" href="/login">')));
  assert.match(topLinks, /href="\/login"[^>]*>Log in</, 'Log in link');
  assert.match(topLinks, /href="mailto:hello@keel\.ai"[^>]*>Contact sales</, 'Contact sales link');
  assert.match(html, /class="ks-btn ks-btn-dark ks-btn-sm" href="\/login">Get Keel</, 'Get Keel link');
  assert.match(html, /href="\/product\/keel-security" aria-current="page">Keel Security</,
    'specialized nav link now points to the new route');
  assert.match(css, /\.ks-header\s*\{[^}]*position: sticky/, 'sticky header');
});

test('hero reproduces the reference copy, floating card and padlock', () => {
  assert.match(html, /<h1 class="ks-title">From scan to fix, done seamlessly<\/h1>/, 'serif hero heading');
  assert.match(html, /Keel scans your codebase with Keel Mythos, vulnerabilities finding, and auto-fixes with your approval\. Available in public beta for Keel Enterprise\./, 'hero subtitle');
  assert.match(html, /class="ks-btn ks-btn-dark" href="mailto:hello@keel\.ai">Contact sales</, 'Contact sales button');
  assert.match(html, /data-announcement>Read the Announcement<\/button>/, 'announcement button');
  assert.match(html, /<aside class="ks-chat-card" id="floatCard"/, 'floating security card');
  assert.ok(html.includes('Keel security'), 'card title');
  assert.ok(html.includes('Help me fix this security vulnerability'), 'card prompt');
  assert.ok(html.includes('Show issue'), 'card action');
  assert.match(html, /<div class="ks-lock" aria-hidden="true">\s*<svg/, 'inline orange padlock art');
  assert.match(js, /data-show-issue/, 'Show issue handler is bound');
  assert.match(js, /is-flash/, 'Show issue highlights the data-flow band');
});

test('yellow-beige data-flow band carries the exact example line', () => {
  assert.match(html, /<section class="ks-flow" id="data-flow"/, 'band section');
  assert.match(html, /<code class="ks-flow-code" id="flowCode">Data flows: 1\. Attacker POSTs \/api\/recover\/login \{login: unknownUser\(\)\}<\/code>/,
    'exact data-flow snippet');
  assert.match(html, /data-copy-flow/, 'copy control');
  assert.match(js, /data-copy-flow/, 'copy handler is bound');
  assert.match(css, /--ks-band:\s*#f2e7c3/, 'yellow-beige band colour');
});

test('usage and proof sections match the requested copy without false claims', () => {
  assert.match(html, /<h2 class="ks-section-title ks-reveal">How teams use Keel Security<\/h2>/, 'usage heading');
  assert.match(html, /Keel reasons through your code like a skilled security researcher\. It validates real risks in context, filters out false positives, and then suggests and tracks fixes\./, 'usage copy');
  assert.match(html, /Built for security teams, used by Keel users/, 'proof heading');
  assert.match(html, /Y Combinator award/, 'reference badge text');
  assert.match(html, /Beta launch about Keel Security video/, 'video card');
  assert.match(html, /Powered by Keel Mythos/, 'model heading');
  assert.match(html, /Scan your codebase with our latest cyber capability model\./, 'model copy');
  assert.match(js, /data-award/, 'award badge handler');
  assert.match(js, /data-video="beta-launch"/, 'video card handler');
  assert.match(js, /not a claim about Keel/, 'badge is not presented as a factual Keel award');
});

test('four security resources have Blog tags, real hrefs and click handlers', () => {
  const titles = [
    'Keel Security Playground for security teams',
    'Keel Security how to use guide',
    'Evaluating and mitigating AI-generated open source risks',
    'Experimenting with AI for security information'
  ];
  ordered(html, titles, 'resource card order');
  const cards = html.match(/<a class="ks-resource-card ks-reveal"[^>]*>/g) || [];
  assert.equal(cards.length, 4, 'four resource cards');
  assert.equal((html.match(/<span class="ks-tag">Blog<\/span>/g) || []).length, 4, 'four Blog tags');
  const hrefs = [...html.matchAll(/class="ks-resource-card ks-reveal" href="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(hrefs.length, 4, 'four resource links');
  for (const href of hrefs) {
    assert.ok(rewriteBySource.has(href), `resource link has a real route: ${href}`);
  }
  assert.match(html, /href="\/resources\/articles">Read the blog</, 'Read the blog button');
  assert.match(html, /href="mailto:hello@keel\.ai">Contact sales</, 'resource Contact sales button');
  assert.match(js, /data-resource/, 'resource cards are wired');
  assert.match(js, /keel_security_resources/, 'resource selection is remembered locally');
});

test('every in-page anchor and internal link resolves to real content', () => {
  const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]));
  const hrefs = [...html.matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
  const anchors = hrefs.filter((href) => href.startsWith('#'));
  assert.ok(anchors.length > 0, 'in-page anchors are used');
  for (const href of anchors) {
    assert.ok(ids.has(href.slice(1)), `anchor target exists: ${href}`);
  }
  const internal = [...new Set(hrefs.filter((href) => href.startsWith('/')))];
  for (const href of internal) {
    const clean = href.split('#')[0];
    const file = path.join(SITE, clean.replace(/^\//, ''));
    const candidates = clean.endsWith('/')
      ? [path.join(file, 'index.html')]
      : [file, `${file}.html`, path.join(file, 'index.html')];
    const physical = candidates.some((candidate) =>
      fs.existsSync(candidate) && fs.statSync(candidate).isFile());
    const served = rewriteBySource.has(clean) || rewriteBySource.has(`${clean}/`) || physical;
    assert.ok(served, `internal link is served: ${href}`);
  }
});

test('six FAQ questions are present in order with an accordion handler', () => {
  ordered(html, [
    'What is this available to?',
    'What is the access level this gives me?',
    'What is the security risk I should know about?',
    'What types of vulnerabilities does Keel Security find?',
    'How is this different from traditional security tools?',
    'Does Keel Security work with my existing security tools?'
  ], 'FAQ order');
  assert.equal((html.match(/class="ks-acc-item/g) || []).length, 6, 'six accordion items');
  assert.match(js, /function initAccordion/, 'accordion handler exists');
  assert.match(js, /\.ks-acc-btn'/, 'accordion buttons are bound');
  assert.match(js, /\.ks-nav-trigger\[aria-controls\]/, 'mega menu triggers are bound');
  assert.match(js, /function initMegaMenus/, 'mega menu handler exists');
  assert.match(js, /byId\('navToggle'\)/, 'mobile menu is wired');
  assert.match(js, /setAttribute\('aria-expanded'/, 'ARIA state is updated');
});

test('dark footer has the five columns and a language selector', () => {
  assert.match(css, /\.ks-footer\s*\{[^}]*background: var\(--ks-footer-bg\)/, 'dark footer');
  ordered(html, [
    '<h2 class="ks-footer-h">Products</h2>',
    '<h2 class="ks-footer-h">Developers</h2>',
    '<h2 class="ks-footer-h">Enterprise</h2>',
    '<h2 class="ks-footer-h">Company</h2>',
    '<h2 class="ks-footer-h">Terms and policies</h2>'
  ], 'footer columns');
  assert.match(html, /id="languageSelect"/, 'language selector');
  assert.match(html, /class="ks-socials"/, 'social row');
  assert.match(js, /keel_security_language/, 'language preference is saved locally');
});

test('routing adds both clean URLs and keeps every rewrite target on disk', () => {
  assert.equal(rewriteBySource.get('/product/keel-security'), '/product/keel-security.html');
  assert.equal(rewriteBySource.get('/product/keel-security/'), '/product/keel-security.html');
  for (const { source, destination } of VERCEL.rewrites) {
    const target = path.join(SITE, destination.replace(/^\//, ''));
    assert.ok(fs.existsSync(target) && fs.statSync(target).isFile(),
      `${source}: rewrite target missing: ${destination}`);
  }
  const serverSource = fs.readFileSync(SERVER, 'utf8');
  assert.match(serverSource, /'\/product\/keel-security': '\/product\/keel-security\.html'/);
  assert.match(serverSource, /'\/product\/keel-security\/': '\/product\/keel-security\.html'/);
  const xml = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');
  assert.ok(xml.includes('<loc>https://keel-desktop.vercel.app/product/keel-security</loc>'),
    'sitemap lists the new route');
});

test('animation is subtle, rAF throttled and reduced-motion aware', () => {
  assert.match(js, /IntersectionObserver/, 'IntersectionObserver reveals');
  assert.match(js, /requestAnimationFrame/, 'rAF throttled scroll work');
  assert.match(js, /addEventListener\('scroll', onScroll, \{ passive: true \}\)/, 'passive scroll listener');
  assert.doesNotMatch(js, /setInterval/, 'no busy loops');
  assert.match(js, /prefers-reduced-motion/, 'JS reduced-motion kill switch');
  assert.match(js, /window\.matchMedia/, 'reads motion preference');
  assert.match(css, /\.ks-reveal/, 'reveal styles');
  assert.match(css, /transition: opacity \.2s ease, transform \.2s ease/, '200ms reveal <= 220ms');
  assert.match(css, /translateY\(12px\)/, 'reveal distance <= 14px');
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/, 'CSS reduced-motion kill switch');
  assert.match(css, /\.ks-header\.is-scrolled/, 'sticky nav shadow');
  assert.match(css, /--ks-card-shift/, 'floating card parallax');
  assert.match(js, /--ks-card-shift/, 'parallax variable is updated on scroll');
});

/* Local QA server smoke check for both clean URLs. */
let serverProcess;
let base;
let serverOutput = '';

async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

before(async () => {
  const port = await freePort();
  serverProcess = spawn(process.execPath, [SERVER], {
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

test('QA server serves the new page with and without a trailing slash', async () => {
  for (const route of ['/product/keel-security', '/product/keel-security/']) {
    const response = await fetch(`${base}${route}`);
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    const body = await response.text();
    assert.match(body, /<title>Keel Security — From scan to fix, done seamlessly<\/title>/);
    assert.match(body, /From scan to fix, done seamlessly/);
  }
});
