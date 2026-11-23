# Remaining P0 implementation batches

Generated from PLAN-INDEX.json: **35 not-started P0 features** in 14 source groups.

These are candidate workstreams for specialist agents. Do not mark any feature verified until real code, tests and runtime evidence exist.

## V — 7 features

- `V1` (M10) Plugin scope tree (lifecycle-safe plugins): every plugin runs in a scope that records what it registered (tools, hooks, routes, UI panels, timers, subprocesses)
- `V16` (M0) Keel invariant-gate catalog: a list of gates specific to Keel: Tier-2 table hash unchanged; no outbound network in offline suite; no secret in logs; every tool 
- `V2` (M3) Policy simulator with "winning rule" trace: shows ordered rules, which matched, which won, why a multi-resource op was denied, and the Tier-2 verdict.
- `V24` (M5) Tool conformance kit: one automated suite every tool must pass: output schema declared, presenter pure on replay, cancel honored within N ms, no leaked fields i
- `V26` (M4) Request-reconstruction test: replay a session log and rebuild the exact provider request; byte-compare with what was actually sent (hash) to prove "model-visibl
- `V31` (M19) Local-socket transport spike: prove Electron ↔ Python over named pipe/UDS with streaming and backpressure on all three OSes before committing (C-19); keep TCP+t
- `V5` (M3) Strictness presets as rule sets: Cautious / Balanced / Trusted compiled into ordered rule arrays, diffable and exportable, never able to touch Tier 2.

## D7 — 4 features

- `D7.1` (M0) Gate scheduler (`run-gates`): all gates as a dependency graph; bounded concurrency env var; fail-fast switch; a failure skips only its dependents so independent
- `D7.12` (M0) CI layout: broad lanes of independent gates, a smaller Node-version compatibility matrix, native Windows lane in a separate workflow, Python checks separate, re
- `D7.19` (M21) Benchmark method: drive tasks through the SDK's minimal JSON-RPC agent variant with separate workspaces and session ids per independent task.
- `D7.9` (M0) Strict dependency linker so undeclared deps fail; build scripts of dependencies explicitly allowlisted.

## E4 — 3 features

- `E4.15` (M0) Every non-trivial model/protocol/human-visible change updates a keyless recorded-session scenario; new capability seams and lifecycle variants name every requir
- `E4.5` (M25) Snapshot scenarios: parent/child session files with version in filename that must agree with header; snapshot.yml declares profile, header class, recording poli
- `E4.8` (M25) Test-process isolation rules: forked workers share ports, paths, namespaces and children; each test owns every resource it acquires through teardown; a spec tha

## X10 — 3 features

- `X10.1` (M0) Definition-of-done template
- `X10.2` (M0) Provenance file
- `X10.4` (M0) Builder "stop list": actions that always pause for the owner, mirrored from gates G1 to G7 plus destructive repo actions, as a machine-readable file the builder

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
