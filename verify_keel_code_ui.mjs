#!/usr/bin/env node
/* Static + syntax verification for the KEEL Code product page. No dependencies. */
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = resolve(HERE, 'keel/site');
const HTML = resolve(SITE, 'product/keel-code.html');
const CSS = resolve(SITE, 'ui/keel-code.css');
const JS = resolve(SITE, 'ui/keel-code.js');

let failures = 0;
const ok = (msg) => console.log('  PASS  ' + msg);
const bad = (msg) => { failures++; console.log('  FAIL  ' + msg); };
const check = (cond, msg) => { cond ? ok(msg) : bad(msg); };

console.log('\n=== KEEL Code product page verification ===\n');

if (!existsSync(HTML)) { bad('missing HTML: ' + HTML); process.exit(1); }
const html = readFileSync(HTML, 'utf8');
const css = existsSync(CSS) ? readFileSync(CSS, 'utf8') : '';
const js = existsSync(JS) ? readFileSync(JS, 'utf8') : '';
const cfg = JSON.parse(readFileSync(resolve(SITE, 'vercel.json'), 'utf8'));
const sitemap = readFileSync(resolve(SITE, 'sitemap.xml'), 'utf8');
const rewriteSources = new Set(cfg.rewrites.map((r) => r.source));

check(html.length > 20000, `HTML is substantial (${html.length} bytes)`);
check(css.length > 8000, `CSS is substantial (${css.length} bytes)`);
check(js.length > 3000, `JS is substantial (${js.length} bytes)`);

check(/<body[^>]*class="[^"]*\bcode-page\b/.test(html), 'body carries code-page class');
check(/<body[^>]*class="[^"]*\blanding\b/.test(html), 'body carries landing class (shared tokens)');
check(html.includes('/ui/landing.css'), 'links shared landing.css');
check(html.includes('/ui/keel-code.css'), 'links keel-code.css');
check(html.includes('/ui/landing.js'), 'loads shared landing.js');
check(html.includes('/ui/keel-code.js'), 'loads keel-code.js');
check(html.includes('id="top"'), 'has #top main anchor');
check(html.includes('Breadcrumb'), 'has breadcrumb navigation');

const ids = ['get-started', 'announcements', 'take-on', 'where-you-code', 'slack',
  'developers', 'faq', 'technical', 'newsletter', 'footer', 'c-modal', 'c-toast',
  'c-panel-team', 'c-panel-individual', 'c-news-form', 'c-news-msg',
  'c-modal-title', 'c-modal-body', 'authModal', 'helpSearch', 'helpForm',
  'searchStatus', 'newsChip', 'languageSelect', 'navToggle', 'mobileMenu'];
for (const id of ids) check(html.includes(`id="${id}"`), `id #${id} present`);

const classes = ['c-crumbs', 'c-hero-grid', 'c-hero-actions', 'c-ways', 'c-way',
  'c-logo-strip', 'c-plan-grid', 'c-plan', 'c-announce-grid', 'c-article',
  'c-changelog', 'c-terminal', 'c-terminal-body', 'c-ttab', 'c-takeon-grid',
  'c-feature', 'c-where-grid', 'c-where-card', 'c-copy', 'c-slack-inner',
  'c-voice-grid', 'c-voice', 'c-voice-logos', 'c-voice-note', 'c-faq',
  'c-res-grid', 'c-res', 'c-cta', 'c-cta-grid', 'c-cta-news', 'c-modal',
  'c-modal-backdrop', 'c-modal-close', 'c-toast', 'l-faq-item', 'l-faq-q',
  'l-faq-a', 'l-toggle-btn', 'l-plan-panel', 'js-auth'];
for (const c of classes) check(html.includes(c) || js.includes(c) || css.includes(c), `class .${c} wired`);

for (const [name, text] of [['HTML', html], ['CSS', css], ['JS', js]]) {
  check(!/\bClaude\b/.test(text), `${name} has no "Claude"`);
  check(!/\bAnthropic\b/.test(text), `${name} has no "Anthropic"`);
}

const hrefs = [...html.matchAll(/href="([^"]*)"/g)].map((m) => m[1]);
const dead = hrefs.filter((h) => h === '#' || h === '' || h.startsWith('javascript:'));
check(dead.length === 0, `no dead hrefs (${dead.length} found)`);

const local = hrefs.filter((h) => h.startsWith('/') && !h.startsWith('//'));
for (const h of new Set(local)) {
  const pathname = h.split(/[?#]/)[0];
  const candidate = resolve(SITE, '.' + pathname);
  const alt = candidate.endsWith('.html') ? candidate : candidate + '.html';
  const rewritten = rewriteSources.has(pathname);
  check(existsSync(candidate) || existsSync(alt) || rewritten,
    `local link target ${h} exists${rewritten ? ' (rewrite)' : ''}`);
}

const btnTags = [...html.matchAll(/<button\b[^>]*>/gi)].map((m) => m[0]);
const untyped = btnTags.filter((t) => !/\btype="(button|submit|reset)"/i.test(t));
check(untyped.length === 0, `all ${btnTags.length} buttons have explicit type (${untyped.length} untyped)`);

const faqCount = (html.match(/class="l-faq-item/g) || []).length;
check(faqCount === 7, `FAQ has 7 items (found ${faqCount})`);

check(cfg.rewrites.some((r) => r.source === '/product/keel-code' && r.destination === '/product/keel-code.html'),
  'vercel rewrite for /product/keel-code');
check(cfg.redirects.some((r) => r.source === '/product/keel-code.html' && r.destination === '/product/keel-code'),
  'vercel redirect for .html');
check(sitemap.includes('https://keel-desktop.vercel.app/product/keel-code'), 'sitemap includes Keel Code URL');

const braces = [...css].reduce((n, ch) => n + (ch === '{' ? 1 : ch === '}' ? -1 : 0), 0);
check(braces === 0, `CSS braces balanced (net ${braces})`);

// Responsive regression guard: hero previews must not shrink to 0 at <=900px.
check(/body\.code-page \.c-hero-shots\s*\{[^}]*width:\s*100%/.test(css),
  'hero previews grid has explicit width:100% at responsive breakpoints');
check(/c-shot[^{]*svg[^{]*\{[^}]*width:\s*100%/.test(css),
  'hero preview SVGs have explicit width:100%');

if (existsSync(JS)) {
  const result = spawnSync(process.execPath, ['--check', JS], { encoding: 'utf8' });
  check(result.status === 0, `node --check keel-code.js (${result.status === 0 ? 'ok' : result.stderr.trim()})`);
}

console.log(`\n=== ${failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'} ===\n`);
process.exit(failures === 0 ? 0 : 1);
