# `/plugins` page design spec (KEEL)

Reproduce the operator's uploaded screenshot EXACTLY at
https://keel-desktop.vercel.app/plugins — same light app shell as `/new`, with
the Plugins directory content. Brand is **Keel** everywhere (never
Claude/Anthropic; "Claude Code" -> "Keel Code"; "Claude history" -> "Keel history").

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Create ONLY:
- `keel/site/plugins.html`
- `keel/site/ui/plugins.css`
- `keel/site/ui/plugins.js`

Do NOT edit any other file. Do NOT commit, push, or deploy.

## Layout

### Left sidebar (same as `new.html`, light theme)
Keel wordmark + collapse icon at top; `+ New`, `Search`, `Projects`,
`Artifacts`, `Plugins` (Plugins highlighted with light grey rounded
background); `Recents ˅`; recent chat names: Keel harness build plan, Keel
project review and plan, Keel project plan review, Test exercise answers,
Team member project reports (doc icon), Connecting AutoCAD with MCP, Golden
Gate Bridge PowerPoint, Base quantities and SI units, AutoCAD seminar
document with cust…, Exam answers request declined, View all; bottom account
chip `Elios · Free` + collapse icon.

### Main content
- Heading `Plugins` (serif ~32px) with a `…` button at far right.
- Search row: light-grey rounded search input with magnifier, placeholder
  `Search`, ~600px wide. To its right: segmented filters `All` (active),
  `Connectors`, `Skills`; a sliders/filter icon button; black `Add ⌄` button.
- Section `Your plugins` + `Show all →` right. One row: GitHub icon, `GitHub`
  with small verified badge, subtitle `Built-in integration · By Keel`, `…`
  button at right.
- Section `Most used` + `Show all →`. Two-column grid of plugin rows, each with
  a small coloured icon/letter tile, bold name + verified badge, one-line
  description, and a grey meta line. Thin divider under each row:
  - Google Drive — Search, read, and upload files instantly — Connector · By Google
  - Gmail — Draft replies, summarize threads, & search your inbox — Connector · By Google
  - Google Calendar — Manage your schedule and coordinate meetings effortlessly — Connector · By Google
  - Microsoft 365 — Connect your Outlook mail, calendar, and files to Keel — Connector · By Keel
  - Canva — Search, create, autofill, and export Canva designs — Connector · By Canva
  - Google Sheets — Read, analyze, and update your spreadsheets — Connector · By Google
  - Slack — Send messages, create canvases, and fetch Slack data — Connector · By Slack
  - Notion — Connect your Notion workspace to search, update, and… — Connector · By Notion
  - Atlassian MCP — Search, read and update Jira, Confluence, Bitbucket, Loo… — Connector · By Atlassian
  - Google Docs — Edit, comment on, and summarize your documents — Connector · By Google
  - Figma — Generate diagrams and better code from Figma context — Connector · By Figma
  - Superpowers — Core skills library for Keel Code: TDD, debugging,… — Hook & skills · obra/superpowers
- Section `Popular workflows` + Show all →:
  - Unreal Engine Skills — Control Unreal Editor directly from Keel Code via MCP… — Hook & skills · epigames/unreal-engine-skills-for-cla…
  - Meshy — Generate 3D models, textures, and images, rig and animat… — Skills · meshy-dev/meshy-3d-agent
  - frontend-design — Frontend design skill for UI/UX implementation — Skill · keel/plugins-official
  - Unity — Unity's official plugin for Keel Code, with curated skills f… — Skills · unity-technologies/unity-agent-plugin
  - telegram — Telegram channel for Keel Code — messaging bridge wi… — Local MCP server & skills · keel/plugins-…
  - databricks — Databricks skills for the CLI, Apps, Lakebase, Model Servi… — Hooks, commands & skills · databricks/…
- Section `Trending` + Show all →: Zoho Mail (Connector · By Zoho Corporation),
  Lena (Connector · By Exutitive, Inc.), VistaPrint (Connector · By VistaPrint),
  Arca FDA, Trials & PubMed (Connector · By Arca), ThunderPhone (Connector · By
  ThunderPhone), Zoho Books (Connector · By Zoho Corporation).
- Section `New` + Show all →: aws-context (Commands, connector & skills · By
  Amazon Web Services), Slideworks (Connector · By Slideworks), AI Producer by
  OpusClip (Connector & skills · By OpusClip), Make (Connector · By Make),
  aws-continuum (Commands & skills · By Amazon Web Services), Harvest (Connector
  · By Harvest).
- Section `Categories` + Show all →, 4 columns × 5 rows with tiny icons:
  AI models & agents | Contacts & leads | Files & documents | Reference docs
  APIs | Databases | Finances | Sales
  Automation & workflows | Designs & media | Logs & errors | Servers & cloud
  Keel history | Email & messages | Marketing | Tickets & tasks
  Code | Engineering | Notes & memory | Websites
- Footer fine print centred: `Submission to the Directory is governed by the
  <a href="/terms">Software Directory Terms</a>; use of Connectors is governed
  by your relevant terms.`

## Functionality
Search input filters every plugin row live by name/description/meta. All /
Connectors / Skills segmented buttons filter by type (active state updates).
Filter icon opens a small menu (e.g. sort by name, verified only). `Add ⌄`
opens a menu with "Add plugin" / "Browse categories". Every plugin row opens a
detail modal with its name, description and an "Add to Keel" button that shows
a confirmation. Every `Show all →` expands/collapses that section. `…` buttons
open small menus. Category chips filter the directory. Sidebar items and
account chip work (same behaviour as `/new`: navigation to `/`, `/new`,
`/login`, `/download` or informational notes). Responsive down to 390px,
keyboard accessible, focus-visible, no console errors, no dead `href="#"`.
