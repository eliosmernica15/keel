# KEEL DUET PAGE — SHARED BUILD CONTRACT

All subagents MUST read this file first and follow it exactly. This is the single
source of truth for file ownership, class names, copy text and interactions.

## Goal
Replicate the provided screenshot of the "Claude Duet" waitlist marketing page
**exactly in forms, layout, spacing, typography and interaction** at:

    https://keel-desktop.vercel.app/product/keel-duet

Brand is **KEEL / Keel** everywhere (Claude -> Keel, Anthropic -> Keel).
Keep model names Opus 4.5, Sonnet 4.5, Haiku 4.5. All buttons must be functional.

## File ownership (NEVER edit a file you do not own)
- Agent A (HTML): `keel/site/product/keel-duet.html` ONLY (new folder).
- Agent B (CSS):  `keel/site/ui/keel-duet.css` ONLY (new file).
- Agent C (JS):   `keel/site/ui/keel-duet.js` ONLY (new file).
- Agent D (config): `keel/site/vercel.json`, `keel/site/sitemap.xml`,
  `keel/site/product/README.md` ONLY.
Lead agent owns everything else (index.html, download.html, tests, docs, deploy).

## Shared conventions
- `<body class="landing duet-page">` — reuse `/ui/landing.css` for base tokens,
  header, mega menus, buttons and footer so the page matches the existing Keel
  marketing system. Then load `/ui/keel-duet.css` for page-specific overrides.
- Scripts: load `/ui/landing.js` first (mega menus, auth modal helpers) then
  `/ui/keel-duet.js`. Guard ALL JS so it only runs when `document.body.classList.contains('duet-page')`.
- All page-specific classes are prefixed `d-`. Never redefine `l-*` classes
  in keel-duet.css except tiny layout overrides scoped to `body.duet-page`.
- No external network calls. No `href="#"`. Use real routes:
  `/`, `/download`, `/app`, `/privacy`, `/terms`, `/notices`, `/roadmap`,
  `/eula`, `/trademark`, `/requirements`, `/product/keel-duet`, `mailto:`.
- Use inline SVG for icons/logos (CSP forbids remote images). Text-based logos
  are acceptable for stripe / 1Password / Shopify / Gmail.
- Warm page background `#f5f4ef`, ink `#191918`, serif display
  `Georgia, 'Times New Roman', serif`, sans body system stack.
- Responsive: desktop 2-col hero + 3-col features, tablet stacks, mobile
  hamburger menu that actually opens, form fields full width.

## EXACT DOM CONTRACT (ids/classes must match across HTML/CSS/JS)

Header (copy markup from `keel/site/index.html` header, then adjust nav):
- `.d-header` is the existing `.l-header`. Nav links in order:
  Product, Developers, Enterprise, Resources, Pricing, Login, Contact,
  then black pill button `.d-changelog` labeled `Changelog`.
- Keep all five mega dropdowns from index.html (hover/click/keyboard).
- "Keel Duet" mega link must point to `/product/keel-duet`.

Breadcrumb:
`<nav class="d-crumbs l-container" aria-label="Breadcrumb">Product / Duet for Keel</nav>`

Hero:
```
<section class="d-hero">
  <div class="l-container d-hero-grid">
    <div class="d-hero-copy">
      <span class="d-doodle" aria-hidden="true"><svg>...</svg></span>
      <p class="d-eyebrow">INTRODUCING.</p>
      <h1 class="d-title"><span class="d-title-sm">Keel Duet</span><br><span class="d-title-lg">Get back to what<br>needs you</span></h1>
      <p class="d-lede">Keel Duet is a proactive agent that understands what needs your attention. It takes on tasks of all sizes, keeps working while you're away, and waits for your ok when it matters.</p>
      <p class="d-powered">Powered by <a href="#faq">Opus 4.5</a>, <a href="#faq">Sonnet 4.5</a>, and <a href="#faq">Haiku 4.5</a>, with <a href="/download">Keel in Chrome</a>.</p>
    </div>
    <div class="d-signup-wrap">
      <form class="d-form" id="duet-waitlist" novalidate>
        <h2 class="d-card-title">Join the waitlist</h2>
        <div class="d-row2">
          <div class="d-field"><label class="d-label" for="d-first">First name*</label><input class="d-input" id="d-first" name="first" required placeholder="Enter your first name"></div>
          <div class="d-field"><label class="d-label" for="d-last">Last name*</label><input class="d-input" id="d-last" name="last" required placeholder="Enter your last name"></div>
        </div>
        <div class="d-field"><label class="d-label" for="d-email">Email address*</label><input class="d-input" id="d-email" name="email" type="email" required placeholder="If you already use Keel, enter your account email."></div>
        <div class="d-field"><label class="d-label" for="d-company">Company name*</label><input class="d-input" id="d-company" name="company" required placeholder="Company name"></div>
        <fieldset class="d-field d-seg-field"><legend class="d-label">Do you use Keel?</legend><div class="d-segment" role="radiogroup"><button type="button" class="d-seg-btn is-active" data-group="use" data-value="Personal" role="radio" aria-checked="true">Personal</button><button type="button" class="d-seg-btn" data-group="use" data-value="At work" role="radio" aria-checked="false">At work</button></div></fieldset>
        <fieldset class="d-field d-seg-field"><legend class="d-label">Phone*</legend><div class="d-segment" role="radiogroup"><button type="button" class="d-seg-btn is-active" data-group="device" data-value="Phone" role="radio" aria-checked="true">Phone</button><button type="button" class="d-seg-btn" data-group="device" data-value="Android" role="radio" aria-checked="false">Android</button></div></fieldset>
        <div class="d-field"><label class="d-label" for="d-role">What do you do, and what would you hand off to Keel Duet?</label><textarea class="d-textarea" id="d-role" name="role" rows="3" placeholder="I run a small design studio and want help staying on top of client emails..."></textarea></div>
        <label class="d-check"><input type="checkbox" id="d-consent" name="consent"><span>I'm okay with Keel using relevant details from our conversations to help with tasks in other apps</span></label>
        <button type="submit" class="l-btn l-btn-dark d-submit">Join the waitlist</button>
        <p class="d-form-error" id="d-form-error" role="alert" hidden></p>
        <p class="d-form-success" id="d-form-success" role="status" hidden>Thanks — you're on the list. We'll be in touch soon.</p>
      </form>
    </div>
  </div>
</section>
```

Logos strip:
```
<section class="d-logos"><div class="l-container">
  <p class="d-logos-title">Works with more than 6,000 connectors and plugins</p>
  <div class="d-logo-strip"><span class="d-logo d-logo-stripe">stripe</span> ... 1Password, shopify, Gmail 'M' ...</div>
</div></section>
```

Features:
```
<section class="d-features" id="features"><div class="l-container d-feature-grid">
  <div class="d-feature-col">
    <h2 class="d-section-title">Built for judgment</h2>
    <div class="d-squiggle" aria-hidden="true"></div>
    <article class="d-feature"><span class="d-feature-icon">...</span><h3>Knows what needs you</h3><p>Claude Duet looks for pending invitations, unanswered emails, and gaps that need attention. You set the boundaries, and it checks in when something needs your input.</p></article>
    ... "Takes on large tasks", "The Keel you already use" ...
  </div>
  <div class="d-phone" aria-label="Keel Duet phone preview">
    <div class="d-phone-notch"></div>
    <div class="d-phone-date">Monday, October 13</div>
    <div class="d-phone-time">9:41</div>
    <div class="d-phone-notif"><span class="d-notif-icon">...starburst...</span><div><strong>Keel Duet</strong><span>5 Steps in progress and 2 waiting for you</span><button type="button" class="d-notif-btn">Start now,</button></div></div>
    <div class="d-phone-typing"><i></i><i></i><i></i></div>
    <div class="d-phone-bar"></div>
  </div>
  <div class="d-feature-col">
    <h2 class="d-section-title">Safe, secure, private</h2>
    <div class="d-squiggle" aria-hidden="true"></div>
    ... "You approve", "Safety built in", "You see what it's doing" ...
  </div>
</div></section>
```
Phone background is a soft lilac-to-peach vertical gradient.

FAQ (white background section `#fff`):
```
<section class="d-faq" id="faq"><div class="l-container">
  <div class="d-faq-mark" aria-hidden="true">?</div>
  <h2 class="d-faq-title">FAQ</h2>
  <div class="d-accordion">
    <div class="d-acc-item is-open"><button class="d-acc-btn" type="button" aria-expanded="true"><span class="d-acc-q">What is Keel Duet?</span><span class="d-acc-icon"></span></button><div class="d-acc-panel"><p>Keel Duet is a helpful, proactive agent you chat with on the Keel app. Tell it what you need to work on and it works on its own computer in the cloud, using apps and tools you connect. ...</p></div></div>
    ... 8 more items, all collapsed ...
  </div>
</div></section>
```
Exact question list in order:
1. What is Keel Duet?
2. How does Keel Duet work?
3. How is Keel Duet different from Keel?
4. What can Keel Duet do?
5. How much does Keel Duet cost?
6. When can I use Keel Duet?
7. Where can I use Keel Duet?
8. What if I need to stop it?
9. Is Keel Duet safe?

CTA (dark `#1a1a1a`):
```
<section class="d-cta"><div class="l-container">
  <h2 class="d-cta-title">Help us shape it</h2>
  <div class="d-cta-buttons">
    <button type="button" class="l-btn d-cta-join">Join the waitlist</button>
    <button type="button" class="l-btn d-cta-outline">Read the announcement</button>
  </div>
</div></section>
```

Footer: copy the full footer from `keel/site/index.html` verbatim, changing any
remaining "Claude" to "Keel" and "Anthropic" to "Keel". Keep the help search
input with id `d-footer-search` and orange arrow submit. Ensure the "Latest news"
dismissible chip exists with class `.d-news-chip` and close `.d-news-close`.

Chat widget:
```
<aside class="d-chat" id="duet-chat" aria-label="Keel Duet chat">
  <button class="d-chat-close" type="button" aria-label="Close chat">×</button>
  <div class="d-chat-head"><span class="d-chat-avatar">...mascot svg...</span><div><strong>Meet Keel Duet</strong><small>Your proactive agent</small></div></div>
  <p class="d-chat-msg">Tell me what you need</p>
  <div class="d-chat-actions"><button class="d-chat-btn" type="button" data-chat="start">Start chat</button><button class="d-chat-btn d-chat-btn-ghost" type="button" data-chat="next">Next steps</button></div>
</aside>
<button class="d-chat-fab" id="duet-chat-fab" type="button" aria-label="Open chat">💬</button>
```

## EXACT JS REQUIREMENTS (Agent C)
1. Waitlist form submit: validate first, last, email (regex), company required;
   segmented choices required (default Personal/Phone counts); consent optional.
   On success: persist to `localStorage['keel_duet_waitlist']` (JSON array),
   hide form, show `#d-form-success`, dispatch toast. On error: show
   `#d-form-error` with inline message, focus first invalid field.
2. Segmented buttons: click toggles `.is-active` and `aria-checked` within group.
3. Accordion: click toggles `.is-open`, `aria-expanded`, panel max-height; only
   one open at a time; Escape closes.
4. Both "Join the waitlist" buttons (form + dark CTA) must work. CTA scrolls to
   form and focuses `#d-first` (or opens modal if form is already submitted).
   "Read the announcement" opens a modal with real copy and a Close button.
5. Changelog button opens a modal with real "What's new" copy.
6. Chat widget: FAB opens/closes; Start chat opens a functional chat modal with
   message input and scripted Keel replies; Next steps opens a small modal with
   numbered steps. Close buttons work. Escape closes modals.
7. Footer search: filters FAQ questions live and shows "No results" state;
   arrow submit scrolls to FAQ.
8. News chip dismiss removes chip and stores flag in localStorage.
9. Mega menus from landing.js must keep working; do not break them.
10. Mobile hamburger toggles nav; Escape closes.
11. Toast helper `dToast(msg)` creates `.d-toast` appended to body, auto-remove
    after 3.5s.
12. No console errors; all JS wrapped in IIFE and feature-detected.

## EXACT CONFIG REQUIREMENTS (Agent D)
- `vercel.json`: add rewrite `{ "source": "/product/keel-duet", "destination": "/product/keel-duet.html" }`
  and redirect `/product/keel-duet.html` -> `/product/keel-duet` (permanent false).
  Keep all existing headers/rewrites/redirects intact.
- `sitemap.xml`: add `<url><loc>https://keel-desktop.vercel.app/product/keel-duet</loc><lastmod>2026-11-24</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>`.
- `product/README.md`: short doc describing the page, route and ownership.

## DEFINITION OF DONE
- `node --check keel/site/ui/keel-duet.js` passes.
- Opening `/product/keel-duet` locally via a static server renders the whole
  screenshot with no missing assets and no console errors.
- Every button does something real (modal, toast, scroll, navigation, form).
- No dead `href="#"`.
