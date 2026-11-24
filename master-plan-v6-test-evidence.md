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

# Backend completion operation — test evidence (2026-11-24)

Branch: `integration/v6-backend-complete` (local only). Baseline: `0865817`.

## Authoritative integrated-tree full-suite run (20 backend modules)

Command (from `keel/`):

```
python -m pytest -q -o faulthandler_timeout=120
```

Result:

```
3992 passed, 48 skipped, 3621 subtests passed in 669.93s (0:11:09)
```

**0 failed.** This run included all 20 newly integrated backend modules and their per-module
test suites (30–90 tests each). It was executed after cleaning orphaned test servers left by
earlier runs, which had caused two load-induced socket-timeout failures in an earlier attempt.

Per-module targeted suites were independently re-run by the lead before each merge; all passed.
The 8 real-runtime capability-hub integration tests
(`keel/tests/test_backend_hub_integration.py`) passed separately.

The 48 skips remain platform/credential gates (provider live smoke, native Linux/macOS sandbox,
two pre-existing environment gates). No test was deleted, weakened, or converted to a fake pass.

## Comparison with the prior baseline
- Prior operation final run at `0865817`: 2963 passed, 48 skipped, 2502 subtests, 0 failed.
- After the 20 backend modules: 3992 passed (+1029), 48 skipped (unchanged), 3621 subtests (+1119), 0 failed.

## Final run
A definitive post-remediation full-suite run is recorded after the remediation agents' fixes are
integrated (see the final addendum below and `FINAL-ENGINEERING-REPORT.md`).

## FINAL post-remediation full-suite run (authoritative)

Command (from `keel/`):

```
python -m pytest -q -o faulthandler_timeout=120
```

Result:

```
4029 passed, 48 skipped, 3621 subtests passed in 490.94s (0:08:10)
```

**0 failed, exit code 0.** This is the definitive final run after all 20 backend modules,
the capability-hub integration and all 4 remediation batches were merged. It includes
1079 collected backend test cases.

Progression of authoritative runs in this operation:
- Baseline at `0865817` (before this operation): first attempt had 2 load-induced socket timeouts under 20 concurrent agents; no product defect.
- After 20 backend modules: 3992 passed, 48 skipped, 3621 subtests, 0 failed (669.93s).
- **Final after remediation: 4029 passed, 48 skipped, 3621 subtests, 0 failed (490.94s).**

Remediation added 37 passing tests (7 in A, 7 in B, 6 in C, 8 in D, plus additional
case coverage within those suites). Each regression test was independently verified
to fail against the pre-fix source before being merged.

The 48 skips are unchanged platform/credential gates; no test was deleted, weakened,
or converted to a fake success.

Static checks: no `ruff`/`mypy`/`flake8` installed in this environment. `python -m py_compile`
and `python -m compileall -q src/keel` both pass; `git diff --check` clean. All 8 workflow
YAMLs parse and all 30 `uses:` refs are full-SHA pinned.

## FINAL adversarial-audit full-suite run (authoritative, post-remediation)

All 10 audit findings remediations were integrated before this run. Ambient
`~/.keel/settings.json` MCP servers (from concurrent user work) were isolated by running
with a clean local HOME that preserved Keel state but stripped `mcpServers`; in that same
environment the two previously timing-out webapp tests passed in 6.5s.

Command (from `keel/`, clean HOME):

```
python -m pytest -q -o faulthandler_timeout=120
```

Result:

```
4071 passed, 48 skipped, 3640 subtests passed in 585.13s (0:09:45)
```

**0 failed, exit code 0.** +42 passing tests vs the 4029 pre-audit baseline (new regression
tests for every confirmed audit defect). 48 skips unchanged; no test deleted or weakened.

Under 15 concurrent agents an earlier reproduction gave 4027 passed / 2 failed / 48 skipped /
3621 subtests; the 2 failures were 30s localhost HTTP timeouts caused by ambient MCP config,
not product defects (verified: they pass in 4-6s with isolated HOME).

Governance gates after final integration:
`verify_v6_audit.py` CONSISTENCY OK; `verify_backend_operation.py` OK (361/421 traceable IDs);
dependency graph FRESH; license gate OK; 8 workflow YAMLs parse; 30 `uses:` full-SHA pinned.

## Additive cross-reference — docsync reconciliation (2026-11-24, no result changed)

This appendix adds pointers only; the test result and gate outputs above are unchanged and
remain authoritative.

- Registry state at reconciliation: `PLAN-INDEX.json` SHA-256
  `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6` — 865 rows,
  854 verified / 9 not_started / 2 blocked. No status was altered.
- The `361/421` traceable-ID figure above is restated as **361 / 421 fully traceable + 60
  verified with certification limitation = 421 backend-attributed IDs**; the 60 are
  evidence-layer gaps, not test failures or status downgrades
  (`REGISTRY-EVIDENCE-INTEGRITY.md` §4, `REMAINING-WORK-MATRIX.md` §5).
- Dedup backend denominator and completion formulas: `BACKEND-COMPLETION-ACCOUNTING.md`.
- The 5 / 5 workflows (102 / 102 steps) are reported in `AUDIT-REMEDIATION-SUMMARY.md`
  and `BACKEND-IMPLEMENTATION-DETAIL.md`; the clean-environment full-suite result above
  is not modified by this appendix.
