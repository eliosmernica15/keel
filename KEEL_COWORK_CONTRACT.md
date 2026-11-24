# KEEL Cowork page — shared implementation contract

Goal: recreate https://claude.com/product/cowork (layout, sections, forms, interactions)
as a **static, dependency-free** KEEL-branded page served at **https://keel-desktop.vercel.app/product/cowork**.
Reference copy is available in the conversation; the canonical KEEL copy is below.

Brand rules
- Product name: **KEEL Cowork**. Brand wordmark: **KEEL** (uppercase).
- Replace every occurrence of "Claude" with "KEEL" and "Anthropic" with "KEEL".
- Accent color: `--cw-accent: #d97757` (same warm orange as existing KEEL pages).
- Page palette: `--cw-page:#f7f6f2`, `--cw-page-alt:#f1efe8`, `--cw-soft:#faf9f5`,
  `--cw-card:#ffffff`, `--cw-ink:#1b1b1b`, `--cw-muted:#6b6a66`,
  `--cw-line:#dedcd6`, `--cw-dark:#191919`.
- Fonts: system stack only, e.g. `Georgia, 'Times New Roman', serif` for display headings
  and `ui-sans-serif, -apple-system, 'Segoe UI', Arial, sans-serif` for body.
- **No external requests** (Vercel CSP: `img-src 'self' data: blob:`, `connect-src 'self'`).
  All images must be local SVG in `keel/site/assets/img/cw-*.svg` or inline SVG/CSS.

Files and ownership
| File | Owner |
|---|---|
| `keel/site/product/cowork.html` | HTML agent |
| `keel/site/ui/cowork.css` | CSS agent |
| `keel/site/ui/cowork.js` | JS agent |
| `keel/site/assets/img/cw-*.svg`, `keel/site/vercel.json`, `keel/site/sitemap.xml`, `serve_keel_site.mjs`, `keel/site/README.md`, `keel/site/product/README.md`, `verify_cowork_ui.mjs` | Assets/routing agent |

## Global DOM contract (all agents MUST use these exact hooks)

- `<body class="cw-body">`, skip link `<a class="cw-skip" href="#main-content">`.
- Every class is prefixed `cw-`. JS uses `data-*` hooks, never styling classes.
- Root container `<div class="cw-page">`.
- Header: `<header class="cw-header" id="cw-header">` containing
  - `<a class="cw-brand" href="/">` with `<img class="cw-brand-mark" src="/assets/img/cw-mark.svg" alt="">` + `<span>KEEL</span>`
  - `<nav class="cw-nav" aria-label="Primary">` with three dropdown items:
    `data-nav="product"`, `data-nav="developers"`, `data-nav="enterprise"`;
    each has `<button class="cw-nav-trigger" aria-expanded="false" aria-controls="cw-menu-…">` and
    `<div class="cw-mega" id="cw-menu-…" hidden>`.
  - Right side: `<button class="cw-btn cw-btn-dark cw-nav-cta" data-action="open-auth">Log in</button>`,
    `<a class="cw-btn cw-btn-dark" href="/download">Download app</a>`, `<a class="cw-btn cw-btn-primary" href="/app">Try KEEL</a>`,
    `<button class="cw-hamburger" aria-label="Open menu" aria-expanded="false" aria-controls="cw-mobile-menu">`.
  - Mobile drawer: `<div class="cw-mobile-menu" id="cw-mobile-menu" hidden>` with links.
- News toast: `<aside class="cw-news" id="cw-news">` with `.cw-news-kicker`, `.cw-news-title`,
  `.cw-news-body`, `<a class="cw-news-link" href="/product/overview">Read what changed</a>`,
  `<button class="cw-news-close" data-action="dismiss-news" aria-label="Dismiss">`.
- `<main id="main-content">` contains sections in this order (IDs exact):

1. `#hero` — `<section class="cw-section cw-hero">`:
   - `<p class="cw-eyebrow">KEEL Cowork</p>`
   - `<h1 class="cw-hero-title">The work behind your best work</h1>`
   - `<p class="cw-hero-sub">KEEL Cowork completes tasks you can steer from anywhere. Give it a goal, and it works across your files and tools. You come back to polished work for your review.</p>`
   - Buttons: `<a class="cw-btn cw-btn-dark" href="/download">Download for macOS</a>`, `<button class="cw-btn cw-btn-light" data-action="open-contact">Talk to sales</button>`
   - Note: `Works with a paid plan. Rolling out on web, mobile. Not on a paid plan? <a href="/pricing">Upgrade now</a>`
   - Hero mockup: `<div class="cw-hero-visual"><img src="/assets/img/cw-app-window.svg" alt="KEEL Cowork app window showing a task, files and a generated deck"></div>`
2. `#capabilities` — heading "Core capabilities", subhead "Cowork is your teammate for the work that fills your day."
   6 cards in `.cw-cap-grid`, each `<article class="cw-cap-card">` with icon `<img src="/assets/img/cw-cap-N.svg">`, `<h3>`, `<p>`:
   1. "KEEL Cowork takes on your tasks" — "Works directly in folders and tools you choose, and runs your task to deliver work for review. No need to copy from a chat or paste into files."
   2. "Say what, not how" — "Tell KEEL what you need, not how. It opens browsers for web tasks and takes over your screen only when it has to."
   3. "See the work as it happens" — "KEEL shows each step: the files it opens, tools it uses, and choices it makes. Follow along from anywhere, and redirect it if you need to."
   4. "Your work follows you" — "KEEL Cowork runs on web, desktop, and mobile and is the same KEEL, wherever you work. Start at your desk, pick it up on your phone."
   5. "KEEL works when you don't" — "Close your laptop, it keeps going. Schedule a task for any cadence, and it runs unattended. You come back to your deck, spreadsheet, or research."
   6. "More than one thing at a time" — "Big projects are split into chunks that run together. While it drafts, it researches and organizes at the same time. You review polished work."
   Below: built-in browser feature with image `/assets/img/cw-browser.svg`, heading "A built-in browser for Cowork", body copy from reference:
   "When a task requires opening a site, reading a page, or filling a form, KEEL opens a browser in the Cowork side panel instead of yours while you keep working."
   bullet list: "No installation needed.", "Separate from your own browser, logins, and tabs.", "Sign in once for every session, or import cookies to stay signed in to your browser (Chrome, Edge, and Firefox on macOS; Firefox on Windows and Linux)."
   note: "Available in the Cowork desktop app on Pro, Max, Ultra, and Team plans. Enterprise admins manage it in Organization settings → Cowork."
   `<a class="cw-link" href="#tasks">See more use cases</a>`
3. `#tasks` — heading "Power through tedious tasks", subhead "Show KEEL what good looks like, then let it handle the rest."
   Tabs `<div class="cw-task-tabs" role="tablist">` with 4 buttons `data-task="reports|sheets|review|notes"`:
   "Schedule reports", "Build spreadsheets", "Review in bulk", "Analyze notes".
   Interactive panel `.cw-task-panel` with:
   - `.cw-task-note` "Interact with the data—hover and toggle views to uncover patterns"
   - `.cw-task-prompt-label` "Prompt" and `<pre class="cw-task-prompt" data-prompt>` containing the exact weekly marketing readout prompt from the reference (KEEL-branded: replace "Claude" → "KEEL" if present; keep Drive/Amplitude/Marketing wording).
   - `.cw-task-connectors-label` "Connectors" and two connector chips with local logos:
     `<img src="/assets/img/cw-amplitude.svg"> Amplitude`, `<img src="/assets/img/cw-microsoft.svg"> Microsoft 365`.
   - `.cw-task-visual` containing `<img src="/assets/img/cw-deck.svg" alt="Generated deck preview">` and a view toggle
     `<button class="cw-view-btn" data-view="slides">Slides</button>` / `<button class="cw-view-btn" data-view="data">Data</button>`
   - caption `<h3 class="cw-task-caption">Schedule recurring reports, ready for review</h3>` + paragraph from reference.
   Each tab changes prompt, connectors, visual caption, and heading. All four variants must be in the JS data map.
4. `#plugins` — heading "Customize KEEL with plugins", subhead "Plugins bundle your tools, knowledge, and workflows into a single install so KEEL shows up as a specialist from day one.", `<a class="cw-btn cw-btn-dark" href="#plugins-list">Explore plugins</a>`
   3 feature cards: Skills / Connectors / Sub-agents, each with "Learn more" link to `/product/overview`.
   Graphic `<img src="/assets/img/cw-plugins.svg">` + heading "Customize Cowork with plugins" + paragraph + `<a href="/product/overview">Read more</a>`.
   Carousel `<div class="cw-carousel" id="plugins-list">` with slides:
   1. "Brand voice (by Tribe AI)" — reference description; 2. "Monthly close (by KEEL Labs)" — description; 3. "Support triage (by KEEL Labs)" — description.
   Controls: `<button class="cw-carousel-prev" data-carousel="plugins" aria-label="Previous">`, next, and `.cw-carousel-count` showing "1 of 3".
5. `#blog` — three article cards (Built-in browser, Enterprise deployment, Plugin marketplace) with dates from reference and local thumbnails
   `/assets/img/cw-article-browser.svg`, `cw-article-enterprise.svg`, `cw-article-plugins.svg`; each card links to `/product/overview`.
6. `#usecase` — `<section class="cw-section cw-usecase cw-alt">` heading "Introducing KEEL Cowork for everyday work"
   Tabs `<button class="cw-persona-tab" data-persona="marketing|sales|legal">` labels Marketing / Sales / Legal.
   Video poster `<img src="/assets/img/cw-video-marketing.svg">` with play button `<button class="cw-play" data-action="open-video">`;
   caption `<h3>` "KEEL Cowork for marketing" + paragraph "See how KEEL uses KEEL Cowork to gather weekly reviews on a schedule.";
   `<a class="cw-link" href="/product/overview">Learn more</a>`. Each persona has its own title/description/poster (local SVGs `cw-video-sales.svg`, `cw-video-legal.svg`).
7. `#control` — heading "Stay in control", subhead "KEEL Cowork takes real actions on your files and in connected tools. Enterprise admins can configure permissions to customize security according to their needs.", `<a class="cw-btn cw-btn-light" href="/privacy">Read our safety guide</a>`
   3 cards: "You decide what KEEL can access", "KEEL asks before acting", "For Teams & Enterprise" with reference copy.
   Sub-block "Runs where your data lives" with copy + 3 local partner logo SVGs (Amazon Bedrock, Gemini Enterprise Agent Platform, Microsoft Foundry) named `cw-partner-1.svg` etc.
   Testimonial carousel with 5 quotes from reference (Zapier / Thomson Reuters / Airtree / Brainlabs / Hubspot) and local logo SVGs `cw-quote-1.svg` … `cw-quote-5.svg`.
   Controls with `data-carousel="quotes"` and count "1 of 5".
8. `#pricing` — heading "Choose a plan, then start using KEEL Cowork."
   Tabs `<button class="cw-plan-tab" data-plan="individual|team">` Individual / Team & Enterprise.
   Individual cards: Pro $17, Max $100, Ultra $200 with reference descriptions and `<a class="cw-btn cw-btn-dark" href="/app">Try KEEL</a>`; Ultra CTA `href="/product/overview"`.
   Team cards: Team $25 / user/month and Enterprise "Custom" with "Talk to sales" buttons using `data-action="open-contact"`.
   Fine print about usage limits and taxes from reference.
9. `#faq` — `<h2>FAQ</h2>` with 10 accordion items using `<button class="cw-faq-q" aria-expanded="false" data-faq>` and `<div class="cw-faq-a" hidden>`:
   questions exactly as reference (KEEL-branded). Include the "Getting started" help card with `<a href="/requirements">Read more</a>`.
10. `#get-started` — dark CTA section `<section class="cw-section cw-cta">` heading "Get started with KEEL Cowork", subhead "Download the desktop app and hand off your first task in minutes.", buttons Download for macOS (`/download`) and Talk to sales (`data-action="open-contact"`).

Footer `<footer class="cw-footer">` with:
- `.cw-footer-columns` containing Product / Capabilities / Extensions / Models / Enterprise / Departments / Industries / Programs / Developers / Platform / Resources / Help and security / Company / Terms and policies (use the link labels from reference; all hrefs point to real local routes such as `/`, `/download`, `/app`, `/product/overview`, `/product/keel-code`, `/product/keel-duet`, `/keel-in-chrome`, `/privacy`, `/terms`, `/requirements`, `/roadmap`, `/notices`, `/trademark`, or `mailto:hello@keel.dev`).
- `.cw-footer-search` with `<form data-form="footer-search">`, label "Search keel.com", input and submit button.
- `.cw-footer-bottom` with `© 2026 KEEL`, language `<select data-lang>` (English, 日本語, Deutsch, Français, 한국어, Italiano, Español) and social icon links (x.com, threads, linkedin, youtube, instagram — use generic inline SVG circles with aria-labels; no external images).
- Cookie banner `<div class="cw-cookie" id="cw-cookie">` with Accept / Decline buttons `data-action="cookie-accept|cookie-decline"` and localStorage key `cw-cookie-choice`.

Overlays (place at end of body, outside main):
- Contact/sales modal `<div class="cw-modal" id="contact-modal" hidden>` with form `[data-form="contact"]`: fields Name, Work email, Company, Message; submit button "Send request"; on submit preventDefault, validate, show `.cw-toast` success message "Thanks — we'll be in touch." Focus trap, Escape closes, backdrop closes.
- Auth modal `<div class="cw-modal" id="auth-modal" hidden>` with email input, "Continue with email" and "Continue with Google (demo)" buttons; success toast "Signed in as …" (demo only, no network).
- Video modal `<div class="cw-modal" id="video-modal" hidden>` with poster, play/pause button, progress bar, title; clicking play animates progress via CSS transition/JS interval; no external media.
- Toast container `<div class="cw-toast" id="cw-toast" role="status" aria-live="polite">`.

## JS behavior contract

- IIFE, `'use strict'`, no libraries, no network calls. Defer-loaded.
- Nav dropdowns: click toggles; hovering another closes previous; Escape closes all; outside click closes; `aria-expanded`/`hidden` kept in sync. Keyboard focus works.
- Hamburger toggles mobile drawer; sets `aria-expanded`; body class `cw-menu-open`.
- News dismiss hides toast and stores `cw-news-dismissed` in localStorage.
- Task tabs, persona tabs, plan tabs: toggle `aria-selected`, update visible panels/content from a data map, keep DOM in sync, no layout break.
- View toggle (`data-view`) switches `.cw-task-visual` between slides/data artwork by toggling `hidden` on two images.
- Carousels: prev/next + count, wrap around; hidden slides get `hidden`; keyboard arrow support; `aria-live` count.
- FAQ accordion: click toggles one item at a time (close others), `aria-expanded` + `hidden`, smooth height optional.
- Forms: validate required fields and email format with `type="email"`/regex; on success show toast and reset form; on invalid show inline `.cw-field-error` text; never navigate away.
- Footer search: on submit show toast "Searching KEEL for '<term>'" and keep user on page.
- Language select: on change show toast "Language set to X (demo)".
- Cookie buttons: store choice, hide banner; restore on load.
- Modals: open from `data-action`, close on backdrop/Escape/close button; restore focus; basic focus trap (Tab cycles within modal).
- Video modal play toggles a CSS progress animation and label Play/Pause.
- All interactions must be reversible and keyboard accessible; no console errors.

## CSS contract

- Mobile-first, responsive breakpoints at 640/900/1200px. Max content width 1200px with `.cw-container`.
- Match reference feel: off-white background, large serif centered headings, generous whitespace, thin borders, dark primary buttons, orange secondary accent, card grids, dark footer.
- All interactive states: `:hover`, `:focus-visible` (2px orange outline), `[aria-selected="true"]`, `[aria-expanded="true"]`.
- `prefers-reduced-motion` disables transitions/animations.
- Sticky header with subtle shadow on scroll (class `cw-scrolled` toggled by JS).
- No fixed heights that clip content; carousels show one slide at a time.

## QA contract

`verify_cowork_ui.mjs` (assets/routing agent) must assert, by reading files:
- HTML contains all section IDs, all `data-*` hooks listed here, and no string "Claude" or "Anthropic".
- CSS exists and defines `.cw-body`, `.cw-header`, `.cw-hero`, `.cw-footer`.
- JS exists and mentions every behavior hook: `dismiss-news`, `open-contact`, `open-auth`, `open-video`, `carousel`, `faq`, `footer-search`, `cookie-accept`.
- `vercel.json` has rewrite `/product/cowork` → `/product/cowork.html` and redirect `/product/cowork.html` → `/product/cowork`.
- `sitemap.xml` includes `/product/cowork`.
- `serve_keel_site.mjs` maps `/product/cowork` → `/product/cowork.html`.
- No external `http(s)://` URLs in HTML/CSS/JS source (except `mailto:` and canonical/site URLs in meta which are allowed in HTML head).
