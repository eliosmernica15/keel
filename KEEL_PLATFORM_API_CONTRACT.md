# KEEL Platform API page — implementation contract

Target URL: `https://keel-desktop.vercel.app/platform/api`
Site root: `keel/site` (Vercel serves this directory at `/`).

Goal: reproduce the supplied full-page screenshot of the Claude Platform API
marketing page **exactly in forms, layout, spacing, typography, section order
and interaction**, but with the brand rendered as **KEEL** everywhere. Keep
model family names (Fable, Opus, Sonnet, Haiku). All buttons/links must be
functional — no dead `href="#"`, no console errors.

## Files (each owner works ONLY on their files)

| Owner | Files |
|---|---|
| HTML agent | `keel/site/platform/api.html` |
| Assets agent | `keel/site/assets/img/platform/*.svg` |
| CSS agent | `keel/site/ui/platform-api.css` |
| JS agent | `keel/site/ui/platform-api.js` |
| Coordinator | `keel/site/vercel.json`, `sitemap.xml`, `README.md`, cross-site nav links, verification harness |

## Hard conventions (all agents MUST follow)

- Body class: `<body class="pa-body">`. Every CSS rule is scoped under `body.pa-body` (or `body.pa-body ...`) so nothing leaks from `ui/style.css`.
- All classes/ids/attributes are prefixed `pa-`.
- Stylesheet: `<link rel="stylesheet" href="/ui/platform-api.css" />`; script: `<script src="/ui/platform-api.js" defer></script>`.
- Fonts are already available: Inter (`/ui/fonts/inter-400.woff2`) and JetBrains Mono (`/ui/fonts/jetbrains-mono-400.woff2`). Serif headline uses `Georgia, 'Times New Roman', serif`.
- Design tokens (put on `body.pa-body`):
  `--pa-page:#f7f6f2; --pa-page-alt:#f1efe8; --pa-card:#fff; --pa-ink:#191919; --pa-ink-soft:#333; --pa-muted:#6b6a66; --pa-line:#dedcd6; --pa-accent:#d97757; --pa-accent-deep:#a94e32; --pa-dark:#191919; --pa-footer-bg:#191919; --pa-serif:Georgia,'Times New Roman',serif; --pa-body:'Inter',system-ui,sans-serif; --pa-container:1200px;`
- Warm off-white background, black ink, black pill buttons, thin grey borders, terracotta accent, editorial serif section headings, generous whitespace. Dark sections use `#191919`.
- Local artwork only: reference `/assets/img/platform/<name>.svg`. No external network calls. No CDN.
- Accessibility: skip link, labelled buttons, `aria-expanded` on dropdowns/accordion, `aria-controls`, focus-visible rings, `prefers-reduced-motion` support, sensible heading order.
- Responsive: desktop ≥1100, tablet 900–1099, mobile <640 with working hamburger.

## DOM contract — exact ids/classes the CSS and JS agents rely on

```
<body class="pa-body">
  <a class="pa-skip" href="#pa-main">Skip to content</a>
  <div class="pa-progress" id="pa-progress"><span class="pa-progress-fill" id="pa-progress-fill"></span></div>

  <header class="pa-header" id="pa-header">
    <div class="pa-nav-inner">
      <a class="pa-brand" href="/" aria-label="KEEL home">
        <img class="pa-brand-mark" src="/assets/img/platform/pa-mark.svg" alt="" />
        <span class="pa-brand-name">KEEL</span>
      </a>
      <nav class="pa-nav" aria-label="Primary">
        <div class="pa-nav-item" data-pa-nav="product">
          <button class="pa-nav-trigger" type="button" aria-expanded="false" aria-controls="pa-menu-product">Product <span class="pa-chevron" aria-hidden="true"></span></button>
          <div class="pa-mega" id="pa-menu-product" hidden> ... 4 columns .pa-mega-grid > .pa-mega-col (h .pa-mega-heading, .pa-mega-link, optional .pa-mega-subhead) + .pa-mega-footer ... </div>
        </div>
        <!-- same for data-pa-nav = developers | enterprise | resources | pricing, ids pa-menu-developers, pa-menu-enterprise, pa-menu-resources, pa-menu-pricing -->
        <a class="pa-nav-plain" href="/app">Login</a>
      </nav>
      <div class="pa-nav-actions">
        <a class="pa-btn pa-btn-outline" href="#" data-pa-modal="contact">Contact sales</a>
        <a class="pa-btn pa-btn-dark" href="#" data-pa-modal="signup">Try KEEL</a>
        <button class="pa-hamburger" id="pa-hamburger" type="button" aria-expanded="false" aria-controls="pa-mobile-menu" aria-label="Open menu"><span></span><span></span><span></span></button>
      </div>
    </div>
    <div class="pa-mobile-menu" id="pa-mobile-menu" hidden> ... .pa-mobile-link entries + .pa-mobile-cta ... </div>
  </header>

  <aside class="pa-explore" id="pa-explore" aria-label="On this page">
    <button class="pa-explore-toggle" id="pa-explore-toggle" type="button" aria-expanded="true" aria-controls="pa-explore-list">Explore here <span class="pa-explore-icon" aria-hidden="true">—</span></button>
    <nav class="pa-explore-list" id="pa-explore-list">
      <a class="pa-explore-link" href="#pa-models">Models</a>
      <a class="pa-explore-link" href="#pa-design">AI-first design</a>
      <a class="pa-explore-link" href="#pa-agents">Agent SDK</a>
      <a class="pa-explore-link" href="#pa-enterprise">Enterprise</a>
      <a class="pa-explore-link" href="#pa-cost">Cost &amp; performance</a>
      <a class="pa-explore-link" href="#pa-console">Console</a>
      <a class="pa-explore-link" href="#pa-customers">Customers</a>
    </nav>
  </aside>

  <main id="pa-main">
    <!-- 1 HERO -->
    <section class="pa-hero pa-section" id="pa-top">
      <div class="pa-container pa-hero-grid">
        <div class="pa-hero-copy">
          <p class="pa-eyebrow">KEEL Platform</p>
          <h1 class="pa-hero-title">Build frontier models on the KEEL Platform</h1>
          <p class="pa-hero-sub">Frontier models, training and inference infrastructure designed to work together.</p>
          <div class="pa-hero-actions">
            <a class="pa-btn pa-btn-dark pa-btn-lg" href="#" data-pa-modal="signup">Start building <span aria-hidden="true">↗</span></a>
            <a class="pa-btn pa-btn-outline pa-btn-lg" href="#" data-pa-modal="contact">Contact sales</a>
          </div>
        </div>
        <div class="pa-hero-art">
          <img src="/assets/img/platform/pa-hero-blocks.svg" alt="Illustration of a hand placing a block into a stack of model blocks" class="pa-hero-img" />
        </div>
      </div>
    </section>

    <!-- 2 LOGO STRIP -->
    <section class="pa-logos pa-section" aria-label="Teams building on KEEL">
      <div class="pa-container pa-logo-row">
        <img class="pa-logo" src="/assets/img/platform/pa-logo-lovable.svg" alt="Lovable" />
        ... gitlab, notion, rakuten, thomson-reuters, brex, cognition, zoom ...
      </div>
    </section>

    <!-- 3 MODELS -->
    <section class="pa-models pa-section" id="pa-models">
      <div class="pa-container">
        <h2 class="pa-h2">KEEL models for every job</h2>
        <p class="pa-note pa-models-note">Save 50% with batch processing. <a href="#pa-cost">Learn more ↗</a></p>
        <div class="pa-model-grid">
          <article class="pa-model-card" data-pa-model="fable">
            <p class="pa-model-name">Fable 5</p>
            <p class="pa-model-tag">Next generation intelligence for long-running agents</p>
            <ul class="pa-model-uses"><li>Multi-day autonomous projects</li><li>Expert-level work for frontier research</li></ul>
            <div class="pa-price-block">
              <p class="pa-price-head">Prompt caching</p>
              <p class="pa-price-row"><span>Read</span><span>$0.20 / MTok</span></p>
              <p class="pa-price-row"><span>Write</span><span>$10 / MTok</span></p>
              <p class="pa-price-row"><span>Input</span><span>$8 / MTok</span></p>
              <p class="pa-price-row"><span>Output</span><span>$40 / MTok</span></p>
            </div>
            <button class="pa-link-btn" type="button" data-pa-model-detail="Fable 5">Explore Fable <span aria-hidden="true">↗</span></button>
          </article>
          <!-- opus 4.6, sonnet 4.5, haiku 4.5 with same structure; haiku has two-tier prompt caching (≤100K / >100K) -->
        </div>
        <p class="pa-fineprint">For workloads that need to run in the US, US-only inference is available at 1.1x pricing for input and output tokens. <a href="#pa-enterprise">Learn more</a></p>
        <p class="pa-fineprint">Get up to 2.5x faster speeds with fast mode for Opus 4.6 and Fable 5 at 2x standard pricing. <a href="#pa-cost">Learn more</a></p>
        <p class="pa-fineprint">Prompt caching pricing reflects 5-minute TTL. <a href="#pa-cost">Learn about extended prompt caching</a></p>
      </div>
    </section>

    <!-- 4 AI-FIRST DESIGN -->
    <section class="pa-design pa-section" id="pa-design">
      <div class="pa-container">
        <h2 class="pa-h2 pa-center">AI-first design for KEEL</h2>
        <p class="pa-section-sub pa-center">Every layer of the platform is built around how models think.</p>
        <div class="pa-hub-wrap">
          <div class="pa-hub" id="pa-hub">
            <button class="pa-hub-node pa-hub-center" type="button" data-pa-hub-detail="KEEL models">KEEL</button>
            <!-- 8-10 .pa-hub-node buttons positioned around center via CSS custom props --x/--y; data-pa-hub-detail holds description -->
            <button class="pa-hub-node" style="--x:...;--y:..." type="button" data-pa-hub-detail="...">Code execution</button>
            ... Structured outputs, Tool use, Computer use, Citations, Files, Context window, Compaction, Web search and fetch ...
          </div>
        </div>
        <div class="pa-hub-detail" id="pa-hub-detail" role="status" aria-live="polite">Select a capability to see how KEEL uses it.</div>
        <div class="pa-hub-logos"><img src="/assets/img/platform/pa-logo-lovable.svg" alt="Lovable" /><img src="/assets/img/platform/pa-mark.svg" alt="KEEL" /></div>
      </div>
    </section>

    <!-- 5 AGENT SDK -->
    <section class="pa-agents pa-section" id="pa-agents">
      <div class="pa-container">
        <h2 class="pa-h2 pa-center">Power your most ambitious workflows with KEEL Agent SDK</h2>
        <div class="pa-agent-visual">
          <div class="pa-code-window">
            <div class="pa-window-bar"><span class="pa-dots"><i></i><i></i><i></i></span><span>agent.ts</span><button class="pa-copy" type="button" data-pa-copy="pa-code-agent" aria-label="Copy code">Copy</button></div>
            <pre id="pa-code-agent"><code>...</code></pre>
          </div>
          <div class="pa-flow-row">
            <div class="pa-flow-node" data-pa-flow="mcp"><img src="/assets/img/platform/pa-icon-mcp.svg" alt="" /><span>MCP tools</span></div>
            <div class="pa-flow-node" data-pa-flow="memory"><img src="/assets/img/platform/pa-icon-memory.svg" alt="" /><span>Memory</span></div>
            <div class="pa-flow-node" data-pa-flow="sandbox"><img src="/assets/img/platform/pa-icon-sandbox.svg" alt="" /><span>Sandbox</span></div>
            <div class="pa-flow-node" data-pa-flow="skills"><img src="/assets/img/platform/pa-icon-skills.svg" alt="" /><span>Skills</span></div>
          </div>
          <div class="pa-terminal-window">
            <div class="pa-window-bar"><span class="pa-dots"><i></i><i></i><i></i></span><span>console</span><button class="pa-copy" type="button" data-pa-copy="pa-code-terminal" aria-label="Copy output">Copy</button></div>
            <pre id="pa-code-terminal"><code>...</code></pre>
          </div>
        </div>
        <div class="pa-flow-detail" id="pa-flow-detail" role="status" aria-live="polite">Select a building block to learn more.</div>
      </div>
    </section>

    <!-- 6 ENTERPRISE -->
    <section class="pa-enterprise pa-section" id="pa-enterprise">
      <div class="pa-container">
        <h2 class="pa-h2 pa-center">Built for enterprise workflows</h2>
        <div class="pa-enterprise-grid">
          <article class="pa-enterprise-card" data-pa-enterprise="security"><div class="pa-enterprise-icon">◇</div><h3>Security and data governance</h3><p>...</p></article>
          <article class="pa-enterprise-card" data-pa-enterprise="scale"><div class="pa-enterprise-icon">◎</div><h3>Scalable infrastructure</h3><p>...</p></article>
          <article class="pa-enterprise-card" data-pa-enterprise="deploy"><div class="pa-enterprise-icon">⬡</div><h3>Flexible deployment</h3><p>...</p></article>
        </div>
        <div class="pa-cloud-logos"><img src="/assets/img/platform/pa-logo-aws.svg" alt="Amazon Web Services" /><img src="/assets/img/platform/pa-logo-gcp.svg" alt="Google Cloud" /><img src="/assets/img/platform/pa-logo-azure.svg" alt="Microsoft Foundry" /></div>
      </div>
    </section>

    <!-- 7 COST / PERFORMANCE -->
    <section class="pa-cost pa-section" id="pa-cost">
      <div class="pa-container">
        <h2 class="pa-h2 pa-center">Control cost and performance</h2>
        <div class="pa-cost-grid">
          <div class="pa-cost-features" role="tablist" aria-label="Optimization features">
            <button class="pa-cost-tab is-active" type="button" role="tab" aria-selected="true" data-pa-cost="batch">Batch processing <span>Process large volumes asynchronously at reduced cost.</span></button>
            <button class="pa-cost-tab" type="button" role="tab" aria-selected="false" data-pa-cost="cache">Prompt caching <span>Reuse context to cut cost and latency.</span></button>
            <button class="pa-cost-tab" type="button" role="tab" aria-selected="false" data-pa-cost="effort">Effort <span>Choose how hard KEEL works on a task.</span></button>
            <button class="pa-cost-tab" type="button" role="tab" aria-selected="false" data-pa-cost="advisor">Advisor strategy <span class="pa-beta">BETA</span> <span>Smaller models call larger ones to improve plans.</span></button>
          </div>
          <div class="pa-cost-panels">
            <div class="pa-cost-panel is-active" data-pa-cost-panel="batch">
              <div class="pa-batch-visual"><span class="pa-batch-bar" style="--h:38%"></span> ... 8 bars ...</div>
              <p>Save 50% with the Message Batches API.</p>
              <button class="pa-link-btn" type="button" data-pa-modal="docs">Read documentation ↗</button>
            </div>
            <div class="pa-cost-panel" data-pa-cost-panel="cache" hidden>
              <div class="pa-cache-chart"><svg viewBox="0 0 420 160" ...>...</svg></div>
              <p>Reduce cost by up to ~97% and latency by ~60%.</p>
            </div>
            <div class="pa-cost-panel" data-pa-cost-panel="effort" hidden>...</div>
            <div class="pa-cost-panel" data-pa-cost-panel="advisor" hidden>...</div>
          </div>
          <div class="pa-cost-panel" data-pa-cost-panel="batch" hidden>...</div> <!-- alternate layout card -->
        </div>
        <blockquote class="pa-quote-card">
          <img src="/assets/img/platform/pa-logo-quora.svg" alt="Quora" />
          <p>“For Quora, batch processing provides cost savings while also reducing the complexity of running a large number of queries that don’t need to be processed in real time.”</p>
          <cite>Quora · <a href="#pa-customers">Read more ↗</a></cite>
        </blockquote>
      </div>
    </section>

    <!-- 8 CONSOLE -->
    <section class="pa-console pa-section" id="pa-console">
      <div class="pa-container">
        <h2 class="pa-h2 pa-center">Observe and mitigate your agents with the KEEL Console</h2>
        <div class="pa-console-grid">
          <div class="pa-console-pane pa-console-prompt">
            <div class="pa-pane-head"><span>Build your request</span><button class="pa-copy" type="button" data-pa-copy="pa-console-prompt-text">Copy</button></div>
            <pre id="pa-console-prompt-text">Classify all customer support tickets ...</pre>
            <div class="pa-pane-actions"><button class="pa-btn pa-btn-dark pa-run" type="button" id="pa-run">Run request <span aria-hidden="true">→</span></button></div>
          </div>
          <div class="pa-console-pane pa-console-output">
            <div class="pa-pane-head"><span>Session trace · live</span><span class="pa-live"><i></i> live</span></div>
            <pre id="pa-console-output"><code>... trace lines ...</code></pre>
          </div>
        </div>
        <div class="pa-console-tabs" role="tablist" aria-label="Console capabilities">
          <button class="pa-console-tab is-active" type="button" role="tab" aria-selected="true" data-pa-console="build">Build</button>
          <button class="pa-console-tab" type="button" role="tab" aria-selected="false" data-pa-console="deploy">Deploy</button>
          <button class="pa-console-tab" type="button" role="tab" aria-selected="false" data-pa-console="monitor">Monitor</button>
          <button class="pa-console-tab" type="button" role="tab" aria-selected="false" data-pa-console="manage">Manage</button>
        </div>
        <p class="pa-console-detail" id="pa-console-detail" role="status" aria-live="polite">Prototype prompts, upload skills and files, configure your agents.</p>
        <div class="pa-stat-row">
          <img src="/assets/img/platform/pa-logo-datadog.svg" alt="Datadog" />
          <div class="pa-stat"><strong>5 million</strong><span>AI agents running in customer workflows each month</span></div>
          <div class="pa-stat"><strong>10x</strong><span>faster to build production agents</span></div>
        </div>
      </div>
    </section>

    <!-- 9 CUSTOMERS / TESTIMONIALS -->
    <section class="pa-customers pa-section" id="pa-customers">
      <div class="pa-container">
        <h2 class="pa-h2 pa-center">So why builders build on the KEEL Platform</h2>
        <div class="pa-quotes" id="pa-quotes">
          <article class="pa-quote-slide is-active" data-pa-slide="0"> <img ... /> <blockquote>...</blockquote> <cite>...</cite> </article>
          ... 6 slides total ...
        </div>
        <div class="pa-quote-nav">
          <button class="pa-quote-arrow" id="pa-quote-prev" type="button" aria-label="Previous testimonial">←</button>
          <span class="pa-quote-count" id="pa-quote-count">1 / 6</span>
          <button class="pa-quote-arrow" id="pa-quote-next" type="button" aria-label="Next testimonial">→</button>
        </div>
        <div class="pa-quote-dots" id="pa-quote-dots" aria-label="Testimonial navigation"> ... buttons ... </div>
      </div>
    </section>

    <!-- 10 CTA BAND -->
    <section class="pa-cta pa-section dark-scope" id="pa-cta">
      <div class="pa-container pa-cta-grid">
        <div><h2 class="pa-cta-title">Build on the KEEL Platform</h2><a class="pa-btn pa-btn-light" href="#" data-pa-modal="signup">Get started <span aria-hidden="true">↗</span></a></div>
        <div class="pa-terminal-card">
          <div class="pa-terminal-head"><span>Quick start</span><button class="pa-copy" type="button" data-pa-copy="pa-install-cmd">Copy</button></div>
          <pre id="pa-install-cmd"><code>npm install @keel/sdk</code></pre>
        </div>
      </div>
    </section>
  </main>

  <!-- 11 FOOTER -->
  <footer class="pa-footer dark-scope">
    <div class="pa-container">
      <div class="pa-footer-top">
        <a class="pa-brand" href="/"><img src="/assets/img/platform/pa-mark.svg" alt="" /><span>KEEL</span></a>
        <form class="pa-footer-search" id="pa-footer-search">
          <label class="pa-sr-only" for="pa-footer-q">How can we help today?</label>
          <input id="pa-footer-q" type="search" placeholder="How can we help today?" autocomplete="off" />
          <button type="submit" aria-label="Search">→</button>
        </form>
        <div class="pa-search-results" id="pa-search-results" hidden></div>
      </div>
      <div class="pa-footer-cols">
        <div class="pa-footer-col"><h3>Products</h3><a href="/product/overview">KEEL</a> ... etc ...</div>
        ... Enterprise, Developers, Company, Terms and policies ...
      </div>
      <div class="pa-footer-bottom">
        <span>KEEL 2026 All rights reserved.</span>
        <div class="pa-socials"><a href="https://x.com" ...>X</a> ...</div>
        <button class="pa-lang" type="button">English</button>
      </div>
    </div>
  </footer>

  <!-- 12 MODALS / TOAST -->
  <div class="pa-modal" id="pa-modal" hidden role="dialog" aria-modal="true" aria-labelledby="pa-modal-title">
    <div class="pa-modal-backdrop" data-pa-close></div>
    <div class="pa-modal-card">
      <button class="pa-modal-close" type="button" data-pa-close aria-label="Close">×</button>
      <h2 id="pa-modal-title">Sign in to KEEL</h2>
      <p id="pa-modal-desc">Demo sign-in — no real account required.</p>
      <form id="pa-auth-form">
        <button class="pa-btn pa-btn-outline" type="button" id="pa-google">Continue with Google</button>
        <div class="pa-divider"><span>or</span></div>
        <label class="pa-sr-only" for="pa-email">Email</label>
        <input id="pa-email" type="email" placeholder="you@example.com" required />
        <button class="pa-btn pa-btn-dark" type="submit">Continue with email</button>
      </form>
      <form id="pa-contact-form" hidden>
        <label class="pa-sr-only" for="pa-name">Name</label><input id="pa-name" placeholder="Full name" required />
        <label class="pa-sr-only" for="pa-work-email">Work email</label><input id="pa-work-email" type="email" placeholder="Work email" required />
        <label class="pa-sr-only" for="pa-message">Message</label><textarea id="pa-message" placeholder="How can we help?" required></textarea>
        <button class="pa-btn pa-btn-dark" type="submit">Send message</button>
      </form>
    </div>
  </div>
  <div class="pa-toast" id="pa-toast" role="status" aria-live="polite" hidden></div>
</body>
```

## Content mapping (Claude → KEEL)

- All visible "Claude" → "KEEL"; "Anthropic" → "KEEL"; "Try Claude" → "Try KEEL"; "Claude Platform" → "KEEL Platform"; "Claude Agent SDK" → "KEEL Agent SDK"; "Claude Console" → "KEEL Console"; "Claude Code" → "KEEL Code"; "Anthropic commitment" → "KEEL commitment".
- Model names stay: Fable 5, Opus 4.6, Sonnet 4.5, Haiku 4.5.
- Section order and headings must follow the DOM contract above.
- Footer link targets may reuse existing site routes (`/`, `/app`, `/download`, `/pricing`, `/product/overview`, `/product/cowork`, `/product/keel-code`, `/product/keel-duet`, `/privacy`, `/terms`, `/notices`, `/roadmap`, `/eula`, `/trademark`, `/requirements`, `/platform/api`, `/resources/articles/...`) or in-page anchors (`#pa-...`), or open a modal/toast. No dead links.

## Functional requirements (JS agent)

1. Mega dropdowns: hover, click, keyboard (Enter/Space toggles, Escape closes & returns focus, ArrowDown focuses first link, Tab cycles, click-outside closes). Update `aria-expanded`, `hidden`. Only one open at a time.
2. Hamburger toggles `#pa-mobile-menu`, aria-expanded, body scroll lock optional.
3. `#pa-explore-toggle` collapses/expands rail; scroll spy highlights current `.pa-explore-link` (add `.is-active`).
4. `#pa-progress-fill` width reflects scroll progress.
5. Model detail buttons open a toast/modal with that model's full pricing + capability summary.
6. Hub nodes and flow nodes click/keyboard update `#pa-hub-detail` / `#pa-flow-detail` with real copy and `.is-active` state.
7. Cost tabs swap `.pa-cost-panel` visibility + `aria-selected`, update any chart labels.
8. Console tabs swap detail copy; `#pa-run` animates staged lines into `#pa-console-output` (disabled while running, reset after). Copy buttons write to clipboard via `navigator.clipboard` with `document.execCommand('copy')` fallback, then toast "Copied".
9. Testimonial carousel prev/next/dots, wraps, updates count, keyboard arrows, autoplay paused on hover/focus/reduced-motion.
10. CTA install copy works.
11. Footer search filters all footer links + section headings and renders `#pa-search-results` as clickable matches; empty query hides results; Escape clears.
12. Auth modal: triggered by every `[data-pa-modal]`; `signup` shows auth form, `contact` shows contact form, `docs`/`model` maybe show info; Google button simulates sign-in with note; email validation; success sets `localStorage.setItem('keel_logged_in','1')`, toast, then offers link to `/app` (do not auto-navigate without user action). Close via backdrop, ×, Escape; focus trap; restore focus.
13. Newsletter/CTA links that need a destination either go to a real route or open a modal. No JS errors on any control.
14. `node --check keel/site/ui/platform-api.js` must pass.

## Assets agent deliverables (`assets/img/platform/`)

Local, dependency-free SVG files (no external refs, no scripts), sized appropriately, using `#191919`, `#d97757`, warm greys and `#f7f6f2`:
- `pa-mark.svg` — KEEL starburst/asterisk mark (reuse shape language from `assets/img/po-mark.svg`, may copy/adapt).
- `pa-hero-blocks.svg` — line-art illustration: open hand supporting a stack of 4–5 cubes with glowing edges, editorial ink style, transparent background, ~640×520.
- Logos (single-colour, ~140×36): `pa-logo-lovable.svg`, `pa-logo-gitlab.svg`, `pa-logo-notion.svg`, `pa-logo-rakuten.svg`, `pa-logo-thomson-reuters.svg`, `pa-logo-brex.svg`, `pa-logo-cognition.svg`, `pa-logo-zoom.svg`, `pa-logo-datadog.svg`, `pa-logo-github.svg`, `pa-logo-quora.svg`, `pa-logo-spotify.svg`, `pa-logo-vercel.svg`, `pa-logo-aws.svg`, `pa-logo-gcp.svg`, `pa-logo-azure.svg`.
- Icons (~48×48): `pa-icon-mcp.svg`, `pa-icon-memory.svg`, `pa-icon-sandbox.svg`, `pa-icon-skills.svg`.
Keep SVGs valid XML; verify with a parser if available. Do not modify any files outside this directory.
