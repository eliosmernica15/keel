# KEEL Product Overview — parallel build contract

Target: reproduce the operator's screenshot of the Claude **product overview** page at
`https://keel-desktop.vercel.app/product/overview`, with every occurrence of "Claude"
replaced by **Keel** (and "Anthropic" -> "Keel"). Section order, editorial serif
typography, warm off-white background, black pill buttons, thin grey rules and dark
footer must match the screenshot. Every control must be functional.

Site root: `C:\Users\Admin\Desktop\Claude clone\keel\site`

## Ownership (do not edit files assigned to another agent)

| Agent | Owns (exclusive) |
|---|---|
| HTML | `product-overview.html` |
| CSS | `ui/product-overview.css` |
| JS | `ui/product-overview.js` |
| Assets/routing | `assets/img/po-*.svg`, `vercel.json`, `sitemap.xml`, nav/footer links inside `index.html`, `download.html`, `app.html`, `chrome-web-store.html`, `keel-in-chrome.html`, `README.md` |
| Operator | `verify_product_overview.py`, git operations, Vercel deployment |

All paths below are relative to the site root.

## Markup contract (HTML agent produces, CSS/JS agents consume)

Root: `<html lang="en">`, `<body class="po-body">`. Load
`/ui/product-overview.css` in head and `/ui/product-overview.js` with `defer`.
Title: `Keel — Product overview`. Meta description about putting Keel to work.

### Header
```
<header class="po-site-header" id="po-header">
  <a class="po-brand" href="/" aria-label="Keel home">
    <img class="po-brand-mark" src="/assets/img/po-mark.svg" alt="" /> <span>Keel</span>
  </a>
  <nav class="po-main-nav" aria-label="Primary">
    <div class="po-nav-item" data-nav="product">
      <button class="po-nav-trigger" aria-expanded="false" aria-controls="po-menu-product">Product <span class="po-chevron"></span></button>
      <div class="po-mega" id="po-menu-product" hidden>
        <div class="po-mega-grid">
          <div class="po-mega-col"><p class="po-mega-heading">Products</p> ... <a class="po-mega-link" href="...">...</a></div>
          ... Capabilities / Extensions / Models columns ...
        </div>
        <div class="po-mega-footer"><a href="/product-overview">Import to Keel</a> ... <a href="/download">Download apps ↓</a> <a href="/app">Login ↗</a></div>
      </div>
    </div>
    <!-- also data-nav="developers", "enterprise", "resources" -->
    <a class="po-nav-link" href="/#pricing">Pricing</a>
  </nav>
  <div class="po-header-actions">
    <a class="po-btn po-btn-ghost" href="/app">Log in</a>
    <button class="po-btn po-btn-dark po-auth-open" type="button">Get Keel</button>
    <button class="po-hamburger" type="button" aria-label="Open menu" aria-expanded="false"><span></span><span></span><span></span></button>
  </div>
  <div class="po-mobile-menu" id="po-mobile-menu" hidden> ... duplicate primary links ... </div>
</header>
```
Mega menu link groups (exact labels, Keel-branded):
- Product: Products (Keel, Keel Code, Keel Cowork, Keel Duet, Keel Platform, Keel Tag; Specialized: Keel Security, Keel Science), Capabilities (Artifacts, Design, Connectors, Plugins, Skills), Extensions (Keel in Chrome, Keel for Google Workspace, Keel for Microsoft 365), Models (Mythos (including Fable), Opus, Sonnet, Haiku).
- Developers: Build with (Keel Code, Keel Platform, Keel Ship, Code Review, Managed Agents), For developers (Keel Academy, Community, Developer blog).
- Enterprise: Enterprise (Overview, Keel Code for Enterprise, Keel Platform, Keel Ship), Use Cases (AI Agents, Coding, Commerce; Departments: Customer support, Cybersecurity, Legal, Sales), Industries (Financial advisors, Financial services, Government, Healthcare, Higher education, K-12 teachers, Life sciences, Manufacturing, Nonprofits). Footer: Browse marketplace / Customers / Contact sales.
- Resources: Insights (Resources, Articles, Webinars, Customer stories, Marketplace, Keel news), Learn (Keel Academy, Courses, Tutorials, Use cases), Connect (Events, Community). Pricing panel: Overview, API.
Every href must be a real site route/anchor (`/`, `/download`, `/app`, `/product-overview`, `/#pricing`, `/privacy`, `/terms`, `/notices`, `/roadmap`, `/eula`, `/trademark`, `/requirements`, `/keel-in-chrome`, `/chrome-web-store`, `mailto:hello@keel.dev`) or a same-page `#id`. No `href="#"`.

### Hero
```
<section class="po-hero" id="top">
  <div class="po-hero-collage" aria-hidden="true">
    <img class="po-collage po-collage-a" src="/assets/img/po-portrait-a.svg" alt="" />
    <img class="po-collage po-collage-b" src="/assets/img/po-portrait-b.svg" alt="" />
    <img class="po-collage po-collage-c" src="/assets/img/po-portrait-c.svg" alt="" />
  </div>
  <div class="po-hero-inner">
    <h1 class="po-hero-title">Give Keel more</h1>
    <p class="po-hero-subtitle">Turn your thinking into code, documents and more.</p>
    <div class="po-hero-actions"> Get Keel (po-auth-open), See plans (/ #pricing) </div>
    <a class="po-download-link" href="/download">Download desktop app</a>
  </div>
  <div class="po-hero-card" aria-hidden="true"> ... "Research" label + sample Keel answer + /assets/img/po-app-icons.svg ... </div>
</section>
```

### Value grid
`<section class="po-value-grid">` with 3 `.po-value-item` each `.po-value-kicker` (01/02/03), `.po-value-title`, `.po-value-body`:
- "Take tasks off your desk", "Turn ideas into something real", "Extend what you can do" (copy from live reference).

### Put Keel to work
```
<section class="po-work" id="work">
  <h2 class="po-section-title">Put Keel to work</h2>
  <p class="po-section-sub">Hand off tasks on the go or on a schedule, steer from anywhere, and edit anything before it goes out.</p>
  <div class="po-persona-tabs" role="tablist">
    <button class="po-persona-tab is-active" data-persona="everyone" role="tab" aria-selected="true">Everyone</button>
    ... marketing, sales, finance, human-resources, legal, product ...
  </div>
  <div class="po-work-showcase">
    <div class="po-showcase-copy"><p class="po-showcase-time">8:00 AM · Product</p><h3 class="po-showcase-title">Keep up with meetings all day</h3><p class="po-showcase-desc">...</p></div>
    <div class="po-showcase-visual">
      <div class="po-chat-card"><p class="po-chat-prompt">...</p><div class="po-chat-steps">... .po-chat-step items ...</div><span class="po-chat-model">Opus High</span></div>
      <div class="po-output-card"><span class="po-output-label">The result</span> ... </div>
      <img class="po-app-strip" src="/assets/img/po-app-icons.svg" alt="" />
    </div>
  </div>
  <div class="po-work-steps"> 6 .po-step-card with .po-step-title + .po-step-body </div>
  <div class="po-work-visual-2"> ... "Up to date and as close as your inbox" / "Upgrade your H2 copy in one bounceback check in" + .po-mini-ui mock + .po-app-strip ... </div>
  <button class="po-text-link" type="button" data-try-prompt="After each of my meetings...">Try it in Keel</button>
</section>
```
JS agent: persona tabs swap `.po-showcase-copy` text and `.po-chat-prompt` from an in-file data map (at least 3 personas with real copy). `Try it in Keel` opens auth modal with the prompt prefilled.

### Testimonial
```
<section class="po-testimonial">
  <img class="po-testimonial-media" src="/assets/img/po-laptop.svg" alt="Keel running on a laptop" />
  <blockquote class="po-testimonial-quote">...</blockquote>
  <p class="po-testimonial-author">Ian Goodman <span>CEO, Customer.io</span></p>
</section>
```
(Quote from screenshot: "I give Keel a call transcript, a couple of bullets and some context. 10 minutes later I have a strategy deck that's ready to go. It's become my go-to tool for thinking partner.")

### Change the way you work
`<section class="po-change" id="change">` title + subtitle + 3 `.po-change-col` with `.po-change-title` / `.po-change-body`:
- "Build at the speed of thought", "The system is your context layer", "Your tools now think with you".

### See what Keel can do
```
<section class="po-capabilities" id="capabilities">
  <h2 class="po-section-title">See what Keel can do</h2>
  <label class="po-cap-search"><span class="po-sr-only">Search use cases</span><input id="po-cap-search" type="search" placeholder="Search use cases" /></label>
  <div class="po-cap-tabs" role="tablist"><button class="po-cap-tab is-active" data-cap-tab="all"...>All use cases</button> ... Marketing, Design, Sales, Engineering, Product, Education, Finance, Legal, Operations, Customer Success, Human Resources, Research, Software Engineering, Security, IT, Startups, Nonprofits ...</div>
  <div class="po-hub" id="po-hub"><div class="po-hub-core"><span>Keel</span></div>
    <div class="po-hub-node" data-caps="data" data-search="analyze data"><span class="po-hub-node-title">Analyze data</span><span class="po-hub-node-desc">...</span></div>
    ... Build applications, Write and edit, Summarize text, Brainstorm ideas, Automate workflows, Learn and explain, Creative projects ...
  </div>
  <div class="po-cap-detail" id="po-cap-detail"> .po-cap-card items grouped by data-category (quick-tasks, editable-work, tools, yours, control, anywhere, memory) </div>
  <p class="po-cap-empty" id="po-cap-empty" hidden>No use cases match that search.</p>
</section>
```
JS agent: search input filters `.po-hub-node` and `.po-cap-card` by `data-search`; `po-cap-tab` filters by `data-caps`/`data-category`; show/hide `#po-cap-empty`.

### Use case demo
```
<section class="po-usecase" id="use-case">
  <h2 class="po-usecase-heading" id="po-usecase-heading">I'm in Marketing and I need to make the Company numbers.</h2>
  <div class="po-usecase-grid">
    <div class="po-usecase-side">
      <p class="po-usecase-label">Role</p>
      <div class="po-role-list"><button class="po-role is-active" data-role="Marketing">Marketing</button> ... Sales, Finance, Human resources, Legal, Product ...</div>
      <p class="po-usecase-label">Company size</p>
      <div class="po-size-list"><button class="po-size is-active" data-size="Any">Any</button> ... Startup, Mid-market, Enterprise ...</div>
    </div>
    <div class="po-usecase-stage" id="po-usecase-stage">
      <div class="po-stage-card po-stage-email"><span>Campaign-Paused</span> ... Congratulations Paul! ... </div>
      <div class="po-stage-card po-stage-metric"><strong>97%</strong><span>Campaign has ...</span></div>
      <img class="po-stage-art" src="/assets/img/po-stage.svg" alt="" />
    </div>
    <div class="po-usecase-tasks"><p class="po-usecase-label">Task</p><div class="po-task-list"> buttons .po-task data-task with labels: Campaign readout, Call prep, Earnings comps, JD check, Legal research drafting, Action tracking, Asset creation, QBR deck, Month-end close, Survey readout, Deposition prep, Feedback digest, Audience intelligence, CRM hygiene, Budget reforecast, Merit analysis, Contract redline, Metrics dashboard ... </div></div>
  </div>
</section>
```
JS agent: role/size/task selection updates `#po-usecase-heading` to "I'm in {role} and I need to make the {task}." (Title Case), toggles active classes and aria-pressed, and swaps a short stage caption. Add a "View use case" button `.po-view-usecase` that opens the auth modal with that task prefilled.

### FAQ
`.po-faq` title "FAQ", `.po-faq-list` with 6 `.po-faq-item`:
"What should I use Keel for?", "How much does it cost to use?", "Is my data secure with Keel?", "Can Keel integrate with my existing tools?", "Is there an API for Keel?", "How do I get started?"
Each: `<button class="po-faq-q" aria-expanded="false" aria-controls="faq-a-N">Question <span class="po-faq-icon" aria-hidden="true"></span></button><div class="po-faq-a" id="faq-a-N" hidden><p>answer</p></div>`.
JS agent handles accordion (only one open at a time, icon becomes minus, aria updated).

### CTA
`<section class="po-cta" id="get-keel"><h2>Don't know where to start? Ask Keel.</h2><p>Keel works with you to tackle your most complex challenges.</p><form class="po-ask-form" id="po-ask-form"><input id="po-ask-input" type="text" placeholder="Ask a question..." required /><button class="po-btn po-btn-coral" type="submit">Ask Keel</button></form><div class="po-cta-actions">Get Keel / See plans</div></section>`
JS agent: submit shows an inline "thinking" then a canned helpful answer in `#po-ask-result` (aria-live), no network call; prefilled prompts from Try it in Keel / View use case also land here.

### Footer
```
<footer class="po-footer" id="po-footer">
  <div class="po-footer-top">
    <a class="po-brand po-footer-brand" href="/">... Keel ...</a><span class="po-news-chip">Latest news <button class="po-news-dismiss" aria-label="Dismiss">×</button></span>
    <form class="po-footer-search" id="po-footer-search-form"><label class="po-sr-only" for="po-footer-search">Search help</label><input id="po-footer-search" type="search" placeholder="How can we help today?" /><button type="submit" class="po-footer-search-btn" aria-label="Search">→</button></form>
  </div>
  <div class="po-footer-grid"> .po-footer-col with .po-footer-heading + <a class="po-footer-link"> links </div>
  <p class="po-footer-search-result" id="po-footer-search-result" aria-live="polite" hidden></p>
  <div class="po-footer-bottom"><span>KEEL 2026 All rights reserved.</span> social links <a>Add to Preferred Sources</a> <button class="po-lang">English</button> ... </div>
</footer>
```
Footer columns: Products (Keel, Keel Code, Keel Cowork, Keel Duet, Keel Tag, Keel Science, Keel Security, Keel Ship, Code Review), Capabilities, Extensions, Models, Enterprise, Departments, Industries, Programs, Developers, Platform, Resources, Help and security, Company, Terms and policies. All Keel-branded. JS agent: footer search filters `.po-footer-link` text and reveals a result count in `#po-footer-search-result`.

### Overlays
`<div class="po-modal" id="po-auth-modal" hidden>` with `.po-modal-backdrop`, `.po-modal-dialog`, `.po-modal-close`, `<button class="po-google-btn">Continue with Google</button>`, divider "or", `<form id="po-auth-form"><input id="po-auth-email" type="email" required><button type="submit">Continue with email</button></form>`, fine print with Privacy Policy / Terms links, and a small "Demo sign-in — no real account is created." note.
`<div class="po-toast" id="po-toast" role="status" aria-live="polite" hidden></div>`.
JS agent: `.po-auth-open` opens modal, Escape/backdrop/close dismiss it, focus restored, email validated (native + regex), on submit sets `localStorage.setItem('keel_logged_in','1')` and navigates to `/app` (or shows success toast if a `data-no-redirect` flag is present). Google button performs the same demo sign-in with a clear toast. No external network calls.

## Visual contract (CSS agent)
- Warm off-white background `#f7f6f2`-ish; ink `#1b1b1b`; thin borders `#dedcd6`; muted text `#6b6a66`; coral/orange accent `#d97757`.
- Serif display font for all section titles (`Georgia, 'Times New Roman', serif`), sans-serif for body (`Inter, system-ui, sans-serif`) using existing `/ui/fonts/inter-400.woff2` via `@font-face` if convenient.
- Very wide centred container ~1200px, generous vertical rhythm (sections 100–160px apart).
- Pill buttons: dark `#1b1b1b` with white text, outline 1px border, hover transforms subtle.
- Mega dropdown: white panel, 16px radius, soft shadow, 4 columns, grey footer bar; hidden by default, shown by `.is-open` class (JS toggles `hidden` too).
- Hub diagram: absolute-positioned nodes around a central circular "Keel" core, thin connector lines, responsive fallback to stacked grid under 900px.
- Dark footer `#191919`, muted `#a3a3a3` headings, coral search button.
- Responsive breakpoints 1100px / 900px / 640px; hamburger menu visible <=900px.
- `prefers-reduced-motion` honoured; focus-visible rings; `.po-sr-only` utility.

## Functional contract (JS agent)
- Mega dropdowns: hover (desktop), click toggle, keyboard (Enter/Space, Escape closes and returns focus, ArrowDown into first link), `aria-expanded` and `hidden` kept in sync.
- Hamburger menu toggles `#po-mobile-menu`.
- Persona tabs, capability tabs/search, role/size/task selectors, FAQ accordion, ask form, footer search, auth modal, toast, news chip dismiss — all working with no console errors.
- Guard every query with null checks so the script cannot throw if markup differs slightly.
- `node --check ui/product-overview.js` must pass.

## Assets/routing agent details
Create simple, tasteful SVG assets (no external URLs, no text that says "Claude"):
`po-mark.svg` (Keel starburst), `po-portrait-a.svg`, `po-portrait-b.svg`, `po-portrait-c.svg` (abstract portrait avatars), `po-app-icons.svg` (row of app glyphs), `po-laptop.svg` (laptop with Keel chat UI), `po-stage.svg` (abstract campaign dashboard art). Keep them small (<15KB each).
Add rewrite `{ "source": "/product/overview", "destination": "/product-overview.html" }` to `vercel.json` (preserve existing rewrites/headers). Add a `<url>` entry to `sitemap.xml`. Add a "Product overview" link to the primary nav/Product dropdown and footer of `index.html`, `download.html`, `app.html`, `chrome-web-store.html`, `keel-in-chrome.html` where such nav exists (minimal, careful edits — do not rebrand or restructure those pages).

## Definition of done
- `node --check ui/product-overview.js` passes.
- Visiting `/product/overview` renders the full page with no 404.
- Every button/link either navigates to a real route, opens a modal/toast, filters content, or is visibly disabled with a reason. No dead `href="#"`.
- Brand check: `grep -i claude keel/site/product-overview.html` returns nothing (except perhaps historical quote attribution — avoid entirely).
