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
- All 865 canonical IDs are unchanged: 854 verified, 9 not_started (7 D6 human-workflow conventions + W1.18 licensing + Y6.4 external observation), 2 blocked (C11.1/C11.2, owner-gated). See `REMAINING-WORK-MATRIX.md` for the exact reasons.

## Independent audit outcomes (final adversarial backend audit)

Ten independent audit agents (`agent/audit-*` worktrees) examined the 20 modules, their
reachability, cross-module behaviour, security, persistence, testing and architecture.
Headline results, from `AUDIT-REMEDIATION-SUMMARY.md`:

- **All 20 modules are genuine backends.** Independent reviewers rated every module
  `GENUINE_BACKEND`; there are no descriptor-only stubs. The 421 declared feature IDs
  sum exactly to the deduplicated `backend-final-attribution.json` denominator.
- **Real capability entry points are verified.** The four `backend.*` capabilities are
  reachable through real HTTP (`POST /api/capabilities/invoke`), CLI (`capability
  invoke`) and TUI (`/invoke`) paths, with authentication and explicit confirm gates;
  the shipped UI exposes a capability browser. `backend.invoke` executes only an
  explicit allowlist of real deterministic module functions and enforces the `execute`
  permission. `keel/tests/test_backend_hub_integration.py` covers discovery, permission
  denial, real invocation and rejection of unknown modules/functions.
- **5 / 5 end-to-end multi-module workflows passed, 102 / 102 steps**, driving real
  modules (not mocks) through the HTTP bridge.
- **Consumption boundary — intentional, not an integration failure.** No *normal*
  product workflow directly imports or calls the backend modules. They are reachable
  and exercised, but peripheral: an **intentional capability boundary**, not a coherent
  end-to-end product pipeline. Earlier "fully integrated" wording overstated this and
  is corrected here. No normal product workflow directly imports or calls the modules.
  The capability surface is the intended integration path while the
  workflow integration is completed in parallel by a separate workstream; this document
  makes no claim that such integration is finished.
- **Certification limitation:** the strengthened per-ID gate certifies **361 / 421**
  backend IDs; **60** are `verified with certification limitation` (prose-only ID
  mentions or module-level evidence docs without per-ID rows). No registry status was
  changed. See `REGISTRY-EVIDENCE-INTEGRITY.md` §4 and `REMAINING-WORK-MATRIX.md` §5.
- **Defects found were fixed** with fail-before/pass-after regression tests (redaction,
  SSRF/token/grant guards, X3 persistence durability, hub dispatch, fail-open signature
  gate, tar traversal, races); one over-broad hub confirm gate was reverted. All seven
  remediation branches were reviewed and merged. Honest accepted limitations (external
  gates, cross-process grant single-use, DNS-rebinding revalidation) remain documented.

For the authoritative deduplicated denominator, classification counts and completion
formulas, see `BACKEND-COMPLETION-ACCOUNTING.md`.


## FINAL AMENDMENT — all 421 traceability gaps closed (authoritative)

A later remediation batch (`agent/final-trace`, merged and pushed) added AST-visible
`FEATURE_TRACEABILITY` declarations and per-ID evidence rows to every owning module.
`python scripts/verify_backend_operation.py` now reports **421 passing / 0 failing**,
and `--strict` enforces the gate with a non-zero exit on any failure.

All earlier figures of **361 / 421 traceable** and **60 failing IDs** in this document
are **historical** — they describe the state before that batch and are retained only
for provenance. Current authoritative certification:

- Fully traceable: **421 / 421 = 100.0%**
- Verified-with-limitation: **0 / 421 = 0.0%**
- Registry unchanged: 865 rows, 854 verified / 9 not_started / 2 blocked.

The gate remains a certification layer over tests and declarations; it does not claim
native cross-platform or live-provider verification.
