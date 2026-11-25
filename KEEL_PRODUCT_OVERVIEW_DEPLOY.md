# KEEL `/product/overview` — build, QA and deploy runbook

## Ownership map

| File(s) | Owner |
|---|---|
| `keel/site/product-overview.html` | HTML subagent |
| `keel/site/ui/product-overview.css` | CSS subagent |
| `keel/site/ui/product-overview.js` | JS subagent |
| `keel/site/assets/img/po-*.svg`, `vercel.json`, `sitemap.xml`, cross-page nav links, `README.md` | Assets/routing subagent |
| `verify_product_overview.py`, git + Vercel operations | Operator |

Shared contract: `KEEL_PRODUCT_OVERVIEW_CONTRACT.md`.

## QA gate

```powershell
cd "C:\Users\Admin\Desktop\Claude clone"
python verify_product_overview.py
node --check keel/site/ui/product-overview.js
```

Then browser verification (requires the OpenCode desktop app attached):

1. Open a local static server in `keel/site`: `python -m http.server 4173`.
2. Open `http://localhost:4173/product-overview.html` in the in-app browser.
3. Snapshot at 1440px, 900px, 390px; screenshot full page.
4. Exercise: mega dropdowns (hover/click/Escape), hamburger, persona tabs,
   capability search + tabs, role/size/task selectors, FAQ accordion, ask form,
   footer search, auth modal (email + Google demo), toast, news chip dismiss.
5. `console({ level: "error" })` must be empty. `network.list` must show no
   external requests.

Note: the Vercel rewrite (`/product/overview` -> `/product-overview.html`) is only
active on the deployed site; the local Python server serves the `.html` path directly.

## Git

Current branch: `release/backend-production-readiness-2026-11-24`
Remote: `https://github.com/eliosmernica15/keel.git`

The working tree already contains unrelated uncommitted work. Stage only the files
for this task (plus the site config files that must carry the new route):

```powershell
git add keel/site/product-overview.html `
        keel/site/ui/product-overview.css `
        keel/site/ui/product-overview.js `
        keel/site/assets/img/po-mark.svg `
        keel/site/assets/img/po-portrait-a.svg `
        keel/site/assets/img/po-portrait-b.svg `
        keel/site/assets/img/po-portrait-c.svg `
        keel/site/assets/img/po-app-icons.svg `
        keel/site/assets/img/po-laptop.svg `
        keel/site/assets/img/po-stage.svg `
        keel/site/vercel.json `
        keel/site/sitemap.xml `
        keel/site/index.html `
        keel/site/download.html `
        keel/site/app.html `
        keel/site/chrome-web-store.html `
        keel/site/keel-in-chrome.html `
        keel/site/README.md `
        KEEL_PRODUCT_OVERVIEW_CONTRACT.md `
        KEEL_PRODUCT_OVERVIEW_DEPLOY.md `
        verify_product_overview.py
git commit -m "feat(site): add KEEL product overview page at /product/overview"
git push origin HEAD
```

`src/keel/capabilities.py` and other pre-existing changes stay untouched by this
commit.

## Durable routing (important)

`keel/site/product/overview/index.html` is a physical copy of the page. It makes
`/product/overview` work even if another agent rewrites `vercel.json` and drops the
friendly rewrite. If `product-overview.html` is ever updated, copy it to
`product/overview/index.html` as well.

## Vercel

Deploying from the workspace root can fail with `File size limit exceeded (100 MB)`
or a 15,000-file upload cap because that repository contains large research
clones. Deploy from a clean staging directory whose layout is `<root>/keel/site/...`
with a `<root>/.vercel/project.json` pointing at `prj_5BOkBPE8UcXwZApO0FiKyUFyCbSC`:

```powershell
$staging = "$env:TEMP\opencode\keel-deploy-staging"
Copy-Item -Recurse "keel/site" "$staging\keel\site"
cd $staging
vercel --prod --yes
```

The project is linked in `keel/site/.vercel/project.json`
(`prj_5BOkBPE8UcXwZApO0FiKyUFyCbSC`, project `keel-desktop`) and `vercel whoami`
resolves to `losimer100-5729`.

```powershell
cd "C:\Users\Admin\Desktop\Claude clone\keel\site"
vercel --prod --yes
```

Verify: `https://keel-desktop.vercel.app/product/overview` returns 200 and renders
the page (the pre-build URL returned 404 because the route did not exist).
