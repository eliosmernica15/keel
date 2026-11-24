# KEEL CODE PAGE — SHARED BUILD CONTRACT

All subagents MUST read this file first and follow it exactly. This is the single
source of truth for file ownership, class names, copy text and interactions.

## Goal
Replicate the "Claude Code" product page **exactly in forms, layout, spacing,
typography and interaction** at:

    https://keel-desktop.vercel.app/product/keel-code

Brand is **KEEL / Keel** everywhere (Claude -> Keel, Anthropic -> Keel,
CLAUDE.md -> KEEL.md). Keep the warm editorial design system already in the
repo. **Every button, tab, link and form must be functional** — no dead ends,
no `href="#"`, no console errors.

Reference page (fetch for exact copy if needed):
`https://claude.com/product/claude-code`

## File ownership (NEVER edit a file you do not own)
- Agent A (HTML): `keel/site/product/keel-code.html` ONLY (new folder).
- Agent B (CSS):  `keel/site/ui/keel-code.css` ONLY (new file).
- Agent C (JS):   `keel/site/ui/keel-code.js` ONLY (new file).
- Agent D (config): `keel/site/vercel.json`, `keel/site/sitemap.xml`,
  `keel/site/product/README.md` ONLY.
- Lead agent owns everything else (build contract, tests, verification, git,
  deploy).

## Shared conventions
- `<body class="landing code-page">`. Load `/ui/landing.css` THEN
  `/ui/keel-code.css`; load `/ui/landing.js` THEN `/ui/keel-code.js`.
- Reuse the existing `.l-*` marketing system from `index.html`. **Copy the
  entire header, dark footer, news chip and auth modal from
  `keel/site/index.html` verbatim**, then apply the small adjustments below.
- All page-specific classes/ids are prefixed `c-`. Never redefine `l-*`
  classes in `keel-code.css` except tiny layout overrides scoped to
  `body.code-page`.
- No external network calls and no remote images (CSP: `img-src 'self' data:
  blob:`). All logos/screenshots must be inline SVG, text, CSS-drawn mockups,
  or existing local assets under `/assets/`. Text-based logos are acceptable.
- Warm background `#f5f4ef`, ink `#191918`, serif display Georgia, sans body
  system stack, black pill buttons, thin grey borders, orange accent
  `#d97757`.
- Responsive: desktop 2-col hero + 2-col cards, tablet stacks, mobile
  hamburger (handled by `landing.js`) that actually opens.
- Every link must point to a real route/anchor/mailto:
  `/`, `/download`, `/app`, `/privacy`, `/terms`, `/notices`, `/roadmap`,
  `/eula`, `/trademark`, `/requirements`, `/product/keel-code`, `mailto:`.
  Anchors that exist on THIS page: `#faq`, `#get-started`, `#announcements`,
  `#take-on`, `#where-you-code`, `#developers`, `#technical`, `#newsletter`,
  `#footer`. Replace `#plans`/`#top` copied from index.html with `/#plans`/`/`.

## HTML adjustments to the copied header/footer/modal
- Wordmark `href="/"` (both header and footer).
- In the Product mega menu, "Keel Code" link -> `/product/keel-code`.
- In the Developers mega menu, "Keel Code" link -> `/product/keel-code`.
- Add a breadcrumb immediately inside `<main id="top">`:
  `<nav class="c-crumbs l-container" aria-label="Breadcrumb"><a href="/">Product</a><span aria-hidden="true">/</span><span aria-current="page">Keel Code</span></nav>`
- Keep all five mega dropdowns, mobile menu, help search, news chip and the
  full auth modal exactly as in index.html (landing.js wires them up).
- Footer must keep the help search (`#helpSearch`, `#helpForm`,
  `#searchStatus`) and language select (`#languageSelect`) intact.

## EXACT DOM CONTRACT (ids/classes must match across HTML/CSS/JS)

### 1. Hero
```
<section class="c-hero" id="top">
  <div class="l-container c-hero-grid">
    <div class="c-hero-copy">
      <h1 class="c-title">Keel Code</h1>
      <p class="c-lede">Hand Keel a bug fix, test, or multi-day migration. You set its permissions. Steer and review from your desktop, terminal, IDE, Slack, or the web.</p>
      <div class="c-hero-actions">
        <a class="l-btn l-btn-dark" href="/download">Download for macOS</a>
        <a class="l-btn l-btn-outline" href="/requirements">Read documentation</a>
      </div>
      <p class="c-avail">Available for macOS, Linux, and Windows.</p>
      <div class="c-ways">
        <p class="c-ways-title">Other ways to use Keel Code:</p>
        <div class="c-way-links">
          <button type="button" class="c-way" data-way="terminal">Terminal</button>
          <button type="button" class="c-way" data-way="web">Web</button>
          <button type="button" class="c-way" data-way="ios">iOS</button>
          <button type="button" class="c-way" data-way="android">Android</button>
          <button type="button" class="c-way" data-way="github">GitHub</button>
          <button type="button" class="c-way" data-way="vscode">VS Code</button>
          <button type="button" class="c-way" data-way="jetbrains">JetBrains</button>
          <button type="button" class="c-way" data-way="slack">Slack</button>
        </div>
      </div>
    </div>
    <div class="c-hero-shots" aria-label="Keel Code app previews">
      <!-- two CSS/SVG-drawn app window mockups side by side -->
      <div class="c-shot c-shot-a">...</div>
      <div class="c-shot c-shot-b">...</div>
    </div>
  </div>
</section>
```
Below the hero: a logo strip `.c-logo-strip` with the names Zapier, PagerDuty,
Workato, Notion, Asana, Rakuten, Databricks, Ramp, Plaid, Spotify, StubHub,
Uber, Brex, Intercom, Stripe, Shopify, NASA, Figma as inline text/SVG logos.

### 2. Get started
```
<section class="l-section c-get-started" id="get-started">
  <div class="l-container">
    <h2 class="l-section-title">Get started with Keel Code</h2>
    <div class="l-toggle" role="tablist" aria-label="Plan type">
      <button class="l-toggle-btn is-active" type="button" role="tab" id="c-tab-team" aria-selected="true" aria-controls="c-panel-team" data-plan-tab="team">Team &amp; Enterprise</button>
      <button class="l-toggle-btn" type="button" role="tab" id="c-tab-individual" aria-selected="false" aria-controls="c-panel-individual" data-plan-tab="individual" tabindex="-1">Individual</button>
    </div>
    <div class="l-plan-panel" id="c-panel-team" role="tabpanel" aria-labelledby="c-tab-team" tabindex="0">
      <div class="c-plan-grid">
        <article class="c-plan">
          <h3>Team</h3>
          <p>Keel Code for every seat, with self-serve seat management and up to $500 per month in pooled API credits.</p>
          <p class="c-plan-price">$20</p>
          <p class="c-plan-note">Per seat / month if billed annually. For teams of 2 to 150.</p>
          <button type="button" class="l-btn l-btn-dark js-auth" data-auth="signup">Get Team plan</button>
          <a href="/privacy">Learn more</a>
        </article>
        <article class="c-plan">
          <h3>Enterprise</h3>
          <p>Everything in Team, plus Keel Security, usage and ROI analytics, role-based access, spend limits, and custom data controls. <a href="/privacy">Learn more</a></p>
          <button type="button" class="l-btn l-btn-dark js-auth" data-auth="sales">Get Enterprise plan</button>
        </article>
      </div>
      <div class="c-plan-extra">
        <h4>Available on Team and Enterprise</h4>
        <a href="/#plans">See all features and pricing</a>
        <ul><li>Code Review</li><li>Keel Code on web and mobile</li><li>Keel Cowork</li><li>Keel Design, Slides, and Docs</li></ul>
      </div>
      <p class="c-fine">Deploying through the API or a cloud provider? <a href="/requirements">See your options</a></p>
      <p class="c-fine">Usage limits apply. Prices shown don't include applicable tax. Price and plans are subject to change at Keel's discretion.</p>
    </div>
    <div class="l-plan-panel" id="c-panel-individual" role="tabpanel" aria-labelledby="c-tab-individual" tabindex="0" hidden>
      <div class="c-plan-grid c-plan-grid-ind">
        <article class="c-plan"><h3>Pro</h3><p>For everyday work. Keel Code is included.</p><p class="c-plan-price">$17</p><button type="button" class="l-btn l-btn-dark js-auth" data-auth="signup">Try Keel</button></article>
        <article class="c-plan"><h3>Max</h3><p>For all-day work, with more usage and early features.</p><p class="c-plan-price">$100</p><button type="button" class="l-btn l-btn-dark js-auth" data-auth="signup">Try Keel</button></article>
        <article class="c-plan"><h3>Ultra</h3><p>For your largest tasks and highest limits.</p><p class="c-plan-price">$200</p><button type="button" class="l-btn l-btn-dark js-auth" data-auth="signup">Try Keel</button></article>
      </div>
    </div>
  </div>
</section>
```
`landing.js` already switches `.l-toggle-btn[data-plan-tab]` + panels via
`aria-controls`, so this is functional out of the box. Keep `hidden` on the
inactive panel.

### 3. Latest feature announcements
```
<section class="l-section c-announce" id="announcements">
  <div class="l-container">
    <h2 class="l-section-title">Latest feature announcements</h2>
    <div class="c-announce-grid">
      <article class="c-article"><span class="c-article-art">...svg...</span><h3><a href="/notices">Code Review: Catch more bugs before they reach production. Now generally available for Team and Enterprise.</a></h3><p>Blog · Oct 15, 2026</p></article>
      <article class="c-article"><span class="c-article-art">...svg...</span><h3><a href="/notices">Mods: Change how Keel Code behaves and looks with a few lines of TypeScript. Available in the CLI and desktop app.</a></h3><p>Blog · Oct 1, 2026</p></article>
      <article class="c-article"><span class="c-article-art">...svg...</span><h3><a href="/notices">Projects: Group related coding sessions so you can run and easily supervise multiple Keel agents at once. Available on Keel Code Desktop.</a></h3><p>Blog · Sep 17, 2026</p></article>
    </div>
    <button type="button" class="l-btn l-btn-outline c-changelog" data-modal="changelog">View changelog</button>
  </div>
</section>
```

### 4. What Keel Code can take on
```
<section class="l-section c-takeon" id="take-on">
  <div class="l-container">
    <div class="c-doodle" aria-hidden="true">...svg...</div>
    <h2 class="l-section-title">What Keel Code can take on</h2>
    <p class="c-section-lede">Keel Code builds the plan, asks clarifying questions, and handles work that runs for hours or days.</p>
    <a class="l-btn l-btn-dark" href="#get-started">Get Keel Code</a>
    <div class="c-takeon-grid">
      <div class="c-terminal" data-terminal>
        <div class="c-terminal-bar"><span></span><span></span><span></span><em>~/acme-storefront</em></div>
        <div class="c-terminal-body" data-terminal-body>...</div>
        <div class="c-terminal-tabs" role="tablist">
          <button class="c-ttab is-active" type="button" role="tab" aria-selected="true" data-demo="onboarding">Onboarding</button>
          <button class="c-ttab" type="button" role="tab" aria-selected="false" data-demo="triage">Triage issues</button>
          <button class="c-ttab" type="button" role="tab" aria-selected="false" data-demo="migrate">Migrate code</button>
        </div>
      </div>
      <div class="c-takeon-list">
        <article class="c-feature"><h3>Code onboarding</h3><p>Keel Code maps and explains large codebases in a few seconds. It uses agentic search to understand project structure and dependencies without you having to manually select context files.</p></article>
        <article class="c-feature"><h3>Turn issues into PRs</h3><p>Stop bouncing between tools. Keel Code works with GitHub, GitLab, and your command line tools to read issues, write code, run tests, and open pull requests.</p></article>
        <article class="c-feature"><h3>Run multi-hour refactors and migrations</h3><p>Keel Code is designed to follow imports across the repo, run your tests, and keep going when something breaks, checking with you when it needs a decision.</p></article>
      </div>
    </div>
  </div>
</section>
```

### 5. Meets you where you code
```
<section class="l-section c-where" id="where-you-code">
  <div class="l-container">
    <h2 class="l-section-title">Meets you where you code</h2>
    <a class="l-btn l-btn-dark" href="#get-started">Get Keel Code</a>
    <div class="c-where-grid">
      <article class="c-where-card">
        <div class="c-where-art c-art-terminal">...svg/css...</div>
        <h3>Start in your terminal</h3>
        <p>Super powerful terminal integration. Works with all your CLI tools alongside popular IDEs.</p>
        <div class="c-copy-row"><code>curl -fsSL https://keel.ai/install.sh | bash</code><button type="button" class="c-copy" data-copy="curl -fsSL https://keel.ai/install.sh | bash" aria-label="Copy install command">Copy</button></div>
        <a href="/requirements">Or read the documentation</a>
        <div class="c-where-actions"><a class="l-btn l-btn-dark" href="/app">Try Keel Code</a><a class="l-btn l-btn-outline" href="/requirements">Developer docs</a></div>
      </article>
      <article class="c-where-card">
        <div class="c-where-art c-art-editor">...svg/css...</div>
        <h3>Integrate with your editor</h3>
        <p>Native extensions for VS Code (+ Cursor, Devin Desktop) and JetBrains IDEs.</p>
        <div class="c-where-actions"><button type="button" class="l-btn l-btn-outline" data-modal="vscode">VS Code</button><button type="button" class="l-btn l-btn-outline" data-modal="jetbrains">JetBrains</button></div>
      </article>
      <article class="c-where-card">
        <div class="c-where-art c-art-browser">...svg/css...</div>
        <h3>Access anywhere</h3>
        <p>Quick access from browser, mobile app, or Keel on desktop. Great for parallel work or on-the-go coding.</p>
        <div class="c-where-actions"><a class="l-btn l-btn-dark" href="/app">Open in browser</a><a class="l-btn l-btn-outline" href="/download">Download app</a></div>
      </article>
    </div>
  </div>
</section>
```
Card art: terminal = warm orange/red gradient window with fake code lines;
editor = dark navy IDE window with gutter + green diff lines; browser = blue
window with a chat panel. All drawn with CSS + inline SVG.

### 6. Slack
```
<section class="l-section c-slack" id="slack">
  <div class="l-container c-slack-inner">
    <h2>Kick off coding tasks in Slack</h2>
    <div class="c-slack-actions">
      <button type="button" class="l-btn l-btn-dark" data-modal="slack">Add to Slack</button>
      <a href="/requirements" class="l-btn l-btn-outline">Learn more</a>
    </div>
  </div>
</section>
```

### 7. What developers are saying
```
<section class="l-section c-voices" id="developers">
  <div class="l-container">
    <h2 class="l-section-title">What developers are saying</h2>
    <div class="c-voice-grid">
      <article class="c-voice"><span class="c-voice-logo">Ramp</span><blockquote>“Keel Code has dramatically accelerated our team's coding efficiency. I can now write EDA code in a notebook—pulling data, training a model, and evaluating it with basic metrics—and then ask Keel to convert that into a Metaflow pipeline. This process saves 1-2 days of routine (and often boring!) work per model.”</blockquote><p>Anton Biryukov, Staff Software Engineer</p><a href="/notices">Read story</a></article>
      <article class="c-voice"><span class="c-voice-logo">Intercom</span><blockquote>“With Keel, we're not just automating customer service—we're elevating it to truly human quality. This lets support teams think more strategically about customer experience and what makes interactions genuinely valuable.”</blockquote><p>Fergal Reid, VP of AI</p><a href="/notices">Read story</a></article>
      <article class="c-voice"><span class="c-voice-logo">Notion</span><blockquote>“Keel Code is moving our team up a level: we decide what needs to happen, and smooth the process so it can build and verify end-to-end. A big part of my job now is to keep as many instances of Keel Code busy as possible.”</blockquote><p>Simon Last, Co-founder</p><a href="/notices">Read story</a></article>
    </div>
    <div class="c-voice-logos">... Gitlab, Dynatrace, Kubernetes, Heroku, Stripe, Elastic, Terraform, Sentry, AWS, MongoDB, Atlassian, Datadog, GitHub, Vercel, New Relic as text logos ...</div>
    <div class="c-voice-note"><h3>Connects with your favorite command line tools</h3><p>Your terminal is where real work happens. Keel Code connects with the tools that power development—deployment, databases, monitoring, version control. Rather than adding another interface to juggle, it enhances your existing stack.</p></div>
  </div>
</section>
```

### 8. FAQ
Use the **same `.l-faq` markup as index.html** so `landing.js` powers the
accordion. Heading `<h2 class="l-section-title">FAQ</h2>` with id `faq`.
Seven items, in order, with real answers in `.l-faq-a`:
1. How do I get started with Keel? — "You can access Keel Code with a Keel Pro, Max, or Ultra plan, a Team or Enterprise plan, or a Keel Console account. Download Keel Code and sign in with your respective Keel or Console credentials."
2. What kind of tasks can Keel Code handle? — "Keel Code can handle routine work like bug fixes and testing, and larger jobs like refactors and new features that are long-running and asynchronous. You set the direction as the architect and orchestrator, and Keel Code does the work. Describe what you want and it plans, writes code, runs tests, and opens pull requests. It can work on several tasks at once, and surface decisions you need to make for it to keep going."
3. How does Keel Code work with my existing tools? — "Keel Code runs in your terminal and works alongside your preferred IDE and development tools without requiring you to change your workflow. Keel Code can also use command line tools (like Git) and MCP servers (like GitHub) to extend its own capabilities using your tools."
4. Is Keel Code secure? — "Keel Code is designed to work within limits you set. Permission modes, allow and deny rules, and hooks decide what runs with or without your approval. In auto mode, safeguards check higher-risk actions before they run and block the ones they flag as risky. Auto mode relies on classification systems and does not eliminate risk."
5. What are the system requirements to run Keel Code? — "Keel Code works on macOS, Linux, and Windows. See full system requirements." (link to `/requirements`)
6. How much does Keel Code cost? — "When used with a Keel Console account, Keel Code consumes API tokens at standard API pricing." (link to `/#plans`)
7. Does Keel Code work with the Keel desktop app? — "Yes. Pro, Max, Ultra, Team, and Enterprise users can access Keel Code on the Keel desktop app." (link to `/download`)

### 9. Get the technical rundown
```
<section class="l-section c-technical" id="technical">
  <div class="l-container">
    <div class="c-doodle" aria-hidden="true">...svg...</div>
    <h2 class="l-section-title">Get the technical rundown</h2>
    <div class="c-res-grid">
      <article class="c-res"><span class="c-res-art">...svg...</span><h3><a href="/requirements">Keel Code documentation</a></h3><p>Developer docs</p></article>
      <article class="c-res"><span class="c-res-art">...svg...</span><h3><a href="/requirements">Common workflows</a></h3><p>Developer docs</p></article>
      <article class="c-res"><span class="c-res-art">...svg...</span><h3><a href="/notices">Using KEEL.md files</a></h3><p>Blog</p></article>
      <article class="c-res"><span class="c-res-art">...svg...</span><h3><a href="/notices">Introduction to agentic coding</a></h3><p>Blog</p></article>
      <article class="c-res"><span class="c-res-art">...svg...</span><h3><a href="/notices">How Keel teams use Keel Code</a></h3><p>Blog</p></article>
      <article class="c-res"><span class="c-res-art">...svg...</span><h3><a href="/notices">Fix software bugs faster with Keel</a></h3><p>Blog</p></article>
    </div>
  </div>
</section>
```

### 10. Dark CTA + newsletter
```
<section class="c-cta" id="get-code">
  <div class="l-container">
    <h2>Create what's exciting.<br>Maintain what's essential.</h2>
    <div class="c-cta-grid">
      <div><h3>Use Keel Code where you work</h3>
        <div class="c-copy-row"><code>curl -fsSL https://keel.ai/install.sh | bash</code><button type="button" class="c-copy" data-copy="curl -fsSL https://keel.ai/install.sh | bash">Copy</button></div>
        <p>Or read the <a href="/requirements">documentation</a></p>
        <div class="c-cta-actions"><a class="l-btn l-btn-dark" href="/app">Try Keel Code</a><a class="l-btn l-btn-outline" href="/requirements">Developer docs</a></div>
      </div>
      <div class="c-cta-news" id="newsletter">
        <h3>Get the developer newsletter</h3>
        <p>Product updates, how-tos, community spotlights, and more. Delivered monthly to your inbox.</p>
        <form id="c-news-form" novalidate>
          <label class="l-sr-only" for="c-news-email">Email address</label>
          <input id="c-news-email" type="email" placeholder="you@example.com" required />
          <button type="submit" class="l-btn l-btn-dark">Sign up</button>
          <p class="c-news-msg" id="c-news-msg" role="status" hidden>Please provide a valid email address.</p>
        </form>
        <p class="c-news-fine">Please provide your email address if you'd like to receive our monthly developer newsletter. You can unsubscribe at any time.</p>
      </div>
    </div>
  </div>
</section>
```

### 11. Footer / news chip / auth modal
Copy verbatim from `index.html` with the adjustments listed above.

### 12. Generic modal (for data-modal buttons)
Add one reusable modal at the end of `<body>` (before scripts):
```
<div class="c-modal" id="c-modal" hidden>
  <div class="c-modal-backdrop" data-c-close></div>
  <div class="c-modal-card" role="dialog" aria-modal="true" aria-labelledby="c-modal-title">
    <button type="button" class="c-modal-close" data-c-close aria-label="Close dialog">×</button>
    <h2 id="c-modal-title"></h2><div id="c-modal-body"></div>
    <button type="button" class="l-btn l-btn-dark" data-c-close>Close</button>
  </div>
</div>
<div class="c-toast" id="c-toast" role="status" aria-live="polite" hidden></div>
```

## EXACT JS REQUIREMENTS (Agent C)
Guard everything: only run when `document.body.classList.contains('code-page')`.
Wrap in an IIFE, feature-detect, no console errors.

1. `data-way` buttons: open the generic modal with real copy per target
   (terminal -> scroll to `#where-you-code`, web/iOS/Android -> note + `/app`
   or `/download`, GitHub/VS Code/JetBrains -> install/extension instructions,
   Slack -> scroll to `#slack`). Escape/backdrop/close button close it.
2. `data-modal` buttons (`changelog`, `vscode`, `jetbrains`, `slack`): open
   the same modal with real copy and a working Close button.
3. `.c-ttab[data-demo]` buttons: switch active state + `aria-selected` and
   replace `[data-terminal-body]` with a different realistic Keel Code
   transcript (onboarding / triage / migrate). Keyboard arrow keys supported.
4. `.c-copy[data-copy]` buttons: copy to clipboard (with `document.execCommand`
   fallback), change label to "Copied", show a toast, revert after 1.8s.
5. Newsletter form: validate email regex, set `#c-news-msg` text accordingly,
   on success store to `localStorage['keel_newsletter']` and show a success
   message + toast; clear input. Never submit to a network.
6. Generic modal helpers: `openCModal(title, html)`, `closeCModal()`, focus
   management, Escape closes, click outside closes, `.c-modal-open` body class.
7. Toast helper `cToast(msg)` shows `#c-toast`, auto-hides after 3.2s.
8. Do NOT break `landing.js`: nav mega menus, mobile menu, auth modal, help
   search, news chip, language select, FAQ accordion, plan tabs, global keys.
9. Smooth-scroll for in-page anchor links that target real ids.
10. No `href="#"`, no dead buttons, no uncaught errors.

## EXACT CONFIG REQUIREMENTS (Agent D)
- `vercel.json`: add rewrite
  `{ "source": "/product/keel-code", "destination": "/product/keel-code.html" }`
  and redirect
  `{ "source": "/product/keel-code.html", "destination": "/product/keel-code", "permanent": false }`.
  Keep ALL existing headers/rewrites/redirects intact. Valid JSON only.
- `sitemap.xml`: add
  `<url><loc>https://keel-desktop.vercel.app/product/keel-code</loc><lastmod>2026-11-24</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>`
  inside `<urlset>`.
- `product/README.md`: short doc describing the page, route and ownership.

## DEFINITION OF DONE
- `node --check keel/site/ui/keel-code.js` passes.
- Opening `/product/keel-code` via a local static server renders the full
  screenshot structure with no missing assets and no console errors.
- Every button does something real (modal, toast, scroll, navigation, form).
- No dead `href="#"`.
- All brand references are Keel, never Claude/Anthropic.
