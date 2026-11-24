# Keel v6 backend implementation detail
Branch: `integration/v6-backend-complete` (local only).
Generated from `backend-final-attribution.json` and per-module evidence documents.
Attribution uses each module's declared feature registry; cross-references to othermodules' features are NOT attributed.

| Module | Features | Subsystem | Evidence ||---|---:|---|---|
| `keel/src/keel/d3_backend.py` | 13 | Capability packages, agent teams, deliverables, extension approval, quarantine, scheduling, framed wire codecs | master-plan-v6-d3-backend-evidence.md |
| `keel/src/keel/d6_reliability_backend.py` | 18 | Typed KeelError hierarchy, API change recorder, reference loader, import gates, doc-coverage checks, SDK projection validation | master-plan-v6-d6-backend-evidence.md |
| `keel/src/keel/d7_workflow_backend.py` | 16 | Worker budgets, typecheck faces, build plans/identity, hook sets, doc gates, coverage gates, signing profiles | master-plan-v6-d7-backend-evidence.md |
| `keel/src/keel/e3_backend.py` | 13 | In-memory subagent tree: one activation API, capability options, durable children, messaging, interrupts, whole-tree drain | master-plan-v6-e3-backend-evidence.md |
| `keel/src/keel/e5_backend.py` | 13 | Release identity, bundled-runtime enforcement, transactional activation/rollback, seed manifest, updater, plugin IPC | master-plan-v6-e5-backend-evidence.md |
| `keel/src/keel/e6_x5_x6_backend.py` | 27 | Provider config/edit rules, follow-pin lists, JIT grants + audit, sandbox profiles, config schema, event registry | master-plan-v6-e6-x5-x6-backend-evidence.md |
| `keel/src/keel/e7_runtime_backend.py` | 36 | Token measurement, auth flows, pressure reconciliation, session bindings, fail-closed validators, MCP gates | master-plan-v6-e7-backend-evidence.md |
| `keel/src/keel/small_groups_backend.py` | 54 | Voice, hooks/projections, coverage gates, MCP panel, VCR/soak, memory ledger, model precedence, planning | master-plan-v6-small-groups-backend-evidence.md |
| `keel/src/keel/v_series_backend.py` | 24 | Reject cascades, opaque correlation IDs, adapter one-writer lock, confirmation codes, capability scans, fuzzers | master-plan-v6-v-series-backend-evidence.md |
| `keel/src/keel/w1_security_backend.py` | 16 | Plugin scope tree, loopback web launch, SSH hints, CI matrix, benchmark store, doc/i18n, private plugin index | master-plan-v6-w1-backend-evidence.md |
| `keel/src/keel/w4_backend.py` | 13 | MCP config normalization, OAuth/CIMD/DCR, callback validation, pooled connections, slash commands, elicitation | master-plan-v6-w4-backend-evidence.md |
| `keel/src/keel/w7_x1_y5_d1_backend.py` | 32 | Sign-in tokens, share views, spend ledger, CSRF, reversible plugin effects, profiles, webhooks, dialect re-render | master-plan-v6-w7-x1-y5-d1-backend-evidence.md |
| `keel/src/keel/x2_orchestration_backend.py` | 16 | Diagnostics ledger, LSP code actions, TDD state machine, merge queue, runner adapters, process supervisor | master-plan-v6-x2-backend-evidence.md |
| `keel/src/keel/x3_memory_backend.py` | 16 | Durable JSON/SQLite memory, consent gates, encrypted clipboard, PNG/pHash, SM-2, safe formula evaluator, PDF writer | master-plan-v6-x3-backend-evidence.md |
| `keel/src/keel/x8_backend.py` | 15 | Layout/notification/tray state, selection routing, thread index, citation validation, LCS diff, draft recovery, WCAG | master-plan-v6-x8-backend-evidence.md |
| `keel/src/keel/y1_config_backend.py` | 25 | MCP permission naming, tool exposure, patch format, glob/grep defaults, shell/web tools, config precedence, plugin DSL | master-plan-v6-y1-backend-evidence.md |
| `keel/src/keel/y2_backend.py` | 15 | Card/event rows, collab tools, screen leasing, compaction, prompt cache identity, SSE streams, routines/cron | master-plan-v6-y2-backend-evidence.md |
| `keel/src/keel/y3_backend.py` | 13 | Provisioning queues, pairing flow, admin invites, versioned routes, approval, LRU cache, branding/docs | master-plan-v6-y3-backend-evidence.md |
| `keel/src/keel/y4_d4_x7_backend.py` | 31 | Tarball builder, integrity checks, path-safe vault/import, state machines, lint gates, identity/composition seams | master-plan-v6-y4-d4-x7-backend-evidence.md |
| `keel/src/keel/z_backend.py` | 15 | SHA-256 lockfiles, agent runner, redacted replay, capability negotiation, hash-chained sync, Ed25519 catalog, budgets | master-plan-v6-z-backend-evidence.md |

## Verification and integration

- Each module has a dedicated test file with behavioral assertions (outputs, errors, state transitions). Independent reviewers rated all 20 modules **GENUINE_BACKEND** (no descriptor-only stubs).
- Modules are reachable from the real runtime through `keel/src/keel/backend_hub.py`, which registers four capabilities on `keel.capabilities` — the authenticated permission-aware surface used by the web bridge, CLI, TUI and desktop shell. `backend.invoke` executes only an explicit allowlist of real deterministic module functions and enforces the `execute` permission.
- `keel/tests/test_backend_hub_integration.py` exercises discovery, permission denial, real function invocation, unknown-module/function rejection, import verification and feature-index integrity.
- MEDIUM/LOW findings from independent review were fixed with regression tests (see remediation commits).
- All 865 canonical IDs are unchanged: 854 verified, 9 not_started (7 D6 human-workflow conventions + W1.18/Y6.4 owner-gated conflicts), 2 blocked (C11.1/C11.2).
