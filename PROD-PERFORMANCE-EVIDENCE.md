# Production Performance & Load — Evidence (read-only measurement)

Branch: `agent/prod-perf` · Candidate HEAD: `e6e7efc50d098aaf55b80c5b35e799c0c2e25a86`
Worktree: `C:\Users\Admin\.local\share\opencode\worktree\production\perf`
Scope: startup/shutdown, HTTP latency, event throughput, SQLite write latency,
concurrent sessions/tasks, memory/CPU, failure recovery, slow provider,
DB contention, worker failure, resource-limit enforcement.

**No production source was edited.** Harness scripts and raw JSON are preserved
in `perf-harness/` (see `perf-harness/README.md`). All numbers below are
measured on this candidate; none are invented. All proposed targets are
labelled **PROPOSED** and are **not owner-approved**.

---

## 1. Headline numbers (measured)

| Metric | Measured (median unless noted) |
|---|---|
| Cold import `keel.capabilities` (hub + all 20 backends) | **3,194 ms** (7 runs, min 2,245 / max 4,644) |
| Cold import full runtime set (capabilities+webapp+fleet+events+runner+limits+resilience+scheduler) | **3,568 ms** (min 2,571 / max 8,342) |
| Cold import `keel.backend_hub` alone | **2,027 ms** |
| Cold import `keel` package alone | 5.4 ms |
| Full-runtime cold process (interpreter + import + exit) | **4,237 ms** |
| Shutdown (READY→exit) after full runtime import | 282 ms (bare interpreter baseline 44 ms) |
| HTTP GET `/api/health`, single client, p50 / p95 / p99 | 26.85 / 108.77 / 204.72 ms |
| HTTP mixed GET, 8 clients × 100, p50 / p95 / p99 | 107.43 / 695.28 / 1,247.23 ms |
| HTTP connection refusals, 100-client burst (default backlog) | **23 / 2,000 (1.15%)**; 0 with backlog 128 |
| `FleetStore.append_row` single-thread p50 / p95 / p99 | 1.26 / 2.01 / 11.54 ms (~675–724 writes/s) |
| `append_row` p99 with 32 separate DB connections | **1,202 ms** (no errors, but severe tail) |
| Ephemeral event `publish()` with 4 subscribers | 23,571 events/s |
| Restart recovery, 100 pending approvals + 100 running tasks | **723 ms** |
| Pending asks expired on restart | **0 / 100** (defect, see §6.3) |
| Concurrent same-name bot creation | **13 / 16 failed** with `IntegrityError` |
| Hard resource cap under 8-thread race | enforced 4/4 (correct) |

**Blocking performance issues:** (1) ~3.2–3.6 s cold startup from eager import of
all 20 backend modules; (2) duplicate-agent creation race under concurrency
(`IntegrityError`); (3) pending asks never expire on restart. Details and exact
file:line in §6.

---

## 2. Environment (recorded before any measurement)

```
OS            Microsoft Windows 11 Pro, 10.0.26300, build 26300, 64-bit
CPU           AMD Ryzen 7 5700U with Radeon Graphics; 8 cores / 16 logical; 1801 MHz
RAM           14,870,306,816 bytes (13.85 GiB)
Disk          WD PC SN740 SDDPMQD-512G-1101, 512,110,190,592 bytes (NVMe SSD)
Python        3.11.9, C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
Platform      Windows-10-10.0.26300-SP0, AMD64
Key packages  fastapi 0.142.4, uvicorn 0.54.0, starlette 1.7.0, pydantic 2.13.5,
              sqlalchemy 2.0.20, httpx 0.28.1, aiohttp 3.14.4, anyio 4.15.1,
              pytest 9.0.2, gunicorn 23.0.0; psutil NOT INSTALLED
```

RSS is obtained via Win32 `psapi.GetProcessMemoryInfo` (`WorkingSetSize`) through
`ctypes` (`perf-harness/benchcommon.py`, `memtest.py`); no psutil dependency.
`python -P -X importtime` was used for import attribution. `keel.__file__` was
verified to be the worktree copy
(`...\worktree\production\perf\keel\src\keel\__init__.py`) in every script; no
editable-install leak. Backend inventory verified: 20 modules, 421 feature IDs,
144 dispatchable function schemas, 4 registered backend capabilities.

No CPU affinity/pinning, no isolated machine, real file-system SQLite on the
OS SSD, loopback HTTP. Measurements are directional, not contractual.

---

## 3. Method & exact commands

All commands run from `C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf`
(the harness copy in the worktree is `perf-harness/`; see its README):

```
python -P probe.py
python -P -X importtime imp.py 2> importtime.log
python -P import_breakdown.py
python -P per_module.py
python -P bench_startup.py
python -P bench_http.py
python -P bench_http_backlog.py
python -P bench_db.py
python -P bench_cap.py
python -P bench_resilience.py
```

Environment capture commands (PowerShell):

```
(Get-CimInstance Win32_OperatingSystem) | Select-Object Caption, Version, BuildNumber, OSArchitecture
(Get-CimInstance Win32_Processor) | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed
(Get-CimInstance Win32_ComputerSystem) | Select-Object TotalPhysicalMemory
Get-PhysicalDisk | Select-Object FriendlyName, MediaType, Size
python --version
python -c "import importlib.metadata as m; ..."
```

Percentiles use linear interpolation (NumPy `percentile` method), implemented in
`benchcommon.percentile`. Startup = median of 7 fresh subprocesses; other
scenarios are single runs (see §8 limitation).

---

## 4. Raw results

### 4.1 Startup / import / shutdown (`result_startup.json`)

Each mode imported in a fresh `python -P` child; parent measures total process
time; child self-times the import and prints `READY` immediately before exit,
so shutdown = READY→process-exit (includes interpreter finalization).

| Mode | import p50 (ms) | import min/max | shutdown p50 (ms) | total process p50 (ms) | modules loaded |
|---|---|---|---|---|---|
| none (baseline) | 0.002 | 0.001/0.003 | 44.04 | 375.87 | 96 |
| `keel` | 5.44 | 3.54/11.12 | 54.23 | 470.10 | 97 |
| `keel.backend_hub` | **2,027.14** | 1,780.50/2,904.89 | 212.74 | 2,713.07 | 227 |
| `keel.capabilities` | **3,194.09** | 2,245.35/4,643.74 | 356.56 | 4,049.55 | 227 |
| `keel.webapp` | 1,796.30 | 1,052.72/2,471.04 | 178.65 | 2,546.42 | 254 |
| full runtime set | **3,568.06** | 2,570.66/8,341.61 | 282.46 | 4,236.53 | 310 |

Import-time attribution (`-X importtime`, `importtime.log`, top cumulative):

```
import time:     58468 |    3316378 | keel.capabilities
import time:   2172460 |    3044757 |   keel.backend_hub   <- self time = eager body
import time:     15283 |     762074 | site
import time:    83074 |     677297 |   __editable___apl_lang_0_1_0_finder
import time:      5207 |     297363 |     xml.sax.saxutils  <- w4_backend.py:44
import time:     15249 |     260944 |       urllib.request
import time:      ...
import time:     52132 |     110915 |         collections
import time:     64283 |      64283 |     keel.result_contracts
import time:     54651 |      54651 |     keel.builder_contracts
```

Per-module cold import (`per_module.py`, single run, ms):
d3 284.41, d6 127.38, d7 121.02, e3 153.24, e5 26.51, e6 110.56,
e7 211.19, small_groups 74.84, v_series 106.85, w1 62.01, **w4 452.00**,
w7 122.40, x2 54.44, x3 58.62, x8 160.43, **y1 311.59**, **y2 288.48**,
y3 71.91, y4 140.09, z 74.22. Sum ≈ 2.8 s.

`import_breakdown.py` (2 runs):
`import20_ms` 3,227 / 2,460; `hub_import_after20_ms` 105 / 208;
`schema_recompute_ms` 38.09 / 39.54 (144 schemas); `assert_cached_ms` 0.25;
`sync_cached_ms` 0.69/0.79.
⇒ The cost is importing the 20 modules and their heavy stdlib dependencies,
not the hub's schema derivation.

### 4.2 Capability/backend hub invocation (warm, in-process; `result_cap.json`)

| Call (1,000 iterations) | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| `caps.invoke("backend.modules")` | 0.314 | 0.746 | 1.093 |
| `caps.invoke("backend.describe")` | 0.339 | 0.840 | 1.223 |
| `caps.invoke("backend.invoke", e5.validate_app_id)` | 0.376 | 0.851 | 1.051 |
| `hub.invoke(e5.validate_app_id)` | 0.132 | 0.205 | 0.277 |
| `hub.describe()` (all modules) | 2.025 | 3.258 | 3.899 |
| `hub.sync_capability_schemas()` | 0.087 | 0.144 | 0.319 |

Warm in-process latency is sub-millisecond; the problem is cold process startup,
not steady-state dispatch.

### 4.3 HTTP endpoint latency (`result_http.json`)

Real `keel.webapp.make_server(0)` (`ThreadingHTTPServer`), token `benchtoken`
via `KEEL_TOKEN`, fleet store on a temp DB (20 bots, 50 tasks). Client opens a
fresh HTTP/1.0 TCP connection per request on Windows loopback → ~5 ms floor
(min observed 4.91–5.14 ms). Percentiles in ms.

| Endpoint, 200 sequential requests | min | p50 | p95 | p99 | max | mean |
|---|---|---|---|---|---|---|
| `/api/health` | 5.07 | 26.85 | 108.77 | 204.72 | 291.49 | 37.56 |
| `/api/providers` | 11.55 | 30.47 | 197.02 | 287.98 | 556.20 | 55.57 |
| `/api/fleet/bots` | 4.91 | 14.64 | 120.87 | 204.36 | 258.37 | 31.55 |
| `/api/fleet/tasks` | 5.14 | 19.72 | 85.34 | 118.33 | 183.45 | 30.09 |
| unauthorized `/api/health` (403) | — | 6.89 | — | — | — | — |

| Scenario | requests | ok | failed | req/s | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|
| normal, 8 threads × 100 | 800 | 799 | 1 | 39.8 | 107.43 | 695.28 | 1,247.23 |
| increased, 32 × 100 | 3,200 | 2,997 | 203 | 61.1 | 129.96 | 2,036.84 | 2,186.11 |
| burst, 100 × 20 | 2,000 | 1,355 | 645 | 73.7 | 1,262.24 | 2,104.39 | 2,295.78 |

Failures are `ConnectionRefusedError: [WinError 10061]` — listen backlog
exhaustion, not handler errors. All received responses were 200/403 as expected.

Backlog A/B (`result_backlog.json`, same handler, 100 threads × 20 requests):

| Server | queue size | ok | failed | req/s | p50 | p99 |
|---|---|---|---|---|---|---|
| default `ThreadingHTTPServer` | 5 | 1,977 | **23** | 246.8 | 19.45 | 1,672.92 |
| subclass `request_queue_size=128` | 128 | 2,000 | **0** | 272.1 | 326.01 | 684.70 |

### 4.4 SQLite writes, events, memory/CPU (`result_db.json`)

| Scenario | p50 | p95 | p99 | throughput |
|---|---|---|---|---|
| `append_row` single thread (2,000 writes) | 1.26 ms | 2.01 ms | 11.54 ms | 675.5 writes/s (sum of latencies); 724.4 ev/s wall-clock |
| `insert_usage` single thread (1,000) | 1.22 ms | 1.84 ms | 2.94 ms | — |
| shared store, 8 threads × 500 | 10.68 ms | 30.22 ms | 61.51 ms | 567.4 writes/s, 0 errors |
| shared store, 32 threads × 200 | 46.61 ms | 93.92 ms | 137.40 ms | 638.3 writes/s, 0 errors |
| 8 separate connections, same DB, 200 each | 1.25 ms | 2.21 ms | 129.54 ms | 733.9 writes/s, 0 errors |
| 32 separate connections, same DB, 200 each | 1.27 ms | 10.14 ms | **1,202.01 ms** | 653.5 writes/s, 0 errors |

| Event metric | Measured |
|---|---|
| `append_row` + 0 subscribers (3,000 events) | 724.4 events/s (1.381 ms/event) |
| `append_row` + 4 subscribers | 708.1 events/s (1.412 ms/event) |
| `append_row` + 16 subscribers | 654.9 events/s (1.527 ms/event) |
| Ephemeral `publish()` + 4 subscribers (20,000) | 23,571.4 events/s |
| Slow subscriber (never drained, 1,000 published) | queue capped at 256/256 (drop-oldest works) |

Sustained mixed workload (20,000 `append_row` + 2,000 `publish`, 4 subscribers):
elapsed 41.174 s, process CPU 30.594 s (CPU ratio 0.743 ≈ single-core bound),
RSS 29,913,088 → 31,756,288 bytes (**+1,843,200 B**), tracemalloc current
151,429 B / peak 167,099 B — no unbounded Python allocation observed.

### 4.5 Resource limits, concurrency, recovery, failure (`result_resilience.json`)

| Test | Measured |
|---|---|
| `ResourceMeter` cap=4, 8 threads × 200 acquires | granted **4**, final used 4, cap respected; 0.049 s |
| `ResourceMeter.acquire`+`release` × 20,000 | p50 0.002 ms |
| `ResourceManager` 16 threads × 20 tabs + workspace | 8 tabs opened / 8 denied (limit 8 respected); workspace 1,000,000 / 1,048,576 B, 11 denials |
| Concurrent sessions/tasks, 16 threads × 20 each | 320 bots + 320 tasks created, 0 errors, 239.4 ops/s, 2.673 s |
| Same-name bot creation, 16 threads | **7 succeeded / 13 `IntegrityError`** — see §6.2 |
| `chat_for_project`, 8 threads | 2 succeeded / 6 `IntegrityError`, **2 bots for one project** — see §6.2 |
| Restart recovery, 1 pending item | 19.51 ms; 1/1 approval expired, 1/1 run+task failed, routine released, **0/1 asks interrupted** |
| Restart recovery, 100 pending items | 723.27 ms; 100/100 approvals expired, 100/100 runs+tasks failed, routines released, **0/100 asks interrupted** |
| Slow provider (2 s simulated turn, 0.4 s timeout) | returned in 445.9 ms with `timeout`; run/task failed, routine released |
| Worker failure (`execute_turn` raises) | returned in 53.5 ms with `internal_error`; run/task failed, routine released |
| DB write with 0.3 s exclusive lock held by other connection | write latency **322 ms** (writer blocks) |

---

## 5. Derived operational targets — **PROPOSED, not owner-approved**

Derived from the measurements above as realistic improvement goals; they are
engineering proposals, not accepted SLAs.

| Area | Measured | **PROPOSED** target | Rationale |
|---|---|---|---|
| Cold import hub + 20 backends | 3,194 ms | ≤ 500 ms | Defer backend imports; keep `assert_dispatch_targets()` lazy |
| Cold import full runtime | 3,568 ms | ≤ 800 ms | Same; webapp alone is 1,796 ms |
| Cold full process | 4,237 ms | ≤ 1,200 ms | Dominated by imports |
| Shutdown after full runtime | 282 ms | ≤ 300 ms | Already acceptable (interpreter-bound) |
| HTTP `/api/health` single client p95 | 108.8 ms | ≤ 100 ms | Loopback floor ~5 ms; handler is trivial |
| HTTP mixed, 8 clients p95/p99 | 695 / 1,247 ms | ≤ 300 / ≤ 500 ms | Requires backlog + handler tuning |
| Connection refusals under 100-client burst | 1.15% | **0%** | Achieved with backlog 128 in A/B |
| `append_row` p99 (single) | 11.54 ms | ≤ 5 ms | Reduce fsync/commit cost |
| `append_row` p99 (32 connections) | 1,202 ms | ≤ 100 ms | Batch writes / single writer |
| Event throughput (DB-backed) | 655–724 ev/s | ≥ 1,000 ev/s | Batch commits |
| Ephemeral publish throughput | 23,571 ev/s | ≥ 20,000 ev/s | Meets target today |
| Restart recovery, 100 items | 723 ms | ≤ 100 ms | Batch recovery transactions |
| Pending asks expired on restart | 0% | 100% | Correctness target |
| Concurrent same-name creation | 13/16 failures | 0 failures | Correctness target |
| RSS growth over 22k ops | +1.84 MB | ≤ 10 MB | No leak observed |
| Capability `invoke` p99 (warm) | ~1.1 ms | ≤ 2 ms | Meets target today |

---

## 6. Bottlenecks, production-significant problems, and recommended fixes

Paths are relative to `keel/src/keel/`. **None of these were implemented** —
recommendations only.

### 6.1 BLOCKING — ~3.2–3.6 s cold startup from eager backend import
- `capabilities.py:198` (`_register_backend_capabilities()`) runs at import and
  at `:142` does `from . import backend_hub as _hub`.
- `backend_hub.py:366` `assert_dispatch_targets()` at import → `:355`
  `importlib.import_module("keel." + module)` for all 20 modules;
  `backend_hub.py:1150` `_publish_schemas_on_import()` also runs at import.
- Heavy stdlib at module scope in backends, e.g. `w4_backend.py:44`
  `from xml.sax.saxutils import escape` (~297 ms cold), `urllib.parse` at `:43`,
  `dataclasses` at `:41`; `d3_backend.py:41` `dataclasses`; plus `urllib.request`,
  `email.parser`, `inspect`, `pathlib` pulled in transitively.
- Measured: 2,027 ms hub import, 3,194 ms capabilities import, 3,568 ms full
  runtime; 20-module cold import ≈ 2.46–3.23 s.
- **Fix:** make `assert_dispatch_targets()` lazy (validate on first real
  `backend.*` call, cached), drop `_publish_schemas_on_import()` eager call, and
  move `xml.sax`/`urllib` imports in `w4_backend.py` to function scope. Keep the
  honest fail-closed check but pay for it only when a backend capability is used.

### 6.2 BLOCKING — duplicate agent creation race (`IntegrityError`) and duplicate project chat
- `service.py:187-190` — `while self._bot_exists(base)` slug uniqueness check
  acquires/releases `self._lock` per call; `:202-211` — the `INSERT INTO bots`
  is a **separate** critical section. Two threads can pick the same slug before
  either inserts. `_bot_exists` at `:239-243`.
- Measured: 13/16 concurrent `create_bot(name="same")` calls raised
  `IntegrityError: UNIQUE constraint failed: bots.id`; only 3 bots existed.
- `chat_for_project` (`:468-487`) reads outside the lock then calls
  `create_bot`; 6/8 concurrent calls failed and **2 bots** were created for one
  project (two stale chats).
- **Fix:** hold `self._lock` across slug selection + INSERT (one atomic critical
  section), or use `INSERT ... ON CONFLICT` with bounded retry. Re-check
  `project_id` ownership inside the same lock in `chat_for_project`.

### 6.3 BLOCKING — pending asks are never expired on restart
- `service.py:103-106` in `expire_pending_asks()`:
  `json_type(body, '$.status') = '"pending"'`. SQLite `json_type()` returns the
  **type name** (`text`), never the JSON literal `"pending"`, so the predicate
  never matches. Verified independently (`jsoncheck.py`):
  `json_type = text`, `json_extract = pending`, matching rows = 0.
- Measured: after simulated restart, 100/100 pending asks remained `pending`
  (0 interrupted), while approvals/runs/tasks recovered correctly.
- **Fix:** use `json_extract(body, '$.status') = 'pending'` (optionally guarded
  by `json_type(...)='text'`).

### 6.4 HIGH — HTTP listen backlog of 5 causes connection refusals under burst
- `webapp.py:1311` returns `ThreadingHTTPServer(("127.0.0.1", port), Handler)`;
  the inherited `socketserver.TCPServer.request_queue_size` is 5 and is not
  overridden in `make_server()` (`:235`).
- Measured 23/2,000 refusals at 100-client burst; controlled A/B with
  `request_queue_size = 128` → 0 refusals under identical load.
- **Fix:** subclass `ThreadingHTTPServer` with `request_queue_size = 128` (and
  `daemon_threads = True`), use it in `make_server()`.

### 6.5 HIGH — SQLite write tail latency under contention
- `fleet/db.py:250` `timeout=30`, `:252` `PRAGMA journal_mode=WAL` but no
  `synchronous=NORMAL` (default `FULL` → fsync per commit).
- `service.py:638-646` `append_row` does INSERT + UPDATE bots + COMMIT under the
  store RLock; every event costs its own transaction.
- Measured: single p99 11.54 ms; shared-store 32-thread p50 46.61 ms / p99
  137.40 ms; 32-connection p99 1,202 ms; 300 ms exclusive lock → 322 ms write.
- **Fix:** set `PRAGMA synchronous=NORMAL` at `fleet/db.py:252`, batch/group
  commits in `append_row` (`service.py:638-646`) and `insert_usage` (`:791-802`),
  and funnel writes through a single queue writer per process; keep WAL.

### 6.6 MEDIUM — timeout bookkeeping / stranded workers
- `fleet/scheduler.py:236` formats `int(timeout)`, so a 0.4 s timeout reports
  "routine timed out after 0s" (observed). Cosmetic.
- `fleet/scheduler.py:229-237` starts a daemon worker and `join(timeout)`; on
  timeout the worker is not cancelled and continues running (simulated 2 s
  provider kept sleeping after the 0.4 s timeout). Repeated slow providers
  accumulate live threads.
- **Fix:** report the real timeout value; add cooperative cancellation/shared
  stop flag so timed-out workers exit, or run turns in a bounded executor.

---

## 7. What passed / worked correctly

- Resource caps are correctly atomic under an 8-thread race (4/4 granted), and
  `ResourceManager` tab/workspace limits held under 16-thread load.
- Unique-name concurrent session/task creation: 640 objects, 0 errors, 239 ops/s.
- Event fan-out is bounded: slow subscriber stayed at exactly 256/256, no
  publisher blocking; ephemeral publish reached 23.6k events/s.
- Restart recovery correctly fails pending approvals, running runs, and tasks,
  and releases routines (100/100 each), in 723 ms.
- Timeout and worker-failure paths both finalized state correctly (failed run +
  failed task + released routine) in 446 ms / 54 ms respectively.
- Memory stayed bounded: +1.84 MB RSS and 167 KB tracemalloc peak over 22k ops.
- Warm capability/backend dispatch is sub-millisecond.

---

## 8. Limitations / threats to validity

1. **Single host, single run** for most scenarios (startup has 7 repeats); no
   confidence intervals. Laptop-class Windows 11 host, no CPU pinning, other
   processes active. Re-run before treating any number as an SLA.
2. **HTTP latency includes a fresh TCP connect per request** because
   `BaseHTTPRequestHandler` defaults to HTTP/1.0; Windows loopback delayed-ACK
   sets a ~5 ms floor. Absolute HTTP numbers are client-methodology-inflated;
   the backlog A/B is the load-bearing HTTP finding.
3. `psutil` is unavailable; RSS is Win32 `WorkingSetSize` (includes shared
   pages), not precise RSS. CPU is `time.process_time()` (whole process).
4. No real LLM provider was called. Slow provider / worker failure were
   simulated by temporarily monkeypatching `turn_core.execute_turn` **in the
   benchmark process only** (no source edit; restored afterwards).
5. One Python process with threads; no multi-process/multi-worker deployment,
   no external network, no large (>24 MB) uploads, no SSE long-lived subscriber
   soak beyond the 256-frame queue bound.
6. Shutdown timing includes interpreter finalization/GC; keel registers no
   measured atexit cleanup, so this is not a keel-specific teardown cost.
7. The candidate HEAD was measured in isolation — no A/B against a prior
   commit. "PROPOSED" targets are derived from these numbers, not negotiated.
8. Harness scripts hard-code the absolute temp/worktree paths used during
   measurement (see `perf-harness/README.md` for re-run instructions).
