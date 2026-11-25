# UI reference provenance

Keel's `architecture.md` requires clean-room implementation: interface facts may be matched for compatibility, but expression is Keel's own. This log records **behavioural patterns only**. No source file, stylesheet, component markup, logo, wordmark, screenshot or branded colour system was copied from a reference repository.

| Pattern adopted | Reference (behavioural) | Keel implementation | Evidence |
|---|---|---|---|
| Persistent app shell with collapsible/resizable side regions | OpenCode `packages/app/src/shell/shell.tsx` | `fleet-next/app/page.tsx`, `app/ui.css` (`.keel-app`, `.keel-sidebar`, `.keel-right`, `ResizeHandle`) | shell renders four surfaces + two global destinations; widths persist |
| Global command palette (`Ctrl/Cmd+K`), grouped searchable actions | OpenCode settings/shell | `app/page.tsx` `CommandPalette` + `lib/state.tsx` `commands` | keyboard handler ignores typing targets |
| Session/work timeline with grouped activity and progressive disclosure | OpenCode `session/timeline`, OpenMan `task/work-log.tsx` | Subagent A `features/cowork/` | Cowork feature suite **28 passed**; prod E2E **144/144** (finalization round, `UI-TEST-MATRIX.md`) |
| Human-readable tool activity groups + live active row | OpenMan `task/tools.tsx`, Orgo `ActivityLine.tsx` | Subagent A `features/cowork/` | Cowork feature suite **28 passed**; activity asserted against real bridge rows, no invented events |
| Approval cards distinguishing once / always / never with scope | DeepSeek `ui-approval`, OpenMan approvals | Subagent A; decision values verified in bridge routes (`once\|always\|never`) | `UI-BACKEND-CONTRACT.md` §3.1; Cowork suite 28 passed |
| Agent roster with identity, state and details panel | Orgo `Sidebar.tsx`, `DetailsPanel.tsx` | Subagent C `features/fleet/` | Fleet feature suite **20 passed**; prod E2E 144/144 |
| Subagent tree with parent/child and safe continuation | DeepSeek `ui-subagent` | Subagent C (row-derived only; no `parent_id` route — full tree `api-missing`) | Fleet suite 20 passed for row-derived links; honest unavailable state for full hierarchy |
| Task-first workspace, plan cards, deliverable cards | OpenMan `task-view.tsx`, DeepSeek `ui-plan` / `ui-deliverables` | Subagents A & C | Cowork 28 + Fleet 20 passed; deliverable/library routes in `UI-FEATURE-PARITY.md` |
| Resizable multi-pane developer workspace with tabs | OpenCode `session/screen.tsx` | Subagent B `features/duet/`, `components/ui.tsx ResizeHandle` | Code+Duet feature suite **30 passed**; 72/72 viewport re-run, 0 overflow |
| Capability catalogue with honest status states | DeepSeek modular client packages, OpenCode settings | Subagent D `features/capabilities/` | Capabilities/Settings suite **17 passed** |
| Guided first-run, required/optional/later checklist | Nick's Stack first-boot flow | Subagent E `features/onboarding/` | Onboarding suite **13 passed**; Agent G `03-desktop-first-launch.spec.ts` keyboard tour check |
| Theme tokens applied before first paint | DeepSeek `ui-theme` | `app/layout.tsx` inline `themeInit` | implemented; system-theme first-paint **measurement** still implemented-unverified |

## Licensing note

The reference repositories expose MIT licences, but Keel's own clean-room rule takes precedence. No reference code was imported. Keel's fonts (Inter, Space Grotesk, JetBrains Mono) were already present in the repository and are audited separately in `THIRD_PARTY_NOTICES.md` / `MODEL-AND-VOICE-LICENSES.json`. No new third-party runtime dependency was added by this workstream; the icon set is original SVG drawn for Keel.

## Finalization note (2026-11-25)

- The `Get Keel Desktop` PWA shortcut is a **contract/behaviour pattern** borrowed from the distribution baseline (a contextual download entry), not copied markup or branding. The `site/manifest.webmanifest` implementation is verified by Agent G's `02-pwa-journey.spec.ts`; the parallel `fleet-next/app/manifest.ts` working-tree edit is uncommitted and **not verified**, so it is not recorded as an adopted, evidence-backed pattern here.
- Provenance evidence in this log is now tied to **passing test runs** (feature suites, prod E2E, a11y), not to the presence of files. Full subagent hierarchy, tool catalogue and extension marketplace remain explicitly unadopted. Fleet rewind/export controls and the unified-UI dictation control appeared as **uncommitted working-tree code** between 11:19–11:24 with specs present but no recorded pass; they are therefore **implemented-unverified**, not adopted/verified patterns in this log.
- No source file, stylesheet, component markup, logo, wordmark, screenshot or branded colour system was copied from a reference repository during this round.
