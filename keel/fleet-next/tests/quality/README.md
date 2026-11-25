# Agent F — shared QA, frontend finalization round (2026-11-25)

Worktree `keel-frontend-worktree`, branch `feat/frontend-finalization-2026-11-25`.
QA owns this directory only; no feature/screen, backend, site, marketing or git
changes were made. Tests use an isolated Next dev server on `:3306` with
`KEEL_DIST_DIR=.next-quality`, so the lead's `:3000`/`:3200`, E2E `:3300` and
a11y `:3302` servers are untouched.

## Commands actually run and results

| Check | Exact command | Result |
|---|---|---|
| TypeScript (baseline, before concurrent edits) | `npx tsc --noEmit --incremental false` | exit 0, no output |
| TypeScript (final, plain) | `npx tsc --noEmit --incremental false` | **exit 2**: 4 × `TS6053` for stale `.next/types/**/*.ts` paths matched by the auto-added include in lead-owned `tsconfig.json` |
| TypeScript (source, generated dirs excluded) | `npx tsc --noEmit --project tests/quality/tsconfig.qa.json` | exit 0, no output |
| QA identity/theme suite | `npx playwright test --config tests/quality/playwright.quality.config.ts tests/quality/01-identity-theme.spec.ts --workers=1 --reporter=line` | **6 pass / 1 fail** (the system-fallback defect below) |
| QA shared primitives | `npx playwright test --config tests/quality/playwright.quality.config.ts tests/quality/03-shared-primitives.spec.ts --workers=1 --reporter=line` | **2 pass** |
| QA fresh responsive shots | `npx playwright test --config tests/quality/playwright.quality.config.ts tests/quality/02-responsive-shots.spec.ts tests/quality/03-shared-primitives.spec.ts --workers=1 --reporter=line` | **73 pass / 1 fail** (the failure was a QA test role assumption, fixed and re-run green) |
| QA layout widths | `npx playwright test --config tests/quality/playwright.quality.config.ts tests/quality/04-layout-widths.spec.ts --workers=1 --reporter=line` | **2 fail** (the editor-squeeze defect below; re-run after concurrent Code/Duet edits, still failing) |
| Existing a11y suite | `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | **12 pass / 0 fail** |
| Existing responsive suite | `npx playwright test tests/e2e/07-responsive.spec.ts --workers=1 --reporter=line` | **36 pass / 0 fail** |

## Verified green

- **Obsidian & Gold identity**: dark tokens `--outer #0a0605`, `--accent #e6d54c`, `--text #f2f0ea`; light `--outer #e9e9e7`, `--accent #8a5a07`, `--text #141414`. Skip link/primary gold `rgb(230,213,76)` dark and `rgb(138,90,7)` light; Inter body font; canvas is never a flat gold fill. Semantic status tokens correct in both themes.
- **Themes**: dark/light explicit, `system` follows `prefers-color-scheme` and reacts to a *live* OS change (light → dark) via the `matchMedia` listener. Settings' theme `SegmentedControl` uses roving tabindex (`0,-1,-1`) and arrow keys.
- **Theme/reduced-motion before first paint**: an injected HTML-parse probe (after the inline `themeInit`, before hydration) recorded `theme=light,colorScheme=light` for a saved light theme even with OS dark, and `reducedMotion=true` with OS reduce. No first-paint flash for saved preferences.
- **Contrast**: a11y suite dark 0 violations (min 5.33:1), light 0 violations (min 4.87:1), six destinations each.
- **Focus/keyboard**: skip link first; 18-step focus order with no positive tabindex or off-screen stop; visible 2px gold focus ring (Settings text field measured `2px solid rgb(230,213,76)`); palette trap 60 forward + 12 reverse Tabs; shared `Dialog` traps (Fleet 24 Tabs, Settings 20 Tabs), Escape closes and focus is restored; controls all have programmatic names; landmarks present on all six surfaces.
- **Reduced motion / zoom**: `worstAnimationMs=0.001`, `worstTransitionMs=0.001`, `scrollBehavior:auto`; 720×450 (200% zoom proxy) no document overflow and keyboard walkthrough reaches all six destinations.
- **Responsive**: 72 fresh screenshots (6 viewports × 6 destinations × 2 themes) under `screenshots/<theme>/<WxH>/<dest>.png`; all 12 contact sheets under `screenshots/contact-sheets/` were **opened and visually inspected** (not merely saved). No horizontal overflow, no blank/whitespace-only surface; drawers closed at 360–1024 px and open at 1280/1440 px.

## Defects routed to the lead

### QA-F-019 — system fallback overridden after hydration (Medium)
- Owner/file: shared state owner — `keel/fleet-next/lib/state.tsx:53` (`useState<Theme>("dark")`) and `:72` (`readStored("keel-theme-v2", "dark", …)`).
- Repro: OS `prefers-color-scheme: light`, **no** `keel-theme-v2` key. Pre-paint probe = `light`; after `AppProvider` hydration `data-theme=dark`. First-run users whose OS is light get a dark flash/wrong theme.
- Expected: default to `system` (the inline script already resolves it). Explicitly saved `system` works correctly; only the absent-key fallback is wrong.
- Evidence: `NO STORED THEME: paint={"theme":"light",…} after=dark`; test `01-identity-theme.spec.ts:88`.

### QA-F-020 — Code/Duet editor collapsed by two simultaneous right panels (High)
- Owner/file: Code/Duet feature owners — `features/code/Code.tsx:337-410` (explorer + feature right panel always open when `!narrow`) with the shell right panel `app/ui.css:363-369` and default `rightWidth` in `lib/state.tsx:58`; Duet equivalent `features/duet/Duet.tsx:534-635`.
- Repro: 1280×800 or 1440×900, Code surface, both shell Context and feature Review/Context panels open.
- Measured: 1280 → `canvas=668, shellRight=340, codeMain=42, codeRight=352, emptyBox=48`; 1440 → `canvas=828, shellRight=340, codeMain=202`. Screenshot `screenshots/dark/1280x800/code.png` shows "No pro ject selected" wrapped one word per line and an unusably narrow editor.
- Existing `07-responsive.spec.ts` passes because it only checks *document-level* overflow; inner canvas collapse is invisible to that gate.
- Evidence: test `04-layout-widths.spec.ts` (2 fail; re-run after concurrent Code/Duet edits, still failing).

### TS-ENV-001 — stale generated type paths in tsconfig (Low, hygiene)
- Owner/file: lead — `keel/fleet-next/tsconfig.json` include patterns `.next/types/**/*.ts` (auto-added by `next dev` for several QA dist dirs).
- `npx tsc --noEmit` fails with `TS6053` when a build removes those generated files; source type-checking passes (`tests/quality/tsconfig.qa.json`). Two earlier type errors seen mid-run (`features/fleet/AgentDetails.tsx:355`, `tests/features/fleet/fixtures.ts:244`) were concurrent in-flight owner edits and are now resolved.

## Limitations
- No NVDA/JAWS/VoiceOver run; only ARIA roles/names/states and live regions were checked.
- 200% zoom is the documented 720×450 CSS-viewport proxy, not browser-native zoom.
- Contrast is computed from `getComputedStyle` with ancestor compositing; gradient/image-painted backgrounds are excluded (14 `unknown` nodes on Code/Duet).
- Bridge 504 console noise (QA-F-003/011) remains environmental; this round's suite runs saw no failures from it.
