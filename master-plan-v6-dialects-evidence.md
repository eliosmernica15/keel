# Addendum 3 dialects — implementation evidence (X1.1, X1.2, X1.3)

**Branch:** `agent/a3-dialects` · **Baseline:** `52b752c`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\dialects`

## Scope

Implemented the three P0 rows from the reconciled 865-row registry:

| ID | Registry feature | Implementation |
| --- | --- | --- |
| X1.1 | Tool-call dialect adapters | `detect_dialect`, `detect_dialect_scores`, `parse_tool_calls`, `format_tool_call`, `dialect_for_model_family`, `select_dialect_for_model`; `ToolCall`, `DIALECTS`, `DIALECT_PRIORITY` |
| X1.2 | Chat-template handling | `load_chat_template`, `template_warning`; `ChatTemplateRecord` and contained catalog readers |
| X1.3 | Reasoning-model output handling | `split_reasoning`, `strip_reasoning`, `collapse_reasoning`, `should_include_in_history`, `count_reasoning_tokens`, `count_total_reasoning_tokens`; `ReasoningBlock` |

## Files owned (only these were changed)

* NEW `keel/src/keel/model_dialects.py`
* NEW `keel/tests/test_model_dialects.py`
* NEW `keel/docs/research/model-dialect-behavior.md`
* NEW `master-plan-v6-dialects-evidence.md` (this file)

`PLAN-INDEX.json`, other source modules and existing tests were **not** edited.

## Verification

Command (run from the worktree root, exactly as specified):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_model_dialects.py']))"
```

Result: **70 passed, 1 skipped** in ~1 s.

The single skip is the symlink-escape case (`test_load_chat_template_rejects_symlink_escape`):
this Windows host cannot create the test symlink without elevated/developer
mode. Containment is still exercised by the traversal-model-id matrix (10
cases) and the `template_file: ../outside-template.txt` escape case; the
`realpath` + `commonpath` guard covers symlinks in code.

### Edge cases explicitly covered (tests first, then implementation)

* truncated JSON tool call → partial name/arguments recovered, `incomplete=True`
* nested XML / repeated tag names / nested parameter tags → structured dicts
* conflicting dialects → deterministic, stable `detect_dialect` choice
* path traversal in `model_id` (relative, absolute, Windows drive, encoded, doubled separators, dot segments) → `ValueError`
* traversal in catalog `template_file` → rejected with warning, inline template retained
* oversized reasoning block (200 000 chars) → single linear scan, exact content preserved
* unicode (CJK, emoji, full-width dialect/reasoning tokens) → preserved and byte-counted

## TDD evidence

`test_model_dialects.py` was written and executed before the module existed;
collection failed with `ModuleNotFoundError: No module named
'keel.model_dialects'`. After implementation the same command reports the
green result above. Seven intermediate failures (container-tag descent, XML
entity unescaping, override path depth, template_file warning, and
pipe-style reasoning close tags) were diagnosed and fixed against the tests.

## Design notes

* Stdlib only; no network, `eval`, `exec` or subprocess. Tool calls are inert
  data records, never executed by the adapter.
* Detection scores are exposed and tie-broken by a fixed priority order; probe
  results and model-family inference provide per-model overrides.
* Reasoning is excluded from history by default (`should_include_in_history`
  returns `False` unless an explicit opt-in keyword is passed) and is counted
  in budgets via Keel's stable `estimate_tokens` heuristic from
  `keel/context.py`, with an identical local fallback.
* Full behavior spec and clean-room provenance:
  `keel/docs/research/model-dialect-behavior.md`.

## Integration changes needed by the lead (not made here — file ownership)

1. **X1.1 / X1.3 normalization in the turn loop.** In `keel/src/keel/session.py`
   the model result is consumed at `blocks = self.model.complete(...)` (around
   line 821) and split into `tool_blocks` / `text_blocks` (around line 854).
   For local-model adapters that return text blocks containing encoded calls,
   run `visible, reasoning = split_reasoning(text)` first, then
   `parse_tool_calls(visible, dialect=<selected>)` and map each `ToolCall` to
   the existing `{"type": "tool_use", "id", "name", "input"}` shape (use
   `call.call_id` or a generated id). Keep `reasoning` only for the UI. Skip
   any call with `call.incomplete=True` until X1.11 provides validated
   streaming parsing, or surface it as a recoverable parse error.
2. **X1.2 model configuration.** When a model/runtime is configured, call
   `load_chat_template(model_id, <offline catalog root>)` and surface
   `record.warnings` (including `template_warning`) in the model picker / logs;
   pass `select_dialect_for_model(model_id, probe_results)` (or the catalog
   override's `dialect`) as the dialect argument in step 1.
3. **X1.3 UI + budgets.** Render the `ReasoningBlock` list in a collapsible
   detail widget (data and `collapse_reasoning` placeholder are provided).
   Add `count_total_reasoning_tokens(raw_output)` to the context-budget
   calculation alongside `keel.context.estimate_tokens`, and keep reasoning
   blocks out of `outbound_messages` unless the user opts in via
   `should_include_in_history(..., include_reasoning_in_history=True)`.
4. **Registry bookkeeping (lead).** Flip `X1.1`, `X1.2`, `X1.3` in
   `PLAN-INDEX.json` to implemented with the test reference
   `keel/tests/test_model_dialects.py`; this subagent was explicitly told not
   to edit that file.
