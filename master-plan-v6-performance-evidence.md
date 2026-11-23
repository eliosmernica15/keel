# Agent 46 — Performance & Resource Management Evidence

Branch: `agent/f-perf` · Baseline: `8867e735cddefd332e8e1d1e7e04daba0d133d6a`
Files owned: `keel/src/keel/{performance_budgets,resource_caps,hardware}.py`,
`keel/tests/test_perf_hardening.py`, this evidence file.

## Environment / invocation note

`keel` is installed editable from the *main* workspace, so running `python -m pytest`
inside the worktree silently imports the wrong source. All test commands below use a
small runner that puts the worktree `src` first on `sys.path` and prints the resolved
module path (verified as `...\worktree\final\perf\keel\src\keel\hardware.py`):

```
python -P C:\Users\Admin\AppData\Local\Temp\opencode\run_perf_tests.py
python -P C:\Users\Admin\AppData\Local\Temp\opencode\run_all_tests.py
```

`-P` is required because a stray `select.py` in the temp directory shadows the stdlib
otherwise. Benchmark scripts (both uncommitted scratch) are `perf_repro.py` (with
`tracemalloc`) and `perf_final_bench.py` (without), in the same temp directory.

## Issues found and fixed (with reproductions)

1. **Resource cap not enforced under concurrency** — `resource_caps.ResourceMeter.acquire`
   did a non-atomic check-then-increment (`used = self._used.get(...)`, then write).
   Repro: replace `_used` with a dict whose `get()` calls `time.sleep(0)`, then race 8
   threads against `browser` cap 4. Before fix: **7 of 8 acquisitions succeeded**
   (`used` reached 5 > cap 4). Fix: `threading.RLock` guarding `acquire`, `release`,
   `meters`, `set_low_power`. After fix: always exactly 4/8, `used == 4`.
2. **Invalid RAM hint produced nonsense quantization advice** — `hardware.detect`
   accepted `nan`/`inf`/`0`/negative from `KEEL_SYSTEM_RAM_GB`, giving `Q3_K_S` for
   `nan` and `F16` for `inf`. Fix: `_ram_hint()` rejects non-finite/non-positive values
   (and unparseable strings) as unknown; `advise_quantization` also defensively ignores
   such `info["ram_gb"]` values. All four now report `ram_gb=None` → conservative
   `Q4_K_M`.
3. **Explicit empty budget map silently ignored** — `performance_budgets.check` used
   `budgets or DEFAULT_BUDGETS`, so `check({...}, budgets={})` checked the defaults.
   Fix: only `None` selects defaults; `{}` now returns `[]`.
4. **Repeated `detect()` redid OS queries with no bound** — added
   `@lru_cache(maxsize=1)` over process-lifetime platform facts. Cache is strictly
   bounded (verified `maxsize=1, currsize=1`, 100k hits/1 miss over 100k calls), while
   the dynamic env-derived RAM hint is still read fresh on every `detect()` call.
   Also removed the unused `time` import from `resource_caps.py`.

No file handles, timers, or caches existed in the other two modules; boundedness of
meter state is now asserted over 10,000 create/acquire/release cycles.

## Benchmarks (actual measured numbers)

`perf_repro.py` (10,000 calls, with `tracemalloc`, same script run before and after):

| operation | before | after |
|---|---|---|
| `detect()` | 291.69 ms / 29.17 µs per call | 214.93 ms / 21.49 µs per call |
| `check()` (4 measurements) | 565.39 ms / 56.54 µs | 512.29 ms / 51.23 µs |
| meter acquire+release | 35.58 ms / 3.56 µs | 95.70 ms / 9.57 µs |
| `set_low_power()` toggle | 159.16 ms / 15.92 µs | 201.05 ms / 20.11 µs |

`perf_final_bench.py` (100,000 calls, no `tracemalloc`, after fix):

| operation | wall clock | per call |
|---|---|---|
| `detect()` | 385.39 ms | 3.85 µs |
| `check()` (4 measurements) | 824.51 ms | 8.25 µs |
| meter acquire+release | 298.41 ms | 2.98 µs |

Trade-off: the lock adds ~2–6 µs per meter operation (~35 ms → ~96 ms per 10k
acquire/release under tracemalloc). This is the cost of correct cap enforcement;
no unbounded growth was observed (peak traced memory stayed ≤ 11.1 KiB in all loops).

## Tests

- Targeted (new + 3 related existing files): **29 passed** (`test_perf_hardening.py`,
  `test_performance_budgets.py`, `test_resource_caps.py`, `test_hardware.py`).
- Full keel suite: **1417 passed, 45 skipped, 11 failed in 527 s**. All 11 failures are
  unrelated pre-existing/environmental: missing `keel/release/*` artifacts
  (`test_distribution_package`, `test_gap_closure`, `test_release_integrity`), Windows
  AppContainer unavailable (`test_os_sandbox`, 4 tests), stale downloaded plan hashes
  (`test_plan_index`), and one timing-sensitive `test_compat_runtime` approval test.
  No failure touches any of the three owned modules.
- No `test_engine*.py` files exist in this repository.

Commit SHA is reported in the agent's final message (a commit cannot contain its own SHA).
