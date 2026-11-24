# Intelligence contracts — implementation evidence (D7.x P0 assignment)

**Branch:** `agent/a7-d7` · **Baseline:** `a454640`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a7-d7`

## Scope and registry note

The assignment was to implement the `not_started` **P0** `D7.*` rows in
`PLAN-INDEX.json` and to implement the pure memory/provenance/taint/scope/
relevance "intelligence contracts" surface in three new files.

Reading the registry at the assigned baseline found exactly four such rows.
Their full text is reproduced here for traceability:

| ID | Full registry feature text | Detail | Status |
| --- | --- | --- | --- |
| D7.1 | Gate scheduler (`run-gates`): all gates as a dependency graph; bounded concurrency env var; fail-fast switch; a failure skips only its dependents so independent errors all report. | `scripts/run_gates.py` with `KEEL_GATE_CONCURRENCY`, `KEEL_GATE_FAIL_FAST`. | `not_started` / P0 |
| D7.9 | Strict dependency linker so undeclared deps fail; build scripts of dependencies explicitly allowlisted. | `pip-compile`/lockfile with hash pinning; Electron side uses a strict package manager config with an allowlist of postinstall scripts. | `not_started` / P0 |
| D7.12 | CI layout: broad lanes of independent gates, a smaller Node-version compatibility matrix, native Windows lane in a separate workflow, Python checks separate, required benchmarks on standard hosted Linux, real-API e2e in its own workflow, partitioned coverage using per-platform timing data. | CI lanes: gates, matrix (Python 3.11/3.12/3.13), Windows, macOS, benchmarks, provider-e2e (opt-in, self-skips without key). | `not_started` / P0 |
| D7.19 | Benchmark method: drive tasks through the SDK's minimal JSON-RPC agent variant with separate workspaces and session ids per independent task. | Keel benchmark runner uses the `sdk-minimal` profile and isolated workspaces (C13.1). | `not_started` / P0 |

These four rows are all in section "8. Dev workflow, build, CI and release
(new items)" of `Keel_Master_Plan_v6.md` and concern build/CI/release
machinery — **not** memory provenance, taint, scope or intelligence. The
explicit deliverable specification (file names and required behaviour) is
unambiguous, so this change implements that specification: a stdlib-only,
pure descriptor/policy module for memory provenance, taint propagation, scope
separation and deterministic relevance. `PLAN-INDEX.json` and all other
existing files were **not** edited; no row status was changed here.

## Files owned (only these were added)

* NEW `keel/src/keel/intelligence_contracts.py`
* NEW `keel/tests/test_intelligence_contracts.py`
* NEW `master-plan-v6-intelligence-contracts-evidence.md` (this file)

## Required behaviour → implementation map

| Requirement | Contract surface in `keel.intelligence_contracts` |
| --- | --- |
| Memory provenance: source session and tool | `Provenance` (frozen: `source`, `session_id`, `tool_name`, `trust`, `derived_from`, `reviewed_by`), `make_provenance`, `origins()` |
| Taint propagation from untrusted sources (web/doc/MCP) | `is_untrusted_source`, `source_trust`, `UNTRUSTED_SOURCES`, `UNTRUSTED_TOKENS`, `Provenance.tainted`, `MemoryRecord.flags`, default exclusion in `rank_memories` |
| Taint cannot be laundered | lineage-based `tainted`, `derive_provenance`/`derive_memory`, `with_review`/`promote_trust` (annotation only), recomputation in `from_dict` |
| Memory scope separation (shared/per-agent) | `MemoryScope` (`SHARED`/`PER_AGENT`/`UNKNOWN`), `can_access`, `visible_records`, fail-closed owner check |
| Deterministic relevance scoring | `tokenize`, `relevance_score`, `rank_memories`, `RankedMemory`, stable sort key `(-score, memory_id, provenance JSON)` |
| No DB/network/host state | stdlib-only imports (`dataclasses`, `enum`, `json`, `re`, `typing`); no persistence, transport, clock or chance input |

## Verification

Both commands were run from the worktree root with the required `sys.path`
insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_intelligence_contracts.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **42 tests passed in 0.007 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_intelligence_contracts.py']))"
```

Result: **42 passed, 61 subtests passed in 0.76 s**.

## Adversarial coverage (all green)

* **No laundering by relabeling** — deriving from `web_fetch`/`mcp`/`document`
  with `source="assistant"`, `source="user"` or `trust="trusted"` keeps the
  record tainted; six-hop derivation chains keep taint.
* **No laundering by review** — `with_review` and `promote_trust` add an
  annotation but never clear taint; reviewed tainted records stay out of
  default recall.
* **No laundering by serialization** — a tampered payload with
  `"tainted": false`, `"trust": "trusted"` and `"flags": []` is rebuilt with
  taint recomputed from the recorded source lineage.
* **Provenance preserved** — original session/tool/source survive derivation,
  multi-origin merges, record round-trips and ranking results; `origins()`
  always returns the leaf origins.
* **Untrusted content flagged** — web/doc/MCP/group-chat/clipboard/injected
  sources are classified untrusted (including case, prefix and compound
  forms); records carry `tainted` and `untrusted_source` flags and are
  excluded unless `include_tainted=True`, in which case they are penalized.
* **Scope isolation** — per-agent memories are visible only to their owner;
  empty owners, unknown scopes and empty agent ids fail closed; derived
  memories keep scope and owner. A tainted per-agent memory needs both owner
  and explicit `include_tainted` to be recalled.
* **Purity** — a test reads the module source and fails on any DB, network,
  process, clock or chance import/substring; results are frozen dataclasses
  in immutable tuples.

## TDD evidence

`test_intelligence_contracts.py` was written first and run before the module
existed. The run failed at collection with
`ModuleNotFoundError: No module named 'keel.intelligence_contracts'`.
After adding the module, one design bug was diagnosed and fixed: an unknown
scope originally raised a `ValueError` instead of mapping to a fail-closed
`MemoryScope.UNKNOWN`. The suite then reached 42/42 green (also under pytest).

## Design notes

* **Taint is a property of lineage, not a mutable bit.** A derived hop may
  carry any local source/trust claim, but `Provenance.tainted` consults every
  ancestor; a clean result is only possible when all origins are clean. This
  is what makes review, summarization and re-serialization non-laundering.
* **Trust classification is source-driven and fail-closed.** Even an explicit
  caller claim of `trust="trusted"` is downgraded for untrusted sources, and
  any trust value other than the literal `"trusted"` is untrusted.
* **Scope checks are fail-closed.** `SHARED` is public; `PER_AGENT` requires a
  non-empty owner equal to a non-empty agent id; unknown values map to
  `UNKNOWN` and are never visible.
* **Scoring is a pure function of (query, record).** Word-overlap cosine-style
  score, small tag bonus, 0.25 factor for taint, cap at 1.0, rounded to six
  decimals. Ranking is independent of input order thanks to deterministic
  tie-breakers, so it is reproducible across processes and platforms.

## Integration seams for the lead (not made here — file ownership)

1. **Memory writes** — build records with `new_memory(...)` instead of raw
   dicts so source-derived taint and provenance are always present.
2. **Summaries / consolidation / compaction** — use `derive_memory(...)`;
   a tainted source can never produce a clean summary.
3. **Recall** — use `rank_memories(query, records, agent_id=..., include_tainted=False)`;
   only pass `include_tainted=True` for explicit inspection UIs that render
   `record.flags()`.
4. **Agent boundaries** — call `visible_records(records, agent_id=...)` before
   injecting memory into a subagent's context to preserve per-agent scope.
