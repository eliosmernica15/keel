# Remaining P0 implementation batches

Generated from PLAN-INDEX.json: **98 not-started P0 features** in 25 source groups.

These are candidate workstreams for specialist agents. Do not mark any feature verified until real code, tests and runtime evidence exist.

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

## X0 — 8 features

- `X0.1` (M0) Priority inflation
- `X0.10` (M0) Plan says "reimplement from behavior" but gives no clean-room procedure
- `X0.2` (M19) M19 (desktop UI) is overloaded
- `X0.3` (M0) No dependency graph
- `X0.4` (M12) Duet defined three ways
- `X0.6` (M0) Free-tier trap list is incomplete
- `X0.7` (M2) Voice/ML licensing is stated as "check"
- `X0.8` (M25) "Zero network without account" is asserted but there is no test list

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

## E7 — 6 features

- `E7.18` (M3) sandboxPolicy: the single home for default sandbox mode and workspace root so bash and fs can't confine to different roots; consumers hand over the exact argv; 
- `E7.2` (M4) toolResultPruner: model-free pruning of oversized *current* tool results through replayable surface replacements before summary compaction.
- `E7.20` (M3) permissionPresets: user-facing presets bundling sandbox mode + approval policy; switching writes one logged permission/preset event that updates both knobs.
- `E7.21` (M5) fs-observation-policy: observed-state checks (read-before-edit, stale-file detection) contributed through the fs/* event gate.
- `E7.23` (M5) web seam: search and fetch providers register into one service; tool names stay stable.
- `E7.6` (M5) workspaceFiles: stat, paged text, byte windows, directory listings and a change feed confined by lstat, containment and a stat re-check.

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

## E4 — 3 features

- `E4.15` (M0) Every non-trivial model/protocol/human-visible change updates a keyless recorded-session scenario; new capability seams and lifecycle variants name every requir
- `E4.5` (M25) Snapshot scenarios: parent/child session files with version in filename that must agree with header; snapshot.yml declares profile, header class, recording poli
- `E4.8` (M25) Test-process isolation rules: forked workers share ports, paths, namespaces and children; each test owns every resource it acquires through teardown; a spec tha

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
