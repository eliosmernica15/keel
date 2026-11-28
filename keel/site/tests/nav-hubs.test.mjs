/* Static + local-route verification for the three top-nav hub pages.
 * Run: node --test keel/site/tests/nav-hubs.test.mjs
 *
 * Checks the /developers, /enterprise and /resources hubs: paired files,
 * real routes and rewrites, the shared warm editorial shell, local-only
 * behaviour, progressive enhancement and the QA server.
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
const SERVER = path.join(REPO, 'serve_keel_site.mjs');

const HUBS = ['developers', 'enterprise', 'resources'];
const TITLES = {
  developers: 'Build with Keel — Developer hub | Keel',
  enterprise: 'Keel for teams and organizations | Keel',
  resources: 'Resource hub — articles, tutorials and docs | Keel',
};
const HERO_TITLES = {
  developers: 'Build with Keel',
  enterprise: 'Keel for teams and organizations',
  resources: 'Everything you need to get more from Keel',
};
const REWRITES = {
  '/developers': '/developers.html',
  '/enterprise': '/enterprise.html',
  '/resources': '/resources.html',
  '/developers/': '/developers.html',
  '/enterprise/': '/enterprise.html',
  '/resources/': '/resources.html',
};

const CSS = fs.readFileSync(path.join(SITE, 'ui', 'nav-hubs.css'), 'utf8');
const JS = fs.readFileSync(path.join(SITE, 'ui', 'nav-hubs.js'), 'utf8');
const VERCEL = JSON.parse(fs.readFileSync(path.join(SITE, 'vercel.json'), 'utf8'));
const SERVER_SRC = fs.readFileSync(SERVER, 'utf8');
const SITEMAP = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');
const REWRITE_BY_SOURCE = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));

const HTMLS = {};
for (const hub of HUBS) {
  HTMLS[hub] = fs.readFileSync(path.join(SITE, `${hub}.html`), 'utf8');
}

function between(source, start, end) {
  const a = source.indexOf(start);
  assert.notEqual(a, -1, `missing start marker ${start}`);
  const b = source.indexOf(end, a + start.length);
  assert.notEqual(b, -1, `missing end marker ${end}`);
  return source.slice(a, b);
}
function count(source, needle) { return source.split(needle).length - 1; }
function localPath(route) { return path.join(SITE, route.replace(/^\/+/, '')); }
function existsOnDisk(route) {
  const clean = route.split('#')[0];
  if (clean === '/') return fs.existsSync(path.join(SITE, 'index.html'));
  const target = localPath(clean);
  return fs.existsSync(target) || fs.existsSync(path.join(target, 'index.html'));
}
async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

/* ------------------------------------------------------------------ files */

test('all three hubs exist as top-level files and byte-identical index copies', () => {
  for (const hub of HUBS) {
    const top = path.join(SITE, `${hub}.html`);
    const index = path.join(SITE, hub, 'index.html');
    assert.ok(fs.existsSync(top), `missing ${hub}.html`);
    assert.ok(fs.existsSync(index), `missing ${hub}/index.html`);
    assert.equal(HTMLS[hub], fs.readFileSync(index, 'utf8'), `${hub}: copies must be byte-identical`);
    assert.match(HTMLS[hub], /^<!doctype html>/i, `${hub}: doctype`);
    assert.ok(HTMLS[hub].includes(`<title>${TITLES[hub]}`), `${hub}: title`);
    assert.ok(HTMLS[hub].includes(`<link rel="canonical" href="https://keel-desktop.vercel.app/${hub}" />`), `${hub}: canonical`);
    assert.ok(HTMLS[hub].includes('href="/ui/keel-duet-shell.css"'), `${hub}: shared shell stylesheet`);
    assert.ok(HTMLS[hub].includes('href="/ui/nav-hubs.css"'), `${hub}: hub stylesheet`);
    assert.ok(HTMLS[hub].includes('<script src="/ui/nav-hubs.js" defer></script>'), `${hub}: deferred script`);
    assert.ok(HTMLS[hub].includes('<body class="duet-page navhub-page">'), `${hub}: warm editorial body`);
  }
});

test('no stale branding, no /app links, no inline handlers, scripts, styles or data URIs', () => {
  for (const [name, source] of Object.entries({ css: CSS, js: JS, ...HTMLS })) {
    assert.doesNotMatch(source, /claude/i, `${name}: stale branding`);
  }
  for (const hub of HUBS) {
    const html = HTMLS[hub];
    assert.doesNotMatch(html, /\/app(?=["'/]|$)/, `${hub}: no /app route`);
    assert.doesNotMatch(html, /href="\/app/, `${hub}: no /app links; use /login`);
    assert.doesNotMatch(html, /\son(?:click|load|error|change|submit|mouseover|focus|blur|keydown)\s*=/i,
      `${hub}: no inline event handlers`);
    assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)|<style[\s>]/i, `${hub}: no inline code blocks`);
    assert.doesNotMatch(html, /data:(?:image|text|application)/i, `${hub}: no data URIs`);
    assert.doesNotMatch(html, /\sstyle=/i, `${hub}: no inline styles`);
    assert.ok(html.includes('href="/login"'), `${hub}: sign-in uses /login`);
  }
});

test('every local asset reference exists', () => {
  for (const hub of HUBS) {
    const refs = [...HTMLS[hub].matchAll(/(?:src|href)="(\/(?:assets|ui)\/[^"]+)"/g)].map((m) => m[1]);
    assert.ok(refs.length > 0, `${hub}: no local assets`);
    for (const ref of refs) {
      assert.ok(fs.existsSync(localPath(ref)), `${hub}: missing asset ${ref}`);
    }
  }
});

/* ------------------------------------------------------------------- design */

test('each hub reuses the sticky four-column Product mega menu with real model links', () => {
  for (const hub of HUBS) {
    const html = HTMLS[hub];
    assert.ok(html.includes('<header class="l-header" id="nh-header">'), `${hub}: sticky header`);
    const product = between(html, '<div class="l-mega" id="mega-product"', '</div>\n        </div>\n\n        <div class="l-nav-item" data-menu="developers">');
    assert.equal(count(product, '<div class="l-mega-col">'), 4, `${hub}: four Product columns`);
    for (const model of ['mythos', 'opus', 'sonnet', 'haiku']) {
      assert.ok(html.includes(`href="/models/${model}"`), `${hub}: model link ${model}`);
    }
    assert.ok(html.includes('aria-hidden="true"') && html.includes('aria-expanded="false"'), `${hub}: menu a11y state`);
    assert.ok(html.includes('id="mobileMenu"') && html.includes('id="navToggle"'), `${hub}: mobile menu`);
    assert.ok(html.includes('<footer class="l-footer" id="footer">'), `${hub}: dark footer`);
    assert.ok(html.includes('id="languageSelect"'), `${hub}: language selector`);
    assert.ok(html.includes('l-footer-sub">Models'), `${hub}: footer Models column`);
  }
});

test('each hub has hero, content sections, FAQ, CTA and honest local-only notes', () => {
  for (const hub of HUBS) {
    const html = HTMLS[hub];
    assert.ok(html.includes('<section class="nh-hero"'), `${hub}: hero`);
    assert.ok(html.includes(HERO_TITLES[hub]), `${hub}: hero title text`);
    assert.ok(count(html, '<section class="nh-section') >= 4, `${hub}: at least four content sections`);
    assert.ok(html.includes('id="faq"'), `${hub}: FAQ anchor`);
    const faqs = count(html, 'class="nh-acc-item nh-reveal"');
    assert.ok(faqs >= 4 && faqs <= 6, `${hub}: 4-6 FAQ items (got ${faqs})`);
    assert.ok(html.includes('<section class="nh-cta'), `${hub}: dark CTA band`);
    assert.ok(html.includes('data-nh-tabs') && html.includes('role="tablist"'), `${hub}: working tabs`);
    assert.ok(/[Nn]othing (?:is )?sent/.test(html), `${hub}: explicit nothing-sent note`);
    assert.ok(html.includes('data-reveal') === false, `${hub}: uses .nh-reveal instead`);
    assert.ok(html.includes('nh-reveal'), `${hub}: reveal hooks`);
  }
  assert.ok(count(HTMLS.developers, 'data-nh-copy') >= 3, 'developers: three copy buttons');
  assert.ok(HTMLS.developers.includes('data-nh-form="quickstart"'), 'developers: local quickstart form');
  assert.ok(HTMLS.enterprise.includes('data-nh-form="choice"'), 'enterprise: local selection form');
  assert.ok(HTMLS.resources.includes('data-nh-search=".nh-search-status"'), 'resources: local filter form');
  assert.ok(HTMLS.enterprise.includes('No invented certifications'), 'enterprise: no fabricated certifications');
});

test('all internal links resolve to a rewrite or a file that exists', () => {
  for (const hub of HUBS) {
    const hrefs = [...HTMLS[hub].matchAll(/href="(\/[^"]*)"/g)].map((m) => m[1].split('#')[0]);
    assert.ok(hrefs.length > 20, `${hub}: expected a real link set`);
    for (const href of hrefs) {
      assert.ok(REWRITE_BY_SOURCE.has(href) || existsOnDisk(href),
        `${hub}: dead link ${href}`);
    }
    assert.ok(hrefs.some((href) => href.startsWith('mailto:') === false && href.includes('/resources/articles')),
      `${hub}: links to the article index`);
  }
  for (const hub of HUBS) {
    assert.ok([...HTMLS[hub].matchAll(/href="(mailto:[^"]+)"/g)].length > 0, `${hub}: real mailto contact link`);
  }
});

/* --------------------------------------------------------------- behaviour */

test('nav-hubs.js wires menus, tabs, FAQ, copy, local forms, IO, rAF and reduced motion', () => {
  for (const needle of [
    'IntersectionObserver', 'nh-animate', 'nh-reveal', 'is-visible',
    "addEventListener('scroll', onScroll, { passive: true })", 'window.requestAnimationFrame(update)',
    "matchMedia('(prefers-reduced-motion: reduce)')",
    '.l-nav-trigger', '.l-nav-toggle', 'aria-expanded', 'Escape',
    'data-nh-tab', 'aria-selected', '.nh-acc-btn',
    '[data-nh-copy]', 'navigator.clipboard', 'Nothing sent.',
    '[data-nh-form="quickstart"]', '[data-nh-form="choice"]', '[data-nh-search]',
    "byId('languageSelect')", 'localStorage', 'event.preventDefault()',
  ]) {
    assert.ok(JS.includes(needle), `nav-hubs.js missing ${needle}`);
  }
  assert.doesNotMatch(JS, /\b(fetch|XMLHttpRequest|WebSocket|sendBeacon)\s*\(/, 'no network calls');
  assert.match(CSS, /translateY\(12px\)/, 'reveal distance <= 14px');
  assert.match(CSS, /\.2s ease/, 'reveal duration <= 220ms');
  assert.match(CSS, /prefers-reduced-motion: reduce/, 'reduced-motion kill switch');
  assert.match(CSS, /overflow-x: clip/, 'no horizontal overflow');
});

/* ------------------------------------------------------------------ routes */

test('vercel.json holds exactly the six new rewrites and keeps its headers', () => {
  for (const [source, destination] of Object.entries(REWRITES)) {
    assert.equal(REWRITE_BY_SOURCE.get(source), destination, `rewrite ${source}`);
    assert.equal(VERCEL.rewrites.filter((r) => r.source === source).length, 1, `one rewrite for ${source}`);
  }
  for (const hub of HUBS) {
    assert.equal(VERCEL.rewrites.filter((r) => r.destination === `/${hub}.html`).length, 2,
      `${hub}: clean and trailing-slash only`);
  }
  assert.ok(VERCEL.headers.some((h) => h.source === '/(.*)' && h.headers.some((e) => e.key === 'Content-Security-Policy')),
    'existing CSP header untouched');
  assert.ok(VERCEL.redirects.length > 0, 'existing redirects untouched');
});

test('every Vercel rewrite target exists on disk', () => {
  for (const { source, destination } of VERCEL.rewrites) {
    assert.match(destination, /^\//, `${source}: site-absolute destination`);
    const target = localPath(destination);
    const file = destination.endsWith('/') ? path.join(target, 'index.html') : target;
    assert.ok(fs.existsSync(file) && fs.statSync(file).isFile(), `${source}: missing ${destination}`);
  }
});

test('the local QA server mirrors the same six rewrites', () => {
  const block = between(SERVER_SRC, 'const REWRITES = {', '\n};');
  for (const hub of HUBS) {
    assert.ok(block.includes(`'/${hub}': '/${hub}.html',`), `server clean rewrite /${hub}`);
    assert.ok(block.includes(`'/${hub}/': '/${hub}.html',`), `server slash rewrite /${hub}/`);
  }
});

test('sitemap includes the three clean hub URLs', () => {
  const locs = [...SITEMAP.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/g)].map((m) => m[1]);
  for (const hub of HUBS) {
    const url = `https://keel-desktop.vercel.app/${hub}`;
    assert.ok(locs.includes(url), `sitemap missing ${url}`);
    assert.ok(REWRITE_BY_SOURCE.has(`/${hub}`), `${hub}: sitemap URL has a rewrite`);
  }
});

/* ---------------------------------------------------------------- local QA */

let serverProcess;
let base;
let serverOutput = '';

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

test('QA server serves all three hubs with and without a trailing slash', async () => {
  for (const hub of HUBS) {
    for (const route of [`/${hub}`, `/${hub}/`]) {
      const response = await fetch(`${base}${route}`);
      const body = await response.text();
      assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
      assert.ok(body.includes(HERO_TITLES[hub]), `${route}: hub content missing`);
      assert.ok(body.length > 1000, `${route}: unexpectedly small response`);
    }
  }
});
