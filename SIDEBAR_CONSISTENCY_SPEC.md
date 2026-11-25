# Sidebar consistency across the light app pages

Work ONLY in these files in the worktree's `keel/site`:
- `plugins.html`, `ui/plugins.css`, `ui/plugins.js`
- `projects.html`, `ui/projects.css`, `ui/projects.js`
- `artifacts.html`, `ui/artifacts.css`, `ui/artifacts.js`
- `downloads.html`, `ui/downloads.css`, `ui/downloads.js` (only if it has a sidebar — it does not, so skip)

Do NOT edit new.html/new.css/new.js, keel-chat.js, vercel.json, or docs.
Do NOT commit/push/deploy.

TASK:
1. Every sidebar item must be a real navigation control: `New` -> `/new`,
   Projects -> `/projects`, Artifacts -> `/artifacts`, Plugins -> `/plugins`,
   Search -> shared palette, Recents -> toggle, View all -> toggle. The URL
   must change when clicked. Use real `<a href>` or `location.assign`, and set
   `aria-current="page"` on the active item. Remove any informational-only
   handlers that prevent navigation for these four items.
2. Remove all hardcoded recent chat titles from the sidebars. Default recents
   state is empty (`No recent chats yet`) with View all hidden. Load any saved
   recents from localStorage key `keel_new_recents_v1` if present; otherwise
   empty. Page-specific content (plugin lists, projects, artifacts) stays.
3. Fix the mobile sidebar toggle so it reliably opens/closes: one state
   class on the root, `aria-expanded` on the toggle, backdrop click and
   Escape close, main area reflows. The recents filter must not leave the
   sidebar stuck open.
4. Keep each page's own functionality intact (search/filters, dialogs,
   persistence). Brand Keel everywhere; no dead `href="#"`; no console errors.

VERIFY: `node --check` on every JS file you edit; report exact results.
Do not claim browser verification.