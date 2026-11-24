# Master Plan v6 — Edit Formats Evidence (X1.4 + X1.5)

- **Branch:** `agent/a3-patches`
- **Baseline:** `52b752c` ("Record DeepSeek contradicted/unverifiable claims as registry known limitations")
- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\patches`
- **Scope:** feature IDs X1.4 (Selectable edit formats per model) and X1.5
  (Fuzzy patch application), both M5 / P0, from the reconciled registry
  (`PLAN-INDEX.json`, rows sourced from `Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`).

> Constraint honored: I edited **only** the four files I own — the new module
> `keel/src/keel/edit_formats.py`, the new test `keel/tests/test_edit_formats.py`,
> the clean-room behavior spec `keel/docs/research/edit-format-behavior.md`,
> and this evidence file. No other source file or existing test was touched.
> Files that need follow-up changes are called out exactly in §5; they were
> read only.

---

## 1. What was implemented

### 1.1 X1.4 — selectable edit formats

`keel/src/keel/edit_formats.py` provides:

- Constants `FORMAT_WHOLE_FILE`, `FORMAT_SEARCH_REPLACE`,
  `FORMAT_UNIFIED_DIFF`, `FORMAT_LINE_RANGE`, `SUPPORTED_FORMATS`,
  `DEFAULT_FORMAT`, `DEFAULT_THRESHOLD`.
- `detect_edit_format(text)` → canonical format id; plus
  `detect_edit_format_details(text)` → `FormatDetection` with confidence,
  reason and detected markers. Detection precedence is fixed and documented:
  `*** Begin Patch` → search/replace markers → unified-diff hunk header →
  line-range header → whole-file fallback.
- `apply_edit(original, edit_text, format=None, *, threshold=0.8)` → new
  content, or a typed error. An explicit format always beats detection;
  `None`/`"auto"` detects. Supported dialects:
  - whole-file (verbatim replacement, byte-exact no-op),
  - search/replace with `<<<<<<< SEARCH`/`=======`/`>>>>>>> REPLACE`,
    `<<< SEARCH >>>`/`<<< DIVIDER >>>`/`<<< REPLACE >>>`,
    `<search>`/`</search>`/`<replace>`/`</replace>`, and `*** Begin Patch`
    (`*** Update File:`, `@@` section anchors, `*** Add File:`,
    `*** Delete File:`),
  - unified diff (multi-hunk, count validation, cumulative anchor adjustment,
    all-`+` insertions, `\ No newline at end of file` marker ignored),
  - line-range (`[lines 3-5]`, `L7`, `line 2 through 4`, `to`/`..` variants).
- `recommend_format(model_id, eval_stats)` → deterministic canonical format;
  `recommend_format_details(...)` → `FormatRecommendation` with `source`
  (`eval`/`default`), all smoothed scores and the model id.

### 1.2 X1.5 — fuzzy patch application

- `fuzzy_replace(original, old, new, threshold=0.8, *, anchor=None)` →
  `(result, MatchInfo)`. `MatchInfo` records the 0-based/1-based span, score,
  normalization strategy used, `no_op`, applied indentation delta and anchor.
- Five normalization levels (`exact`, `rstrip`, `collapsed`, `indentless`,
  `compact`) scored with `difflib.SequenceMatcher`; each score is reduced by an
  indentation penalty so uniform shifts are tolerated but indentation is used
  to prefer the right candidate.
- Strict same-line-count windows; `threshold` gate; ambiguity guard (multiple
  equally good candidates are refused, never resolved by "first match wins");
  anchor hints only break exact ties.
- Typed errors: `EditFormatError` base, `EditParseError` (malformed patch,
  `truncated_diff`, `out_of_range`, `unsupported_format`, ...), and
  `FuzzyMatchError` (`no_match`, `ambiguous_match`, `empty_search`,
  `invalid_threshold`). Each error carries `code`, `message`, `line`,
  `snippet`, `similarity` and `candidates`; `to_model_message()` renders a
  model-facing report with the nearest-match snippet and line number.
- Line-ending-safe application: replacements inherit the replaced region's
  CRLF/LF/CR separators; indentation deltas are transferred to new lines;
  no-op edits return the original string byte-for-byte.

Stdlib only: `re`, `difflib`, `dataclasses`, `typing`. No third-party imports,
no filesystem access, no network access.

### 1.3 Clean-room behavior spec

`keel/docs/research/edit-format-behavior.md` records the behavior contract
(detection precedence, all accepted marker syntaxes, scoring and guards,
error/report shape, recommender tie-breaks) with an explicit provenance
statement. No external reference implementation was cloned or read; it is
derived solely from the reconciled registry rows.

---

## 2. Test coverage

`keel/tests/test_edit_formats.py` — **26 tests, all passing**, covering every
scenario named in the task and the dialect-specific edges:

| Area | Tests |
|---|---|
| Detection | whole-file default, all four search/replace marker families, unified diff, line range, format aliases |
| Application | whole-file + no-op, Aider single/multiple blocks, `*** Begin Patch` with context/anchor, custom markers, unified diff single/multiple hunks, truncated diff, line-range replace/single-line/out-of-range, invalid format, chained blocks with adjusted anchors |
| Fuzzy matching | trailing whitespace, collapsed whitespace, indentation shift with re-indentation, indentation-aware disambiguation, ambiguous matches, no-match nearest snippet/line, below-threshold rejection, invalid threshold, empty search |
| Robustness | CRLF/LF preservation, unicode (`café`, `☕`, `日本`, full-width `＝`), 20,000-line file, exact no-op preservation |
| Recommendation | eval-driven choice, per-model isolation, determinism and preference tie-break, details record, missing/malformed stats fallback |

Command and result (run from the worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_edit_formats.py']))"
..........................                                               [100%]
26 passed in 3.46s
```

No skips, no xfails, no tools failed. The required command is reproduced
verbatim and passed.

---

## 3. Design decisions worth reviewing

1. **Ambiguity is an error, not a heuristic choice.** Two equally scored
   windows raise `ambiguous_match` even when one is "obviously" right to a
   human. This is the strongest form of the "never silently apply a wrong
   match" guard. Callers can pass a unique anchor (from a diff hunk header, a
   `@@` section header, or explicitly to `fuzzy_replace`) to break the tie.
2. **Indentation penalty is capped at 0.20** (`0.03` per column). A four-space
   shift costs 0.12, so a text-identical, shifted candidate still clears the
   default 0.80 threshold, while an eight-space competitor (0.24) does not.
3. **Recommender uses Laplace smoothing and a fixed preference order**, not
   model-family priors. No reliability claim about a vendor is encoded; a
   single successful trial yields `(1+1)/(1+2) ≈ 0.667`, below a well-measured
   alternative. This keeps the router deterministic and evidence-driven.
4. **No filesystem side effects.** The module returns new content; writing it
   remains the caller's responsibility. This makes it safe to unit-test and to
   call from a planner/router before any permission-gated write.
5. **Detection is conservative but not clairvoyant.** A whole-file replacement
   containing a literal marker line is misdetected; callers that know the
   dialect must pass `format` explicitly. This is documented in the spec.

---

## 4. Known limitations

- `*** Begin Patch` file paths are parsed but not resolved; the applier always
  edits the single `original` string it was given. A multi-file patch caller
  must split it per file before calling.
- No rename/binary/mode-change semantics; this is a text-only layer.
- The recommender consumes local eval stats but does not collect them; an
  evaluation harness must feed it `successes`/`attempts` per format per model.
- Unified-diff count validation rejects diffs whose trailing newline was cut
  off mid-hunk. That is intentional (the task requires a precise error for a
  truncated diff), but a model emitting a hunk without a final newline may see
  `truncated_diff` even when the missing content was only whitespace.
- Complexity is O(lines × search-lines × 5) per block. The 20,000-line test
  completes in well under a second; extremely large files with very long
  search blocks should be chunked by the caller.

---

## 5. Integration needs (for the lead; not performed here)

These files were **not** modified because they are outside this task's
ownership. All are straightforward additive hooks:

1. **`keel/src/keel/tools/native.py`** — the existing `apply_patch` tool schema
   (`path`, `old_string`, `new_string`) currently documents itself as
   "Exact-match edit of a text file". Its handler should call
   `fuzzy_replace(existing_text, old_string, new_string)` and, on
   `FuzzyMatchError`, return `error.to_model_message()` to the model so the
   nearest-match evidence is visible. This is feature Y1.2's natural landing
   spot for the tool-exposure table.
2. **`keel/src/keel/model_router.py`** (or the model-selection/config layer) —
   call `recommend_format(model_id, eval_stats)` when building an edit prompt,
   inject the returned format id into the tool description, and persist the
   eval counters in the shape documented in §6 of the behavior spec.
3. **`keel/src/keel/eval_tools.py`** — feed measured
   `successes`/`attempts` per `(model_id, format)` into the recommender's
   `eval_stats` mapping; add a regression harness that runs the same edit task
   across the four formats and records each model's reliability.
4. **`keel/src/keel/commands.py` / `keel/src/keel/webapp.py`** — optional: expose
   a settings toggle for the default edit format and the fuzzy threshold
   (`DEFAULT_THRESHOLD = 0.8`), validating threshold values through
   `_check_threshold`.
5. **Registry bookkeeping** — `PLAN-INDEX.json`, `parity.json`,
   `master-plan-v6-final-matrix.csv/.json`, `REMAINING-WORK-MATRIX.md` and
   `DEPENDENCY-GRAPH.md` still list X1.4/X1.5 as `not_started` and
   "source_file_missing, test_file_missing". They are generated/reconciled
   artifacts outside this task's file ownership; the lead should regenerate
   them from the new source/test paths. Y1.2's `GATE: X1.4 (not_started)` note
   can then be cleared.

---

## 6. Commit

Single commit on `agent/a3-patches`, containing exactly the four owned files.
No push was performed. The commit SHA is reported in the agent's final message.
