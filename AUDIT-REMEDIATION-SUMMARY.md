# Keel final adversarial backend audit — remediation record

Branch: `integration/v6-backend-complete` (local only). Audit baseline: `5dbc5f9`.

## Audit workstreams (10 independent agents, isolated worktrees)
`agent/audit-{hub,pathways,modules-a,modules-b,crossmod,security,persist,testing,arch,redteam}`.
Reports: `AUDIT-{HUB-INTEGRATION,REAL-PATHWAYS,MODULES-A,MODULES-B,CROSSMODULE,SECURITY,PERSISTENCE,TESTING,ARCHITECTURE,REDTEAM}.md`.

## Verdicts
- **All 20 modules perform genuine backend operations** (no descriptor-only modules). 5 end-to-end multi-module workflows passed 102/102 steps through real modules.
- **Reachability: YES** — the 4 `backend.*` capabilities are reachable via real HTTP (`/api/capabilities/invoke`), CLI (`capability invoke`) and TUI (`/invoke`) paths, with auth + explicit confirm gates. The shipped UI exposes a capability browser.
- **Consumption: PARTIAL** — no normal product workflow imports or calls the modules directly; they are reachable but peripheral (an intentional capability boundary, not a coherent end-to-end pipeline). The previous "fully integrated" wording overstated this; corrected in documentation.
- **Registry integrity**: strengthened from dict-membership certification to an AST + evidence-doc symbol/test cross-check. 361/421 traced IDs pass; 60 fail traceability (not status-downgraded — their modules/tests exist; documented as a certification-layer limitation).

## Confirmed defects fixed (fail-before/pass-after regression tests)
| Area | Defects | Fix branch |
|---|---|---|
| W7/W4/Z/shared/E5 redaction | 3 HIGH credential leaks (share artifacts, OAuth errors, replay HTML) + DLP gaps | `agent/auditfix-redact` |
| Y1/Y2/E6 guards | SSRF DNS bypass, token never compared, grant replay via serialized snapshot | `agent/auditfix-guards` |
| X3 persistence | consent grants not durable, fixed-temp atomic save, fail-open load, finance dedupe, receipt split-brain | `agent/auditfix-x3` |
| Hub | broken dispatch entries, text-only verify, duplicate feature ownership, over-broad confirm gate (reverted on integration after regression) | `agent/auditfix-concurrency` |
| Logic/safety | release signature fail-open, tar path traversal, read-only SQL key-name check, fake-success summaries, timestamp validation | `agent/auditfix-logic` |
| Z/W7 races | budget TOCTOU, unsafe JSONL append, cross-instance lock failures, DriftStore thread-bound connection, negative-charge fake success | `agent/auditfix-races` |
| Registry | derived criteria for 93 rows, AST + evidence-doc cross-check, honest limitation record | `agent/auditfix-docs` |

## Honest accepted limitations
- No production workflow directly consumes the modules; capability boundary is the intended integration path.
- Cross-process grant single-use and DNS-rebinding revalidation need host-consumer work/durable design; out of local scope.
- Native Linux/macOS sandbox verification, provider credentials, signing and push authorization remain external/owner-gated.
- Several LOW test-quality findings (weak assertions, descriptor-only coverage loops) documented, not silently patched.

## Remediation integration status — COMPLETE

All seven remediation branches were lead-reviewed (diff + independently re-run targeted
suites) and merged with `--no-ff` onto `integration/v6-backend-complete`:

| Branch | Bugs fixed | Regression proof |
|---|---|---|
| `agent/auditfix-redact` | 3 HIGH + 1 MED + 1 LOW credential leaks; W4 helper rename | 6 new failing-then-passing tests; 330 targeted tests pass |
| `agent/auditfix-guards` | SSRF DNS, token comparison, grant replay | 10 new tests; 179 targeted tests pass |
| `agent/auditfix-x3` | consent durability, atomic save, fail-open load, finance dedupe, receipt split-brain | 9 new tests; 33 targeted pass |
| `agent/auditfix-concurrency` (hub) | broken dispatch entries, text-only verify, duplicate feature ownership | 15 hub tests; canonical map now 0 duplicates, 421 IDs exactly |
| `agent/auditfix-logic` | fail-open signature gate, tar traversal, SQL key-only check, fake success, timestamp | 5 new tests; 273 targeted pass |
| `agent/auditfix-races` | budget TOCTOU, JSONL corruption, LocalSync/DriftStore/W7 races, negative charge | 7 new tests; 135 targeted pass |
| `agent/auditfix-docs` | 93 derived criteria, AST + evidence cross-check | 361/421 IDs now traceable (was 231) |

One over-broad capability confirm gate from the hub fix was **reverted on the integration
branch** because it fired before saved-policy enforcement and broke an existing security
test (`test_sandbox_no_host_write`); all real entry points (webapp/TUI/CLI) already enforce
`confirm` for write/execute capabilities.

## Environmental finding (not a product defect)
Two webapp tests (`test_quick_ask_endpoint_uses_real_runtime`,
`test_run_streams_events_and_done_marker`) timed out under ambient `~/.keel/settings.json`
MCP configuration created by concurrent user work. With an isolated `HOME`, both pass in
4 seconds. The definitive final suite therefore ran with a clean local HOME; no test was
deleted, weakened, or changed to obtain a pass.
