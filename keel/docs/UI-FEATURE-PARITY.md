# UI feature parity checklist — classic Fleet / desktop UI vs unified `fleet-next`

**Evidence base:** `desktop/fleet/fleet.js` + `desktop/fleet/index.html` (classic reference),
`src/keel/fleet/routes.py` / `service.py` / `db.py` (authoritative bridge),
`fleet-next/features/fleet/**` and `fleet-next/tests/features/fleet/**` (new implementation + specs).
**Rule:** `implemented` needs both a real bridge route and a working, tested UI flow.
`api-missing` means the Python bridge has no route at all; `blocked` means a route exists but a
host/hardware/credential gate prevents verification here. Statuses below were verified in the
Fleet finalization round (see “Verification evidence”).

## Fleet

| Capability | Classic UI | Bridge API (route evidence) | Unified UI | Status |
|---|---|---|---|---|
| Agent roster / identity / status / search | yes | `GET bots` `routes.py:136`; `bots/:id/rows` `routes.py:315`; SSE `events` `routes.py:140,1727` | `Fleet.tsx`, `Agents.tsx`, `Activity.tsx`, `support.ts` | implemented |
| Agent create (name/role/engine/notes/hue) | yes | `POST bots` `routes.py:721` | `Agents.tsx` | implemented |
| Agent fork / rename / delete | yes | `bots/:id/{fork,update,delete}` `routes.py:1346,1469,1482` | `Agents.tsx` | implemented |
| Details drawer — Studio / Engine / Notes / Tasks / Permissions / Activity | yes (same six tabs in `index.html:246-251`) | `bots/:id/update`, `tasks`, `bots/:id/{policies,audit,rows}` | `AgentDetails.tsx` | implemented |
| Engine config (incl. reasoning effort allow-list) | yes | `update_bot` allow-list `service.py:245-278` | `AgentDetails.tsx` (select limited to `minimal/none/low/medium/high/xhigh/max`) | implemented |
| Transcript / live activity / approvals / questions / delegation | yes | `bots/:id/rows`, SSE, `approvals/:id/decide` `routes.py:1512`, `asks/:id/answer` `routes.py:1396` | `Activity.tsx` | implemented |
| Honest derived status (no fabricated “working”) | partial | no `bots.state` column; statuses derived from `step`/`turn_end` rows | `support.ts:deriveActivity` (failed terminal reasons only from `turn_core.py`) | implemented |
| Groups: create / chat / delete | yes | `groups` `routes.py:153,747`; `groups/:id` `routes.py:281`; `messages` `routes.py:1301`, `delete` `routes.py:1296` | `Groups.tsx`, `Fleet.tsx` (real group tab count) | implemented |
| Group workflows (one bounded round, member statuses, loop guard, 409 busy) | yes | `groups.py:69-153`; 409 `{queued:false,busy:true}` `routes.py:1324-1332` | `Groups.tsx` (seq-based round tracking, honest 409 warning, recheck) | implemented |
| Tasks CRUD / assign / status / cancel / reorder / events / undo | yes | `tasks` `routes.py:158,988`; `reorder` `routes.py:1022`; `tasks/:id/*` `routes.py:1035-1114` | `Tasks.tsx` (dedicated `cancel` route, real payloads) | implemented |
| Recoverable task delete (single undo snapshot) | partial | soft delete `db.py:301`, `service.py:1229`; `tasks/:id/undo` `routes.py:1039` | `Tasks.tsx` (“Undo delete” action after delete) | implemented |
| Routines create / edit / enable / disable / pause / resume / run / history | yes | `routines` `routes.py:175,1117`; `routines/:id/*` `routes.py:1137-1207`; 409 on paused/disabled/running | `Routines.tsx` (409 warning, pause reason, real run rows) | implemented |
| Library list / filters / upload / download / preview / delete confirmation | yes | `library` `routes.py:202,1211`; `library/:id/{download,preview}` `routes.py:245-278`; `delete` `routes.py:1277` | `Library.tsx` (preview offered for every real file; hard-delete warning) | implemented |
| Per-agent policy revoke | yes | `bots/:id/policies/revoke` `routes.py:1487-1507` | `AgentDetails.tsx` | implemented |
| Audit / decision history with real filters | yes | `bots/:id/audit?limit=` `routes.py:334,341` | `Audit.tsx`, `AgentDetails.tsx` (filters match real event / decision / outcome values) | implemented |
| Parent/child subagent presentation **where the row schema supports it** | partial | `delegated` on `send_to_bot` step rows `turn_core.py:438-446`; `delegated_from` on child user rows `delegation.py:34-44`; no parent/child table | `Activity.tsx`, `support.ts` (both directions, links only when target is in the roster) | implemented (row-derived only) |
| Recoverable bot / group / routine / library delete | no | hard deletes: `service.py:454` (bot), `:921` (group), `:1484` (routine), `:1312` (library); no restore route | honest “permanent” wording in delete dialogs | **api-missing** (documented, not faked) |
| Agent transcript rewind + restore rows | partial | `bots/:id/{rewind,restore}` `routes.py:1363,1382`; UI client methods exist in `lib/api.ts` | not surfaced in Fleet drawer | **gap** (client supports it; no UI control added in this round — see “Still blocked / gaps”) |
| Markdown transcript export | partial | `bots/:id/export.md` `routes.py:344` | `bridge.exportUrl()` exists; no Fleet button | **gap** (route real, UI not added in this round) |
| Full parent/child hierarchy tree | no | no `parent_id` / child-id columns; rows only | explicitly not invented (`Activity.tsx`) | **api-missing** (honest note shown) |

### Recoverable delete audit (explicit verification)

- **Tasks:** `fleet_tasks.deleted_at` (`db.py:301`) + `service.py:1229` soft delete; `undo_task`
  (`service.py:1054-1080`) restores the single `prev_state` snapshot through
  `POST tasks/:id/undo` (`routes.py:1039`). The UI now exposes this real path.
- **Bots:** `delete_bot` (`service.py:454-465`) removes Library files and cascades rows; no
  bot-restore route exists. `bots/:id/restore` (`routes.py:1382`) restores **transcript rows**
  only, not the bot record. The delete dialog says so.
- **Groups / routines / library:** `delete_group`, `delete_routine`, `delete_library_entry`
  are hard deletes; library also deletes bytes from disk (`routes.py:1284`). No trash/restore
  route exists anywhere in `routes.py`. The dialogs say the action is permanent.

## Cowork / Code / Duet / capabilities (new unified scope — unchanged scope notes)

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

## Verification evidence (Fleet finalization round)

Commands (from `keel/fleet-next`):

```
npx tsc --noEmit
npx playwright test --config tests/features/fleet/playwright.config.ts
```

Result: `npx tsc --noEmit` exits 0; the Playwright run reports **8 passed (1.9m)**, 0 failed.
The run used a dedicated port (3397) and its own Next build directory (`.next-fleet-parity`) so
it did not disturb the shared E2E config or other workstreams.

Specs live in `tests/features/fleet/`. They install `page.route` fixtures whose bodies are the
real bridge envelopes (`{bots}`, `{group, rows}`, `{task}`, `{audit}`, `{files, usage_bytes}`,
`{routines}`, `{runs}`, `{queued, seq}`) and assert the exact mutation payloads captured at the
browser boundary. The SSE route receives a valid `text/event-stream` ping frame (no invented
event rows). Five specs use the shared strict console gate (zero `console.error` / `pageerror`);
three deliberately return a real HTTP 409/502 and use `testWithExpectedHttpError`, which excludes
only Chromium’s “Failed to load resource … 409/502” messages and still fails on every other
console error and on any page error.

Coverage: group creation `bot_ids`, 409/busy handling and seq-based round close; task create /
update / assign / cancel / delete / undo payloads; routine run 409, pause reason, history rows;
library upload base64, delete confirmation, preview route; policy revoke; global audit filters;
row-derived parent/child presentation; honest bridge-unavailable state; failed terminal reason
not shown as a successful turn.

## Still blocked / gaps

1. **No restore route for bot/group/routine/library delete** — `api-missing`; dialogs state the
   action is permanent. No trash UI was faked.
2. **No parent/child hierarchy table** — only row fields exist; the UI shows those links and
   explicitly declines to draw a tree.
3. **Rewind/restore rows and Markdown export are real routes but not surfaced in the Fleet
   drawer** — left as a documented gap rather than adding a control in this round.
4. **Live provider round-trip** — blocked on host (no provider credentials). Not faked.
5. **Renderer/packaging gates** (Electron asset root, Tauri path, public mirror) remain outside
   this feature-parity matrix; see `UI-ARCHITECTURE.md`.

## Renderer parity gate

This matrix covers **feature** parity, not packaging parity. Classic Fleet and `desktop/ui` must
remain available until those gates pass.
