# Orgo Teammates — clean-room behavior specification

This document describes **observable behavior** of a reference repository in Keel's own
vocabulary. It is a research input for the Keel plan, not a porting guide. No source code,
prompt text, branding, icons, logos, names, or other proprietary assets are reproduced here.

## 1. Source metadata

| Field | Value |
| --- | --- |
| Repository URL | `https://github.com/nickvasilescu/orgo-teammates.git` |
| Local clone | `C:\Users\Admin\Desktop\Claude clone\research\references\orgo-teammates` |
| Clone HEAD | `git -C "…\orgo-teammates" rev-parse HEAD` → `6546561f0ee15b30cb462a713ed03c51612fe4ce` |
| HEAD commit | `2026-11-19T01:12:51-08:00` — "Rename to Orgo Teammates, remove third-party artwork, security hardening (#13)" |
| Research date | 2026-11-23 |
| Repository licence / posture | MIT for project code; README calls the project experimental, with a basic review but no professional audit. |
| Derived/second-hand docs inside the repo | `docs/orgo-builder-guide.md` and `docs/xai-and-composio.md` are the repository authors' *own* research notes about third-party services; facts from them are marked below as "guide-reported" and were not verified against a live account. |

Files read (implementation first, documentation second):

- `server/src/env.ts`, `server/src/lib/auth.ts`, `server/src/routes.ts` (lines 1–240),
  `server/src/computer.ts`, `server/src/orgo.ts`, `server/src/idle.ts`, `server/src/vnc.ts`,
  `server/src/agent/prompt.ts`, `server/src/agent/subagents.ts`
- `tests/e2e.mjs`, `tests/voice-call.mjs` (file inventory; `voice-call.mjs` not quoted here), `.env.example`, `package.json`
- `SECURITY.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/orgo-builder-guide.md`,
  `docs/xai-and-composio.md` (inventory and architecture/integration sections)
- File inventory of `web/src/**`, `server/src/agent/**`, `server/src/lib/**` to locate the above.

## 2. Observed behavior, stated in Keel terminology

B1. **Layer split.** A browser front end owns only rendering; a single Node server owns the L4
    agent loop, the L5 tool registry and permission decisions, the L7 SQLite session store, and
    the provider adapter (L3) to a hosted Responses-style model API. Voice is a second front end
    that hands work to the *same* L4 loop rather than running an independent agent.
    (`README.md` "How it works"; `docs/ARCHITECTURE.md` components table.)

B2. **Session log shape.** A conversation is an append-mostly log of rows carrying a sequence, a
    per-agent revision counter, a kind, and a JSON body. A streaming reply rewrites the same row
    with a higher revision, so clients upsert by sequence; a per-agent generation counter resets
    the conversation. Model-visible input items are stored separately from user-visible rows, with
    server-side storage disabled and encrypted reasoning passed back unchanged. Only a bounded
    number of recent screenshots stay inline, and orphaned tool calls from an interrupted turn are
    repaired before the next provider call. This is close to Keel's split between session events,
    model request reconstruction, and the recorded-session projection. (`docs/ARCHITECTURE.md`
    "Transcript model"; `server/src/agent/history.ts` inventory.)

B3. **Agent instruction assembly is a pure projection.** Each turn builds the model instructions
    from durable state: the agent's role/label/description, primary-agent flag, personal-versus-team
    mode, a character-bounded memory section, per-agent skills, routine summaries, connected-app
    names, the visible roster of sibling agents, and user-authored instructions. The text is
    assembled in one function from rows; it is not a static file. Keel's equivalent is a registered
    system-prompt assembly unit fed by session projections. (`server/src/agent/prompt.ts`.)

B4. **Tool surface and approval policy.** The L5 registry mixes computer-use actions, a shell, a
    file-save action, memory actions, routine/task actions, inter-agent messaging, subagent
    controls, group-chat posting, approval/question cards, and third-party catalog meta-tools.
    Read-only third-party tools (slug patterns plus discovery tools) execute automatically;
    capable "do anything" meta-tools and any call whose inner tools cannot be inspected pause the
    turn behind an approval card. Card answers are allow-once, remember-a-per-tool-policy, or deny
    (which sends the model a refusal and instructs it not to retry). A new user message expires any
    still-pending approval. (`docs/ARCHITECTURE.md` "Approvals"; `server/src/agent/tools.ts`
    inventory.)

B5. **Agent addressing and delegation.** Agents address each other with a direct message tool;
    replies flow back through the same channel. Subagents are hidden child agents with their own
    context, screen, and identity, capped at four per parent, and are removed through a dedicated
    stop control. Group chats are a special agent row with members; a message routes to @mentioned
    members or all members up to a small cap. This is a task board and child-session pattern
    (Keel D3.4 / E3.5), not a shared-memory pool. (`server/src/agent/subagents.ts`,
    `server/src/agent/rooms.ts` inventory, `docs/ARCHITECTURE.md`.)

B6. **Workspace-to-compute mapping.** One remote Linux compute unit is created per user; each agent
    leases one *screen* (a separate X display with its own pointer and window manager) on that unit.
    The primary agent may use the boot screen. Screens are capped at four including boot; beyond
    that the least-recently-used idle lease is evicted, the victim's browser processes are killed,
    and its on-disk browser profile is retained for the next lease. Lease existence is re-checked
    against the provider on every use, and stale leases are deleted locally. This is Keel's screen
    leasing plus per-agent persistent browser profile, realized in a remote provider rather than
    locally. (`server/src/computer.ts` `MAX_SCREENS`, `screenFor`, `chromeProfilePattern`.)

B7. **Compute lifecycle as a guarded state machine.** A per-user state row moves through
    absent → creating → starting/creating → running → suspending → suspended → resuming → running,
    with stopped/error as recoverable states. Concurrent callers share one in-flight promise; a
    creation uses a deterministic idempotency key; a resume waits for an in-flight suspend to settle
    before issuing its own call; a start polls until running with a bounded timeout. A provider 404
    forgets the unit and its leases so the next call recreates it. All transitions emit a live
    state event to the front end. (`server/src/computer.ts` `ensureComputer`, `waitRunning`,
    `suspendComputer`, `refreshComputer`.)

B8. **Idle suspend/wake.** A pure decision function computes busy/wait/suspend from three inputs:
    any agent turn running, any viewer socket open, and the latest persisted activity timestamp.
    Default idle threshold 20 minutes, sweep every 60 seconds, with a dry-run mode that logs
    decisions without acting. Viewer open/close events feed the same decision so a human watching
    prevents hibernation. The next computer tool call wakes the unit through the normal ensure path.
    (`server/src/idle.ts`, `server/src/vnc.ts` `viewerOpened`/`viewerClosed`.)

B9. **Remote-execution seam.** Every provider call goes through one thin HTTP client: bearer key
    from server environment, abort timeout per call, typed error carrying HTTP status and provider
    code, base64 screenshot capture, screen selector via encoded query parameter, per-call timeouts
    derived from the requested command timeout, and a file-export helper. There is no generic
    provider abstraction here; the seam is a single module, which Keel would model as one provider
    implementation behind a capability seam. (`server/src/orgo.ts`.)

B10. **Viewer relay as a credential-hiding capability seam.** A WebSocket relay authenticates the
    user from the session cookie, checks Origin against a trusted-origin list, verifies that the
    named agent belongs to that user, performs the upstream RFB handshake with the root-equivalent
    desktop password *server-side*, then offers the browser an unauthenticated RFB session. In
    watch mode it parses client frames and drops keyboard, pointer, and clipboard input messages;
    unknown frame types are dropped ("fail closed"). Opening the relay marks the user busy for idle
    suspension. (`server/src/vnc.ts` `WatchFilter`, `attachVncRelay`, `relay`.)

B11. **Auth gate and signup policy.** All API paths except auth/health go through a session
    middleware; sessions are opaque random tokens in SQLite with an HTTP-only cookie, Secure when
    the public URL is HTTPS, SameSite=Lax, 30-day lifetime. A legacy cookie name remains accepted
    for upgrade compatibility. Passwordless local sign-in is only enabled when both the listen
    address and public URL are loopback. Signup is gated by an email/domain allow-list; on a public
    URL with no list, new signups are refused. The device-style sign-in binds the attempt to the
    originating browser with a short-lived cookie and trusts only the connected-account id recorded
    at start, not a callback query value. (`server/src/lib/auth.ts`, `server/src/env.ts`,
    `server/src/routes.ts` auth section.)

B12. **Secrets stay behind the gate.** Provider keys are required at process start and live only in
    the server environment; the browser receives only a short-lived voice secret. The desktop
    password is fetched server-side per relay session and never persisted. The inline bootstrap JSON
    escapes tag-breaking characters before embedding. (`server/src/env.ts`, `server/src/vnc.ts`,
    `server/src/routes.ts` `jsonForScript`, `SECURITY.md`.)

B13. **End-to-end verification is a real-runtime script.** A Playwright script drives a real server,
    real model calls, and a real remote computer: dev login via cookie, create a throwaway agent,
    streamed chat with a deterministic answer assertion, shell tool on the agent's leased screen,
    viewer watch → take control → hand back with screenshots, search palette, connector catalog,
    realtime voice audio chunks, group-chat @mention reply, settings tabs, and a final cleanup. It
    writes a structured summary with per-step timings, console errors, and screenshots, and exits
    non-zero on any failure. This maps to Keel's L9 real-flow E2E and screenshot-gallery evidence.
    (`tests/e2e.mjs`, `README.md` "Integration tests".)

B14. **Builder and integration guides are first-class artifacts.** The repo ships a dedicated
    builder guide and a separate integration guide. The builder guide labels each statement with a
    source section/line, marks inferred designs explicitly, distinguishes documented behavior from
    permission-table-only endpoints, and states that no live API call was made while writing it.
    The integration guide similarly tags statements as documented/inferred/recommended and records
    open questions to verify with a live key. Keel's C1.5/Y4.10 "one setup runbook per integration"
    and A1.22 internal builder guide are the direct analogue. (`docs/orgo-builder-guide.md`,
    `docs/xai-and-composio.md`.)

B15. **Guide-reported remote constraints (not locally verified).** The builder guide reports: four
    screens per Linux unit including boot; no inbound networking, so any in-unit host must dial out;
    about 600 control calls/minute per unit; suspend preserves memory but stop/cold-start does not;
    plan-capacity units hold resources while asleep; custom templates need a higher tier; the
    provider-hosted chat endpoint cannot target a screen and has no key slot for the model family
    this project uses. These are third-party service facts observed in the repository's research
    notes, not behavior of the software under study, and are included only as constraints that
    shaped B6–B9. (`docs/orgo-builder-guide.md` TL;DR and §§1–4, 8–10.)

B16. **Explicit honesty about residual risk.** The README states that write approvals for the
    third-party connector system do not cover every action an agent can take through its browser or
    shell, and that agents in one account share a compute unit. The security guidance tells
    operators to keep keys off screen and in recordings, use the narrowest provider key, set spend
    limits, and review approval requests rather than granting standing approvals. (`README.md`
    "Project status"; `SECURITY.md`.)

## 3. Security and permission implications

S1. **Remote execution is powerful by design; the boundary is the account, not the process.** Agents
    run with root-equivalent authority on a shared remote unit and can read each other's files and
    tokens. Isolation is per user (one unit per user), not per agent. Keel must not treat an agent
    screen or profile as a security boundary.

S2. **Viewer safety depends on where the filter runs.** Server-side RFB input filtering (B10) is a
    real enforcement point; a client-side "read-only" flag is not. The relay also keeps the desktop
    password out of browser code, and the Origin check prevents a third-party site from riding the
    session cookie. Unknown frame types are dropped rather than forwarded.

S3. **Standing approvals are the weak link.** "Always allow" persists a per-tool policy, and the
    project's own guidance warns against it. A policy that cannot express scope, expiry, or
    last-used review accumulates broad authority. Keel's time-boxed permissions and broadness
    scoring address this directly.

S4. **Idle hibernation is a liveness/cost trade with a race surface.** The suspend decision depends
    on viewer socket counts and in-memory turn status; a suspend landing mid-resume or a viewer
    connecting during a sweep must be settled by promise dedup and bounded polling (B7–B8). Any
    Keel equivalent must make the decision pure and testable, as this implementation does.

S5. **Signup is the cost gate.** Every new account can spend the operator's model, compute, and
    connector credits, so open signup is disabled on public URLs and an allow-list is mandatory.
    This is a deployment-level economic control, not an application permission.

S6. **Lease eviction is availability, not isolation.** Killing a victim's browser closes windows
    but leaves its profile on disk; the next agent gets a clean window set, not a clean identity.
    Cookie/session residue in a retained profile can still leak between sequential agents.

S7. **Research notes are not authority.** Guide-reported endpoints that exist only in key
    permission tables have undocumented request/response shapes; a Keel implementation must not
    design a seam around them without local verification.

S8. **No live-provider dependency may be introduced.** Keel is local-first; provider clients,
    model adapters, and screen relays must remain replaceable seams with offline behavior, never a
    mandatory account.

## 4. Keel applicability (feature IDs from `PLAN-INDEX.json`)

| Observed behavior | Keel feature IDs | Applicability |
| --- | --- | --- |
| B1 server-owned loop + provider adapter | `D1.12`, `D3.9`, `D3.1` | Confirms the loop/tools/session split; Keel keeps all of it local. |
| B2 row log, revisions, generation, separate model items, replay repair | `D2.1`, `D2.11`, `D2.13`, `D2.15`, `D6.15`, `V26` | Adopt the *shape* of durable facts vs model-visible input and recorded-session replay. |
| B3 state-derived agent instructions | `D6.17`, `B2.4`, `A1.22`, `Y1.1` | Instruction assembly as a registered, testable projection; no copied prompt text. |
| B4 approval card + per-tool policy | `E1.5`, `E2.2`, `W3.9`, `X5.3`, `X5.7`, `E7.20` | Keel already specifies richer approval answers; reuse once/always/deny as the baseline, add expiry and review. |
| B5 child agents, groups, caps | `D3.4`, `E3.3`, `E3.5`, `W2.2`, `W2.6`, `Y1.11` | Child sessions with identity, capacity, and launch permissions; do not copy the four-child number as a rule. |
| B6 screen lease + per-agent browser profile | `Y2.12`, `A2.3`, `E7.43`, `C9.4`, `B4.3` | Adopt leasing and persistent-profile separation; Keel's provider seam must own per-session resources. |
| B7 lifecycle state machine, idempotency, in-flight dedup | `A2.4`, `D2.16`, `Y1.32` | Mirrors suspend/wake and workspace-scope rules; keep resource identity separate from state. |
| B8 pure idle decision + dry run | `A2.4`, `A3.2`, `Y1.32`, `C9.4` | Reuse the pure decide/sweep split and dry-run affordance. |
| B9 single remote client with typed errors | `D3.1`, `D3.9`, `E1.15`, `C4.10` | Capability seam pattern; Keel's provider must be swappable and offline-capable. |
| B10 server-side VNC relay + input filter | `Y2.14`, `C1.4`, `W7.19`, `Y2.12` | Direct match; Keel should enforce watch-only in the relay, never in the client. |
| B11 auth gate, allow-list, browser-bound sign-in | `W7.7`, `W7.8`, `W8.1`, `D4.3` | Reuse domain-pattern allow-lists and browser-bound flows in Keel's local pairing. |
| B12 secrets behind the gate | `W7.1`, `W7.3`, `B3.6`, `A4.8`, `Y4.13` | Same threat model; Keel adds egress redaction and release secret scans. |
| B13 real-runtime E2E with screenshots | `A2.8`, `B5.6`, `E4.7`, `E4.15`, `Y2.23` | Reuse the structure (real flow, per-step evidence, failure screenshots, non-zero exit). |
| B14 builder/integration guides with evidence markers | `C1.5`, `Y4.10`, `A1.22`, `X10.1`, `Y3.20` | Adopt the *documentation discipline*: citations, inferred/documented markers, open questions. |
| B15 guide-reported provider constraints | `C1.11`, `C4.10`, `Z16` | Treat as reasons to keep an in-process executor and local-first target, not as Keel requirements. |
| B16 honest residual-risk statement | `D5.1`, `D5.2`, `D5.3`, `W7.19`, `A3.7`, `Y2.21` | Keel's safety notices and "proven vs unproven" page should say the same plainly. |

## 5. Do NOT copy

- Do not copy any source file, identifier naming scheme, function body, SQL string, or UI markup.
  This document states behavior only.
- Do not copy the reference product's name, logo, banner, avatar shapes/colors, agent names, labels,
  or any marketing copy into Keel.
- Do not reproduce the assembled agent instructions, tool descriptions, or prompt prose. Keel writes
  its own instructions from its own terminology and feature contracts.
- Do not copy the third-party guides' prose, citation markers, tables, or examples verbatim; record
  independently verified facts in Keel's own evidence docs.
- Do not copy provider-specific URLs, key prefixes, error strings, close codes, or vendor constants
  into Keel's runtime interfaces. Interface facts may be re-derived only where interoperability
  requires them, and must be rewritten in Keel's terms.
- Do not add a mandatory dependency on the remote compute provider, the model vendor, or the
  connector broker. Keel must remain usable and testable offline.
- Do not treat the reference's numeric limits (four screens, 20-minute idle, 600 calls/minute) as
  Keel constants; they are properties of a remote service, not design requirements.

## 6. Provenance

All statements above were derived by reading the local clones listed in section 1 on 2026-11-23.
Implementation claims cite files and symbols that were read directly; documentation claims cite the
repository's own docs. Third-party service facts are explicitly labeled "guide-reported" and were
**not** verified against any live account, API, or network call. No prompt text, code, generated
image, icon, logo, or other asset was transferred into Keel. Where behavior was ambiguous, the
document says so or omits the claim; nothing here asserts that the reference behaves in a way not
observed in the cited files. Keel feature IDs were read from the local `PLAN-INDEX.json`
(`git -C <worktree> rev-parse HEAD` = `b234ecd690060ff881b9c0bba8756148650f83eb`).

## 7. Concrete locally achievable improvements for Keel

All items are implementable and testable on a developer machine without network access, accounts,
or paid services.

| # | Improvement | Feature IDs | Local acceptance check |
| --- | --- | --- | --- |
| I1 | Add a pure screen-lease decision module: capacity, LRU eviction order, "never evict mid-turn", and profile retention as *data*, with unit tests over synthetic leases. | `Y2.12`, `A2.3`, `C9.4` | Table-driven tests for full-capacity eviction, stale lease, and primary-screen reservation; no UI or provider needed. |
| I2 | Add a pure idle suspend/wake decision (busy/wait/suspend) with injectable clock, viewer count, and activity, plus a dry-run flag. | `A2.4`, `Y1.32`, `A3.2` | Unit tests for viewer-open, turn-running, threshold boundary, and suspend failure backoff. |
| I3 | Enforce watch-only in Keel's own relay by parsing view frames and dropping input frame types; fail closed on unknown frames; add a recorded-session test with synthetic frames. | `Y2.14`, `C1.4`, `W7.19` | Test asserts synthetic input frames never reach the upstream sink and that unknown frame types are dropped. |
| I4 | Make approval answers first-class typed events with once/always/deny, plus last-used date and broadness scoring on standing rules. | `E1.5`, `W3.9`, `X5.7`, `V3`, `X5.3` | Permission-gate unit tests for each answer, a stale-rule report, and a broad-pattern warning. |
| I5 | Add an offline "agent instruction projection" test: given fixed session state, assert the bounded sections (memory, skills, roster) and that no provider-specific text is present. | `D6.17`, `B2.4`, `A1.22` | Snapshot test of the assembled instruction structure, with secrets and long memory truncated. |
| I6 | Add a real-flow E2E lane that runs against the local runtime only: seeded session, deterministic tool results, viewer card, summary JSON and failure screenshots. | `A2.8`, `E4.7`, `B5.6`, `Y2.23` | `node`/pytest command starts the local app, performs the flow, exits non-zero on failure, writes evidence to a temp folder. |
| I7 | Create Keel's own integration-runbook template with required sections: source of truth, verified vs inferred markers, env keys, test-fire, rotation, and open questions. | `C1.5`, `Y4.10`, `A4.6`, `Y3.20` | Lint check that every runbook has all required sections; no copied prose. |
| I8 | Add a "safe mode" UI toggle that masks secrets, emails, paths, and tokens while screen sharing or recording. | `C1.4`, `B3.6`, `D5.1` | Component tests for masked/unmasked states; no network. |
| I9 | Add an in-process/local executor path for desktop actions so core flows do not require a remote VM. | `C1.11`, `C4.10`, `D3.9` | Local smoke test drives the same tool interface against a temp workspace. |
| I10 | Publish a "proven vs built-but-unproven" status page generated from build-time evidence. | `A3.7`, `Y2.21`, `Y4.13` | Generated page matches recorded test/evidence metadata; fails build if evidence is stale. |
