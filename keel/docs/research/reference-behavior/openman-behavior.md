# OpenMan — clean-room behavior specification

This document records **observable behavior** of a reference repository in Keel's own vocabulary.
It is research input for the Keel plan, not a porting guide. No source code, prompt text, branding,
icons, logos, or other proprietary assets are reproduced here.

## 1. Source metadata

| Field | Value |
| --- | --- |
| Repository URL | `https://github.com/nickvasilescu/openman.git` |
| Local clone | `C:\Users\Admin\Desktop\Claude clone\research\references\openman` |
| Clone HEAD | `git -C "…\openman" rev-parse HEAD` → `12ea5bddfedc95328eb9b8b6e3ad4ea357e76278` |
| HEAD commit | `2026-11-19T13:34:48-08:00` — "Finish Orgo sign-in (device approval, API key, workspace and computer picker), production guard for dev bypass, SPDX headers, README quick-start fixes" |
| Research date | 2026-11-23 |
| Repository posture | MIT project code; README labels the software "early". Security policy reports best-effort service levels and supports only the latest commit/release. |

Files read (implementation first, documentation second):

- `AGENTS.md`, `SECURITY.md`, `README.md`, `.env.example` (inventory), `src/config/usage-limits.ts`
- `src/proxy.ts`, `src/lib/session/{gate,bypass,startup,identify,csrf,cookie,signin-limit}.ts`
- `src/lib/db/client.ts`, `src/lib/orgo/secret-file.ts`, `src/lib/net/safe-fetch.ts` (lines 1–140),
  `src/lib/limits/workspace.ts`, `src/lib/usage/index.ts`
- `src/lib/agent/server/{computer-view,connection,agent-tools-mcp}.ts`,
  `src/app/api/computers/[id]/view/route.ts`
- `supabase/migrations/20261120000000_baseline.sql` (RLS gate, rate/usage functions, grant loop)
- `scripts/auth-hardening-test.mjs`, `scripts/workspace-test.mjs` (headers and first sections)
- `docs/{ARCHITECTURE,deploy,OPERATIONS,security-model}.md`
- `content/docs/{getting-started,tasks,cloud-computers,projects,sharing,modes-and-models,security}.md`,
  `content/docs/api/{authentication,rate-limits}.md`

## 2. Observed behavior, stated in Keel terminology

B1. **Deployment is three pieces, not one.** A Node/Next web process, a server-only database with
    applied migrations and a registered server secret, and a separate always-on scheduler worker
    that calls a cron endpoint once a minute. Minimum host footprint is small because all agent
    compute lives in each user's own remote computer. Releases are immutable directories behind a
    switchable link; migrations are additive and are never rolled back with code. Serverless hosting
    is explicitly untested because long-lived streams and a local file cache need a persistent
    process. (`docs/deploy.md`, `docs/OPERATIONS.md`.)

B2. **Fail-closed startup guards.** The process inspects its environment at startup and exits with
    a reason if an authentication bypass is set in production. A development identity is allowed
    only under the development server; local sign-in with the host's key needs a loopback bind, a
    loopback public URL, and a per-request loopback check (Host, forwarded host, every forwarded-for
    entry). The guards are pure functions over an env object so they can be tested without booting
    the app. (`src/lib/session/bypass.ts`, `startup.ts`, `src/instrumentation.ts` inventory.)

B3. **Authentication is delegated to the compute provider, with two entry paths.** A device-style
    approval flow binds the pending attempt to the starting browser with a sealed cookie and never
    exposes the underlying device code; a pasted provider key is verified with the provider itself.
    An account-scoped key identifies the person directly; a workspace-scoped key is accepted only
    when that workspace has exactly one member, its owner, otherwise it is refused. Sign-in starts
    are budgeted per client address and globally in database counters, with reusable pending
    attempts so repeated clicks are free. Only relative same-origin return paths are honoured.
    (`src/lib/session/identify.ts`, `signin-limit.ts`, `README.md` "Sign in with Orgo".)

B4. **Session and revocation model.** The session cookie is a sealed JSON value using a dedicated
    key and additional authenticated data, HTTP-only, SameSite=Lax, Secure in production, 30 days;
    it never carries the provider credential. A separate revocations table backs "sign out
    everywhere", account deletion, and an automation token, and survives account deletion. Public
    API keys are prefixed random tokens stored only as hashes and shown once, with a fixed-window
    per-key rate limit and per-user idempotency keys. (`src/lib/session/cookie.ts`,
    `content/docs/api/authentication.md`, `rate-limits.md`, `docs/security-model.md`.)

B5. **Database gate is the tenant boundary.** Only the server constructs the database client; it
    uses a publishable key plus a secret header. Row-level security admits the anonymous role only
    when a security-definer function hashes that header and compares it to a single stored hash;
    every table gets one "server only" policy, the authenticated role gets no grants, and RPC helpers
    run as invoker so the same gate applies. Every repository query is scoped by the signed-in user
    id. New tables must be added to export and deletion code as well.
    (`src/lib/db/client.ts`, migration lines 19–47 and 961–989, `AGENTS.md` rules.)

B6. **Secrets never travel in command text.** Per-user credentials (provider key, agent key,
    connector headers, webhook secrets) are sealed with AES-256-GCM using a fresh IV and auth tag.
    Values destined for a user's computer are uploaded as a staged file through a two-step transfer;
    the setup script reads and immediately deletes it. The generated Python snippet validates the
    staged path with a strict regex before emitting it. Logs pass a redaction step and store keyed
    hashes of user ids. (`src/lib/orgo/secret-file.ts`, `docs/security-model.md`, `AGENTS.md`.)

B7. **Request-hardening seams.** One request gate handles sign-in routing, invite gating, share-link
    validation, and CSRF: a state-changing cookie-authenticated API request must originate from this
    site (Origin, with Sec-Fetch-Site fallback); bearer routes, webhooks, and the scheduler are
    exempt. Every server-side fetch of a user- or agent-supplied URL goes through one safe-fetch
    implementation that allows only http(s), resolves and checks every address against a public-IP
    allowlist, pins the checked address, re-checks each redirect, drops credentials cross-origin,
    and caps time and size. Rendered Markdown excludes raw HTML, links use a scheme allowlist, and
    inline-served scriptable file types and generated-site previews get sandboxing.
    (`src/proxy.ts`, `src/lib/session/csrf.ts`, `src/lib/net/safe-fetch.ts`, `docs/security-model.md`.)

B8. **Inbound channel rules.** Vendor callbacks are verified with signatures (one HMAC-based, one
    third-party signature scheme), constant-time comparison, a 300-second window, de-duplication,
    and refusal when no secret is configured. Only approved senders can start work by email or SMS;
    a phone call never starts a task by itself without an SMS code to the caller. Email triggers
    accept only clean mail and by default only from the owner's address. (`docs/security-model.md`.)

B9. **Usage limits are atomic and pre-flight.** Eleven operator-paid metrics (phone numbers, SMS,
    call turns, inboxes, emails, transcription sessions/seconds/jobs/MB, speech characters, sound
    effects, site invitations) have per-user day and month caps in code, overridable by an env JSON
    object. A database function locks both counters and returns success only if both stay within
    limits; the caller spends *before* invoking the vendor and fails closed with a 429 when caps
    cannot be checked. Model/compute spend is deliberately excluded because it is billed to the
    user's own account. (`src/config/usage-limits.ts`, `src/lib/usage/index.ts`, migration lines
    815–850.)

B10. **Agent runtime is a per-user remote service seam.** Each user has a home computer with an
    agent server; provisioning is idempotent, versioned, and resumable, re-running only changed
    steps on the user's next visit. The relay talks to that server for runs, event streams, stop,
    steer, approvals, and questions, and stores every event so the browser can reconnect and replay.
    Modes map to provider models billed through the compute provider's proxy.
    (`docs/ARCHITECTURE.md` "Compute and the agent", `src/lib/agent/server/connection.ts`.)

B11. **Agent instructions exist at two levels.** Repository-level instructions for *builders*
    are a checked-in guide: read local framework docs before editing, no route-segment config,
    server-only data, secrets and quoting rules, the exact new-table migration pattern, branding from
    a central config, "offer only what works", and redacted structured logging. Runtime-level
    instructions are installed on the user's computer as a small standard-library MCP tool server
    plus a restricted profile: tools carry a task handle that is regex-validated, calls are written
    as files in a 0700 directory and answered by the relay using data scoped to that owner and task,
    and the tool list includes creation of parallel tasks, automations, speech, and project-update
    proposals (the last requiring user approval). Project instructions, connectors, and skills are
    injected into tasks at the application layer. (`AGENTS.md`, `src/lib/agent/server/agent-tools-mcp.ts`,
    `content/docs/projects.md`.)

B12. **Application screens and interaction contract.** Home composer with files, computer picker,
    mode, and dictation; task view with conversation, plan, tool steps, produced files, and a live
    computer panel that starts view-only with "take controls"/"give back control"; mid-run messaging
    with three delivery choices plus stop; approvals and per-app desktop permissions with a settings
    page for standing choices; computers list/detail with watch, terminal, SSH keys, resize, restart,
    backups; projects with shared instructions/files; library; settings tabs including sign-in
    security, data controls, usage/billing, developers; operator page; public share and step replay
    pages that mask secret-looking text and never show the live screen.
    (`content/docs/getting-started.md`, `tasks.md`, `cloud-computers.md`, `projects.md`, `sharing.md`,
    `modes-and-models.md`, `docs/OPERATIONS.md`.)

B13. **Workspace behavior and resource hygiene.** The home computer is created on first sign-in and
    is the default run target; extra computers come from the user's own listing. A named computer in
    a request is checked against that listing, and the home computer cannot be resized, restarted,
    renamed, or deleted through the app. Each task gets its own working folder on the computer;
    folders idle for a configurable number of days are swept by the scheduler, with delivered files
    cached to the server first, a per-pass task cap, and a file-size cap that skips rather than
    loses data. Task concurrency is limited by computer size, with overflow queued.
    (`content/docs/cloud-computers.md`, `src/lib/limits/workspace.ts`,
    `src/lib/agent/server/connection.ts`, `docs/ARCHITECTURE.md`.)

B14. **Live desktop credential handling is deliberately weaker than a relay.** The server fetches a
    per-session desktop password and gives the owner a websocket URL carrying it with no-store
    caching; nothing about the desktop is stored in the browser. The view-only flag is a client-side
    property, and the security model explicitly lists this as a known limitation. The env-provided
    stream (which carries a root-equivalent password) is restricted to the development/local owner.
    (`src/lib/agent/server/computer-view.ts`, `src/app/api/computers/[id]/view/route.ts`,
    `docs/security-model.md`.)

B15. **Operations are observable and scripted.** A liveness endpoint needs no auth or database; a
    deep readiness endpoint needs the cron secret and reports database/gate health, tick age,
    webhook backlog, failing automations, stuck provisioning, sign-in budget, error counts, and
    settings presence. Failures return a generic message plus a request id, with details in logs and
    an operator event table retained 30 days. Alerts fire at most once per kind per hour. The
    operator guide covers pre-deploy checks, additive migrations, secret rotation consequences,
    database restore, forced re-provisioning, stuck-queue draining, credential-leak response, and
    graduated service pause. (`docs/OPERATIONS.md`, `docs/deploy.md`.)

B16. **Honest limitations are documented.** The security model states that the agent is powerful by
    design, prompt injection within one user's account is a known limitation, view-only is
    client-enforced, many users share one sign-in budget, and a self-hosted deployment is only as
    safe as its operator's setup. The security policy scopes out same-account agent behavior and
    third-party service flaws. (`docs/security-model.md` "Known limitations", `SECURITY.md`.)

## 3. Security and permission implications

S1. **The server is the only trust anchor.** Browser untrusted, database behind a server-only gate,
    per-user computer powerful by design. This is the same boundary Keel calls "client untrusted,
    daemon holds secrets, agent environment powerful" (`W7.1`); Keel must keep it even when its
    runtime is local.

S2. **Database security does not rely on the client.** RLS plus a hashed server header means a
    stolen publishable key yields nothing. Keel's equivalent is a local, permission-gated store that
    never accepts a raw client-supplied identity as authority.

S3. **Credential staging beats command interpolation.** Passing secrets through a staged file that
    is read-and-deleted prevents them appearing in command echoes and logs. This is a concrete
    pattern Keel should adopt for any child-process setup.

S4. **Pre-spend caps are economic safety.** Atomic database counters checked *before* a vendor call
    prevent one user from exhausting operator-paid integrations. Keel needs the same pattern for any
    metered local resource or remote provider it does enable, with fail-closed behavior.

S5. **Client-side view-only is not a permission.** If a viewer receives a root-equivalent desktop
    credential, "watch only" can be bypassed. Keel should prefer the relay-side filter pattern
    described in the Orgo reference and document the gap if it cannot.

S6. **Startup guards prevent "temporarily disable auth" from reaching production.** A process that
    refuses to start with unsafe settings is a stronger control than a warning. Keel's local-first
    defaults must make this explicit for any dev bypass.

S7. **Provisioning is code execution on a remote machine.** Versioned, idempotent steps and
    re-running only changed steps limit blast radius; the operator must be able to reset a stuck
    user without touching everyone.

S8. **Scope and honesty are part of security.** Declaring what is out of scope (same-account agent
    actions, third-party services, misconfiguration) prevents false assurance and tells reviewers
    where to look. Keel's known-limitations list should be equally specific.

## 4. Keel applicability (feature IDs from `PLAN-INDEX.json`)

| Observed behavior | Keel feature IDs | Applicability |
| --- | --- | --- |
| B1 three-part deployment, additive migrations, rollback by link | `A3.11`, `C13.4`, `E5.12`, `X10.1` | Keel's headless deployment docs and release rehearsals; keep local-first, no cloud requirement. |
| B2 fail-closed startup guards | `Y3.13`, `E5.13`, `W7.19`, `C12.6` | Add env validation that stops the process on unsafe local overrides. |
| B3 delegated sign-in, browser-bound attempts, budgets | `W7.7`, `W7.8`, `W8.1`, `Y4.2`, `Y3.9` | Direct analogues for Keel pairing, allow-lists, and sign-out semantics. |
| B4 sealed cookie + revocations + hashed API keys | `W7.3`, `W7.4`, `Y3.9`, `E6.1` | Keel's key descriptor and revocation design; store references, never secrets. |
| B5 server-only DB + RLS gate | `W7.1`, `D2.14`, `E7.41`, `D3.18` | Keel's storage seam and workspace entities; authority stays in the daemon. |
| B6 sealed secrets + staged file to child | `W7.3`, `W7.5`, `B3.6`, `E6.1`, `A4.8` | Adopt the staged-file pattern for Keel child-process setup and redaction. |
| B7 CSRF, safe fetch, rendering safety, headers | `W7.13`, `W7.14`, `W3.13`, `E7.43` | Keel's served UI and browser seam need the same checks locally. |
| B8 inbound signature rules | `W7.17`, `Y5.4`, `D3.8` | Direct match for Keel webhook/channel rules. |
| B9 atomic per-user usage caps | `Z16`, `C9.4`, `A4.6`, `X5.3` | Keel cost budgets and resource meters; caps must be checked before spend. |
| B10 per-user remote agent seam + versioned provisioning | `D3.1`, `D3.9`, `C4.10`, `E7.16`, `A3.5` | Capability seam with replaceable provider; Keel's setup script is generate-only. |
| B11 builder guide + runtime tool contract | `A1.22`, `C1.3`, `W1.2`, `Y4.10`, `V11`, `V18` | Keel's builder instructions and tool-surface report; static capability scan for bundled tools. |
| B12 application screens and approvals | `D4.3`, `E2.2`, `E7.5`, `W8.3`, `X8.17`, `C2.5` | Reuse the flow contracts (composer, live panel, approvals, settings), not the visuals. |
| B13 workspace hygiene, home-computer protection | `A3.2`, `D2.16`, `W8.3`, `D3.18`, `E7.15` | Direct match for folder GC, scope rules, and "protect the primary workspace resource". |
| B14 client-side view-only gap | `Y2.14`, `W7.19`, `C1.4` | Explicitly record the difference; Keel should implement relay-enforced watch mode. |
| B15 deep health, request ids, operator runbook | `A3.11`, `X10.4`, `B3.12`, `E7.20`, `Y3.20` | Keel's ops docs, audit bundle, and permission-change events. |
| B16 documented limitations | `D5.1`, `D5.2`, `D5.3`, `W7.19`, `A3.7` | Direct input to Keel's honest status and safety-notice pages. |

## 5. Do NOT copy

- Do not copy any source file, route handler, SQL migration text, UI component, CSS token, or script.
  Behavior only.
- Do not copy product names, logos, wordmarks, brand icons, third-party brand SVGs, marketing copy,
  or screen layouts into Keel.
- Do not copy the checked-in builder instructions or any runtime prompt/tool description text. Keel
  writes its own `AGENTS.md` and tool contracts in Keel terminology.
- Do not copy provider-specific URLs, header names, key prefixes, env variable names, error codes, or
  numeric limits into Keel interfaces. Where a Keel feature has the same *function*, give it a Keel
  name and a local implementation.
- Do not copy the Supabase-specific RLS policy string or database schema. Keel's storage seam must be
  its own, with its own tests.
- Do not introduce a mandatory account, hosted database, or paid vendor into Keel's local-first path.
- Do not copy the reference's screenshots, illustrations, avatar art, or generated media.

## 6. Provenance

All statements above were derived from the local clone listed in section 1 on 2026-11-23. Implementation
claims cite files and symbols that were read directly; documentation claims cite files in the clone.
No network calls, live accounts, or provider APIs were used. Where the repository itself labels a
statement a limitation or a known gap, this document preserves that qualification rather than
asserting stronger behavior. No code, prompt, image, logo, or other asset was transferred into Keel.
Keel feature IDs were read from the local `PLAN-INDEX.json` in worktree
`b234ecd690060ff881b9c0bba8756148650f83eb`.

## 7. Concrete locally achievable improvements for Keel

All items are implementable and testable on a developer machine with no network, accounts, or paid
services.

| # | Improvement | Feature IDs | Local acceptance check |
| --- | --- | --- | --- |
| I1 | Add a pure startup-settings validator that blocks unsafe local bypass flags outside development mode, with warnings for deprecated names. | `Y3.13`, `E5.13`, `W7.19` | Unit tests for production + bypass (exit), development + bypass (allow), deprecated name (warning). |
| I2 | Add a staged-file secret helper for child processes: write to a 0700 temp dir, pass only the path, emit a read-and-delete snippet, validate the path strictly. | `W7.5`, `W7.3`, `B3.6` | Test asserts no secret bytes in argv or logs, file removed after read, bad path rejected. |
| I3 | Add atomic pre-flight resource budgets with day/month windows, environment overrides, and fail-closed behavior when the counter is unavailable. | `Z16`, `C9.4`, `A4.6` | Test with a fake counter: cap boundary, 429-equivalent typed refusal, counter outage. |
| I4 | Add a pure request-gate suite: CSRF decisions, same-origin return paths, invite/allow-list decisions, and cookie decode/revocation. | `W7.7`, `W7.8`, `W7.13`, `W8.1` | Table-driven tests including forwarded-host proxy case and cross-site POST without Origin. |
| I5 | Add an offline safe-fetch regression suite using a local resolver stub: private/metadata/IPv6 forms, redirect re-check, DNS-rebinding simulation, size/time caps. | `W7.1`, `W7.14` | Tests use no real network; every blocked address family has a case. |
| I6 | Add a versioned, idempotent local setup procedure that records completed steps in a local state file and re-runs only changed steps. | `A3.5`, `Y3.13`, `A4.6` | Run twice; second run performs no work; bump a step version and see only that step re-run. |
| I7 | Add a "home resource" protection rule: a designated primary workspace/computer cannot be deleted or resized through API calls, with ownership checked against a local inventory. | `W8.3`, `D4.3`, `E7.18` | Unit tests for named resource not in inventory, primary resource, and normal resource. |
| I8 | Add an operator-style deep health command that reports local store health, scheduler tick age, pending jobs, and settings presence with a typed status and request id. | `A3.11`, `B3.12`, `Y3.20` | CLI command returns 0/1 deterministically against a temp data dir. |
| I9 | Add a documented known-limitations section generated alongside the status page, including prompt injection, client-only view-only, and shared budgets. | `W7.19`, `D5.2`, `A3.7`, `Y2.21` | Build check fails if the section is missing or stale relative to evidence. |
| I10 | Add a tool-surface report for Keel agents: list reachable tools, seams, and approval requirements after resolution, with a permission-diff on config change. | `V11`, `C8.5`, `E7.20`, `A1.12` | Report command compares two configs and prints added/removed capabilities and logged preset changes. |
