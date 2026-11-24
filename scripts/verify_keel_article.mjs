// Static verification for the "Introducing Keel Ship" article page.
// Run: node scripts/verify_keel_article.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SITE = path.join(ROOT, 'keel', 'site');
const PAGE = path.join(SITE, 'resources', 'articles', 'introducing-keel-ship', 'index.html');
const CSS = path.join(SITE, 'ui', 'article.css');
const JS = path.join(SITE, 'ui', 'article.js');
const ASSETS = path.join(SITE, 'assets', 'img', 'article');

let pass = 0;
let fail = 0;
const ok = (msg) => { pass++; console.log('  PASS  ' + msg); };
const bad = (msg) => { fail++; console.log('  FAIL  ' + msg); };
const check = (cond, msg) => cond ? ok(msg) : bad(msg);

console.log('\nKeel Ship article — static verification\n');

// --- files exist -----------------------------------------------------------
for (const f of [PAGE, CSS, JS]) {
  check(fs.existsSync(f), `exists: ${path.relative(ROOT, f)}`);
}
if (!fs.existsSync(PAGE)) process.exit(1);

const html = fs.readFileSync(PAGE, 'utf8');
const css = fs.existsSync(CSS) ? fs.readFileSync(CSS, 'utf8') : '';
const js = fs.existsSync(JS) ? fs.readFileSync(JS, 'utf8') : '';

// --- branding --------------------------------------------------------------
const banned = html.match(/Claude|Anthropic/gi) || [];
check(banned.length === 0, `no Claude/Anthropic strings in HTML (found ${banned.length})`);
check(/Introducing Keel Ship/.test(html), 'title/heading says "Introducing Keel Ship"');
check(/By the Keel team/.test(html), 'byline is KEEL-branded');
check(/keel-desktop\.vercel\.app/.test(html), 'canonical/OG URL points at keel-desktop.vercel.app');

// --- structure / duplicate IDs --------------------------------------------
const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
check(dupes.length === 0, `unique element IDs (duplicates: ${[...new Set(dupes)].join(', ') || 'none'})`);

const requiredIds = ['ks-header', 'ks-search', 'ks-search-input', 'ks-menu-toggle',
  'ks-mobile-menu', 'ks-toc', 'ks-main', 'ks-newsletter', 'ks-email', 'ks-news-msg', 'ks-to-top'];
for (const id of requiredIds) check(ids.includes(id), `required id #${id}`);

const requiredClasses = ['ks-brand', 'ks-nav', 'ks-nav-group', 'ks-mega', 'ks-btn-dark',
  'ks-article-grid', 'ks-toc-nav', 'ks-prose', 'ks-figure', 'ks-code', 'ks-copy',
  'ks-callout', 'ks-steps', 'ks-checklist', 'ks-related', 'ks-related-card',
  'ks-footer', 'ks-news-form', 'ks-footer-cols', 'ks-to-top'];
for (const cls of requiredClasses) check(html.includes(cls), `required class .${cls}`);

// --- CSP-safe markup -------------------------------------------------------
check(!/<script(?![^>]*\bsrc=)/i.test(html), 'no inline <script> (CSP)');
check(!/<style[\s>]/i.test(html), 'no inline <style> (CSP)');
check(!/\son(click|load|error|submit|mouseover|change)\s*=/i.test(html), 'no inline event handlers');
check(/href="\/ui\/article\.css"/.test(html), 'links /ui/article.css');
check(/src="\/ui\/article\.js"[^>]*defer/.test(html) || /defer[^>]*src="\/ui\/article\.js"/.test(html), 'defers /ui/article.js');

// --- TOC anchors -----------------------------------------------------------
const tocHrefs = [...html.matchAll(/<a[^>]+href="#([^"]+)"[^>]*>/g)].map((m) => m[1]);
const relatives = ['introduction', 'keel-code-subagent', 'replaying-sessions',
  'preserving-context', 'how-to-use', 'availability'];
for (const a of relatives) {
  check(ids.includes(a), `section id #${a}`);
  check(tocHrefs.includes(a), `TOC link to #${a}`);
}

// --- local asset / link resolution ----------------------------------------
const rewrites = Object.fromEntries(
  (JSON.parse(fs.readFileSync(path.join(SITE, 'vercel.json'), 'utf8')).rewrites || [])
    .map((r) => [r.source, r.destination])
);
const refs = [...html.matchAll(/(?:src|href)="(\/[^"#?]+)"/g)].map((m) => m[1]);
const missing = [];
for (const ref of [...new Set(refs)]) {
  const rel = rewrites[ref] || ref.replace(/^\//, '');
  if (!fs.existsSync(path.join(SITE, rel))) missing.push(ref);
}
check(missing.length === 0, `all local src/href targets exist (missing: ${missing.join(', ') || 'none'})`);

const articleImgs = [...html.matchAll(/src="(\/assets\/img\/article\/[^"]+)"/g)].map((m) => m[1]);
const missingImgs = articleImgs.filter((img) => !fs.existsSync(path.join(SITE, img.replace(/^\//, ''))));
check(missingImgs.length === 0, `article images present (${articleImgs.length} refs, missing: ${missingImgs.join(', ') || 'none'})`);

// --- CSS / JS sanity -------------------------------------------------------
for (const sel of ['.ks-header', '.ks-mega', '.ks-article-grid', '.ks-toc-nav a',
  '.ks-related-grid', '.ks-footer', '.ks-to-top', '[hidden]']) {
  check(css.includes(sel), `CSS defines ${sel}`);
}
try {
  execFileSync(process.execPath, ['--check', JS], { stdio: 'pipe' });
  ok('JS syntax valid (node --check)');
} catch (e) {
  bad('JS syntax valid: ' + String(e.stderr || e.message).slice(0, 300));
}
for (const token of ['ks-search-open', 'ks-menu-toggle', 'ks-copy', 'ks-newsletter', 'ks-to-top']) {
  check(js.includes(token), `JS wires ${token}`);
}

// --- deploy config ---------------------------------------------------------
const vc = JSON.parse(fs.readFileSync(path.join(SITE, 'vercel.json'), 'utf8'));
check((vc.rewrites || []).some((r) => r.source === '/resources/articles/introducing-keel-ship'),
  'vercel.json rewrites the exact article URL');
const sm = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');
check(sm.includes('/resources/articles/introducing-keel-ship'), 'sitemap includes article URL');

// --- related article pages -------------------------------------------------
const extraPages = [
  path.join(SITE, 'resources', 'articles', 'introducing-keel-code', 'index.html'),
  path.join(SITE, 'resources', 'articles', 'keel-ship-session-format', 'index.html'),
];
for (const pagePath of extraPages) {
  if (!fs.existsSync(pagePath)) { bad(`exists: ${path.relative(ROOT, pagePath)}`); continue; }
  const h = fs.readFileSync(pagePath, 'utf8');
  const label = path.basename(path.dirname(pagePath));
  check(!/Claude|Anthropic/i.test(h), `${label}: KEEL branding only`);
  const pageIds = [...h.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  check(new Set(pageIds).size === pageIds.length, `${label}: unique IDs`);
  check(/href="\/ui\/article\.css"/.test(h) && /src="\/ui\/article\.js"[^>]*defer/.test(h), `${label}: shared CSS/JS`);
  check(!/<script(?![^>]*\bsrc=)|<style[\s>]/i.test(h), `${label}: no inline CSS/JS`);
  const pageRefs = [...h.matchAll(/(?:src|href)="(\/[^"#?]+)"/g)].map((m) => m[1]);
  const missingRefs = [...new Set(pageRefs)].filter((ref) => {
    const rel = rewrites[ref] || ref.replace(/^\//, '');
    return !fs.existsSync(path.join(SITE, rel));
  });
  check(missingRefs.length === 0, `${label}: all links/assets resolve (missing: ${missingRefs.join(', ') || 'none'})`);
  const anchors = [...h.matchAll(/href="#([^"]+)"/g)].map((m) => m[1]);
  const badAnchors = anchors.filter((a) => !pageIds.includes(a));
  check(badAnchors.length === 0, `${label}: in-page anchors resolve (bad: ${badAnchors.join(', ') || 'none'})`);
}

console.log(`\nResult: ${pass} passed, ${fail} failed\n`);
process.exit(fail ? 1 : 0);
