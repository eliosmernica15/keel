# Invariant contracts - implementation evidence (a9-v P0 assignment)

**Branch:** `agent/a9-v` **Baseline:** `f2c0fe6`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a9-v`

## Scope and registry note

The assignment was to implement the seven `not_started` **P0** `V*` rows from
`PLAN-INDEX.json` as a stdlib-only, pure, fail-closed contract surface. Reading
the registry at the assigned baseline found exactly these rows (full text):

| ID | Full registry feature text | Detail | Milestone | Status |
| --- | --- | --- | --- | --- |
| V1 | Plugin scope tree (lifecycle-safe plugins): every plugin runs in a scope that records what it registered (tools, hooks, routes, UI panels, timers, subprocesses); unload/reload disposes all of it automatically; child scopes inherit parent permissions only down, never up. | Python context manager tree; registration functions return disposables attached to the active scope; test by loading/unloading a plugin 100 times and asserting zero leaked handlers/processes. Underpins W1.1, hot reload (Y1.31) and safe mode. | M10 | `not_started` / P0 |
| V2 | Policy simulator with "winning rule" trace: shows ordered rules, which matched, which won, why a multi-resource op was denied, and the Tier-2 verdict. | Reuse the matcher; output a JSON trace rendered in the UI and `keel policy test`. Required by C-1. | M3 | `not_started` / P0 |
| V5 | Strictness presets (Cautious/Balanced/Trusted as ordered rule sets). | (see feature text; implemented as ordered rule sets on the V2 matcher.) | - | `not_started` / P0 |
| V16 | Keel invariant-gate catalog: a list of gates specific to Keel: Tier-2 table hash unchanged; no outbound network in offline suite; no secret in logs; every tool has a presenter; every plugin manifest declares permissions; no hardcoded UI copy; migration compat matrix; no `Any` baseline growth. | Create `gates/` with one script per invariant; each gate has a failing-fixture test proving it rejects bad input (D6.25). | M0 | `not_started` / P0 |
| V24 | Tool conformance kit: one automated suite every tool must pass: output schema declared, presenter pure on replay, cancel honored within N ms, no leaked fields in schemas(), concurrency flag only on read-only tools, timeout cooperative, errors typed. | Table-driven pytest over the registry; fails CI on any new tool that doesn't register conformance metadata. Implements E1.x/E2.x checks. | M5 | `not_started` / P0 |
| V26 | Request-reconstruction test: replay a session log and rebuild the exact provider request; byte-compare with what was actually sent (hash) to prove "model-visible = logged" (D2.11). | Store request hash per step; test recomputes from log. | M4 | `not_started` / P0 |
| V31 | Local-socket transport spike: prove Electron ↔ Python over named pipe/UDS with streaming and backpressure on all three OSes before committing (C-19); keep TCP+token as fallback. | 1-week spike with benchmark; decide via DECISIONS.md. | M19 | `not_started` / P0 |

The registry describes product work (UI trace rendering, CLI command, real
sockets, a benchmark, CI wiring). The explicit assignment is the *descriptor /
checker* layer those deliverables consume, so this change implements that
layer in one additive module. `PLAN-INDEX.json` and all existing files were
**not** edited; no row status was changed here. This evidence does not claim
that the live `keel policy test` command, UI rendering, real sockets, the
one-week benchmark, CI wiring or signed decisions were shipped.

## Files owned (only these were added)

* NEW `keel/src/keel/invariant_contracts.py`
* NEW `keel/tests/test_invariant_contracts.py`
* NEW `master-plan-v6-invariant-contracts-evidence.md` (this file)

No existing module was modified. In particular, V24 is a standalone
descriptor/checker and does **not** import or duplicate `keel.tool_contracts`;
V26 replays caller-supplied log data and does **not** import
`keel.session_contracts`.

## Required behaviour - implementation map

| Requirement | Contract surface in `keel.invariant_contracts` |
| --- | --- |
| V1 scope tree, disposables, zero leaks | `Scope`, `plugin_scope`, `register`, `active_scope`, `Disposable` (idempotent `close`), `REGISTRATION_KINDS` (tool/hook/route/ui_panel/timer/subprocess), LIFO disposal in `close()` including children, `live_disposables` / `assert_no_leaks`; a registration outside a live scope raises `ScopeError` |
| V1 downward-only permissions | `Scope._permissions`, `has_permission`, `require_permission`, `grant_permission`, `effective_permissions`; a child's set is validated as a subset of its parent's at construction, escalation fails closed, parent never sees child-only permissions, closed scopes report no permissions |
| V2 winning-rule trace | `Rule` / `make_rule`, `Operation` / `make_operation`, `simulate`, `SimulationTrace.to_dict()` / `to_json()`, `RuleEvaluation`, `ResourceDecision` - ordered evaluations, per-resource winners, earliest deny wins, default deny, explicit `denial_reason` for multi-resource ops, `Tier2Verdict` (`not_applicable`/`pass`/`requires_approval`/`blocked`) |
| V5 strictness presets | `Strictness`, `STRICTNESS_ORDER`, `preset_rules`, `describe_preset`; Cautious / Balanced / Trusted are ordered `Rule` tuples, deny-first, monotonically more permissive, secret resources always denied |
| V16 invariant-gate catalog | `GATE_CATALOG` (8 gates), `Gate`, `GateResult`, `compute_tier2_hash`, `check_gate`, `run_all_gates`, `all_gates_pass`, `gate_fixture_result`, `check_all_failing_fixtures`; each gate carries its own `failing_fixture` and rejects it |
| V24 tool conformance kit | `ConformanceCheck` / `CONFORMANCE_CHECKS` (7 checks), `check_tool_conformance`, `ConformanceReport`, `conformance_gate`, `ConformanceGateReport`, `assert_conformant`, `conformant_metadata`, `failing_conformance_metadata`; missing metadata fails the gate so CI can gate new tools |
| V26 request reconstruction | `record_request` / `RequestRecord` (hash bound per step), `reconstruct_request`, `verify_reconstruction`, `ReconstructionResult`, `session_log_fixture`, `tamper_log`; canonical SHA-256 of the rebuilt request, optional byte-compare against the actually-sent request |
| V31 transport spike descriptor | `Transport`, `TransportDescriptor`, `TRANSPORT_CANDIDATES`, `validate_transport`, `platform_support`, `select_transport`, `SpikeDecision`, `evaluate_spike` / `spike_decision`; named pipe (Windows), UDS (Linux/macOS), loopback TCP+token fallback, streaming/backpressure/peer-auth criteria; no socket API is imported or called |
| Purity / fail-closed | stdlib-only imports (`fnmatch`, `hashlib`, `json`, `re`, `threading`, `weakref`, `dataclasses`, `enum`, `typing`); a source-AST test asserts no `socket`/`subprocess`/`time`/`random`/`os`/`pathlib`/`http`/`urllib`/`keel` import; all malformed/unknown values raise `ContractValidationError` (scrubbed) or produce a failing result |

## Verification

Both commands were run from the worktree root with the required `sys.path`
insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_invariant_contracts.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **56 tests passed in 0.040 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_invariant_contracts.py']))"
```

Result: **56 passed, 63 subtests passed in 0.90 s**.

## Adversarial coverage (all green)

* **V1 leaks** - a plugin with all six registration kinds is loaded/unloaded
  100 times; a shared live-handle counter returns to zero, `live_disposables()`
  is empty and `assert_no_leaks()` passes. Disposal order is asserted LIFO,
  child scopes are disposed by their parent, double-close is a no-op, and a
  deliberately leaked timer is detected. Registrations outside a live scope,
  on a closed scope, with an unknown kind or a non-callable disposer all fail
  closed. A child cannot be created with (or granted) a parent-unheld
  permission, and cannot re-enter after close.
* **V2 traces** - an allow rule ordered before a deny rule still loses; the
  winning rule id, ordered evaluation list and `matched` flags are asserted;
  a multi-resource write to `file:ok` + `secret:key` is denied with the exact
  resource and deny-rule name in the reason; default-deny is verified; all
  four Tier-2 verdicts are reached; malformed rules/operations and a
  non-bool approval flag raise.
* **V5 presets** - the three presets are ordered, uniquely identified rule
  sets; allowed-set monotonicity holds for read/write/exec; secret reads are
  denied under every preset; Cautious requires Tier-2 approval while Balanced
  carries the acknowledgement; unknown preset names raise.
* **V16 gates** - all eight gates reject their own failing fixtures; a good
  observation set passes all eight; a changed Tier-2 table fails the hash
  gate; an empty observation set fails every gate; a literal API key in a log
  line fails the gate and is `[REDACTED]` in the reason; malformed
  observations and unknown gate ids fail closed.
* **V24 conformance** - a fully conformant tool passes; each of the seven
  checks has a failing fixture that is rejected; an unregistered tool fails
  `conformance_gate` with its name in `missing_metadata`;
  `assert_conformant` raises for both failing and missing metadata; non-mapping
  input and unknown check ids raise.
* **V26 reconstruction** - the rebuilt request hashes to the recorded step
  hash and matches the sent request byte-for-byte; five independent tamper
  cases (model, system prompt, message content, parameter value, added
  parameter) and a truncated log all change the hash and fail verification;
  a mismatched sent request and a wrong expected hash fail; unknown event
  kinds, wrong field types, a missing model and a bad expected hash all fail
  closed.
* **V31 spike** - all three OSes map to viable primaries (named pipe on
  Windows, UDS on Linux/macOS), TCP+token is the declared fallback, the
  decision record is complete and deterministic; unsupported transports/OSes
  and a non-viable descriptor are rejected. The source-AST test proves no
  socket is ever imported.

## Limitations / integration seams

* V2 emits a canonical JSON trace through `SimulationTrace.to_json()` for a
  future `keel policy test` command and UI renderer; the CLI command and UI
  are not part of this additive module.
* V16 models gates as one checker per invariant in a single catalog rather
  than a literal `gates/` directory of scripts; the fixtures are data, not a
  pytest plugin. Wiring the catalog into CI is a lead decision.
* V24 is a descriptor/checker over caller-supplied metadata; the real tool
  registry is not introspected here and `assert_conformant` is the CI seam.
* V26 verifies caller-supplied log records and hashes; it does not read a real
  session file or intercept a live provider call.
* V31 is descriptor-level only: no socket is opened, no benchmark is run and
  no `DECISIONS.md` entry is made (a real spike and OS acceptance are still
  required before committing to the transport).
