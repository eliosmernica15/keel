# Master Plan v6 — Repo Map Ranking & Token Counting Evidence (X1.7 / X1.8)

- Branch: `agent/a3-repomap`
- Baseline: `52b752c` (`Record DeepSeek contradicted/unverifiable claims as registry known limitations`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\repomap`
- Files owned (only these were changed):
  - `keel/src/keel/repo_map.py` (new)
  - `keel/tests/test_repo_map.py` (new)
  - `master-plan-v6-repomap-evidence.md` (new)

## Environment note

The editable `keel-harness` install on this machine points at
`C:\Users\Admin\Desktop\Claude clone\keel\src`. The required test command
inserts the worktree copy at `sys.path[0]`, so the new module is the one under
test. No source file or existing test outside the three owned files was edited.

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_repo_map.py']))"
-> 23 passed in ~1.0s
```

## X1.7 — Repo map ranking

Public surface in `keel.repo_map` (stdlib only: `ast`, `math`, `re`,
`threading`, `dataclasses`, `collections.abc`, `typing`):

| Function | Contract |
| --- | --- |
| `build_symbol_graph(files)` | `path -> content` mapping to a bounded `SymbolGraph` of `Symbol` nodes and reference edges. Python uses `ast` with a regex fallback on syntax errors; other languages use conservative `def`/`class`/`function`/`require`/`import` regexes. Binary and >2 MB files are skipped; nodes are capped at `MAX_NODES = 5000`, edges per symbol at 48. Two passes (all nodes first, then edges) make forward references across files resolve; paths and ids are sorted for reproducible output. |
| `page_rank(graph, *, damping=0.85, iterations=64, tolerance=1e-12)` | Deterministic PageRank with no third-party dependency. Edges run referencing -> referenced, so central symbols accumulate mass. Dangling mass is redistributed uniformly, self-edges are ignored, cycles converge, and isolated nodes retain base mass. Scores are normalized to sum to 1. |
| `rank_symbols(graph, recency_weights=None, top_n=50, token_budget=2048, *, counter=None)` | Final score = PageRank × kind prior × (1 + recency). Recency keys are tried as node id, qualified name, short name, then file path and clamped to `[0, 1]`. Ties break on `(-score, -recency, file, name, kind, line)`; scores are rounded to 12 places before comparison. Each line's token cost is measured with `TokenCounter`, cumulative cost is trimmed to `token_budget`, then `top_n` is applied. Returns `RankedSymbol` records with `rank`, `score`, `recency`, `tokens`. |
| `render_repo_map(ranked, budget=2048, *, counter=None)` | Emits complete ranked lines only, in rank order, skipping lines that do not fit and re-checking the whole text against the budget (guards estimator rounding). Deterministic for repeated calls. |
| `build_repo_map(files, recency_weights=None, top_n=50, token_budget=2048, *, counter=None)` | One-shot integration helper returning `graph`, `ranked`, `text`, `tokens`, `symbols`, `shown`. |

Edge cases exercised: empty repository, import and self-reference cycles,
isolated nodes, syntax-error fallback, non-Python sources, binary-file skip,
dict-order independence, a generated `MAX_NODES`-file graph, fixed budgets,
and recency re-ranking.

## X1.8 — Accurate token counting

`TokenCounter(tokenizer_fn=None, *, calibration=None)` is in the same module so
the whole change stays inside the owned file.

- `tokenizer_fn(text) -> int` is the only runtime integration point. It is
  injected by the caller; the class never opens a socket or imports an HTTP
  client. Exceptions, booleans, negative values, floats with fractions and
  non-numeric returns are treated as failures and fall back to the estimator;
  `tokenizer_failures` counts them.
- The fallback is the `keel.context` style `ceil(utf8_bytes / 4)`, with a
  calibration table: `calibrate(samples)` accepts `(text, observed_tokens)`
  tuples or `{"text": ..., "tokens": ...}` mappings, computes the byte-weighted
  aggregate ratio, clamps to `[1.0, 12.0]`, and is idempotent for the same
  samples. Empty/invalid samples leave the ratio untouched.
- `count`, `calibrate`, `set_tokenizer` and all properties are guarded by an
  `RLock`; the injected tokenizer is invoked outside the lock so concurrent
  callers cannot deadlock on a slow runtime callback.
- `ratio`, `bytes_per_token`, `calibration_table`, `sample_count`,
  `tokenizer_failures`, `uses_tokenizer`, `count_batch`, `set_tokenizer` and
  the stateless `estimate_tokens(text)` helper are provided for callers.

## Test matrix (23 tests, all passing)

| Area | Tests |
| --- | --- |
| Graph construction | `test_empty_repository`, `test_python_defs_imports_and_methods`, `test_import_cycle_is_finite_and_converges`, `test_syntax_error_falls_back_to_regex`, `test_non_python_files_use_regex_and_ignore_binary`, `test_build_order_is_deterministic`, `test_huge_graph_is_bounded` |
| Ranking / rendering | `test_pagerank_rewards_inbound_references_and_handles_isolates`, `test_pagerank_self_loop_does_not_trap_mass`, `test_rank_centrality_and_recency_and_top_n`, `test_budget_truncation_is_deterministic_and_bounded`, `test_build_repo_map_end_to_end`, `test_render_repo_map_respects_tighter_budget` |
| Token counting | `test_default_estimator_matches_context_style`, `test_empty_unicode_and_crlf_text`, `test_injected_tokenizer_is_used`, `test_tokenizer_errors_and_bad_returns_fall_back`, `test_calibration_updates_ratio_and_estimates`, `test_calibration_stability_repeated_and_batched`, `test_calibration_ignores_invalid_samples_and_clamps`, `test_calibration_accepts_mapping_samples`, `test_token_counter_is_thread_safe`, `test_module_makes_no_outbound_calls` |

## Integration needs (out of scope: no other files were touched)

1. **Runtime tokenizer endpoint:** the turn loop must construct one
   `TokenCounter(tokenizer_fn=...)` and pass it as `counter=` to `rank_symbols`
   / `render_repo_map` (or store it process-wide). The repo-map module does not
   know any endpoint and deliberately does no network I/O.
2. **Recency source:** supply `recency_weights` from file mtimes, git recency,
   or the existing `repo_index` metadata; keys may be file paths or qualified
   symbol names. Without it the map is pure centrality.
3. **Per-turn budget:** feed the remaining context-window tokens (minus
   reserved output) as `token_budget`; `build_repo_map()` is the single call
   for callers that want the whole pipeline.
4. **Re-export decision:** `TokenCounter` currently lives in `repo_map.py`
   because only that source file was owned. An integrator may re-export it from
   `keel.context` or move it there; no other module was modified here.
5. **Capability/CLI wiring:** no registry or CLI command was added, since that
   would require editing owned-by-others files. `build_repo_map()` is the
   integration seam.

## Known limitations

- The estimator is a heuristic, not a billing estimate; calibration quality is
  bounded by the supplied samples and clamped to `[1, 12]` bytes/token.
- Regex fallback for non-Python sources is deliberately conservative (no full
  language parsers, no third-party dependencies).
- PageRank is recomputed per call; there is no incremental cache across turns.
