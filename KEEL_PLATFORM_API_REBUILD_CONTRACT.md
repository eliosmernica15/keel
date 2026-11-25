# KEEL Platform page — EXACT rebuild contract (from the user's screenshot)

Reference image: `C:\Users\Admin\Downloads\screencapture-claude-platform-api-2026-11-24-23_29_16.png` (1920 × 19952). Read it with the `read` tool; cropped sections are in `C:\Users\Admin\AppData\Local\Temp\opencode\ref-*.png`. This is the ONLY source of truth. Do NOT fetch claude.com — the live site has changed and is not the reference.

Brand mapping: Claude → KEEL, Anthropic → KEEL, Try Claude → Try KEEL. Keep model family names and version numbers EXACTLY: Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5.

Files: `keel/site/platform/api.html` (and `keel/site/platform/api/index.html` copy), `keel/site/ui/platform-api.css`, `keel/site/ui/platform-api.js`, `keel/site/assets/img/platform/*.svg`. Same paths as before; overwrite them.

Body class `pa-body`; all classes prefixed `pa-`. Link `/ui/platform-api.css` and defer `/ui/platform-api.js`.

## Exact page structure (top → bottom)

1. **Header** — KEEL starburst + "KEEL" left; nav `Product ˅ Developers ˅ Enterprise ˅ Resources ˅ Pricing ˅ Login`, then outlined `Contact sales`, black `Try KEEL`. Warm off-white, thin bottom border. Five mega dropdowns.
2. **Sub-header bar** — left small text `KEEL Platform`; right `Explore here ^` control opening a white floating panel with two items: `Ask questions about this page` and `Copy as markdown`. (This replaces the old vertical rail.)
3. **Hero** — two columns. Left: small grey eyebrow `KEEL Platform`; huge Georgia serif h1 **"Build frontier agents on the KEEL Platform"** on two lines; subtitle `Frontier models, harnesses, context management, and infrastructure designed to work together.`; black pill `Start building` and light-beige pill `Contact sales`. Right: hand-drawn illustration of a hand placing a terracotta block onto a stack of outlined cubes (transparent background).
4. **Trusted by** — centred small serif label `Trusted by`, then a single row of 8 logos: Lovable, GitLab, Notion, Rakuten, Thomson Reuters, Brex, Cognition, Zoom.
5. **Models** — tiny umbrella line glyph centred above h2 `KEEL models for every job`. Four white cards with hairline borders and generous padding:
   - **Fable 5.2** — "Next generation intelligence for long-running agents" — bullets Multi-day autonomous projects / Expert-level work for frontier research — Prompt caching: Read $0.20, Write $10 /MTok — Input $8, Output $40 /MTok — black full-width `Explore Fable` button.
   - **Opus 5.5** — "Daily driver for agentic coding and enterprise work" — Long-horizon coding and large migrations / Multi-step agents across enterprise tools and data — Read $0.20, Write $5 — Input $4, Output $20 — `Explore Opus`.
   - **Sonnet 5.5** — "High-performance model for coding and agents" — Everyday coding and developer loops / Customer-facing agents and multi-tool workflows at scale — Read $0.10, Write $2.50 — Input $2, Output $10 — `Explore Sonnet`.
   - **Haiku 5.5** — "Fastest, most cost-effective model" — Real-time, latency-sensitive product experiences / Sub-agents inside larger multi-model systems — Prompt caching: ≤100K Read $0.01, Write $0.125; >100K Read $0.05, Write $0.625 — Input: ≤100K $0.10, >100K $0.50 — Output: ≤100K $0.50, >100K $2.50 — `Explore Haiku`.
   - Beige rounded banner below cards: `Save 50% with batch processing. Learn more` left, `Batch processing` label + functional toggle switch right.
   - Three centred fine-print lines with links about US-only inference (1.1x), fast mode (2.5x for Opus 5.5 and Fable 5.2 at 2x), and 5-minute prompt caching TTL.
6. **APIs designed for KEEL** — small lightning-bolt glyph above h2. Two columns of 10 checkmarked features with bold label + 1–2 line description: Code execution, Structured outputs, Tool use, Computer use, Citations, Files, Context window, Compaction, Context editing, Web search and fetch (use the descriptions from the live Claude page — they match the screenshot). Right side: floating white `Customer story` card with Atlassian logo, `5 million` / "AI agents running in customer business workflows each month", Vibecode logo, `10x` / "faster to build production agents".
7. **Managed Agents** — flag glyph, small `BETA` badge, h2 `Power your most ambitious workflows with KEEL Managed Agents`, subtitle `Build and deploy long-running agents at scale.`, black `Learn more` + light `See features →|` buttons. Large rounded light panel with a play button in the centre and a thin faux IDE/status strip at the bottom.
8. **Three stacked rows** with hairline separators, icon + bold label left, description right: `Security by design` / "Credentials stay out of the sandbox, encryption is built in, and state persists automatically."; `Observable end to end` / "Session tracing records what every agent did and why, with built-in analytics to improve agent performance."; `Built for KEEL` / "The underlying harness is optimized for KEEL. As the model improves, your agents improve with it."
9. **Extend and customize** — gears glyph, centred sentence-case heading `Extend and customize what KEEL can do.` Three columns separated by hairlines, each with a small line icon, bold label, description, and a small outlined pill link: `Model Context Protocol (MCP)` / "Connect KEEL to your tools and data through the open standard for AI integrations." / `Explore MCP`; `Skills` / "Teach KEEL your expertise, procedures, and best practices through pre-built or customizable skills." / `Learn more`; `Memory stores` / "Agents remember across sessions, keeping memory files on your infrastructure." / `Learn more`.
10. **KEEL Marketplace** — wide rounded panel, left muted-sage area with a 3×3 grid of app-icon tiles, right warm-cream area with serif `KEEL Marketplace`, text `Use your existing KEEL commitment to pay for KEEL-powered solutions from our partners.`, outlined `Explore partners` pill.
11. **Enterprise** — building glyph, h2 `Built for enterprise workloads`, subtitle `Controls and safeguards for your data.` Three columns with icon, bold title, description, small outlined pill: `Enterprise Frontier Safeguards`, `Residency`, `Your data stays yours`. Then a row of 4 small line glyphs, then a rounded outlined panel with cloud icon and `Available on all major cloud providers` + supporting text mentioning AWS, Google Cloud, Microsoft Foundry.
12. **Cost** — speedometer glyph, h2 `Control cost and performance`, black `Read documentation` button. Left column of 4 checkmark rows with label + description: Batch processing, Prompt caching, Effort, Advisor strategy (beta). Right floating white `Customer story` card: `Batch processing`, Quora logo, quote, `Read more` pill.
13. **Console** — glyph, h2 `Observe and manage your agents with the KEEL Console`. Large rounded sage-green panel with subtle star pattern containing two dark code panes: small left "Build your request" pane and large right prompt pane (ticket-classification prompt). Below, four columns with icons: `Build`, `Deploy`, `Monitor`, `Manage` with the corresponding descriptions.
14. **Testimonials** — speech-bubble glyph, h2 `See why businesses build on the KEEL Platform`. Three white-outlined quote cards side by side (Datadog, GitHub, Cognition) with exact quotes from the screenshot and author lines. Below: left arrow button, 19 small dots (first active), right arrow button.
15. **Resources** — scribble glyph, 8 outlined cards in 2 rows × 4 columns with titles and a small link-type label (`Blog`, `Docs`, `Cookbook`): Reducing cost and improving performance with KEEL Platform; Demystifying evals for AI agents; KEEL Cookbook: Practical guides and examples for using KEEL effectively; KEEL Managed Agents overview; CLI, SDKs, and libraries; Building agents that reach production systems with MCP; Scaling Managed Agents: Decoupling the brain from the hands; Effective harnesses for long-running agents.
16. **Dark CTA band** — h2 `Build on the KEEL Platform` (serif, white), light `Start building` + dark-grey `Read documentation` buttons; right dark newsletter card with bell icon, `Get the developer newsletter`, descriptive copy, email input with white circular arrow submit, fine print.
17. **Footer** — black. KEEL starburst + wordmark; `How can we help today?` search input with small terracotta arrow button; 4 link columns (Products, Enterprise, Developers, Company) with grey subheadings; bottom bar `KEEL 2026 All rights reserved.`, socials, `Add to Preferred Sources`, `English` selector.

## Interaction contract (all buttons functional)

- Nav mega dropdowns: hover/click/keyboard, Escape, aria-expanded, one open at a time.
- `Explore here` toggles its white panel; `Ask questions about this page` opens a modal with an input that searches page text and shows matching sections (or a toast); `Copy as markdown` copies a plain-text outline of the page to clipboard with fallback toast.
- `Start building`, `Try KEEL` → auth modal (Google demo sign-in note, email validation, `keel_logged_in` flag, success state with `/app` link, no auto-navigate).
- `Contact sales` → contact modal with validation + success toast.
- Model `Explore X` buttons → modal with that model's full pricing and features (use the exact numbers above).
- Batch-processing toggle actually toggles state and swaps the banner copy (50% savings on/off).
- All "Learn more"/"Explore MCP"/"Read more"/"Read documentation" pills open an info modal or navigate to a real site route — no dead clicks.
- Managed Agents play button opens a modal with a simulated player state and a note; `See features` scrolls to the three rows.
- Marketplace `Explore partners` and resource cards open info modals or navigate to real existing site routes.
- Testimonials: 3-at-a-time carousel with 19 dots, arrows, keyboard, wrap, autoplay paused on hover/focus and disabled under reduced motion.
- Newsletter form validates email and shows success toast; footer search filters footer links and shows clickable results; no dead links anywhere.
- Copy actions use `navigator.clipboard` with `execCommand` fallback and a clear toast.
- No console errors, no external network calls, `node --check` passes.

## Visual tokens

Warm off-white `#f7f6f2` / `#faf9f5` sections, white cards, hairline `#dedcd6` borders, ink `#191919`, muted `#6b6a66`, terracotta `#d97757`, light-beige pill `#e8e5db`, sage-green `#b9cdc5` console panel, black `#191919` CTA/footer. Georgia serif headings (~56–64px h1, ~44px h2), Inter body ~15px. Very generous vertical whitespace, centred section glyphs above headings, small outlined pill buttons, black pill CTAs. Responsive at 1100/900/640, reduced-motion support, `body.pa-body` scoping, `aria-*` and focus-visible throughout.

## Asset list (reuse filenames where possible, redraw to match)

`pa-mark.svg` (KEEL starburst), `pa-hero-blocks.svg` (hand-drawn hand placing terracotta block on outline cube stack), 8 customer logos (`pa-logo-lovable.svg`, `pa-logo-gitlab.svg`, `pa-logo-notion.svg`, `pa-logo-rakuten.svg`, `pa-logo-thomson-reuters.svg`, `pa-logo-brex.svg`, `pa-logo-cognition.svg`, `pa-logo-zoom.svg`), `pa-logo-atlassian.svg`, `pa-logo-vibecode.svg`, `pa-logo-quora.svg`, `pa-logo-datadog.svg`, `pa-logo-github.svg`, 9 marketplace app tiles (`pa-app-1.svg` … `pa-app-9.svg`), and section glyph SVGs (`pa-glyph-umbrella.svg`, `pa-glyph-bolt.svg`, `pa-glyph-flag.svg`, `pa-glyph-gears.svg`, `pa-glyph-building.svg`, `pa-glyph-speed.svg`, `pa-glyph-console.svg`, `pa-glyph-chat.svg`, `pa-glyph-scribble.svg`, `pa-glyph-bell.svg`). Optional existing icon SVGs may be reused.
