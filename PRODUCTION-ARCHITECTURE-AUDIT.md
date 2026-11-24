# Production-Readiness Audit — Backend Architecture (candidate `e6e7efc`)

**Role:** read-only architecture subagent (`agent/prod-arch` worktree, branch `agent/prod-arch`).
**Candidate:** `e6e7efc build(release): create production candidate with classified backend-only promotion from origin/main`.
**Baseline:** `origin/main` (`ecba9d2` merge base).
**Scope audited:** `backend_hub.py`, `backend_workflows.py`, `backend_events.py`, `backend_observability.py`, the 20 `*backend.py` feature modules, `capabilities.py`, `capability_registry.py`, `webapp.py`, `cli/main.py`, `tui.py`, `runner.py`, `policy_enforcement.py`, `exec_policy.py`, `backend_contracts.py`.
**Method:** static inspection + real probes run against the **worktree source** (forced with `PYTHONPATH=<worktree>\keel\src`; note the editable install otherwise resolves `keel` to `C:\Users\Admin\Desktop\Claude clone\keel\src`). Probe scripts are in `%TEMP%\opencode\archprobe\` (not committed). No source file was modified.

---

## 0. Verdict (headline)

**Architecture verdict: CONDITIONAL PASS with three HIGH-severity defects (two error-boundary/integration, one startup/performance).** The promoted backend is internally well-built (fail-closed dispatch allowlist, cross-process file locks, idempotency ledger, hash-chained JSONL, redaction, typed envelopes) and all 114 targeted architecture tests pass. However:

1. The workflow subsystem is **wired into the product through a second, parallel call path that bypasses the capability hub** and its policy/error/audit boundaries.
2. A **typed error envelope (`bad_state_root`) is defeated by an unguarded re-derivation** in `_finalize`, so malformed state-root input raises a raw `FileExistsError` out of the webapp and CLI request handlers.
3. The capability surface **eagerly imports all 20 backend modules at import time** despite an explicit "lazy" design claim; measured capability-registry import is multi-second (2–8 s in this environment).
4. `backend_events.py` and `backend_observability.py` have **no runtime consumer** — they are reachable only from their own tests, and a duplicate `EventBus` exists in `automation.py`.

**Production recommendation:** do not treat this candidate as production-ready until the three HIGH findings (HIGH-1, HIGH-2, HIGH-3) are fixed and the eager-import/lazy-contract contradiction is resolved or explicitly accepted as a startup budget. There is **no unrelated/frontend work** in the candidate (§5).

---

## 1. Architecture diagram — real runtime call paths

```
 SURFACES
 ├── Browser UI (keel/site static assets, served by webapp)
 │        HTTP ──> webapp.py:make_server() -> Handler.do_GET/do_POST
 ├── CLI  `keel ...`  ──> cli/main.py:main() dispatch
 ├── TUI  `keel tui`  ──> tui.py:Tui.handle_command()
 └── Agent tool `run_workflow` ──> runner.py:719  ──> workflows.py  (LEGACY local
                                    workflow engine — NOT backend_workflows)

 PATH A — CAPABILITY PATH (web / CLI / TUI)
 webapp.py:578  POST /api/capabilities/invoke
 cli/main.py:232  `keel capability invoke`
 tui.py:180       `/invoke <id>`
        |
        v
 capability_registry.py imported  (230 capabilities registered at import)
        |
        v
 capabilities.py:78  invoke(cap_id, params, context)
        ├─ CapabilityError: not_found / bad_params / permission_denied
        ├─ policy_enforcement.py:82 enforce()   [called BEFORE handler, OUTSIDE try]
        │       └─ exec_policy.py:385 read_policy_doc()  -> exec-policies/default.json
        ├─ handler (e.g. capabilities.py:177 _backend_invoke)
        │       |
        │       v
        │   backend_hub.py:998  invoke(module, function, params)
        │       ├─ allowlist: MODULE_FEATURES (20 modules) + DISPATCH (144 callables)
        │       ├─ importlib.import_module("keel."+module)
        │       ├─ _coerce_params() -> backend_contracts.coerce_value() (envelope decode)
        │       ├─ fn(**params)  -> real module function
        │       └─ backend_contracts.encode() -> JSON-able envelope / scalar
        │              -> 20 feature modules: d3, d6, d7, e3, e5, e6_x5_x6,
        │                 e7, small_groups, v_series, w1_security, w4,
        │                 w7_x1_y5_d1, x2, x3, x8, y1, y2, y3, y4_d4_x7, z
        │                 (overwhelmingly PURE deterministic transforms; no I/O)
        ├─ handler error -> CapabilityError(code="handler_error")  [:500]
        └─ webapp.py:610 / cli:294 / tui:231 -> record_audit()
               -> <state_root>/capability-audit.jsonl  (append-only JSONL)

 PATH B — WORKFLOW PATH (web / CLI)  *** BYPASSES capability hub ***
 webapp.py:629  POST /api/backend-workflows/<name>
 cli/main.py:314  `keel backend-workflow <name> --confirm`
        |
        v  (direct import; no capabilities.invoke, no policy_enforcement,
        |   no allowed_permissions, no record_audit)
        v
 backend_workflows.py:1386 run_workflow(name, params)
        └─ _finalize (445) -> _execute (385) -> _execution (338)
              ├─ _locked_path (200): threading.RLock + O_EXCL lock file (*.jsonl.lock)
              ├─ idempotency key (320) -> replay_denied on reuse (369)
              ├─ impl: _request_impl / _approval_impl / _delegation_impl /
              │        _mcp_impl / _recovery_impl
              └─ JSONL ledger append:
                 <state_root>/backend-workflows/{request,approval,delegation,mcp,
                 recovery}-results.jsonl
                 approval.seal.key (HMAC key, mode 0600)

 PATH C — BACKEND INFRASTRUCTURE MODULES (reachable only from tests / static scripts)
 backend_events.py:1133 EventBus   -> <state_root>/backend-events.jsonl (digest chain)
                                      + delivery-state JSONL (DeliveryTracker)
 backend_observability.py:361 record_event / :481 health_snapshot / :319 verify_chain
                                      -> <state_root>/observability.jsonl (hash chain)
        NOTE: runtime fleet events use automation.py:37 EventBus — a DIFFERENT class.
        No `import keel.backend_events` / `import keel.backend_observability`
        exists anywhere else under src/keel.

 STORAGE SUMMARY
 JSONL: capability-audit.jsonl, backend-workflows/*-results.jsonl,
        backend-events.jsonl, delivery-state.jsonl, observability.jsonl
 SQLite: x3_memory_backend.py:1071 receipts.sqlite3, :2048 finance.sqlite3;
         z_backend.py:1151 model_health (DriftStore, has close());
         fleet/db.py:250 fleet.db (pre-existing service, not a promoted module)
```

**Key structural fact:** the promotion adds a *generic capability bridge* to 20 mostly-pure function libraries, plus a *separately-wired* workflow engine. It does not make the backend services (`backend_events`, `backend_observability`) part of any product workflow. This matches `FINAL-ENGINEERING-REPORT.md:196-199` — "no normal product workflow directly consumes the backend modules — an intentional capability boundary".

---

## 2. Risks (severity, location, reproduction, production fix)

### HIGH-1 — Workflow call path bypasses the capability hub and its boundaries
- **Where:** `webapp.py:629-643`, `cli/main.py:314-339` vs. `webapp.py:578-625`, `capabilities.py:78-119`.
- **What:** `/api/backend-workflows/<name>` and `keel backend-workflow` call `backend_workflows.run_workflow()` **directly**. They never call `capabilities.invoke()`, so they skip: capability lookup/`permission` tier, `allowed_permissions` check, `policy_enforcement.enforce()` (saved exec/egress policy), `CapabilityError` normalization, and `record_audit()`. Only a token/origin gate and a literal `confirm is True` check remain. By contrast the capability path applies all of these. Two paths with divergent security/audit semantics exist for durable, mutating operations.
- **Reproduction:** static trace above; probe `probe_e2e.py` shows `backend_workflows` is not even in `MODULE_FEATURES`, so it cannot be reached through `backend.invoke` at all. `caps.list_capabilities()` contains no `backend.workflow.*` capability.
- **Production fix:** register each workflow as a `mutates=True, permission="execute"` capability in `capability_registry.py` and route both surfaces through `capabilities.invoke()`; delete the direct `run_workflow()` calls. Keep one enforcement and audit choke point. If a separate path must remain, apply `policy_enforcement.enforce()` and `record_audit()` to it explicitly and document the divergence.

### HIGH-2 — `bad_state_root` envelope defeated; raw exception escapes web/CLI
- **Where:** `backend_workflows.py:445-458` (`_finalize`, line 450) with `:263-268` (`_state_root`) and `:393-398` (`_execute`).
- **What:** `_execute` correctly catches `OSError/ValueError` from `_state_root` and returns a typed `{"code":"bad_state_root"...}` envelope. `_finalize` then calls `_state_root(dict(params))` **again, outside any guard** to attach the ledger location, re-raising the same error. Webapp line 643 has no `try/except`; CLI line 337 has no `try/except`. Result: an HTTP request/CLI command aborts with a traceback instead of a stable machine-readable error. TUI does not expose this path.
- **Reproduction:** `probe_workflow_boundary.py` — pass `state_root` pointing at a regular file:
  ```
  run_request_workflow({"state_root": <file>})
  -> RAISED builtins.FileExistsError [WinError 183] Cannot create a file when that file already exists
  ```
  `run_workflow("request", ...)` raises identically. 114 passing tests do not cover this case.
- **Production fix:** make `_finalize` reuse the already-resolved root (return it from `_execute` in the response or via `ctx`), or wrap the re-derivation in the same `try/except` and return the envelope unchanged. Add a surface-level `try/except WorkflowError/Exception` in `webapp.py:643` and `cli/main.py:337` so no backend exception can crash the request loop.

### HIGH-3 — Malformed saved policy escapes the `CapabilityError` boundary
- **Where:** `capabilities.py:97-107` (policy call outside `try`), `exec_policy.py:385-399` (`json.loads` uncaught), `webapp.py:603-624` (catches only `CapabilityError`).
- **What:** `capabilities.invoke()` calls `policy_enforcement.enforce()` before the `try` that wraps the handler. A malformed `exec-policies/default.json` makes `read_policy_doc()` raise `json.JSONDecodeError` (a `ValueError`). CLI catches `(OSError, ValueError)` (`cli/main.py:301`) and TUI catches broad `Exception` (`tui.py:239`), but the webapp catches only `CapabilityError`, so the client gets a connection error/traceback rather than the canonical error envelope.
- **Reproduction:** `probe_policy_boundary.py` with a state root containing `{ this is not json`:
  ```
  caps.invoke("backend.modules", {}, context={...})
  -> RAISED json.decoder.JSONDecodeError; is CapabilityError? False; is ValueError? True
  ```
- **Production fix:** wrap the policy call inside the same `try` in `capabilities.invoke()` and normalize `OSError/ValueError` to `CapabilityError(code="policy_error")` (matching the CLI label). Add a broad `except Exception` fallback in `webapp.py` POST handler that emits a canonical 500 envelope. Validate policy documents at write time as defence in depth.

### MEDIUM-4 — Declared capability permission tiers are never enforced by the hub
- **Where:** `capabilities.py:80, 88-93`; all three call sites (`webapp.py:604`, `cli/main.py:289`, `tui.py:228`) omit `allowed_permissions`.
- **What:** `invoke()` defaults `allowed_permissions` to `{read, write, execute}` when the caller passes nothing, and **no caller passes it**. Grep for `allowed_permissions` across `src/keel` finds only the definition and the default. Therefore `backend.invoke` (`permission="execute"`) and `backend.modules` (`permission="read"`) are equally callable through the hub. Enforcement is entirely delegated to each surface's boolean confirm gate, which is implemented three times with slightly different logic (webapp/CLI simple; TUI additionally probes policy for read-tier capabilities).
- **Reproduction:** grep result (2 hits, both in `capabilities.py`); `probe_e2e.py` shows `backend.invoke` executed with no permission argument.
- **Production fix:** derive `allowed_permissions` from the authenticated session in each surface (or add a required `context["permissions"]` with fail-closed default of `{"read"}`) and centralize confirm/policy logic in `capabilities.invoke()` so all surfaces share one gate.

### MEDIUM-5 — Import-time eager loading of all 20 modules; "lazy" claim is false
- **Where:** `capabilities.py:6-7, 138, 142` (docstring/comment claim lazy, line 142 imports hub at module scope); `backend_hub.py:341-366` (`assert_dispatch_targets()` called at import, imports all 20 modules at line 355); `backend_hub.py:1135-1150` (`_publish_schemas_on_import()` called at import, imports `capabilities` and mutates its schema objects).
- **What:** importing `keel.capabilities` or `keel.backend_hub` eagerly imports all 20 large backend modules and derives 144 signature schemas. `function_schemas()` (`backend_hub.py:838-855`) itself costs ~43 ms; the bulk is module import. No network/filesystem writes occur at import (AST scan), but CPU/time cost is material.
- **Reproduction:**
  - `probe_import.py`: `import keel.backend_hub` -> 22 backend-related modules in `sys.modules`; measured 2,006 ms / 8,043 ms on repeated runs (noisy shared machine).
  - `probe_capabilities.py`: `import keel.capabilities` -> 20 backend modules loaded; 1,578 ms.
  - `probe_registry.py`: `import keel.capability_registry` (the real surface init) -> 230 capabilities, 20 backend modules, 5,042 ms.
  - `probe_per_module.py`: sequential import of all 24 backend files ~4.6–5.3 s warm.
- **Production fix:** remove the two module-scope calls; expose `assert_dispatch_targets()` as an explicit startup/doctor check; replace `_publish_schemas_on_import()` with an idempotent `sync_capability_schemas()` invoked on first capability listing/invoke. Make `function_schemas()` per-module lazy (derive only for the module being described/invoked). Add a startup-budget test (e.g., <300 ms to import `capabilities`).

### MEDIUM-6 — `backend_events` and `backend_observability` are orphan modules; duplicate event bus
- **Where:** `backend_events.py:1133`, `backend_observability.py:361,481,319`; `automation.py:37`; `capability_registry.py:1535,1548`.
- **What:** no runtime module imports `backend_events` or `backend_observability` (grep across `src/keel` returns only their own internal references). Fleet event capabilities use `automation.EventBus`, a separate simpler class. Consequently the digest-chained event log, delivery tracker, observability chain, `health_snapshot()` and `diagnostic_report()` are dead code in production: no events are ever published to them by the product, so their integrity/observability guarantees are never exercised outside tests.
- **Reproduction:** grep for `backend_events|backend_observability` under `src/keel` -> 1 match (the module's own `SCHEMA_ID`). `hub.dispatchable()` rejects both as "unknown backend module" (`probe_e2e.py`).
- **Production fix:** either wire them in (publish real lifecycle events via `backend_events.EventBus`, call `record_event()` from the capability audit boundary, expose `health_snapshot()` as a capability) or explicitly mark them as non-runtime libraries in the promotion manifest and exclude them from production-readiness claims. Consolidate `automation.EventBus` and `backend_events.EventBus` into one implementation to avoid divergent log semantics.

### MEDIUM-7 — Import-order-dependent capability schema publication
- **Where:** `backend_hub.py:867-908` (`sync_capability_schemas`), `:1135-1150` (import-time best-effort publish), `capabilities.py:198` (registration happens after hub import returns).
- **What:** when `capabilities` is imported first (the normal surface path), `_register_backend_capabilities()` imports the hub; the hub's `_publish_schemas_on_import()` runs while registration has not yet completed, so `get("backend.invoke")` is `None` and no schema is published. Only subsequent hub calls (`feature_ids/describe/invoke/verify`) re-sync. `list_capabilities()` (used by `GET /api/capabilities`) never triggers a sync, so a client listing capabilities immediately after startup sees the static schema without `x-function-schemas`/`x-function-names`. Self-heals on first backend call, but discovery is inconsistent.
- **Reproduction:** `probe_schema_order.py` —
  ```
  capabilities-first: before hub call  x-function-schemas = False
                      after hub.feature_ids() = True (144 names)
  hub-first:          after import      = True
  ```
- **Production fix:** publish schemas at the single point where the capability is registered (in `capabilities.py`, after all registrations complete), or make `list_capabilities()` call `sync_capability_schemas()`. Add an order-independence test that imports the two modules in both orders in fresh interpreters.

### LOW-8 — Return-type schema fidelity
- **Where:** `backend_contracts.py:87-104` (`encode` falls back to `repr(value)`); `backend_hub.py:838-855` (schema derives return type from annotations).
- **What:** `y3_backend.canonical_bytes() -> bytes` is advertised as `returns: {"type":"array"}`, but `encode()` returns the string `b'"hello"'`. Clients following the advertised schema will mishandle binary results. Same for sets/datetimes.
- **Reproduction:** `probe_e2e.py` result `"b'\\"hello\\"'"` vs. schema `returns.type = array`.
- **Production fix:** encode `bytes` explicitly (base64 with `contentEncoding` marker) and map annotation `bytes` to that JSON type in `contracts.function_schema`; or document the `repr` fallback as a compatibility contract in the schema.

### LOW-9 — Unbounded in-memory registries and append-only audit logs
- **Where:** `backend_workflows.py:133-134` (`_PATH_LOCKS`), `backend_events.py:691-697` (`_LOCKS_GUARD`/`_BUS_STATES`), `backend_hub.py:835` (`_FUNCTION_SCHEMAS`), `capabilities.py:126-132` (`record_audit`), `backend_observability.py:38` (hash-chained append-only log).
- **What:** per-path lock objects and per-log shared state are never evicted; `capability-audit.jsonl` and observability logs grow without rotation. A long-lived process serving many state roots will slowly accumulate memory; on-disk logs have no retention policy.
- **Production fix:** bound the lock caches (LRU/TTL) and add log rotation/retention to `record_audit()` and observability chain writes (rotation must preserve chain continuity by carrying forward the terminal digest).

---

## 3. Startup / shutdown and resource cleanup assessment

**Startup**
- Import-time side effects found (AST scan of all 24 backend files + registry):
  - `backend_hub.py:366` `assert_dispatch_targets()` — imports all 20 modules, fail-closed on stale DISPATCH entries (good intent, wrong phase).
  - `backend_hub.py:1150` `_publish_schemas_on_import()` — imports `capabilities`, mutates registered schemas in place.
  - Benign module-level constants: regex compiles, `frozenset`s, `threading.Lock/RLock` objects, a few default registry objects (`y2_backend.py:314,473`, `z_backend.py:1645-1669`, `x8_backend.py:230`, `e6_x5_x6_backend.py:2108`). **No network calls, no file writes, no subprocess launches at import** in any backend module.
  - `capability_registry.py` import is pure decorator registration (233 static `@capability` decorators; 230 live IDs — 3 are test fixtures inside functions in `reliability_contracts.py`). No duplicate IDs (last-write-wins risk currently unrealized).
- Measured import cost: `backend_hub` 2.0–8.0 s, `capabilities` ~1.6 s, `capability_registry` (real surface init) ~5.0 s, all 24 files sequentially 4.6–5.3 s. Highly variable with machine load. The dominant cost is parsing/executing ~1.3 MB of backend source plus 144 `get_type_hints()` derivations (~43 ms).
- Configuration sources are **inconsistent**: surfaces resolve `KEEL_STATE_DIR` or `~/.keel` (`webapp.py:601`, `cli/main.py:286`, `tui.py:self.state_root`); `backend_workflows._state_root` additionally accepts `params["state_root"]`; `backend_events`/`backend_observability` require an explicit `state_root` argument. No single config owner.

**Runtime / service ownership**
- No central service container or lifecycle manager. Stateful objects (`EventBus`, `DeliveryTracker`, `DriftStore`, workflow lock contexts) are constructed per invocation from caller-supplied path arguments. This gives clean isolation but means repeated directory creation, lock-file churn, and JSONL re-indexing on each call (`EventBus.__init__` calls `_reindex()`).
- `backend_hub.invoke()` ignores the `context` dict entirely — the authenticated surface's `state_root` never reaches backend functions. This is why only pure functions can be exposed via the hub; it is an intentional boundary but limits future stateful capability work.

**Cleanup**
- File locks are correctly released in `finally` with `os.close()` + `unlink()` (`backend_workflows.py:222-230`, `backend_events.py:847-861`, `backend_observability.py:158-166`). Stale locks are reclaimed by mtime (`_STALE_LOCK_SECONDS`). This is the strongest part of the design.
- `z_backend.DriftStore` has `close()` (`z_backend.py:1162`) but no context manager and no runtime owner; no leak occurs in practice because it is never instantiated by product code.
- No background threads, `atexit` handlers, or `__del__` finalizers exist in the promoted backend modules.
- `webapp.serve()` (`webapp.py:1314-1327`) has `try/finally: server.server_close()` — the listening socket is released on `KeyboardInterrupt`. `ThreadingHTTPServer` request threads are daemon threads and are not joined, so in-flight requests are cut off at shutdown; acceptable for a local tool, not for graceful drain.
- No explicit shutdown path exists for capability audit/observability logs (append-only, OS-buffered; each `record_audit()` opens/closes the file, so durability per record is reasonable).

**Conclusion:** startup is correct but unacceptably heavy for a CLI/TUI tool and misdocumented; shutdown is adequate for a local single-user process; no resource leak found in normal paths, but unbounded caches/logs need a retention policy for long-lived servers.

---

## 4. Production-readiness gate coverage

**Note on gate identity.** The mission's authoritative list of 20 gates was not present anywhere in the audited worktree (searched `FINAL-APPROVAL-GATE.md`, `PRODUCTION-PROMOTION-MANIFEST.md`, and all `master-plan-v6-*evidence.md` files; they contain plan gates G1–G7, research Gates 1–5, and M0–M17, not a 20-item production-readiness set). I therefore enumerate the **20 standard production-readiness gates (G01–G20) used for this audit** below. If the parent mission numbers them differently, the evidence rows map directly by topic and can be relabelled.

| Gate | Description | Covered by this evidence? | Result |
|---|---|---|---|
| G01 | Clean-environment import succeeds | Yes — probes with forced worktree `PYTHONPATH` | **PARTIAL**: imports succeed, but 2 s–8 s cost |
| G02 | No import-time network/FS side effects | Yes — AST scan of 24 modules + registry | **PASS** (only in-memory mutation) |
| G03 | Startup latency budget | Yes — timed imports | **FAIL** (multi-second; no budget test) |
| G04 | Deterministic capability registration | Yes — static+live ID scan | **PASS** (230 live, 0 duplicates) |
| G05 | Capability schema complete at discovery | Yes — import-order probes | **FAIL** (order-dependent, MEDIUM-7) |
| G06 | Dispatch allowlist fail-closed | Yes — `assert_dispatch_targets`, `invoke` checks | **PASS** (20 modules / 144 fns; stale entries fail import) |
| G07 | Typed errors at hub boundary | Yes — `invoke` try/except | **PASS** (BackendHubError) |
| G08 | Typed errors at capability boundary | Yes — malformed-policy probe | **FAIL** (HIGH-3) |
| G09 | Typed errors at surface boundary | Yes — webapp/CLI/TUI source + probes | **FAIL** (HIGH-2, HIGH-3) |
| G10 | Permission tier enforced end-to-end | Yes — grep of `allowed_permissions` | **FAIL** (MEDIUM-4) |
| G11 | Saved exec/egress policy enforced at boundary | Yes — `policy_enforcement` review | **PARTIAL** (enforced on capability path only; see HIGH-1) |
| G12 | Consistent confirm/authentication across surfaces | Yes — three surface handlers | **PARTIAL** (web/CLI/TUI differ; workflow path diverges) |
| G13 | JSONL persistence atomicity & idempotency | Yes — static review of `_execution`, locks | **PASS** (replay guard, O_EXCL locks) |
| G14 | SQLite connection lifecycle & thread safety | Yes — `DriftStore`, x3 SQLite sites | **PASS** (single conn + RLock; no runtime owner) |
| G15 | Cross-process locking | Yes — lock acquisition/release review | **PASS** |
| G16 | Secret redaction before persistence/return | Yes — `_redact`, `redact_text` call sites | **PASS** (static evidence only) |
| G17 | Hash-chain integrity & auditability | Static review only | **UNVERIFIED** live: no runtime producer writes to these chains (MEDIUM-6) |
| G18 | Graceful shutdown & resource cleanup | Source review of `serve()`, locks, finalizers | **PARTIAL**: socket closed; request threads not joined; no soak test |
| G19 | Promotion scope isolation (no frontend) | `git diff` checks | **PASS** (§5) |
| G20 | Real call-path integration (no orphan modules) | Grep + E2E probes | **FAIL** (HIGH-1, MEDIUM-6) |

**Gates explicitly not verified by this architecture evidence (require other subagents / external conditions):** live provider/model behaviour; native macOS/Linux sandbox conformance; full-suite test execution beyond the 114 targeted tests; concurrency/load and multi-process contention soak; clean-VM install and upgrade; signing/release/owner gates; long-running memory and log-growth soak (G09/G17/G18 dynamics); UI integration and observable behaviour in the browser/desktop shell.

---

## 5. Promotion scope — unrelated/frontend work statement

**Explicit statement: the candidate contains no unrelated frontend/desktop work.**

Verified by real commands in the worktree:
- `git diff --name-only origin/main -- keel/site keel/desktop keel/desktop-app` → **empty output** (the exact mandated check).
- Broader sweep for `*.js, *.jsx, *.ts, *.tsx, *.css, *.html, *.vue, *.svelte, *.swift, *.kt, *.rs`, `Cargo.toml`, `package.json`, `tailwind` across all 359 changed paths → **empty output**.
- `git diff --name-only origin/main -- keel/fleet-next` → **empty output**.

Desktop-adjacent paths that *are* present are backend/CI artefacts, not frontend source: `.github/workflows/build-desktop.yml` (classified `BACKEND_TEST_OR_CI`), `keel/src/keel/desktop_contracts.py` (backend contract library), and desktop-related capability validators inside `y4_d4_x7_backend.py`. `PRODUCTION-PROMOTION-MANIFEST.md:66-68,102-106` correctly classifies the actual frontend files (`desktop-app/main.js`, `desktop/sw.js`, `site/ui/app.js`, `site/ui/style.css`, etc.) as `UNRELATED_EXCLUDED`, and they are absent from the candidate. No commit in `e6e7efc` touches them.

---

## 6. Evidence appendix — probes and results

All probes were run with `PYTHONPATH=<worktree>\keel\src` (verified `keel.__file__` = worktree path), Python 3.11.9, stdout encoding cp1252, on 2026-11-24.

| Probe | Command / purpose | Result |
|---|---|---|
| Import surface | `probe_import.py`: import `backend_hub`, count modules and schemas | 2,006 ms first run / 8,043 ms later run; 25 keel modules, 22 backend-named; 20 modules, 421 feature IDs, 144 dispatch entries, 144 schemas |
| Capability import | `probe_capabilities.py` | 1,578 ms; 20 backend modules loaded; only 4 backend capabilities registered by `capabilities.py` |
| Registry import | `probe_registry.py` | 5,042 ms; 230 capabilities; 20 backend modules; hub loaded |
| Per-module timing | `probe_per_module.py` | 24 files, 4.6–5.3 s total; hotspots `w4_backend` ~510–764 ms, `backend_contracts` ~313–582 ms, `backend_events` ~342–383 ms |
| Schema derivation | inline: reset `_FUNCTION_SCHEMAS`, time `function_schemas()` | 43.4 ms cold (144 entries), 0.001 ms warm |
| AST side-effect scan | `ast_sideeffects.py` over all `*backend*.py` | Only 2 executable import-time calls in `backend_hub.py` (366, 1150); rest are constants/locks/regexes |
| Call-path trace | grep + reads of `webapp.py`, `cli/main.py`, `tui.py`, `runner.py`, `capabilities.py` | Path A (capability) and Path B (direct workflow) confirmed; `runner.run_workflow` → legacy `workflows.py` |
| Dispatch reachability | `probe_e2e.py` | `backend_workflows`, `backend_events`, `backend_observability`, `backend_hub`, `backend_contracts` all rejected by `dispatchable()` / `invoke()` as unknown modules |
| E2E capability invoke | `probe_e2e.py`: `backend.invoke` → `y3_backend.canonical_bytes` | `{"ok":true,...,"result":"b'\"hello\"'"}`, `elapsed_ms:0.0` |
| Error boundary (policy) | `probe_policy_boundary.py`: malformed `exec-policies/default.json` | Raw `json.decoder.JSONDecodeError`; not a `CapabilityError`; is a `ValueError` |
| Error boundary (workflow) | `probe_workflow_boundary.py`: `state_root` = existing file | Raw `FileExistsError [WinError 183]` from both `run_request_workflow` and `run_workflow` |
| Schema order | `probe_schema_order.py`: fresh interpreters, two import orders | capabilities-first: schema missing at startup, appears after `feature_ids()`; hub-first: present at import |
| Duplicate capability IDs | `probe_dupes.py` | 233 static decorators, 230 live IDs; 3 static-only are test fixtures; 0 duplicates |
| Targeted tests | `python -m pytest -q tests/test_backend_hub_integration.py tests/test_backend_workflows.py tests/test_backend_observability.py tests/test_backend_events.py` | **114 passed in 36.12 s** |
| Frontend scope | three `git diff --name-only origin/main -- ...` sweeps | all empty |

---

## 7. Final recommendation

- **Merge-blocker fixes:** HIGH-1 (single enforcement/audit path for workflows), HIGH-2 (guard `_finalize` re-derivation + surface exception guards), HIGH-3 (normalize policy errors inside `capabilities.invoke`).
- **Before production release:** MEDIUM-4 (permission tiers), MEDIUM-5 (remove eager imports and correct the "lazy" documentation / set a startup budget), MEDIUM-6 (wire or formally descope the orphan modules), MEDIUM-7 (order-independent schema publication).
- **Operational follow-up:** LOW-8 (binary schema fidelity), LOW-9 (bounds/rotation), graceful request drain, and independent verification of G17/G18 under load.
- **Scope:** the candidate is cleanly backend-only; no frontend/desktop work is present and no source file was modified by this audit.
