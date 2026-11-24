# `/login` page design spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY in layout, spacing and
content, with brand **Keel** instead of Claude/Anthropic. This is a dedicated
sign-in / create-account page at `https://keel-desktop.vercel.app/login`.

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Your scope: create ONLY
- `keel/site/login.html`
- `keel/site/ui/login.css`
- `keel/site/ui/login.js`

Do NOT touch index.html, download.html, app.html, other CSS/JS, vercel.json,
or any docs. Do NOT commit, push or deploy.

## Structure (top to bottom)

1. **Top bar** — small Keel starburst + serif "Keel" at far left; right side a
   single black pill "Try Keel". NO nav dropdowns, no Contact sales.
   Very light warm-white background (#faf9f7), generous horizontal padding.

2. **Hero** — two columns, left copy and right image, big top margin.
   - Left column centred:
     - Serif h1 `Question what's next` (~56px).
     - Subtitle `Your thinking partner for big ambitions`.
     - White login card ~360px wide, rounded ~14px, thin border, soft shadow,
       padded ~24px. Contents in order:
         * light-grey full-width button `G Continue with Google`
         * light-grey full-width button `` Continue with Apple`` (apple glyph)
         * thin divider with centred `or`
         * light-grey input with placeholder `Enter your email`
         * black full-width button `Continue with email`
         * small centred fine print: `By continuing, you acknowledge Keel's <a href="/privacy">Privacy Policy</a>.`
     - Beneath the card: small button with download icon `Download desktop app` → `/download`.
   - Right column: rounded-corner hero image. Use existing repo asset
     `/assets/img/keel-app.jpg` (we have no stock photo).

3. **Large empty gap** (~80–100px).

4. **Explore plans** — centred serif heading. Segmented toggle with EXACT labels
   `Individual` and `Team and Enterprise`. Three white rounded cards in a row:
   - **Free** — botanical line glyph, `Try Keel` tagline, `$0`, `Free for
     everyone`, black `Try Keel` button, tiny `No credit card required`,
     features: Chat on web, desktop, and mobile; Search the web, create files,
     and run code; Memory across conversations; Connect your apps and tools;
     Keel Design, Slides, and Docs.
   - **Pro** — glyph, `For everyday work`, `$17`, `Per month with annual
     subscription discount ($200 billed up front), $20 if billed monthly.`,
     black `Try Keel`, tiny `No credit card required`. `Everything in Free,
     plus:`: More usage*; Hand off tasks and get back finished docs, sheets,
     and designs; Keel Data; Keel Code; Keel Science; Projects; More Keel
     models; Keel in Chrome and Microsoft 365.
   - **Max and Ultra** — glyph, `For people who work with Keel all day`,
     `From $100`, `Per month`, black `Try Keel`, tiny `No credit card
     required`. `Everything in Pro, plus:`: Choose 5x Pro usage every 5 hours
     and every week, or 10x Pro usage every week*; Early access to advanced
     Keel features; Priority access at high traffic times.
   - Footnote centred grey fine print: `*Usage limits apply. Prices shown don't
     include applicable tax. Prices and plans are subject to change at Keel's
     discretion.`
   - Team panel: a simple second panel with Team and Enterprise cards that is
     actually shown when the toggle changes.

5. **Frequently asked questions** — centred serif heading (NOT just "FAQ"),
   ~660px wide list of three rows with a `>` chevron on the right (not `+`):
   `What is Keel and how does it work?`, `What should I use Keel for?`,
   `How much does it cost to use?`. Rows toggle open/closed with real answer
   paragraphs and rotate the chevron downward.

6. **Footer on a LIGHT background** (not dark) — Keel starburst + wordmark at
   bottom left; five columns of small grey links:
   - Products: Keel, Keel Code, @Keel, Keel Science, Keel Security, Download
     app, Pricing, Log in. Capabilities: Artifacts, Design, Connectors,
     Plugins, Skills. Extensions: Keel in Chrome, Keel for Google Workspace,
     Keel for Microsoft 365. Models: Mythos, Opus, Sonnet, Haiku.
   - Enterprise: Overview, Keel Code for Enterprise. Departments: Customer
     support, Cybersecurity, Legal, Sales. Industries: Financial advisors,
     Financial services, Government, Healthcare, Higher education, K-12
     teachers, Life sciences, Nonprofits. Programs: Keel Academy, Frontier
     Academy, Startups.
   - Developers: Developer docs, Developer blog, Console, Engineering at Keel.
     Platform: Overview, Marketplace, Keel on AWS, Google Cloud, Microsoft
     Foundry. Resources: Overview, AI academy, Webinars, Articles, Customer
     stories, Keel partner network, Events, Powered by Keel, Service partners.
     Help and security: Availability, Check files, Regional compliance, Report
     a bug, Trust & safety, Security and compliance, Status, Support center.
   - Company: Keel, Careers, Publicity, Research, Keel news. Publicity and
     Responsible AI: Responsible scaling policy, Transparency. Terms and
     policies: Privacy policy, Terms of service, Responsible disclosure
     policy, Terms of service: Commercial, Consumer terms, Data processing
     addendum, US state privacy disclosures, K-12, Usage policy.
   - Bottom: `KEEL © 2026 All rights reserved.` and small social icons.

## Functionality (all buttons must work)
- Google / Apple buttons: demo sign-in — show a short "demo only" note, set
  `localStorage.setItem("keel_logged_in", "true")`, then navigate to `/app`.
- Email input: validate a real email address (show inline error if invalid),
  then on `Continue with email` set the same flag and navigate to `/app`.
- All `Try Keel` buttons: same validated email sign-up flow (or navigate to
  the email input with focus); header `Try Keel` can scroll to plans.
- Plan toggle, FAQ accordion, Download desktop app link, and all footer links
  must work. Real hrefs only: in-page anchors, `/`, `/app`, `/download`,
  `/privacy`, `/terms`, `/notices`, `/roadmap`, `/eula`, `/trademark`,
  `/requirements`, `mailto:`. NO dead `href="#"`.
- Honour `?intent=login|signup|sales` and `?next=/path` query params where
  sensible (prefill/focus the email field, adjust button label).
- Responsive down to 390px, keyboard accessible, focus-visible states, no
  console errors.

Keep the same fonts and visual language as the existing landing page
(`ui/landing.css`) but this page has its own light footer and dedicated auth
card. Reuse the Keel starburst SVG from `index.html`.
