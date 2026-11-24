# KEEL UI/UX replica spec (working document)

Goal: reproduce the Claude marketing UI/UX shown in the operator's screenshots,
**exactly in forms, layout, spacing, typography and interaction**, on
https://keel-desktop.vercel.app, but with the brand name **Keel** everywhere.
The after-login app screen must follow the **existing Keel desktop design in the
repo** (it already does — `site/app.html` + `site/ui/style.css`), so do not
rebrand that surface to look like Claude; only make sure it is functional and
that its empty/home state matches the screenshot structure (sidebar with
New / Search / Projects / Artifacts / Plugins + Recents list; centered
"you're here" greeting; composer with `/ for skills`, attach `+`, mic and
voice controls; model selector; "Recent artifacts" card; account chip "Elios · Free").

Workspace: `C:\Users\Admin\Desktop\Claude clone`
Site root: `keel/site` (deployed at URL root by Vercel).

## Global brand mapping
- "Claude" -> "Keel" (wordmark, buttons "Try Keel", product names "Keel Code", "Keel Cowork", etc.)
- "Anthropic" -> "Keel" (footer company column, legal links, "Keel's Privacy Policy")
- Keep model names (Mythos/Fable, Opus, Sonnet, Haiku) as in screenshots.
- Keep the serif headline / editorial typography, near-white warm background,
  black ink text, black pill buttons, thin grey borders.

## Page 1 — `/` landing (`keel/site/index.html`, `ui/landing.css`, `ui/landing.js`)
Exact structure top to bottom:

1. **Header** — Keel starburst + "Keel" at left. Center/right nav:
   `Product ˅  Developers ˅  Enterprise ˅  Resources ˅  Pricing ˅  Login`
   then outlined pill `Contact sales`, then black pill `Try Keel`.
   Sticky or static as in screenshot; warm off-white background.
   Five mega dropdowns (hover + click + keyboard), anchored under triggers,
   white rounded panel with soft shadow, 4-column grid, light-grey footer bar.

2. **Hero** — two columns.
   - Left: huge serif `Question what's next` (two lines on narrow widths),
     subtitle `Your thinking partner for big ambitions`.
   - Login card (white, rounded ~16px, soft border/shadow, ~380px wide):
     * outlined button `G Continue with Google`
     * divider `or`
     * black button `Continue with email`
     * fine print: `By clicking continue, you agree to Keel's Privacy Policy and Terms of Service, and agree to receive occasional promotional emails and notifications.`
     * beneath the card, a small centred button `↓ Download desktop app` linking to `/download`.
   - Right: rounded-corner hero photo area. Use existing repo asset
     `/assets/img/keel-app.jpg` if no photo is available; keep the same
     dimensions/rounded framing so the layout matches.

3. **Explore plans** — huge centred serif heading. Segmented toggle
   `Individual | Team & Enterprise` (functional: switches active state and
   pricing copy/cards where practical). Four white rounded cards in a row,
   each with a thin line-art plant/botanical glyph at top-left, name, tagline,
   price, billing note, black `Try Keel` button and tiny "No credit card required"
   note, then a ticked feature list.
   - Free — "Try Keel" — $0 — "Free for everyone" — features:
     Limited usage every 5 hours and a limit on weekly usage (1000 billable
     hours, 120 billable monthly); Chat on web, desktop, and mobile; Search
     the web, create files, and run code; Memory across conversations;
     Connect apps and tools; Create Artifacts, Slides, Docs.
   - Pro — "For everyday work" — $17 — "Per month with annual subscription discount (billed annually)" — "Everything in Free, plus:" features:
     More usage than Free, every 5 hours; Fast, paid access with more usage;
     Hands off and schedule tasks; Keel Code; Keel Science; Projects;
     Model choice; Keel Chrome and Microsoft 365.
   - Max — "For all-day work" — $100 — "Per month" — "Everything in Pro, plus:" features:
     5x Pro usage every 5 hours and early access to new features; Higher
     limits — up to half your agency's work! New: build on the Keel Platform
     for New; $100 a month in API credits, Platform, new; Early access to
     advanced Keel features; Priority access at high traffic times.
   - Ultra — "For your largest tasks" — $200 — "Per month" — "Everything in Max, plus:" features:
     10x Pro usage every 5 hours*; 100+ Pro usage limits weekly*; $200 in
     monthly API credits, up from $100 on Max. New.
   - Footnotes below cards, centred grey fine print:
     `* Usage limits apply. How fast you reach a limit depends on the model you
     use, how long your chats are and how large your files are. * No 5-hour
     limit for verified accounts. Prices shown do not include applicable tax.
     Prices and plans are subject to change at Keel's discretion.`

4. **FAQ** — huge centred serif "FAQ", then a centred list width ~660px with
   thin top/bottom rules and a `+` on the right of each row:
   `What is Keel and how does it work?`, `What should I use Keel for?`,
   `How much does it cost to use?`. Accordion must actually expand/collapse
   with a real answer paragraph and rotate the icon to `−`.

5. **Dark footer** (#191919) — Keel starburst + wordmark; a "How can we help
   today?" input with a small orange arrow submit button (functional: filters
   footer links / FAQ, or shows results); a small floating "Latest news" chip
   with dismiss × on some pages. Columns with grey headings and stacked links:
   - **Claude -> Keel column**: Keel, Keel Code, Keel Cowork, Keel Duet,
     Keel Platform, Keel Science; `Specialized`: Keel Security, Keel Science;
     Keel in Chrome, Keel for Google Workspace, Keel for Microsoft 365,
     Login, Pricing; `Capabilities`: Artifacts, Design, Connectors, Plugins,
     Skills; `Extensions`: Keel in Chrome, Keel for Google Workspace, Keel for
     Microsoft 365; `Models`: Mythos (including Fable), Opus, Sonnet, Haiku.
   - **Enterprise**: Overview, Keel Code for Enterprise, Keel Platform,
     Customer support, Cybersecurity, Legal, Sales, Finance, Healthcare,
     Government, Higher education, K-12 education, Life sciences,
     Manufacturing, Nonprofits, Small business, Startups, Programs,
     Frontline Academy, Services.
   - **Developers**: Developer docs, Developer blog, Console, Engineering at
     Keel; `Platform`: Overview, Manuscript, Keel in AWS, Claude on AWS (use
     Keel wording), Microsoft Foundry, Managed Agents; `Resources`: Overview,
     AI academy, Keel partner network, Keel Academy, Events, Programs,
     Extended thinking with Claude Code; `Help and security`: Availability,
     Check files, Regional compliance, Report a bug, Trust centre,
     Agency and compliance, Support centre.
   - **Company**: Keel, Careers, Jobs, News, Anthropic news (use "Keel news"),
     Publicity, Responsible scaling policy, Transparency, Trust & safety;
     `Terms and policies`: Privacy policy, Terms of service, Responsible
     disclosure policy, Terms of service: Commercial, Consumer terms,
     Cookie settings, Data processing addendum, US state privacy disclosures,
     KB-000412, Usage policy.
   - Bottom bar: `KEEL 2026 All rights reserved.` social icons, `Add to
     Preferred Sources`, language selector `English`.
   All links must lead somewhere meaningful: in-page anchors, other site
   pages (`/download`, `/app`, `/privacy`, `/terms`, `/notices`, `/roadmap`,
   `/eula`, `/trademark`, `/requirements`), or `mailto:`/external-safe hrefs.

## Page 2 — `/download` (`download.html`, `ui/download-clone.css`, `ui/download-clone.js`)
Already largely cloned (uncommitted work in progress). Finish/verify:

- Hero: giant serif `Download Keel`, subtitle `Think, hand off tasks, and
  code, all in one place.` and platform buttons (Windows / Windows arm64 /
  macOS / Linux + Microsoft Store badge + QR SVG). Buttons that have no
  published installer must be visibly disabled with a clear note (per manifest).
- Nav mega dropdowns must match screenshots exactly:
  - **Product**: 4 columns — Products (Keel, Keel Code, Keel Cowork, Keel
    Duet, Keel Platform, Keel Tag; Specialized: Keel Security, Keel Science),
    Capabilities (Artifacts, Design, Connectors, Plugins, Skills), Extensions
    (Keel in Chrome, Keel for Google Workspace, Keel for Microsoft 365),
    Models (Mythos (including Fable) ↗, Opus ↗, Sonnet ↗, Haiku ↗). Footer:
    `Import to Keel` | `Download apps ↓` `Login ↗`.
  - **Developers**: `Explore here ↓` top-right; columns Build with (Keel
    Code, Keel Platform, Keel Ship, Code Review, Managed Agents) and For
    developers (Keel Academy ↗, Community, Developer blog ↗).
  - **Enterprise**: columns Enterprise (Overview, Keel Code for Enterprise,
    Keel Platform, Keel Ship), Use Cases (AI Agents, Coding, Commerce;
    Departments: Customer support, Cybersecurity, Legal, Sales), Industries
    (Financial advisors, Financial services, Government, Healthcare, Higher
    education, K-12 teachers, Life sciences, Manufacturing, Nonprofits).
    Footer: `Browse marketplace` | `Customers` `Contact sales`.
  - **Resources**: Insights (Resources, Articles, Webinars, Customer stories,
    Marketplace, Anthropic news/Keel news ↗), Learn (Keel Academy ↗, Courses
    ↗, Tutorials ↗, Use cases ↗), Connect (Events ↗, Community ↗).
  - **Pricing**: small panel `Overview`, `API`.
- Every dropdown trigger works on hover, click and keyboard (Escape closes,
  focus moves sensibly, aria-expanded updated).
- Every button/link either navigates to a real route/anchor, opens a real
  modal/toast, or is clearly disabled with an explanation. No `href="#"` dead
  ends and no JS errors.

## Functional requirements (all pages)
- No console errors. `node --check site/ui/*.js` passes.
- Login / Try Keel / Contact sales flows: clicking opens a functional
  in-page modal (email validation, "Continue" sets a `keel_logged_in` flag in
  localStorage and sends the user to `/app` or shows a success state). Google
  button can simulate the same flow with a clear "demo sign-in" note.
- Download buttons read `download.json` and stay disabled unless
  `available === true` with https url/size/sha256 (existing rule — keep it).
- Responsive: desktop, tablet and mobile (hamburger menu that actually opens).
- Accessibility: labelled buttons, focus-visible rings, aria-expanded on
  dropdowns/accordion, sensible heading order.

## Constraints
- Work only on your assigned files; do not commit, push or deploy.
- Keep local-first principles: no external network calls except same-origin.
- Preserve the existing Keel design tokens/fonts on the app page.
