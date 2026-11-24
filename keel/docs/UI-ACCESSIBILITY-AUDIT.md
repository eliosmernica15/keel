# UI accessibility audit — independent browser verification (Agent F)

**Date:** 2026-11-24 · **Worktree:** `keel-frontend-worktree` · **Branch:** `feat/frontend-unified-workspace`
**Owner:** continuous QA (exclusive ownership of `fleet-next/tests/a11y/**`, `tests/e2e/**`, this document).
**Rule:** every result below comes from a command actually run. No screen-reader claim is made.

## 1. What was added

| File | Purpose |
|---|---|
| `fleet-next/tests/a11y/playwright.a11y.config.ts` | Dedicated Chromium config on `:3302`, isolated `KEEL_DIST_DIR=.next-a11y`. `KEEL_A11Y_REUSE=1` reuses a QA-owned server to avoid cold Next compiles. Never touches `:3200` or `.next`. |
| `fleet-next/tests/a11y/helpers.ts` | Real computed-style WCAG contrast collector (foreground/background compositing, large-text threshold), accessible-name scanner, focus descriptor, themed app opener. |
| `fleet-next/tests/a11y/01-contrast.spec.ts` | Computed AA contrast on all six destinations in **both** themes. |
| `fleet-next/tests/a11y/02-focus-keyboard.spec.ts` | First tab stop, visible focus ring, 18-step focus order, palette and shared-dialog Tab traps, Escape and focus restoration, landmarks/names. |
| `fleet-next/tests/a11y/03-motion-aria.spec.ts` | `prefers-reduced-motion` on/off, ARIA roles/states, live region, status-image names, headings. |
| `fleet-next/tests/a11y/04-zoom-keyboard-walkthrough.spec.ts` | 200%-zoom proxy (720×450 CSS viewport), contrast at zoom, keyboard-only reachability of all six destinations. |

No new runtime dependency: `@playwright/test` was already a devDependency of the E2E workstream.

## 2. Results (real command output)

| Check | Command | Result |
|---|---|---|
| Static a11y source guards | `node tests/ui/verify-ui.mjs` | `{"info":1,"pass":14,"skipped":4}`, exit 0 (`A11Y-01..05` pass) |
| Focus / dialog / ARIA suite | `KEEL_A11Y_REUSE=1 npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | 9 passed / 3 failed; all focus, trap, Escape, restoration, landmarks, names, reduced-motion, ARIA and keyboard-walkthrough checks pass |
| Dark-theme contrast | same run, `CONTRAST dark:` console line | **0 violations** across six surfaces; minimum measured ratio **5.33:1**; 82–87 text nodes measured per surface |
| Light-theme contrast (initial audit) | same run, `CONTRAST light:` console line | **338 violations**: cowork 61, code 50, duet 50, fleet 57, capabilities 59, settings 61. Minimum **3.31:1**. See `QA-F-002` in `UI-DEFECT-LOG.md` |
| Light-theme contrast (lead re-test after token fix) | `npx playwright test --config tests/a11y/playwright.a11y.config.ts tests/a11y/01-contrast.spec.ts --workers=1` | **2 passed**; `CONTRAST light:` 0 violations on all six surfaces, minimum **4.87:1**. Dark theme also 0 violations. `QA-F-002` closed. |
| Reduced motion | `tests/a11y/03-motion-aria.spec.ts` | `{"matches":true,"worstAnimationMs":0.001,"worstTransitionMs":0.001,"scrollBehavior":"auto"}`; status bar shows "Reduced motion"; restoring `no-preference` removes the flag |
| Focus order | `FOCUS ORDER:` console line | Skip link first; then top-bar controls, sidebar nav, setup checklist; all 18 steps visible, no positive `tabindex` |
| Palette trap / Escape / restoration | `02-focus-keyboard.spec.ts` | 60 forward + 12 reverse Tabs stayed inside `role=dialog`; Escape closed it and restored focus to the palette trigger |
| Shared `Dialog` trap / Escape / restoration | Fleet → New agent | 24 Tabs stayed inside; Escape closed; focus returned to the trigger |
| Keyboard-only walkthrough | `KEYBOARD WALKTHROUGH:` console line | `1`–`4` reached the four work surfaces; palette reached Capabilities and Settings; `[` / `\` toggled the drawers |
| 200% zoom | `04-zoom-keyboard-walkthrough.spec.ts` | At 720×450 CSS viewport all six destinations had `documentElement.scrollWidth <= innerWidth`; the zoom-specific contrast test fails only because of the light-theme defect |
| Stress (large data) | `npx playwright test tests/e2e/08-stress.spec.ts --workers=2 --reporter=line` | **3 passed**. 1200-row transcript: 0 idle mutations, 9 frames, 9 ms script, 23 130 DOM nodes. 400 agents: 0 mutations, 10 frames, 11 ms script, 12 380 nodes. 1600-node tree: 0 mutations, 13 frames, 1 ms script, 12 577 nodes |
| Network / broken routes | `tests/e2e/10-network-routes.spec.ts` | `NETWORK failed=[] httpErrors=[]`; all 13 read-only BFF endpoints HTTP 200; unknown path returns real 404 |
| Tour-command regression | `tests/e2e/11-tour-command.spec.ts` | Passed; real storage order `[["keel-onboarding:step","\"tour\""],["keel-onboarding-done","false"]]` |

## 3. Screenshots inspected

72 screenshots were regenerated at `tests/e2e/screenshots/themes/<dark|light>/<WxH>/<destination>.png`
(6 viewports × 6 destinations × 2 themes) with `tests/e2e/09-theme-viewports.spec.ts`.
A contact sheet per theme×viewport was generated with PIL under
`tests/e2e/screenshots/themes/contact-sheets/` and **all 12 sheets were opened and visually inspected**.
No horizontal overflow or whitespace-only surfaces were observed; at 360/390/768/1024 px the drawers start
closed and the workspace fills the viewport; at 1280/1440 px both drawers are open. The light-theme sheets
visibly confirm the low-contrast grey/orange text recorded by the computed audit (QA-F-002).

## 4. Method and limitations

- **Contrast** is computed from `getComputedStyle`: text colour, ancestor background colours composited until an
  opaque layer is found, WCAG relative luminance, thresholds 4.5:1 (normal) and 3:1 (large ≥24 px or ≥18.66 px bold).
  Elements with `aria-hidden`, `sr-only`, zero opacity, disabled state or no opaque background are skipped; Code/Duet
  reported 14 such text nodes (`unknown`) per surface. Gradient/image-painted backgrounds cannot be computed from
  computed styles and are excluded rather than guessed.
- **200% zoom** is approximated by halving the CSS viewport (1440×900 → 720×450), which is the layout a browser
  zoom of 200% produces. Browser-native zoom controls are not exposed by Playwright; no claim about OS-level
  magnification or reflow at fractional zoom is made.
- **Screen-reader announcements** were not verified with NVDA/JAWS/VoiceOver; only ARIA roles, names, states and
  the presence of an `aria-live="polite"` region were checked.
- **Bridge 504s** (`QA-F-003`) intermittently trip the strict console gate in shared-bridge runs even when all
  functional assertions inside a test pass. They are recorded as an environmental/backend reliability finding,
  not treated as an accessibility pass.
- System theme and first-paint flash remain outside this audit's direct measurement.

## 5. Final completion round — new components (static review; runtime re-test pending)

Read-only review of the components added by the other owners this round:

| Component | Keyboard / names / states observed in source | Honest-state rule |
|---|---|---|
| `cowork/Search.tsx` | `<section aria-label="Conversation search">` (region), labelled input with `aria-keyshortcuts`, labelled Previous/Next/Close buttons, `aria-current` on the active result, live match count | Search is explicitly client-side over rows already loaded — no invented backend call. **Defect QA-F-013:** Escape is bound only to the input, so it stops working after a nav button takes focus. |
| `cowork/LiveStream.tsx` | Stream buffer isolates the token-level re-render to one bubble; history is not re-rendered per token | No stream text is invented; deltas come only from SSE rows. |
| `cowork/Cowork.tsx` windowing | `WINDOW_SIZE=150`, visible "Show earlier messages — N of M hidden" control; search indexes all loaded rows and expands the window | Rows outside the window are not rendered as if absent; the count is shown. Export link is a real download; Import is `disabled` with `aria-describedby` and an explicit note. |
| `fleet/Board.tsx` | Five column `role=region`s named from the real `fleet_tasks.status` values; per-card labelled status/assignee selects | Unknown statuses are counted and shown as outside the known set, never relabelled. |
| `fleet/OrgChart.tsx` | Status region explains the missing hierarchy; only row-derived delegation edges with named actions | States plainly that `parent_id` and a hierarchy route do not exist; no tree is fabricated. |
| `fleet/LiveWall.tsx` | Cards labelled `Agent <name> activity`, activity badge/dot, explicit "not reported" copy | No `bots.state` column exists; agents with no reported activity stay "not reported". |
| `fleet/CostPanel.tsx` | Table column headers with `scope="col"`, row headers with `scope="row"` | Dollar figures only from a real `cost_usd`; token counts are labelled "not cost". |
| `onboarding/HelpCenter.tsx` | `role="dialog" aria-modal="true"` labelled by a real heading; window-capture Escape/Tab trap with focus restoration; labelled action buttons | Both registries are read live on open; the page cannot start a bridge, grant trust or store a key. |
| `duet/reviewPair.tsx` | Builder/reviewer cards with explicit identity facts, `Badge` states ("Comment-only"/"Builds"), labelled review findings | Reviewer role comes only from reported `role` text; an absent reviewer is "not configured by this bridge"; status is labelled as inferred from a real row. No edit/write/execute control is rendered. |

Runtime a11y re-verification of these components requires a clean app build; the first attempt was
blocked by QA-F-009 (CSS Module `CssSyntaxError` → `GET / 500`), which the colleague fixed at 5:41 PM.
Re-run `KEEL_A11Y_REUSE=1 npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1`
after the concurrent owner suites finish; results are recorded in `UI-TEST-MATRIX.md`.

