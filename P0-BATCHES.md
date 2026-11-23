# Remaining P0 implementation batches

Generated from PLAN-INDEX.json: **196 not-started P0 features** in 35 source groups.

These are candidate workstreams for specialist agents. Do not mark any feature verified until real code, tests and runtime evidence exist.

## E1 — 14 features

- `E1.1` (M5) Every tool declares a mandatory canonical output (JSON schema), returns one lossless JSON value, and a pure render(args, value) produces the model-facing conten
- `E1.10` (M5) Concurrency classifier isConcurrencySafe(args): pure, only true opts in; anything else (omission, exception, invalid) is exclusive; loop forms exclusive barrier
- `E1.11` (M5) Executor contract: one outcome per input call in input order (skipped calls on abort included); never settles while started work still runs; internal failure dr
- `E1.12` (M7) Per-scope tool restriction (allow / deny lists) that intersect; scoped registrations stay exempt; deny-only admits later tools, allow-list excludes them.
- `E1.14` (M5) Stable error vocabulary: INVALID_ARGS, INVALID_TOOL_OUTPUT, UNKNOWN_TOOL, ABORTED, ABORTED_BEFORE_DISPATCH, TOOL_TIMEOUT, APPROVAL_REJECTED/CANCELLED/UNAVAILABL
- `E1.18` (M5) Long-running work: background start returns a typed handle ({kind:'background', job_id}); job spec has synchronous cancel, non-rejecting done that settles after
- `E1.2` (M5) Model-facing schema built by explicit allowlist (name, description, parameters only); execution, timeout, presenters, concurrency flags never leak into a reques
- `E1.3` (M5) One schema vocabulary for params and outputs (scalars, arrays, objects with explicit additionalProperties, exact-one oneOf, enum/const), with inferred types; mi
- `E1.4` (M5) Args are deep-frozen and snapshotted as lossless JSON before policy runs; args cannot be rewritten later because history, audit, UI and execution must agree.
- `E1.5` (M3) Pre-execute decisions: allow, deny (reason + optional structured error id), cancel, ask (audited reason + optional localized display reason); only allowed-once 
- `E1.6` (M3) Guards are monotonic: a final guard can only deny, never allow, so listener order cannot turn a denial into permission.
- `E1.7` (M3) Post-execute decisions: accept, replace *content* or replace *value* (never both), attach context for the next request, or block with corrective feedback. Conte
- `E1.8` (M5) Around-dispatch wrapper for timeout/retry/metrics may replace but not remove the cancellation signal; the registry re-fuses the caller's signal.
- `E1.9` (M5) Cooperative per-tool timeout (timeoutMs): declaring it asserts the tool forwards the cancel signal and reaches quiescence; never sent to the model; result error

## Y1 — 14 features

- `Y1.16` (M6) MCP permission naming
- `Y1.17` (M3) Ordered rule list permissions
- `Y1.19` (M2) Config precedence algorithm
- `Y1.2` (M5) Model-dependent tool exposure
- `Y1.20` (M2) {env:VAR} and {file:path} config substitution
- `Y1.24` (M4) Compaction config
- `Y1.3` (M5) patch multi-file format
- `Y1.30` (M10) Plugin enable/disable DSL
- `Y1.4` (M5) read limits and paging
- `Y1.5` (M5) glob/grep defaults
- `Y1.6` (M5) edit unique-match requirement and formatter hook
- `Y1.7` (M5) Shell tool details
- `Y1.8` (M5) webfetch and websearch provider selection
- `Y1.9` (M5) question tool

## W7 — 12 features

- `W7.1` (M1) Explicit trust boundary list (client untrusted, daemon holds secrets, agent environment powerful, third parties).
- `W7.10` (M3) SSRF safe fetch details: http(s) only, resolve then pin the checked address, re-check every redirect, cap time and size.
- `W7.13` (M20) Security headers for any served UI: CSP, `X-Frame-Options: DENY`, HSTS (when HTTPS), `nosniff`, strict referrer policy, COOP, permissions policy (microphone onl
- `W7.14` (M19) Rendering safety: Markdown rendered without raw HTML; link scheme allow-list; no `dangerouslySetInnerHTML`; inline-served HTML/SVG/XML get a sandboxing CSP; gen
- `W7.16` (M18) Publishing copies only from the site's own folder; never hidden files or symlink targets outside.
- `W7.17` (M15) Inbound channel rules: signature verified with constant-time compare, 300 s window, de-duplication, refuse when no secret configured; only approved senders can 
- `W7.19` (M26) Honest "known limitations" list: prompt injection can still misuse granted power; "watch only" enforced only in client in openman (orgo-teammates enforces on se
- `W7.3` (M3) Secrets sealed with AES-256-GCM, random 12-byte IV per value + auth tag; session cookie sealed with its own key and additional authenticated data, HttpOnly, Sam
- `W7.4` (M3) API keys: prefixed random token, stored only as SHA-256, shown once; per-key rate limit; per-user idempotency keys.
- `W7.5` (M3) Secrets reach child processes as a staged file read-and-deleted by the setup script, never on a command line.
- `W7.6` (M3) Log redaction plus keyed hash of user ids instead of ids.
- `W7.8` (M20) Sign-in/pairing attempts rate limited per client address and globally; use trusted-proxy hop count for address detection; only same-origin relative return paths

## D2 — 11 features

- `D2.1` (M8) Three event domains: *session events* (durable facts in the log, broadcast), *agent events* (`agent/*`, live, observe/intercept in-flight work), *capability eve
- `D2.10` (M4) Process-local live stream frames (`assistant-stream` start/chunk/end) vs durable settled message that embeds the compact timed stream; `assistant/attempt` retai
- `D2.11` (M4) Model-visible ⇔ logged: every model request must be reconstructable from the log; any new model-visible input requires a session event; plugins that alter messa
- `D2.13` (M4) Session format versioning with adjacent migrations: header-only `stat`/`list` pick the highest generation; read-open translates in memory; write-open publishes 
- `D2.15` (M4) Fork at a turn boundary (seeded session with inherited event count; only agent-loop-published sessions persist).
- `D2.16` (M5) Working directories supply user context and execution paths without changing project identity, sandbox write roots, or existing process dirs.
- `D2.3` (M7) Turn flow definition: step = one model request + the tools it calls; turn = zero or more steps; sequence `turn/start` → claim input → snapshot model selection →
- `D2.5` (M7) One inbox per agent driver; injected context (`agent.inject()`) waits for a waking message and lands in the next admitted request.
- `D2.7` (M4) System prompt travels as logged `system/message` history; empty text clears it.
- `D2.8` (M4) Cancellation during prompt preparation commits nothing (neither system nor user messages).
- `D2.9` (M4) Failed steps record missing tool results (synthetic).

## W3 — 11 features

- `W3.1` (M3) Rule = `{action, resource, effect}`; effects `allow/deny/ask`; no match means ask.
- `W3.10` (M3) Policies layer can hard-deny after rules and saved approvals; turns allow/ask into deny, never grants; global/managed policies override project config.
- `W3.12` (M20) Non-interactive clients must decide approval behavior; configured deny always enforced.
- `W3.13` (M3) Docs warning: shell has full host authority; prefer narrow allowlists over trying to recognize every dangerous command.
- `W3.2` (M3) Last matching rule wins (broad first, exceptions after); rules combine in order: lower-priority config, global, then agent.
- `W3.3` (M3) Wildcards: `*` matches any characters including `/`; `?` one character; whole-value match; backslashes normalized; case-insensitive on Windows; shell pattern en
- `W3.4` (M3) Multi-resource operations: any `deny` denies; else any `ask` asks; else allow (e.g., a patch touching several files).
- `W3.6` (M3) `external_directory` action: paths outside the project/worktree are checked before read/edit rules. opencode's default is allow.
- `W3.7` (M3) Shell scanner for Bash, Zsh, POSIX sh and PowerShell: each extracted subcommand and `cd` target is checked; malformed or dynamically evaluated commands return a
- `W3.8` (M3) Base default policy: allow all, but ask on `.env` / `.env.*` reads except `.env.example`.
- `W3.9` (M3) Approval replies: `once`, `always` (saves tool-proposed patterns, project-scoped, never overrides a configured deny), `reject` (rejects every other pending requ

## D3 — 10 features

- `D3.1` (M0) Capability seam = Service Definition + Service Provider + Consumer; one role alone is not a seam; adding a capability means designing all three.
- `D3.11` (M7) Packages Keel is missing or underspecified (from the 60+ dsh package groups): `deliverables` (turn deliverables), `spill` (output spill), `attachment`, `guard` 
- `D3.13` (M5) `spill`: large tool output spills to a file with a preview (matches Master rule 5).
- `D3.14` (M4) `guard`: loop and tool guards as their own plugin group.
- `D3.18` (M4) `workspace` entities + `session-query` (browse/search/export).
- `D3.2` (M5) One provider swap changes the whole product: filesystem and subprocess providers share one execution world, so pointing them at a remote sandbox moves bash, PTY
- `D3.6` (M7) Human commands registered on a commands service dispatch without a model turn.
- `D3.7` (M5) Background jobs service with `job_*` tools to read/stop jobs.
- `D3.8` (M15) Webhook runtime: a *trusted rule* starts a session from an external webhook; provider adapters mount beside it.
- `D3.9` (M5) Shell backend, terminals backend, sandbox backend as separate services; sandbox wraps argv before spawning.

## Y2 — 10 features

- `Y2.1` (M4) Transcript row model
- `Y2.14` (M16) VNC relay that hides credentials from the browser
- `Y2.2` (M4) Model history stored separately
- `Y2.20` (M3) Exposure defaults
- `Y2.3` (M4) last N screenshots inline (N=3)
- `Y2.4` (M4) Orphaned tool-call repair
- `Y2.5` (M4) Per-agent serial queue
- `Y2.6` (M3) Pending-turn persistence
- `Y2.7` (M3) approval buttons: Allow / Always allow / Don't allow
- `Y2.8` (M15) Auto-classification of read-only tools by slug

## W2 — 8 features

- `W2.1` (M7) Markdown agent files with YAML frontmatter; nested path becomes agent ID (`team/reviewer`); global + project locations; same fields as config entries; body is t
- `W2.11` (M7) Plan agent may write only plan files in a dedicated plan folder; shell stays permission-controlled.
- `W2.2` (M7) Modes `primary` / `subagent` / `all`; subagents run in child sessions with fresh context.
- `W2.3` (M7) Built-ins: build, plan, general (no further subagents), explore (read-only incl. web); hidden maintenance agents (`compaction`, `title`, `summary`) that are not
- `W2.4` (M7) `steps` limit: max model steps per turn; on the final step tools are removed and the model must summarize in text; new user input resets.
- `W2.6` (M12) Subagent launch permissions: parent's `subagent` rules control which agents it may launch (e.g., deny `*`, allow `reviewer`); child uses its own permissions, no
- `W2.8` (M7) `system` replaces the provider base prompt for that agent, but project instructions, skills, references still get added.
- `W2.9` (M2) Agent merge semantics: later scalars replace, maps merge by key, permission rules append; global rules apply before agent rules.

## X0 — 8 features

- `X0.1` (M0) Priority inflation
- `X0.10` (M0) Plan says "reimplement from behavior" but gives no clean-room procedure
- `X0.2` (M19) M19 (desktop UI) is overloaded
- `X0.3` (M0) No dependency graph
- `X0.4` (M12) Duet defined three ways
- `X0.6` (M0) Free-tier trap list is incomplete
- `X0.7` (M2) Voice/ML licensing is stated as "check"
- `X0.8` (M25) "Zero network without account" is asserted but there is no test list

## X1 — 8 features

- `X1.1` (M2) Tool-call dialect adapters
- `X1.13` (M4) Steering and interrupt
- `X1.2` (M2) Chat-template handling
- `X1.3` (M2) Reasoning-model output handling
- `X1.4` (M5) Selectable edit formats per model
- `X1.5` (M5) Fuzzy patch application
- `X1.7` (M11) Repo map ranking
- `X1.8` (M2) Accurate token counting

## E4 — 7 features

- `E4.1` (M10) HMR-safety test for every registry: dispose the contributing scope, assert cleanup.
- `E4.10` (M25) Mock only the expensive/non-deterministic boundary (model, network, clock); keep the real tool registry, pipeline and persistence behind the scripted mock; reco
- `E4.12` (M10) Real-composition tests for product-visible plugins: boot a test-only config through the real loader, mock only external services, assert model-visible request/l
- `E4.15` (M0) Every non-trivial model/protocol/human-visible change updates a keyless recorded-session scenario; new capability seams and lifecycle variants name every requir
- `E4.2` (M25) Permanent contract-regression specs for the agent loop.
- `E4.5` (M25) Snapshot scenarios: parent/child session files with version in filename that must agree with header; snapshot.yml declares profile, header class, recording poli
- `E4.8` (M25) Test-process isolation rules: forked workers share ports, paths, namespaces and children; each test owns every resource it acquires through teardown; a spec tha

## E7 — 7 features

- `E7.18` (M3) sandboxPolicy: the single home for default sandbox mode and workspace root so bash and fs can't confine to different roots; consumers hand over the exact argv; 
- `E7.19` (M3) approval seam fails closed: absence of an answerer yields unavailable.
- `E7.2` (M4) toolResultPruner: model-free pruning of oversized *current* tool results through replayable surface replacements before summary compaction.
- `E7.20` (M3) permissionPresets: user-facing presets bundling sandbox mode + approval policy; switching writes one logged permission/preset event that updates both knobs.
- `E7.21` (M5) fs-observation-policy: observed-state checks (read-before-edit, stale-file detection) contributed through the fs/* event gate.
- `E7.23` (M5) web seam: search and fetch providers register into one service; tool names stay stable.
- `E7.6` (M5) workspaceFiles: stat, paged text, byte windows, directory listings and a change feed confined by lstat, containment and a stat re-check.

## V — 7 features

- `V1` (M10) Plugin scope tree (lifecycle-safe plugins): every plugin runs in a scope that records what it registered (tools, hooks, routes, UI panels, timers, subprocesses)
- `V16` (M0) Keel invariant-gate catalog: a list of gates specific to Keel: Tier-2 table hash unchanged; no outbound network in offline suite; no secret in logs; every tool 
- `V2` (M3) Policy simulator with "winning rule" trace: shows ordered rules, which matched, which won, why a multi-resource op was denied, and the Tier-2 verdict.
- `V24` (M5) Tool conformance kit: one automated suite every tool must pass: output schema declared, presenter pure on replay, cancel honored within N ms, no leaked fields i
- `V26` (M4) Request-reconstruction test: replay a session log and rebuild the exact provider request; byte-compare with what was actually sent (hash) to prove "model-visibl
- `V31` (M19) Local-socket transport spike: prove Electron ↔ Python over named pipe/UDS with streaming and backpressure on all three OSes before committing (C-19); keep TCP+t
- `V5` (M3) Strictness presets as rule sets: Cautious / Balanced / Trusted compiled into ordered rule arrays, diffable and exportable, never able to touch Tier 2.

## Y3 — 7 features

- `Y3.10` (M3) Local-only sign-in
- `Y3.11` (M2) Mock agent
- `Y3.13` (M3) setup script: generate-only, never overwrite
- `Y3.2` (M4) 'reuse before building' / 'server is only DB client'
- `Y3.4` (M4) Relay stores every run event
- `Y3.6` (M4) table ideas / schema additions
- `Y3.9` (M3) Sign out / Sign out everywhere / Disconnect

## E5 — 6 features

- `E5.1` (M19) No listening port in the desktop app: the backend runs as a bundled child; framed byte pipes carry requests and streaming responses with backpressure, Node IPC 
- `E5.12` (M22) Per-target build isolation: each target owns its inputs, prepared runtime, seed and artifacts under targets/<target>/; shared download cache verified by name+ha
- `E5.14` (M22) Packaging never receives upload credentials (stripped from subprocesses); a target completion record is written only after every build/sign step succeeds.
- `E5.15` (M22) Upload guard: uploader requires the completion record to match environment, target, public URL and version, and checks artifact names, sizes, SHA-512 before it 
- `E5.4` (M19) Process-lifetime single-instance lock acquired before any profile access; the desktop app exclusively owns its profile directory; CLI and desktop share product 
- `E5.9` (M10) Plugins with install-time lifecycle scripts are rejected unless in a reviewed allowlist.

## D1 — 5 features

- `D1.1` (M10) Every part is a plugin, including model adapter, tool registry, session log and the agent loop itself, each replaceable from configuration; "no privileged core 
- `D1.10` (M19) Desktop shell: Electron ships the exact production runtime in signed resources, owns a reserved `desktop` profile, starts a private Desktop Host (Electron-as-No
- `D1.12` (M7) Core package map (session log, system-prompt assembly, tool registry + guarded pipeline, agent interface + live registry, agent loop driver, per-agent scope pri
- `D1.4` (M2) Layered composition order: bundles in order, then profile patch, then home patch, then `--patch` overlays; a patch targets a row by id (replace whole config) or
- `D1.5` (M2) `--dump-config`: prints the exact plugin tree the machine will boot; any printed row can be replaced by a patch.

## D5 — 5 features

- `D5.1` (M19) Plain statement that the software executes model-generated code/commands, loads third-party plugins, and accesses network, processes, credentials and files; def
- `D5.2` (M19) "Sandboxing, approvals and permissions reduce risk but do not guarantee isolation"; do not rely on it as the sole control for untrusted workloads.
- `D5.3` (M19) Responsible-use list: least privilege; disposable VM/container; keep backups; don't expose sensitive credentials; review plugins, config and proposed commands.
- `D5.4` (M1) No warranty / no liability paragraph referencing the license.
- `D5.5` (M0) Host sandbox failures rule (builder): if a required command fails because the dev sandbox blocks credentials/network/IPC, retry unchanged with the narrowest esc

## E6 — 5 features

- `E6.1` (M3) Keys are write-only: the UI receives a redacted descriptor, never the secret; settings store only a credential reference; masked preview rule (identifier prefix
- `E6.10` (M2) Request-compatibility switches (supports_developer_role, max_tokens_field, thinking_format, ...) at route level with per-model field-by-field override; empty va
- `E6.5` (M2) Third-party provider picker from an installed catalog (endpoint, protocol, models) vs Custom model API form: permanent lowercase provider ID, base URL, protocol
- `E6.8` (M2) Per-model capability fields: input types (text, image), context window, max output tokens; route-level defaultInput fallback (never removes images the catalog k
- `E6.9` (M2) Reasoning-effort declarations per model: levels with the API value sent for each (off may be empty = send nothing), route default, picker choice saved with mode

## D7 — 4 features

- `D7.1` (M0) Gate scheduler (`run-gates`): all gates as a dependency graph; bounded concurrency env var; fail-fast switch; a failure skips only its dependents so independent
- `D7.12` (M0) CI layout: broad lanes of independent gates, a smaller Node-version compatibility matrix, native Windows lane in a separate workflow, Python checks separate, re
- `D7.19` (M21) Benchmark method: drive tasks through the SDK's minimal JSON-RPC agent variant with separate workspaces and session ids per independent task.
- `D7.9` (M0) Strict dependency linker so undeclared deps fail; build scripts of dependencies explicitly allowlisted.

## W5 — 4 features

- `W5.1` (M7) Markdown or JSON commands; nested folders become `/team/review`; global vs project; project overrides global; nearer overrides ancestor; custom may replace buil
- `W5.2` (M7) Frontmatter: `description`, `agent`, `model`, `subagent` (true/false/omit rules); legacy alias `subtask`.
- `W5.3` (M7) Arguments: `$ARGUMENTS`, positional `$1..$n` with quote grouping (last placeholder takes the rest, missing = empty); fallback appends args when no placeholder.
- `W5.4` (M7) Shell injection `!` + backtick command: output inserted into the prompt; opencode notes it runs outside the agent permission flow.

## X9 — 4 features

- `X9.1` (M2) Fixture model server
- `X9.3` (M2) Provider contract tests: each adapter must pass the same behavior suite (streaming, cancel, tool call, usage, errors)
- `X9.5` (M3) Cross-platform path/permission matrix tests (Windows reserved names, ADS, long paths, case-insensitive FS, symlinks/junctions)
- `X9.7` (M4) Migration matrix: every released schema version upgraded to current, with data checksums

## D4 — 3 features

- `D4.11` (M10) Plugin Manager UI in the base bundle for Web and agents.
- `D4.2` (M2) Custom OpenAI-compatible endpoints documented as a first-class path.
- `D4.7` (M5) Tool UI presentation designed up front: host presenters are pure; web cards derive from raw events and persisted result metadata.

## X10 — 3 features

- `X10.1` (M0) Definition-of-done template
- `X10.2` (M0) Provenance file
- `X10.4` (M0) Builder "stop list": actions that always pause for the owner, mirrored from gates G1 to G7 plus destructive repo actions, as a machine-readable file the builder

## X5 — 3 features

- `X5.1` (M3) Sensitive-project mode
- `X5.5` (M3) Mass-change guard
- `X5.6` (M5) Filesystem change journal per task so every touched path can be reviewed and reverted as a set

## Y4 — 3 features

- `Y4.13` (M22) version badge and zero-secrets release scan
- `Y4.3` (M19) first-boot sign-in test-fire
- `Y4.9` (M7) Persona file with rigor contract + coding-agent routing + desktop control plane

## Y6 — 3 features

- `Y6.1` (M0) repo evidence docs cross-walk
- `Y6.2` (M0) .verify-* and .build artifacts
- `Y6.4` (M1) repo visibility: Public, 0 stars/forks

## E2 — 2 features

- `E2.1` (M5) Presenters are pure (present_call(args), present_result(args, result)), run on live stream and log replay, no I/O/clock/session state; malformed or old args fal
- `E2.3` (M4) Durable presentation metadata (presentation_meta(args, value)) stored on the result so replay shows hunks/search facts without persisting the canonical value; s

## E3 — 2 features

- `E3.3` (M12) Agent names: 1 to 32 lowercase letters/digits/hyphens starting with a letter, not lead; default agent-N; root is lead; full names are slash paths; names are mod
- `E3.8` (M12) Result object: final output = last non-empty assistant message; optional structured value validated against the requested schema; diagnostic text limited to 4,0

## W1 — 2 features

- `W1.10` (M19) `SAFETY.md` surfaced as a first-run notice ("review the safety notice before running").
- `W1.18` (M0) MIT license + `THIRD_PARTY_NOTICES.md`.

## W6 — 2 features

- `W6.1` (M7) Accuracy-over-approval response contract: verify facts/figures/citations before finalizing; never fabricate; say unknown plainly; do not anchor on user-supplied
- `W6.3` (M7) Anti-sycophancy rules: no praise of questions, say immediately if the user is wrong, strongest counterargument first, do not capitulate under pushback without n

## X8 — 2 features

- `X8.1` (M19) Local component catalog
- `X8.2` (M19) Design-token contract file (`tokens.json`) as the only source of color, type, spacing, radius, motion; lint rule rejects hard-coded values

## W4 — 1 features

- `W4.3` (M6) OAuth for remote servers: PKCE, discovery, refresh; credentials stored outside project config; `oauth:false` for header-key servers.

## X6 — 1 features

- `X6.7` (M2) Config validation with "did you mean" suggestions, line/column errors for JSONC, and `keel config explain <key>`

## Y5 — 1 features

- `Y5.4` (M3) webhook signature headers and no-secret rejection

## Z — 1 features

- `Z4` (M4) Crash-safe turn journal
