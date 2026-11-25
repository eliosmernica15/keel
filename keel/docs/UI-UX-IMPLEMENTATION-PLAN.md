# Keel UI/UX Unification & Implementation Plan

**Prepared:** 24 November 2026  
**Scope:** Keel's local-first desktop/PWA product, coding workspace, Cowork surface, Duet workspace, Fleet, settings and optional integrations.  
**Repository audited:** [eliosmernica15/keel](https://github.com/eliosmernica15/keel) (`main`)  
**Reference repositories:** OpenCode, Orgo Teammates, OpenMan, Nick's Stack, Clawdbot Channel Linq and DeepSeek Harness.

---

## 1. Executive direction

Keel should become one coherent, premium-feeling AI work environment rather than a collection of separately styled screens. The target is a single product shell with a consistent navigation model, design system, keyboard model, interaction language and state presentation across **Cowork, Code, Duet and Fleet**.

The recommended visual direction is to evolve Keel's existing **Obsidian & Gold** identity. Keep its dark, warm, editorial/technical character; refine the hierarchy, typography, spacing, surfaces and motion; and support a carefully tuned light theme. The references should contribute proven interaction patterns, not their branding or an unrelated visual identity.

The major implementation principle is **make every important backend capability discoverable, understandable and operable from the UI**. A feature does not count as user-facing because an API exists. It needs an entry point, a useful empty state, a loading state, a success state, an error state, clear permissions, and a complete user workflow.

### Recommended product outcome

A user can open Keel and immediately understand:

1. What they can ask Keel to do, and which workspace/project it will work in.
2. Which model/provider and permission mode are active.
3. What the agent is currently doing, what tools it used, what it changed, and what needs approval.
4. Which agents/subagents are working, waiting, completed or failed.
5. Where the resulting files, diffs, tasks, routines and history live.
6. How to configure models, workspaces, tools, skills, MCP, permissions, privacy and appearance without digging through disconnected settings pages.

### Primary UX principles

- **One shell, multiple work surfaces.** Cowork, Code, Duet and Fleet feel like related work modes, not four different products.
- **Progressive disclosure.** The default view is calm and task-focused. Deep tool details, execution traces, policy configuration and diagnostics are available when needed.
- **Observable agent work.** Explain actions as readable activity groups, not raw JSON or an endless stream of technical tool names.
- **Permission clarity.** Explain what will happen, which scope is being granted, and how long the grant lasts. Never blur “allow once” and “always allow.”
- **Local-first by default.** Local folders, provider keys, transcripts and agent data remain under Keel's established local trust/security model. Cloud-based reference features are optional concepts, not new mandatory dependencies.
- **Durable state.** Reloading, changing work surfaces or reconnecting should not lose the user's task, plan, progress or chosen layout.
- **Accessible by design.** Keyboard navigation, visible focus, screen-reader announcements, reduced motion and readable contrast are part of the interaction design—not a final patch.
- **Original Keel identity.** Do not import another product's logo, name, screenshots, brand system or signature composition.

---

## 2. Repository audit: what Keel has today

This is a source-level audit of the default branch, not a fresh end-to-end runtime verification of every screen. Before implementation, the first phase must run the actual app on supported platforms and capture a route/state inventory.

### 2.1 Current frontend surfaces and why they need unification

| Current location | Current role evidenced in the repo | UX implication / action |
|---|---|---|
| `keel/desktop/ui/` | Existing vanilla HTML/CSS/JS app used by the local bridge by default; `index.html`, `app.js`, `style.css`, settings and PWA assets. | This is the current local app surface to preserve while establishing parity and a single renderer decision. |
| `keel/site/` | Public static website plus `/app` mirror. `site/app.html` and `site/ui/app.js` describe a browser-only BYOK mirror with no local agent or disk access. | Keep the public mirror distinct from the local product. It may share tokens and visual components, but must clearly communicate its reduced capabilities. |
| `keel/desktop/fleet/` | Classic Fleet UI: agent rail, chat, groups, tasks, library, routines and a details panel with Studio/Engine/Notes/Tasks/Permissions. Its README calls this the Fleet reference implementation. | It currently contains capabilities that the newer Fleet Next README lists as missing. Do not retire it until functional parity is proven. |
| `keel/fleet-next/` | Next.js 15 / React 19 frontend. README describes Cowork, Code, Duet and Fleet surfaces, project/file workspace, right-side panels, model/context controls and Fleet management. | Strong candidate for the long-term unified product UI, but needs decomposition and feature-parity work before replacing the current renderer. |
| `keel/desktop-app/` | Electron wrapper that starts the Python sidecar and selects a UI directory. Its `uiRoot()` checks `site` before `desktop/ui`. | Audit and explicitly resolve which UI build Electron is supposed to ship. Do not let an incidental directory preference choose the product UI. |
| `keel/desktop/src-tauri/` | Tauri v2 shell; `tauri.conf.json` points `frontendDist` at `../ui`. | Keep its UI asset path aligned with the chosen canonical local frontend. |
| `keel/src/keel/webapp.py` and `keel/src/keel/fleet/` | Python bridge serves local UI/API and dispatches Fleet routes; `/api/run` streams NDJSON; Fleet route module owns Fleet endpoints. | Preserve the backend as the authoritative execution and permission boundary. Build UI adapters on top of existing APIs; do not duplicate agent/security logic in the renderer. |

**Critical path-selection risk:** the Electron wrapper currently checks the `site` folder before `desktop/ui`, while the local bridge's default `UI_DIR` is `desktop/ui` and the Tauri build uses `desktop/ui`. The public site's app JS explicitly describes a no-local-agent/no-disk mirror. This is not enough evidence to claim the packaged app is broken, because the runtime/build setup must be exercised, but it is a clear path-selection ambiguity that must be resolved and tested in Phase 0.

### 2.2 What the existing Keel UI already contains

The current `desktop/ui/index.html` is not an empty prototype. Its visible structure includes:

- Cowork and Code surface switches.
- Sidebar, new session, pinned items, recents, grouping/context actions.
- Prompt composers, attachments, file/folder picker, working-directory selector and model/permission chips.
- Provider/model configuration, usage, transcript controls, storage/privacy and import/export.
- Accessibility/readability, theme, motion and font controls.
- Execution policy editor, command test, network egress rules and operator/admin diagnostics.
- Skills, commands, workflows, MCP server list, connector inventory and plugin/module status.
- Tutorial overlay and voice/dictation-related controls.

`desktop/ui/app.js` includes handlers for streaming events, tool call/result rendering, sending/stopping runs, recents, settings, model/provider catalog, filesystem picker, workspace selection, tutorial, accessibility announcements, voice, admin and policy flows. This needs UX restructuring and visual consistency, not a blind replacement of all existing behavior.

The classic Fleet UI adds agent creation, groups, fleet-wide tasks, library, routines, execution history, standing policies and recent decisions. The Fleet Next README explicitly says some advanced functions remain available only in the classic UI, including group workflows, routine creation, library upload/deletion/previews, per-agent permission policies and audit-log view.

### 2.3 Current strengths to preserve

- Existing local Python bridge and local-first runtime model.
- Existing Obsidian & Gold token direction and font family choices: Inter, Space Grotesk and JetBrains Mono.
- Dark/light theme support and theme persistence.
- Streaming event handling and clear stop/kill mechanisms.
- Folder selection and trust gate; workspace context.
- Explicit execution modes and policy controls.
- Existing accessibility, screen-share-safe-mode and privacy features where present.
- Fleet persistence, SSE reconnection and approval workflows.

### 2.4 Main UX gaps and technical risks to solve

1. **Multiple UI roots:** `desktop/ui`, `site`, `desktop/fleet` and `fleet-next` can drift visually and behaviorally.
2. **Split navigation:** some features live in settings, some in Fleet, some in Code/Duet, and some only in classic Fleet.
3. **Monolithic React surface:** `fleet-next/app/page.tsx` is a very large page (about 4,024 lines in the audited snapshot), so adding features directly will compound maintenance and testing difficulty.
4. **Duplicated theme rules:** desktop and site CSS both carry large theme definitions; Fleet Next carries its own token set. Tokens need one source of truth and mapping for every surface.
5. **Capability discoverability:** skills, commands, workflows, MCP and connectors need one clear “Capabilities” area with truthful status and permission visibility.
6. **Activity presentation:** the product needs a shared, readable work timeline, step groups, plan cards, approval cards, changed-file summaries and a useful “waiting for you” state.
7. **Subagent visibility:** a coding agent should not hide child work; parent/child relationships, current activity, completion/failure and continuation need a predictable UI.
8. **Feature parity:** before switching the default frontend, the new UI must cover functions already working in the old UI.
9. **Runtime-path certainty:** Electron, Tauri, `keel serve`, Fleet and public mirror must load the intended UI and call the correct backend capability set.
10. **Evidence-based states:** never show a green “connected” badge, successful run, file-change card or healthy status unless the underlying API/event confirms it.

---

## 3. Reference repository review and how each should influence Keel

The following are **reference patterns**, not a requirement to port the source architecture. Links are pinned to each repository's default branch at audit time: OpenCode `dev`, Orgo Teammates `main`, OpenMan `main`, Nick's Stack `main`, Linq channel `main`, DeepSeek Harness `master`.

### 3.1 OpenCode — best reference for the core coding workspace

**Use it for:** app shell, resizable/collapsible navigation, session timeline, tabs and side panes, composer/model controls, keyboard shortcuts, searchable settings and deliberate motion.

Primary source locations:
- [App providers and composition](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/app.tsx)
- [Application shell](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/shell/shell.tsx)
- [Session screen](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/session/screen.tsx)
- [Session/timeline system](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/session/timeline)
- [Composer](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/composer)
- [Settings](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/settings)
- [Shared UI components](https://github.com/anomalyco/opencode/tree/dev/packages/ui/src/components)
- [Motion utilities and reduced-motion handling](https://github.com/anomalyco/opencode/tree/dev/packages/ui/src/motion)

**What to adapt:** a persistent shell with resizable sidebars, panel peeking, accessible tabs, global command palette, stable session timeline, scroll restoration, virtualized history, model selector, attach affordances and tested transition primitives.

**What not to copy blindly:** OpenCode uses SolidJS and its own plugin/runtime context. Keel's runtime is Python-first and the current modern frontend candidate is React/Next. Recreate the behavior in Keel's chosen stack; do not transplant framework-specific provider, routing or plugin code.

### 3.2 Orgo Teammates — best reference for Fleet and human-feeling agents

**Use it for:** teammate identity, agent roster, chat/details composition, live activity language, voice/dictation, per-agent drafts and shortcuts.

Primary source locations:
- [Frontend shell](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/App.tsx)
- [Sidebar](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/components/Sidebar.tsx)
- [Chat view](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/components/ChatView.tsx)
- [Composer](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/components/Composer.tsx)
- [Live activity line](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/components/ActivityLine.tsx)
- [Details panel](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/components/DetailsPanel.tsx)
- [Voice components and implementation](https://github.com/nickvasilescu/orgo-teammates/tree/main/web/src/voice)
- [Split stylesheet structure](https://github.com/nickvasilescu/orgo-teammates/tree/main/web/src/styles)
- [Design tokens](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/styles/tokens.css)

**What to adapt:** each agent has a clear avatar/name/role/provider identity; a readable “Searching files…”, “Running tests…” activity line; a details panel for notes, tasks, engine and permissions; per-agent draft preservation; voice dictation insertion at cursor; keyboard-first search/navigation.

**What to reject:** Orgo cloud computers, xAI and Composio are dependencies of that product, not dependencies Keel should acquire. Keel must continue to work locally with the user's own provider keys and local files.

### 3.3 OpenMan — best reference for task execution, work log and deliverables

**Use it for:** task-first conversations, tool work logs, approvals/questions/errors as cards, task status, computer/workspace panes, diffs and result artifacts.

Primary source locations:
- [Task screen/layout](https://github.com/nickvasilescu/openman/blob/main/src/components/task/task-view.tsx)
- [Conversation renderer](https://github.com/nickvasilescu/openman/blob/main/src/components/task/conversation.tsx)
- [Grouped work log](https://github.com/nickvasilescu/openman/blob/main/src/components/task/work-log.tsx)
- [Tool-to-readable-action mapping](https://github.com/nickvasilescu/openman/blob/main/src/components/task/tools.tsx)
- [Proposal diff](https://github.com/nickvasilescu/openman/blob/main/src/components/task/proposal-diff.tsx)
- [Task composer](https://github.com/nickvasilescu/openman/tree/main/src/components/composer)
- [Computer/file/preview panel](https://github.com/nickvasilescu/openman/tree/main/src/components/computer)
- [Artifact viewers](https://github.com/nickvasilescu/openman/tree/main/src/components/artifacts)
- [Product shell/navigation](https://github.com/nickvasilescu/openman/blob/main/src/components/shell/sidebar.tsx)

**What to adapt:** central conversation plus collapsible work log; tool-call grouping (e.g. “Read 4 files · Ran 2 commands”); readable names and target paths; live shimmer row only for the active call; plan step checklist; task side panel with computer/files/preview tabs; changed-file summary and delivered-file cards.

**What to change for Keel:** use a local filesystem/project view and Keel's own tools/security boundary. Do not adopt OpenMan's remote Orgo computer / Supabase architecture as a requirement.

### 3.4 Nick's Stack — best reference for first-run setup and operational handoff

This is a template/reproducible agent stack, not a front-end UI kit.

Primary source locations:
- [README and first-run flow](https://github.com/nickvasilescu/nicks-stack/blob/main/README.md)
- [Setup files and templates](https://github.com/nickvasilescu/nicks-stack/tree/main/files)
- [Docs/assets](https://github.com/nickvasilescu/nicks-stack/tree/main/docs/assets)

**What to adapt:** guided first launch; provider/device connection with a real verification step; optional communication-channel setup; clear “required / optional / later” checklist; setup that can pause and resume; simple status after onboarding.

**What not to adopt:** its gateway setup, phone/email/card integrations, external secret vault, Orgo-specific template and infrastructure are not Keel's product architecture.

### 3.5 Clawdbot Channel Linq — best reference for optional channel connection states

This repository has no product frontend. It is a channel plugin implementation and its README describes the user-facing behavior Keel may eventually need to represent.

Primary source locations:
- [Plugin README/configuration and supported behavior](https://github.com/nickvasilescu/clawdbot-channel-linq/blob/main/README.md)
- [Channel registration and account resolution](https://github.com/nickvasilescu/clawdbot-channel-linq/blob/main/src/channel.ts)
- [Inbound/outbound implementation](https://github.com/nickvasilescu/clawdbot-channel-linq/tree/main/src)

**What to adapt only if Keel supports external messaging:** per-channel connection card, account status, pairing/allowlist review, message delivery/read states, attachments and reaction support, clear opt-in and revoke action.

**Do not assume:** Keel currently has an integrated Linq channel, or that it should add Linq, SMS, iMessage or any public webhook dependency. This is an optional future integration surface.

### 3.6 DeepSeek Harness — best reference for modular UI features, approvals and agent/workflow disclosure

**Use it for:** modular UI domains, session/subagent navigation, approval scope, theme token architecture, plan review, durable workflow-run trees and final deliverables.

Primary source locations:
- [Client UI package catalog](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client)
- [Chat UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-chat)
- [Session UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-session)
- [Subagent UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-subagent)
- [Approval UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-approval)
- [Theme UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-theme)
- [Plan UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-plan)
- [Workflow-run UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-workflow-run)
- [Deliverables UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-deliverables)
- [Agent-team UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-agent-team)
- [Brand guidelines](https://github.com/deepseek-ai/deepseek-harness/blob/master/BRAND_GUIDELINES.md)

**What to adapt:** modular feature packages with explicit registration/unregistration; subagent tree with counts and safe continuation; approval cards that explain scope and stale-request protection; theme tokens applied before first paint; plan cards saved in history; workflow run/phase/member disclosure; end-of-turn changed-file and deliverable cards.

**What not to copy:** DeepSeek branding, logo, name presentation, its Cordis plugin framework or assumptions about its host runtime. The repository's own brand guidelines explicitly warn against implying official endorsement or using brand assets in a confusing way.

---

## 4. Clean-room, licensing and provenance rules

Keel's `architecture.md` identifies clean-room implementation and original code/assets/UI as design constraints. It says interface facts may be matched for compatibility, but implementation and expression are Keel's own. This plan therefore uses public repositories as **behavioral and structural references**. Reimplement the patterns independently in Keel.

The inspected reference repositories each expose an MIT `LICENSE` (OpenCode, Orgo Teammates, OpenMan, Nick's Stack, Linq channel and DeepSeek Harness). That permission may allow reuse subject to preserving notices and checking the complete dependency/asset provenance. It does **not** mean Keel should automatically copy their code: doing so would conflict with Keel's current original/clean-room UI direction. Keel's repository did not expose a root `LICENSE` file in the audit, so do not infer a general license grant for Keel code or assets.

Required guardrails:

- Do not copy logos, wordmarks, product names, screenshots, signature illustrations or branded color systems.
- Do not copy source code, stylesheets, strings or component markup into Keel by default. Reimplement behavior from observed product requirements and the descriptions in this plan.
- If the owner later explicitly chooses to incorporate a specific MIT component, make that a separate provenance decision: record source URL, exact commit, files/lines, license, copyright notice, modifications, dependencies and resulting THIRD_PARTY_NOTICES obligations; review the Keel clean-room rule first.
- Audit fonts, icon sets, animation packages, editor components and other assets separately. A repository-level MIT license does not automatically settle every nested asset or dependency.
- Maintain a `UI-REFERENCE-PROVENANCE.md` log with each adopted UX pattern, its source reference, Keel's independent implementation location and the test/evidence that validates the Keel behavior.

---

## 5. Recommended information architecture

### 5.1 One global application shell

**Global frame** (desktop):

- **Top bar:** Keel mark/name; current project/workspace; surface switcher (`Cowork`, `Code`, `Duet`, `Fleet`); connection/runtime status; command/search; notifications; user/operator menu.
- **Left navigation rail/sidebar:** New task/session; pinned and recent sessions; projects/workspaces; agent/fleet entry; tasks; library/artifacts; scheduled routines; capabilities; settings. Allow collapse, resize and keyboard reveal.
- **Main canvas:** content for the selected surface.
- **Right context panel:** contextual details that change with selection—plan, tool detail, files/diff, environment, model/context, agent details, tasks or permissions. It must be resizable, hideable, keyboard-accessible and remember its width/state per surface.
- **Global status strip:** active work count, waiting approvals/questions, background jobs and bridge/provider state. Do not show meaningless “green” when not actually verified.

**Mobile/narrow-window frame:** replace fixed sidebars with drawers; use tabs for the main/right panel; keep the prompt and Stop action reachable; never shrink the code editor/chat to unusable widths. Use OpenCode's mobile drawers/panel concepts as a reference.

### 5.2 Main product surfaces

| Surface | Primary job | Core screen |
|---|---|---|
| **Cowork** | General work, research, writing, file analysis and multi-step tasks. | Landing/home composer, conversation timeline, task progress and artifacts. |
| **Code** | Agentic coding in a trusted local project. | Project/file tree, conversation/work log, changes/diff, terminal and context/environment panels. |
| **Duet** | A focused multi-pane developer workspace. | Editor/open-file tabs plus Review, Terminal and Browser preview panes. |
| **Fleet** | Manage and collaborate with named agents and groups. | Agent roster, live conversation/activity, groups, fleet tasks, routines, library and per-agent settings. |

### 5.3 Global capabilities/settings destinations

- **Models & Providers:** provider connections, credential state, model catalog, default model, model capabilities, verify/test.
- **Capabilities:** Skills, MCP servers, tools, commands, workflows and future plugin/extension catalog. Distinguish “installed”, “enabled”, “requires setup”, “blocked by policy” and “not supported”.
- **Permissions & Security:** permission mode, allow/ask/deny rules, folder trust, network egress, screen-share safe mode, audit/decision history.
- **Workspace & Projects:** recent workspaces, trusted paths, project instructions, excluded folders, project-specific model/settings.
- **Automation:** schedules/routines, run history, pause/resume, next run and timezone.
- **Library & Deliverables:** files created by agents, previews, source task/session, download/reveal, recoverable deletion.
- **Appearance & Accessibility:** theme, typography, motion, density, contrast, screen-reader behavior, shortcut reference.
- **Privacy & Data:** transcript storage, retention, export/import, backups, local storage usage and cleanup.
- **System & Diagnostics:** local bridge, version, health, resource budgets, logs, startup state, safe diagnostic export.

---

## 6. Keel design system: Obsidian & Gold, refined

### 6.1 Identity and palette

Preserve the existing identity but formalize it into semantic tokens. Do not scatter raw hex values through each page.

Suggested starting palette based on current Keel CSS (validate against actual contrast in Phase 1):

| Role | Dark theme baseline | Light theme baseline | Usage |
|---|---|---|---|
| App background | `#0A0605` | `#F7F4EF` | Main canvas, restrained ambient background. |
| Elevated surface | `rgba(22,15,10,.70)` | `rgba(255,255,255,.78)` | Sidebar, header, modal, drawers. |
| Main text | `#F2F0EA` | `#241F1A` | Primary text. |
| Secondary text | `#8A8279` | `#6F685F` | Supporting labels and metadata. |
| Signature accent | `#E6D54C` | `#8A5A07` | Primary action, selected state and important focus. |
| Warm secondary accent | `#C2530A` | `#A5660A` | Small decorative/active cues, not broad fill. |
| Border | `rgba(255,255,255,.08)` | `rgba(46,32,14,.09)` | Quiet separation. |
| Success | `#6FE3B0` | `#1B6B47` | Confirmed success only. |
| Warning | `#E6D54C` | `#9A6A05` | Needs attention / pending approval. |
| Danger | `#F09A86` | `#C2432C` | Blocked, failed or destructive state. |

Gold should be an intentional signal, not the color of every icon, divider, badge and card. Large gold-filled areas should be rare. Use success/warning/danger colors semantically, with text/icons and labels—not color alone.

### 6.2 Typography

- Interface and body: Inter.
- Headlines, key screen titles and small branding accents: Space Grotesk.
- Code, file paths, tokens and terminal: JetBrains Mono.
- Establish text styles (`display`, `title`, `heading`, `body`, `label`, `caption`, `code`) with consistent line-height and a user-adjustable text/code/terminal scale.
- Keep labels and secondary text readable; avoid overly tiny 11–12px UI controls for frequently used actions.

### 6.3 Layout, spacing and surfaces

Create design tokens for:
- spacing scale (4/8/12/16/20/24/32/40/48/64px);
- corner radii (small controls, standard cards, large panels, modal);
- border strength, elevation and shadow levels;
- sidebar width, right-panel width, composer max-width and content gutters;
- z-index/layer order for popovers, menus, drawers, modals and toasts;
- focus ring, hover/pressed/disabled/loading states.

Use subtle glass/transparency only where it improves hierarchy: app frame, sidebars, overlays and floating panels. Keep chat text, code, diff and tool output on stable opaque/near-opaque surfaces for legibility. Film grain/ambient radial glow are background decoration and must not reduce contrast or consume GPU continuously.

### 6.4 Components to build once

`Button`, `IconButton`, `Menu`, `ContextMenu`, `Tooltip`, `Tabs`, `SegmentedControl`, `TextField`, `Textarea/ComposerInput`, `Select`, `Toggle`, `Checkbox`, `Badge/StatusPill`, `Card`, `EmptyState`, `Skeleton`, `Toast`, `Dialog`, `Drawer`, `ResizablePanel`, `Search/CommandPalette`, `Avatar`, `FileIcon`, `MarkdownRenderer`, `CodeBlock`, `DiffViewer`, `ActivityRow`, `TimelineGroup`, `ApprovalCard`, `QuestionCard`, `PlanCard`, `DeliverableCard`, `AgentCard`, `Progress/TokenMeter`.

Each component needs documented variants, keyboard behavior, hover/focus states, loading/disabled/empty/error states and responsive behavior. Keep feature-specific components out of a giant global component file.

### 6.5 Motion system

Use motion to explain state changes, not to decorate every object.

- Use short fade/slide entrances for new content, a restrained spring for drawers/panels, and small hover/press feedback.
- Animate only when an element enters, exits, changes position or changes state.
- Avoid animating large shadows, filters or background blur continuously.
- Respect `prefers-reduced-motion` and Keel's user motion setting at every animation entry point.
- Provide no-motion fallback; don't hide information behind animation.
- Keep message streaming stable: no whole-transcript reflow for every token; animate the active status indicator, not every text fragment.

Reference: [OpenCode motion package](https://github.com/anomalyco/opencode/tree/dev/packages/ui/src/motion) for springs/RAF/reduced-motion principles; reimplement only what the chosen Keel stack needs.

---

## 7. Detailed implementation phases

Each phase includes the Keel target areas, source inspiration and acceptance conditions. File paths are target locations based on the audited repository; Phase 0 may adjust them after confirming the active build path.

### Phase 0 — Runtime, UI and feature-parity audit (must happen first)

**Goal:** know exactly which UI build runs in Electron, Tauri, `keel serve`, classic Fleet and public mirror. Prevent a redesign from polishing the wrong asset folder.

**Keel targets:**
- `keel/desktop-app/main.js`
- `keel/desktop/README.md`
- `keel/desktop/src-tauri/tauri.conf.json`
- `keel/src/keel/webapp.py`
- `keel/desktop/ui/`
- `keel/site/`
- `keel/desktop/fleet/`
- `keel/fleet-next/`
- `keel/docs/IMPLEMENTATION-PROGRESS.md`

**Build steps:**
1. Start each supported entry point separately: local bridge/browser, Electron, Tauri (where buildable), classic Fleet route, Fleet Next and public `/app` mirror.
2. Capture real screenshots at desktop 1440×900, laptop 1280×800, compact desktop 1024×768, mobile 390×844 and 360×800.
3. Record every visible route/view, all settings panes, dialogs, popovers, loading/empty/error states and keyboard shortcut.
4. Trace the exact UI directory each app shell loads. Resolve the `site` vs `desktop/ui` precedence explicitly. Add a packaging assertion that checks the intended local product entry point is loaded.
5. Build a capability matrix: backend/API exists, UI entry point exists, user flow works, tests exist, externally verified or blocked. Mark unknown as unknown.
6. Compare classic Fleet vs Fleet Next behavior. List missing features and decide which frontend is the canonical target.
7. Make a renderer decision record. Recommended default: treat `fleet-next` as the candidate long-term unified UI because it already models Cowork/Code/Duet/Fleet, but do not make it default until it has the classic UI parity checklist, runs against the local bridge, and has a build/packaging path that works offline/local-first. Keep `desktop/ui` as the stable product until that gate passes. The public site mirror remains a separately scoped surface.
8. Produce an architecture diagram and migration map. No new backend feature work in this phase.

**Reference:** OpenCode app shell; Keel local bridge and current Fleet README; OpenMan's component-domain structure.

**Acceptance:** every current UI entry point is documented; no ambiguity about which assets ship; all existing screens have screenshots; the chosen renderer decision is recorded; no previously working feature is dropped.

### Phase 1 — UI foundations and token unification

**Goal:** one Obsidian & Gold design system used by every Keel UI surface.

**Keel targets (proposed):**
- `keel/fleet-next/app/globals.css` (if Fleet Next is chosen)
- `keel/desktop/ui/style.css` (legacy/current local app during transition)
- `keel/site/ui/style.css` (public mirror token mapping)
- new shared design token source under a chosen shared frontend directory, e.g. `keel/ui-system/tokens.css` and `keel/ui-system/components/` (final location decided after Phase 0)
- add `keel/docs/UI-DESIGN-SYSTEM.md`

**Build steps:**
1. Inventory raw CSS values and existing theme variables in all UI builds.
2. Define semantic tokens for backgrounds, panels, text, icons, borders, accent, states, spacing, radii, shadows, typography, focus and z-layers.
3. Map old variables to the semantic tokens so existing surfaces can migrate incrementally.
4. Create dark, light and system theme modes. Apply saved theme synchronously before the UI first paint to avoid flashing.
5. Add font family and text/code/terminal size settings while preserving sensible defaults.
6. Build the component primitives listed in Section 6.4.
7. Add a token/component preview page or storybook-like gallery with all states and both themes.
8. Verify contrast for normal text, secondary labels, controls, disabled controls and status states. Avoid using gold as the only state cue.
9. Add reduced-motion and high-contrast behavior to primitive components.

**References:** [Keel Fleet Next globals](https://github.com/eliosmernica15/keel/blob/main/keel/fleet-next/app/globals.css); [Keel desktop styles](https://github.com/eliosmernica15/keel/blob/main/keel/desktop/ui/style.css); [Orgo design tokens](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/styles/tokens.css); [DeepSeek theme UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-theme); [OpenCode shared UI](https://github.com/anomalyco/opencode/tree/dev/packages/ui/src/components).

**Acceptance:** the same control looks and behaves the same in Cowork, Code, Duet, Fleet and shared settings; switching theme changes all surfaces without first-paint flash; all controls have keyboard/focus/disabled states; no severe contrast failures; old behavior still works.

### Phase 2 — Unified shell, navigation and command system

**Goal:** replace disconnected navigation with one consistent shell.

**Keel targets:** chosen renderer's shell/layout/routes; for current candidate `keel/fleet-next/app/page.tsx` should be decomposed into `components/shell`, `features/cowork`, `features/code`, `features/duet`, `features/fleet`, `features/settings`, and `lib/api` or equivalent; keep `keel/src/keel/webapp.py` API unchanged unless a UI adapter requires a clearly versioned endpoint.

**Build steps:**
1. Implement global top bar, left nav, central canvas and right context panel.
2. Add unified switcher for Cowork / Code / Duet / Fleet. Preserve current surface selection across restart.
3. Build sidebar sections for New task, Recent/Pinned, Projects, Tasks, Library, Scheduled, Agents/Fleet, Capabilities and Settings. Hide destinations that truly have no feature yet; show a “not available yet” state only where a deliberate placeholder is useful.
4. Add resize/collapse/peek interactions for sidebars and remember widths per workspace/surface.
5. Add command palette (Ctrl/Cmd+K), searchable navigation/settings/actions, shortcut hints, command grouping and safe handling inside text inputs.
6. Add global notification/status center for approvals, questions, completed background tasks and failed runs.
7. Support narrow windows and mobile drawers. Ensure the composer and Stop control remain reachable.
8. Split the monolithic page into domain components and feature-owned state/data hooks before building additional pages.

**References:** [OpenCode shell](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/shell/shell.tsx), [OpenCode settings search](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/settings), [Orgo app shell](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/App.tsx), [OpenMan sidebar](https://github.com/nickvasilescu/openman/blob/main/src/components/shell/sidebar.tsx).

**Acceptance:** every core screen is reachable from the same nav; one command palette finds pages/actions/settings; keyboard shortcuts don't break typing; panels resize and restore; mobile has no horizontal overflow; tab/surface switching preserves active task and draft.

### Phase 3 — Cowork: chat, task timeline and composer

**Goal:** a polished general-purpose agent workspace where the user can see what Keel is doing without being overwhelmed.

**Keel targets:** Cowork renderer feature folder; existing event handling in `keel/desktop/ui/app.js` and API streams in `keel/src/keel/webapp.py`; relevant Fleet stream/render code in `keel/desktop/fleet/fleet.js` as behavior reference.

**Build steps:**
1. Build a clear empty/home screen: title, workspace context, large composer and useful quick-start prompts. Do not fill the page with fake metrics or decorative cards.
2. Build a durable message timeline with clear user/assistant separation, readable Markdown, code blocks, tables, images/file attachments, timestamps and message actions.
3. Add streaming that preserves scroll position and only follows new messages while the user is near the bottom; show a “Jump to latest” control when they scroll away.
4. Build an expanding work-log timeline. Group related tool calls into summaries. Render action categories and targets in human language (e.g. “Read 3 files”, “Searched the web”, “Ran tests in `src/`”), with raw input/output available on demand.
5. Show a live active row (what is happening now), elapsed time and waiting reason. Distinguish running, queued, paused, waiting-for-user, failed, cancelled and completed.
6. Add plan cards with ordered steps, active/done/stopped state, review/approve/reject and link to the completed result. The plan must survive reload.
7. Implement prompt composer: autosize, multiline, draft persistence per session, attachment chips, paste/drag-drop, slash commands, mention/reference support, model selector, permission mode, send/stop/retry and optional dictation.
8. Add file/image upload with explicit limits, upload progress, retry and failure feedback. Never claim an attachment was sent if it failed to upload.
9. Add finish-of-turn cards: changed files, generated deliverables, token/cost summary if real data is present, and links to open/review the file.
10. Add empty/error/reconnect states for backend unavailable, provider not configured, invalid model, session expired and streaming interruption.

**References:** [OpenCode session timeline](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/session/timeline), [OpenCode composer](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/composer), [OpenMan conversation](https://github.com/nickvasilescu/openman/blob/main/src/components/task/conversation.tsx), [OpenMan work log](https://github.com/nickvasilescu/openman/blob/main/src/components/task/work-log.tsx), [OpenMan tool mapping](https://github.com/nickvasilescu/openman/blob/main/src/components/task/tools.tsx), [DeepSeek chat UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-chat), [DeepSeek plan UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-plan), [DeepSeek deliverables UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-deliverables).

**Acceptance:** full Cowork task can be started, streamed, stopped, resumed/reloaded, reviewed and exported; work-log rows match actual runtime events; no fake progress; message history virtualization/scroll behavior works with long sessions; drafts and attachments do not silently disappear.

### Phase 4 — Code: project-aware coding workspace

**Goal:** make Code the professional developer workspace, not merely a chat tab with a folder selected.

**Keel targets:** Code feature domain in selected frontend; existing project/workspace API and file-picker endpoints in `keel/src/keel/webapp.py`; existing path/trust handling; current code view in `keel/fleet-next/app/page.tsx` and Duet implementation.

**Build steps:**
1. Left project explorer: project switcher, trusted workspace indicator, collapsible tree, search files, ignored/hidden paths, refresh and recent files.
2. First-time workspace trust screen: show absolute path, exact read/write/execute scopes and a clear trust/reject decision; support revocation from project settings.
3. Main work area: conversation/work log with file tabs; open files in a text editor/viewer with syntax highlighting, line numbers, search and safe save state. Keep editor support aligned with actual available APIs; do not fake full IDE features.
4. Right panel tabs: Review, Terminal, Browser preview, Context, Environment, Files and relevant tool details. Allow drag/resize and restore panel layout.
5. Review view: Git status, branches/log if available, diffstat and file-level diffs; show additions/deletions; provide hunk navigation and open changed file. Any write/apply/revert action must have explicit confirmation and use existing guarded backend operations.
6. Terminal: command input, streaming output, exit code, running/stopped state, copy output, rerun, background process controls and working-directory context. Dangerous actions must continue through Keel's permission/safety gates.
7. Browser preview: only show the supported project preview mechanism; clearly label it as local preview rather than a general-purpose internet browser if that is the boundary.
8. Context/environment panel: workspace path, current model/provider, context-window/token meter where data is available, permission mode, connector/tool availability, active shell/processes and environment facts that Keel actually exposes.
9. Add unsaved changes indicator, file save/reload conflicts and binary/large-file handling messages.
10. Add keyboard navigation for files/tabs/panes and quick-open path.

**References:** [OpenCode session screen and side regions](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/session/screen.tsx), [OpenCode session panels/timeline](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/session), [OpenMan task view](https://github.com/nickvasilescu/openman/blob/main/src/components/task/task-view.tsx), [OpenMan computer panel](https://github.com/nickvasilescu/openman/blob/main/src/components/computer/computer-panel.tsx), [OpenMan proposal diff](https://github.com/nickvasilescu/openman/blob/main/src/components/task/proposal-diff.tsx), [Keel Fleet Next documented Code surface](https://github.com/eliosmernica15/keel/blob/main/keel/fleet-next/README.md).

**Acceptance:** trusted project can be selected, explored, edited only through real tools/API, diff reviewed, terminal commands run under the normal permission system and project state restored after app restart. No path access beyond the backend trust model.

### Phase 5 — Duet: multi-pane developer workbench

**Goal:** turn Duet into a stable, keyboard-friendly workspace for people switching between code, terminal, browser preview and review.

**Keel targets:** Duet feature components and layout persistence in selected frontend; existing Duet tab/pane logic in `keel/fleet-next/app/page.tsx` and API adapters.

**Build steps:**
1. Establish a consistent workspace tab bar with Review, Terminal, Open File, Browser and per-file tabs.
2. Add resizable split panes, drag-to-reorder tabs, close/restore recent tabs and reset layout.
3. Keep tabs linked to the selected project and current session; switching projects should not accidentally show files from a previous project.
4. Implement Review as read-only Git review first; add controlled write operations only after their permission and rollback flows are verified.
5. Implement terminal tabs with process state and clear background process indicator.
6. Implement local browser preview with origin/port display and explicit close/refresh. Respect the app's sandbox/CSP rules.
7. Add quick open, command palette actions and keyboard shortcuts. Make all actions discoverable via tooltips/shortcut reference.
8. Make pane layout responsive: collapse into tabbed panels at narrow widths, preserve useful minimum widths on desktop.

**References:** [OpenCode session panel layout](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/session/screen.tsx), [OpenCode shell/panel motion](https://github.com/anomalyco/opencode/blob/dev/packages/app/src/shell/shell.tsx), [Keel Fleet Next documented Duet UI](https://github.com/eliosmernica15/keel/blob/main/keel/fleet-next/README.md).

**Acceptance:** layout/tab state persists; opening/closing panes does not lose editor or task state; keyboard controls work; browser and terminal panels never break the app's local trust/security boundary.

### Phase 6 — Fleet: agents, groups, tasks, routines and library

**Goal:** make Keel Fleet the command center for humans and named agents working together.

**Keel targets:**
- `keel/desktop/fleet/index.html`, `fleet.js`, `fleet.css` (current parity source)
- `keel/src/keel/fleet/` API/runtime modules
- `keel/fleet-next/app/page.tsx` (current React candidate)
- proposed `features/fleet/{agents,groups,tasks,routines,library,activity,permissions}`

**Build steps:**
1. Agent roster cards: name, role, visual identity, provider/model, current state, last activity, task count and quick actions. Do not imply an agent is live if only a scripted/test agent exists.
2. Agent details drawer: Studio/Profile, Engine, Notes/Memory, Tasks, Permissions, Activity/History. Save feedback and error states must be visible.
3. Group creation and group chat: select 2–3 agents where that is the backend limit; show group member roles, activity and messages; prevent duplicate/recursive trigger loops at the API/runtime layer.
4. Subagent tree: parent, child and sibling hierarchy; direct-child progress totals; running first; open child conversation; follow up only when continuation is supported; Stop/interrupt only for live/runnable children; historical one-shot children read-only.
5. Live activity: one-line phrase and elapsed time (e.g. “Reviewing `auth.py` · 1m 12s”), status dot and a “waiting for you” reason. Expand to detailed work log when selected.
6. Fleet tasks: list/board filters, create, priority, assignee, status, progress, timeline/events, detail and links to the source agent/session. Include empty, overdue, cancelled and failed states.
7. Routines: templates and manual schedule; timezone-aware next run, last run and run history; pause/enable, run now, edit and delete; explain missed-run behavior and whether unattended execution requires approval.
8. Library: file grid/list, filter by agent/task/type, quota/usage if real; preview supported formats; download/reveal; recoverable delete; upload only if the backend supports it.
9. Audit/decision history: filter by agent, tool, date and result; show permission decision and exact scope; never expose secrets in log content.
10. Restore missing parity features from classic Fleet before the Next UI becomes default: groups, routine create/edit/run history, library upload/delete/preview, per-agent policy management and audit log view (verify each against current API/tests before declaring complete).

**References:** [Keel classic Fleet UI](https://github.com/eliosmernica15/keel/tree/main/keel/desktop/fleet), [Keel Fleet Python backend](https://github.com/eliosmernica15/keel/tree/main/keel/src/keel/fleet), [Keel Fleet Next README and explicit parity gaps](https://github.com/eliosmernica15/keel/blob/main/keel/fleet-next/README.md), [Orgo sidebar/chat/activity/details](https://github.com/nickvasilescu/orgo-teammates/tree/main/web/src/components), [DeepSeek subagent UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-subagent), [DeepSeek agent-team UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-agent-team), [DeepSeek workflow-run UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-workflow-run).

**Acceptance:** every roster, group, task, routine and library interaction maps to a working backend operation; live status matches SSE/events; reload/reconnect rebuilds the same state; child-session navigation is correct; permissions remain enforced by the Python runtime.

### Phase 7 — Capabilities hub: Skills, MCP, Tools, Commands and Workflows

**Goal:** give users one understandable place to discover and manage what Keel can do.

**Keel targets:** existing `desktop/ui/index.html` settings panes (`pane-skills`, `pane-commands`, `pane-workflows`, `pane-connectors`, `pane-plugins`); `app.js` loaders (`loadSkills`, `loadConnectors`); existing Python modules for skills/MCP/commands/workflow/capability endpoints; equivalent feature area in chosen renderer.

**Build steps:**
1. Create a Capability Hub with tabs/sections: Skills, MCP Servers, Tools, Commands, Workflows and Extensions/Plugins (only when an actual extension system exists).
2. Each capability card shows what it does, source, scope (built-in/user/project), status, permission requirements, compatibility and last error.
3. Skills manager: search, categories, detail/preview, trusted source and provenance, injection/safety scan summary, enable/disable where supported, and project/user scope.
4. MCP manager: server list, stdio/HTTP type, configured/enabled state, tool/resource/prompt list, connection test, permission/approval path, logs and remove/disable. Secrets must be masked and never returned in the UI after save.
5. Tools view: discover tool description, schema and permission class; show availability by provider/model/host; allow policy changes only through existing backend policy endpoints.
6. Commands view: slash commands with descriptions, usage examples, shortcuts and source path; user-defined command management only if current backend accepts it.
7. Workflow builder/runner: first show existing deterministic workflows as readable steps and execution history; later add a visual builder only if backend has validated node schemas, dry-run, versioning and recovery.
8. Make missing systems explicit. Example: if there is no real plugin marketplace, say “Extension marketplace is not available in this build” rather than rendering a false install UI.

**References:** [DeepSeek modular client packages](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client), [DeepSeek workflow run](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-workflow-run), [OpenCode settings/catalog](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/settings), [Keel existing capabilities panes](https://github.com/eliosmernica15/keel/blob/main/keel/desktop/ui/index.html).

**Acceptance:** every displayed capability has an accurate source/status and actionable management path; no fake marketplace; changes persist in the right scope; MCP failures/permission denials are visible and non-fatal to other capabilities.

### Phase 8 — Settings, providers, permissions and trust UX

**Goal:** transform technical configuration into safe, understandable, searchable settings.

**Keel targets:** current settings HTML panes and `desktop/ui/app.js` settings loaders/savers; `keel/src/keel/webapp.py` settings/provider/model catalog endpoints; `keel/src/keel/permissions.py`, `settings.py`, `settings_store.py`, `secret_store.py` and policy APIs (confirm paths against current source before work).

**Build steps:**
1. Build searchable settings navigation with categories and breadcrumb/header. Preserve direct links to settings panes and search results.
2. Providers & models: cards for each provider; configured/unconfigured, verify/test, model list/search, model metadata, default selection and clear errors. Use actual `/api/providers`, model catalog and relevant credential endpoints.
3. Credentials: mask after save; never prefill the secret into a field or return it through a public projection. Add replace/remove, verify state, last checked and secure storage explanation.
4. Permission mode picker: Build / Accept Edits / Plan / Autopilot etc. Show concise consequences and current scope. Do not expose modes unsupported by the backend.
5. Policy editor: allow/ask/deny lists, validate errors inline, diff before save, activate/deactivate and test-command path. Make the non-configurable safety layer visible as protected, not toggleable.
6. Workspace trust: trusted paths, project-specific instructions, trust/revoke, dangerous path and symlink warning where applicable.
7. Egress/network rules: list allowed domains/rules, reason, scope and dry-run/test. Denied attempts should link to the relevant log/approval state.
8. Privacy/data: transcript location/retention, local storage usage, export/import, cleanup with confirmation, and recovery path if available.
9. Accessibility: text/code/terminal size, fonts, contrast, live announcements, keyboard-first navigation, reduced motion, and screen-reader status.
10. System diagnostics: bridge state, version, startup checks, health, background jobs, resource budgets and redacted diagnostics bundle.
11. Add contextual help and reset-to-default with explicit preview/confirmation.

**References:** [OpenCode settings architecture/search](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/settings), [DeepSeek settings/theme UI](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-settings), [DeepSeek approvals](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-approval), [Keel settings UI](https://github.com/eliosmernica15/keel/blob/main/keel/desktop/ui/index.html), [Keel provider catalog bridge work](https://github.com/eliosmernica15/keel/blob/main/keel/docs/IMPLEMENTATION-PROGRESS.md).

**Acceptance:** provider setup and policy modification can be completed without editing files manually; secrets remain masked; denied/dangerous actions remain blocked by backend safety rules; validation is inline and accurate; settings are searchable and retained across restart.

### Phase 9 — Onboarding, tutorial and optional integrations

**Goal:** get a new user to their first safe, real task quickly.

**Keel targets:** existing onboarding/tour in `desktop/ui/app.js` and `index.html`; provider/setup APIs; capability hub; optional integration adapters only if Keel adds them.

**Build steps:**
1. First-run welcome with three choices: start with Cowork, start with Code, or set up Fleet. Explain that Keel runs locally and uses the user's provider.
2. Provider setup: choose provider, enter secret, save, run a tiny verification request and show truthful success/failure. Make skip possible.
3. Workspace selection: browse folder, explain read/write/execute permissions, trust/decline and select starter project. Do not trust automatically.
4. Permission mode explanation and safe default; make the trade-off explicit.
5. Optional skills/MCP setup. Distinguish built-in defaults from third-party servers and show provenance/permissions.
6. Optional voice and communication channels with clear privacy/permission copy. Do not make Linq/Telegram/phone integrations mandatory.
7. Short interactive tour: send first prompt, inspect tool activity, approve one safe action, view a changed file, stop/resume a task.
8. Make onboarding resumable; user can revisit via Help / Take the tour.
9. Include setup checklist in sidebar until all required items are complete; hide completed items but keep the status page accessible.

**References:** [Nick's Stack README first-boot setup](https://github.com/nickvasilescu/nicks-stack/blob/main/README.md), [Orgo frontend setup/sign-in component structure](https://github.com/nickvasilescu/orgo-teammates/tree/main/web/src/components), [Keel existing guided tour](https://github.com/eliosmernica15/keel/blob/main/keel/desktop/ui/app.js).

**Acceptance:** user can skip optional setup, resume later, verify provider connection with a real check, trust a workspace deliberately, complete a first task without knowing CLI commands, and see an honest state when credentials or a provider are unavailable.

### Phase 10 — Optional messaging/notification channel UX (future, gated)

**Goal:** if Keel decides to support external messaging channels, design a safe channel-management experience without coupling core Keel to one vendor.

**Keel targets:** a future channel/integration feature module and its own API contract; do not implement by modifying unrelated chat components.

**Build steps:**
1. Define a generic channel contract before adding a vendor-specific connector: accounts, connection test, send/receive capability, attachments, read/delivery status, pairing policy and revocation.
2. Add channel connection cards that clearly identify external provider, credentials scope and data that leaves the device.
3. Pairing UI: pending request, requester identity, approve/deny, allowlist and group policy. No silent open-DM default.
4. Show sent/delivered/read/failed states only when provider events actually report those facts.
5. Add media attachment preview, retry, reaction support and account switching only for channels that support them.
6. Keep external integrations disabled until user opts in and grants required access.
7. Include revoke/disconnect and local data cleanup.

**References:** [Linq channel README](https://github.com/nickvasilescu/clawdbot-channel-linq/blob/main/README.md), [Linq account/channel handling](https://github.com/nickvasilescu/clawdbot-channel-linq/blob/main/src/channel.ts), [Orgo voice UI patterns](https://github.com/nickvasilescu/orgo-teammates/tree/main/web/src/voice).

**Acceptance:** integrations are optional; scopes/pairing are transparent; message states are evidence-backed; secrets are masked; revoke disconnects access; local-first functionality works with no messaging provider configured.

### Phase 11 — Motion, polish, accessibility and performance

**Goal:** make the whole product feel intentional, fast and predictable.

**Build steps:**
1. Apply shared motion tokens to screen transitions, panel resize/open, menus, toasts, activity changes, card appearance and tab switches.
2. Avoid motion on every message token; keep streamed content stable.
3. Run reduced-motion mode through every animation path, including panels, toasts, shimmer, count animations and first-run sequence.
4. Audit keyboard focus order, Escape behavior, focus restoration, modal trapping, menu arrow-key behavior, shortcut discoverability and input composition.
5. Test screen-reader announcements for agent started/paused/completed, approval requested, question pending, permission denied, error and new deliverable.
6. Verify color contrast and text scaling; support 200% zoom and high DPI.
7. Virtualize long transcripts, large file trees and long activity feeds; debounce expensive search and avoid re-rendering the entire shell on every streamed event.
8. Respect window visibility and app suspension; do not run expensive screen refresh loops when hidden.
9. Add skeletons and optimistic feedback only when rollback is reliable.
10. Ensure every empty state explains next action and every error includes a useful recovery path.

**References:** [OpenCode motion/reduced-motion](https://github.com/anomalyco/opencode/tree/dev/packages/ui/src/motion), [OpenCode timeline virtualizer](https://github.com/anomalyco/opencode/tree/dev/packages/app/src/session/timeline), [Orgo ActivityLine](https://github.com/nickvasilescu/orgo-teammates/blob/main/web/src/components/ActivityLine.tsx), [DeepSeek UI theme](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client/ui-theme).

**Acceptance:** no critical keyboard trap; no reduced-motion failures; no horizontal overflow on required viewports; long conversation/file lists remain responsive; screen-reader status messages are useful and not excessively repetitive.

### Phase 12 — Verification, rollout and legacy retirement

**Goal:** switch the canonical UI only after real workflow and feature-parity evidence.

**Build steps:**
1. Unit-test components, reducers/state machines, status mappings, approval lifecycle and panel state.
2. Add API contract tests for every new UI endpoint/adapter. Python runtime remains responsible for permissions and actions.
3. Playwright end-to-end flows: fresh install, provider setup, new Cowork task, streaming, stop/resume, file attachment, permission approval/deny, Code workspace trust, file/diff view, terminal, subagent launch/stop, Fleet group/task/routine/library, capability setup, theme, export/import and recovery.
4. Run visual regression screenshots for dark/light at desktop/tablet/mobile and key UI states.
5. Run accessibility automation plus manual keyboard and screen-reader walkthroughs.
6. Test Windows, macOS and Linux package/runtime paths. Include offline/no-provider/no-credentials cases.
7. Verify Electron and Tauri load the exact intended canonical UI build; assert public `/app` mirror still uses the browser-only provider-only scope.
8. Compare all classic Fleet interactions to the replacement feature parity matrix. Keep classic Fleet available behind a fallback route until the gate passes.
9. Roll out by defaulting one surface at a time; retain a rollback flag/config for the previous renderer while migration is in progress.
10. Update screenshots, docs, progress ledger, capability matrix and provenance register. Retire old UI only after explicit sign-off and passing tests.

**References:** [Keel AGENTS.md workflow and evidence rules](https://github.com/eliosmernica15/keel/blob/main/keel/AGENTS.md), [Keel Fleet verification roadmap](https://github.com/eliosmernica15/keel/blob/main/keel/docs/FLEET-ROADMAP.md), [OpenCode UI stories/components](https://github.com/anomalyco/opencode/tree/dev/packages/ui/src/components), [DeepSeek feature package tests](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/client).

**Acceptance:** all gates pass on actual packaged builds; no lost backend features; no fake/demo state in production; app can operate without external SaaS services; all paths honor the Python runtime's safety model; rollback remains possible until stable.

---

## 8. Implementation ownership and parallel work plan

Parallelize only after Phase 0 locks the renderer and Phase 1 stabilizes shared tokens/primitives. Do not let multiple agents edit the same global stylesheet or giant root page simultaneously.

| Workstream | Owns | Excludes | Exit gate |
|---|---|---|---|
| A. Shell & navigation | App shell, routes, sidebar, panel system, command palette, responsive shell. | Feature-specific timeline and Fleet business rules. | Every surface reachable; responsive shell and keyboard nav pass. |
| B. Cowork & timeline | Transcript, composer, activity/work log, plan, approvals/questions, attachments, deliverables. | Project explorer and terminal internals. | Full Cowork run tested end-to-end. |
| C. Code & Duet | Project browser, workspace trust UX, file tabs/editor, diff/review, terminal, browser preview, panes. | Provider credential storage and Fleet roster. | Project workflow passes with backend trust/permission enforcement. |
| D. Fleet | Agent roster, group UI, subagent tree, task/routine/library, per-agent settings. | Global shell and shared token editing. | Classic parity checklist satisfied. |
| E. Capabilities & Settings | Providers/models, skills/MCP/tools/commands/workflows, policies, system/privacy/appearance. | Agent runtime implementation; UI calls existing APIs. | Each displayed capability has an accurate API-backed state. |
| F. Quality & integration | Playwright, visual regression, a11y, performance, packaging and parity gates. | Changing feature UX without issue/owner agreement. | Platform matrix passes and reports artifacts. |

**File ownership rule:** assign exclusive folders per workstream. Shared primitives and tokens have one designated owner. Feature branches/PRs should include screenshots and test evidence. Merge in dependency order: tokens/primitives → shell → vertical slices → Fleet parity → polish → packaged release verification.

---

## 9. Quality gates and measurable definition of done

### Visual quality

- One coherent Keel visual identity in dark and light mode.
- No default browser styles or inconsistent one-off button/card variants.
- Predictable spacing, type, radii, focus, status color and panel behavior.
- No severe readability issue at 100–200% zoom.
- No horizontal overflow at 360×800, 390×844, 768×1024, 1024×768, 1280×800 and 1440×900.

### Functional quality

- Every visible button has a real action and failure feedback.
- No fabricated providers, model status, agent execution, progress, files changed or audit events.
- All core workflows preserve state after reload and reconnect.
- Every approval identifies the operation and scope. “Allow once” and “Always allow” are visually and semantically distinct.
- All file paths and destructive actions use the existing local backend trust, policy and permission gates.
- The UI never stores or logs full API keys.

### Accessibility quality

- Full keyboard navigation; visible focus ring; meaningful labels; logical focus restoration.
- Dialogs/drawers/menus have expected Escape and focus behavior.
- Live region messages announce meaningful state transitions without announcing every token.
- Reduced-motion fully respected.
- Contrast and color are not the only means of communicating status.

### Performance quality

- Initial shell shows quickly while data loads progressively.
- Long transcript and activity lists are virtualized or otherwise bounded.
- Streaming does not re-render the entire application for every token/event.
- No ongoing background polling/animation when the relevant panel/window is hidden unless required for correctness.

### Security and privacy quality

- Provider secrets remain masked and encrypted by existing storage services.
- Browser UI does not receive privileged secrets or bypass Python policy checks.
- Workspace access is limited by explicit trust and existing runtime rules.
- Sensitive paths/keys are redacted in screen-share safe mode and diagnostic exports.
- Optional remote connectors are opt-in, explain external data flow and are revocable.

---

## 10. Critical implementation decisions to make in Phase 0

1. **Canonical renderer:** Should `fleet-next` become the unified local product UI after feature-parity and packaging gates, or should the vanilla desktop UI remain canonical and be modularized? Preferred direction: Fleet Next as a future candidate, not an immediate cutover.
2. **Electron asset source:** Should Electron load a dedicated local UI build rather than selecting the public `site` directory first? This must be decided and tested.
3. **Fleet parity gate:** Which legacy Fleet features are required in the first unified release? Recommended baseline: all features currently supported by classic Fleet, including groups, routines, library operations, per-agent permission policies and audit/decision history.
4. **Native shell parity:** What is the release target between Electron and Tauri? One shared frontend build should feed both, or the differences must be documented and tested.
5. **Public mirror boundary:** Keep `/app` a visibly constrained browser-only surface, not a misleading copy of the local agent UI.
6. **Feature truth:** For each Capability Hub item, what is actually implemented, API-backed, verified and available in a packaged build?

---

## 11. Suggested project documentation additions

Create/maintain these documents as part of the project, rather than burying UI decisions in chat or commit messages:

- `keel/docs/UI-UX-IMPLEMENTATION-PLAN.md` — this plan.
- `keel/docs/UI-ARCHITECTURE.md` — canonical renderer, route map, component/domain ownership and runtime asset loading.
- `keel/docs/UI-DESIGN-SYSTEM.md` — tokens, typography, spacing, components, states and motion rules.
- `keel/docs/UI-FEATURE-PARITY.md` — current classic vs new UI feature matrix, including evidence/status.
- `keel/docs/UI-REFERENCE-PROVENANCE.md` — source URL, pattern learned, independent Keel implementation and license/provenance notes.
- `keel/docs/UI-TEST-MATRIX.md` — routes, viewports, themes, keyboard, a11y, screenshot and E2E coverage.

Do not edit generated plan/index artifacts as a shortcut for recording UI progress. Update the source plan/progress records and regenerate derived files only through Keel's documented scripts.

---

## 12. Final recommendation

Do not start by redesigning individual cards or adding another dashboard. Start with **Phase 0: audit and canonical-renderer decision**, then **Phase 1: shared Obsidian & Gold design system**, then build one complete vertical slice through the new shell: **Cowork conversation → visible work log → approval → changed-file/deliverable review**. That slice exercises the shell, timeline, composer, tool activity, permission state and file delivery end to end. Next bring Code/Duet across, then Fleet parity, then capabilities/settings and polish.

This sequence makes the new UX visibly better early, without abandoning the working Python runtime or losing functionality that currently exists only in the older screens.
