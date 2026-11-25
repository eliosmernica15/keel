# `/downloads` page design spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY at
https://keel-desktop.vercel.app/downloads — the "Apps and extensions" page.
Brand **Keel** everywhere: "Claude" -> "Keel", "Claude Code" -> "Keel Code",
"claude.ai/mobile" -> "keel.ai/mobile", "Cowork" -> "Cowork" (Keel Cowork).

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Create ONLY:
- `keel/site/downloads.html`
- `keel/site/ui/downloads.css`
- `keel/site/ui/downloads.js`

Do NOT edit any other file. Do NOT commit, push, or deploy.

## Layout
- Very light warm-white background, near-black serif headings, grey body text,
  thin light card borders and soft shadows.
- Top bar: small back arrow followed by `Apps and extensions`, left aligned,
  with a thin divider under it.
- Centred serif heading: `Do more with Keel, everywhere you work`.
- Content container ~900px wide.

### Card 1 — Desktop (full width, ~900×330)
Left: `Desktop`, then `Chat, cowork, and code in one app.` / `Keel works with
your files, apps, and browser tabs.` Black pill button `Download for Windows`.
Right: soft illustration — overlapping chat bubbles such as `My downloads
folder is a mess! Can you clean it up?`, `Turn these receipts into an expense
report`, `Create a shopping list, go on Chrome, and make an order`, with a
small browser/window mock and grocery thumbnails. Draw in CSS/inline SVG, no
external images.

### Cards 2–5 — 2×2 grid
- **Microsoft 365** — `Analyze data, build presentations, draft documents,
  and triage your inbox with Keel alongside you.` Light grey `Upgrade` pill.
  Four rows with small coloured icons and ↗ arrows: Excel, PowerPoint, Word,
  Outlook. Bottom: faint green-tinted spreadsheet screenshot mock with a chat
  bubble `Which names are the top movers in my portfolio and why?`.
- **Keel Code** — `Build, debug, and ship from the desktop app, your terminal,
  or your IDE.` `Upgrade` pill. Rows with icons and ↗: Desktop app, Terminal,
  VS Code, JetBrains, Slack. Bottom: terminal mock with a small robot mark and
  `> Fix the auth bug in signup flow`.
- **Chrome** — `Keel navigates, clicks buttons, and fills forms in your
  browser. Works in Cowork.` `Upgrade` pill. Bottom: browser mock with a
  Returns order page showing `Wireless Headphones Pro`, `$79.99`, `Start
  return`.
- **Mobile** — `Chat hands-free, connect Keel to your favorite apps, and kick
  off tasks on the go.` A QR code (CSS/SVG mock is fine) centred, then
  `Scan with your phone to get the Keel app`, `Or visit keel.ai/mobile`. Bottom
  illustration: chat bubbles `Let's look at your latest runs and make a plan
  to trim some time.` and `Read health data` over a pink bar chart with
  months `Dec 7 11 15 19 23 27 31`.

## Functionality
- Back arrow works (`history.back()` when possible, otherwise `/download`).
- `Download for Windows` → `/download`, with a platform note if unavailable.
- Every `Upgrade` pill opens an informational plans dialog linking to `/#plans`
  and `/login?intent=signup`.
- Every integration row (Excel, PowerPoint, Word, Outlook, Desktop app,
  Terminal, VS Code, JetBrains, Slack) opens a detail dialog with a real link
  to `/app`, `/download` or `/plugins`; no dead controls.
- QR is decorative but clickable → `/download`; the mobile link → `/download`.
- Cards are keyboard focusable and their buttons have aria labels. Responsive
  to 390px: full-width card stacks and grid becomes one column. No console
  errors, no dead `href="#"`, no "Claude"/"Anthropic" text.
