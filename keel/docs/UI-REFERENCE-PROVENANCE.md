# UI reference provenance

Keel's `architecture.md` requires clean-room implementation: interface facts may be matched for compatibility, but expression is Keel's own. This log records **behavioural patterns only**. No source file, stylesheet, component markup, logo, wordmark, screenshot or branded colour system was copied from a reference repository.

| Pattern adopted | Reference (behavioural) | Keel implementation | Evidence |
|---|---|---|---|
| Persistent app shell with collapsible/resizable side regions | OpenCode `packages/app/src/shell/shell.tsx` | `fleet-next/app/page.tsx`, `app/ui.css` (`.keel-app`, `.keel-sidebar`, `.keel-right`, `ResizeHandle`) | shell renders four surfaces + two global destinations; widths persist |
| Global command palette (`Ctrl/Cmd+K`), grouped searchable actions | OpenCode settings/shell | `app/page.tsx` `CommandPalette` + `lib/state.tsx` `commands` | keyboard handler ignores typing targets |
| Session/work timeline with grouped activity and progressive disclosure | OpenCode `session/timeline`, OpenMan `task/work-log.tsx` | Subagent A `features/cowork/` | pending subagent report |
| Human-readable tool activity groups + live active row | OpenMan `task/tools.tsx`, Orgo `ActivityLine.tsx` | Subagent A `features/cowork/` | pending subagent report |
| Approval cards distinguishing once / always / never with scope | DeepSeek `ui-approval`, OpenMan approvals | Subagent A; decision values verified in bridge routes (`once\|always\|never`) | `UI-BACKEND-CONTRACT.md` §3.1 |
| Agent roster with identity, state and details panel | Orgo `Sidebar.tsx`, `DetailsPanel.tsx` | Subagent C `features/fleet/` | pending subagent report |
| Subagent tree with parent/child and safe continuation | DeepSeek `ui-subagent` | Subagent C (only if real row hierarchy exists) | pending subagent report |
| Task-first workspace, plan cards, deliverable cards | OpenMan `task-view.tsx`, DeepSeek `ui-plan` / `ui-deliverables` | Subagents A & C | pending subagent report |
| Resizable multi-pane developer workspace with tabs | OpenCode `session/screen.tsx` | Subagent B `features/duet/`, `components/ui.tsx ResizeHandle` | pending subagent report |
| Capability catalogue with honest status states | DeepSeek modular client packages, OpenCode settings | Subagent D `features/capabilities/` | pending subagent report |
| Guided first-run, required/optional/later checklist | Nick's Stack first-boot flow | Subagent E `features/onboarding/` | pending subagent report |
| Theme tokens applied before first paint | DeepSeek `ui-theme` | `app/layout.tsx` inline `themeInit` | implemented |

## Licensing note

The reference repositories expose MIT licences, but Keel's own clean-room rule takes precedence. No reference code was imported. Keel's fonts (Inter, Space Grotesk, JetBrains Mono) were already present in the repository and are audited separately in `THIRD_PARTY_NOTICES.md` / `MODEL-AND-VOICE-LICENSES.json`. No new third-party runtime dependency was added by this workstream; the icon set is original SVG drawn for Keel.
