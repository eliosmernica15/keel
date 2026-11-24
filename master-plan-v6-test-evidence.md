# Master Plan v6 — Test evidence

**Current branch:** `integration/v6-addenda-complete` (local only, not pushed)
**Final commit:** `38ae621` (see git log for subsequent evidence commits)
**OS:** Windows 10 (10.0.26300-SP0), AMD64
**Python:** 3.11.9 (MSC v.1938 64 bit)
**Node:** v24.22.2

## Authoritative final full-suite run (addenda 3–7 operation)

Command (from `keel/`):

```
python -m pytest -q -o faulthandler_timeout=120
```

Result:

```
2963 passed, 48 skipped, 2502 subtests passed in 461.14s (0:07:41)
```

**0 failed.** This is the definitive green run at the final integrated tree.

### Root cause of the earlier 14 order-dependent failures (fixed)

Seven consecutive full runs had shown 14 failures that all passed in isolation. This was **not** stale state — it was genuine test pollution. `tests/test_offline_runtime.py::test_no_outbound_import_hooks` deleted every `keel.*` module from `sys.modules` to test a clean import, without restoring them. Any test that had captured a class reference at collection time (`keel.tools.registry.Tool`, `keel.capabilities.CapabilityError`, `keel.security_contracts.UnsafeLinkError`, etc.) then held a reference to the *old* class object, so later `isinstance(...)` checks failed with `TypeError: tool must be a Tool instance`, stale policy decisions came from the wrong module instance, SQLite state diverged, and config paths reverted to defaults. The test was fixed by snapshotting and restoring the evicted modules in a `finally` block, preserving its original network-at-import guarantee while eliminating global pollution. Verified: the exact polluter→victim sequence passes 152/152, and the full suite is green.

## Historical runs (provenance)

- Baseline `cadb343` (before this operation): `python -m pytest -q` → 1270 passed, 10 skipped.
- After the earlier completion operation: 1513 passed, 46 skipped.
- Mid-merge runs during the 10-wave parallel operation: 2182–2949 passed with 14–15 failures, all attributable to the `sys.modules` pollution above (now fixed). No test was deleted or weakened to obtain the green result.

## Skip reasons (48)

- 10 provider live-smoke tests: no `KEEL_*_API_KEY` credentials configured (external dependency, reported as blocked — not converted to passes).
- 36 native-sandbox platform gates: Linux Landlock/seccomp and macOS Seatbelt cannot execute on this Windows host; Python interpreter under AppContainer cannot launch here. Each skip names the exact platform limitation.
- 2 pre-existing environment/platform gates (symlink creation without elevation; generated-artifact-dependent checks).

No security-critical test converts failed enforcement into a skipped success.

## Other verification

- `python scripts/verify_v6_audit.py` → CONSISTENCY OK (865 IDs, parity identical, all verified refs resolve).
- `python keel/scripts/build_dependency_graph.py --check` → FRESH.
- `python scripts/check_model_licenses.py` → LICENSE GATE OK.
- All 8 GitHub Actions workflow YAMLs parse; 26 `uses:` refs are full-SHA pinned.
- Offline runtime tests: 4 passed (network namespace lane in CI is fail-closed).
- Per-batch targeted suites across 42 specialist branches: all passing before merge; independent reviewers found 0 critical and their high/medium findings were fixed with regression tests.
