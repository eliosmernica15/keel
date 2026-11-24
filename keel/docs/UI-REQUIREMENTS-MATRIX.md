# Frontend requirements matrix — Keel completion round

Derived from the attached UI/UX implementation plan, `Keel_Master_Plan_v6.md`, and the actual code/tests in `fleet-next`. Backend-only requirements are excluded. Generated registry files (`PLAN-INDEX.json`, `parity.json`, `Keel_Master_Plan_v6.md`) were read but never hand-edited.

Statuses are evidence-based: `verified` needs passing tests/runtime evidence; `implemented, unverified` means code exists without a passing acceptance test; `partial` means some but not all acceptance criteria are met; `blocked` names the owner gate.

## Initial assessment (after recovery, before this round's implementation)

| Area | Total | Verified | Implemented, unverified | Partial | Not started | Blocked |
|---|---:|---:|---:|---:|---:|---:|
| Shared design system | 10 | 9 | 1 | 0 | 0 | 0 |
| Application shell | 14 | 13 | 1 | 0 | 0 | 0 |
| Cowork | 18 | 16 | 1 | 1 | 0 | 0 |
| Code | 14 | 13 | 1 | 0 | 0 | 0 |
| Duet | 12 | 8 | 1 | 2 | 1 | 0 |
| Fleet | 18 | 14 | 1 | 2 | 0 | 1 |
| Providers / models | 10 | 8 | 1 | 0 | 0 | 1 |
| Capabilities | 8 | 7 | 1 | 0 | 0 | 0 |
| Settings / security UX | 12 | 10 | 1 | 0 | 0 | 1 |
| Onboarding | 10 | 9 | 1 | 0 | 0 | 0 |
| Accessibility / performance | 14 | 11 | 1 | 0 | 1 | 1 |
| Renderer / packaging | 10 | 2 | 2 | 2 | 1 | 3 |
| **Total** | **150** | **120** | **13** | **7** | **3** | **7** |

- Verified completion: **120/150 = 80.0 %**
- Remaining implementation: **(3+7)/150 = 6.7 %**
- Implemented but unverified: **13/150 = 8.7 %**
- Blocked: **7/150 = 4.7 %**

### Non-verified requirements (initial)

- **Partial — Duet:** explicit builder/reviewer identity and permission separation; reviewer comment-only review/findings state.
- **Partial — Fleet:** kanban task board; organization chart; live agent wall; cost-per-agent (only when real data exists).
- **Partial — Cowork:** history virtualization for very long transcripts.
- **Partial — renderer:** Electron/Tauri packaged UI assertion; renderer switch decision.
- **Not started:** optional dictation; browser-native 200 % zoom verification; packaged Tauri launch.
- **Blocked:** live provider round-trip (no credentials); packaged Electron/Tauri GUI (no fresh build/binary); screen-reader hardware audit; live bridge 504 under heavy parallel load; default-model setter route absent in backend; network/egress rules API absent; renderer packaging decision (owner gate).

### Highest-priority outstanding items (initial)

1. Duet builder/reviewer identity and comment-only reviewer states (Agent B).
2. Fleet kanban / org chart / live wall / cost visualization from real data (Agent C).
3. Cowork session search/export/import and history virtualization where supported (Agent A).
4. Renderer/packaging evidence and decision record (lead; owner-gated).
5. Push reviewed work to GitHub continuously (lead).

## Final assessment

Updated at the end of this round with re-calculated counts and evidence.
