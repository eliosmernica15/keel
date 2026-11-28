# Keel in Chrome — current-state QA report

- **Date:** 2026-11-25
- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\e3c464\keel-chrome-delivery`
- **Scope:** the new single-page plan — `keel/site/keel-in-chrome.html` and its physical route index `keel/site/keel-in-chrome/index.html`, `ui/chrome-landing.js`, `ui/chrome-install.js`, the MV3 extension in `keel/site/extension/`, `keel-extension.zip`, `store-assets/`, `vercel.json`, `sitemap.xml`, and nav links in `index.html` / `download.html`. The retired `/chrome-web-store` replica page and its CSS/JS are **out of scope except for a negative check** that nothing references that route.
- **Method:** `python verify_keel_chrome.py` — static analysis plus real headless Chrome 1440×900 / 390×844 screenshots and live CDP interactions.
- **No product file was edited by QA. No commit, push, deploy, or store upload was performed.**
- **Final install flow is free and functional.** All `Add to Chrome` CTAs download `keel-extension.zip` and open a load-unpacked guide from `ui/chrome-install.js`. The retired `/chrome-web-store` replica is deleted.
- **The extension is NOT published to the Chrome Web Store.** Google requires a one-time $5 developer registration fee and the Web Store API cannot create the first item. OAuth authorization succeeded locally, but no item was uploaded. A Web Store URL slot remains in `ui/chrome-install.js` if that route is chosen later.

## Checks and results (exact final run)

Command: `python verify_keel_chrome.py` → **17 PASS, 0 FAIL, 0 SKIP; verdict: READY**

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `node --check` on all UI + extension JS (11 files) | **PASS** | `chrome-install.js` and `chrome-landing.js` tagged NEW; all OK |
| 2a | No `href="#"`, anchors resolve, no Claude/Anthropic branding, no inline `<script>` in the landing copies | **PASS** | 0 empty hrefs, 0 broken anchors, 0 branding hits, 0 inline scripts |
| 2b | Same-origin paths resolve to a file or Vercel rewrite | **PASS** | 0 unresolved links on either landing copy |
| 3 | `/keel-in-chrome` rewrite + sitemap + physical route index + HTML parity | **PASS** | rewrite → `/keel-in-chrome.html`; sitemap entry present; both copies exist; title, canonical, scripts and 3/3 CTAs match |
| 4a | Manifest valid JSON, MV3, referenced files exist | **PASS** | `manifest_version: 3`, 9 referenced paths, 0 missing |
| 4b | Every ID referenced in `sidepanel.js` exists in `sidepanel.html` | **PASS** | 53 IDs, 0 missing (uses the new `TAB_IDS` map) |
| 4c | Every message type sent has a handler | **PASS** | 16 panel→background, 2 background→content/panel, 0 unhandled; 20 background cases |
| 4d | `SET_SETTINGS` payload shape matches its handler | **PASS** | payload shapes agree (nested `settings` object is read) |
| 4e | `keel-extension.zip` root manifest + byte parity with folder | **PASS** | 10 entries, `manifest.json` at root, 0 zip-only/folder-only files, 0 content mismatches |
| 5 | Buttons/controls wired (static cross-reference) | **PASS** | each copy: 183 `<a>`, 46 `<button>`, 3 inputs/selects, 2 forms; 0 unwired |
| 5b | Every `Add to Chrome` CTA carries `data-store-install` and the configured store URL/token | **PASS** | 3 CTAs per copy (lines 232, 573, 588), all with the attribute and `chromewebstore.google.com/detail/...` href; token `window.KEEL_CHROME_WEB_STORE_URL` discovered |
| 5c | `ui/chrome-install.js` exists and is loaded by both landing copies | **PASS** | 670-byte file; `<script src="/ui/chrome-install.js">` present in both |
| 6 | No site file references `/chrome-web-store` | **PASS** | 0 references anywhere under `keel/site` (including retired files, now deleted) |
| 9 | `store-assets/store-listing.md` present (publishing input) | **PASS** | 5,708 bytes, plus screenshots and promo tiles in the same directory |
| 7 | Headless Chrome renders both landing copies at desktop + mobile, non-blank | **PASS** | 4/4 screenshots non-blank; distinct colours 1,039–2,541; max std-dev 33.1–52.7 |
| 7b | No browser/console errors | **PASS** | 0 CDP errors, 0 filtered Chrome stderr hits |
| 8 | CDP interaction exercises | **PASS** | 12/12 OK, including live DOM verification of the 3 install CTAs |

Final summary line from the run:

```
17 PASS; 0 FAIL; 0 SKIP (17 checks total)
verdict: READY
screenshots: C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots
```

No checks were skipped in the final run. During earlier runs, while other agents were still writing, the script correctly reported `SKIP` for `ui/chrome-install.js`, the CTA check (no CTAs present yet), and the store-listing file, and reported `FAIL` for a stale ZIP and a transient `TAB_IDS` cross-reference; all were resolved by the other agents before this final run.

## Screenshots

All files under `C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots\`:

| File | Viewport | Size | Distinct colours / max std-dev |
|------|----------|------|-------------------------------|
| `qa-keel-in-chrome-desktop.png` | 1440×900 | 84,510 B | 1,039 / 33.1 |
| `qa-keel-in-chrome-mobile.png` | 390×844 | 45,163 B | 2,541 / 37.9 |
| `qa-keel-in-chrome-route-desktop.png` | 1440×900 | 84,510 B | 1,039 / 33.1 |
| `qa-keel-in-chrome-route-mobile.png` | 390×844 | 42,092 B | 2,187 / 52.7 |

Raw logs: `qa-chrome-stderr.log`, `qa-http-server.log` in the same folder. Full raw console output of the final run: `%TEMP%\opencode\qa-final-run.log`.

Live CDP interactions (12/12): FAQ accordion, hero carousel dot, Chat/Convert toggle, workflow demo tabs, capability preview buttons, safety segmented tabs, auth modal, guide modal, footer link search, language selector, Add-to-Chrome CTA DOM wiring, mobile nav toggle. The local server used `python -m http.server` over `keel/site`; Chrome ran with `--headless=new` and a fresh profile/CDP port.

## Observations (non-blocking)

- The CTA URL is a placeholder (`PENDING_ITEM_ID`). The site is functionally correct but **users are not yet sent to a live store listing**. Publishing is a manual, owner-approved step; see `CHROME_EXTENSION_PUBLISHING.md`.
- `store-assets/store-listing.md` says "Narrow host access: HTTPS web pages only", while `extension/manifest.json` currently declares both `https://*/*` and `http://*/*` in `host_permissions`. Align the listing copy with the manifest (or narrow the manifest) before submitting, to avoid a review question.
- The listing file's final checklist still has one unchecked item: load the unpacked folder in Chrome and smoke-test Chat, Convert, History and the toolbar icon on a real HTTPS page before submitting. QA's CDP checks exercise the *site* and static extension wiring, not a loaded unpacked extension.
- Mobile screenshots were captured after the desktop interaction run, so they retain minor interaction state. This is a harness artefact, not a rendering defect.

## Verdict

**READY — for commit and deploy of the site and packaged extension.** All 17 automated QA checks pass with 0 failures and 0 skips. This verdict does **not** mean the extension is published: the store item must still be created, approved and its real item ID substituted into `ui/chrome-install.js`, followed by a redeploy and a re-run of `python verify_keel_chrome.py` (expect 17/17 PASS with a real `chromewebstore.google.com/detail/...` URL in check 5b).
