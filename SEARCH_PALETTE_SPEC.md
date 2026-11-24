# Sidebar Search palette spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY as a reusable search
palette opened by the sidebar `Search` button on the light Keel app pages.

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Create ONLY:
- `keel/site/ui/search-palette.css`
- `keel/site/ui/search-palette.js`

Do NOT edit any HTML file or any other CSS/JS. Do NOT commit, push or deploy.
Integration into pages is done by the coordinator.

## Design
- Full-screen dimmed/blurred backdrop; centered white rounded modal ~650px
  wide, max-height ~80vh, soft shadow, top offset ~5vh.
- Top: search input with placeholder `Search`, no border, large padding,
  focus automatically. Top-right `×` close button.
- Tab row: `All` (active, light grey rounded pill), `Artifacts`, `Sessions`,
  `Code`, `Projects`, `Scheduled`. Thin divider below.
- Small grey section label `Recents`. Rows (chat-bubble icon unless noted):
  1. `Keel harness build plan` — highlighted/selected with grey background;
     right side has `…` and a `↩` icon.
  2. `GPT-6.2 vs Fable 5.2 Prompts` — right side text `Shared with you`.
  3. `Keel project review and plan`
  4. `Keel project plan review`
  5. `Test exercise answers`
  6. `Team member project reports`
  7. `Discover Kosovo: Team Member Reports, Sprint 1 and 2 · Docs` — document
     icon (blue).
  8. `Connecting AutoCAD with MCP`
- Small grey section label `Actions`; one row with icon `New session`.
- Bottom bar with thin top divider: `Close Esc`, `Change type ← →`, `Filters /`,
  `Actions Alt ↩` on the left; `Compose Tab` on the right. Small grey text.

Brand is Keel. No Claude/Anthropic text.

## Behaviour
- Export a global `KeelSearchPalette` with `open()` / `close()` / `toggle()`.
- On load, auto-bind to every element that looks like the sidebar Search
  trigger: `[data-search-trigger]`, `a[id="nav-search"]`, or a sidebar element
  whose text is exactly `Search` (avoid binding to the in-page search input on
  `/plugins`). Clicking opens the palette and focuses the input.
- Closing via ×, backdrop click, or Escape.
- Typing filters rows live (hide non-matching rows, hide empty section labels).
- Tabs filter by type and update active state; `All` shows everything.
- Arrow keys move the selected row; Enter activates it (dispatch a custom
  `keel:search-select` event with the row's title and type on `document`).
- `…` on a row opens a tiny menu (Copy link / Rename / Delete) that shows a
  transient note; `↩` activates the row.
- `New session` action dispatches `keel:search-action` with `new-session`, or
  navigates to `/new` if no listener exists.
- Bottom shortcuts work: Escape closes; `/` focuses filters note; Alt+Enter
  shows an Actions note; Tab focuses the first row / moves focus; arrows change
  tab when focus is on the tab row.
- Responsive: below 600px the modal becomes nearly full width; no horizontal
  overflow. Keyboard accessible with aria roles (`dialog`, `listbox`,
  `option`), aria-expanded on the trigger, focus trap and focus restoration.
- No external network calls, no console errors.
