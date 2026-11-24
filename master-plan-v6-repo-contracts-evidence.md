# Repository contracts: webhook signatures, evidence cross-walk, artifact handling and crash-safe journal — implementation evidence (Y5.4 / Y6.1 / Y6.2 / Z4 P0 assignment)

**Branch:** `agent/a10-repo` · **Baseline:** `e2121c4`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a10-repo`

## Scope and registry note

The assignment was to implement the `not_started` **P0** rows `Y5.4`, `Y6.1`,
`Y6.2` and `Z4` in `PLAN-INDEX.json` as stdlib-only, pure, fail-closed
contracts, and explicitly **not** `Y6.4` (public repo visibility), which is
owner-gated by gate G1 and conflicts with the private-source requirement.
Reading the registry at the assigned baseline found exactly those four rows:

| ID | Full registry feature text | Detail | M | Status |
| --- | --- | --- | --- | --- |
| Y5.4 | Webhook signature headers and no-secret rejection. | `X-Webhook-Signature` (hex HMAC) + `X-Webhook-Timestamp`; signed payload `timestamp.rawBody`; reject older than 5 min; missing secret means every request is rejected (401). | M3 | `not_started` / P0 |
| Y6.1 | Repo evidence docs cross-walk. | Root `agent-evidence-area*.md` plus checklist/test/benchmark/feasibility/interface/`llm-*` docs; cross-walk each to plan IDs; anything uncovered becomes a row; training-data and model-architecture docs out of scope (Master 4.2.5). | M0 | `not_started` / P0 |
| Y6.2 | `.verify-*` and `.build` artifacts. | Move to `docs/archive/` (private) or ignore; ensure absent from artifacts (artifact allowlist scan). | M0 | `not_started` / P0 |
| Z4 | Crash-safe turn journal. | Write-ahead entry before each tool run, mark done after; on restart show "interrupted tool, retry or skip"; extends Y2.4/Y2.6. | M4 | `not_started` / P0 |

`PLAN-INDEX.json` and every other existing file were **not** edited; no row
status was changed here. This change adds a host-side contract layer only. It
does not claim a real webhook endpoint, real file moves, a real .gitignore
edit, a real release pipeline or a real on-disk journal was shipped end to end.
No file is created, moved, written or deleted by this module.

## Files owned (only these were added)

* NEW `keel/src/keel/repo_contracts.py`
* NEW `keel/tests/test_repo_contracts.py`
* NEW `master-plan-v6-repo-contracts-evidence.md` (this file)

## Requirement → implementation map

| Requirement | Contract surface in `keel.repo_contracts` |
| --- | --- |
| Y5.4 — signature headers and wire format | `SIGNATURE_HEADER = X-Webhook-Signature`, `TIMESTAMP_HEADER = X-Webhook-Timestamp`, `sign_webhook`, `webhook_headers`: lowercase 64-hex HMAC-SHA256 over `str(timestamp) + "." + rawBody`; exactly two headers emitted; no implicit clock or environment |
| Y5.4 — freshness | `DEFAULT_MAX_AGE_SECONDS = 300`, `verify_webhook`: rejects `abs(now - timestamp) > 300` (stale *and* future), caller supplies `now`; strict decimal timestamp parsing, uniform 401 for every bad value |
| Y5.4 — no secret means reject all | `secret_configured`, `_reject(REASON_NO_SECRET)`, `WebhookVerifier`: blank/absent/non-string secret is rejected *before* any signature is examined; signing with no secret raises; never "accept unsigned" |
| Y5.4 — constant time / adversarial | `hmac.compare_digest(expected, signature)`, strict hex shape check, case-insensitive header projection, duplicate-header and non-string-header rejection, bytes-only body, structural misuse raises. An AST/source test pins the constant-time call |
| Y6.1 — required evidence set | `REQUIRED_EVIDENCE_DOCS` (17 root documents), `OUT_OF_SCOPE_DOCS` (`training-data-plan.md`, `model-architecture-proposal.md` per Master 4.2.5), `_validate_documents`, `verify_evidence_documents`: missing/empty documents become explicit rows and errors |
| Y6.1 — cross-walk to plan IDs | `build_cross_walk`, `CrossWalk`, `CrossWalkRow`, `_ID_REF_RE`, `_validate_known_ids`: deterministic, sorted rows; every in-scope document maps to the recognised plan IDs it references; dangling references are surfaced as `unknown_ids` inconsistencies |
| Y6.1 — anything uncovered becomes a row | `STATUS_MISSING`, `STATUS_EMPTY`, `STATUS_UNCOVERED`, `CrossWalk.uncovered`, `verify_cross_walk`, `cross_walk_dict`: uncovered/missing/empty docs are first-class rows and make verification fail closed; out-of-scope docs are recorded in `out_of_scope_ignored`, never treated as uncovered |
| Y6.2 — detection | `classify_path`, `is_publishable`, `scan_artifacts`, `ArtifactScan`: any path segment `.build` or starting `.verify-` (casefolded, `/` and `\` accepted) is an artifact; traversal, absolute/drive/UNC, encoded traversal, control chars and non-strings fail closed |
| Y6.2 — ignore, exclude, no deletion | `GITIGNORE_PATTERNS`, `gitignore_patterns`, `make_allowlist`, `is_allowed`, `filter_publishable`, `artifact_disposition`, `Disposition`: only `ignore`, `exclude_from_publish`, `publish` actions exist; an explicit `_FORBIDDEN_ACTIONS` guard and tests enforce that deletion is never an option; no file is touched |
| Y6.2 — artifact allowlist scan | `validate_artifact_scan`: an artifact or wildcard smuggled into an allowlist is reported; canonicalisation collapses equivalent spellings without widening the allowlist |
| Z4 — write-ahead journal | `Journal.begin_tool` / `Journal.finish_tool` / `_commit`, `MemorySink.append`: one newline-terminated, checksummed, hash-chained record per atomic append; a start is durable before the tool runs, a done only after its result exists |
| Z4 — atomic recovery / exact resume point | `recover`, `RecoveryDescriptor`, `InterruptedTool`: parsing stops at the first incomplete/corrupt/out-of-order record, reports `tail_discarded`, `durable_bytes`, `errors` and the pending tools; a torn `tool_done` leaves its `tool_started` pending |
| Z4 — retry or skip / no I/O | `interrupted_tool_prompt` emits the exact phrase `interrupted tool, retry or skip`; `RecoveryAction`, `RecoveryDescriptor.actions`, `resume_journal`, `Journal.from_records`: rebuild from durable records only, continue with `seq + 1` and the correct `prev` digest. All storage is an in-memory `MemorySink`; no real I/O |
| Cross-cutting purity | imports limited to `__future__`, `dataclasses`, `enum`, `hashlib`, `hmac`, `json`, `re`, `typing`; no process, file, network, clock, chance or environment access; AST tests enforce it. Every malformed or unknown value fails closed |

## Exact fixes applied after the initial failing run

The first run surfaced 8 failures; the reported 5 included the two journal
tests. All were resolved without relaxing an assertion:

1. **Cross-walk ID regex (implementation, real bug).** `_ID_REF_RE` originally
   used the lookahead `(?![A-Za-z0-9_.])`, so a plan ID at the end of a sentence
   (`"Maps to Z4."`) was not recognised and produced a spurious `uncovered`
   row. The lookahead is now `(?![A-Za-z0-9]|\.[0-9])`: a trailing full stop is
   punctuation, but an adjacent alphanumeric or `.` followed by a digit still
   blocks the match (so `Y6.1x` and a longer numeric ID cannot be truncated).
2. **`known_ids=None` (implementation, real bug).** The shared iterable helper
   treated `None` as an empty sequence, so a missing plan registry silently
   produced "all uncovered" instead of failing closed. `_validate_known_ids`
   now rejects `None` explicitly.
3. **Purity AST guard (implementation).** `_path_segments` used
   `text.replace("\\", "/")`; the method name `replace` was caught by the
   no-host-effects guard intended for `os.replace`. The implementation now
   uses `re.sub(r"\\", "/", text)` — same canonicalisation, no ambiguous call.
4. **Allowlist test scenario (test setup corrected, assertion strengthened).**
   The duplicate-entry probe used `["a", "a\\b", "a/b"]`, where `a` is a
   distinct path, so the dedupe expectation was wrong. It now uses three
   spellings of the *same* path (`a/b`, `a\b`, `a/b`), still asserting exactly
   one canonical entry.
5. **Torn-tail journal scenarios (test setup corrected, assertions kept).**
   Both tests cut 9 bytes from a two-record journal, which tore the *only*
   `tool_done` — the implementation correctly reported `seq=1` and an
   interrupted tool. Each scenario now writes a third record before tearing
   it, so two complete records (start + matching done) are durable. All
   original assertions (`seq=2`, exact `durable_bytes`, no interrupted tool,
   resume at `seq=3` with the correct `prev`) are unchanged and now actually
   exercise a torn tail after a completed tool run.

Final analysis: the two reported journal failures were misconstructed test
scenarios, not a journal defect — a torn `tool_done` is *supposed* to leave an
interrupted tool. The three genuine defects were the ID regex, `None` registry
handling and the ambiguous `replace` call.

## Verification

Run from the worktree root with the standard `sys.path` insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_repo_contracts.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **59 tests passed in 0.069 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_repo_contracts.py']))"
```

Result: **59 passed, 604 subtests passed in 1.21 s** (pytest 9.0.2, Python 3.11.9).

Related-regression subset (webhooks, webhook security, gate scheduler, repo hygiene, new suite):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_gate_scheduler.py','keel/tests/test_webhooks.py','keel/tests/test_webhook_security.py','keel/tests/test_repo_hygiene.py','keel/tests/test_repo_contracts.py']))"
```

Result: **160 passed, 1310 subtests passed in 6.23 s**.

The change is purely additive (three untracked new files, no existing file
edited). Y6.4 was deliberately not implemented: it is owner-gated and would
conflict with the private-source requirement.
