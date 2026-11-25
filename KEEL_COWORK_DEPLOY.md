# KEEL `/product/cowork` — build, QA and deploy runbook

## Goal

Reproduce the Claude Cowork product page (layout, copy structure, forms, interactions)
as a KEEL-branded static page at **https://keel-desktop.vercel.app/product/cowork**.

## Ownership map

| File(s) | Owner |
|---|---|
| `keel/site/product/cowork.html` | HTML subagent |
| `keel/site/ui/cowork.css` | CSS subagent |
| `keel/site/ui/cowork.js` | JS subagent |
| `keel/site/assets/img/cw-*.svg`, `keel/site/vercel.json`, `keel/site/sitemap.xml`, `serve_keel_site.mjs`, site READMEs, `verify_cowork_ui.mjs` | Assets/routing subagent |
| `KEEL_COWORK_CONTRACT.md`, this runbook, git + Vercel operations | Operator |

Shared contract: `KEEL_COWORK_CONTRACT.md`.

## QA gate (run after all subagents finish)

```powershell
cd "C:\Users\Admin\Desktop\Claude clone"
node verify_cowork_ui.mjs
node --check keel/site/ui/cowork.js
node --check verify_cowork_ui.mjs
node -e "JSON.parse(require('fs').readFileSync('keel/site/vercel.json','utf8'))"
```

Local browser check (OpenCode desktop browser tools):

1. Start the QA server: `node serve_keel_site.mjs` (port 3100).
2. Open `http://localhost:3100/product/cowork` at 1440px, 900px and 390px.
3. Exercise every control: three mega menus (hover/click/Escape/outside click),
   hamburger drawer, news dismiss, four task tabs + view toggle, plugins carousel,
   three persona tabs, quotes carousel, plan toggle, FAQ accordion, contact/auth/video
   modals, footer search, language select, cookie banner.
4. Confirm no console errors and no external network requests.

## Git

Branch: `release/backend-production-readiness-2026-11-24`
Remote: `https://github.com/eliosmernica15/keel.git`

The working tree contains substantial unrelated uncommitted work. Stage only this task's
files plus the shared routing files:

```powershell
git add KEEL_COWORK_CONTRACT.md KEEL_COWORK_DEPLOY.md verify_cowork_ui.mjs `
        serve_keel_site.mjs `
        keel/site/product/cowork.html `
        keel/site/ui/cowork.css keel/site/ui/cowork.js `
        keel/site/assets/img/cw-mark.svg `
        keel/site/vercel.json keel/site/sitemap.xml `
        keel/site/README.md keel/site/product/README.md
git commit -m "feat(site): add KEEL Cowork product page at /product/cowork"
git push origin HEAD
```

Use `git add` with explicit paths; do not use `git add -A`. If the assets agent created
additional `cw-*.svg` files, add them with `git add keel/site/assets/img/cw-*.svg`.

## Vercel

Project linked in `keel/site/.vercel/project.json` (`keel-desktop`);
`vercel whoami` resolves to `losimer100-5729`.

```powershell
cd "C:\Users\Admin\Desktop\Claude clone\keel\site"
vercel --prod --yes
```

Verify: `https://keel-desktop.vercel.app/product/cowork` returns 200 and renders the page.
(The pre-build URL returned 404 because the route did not exist.)
