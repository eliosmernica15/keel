/* Static + local-route verification for the four future Keel model concept pages.
 * Run: node --test keel/site/tests/models.test.mjs
 *
 * These pages are concepts only. The suite checks that all four entry points
 * stay in sync, are labelled as concepts everywhere, use only real routes,
 * wire real in-page behaviour, and resolve through the same rewrite map that
 * production mirrors.
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

const KEYS = ['mythos', 'opus', 'sonnet', 'haiku'];
const TITLES = {
  mythos: 'Keel Mythos', opus: 'Keel Opus',
  sonnet: 'Keel Sonnet', haiku: 'Keel Haiku',
};
const VISUALS = { mythos: 'prism', opus: 'orbit', sonnet: 'wave', haiku: 'chip' };

const css = fs.readFileSync(path.join(SITE, 'ui', 'models.css'), 'utf8');
const js = fs.readFileSync(path.join(SITE, 'ui', 'models.js'), 'utf8');
const VERCEL = JSON.parse(fs.readFileSync(path.join(SITE, 'vercel.json'), 'utf8'));
const SERVER_SRC = fs.readFileSync(SERVER, 'utf8');
const SITEMAP = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');

const HTMLS = {};
for (const key of KEYS) {
  HTMLS[key] = fs.readFileSync(path.join(SITE, 'models', `${key}.html`), 'utf8');
}

function ordered(source, needles, label) {
  let cursor = -1;
  for (const needle of needles) {
    const found = source.indexOf(needle, cursor + 1);
    assert.notEqual(found, -1, `${label}: missing ${JSON.stringify(needle)}`);
    cursor = found;
  }
}

function count(source, needle) {
  return source.split(needle).length - 1;
}

function between(source, start, end) {
  const a = source.indexOf(start);
  assert.notEqual(a, -1, `missing start marker ${start}`);
  const b = source.indexOf(end, a + start.length);
  assert.notEqual(b, -1, `missing end marker ${end}`);
  return source.slice(a, b);
}

/* ------------------------------------------------------------------ files */

test('all four pages exist and match their byte-identical index copies', () => {
  for (const key of KEYS) {
    const top = path.join(SITE, 'models', `${key}.html`);
    const index = path.join(SITE, 'models', key, 'index.html');
    assert.ok(fs.existsSync(top), `missing models/${key}.html`);
    assert.ok(fs.existsSync(index), `missing models/${key}/index.html`);
    const html = HTMLS[key];
    assert.equal(html, fs.readFileSync(index, 'utf8'), `${key}: copy must match index`);
    assert.match(html, /^<!doctype html>/i, `${key}: doctype`);
    assert.ok(html.includes(`<body class="mdl-body mdl--${key}">`), `${key}: body class`);
    assert.ok(html.includes('href="/ui/models.css"'), `${key}: shared stylesheet`);
    assert.ok(html.includes('<script src="/ui/models.js" defer></script>'), `${key}: deferred JS`);
    assert.ok(html.includes(`<link rel="canonical" href="https://keel-desktop.vercel.app/models/${key}" />`),
      `${key}: canonical URL`);
  }
});

test('no stale branding, no /app links, no inline handlers, scripts, styles or data URIs', () => {
  for (const [name, source] of Object.entries({ css, js, ...HTMLS })) {
    assert.doesNotMatch(source, /claude/i, `${name}: stale branding`);
  }
  const inlineHandler = /\son(?:click|load|error|change|submit|mouseover|focus|blur|keydown)\s*=/i;
  for (const key of KEYS) {
    const html = HTMLS[key];
    assert.doesNotMatch(html, /\/app(?=["'/]|$)/, `${key}: no /app route`);
    assert.doesNotMatch(html, /href="\/app/, `${key}: no /app links; use /login`);
    assert.doesNotMatch(html, inlineHandler, `${key}: no inline event handlers`);
    assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)|<style[\s>]/i, `${key}: no inline code blocks`);
    assert.doesNotMatch(html, /data:image/i, `${key}: no inline data URIs`);
  }
});

test('every referenced local asset exists', () => {
  for (const key of KEYS) {
    const refs = [...HTMLS[key].matchAll(/(?:src|href)="(\/(?:assets|ui)\/[^"]+)"/g)].map((m) => m[1]);
    assert.ok(refs.length > 0, `${key}: no local assets referenced`);
    for (const ref of refs) {
      assert.ok(fs.existsSync(path.join(SITE, ref.replace(/^\/+/, ''))), `${key}: missing asset ${ref}`);
    }
  }
});

/* ----------------------------------------------------------------- routes */

test('vercel.json holds all eight model rewrites and keeps its existing headers', () => {
  const bySource = new Map(VERCEL.rewrites.map((r) => [r.source, r.destination]));
  for (const key of KEYS) {
    assert.equal(bySource.get(`/models/${key}`), `/models/${key}.html`, `clean rewrite ${key}`);
    assert.equal(bySource.get(`/models/${key}/`), `/models/${key}.html`, `slash rewrite ${key}`);
  }
  assert.ok(VERCEL.headers.some((h) => h.source === '/(.*)' && h.headers.some((e) => e.key === 'Content-Security-Policy')),
    'existing CSP header is untouched');
});

test('the local QA server mirrors the same eight rewrites', () => {
  const block = between(SERVER_SRC, 'const REWRITES = {', '\n};');
  for (const key of KEYS) {
    assert.ok(block.includes(`'/models/${key}': '/models/${key}.html',`), `server clean rewrite ${key}`);
    assert.ok(block.includes(`'/models/${key}/': '/models/${key}.html',`), `server slash rewrite ${key}`);
  }
});

test('sitemap lists the four model routes', () => {
  for (const key of KEYS) {
    assert.ok(SITEMAP.includes(`<loc>https://keel-desktop.vercel.app/models/${key}</loc>`),
      `sitemap missing /models/${key}`);
  }
});

/* ---------------------------------------------------------------- content */

test('every page states the concept status and labels every target', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    assert.ok(html.includes('CONCEPT / FUTURE MODEL — not currently available'), `${key}: concept badge`);
    assert.ok(html.includes('A concept, not a product'), `${key}: availability statement`);
    assert.ok(html.includes('Not currently available'), `${key}: availability row`);
    assert.ok(html.includes('not currently available'), `${key}: meta description`);
    assert.ok(count(html, 'Concept target') >= 8, `${key}: concept targets are labelled`);
    assert.ok(count(html, 'not measured') >= 1, `${key}: no factual performance claim`);
  }
});

test('sections appear in the required order on every page', () => {
  for (const key of KEYS) {
    const needles = [
      '<header class="mdl-header"',
      '<nav class="mdl-crumbs"',
      'CONCEPT / FUTURE MODEL',
      '<section class="mdl-hero"',
      '<section class="mdl-section mdl-section--alt" id="designed-for"',
      '<section class="mdl-section" id="specs"',
    ];
    if (key === 'mythos') needles.push('<section class="mdl-section" id="fable"');
    needles.push(
      '<section class="mdl-section mdl-section--alt" id="compare"',
      '<section class="mdl-section" id="availability"',
      '<section class="mdl-section mdl-section--alt" id="faq"',
      '<section class="mdl-cta"',
      '<footer class="mdl-footer"'
    );
    ordered(HTMLS[key], needles, key);
  }
});

test('breadcrumb reads Models / Keel <name>', () => {
  for (const key of KEYS) {
    ordered(HTMLS[key], [
      '<li>Models</li>',
      '<li aria-hidden="true">/</li>',
      `aria-current="page">${TITLES[key]}</li>`,
    ], key);
  }
});

test('sticky nav has a four-column Product mega menu linking to all four models', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const mega = between(html, '<div class="mdl-mega" id="mdl-mega-product"', '<div class="mdl-mega-footer">');
    assert.equal(count(mega, 'class="mdl-mega-col"'), 4, `${key}: four mega columns`);
    assert.ok(mega.includes('>Models <span class="mdl-mega-dot"'), `${key}: Models column heading`);
    for (const other of KEYS) {
      assert.ok(mega.includes(`href="/models/${other}"`), `${key}: mega links /models/${other}`);
      assert.ok(html.includes(`class="mdl-mobile-link" href="/models/${other}"`),
        `${key}: mobile menu links /models/${other}`);
    }
    assert.ok(mega.includes(`href="/models/${key}" aria-current="page"`), `${key}: current model marked`);
    assert.ok(html.includes('href="/login"'), `${key}: login link, never /app`);
  }
});

test('hero has a serif statement, two description lines, a CSS visual and a local notify form', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const hero = between(html, '<section class="mdl-hero"', '<section class="mdl-section');
    assert.ok(hero.includes('<h1 class="mdl-hero-title"'), `${key}: serif hero statement`);
    assert.equal(count(hero, '<p class="mdl-hero-line">'), 2, `${key}: two-line description`);
    assert.ok(hero.includes(`<div class="mdl-visual mdl-visual--${VISUALS[key]}"`), `${key}: CSS-drawn visual`);
    assert.ok(hero.includes('data-parallax'), `${key}: hero parallax layer`);
    assert.ok(hero.includes('data-notify-form') && hero.includes('data-notify-input') &&
      hero.includes('data-notify-result'), `${key}: notify form hooks`);
    assert.ok(hero.includes('>Get notified</button>'), `${key}: Get notified submit`);
    assert.ok(hero.includes('nothing is sent'), `${key}: honest form note`);
  }
});

test('designed-for row and concept-target grid each contain four cards', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const designed = between(html, '<section class="mdl-section mdl-section--alt" id="designed-for"',
      '<section class="mdl-section" id="specs"');
    const specs = between(html, '<section class="mdl-section" id="specs"',
      key === 'mythos' ? '<section class="mdl-section" id="fable"' :
        '<section class="mdl-section mdl-section--alt" id="compare"');
    assert.equal(count(designed, 'class="mdl-feature-card"'), 4, `${key}: four designed-for cards`);
    assert.equal(count(specs, 'class="mdl-feature-card"'), 4, `${key}: four spec cards`);
    for (const label of ['Context window', 'Response tempo', 'Modalities', 'Ideal tasks']) {
      assert.ok(specs.includes(label), `${key}: spec ${label}`);
    }
  }
});

test('Mythos carries a dedicated Fable creative-variant section', () => {
  const mythos = HTMLS.mythos;
  const fable = between(mythos, '<section class="mdl-section" id="fable"',
    '<section class="mdl-section mdl-section--alt" id="compare"');
  assert.ok(fable.includes('Fable — the creative side of Mythos'), 'Fable heading');
  assert.ok(fable.includes('Creative variant · concept'), 'Fable is labelled a concept');
  for (const label of ['Worldbuilding', 'Narrative voice', 'Visual storytelling']) {
    assert.ok(fable.includes(label), `Fable detail: ${label}`);
  }
  for (const key of ['opus', 'sonnet', 'haiku']) {
    assert.doesNotMatch(HTMLS[key], /id="fable"/, `${key}: no Fable section`);
  }
});

test('comparison section has three working tab panels of concept targets', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const compare = between(html, '<section class="mdl-section mdl-section--alt" id="compare"',
      '<section class="mdl-section" id="availability"');
    assert.equal(count(compare, 'role="tablist"'), 1, `${key}: one tablist`);
    assert.equal(count(compare, 'data-tab="family"'), 3, `${key}: three tabs`);
    assert.equal(count(compare, 'role="tabpanel"'), 3, `${key}: three panels`);
    assert.equal(count(compare, 'class="mdl-table"'), 3, `${key}: three tables`);
    assert.equal(count(compare, 'class="mdl-model-cell"'), 12, `${key}: four models per table`);
    assert.equal(count(compare, 'class="is-current"'), 3, `${key}: current model highlighted in each table`);
    for (const other of KEYS) {
      assert.ok(compare.includes(`<td class="mdl-model-cell">Keel ${TITLES[other].split(' ')[1]}`),
        `${key}: compares ${other}`);
    }
    assert.ok(compare.includes('not a real product, benchmark or promise'), `${key}: comparison disclaimer`);
  }
});

test('availability section points to the roadmap and login', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const availability = between(html, '<section class="mdl-section" id="availability"',
      '<section class="mdl-section mdl-section--alt" id="faq"');
    assert.ok(availability.includes('href="/roadmap"'), `${key}: roadmap link`);
    assert.ok(availability.includes('href="/login"'), `${key}: login link`);
  }
});

test('FAQ has working disclosure hooks for every question', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const faq = between(html, '<section class="mdl-section mdl-section--alt" id="faq"',
      '<section class="mdl-cta"');
    const expected = key === 'mythos' ? 6 : 5;
    assert.equal(count(faq, 'data-faq-q'), expected, `${key}: ${expected} questions`);
    assert.equal(count(faq, 'class="mdl-faq-a"'), expected, `${key}: matching answers`);
    assert.equal(count(faq, 'aria-expanded="false"'), expected, `${key}: collapsed by default`);
    for (const id of faq.match(/aria-controls="(mdl-faq-a-[^"]+)"/g) || []) {
      const value = id.slice('aria-controls="'.length, -1);
      assert.ok(faq.includes(`id="${value}"`), `${key}: FAQ panel ${value} exists`);
    }
  }
});

test('dark CTA and shared dark footer include a language selector', () => {
  for (const key of KEYS) {
    const html = HTMLS[key];
    const cta = between(html, '<section class="mdl-cta"', '</main>');
    assert.ok(cta.includes('href="/login"'), `${key}: CTA login link`);
    assert.ok(cta.includes('href="/roadmap"'), `${key}: CTA roadmap link`);
    const footer = between(html, '<footer class="mdl-footer"', '</footer>');
    assert.equal(count(footer, 'class="mdl-footer-col"'), 4, `${key}: four footer columns`);
    assert.ok(footer.includes('data-lang-toggle'), `${key}: language toggle`);
    assert.ok(footer.includes('data-lang-menu'), `${key}: language menu`);
    assert.equal(count(footer, 'data-lang-option'), 4, `${key}: four languages`);
    assert.ok(footer.includes('KEEL 2026 All rights reserved.'), `${key}: shared footer line`);
  }
});

/* --------------------------------------------------------------- behaviour */

test('shared JS wires progressive enhancement, reduced motion and passive rAF scroll', () => {
  assert.match(js, /document\.documentElement\.classList\.add\("mdl-reveal-ready"\)/, 'reveal opt-in class');
  assert.match(js, /new IntersectionObserver/, 'IntersectionObserver reveals');
  assert.match(js, /document\.documentElement\.classList\.add\("mdl-faq-ready"\)/, 'FAQ opt-in class');
  assert.match(js, /matchMedia\("\(prefers-reduced-motion: reduce\)"\)/, 'reduced-motion kill switch');
  assert.match(js, /requestAnimationFrame/, 'rAF throttle');
  assert.match(js, /addEventListener\("scroll", frame, \{ passive: true \}\)/, 'passive scroll listener');
  assert.match(js, /\[data-parallax\]/, 'per-model parallax layer');
  assert.match(js, /\[data-mega-trigger\]/, 'mega menu handler');
  assert.match(js, /\[data-mobile-toggle\]/, 'mobile menu handler');
  assert.match(js, /\[data-tab\]/, 'tab handler');
  assert.match(js, /\[data-faq-q\]/, 'FAQ handler');
  assert.match(js, /\[data-notify-form\]/, 'notify form handler');
  assert.match(js, /Nothing was sent/, 'explicit nothing-sent state');
});

test('shared CSS keeps reveals short and defines four distinct accents', () => {
  assert.match(css, /--mdl-reveal-duration:\s*220ms/, 'reveal duration <= 220ms');
  assert.match(css, /--mdl-reveal-shift:\s*14px/, 'reveal shift <= 14px');
  assert.match(css, /html\.mdl-reveal-ready body\.mdl-body \[data-reveal\]/, 'no-JS content stays visible');
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/, 'CSS reduced-motion guard');
  assert.match(css, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/, 'four-column mega menu');
  for (const key of KEYS) {
    assert.match(css, new RegExp(`body\\.mdl--${key}\\s*\\{`), `${key}: accent block`);
  }
});

/* ------------------------------------------------------------ local server */

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

test('QA server serves every clean route and trailing-slash variant', async () => {
  for (const key of KEYS) {
    for (const route of [`/models/${key}`, `/models/${key}/`]) {
      const response = await fetch(`${base}${route}`);
      const body = await response.text();
      assert.equal(response.status, 200, `${route}: expected 200, got ${response.status}`);
      assert.ok(body.includes(TITLES[key]), `${route}: correct page`);
      assert.ok(body.includes('CONCEPT / FUTURE MODEL'), `${route}: concept badge`);
    }
    const physical = await fetch(`${base}/models/${key}/index.html`);
    assert.equal(physical.status, 200, `${key}: physical index must serve`);
    assert.equal(await physical.text(), HTMLS[key], `${key}: served index matches copy`);
  }
});
