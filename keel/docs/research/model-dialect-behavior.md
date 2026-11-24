# Model dialect behavior — X1.1 / X1.2 / X1.3

**Status:** implemented (Addendum 3, reconciled 865-row registry, all P0).
**Module:** `keel/src/keel/model_dialects.py`
**Tests:** `keel/tests/test_model_dialects.py`

## Provenance

This document is a **clean-room behavior specification**. It was derived only
from:

1. the reconciled registry rows `X1.1`, `X1.2`, `X1.3` in `PLAN-INDEX.json`;
2. their source table in `keel/docs/plan-sources/Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`
   (section A, "Model dialects and local-model reliability");
3. Keel's own terminology and conventions as used in `keel/context.py`
   (stable byte-length token estimate, budget accounting) and the surrounding
   test style.

No reference implementation, vendor SDK source, or repository code was copied,
transcribed, or consulted. The wire formats described below are public,
observable text encodings — they are **facts about model output**, not code.
Where this document names a model family, it does so only to explain which
observable markers the deterministic heuristics look for; it makes no claim
about a model's internal design or about any vendor's intent.

Safety invariants, by construction:

* standard library only;
* no network calls;
* no `eval`, `exec`, `subprocess`, or dynamic code loading; tool calls are
  returned as inert `ToolCall` records and are never executed by this module;
* the sole filesystem access is the offline catalog reader, which enforces
  path containment including symlink resolution.

---

## X1.1 — Tool-call dialect adapters

### Supported dialects

| Dialect name | Observable markers used for detection | Emitter shape |
| --- | --- | --- |
| `json` | JSON object containing `name`/`tool`/`function` together with `arguments`/`args`/`parameters`, including `tool_calls` batches and fenced blocks | `{"name": ..., "arguments": {...}}` |
| `xml` | `<tool_call>`, `<function_call>`, `<invoke>`, `<tool_name>`, `<parameters>` tags | `<tool_call><name>…</name><arguments>{…}</arguments></tool_call>` |
| `hermes` | `to=functions.<name>`, `<|channel|>`, ChatML `<|im_start|>` | `<|im_start|>assistant<|channel|>commentary to=functions.<name> <|constrain|>json\n{…}<|im_end|>` |
| `react` | `Action:` plus `Action Input:` / `Thought:` / `Observation:` | `Action: <name>\nAction Input: {…}` |
| `mistral` | `[TOOL_CALLS]` / `[TOOL_CALL]` prefix | `[TOOL_CALLS] [{…}]` |
| `qwen` | `<tool_call>` whose body starts with a JSON object | `<tool_call>\n{…}\n</tool_call>` |
| `deepseek` | full-width `<｜tool▁call▁begin｜>` family of tokens (ASCII-normalised before parsing) | `<｜tool▁calls▁begin｜>…<｜tool▁calls▁end｜>` |
| `llama` | no unique marker — a JSON-shaped alias, selected via probe or family inference | same as `json` |

### Detection contract

`detect_dialect(text)` is deterministic and side-effect free.
`detect_dialect_scores(text)` exposes the evidence:

* strong unique markers (DeepSeek tokens, Mistral prefix, Hermes markers) score 5;
* structural markers (Qwen JSON-in-tag, XML tags, ReAct action grammar) score 4;
* a JSON tool envelope scores 3;
* `unknown` is returned when every score is zero.

Ties are broken by a fixed specificity order
(`deepseek → mistral → hermes → qwen → xml → react → json → llama`), so a
single prompt containing several formats always resolves the same way. This
is the documented answer to the "conflicting dialects" case; callers who know
better pass an explicit dialect or a probe result.

### Parse contract

`parse_tool_calls(text, dialect="auto")` returns `list[ToolCall]`. A `ToolCall`
carries `name`, `arguments`, `dialect`, a truncated `raw` excerpt, an optional
`call_id` and an `incomplete` flag.

* **Malformed / truncated JSON:** quote- and bracket-aware span scanning,
  markdown-fence stripping, trailing-comma removal, open-string closing and
  bracket balancing recover the call; recovered calls are marked
  `incomplete=True`. Single-quoted payloads are accepted as a fallback.
* **Nested XML:** a tolerant stack-based tag scanner (not an XML validator)
  descends through container tags, tracks depth for repeated tag names, unescapes
  entities, and converts nested parameter tags into nested dicts.
* **Boundaries:** ReAct parsing stops at the next `Thought:`/`Action:`/
  `Observation:`/`Final Answer:`; Hermes parsing stops at `<|im_end|>`.
* **Failure mode:** unparseable or empty input returns `[]`; parser exceptions
  are contained so a hostile fragment cannot break the turn loop.

### Emit contract

`format_tool_call(name, arguments, dialect, *, call_id=None)` is the inverse of
the parser for every dialect above. Arguments are serialised with sorted keys
and `ensure_ascii=False` so output is byte-stable; XML text is entity-escaped.
An unknown dialect raises `ValueError`.

### Per-model auto-selection

`dialect_for_model_family(model_id)` is the offline fallback (family substring
→ dialect, default `json`). `select_dialect_for_model(model_id, probe_results)`
prefers a probe verdict — accepted shapes include a dialect string, a
`{"dialect", "score"}` record, a `{dialect: score}` mapping, a list of records,
or a `{"models": {...}}` wrapper — and falls back to the family inference.

---

## X1.2 — Chat-template handling

### Offline catalog layout

All lookups are rooted at the caller-supplied `catalog_root`. Lookup order:

1. `overrides/<org>/<name>.json` — per-model override (highest priority);
2. `models/<org>/<name>/chat_template.jinja` (also `.jinja2`, `.txt`, `.tmpl`,
   `template.jinja`) — the model's own template file;
3. `models/<org>/<name>/template.json` (also `model.json`, `config.json`,
   `catalog_entry.json`) — metadata with a `chat_template` / `template` key;
4. `catalog.json` at the root — `models` mapping keyed by the full model id,
   with an inline `chat_template` or a contained `template_file`.

`load_chat_template` returns a `ChatTemplateRecord` (`found`, `template`,
`source`, `overrides`, `warnings`, `to_dict()`).

### Containment rules

* Model ids are split on `/`; each segment must match
  `[A-Za-z0-9][A-Za-z0-9._-]*`. Backslashes, URL-encoded traversal (`%2e%2e`),
  drive prefixes, `://`, NUL bytes, empty segments, `.` and `..` are rejected
  with `ValueError`.
* Every resolved candidate is checked with `realpath` + `commonpath` against
  the real catalog root; symlinks pointing outside are rejected and recorded
  as a warning rather than read.
* `template_file` values inside catalog JSON are subject to the same check.
* No remote or plugin-resolved location is ever consulted.

### Mismatch warnings

`template_warning(template, model_id, *, dialect=None)` is pure and returns
either a deterministic warning string or `None`. It warns when:

* no template is declared (Keel default framing will be used);
* family markers are missing (`<|im_start|>` for Hermes/Qwen, `[INST]` for
  Llama/Mistral, either plus the full-width marker for DeepSeek);
* no recognizable user/assistant role markers are present;
* a tool-capable dialect is selected but the template declares no tool markers.

`load_chat_template` attaches this warning to `record.warnings`, using any
`dialect` recorded in the override.

---

## X1.3 — Reasoning-model output handling

### Split contract

`split_reasoning(text) -> (visible_text, reasoning_blocks)` recognises
`think`, `thinking`, `reasoning`, `analysis`, `scratchpad` and `cot` blocks in
three bracket styles: `<think>…</think>`, `<|think|>…<|/think|>` and the
full-width `<｜think｜>…<｜/think｜>` variant. Tag matching is case-insensitive.
A trailing unclosed opening tag yields a final `ReasoningBlock` with
`closed=False`; oversized blocks are handled by a single non-greedy scan with
no recursion.

Each `ReasoningBlock` records `text`, `tag`, `start`, `end`, `closed` — enough
for a collapsible UI to render the original span without re-parsing.

### History and UI contract

* `should_include_in_history(reasoning, *, include_reasoning_in_history=False,
  include_reasoning=None)` returns `False` **by default**. Reasoning never
  re-enters conversation history unless a caller explicitly opts in.
* `strip_reasoning(text)` returns only visible text; `collapse_reasoning(text,
  placeholder="[reasoning collapsed]")` inserts one placeholder per block for
  compact summaries. The UI owns the actual disclosure widget; this module
  supplies the data and the collapsed representation.

### Budget contract

* `count_reasoning_tokens(reasoning, *, estimator=None)` counts a block, a
  raw string, or a list of either. The default estimator delegates to
  `keel.context.estimate_tokens` when importable (the same stable
  `ceil(utf8_bytes / 4)` heuristic used by Keel's context accounting), with an
  identical local fallback otherwise. An injected estimator is called once per
  text with the reasoning body.
* `count_total_reasoning_tokens(text)` splits a full model output and totals
  all reasoning tokens, so callers can charge reasoning against budgets even
  though it is excluded from history.

---

## Known limitations

* Detection is heuristic; a model that emits an undocumented hybrid format may
  need an explicit dialect or a probe override. This is the intended escape
  hatch, not a failure.
* The XML reader is tolerant rather than validating: badly crossed tags are
  recovered as data, not reported as XML errors.
* Token counts are the project's deterministic byte heuristic, not a model
  tokenizer; they are budget estimates, never billing claims.
* The offline catalog has no network fallback by design; a missing template
  produces a warning and Keel default framing.
