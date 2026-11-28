/* Static verification for the Keel Duet product page.
 * Run: node --test keel/site/tests/product-keel-duet.test.mjs
 * The page must follow the supplied reference structure, use only real routes,
 * keep both HTML entry points in sync, and wire real in-page behaviour.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const HTML_PATH = path.join(SITE, 'product', 'keel-duet.html');
const INDEX_PATH = path.join(SITE, 'product', 'keel-duet', 'index.html');
const CSS_PATH = path.join(SITE, 'ui', 'keel-duet.css');
const JS_PATH = path.join(SITE, 'ui', 'keel-duet.js');

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

test('both Keel Duet entry points exist and stay identical', () => {
  assert.ok(fs.existsSync(HTML_PATH), 'missing product/keel-duet.html');
  assert.ok(fs.existsSync(INDEX_PATH), 'missing product/keel-duet/index.html');
  assert.equal(html, index, 'the two entry points must serve the same design');
  assert.match(html, /^<!doctype html>/i, 'HTML document type');
  assert.match(html, /<body class="duet-page">/, 'duet page body class');
  assert.match(html, /href="\/ui\/keel-duet-shell\.css"/, 'shared shell stylesheet');
  assert.match(html, /href="\/ui\/keel-duet\.css"/, 'duet stylesheet');
  assert.match(html, /<script src="\/ui\/keel-duet\.js" defer><\/script>/, 'deferred JS');
});

test('no stale Claude branding, no /app links, no inline handlers', () => {
  for (const [name, source] of Object.entries(owned)) {
    assert.doesNotMatch(source, /claude/i, `${name}: stale Claude branding`);
  }
  assert.doesNotMatch(html, /\/app(?=["'/]|$)/, 'no /app links; use /login');
  const inlineHandler = /\s(?:onclick|onload|onerror|onchange|onsubmit|onmouseover|onfocus|onblur|onkeydown)\s*=/i;
  assert.doesNotMatch(html, inlineHandler, 'no inline event handlers in HTML');
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)|<style[\s>]/i, 'no inline script or style blocks');
  assert.doesNotMatch(html, /data:image/i, 'no inline data URIs in markup');
});

test('reference sections appear in order', () => {
  ordered(html, [
    '<header class="l-header d-header">',
    '<nav class="d-crumbs l-container"',
    '<section class="d-hero" id="waitlist">',
    '<section class="d-logos" id="connectors">',
    '<section class="d-features" id="features">',
    '<section class="d-faq" id="faq">',
    '<section class="d-cta d-reveal">',
    '<footer class="l-footer" id="footer">'
  ], 'page structure');
  assert.match(html, /<a href="\/">Product<\/a> <span aria-hidden="true">\/<\/span> Keel Duet<\/nav>/,
    'breadcrumb reads Product / Keel Duet');
});

test('sticky nav has a four-column Product mega menu and real top links', () => {
  const productMega = html.slice(
    html.indexOf('<div class="l-mega" id="mega-product"'),
    html.indexOf('<!-- Developers -->')
  );
  assert.equal((productMega.match(/class="l-mega-col"/g) || []).length, 4,
    'Product mega menu has four columns');
  const topLinks = html.slice(html.indexOf('<a class="l-nav-link" href="/login">'),
    html.indexOf('</nav>', html.indexOf('<a class="l-nav-link" href="/login">')));
  assert.match(topLinks, /href="\/login"[^>]*>Log in</, 'Log in link');
  assert.match(topLinks, /href="mailto:hello@keel\.ai"[^>]*>Contact sales</, 'Contact sales link');
  assert.match(html, /class="l-btn l-btn-dark l-btn-sm" href="\/login">Get Keel</, 'Get Keel link');
  assert.doesNotMatch(html, /data-auth="(?:login|sales|email)"/, 'no auth buttons in this page');
});

test('hero reproduces the reference copy, chips and actions', () => {
  assert.match(html, /class="d-burst"/, 'starburst mark');
  assert.match(html, /<h1 class="d-title">Get back to what needs you<\/h1>/, 'serif hero heading');
  assert.match(html, /waits for your OK when it matters\./, 'hero subtitle');
  assert.match(html, /Powered by Keel 5, Opus, Sonnet, Haiku and the other Keel models/,
    'model line');
  for (const model of ['Keel 5', 'Opus', 'Sonnet', 'Haiku', 'other Keel models']) {
    assert.ok(html.includes(`data-model="${model}"`), `model chip: ${model}`);
    assert.ok(js.includes(`'${model}'`), `model info for: ${model}`);
  }
  assert.match(html, /class="l-btn l-btn-dark" href="#waitlist-card">Join the waitlist</, 'primary CTA');
  assert.match(html, /class="l-btn l-btn-outline" href="mailto:hello@keel\.ai">Talk to sales</, 'secondary CTA');
});

test('waitlist fields validate and persist through localStorage', () => {
  for (const label of [
    'First name*', 'Last name*', 'Email address*', 'Company name*', 'Phone*'
  ]) {
    assert.ok(html.includes(`>${label}<`), `required field label: ${label}`);
  }
  assert.match(html, /name="platform" value="Android"/, 'Android radio');
  assert.match(html, /name="platform" value="iOS"/, 'iOS radio');
  assert.match(html, /What do you do, and what would you like to use Keel Duet first\?/, 'textarea prompt');
  assert.match(html, /id="d-form-error" role="alert"/, 'validation error region');
  assert.match(html, /id="d-form-success" role="status"/, 'saved state region');

  assert.match(js, /WAITLIST_KEY = 'keel_duet_waitlist'/, 'localStorage key');
  assert.match(js, /window\.localStorage\.setItem\(key, value\)/, 'storage write helper');
  assert.match(js, /storageSet\(WAITLIST_KEY/, 'writes the waitlist entry');
  assert.match(js, /EMAIL_PATTERN\.test/, 'validates email');
  assert.match(js, /PHONE_PATTERN\.test/, 'validates phone');
  assert.match(js, /aria-invalid/, 'marks invalid fields');
  assert.match(js, /platform: checked \? checked\.value : ''/, 'captures the selected platform');
  assert.match(css, /\.d-input\[aria-invalid="true"\]/, 'invalid field styling');
});

test('saved state is explicit about local-only storage', () => {
  assert.match(html, /Saved locally on this device — no account created\./, 'local-only success copy');
  assert.match(js, /Saved locally on this device — no account created\./, 'JS saved state message');
  assert.match(js, /blocked local storage, so nothing was saved/, 'honest storage failure state');
  assert.match(html, /Waitlist entries are stored locally on your device\./, 'footer disclaimer');
});

test('floating announcement overlaps the form and can be dismissed', () => {
  assert.match(html, /<aside class="d-announce" id="duet-announce"/, 'floating card');
  assert.match(html, /Keel Duet is here!/, 'announcement title');
  assert.match(html, /Support ongoing work in your browser and on your mobile device/,
    'announcement copy');
  assert.match(html, /class="d-announce-close"/, 'dismiss control');
  assert.match(html, /data-announcement>Read the announcement</, 'announcement action');
  assert.match(js, /keel_duet_announcement_dismissed/, 'dismissal is remembered');
  assert.match(css, /\.d-announce\s*\{/, 'overlapping card styles');
});

test('connector logos and phone preview match the reference', () => {
  assert.match(html, /Works with more than 6,000 connectors and plugins/, 'connector line');
  for (const logo of ['stripe', '1Password', 'shopify', 'gmail']) {
    assert.ok(html.includes(logo), `connector: ${logo}`);
  }
  assert.match(html, /Monday, October 19/, 'phone date');
  assert.match(html, /class="d-phone-time">9:41</, 'phone time');
  assert.match(html, /5 steps in progress and 2 waiting for your OK/, 'notification text');
  assert.match(html, /data-next-step>Find next step</, 'phone action');
  assert.match(html, /class="d-guide-link" href="\/privacy">Read our safety guide/, 'safety guide link');
});

test('FAQ contains the eight listed questions in order, with JS handlers', () => {
  ordered(html, [
    'What is Keel Duet?',
    'How does Keel Duet work?',
    'How is Keel Duet different from Keel Code/Cowork?',
    'What can Keel Duet do?',
    'Who can use Keel Duet and what does it cost?',
    'How does usage work for Keel Duet?',
    'Where can I use Keel Duet?',
    "What's next for Keel Duet?"
  ], 'FAQ order');
  assert.equal((html.match(/class="d-acc-item/g) || []).length, 8, 'eight accordion items');
  assert.match(js, /\.d-acc-btn'/, 'accordion buttons are bound');
  assert.match(js, /function initAccordion/, 'accordion handler exists');
  assert.match(js, /\.l-nav-trigger\[aria-controls\]/, 'mega menu triggers are bound');
  assert.match(js, /function initMegaMenus/, 'mega menu handler exists');
  assert.match(js, /setAttribute\('aria-expanded'/, 'ARIA state is updated');
  assert.match(js, /#navToggle|byId\('navToggle'\)/, 'mobile menu is wired');
});

test('dark CTA and five-column footer are present', () => {
  assert.match(html, /<h2 class="d-cta-title">Help us shape it<\/h2>/, 'CTA heading');
  assert.match(html, /class="l-btn d-cta-join">Join the waitlist</, 'CTA join button');
  assert.match(html, /data-announcement>Read the announcement</, 'CTA announcement button');
  ordered(html, [
    '<h2 class="l-footer-h">Products</h2>',
    '<h2 class="l-footer-h">Developers</h2>',
    '<h2 class="l-footer-h">Enterprise</h2>',
    '<h2 class="l-footer-h">Company</h2>',
    '<h2 class="l-footer-h">Terms and policies</h2>'
  ], 'footer columns');
  assert.match(html, /class="l-brand-mark"/, 'Keel mark in footer');
  assert.match(html, /id="languageSelect"/, 'language selector');
  assert.match(html, /class="l-socials"/, 'social row');
});

test('animation is subtle, rAF throttled and reduced-motion aware', () => {
  assert.match(js, /IntersectionObserver/, 'IntersectionObserver reveals');
  assert.match(js, /requestAnimationFrame/, 'rAF throttled scroll work');
  assert.match(js, /addEventListener\('scroll', onScroll, \{ passive: true \}\)/, 'passive scroll listener');
  assert.doesNotMatch(js, /setInterval/, 'no busy loops');
  assert.match(js, /prefers-reduced-motion/, 'JS reduced-motion kill switch');
  assert.match(js, /window\.matchMedia/, 'reads motion preference');
  assert.match(css, /\.d-reveal/, 'reveal styles');
  assert.match(css, /transition: opacity \.2s ease, transform \.2s ease/, '200ms reveal <= 220ms');
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/, 'CSS reduced-motion kill switch');
  assert.match(css, /\.l-header\.is-scrolled/, 'sticky nav shadow');
  assert.match(css, /--duet-phone-shift/, 'phone parallax');
  assert.match(css, /--duet-announce-shift/, 'notification parallax');
});
