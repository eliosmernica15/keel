# Remediation of core-review findings (branch `agent/a4-fix-high`)

Baseline: `52c94b8`. Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\fix-high`.

Scope: the 3 HIGH findings plus the 4 MEDIUM findings from `REVIEW-CORE-FINDINGS.md`.
Only the six owned source/test files plus this document were changed. No existing
test was removed, weakened, or made permissive; every change to production code
is accompanied by a new regression test that was confirmed red before the fix.

## Test command (run from the worktree root)

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_tool_contracts.py','keel/tests/test_tool_contracts_bridge.py','keel/tests/test_edit_formats.py']))"
```

## Test timeline (exact output)

Baseline, before any change (90 existing tests):

```
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 4.57s
```

HIGH regression tests first — red (the first run also exposed that the first H1
fixture returned an output that failed canonical schema validation; the fixture
was corrected to include `ok: True`, and the run was repeated):

```
FAILED keel/tests/test_tool_contracts.py::test_contract7_replace_value_scrubs_every_result_surface
       AssertionError: presentation_meta
FAILED keel/tests/test_tool_contracts.py::test_contract7_replace_value_discards_pre_dlp_attached_context
       AssertionError: assert [{'note': 'SECRET_IN_DEFERRED_CONTEXT'}] == []
FAILED keel/tests/test_tool_contracts.py::test_contract8_pre_cancelled_call_never_dispatches_handler
       AssertionError: assert [True] == []
FAILED keel/tests/test_tool_contracts.py::test_contract8_pre_cancelled_wrapper_signal_never_dispatches
       AssertionError: assert [True] == []
FAILED keel/tests/test_edit_formats.py::test_fuzzy_compact_never_substitutes_semantically_different_lines
       Failed: DID NOT RAISE <class 'keel.edit_formats.FuzzyMatchError'>
FAILED keel/tests/test_edit_formats.py::test_fuzzy_threshold_one_cannot_be_defeated_by_compact
       Failed: DID NOT RAISE <class 'keel.edit_formats.FuzzyMatchError'>
6 failed, 90 deselected in 1.50s
```

After the HIGH fixes — green:

```
......                                                                   [100%]
6 passed, 90 deselected in 1.08s
```

All three files after the HIGH fixes (no existing test disturbed):

```
........................................................................ [ 75%]
........................                                                 [100%]
96 passed in 4.22s
```

MEDIUM regression tests written first — red:

```
FAILED ...::test_contract3_numeric_types_follow_json_schema_widening
       AssertionError: ['$: expected number, got integer'] == []
FAILED ...::test_contract10_dispatched_baseexception_failure_is_not_reported_as_skipped
       AssertionError: assert 'ABORTED_BEFORE_DISPATCH' == 'TOOL_EXECUTION_ERROR'
FAILED ...::test_conformance_reports_schema_leak_instead_of_raising
       ValueError: model-facing schema leaked fields: ['handler', 'timeout_s']
FAILED ...::test_fuzzy_replace_preserves_absent_final_newline
       AssertionError: assert 'a\nb\nC\n' == 'a\nb\nC'
4 failed, 96 deselected in 1.47s
```

Final, required command:

```
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 4.29s
```

Broader regression check (the seven files from the review):

```
........................................................................ [ 32%]
..................................................s..................... [ 65%]
........................................................................ [ 98%]
...                                                                      [100%]
218 passed, 1 skipped in 6.04s
```

(The single skip is the pre-existing Windows symlink skip in `test_model_dialects.py`.)

## HIGH findings

### H1 — DLP `replace_value` leaked the original secret via `presentation_meta`

**Before.** `apply_post_hooks` (`tool_contracts.py`) called
`replace(current, value=new_value, display=...)` only. `presentation_meta` had
already been computed in `execute_tool` from the *pre-DLP* value, and deferred /
injected context was already attached. For a `read_file`-shaped result the full
secret survived durably:

```
meta = {... 'fields': {'lines': ['SECRET_VALUE_here'], ...}}
LEAK_IN_PRESENTATION_META = True
```

**After.** The `REPLACE_VALUE` branch now rebuilds *all* data surfaces from the
replacement value: `presentation_meta(name, safe_args, new_value)` is recomputed
and `attached_context` is cleared. `display` is re-rendered from the redacted
value, as before. `audit` / `durable_reason` hold policy diagnostics only and
never the value. The regression test recursively scans every data field of the
returned `ToolResult` and fails if the secret appears anywhere.

Tests: `test_contract7_replace_value_scrubs_every_result_surface`,
`test_contract7_replace_value_discards_pre_dlp_attached_context`.

### H2 — pre-cancelled single call still dispatched its handler

**Before.** After policy passed, `pool.submit(dispatch, ...)` was unconditional.
A cancel signal set before `execute_tool` was entered still ran the side-effecting
handler; only afterwards was the result reported `ABORTED`:

```
pre-cancelled result code= ABORTED handler started= ['started']
```

**After.** Immediately after wrappers are applied and signals are fused, and
before any worker is created, the pipeline checks
`caller_signal.cancelled or effective.cancelled` and returns a typed
`ABORTED` failure with a durable reason. The handler is never invoked. The gate
covers both the caller's signal and any wrapper-supplied signal. `ABORTED` was
chosen because the mandated single-call cancellation vocabulary is
`CANCELLED`/`ABORTED` and the existing contract test
`test_contract8_caller_cancel_propagates_through_wrapper` requires `ABORTED`
for this path; `ABORTED_BEFORE_DISPATCH` remains the honest code for *batch*
calls that were never submitted (see M2).

Tests: `test_contract8_pre_cancelled_call_never_dispatches_handler`,
`test_contract8_pre_cancelled_wrapper_signal_never_dispatches`.

### H3 — `compact` matched a semantically wrong line at similarity 1.0

**Before.** `_normalize(..., "compact")` removed *all* whitespace, including
whitespace inside string literals and between digits/identifiers. Two different
lines collapsed to the same string, scored 1.0, outranked the correct
`rstrip`/`collapsed` match and passed `threshold=1.0`:

```
APPLIED  old= 'x = "a b"'  orig= 'x = "ab"\n'  ->  'x = "cd"\n'  strategy= compact  sim= 1.0
APPLIED  old= 'return 1 2' orig= 'return 12\n' ->  'return 99\n' strategy= compact  sim= 1.0
THRESHOLD 1.0 BYPASSED
```

**After.** Two independent guards:

1. `_unsafe_compact_collision` rejects a window when naive whitespace removal
   makes the texts equal *only* because whitespace inside a quoted literal or
   between two word characters (identifiers/numbers) was discarded.
   `_safe_compact` protects those gaps. Such windows are never eligible at any
   threshold and produce a typed `no_match`.
2. When `threshold >= 1.0 - eps`, the lossy `compact` strategy is removed from
   the strategy list entirely, so `threshold=1.0` cannot be defeated.

Safe whitespace compaction (e.g. `call( a , b )` vs `call(a, b)`) still works at
the default threshold; exact matches still work at `threshold=1.0`.

Tests: `test_fuzzy_compact_never_substitutes_semantically_different_lines`,
`test_fuzzy_threshold_one_cannot_be_defeated_by_compact`.

## MEDIUM findings

- **M1 numeric validation.** `_type_matches` now treats `integer` as satisfying
  `number` and an integral float as satisfying `integer`; `bool` and strings
  remain invalid. Test: `test_contract3_numeric_types_follow_json_schema_widening`.
- **M2 honest batch outcomes.** On an internal `BaseException`, `execute_batch`
  now drains every submitted safe future with a guarded helper; a future that
  raised is recorded as `TOOL_EXECUTION_ERROR`, not back-filled as
  `ABORTED_BEFORE_DISPATCH`. Only calls never submitted can be "skipped".
  Test: `test_contract10_dispatched_baseexception_failure_is_not_reported_as_skipped`.
- **M3 lossless last line.** `_replace_span` now preserves an empty final
  separator instead of substituting the dominant separator, so editing or
  replacing the final line of a newline-free file does not add a byte.
  Test: `test_fuzzy_replace_preserves_absent_final_newline`.
- **M4 conformance leak reporting.** `check_native_conformance` wraps
  `project_model_schemas` in `try/except ValueError` and appends the leak
  message to `problems`, returning `ok: False` instead of raising.
  Test: `test_conformance_reports_schema_leak_instead_of_raising`.

## Result

All 3 HIGH findings fixed. All 4 MEDIUM findings fixed. No finding was left
unfixed. 100/100 tests pass in the three owned test files; 218 pass / 1 skip in
the broader review suite.
