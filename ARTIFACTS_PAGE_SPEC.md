# `/artifacts` page design spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY at
https://keel-desktop.vercel.app/artifacts — same light app shell as `/new`,
`/plugins`, `/projects`, with Artifacts selected. Brand **Keel** everywhere.

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Create ONLY:
- `keel/site/artifacts.html`
- `keel/site/ui/artifacts.css`
- `keel/site/ui/artifacts.js`

Do NOT edit any other file. Do NOT commit, push, or deploy. The coordinator
will add the shared search-palette tags.

## Layout
### Left sidebar
Identical to `new.html` / `plugins.html` / `projects.html`: Keel wordmark +
collapse icon; `+ New`, `Search`, `Projects`, `Artifacts` (highlighted grey),
`Plugins`; `Recents ˅` with the exact ten recent chat names and `View all`;
bottom account chip `Elios · Free` + collapse icon.

### Main area
- Serif heading `Artifacts`.
- Second row: tabs `All` (active grey pill), `Yours`, `Shared with you`.
  On the right: magnifier button, filter/sliders button, list-view button,
  and a `+` button.
- Small label `Make something new`.
- Four rounded tiles in a row (~135×100 each):
  1. Docs — light blue background, blue document icon, faint document watermark.
  2. Slides — light peach, brown presentation-screen icon, faint watermark.
  3. Design — light purple, purple palette icon, faint watermark.
  4. A light grey tile with a centred `+`.
- Below: artifact cards in a two-column grid.
  - Card 1: light grey thumbnail with a wireframe of grey blocks; title
    `GPT-6.2 vs Fable 5.2 Prompts`; metadata `Nov 21`, eye icon `381`, globe icon.
  - Card 2: light blue thumbnail containing a tiny document preview headed
    `Discover Kosovo: Team Member Reports, Sprint 1 and 2`; title
    `Discover Kosovo: Team Member Report…`; metadata `Docs · Oct 27`.

## Functionality
- Tabs filter artifacts: All / Yours / Shared with you (active state updates).
- Magnifier button opens the shared search palette if present, otherwise an
  in-page search input that filters artifact cards.
- Filter/sliders button opens a menu (type: Docs / Slides / Design, sort by
  date/name) that actually filters/sorts.
- List-view button toggles grid/list layout.
- `+` and the four Make-something-new tiles open a "Create artifact" dialog
  with a type preselection, name input and Create action; new artifact cards
  are added and persisted in localStorage.
- Artifact cards open a detail modal with a larger preview, title, type/date,
  and actions Open / Duplicate / Delete (all functional, persisted).
- Sidebar items and account chip work like `/new`; Recents toggle and View all
  work.
- Responsive to 390px, keyboard accessible, focus-visible, aria labels, no
  console errors, no dead `href="#"`.

Use only KEEL branding and reuse the icon/line-art style from `new.html`.
