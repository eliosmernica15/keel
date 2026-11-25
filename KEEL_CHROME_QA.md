# Keel in Chrome — Final QA report

- **QA worktree:** `C:\Users\Admin\.local\share\opencode\worktree\e3c464\keel-chrome-delivery`
- **Scope:** `keel/site/keel-in-chrome.html`, `chrome-web-store.html`, their CSS/JS, `extension/**`, `keel-extension.zip`, `vercel.json`, `sitemap.xml`, nav edits in `index.html` / `download.html`
- **Method:** static analysis via `verify_keel_chrome.py` (written and run for this QA) + real headless Chrome 1440px/390px screenshots + live Chrome DevTools Protocol interaction tests
- **No product file was edited by QA.** No commit, push, or deploy was performed.

## PASS / FAIL summary

| # | Check | Result |
|---|-------|--------|
| 1 | `node --check` on all UI + extension JS (11 files) | **PASS** |
| 2a | HTML: no `href="#"`, anchors resolve, no Claude/Anthropic in new pages, no inline `<script>` | **PASS** |
| 2b | Every same-origin path/route resolves to a file or a declared Vercel rewrite | **FAIL** — see D1 |
| 3 | Vercel rewrites + sitemap contain `/keel-in-chrome` and `/chrome-web-store` | **PASS** |
| 4a | Manifest valid JSON, MV3, all referenced files/icons exist | **PASS** |
| 4b | Every ID referenced in `sidepanel.js` exists in `sidepanel.html` | **PASS** (53 IDs, 0 missing) |
| 4c | Every message type sent has a handler | **PASS** (16 panel→background, 2 background→content/panel, 0 unhandled) |
| 4d | `SET_SETTINGS` payload shape matches its handler | **FAIL** — see D2 |
| 4e | ZIP has `manifest.json` at root and byte-matches the extension folder | **PASS** (10 entries, 0 diffs) |
| 5 | Buttons/controls wired (static cross-reference of 46+27 buttons, inputs, forms) | **PASS** (0 unwired) |
| 6 | Headless Chrome renders both pages at 1440px and 390px, non-blank | **PASS** (4/4 screenshots) |
| 6b | No browser/console errors | **PASS** (0 CDP errors; 2 benign Chrome registry messages filtered) |
| 7 | CDP interaction exercises (21 interactions across both pages) | **PASS** (21/21) |

**Result: 11 PASS / 2 FAIL.**

---

## Defects

### D1 — Deployment-blocking: six clean-URL routes linked by the new pages have no Vercel rewrite (FAIL check 2b)

**Severity: HIGH (blocks deploy).**

`keel/site/vercel.json` lines 22–28 declare rewrites only for `/download`, `/app`, `/keel-in-chrome`, `/chrome-web-store` and `/terms`. The same change adds sitemap entries (`keel/site/sitemap.xml` lines 8–14) for `/privacy`, `/requirements`, `/roadmap`, `/eula`, `/trademark`, `/notices` and the new pages link to those extensionless URLs heavily. Vercel's `cleanUrls` option defaults to **`false`** (confirmed in Vercel's `vercel.json` docs), so a static `privacy.html` is served at `/privacy.html`, **not** `/privacy`; without a rewrite these requests 404. The fact that this change explicitly added a `/terms → /eula.html` rewrite shows the extensionless-path requirement was understood, but the other six were missed.

Affected links (exhaustive list produced by the QA script):

- `keel/site/chrome-web-store.html`: lines 105, 106, 427, 430 (`/roadmap`, `/privacy`)
- `keel/site/keel-in-chrome.html`: lines 50, 101–103, 129, 148, 162–167, 171–173, 178–179, 215, 401, 407, 413, 419, 425, 431, 494, 602, 649, 671–674, 680–681, 682, 684, 701–703, 705–707, 715–721, 728–733, 739–745, 796 (`/privacy`, `/requirements`, `/roadmap`, `/eula`)
- `keel/site/index.html`: lines 50, 65 — the nav edit in this change replaced `#docs` with `/requirements`, introducing two more dead links
- Pre-existing occurrences elsewhere: 57 links to the same six routes

**Suggested fix** — add explicit rewrites in `keel/site/vercel.json` `rewrites` array:

```json
{ "source": "/privacy",      "destination": "/privacy.html" },
{ "source": "/requirements", "destination": "/requirements.html" },
{ "source": "/roadmap",      "destination": "/roadmap.html" },
{ "source": "/eula",         "destination": "/eula.html" },
{ "source": "/trademark",    "destination": "/trademark.html" },
{ "source": "/notices",      "destination": "/notices.html" }
```

(Alternative: top-level `"cleanUrls": true`. Prefer explicit rewrites here to avoid changing behaviour of existing `.html` links.)

### D2 — Extension settings never persist: `SET_SETTINGS` sender/handler payload mismatch (FAIL check 4d)

**Severity: MEDIUM (functional defect in the shipped extension).**

- `keel/site/extension/sidepanel.js:1057` sends `{ type: 'SET_SETTINGS', settings: patch }`.
- `keel/site/extension/background.js:485–493` computes `payload = message` (there is no `message.payload` property), then iterates `Object.keys(payload)` — i.e. `['type', 'settings']` — copying only values whose `typeof` is `boolean`. Neither `message.type` (string) nor `message.settings` (object) is boolean, so **nothing is stored**, and the handler echoes the unchanged settings back.
- `keel/site/extension/sidepanel.js:1054–1060` then replaces local state with that unchanged response and re-applies the UI, so toggling Stream / Auto-save / Keyboard hints / Reduce motion visibly **snaps back**. `resetPreferences()` (line 1069) is affected the same way.
- Every other message type uses flat fields (`payload.model`, `payload.mode`, `payload.tab`, `payload.source`, `payload.seen`, …), so `SET_SETTINGS` is the sole outlier.

**Runtime proof** (Node harness with mocked `chrome.*` APIs, loading the real `background.js`):

```
handler response : {"ok":true,"settings":{"stream":true,"autoSave":true,"keyboardHints":true,"reduceMotion":false}}
stored settings  : {"stream":true,"autoSave":true,"keyboardHints":true,"reduceMotion":false}
stream persisted as false?  false
```

**Suggested fix** — make the handler read the nested object (safer than changing the caller, since it keeps the API consistent with all other flat-field messages):

```js
case 'SET_SETTINGS': {
  var current = await getState();
  var nextSettings = Object.assign({}, current.settings);
  var patch = (payload && payload.settings && typeof payload.settings === 'object')
    ? payload.settings : payload;
  Object.keys(patch || {}).forEach(function (key) {
    if (typeof patch[key] === 'boolean') nextSettings[key] = patch[key];
  });
  await setState({ settings: nextSettings });
  return { ok: true, settings: nextSettings };
}
```

Then regenerate `keel/site/keel-extension.zip` so the shipped archive contains the fix.

---

## Non-blocking observations (not counted as failures)

- `chrome-web-store.html:149` CTA reads **"Add to KEEL"** while every other CTA reads "Add to Chrome"; likely intentional rebranding, but it reads oddly on a Chrome Web Store replica.
- `chrome-web-store.html:153` link text is `keel.com` but `href="/keel-in-chrome"`; cosmetic mismatch.
- The share-button test in headless Chrome used the `execCommand` fallback (`"Copy unavailable — copy the URL from the address bar"`) because clipboard permission is not granted in the harness. The fallback path works; no page error.
- Chrome stderr contained two benign `external_registry_loader_win.cc` messages about unrelated preinstalled extension registry keys; no page-originated console errors, no `Runtime.exceptionThrown`, no failed resource loads.
- The marketing page loads `/ui/download-clone.css` but not `download-clone.js`; all its controls are wired by `chrome-landing.js`, so this is harmless (verified statically and via CDP).

---

## Evidence details

### Syntax, HTML, routes, extension, controls

- All 11 JS files pass `node --check`: `app.js`, `chrome-landing.js`, `chrome-web-store.js`, `download-clone.js`, `download.js`, `landing-download.js`, `landing.js`, `management.js`, `background.js`, `content.js`, `sidepanel.js`.
- 0 empty `href="#"`, 0 broken anchors (including 8 `/#models` links in the new page → `index.html#models`, which exists at `index.html:157`), 0 Claude/Anthropic strings in the two new pages, 0 executable inline scripts (the JSON-LD block at `index.html:22` is inert data and CSP-safe).
- Both new routes are correctly rewritten (`/keel-in-chrome → /keel-in-chrome.html`, `/chrome-web-store → /chrome-web-store.html`) and listed in the sitemap.
- Manifest is valid MV3 (`manifest_version: 3`); `sidepanel.html`, `background.js`, `content.js` and all 6 icon paths exist. All 53 element IDs used by `sidepanel.js` exist in `sidepanel.html` (including the 4 dynamically assembled `tab-<name>` IDs).
- Message coverage: `GET_STATE`, `GET_PAGE_CONTEXT`, `GET_PENDING_ACTION`, `CLEAR_PENDING_ACTION`, `NEW_SESSION`, `SAVE_SESSION`, `LIST_SESSIONS`, `SAVE_SESSIONS_REPLACE`, `CLEAR_SESSIONS`, `SET_SETTINGS`, `SET_WELCOME_SEEN`, `SET_APPROVAL_MODE`, `SET_MODEL`, `SET_MODE`, `SET_ACTIVE_TAB`, `SET_CONTEXT_SOURCE` → all handled in `background.js`; `KEEL_GET_CONTEXT` handled in `content.js`; `KEEL_PAGE_CHANGED` handled in `sidepanel.js`.
- ZIP: 10 entries (`manifest.json` at root, `sidepanel.*`, `background.js`, `content.js`, 3 icons, `README.md`); exact set and byte-for-byte parity with `extension/`.
- Control wiring: `keel-in-chrome.html` 183 `<a>`, 46 `<button>`, 3 inputs/selects, 2 forms; `chrome-web-store.html` 21 `<a>`, 27 `<button>`, 1 input — **0 unwired** after cross-referencing IDs, classes, `data-*` attributes, delegation selectors and submit handlers.

### Browser rendering and interactions

Server: `python -m http.server <fresh port> --directory keel/site`; pages requested by `.html` filename (local server has no Vercel rewrites).
Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe` with `--headless=new --disable-gpu --remote-debugging-port=<fresh> --user-data-dir=<fresh> --enable-logging=stderr --v=0 --window-size=1440,900` and CDP `Emulation.setDeviceMetricsOverride` for 390×844 mobile.

Screenshots (all non-blank; distinct-colour counts 989–2541, max channel std-dev 33–89):

- `C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots\qa-keel-in-chrome-desktop.png` (1440×900, 84,510 B)
- `C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots\qa-keel-in-chrome-mobile.png` (390×844, 45,163 B)
- `C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots\qa-chrome-web-store-desktop.png` (1440×900, 64,694 B)
- `C:\Users\Admin\AppData\Local\Temp\opencode\qa-shots\qa-chrome-web-store-mobile.png` (390×844, 46,557 B)

Raw logs: `...\qa-shots\qa-chrome-stderr.log`, `...\qa-shots\qa-http-server.log`.

CDP interaction results (21/21 OK):

- Marketing page: FAQ accordion open/close; hero carousel dot; Chat/Convert toggle; workflow demo tabs; capability preview buttons; safety segmented tabs; auth modal open/close; guide modal open/close; footer link search; language selector; mobile nav toggle.
- Store page: Discover/Extensions/Themes tabs + `data-goto` back; search no-results and clear; search matching query; carousel arrows and dots; install modal; demo-video modal; account popover; ratings tooltip; share toast; `data-toast` menu item.

Note: mobile screenshots were captured after the desktop interaction run, so they show retained state (scrolled section / search text / toast). This is a harness artefact, not a rendering defect; both mobile layouts render correctly and the mobile nav toggle was exercised at 390px.

### Notes on QA methodology

Initial static-analysis runs produced false positives (duplicate `screenshots/index.html` key overwriting `index.html` in the ID map; valueless HTML attributes; inert JSON-LD treated as executable script; dynamically assembled `tab-` ID; multi-line selector-literal regex; benign Chrome registry messages). Each was investigated and corrected in `verify_keel_chrome.py` before the final run; the two remaining failures (D1, D2) were reproduced independently — D2 with a mocked-Chrome Node runtime harness.

---

## Final verdict

**NOT ready to deploy as-is.** The two new pages themselves are high quality: they render correctly at desktop and mobile, every control is wired, all 21 live interactions pass, syntax/branding/CSP/anchor checks are clean, and the MV3 extension archive is internally consistent and loadable.

Block deployment on **D1**: without the six Vercel rewrites, dozens of links on the new marketing page (and the new `/requirements` nav links in `index.html`) will 404 even though the sitemap advertises them.

Fix **D2** before shipping `keel-extension.zip`: the extension loads, but its settings toggles do not persist and visibly revert.

Once D1 and D2 are fixed (and the ZIP regenerated for D2), a short re-run of `python verify_keel_chrome.py` should yield 13/13 PASS, after which the deliverables are ready to commit and deploy.

---

## Remediation (lead agent, same session)

- **D1 fixed** — added explicit rewrites for `/privacy`, `/requirements`, `/roadmap`, `/eula`, `/trademark`, `/notices` in `keel/site/vercel.json`.
- **D2 fixed** — `SET_SETTINGS` in `keel/site/extension/background.js` now reads the nested `message.settings` object (with a flat-payload fallback) and persists boolean keys; `keel/site/keel-extension.zip` was regenerated from the extension folder.
- Re-ran `python verify_keel_chrome.py`: **13/13 checks PASS, 0 FAIL**, including 21/21 live CDP interactions and 0 console errors.
- **Final verdict: READY to commit, push and deploy.**
