# `/projects` page design spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY at
https://keel-desktop.vercel.app/projects — same light app shell as `/new` and
`/plugins`, with Projects selected. Brand is **Keel** everywhere.

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Create ONLY:
- `keel/site/projects.html`
- `keel/site/ui/projects.css`
- `keel/site/ui/projects.js`

Do NOT edit any other file. Do NOT commit, push, or deploy. Integration of the
shared search palette is done by the coordinator.

## Layout
### Left sidebar
Identical to `new.html` / `plugins.html`: Keel wordmark + collapse icon;
`+ New`, `Search`, `Projects` (highlighted grey), `Artifacts`, `Plugins`;
`Recents ˅` with the exact ten recent chat names and `View all`; bottom
account chip `Elios · Free` + collapse icon.

### Main area
- Top row: serif `Projects` heading on the left. On the right: a magnifier
  search icon button, a sort (up/down arrows) icon button, and a black
  `New project` button.
- Centred empty state, vertically around 40% down:
  - line-art icon of two stacked boxes and a hand (hand-drawn/outline style),
    ~70px.
  - `Looking to start a project?`
  - `Upload materials, set custom instructions, and organize sessions in one space.`
  - a light grey rounded `New project` button.

## Functionality
- Both `New project` buttons open a real "Create project" dialog with a name
  input, optional description, an "Add materials" area (shows a note that file
  upload belongs to the local app), Create and Cancel. Creating adds a project
  card to the page (replacing the empty state) and persists it in localStorage.
- Magnifier button opens the shared search palette if available, otherwise an
  in-page search input that filters project cards.
- Sort button opens a small menu (Name A–Z, Name Z–A, Newest, Oldest) that
  actually reorders project cards.
- Projects have a `…` menu with Rename / Duplicate / Delete (all functional,
  persisted), and clicking a project opens a detail panel showing its name,
  description and linked sessions.
- Sidebar items and account chip work like `/new` (navigation or informational
  notes). Recents toggle and View all work.
- Responsive to 390px, keyboard accessible, focus-visible rings, aria labels,
  no console errors, no dead `href="#"`.

Use only KEEL branding and reuse the icon/line-art style from `new.html`.
