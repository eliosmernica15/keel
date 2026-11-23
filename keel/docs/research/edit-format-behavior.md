# Edit-format selection and fuzzy application — clean-room behavior spec

This document records **behavioral requirements only**, expressed in Keel's own
vocabulary. It is not a design mirror, not a porting guide, and not a source
excerpt. No reference-repository code, prompts, branding, icons, logos, or other
proprietary assets appear here. It is the normative companion to
`keel/src/keel/edit_formats.py` (features X1.4 and X1.5).

---

## Source metadata

- **Registry read:** `PLAN-INDEX.json` in this worktree (canonical Keel feature IDs).
- **Feature rows:** X1.4 "Selectable edit formats per model" (M5, P0); X1.5
  "Fuzzy patch application" (M5, P0).
- **Registry detail (X1.4):** "Whole-file, search/replace blocks, unified diff,
  line-range edit. Router picks the format the model is most reliable with
  (from local eval)."
- **Registry detail (X1.5):** "Whitespace-tolerant, indentation-aware matching
  with a similarity threshold; on failure return a precise error and
  nearest-match snippet to the model."
- **Method:** first-principles behavior analysis of the two registry rows,
  translated into a deterministic, stdlib-only contract. No external reference
  implementation was cloned or read for this document. Any resemblance to
  common editor conventions is intentional interoperability, not copied text.
- **Research date:** 2026-11-23
- **Worktree / branch:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\patches` on `agent/a3-patches`
- **Baseline:** `52b752c`

---

## 1. Scope and vocabulary

An **edit format** is a dialect used by a model to express a replacement of a
file's content. A **router** selects a dialect per model; an **applier** turns a
dialect-specific edit into new file content. A **search block** is one
old-text/new-text pair inside a dialect. **Local eval** is a mapping of observed
success/attempt statistics, produced offline, used only to rank dialects.

The module operates on text, not on the filesystem. It never opens, writes, or
deletes a path, and it never mutates its input strings.

Canonical format identifiers:

| Identifier | Meaning |
|---|---|
| `whole_file` | The edit text is the complete replacement content. |
| `search_replace` | One or more old/new blocks with explicit markers. |
| `unified_diff` | Standard `@@ -a,b +c,d @@` hunks with `-`, `+`, context lines. |
| `line_range` | A header naming absolute lines, followed by replacement lines. |

`auto` (or `None`) means "detect".

---

## 2. Observed/required behavior — detection

`detect_edit_format(text)` is deliberately conservative: plain text is always
`whole_file`. Structured markers win in this fixed precedence order:

1. A line equal to `*** Begin Patch` → `search_replace`.
2. A search/replace marker line (`<<<<<<< SEARCH`, `<<< SEARCH >>>`, `<search>`,
   or their documented aliases) → `search_replace`.
3. At least one unified-diff hunk header matching `@@ -N[,M] +N[,M] @@` →
   `unified_diff`.
4. A line-range header such as `[lines 3-5]`, `L7`, or `line 2 through 4` →
   `line_range`.
5. Otherwise → `whole_file`.

The precedence matters: a `*** Begin Patch` block may contain `@@` section
headers that look like diff hunks; detection must still return
`search_replace`. `detect_edit_format_details` returns the same decision plus a
confidence, a human reason and the marker names used, for auditability.

A false positive is possible if a whole-file replacement happens to contain a
literal marker line. Callers that know the intended dialect must pass it
explicitly; an explicit format always overrides detection.

---

## 3. Required behavior — each dialect

### 3.1 Whole-file

The returned content is exactly the edit text. An edit identical to the
original is a no-op and returns the original string object unchanged (including
all line endings).

### 3.2 Search/replace blocks

Three marker families are accepted, all mapping to the same internal
old/new-block representation:

```
<<<<<<< SEARCH
old text
=======
new text
>>>>>>> REPLACE
```

```
<<< SEARCH >>>        (aliases: FIND, OLD)
old text
<<< DIVIDER >>>       (aliases: SPLIT, SEP; or a bare === line)
new text
<<< REPLACE >>>       (alias: NEW)
```

```
<search>              (alias: <old>)
old text
</search>
<replace>
new text
</replace>
```

Blocks are applied in order. The `*** Begin Patch` family is:

```
*** Begin Patch
*** Update File: path
@@ optional section header
 context line
-old line
+new line
*** End Patch
```

The `@@` header's text is an optional anchor: if a line with that text exists in
the original, it is used to disambiguate equal-scoring candidates. `*** Add
File:` replaces the whole file with the added lines; `*** Delete File:` empties
it. Only content semantics are modeled; file paths are not resolved by this
module.

Lines in a hunk body are classified as context (leading space), removal
(leading `-`), addition (leading `+`), or blank-context (empty line). A
`\ No newline at end of file` line is ignored for matching.

### 3.3 Unified diff

File headers (`diff --git`, `--- a/...`, `+++ b/...`, `index ...`) are skipped.
Each hunk's declared old/new line counts are validated against the body. On
mismatch the applier raises a typed parse error with code `truncated_diff`, the
hunk header's 1-based line number and a raw snippet — it never applies a
partially received hunk. Each hunk's `-N` start value is an anchor hint; after
earlier hunks change line counts, later anchors are adjusted by the cumulative
line-count delta. A hunk with only `+` lines is an insertion at its anchor.

### 3.4 Line-range

The first non-blank line is the header; all following lines are the replacement
body. Accepted headers: `[lines 3-5]`, `(lines 3-5)`, `L7`, `line 2 through 4`,
and the `to`/`..` variants. Absolute line numbers are 1-based. A range starting
at `len(lines)+1` appends. Out-of-range requests raise `out_of_range` with the
header as the snippet.

---

## 4. Required behavior — fuzzy matching (X1.5)

### 4.1 Candidate model

A candidate is a window of exactly the same number of lines as the search
block. Windows of a different size are never considered; this is what prevents
a short search from silently deleting unrelated lines.

Five normalization levels are scored, from strictest to loosest:

| Level | Transformation |
|---|---|
| `exact` | none (after line-ending normalization) |
| `rstrip` | trailing whitespace removed per line |
| `collapsed` | whitespace runs collapsed to one space, ends stripped |
| `indentless` | leading indentation removed, then collapsed |
| `compact` | all whitespace removed |

For each window the highest-scoring level is retained. A similarity is
`SequenceMatcher.ratio()` over the normalized strings, minus an **indentation
penalty** of `min(0.20, 0.03 × |indent(window) − indent(search)|)` columns. The
penalty makes the matcher indentation-aware: it tolerates a uniform shift, but
prefers the candidate whose indentation matches the search text when two
otherwise identical candidates exist.

### 4.2 Acceptance and guards

A window qualifies only when its score is at least the threshold (default
`0.80`). If none qualifies, the applier raises `no_match` and reports the
highest-scoring window, its 1-based line number and a numbered snippet with one
line of context on each side.

If two or more qualifying windows share the best score (within `1e-9`), the
applier raises `ambiguous_match` with every candidate line number and a snippet.
An optional anchor hint breaks the tie only when it is strictly closer to one
candidate. There is no "first match wins" fallback: ambiguity is always an
error, and the model must supply a longer search block or a unique anchor.

Empty or whitespace-only search text raises `empty_search`. A threshold outside
`(0, 1]` raises `invalid_threshold`. Both are typed errors, not silent
successes.

### 4.3 Indentation transfer and line endings

When the matched window has a different indentation from the search text, the
same column delta is applied to every non-blank line of the replacement. This
makes an indentation-shift edit (e.g. a function moved into a class) produce
correctly indented replacement lines.

Line endings are preserved locally: replacement lines inherit the separator of
the first replaced line, and the final replacement line inherits the separator
of the last replaced line (so a file ending without a newline stays that way).
Mixed-ending files are handled line by line; a no-op edit returns the original
bytes unchanged.

### 4.4 No-op semantics

When the search text and replacement text are identical, the result is the
original string and `MatchInfo.no_op` is true. This holds even when the match
was found only after whitespace normalization, so fuzzy application can never
introduce cosmetic drift into untouched content.

---

## 5. Required behavior — model-facing errors

Every failure is a typed exception carrying `code`, `message`, `line`,
`snippet`, `similarity` (where meaningful) and a `candidates` line list.
`to_model_message()` renders a deterministic, copy-pasteable report:

```
Edit failed (ambiguous_match): Refusing to apply an ambiguous edit: 2 equally good matches at lines 1, 3.
Nearest location: line 1.
Equally good candidates: 1, 3
Best similarity: 1.000.
Nearest match:
    1 | x = 1
    2 | y = 2
     ...
```

The contract is that the model receives enough evidence to correct its edit:
where the applier looked, how close the best candidate was, and what it saw.

---

## 6. Required behavior — format recommendation

`recommend_format(model_id, eval_stats)` is pure and deterministic. It accepts
local eval stats keyed by model (`{"models": {id: {"formats": {...}}}}`,
`{id: {"formats": {...}}}`, or a flat `{format: stat}` mapping). A stat is a
rate in `[0, 1]`, a success count, or a mapping containing
`successes`/`attempts` (equivalently `success`/`trials`/`total`) or
`success_rate`.

Rates use Laplace smoothing `(successes + 1) / (attempts + 2)` so a single
lucky trial cannot dominate. The highest smoothed rate wins. Ties break on a
fixed preference order — `search_replace`, `unified_diff`, `line_range`,
`whole_file` — then on format name. With no usable stats for the model, the
default is `search_replace`. Dict insertion order never affects the result, and
no model-family priors are encoded: reliability claims come only from local
eval, never from assumptions about a vendor.

`recommend_format_details` returns the chosen format plus `source`
(`"eval"` or `"default"`), all smoothed scores, and the model id for audit
trails.

---

## 7. Provenance statement

This specification was authored clean-room. No reference implementation was
read, no non-public material was used, and no source text was copied. It is an
original behavioral contract derived from Keel's own reconciled registry, and
is provided for implementing and verifying Keel's edit-format layer.
