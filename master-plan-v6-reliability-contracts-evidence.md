# Addendum 3 - Reliability testing contracts (X9.x P0): implementation evidence

Branch: `agent/a7-x9` (worktree `.../worktree/addenda/a7-x9`)
Baseline: `a454640` (read-only).
Source of requirements: `PLAN-INDEX.json` -> `features[]`, the four
**not_started P0** X9.x rows (milestones M2-M4, source
`Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`, section I "Testing and quality
(beyond B7, C13)"):

| ID | Registry requirement (verbatim) |
| --- | --- |
| X9.1 | "Fixture model server: a local OpenAI-compatible mock that replays scripted tool calls, malformed JSON, partial streams, slow tokens and errors; used by every provider and agent test." |
| X9.3 | "Provider contract tests: each adapter must pass the same behavior suite (streaming, cancel, tool call, usage, errors)." |
| X9.5 | "Cross-platform path/permission matrix tests (Windows reserved names, ADS, long paths, case-insensitive FS, symlinks/junctions)." |
| X9.7 | "Migration matrix: every released schema version upgraded to current, with data checksums." |

This workstream is **additive**: no existing source file, registry row, test or
artifact was edited. The canonical implementation is a new module exercised by
a new, permanent contract-regression test file. The real keel provider adapters
(`OpenAICompatibleAdapter`, `AnthropicAdapter`, `GeminiAdapter`) are imported
lazily by the X9.3 wrapper and are exercised unmodified against the live
loopback fixture server; they are never patched or replaced.

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/reliability_contracts.py` | Canonical implementation of all four X9.x contracts. Stdlib only; typed descriptors, frozen results, canonical-JSON checksums, loopback-only HTTP server, no ambient I/O at import time. |
| `keel/tests/test_reliability_contracts.py` | 39 permanent contract/adversarial tests, grouped by registry ID. |
| `master-plan-v6-reliability-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Primary symbols | Behaviour | Tests |
| --- | --- | --- | --- |
| X9.1 | `ScriptEvent`, `FixtureScript`, `WireFrame`, `FixtureModelServer`, `make_fixture_server`, `standard_scripts`, `render_script`, `RecordedRequest`, `StreamStats` | Validated semantic script -> deterministic wire frames for three dialects; real loopback HTTP server; scripted text, fragmented tool calls, malformed JSON, partial streams, slow tokens, HTTP errors; redacted request log; call budgets | 12 |
| X9.3 | `ProviderContractSuite`, `AdapterBinding`, `KeelAdapter`, `TrackingHTTPTransport`, `CancellingAdapter`, `ContractReport`, `default_bindings` | One 8-case suite (streaming, tool_call, usage, errors, malformed_json, partial_stream, slow_tokens, cancel) run unchanged over all three real adapters; typed error mapping; wire-level truth checks; deterministic fingerprints | 10 |
| X9.5 | `PathCase`, `evaluate_path`, `path_matrix`, `PermissionRequest`, `evaluate_permission`, `permission_matrix`, `MatrixReport` | Windows reserved names/ADS/trailing dots/drive-qualified/UNC, long paths and components, case-insensitive collisions, Unicode normalization, symlink/junction escape; deny-by-default principal x permission matrix with independent expectation oracle | 9 |
| X9.7 | `MigrationMatrix`, `MIGRATIONS`, `RELEASED_VERSIONS`, `build_version_fixture`, `checksum_data`, `payload_view`, `MigrationResult` | All 11 released schema versions upgraded to v11 through real data-preserving transforms; canonical-JSON source/payload checksums; fail-closed on gaps, cycles, downgrades, checksum drift and payload loss | 8 |

## Design decisions worth the lead's attention

1. **The fixture is a real server, not a canned function (X9.1).** It binds only
   `127.0.0.1`/`localhost`/`::1` and refuses any other host. It validates
   Content-Length, rejects non-JSON/non-object bodies, unknown paths, methods
   and models, and answers with typed JSON statuses (400/404/405/413/503).
   `X-Keel-Fixture-Script` or the request `model` selects a script; duplicate
   names/models and ambiguous selectors are rejected at construction.
2. **One semantic script, three wire dialects (X9.1).** `render_script` produces
   OpenAI chat-completions SSE, Anthropic Messages SSE and Gemini
   streamGenerateContent SSE from the *same* descriptor, so an adapter cannot
   pass the suite by special-casing one provider. Frames carry delay, status
   and termination metadata; `StreamStats` records what was actually sent.
3. **Slow tokens are deterministic (X9.1).** Delays are injected through a
   `sleeper` callable (default: no-op) and also recorded on the wire frames.
   Tests use a recording sleeper, so no wall-clock time enters any verdict or
   fingerprint.
4. **Every adapter faces the same 8 cases (X9.3).** `default_bindings()` wires
   the three real keel adapters with a `TrackingHTTPTransport` that uses
   stdlib `urllib` against the loopback server, records the request and closes
   the HTTP response when the consumer cancels. Cancel is verified by an
   actual generator close plus `transport_closed == True`; no event after
   cancellation is counted.
5. **No fake success (X9.3).** `ContractReport.ok` is `all(result.ok ...)`;
   each result compares adapter events with fixture-supplied truth (text, tool
   name/arguments, usage counts), typed error category/status/retryable, and
   wire stats (malformed frames, partial termination, token delays). A broken
   adapter yields failing results, never a pass. A deliberately cut stream may
   not claim reported token counts; malformed frames may not become content.
   `ContractReport.fingerprint` strips the ephemeral loopback port, making it
   stable across processes.
6. **Path verdicts are lexical and deny-by-default (X9.5).** No filesystem call
   can race the verdict or be fooled by a planted symlink: link targets are
   supplied by the caller and resolved against the link's parent, then checked
   for containment. The matrix carries expectations declared *independently*
   of `evaluate_path`; `MatrixReport.ok` means observed verdicts matched every
   expectation (including the adversarial cases that must be blocked). A case
   without an expectation fails closed. Approval/elevation never bypasses an
   unsafe path.
7. **Migrations are verified, not assumed (X9.7).** Released versions mirror
   `fleet.db` (`SCHEMA_VERSION = 11`). Each step performs a real,
   data-preserving edit (new defaulted columns/lists, deterministic task
   positions). Every upgrade recomputes checksums of the stable payload view
   before and after; a changed payload raises `ReliabilityError` rather than
   returning a success report. Canonical JSON (sorted keys, compact
   separators, `allow_nan=False`) makes checksums insertion-order independent
   and strict. Unknown versions, downgrades, missing steps, cycles and
   expected-checksum mismatches all fail closed.

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_reliability_contracts.py']))"
```

Result: **39 passed in 2.15 s** (Python 3.11.9, pytest 9.0.2).
`py_compile` clean on the new module. No existing test file was modified.

### Fix applied during verification

Two specs initially failed with `NameError: name 'PermissionRequest' is not
defined` because the focused import block omitted that symbol; the
implementation was already correct. The import was added (no assertion was
weakened). Both named tests now pass:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_reliability_contracts.py::test_permissions_deny_by_default_and_never_escalate_a_hazard','keel/tests/test_reliability_contracts.py::test_matrix_validation_and_wrong_expectations_fail_closed']))"
```

Result: `2 passed`. One genuine implementation hardening was also added: the
fixture now drains a bounded amount of an oversized request body before
returning 413, so a client writing 1 MiB does not abort the connection before
it can read the typed refusal.

## Integration seams for the lead

This module is deliberately not wired into the live runtime. To adopt it:

1. **X9.1** - use `make_fixture_server()` from `conftest.py` as a session
   fixture and point existing provider tests at `server.base_url`. The standard
   script set is shared; additional scripts are plain `FixtureScript`
   descriptors.
2. **X9.3** - call `ProviderContractSuite().run_all(server)` in CI. Add an
   `AdapterBinding` for any new adapter with its target dialect; the suite
   cases are unchanged.
3. **X9.5** - feed `PathCase`/`PermissionRequest` from real scanner/watcher
   output (the module stays pure). `run_path_matrix`/`run_permission_matrix`
   are drop-in CI checks.
4. **X9.7** - register a new transform in `MIGRATIONS` and append the version
   to `RELEASED_VERSIONS`; `run_all()` then proves every old version upgrades
   without losing payload data.
