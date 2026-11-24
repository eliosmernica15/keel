# Independent test-quality + accounting review — final

Reviewer: `agent/final-review2` (read-only; no tracked source edited).
Scope: `git diff a64cd5d..integration/backend-completion-2026-11-24` (8 implementation
batches + lead fix), focused on tests, docs, accounting and the 421/421 traceability change.

## Verdict

**CONDITIONAL FAIL — 2 HIGH findings must be fixed before delivery.**

The new tests are genuinely behavioral and mutation-sensitive (5/5 sampled tests killed by
a no-op mutation), the registry/accounting arithmetic is exactly correct, and no status was
inflated. However, the **certification/accounting narrative is stale**: all authoritative
docs still report **361/421 traceable + 60 certification-limited**, while the current
verifier reports **421/421 passing** after the traceability batches. Separately, the
"governance gate" that docs call green is **advisory-only** and demonstrably gameable by a
bare string, so its OK exit does not certify evidence.

---

## HIGH 1 — All authoritative docs report 361/421 + 60 limitations; the real gate is 421/421

**Severity: HIGH.** The headline certification number in the normative accounting document
is factually wrong for the delivered tree, and it contradicts another doc in the same set.

Evidence:
- `python scripts/verify_backend_operation.py` (integration HEAD `5996938`) prints:
  `attributed IDs audited: 421`, `passing all checks: 421`, `failing at least one check: 0`.
- `BACKEND-COMPLETION-BACKLOG.md` item 3 (updated in the final batch) says
  `**integrated + pushed** (421/421 now pass)`.
- But `BACKEND-COMPLETION-ACCOUNTING.md` lines 56-57, 73-74, 77 and 126-130 still define
  `T_B = 361`, `L_B = 60`, `completion_backend_certified = 361/421 = 85.7%`,
  `limitation_rate = 60/421 = 14.3%`, and the "one-line authoritative statement" repeats
  85.7% / 14.3%.
- Same stale figure in: `REMAINING-WORK-MATRIX.md` §5 (lines 64-88, titled "current
  authoritative state", lists all 60 IDs as failing); `FINAL-ENGINEERING-REPORT.md`
  lines 189-192; `master-plan-v6-test-evidence.md` line 151 and its appendix ("is restated
  as 361/421 fully traceable + 60 ..."); `keel/docs/IMPLEMENTATION-PROGRESS.md` lines
  1160-1162; `BACKEND-IMPLEMENTATION-DETAIL.md` line 62; `REGISTRY-EVIDENCE-INTEGRITY.md`
  §4 (361/60 result).
- Root cause: docs were written at 17:43-17:45; commits `2b053d2` (18:11) and `e6544a5`
  (18:12) closed all 60 gaps by adding `FEATURE_TRACEABILITY` declarations plus per-ID
  evidence-table rows. No documentation commit followed.
- The fix is **genuine**, not gate-gaming: I AST-verified all 47 declared IDs / 145 named
  symbols across `d6_reliability_backend.py`, `e6_x5_x6_backend.py`, `w7_x1_y5_d1_backend.py`
  and `y2_backend.py` — every named symbol is a real module definition, and the evidence
  docs (e.g. `master-plan-v6-e6-x5-x6-backend-evidence.md`) now contain per-ID rows naming
  real behavioral test functions.

Recommended fix: re-run the verifier, then update all seven documents to the current
`421/421 passing` result (and delete or explicitly mark the 60-ID failure list as
historical). If the team considers the new declarations to be certification-by-declaration
rather than a resolved gap, say so explicitly and make the verifier report the same
number — do not leave two contradictory "authoritative" figures.

---

## HIGH 2 — `verify_backend_operation.py` evidence gate is reported-only and gameable; "governance green" is not an evidence gate

**Severity: HIGH.** Docs cite this script as a passing governance gate
(`FINAL-ENGINEERING-REPORT.md` line 92: "verify_v6_audit.py, verify_backend_operation.py
... all green"), but the script exits 0 with `BACKEND OPERATION VERIFICATION OK` regardless
of how many evidence checks fail.

Evidence (all probes run on a temporary copy, no tracked source changed):
1. **Not enforced.** Zeroed `acceptance_criteria` for one ID (`D6.1`) in `PLAN-INDEX.json`
   and `parity.json`. Verifier output: `passing all checks: 420`, `failing at least one
   check: 1`, `1 x acceptance_criteria empty` — then `exit code: 0` and
   `BACKEND OPERATION VERIFICATION OK`. The script's own docstring (lines 11-33) and code
   (lines 444-452) confirm failures are "reported, not enforced".
2. **Bare string satisfies the test check.** `_test_reference_ok` accepts
   `fid in info["strings"]`. A synthetic test file with **no test function at all**, only
   `LABEL = "D6.1"`, returned `test-reference check passes: True`.
3. **Fake ID survives module + test checks.** A synthetic module with
   `TRACE = {"D6.99": ("RealSymbol",)}` (dict key) plus a test file containing only the
   string `"RealSymbol"` returned `module construct (dict key) passes: True` and
   `test-reference check passes: True`, with zero real test functions. (The evidence-row
   cross-check still failed, but that too is advisory.)
4. Correct behavior confirmed: a bare **comment** does *not* pass the module check
   (`_module_construct_ok` on a file with the ID only in a comment returned `False`), so
   the docstring's "comments and plain strings do NOT count" is true for the module check
   only — not for the test check.

Recommended fix: add an enforced mode (`--strict` / `VERIFY_BACKEND_STRICT=1`) that makes
`gate_failures` non-empty exit 1, and wire it into CI/governance; tighten
`_test_reference_ok` to require the reference to occur inside a real `test*` function
(AST), not any string constant; validate that a declaration's mapped symbols are real
definition names for path (a) as well as path (b). Until then, docs must state that the
script's OK covers only hard checks (counts/paths/existence), not evidence quality.

---

## MEDIUM findings

**M1 — "No normal product workflow directly consumes the backend modules" is now false.**
`FINAL-ENGINEERING-REPORT.md` lines 196-198 and `keel/docs/IMPLEMENTATION-PROGRESS.md`
~1164 still claim an intentional capability boundary "while workflow integration proceeds
in parallel". Batch 1 added `keel/src/keel/backend_workflows.py` wired into
`webapp.py` (`POST /api/backend-workflows/<name>`) and `cli/main.py` (`backend-workflow`
subcommand), with tests `test_webapp_backend_workflow_endpoint_auth_confirm_and_replay`
and `test_cli_backend_workflow_runs_and_replays` in `test_backend_workflows.py` (both pass).
Recommended fix: restate the boundary as "direct consumption now exists through the
new product workflow endpoints; the generic capability surface remains permission-gated".

**M2 — 433/430/2 shown as current in the "Remaining" section of FINAL-ENGINEERING-REPORT.md.**
Lines 31-33 state "Registry: 433 verified / 430 not_started / 2 blocked" and
"Remaining P1/P2 work (430 rows) continues" with no inline historical marker. The
amendment at lines 176-199 later corrects this, but a reader of the top section gets the
wrong current state. Recommended fix: add "(historical snapshot — superseded; see
amendment below)" inline at lines 31-33. (The occurrences in `REMAINING-WORK-MATRIX.md`
lines 124-129 and `IMPLEMENTATION-PROGRESS.md` line 1146 are already labeled historical.)

---

## LOW findings

**L1 — `feature-checklist.md` cross-inventory number off by one.** Accounting §5 says the
rendered tables contain "410 unique contract IDs"; actual table rows = 410, unique IDs =
409 (`S4-PLAN-016` appears twice). The declared total is 398. Recommended fix: say
"410 rows / 409 unique IDs" and use the correct denominator in the bigram-matcher ratios.

**L2 — `BACKLOG-traceability-failures.txt` has no "resolved" header.** It is a bare list of
the 60 now-closed failures. Recommended fix: prepend a line noting all 60 were resolved in
`2b053d2`/`e6544a5` and the current gate is 421/421.

**L3 — declaration-only guards are weak.** The four added
`test_*_feature_traceability_*_maps_real_symbols` tests in `test_d6_reliability_backend.py`,
`test_e5_backend.py`, `test_e6_x5_x6_backend.py` and `test_y2_backend.py` only assert
`set(declaration) == expected` and that each name resolves to `callable(obj) or
isinstance(obj, (type/str/tuple/dict/set/...))`. They test the declaration, not behavior
(behavior is covered elsewhere). Not harmful, but they inflate apparent test count.
Recommended fix: rely on the per-ID behavioral tests and keep declaration checks minimal.

**L4 — "definitive final suite 4071 passed" predates the 8 batches.** 128 tests in the
six new/expanded files pass in the integration tree, but no post-integration full-suite
result is recorded; `master-plan-v6-test-evidence.md` still calls 4071 the definitive
final result. Recommended fix: record a fresh clean-environment full-suite number after
the integration (the backlog correctly labels 4071 as the *baseline*).

---

## Positive findings (verified)

1. **Tests are behavioral, not descriptor-only.** Reviewed all five new files
   (`test_backend_workflows.py`, `test_backend_contracts.py`, `test_backend_events.py`,
   `test_backend_observability.py`, `test_backend_contracts_hardening.py`) plus
   `test_backend_hub_integration.py` and the strengthened bulk tests (`all_31_ids`,
   `all_36_ids`, `all_16_ids`, small-groups registry dispatch). They pin exact outputs,
   typed errors, durable artifacts and concurrency invariants. Targeted run: **128 passed**.
2. **Mutation sensitivity, 5 sampled tests (temp copy, no-op monkeypatch):**
   - `test_request_workflow_executes_real_tool_and_persists` → patch
     `keel.backend_workflows._execute` → **FAILED** (AttributeError at `_finalize`).
   - `test_rehydrate_rebuilds_real_model_route_accepted_by_typed_consumer` → patch
     `keel.backend_contracts.rehydrate` → **FAILED** (AssertionError line 72).
   - `test_replay_from_new_bus_object` → patch `keel.backend_events.EventBus.publish` →
     **FAILED** (AssertionError line 236).
   - `test_hash_chain_detects_tampering` → patch
     `keel.backend_observability.record_event` → **FAILED** (FileNotFoundError).
   - `test_w5_5_registry_dispatch_pins_model_precedence` → source-level mutation of
     `sg.resolve_model_precedence` to `return None` → **FAILED** (`None != 'cli'`).
     Note: runtime monkeypatching the module attribute alone does not kill this test
     because `FEATURE_IMPLEMENTATIONS` binds the function at import time; a source-level
     mutation does. All 5 are therefore mutation-sensitive.
3. **Registry integrity confirmed.** `PLAN-INDEX.json` and `parity.json` are byte-identical
   (SHA-256 `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`), 865 rows,
   854 verified / 9 not_started / 2 blocked. The 9 not_started are exactly the 7 D6
   conventions + W1.18 + Y6.4; blocked are C11.1/C11.2.
4. **Accounting arithmetic confirmed.** 421 attributed + 426 verified-not-attributed +
   3 owner-gated + 3 external + 3 dormant + 9 not_started = 865; verified rows
   421+426+7 = 854; applicable 847/856 = 98.9%; raw 854/865 = 98.7%. Attribution has 421
   unique IDs, all verified; **none** of the 9 excluded owner-gated/external/dormant IDs
   appears in the 421. `backend-final-attribution.json` has 421 unique IDs and the 20
   per-module counts in `BACKEND-IMPLEMENTATION-DETAIL.md` sum to 421. No status inflation.
5. `python scripts/verify_v6_audit.py` → `CONSISTENCY OK`;
   `python scripts/verify_backend_operation.py` → `BACKEND OPERATION VERIFICATION OK`
   (with the HIGH 2 caveat about what "OK" means).
