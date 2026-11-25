# KEEL Code page — QA checklist (second wave)

Use this when reviewing the built page at `/product/keel-code`.

## Environment
- Local QA server: `node serve_keel_site.mjs` serves `keel/site` at
  `http://localhost:3100` with Vercel-like rewrites.
- Target page: `http://localhost:3100/product/keel-code`
- Reference copy: `https://claude.com/product/claude-code`
- In-app browser: load the `browser` skill first, then use `tools.browser.*`
  (tab IDs from `tabs.open`; `console` for errors; `snapshot` for controls;
  `screenshot` for visual review; `evaluate` for DOM assertions).

## Visual / structural checks
1. Full page renders top-to-bottom in this order, with no missing art:
   header + breadcrumb, hero + two app previews, connector logo strip,
   Get started (Team & Enterprise default) with toggle, announcements (3),
   What Keel Code can take on (terminal + 3 features), Meets you where you
   code (3 art cards), Slack band, testimonials (3) + logo cloud + note,
   FAQ (7), technical rundown (6 resources), dark CTA + newsletter,
   dark footer, news chip, auth modal.
2. Warm editorial look: #f5f4ef page, Georgia serif display headings,
   black pill buttons, thin grey rules, white cards, generous whitespace.
3. Three where-you-code card artworks are visibly distinct (orange terminal,
   dark IDE with green diff, blue browser panel). No broken image icons.
4. Tablet (~800px) and mobile (~390px) stack cleanly; hamburger opens.
5. No horizontal overflow at any width.

## Interaction checks (click each, confirm a visible result)
- All five mega dropdowns: hover, click, keyboard; Escape closes.
- Mobile hamburger opens/closes; Escape closes.
- Hero "Download for macOS" -> /download; "Read documentation" -> /requirements.
- All 8 `data-way` buttons -> real modal with copy; close via ×, backdrop, Escape.
- "View changelog" -> modal with the 3 dated features.
- Plan toggle switches Team & Enterprise <-> Individual panels.
- Get Team plan / Get Enterprise plan / Try Keel -> auth modal.
- "Get Keel Code" buttons scroll to #get-started.
- Terminal tabs Onboarding / Triage / Migrate change the transcript; arrow keys work.
- Copy buttons copy command, show "Copied" and a toast.
- VS Code / JetBrains / Add to Slack buttons -> modals.
- Testimonial "Read story" and resource cards -> real routes.
- FAQ accordion: one open at a time, +/- icon, aria-expanded correct.
- Newsletter: invalid email shows error; valid email shows success + toast.
- Footer help search filters links/FAQ; Clear search restores.
- News chip dismiss works and persists on reload.
- Language select, "Add to Preferred Sources", all footer links -> real targets.
- Auth modal: invalid email error; valid email sets localStorage flag and
  offers "Continue to Keel" -> /app.
- No `href="#"` and no button with no handler.

## Error checks
- `tools.browser.console({ level: 'error' })` is empty after load and after
  each interaction.
- `network.list` shows no failed (4xx/5xx) same-origin requests.
- `node --check keel/site/ui/keel-code.js` passes.
- `node verify_keel_code_ui.mjs` passes.

## Brand checks
- Search rendered text and source for "Claude", "Anthropic", "CLAUDE.md".
  All must be "Keel", "Keel", "KEEL.md" respectively.

## Reporting
Report findings as a prioritized list with exact selectors/sections and a
clear PASS/FAIL per item. Do NOT edit files in this review pass.
