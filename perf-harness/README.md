# Performance harness (read-only measurement artifacts)

These are the exact scratch scripts and raw result JSON files used to produce
`../PROD-PERFORMANCE-EVIDENCE.md`. No production source file was modified.

They were executed from `C:\Users\Admin\AppData\Local\Temp\opencode\prod-perf`
with `python -P`; each script inserts the worktree source directory
`C:\Users\Admin\.local\share\opencode\worktree\production\perf\keel\src`
at `sys.path[0]`, so `keel` resolves to the candidate worktree, not any
editable install. `-P` avoids a stray `select.py` in the parent temp directory.

To re-run from this folder, first edit the `HERE` constant in each script to
this folder's absolute path (it currently points at the temp folder where the
measurements were taken), then:

```
python -P bench_startup.py
python -P bench_http.py
python -P bench_http_backlog.py
python -P bench_db.py
python -P bench_cap.py
python -P bench_resilience.py
```

Supporting diagnostics: `probe.py`, `imp.py` (`python -P -X importtime imp.py`),
`import_breakdown.py`, `per_module.py`, `jsoncheck.py`, `memtest.py`, `sig.py`.
Result files: `result_startup.json`, `result_http.json`, `result_backlog.json`,
`result_db.json`, `result_cap.json`, `result_resilience.json`.
