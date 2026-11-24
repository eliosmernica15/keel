# KEEL Platform API page — delivery notes

## What shipped

A faithful, KEEL-branded reproduction of the Claude Platform API marketing
page at the exact URL **https://keel-desktop.vercel.app/platform/api**.

### Files

- `keel/site/platform/api.html` — full page markup (header mega nav, explore
  rail, hero, customer logos, model cards, capability hub, Agent SDK,
  enterprise, cost controls, Console, testimonials, CTA, footer, modal, toast).
- `keel/site/ui/platform-api.css` — self-contained editorial styling scoped to
  `body.pa-body`, responsive at 1100/900/640 and reduced-motion aware.
- `keel/site/ui/platform-api.js` — all interactions, no libraries, no network.
- `keel/site/assets/img/platform/*.svg` — 22 local SVGs (mark, hero artwork,
  wordmarks, icons).
- `keel/site/vercel.json` — `/platform/api` rewrite and `.html` redirect.
- `keel/site/sitemap.xml`, `keel/site/README.md` — route registration.
- `verify_platform_api.mjs` — dependency-free integrity/wiring verifier.

### Integration

Existing marketing pages that labelled a link "Keel Platform" now point to
`/platform/api` instead of a pricing anchor, the app route or a requirements
page. `serve_keel_site.mjs` mirrors the Vercel rewrite for local QA.

## Verification

- `node verify_platform_api.mjs` — all checks pass (branding, 40 required ids,
  unique ids, `aria-controls` targets, 162 links with no dead ends, 22 local
  assets, rewrite + redirect, JS wiring, `node --check`).
- Browser QA at `http://127.0.0.1:3100/platform/api` — no console errors;
  mega nav, hamburger, explore rail, cost tabs, carousel and modal exercised.
- Lighthouse (local): Accessibility 0.94, Best Practices 1.0, SEO 1.0.

## Deploy

From `keel/site` (the Vercel project root, project `keel-desktop`):

```
vercel --prod --yes
```

The production URL is `https://keel-desktop.vercel.app/platform/api`.
