# Keel Code product page

`keel-code.html` is the KEEL-branded replica of the Claude Code product page. It
is served at **`/product/keel-code`** (the clean URL is rewritten to the HTML
file, and direct requests to the `.html` file redirect back to the clean URL via
`vercel.json`).

## Files involved

- `product/keel-code.html` — page markup, structure, copy and inline SVG art.
- `ui/keel-code.css` — page-specific styles (`.c-*` classes), scoped so the
  shared marketing system is untouched.
- `ui/keel-code.js` — page interactions (modals, terminal demos, copy buttons,
  newsletter form, toasts). Guarded to run only when `body.code-page` is
  present.

The page reuses the shared `ui/landing.css` and `ui/landing.js` assets from
`index.html`: the header, five mega menus, mobile menu, help search, news chip,
auth modal, dark footer, FAQ accordion and plan toggle all come from the landing
system. `landing.css`/`landing.js` load first, then the page-specific
`keel-code` files.

## Brand mapping

This is a KEEL-branded replica, so the original product names are remapped
everywhere: **Claude → Keel**, **Anthropic → Keel**, and **CLAUDE.md → KEEL.md**.
There are no Claude/Anthropic references left in the page copy.

## Interactions

Every button, tab, link and form is functional — there are no dead ends or
`href="#"` placeholders. Links point to real routes/anchors or `mailto:`; tabs,
modals, copy buttons, the newsletter form and smooth-scroll anchors are all
wired up by `ui/keel-code.js`.

## Keel Duet product page

`product/keel-duet.html` is the KEEL-branded replica of the Claude Duet waitlist
page, served cleanly at **`/product/keel-duet`** (see `vercel.json`).

- `product/keel-duet.html` — full waitlist page markup (hero, signup form,
  connector strip, features/phone preview, FAQ, dark CTA, footer, chat widget).
- `ui/keel-duet-shell.css` — self-contained warm editorial shell (tokens,
  header, mega menus, footer, buttons) so the page does not depend on the
  shared landing stylesheet.
- `ui/keel-duet.css` / `ui/keel-duet.js` — page-specific styling and all
  interactions (form validation, segments, accordion, modals, chat, toasts,
  mega menus, auth and mobile nav), guarded by `body.duet-page`.

Brand rule: **Claude → Keel**, **Anthropic → Keel**. All controls are functional
and there are no `href="#"` dead ends.

## KEEL Cowork product page

`product/cowork.html` is the KEEL-branded Cowork product page, served cleanly at
**`/product/cowork`** (rewritten to the HTML file in `vercel.json`, with direct
`.html` requests redirected back to the clean URL; `serve_keel_site.mjs` applies
the same rewrite locally). The route is listed in `sitemap.xml`.

- `product/cowork.html` — page markup and copy: hero, core capabilities,
  built-in browser, tedious-task tabs, plugins, articles, use-case videos,
  control, pricing, FAQ and the closing CTA, plus footer, overlays and cookie
  banner. All classes are `cw-`-prefixed and all behavior hooks are `data-*`.
- `ui/cowork.css` — self-contained, mobile-first styling (`.cw-*` only) with
  warm neutral tokens and the `#d97757` accent; respects reduced motion.
- `ui/cowork.js` — dependency-free IIFE handling nav/mobile menus, task,
  persona and plan tabs, view toggle, carousels, FAQ, forms, modals, toasts and
  the cookie banner. No network calls.
- `../assets/img/cw-*.svg` — local artwork: brand mark, app window, capability
  icons, browser panel, connector logos, deck, plugins, article thumbnails,
  video posters, partner marks and testimonial wordmarks.

The page makes **no external requests**: all images are local SVGs, fonts are
system stacks, and overlays simulate video and sign-in without a backend.
Brand rule: **Claude → KEEL**, **Anthropic → KEEL**. Run
`node verify_cowork_ui.mjs` from the workspace root to QA the page, assets and
routing.
