# Stabilization Performance & Resource Evidence (read-only measurement)

Branch `agent/stab-perf` · Measured tree `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb` (2026-11-25 01:58:27 +0100)
Worktree `C:\Users\Admin\.local\share\opencode\worktree\stab\perf`

**No production source was edited.** `git status` was clean before and after measurement.
Harness copies and raw JSON are in `perf-harness/stab/` and `perf-harness/stab-results/`.
Every number below was measured on this tree; none are invented or carried over without
an explicit label. All targets are **PROPOSED** engineering goals, **not owner-approved**.

---

## 1. Environment (captured before measurement)

```
OS            Microsoft Windows 11 Pro, 10.0.26300, build 26300, 64-bit
CPU           AMD Ryzen 7 5700U with Radeon Graphics; 8 cores / 16 logical; 1801 MHz
RAM           14,870,306,816 bytes (13.85 GiB); 14,521,784 KB visible at capture
Disk          WD PC SN740 SDDPMQD-512G-1101, 512,110,190,592 bytes (NVMe SSD)
Python        3.11.9, C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
              (tags/v3.11.9:de54cf5, MSC v.1938 64 bit AMD64)
Platform      Windows-10-10.0.26300-SP0
Packages      fastapi 0.142.4, uvicorn 0.54.0, starlette 1.7.0, pydantic 2.13.5,
              sqlalchemy 2.0.20, httpx 0.28.1, aiohttp 3.14.4, anyio 4.15.1,
              pytest 9.0.2, gunicorn 23.0.0; psutil NOT INSTALLED
```

RSS is Win32 `psapi.GetProcessMemoryInfo` `WorkingSetSize` via `ctypes`
(`benchcommon.py`); CPU is `time.process_time()`. No CPU pinning, no isolated host —
other Python processes from other sessions were present. Measurements are directional,
not contractual. SQLite ran on the real SSD; HTTP on loopback.

## 2. Method / exact commands

The existing `perf-harness/` scripts were copied to
`C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf`, with hard-coded paths rewritten
to this worktree's `keel/src`; new scripts were written there for the extra checks.
Every script asserts/uses `C:\Users\Admin\.local\share\opencode\worktree\stab\perf\keel\src`
at `sys.path[0]`, so `keel` resolves to the measured tree (verified by `probe.py`:
`keel.__file__ = ...\worktree\stab\perf\keel\src\keel\__init__.py`). `-P` avoids a
stray `select.py` shadowing the stdlib in the parent temp directory.

```
cd C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf
python -P probe.py
python -P import_breakdown.py
python -P per_module.py
python -P -X importtime imp.py 2> importtime.log
python -P bench_startup.py
python -P bench_cap.py
python -P bench_http.py
python -P bench_backlog_verify.py
python -P bench_db.py
python -P bench_resilience.py
python -P bench_first_call.py
python -P bench_workflows.py
python -P bench_races.py          # first run hung on a harness barrier bug; fixed, rerun
python -P bench_bounds.py
python -P bench_ledger_scaling.py
python -P verify_fixes.py
```

Environment capture (PowerShell):
```
(Get-CimInstance Win32_OperatingSystem) | Select-Object Caption,Version,BuildNumber,OSArchitecture
(Get-CimInstance Win32_Processor) | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
Get-PhysicalDisk | Select-Object FriendlyName,MediaType,Size
python --version
python -c "import importlib.metadata as m; ..."
git status --short --branch; git rev-parse HEAD
```

Startup = median of 7 fresh `python -P` subprocesses; child self-times the import,
prints `READY`, then exits; shutdown = READY→exit (includes interpreter finalization).
All other scenarios are single runs. Percentiles use linear interpolation
(`benchcommon.percentile`, NumPy default method).

### Prior baseline used only for comparison (different candidate, not re-measured here)

`PROD-PERFORMANCE-EVIDENCE.md` on candidate `e6e7efc` reported cold `keel.capabilities`
import 3,194 ms, full runtime 3,568 ms, HTTP `/api/health` p50 26.85 ms, 23/2,000
connection refusals under burst, and 13/16 duplicate-bot failures. Those numbers are
cited as historical context only; the numbers in §3–§8 are this tree's measurements.

---

## 3. Headline numbers (this tree, measured)

| Metric | Measured |
|---|---|
| Cold import `keel` package | 4.03 ms (7 runs) |
| Cold import `keel.backend_hub` | 98.46 ms |
| Cold import all 20 backend modules | 1,569.69 ms (separate single-run cold imports: 3,613.61 ms) |
| Cold import `keel.capabilities` | 174.05 ms (min 131.44 / max 306.14) |
| Cold import full runtime set | 815.59 ms (min 777.95 / max 1,617.58) |
| Full-runtime cold process (interpreter+import+exit) | 1,707.91 ms |
| Shutdown (READY→exit), bare interpreter / full runtime | 38.02 / 125.21 ms |
| **First real `backend.modules` call in a cold process** | **1,569.68 ms p50** (cost moved from import to first use) |
| HTTP `/api/health`, single client, p50/p95/p99 | 3.15 / 4.19 / 18.25 ms |
| HTTP mixed, 8 clients × 100, p50/p95/p99 | 40.34 / 75.92 / 101.27 ms; 0 errors |
| HTTP mixed, 32 clients × 100, p50/p95/p99 | 157.06 / 369.40 / 423.62 ms; 0 errors |
| HTTP burst, 100 clients × 20, p50/p95/p99 | 654.67 / 1,126.11 / 1,344.02 ms; **0 refusals** |
| Burst refusals: control backlog 5 / current `make_server` backlog 128 | 22/2,000 / **0/2,000** |
| `FleetStore.append_row` single, p50/p95/p99 | 1.24 / 2.32 / 12.97 ms |
| `append_row` 32 separate connections, p99 | 1,523.42 ms (0 errors) |
| Ephemeral event `publish()` with 4 subscribers | 32,471 events/s |
| Restart recovery, 100 pending approvals + 100 running tasks | 660.34 ms; 100/100 asks interrupted |
| Concurrent same-name bot creation, 32 threads | 32/32 succeeded, 32 distinct IDs, 0 errors |
| Duplicate workflow submission, 16 threads, same key | 1 winner / 15 `replay_denied` / 1 ledger record |
| Cap under 8-thread race | 4 granted / cap 4, respected |
| Sustained 22k ops RSS delta / tracemalloc peak | +1,458,176 B / 158,571 B |
| **Workflow ledger growth: first-50 → last-50 p50 over 300 calls** | **112.50 ms → 642.34 ms** (1.1 MB ledger) |
| **Steering retention, 20k undrained messages** | **20,000 retained, +6,328,320 B RSS** (no cap) |

**Production-significant findings:** (1) per-call O(n) workflow ledger verification
(§9.1); (2) unbounded steering message retention (§9.2); (3) ~1.57 s first backend
capability call in a cold process (§9.3); (4) 32-connection SQLite p99 1.52 s (§9.5);
(5) timed-out routine workers keep running (§9.6). Fixes previously reported are all
still present (§8).

---

## 4. Startup / import / shutdown

`result_startup.json` — import is child-self-timed, 7 fresh processes per mode:

| Mode | import p50 | import min / max | shutdown p50 | total process p50 | modules loaded |
|---|---|---|---|---|---|
| none (baseline) | 0.002 ms | 0.001 / 0.002 | 38.02 ms | 344.32 ms | 96 |
| `keel` | 4.03 ms | 2.96 / 4.45 | 34.41 ms | 325.56 ms | 97 |
| `keel.backend_hub` | 98.46 ms | 75.98 / 152.34 | 56.31 ms | 476.09 ms | 115 |
| all 20 backend modules | 1,569.69 ms | 1,347.88 / 2,162.97 | 155.00 ms | 2,000.75 ms | 224 |
| `keel.capabilities` | 174.05 ms | 131.44 / 306.14 | 74.41 ms | 729.55 ms | 121 |
| `keel.webapp` | 971.55 ms | 731.67 / 2,305.48 | 119.15 ms | 1,536.38 ms | 254 |
| full runtime set¹ | 815.59 ms | 777.95 / 1,617.58 | 125.21 ms | 1,707.91 ms | 266 |

¹ capabilities + webapp + fleet.service + fleet.routes + events + runner +
resource_caps + resource_limits + resilience + fleet.scheduler. Its median is lower
than `webapp`'s because of run-to-run variance (webapp max 2,305 ms); both are single
populations of 7, no confidence intervals.

Diagnostics:

- `probe.py`: `keel` import 3.871 ms; `capabilities` import 296.816 ms; `backend_hub`
  import 0.073 ms after capabilities; 20 modules, 421 feature IDs, 144 function
  schemas, 4 registered capabilities; 216 modules in `sys.modules`.
- `import_breakdown.py`: cold 20-module import 3,613.61 ms; hub import after those
  modules 44.68 ms; schema recompute 73.42 ms for 144 schemas; cached
  `assert_dispatch_targets()` 2.41 ms; cached `sync_capability_schemas()` 0.20 ms.
  ⇒ schema derivation is not the cost; the 20 module bodies and their stdlib
  dependencies are.
- `per_module.py` (one cold import each, ms): d3 366.11, d6 222.30, d7 115.98,
  e3 261.16, e5 71.80, e6 187.08, e7 268.98, small_groups 169.98, v_series 220.96,
  w1 150.54, **w4 417.19**, w7 108.58, x2 155.44, x3 219.92, x8 269.23,
  y1 184.64, y2 250.43, y3 223.66, y4 206.12, z 146.82.
- `-X importtime` top cumulative lines: `keel.capabilities` 124.38 ms,
  `site` 199.89 ms, `__editable___apl_lang_0_1_0_finder` 156.73 ms,
  `pathlib` 67.60 ms, `dataclasses` 64.65 ms, `inspect` 47.92 ms,
  `urllib.parse` 19.43 ms, `keel.backend_hub` 14.27 ms.
  The editable-install finder and stdlib dominate the remaining ~174 ms; the
  backends are no longer imported at startup.

Warm in-process dispatch (`result_cap.json`, 1,000 iterations each):
`caps.invoke("backend.modules")` p50/p95/p99 = 0.761/2.501/4.986 ms;
`backend.describe` 0.676/1.986/3.787 ms; `backend.invoke` 0.610/1.051/1.437 ms;
`hub.invoke` 0.133/0.302/0.601 ms; `hub.describe()` 1.903/2.776/3.232 ms;
`hub.sync_capability_schemas()` 0.086/0.131/0.165 ms.

---

## 5. HTTP latency, failures, listen backlog

Real `keel.webapp.make_server(0)` (`ThreadingHTTPServer` subclass), token `benchtoken`
via `KEEL_TOKEN`, real fleet store on a temp DB (20 bots, 50 tasks). Each client
request opens a fresh HTTP/1.0 TCP connection (server default), so connect time is
included. `result_http.json`:

| Endpoint, 200 sequential requests | min | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| `/api/health` | 1.75 | 3.15 | 4.19 | 18.25 | 19.20 ms |
| `/api/providers` | 6.74 | 9.99 | 13.31 | 26.36 | 29.40 ms |
| `/api/fleet/bots` | 2.72 | 4.51 | 5.96 | 13.50 | 20.74 ms |
| `/api/fleet/tasks` | 3.33 | 5.55 | 7.99 | 22.38 | 24.98 ms |
| unauthorized `/api/health` (100 requests, all 403) | 3.21 | 4.51 | 6.58 | 7.60 | 20.23 ms |

| Scenario | requests | ok | failed | req/s | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|
| normal, 8 threads × 100 | 800 | 800 | 0 | 193.6 | 40.34 | 75.92 | 101.27 ms |
| increased, 32 threads × 100 | 3,200 | 3,200 | 0 | 196.0 | 157.06 | 369.40 | 423.62 ms |
| burst, 100 threads × 20 | 2,000 | 2,000 | 0 | 155.4 | 654.67 | 1,126.11 | 1,344.02 ms |

Burst A/B (`result_backlog_verify.json`, same handler, 100 threads × 20 requests):

| Server | `request_queue_size` | ok | failed | req/s | p50 | p99 |
|---|---|---|---|---|---|---|
| control `ThreadingHTTPServer` subclass | 5 | 1,978 | **22** | 231.8 | 18.00 | 1,698.13 ms |
| **current `webapp.make_server()`** | 128 | 2,000 | **0** | 164.0 | 496.50 | 1,194.89 ms |
| explicit 128 subclass (reference) | 128 | 2,000 | **0** | 201.0 | 417.87 | 1,022.00 ms |

No handler errors occurred in any scenario; all responses were 200/403 as expected.
The backlog fix removes refusals, but burst latency remains high (p50 ≈ 655 ms with
100 concurrent clients) — a queueing/handler-thread effect, not connection failure.

---

## 6. Concurrent workflows, sessions/tasks, workers

`result_workflows.json` — five real backend workflow types (`WORKFLOW_NAMES =
("request", "approval", "delegation", "mcp", "recovery")`), each call given a distinct
state-root subdirectory and idempotency key; 8 threads × 2 calls per type. `mcp` is an
honest dry run and intentionally returns `code="dry_run"`.

| Workflow | single call | concurrent calls/s (8×2) | p50 / p99 (ms) | codes | exceptions |
|---|---|---|---|---|---|
| request | 511.78 ms (ok) | 24.40 | 237.32 / 451.95 | 16 ok | 0 |
| approval | 296.63 ms (ok) | 14.40 | 444.94 / 588.78 | 16 ok | 0 |
| delegation | 780.03 ms (ok) | 8.70 | 893.12 / 958.93 | 16 ok | 0 |
| mcp | 395.82 ms (dry_run) | 15.40 | 491.91 / 569.54 | 16 dry_run | 0 |
| recovery | 169.09 ms (ok) | 20.40 | 371.95 / 413.22 | 16 ok | 0 |

Worker budget (`d7.effective_workers`, in-process): local 16 CPUs / cap 8 → 8 workers;
CI 16 CPUs / cap 8 → 16; CI 16 CPUs + cgroup 2.5 → 2; local 1 CPU + cgroup 0.5 → 1.
Delegation is the subprocess-producing workflow; its 8-thread throughput is
8.70 completed workflows/s (16 child processes per batch in these runs).

Concurrent sessions/tasks (`result_resilience.json`, 16 threads × 20 each): 320 bots +
320 tasks created, 0 errors, 2.527 s, 253.2 ops/s.

Duplicate submission (`result_races.json`, 16 threads, identical MCP params + key):
`dry_run` 1, `replay_denied` 15, 0 exceptions, exactly 1 ledger record — the
cross-process lock and idempotency guard hold.

---

## 7. SQLite writes, events, memory/CPU, recovery, limits

`result_db.json`:

| Scenario | p50 | p95 | p99 | throughput |
|---|---|---|---|---|
| `append_row` single thread (2,000 writes) | 1.24 ms | 2.32 ms | 12.97 ms | 596.8 writes/s (sum of latencies), 601.8 ev/s wall clock |
| `insert_usage` single thread (1,000) | 1.19 ms | — | 8.35 ms | — |
| shared store, 8 threads × 500 | 10.56 ms | — | 31.22 ms | 649.4 writes/s, 0 errors |
| shared store, 32 threads × 200 | 49.21 ms | — | 200.15 ms | 605.5 writes/s, 0 errors |
| 8 separate connections, same DB, 200 each | 1.24 ms | — | 244.37 ms | 513.2 writes/s, 0 errors |
| 32 separate connections, same DB, 200 each | 1.23 ms | — | **1,523.42 ms** | 566.1 writes/s, 0 errors |

Event throughput: DB-backed `append_row` with 0/4/16 subscribers = 601.8 / 664.5 /
599.7 events/s; ephemeral `publish()` with 4 subscribers (20,000 events) = 32,471
events/s. Slow subscriber queue stayed capped at 256/256 (drop-oldest works).

Sustained mixed workload (20,000 `append_row` + 2,000 `publish`, 4 subscribers):
40.914 s wall, 27.0 s process CPU (ratio 0.66 ≈ single-core bound), RSS
30,605,312 → 32,063,488 bytes (**+1,458,176 B**), tracemalloc current 142,901 B /
peak 158,571 B — no unbounded Python allocation in this path.

Recovery / failure / limits (`result_resilience.json`, `result_races.json`):

| Test | Measured |
|---|---|
| `ResourceMeter` cap 4, 8 threads × 200 acquires | 4 granted, final used 4, cap respected, 0.079 s |
| `ResourceMeter.acquire`+`release` × 20,000 | p50 0.002 ms |
| `ResourceManager`, 16 threads × 20 tabs + workspace | 8 tabs / 8 denied (limit 8), workspace 1,000,000/1,048,576 B, 11 denials |
| Same-name bot creation, 16 / 32 threads | 16/16 and 32/32 succeeded, distinct IDs, 0 `IntegrityError` |
| `chat_for_project`, 8 threads | 8 succeeded, **1 bot** for the project |
| Restart recovery, 1 pending item | 24.55 ms; 1/1 approval expired, ask interrupted, run/task failed, routine released |
| Restart recovery, 100 pending items | 660.34 ms; 100/100 each for approvals, asks, runs, tasks, routines |
| Slow provider (2 s simulated turn, 0.4 s timeout) | 428.3 ms, `routine timed out after 0s`, state finalized as failed |
| Worker failure (`execute_turn` raises) | 26.3 ms, `internal_error`, state finalized as failed |
| DB write with 0.3 s exclusive lock held elsewhere | 259.3 ms write latency |

Steering cancel race (`result_races.json`, 8 submitters × 200 + concurrent aborts):
1,600 submitted, 1,600 retained in `all_messages`, 1,600 retained in queues, 1 abort,
0 exceptions — no message lost under this race.

Recursion/resource bounds (`result_bounds.json`, `result_races.json`):
`tool_contracts.to_jsonable` accepts depth 10, rejects depth 50 / 200 / 1000 with
`ToolError: ARGS_RESOURCE_LIMIT`; 20,000-node input rejected; 100,000-char string
accepted (the configured `MAX_STRING_CHARS` is 100,000, so this is the boundary, not
a bypass). HTTP `_json_body` bounds `Content-Length`, drains oversized bodies, and
catches `RecursionError` from `json.loads` (`webapp.py:355-408`).

---

## 8. Verification of the four previously reported fixes

`result_fix_verify.json`, `result_backlog_verify.json`, `result_resilience.json`,
`result_races.json`. Source read-only; behavior measured in fresh processes.

| Fix | Verification on this tree | Status |
|---|---|---|
| Lazy hub import | Fresh process: 0 `*_backend` modules after `import keel.capabilities`; exactly 20 after first `caps.invoke("backend.describe", ...)`. Fresh `import keel.backend_hub`: 0 backend modules; 20 after first `hub.describe()`; `_INITIALIZED=True`. Cold `capabilities` import 174.05 ms vs 3,194 ms historical. Source `backend_hub.py:342-404` (`_ensure_initialized` at :385) and `capabilities.py:213`. | **Holds** |
| Bot-create lock | 16 threads: 16 successes / 0 errors / 16 distinct IDs; 32 threads: 32/32 successes / 0 errors / 32 distinct IDs. `chat_for_project` 8 threads: 1 bot. Source `fleet/service.py:197-215`, `:471-493`. | **Holds** |
| Ask expiry | Direct `expire_pending_asks()` turns `{"status":"pending"}` into `{"status":"interrupted"}`. Restart recovery: 1/1 and 100/100 asks interrupted, 0 still pending. Source `fleet/service.py:99-124` uses `json_extract(body,'$.status')='pending'` at :106. | **Holds** |
| Backlog 128 | `make_server()` returns `_KeelThreadingHTTPServer` (`request_queue_size=128`, `daemon_threads=True`, `webapp.py:280-288`, returned at :1449). Under 100×20 burst: 0/2,000 refusals; control queue 5: 22/2,000. | **Holds** |

Note: the lazy-import fix *moves* ~1.57 s of work to the first real backend call
(§9.3); it does not remove it.

---

## 9. Bottlenecks and production-significant defects

Paths are relative to `keel/src/keel/`. Nothing here was fixed by this agent.

### 9.1 BLOCKING / PRODUCTION-SIGNIFICANT — workflow ledger verification is O(n) per call

- `backend_workflows.py:394-437` `_read_jsonl()` reads and HMAC-verifies **every**
  ledger record (`:400` full-file read, `:406-435` per-record loop, `:436` chain head).
  It is called on **every** workflow invocation in `_execution` (`:486-513`, scan at
  `:493`) and again in `_finalize` (`:602-619`, scan at `:611`).
- Measured with the real `request` workflow, 300 unique keys to one state root
  (`result_ledger_scaling.json`): ledger 1,105,097 B; first-50 p50 **112.50 ms**,
  middle-50 p50 **272.67 ms**, last-50 p50 **642.34 ms**, last-50 p95 831.31 ms,
  overall p50 282.75 ms / p99 863.21 ms. A trivial workflow becomes ~5.7× slower
  purely due to ledger growth.
- Consequence: latency grows without bound for any long-lived deployment using the
  workflow surface; 1,000 historical records would imply multiple seconds per call.
- **Recommended (not implemented):** keep an in-process idempotency index keyed by
  `(ledger path, idempotency key)` with a bounded LRU; verify only appended records
  incrementally and verify full-chain integrity out-of-band/at startup; avoid the
  second full scan in `_finalize` by returning the persisted sequence from `_execute`.

### 9.2 PRODUCTION-SIGNIFICANT — unbounded steering-message retention

- `steering.py:105-116` allocates `_queued`, `_boundary`, `_resume_pending`,
  `_delivered` as unbounded `deque()` and `_all` as a plain list; `:194-222`
  `submit_message()` appends to `_all` and to a routing deque on every call with no
  cap or eviction. `drain_queue()` (`:238-243`) only clears `_queued` when a caller
  drains; nothing bounds the other collections.
- Measured (`result_bounds.json`): 20,000 undrained `QUEUE` messages → 20,000 in
  `all_messages`, 20,000 in `queued`, RSS +6,328,320 B, tracemalloc peak 5,741,538 B
  in 0.769 s. Extrapolates linearly; a long-running session receiving steering
  messages without a consumer grows memory without limit.
- **Recommended (not implemented):** per-controller caps with explicit overflow code,
  or ring buffers for delivered/history plus a bounded pending queue.

### 9.3 HIGH — cold first backend capability call costs ~1.57 s

- `capabilities.py:213` still registers `backend.*` capabilities at import, but their
  handlers (`:192-208`) delegate to `backend_hub`; the first public hub call runs
  `_ensure_initialized()` (`backend_hub.py:385-404`), whose
  `assert_dispatch_targets()` (`:342-365`) imports all 20 modules under a lock.
- Measured (`result_first_call.json`, 7 fresh processes): cold `capabilities` import
  p50 101.51 ms; first `caps.invoke("backend.modules")` **1,569.68 ms p50**
  (1,260.17–2,187.39 ms); subsequent `backend.describe` 0.672 ms and
  `backend.invoke` 0.838 ms p50. A first HTTP request that calls `backend.modules`
  stalls ~1.6 s (serialized across concurrent first callers by `_INIT_LOCK`).
- **Recommended (not implemented):** pre-warm the hub on a background thread after
  startup, or lazily validate only the module actually invoked while running full
  validation asynchronously; keep fail-closed semantics before dispatch.

### 9.4 HIGH — HTTP burst queueing despite zero refusals

- `webapp.py:280-288` fixes listen backlog, but `make_server()` (`:291`, returned at
  `:1449`) uses one thread per connection with no concurrency cap.
- Measured: 100-client burst p50 654.67 ms / p99 1,344.02 ms; controlled backlog-128
  server p50 496.50 ms / p99 1,194.89 ms; 8- and 32-client p95 75.92 / 369.40 ms.
  The handler itself is cheap (single-client `/api/health` p50 3.15 ms), so the tail
  is scheduler/connection queueing plus per-request token/origin checks.
- **Recommended (not implemented):** bounded worker pool / keep-alive, connection
  throttling, and measure with HTTP/1.1 persistent connections before tuning.

### 9.5 HIGH — SQLite write tail under multi-connection contention

- `fleet/db.py:250` `timeout=30`; `:252` WAL but no `synchronous=NORMAL`, so
  default `FULL` fsyncs each commit. `fleet/service.py:641-662` `append_row` performs
  INSERT + UPDATE + COMMIT per event under the store lock; `insert_usage` at `:790`.
- Measured: single p99 12.97 ms; shared store 32-thread p50 49.21 ms / p99 200.15 ms;
  32 separate connections p99 1,523.42 ms; 300 ms foreign exclusive lock → 259.3 ms
  write. Sustained workload CPU ratio 0.66 (single-core-ish).
- **Recommended (not implemented):** `PRAGMA synchronous=NORMAL`, group/batch commits,
  single writer queue per process; keep WAL and idempotency semantics.

### 9.6 MEDIUM — timed-out routine workers are not cancelled

- `fleet/scheduler.py:229-237` starts a daemon worker, `join(timeout)`, and on timeout
  returns without stopping the worker; `:236` formats `int(timeout)`, so a 0.4 s
  timeout is reported as "routine timed out after 0s".
- Measured (`result_races.json`): 5 consecutive 0.4 s timeouts against a 2 s simulated
  provider left 1, 2, 3, 4, 4 live `fleet-routine-*` threads immediately after the
  calls returned (all eventually exited after ~2.3 s). Under repeated slow providers
  these accumulate.
- **Recommended (not implemented):** cooperative stop flag/executor with cancellation;
  report the real timeout value.

### 9.7 MEDIUM — recovery is correct but not batched

- Restart recovery touches each pending item in its own transaction path
  (`fleet/service.py:99-124` and restart logic above it).
- Measured: 100 pending items → 660.34 ms (1 item → 24.55 ms). All 100 approvals,
  asks, runs, tasks and routines were finalized correctly, so this is throughput, not
  correctness.

---

## 10. Derived operational targets — **PROPOSED, not owner-approved**

| Area | Measured (this tree) | **PROPOSED** target | Rationale |
|---|---|---|---|
| Cold `capabilities` import | 174.05 ms | ≤ 200 ms | Meets target today |
| Cold full runtime import | 815.59 ms | ≤ 800 ms | Marginal; editable finder + stdlib dominate |
| Cold full process | 1,707.91 ms | ≤ 1,200 ms | Need ~0.5 s off webapp/stdlib imports |
| First backend capability call (cold) | 1,569.68 ms | ≤ 200 ms | Pre-warm / partial lazy validation |
| Shutdown after full runtime | 125.21 ms | ≤ 150 ms | Meets target today (interpreter-bound) |
| Single-client `/api/health` p95 | 4.19 ms | ≤ 10 ms | Meets target today |
| 8-client mixed p95 / p99 | 75.92 / 101.27 ms | ≤ 100 / ≤ 200 ms | Meets proposed p95 today |
| 32-client mixed p95 / p99 | 369.40 / 423.62 ms | ≤ 200 / ≤ 400 ms | Needs handler/concurrency tuning |
| 100-client burst p95 / p99 | 1,126 / 1,344 ms | ≤ 500 / ≤ 800 ms | Bounded worker pool / keep-alive |
| Connection refusals under burst | 0/2,000 | 0 | Meets target today |
| `append_row` single p99 | 12.97 ms | ≤ 5 ms | Batch commits / `synchronous=NORMAL` |
| `append_row` 32-connection p99 | 1,523.42 ms | ≤ 100 ms | Single-writer queue |
| DB-backed event throughput | 600–665 ev/s | ≥ 1,000 ev/s | Batch commits |
| Ephemeral publish throughput | 32,471 ev/s | ≥ 20,000 ev/s | Meets target today |
| Workflow call latency after 300 ledger records | 642.34 ms | ≤ 100 ms | Indexed idempotency / incremental chain check |
| Steering retention, 20k undrained messages | 20,000 retained | bounded (≤ 1,000) + explicit overflow | Cap queues/history |
| Restart recovery, 100 items | 660.34 ms | ≤ 100 ms | Batch recovery transaction |
| Timed-out workers still alive immediately after timeout | up to 4 | 0 | Cooperative cancellation |
| RSS growth over 22k DB ops | +1,458,176 B | ≤ 10 MB | Meets target today |
| Warm capability `invoke` p99 | ~5 ms (`backend.modules`) | ≤ 5 ms | Marginal; measure after pre-warm |

---

## 11. What passed / worked correctly

- All four previously reported fixes hold on this tree (§8).
- Startup: `keel.capabilities` import fell from ~3.2 s (historical) to 174 ms; no
  backend module is imported at startup.
- HTTP: zero connection refusals and zero handler errors in 8-, 32- and 100-client
  scenarios.
- All five workflow types complete concurrently with correct codes and zero exceptions;
  idempotency guard yields exactly one winner for 16 duplicate submissions.
- Resource caps and manager limits enforced under 16–32-thread races; same-name bot
  creation and project chat creation are race-free.
- Restart recovery finalizes approvals, asks, runs, tasks and routines 100/100 in
  660 ms; timeout and worker-failure paths finalize state correctly.
- Event fan-out bounded (256/256 slow subscriber); memory bounded over 22k mixed ops;
  tool-argument depth/node limits reject hostile input; HTTP body/recursion guards
  present.
- Warm backend dispatch is sub-millisecond for most calls.

---

## 12. Limitations / threats to validity

1. Single developer laptop, shared with other processes; no CPU pinning, no isolated
   machine. Most scenarios are single runs; only startup has 7 repeats. Re-run before
   treating any number as an SLA.
2. HTTP latency includes a fresh TCP connect per request (HTTP/1.0 default), so
   absolute values are client-methodology-inflated; the backlog A/B is the
   load-bearing HTTP finding.
3. `psutil` unavailable: RSS is Win32 `WorkingSetSize` (includes shared pages), not
   precise private RSS; CPU is whole-process `time.process_time()`.
4. No real LLM provider was called. Slow provider and worker failure were simulated
   by monkeypatching `turn_core.execute_turn` **in the benchmark process only**; source
   was not edited and the original callable was restored.
5. No multi-process/multi-worker HTTP deployment, no external network, no large
   uploads, no long-lived SSE soak beyond the 256-frame queue bound.
6. Shutdown timing includes interpreter finalization; keel registers no measured
   atexit teardown cost.
7. The first version of `bench_races.py` hung because of a harness bug (barrier
   parties = 8 while 9 threads called `wait()`); it was fixed and rerun. Only the
   successful rerun's `result_races.json` is preserved.
8. The workflow ledger scaling measurement uses 300 calls in one process; the
   extrapolation to 1,000 records is reasoning from the measured trend, not a
   separate measurement.

---

## 13. Raw artifacts

All raw JSON from this tree is preserved in `perf-harness/stab-results/`:
`result_startup.json`, `result_cap.json`, `result_http.json`,
`result_backlog_verify.json`, `result_db.json`, `result_resilience.json`,
`result_first_call.json`, `result_workflows.json`, `result_races.json`,
`result_bounds.json`, `result_ledger_scaling.json`, `result_fix_verify.json`.
The exact scripts used (including the path-rewritten copies of the original harness)
are in `perf-harness/stab/`. `importtime.log` was captured in the temp run directory;
its top lines are quoted in §4.
