# STAB-INTEGRATION-EVIDENCE — backend integration audit (read-only)

**Branch:** `agent/stab-integrate` · **Base:** stabilization HEAD `f60b080`
(`f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb`) · **Date:** 2026-11-25
**Mode:** read-only source inspection + isolated runtime probes. No source file was
modified by this audit. All probe scripts and logs live outside the worktree in
`C:\Users\Admin\AppData\Local\Temp\opencode\integrate-probe\`.

---

## 0. Executive summary

| Question | Verdict |
|---|---|
| 20 backend modules real, not descriptor-only stubs? | **Yes** — 20/20 genuine implementations; 5/5 sampled modules produced real, non-trivial results (§7). No module is a descriptor-only stub. |
| Declared feature IDs | 421 unique IDs, 144 dispatch entries, 20 modules (`backend_hub.feature_ids()`, `DISPATCH`). Strict gate: **421 passing / 0 failing** (`scripts/verify_backend_operation.py --strict`, exit 0). |
| Capability hub real invocation path? | **Yes** — `POST /api/capabilities/invoke`, `keel capability invoke`, TUI `/invoke` all reach `capabilities.invoke` → `backend_hub.invoke` → real module function (§3). |
| Schema publication real? | **Yes but lazy** — 144 signature-derived schemas published only after a hub entry point; generic discovery returns an empty schema map (finding **M-3**). |
| Permission enforcement real? | **In the core, yes; in production paths, declarative only** — `allowed_permissions` is honoured by `capabilities.invoke`, but no web/CLI/TUI caller supplies it (finding **M-2**). |
| Cross-module workflows real? | **Yes** — 5/5 workflows completed end-to-end with real modules, real subprocesses, real persistence and honest dry-run/failure reporting (§5). |
| `backend_events` / `backend_observability` consumed at runtime? | **No** — zero importers under `src/keel`; dormant-by-design libraries, reachable only from tests (§4). This is an architectural boundary, not a broken call. |
| Startup/shutdown registration | Import-time capability registration; lazy one-shot hub init; process-global registry with no unregister hook; locks released via `finally` (§6). |
| HIGH defects | **0 confirmed**. |
| MEDIUM defects | **4** (M-1 … M-4). LOW/observations: 3. |

---

## 1. Method and evidence base

- AST inventory of all 25 `*backend*.py` files: 20 feature modules + 5 infrastructure
  (`backend_contracts`, `backend_events`, `backend_hub`, `backend_observability`,
  `backend_workflows`). Output: `backend_analysis.json`, `module_detail.json`.
- Import-graph scan over every `.py` under `keel/src` (AST `Import`/`ImportFrom` plus
  dynamic `keel.<module>` string literals): `callgraph.json`.
- Direct source reading of `backend_hub.py`, `capabilities.py`, `capability_registry.py`,
  `policy_enforcement.py`, `backend_workflows.py`, `webapp.py`, `cli/main.py`, `tui.py`.
- Real probes through the shipped entry points (§5, §7), isolated temp state roots.
- Targeted test suite: **143 passed in 28.97 s** (`test_backend_hub_integration`,
  `test_backend_workflows`, `test_backend_contracts`,
  `test_backend_contracts_hardening`, `test_backend_events`,
  `test_backend_observability`). Strict evidence gate: **OK**.

> **Environment note:** an early probe run from a shared temp directory picked up a
> foreign `select.py` created by a concurrent session, shadowing the stdlib and
> producing a spurious `UnicodeEncodeError`. Probes were moved to a private
> directory (`integrate-probe\`) and re-run clean; this is **not** a repository
> defect and is not counted as a finding.

---

## 2. Call graph (actual runtime paths)

```
                       ┌──────────── transport surfaces ────────────┐
                       │ webapp.py:670  /api/capabilities/invoke     │
                       │ cli/main.py:267 keel capability invoke      │
                       │ tui.py:180     /invoke <id> [json]           │
                       └──────────────────┬───────────────────────────┘
                                          │  capabilities.invoke()
                                          │  (permission + policy + confirm)
                                          ▼
                       capabilities.py:156 _register_backend_capabilities()
                       backend.modules / describe / invoke / verify  [core, read|execute]
                                          │
                                          ▼
                       backend_hub.py:1042 invoke()
                       allowlist DISPATCH (144 names) + importlib.import_module()
                                          │
                          ┌───────────────┴────────────────┐
                          ▼                                ▼
                 20 feature modules               backend_contracts
                 (pure/stateful services)          (envelope codec)
                          ▲
                          │  direct imports (10 of 20 only)
                          │
                       backend_workflows.py  ──► webapp.py:760 /api/backend-workflows/<name>
                       (5 composed workflows) ──► cli/main.py:314 keel backend-workflow
                                          │
                                          ├─ policy_enforcement.enforce("backend.workflow")
                                          ├─ capabilities.record_audit(surface="workflow")
                                          └─ HMAC-chained JSONL ledgers per workflow

   DORMANT (0 runtime importers):
     backend_events.py  (SCHEMA_ID self-reference only)
     backend_observability.py ──imports──> backend_hub.py   [one-way edge]
```

### 2.1 Direct static callers of each backend module (runtime source, tests excluded)

| Direct caller | Modules |
|---|---|
| `backend_workflows.py` (real workflow seam) | `e3_backend` (:1118), `e6_x5_x6_backend` (:898,919,982), `w1_security_backend` (:1242,1255), `w4_backend` (:1256), `w7_x1_y5_d1_backend` (:921,983), `x2_orchestration_backend` (:1119,1257), `x3_memory_backend` (:679,1415), `y1_config_backend` (:1258), `y2_backend` (:1120), `z_backend` (:1414) |
| **No static caller** — reachable only via hub dynamic `importlib.import_module` | `d3_backend`, `d6_reliability_backend`, `d7_workflow_backend`, `e5_backend`, `e7_runtime_backend`, `small_groups_backend`, `v_series_backend`, `x8_backend`, `y3_backend`, `y4_d4_x7_backend` |
| Infrastructure | `backend_contracts` ← `backend_hub.py:24`; `backend_hub` ← `capabilities.py:157` (real) and `backend_observability.py:745` (orphan); `backend_workflows` ← `webapp.py:769`, `cli/main.py:315` |

**Interpretation:** the hub is the universal integration path (all 20); a separate,
narrower workflow composer directly wires 10 of 20 into product workflows. This
matches the corrected boundary in `BACKEND-IMPLEMENTATION-DETAIL.md:54-61` — the
capability surface is the intended integration path, not a fully woven pipeline.

---

## 3. Per-module verdicts (20/20)

Legend: `F/C` = top-level functions / classes; `own IDs` = the module's own declared
registry count; `hub IDs` = IDs attributed by `backend_hub.MODULE_FEATURES`; `disp` =
allowlisted dispatch functions.

| # | Module | Verdict | F/C | own IDs | hub IDs | disp | Direct runtime caller | Persistence | Permissions / error handling | Resource limits |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| 1 | `d3_backend` | GENUINE | 27/59 | `FEATURE_IDS`=13 | 25 | 3 | hub only | JSONL/text writes, atomic replace | 15 typed errors; Fs verdicts | `_OFFLINE_SCAN_LIMITS` (5), timeouts |
| 2 | `d6_reliability_backend` | GENUINE | 42/76 | `FEATURE_TRACEABILITY`=18 | 18 | 8 | hub only | JSON report output | `KeelError` hierarchy + 23 errors; fail-closed gates | `max_*`, budget, timeouts |
| 3 | `d7_workflow_backend` | GENUINE | 84/36 | `FEATURE_IDS`=16, `P0_FEATURE_IDS`=4 | 20 | 10 | hub only | plan/record JSON | typed contract errors; signing/packaging gates | `max_*`, budget, security-critical module set |
| 4 | `e3_backend` | GENUINE | 16/44 | `FEATURE_IDS`=13 | 15 | 5 | `backend_workflows.py:1118` | in-memory tree (durable children by design) | `E3_1_CAPABILITIES`, route allowlist; 6 typed errors | capacity, depth_limit, fork contiguity |
| 5 | `e5_backend` | GENUINE | 45/17 | feature manifest in `__all__` + traceability fn | 13 | 2 | hub only | none (pure contract/state machine) | 14 typed errors; activation/lock ownership, forbidden plugin caps | 16 seed shards, 1 rollback profile, lock staleness |
| 6 | `e6_x5_x6_backend` | GENUINE | 66/63 | `FEATURE_TRACEABILITY`=27 | 27 | 10 | `backend_workflows.py:898,919,982` | JSON config/export state | `CapabilityTokenIssuer`, grants, JIT, time-boxed rules; 3 typed errors | TTL, egress allowlist, cap |
| 7 | `e7_runtime_backend` | GENUINE | 38/124 | `FEATURE_IDS`=36, `FEATURE_SURFACES`=36 | 39 | 7 | hub only | JSON snapshots / open() | role policy, auth/authorization split, fail-closed validators; 7 typed errors | `_VISIBILITY_LIMIT`, cursor/history caps, budgets |
| 8 | `small_groups_backend` | GENUINE | 19/47 | `FEATURE_IMPLEMENTATIONS` | 54 | 5 | hub only | JSONL persistence, SQLite-backed sessions | consent gates, permission simulation; typed hook errors | blob caps, soak/benchmark budgets, timeouts |
| 9 | `v_series_backend` | GENUINE | 100/54 | `FEATURE_IDS`=24 | 31 | 10 | hub only | JSON artifacts, text writes | `CAPABILITY_TO_PERMISSION`, confirmation gate; 2 typed errors | budget table/countdown, fuzz corpus, worktree lock |
| 10 | `w1_security_backend` | GENUINE | 36/18 | `W1_FEATURES`=16 | 20 | 5 | `backend_workflows.py:1242,1255` | atomic plugin YAML/JSON writes | scope tree, loopback-only web launch, vendor policy; 4 typed errors | CI matrix bounds, feedback bundle limits |
| 11 | `w4_backend` | GENUINE | 45/27 | `FEATURE_IDS`=13, `FEATURE_IMPLEMENTATIONS`=13 | 14 | 10 | `backend_workflows.py:1256` | config document JSON | permission rules, session-id suppression, pool leases; 9 typed errors | timeouts (30 s/30 s/12 h), pool size |
| 12 | `w7_x1_y5_d1_backend` | GENUINE | 64/18 | `FEATURE_TRACEABILITY`=1 | 34 | 10 | `backend_workflows.py:921,983` | atomic JSON, sealed key files | CSRF, sealed tokens, spend ledger, capped multipart; 2 typed errors | `_MAX_TTL`, body/recording caps |
| 13 | `x2_orchestration_backend` | GENUINE | 35/24 | `FEATURE_IDS` | 16 | 3 | `backend_workflows.py:1119,1257` | JSON ledgers, atomic writes | `BackendError.to_dict`, guard errors, review gates | bounds, timeouts, tail limits |
| 14 | `x3_memory_backend` | GENUINE | 19/6 | traceability via methods | 16 | 3 | `backend_workflows.py:679,1415` | SQLite + JSON state, atomic replace, encrypted clipboard | consent grants, folder approval, redaction; `X3Error`/`ConsentDenied` | TTL, state locks, file-size caps |
| 15 | `x8_backend` | GENUINE | 39/70 | traceability via declarations | 17 | 10 | hub only | layout/theme JSON | kill switch, citation validation, undo safety; 16 typed errors | contrast/WCAG thresholds, zoom bounds |
| 16 | `y1_config_backend` | GENUINE | 87/49 | traceability via 25 dedicated IDs | 26 | 10 | `backend_workflows.py:1258` | none (pure config validators) | 26 typed errors, skill/subagent depth gates, URL/transport validation | `_MAX`, media/tool-output limits, idle timeout |
| 17 | `y2_backend` | GENUINE | 30/78 | `FEATURE_TRACEABILITY`=1 | 21 | 9 | `backend_workflows.py:1120` | JSON ledger | `RolePolicy`-style tool registry, token bucket, realtime secrets; 12 typed errors | rate/lease limits, compaction config |
| 18 | `y3_backend` | GENUINE | 29/61 | traceability via validation IDs | 23 | 6 | hub only | JSON cache/proposals | pairing/invite gates, admin acknowledgement, approval ledger; 15 typed errors | `SECURITY_MODEL_LIMITS`=6, concurrency, LRU |
| 19 | `y4_d4_x7_backend` | GENUINE | 50/37 | `FEATURE_BEHAVIORS`=31 | 38 | 9 | hub only | tarball/vault/import writes | path-safe tar, provider binding, workspace gate; typed errors | artifact budget, verify download |
| 20 | `z_backend` | GENUINE | 81/16 | `FEATURE_IDS`=15 | 19 | 9 | `backend_workflows.py:1414` | lockfiles, replay, SQLite/JSON, atomic writes | Ed25519 catalog verify, prompt injection corpus, policy locks; 2 typed errors | project budgets, key/signature verification |

**No descriptor-only stub detected.** The closest case is `e5_backend`, whose
`*_descriptor()` functions return static policy objects — but they are paired with
real validators (`assert_release_identity`, `assert_bundled_runtime`) and a real
state machine (`plan_activation` → `execute_activation` → `recover_activation`,
`TransactionLock`, `is_transaction_stale`), so the module is a genuine contract
implementation. `y1_config_backend` is pure but supplies 87 working validators.

---

## 4. Capability hub — allowlist, schema, permissions, invocation

### 4.1 Dispatch allowlist (real, fail-closed)
- `backend_hub.DISPATCH` (`backend_hub.py:294-339`) exposes exactly **144** named
  callables across 20 modules. `backend_hub.invoke` (`:1042-1080`) rejects unknown
  modules/functions, non-object params, and rehydrates typed envelopes
  (`_coerce_params`, `:1012-1039`). Real exceptions are re-raised as
  `BackendHubError` (`:1074-1076`) — **no fake success**.
- `assert_dispatch_targets()` (`:342-365`) verifies every advertised name is a
  callable module attribute before the first invoke (fixes the historical
  `x3_memory_backend._embedding` class-method bug, see comment at `:322-325`).
- Negative probes (§7) confirmed `not_a_module.x` and the real-but-not-allowlisted
  `d3_backend.generate_metadata` both return `bad_request`.

### 4.2 Schema publication (real but lazy)
- `function_schemas()` (`:878-896`) derives signatures via `inspect`/annotations;
  `sync_capability_schemas()` (`:908-950`) mutates the *registered* capability
  schemas in place (`x-function-schemas`, `x-module-schemas`, module `enum`).
- Confirmed: 144 schemas after one `backend.describe` call; **0 before** (finding M-3).

### 4.3 Permission enforcement
- Four capabilities registered at import time (`capabilities.py:156-213`):
  `backend.modules` (read), `backend.describe` (read), `backend.invoke` (execute),
  `backend.verify` (read), all on surface `core`.
- `capabilities.invoke` (`:78-134`) checks `allowed_permissions`, saved exec/egress
  policy (`policy_enforcement.enforce`), and a strict boolean confirm for `ask`
  decisions. My probe with `allowed_permissions={"read"}` correctly produced
  `permission_denied`.
- **Production gap (M-2):** `webapp.py:715-720`, `cli/main.py:289-293`,
  `tui.py:228-230` never pass `allowed_permissions`, so the default
  `{read, write, execute}` applies; tier separation is enforced only by each
  transport's boolean confirm gate.

### 4.4 Real invocation path (verified)
`POST /api/capabilities/invoke` (`webapp.py:670-755`) → token/origin gate → strict
`confirm is True` for execute-tier → `capabilities.invoke` → handler
`_backend_invoke` (`capabilities.py:192-198`) → `backend_hub.invoke` → module function
→ JSON response + audit record. CLI and TUI mirror this with their own confirm
prompts and audit writes. Transport errors map to 403/404/400/409/500 via
`api_contracts.http_status_for_code`.

---

## 5. `backend_events` / `backend_observability`: dormant-by-design boundary

**Finding: architectural boundary, honestly documented — not an integration failure.**

- Import scan under `keel/src`: `backend_events` has **one** self-reference
  (`backend_events.py:96` `SCHEMA_ID`); `backend_observability` has **zero** importers.
- `backend_observability.py:745` imports `backend_hub` (one-way) to compute
  `health_snapshot()`; nothing in the runtime calls back.
- `backend_observability.record_event` (`:583`), `health_snapshot` (`:761`),
  `diagnostic_report` (`:811`), `record_audit_event` (`:875`),
  `health_http_payload` (`:1122`) have **no runtime consumer outside tests**
  (`test_backend_observability.py`, `test_prod_observe.py`, `test_prod_revocation.py`).
- The fleet/event capabilities use a *different* `EventBus` in `automation.py:37`
  (called at `capability_registry.py:1535,1544,1548`); a third exists at
  `session_contracts.py:166`, and `d3_backend.FsEventBus` (`:632`) is a fourth.
- The `core.diagnostics` capability (`capability_registry.py:91-95`) uses
  `diagnostics.collect()`, **not** `backend_observability`. The claim in
  `BACKEND-DEPLOYMENT.md:151-153` that `webapp.py:378` consumes
  `health_snapshot()` is stale — that line is HTTP body-drain logic.
- Both modules are mature, hardened libraries (hash-chained JSONL, redaction,
  bounded locks, delivery tracker with backoff bounds) with 128 passing tests.
  They are simply **not wired into the product**. Consequence: their integrity
  guarantees are never exercised in production. This matches the pre-existing
  MEDIUM-6 finding in `PRODUCTION-ARCHITECTURE-AUDIT.md:149-153` and the corrected
  wording in `BACKEND-IMPLEMENTATION-DETAIL.md:54-61`.

---

## 6. Cross-module workflows — 5/5 end-to-end (real modules)

Probe: `backend_workflows.run_workflow(name, params)` with isolated
`KEEL_STATE_DIR` and `state_root` beneath it; same dispatcher used by HTTP and CLI.

| # | Workflow | Result | Steps | Real modules exercised | Real artifacts |
|---|---|---|---:|---|---|
| 1 | **request** | `ok=True`, `code=ok` (replay → `replay_denied`) | 8 | `permissions`, `provider_contracts`, `runner.RealTools`, `session_contracts`, `tools.registry`, **`x3_memory_backend`** | real `read_file` tool output (content+SHA-256 matched), 1 memory hit, persisted session (7 events, version ok), HMAC-chained result ledger |
| 2 | **approval** | `ok=True`, grant `just_in_time_granted` | 7 | **`e6_x5_x6_backend`** (`CapabilityTokenIssuer`, `resolve_profile`, `operation_allowed`, `issue_grant`, `consume_grant`), **`w7_x1_y5_d1_backend`** (`check_csrf_origin`, `seal_value`, `unseal_value`) | sealed token, possession digest, single-use consume under cross-process lock; durable actions `request → consume → revoke`; replay and post-revoke denials |
| 3 | **delegation** | `ok=True`, aggregated 2/2 | 3 | **`e3_backend`** (tree, fork prefix, settle, tree drain/dispose), **`x2_orchestration_backend`** (`ProcessSupervisor`, `normalize_outcome`), **`y2_backend`** (hidden subagents) | 2 real short-lived `sys.executable` child processes, digest-verified output, 6 lifecycle events, hidden contexts cleared |
| 4 | **mcp** | `ok=False`, `code=dry_run` (intentional) | 6 | **`y1_config_backend`** (`parse_plugin_manifest`), **`w1_security_backend`** (`parse_simple_yaml`, `bundle_digest`), **`w4_backend`** (config, naming, permission rules, system prompt, connect/disconnect), **`x2_orchestration_backend`** | real deterministic child process producing invocation descriptor; real forced failure path (`tool_failure`); permission denial of all tools; config digest unchanged; `command_executed=False`, `dry_run=True` |
| 5 | **recovery** | `ok=True` | 4 | **`x3_memory_backend`** (index, search, quarantine + `recover_state`), **`z_backend`** (`user_state_root`, `LocalSync`, `write_replay`, `verify_replay`, `assert_no_network_assets`) | 1 quarantined corrupt state file, durable query survived, replay verified, no network assets, 4 sync changes, restored state version |

**Workflow observations**
- No fake success: MCP explicitly returns `ok=False/dry_run` and never executes a
  caller-supplied command (`backend_workflows.py:1324-1388`). Forced failure is a real
  child-process exit code, not a simulated flag.
- Idempotency/replay guards, HMAC result ledgers and `capability-audit.jsonl`
  (`surface="workflow"`) are written for every branch, including denials.
- Saved-policy enforcement and audit were added to `run_workflow`
  (`:1562-1617`, `_audit_workflow` `:1547-1559`); the older HIGH-1 "no policy/no
  audit" finding in `FINAL-RELEASE-ACCEPTANCE.md:92-96` is **closed** at this HEAD.
- Missing seam (LOW-1): TUI has `/invoke` but no workflow command; workflows are
  reachable from web (`webapp.py:760`) and CLI (`cli/main.py:314`) only.
- Labeling nit (LOW-2): in the full approval flow a post-revoke resolve reports
  `replay_denied`, not `revoked`, because the consume check precedes the revoke
  check (`:1003-1006`). Both are denials; security is unaffected.
- Misleading hint (M-1): all successful workflows (and the honest MCP dry run)
  carry `http_status=500` in the response body (see findings).

---

## 7. Five genuine-module probes (real capability path)

All invoked via `capabilities.invoke("backend.invoke", ...)` with a temp `state_root`
and `confirm=True`. Marker = non-trivial real result.

| Module | Function / probe | Result |
|---|---|---|
| `d3_backend` | `canonical_digest({"a.py":"hello","b.py":"world"})` | `33749df5…e0232` — real length-prefixed SHA-256 ✓ |
| `e7_runtime_backend` | `parse_at_paths("see @docs/a.md and @src/b.py")` | `["docs/a.md","src/b.py"]` — real parsing ✓ |
| `v_series_backend` | `make_case(id="c1", correct_answer="Paris", pushback=…, revised_answer=…)` | typed envelope `{"type":"SycophancyCase","fields":{…}}` ✓ |
| `z_backend` | `parse_client_capabilities({"capabilities":["tools","tools","stream"],…})` | de-duplicated `["tools","stream"]` with protocol `keel-capabilities/1` ✓ |
| `e3_backend` | `parse_model_route("local/sonnet")` | typed envelope `{"type":"ModelRoute","fields":{"provider":"local","model":"sonnet"}}` ✓ |

Additional direct probes:
- `e3.compute_fork_prefix([TurnStep("a"),TurnStep("b")], source_agent_id="lead")` →
  `("a","b")`, and correctly rejects a completed step after an incomplete one with
  `ForkPrefixError` — real state logic, not a descriptor.
- `X3Backend` in a fresh temp root: `approve_folder` + `index_folders` +
  `search_documents("marker")` + `save()`, then reopen with a **new** `X3Backend`
  instance → approved folder persisted, 1 hit restored, state version present —
  real durable persistence.
- Negative: unknown module and real-but-unlisted `d3_backend.generate_metadata` →
  `bad_request`; `allowed_permissions={"read"}` on execute-tier `backend.invoke` →
  `permission_denied`.

---

## 8. Startup / shutdown registration and orphan components

- **Startup:** `capabilities.py:213` calls `_register_backend_capabilities()` at
  import; `capability_registry.py` (imported lazily by `webapp.py:590,674`,
  `cli/main.py:233`, `tui.py:170,181`) registers all other capabilities. Backend
  modules themselves are *not* imported at startup: `backend_hub._ensure_initialized()`
  (`:385-404`) performs one-shot lazy validation + schema publication under a lock
  on first public hub call.
- **Shutdown:** no `atexit`, unregister or teardown hook exists for the
  process-global `_REGISTRY`/`_INITIALIZED` — normal for a long-lived local process.
  All file locks use `try/finally` with `os.close` + unlink (`backend_workflows.py:201-230`,
  `backend_events.py:739-882`, `backend_observability.py:135-184`); stale locks are
  reclaimed by mtime. No leaked-lock orphan found.
- **Orphan/disconnected components:**
  1. `backend_events.py` — no runtime consumer (§5).
  2. `backend_observability.py` — no runtime consumer (§5); one-way import of hub.
  3. Three additional `EventBus` implementations (`automation.py:37` — the only one
     actually used at runtime; `session_contracts.py:166`; `backend_events.py:1140`;
     plus `d3_backend.FsEventBus:632`) — divergent log semantics (LOW-3).
  4. `backend_workflows` is intentionally outside the capability registry — it is a
     separate direct route with its own policy/audit gate; not an orphan (it has real
     web/CLI callers and ledgers).

---

## 9. Findings (with file:line)

### MEDIUM

**M-1 — Successful workflow responses advertise `http_status: 500`.**
- **Where:** `keel/src/keel/backend_workflows.py:83-87` (`_http_status`) and
  `:578-592`; consumed at `keel/src/keel/webapp.py:112-122,791-799`.
- **What:** `_http_status` maps only 403/400 code sets and returns **500 for every
  other code**, including `ok`. Probe: `run_workflow("request", …)` returns
  `ok=True, code="ok", http_status=500`; `delegation` and `recovery` likewise; the
  intentional MCP `dry_run` result also carries 500. The web layer happens to
  override with `HTTPStatus.OK` when `result["ok"]` is true, so the wire status is
  200 for successes — but the canonical response body field contradicts it, and
  for the MCP dry run the wire status really is 500 despite a completed, correctly
  reported dry run. Tests assert `http_status` only for denials
  (`test_backend_workflows.py:611-633`); success/dry-run hints are untested.
- **Impact:** clients reading the documented `http_status` hint misclassify success
  as a server error; operational dashboards/metrics on that field will show false 500s.
- **Fix:** add `200` for `ok`/`dry_run` (or omit the hint when `ok` is true) in
  `_http_status`, and assert it for all five workflows.

**M-2 — Capability permission tiers are not narrowed by any real transport.**
- **Where:** `keel/src/keel/capabilities.py:78-93` (default
  `allowed_permissions={read,write,execute}`); call sites `webapp.py:715-720`,
  `cli/main.py:289-293`, `tui.py:228-230` all omit it. Repo-wide grep finds no
  production caller passing `allowed_permissions` (only tests do).
- **What:** `backend.invoke` is registered as `permission="execute"`
  (`capabilities.py:183`), but through all three shipped surfaces it is callable
  with the same effective permissions as a read capability; the only gate is the
  transport's boolean confirm. The core enforcement is real (my
  `allowed_permissions={"read"}` probe returned `permission_denied`) — the seam is
  missing, not the mechanism.
- **Impact:** declarative permission tiers do not constrain end users; contradicts
  the "permission-aware surface" claim and makes tier separation test-only.
- **Fix:** derive `allowed_permissions` from the authenticated session in each
  surface, or require `context["permissions"]` with a fail-closed default of
  `{"read"}`, and centralize confirm/policy logic in `capabilities.invoke`.

**M-3 — Function schemas are published lazily, so capability discovery is empty.**
- **Where:** `keel/src/keel/backend_hub.py:372-382,385-404,908-950`;
  `capabilities.py:66-75` (`list_capabilities` returns the raw schema);
  `cli/main.py:256-265`; `webapp.py:586-597`.
- **What:** `_publish_schemas()` runs only from `_ensure_initialized()`, which is
  triggered by public hub calls. In a fresh process, `keel capability describe
  backend.invoke` and `GET /api/capabilities` report `x-function-schemas = {}`
  (measured: 0 entries), while the description text says "see x-function-schemas".
  After one `backend.describe` call the same object contains 144 schemas.
- **Impact:** clients cannot discover dispatchable function parameters before the
  first invoke/describe; the capability browser shows an incomplete contract.
- **Fix:** publish schemas at registration time (or have `list_capabilities`/`describe`
  hub-aware capabilities trigger a sync) without importing all 20 modules at startup
  — e.g. cache-and-lazy-fill on schema read.

**M-4 — `backend_events` and `backend_observability` have no runtime consumer.**
- **Where:** `backend_events.py:96,1140`; `backend_observability.py:583,761,811,875,1122`;
  duplicate bus at `automation.py:37` used by `capability_registry.py:1535,1544,1548`.
- **What:** zero imports under `src/keel` outside the modules themselves (§5). The
  hash-chained audit log, delivery tracker, health/readiness probes and redacted
  diagnostic export are never exercised by the product; fleet events use a
  different, simpler `EventBus`.
- **Impact:** production-readiness claims about tamper-evident logging and
  health/readiness are not realised at runtime; divergent event semantics across
  four bus implementations.
- **Fix:** either wire real lifecycle/audit events into these modules and expose
  `health_snapshot` via a capability, or formally classify them as non-runtime
  libraries in the promotion manifest and exclude them from readiness claims.

### LOW / observations

- **LOW-1:** TUI has no workflow command; workflows are web/CLI only (`tui.py:165-255`).
- **LOW-2:** full-approval post-revoke attempt is labelled `replay_denied` rather
  than `revoked` (`backend_workflows.py:1003-1006`) — still a denial.
- **LOW-3:** four `EventBus` implementations (`automation.py:37`,
  `session_contracts.py:166`, `backend_events.py:1140`, `d3_backend.py:632`);
  only `automation.EventBus` is used at runtime.

### Explicitly checked and NOT defects

- No HIGH-severity integration defect confirmed in the audited call graph.
- No descriptor-only stub; no fake-success workflow step.
- The historical HIGH-1 "workflows skip policy/audit" is **closed** at this HEAD
  (`backend_workflows.py:1547-1617`).
- The spurious `UnicodeEncodeError` seen in one probe location was caused by a
  foreign `select.py` in a shared temp directory, not by this repository.

---

## 10. Reproduction commands

```powershell
# from worktree root
python scripts/verify_backend_operation.py --strict
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_backend_hub_integration.py','keel/tests/test_backend_workflows.py','keel/tests/test_backend_contracts.py','keel/tests/test_backend_contracts_hardening.py','keel/tests/test_backend_events.py','keel/tests/test_backend_observability.py']))"
python keel/src/../scripts/.. # (probes in C:\Users\Admin\AppData\Local\Temp\opencode\integrate-probe\)
```

Probe scripts (kept outside the worktree):
`analyze_backends.py`, `callgraph.py`, `module_detail.py` (in
`%TEMP%\opencode\`), and `probe_real.py`, `probe_workflows.py` (in
`%TEMP%\opencode\integrate-probe\`). Outputs: `backend_analysis.json`,
`callgraph.json`, `module_detail.json`, `probe_out2.txt`, `wf_out.txt`,
`detail_out.txt`, `gate.txt`, `tests.txt`, `cli_desc.txt`.

## 11. Limitations

- Static analysis is AST-based; dynamic `getattr`/`import_module` targets were cross-
  checked against the live hub (`assert_dispatch_targets()` passed).
- Five modules were exercised with real probes; the remaining 15 were verified by
  structural/AST evidence, registry gate, dispatch-target validation and tests —
  not by one probe per module.
- No live provider credentials, native cross-platform runner, or signed clean-VM
  checks were available; those remain external gates and are outside this audit.
