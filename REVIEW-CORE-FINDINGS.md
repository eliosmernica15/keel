# Independent review — merged core implementation batches

Reviewer: independent subagent (read-only; no implementation changes).
Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\review-core` (branch `agent/a4-review-core`).

## Baseline note (transparency)

The supplied baseline `458741e` is **identical to HEAD** on this branch (`git rev-parse HEAD` == `git rev-parse 458741e`); `git diff --stat 458741e HEAD` is empty. The implementation batches under review are ancestor commits of the baseline:

```
dcdab71 Merge X1.1-X1.3 model dialect adapters (70 tests)
ad17d2a Merge X1.13 steering/interrupt (20 tests)
6f07762 Merge X1.7 repo map ranking + X1.8 token counting (23 tests)
3fe7cc3 Merge Addendum 7 tool contracts: 20 contracts, 60 tests
92c7e54 Add tool-contracts bridge
e2da531 Merge X1.4-X1.5 edit formats and fuzzy patches (26 tests)
fa062a4 ...fix status page not_started accounting
```

I therefore reviewed the actual source and tests at HEAD rather than a diff, and reproduced claims by executing code from the worktree.

## Exact commands and results

### Required test command

```
cd "C:\Users\Admin\.local\share\opencode\worktree\addenda\review-core"
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_tool_contracts.py','keel/tests/test_model_dialects.py','keel/tests/test_edit_formats.py','keel/tests/test_repo_map.py','keel/tests/test_steering.py','keel/tests/test_tool_contracts_bridge.py','keel/tests/test_status_page.py']))"
```

Result:

```
........................................................................ [ 34%]
............................................s........................... [ 68%]
.................................................................        [100%]
208 passed, 1 skipped in 6.73s
```

### Skip reason

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','-rs','keel/tests/test_model_dialects.py']))"
```

Result: `70 passed, 1 skipped in 0.99s`, with:
```
SKIPPED [1] keel\tests\test_model_dialects.py:370: symlinks unavailable on this platform
```

### Reproduction probes

Probes were written to `C:\Users\Admin\AppData\Local\Temp\opencode\review_probe\` (outside the worktree) and run as `python <probe>.py`. Outputs are quoted verbatim under each finding below. The full scripts are `probe.py` … `probe6.py` in that directory.

---

## Findings by severity

**Summary: 0 Critical, 3 High, 4 Medium, 2 Low (9 total).**

### HIGH

#### H1 — `dlp_replace_value` redacts `value`/`display` but leaves the original secret in `presentation_meta`

**Files:** `keel/src/keel/tool_contracts.py:644-648` (`dlp_replace_value`), `:671-676` (`REPLACE_VALUE` branch omits `presentation_meta`), `:1242-1246` (meta computed from the *original* value before post-hooks), `:1769-1799` (`present_result` copies value fields, incl. `read_file` `lines`, into card fields).

DLP is advertised as protecting "the actual `value` that both the renderer and programmatic callers see (DLP must use this or BLOCK)" (`:598-601`). In reality `apply_post_hooks`'s `REPLACE_VALUE` branch calls `replace(current, value=new_value, display=...)` only; `presentation_meta` is never recomputed or cleared. Because `presentation_meta` was built at `:1245` from the pre-DLP value, a `read_file` result's full contents survive in `result.presentation_meta["fields"]["lines"]`. That object is a durable/replay UI surface — so a DLP "replace value" hook fails to protect the confidential data on a persisted surface.

**Reproduction (`probe.py`):** register a `read_file`-shaped spec whose handler returns `lines: ["SECRET_VALUE_here"]`, add `tc.dlp_replace_value("[REDACTED]")`, execute, inspect result:

```
value   = '[REDACTED]'
display = '[tool result: "[REDACTED]"]'
meta    = {'tool': 'read_file', 'card_kind': 'read', 'icon': 'read', 'status': 'completed', 'fields': {'path': 'x', 'offset': 1, 'lines': ['SECRET_VALUE_here'], 'total_lines': None, 'language': None}}
LEAK_IN_PRESENTATION_META = True
```

`test_contract7_replace_value_protects_actual_value` (`:324-331`) only asserts on `result.value` and `result.display`, so it gives a false sense of DLP coverage. **Fix:** on `REPLACE_VALUE`, reset `presentation_meta` (e.g. `presentation_meta(name, args.json, new_value)`) and scrub any previously attached context; add an assertion that no pre-DLP bytes appear in any result surface.

#### H2 — A pre-cancelled single call still dispatches and executes its handler

**Files:** `keel/src/keel/tool_contracts.py:1177-1198` — after policy passes, `pool.submit(dispatch, ...)` is unconditional; there is no `if caller_signal.cancelled` / `effective.cancelled` pre-dispatch gate. `ABORTED_BEFORE_DISPATCH` exists (`:66`, part of the mandated vocabulary) but is only used by `execute_batch` (`:1300-1303`).

The module claims cancellation is an "around-dispatch" guarantee (`:692`, `:1105-1122`) and `ABORTED_BEFORE_DISPATCH` exists precisely for calls skipped before dispatch. For a call that is already cancelled when `execute_tool` is entered, the handler is nevertheless submitted and runs; a handler with side effects (delete/write/network) will perform them, and only then is the result reported `ABORTED`. Cancellation is therefore not fail-closed for the single-call path — a user abort racing a queued tool call does not stop the side effect.

**Reproduction (`probe2.py`):**

```
=== PROBE 9: cancellation before dispatch still runs handler? ===
pre-cancelled result code= ABORTED handler started= ['started']
```

`test_contract10_one_outcome_per_call_including_skipped` (`:486-494`) covers only the batch path. **Fix:** check `caller_signal.cancelled` (and any wrapper-provided signal) immediately before `pool.submit` and return `failure_result(name, ToolErrorCode.ABORTED_BEFORE_DISPATCH, ...)`; add a test that the handler is never invoked when cancel is pre-set.

#### H3 — `fuzzy_replace` can apply a *wrong* line at similarity 1.0; the threshold guard is bypassed

**Files:** `keel/src/keel/edit_formats.py:84` (`_LEVELS` includes `compact`), `:442-451` (`_normalize` compact = `_WS_RE.sub("", body)`), `:518-528` (best-score/eligible computation), `:543-568` (pick `tied[0]` and apply).

The `compact` strategy removes **all** whitespace, including whitespace inside string literals and between digits/identifiers. Two semantically different lines collapse to the same normalized string, yielding `similarity == 1.0`. This outranks the correct `rstrip`/`collapsed` match and defeats both the threshold (`1.0` passes) and the ambiguity guard (only one candidate reaches the top score). The design guarantee "never guesses between equally good candidates" (`:16`) does not cover this case because the wrong candidate is *uniquely* "best".

**Reproduction (`probe4.py`):**

```
APPLIED  old= 'x = "a b"'  orig= 'x = "ab"\n'  ->  'x = "cd"\n'  strategy= compact  sim= 1.0
APPLIED  old= 'url = "https://example. com"'  orig= 'url = "https://example.com"\n'  ->  'url = "SAFE"\n'  strategy= compact  sim= 1.0
APPLIED  old= 'msg = "helloworld"'  orig= 'msg = "hello world"\n'  ->  'msg = "X"\n'  strategy= compact  sim= 1.0
APPLIED  old= 'return 1 2'  orig= 'return 12\n'  ->  'return 99\n'  strategy= compact  sim= 1.0
```

**And `probe5.py` proves the threshold guard does not help:**

```
THRESHOLD 1.0 BYPASSED: 'x = "cd"\n' compact 1.0
```

Existing tests only exercise whitespace *between* tokens (`test_fuzzy_replace_tolerates_collapsed_whitespace`, `:145-149`) and never test whitespace inside literals. **Fix:** exclude `compact` from the eligible strategies for code edits (or preserve whitespace inside quoted strings / make compact a low-priority tie-break that can never outrank an exact/rstrip/collapsed match of another window); add adversarial tests with quoted literals and numeric tokens.

### MEDIUM

#### M1 — `validate_value` rejects valid JSON Schema numeric values

**Files:** `keel/src/keel/tool_contracts.py:247-262` (`_json_type` returns `"integer"` for `int`, `"number"` for `float`), `:327-332` (exact string membership test on `expected_types`).

JSON Schema treats every integer as a valid `number` and an integral float as a valid `integer`. The strict membership check rejects `5` for `{"type":"number"}` and `5.0` for `{"type":"integer"}`. This is fail-closed (not a privilege escalation) but breaks legitimate tool calls and contradicts the module's "single schema vocabulary" claim.

**Reproduction (`probe.py`):**

```
number<-int   errors = ['$: expected number, got integer']
integer<-float errors = ['$: expected integer, got number']
...
end-to-end integer for number schema code = INVALID_ARGS ok = False
```

**Fix:** treat `"integer"` as satisfying `"number"` and accept integral floats for `"integer"`.

#### M2 — `execute_batch` reports a dispatched, BaseException-failed call as `ABORTED_BEFORE_DISPATCH`

**Files:** `keel/src/keel/tool_contracts.py:1331-1342` (submit + `fut.result()` in try), `:1346-1347` (`except BaseException`), `:1349-1352` (missing outcomes filled with `_aborted`).

When a safe call's future raises a `BaseException` (e.g. `KeyboardInterrupt`/`SystemExit` from a handler), the `except BaseException` arm sets `internal_error` and exits the loop without collecting the other `pending_safe` futures. Those calls *were* dispatched but their outcomes are left `None` and then back-filled with `ABORTED_BEFORE_DISPATCH`. The docstring promises "started calls settle with their real ... outcome; only not-yet-dispatched calls are marked as skipped" (`:1310-1311`), and `ToolBatchExecutionError` promises "preserves already-committed outcomes" (`:117`). Outcomes remain deterministic but are dishonest.

**Reproduction (`probe2.py`):**

```
ToolBatchExecutionError outcomes: [('ok', None), ('boom', 'ABORTED_BEFORE_DISPATCH')]
```

(the `boom` call was in `pending_safe`, dispatched, and raised `KeyboardInterrupt`). `test_contract10_internal_failure_drains_then_typed_batch_error` (`:496-512`) only monkeypatches `execute_tool` to raise for an *exclusive* call, so it never exercises this path. **Fix:** in the exception arm, drain `pending_safe` with `fut.result()` under a guarded helper before filling gaps, and distinguish "dispatched but failed" from "skipped".

#### M3 — Editing the last line of a file without a trailing newline adds one

**Files:** `keel/src/keel/edit_formats.py:185-206` (`_split_lines`/`_join`), `:281-311` (`_replace_span`, esp. `:296-301` separator selection and `:303-311` rebuild).

The design guarantee states "All line-ending handling is lossless ... no-op edits return the original string byte-for-byte" (`:17-19`). When the replaced span is the final line and that line has no separator, `_replace_span` assigns `trailing_sep = target_sep` (default `"\n"`), and `_join` appends it to the new last line. A one-line change to a newline-free file silently changes the file's final byte.

**Reproduction (`probe.py`):**

```
orig = 'a\nb\nc'
res  = 'a\nb\nC\n'
ADDED_TRAILING_NEWLINE = True
orig2 = 'a\r\nb\r\nc'
res2  = 'a\r\nb\r\nC\r\n'
```

`test_fuzzy_replace_preserves_crlf_and_lf` (`:209-215`) and `test_fuzzy_replace_no_op_is_exact_and_preserves_bytes` (`:234-239`) both use inputs with a trailing newline, so they miss this. **Fix:** propagate the original final line's `sep` (empty string) when the replaced span includes the last line.

#### M4 — `check_native_conformance` crashes instead of reporting a schema leak

**File:** `keel/src/keel/tool_contracts_bridge.py:65-81`, specifically `:68` (`projected = project_model_schemas(native_registry.schemas())`).

`project_model_schemas` deliberately raises `ValueError` on leaked fields (`:41-45`), which is correct for a projection API. But `check_native_conformance` is documented to "produce a conformance report" with a `problems` list and `ok` flag; it calls the raising API unguarded, so the single most important conformance failure (an internal field in a model-facing schema) aborts CI with an exception instead of appearing in `report["problems"]`.

**Reproduction (`probe6.py`)** with a registry whose `schemas()` includes `handler`/`timeout_s`:

```
CONFORMANCE CHECK RAISED INSTEAD OF REPORTING: ValueError "model-facing schema leaked fields: ['handler', 'timeout_s']"
```

`test_native_registry_conforms` (`:21-25`) only exercises a clean registry. **Fix:** wrap the projection in `try/except ValueError` and append the message to `problems`.

### LOW

#### L1 — "no embedded code executed" assertion is trivially true on this platform

**File:** `keel/tests/test_model_dialects.py:199-208`. The security assertion `assert not os.path.exists("/tmp/pwned")` is platform-specific and vacuously true on Windows (the actual test host), so it does not verify the claim. The parser itself is data-only (no `eval`/`exec`/`subprocess`), so this is a test-quality issue only. **Fix:** monkeypatch `os.system`/`subprocess` to fail if called, or assert on the inert `ToolCall` payload alone without a filesystem sentinel.

#### L2 — symlink path-containment test is skipped on the review host

**File:** `keel/tests/test_model_dialects.py:361-373`; skip confirmed at `:370` in the `-rs` run above. The implementation `_contained_path` (`keel/src/keel/model_dialects.py:682-693`) uses `os.path.realpath` + `commonpath` and my probes (`probe2.py`, "PROBE 8") confirmed traversal strings (`../`, `../../`, `C:/Windows/win.ini`, `/etc/passwd`) are not read and no outside content is returned. However, the symlink-escape case — the one containment check most likely to regress — is currently untested on Windows. **Fix:** add a non-symlink containment regression (already partly present via `template_file` traversal) or mark the symlink case as a known platform gap.

---

## Challenge-question verdicts (answers to the seven specific questions)

1. **Do the tests exercise real behavior?** Mostly yes — 208 passing tests drive real handlers, hooks, parsers, graph building and concurrency. Exceptions: the DLP test (H1) checks only two of several result surfaces, the batch-failure test (M2) misses safe-call futures, and L1/L2 are weak/skipped security assertions. No swallowed exception or skipped security assertion was found in the core contract/steering/repo-map paths.

2. **Tool contracts — deny→allow?** **No.** `combine_decisions` (`:484-492`) orders severity `DENY > CANCEL > ASK > ALLOW`; `apply_guards` (`:495-514`) rebuilds non-ALLOW decisions so a guard's `ALLOW` cannot upgrade; the approval responder path (`:541-566`) upgrades only `ASK`→`ALLOW` and only with `allow_once`. Reproduced in `probe2.py` PROBE 6: `deny+guard allow+approver allow -> APPROVAL_REJECTED`. **DLP value-level?** Incomplete (H1). **Cancellation propagate?** Propagates while running (`:1184-1225`, tests `:371-400`), but not before dispatch (H2). **Batch outcomes deterministic?** Order is deterministic; honesty gap on BaseException (M2). **Model schemas free of internal fields?** Yes on the projection path (`:935-955`, bridge tests), but the conformance reporter crashes on a leak (M4).

3. **Dialects — malformed/truncated call accidentally executed?** No execution exists anywhere in `model_dialects.py`; `ToolCall` is a frozen data record and `parse_tool_calls` (`:528-544`) catches all exceptions. Truncation is flagged `incomplete=True` (`:243-253`, test `:134-141`). **Reasoning excluded from history by default?** Yes — `should_include_in_history` defaults to `False` (`:935-944`, test `:451-457`). **Path containment for templates?** Confirmed safe (`:667-706`, probe PROBE 8); only the symlink variant is untested on this host (L2).

4. **Edit formats — fuzzy wrong match?** Yes (H3), including at `threshold=1.0`. **Ambiguity/threshold guards real?** The exact-tie ambiguity guard (`:553-564`) works for byte-identical candidates (test `:169-178`), but is bypassed by the compact-strategy semantic collision (H3). **CRLF/indentation correctness?** CRLF/LF replacement inside a file is correct (test `:209-215`); final-line newline fidelity is broken (M3); indentation shift handling is exercised (test `:152-166`) and looks correct.

5. **Repo map — token budget deterministic?** Yes: `rank_symbols` (`:576-592`) and `render_repo_map` (`:611-638`) trim greedily in ranked order and re-check the whole-text count; repeated calls equal (test `:168-176`). **PageRank cycles safe?** Yes — dangling mass redistributed, self-loops filtered, fixed iterations with tolerance, normalized (`:492-532`; tests `:66-75`, `:139-144`). **Tokenizer fallback honest (no network)?** Yes — injected `tokenizer_fn` is the only integration point, failures counted and degraded to bytes/4 (`:134-148`); test `:325-330` checks banned imports. No issue found.

6. **Steering — concurrency races/lost messages?** No: all mutations under `RLock`, `seq` assigned under lock, concurrent submit/deliver/output tests (`:126-197`, `:316-376`) pass. **Partial-output byte fidelity?** `bytes` copy in snapshot/resume (`:171-189`, `:291-303`, `:329-362`); invalid-UTF-8 test `:214-231` passes. **Abort idempotence?** `_abort_locked` (`:262-278`) increments `abort_count` and captures the snapshot only once; tests `:234-249` pass. No issue found.

7. **Status page — not_started accounting correct and honest?** Yes. Registry has 865 features: `verified=268, blocked=2, not_started=595`; `verified_end_to_end=262`, `built_unproven=6`, `not_started=595`, `blocked=2` — sums to 865 exactly. No verified-but-uncounted feature and no proven-tier verified feature missing `test_references`. `render_markdown` displays the not_started count. No issue found.

---

## Verdict per module

| Module | Verdict | Specifics |
| --- | --- | --- |
| `keel/src/keel/tool_contracts.py` (+ `tests/test_tool_contracts.py`) | **FIX REQUIRED** | H1 (DLP leaks via `presentation_meta`), H2 (pre-cancelled handler still dispatched), M1 (numeric type strictness), M2 (batch BaseException outcome honesty). Add tests covering all result surfaces, pre-cancel dispatch, JSON-Schema numeric compatibility and safe-call infra failures. |
| `keel/src/keel/tool_contracts_bridge.py` (+ tests) | **FIX REQUIRED** | M4 — catch `ValueError` from `project_model_schemas` and report it in `problems` instead of raising; add a leaking-registry test. |
| `keel/src/keel/model_dialects.py` (+ tests) | **ACCEPT** | Monotonic deny/allow, data-only tool calls, template containment and history exclusion verified. Address L1 (vacuous `/tmp/pwned` assertion) and L2 (skipped symlink test) as test hygiene; no code change required for the reviewed contracts. |
| `keel/src/keel/edit_formats.py` (+ tests) | **FIX REQUIRED** | H3 (compact strategy silently applies a semantically wrong line and defeats threshold=1.0; add literal/numeric adversarial tests), M3 (preserve absent trailing newline on final-line edits; add no-trailing-newline fixtures). |
| `keel/src/keel/repo_map.py` (+ tests) | **ACCEPT** | Deterministic budgeting, cycle-safe PageRank, honest local-only tokenizer fallback. No findings. |
| `keel/src/keel/steering.py` (+ tests) | **ACCEPT** | No races/lost messages, byte-exact partial output, idempotent abort. No findings. |
| `keel/src/keel/status_page.py` (+ tests) | **ACCEPT** | `not_started` count and IDs added correctly; bucket accounting is exact and honest on the 865-row registry. No findings. |

**Overall:** the batch is not ready to ship as-is. Three High-severity issues (DLP surface leak, pre-dispatch cancellation, silent wrong-line fuzzy edit) and four Medium issues should be fixed before these modules are relied on. The remaining three modules are acceptable.
