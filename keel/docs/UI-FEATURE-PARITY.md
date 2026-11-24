# UI feature parity checklist — classic Fleet / desktop UI vs unified `fleet-next`

**Evidence base:** `desktop/fleet/fleet.js` (classic reference), `src/keel/fleet/routes.py` (bridge routes), `fleet-next/features/**` (new implementation).
**Rule:** a row is `implemented` only when both a real bridge endpoint and a working UI flow exist. Status here is pre-final-verification; update after integration testing.

## Fleet

| Capability | Classic UI | Bridge API | Unified UI | Status |
|---|---|---|---|---|
| Agent roster / create / fork / delete / rename | yes | `bots`, `bots/:id/{fork,update,delete}` | `features/fleet/Agents.tsx` | implemented (verify) |
| Agent details: Studio/Engine/Notes | yes | `bots/:id/update` | `features/fleet/AgentDetails.tsx` | implemented (verify) |
| Per-agent permissions / policy revoke | yes | `bots/:id/policies`, `policies/revoke` | `features/fleet/AgentDetails.tsx` | implemented (verify) |
| Audit / decision history | yes | `bots/:id/audit` | `features/fleet/AgentDetails.tsx` | implemented (verify) |
| Transcript / live activity | yes | `bots/:id/rows`, SSE `events` | `features/fleet/Activity.tsx` | implemented (verify) |
| Groups (create/chat/delete) | yes | `groups` + `groups/:id/{rows,messages,delete}` | `features/fleet/Groups.tsx` | implemented (verify) |
| Tasks CRUD / reorder / undo / events | yes | `tasks` + subroutes | `features/fleet/Tasks.tsx` | implemented (verify) |
| Routines create/edit/run/pause/history | yes | `routines` + subroutes | `features/fleet/Routines.tsx` | implemented (verify) |
| Library list / preview / download / upload / delete | yes | `library` + subroutes | `features/fleet/*` | implemented (verify) |
| Subagent hierarchy | partial (rows) | row fields only | derived only from real rows | conditional (no invented tree) |

## Cowork / Code / Duet / capabilities (new unified scope)

| Capability | Bridge API | Unified UI | Status |
|---|---|---|---|
| Conversation timeline + streaming | `bots/:id/rows`, SSE | `features/cowork/Timeline.tsx`, `WorkLog.tsx` | implemented (verify) |
| Composer + drafts + attachments | `bots/:id/messages` | `features/cowork/Composer.tsx` | implemented (verify) |
| Approvals (once/always/never) + questions | `approvals/:id/decide`, `asks/:id/answer` | `features/cowork/Timeline.tsx` | implemented (verify) |
| Deliverables / library links | `library/:id/{download,preview}` | `features/cowork/*` | implemented (verify) |
| Project trust / tree / file read+write | `projects` + subroutes | `features/code/` | implemented (verify) |
| Read-only git review | `projects/:id/review` | `features/code/workspace.tsx` | implemented (verify) |
| Terminal (detached shells) | `terminal/exec`, `shells/*` | `features/code/`, `features/duet/` | implemented (verify) |
| Browser preview | **no bridge route** | honest unavailable state | gap (documented) |
| Duet panes / tabs / persistence | client state only | `features/duet/` | implemented (verify) |
| Skills manage / install / enable / remove | `skills*` | `features/capabilities/SkillsPanel.tsx` | implemented (verify) |
| MCP servers + health | `mcp/servers`, `mcp/health` | `features/capabilities/McpPanel.tsx` | implemented (verify) |
| Connectors add/test/remove | `connectors*` | `features/capabilities/McpPanel.tsx` | implemented (verify) |
| Commands catalogue + guarded execute | `commands`, `commands/execute` | `features/capabilities/ToolsCommandsPanel.tsx` | implemented (verify) |
| Workflows discovery + guarded runner | `workflows`, `workflows/execute` | `features/capabilities/WorkflowsExtensionsPanel.tsx` | implemented (verify; runner, not builder) |
| Tool catalogue | no catalogue route | tool names only from live rows | gap (documented) |
| Extension marketplace | none | explicit unavailable state | gap (documented) |
| Providers (session + saved credentials) | `providers*` | `features/settings/ProvidersSettings.tsx` | implemented (verify) |
| Permissions / trust UX | bot mode + `projects/:id/trust` | `features/settings/SecuritySettings.tsx` | implemented (verify) |
| Egress rules / retention / diagnostics bundle | no routes | explicit unavailable states | gap (documented) |
| Onboarding + setup checklist | client + real setup endpoints | `features/onboarding/` | implemented (verify) |

## Renderer parity gate

This matrix covers **feature** parity, not packaging parity. See `UI-ARCHITECTURE.md` for the remaining renderer gates (Electron asset root, Tauri path, public mirror scope). Classic Fleet and `desktop/ui` must remain available until those gates pass.
