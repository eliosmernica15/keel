# `/new` page design spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY at
`https://keel-desktop.vercel.app/new`. Brand is **Keel** everywhere (never
Claude/Anthropic). Light theme — unlike the dark existing `/app` mirror.

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Create ONLY:
- `keel/site/new.html`
- `keel/site/ui/new.css`
- `keel/site/ui/new.js`

Do NOT edit any other file. Do NOT commit, push, or deploy.

## Layout

Overall: white / very light warm background, near-black ink, grey secondary
text, thin light borders, orange Keel starburst. Full viewport height, no page
scroll on desktop.

### Top bar
Left: small sidebar-toggle icon then serif wordmark `Keel`. Right: small
question-mark help icon. No other header controls.

### Sidebar (~260px wide, right border)
- `+ New` — highlighted with a light grey rounded background.
- `Search` (magnifier icon)
- `Projects` (stacked-layers icon)
- `Artifacts` (artifact icon)
- `Plugins` (plugin/puzzle icon)
- Small grey label `Recents` with a chevron.
- Recent items, exactly: `Keel harness build plan`, `Keel project review and
  plan`, `Keel project plan review`, `Test exercise answers`, `Team member
  project reports` (with a small document icon), `Connecting AutoCAD with MCP`,
  `Golden Gate Bridge PowerPoint`, `Base quantities and SI units`,
  `AutoCAD seminar document with cust…` (truncated), `Exam answers request
  declined`, then `View all`.
- Bottom: small red/orange circle with `E`, text `Elios · Free`, a chevron, and
  a sidebar-collapse icon at the far right.

### Main area
- Top-centre small pill: `Free plan · Upgrade` (Upgrade in blue).
- Centred: orange starburst followed by large serif `You're here!`.
- Composer: wide rounded box (~700px) with thin border, placeholder
  `How can I help you today?`; bottom row has `+` on the left, then mic icon,
  a small chevron and a voice-wave icon on the right.
- Beneath composer: `Project ⌄` on the left; `Sonnet 5.5  Medium` toward the
  right; `Auto` at the far right.
- `Recent artifacts` heading on the left and `View all` on the right.
- One artifact card: light-blue thumbnail with a tiny fake document preview,
  label `Discover Kosovo…` and date `Oct 27`.

## Functionality (all controls must work)
- `New` clears the composer and focuses it; optionally shows a fresh-home state.
- `Search` opens a filter input for the recents list.
- `Projects` / `Artifacts` / `Plugins` open small in-page panels or system notes
  (no dead buttons).
- Recent items are clickable: clicking one fills the composer with its title and
  focuses it (or shows a note). `Recents` chevron toggles the list; `View all`
  toggles between a short and full list.
- Upgrade opens an informational plans dialog with a link to `/#plans`.
- Composer: typing and pressing Enter (or a send control) adds a user message
  below the greeting and clears the input; a small canned reply is acceptable
  because this is a static mirror.
- `+` attach button opens a note that file upload belongs to the local app.
- Mic / chevron / voice-wave toggle a visible voice-status control.
- `Project`, model chip and `Auto` open small menus or informational notes.
- `View all` beside artifacts reveals more artifact cards.
- Help icon opens a small help dialog.
- Account chip opens a small account menu with `Upgrade` and `Settings` links.
- Responsive down to 390px: sidebar collapses behind a toggle; no horizontal
  overflow. Keyboard accessible, focus-visible rings, aria labels, no console
  errors, no dead `href="#"`.

Use a self-contained design with its own tokens in `ui/new.css`; reuse the Keel
starburst SVG from `index.html`. Real hrefs only: `/`, `/app`, `/login`,
`/download`, `/privacy`, `/terms`, `#`-anchors that exist on the page, mailto.
