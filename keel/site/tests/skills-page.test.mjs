/* Static + local-route verification for the Keel Skills capabilities page.
 * Run: node --test keel/site/tests/skills-page.test.mjs
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
const HTML_PATH = path.join(SITE, 'skills.html');
const INDEX_PATH = path.join(SITE, 'skills', 'index.html');
const CSS_PATH = path.join(SITE, 'ui', 'skills.css');
const JS_PATH = path.join(SITE, 'ui', 'skills.js');
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

test('both Skills entry points exist and stay byte-identical', () => {
  assert.ok(fs.existsSync(HTML_PATH), 'missing skills.html');
  assert.ok(fs.existsSync(INDEX_PATH), 'missing skills/index.html');
  assert.equal(html, index, 'the two entry points must serve the same design');
  assert.match(html, /^<!doctype html>/i, 'HTML document type');
  assert.match(html, /<body class="duet-page skills-page">/, 'skills page body class');
  assert.match(html, /href="\/ui\/keel-duet-shell\.css"/, 'shared shell stylesheet');
  assert.match(html, /href="\/ui\/skills\.css"/, 'skills stylesheet');
  assert.match(html, /<script src="\/ui\/skills\.js" defer><\/script>/, 'deferred JS');
  assert.match(html, /<link rel="canonical" href="https:\/\/keel-desktop\.vercel\.app\/skills" \/>/,
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
    '<section class="s-hero" id="skills-home">',
    '<section class="s-benefits" id="benefits">',
    '<section class="s-use" id="use">',
    '<section class="s-create" id="writing">',
    '<section class="s-stories" id="stories">',
    '<footer class="l-footer" id="footer">'
  ], 'page structure');
  assert.match(html,
    /<a href="\/">Product<\/a> <span aria-hidden="true">\/<\/span> Skills<\/nav>/,
    'breadcrumb reads Product / Skills');
});

test('sticky nav has a four-column Product mega menu with Capabilities → Skills', () => {
  const productMega = html.slice(
    html.indexOf('<div class="l-mega" id="mega-product"'),
    html.indexOf('<div class="l-nav-item" data-menu="developers">')
  );
  assert.equal((productMega.match(/class="l-mega-col"/g) || []).length, 4,
    'Product mega menu has four columns');
  assert.match(productMega, /<p class="l-mega-title">Capabilities<\/p>/, 'Capabilities column');
  assert.match(productMega, /href="\/skills" aria-current="page">Skills<\/a>/,
    'Capabilities → Skills link');
  assert.match(html, /href="\/login">Log in<\/a>/, 'Log in link');
  assert.match(html, /href="mailto:hello@keel\.ai">Contact sales<\/a>/, 'Contact sales link');
  assert.match(html, /class="l-btn l-btn-dark l-btn-sm" href="\/login">Get Keel</, 'Get Keel link');
  assert.match(html, /href="\/skills">Skills<\/a>\s*<a href="\/download">Download desktop app<\/a>/,
    'mobile menu includes Skills');
});

test('hero reproduces the reference copy, beige document mock and CTA', () => {
  assert.match(html, /<h1 class="s-hero-title">Teach Keel your way of working<\/h1>/, 'serif hero heading');
  assert.match(html,
    /Turn your organization's processes, institutional knowledge and specialized expertise into Keel skills to apply them automatically, every time\./,
    'hero subtitle');
  assert.match(html, /src="\/assets\/img\/platform\/pa-icon-skills\.svg"/, 'small skills icon');
  assert.match(html, /class="l-btn l-btn-dark" href="#writing" data-scroll="writing">Writing skills</,
    'primary CTA');
  assert.match(html, /class="s-doc-card s-parallax" data-depth="0\.6"/, 'parallax document card');
  assert.match(html, /<span class="s-doc-title">Creating a skill<\/span>/, 'Creating a skill card');
  assert.match(html, /data-file-tab="description" aria-selected="true" role="tab">Description\.md</,
    'Description.md file tab');
  assert.match(html, /data-copy="doc-copy"/, 'hero copy control');
  assert.match(html, /data-hero-build aria-controls="s-hero-status"/, 'hero build action');
});

test('four benefit cards and three feature blocks match the reference copy', () => {
  for (const heading of [
    'Get specialized results on specialized tasks',
    'Capture what your organization knows',
    'Build once, use everywhere',
    'Stack skills for complex work'
  ]) {
    assert.ok(html.includes(`<h3>${heading}</h3>`), `benefit: ${heading}`);
  }
  assert.equal((html.match(/data-benefit=/g) || []).length, 4, 'four real benefit disclosures');
  ordered(html, [
    '<article class="s-feature s-reveal" id="built-in">',
    '<article class="s-feature s-feature-alt s-reveal" id="company-skills">',
    '<article class="s-feature s-reveal" id="individual">'
  ], 'feature blocks');

  assert.match(html, /How teams use skills/, 'feature section heading');
  assert.match(html, /Keel comes with built-in skills for common workflows\. You can add your own to give it specialized expertise for your work\./,
    'feature section description');
  for (const bullet of [
    'Create reusable workflows',
    'Automate frequently repeated tasks',
    'Handle repetitive tasks consistently',
    "Encode your organization's knowledge",
    'Unify company specific output across teams',
    'Create a library of skills in a single click',
    'Build rules for how you like to work',
    'Create skills that turn repeated tasks into workflows for Keel'
  ]) {
    assert.ok(html.includes(`<li>${bullet}</li>`), `bullet: ${bullet}`);
  }
  assert.equal((html.match(/class="s-mock /g) || []).length, 3, 'three side mock cards');
  assert.equal((html.match(/data-mock-tab=/g) || []).length, 2, 'mock tabs are wired');
});

test('two green feature cards, code sample and accordion are present', () => {
  ordered(html, [
    '<article class="s-green-card s-reveal" id="creator">',
    '<article class="s-green-card s-reveal" id="skill-md">'
  ], 'green cards');
  assert.match(html, /<h2>Try the skill-creator skill<\/h2>/, 'skill creator card');
  assert.match(html, /<h2>Develop your own SKILL\.md file<\/h2>/, 'SKILL.md card');
  assert.match(html, /<span class="s-prompt-label">Sample prompt<\/span>/, 'sample prompt box');
  assert.match(html, /data-copy="creator-prompt"/, 'prompt copy button');
  assert.match(html, /<pre id="code-sample">/, 'static code snippet');
  assert.match(html, /data-copy="code-sample"/, 'code copy button');
  assert.match(html, /href="#skill-md" data-scroll="skill-md">Learn how to use it/, 'Learn how to use it');
  assert.match(html, /href="\/requirements">Read the documentation/, 'documentation link');
  assert.equal((html.match(/class="s-acc-item/g) || []).length, 3, 'three accordion items');
  assert.match(html, /class="s-acc-item is-open s-reveal"/, 'first accordion item expanded');
});

test('three testimonial cards with real story disclosures', () => {
  for (const brand of ['Figma', 'box', 'Notion']) {
    assert.ok(html.includes(`<p class="s-story-brand">${brand}</p>`), `story: ${brand}`);
  }
  assert.equal((html.match(/data-story=/g) || []).length, 3, 'three story cards');
  assert.equal((html.match(/Read the full story/g) || []).length, 3, 'three full-story links');
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
  assert.match(html, /id="footerSearch"/, 'footer search');
  assert.match(html, /KEEL 2026 All rights reserved\. Skills is a capability of Keel\./,
    'signature');
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
    'function initScrollLinks', 'function initFileTabs', 'function initCopyButtons',
    'function initHeroBuild', 'function initBenefits', 'function initMockTabs',
    'function initStoryFocus', 'function initAccordion', 'function initStories',
    'function initMegaMenus', 'function initMobileNav', 'function initFooterSearch',
    'function initLanguage', 'function initReveals', 'function initScrollEffects'
  ]) {
    assert.ok(js.includes(handler), `handler exists: ${handler}`);
  }
  for (const selector of [
    '[data-scroll]', '[data-file-tab]', '[data-copy]', '[data-hero-build]',
    '[data-benefit]', '[data-mock-tab]', '[data-story-focus]', '[data-story]',
    '.l-nav-trigger[aria-controls]', "byId('navToggle')", "byId('footerSearch')",
    "byId('languageSelect')"
  ]) {
    assert.ok(js.includes(selector), `JS binds ${selector}`);
  }
  assert.match(js, /\.s-acc-btn'/, 'accordion buttons are bound');
  assert.match(js, /setAttribute\('aria-expanded'/, 'ARIA state is updated');
  assert.match(js, /navigator\.clipboard\.writeText/, 'clipboard is used');
  assert.match(js, /copyText\(text\)/, 'copy handler performs a copy');
  assert.match(js, /byId\(button\.getAttribute\('aria-controls'\)\)/, 'disclosures are bound');
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
  assert.match(css, /--s-shift/, 'hero document parallax');
});

test('route rewrites, sitemap and QA server resolve both clean URLs', () => {
  const rewrites = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));
  for (const route of ['/skills', '/skills/']) {
    assert.equal(rewrites.get(route), '/skills.html', `rewrite for ${route}`);
    assert.ok(SERVER.includes(`'${route}': '/skills.html'`),
      `QA server rewrite for ${route}`);
  }
  assert.ok(fs.existsSync(HTML_PATH), 'rewrite target exists');
  assert.ok(SITEMAP.includes('https://keel-desktop.vercel.app/skills'),
    'sitemap includes the new route');
  /* Every pre-existing route and header is preserved. */
  assert.equal(rewrites.get('/artifacts'), '/artifacts.html', 'existing rewrite kept');
  assert.equal(rewrites.get('/features/artifacts'), '/features/artifacts.html', 'existing rewrite kept');
  assert.equal(rewrites.get('/product/design'), '/product/design.html', 'existing rewrite kept');
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
  for (const route of ['/skills', '/skills/']) {
    const response = await fetch(`${base}${route}`);
    const body = await response.text();
    assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
    assert.match(body, /Teach Keel your way of working/, `${route}: page content`);
    assert.equal(body, html, `${route}: same design as the .html entry point`);
  }
});

test('QA server serves the shared assets used by the page', async () => {
  for (const asset of [
    '/ui/skills.css', '/ui/skills.js', '/ui/keel-duet-shell.css',
    '/assets/img/platform/pa-icon-skills.svg'
  ]) {
    const response = await fetch(`${base}${asset}`);
    assert.equal(response.status, 200, `${asset}: expected 200, got ${response.status}`);
  }
});
