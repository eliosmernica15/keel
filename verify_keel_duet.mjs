#!/usr/bin/env node
/* Static verification for the KEEL Duet page. No dependencies. */
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = resolve(HERE, 'keel/site');
const HTML = resolve(SITE, 'product/keel-duet.html');
const CSS = resolve(SITE, 'ui/keel-duet.css');
const JS = resolve(SITE, 'ui/keel-duet.js');

let failures = 0;
const ok = (msg) => console.log('  PASS  ' + msg);
const bad = (msg) => { failures++; console.log('  FAIL  ' + msg); };

function check(cond, msg) { cond ? ok(msg) : bad(msg); }

console.log('\n=== KEEL Duet verification ===\n');

if (!existsSync(HTML)) { bad('missing HTML: ' + HTML); process.exit(1); }
const html = readFileSync(HTML, 'utf8');
const css = existsSync(CSS) ? readFileSync(CSS, 'utf8') : '';
const js = existsSync(JS) ? readFileSync(JS, 'utf8') : '';

check(html.length > 15000, `HTML is substantial (${html.length} bytes)`);
check(css.length > 5000, `CSS is substantial (${css.length} bytes)`);
check(js.length > 3000, `JS is substantial (${js.length} bytes)`);

check(/<body[^>]*class="[^"]*\bduet-page\b/.test(html), 'body carries duet-page class');
check(html.includes('/ui/keel-duet-shell.css'), 'links self-contained shell CSS');
check(html.includes('/ui/keel-duet.css'), 'links keel-duet.css');
check(!html.includes('/ui/landing.css'), 'does not depend on shared landing.css');
check(!html.includes('/ui/landing.js'), 'does not depend on shared landing.js');
check(html.includes('/ui/keel-duet.js'), 'loads keel-duet.js');

// All contract IDs
const ids = ['duet-waitlist','d-first','d-last','d-email','d-company','d-role','d-consent',
  'd-form-error','d-form-success','faq','duet-chat','duet-chat-fab','d-footer-search'];
for (const id of ids) check(html.includes(`id="${id}"`), `id #${id} present`);

// All contract class hooks
const classes = ['d-crumbs','d-hero-grid','d-form','d-row2','d-segment','d-seg-btn',
  'd-logo-strip','d-feature-grid','d-phone','d-accordion','d-acc-btn','d-acc-panel',
  'd-cta','d-cta-join','d-cta-outline','d-chat','d-chat-fab','d-toast','d-modal-overlay'];
for (const c of classes) check(html.includes(c) || js.includes(c) || css.includes(c), `class .${c} wired`);

// Brand: no Claude / Anthropic anywhere in page files
for (const [name, text] of [['HTML', html], ['CSS', css], ['JS', js]]) {
  check(!/\bClaude\b/.test(text), `${name} has no "Claude"`);
  check(!/\bAnthropic\b/.test(text), `${name} has no "Anthropic"`);
}

// No dead links
const hrefs = [...html.matchAll(/href="([^"]*)"/g)].map(m => m[1]);
const dead = hrefs.filter(h => h === '#' || h === '' || h.startsWith('javascript:'));
check(dead.length === 0, `no dead hrefs (${dead.length} found)`);

// Local asset/link targets exist
const cfg = JSON.parse(readFileSync(resolve(SITE, 'vercel.json'), 'utf8'));
const cfgRewriteSources = new Set(cfg.rewrites.map(r => r.source));
const local = hrefs.filter(h => h.startsWith('/') && !h.startsWith('//'));
for (const h of new Set(local)) {
  const pathname = h.split(/[?#]/)[0];
  const candidate = resolve(SITE, '.' + pathname);
  const alt = candidate.endsWith('.html') ? candidate : candidate + '.html';
  const rewritten = cfgRewriteSources.has(pathname);
  check(existsSync(candidate) || existsSync(alt) || rewritten, `local link target ${h} exists${rewritten ? ' (rewrite)' : ''}`);
}

// Buttons are typed or have data hooks
const btnTags = [...html.matchAll(/<button\b[^>]*>/gi)].map(m => m[0]);
const untyped = btnTags.filter(t => !/\btype="(button|submit|reset)"/i.test(t));
check(untyped.length === 0, `all ${btnTags.length} buttons have explicit type (${untyped.length} untyped)`);

// FAQ count
const faqCount = (html.match(/class="d-acc-btn"/g) || []).length;
check(faqCount === 9, `FAQ has 9 items (found ${faqCount})`);

// Config
check(cfg.rewrites.some(r => r.source === '/product/keel-duet' && r.destination === '/product/keel-duet.html'), 'vercel rewrite for /product/keel-duet');
check(cfg.redirects.some(r => r.source === '/product/keel-duet.html' && r.destination === '/product/keel-duet'), 'vercel redirect for .html');
const sitemap = readFileSync(resolve(SITE, 'sitemap.xml'), 'utf8');
check(sitemap.includes('https://keel-desktop.vercel.app/product/keel-duet'), 'sitemap includes Duet URL');

console.log(`\n=== ${failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'} ===\n`);
process.exit(failures === 0 ? 0 : 1);
