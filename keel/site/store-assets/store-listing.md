# Chrome Web Store listing — Keel in Chrome

Use this file as the source of truth for the store listing fields. All copy is
deliberately conservative: this extension is a local, deterministic demo, not a
live AI product.

## Store title (14 / 50 characters)

```
Keel in Chrome
```

## Short summary (124 / 132 characters)

```
A private side panel that reads the page you're on, answers questions and builds a brief. Local demo rules only. No account.
```

## Category and tags

- **Category:** Productivity
- **Additional category:** Developer Tools
- **Tags:** `productivity`, `side panel`, `summaries`, `notes`, `local first`, `privacy`

## Full description

```
Keel in Chrome is a small side panel that helps you read and rework the web
page you are on. It is a local, deterministic demo: the answers are built by
rules inside the extension, not by a remote AI service.

WHAT IT DOES

- Reads the current tab. A read-only content script copies the visible text of
  an HTTPS page and the text you have highlighted. It never modifies the page.
- Chat mode gives you a quick, structured read of the page: the strongest
  sentences, the key terms, the page type it detected, and a suggested next
  step.
- Convert mode turns the page into a markdown brief with a summary, action
  items, a key-facts table, term frequencies and next steps.
- Approval modes ("Ask before each action", "Permissions Mode", "Work
  autonomously") and the four model-style profile labels are demo controls.
  They are recorded in the answer footer and in local settings; they do not
  grant real permissions, take actions on websites, or contact a model
  provider.
- Session history keeps up to 60 conversations in this browser profile only.
  You can restore or delete them from the History drawer.
- Tool tabs swap the example prompts for code review, everyday writing and
  background-task ideas. "Copy as markdown" copies the page context so you can
  paste it into another tool.
- Keyboard support: Enter sends, Shift+Enter adds a line, K toggles Chat /
  Convert, Escape closes menus and drawers.

HONEST LIMITATIONS

- This is not a live model. The same page and prompt always produce the same
  answer body. The profile names shown in the selector are labels only.
- The suggested prompts are examples. Keel does not connect to Google Drive,
  analytics dashboards, a CRM, a calendar or an email account.
- The microphone button is a clearly labelled simulation. No audio is recorded,
  stored or sent.
- Page text can only be read on https:// web pages. On chrome:// pages, the
  Web Store and other restricted pages the panel falls back to the tab title
  and URL and shows "limited page access".
- No account, no cloud sync, no paid dependency, no external fonts or scripts.

PRIVACY

No data leaves your browser. The extension makes no fetch, XMLHttpRequest,
telemetry or analytics calls. Page text is processed in memory; if auto-save is
on, only the conversation and a small page-context summary are stored locally
in chrome.storage.local. Uninstalling the extension removes that data with the
browser profile. The one outbound link in the UI (Open Keel web app) is a link
you can click yourself; nothing navigates or uploads without your action.

Privacy policy: https://keel-desktop.vercel.app/privacy
Support and system requirements: https://keel-desktop.vercel.app/requirements
Homepage: https://keel-desktop.vercel.app/keel-in-chrome
```

## Screenshots (upload in this order)

All are 1280×800 PNGs rendered from the real `sidepanel.html` with a local mock
for the extension message transport. They contain no browser chrome and no
fictitious product claims.

1. `screenshot-1-chat.png` — Chat mode, page context chip and suggested prompts.
2. `screenshot-2-chat-answer.png` — Chat answer generated from the page text.
3. `screenshot-3-convert.png` — Convert mode, structured markdown brief.
4. `screenshot-4-history.png` — Local session history drawer.

## Promo assets

- `promo-small-440x280.png` — 440×280 small tile.
- `promo-marquee-1400x560.png` — 1400×560 marquee tile.

Both use the Keel starburst and locally installed system fonts only.

## Privacy policy URL

```
https://keel-desktop.vercel.app/privacy
```

Chrome does not support a privacy-policy field in `manifest.json`; the URL is
entered in the store listing's privacy policy field and published on the site.

## Support

```
https://keel-desktop.vercel.app/requirements
```

## Review-readiness checklist

- [x] Manifest V3, valid JSON, `name` "Keel in Chrome", `short_name` "Keel", `version` "1.0.0".
- [x] `homepage_url`, icons at 16/48/128 px, `side_panel.default_path`, `background.service_worker`.
- [x] Explicit extension-pages CSP: `script-src 'self'; object-src 'self'` — no remote code.
- [x] Narrow host access: HTTPS web pages only; no `<all_urls>`.
- [x] Minimal permissions: `activeTab`, `sidePanel`, `storage`, `tabs`, `contextMenus` — justified in `extension/README.md`.
- [x] No `http://` URLs, no `fetch`, no XHR, no WebSocket, no analytics or telemetry.
- [x] All JS passes `node --check`; all message types and element IDs cross-checked.
- [x] Toolbar icon opens the panel via `sidePanel.setPanelBehavior`; context menus open it within the user gesture.
- [x] Content-script messaging uses `tabs.sendMessage` (not `runtime.sendMessage`).
- [x] Screenshots and promo tiles have the exact required pixel dimensions.
- [x] Privacy policy and support URLs are live site pages.
- [x] ZIP contains `manifest.json` at the root and only extension files.
- [ ] Final step for the publisher: load the unpacked folder in Chrome and smoke-test Chat, Convert, History and the toolbar icon on a real HTTPS page before submitting.
