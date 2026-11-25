# Agent 45 — Accessibility & visual quality evidence

- Branch: `agent/f-accessibility` (based on baseline `8867e73`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\final\accessibility`
- Owned files touched: `keel/site/app.html`, `keel/site/ui/style.css`
- New test: `keel/tests/test_accessibility_hardening.py`
- No JavaScript was edited.

## Method (local self-check, not an audit)

Reviewed `app.html` and `style.css` statically for accessible names, landmark
structure, focus indicators, live regions, keyboard operability, reduced-motion
support and hardcoded colour pairs. Added a dependency-free regression test that
parses the HTML/CSS with Python's standard library (`html.parser`, `re`) — no
browser, axe, or screen reader is involved. Cross-checked interactive elements
against `keel/site/ui/app.js` (read-only) before changing element types.

## Defects found and fixed

Line numbers below refer to the fixed files.

| # | Location | Defect | Fix |
|---|----------|--------|-----|
| D1 | `app.html:50-52` (was 50-52) | `New session`, `Customize Keel`, `Take the tour` were `<a tabindex="0">` with no `href`. Browser does not synthesise `click` on Enter for href-less anchors, so these primary commands were mouse-only. | Converted to `<button type="button">`; existing `click` listeners in `app.js` are unchanged and still fire. Added `aria-label="Main"` to the surrounding `<nav>`, and extended `.nav a` CSS to `.nav a, .nav button` (`style.css:219`). |
| D2 | `app.html:71, 80, 87, 93` (four `ctx-sub` rows) | Context-menu submenu triggers were hover-only `<div>`s. Their flyouts are `display:none` until `:hover`/`:focus-within`, but the triggers had no tab stop, so keyboard users could never reveal "Open in / Move to section / Add to project / Move to group". | Added `tabindex="0" role="menuitem" aria-haspopup="menu"` to all four. `:focus-within` now fires on the trigger itself, revealing the flyout; Tab then enters the flyout's real buttons. |
| D3 | `app.html:219-221` | Three permission-mode selectors in `#pop-perm` were clickable `<div>`s with no tab stop or role. | Converted to `<button type="button" class="pop-item" data-mode="…">`. `app.js:880` (`querySelectorAll("#pop-perm .pop-item")`) and `app.js:2273-2277` (click delegation via `closest(".pop-item")`) work unchanged on buttons. |
| D4 | `app.html:481`, `app.html:627` | `#policy-editor` and `#caps-params` textareas had only `placeholder` text — no accessible name. Placeholders are not accname sources. | Added `aria-label="Policy document (JSON)"` and `aria-label="Module invocation parameters (JSON)"`. |
| D5 | `app.html:297-312` and the other 15 settings panes | `role="tabpanel"` sections had no accessible name. | Added `aria-label` to all 16 panes. |
| D6 | `app.html:321` | `#vim-status-text` had two `class` attributes (`fine`, `vim-status`); the second was ignored by the parser, so the vim status style never applied. | Merged into `class="fine vim-status"`. |
| D7 | `app.html:16`, `app.html:134`, `style.css:175-178` | No skip link; keyboard users had to tab through the whole toolbar/sidebar to reach main content. | Added `<a class="skip-link" href="#main-content">`, `id="main-content" tabindex="-1"` on `<main>`, and a visually hidden `.skip-link` that appears on `:focus` using `var(--accent)`/`var(--on-accent)`. |
| D8 | `app.html:189, 192-193` | `chip-env`, `chip-folder`, `chip-perm` used `aria-haspopup="true"` (announced as "menu") while their popovers are `role="dialog"`. | Changed to `aria-haspopup="dialog"`. |
| D9 | `style.css:808` (was 801) | `.ctx-item:focus-visible { outline: none }` removed the focus ring from every context-menu item — keyboard focus had only a faint background change. | Split the rule: hover keeps the background; `:focus-visible` gets `outline: 2px solid var(--hl); outline-offset: -2px`. |
| D10 | `style.css:326, 364, 509, 549, 754, 687` | Six text inputs explicitly set `outline: 0`/`outline: none` (prompt textarea, code input, settings search, instructions, folder search, model filter). With the native outline removed, several had no replacement focus indicator. | Removed those declarations so the global `:focus-visible` 2px ring (already present at `style.css:173`) applies. Container `:focus-within` highlights remain as a secondary cue. |
| D11 | `style.css:303, 336, 372, 581-582, 814, 881-883, 892, 899, 923` | Dark-theme-only hex text colours on controls that also render in the light theme. Worst case `.send` used `#f7f3e8` on a translucent near-white background in light theme (~1.2:1). Others: `#ddd8c4` (tag), `#cfc9bd` (footer chips), `#f0b9a8`/`#f7cdbf` (danger buttons, tour status), `#000`/`#171310` on `var(--accent)` (caps Invoke, Approve, badges). | Replaced with themed tokens: `var(--text)`, `var(--danger)`, `var(--on-accent)`, `var(--accent)`, `var(--ok)`. No raw dark-only text hex remains on shared controls. |
| D12 | `style.css:62` | Several rules use `font: … var(--sans)` but `--sans` was never defined, making those shorthand declarations invalid (safe-mode badge, caps panels, quick panel). | Defined `--sans: Inter, system-ui, sans-serif` on `:root` so those panels inherit the intended font/size — a layout-consistency fix. |

### Colour spot-check (computed from the token hex values)

| Pair | Ratio |
|------|-------|
| dark text `#f2f0ea` on `#0a0605` | 17.70:1 |
| dark muted `#8a8279` on `#0a0605` | 5.33:1 |
| light text `#241f1a` on `#f7f4ef` | 14.89:1 |
| light muted `#6f685f` on `#f7f4ef` | 5.01:1 |
| dark `on-accent` `#171310` on `#e6d54c` | 12.30:1 |
| light `on-accent` `#f7f2e6` on `#8a5a07` | 5.30:1 |
| light danger `#c2432c` on `#f7f4ef` | 4.63:1 |

All are >= 4.5:1. The check is token-level only, not a computed-style audit of
translucent glass layers.

## Tests added

`keel/tests/test_accessibility_hardening.py` — 11 static regression tests:

1. `test_every_button_has_an_accessible_name` — all 110 `<button>` elements resolve a name via aria-label/labelledby/text/title/alt.
2. `test_form_controls_have_labels_or_aria_names` — label `for`, wrapping `<label>`, or aria-name for every visible input/select/textarea.
3. `test_landmarks_language_and_skip_link` — `lang`, `<title>`, main/nav/aside/footer/h1, named tabpanels, skip-link target.
4. `test_no_duplicate_ids_or_attributes` — catches regressions like D6.
5. `test_focus_indicators_are_defined_and_not_suppressed` — global and component `:focus-visible` rules must define a visible outline/box-shadow and never `outline:none`; guards D9/D10; skip link appears on focus.
6. `test_streaming_and_status_live_regions_present` — `aria-live="polite"` on both threads plus the visually hidden `role="status" aria-atomic="true"` region.
7. `test_controls_are_keyboard_operable` — nav commands are buttons; submenu triggers have tab stop/role/haspopup; permission modes are buttons; no inline event handlers.
8. `test_dialogs_and_popups_have_accessible_names` — all dialogs named; chips announce `dialog`.
9. `test_known_colour_tokens_meet_spot_check` — the seven pairs above at >= 4.5:1.
10. `test_no_dark_theme_only_hex_on_shared_controls` — guards D11 with selector-scoped regexes.
11. `test_reduced_motion_is_supported` — media query and `body.reduce-motion` rule both present.

### Results

```
cd keel && python -m pytest tests/test_accessibility_hardening.py tests/test_accessibility_ui.py -q
.................                                                        [100%]
17 passed in 2.62s

cd keel && python -m pytest tests/test_accessibility_ui.py \
  tests/test_accessibility_hardening.py tests/test_tutorial_ui.py \
  tests/test_screen_safe_mode.py tests/test_policy_ui.py tests/test_settings.py -q
.....................................................                    [100%]
53 passed in 5.76s
```

`test_accessibility_ui.py::test_js_syntax` also passed — confirming no JS was
changed or broken. No tool failures occurred.

## JS changes referred to the lead (not made here)

I do not own `app.js`. One real keyboard defect remains and needs a JS owner:

- **Modal dialogs never move focus into themselves and do not trap Tab.**
  `openSettings` (`app.js:1665-1669`), `openFsPicker` (`app.js:2105-2113`),
  `openCaps` (`app.js:2516-2523`), `openTour` (`app.js:2706-2714`) and
  `openWhatsNew` (`app.js:2743`) only unhide their overlays; no `focus()`,
  `inert`, dialog `showModal()` or Tab-trap exists anywhere in the file. Focus
  stays on the trigger behind `aria-modal="true"`, and Tab can reach the
  background UI. Close functions (e.g. `closeSettings`, `closeFsPicker`,
  `closeCaps`, `closeTour`) do not restore focus to the trigger.
  Suggested fix in JS: on open, remember `document.activeElement`, focus the
  first focusable descendant (or the dialog itself with `tabindex="-1"`), set
  `inert` on `.app` while the dialog is open, intercept Tab within the dialog,
  and on close restore the saved focus. Alternatively use native
  `<dialog>.showModal()`/`close()` for these overlays.

- Minor, optional: `#usage-ring` (`app.html:191`) is `role="status"` with only a
  `title` updated by JS; title changes are not reliably announced. If live
  accounting should be spoken, have JS write text into a visually hidden child
  (the existing `#a11y-live-region` at `app.html:594` is available).

## Explicit limitation statement

This is a **local static self-check only**, not a formal WCAG 2.x conformance
audit and not a certification. No real browser, screen reader, zoom test, or
computed-style engine was used. Colour contrast was evaluated on token hex
values only; translucent "glass" layers, images, gradients, focus/mouse/hover
states and platform font rendering were not measured. Focus-visible styling was
verified by rule inspection, not by observing focus order. JS-created nodes
(recents, model lists, folder rows, tour dots) were reviewed for pattern
correctness but not exercised. The JS modal-focus defect above is documented,
not fixed, and must be handled by the `app.js` owner.
