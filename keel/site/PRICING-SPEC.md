# KEEL Pricing page — build spec (reproduction of the Claude pricing UI/UX, rebranded KEEL)

Build a **single static page** at `keel/site/pricing.html` with its own CSS `keel/site/ui/pricing.css`
and JS `keel/site/ui/pricing.js`. Match the supplied screenshot's layout exactly, but replace every
brand occurrence with **KEEL** (Claude -> KEEL, Anthropic -> KEEL, Get Claude -> Get KEEL, etc.).
The screenshot is a LIGHT/cream design (older Claude pricing page). Do NOT copy the current live
claude.com dark theme — use the light palette below.

## Visual design (from screenshot + Claude design tokens)
- Page background: `#f5f4ed` (cream). Text primary `#1f1e1d` / `#141413`, secondary `#5e5d59`, muted `#87867f`.
- Borders: `#dedcd1` / `#e8e6dc`, 1px. Cards: `#ffffff` / `#faf9f5`, radius 12px, subtle shadow.
- Headings serif: `Georgia, "Times New Roman", serif` (Claude uses anthropicSerif; Georgia is the closest available).
- Body sans: `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`.
- Buttons: solid dark `#141413` with cream text, fully rounded pill (radius 999px), 8px 18px padding;
  outline variant transparent with 1px `#1f1e1d` border.
- Hero title "Pricing": serif, ~56px, centered, ~90px top whitespace.
- Segmented controls: pill track `#e8e6dc`, active segment white with shadow, small text 13-14px.
- "Save up to 20%" badge: small light-green/neutral chip next to Yearly.
- 4 plan cards in a row on desktop, 2 on tablet, 1 on mobile; generous gaps (~16px), max container width ~1180px.
- Comparison table: white surface, thin row separators, sticky-ish header, first column widest; YES = filled black dot
  (`.pr-mark--yes`), NO = light dash (`.pr-mark--no`), with visually-hidden text for a11y. Sticky plan header row is fine.
- FAQ section: centered serif "FAQ" title, centered segmented tabs, accordion rows with thin bottom borders and a +/chevron.
- Footer: dark `#1a1918` background, cream text, ~5 link columns, small bottom bar with language selector and legal links.

## File ownership contract
Each agent owns ONLY its file. Use exactly these class/id names so the three files interlock.

### `pricing.html` structure / classes (agent A)
```
<body class="pricing-page">
<header class="pr-header">
  <div class="pr-header-inner">
    <a class="pr-logo" href="/"> <svg class="pr-logo-mark">…</svg> <span>KEEL</span> </a>
    <nav class="pr-nav" id="prNav" aria-label="Primary">
      <div class="pr-nav-item" data-menu="about">
        <button class="pr-nav-trigger" type="button" aria-expanded="false" aria-controls="pr-mega-about">About us <svg class="pr-chevron"></svg></button>
        <div class="pr-mega" id="pr-mega-about" role="group" aria-label="About us menu">
          <div class="pr-mega-grid">
            <div class="pr-mega-col"><p class="pr-mega-title">Company</p><a class="pr-mega-link" href="/">About KEEL</a> …</div>
          </div>
        </div>
      </div>
      … same pattern for data-menu = developers, enterprise, resources …
      <a class="pr-nav-link" href="/pricing" aria-current="page">Pricing</a>
      <button class="pr-nav-link pr-link-btn" type="button" data-auth-open>Login</button>
      <a class="pr-nav-link" href="mailto:hello@keel.dev">Contact</a>
      <a class="pr-btn pr-btn-dark pr-btn-sm" href="/download">Get KEEL</a>
    </nav>
    <button class="pr-nav-toggle" type="button" aria-expanded="false" aria-controls="pr-mobile-menu" aria-label="Open menu">3 bars</button>
  </div>
  <div class="pr-mobile-menu" id="pr-mobile-menu" hidden>… all nav destinations + buttons …</div>
</header>
<main id="main">
  <section class="pr-hero">
    <div class="pr-container">
      <h1 class="pr-title">Pricing</h1>
      <p class="pr-subtitle">The right plan for every task</p>
      <div class="pr-billing" role="tablist" aria-label="Billing period">
        <button class="pr-billing-opt is-active" type="button" data-billing="monthly" role="tab" aria-selected="true">Monthly</button>
        <button class="pr-billing-opt" type="button" data-billing="yearly" role="tab" aria-selected="false">Yearly <span class="pr-badge">Save up to 20%</span></button>
      </div>
      <div class="pr-plan-tabs" role="tablist" aria-label="Plan type">
        <button class="pr-plan-tab is-active" type="button" data-plan="individual" role="tab" aria-selected="true">Individual</button>
        <button class="pr-plan-tab" type="button" data-plan="team" role="tab" aria-selected="false">Team</button>
      </div>
    </div>
  </section>
  <section class="pr-plans"><div class="pr-container">
    <div class="pr-cards" id="prCards">
      4 × <article class="pr-card" data-plan-set="individual" data-price-monthly="…" data-price-yearly="…">
        <div class="pr-card-icon">svg</div>
        <h2 class="pr-card-name">Free|Pro|Max|Ultra</h2>
        <p class="pr-card-tagline">…</p>
        <p class="pr-card-price"><span class="pr-amount">$0</span><span class="pr-period">…</span></p>
        <button class="pr-btn pr-btn-dark pr-card-cta" type="button" data-auth-open>Try KEEL</button>
        <p class="pr-card-includes">Everything in Free, plus:</p>   (omit on Free)
        <ul class="pr-card-features"><li>feature</li>…</ul>
      </article>
    </div>
    <p class="pr-disclaimer">*Usage limits apply. …</p>
  </div></section>
  <section class="pr-compare" id="compare"><div class="pr-container">
    <div class="pr-compare-head"><span class="pr-compare-icon">svg cursor</span><h2>Compare features across plans</h2></div>
    <div class="pr-compare-toolbar">
      <label class="pr-search"><svg/><input type="search" id="prSearch" placeholder="Search" aria-label="Search features" /></label>
    </div>
    <div class="pr-table-wrap"><table class="pr-table">
      <thead><tr><th>Features</th><th>Free</th><th>Pro</th><th>Max</th><th>Ultra</th></tr></thead>
      <tbody id="prTableBody">
        <tr class="pr-group-row"><th colspan="5">Features and capabilities</th></tr>
        <tr data-feature="Chat on web, iOS, Android and Desktop"><td>Chat on web, iOS, Android and Desktop</td><td><span class="pr-mark pr-mark--yes"><span class="sr-only">Yes</span></span></td>…</tr>
        … all rows from the content list below …
      </tbody>
    </table></div>
    <p class="pr-compare-empty" id="prEmpty" hidden>No features match your search.</p>
  </div></section>
  <section class="pr-faq" id="faq"><div class="pr-container">
    <h2 class="pr-faq-title">FAQ</h2>
    <div class="pr-faq-tabs" role="tablist" aria-label="FAQ topics">
      <button class="pr-faq-tab is-active" type="button" data-faqtab="plans" role="tab" aria-selected="true">Plans and usage</button>
      <button class="pr-faq-tab" type="button" data-faqtab="billing" role="tab" aria-selected="false">Billing and payments</button>
      <button class="pr-faq-tab" type="button" data-faqtab="manage" role="tab" aria-selected="false">Managing your plan</button>
    </div>
    <div class="pr-faq-list" id="prFaqList">
      <div class="pr-faq-item" data-faqgroup="plans"><button class="pr-faq-q" type="button" aria-expanded="false">Question <span class="pr-faq-indicator"></span></button><div class="pr-faq-a" hidden><p>Answer</p></div></div>
      … 4-6 items per group …
    </div>
  </div></section>
</main>
<footer class="pr-footer">… brand column + 5 link columns using internal routes … bottom bar …</footer>
<div class="pr-modal" id="prModal" hidden role="dialog" aria-modal="true" aria-labelledby="prModalTitle">
  <div class="pr-modal-card">
    <button class="pr-modal-close" type="button" aria-label="Close">×</button>
    <h2 id="prModalTitle">Get started with KEEL</h2>
    <p>Choose how you'd like to continue.</p>
    <form id="prModalForm">
      <label for="prEmail">Work email</label>
      <input id="prEmail" name="email" type="email" required placeholder="you@company.com" />
      <button class="pr-btn pr-btn-dark" type="submit">Continue</button>
      <p class="pr-form-msg" id="prFormMsg" role="status" hidden></p>
    </form>
    <div class="pr-modal-links"><a href="/download">Download KEEL</a><a href="/login">Sign in to KEEL</a><a href="mailto:hello@keel.dev">Contact sales</a></div>
  </div>
</div>
<script src="/ui/pricing.js" defer></script>
</body>
```

### `pricing.css` (agent B)
Style every class above. Include responsive breakpoints: >=1080px 4 cards, 700-1079px 2 cards, <700px 1 card and
collapsing nav into `.pr-nav-toggle` controlled `.pr-mobile-menu`. Table horizontally scrollable via `.pr-table-wrap`.
Dark footer. Add `.sr-only`. Add focus-visible outlines, transitions, reduced-motion support.
Do not rely on external fonts/CDNs. Do not use `!important` except where necessary.

### `pricing.js` (agent C)
Vanilla JS, IIFE, no libraries. Implement:
1. Billing toggle `.pr-billing-opt`: toggles `is-active`/`aria-selected`, updates `.pr-amount` and `.pr-period`
   inside each `.pr-card` from its `data-price-monthly` / `data-price-yearly` attributes (format `price|period`).
2. Plan tabs `.pr-plan-tab`: toggles active state; individual shows 4 individual cards, team shows 2 team cards
   (Team $25/seat/month, Enterprise "Custom") — include both sets in HTML with `data-plan-set`.
3. Nav dropdowns: `.pr-nav-trigger` toggles `aria-expanded` and shows its `.pr-mega`; only one open at a time;
   close on outside click and Escape.
4. `.pr-nav-toggle` toggles `hidden` on `#pr-mobile-menu` and `aria-expanded`.
5. FAQ tabs `.pr-faq-tab`: show only `.pr-faq-item[data-faqgroup="…"]`.
6. FAQ accordion `.pr-faq-q`: toggle `aria-expanded`, hide/show sibling `.pr-faq-a`; allow multiple open.
7. Table search `#prSearch`: filter `<tr data-feature>` by case-insensitive substring; hide non-matching rows;
   hide `.pr-group-row` when no visible rows follow it; toggle `#prEmpty`.
8. Modal: every `[data-auth-open]` opens `#prModal`; close via `.pr-modal-close`, backdrop click, Escape;
   `#prModalForm` validates email, then replaces form with success message "Thanks — we'll be in touch." and
   keeps functional links. Focus management: focus first field on open, restore focus on close.
9. No console errors; guard every query so missing elements don't throw.

## Exact content (rebranded to KEEL)

### Cards (Individual)
- **Free** — "The essentials to get started" — $0 — CTA "Try KEEL" — features:
  Limited access to KEEL Sonnet; Help write, brainstorm, and rewrite; Summarize text and documents;
  Analyze data and visual assets; Create artifacts and code; Able to use tools and integrations; Limited usage every 5 hours and every week.
- **Pro** — "For everyday work" — $17 /month with annual subscription ($20 billed monthly) — CTA "Try KEEL" —
  "Everything in Free, plus:" More usage than Free every 5 hours and every week; Hand off and schedule tasks;
  KEEL Code; Projects; More KEEL models; KEEL in Chrome and Microsoft 365; Claude Science -> KEEL Science.
- **Max** — "For all-day work" — $100 /month — CTA "Try KEEL" — "Everything in Pro, plus:"
  5x Pro usage every 5 hours and every week; Fable included, up to half your weekly limit;
  $100 a month in API credits to build on the KEEL Platform; Early access to advanced KEEL features;
  Priority access at high traffic times.
- **Ultra** — "For your longest tasks" — $200 /month — CTA "Try KEEL" — "Everything in Max, plus:"
  No 5-hour limit; 10x Pro usage every week; $200 a month in API credits, up from $100 on Max;
  Early access to experimental features; Priority support.
- Disclaimer: "*Usage limits apply. How fast you reach a limit depends on the model you use, how long your chats are, and how large your files are. Prices shown don't include applicable tax. Price and plans are subject to change."

### Comparison rows (use these verbatim, rebranded)
Features and capabilities:
Chat on web, iOS, Android and Desktop (all Yes); Hand off and schedule tasks (Free No, rest Yes);
Create Artifacts (all Yes); KEEL Data (Free No, rest Yes); KEEL Design (all Yes); KEEL Docs (all Yes);
KEEL Motion (beta) (all No); NEW KEEL Sheets (beta) (Free No, rest Yes); KEEL Slides (all Yes);
NEW KEEL Whiteboards (beta) (Free No, rest Yes); KEEL Code (Free No, rest Yes);
KEEL for Microsoft 365 (Free No, rest Yes); KEEL for Microsoft Outlook (Free No, rest Yes);
KEEL in Chrome (Free No, rest Yes); KEEL Science (Free No, rest Yes); KEEL Tag (all No);
Connectors (all Yes); Create and edit files with code execution (all Yes); Desktop extensions (all Yes);
Enterprise search (all No); Incognito chats (all Yes); Memory (all Yes);
Project sharing and collaboration (all No); Projects (Free "Up to 5", rest "Yes"); Research (Free No, rest Yes);
Skills (all Yes); User preferences (all Yes); Voice mode (all Yes); Web search (all Yes).
Models and usage:
Limit every 5 hours (Limited / 1x / 5x / No 5-hour limit); Limit every week (Limited / 1x / 5x / 10x);
Fable (No / Usage credits / 50% of weekly limits / 50% of weekly limits); Opus (No/Yes/Yes/Yes);
Sonnet (Yes x4); Haiku (Yes x4); Context window (Up to 1M, varies by model for all);
Usage credits (No/Yes/Yes/Yes); NEW Monthly API credits (No/No/$100/month/$200/month);
Priority access at high traffic times (No/No/Yes/Yes); Organizational level spend controls (all No);
Model training (Opt-out x4).
Security and administration:
Single sign-on (SSO) and domain capture; Central billing and administration; Admin controls for remote and local connectors;
Enterprise deployment for the KEEL desktop app; Role-based access; System for Cross-domain Identity Management (SCIM);
Audit logs; Usage analytics; Compliance API; HIPAA-ready offering; Custom data retention controls;
Organization wide skills deployment — all No.
Payment options:
Credit card (n/a/Yes/Yes/Yes); ACH (all No); Invoicing / net terms (all No);
Billing cycle (n/a / Monthly and annual / Monthly / Monthly); Adding seats midterm (n/a x4).

### FAQ (exact answers, rebranded)
Plans and usage:
1. "What do I get with KEEL Pro?" — The Pro plan gives you everything in a Free plan with more usage and more of KEEL's capabilities. That includes KEEL Code, along with projects to organize your chats and documents, access to more KEEL models, and KEEL for Microsoft 365. You can choose a monthly or annual subscription.
2. "How are Max and Ultra different from Pro?" — Max and Ultra are built for people who work with KEEL throughout the day and want longer, uninterrupted sessions. You get everything in Pro, plus more usage. Max gives you 5x the usage of Pro, every 5 hours and every week. Ultra gives you 10x the weekly usage of Pro, with no 5-hour limit for verified accounts. Both plans include Fable, our top model, for up to half your weekly limit, and a monthly API credit to build on the KEEL Platform: $100 on Max, $200 on Ultra. Both plans are billed monthly.
3. "What are the usage limits on each plan, and what happens when I hit them?" — Every plan has usage limits. Most accounts have a limit that resets on a rolling five-hour session window, and paid plans add weekly limits on top. Your activity across KEEL on web, desktop, mobile, and KEEL Code all draws from the same pool… (use full live answer).
4. "Is KEEL Code included in my plan?" — KEEL Code is included in all paid plans. It shares the same usage limits as the rest of your plan…
5. "How much does the KEEL Enterprise plan cost?" — ... $20 per seat per month plus usage billed at API rates... (use full live answer, rebranded).
Billing and payments: 3-4 relevant Q&A (billing cycles, annual discount, refunds, payment methods, taxes).
Managing your plan: 3-4 relevant Q&A (change plans, cancel, usage credits, team seats).

### Footer columns (all links must have real internal destinations)
Products (KEEL, KEEL Code, KEEL Cowork, KEEL Duet, KEEL Tag, KEEL Science, KEEL Security, Download app, Pricing, Log in);
Capabilities (Artifacts, Design, Connectors, Plugins, Skills); Extensions (KEEL in Chrome, KEEL for Google Workspace, KEEL for Microsoft 365);
Models (Mythos (including Fable), Opus, Sonnet, Haiku); Enterprise (Overview, KEEL Code for Enterprise, Departments, Industries);
Resources (Overview, Articles, Webinars, KEEL Academy, Customer stories, Events, Help and security);
Company (KEEL, Careers, Policy, Research, News); Terms and policies (Privacy policy, Terms of service, Usage Policy).
Bottom bar: "© 2026 KEEL", language select (English), Privacy policy, Terms of service, Accessibility.

Valid internal routes: `/`, `/pricing`, `/download`, `/app`, `/product/overview`, `/product/keel-duet`,
`/product/keel-code`, `/keel-in-chrome`, `/chrome-web-store`, `/roadmap`, `/requirements`, `/privacy`,
`/eula`, `/trademark`, `/notices`, `/screenshots`. Use `mailto:hello@keel.dev` for contact items.
Never use `href="#"` unless it targets a real element id on this page.
