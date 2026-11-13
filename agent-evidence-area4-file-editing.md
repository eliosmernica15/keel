# Claude Code — Area #4 Evidence: File Creation, Modification, Patching, and Review

**Subject:** Claude Code CLI (native build) v2.1.306 on Windows 11 Pro 10.0.26300 (win32-x64)
**Implementation model reference:** Claude Opus 5.5
**Investigation date:** 2026-10-21
**Working directory:** `C:\Users\Admin\Desktop\Claude clone`
**Scope:** Area 4 only — the `Edit` / `Write` / `NotebookEdit` / `MultiEdit` tool family, the diff record they produce, how that diff is presented to the user, checkpoint/rewind as the recovery mechanism, and the `/diff` + `/code-review` review surface.

---

## 1. Executive summary

Claude Code's file-editing layer is a **four-tool family with deliberately different contracts**, unified by one internal representation: a **structured patch record**. The design is more disciplined than it first appears, and every part of it is reproducible from public documentation plus black-box observation of the published CLI.

**The four tools, and why they are not interchangeable:**

| Tool | Semantics | Atomicity | Produces a diff? |
|---|---|---|---|
| `Edit` | Exact string replacement of `old_string` → `new_string` | Single occurrence, or all occurrences with `replace_all: true` | Yes — `structuredPatch` |
| `Write` | Whole-file create or **overwrite**; never appends, never merges | Whole file | Yes — `structuredPatch` (empty for a create) |
| `NotebookEdit` | Cell-targeted `replace` / `insert` / `delete` on a `.ipynb` | One cell | No — returns `original_file` / `updated_file` |
| `MultiEdit` | Legacy; **permitted in permission rules but never consulted** | n/a | n/a |

**The single most important implementation fact:** the three-part edit gate is *exact-match, not fuzzy*. `Edit` "performs exact string replacement… It doesn't use regex or fuzzy matching," and "A single character of whitespace or indentation difference is enough to miss." A clean-room implementation that uses a regex or a whitespace-tolerant matcher will diverge from Claude Code on precisely the cases users notice. This is the one place where a naive reimplementation feels nearly right and behaves differently.

**Three findings that were not predictable from the documentation and required experiment:**

1. **The read-before-edit gate is model-dependent, and the relaxation is observable in the result shape.** On the model available here, an `Edit` on a never-read file **succeeded**, and its result carried a distinct boolean `contentNotInModelContext: true` and a success message *without* the usual "(file state is current in your context — no need to Read it back)" suffix. The docs say newer models "can edit an unread file when reading it wouldn't need a permission prompt and the Read tool is available" — but they do not document the `contentNotInModelContext` flag or the message difference. The observable consequence is that the harness **cannot assume the model has the file's content** after a read-relaxed edit, and must re-read before any edit that depends on surrounding content.

2. **Stale-file edits are matched against *current on-disk* content, not the content the model read.** When a file was modified on disk between the model's `Read` and its `Edit`, the edit applied cleanly, the returned `originalFile` was the **current** disk content (including the external change), and the result carried `staleRecovered: true` plus a distinct warning clause. The `structuredPatch` therefore includes the external change as context lines. A reimplementation that diffs against the model's stale view will produce a different patch.

3. **`Write` has no read-before-write gate on this model, even for an existing file.** The docs describe the gate as applying to older models and *always* to notebooks. An observed `Write` over an unread existing file succeeded and returned `type: "update"` with a full `structuredPatch`.

**Review and recovery surface:** edits are presented to the user through `/diff` (a fullscreen diff *panel* in the fullscreen renderer, a *dialog* in the classic renderer — both from the built-in `cc-plugin-diff` mod), with per-turn views labelled `T1`, `T2`, … and `Current`. Because turn views come from the *tool* edit log rather than from git, **a change made through a shell command appears only under `Current`**. Recovery is by checkpointing: a snapshot per turn, 100 checkpoints of retention, `/rewind` (aliases `/checkpoint`, `/undo`) or double-`Esc`, with the on-disk layout `~/.claude/file-history/<session-id>/<16-hex-hash>@v<N>`.

**Clean-room assessment.** This area is unusually tractable. The entire contract is specified in public documentation, the wire format is published in the Agent SDK TypeScript reference, and the diff record format is directly observable in the `stream-json` output. An independent implementation can reach behavioural parity on the editing semantics with **no access to Anthropic code and no reverse engineering** — the specification *is* the public doc plus the tool-result JSON.

**Compliance note.** No decompilation, disassembly, source-map extraction, binary modification, credential/keychain/licence-file access, or reverse-engineering of the Anthropic gateway was performed. Evidence is limited to (a) public Anthropic documentation at `code.claude.com/docs`, and (b) black-box observation of the published CLI's own user-facing surfaces. REA was used only in its **process/terminal-capture** mode; its decompilation, disassembly, JavaScript-recovery, and native-binary-analysis facilities were deliberately **not** invoked. See `agent-reference-shots/TERMS-NOTES.md`.

**Environment caveat.** This machine runs against a custom `ANTHROPIC_BASE_URL` (a third-party gateway serving `minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. `claude doctor` confirms *"Not connected to the Anthropic API (api.anthropic.com)"*. Consequently: (i) the read-before-edit relaxation observed in §3.3 reflects a **non-Anthropic model** on this gateway and is marked **INFERRED** with respect to Claude Opus 5.5; (ii) subscription-gated behaviours (cloud `ultrareview`, managed settings, org policy, GitHub Code Review) are **INFERRED from docs only**, never OBSERVED here.

---

## 2. Classification key

| Tag | Meaning |
|---|---|
| **OBSERVED-DOC** | Stated in a cited public Anthropic document at `code.claude.com/docs`. The URL and the quoted text are given. |
| **OBSERVED-CLI** | Personally ran the published CLI's own surface. The exact command and the exact output are given. |
| **INFERRED** | A conclusion supported by the cited evidence, with the reasoning stated explicitly. Not a direct observation. |
| **UNKNOWN** | The available evidence cannot establish it. |

---

## 3. Findings

---

### F1 — `Edit` is exact string replacement, with an explicit three-gate contract

**Classification: OBSERVED-DOC + OBSERVED-CLI**

**Evidence (DOC).** `https://code.claude.com/docs/en/tools-reference` — "Edit tool behavior":

> The Edit tool performs exact string replacement. It takes an `old_string` and a `new_string` and replaces the first with the second. It doesn't use regex or fuzzy matching.
>
> These checks must pass for an edit to apply. Before any of them, a path matched by a `Read` deny rule is refused, including creating a new file there.
>
> - **Read-before-edit**: Claude reads the file in the current conversation before editing it, and a read cut short with a `PARTIAL view` notice doesn't count. Claude Opus 4.6, Claude Haiku 4.5, and older models always require the read. Newer models can edit an unread file when reading it wouldn't need a permission prompt and the Read tool is available.
> - **Match**: `old_string` must appear in the file exactly as written. A single character of whitespace or indentation difference is enough to miss.
> - **Uniqueness**: `old_string` must appear exactly once. When it appears more than once, Claude either supplies a longer string with enough surrounding context to pin down one occurrence, or sets `replace_all: true` to replace them all.

**Evidence (CLI).** `claude -p "Read demo.js, then use Edit to replace 'const timeout = 30;' with 'const timeout = 60;'." --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read Edit`

```json
{"replace_all": false, "file_path": "<PROJECT>\\demo.js",
 "old_string": "const timeout = 30;", "new_string": "const timeout = 60;"}
```

The tool's wire input is exactly four fields: `file_path`, `old_string`, `new_string`, `replace_all`. There is no line-number, offset, or regex field.

**INFERRED.** The `replace_all` flag is *required* to be present in the request even when false. Both observed `Edit` calls carried `"replace_all": false` explicitly, including the ones where the model was told to make exactly one call. A reimplementation should treat it as a required boolean with a default of `false`, and — importantly — should distinguish "absent" from "explicitly false" only if it wants to reproduce a product that distinguishes them. Claude Code's documented contract does not say it distinguishes them.

**Clean-room implementation opportunity.** Implement `Edit` as: read file bytes → decode (subject to F9) → `indexOf(old_string)` scan counting **all** occurrences → apply gates in the documented order (Read-deny → read-before-edit → match → uniqueness) → write → emit the `structuredPatch` of F7. Use a literal substring search, never a regex, and **normalise nothing** — no trimming, no CRLF→LF coercion, no whitespace collapsing. Match against the file's *current* on-disk content (F5), not a cached view.

---

### F2 — The uniqueness gate produces a specific, recoverable error, and `replace_all: true` is the documented escape

**Classification: OBSERVED-CLI**

**Evidence (CLI).** `claude -p "Read dup.txt. Then IMMEDIATELY call the Edit tool with exactly these arguments: file_path=<abs path of dup.txt>, old_string='dup line', new_string='CHANGED', replace_all=false. Do NOT add any surrounding context to old_string." --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read Edit`, against a file containing `a\ndup line\nb\ndup line\nc\n`.

Result, `is_error: true`:

```
<tool_use_error>Found 2 matches of the string to replace, but replace_all is false. To replace all occurrences, set replace_all to true. To replace only one occurrence, please provide more context to uniquely identify the instance.
String: dup line</tool_use_error>
```

and the structured `tool_use_result`:

```
Error: Found 2 matches of the string to replace, but replace_all is false. To replace all occurrences, set replace_all to true. To replace only one occurrence, please provide more context to uniquely identify the instance.
String: dup line
```

With `replace_all: true` on the same file:

```
The file <PROJECT>\\dup2.txt has been updated. All occurrences were successfully replaced.
```

```json
"structuredPatch": [{"oldStart":1,"oldLines":5,"newStart":1,"newLines":5,
  "lines":[" a","-dup line","+CHANGED"," b","-dup line","+CHANGED"," c"]}],
"replaceAll": true
```

**Observations of implementation detail.**

- The error message is **actionable in both directions** — it names the exact parameter (`replace_all`) and the exact remedy ("provide more context to uniquely identify the instance"). This is deliberate: the model is expected to recover by re-issuing with a longer `old_string`.
- The error is wrapped in a `<tool_use_error>` tag in the `content` field, and is a plain `"Error: …"` string in the `tool_use_result` field. **Two different renderings of the same failure** exist on the wire.
- The `String: dup line` trailer echoes the offending `old_string` verbatim. It does not echo the file path, and it does not give line numbers.
- The `replace_all: true` success message is a **different string** from the ordinary success message: "has been updated. All occurrences were successfully replaced." vs. "has been updated successfully. (file state is current in your context — no need to Read it back)". A reimplementation that uses one success template will not match.
- The `structuredPatch` for a `replace_all` edit interleaves all hunks into a **single** hunk (`oldLines: 5`, `newLines: 5`) rather than emitting multiple hunks — the two replacements at lines 2 and 4 produce one contiguous context block.

**INFERRED.** The "provide more context" remedy in the error text tells the model the intended recovery direction, and the observed model followed it: in a separate run, the same model read `dup.txt`, hit the ambiguity, and re-issued the edit with `old_string: "a\ndup line"` — a two-line anchor — which succeeded and changed only line 2. So the error message is load-bearing in the agent loop, not decoration. A clean-room implementation should copy the message text closely, because the message is a prompt.

**Clean-room implementation opportunity.** Emit the exact error string, wrapped in `<tool_use_error>` in the content channel and prefixed `Error: ` in the structured channel, with the `String: <old_string>` trailer. On `replace_all: true`, emit the distinct "All occurrences were successfully replaced." text. Produce a single merged hunk for the all-occurrences case.

---

### F3 — The not-found error is a distinct, separate failure mode

**Classification: OBSERVED-CLI**

**Evidence (CLI).** `claude -p "Use the Edit tool on notfound.js: old_string='const timeout = 999;', new_string='const timeout = 60;'. Do NOT read the file first, do NOT grep it. Make exactly one Edit call and report the tool result verbatim." --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Edit`

Result, `is_error: true`:

```
<tool_use_error>String to replace not found in file.
String: const timeout = 999;</tool_use_error>
```

structured `tool_use_result`:

```
Error: String to replace not found in file.
String: const timeout = 999;
```

**Observations.**

- This is a **two-line** error, categorically different in shape from the three-line uniqueness error. A reimplementation should not merge them.
- Crucially, the file **existed** and the `Edit` still failed — so "file not found" and "string not found" are different errors with different causes. A reimplementation that only checks file existence will produce a different message.
- The error does **not** echo the file path. The model in the observed run correctly inferred the path from its own request and confirmed the file existed via `git status`.
- The observed model, having been told not to read the file, correctly diagnosed the cause in its reply: *"the match is exact, so different spacing, a different variable name, or a different value would all cause this."*

**INFERRED.** Together, F1–F3 give the error taxonomy of the editing layer: **not-found** (zero matches), **not-unique** (multiple matches with `replace_all: false`), and **success**. There is a fourth, documented but not observed here: the non-UTF-8 refusal (F9). An implementation should expose exactly these, and should **not** invent a fifth ("file does not exist") that the product does not emit for a missing string.

**Clean-room implementation opportunity.** A four-outcome enum for `Edit`: `Applied`, `StringNotFound`, `NotUnique`, `EncodingRefused`. Each with its own verbatim message. Keep the messages byte-stable — they are consumed by the model as recovery instructions.

---

### F4 — `Write` is whole-file create-or-overwrite, and it reports `type: "create"` vs `type: "update"` distinctly

**Classification: OBSERVED-CLI + OBSERVED-DOC**

**Evidence (CLI).** Create:

```
$ claude -p "Use the Write tool to create the file wrote.md in the current directory with exactly this content: '# Hello\n\nWritten by Claude.\n'" --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Write
```

```
File created successfully at: <PROJECT>\\wrote.md (file state is current in your context — no need to Read it back)
```

```json
{"type": "create", "filePath": "<PROJECT>\\wrote.md",
 "content": "# Hello\n\nWritten by Claude.\n",
 "structuredPatch": [], "originalFile": null, "userModified": false}
```

Overwrite of an existing file, after a `Read`:

```
The file <PROJECT>\\wrote.md has been updated successfully. (file state is current in your context — no need to Read it back)
```

```json
{"type": "update", "filePath": "<PROJECT>\\wrote.md",
 "content": "# Hello v2\n\nOverwritten.\n",
 "structuredPatch": [{"oldStart":1,"oldLines":3,"newStart":1,"newLines":3,
   "lines":["-# Hello","+# Hello v2"," ","-Written by Claude.","+Overwritten."]}],
 "originalFile": "# Hello\n\nWritten by Claude.\n", "userModified": false}
```

**Evidence (DOC).** `https://code.claude.com/docs/en/tools-reference` — "Write tool behavior":

> The Write tool creates a new file or overwrites an existing one with the full content provided. It doesn't append or merge. Write also overwrites an existing file whose bytes don't decode and saves the new content as UTF-8…
>
> For partial changes to an existing file, Claude uses Edit instead of Write.

**Observations of implementation detail.**

- `Write` emits a **full-file diff** in `structuredPatch`, not a minimal one. The overwrite of a 3-line file produced a hunk with `oldLines: 3, newLines: 3` in which the unchanged blank line appears as a bare `" "` context entry.
- A **create** has `structuredPatch: []` and `originalFile: null`. A reimplementation that always emits a diff for `Write` will not match the create case.
- The `type` field distinguishes `create` from `update`. This is the only tool that carries it.
- `Write` does **not** preserve the original line endings or encoding. See F9 and F13.

**Clean-room implementation opportunity.** `Write` = truncate-and-write full content, atomically if possible. Emit `type: "create"` with an empty patch when the path did not exist, `type: "update"` with a full-file diff when it did. Use a temp-file + rename to avoid truncating a file on a crash mid-write. Reject content containing `U+FFFD` (F9).

---

### F5 — A stale file is still edited, matched against **current disk content**, and flagged `staleRecovered`

**Classification: OBSERVED-CLI + OBSERVED-DOC**

**Evidence (CLI).** `claude -p "Step 1: Read stale.txt. Step 2: Use Bash to append a line 'EXTERNAL CHANGE' to stale.txt. Step 3: Use Edit on stale.txt to replace 'stale content here' with 'updated content'." --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read Edit Bash`

The `Edit` result:

```
The file <PROJECT>\\stale.txt has been updated successfully (note: the file had been modified on disk since you last read it — the edit applied cleanly, but the file contains other changes not in your context. Read it before edits that depend on surrounding content.)
```

```json
{"filePath": "<PROJECT>\\stale.txt",
 "oldString": "stale content here", "newString": "updated content",
 "originalFile": "stale content here\nsecond line\nEXTERNAL CHANGE\n",
 "structuredPatch": [{"oldStart":1,"oldLines":3,"newStart":1,"newLines":3,
   "lines":["-stale content here","+updated content"," second line"," EXTERNAL CHANGE"]}],
 "userModified": false, "replaceAll": false,
 "staleRecovered": true, "contentNotInModelContext": true}
```

**Evidence (DOC).** `https://code.claude.com/docs/en/tools-reference` — "Edit tool behavior":

> A file that changed on disk after Claude last read it can still be edited when `old_string` matches the current content exactly and unambiguously and Claude Code can read the file without prompting. Matching against the file's current content keeps this safe, and the result notes that the file carries other changes so Claude re-reads it before edits that depend on surrounding content. In any other case, such as a stale `old_string` or one that matches more than once without `replace_all`, Claude reads the file again before editing.

**Observations of implementation detail — this is the highest-value finding in the area.**

- `originalFile` in the result is the file's **current on-disk content at edit time** (`stale content here\nsecond line\nEXTERNAL CHANGE\n`), *not* the content the model had read (`stale content here\nsecond line\n`). The external change is present.
- The `structuredPatch` consequently includes the external line `" EXTERNAL CHANGE"` as a **context line**. The diff is against the current file, not against the model's view.
- The success text has a **parenthetical warning clause** appended, and it is a *different* template from the ordinary success text: note the observed string reads "has been updated successfully (note: …)" — **no period before the parenthesis** — whereas the ordinary success is "has been updated successfully. (file state is current in your context — no need to Read it back)". The punctuation differs.
- Two new booleans appear: `staleRecovered: true` and `contentNotInModelContext: true`.
- The `Read` that preceded the `Edit` was **not re-issued by the harness**. The model was told to re-read, and did so itself in the next turn (observed: a fourth `Read` call whose result showed all three lines). The product *tells* the model to re-read; it does not silently re-read for it.

**INFERRED.** The three result booleans form a coherent set and are the clean-room implementation's most valuable parity target:
- `contentNotInModelContext: true` ⇒ the model has **not** been given the file's current content as context, so any subsequent edit depending on surrounding content is unsafe. The harness must treat the model's view as stale.
- `staleRecovered: true` ⇒ the edit was applied against a file whose on-disk state diverged from the model's last read; the tool recovered rather than refusing.
- `userModified: false` ⇒ the file was not changed by the user between the model's read and the edit (the sibling flag for the "user touched it" case).

**INFERRED (product-design).** The refusal-to-stale-edit decision is delegated to the *model*, not enforced by the harness, in the "matches more than once" and "stale `old_string`" cases — the docs say Claude "reads the file again before editing". The harness enforces only the mechanical gates. A clean-room implementation can choose to enforce staleness mechanically (refuse when the on-disk hash differs from the read hash) and will be *safer* than Claude Code, but it will not be *behaviourally identical*. This is a legitimate design choice and should be documented as a deliberate divergence.

**Clean-room implementation opportunity.** On every `Edit`: stat the file, compare its mtime/size/hash with the record of the model's last read. If it diverged → set `staleRecovered: true`, set `contentNotInModelContext: true`, match against the **current** content, and append the warning clause. If the match count is 0 against current content but > 0 against the model's cached view → re-read the file (or refuse). Diff against current content, always.

---

### F6 — The read-before-edit gate is model-dependent, and the relaxation is visible in the result shape

**Classification: OBSERVED-CLI + OBSERVED-DOC (the relaxation is INFERRED for Claude Opus 5.5)**

**Evidence (CLI).** `claude -p "Use the Edit tool on the file unread.txt in the current directory: replace the string 'never read' with 'now read'. Do NOT call Read first. Make exactly one Edit call." --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Edit`

`unread.txt` had never been read in this session. The result:

```
The file <PROJECT>\\unread.txt has been updated successfully.
```

```json
{"filePath": "<PROJECT>\\unread.txt", "oldString": "never read", "newString": "now read",
 "originalFile": "never read\n",
 "structuredPatch": [{"oldStart":1,"oldLines":1,"newStart":1,"newLines":1,
   "lines":["-never read","+now read"]}],
 "userModified": false, "replaceAll": false, "contentNotInModelContext": true}
```

**Compare against the read-first case (F1):**

| | Read-first | Never read |
|---|---|---|
| Success text | `…has been updated successfully. (file state is current in your context — no need to Read it back)` | `…has been updated successfully.` |
| `contentNotInModelContext` | absent | `true` |
| `userModified` | `false` | `false` |

**Evidence (DOC).** `https://code.claude.com/docs/en/tools-reference`:

> **Read-before-edit**: … Claude Opus 4.6, Claude Haiku 4.5, and older models always require the read. Newer models can edit an unread file when reading it wouldn't need a permission prompt and the Read tool is available.

and, for `Write`:

> - Claude Opus 4.6, Claude Haiku 4.5, and older models always require the read, so a Write to an unread existing file fails with an error.
> - Newer models can overwrite a file they never read this session under the same conditions as read-before-edit…
> - Jupyter notebooks, and files Claude has read only partially with a `PARTIAL view` notice, require the read on every model.
>
> This constraint doesn't apply to new files. Before v2.1.228, every model required the read before overwriting an existing file.

**INFERRED (important, and explicitly scoped).** The read-before-edit **relaxation** was observed on the model this machine is configured to use (`minimax/minimax-m3.1-flash:free` via a custom gateway). The documented relaxation is stated to apply to "newer models"; whether the *reference* implementation model (Claude Opus 5.5) takes the relaxed path is **INFERRED**, not OBSERVED — this host cannot execute against `api.anthropic.com`. The **structural** consequence is what matters and is model-independent: the harness must carry a "the model has not seen this file's content" flag, and the product's own way of carrying it is `contentNotInModelContext`.

**INFERRED.** `Write` on an **existing, never-read** file also succeeded with no gate on this model (F4, case `[9]` in the capture) — consistent with the documented relaxation applying to `Write` on the same conditions. The documented always-gate cases (notebooks, `PARTIAL view` reads) were **not** exercised here.

**INFERRED.** The docs list a specific set of Bash commands that satisfy the read requirement: `cat`, `nl`, `bat`, `batcat`, `head`, `tail`, `sed -n 'X,Yp'`, `grep`, `egrep`, `fgrep`, and `rg`, "each run on one file with no pipes or redirects." This is an *exact allow-list*, and a reimplementation should treat it as data, not as a heuristic.

**Clean-room implementation opportunity.** Make the gate a **policy table** keyed by (model capability, file kind, read completeness), not a hard-coded boolean. Track per-file read state: `{read: bool, partial: bool, viaBash: bool, mtime, size, hash}`. Emit `contentNotInModelContext: true` whenever the model has not received the file's content. Populate the read state from the exact Bash allow-list above.

---

### F7 — `structuredPatch` is the internal diff record, and it is a specific, implementable shape

**Classification: OBSERVED-CLI**

**Evidence (CLI).** From the observed `Edit`, `Write` and `replace_all` results above, the record is:

```json
"structuredPatch": [
  {
    "oldStart": 1,
    "oldLines": 4,
    "newStart": 1,
    "newLines": 4,
    "lines": [
      " line one",
      "-const timeout = 30;",
      "+const timeout = 60;",
      " const retries = 3;",
      " line four"
    ]
  }
]
```

**The format, stated precisely:**

- It is an **array of hunks**. A `Write` overwrite produced exactly one hunk; a `replace_all` edit produced exactly one hunk covering both replacements; a create produced `[]`.
- Each hunk has exactly four numeric fields: `oldStart`, `oldLines`, `newStart`, `newLines` (1-based line numbers; `oldLines`/`newLines` are *counts*).
- `lines` is an array of strings. The **first character of each string is a marker**: `" "` = context, `"-"` = removed, `"+"` = added. The marker is *part of the string* — a context line retains its leading whitespace after the marker, so a blank context line is the single-character string `" "`.
- The line content follows the marker with **no additional indentation stripping** — the observed context line `" const retries = 3;"` shows the source's own leading space preserved after the marker space.
- `oldStart`/`newStart` are the 1-based start lines of the hunk in the old and new files respectively.

**INFERRED.** This is the shape of a standard unified-diff hunk, minus the `@@` header — it is the `diff` npm package's `structuredPatch` output, and its consumer is the IDE diff viewer / `/diff` panel. The absence of the `@@` header is why the renderer can recompute it. A clean-room implementation can produce byte-identical hunks by implementing the standard algorithm (e.g. Myers / linear-space diff) and emitting the same four fields.

**INFERRED — the diff is computed against the *current* file**, not the model's view (F5). The observed stale-edit patch included the external change as a context line, which only happens if the diff baseline is the current on-disk content.

**INFERRED.** `originalFile` is the **pre-edit** content of the file as it existed immediately before the write, always the current-disk content (F5). It is present for `update` and `Edit`, `null` for a `create`.

**Clean-room implementation opportunity.** Implement one diff routine, used by `Edit`, `Write`, the `/diff` panel, and the checkpointing summary. Emit `{oldStart, oldLines, newStart, newLines, lines[]}` with the marker-prefixed line array. Because the same routine serves the UI, a single well-tested implementation covers every surface.

---

### F8 — Success messages carry a "your context is current" hint, and the hint's presence is a contract

**Classification: OBSERVED-CLI**

**Evidence (CLI).** Observed success strings:

| Case | Message |
|---|---|
| `Edit` after a `Read` | `The file <path> has been updated successfully. (file state is current in your context — no need to Read it back)` |
| `Edit` with `replace_all: true` | `The file <path> has been updated. All occurrences were successfully replaced.` |
| `Edit`, never-read file | `The file <path> has been updated successfully.` |
| `Edit`, stale file | `The file <path> has been updated successfully (note: the file had been modified on disk since you last read it — the edit applied cleanly, but the file contains other changes not in your context. Read it before edits that depend on surrounding content.)` |
| `Write` create | `File created successfully at: <path> (file state is current in your context — no need to Read it back)` |
| `Write` update | `The file <path> has been updated successfully. (file state is current in your context — no need to Read it back)` |
| `NotebookEdit` insert | `Inserted cell undefined with cell one` |

**INFERRED — why this matters more than it looks.** The parenthetical "(file state is current in your context — no need to Read it back)" is a **prompt-engineering device**: it tells the model it may skip a redundant `Read` and keep going, which saves a whole tool round-trip per edit. Its **absence** in the never-read and stale cases is the signal that a re-read *is* needed. A clean-room implementation should treat the presence/absence of this clause as a functional part of the contract, not decoration, and should vary it exactly as observed.

**INFERRED.** The `Edit` and `Write` success texts both begin `The file <path> has been updated successfully.` and differ only in the suffix. `Write`'s *create* case uses a different verb form entirely (`File created successfully at: <path>`). Reproducing the exact strings costs nothing and materially changes the agent's tool-call economy.

**Clean-room implementation opportunity.** Build the success message as a function of the same state flags used for the result object: `{created, staleRecovered, contentNotInModelContext, replaceAll}`. Four message templates, selected by that tuple. Keep the em-dash and the exact parenthetical.

---

### F9 — Non-UTF-8 files: `Edit`/`NotebookEdit` refuse; `Write` may replace, losing the encoding

**Classification: OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/tools-reference` — "Non-UTF-8 files":

> Claude can't use NotebookEdit on a file that isn't valid UTF-8. The same goes for Edit, unless the file starts with a little-endian UTF-16 byte-order mark. When Claude tries, the tool refuses the change and leaves the file untouched. Refused files include non-ASCII text saved in a legacy encoding such as Windows-1252 or Shift-JIS, binary files, and UTF-8 with an invalid byte sequence.
>
> The tools refuse because they save the whole file back as UTF-8, which would replace every byte they can't decode with the replacement character `U+FFFD`. Instead, the error Claude receives tells it to make the change with a shell command that keeps the file's encoding, or to ask you about converting it to UTF-8 first.
>
> Claude can still replace such a file with Write, unless the new content contains `U+FFFD`, the character Read shows Claude in place of bytes it can't decode. That guard stops Claude from writing back the garbled text it read. When Write does replace the file, it saves the new content as UTF-8, so the file's original encoding is lost.

**INFERRED.** The rule is a *whole-file* property, not a per-byte one: because the tool saves the entire file back, one undecodable byte anywhere corrupts the whole file, so the tool refuses rather than degrade. The UTF-16LE BOM is a narrow exception, implying a decode path exists for that specific case. The `U+FFFD` guard on `Write` is a **round-trip check** — the model may legitimately have the replacement character in its context (from a `Read`), and writing it back would bake the corruption in permanently.

**INFERRED.** The refusal is a *design choice with a user-facing consequence*: the product tells the model to fall back to a shell command that preserves the encoding, rather than silently transcoding. A clean-room implementation that transcodes automatically would be more convenient but would diverge — and would silently rewrite a user's file encoding, which is a genuine data-loss risk for legacy-encoded files.

**Clean-room implementation opportunity.** Before any `Edit`/`NotebookEdit`: attempt a strict UTF-8 decode (allowing a leading UTF-16LE BOM). On failure → refuse, leave the file untouched, and return an error that tells the model to use a shell command preserving the encoding. For `Write`: allow replacement, but reject content containing `U+FFFD` unless the caller explicitly opts in. Preserve the original bytes until the atomic rename so a refusal never touches the file.

---

### F10 — `NotebookEdit` is a cell-addressed tri-modal editor, with a *different* read format and a real message defect

**Classification: OBSERVED-CLI + OBSERVED-DOC**

**Evidence (CLI).** `claude -p "Use the NotebookEdit tool on nb.ipynb in the current directory to insert a new markdown cell with source 'cell one' at the start. Set edit_mode='insert' and cell_type='markdown'." --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools NotebookEdit`

The call:

```json
{"notebook_path": "<PROJECT>\\nb.ipynb", "new_source": "cell one",
 "cell_type": "markdown", "edit_mode": "insert"}
```

The result:

```
Inserted cell undefined with cell one
```

```json
{"new_source": "cell one", "cell_type": "markdown", "language": "python",
 "edit_mode": "insert", "error": "", "notebook_path": "<PROJECT>\\nb.ipynb",
 "original_file": "{ \"cells\": [], ... }",
 "updated_file": "{ \"cells\": [ {\"cell_type\":\"markdown\",\"source\":\"cell one\",...} ], ... }"}
```

The subsequent `Read` of the same notebook:

```
<cell id="cell-0"><cell_type>markdown</cell_type>cell one</cell id="cell-0">
```

```json
{"type":"notebook","file":{"filePath":"<PROJECT>\\nb.ipynb",
 "cells":[{"cellType":"markdown","source":"cell one","cell_id":"cell-0"}]}}
```

**Evidence (DOC).** `https://code.claude.com/docs/en/tools-reference` — "NotebookEdit tool behavior":

> NotebookEdit modifies a Jupyter notebook one cell at a time, targeting cells by their `cell_id`. It doesn't perform string replacement across the notebook the way Edit does on plain files.
>
> Three edit modes control what happens to the target cell:
> - `replace`: overwrite the cell's source. This is the default.
> - `insert`: add a new cell after the target. With no `cell_id`, the new cell goes at the start of the notebook. Requires `cell_type` set to `code` or `markdown`.
> - `delete`: remove the target cell.

**Observations of implementation detail.**

- The wire field is `notebook_path`, **not** `file_path` — a naming inconsistency with `Edit`/`Write` that a reimplementation must reproduce or consciously normalise.
- `NotebookEdit` does **not** return a `structuredPatch`. It returns `original_file` and `updated_file` — the *entire* notebook before and after. The diff is not computed for notebooks.
- The notebook `Read` format is **completely different** from the text-file format: an XML-ish cell envelope `<cell id="cell-N"><cell_type>…</cell_type>SOURCE</cell id="cell-N">` instead of `N\tline`. The structured form uses `cellType`, `source`, `cell_id` keys.
- The `cell_id` observed was `cell-0` — **position-derived, not content-derived**. A notebook whose cells are reordered or deleted will re-derive ids. This matters: an id is only stable for as long as the cell order is.
- **`"Inserted cell undefined with cell one"` is a genuine defect in the product.** `cell_id` was omitted (there was nothing to anchor to), and the message interpolated the *absent* id rather than the id of the newly created cell. The insert landed correctly — the notebook does contain the cell, and the follow-up `Read` shows `cell-0` — so the defect is in the *message*, not the operation.
- The result carries an `error: ""` field even on success, and a `language` field (`"python"`, taken from the notebook's kernel).
- The `Read` of an **empty** notebook produced `(Read completed with no output)` with `{"type":"notebook","file":{...,"cells":[]}}` — a distinct `type` from the text-file `type: "text"`.

**INFERRED.** `NotebookEdit` is a *structurally different* tool from `Edit`, not a variant of it: different path key, different result shape, no diff, cell-addressed identity, and a different read rendering. An implementation that routes notebooks through the string-replacement engine will get all of this wrong.

**INFERRED.** The `undefined` in the success message suggests the message template is `Inserted cell {cell_id} with {new_source}` and the tool passes the *requested* `cell_id` (absent) rather than the *created* cell's id. A clean-room implementation should report the **created** cell's id — that is strictly better and is a documented, intentional divergence.

**Clean-room implementation opportunity.** A dedicated notebook layer: parse `.ipynb` as JSON, address cells by index-derived id, implement `replace` / `insert` / `delete`, and emit the full `original_file` / `updated_file` pair. Render notebook reads in the cell-envelope format. Validate `cell_type ∈ {code, markdown}` on insert. Report the created cell's id (noting the divergence from the observed `undefined`).

---

### F11 — `MultiEdit` is legacy: accepted in permission rules, never consulted

**Classification: OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/permissions` — "Read and Edit":

> Claude Code checks file permissions against `Edit(path)` and `Read(path)` rules only. If you write a path rule for `Write`, `NotebookEdit`, `Glob`, or the legacy `MultiEdit` tool instead, Claude Code accepts the rule but never consults it, and warns at startup, except for a `Glob` rule passed in `--allowedTools`. Use `Edit(docs/**)` in place of `Write(docs/**)`, `NotebookEdit(docs/**)`, or `MultiEdit(docs/**)`, and `Read(docs/**)` in place of `Glob(docs/**)`. Claude Code doesn't warn about a tool-name rule with no path, such as a deny rule for `Write`; it matches that rule at the tool level everywhere.

**Evidence (DOC).** `https://code.claude.com/docs/en/agent-sdk/typescript` — the `ToolInputSchemas` type defines `FileEditInput`, `FileWriteInput`, `NotebookEditInput`, and `FileReadInput`, but **no** `MultiEditInput`.

**Observations.**

- `MultiEdit` is called "the legacy `MultiEdit` tool" in the permissions doc. It is named in permission rules, in the "not matched by file permission checks" startup warning, and in hook matcher lists — but it is not in the SDK's input schema set.
- The same doc establishes that **`Edit(path)` rules govern `Write` and `NotebookEdit` too** (see F12), so `MultiEdit` is doubly redundant.

**INFERRED.** `MultiEdit` is a backward-compatibility shim: it exists so old permission rules and old hook matchers keep parsing without error, but there is no code path that enforces them against a `MultiEdit` call, and the tool is not part of the current SDK surface. An independent implementation should **omit `MultiEdit` entirely** and document that its omission is a deliberate, source-compatible narrowing — while still accepting `MultiEdit(...)` in rule syntax so that old rule files do not error.

**Clean-room implementation opportunity.** Do not implement `MultiEdit`. Implement the *rule parser* so that `MultiEdit(path)` parses cleanly and is reported by a "rule not matched by file permission checks" diagnostic rather than being silently ignored. This preserves rule-file compatibility at near-zero cost.

---

### F12 — Permission rules for file edits use gitignore syntax with four anchors, and only `Edit(path)` / `Read(path)` are consulted

**Classification: OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/permissions` — "Read and Edit":

> Read and Edit rules both use gitignore pattern syntax with four distinct pattern types:

| Pattern | Meaning | Example | Matches |
|---|---|---|---|
| `//path` | Absolute path from filesystem root | `Read(//Users/alice/secrets/**)` | `/Users/alice/secrets/**` |
| `~/path` | Path from home directory | `Read(~/Documents/*.pdf)` | `/Users/alice/Documents/*.pdf` |
| `/path` | Path relative to the settings source | `Edit(/src/**/*.ts)` | `<primary working directory>/src/**/*.ts` in project settings |
| `path` or `./path` | Path relative to current directory | `Read(*.env)` | `<cwd>/*.env` |

> On Windows, paths are normalized to POSIX form before matching. `C:\Users\alice` becomes `/c/Users/alice`, so use `//c/**/.env` to match `.env` files anywhere on that drive. To match across all drives, use `//**/.env`.

and:

> A `Read` deny rule also blocks the Edit and Write tools on the same path, including creating a new file there. **NotebookEdit isn't covered**, so add an `Edit` deny rule for paths no tool may change. For the Write tool, the check requires Claude Code v2.1.228 or later.

and the warning that deny rules also cover file commands Claude Code recognises in Bash (`cat`, `head`, `tail`, `sed`, `tee`) and Bash redirections (`> file`, `< file`) — but *not* a command that reads files without naming them, or an arbitrary subprocess.

**Observations of implementation detail.**

- The **`/path` anchor is relative to the settings source**, not the cwd and not the repository root. The same rule text resolves differently depending on which file defines it: project settings → `<primary working directory>/path`; user settings → `~/.claude/path`; a `--settings <file>` → `<directory of file>/path`; CLI flags → `<primary working directory>/path`.
- A single leading `/` is **not** an absolute path. The doc is emphatic: *"A pattern like `/Users/alice/file` isn't an absolute path. The single leading slash anchors at the settings source, not the filesystem root. Use `//Users/alice/file` for absolute paths."*
- The **matching depth depends on the rule type** for single-segment directory patterns: `Edit(src/**)` as an *allow* rule matches only `<cwd>/src`, but as a *deny* or *ask* rule it matches a `src` directory at any depth. `Edit(**/src/**)` matches at any depth in every rule type.
- `Read` deny rules are checked **before** the edit gates — the doc places the Read-deny check "Before any of them".
- `NotebookEdit` is **not** covered by `Read` deny rules — a genuine gap in the product's own safety model, and a place where a clean-room implementation can be stricter.

**INFERRED.** The permission layer is orthogonal to the editing layer: the editing tools implement *mechanical* correctness (match, uniqueness, encoding) and the permission layer implements *policy* (may this path be touched at all). A reimplementation must keep them separate — an edit that fails a permission rule should not be reported as a match failure, and vice versa.

**Clean-room implementation opportunity.** Implement a gitignore-syntax matcher with the four anchor types and the settings-source-relative resolution table, POSIX-normalise Windows paths before matching, and support the allow/deny/ask depth asymmetry. Consult **only** `Edit(path)` and `Read(path)` for file tools — but *do* apply `Read` deny rules to `NotebookEdit` as well, and document that as a deliberate safety improvement over the reference product (see the "deliberate divergences" list in §8).

---

### F13 — Permission modes govern whether edits prompt, and the mode is visible per tool call

**Classification: OBSERVED-CLI + OBSERVED-DOC**

**Evidence (CLI).** Every tool result in the observed runs carried a `tool_result_meta` block:

```json
[{"id": "<TOOL_CALL_ID>",
  "permission_decision": {"decision": "accept", "source": "config", "reason_type": "rule"}}]
```

Other observed variants: `"reason_type": "mode"` (auto-accepted by the permission mode rather than by a rule), and `"decision": "reject"` with `"non_execution_kind": "user-rejected"`.

**Evidence (CLI).** `claude --help`:

```
--permission-mode <mode>              Permission mode to use for the session
                                      (choices: "acceptEdits", "auto",
                                      "bypassPermissions", "manual",
                                      "dontAsk", "plan")
```

Note: the help text lists **`manual`**, not `default` — a discrepancy against the commonly cited `default` mode name.

**Observations of implementation detail.**

- The `permission_decision` metadata is attached to the **tool result**, not to a separate event. This means an automation consumer reading `stream-json` gets the *reason* each edit was permitted, per call, without a separate event stream.
- `source: "config"` distinguishes "a rule matched" from other sources (e.g. a user prompt).
- `reason_type` distinguishes the two auto-accept paths: `rule` vs `mode`. A consumer can therefore tell "this was allowed because `Edit(src/**)` matched" from "this was allowed because the session is in `acceptEdits`".

**OBSERVED-CLI (corrected 2026-10-21).** `acceptEdits` is the mode that matters most for this area. In the observed runs, `Edit` and `Write` were accepted with `reason_type: "rule"` (because `--allowedTools Read Edit` was on the command line) or `"mode"` (because the tool was otherwise permitted), while `Bash` and `PowerShell` calls in the same sessions were **rejected** with `non_execution_kind: "user-rejected"`.

**The reason those calls were rejected is not that the mode split the tool set** — that inference
was drawn here and is now retracted (see below). The rejections were command-shape and parse
failures: a multi-operation shell command and an over-long PowerShell command line. Neither is
mode-dependent. `acceptEdits` does *not* reject a bare `Bash` call categorically; it
auto-approves the enumerated filesystem-command set.

**CORRECTED (2026-10-21) — this inference was wrong and is retracted.** The claim that
`acceptEdits`'s blast radius is *"edits only"* is **false**. The reference's `acceptEdits` mode
auto-approves **file edits *and* an enumerated set of common filesystem shell commands**:
`mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, and `sed` (plus `Set-Content`, `Add-Content`,
`Clear-Content`, `Remove-Item` on Windows) — verbatim from
`agent-reference-shots/docs-cache/permission-modes.md`, "Auto-approve file edits with acceptEdits
mode". Reproduced live: under `--permission-mode acceptEdits`, `Bash {"command":"mkdir
subdir_xyz"}` was **accepted** and the directory was created.

The earlier rejections in the captures above were **not** a mode limitation. They were
command-shape and parse failures that would prompt in any mode: a multi-operation shell command
("This Bash command contains multiple operations. The following parts require approval") and a
PowerShell parse failure ("pwsh exited with code 1: The command line is too long"). Both are
consistent with the mode's real behaviour.

**This is a material security-relevant correction.** `rm` is in the `acceptEdits` auto-approve
list. An independent implementation that encodes "acceptEdits = file edits only" is *stricter*
than the reference; one that encodes the reference exactly accepts `rm` without a prompt. Both
are defensible, but the choice must be made deliberately and documented — not inherited by
accident from a wrong inference. Keel's position is recorded in `claude-code-evidence.md` R7 and
in `security-plan.md`; it is a deliberate narrowing, not a compatibility requirement.

**Clean-room implementation opportunity.** Emit the same per-result permission metadata (`decision`, `source`, `reason_type`, `non_execution_kind`). Implement modes as data: a table mapping (mode, tool) → (decision, reason_type). Model `acceptEdits` as "auto-accept `Edit`/`Write`/`NotebookEdit`/`MultiEdit` **plus the enumerated filesystem-command set**; everything else falls through to the normal path." If Keel narrows the command set, the narrowed list MUST be enumerated in the specification rather than left implicit — an unenumerated narrowing is a narrowing nobody can reason about.

---

### F14 — Checkpointing is snapshot-per-turn with a 100-checkpoint window, and its on-disk layout is a plain, reproducible format

**Classification: OBSERVED-CLI + OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/checkpointing`:

> Every prompt you send that starts a turn creates a new checkpoint
> Claude Code keeps file snapshots for the 100 most recent checkpoints in a session. Discarding an older checkpoint deletes the snapshot files that no remaining checkpoint references, except each file's first snapshot, which the VS Code extension uses as the baseline for its session diffs.
> Claude Code saves checkpoints with the conversation, so you can still run `/rewind` after you resume a session

The rewind menu offers six options: **Restore code and conversation**, **Restore conversation**, **Restore code**, **Summarize from here**, **Summarize up to here**, **Never mind**. `/rewind` is reachable by double-`Esc` when the prompt input is empty; the docs note that if the input contains text, double-`Esc` clears it instead and the cleared text is saved to the input history.

**Evidence (CLI).** On-disk inspection of `~/.claude/file-history/`:

```
~/.claude/file-history/2200632f-7049-4f5a-b43b-9a04e451fa6e/043b611b640b254b@v2
~/.claude/file-history/2200632f-7049-4f5a-b43b-9a04e451fa6e/06458d012098dee1@v2
~/.claude/file-history/2200632f-7049-4f5a-b43b-9a04e451fa6e/0e160426483cff37@v2
~/.claude/file-history/2200632f-7049-4f5a-b43b-9a04e451fa6e/0e160426483cff37@v3
~/.claude/file-history/2200632f-7049-4f5a-b43b-9a04e451fa6e/242bfaa49d1f26d1@v2
~/.claude/file-history/2200632f-7049-4f5a-b43b-9a04e451fa6e/242bfaa49d1f26d1@v3
… (and many more, with @v2 and @v3 pairs)
```

The snapshot files are **raw file content** — the previously-observed plan markdown at `2200632f-…/043b611b640b254b@v2` was a readable 2,422-byte markdown document.

**Observations of implementation detail.**

- The layout is `file-history/<session-id>/<16-hex-hash>@v<N>`. The `<vN>` suffix is a **version counter for the same file within the session** — the `@v2`/`@v3` pairs above are successive snapshots of the same path.
- The `16-hex` name is a hash — of the path, most likely — and the version counter disambiguates collisions. **INFERRED:** the hash is of the file path (not of the content), because the same file appears at successive versions and different files appear at different hashes.
- The snapshot is the **raw file bytes**, not a diff and not a compressed archive. This makes the format trivially reimplementable and independently inspectable.
- `~/.claude/` also contains `plans/` (plan-mode plan files), `projects/<encoded-path>/<session-id>.jsonl` (transcripts, in which the `Edit` result appears as `.toolUseResult.structuredPatch`), `shell-snapshots/`, `debug/`, `history.jsonl`, `settings.json`, and `stats-cache.json`.

**INFERRED.** Storing raw content rather than diffs is a deliberate trade: it costs disk (a 100-checkpoint window × full file content) but makes restore trivially correct, including for files deleted since. It also makes the store directly usable by other tools — a clean-room implementation can adopt the same format and be compatible with the reference product's history directory, which would be a real interoperability win.

**Clean-room implementation opportunity.** Implement checkpointing as: on each turn boundary, for every tracked path, copy the current bytes to `file-history/<session-id>/<hash-of-path>@v<N>`; retain the 100 most recent checkpoints; garbage-collect unreferenced snapshots (never delete a file's *first* snapshot, if you want IDE-diff parity). Support the six rewind actions. Use raw content, and name the files exactly this way.

---

### F15 — Checkpointing covers `Write`/`Edit`/`NotebookEdit` only, and its stated limitations are precise

**Classification: OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/agent-sdk/file-checkpointing`:

> Only changes made through the Write, Edit, and NotebookEdit tools are tracked. Changes made through Bash commands (like `echo > file.txt` or `sed -i`) are not captured by the checkpoint system, and neither are edits a subagent applies, except a skill with `context: fork` that runs in the foreground.

and its limitations table:

| Limitation | Description |
|---|---|
| Write/Edit/NotebookEdit tools only | Changes made through Bash commands are not tracked |
| Subagent edits | Edits a subagent applies aren't tracked, except a skill with `context: fork` running in the foreground. A rewind reverts them only in files the main conversation had already edited; use git to revert the rest |
| Same session | Checkpoints are tied to the session that created them |
| File content only | Creating, moving, or deleting directories is not undone by rewinding |
| Local files | Remote or network files are not tracked |

and, from `https://code.claude.com/docs/en/checkpointing`:

> **Symlinked and hard-linked paths not restored** — … Claude Code skips any tracked path that is a symlink or hard link and shows a `Restored the code, but skipped N files` warning.

**Evidence (CLI).** Corroborated in the observed run: the `Bash` append to `stale.txt` was **not** rolled into the edit's diff as a tracked change — it appeared only as context, and the resulting file was not a checkpoint candidate in its own right.

**Observations.**

- The tool set is exactly `{Write, Edit, NotebookEdit}`. `MultiEdit` is not in the list (consistent with F11).
- Directory creation/move/delete is not undone — only **file content** is snapshotted.
- Symlink and hard-link paths are skipped on restore, with a visible count in the warning.

**INFERRED.** The checkpoint store is a *content* store, not a *filesystem* store. Anything that changes the directory tree (creating a directory, renaming a file) is outside its model, and the product is explicit about this. A clean-room implementation that wants stronger guarantees must add directory-structure snapshots — a deliberate improvement over the reference.

**INFERRED.** The "Bash changes are not tracked" limitation interacts with F5 in a way that is easy to miss: because the *Edit* path matches against current disk content, an agent that uses Bash to mutate a file and then Edits it **will** see the Bash change in the Edit's diff — but the **Bash change itself is not independently revertible**. The recovery story for Bash-made changes is git, not `/rewind`.

**Clean-room implementation opportunity.** Restrict the tracked-tool set to `{Write, Edit, NotebookEdit}`. Record, per checkpoint, the set of (path, version) pairs. On restore, rewrite each path to its snapshot bytes, **delete** files that the checkpoint created and that no longer should exist, and skip symlinks/hard links with a `skippedLinks` count in the result. Optionally extend to directory-structure snapshots as a documented improvement.

---

### F16 — The SDK exposes checkpointing as a first-class API with an exact option set

**Classification: OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/agent-sdk/file-checkpointing`:

| Option | Python | TypeScript | Description |
|---|---|---|---|
| Enable checkpointing | `enable_file_checkpointing=True` | `enableFileCheckpointing: true` | Tracks file changes for rewinding |
| Receive checkpoint UUIDs | `extra_args={"replay-user-messages": None}` | `extraArgs: { 'replay-user-messages': null }` | Required to get user message UUIDs in the stream |

and the CLI form:

```bash
CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true claude -p --resume <session-id> --rewind-files <checkpoint-uuid>
```

> The `--rewind-files` flag doesn't appear in `claude --help` output, but the CLI accepts it as shown. When the rewind succeeds, the command prints `Files rewound to state at message <checkpoint-uuid>` and exits without sending a prompt.

and the rewind API:

> `rewindFiles()` (TypeScript) or `rewind_files()` (Python) … File rewinding restores files on disk to a previous state. It does not rewind the conversation itself. The conversation history and context remain intact after calling `rewindFiles()`…

and the result type:

> [`RewindFilesResult`](/docs/en/agent-sdk/typescript#rewindfilesresult) counts every skipped path in its `skippedLinks` field.

**Observations of implementation detail.**

- The checkpoint identity is the **UUID of the first user message** of a turn. `message.uuid` from the `UserMessage` is the restore point. The `replay-user-messages` option is what makes user messages appear in the stream with UUIDs at all.
- `extra_args={"replay-user-messages": None}` / `extraArgs: { 'replay-user-messages': null }` — the value is `None`/`null`, i.e. a **flag with no value**, not a boolean.
- The CLI flag `--rewind-files` is **hidden from `--help`** but functional — a deliberate undocumented surface. The `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING` env var is the gate for bare `-p` runs; the SDK sets it internally when `enableFileCheckpointing` is on, and *"the bare CLI never sets it."*
- The documented failure modes are specific: `"No file checkpoint found for this message"`, `"File rewinding is not enabled"`, `"ProcessTransport is not ready for writing"`.
- The settings key `fileCheckpointingEnabled` (default `true`) governs the interactive path; the docs note *"In a `-p` run or an Agent SDK session, Claude Code ignores this key."* The env override is `CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING`, and *"whichever of the two turns it off, the other can't turn it back on."*

**INFERRED.** The checkpoint design is a clean three-part separation: **(a)** the *harness* snapshots the file; **(b)** the *stream* carries a stable identifier for the moment (the user-message UUID); **(c)** the *client* decides when to rewind. The SDK's `rewindFiles()` is a *file* operation with no conversation effect — the conversation rewind is a separate feature (`/rewind` in the TUI) that can be combined with it. A clean-room implementation should keep those two concerns separate, as the reference does.

**Clean-room implementation opportunity.** Adopt the same API shape: `enableFileCheckpointing` / `enable_file_checkpointing`, `rewindFiles()` / `rewind_files()`, `RewindFilesResult { skippedLinks }`, and the `replay-user-messages` flag. Use the first user-message UUID of a turn as the checkpoint id — it is already in the message, so it costs nothing. Expose `--rewind-files` (it may be hidden; the flag works either way).

---

### F17 — `/diff` is two different UIs, and its per-turn views come from the tool log, not from git

**Classification: OBSERVED-DOC**

**Evidence (DOC).** `https://code.claude.com/docs/en/interactive-mode` — "Review changes with /diff":

> What `/diff` opens depends on which renderer is active:
> - **Fullscreen rendering**: the diff panel opens beside the conversation. It stays open and updates while you keep working.
> - **Classic renderer**: the diff dialog opens above the prompt, and you close it when you're done reading.
>
> The panel and the dialog both come from `cc-plugin-diff`, one of the mods built into Claude Code. If you disable that mod in `/plugin`, `/diff` opens Claude Code's earlier panel and diff viewer instead.
>
> … The panel and the dialog also offer a view of each turn's edits once Claude has edited files. **These turn views come from Claude's file edits rather than from git**, so a change Claude makes through a shell command appears only under `Current`, the working-tree view.

**Diff panel requirements and behaviour:**

> - Fullscreen rendering
> - A git repository
> - A terminal at least 110 columns wide
> - Claude Code v2.1.287 or later
>
> The panel also opens on its own once Claude starts editing files, if your terminal is at least 144 columns wide. After you've opened it yourself with `/diff`, later sessions open it as soon as Claude edits a file in any terminal wide enough to fit it. Close the panel and it stays closed, in this session and later ones, until you run `/diff` again.

> - **Jump to a file**: click its row in the list. … **Ask Claude about a file's changes**: click `ask`, at the right of the file's name above its diff. Claude Code attaches that file's diff to your next prompt, and the button reads `asked ✓` until you send that prompt. Asking on a second file replaces the first.
> - **Show one turn's edits**: click the `source` picker in the panel's header, then choose a turn with `Up` and `Down` and press `Enter`. Turns are labeled `T1`, `T2`, and so on. The picker appears once Claude has edited files, and `Current` returns you to the working tree.
> - **Show the files the panel leaves out**: the list skips test files and generated files, and collapses changes from before this session into one line at the bottom. Click either count line to expand it.
> - **Change what the panel compares against**: press `Ctrl+X B` to cycle from this session's changes, to your uncommitted changes as one list, to everything since your branch split from the default branch. Claude Code remembers the choice for each repository.

**Diff dialog keys:** `Up`/`Down` select a file, `Enter` opens the file's diff, `Esc` returns to the list or closes, `Tab` moves to the `source` picker (choose `Current` or a turn view) or to the `ask` button.

**Observations of implementation detail.**

- There are **two** diff UIs and **three** comparison bases, selected by `Ctrl+X B` and **remembered per repository**.
- The `source` picker labels turns `T1`, `T2`, … and `Current`. The `T`-labels are turn indices, and a turn appears only if it "led Claude to edit files."
- The `ask` button attaches a **file's diff to the next prompt** — a review→agent handoff. It reads `asked ✓` until the prompt is sent, and asking about a second file replaces the first. This is a distinctive and very useful review affordance.
- The panel **skips test files and generated files** from the list, and collapses pre-session changes into one summary line.
- The diff panel requires a **git repository** — but the per-turn views come from the tool log, not git. So a non-git project gets the turn views but not the working-tree view.
- `/diff` is listed in `https://code.claude.com/docs/en/commands` as: *"Review the changes in your working tree, including the edits Claude has made so far."*

**INFERRED.** The reference product maintains **two independent change logs**: git's (the working tree) and its own (the tool-edit log, indexed by turn). The `T1`/`T2`/`Current` selector is a view switch between them. This is the cleanest available evidence that the tool layer and the diff layer are decoupled — the tool layer records a per-turn edit log, and the diff layer renders either that log or git. A clean-room implementation should maintain the same per-turn edit log, because it is the only way to offer "what did you change in that turn?" — and it is the mechanism that makes checkpointing and per-turn diffs the same underlying data.

**Clean-room implementation opportunity.** Maintain a per-turn edit log: for each turn, the list of (path, before-hash, after-hash, patch) records produced by the editing tools. Render two views from it: the *working-tree* view (git) and the *turn* view (log). Implement the `source` picker with `T1`/`T2`/`Current` labels, the `ask` affordance (attach a file's diff to the next prompt), the `Ctrl+X B` comparison-base cycle with per-repository persistence, and the "skip test and generated files" list filter. The diff panel's terminal-width requirements (110 / 144 columns) are implementation detail, but the *thresholds* are worth copying.

---

### F18 — Review is a skill, findings have a machine-readable schema, and `--fix` re-enters the normal edit path

**Classification: OBSERVED-DOC + OBSERVED-CLI**

**Evidence (DOC).** `https://code.claude.com/docs/en/code-review-local`:

> `/code-review` … Claude reviews the changes on your branch, looks for correctness bugs, and reports what it found in your conversation. … `/review` is an alias of `/code-review`.

Flags and levels:

> * `--fix`: also asks Claude to apply the findings to your working tree after the review. Its edits go through your permission mode.
> * `--comment`: posts the findings on a GitHub pull request as inline comments, or on a GitLab merge request as a single note
> * `--max-findings <n>`, `--max-findings all`, or `--max-findings default`: reports up to `n` findings, or every finding with `all`, in place of the review's usual limit. **Where the review reports through the findings tool, the limit is 32.**

> The review runs as a background subagent with its own context window, so it doesn't fill your conversation. The findings arrive in your conversation when the review completes.

Effort levels: `low | medium | high | xhigh | max | ultra`. With no level, the review reuses the last level typed, even in an earlier session, and shows a notice such as `Reusing high effort, the level you typed last time`.

Targets:

| To point the review at | Type |
|---|---|
| Your current branch and uncommitted changes | `/code-review` |
| Your last 15 commits | `/code-review HEAD~15..HEAD` |
| One branch against another | `/code-review main...my-feature` |
| A single commit | `/code-review abc1234^..abc1234` |
| A pull request by number | `/code-review 1234` |
| A file or directory path | `/code-review src/auth` |

**How findings are reported:**

> Claude reports the findings as text in the reply in both of these runs: in a terminal session, where `/code-review` runs the review as a forked subagent; in a `-p` run with text or JSON output.
>
> In a host application that requests the findings list, such as the desktop app, Claude reports the review's findings through the `ReportFindings` tool instead. The report appears as a findings list, and each entry shows the file location, a one-sentence summary, and a category tag such as `correctness` when the finding carries one. A host request applies at every effort level and requires Claude Code v2.1.218 or later.

**Evidence (DOC).** `https://code.claude.com/docs/en/commands` — the `/diff` → `/code-review` relationship:

> **Before you ship.** `/diff` shows what changed. `/code-review` checks the current diff for correctness bugs and can apply the findings with `--fix`; pass a PR number, such as `/code-review high 1234`, to review a pull request instead. `/review` is an alias. `/code-review ultra` runs a multi-agent review in the cloud. `/security-review` checks the diff for security vulnerabilities.

**Evidence (CLI).** `claude ultrareview --help` exposes:

```
--json        (print raw bugs.json)
--no-post / --post
--timeout <minutes>   (default 45)
```

**Observations of implementation detail.**

- The review is a **bundled skill**, not a hard-coded command: *"its instructions are built into Claude Code, so there is no `SKILL.md` file on disk to open or edit."* A project skill named `code-review` replaces it, while `/review` keeps running the bundled one. **This is the key architectural fact**: the review is a *prompt*, and the mechanism is a skill.
- `--fix` **does not bypass the permission model**: *"Its edits go through your permission mode."* A clean-room implementation must route review-applied fixes through the same `Edit`/`Write` path, with the same gates, the same permission metadata, and the same checkpointing. This is a strong parity target because it means review fixes are *recoverable* exactly like normal edits.
- The findings limit is **32** where the review reports through the findings tool.
- The review runs in a **background subagent with its own context window** — the review does not consume the main conversation's context.
- `ReportFindings` is a **deferred tool** in this build, and its schema was not loadable via `ToolSearch` (it returns only a `{"type":"tool_reference","tool_name":"ReportFindings"}` reference, with no JSON schema) — see the "ToolSearch" note in §9.

**INFERRED.** The review feature is the highest-leverage reuse point in the whole editing area: because `--fix` routes back through the ordinary edit path, an implementation that gets the edit path right gets review-fix for free, including checkpoints and permission gating. The review *prompt* is a separate concern; the review *mechanism* is the editing subsystem.

**INFERRED.** The `ReportFindings` schema (file location, one-sentence summary, category tag such as `correctness`) is the natural structured output for a review, and matches the shape of a findings list a host application can render. A clean-room implementation should define an equivalent structured findings schema.

**Clean-room implementation opportunity.** Implement review as a **skill** (a prompt + a target spec), not as a bespoke engine. Support the six effort levels, the target grammar (branch / range / SHA / PR number / path), `--fix` (routed through the normal edit path, hence checkpointed and permission-gated), `--comment`, and `--max-findings` with a 32-item cap on the structured path. Report findings either as text or through a `ReportFindings`-equivalent tool with `{file, summary, category}` fields.

---

## 4. Capability table

| # | Capability | Edit | Write | NotebookEdit | MultiEdit | Classification |
|---|---|---|---|---|---|---|
| 1 | Create a new file | — | ✅ | — | legacy | OBSERVED-CLI |
| 2 | Overwrite an existing file (full content) | — | ✅ | — | legacy | OBSERVED-CLI |
| 3 | Partial modification of an existing file | ✅ | — (doc says use Edit) | — | legacy | OBSERVED-CLI + DOC |
| 4 | Append / merge | ❌ | ❌ | — | — | OBSERVED-DOC |
| 5 | Exact string replacement | ✅ | — | — | legacy | OBSERVED-CLI |
| 6 | Regex / fuzzy matching | ❌ | — | — | — | OBSERVED-DOC |
| 7 | `replace_all` | ✅ | — | — | legacy | OBSERVED-CLI |
| 8 | Cell-level notebook edit | — | — | ✅ (replace/insert/delete) | — | OBSERVED-CLI + DOC |
| 9 | Structured diff output | ✅ `structuredPatch` | ✅ `structuredPatch` | ❌ (`original_file`/`updated_file`) | legacy | OBSERVED-CLI |
| 10 | Diff for a create | — | ✅ (`[]`) | — | — | OBSERVED-CLI |
| 11 | Read-before-edit gate | ✅ (model-dependent) | ✅ (model-dependent) | ✅ (always, per doc) | legacy | OBSERVED-CLI + DOC |
| 12 | Partial-read (`PARTIAL view`) always gates | ✅ (per doc) | ✅ (per doc) | ✅ (per doc) | — | OBSERVED-DOC |
| 13 | Bash-view satisfies the read gate | ✅ (exact allow-list) | ✅ (same) | — | — | OBSERVED-DOC |
| 14 | Non-UTF-8 refusal | ✅ (refuses) | ✅ (allowed; encoding lost) | ✅ (refuses) | — | OBSERVED-DOC |
| 15 | `U+FFFD` guard | — | ✅ (rejects content) | — | — | OBSERVED-DOC |
| 16 | Stale-file detection and recovery | ✅ (`staleRecovered`) | — | — | — | OBSERVED-CLI + DOC |
| 17 | "Content not in model context" flag | ✅ | — | — | — | OBSERVED-CLI |
| 18 | Redundant-Read suppression | ✅ (`file_unchanged`) | — | ✅ | — | OBSERVED-CLI |
| 19 | Per-call permission metadata | ✅ | ✅ | ✅ | — | OBSERVED-CLI |
| 20 | Checkpointing | ✅ | ✅ | ✅ | ❌ | OBSERVED-DOC |
| 21 | `Edit(path)` rules govern all file edits | ✅ | ✅ | ✅ (not by `Read` rules) | ❌ | OBSERVED-DOC |
| 22 | Multi-edit in one call | ❌ (use `replace_all`) | — | — | ✅ (legacy) | OBSERVED-DOC |
| 23 | Line-ending preservation | ❌ (writes LF) | ❌ (writes LF) | ❌ | — | OBSERVED-CLI |
| 24 | Directory create/move/delete | ❌ | ❌ | ❌ | — | OBSERVED-DOC |

---

## 5. Evidence references

### 5.1 Public documentation fetched (OBSERVED-DOC)

| Page | Used for |
|---|---|
| `https://code.claude.com/docs/en/tools-reference` | Edit / Write / NotebookEdit behaviour; the three-gate contract; non-UTF-8 rules; permission-rule interaction |
| `https://code.claude.com/docs/en/permissions` | `Edit(path)` / `Read(path)` rule semantics; gitignore syntax; the four anchor types; Windows POSIX normalisation; `MultiEdit` legacy status |
| `https://code.claude.com/docs/en/checkpointing` | Checkpoint model; 100-checkpoint window; the six rewind actions; the four documented limitations |
| `https://code.claude.com/docs/en/agent-sdk/file-checkpointing` | `enableFileCheckpointing` / `enable_file_checkpointing`; `rewindFiles()` / `rewind_files()`; `replay-user-messages`; `--rewind-files`; `RewindFilesResult.skippedLinks`; the limitations table |
| `https://code.claude.com/docs/en/agent-sdk/typescript` | `FileEditInput`, `FileWriteInput`, `NotebookEditInput`, `FileReadInput`; the absence of `MultiEditInput` |
| `https://code.claude.com/docs/en/interactive-mode` | `/diff` panel and dialog; turn views `T1`/`T2`/`Current`; `ask` button; `Ctrl+X B` |
| `https://code.claude.com/docs/en/code-review-local` | `/code-review` levels, flags, targets, effort reuse, `ReportFindings` |
| `https://code.claude.com/docs/en/commands` | `/diff`, `/code-review`, `/review`, `/security-review`, `/simplify`; the "Before you ship" workflow |
| `https://code.claude.com/docs/en/settings-reference` | `fileCheckpointingEnabled`, `bashEditDiffEnabled`, `diffTool`, `cleanupPeriodDays` |
| `https://code.claude.com/docs/en/permission-modes` | The six modes and their baselines |

### 5.2 Exact CLI commands run (OBSERVED-CLI)

```bash
# Edit — success path
claude -p "Read demo.js, then use Edit to replace the string 'const timeout = 30;' with 'const timeout = 60;'." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read Edit

# Edit — uniqueness failure (forced)
claude -p "Read dup.txt. Then IMMEDIATELY call the Edit tool with exactly these arguments: file_path=<abs path of dup.txt>, old_string='dup line', new_string='CHANGED', replace_all=false. Do NOT add any surrounding context to old_string. Do NOT add extra lines. Just make that one Edit call and report the tool result verbatim." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read Edit

# Edit — string not found (forced)
claude -p "Use the Edit tool on notfound.js: old_string='const timeout = 999;', new_string='const timeout = 60;'. Do NOT read the file first, do NOT grep it. Make exactly one Edit call and report the tool result verbatim." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Edit

# Edit — replace_all
claude -p "Use the Edit tool on dup2.txt: old_string='dup line', new_string='CHANGED', replace_all=true. Do NOT read first. Make exactly one Edit call and report the tool result verbatim." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Edit

# Edit — never-read file
claude -p "Use the Edit tool on the file unread.txt in the current directory: replace the string 'never read' with 'now read'. Do NOT call Read first. Make exactly one Edit call." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Edit

# Edit — stale file (external modification between Read and Edit)
claude -p "Step 1: Read stale.txt. Step 2: Use Bash to append a line 'EXTERNAL CHANGE' to stale.txt. Step 3: Use Edit on stale.txt to replace 'stale content here' with 'updated content'. Make all three calls and report every tool result verbatim, especially the Edit one." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read Edit Bash

# Write — create
claude -p "Use the Write tool to create the file wrote.md in the current directory with exactly this content: '# Hello\n\nWritten by Claude.\n'" \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Write

# Write — overwrite an existing, never-read file
claude -p "Use the Write tool on unwritten.txt in the current directory with content 'brand new content\n'. Do NOT read the file first. Make exactly one Write call and report the tool result verbatim." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Write

# NotebookEdit — insert a markdown cell
claude -p "Use the NotebookEdit tool on nb.ipynb in the current directory to insert a new markdown cell with source 'cell one' at the start. Set edit_mode='insert' and cell_type='markdown'. Make the call and report the tool result verbatim." \
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools NotebookEdit

# Self-description surfaces
claude --help
claude doctor
claude auto-mode defaults
claude ultrareview --help
```

### 5.3 On-disk artefacts inspected (OBSERVED-CLI)

```
~/.claude/file-history/<session-id>/<16-hex-hash>@v<N>     raw file-content snapshots
~/.claude/plans/                                          plan-mode plan files
~/.claude/projects/<encoded-path>/<session-id>.jsonl      session transcripts
~/.claude/settings.json, shell-snapshots/, debug/, history.jsonl
```

### 5.4 Saved captures

`agent-reference-shots/area4-file-editing/`

| File | Contents |
|---|---|
| `interface-capture.txt` | The rendered CLI surface for all 14 observed cases, with the exact tool inputs, results, and diff records |
| `01-edit-success.jsonl` | Edit success (read → edit) |
| `02-edit-uniqueness-error.jsonl` | Edit uniqueness failure |
| `03-edit-not-found-error.jsonl` | Edit string-not-found failure |
| `04-write-create.jsonl` | Write create |
| `05-write-overwrite.jsonl` | Write overwrite after a Read |
| `06-edit-unread-file.jsonl` | Edit on a never-read file (the relaxation) |
| `07-edit-replace-all.jsonl` | Edit with `replace_all: true` |
| `08-notebookedit-insert.jsonl` | NotebookEdit insert + notebook `Read` + redundant-`Read` suppression |
| `09-edit-stale-external-change.jsonl` | Edit against a file modified on disk between Read and Edit |

All captures are sanitized: user paths → `<PROJECT>` / `<HOME>`, session and tool-call ids → `<UUID>` / `<TOOL_CALL_ID>`, and the encoded project path → `<ENCODED_PROJECT_PATH>`. A grep for the literal username across all captures returns zero matches.

---

## 6. Dependencies

### 6.1 Required for the editing layer

| Dependency | Why | Notes |
|---|---|---|
| A model that emits tool calls | The whole editing surface is model-driven | Any provider; the SDK exposes `permissionMode` per provider |
| Filesystem read + write | `Read`/`Edit`/`Write`/`NotebookEdit` | UTF-8 codec with strict decode; UTF-16LE BOM special case |
| A diff algorithm | `structuredPatch`, the `/diff` panel, the checkpoint summary | A Myers-style diff producing `{oldStart, oldLines, newStart, newLines, lines[]}` |
| A JSON parser | `.ipynb` handling | nbformat 4.x; the observed notebook used `nbformat: 4, nbformat_minor: 4` |
| A checkpoint store | `/rewind` | `file-history/<session>/<hash>@v<N>`; raw bytes |

### 6.2 Required for the review surface

| Dependency | Why | Notes |
|---|---|---|
| git | `/diff`'s working-tree view; `/code-review`'s default target | The diff panel explicitly requires a git repository |
| A subagent runtime | `/code-review` runs as a background subagent | Its own context window |
| A skills runtime | `/code-review` is a bundled *skill*, not a hard-coded command | Project skills can override it |
| `gh` / `glab` CLIs | `--comment` posting | Optional; the product falls back to printing findings when `glab` is absent |

### 6.3 Network / account / provider dependencies

| Feature | Network? | Account? | Provider? |
|---|---|---|---|
| `Edit` / `Write` / `NotebookEdit` | No (local) | No | No — model only |
| `structuredPatch` / `originalFile` | No | No | No |
| Checkpointing + `/rewind` | No | No | No |
| `/diff` working-tree view | No (reads local git) | No | No |
| `/diff` per-turn views | No (reads the local edit log) | No | No |
| `/code-review` (local) | Model calls only | No | Yes |
| `/code-review --comment` | Yes (GitHub / GitLab) | Yes (repo access) | — |
| `/code-review ultra` / `claude ultrareview` | Yes (cloud) | Yes (claude.ai) | Anthropic only; **not** on Bedrock/Vertex/Foundry, not with ZDR, not with HIPAA |
| `diffTool: "auto"` (IDE viewer) | No | No | Needs a VS Code / JetBrains IDE connected |

**INFERRED.** The entire *editing* layer is local and provider-independent. Only the *review-posting* and *cloud review* features need network and an account. This is a good property for a clean-room implementation: the hard part of this area has no external dependency at all.

---

## 7. Limitations of this investigation

1. **No terminal screenshot.** REA's process/terminal-capture backend returned a hard `capability_unavailable` error on Windows: *"Windows PTY process capture is unavailable because this adapter does not yet verify descendant cleanup. Use Linux (including WSL for Linux commands) or macOS."* The captures in `agent-reference-shots/area4-file-editing/` are therefore the CLI's own text output, not images. The TUI's *rendering* of these results (colours, borders, spinner, the diff panel's visual layout) is **not** captured.
2. **The interactive TUI was not exercised.** All observations are from `--print --output-format stream-json`. The `/diff` panel and dialog, `/rewind` menu, plan-mode approval, and the permission prompt UI are **documented but not observed**.
3. **The model is not Claude Opus 5.5.** This host is configured against a custom `ANTHROPIC_BASE_URL` serving `minimax/minimax-m3.1-flash:free`. `claude doctor` reports *"Not connected to the Anthropic API (api.anthropic.com)"* and *"Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL"*. Everything model-dependent — notably the read-before-edit relaxation (F6) — is **INFERRED** with respect to the reference model.
4. **Subscription-gated behaviour is unobserved.** Cloud `ultrareview`, GitHub Code Review, managed settings, organisation policy, Remote Control, and artifact publishing are **INFERRED from docs only**.
5. **No hook payloads were captured for `Edit`.** Attempts to author a `PostToolUse` hook config or capture script were denied by the auto-mode classifier — *"Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Self-Modification]."* and *"…Reason: [Auto-Mode Bypass]."* The hook payload shape for file-edit tools therefore rests on **OBSERVED-DOC** alone.
6. **Some error paths were not exercised.** The non-UTF-8 refusal, the `PARTIAL view` gate, symlink/hard-link restore skips, the `No files were restored` error, and the `RewindFilesResult.skippedLinks` field are all **OBSERVED-DOC** only.
7. **`ReportFindings` has no loadable schema.** `ToolSearch` with `select:ReportFindings` returns only `{"type":"tool_reference","tool_name":"ReportFindings"}` — a reference, not a JSON schema. The findings schema in F18 is therefore from the docs, not from a wire capture.
8. **No decompilation, disassembly, or source-map extraction was performed** — by the compliance boundary in `agent-reference-shots/TERMS-NOTES.md`. Some behaviours (e.g. the exact internal ordering of the edit gates) are documented but not independently confirmed against the implementation.
9. **Text fetched from the web was treated as untrusted data.** No instruction found in any fetched document was executed. One page (`https://code.claude.com/docs/en/iam`) returned an authentication page instead of the requested permission content; the correct source (`/docs/en/permissions`) was used instead.

---

## 8. Unresolved questions (UNKNOWN)

1. **Does Claude Opus 5.5 take the read-before-edit relaxation?** The docs say "newer models can edit an unread file when reading it wouldn't need a permission prompt and the Read tool is available." The relaxation was observed only on a non-Anthropic model via a custom gateway. **UNKNOWN** for the reference model. A clean-room implementation should make this a *policy* rather than a constant (F6).
2. **What is the exact internal ordering of the edit gates?** The docs list read-before-edit, match, uniqueness; the Read-deny check is described as happening "Before any of them." Whether the match is evaluated before or after the uniqueness check (i.e. is "not found" checked first?) is not stated, though the observed behaviour is consistent with "count matches, then 0 → not found, >1 and not replace_all → not unique."
3. **What exactly is `contentNotInModelContext`?** It is observable but undocumented. Is it a strict inverse of "the model has this file's content"? Is it set for a `Write` on a never-read file? (Observed: **not** set on `Write`.) **UNKNOWN.**
4. **What is `userModified` in practice?** The observed value was always `false`. The field name implies it becomes `true` when the *user* edits the file between the model's read and the agent's edit. That case was not exercised. **UNKNOWN.**
5. **Is `staleRecovered` set when the file was changed by the *agent itself* (e.g. an earlier `Write` in the same turn) rather than externally?** The stale case was exercised only with an external `Bash` modification. **UNKNOWN.**
6. **Is `originalFile` always the pre-edit *current-disk* content, or the pre-edit content of the last model read when they agree?** The observed stale case shows current-disk. **UNKNOWN** whether the field is ever populated from the model's cache.
7. **What is the exact line-ending and trailing-newline policy?** Observed: the `Edit` tool wrote LF into files whose git index recorded CRLF (`git diff` warned "LF will be replaced by CRLF the next time Git touches it"). Whether `Edit` preserves the file's existing line-ending style, and whether a trailing newline is added or removed, is **UNKNOWN**.
8. **Does `Edit` preserve file permissions / ownership / mtime?** A rewind "restores" content; whether it restores mode bits is **UNKNOWN**.
9. **What is the `Edit` behaviour on a file with CRLF line endings when `old_string` contains LF?** Given the strict "a single character of whitespace difference is enough to miss", a CRLF file would not match an LF-authored `old_string`. This is **UNKNOWN** and is a high-impact portability question on Windows.
10. **What is the exact `/diff` panel and dialog *visual* layout?** Documented behaviour is rich; the rendering is not captured (F17, Limitation 1).
11. **What are the `PostToolUse` hook payloads for `Edit`/`Write`?** Authoring a hook was blocked by the auto-mode classifier (Limitation 5). **UNKNOWN** beyond the docs.
12. **What is `bashEditDiffEnabled` in practice?** The key is documented to record "the files that changed while a Bash command ran" and to feed the changed-file list to `PostToolUse` Bash hooks; its default is *"unset, so Claude Code records changes in auto mode and `bypassPermissions` mode when it directs Claude to edit files through Bash"*. The observable output shape of that record was **not** captured. **UNKNOWN.**
13. **Is the `Edit(path)` rule consulted for `NotebookEdit`?** The docs say NotebookEdit uses the `Edit(...)` path format, but also that a `Read` deny rule does not cover NotebookEdit. The exact interaction is documented but was not exercised. **UNKNOWN** in practice.
14. **What happens on a concurrent edit *during* the write?** The stale check is a read-time comparison; a change landing between the check and the write is a classic TOCTOU window whose handling is **UNKNOWN**.
15. **Does `/code-review --fix` produce checkpointed, rewindable edits?** The docs say a *background* review's `--fix` edits are applied "outside your session's checkpoints" and are not restored by `/rewind`, while a *foreground* review's edits are restored as usual. The precise boundary was **not** exercised. **UNKNOWN** in practice, though documented.

---

## 9. Deliberate divergences a clean-room implementation should consider

These are places where being *better* than the reference is defensible, and where the divergence must be stated in the implementation's own documentation so that a user comparing behaviours is not confused.

| # | Reference behaviour | Proposed divergence | Rationale |
|---|---|---|---|
| 1 | `NotebookEdit` insert reports `Inserted cell undefined` | Report the **created** cell's id | The observed message is a defect; the created id is available (`cell-0` in the observed run) |
| 2 | `Read` deny rules do **not** cover `NotebookEdit` | Apply `Read` deny rules to `NotebookEdit` as well | A documented hole in the reference's safety model; a notebook can contain secrets |
| 3 | Stale edits are matched against current content and the *model* is told to re-read | Optionally refuse the edit and require a re-read | Mechanically enforcing staleness is strictly safer; but it diverges, so it must be a documented mode |
| 4 | `MultiEdit` exists as a legacy shim | Omit it; keep the *rule* parser tolerant of `MultiEdit(...)` | Less surface, same rule-file compatibility |
| 5 | Checkpointing tracks file *content* only | Optionally snapshot directory structure too | The reference explicitly does not undo directory create/move/delete |
| 6 | `Edit` writes LF regardless of the file's existing line endings | Preserve the file's detected line-ending style | On Windows, writing LF into a CRLF file creates a whole-file diff, which is the most common complaint about naive editors |
| 7 | The `file-history` snapshot name is a hash of the path | Use the same layout | Adopting the reference layout yields **interoperability** with the reference's history directory, which is a real win for tooling |

---

## 10. Recommended scope for an independent functional implementation

### Tier 1 — the parity core (must have)

Everything in this list is required for a coding agent to be *correct* at editing files. It is the parity core: roughly 800–1,500 lines of testable code.

1. **`Edit` with the three-gate contract.** Exact substring matching (never regex), occurrence counting, `replace_all`, and the four-way outcome enum with byte-exact error messages: `Applied`, `StringNotFound`, `NotUnique`, `EncodingRefused`.
2. **The four verbatim success/failure message templates**, selected by the tuple `(created, staleRecovered, contentNotInModelContext, replaceAll)` — including the "(file state is current in your context — no need to Read it back)" clause and its deliberate absence.
3. **`Write`** = full-content create/overwrite, `type: "create"` vs `"update"`, empty `structuredPatch` on create, `U+FFFD` guard, atomic write via temp-file + rename.
4. **One diff routine** emitting `{oldStart, oldLines, newStart, newLines, lines[]}` with marker-prefixed line strings, used by `Edit`, `Write`, the diff UI, and the checkpoint summary. Diff against the *current* on-disk content.
5. **The result-object shape** exactly as observed: `filePath`, `oldString`, `newString`, `originalFile`, `structuredPatch`, `userModified`, `replaceAll`, plus the optional `staleRecovered` and `contentNotInModelContext` booleans.
6. **Read-state tracking** per path — `{read, partial, viaBash, mtime, size, hash}` — with the read-before-edit gate as a **policy table** over (model capability, file kind, read completeness), and the exact Bash allow-list (`cat`, `nl`, `bat`, `batcat`, `head`, `tail`, `sed -n 'X,Yp'`, `grep`, `egrep`, `fgrep`, `rg`, one file, no pipes/redirects) populating it.
7. **Strict UTF-8 handling**: refuse `Edit`/`NotebookEdit` on undecodable files (UTF-16LE BOM excepted), leave the file untouched, and return an error that directs the model to a shell command that preserves the encoding.
8. **Checkpointing** — snapshot before each tracked edit to `file-history/<session>/<hash>@v<N>`, retain 100 checkpoints, implement the six rewind actions, and skip symlinks/hard links with a `skippedLinks` count. Use raw bytes.
9. **Permission integration** — the `Edit(path)` / `Read(path)` rule matcher with gitignore syntax and the four anchor types, the settings-source-relative `/path` resolution, POSIX-normalised Windows paths, and the allow/deny depth asymmetry. Consult only `Edit(path)` and `Read(path)`.
10. **Per-call permission metadata** on every tool result: `{decision, source, reason_type, non_execution_kind}`.

### Tier 2 — strong differentiation (high value, moderate effort)

11. **A per-turn edit log** (path, before/after hash, patch, turn id) — the substrate for per-turn diff views, checkpoint summaries, and the "what did you change in turn 3?" question. This is the single most reusable structure in the area.
12. **A `/diff` view with two bases** — working tree (git) and per-turn (the edit log) — with a `source` picker labelled `T1`, `T2`, …, `Current`, and the "ask Claude about this file's diff" handoff that attaches a diff to the next prompt.
13. **A `ReportFindings`-equivalent tool** with `{file, summary, category, severity}` and a 32-item cap, so a host application can render findings structurally.
14. **Review as a skill, not an engine** — a prompt plus a target grammar (branch, range, SHA, PR number, path), with `--fix` routed back through the ordinary edit path so that review fixes are permission-gated and checkpointed like any other edit.
15. **The SDK surface**: `enableFileCheckpointing` / `enable_file_checkpointing`, `rewindFiles()` / `rewind_files()`, `RewindFilesResult { skippedLinks }`, the `replay-user-messages` flag, and the hidden `--rewind-files` CLI flag gated on an env var.
16. **Line-ending preservation** on `Edit` and `Write` — detect the file's existing style and match it. Divergence #6 above. This is cheap and removes the single most common "why is the whole file in my diff" complaint.
17. **A `NotebookEdit` layer with a proper cell model** — cell ids that survive reordering if possible (rather than being purely position-derived), and a `ReportFindings`-style structured result.

### Tier 3 — nice to have

18. **A fullscreen diff panel** with the reference's thresholds (110 columns to open manually, 144 to auto-open), the "skip test and generated files" filter, the pre-session-collapse summary line, and the `Ctrl+X B` comparison-base cycle remembered per repository.
19. **Directory-structure checkpoints** in addition to content checkpoints (divergence #5).
20. **Review finding lifecycle** — mark findings as `fixed`, `skipped`, or `no change needed` when Claude later applies them (the reference does this, and it needs the edit log from Tier 2 to work).
21. **Bash-change diffing** (`bashEditDiffEnabled` equivalent) — record which files a shell command changed and feed the list to a post-tool hook. Extends the checkpointing coverage that the reference explicitly lacks.
22. **Multi-file transactional edits** — the `MultiEdit` niche the reference fills with a legacy shim; implement it as a first-class atomic multi-edit with an all-or-nothing guarantee.

### Explicitly out of scope — do not replicate

- **The cloud `ultrareview` service** — requires claude.ai authentication, is Anthropic-only (unavailable on Bedrock/Vertex/Foundry, with ZDR, or with HIPAA), and is not implementable as a clean-room local feature. Build the *local* review; leave the escalation as a documented "not implemented" state.
- **The GitHub Code Review managed service** — a hosted org product, not a CLI capability.
- **The `ultra` effort level** for the same reason.
- **The hidden `--rewind-files` flag's exact gating** — implement the *capability* (rewind by checkpoint id) under a visible flag name; the hidden-ness is a product choice, not a contract.

---

## 11. Bottom line for this area

**Confirmed by direct observation (OBSERVED-CLI):** the `Edit` input schema (`file_path`, `old_string`, `new_string`, `replace_all`); the exact-not-found and not-unique error strings; the `replace_all` success string; the `Write` create/overwrite distinction with `type: "create"`/`"update"`; the `structuredPatch` record shape; the `originalFile` semantics; the `staleRecovered`, `contentNotInModelContext`, and `userModified` result flags; the read-before-edit relaxation on this model; the stale-file recovery message; the notebook cell-envelope read format and the `Inserted cell undefined` message; the redundant-`Read` suppression message; and the per-call `permission_decision` metadata.

**Confirmed by public documentation (OBSERVED-DOC):** the three-gate edit contract and its model-dependence; the non-UTF-8 refusal and the `U+FFFD` guard; the `Edit(path)`/`Read(path)`-only rule model with gitignore syntax and four anchors; the checkpointing model, its 100-checkpoint window and on-disk layout; the SDK checkpointing API and the hidden `--rewind-files` flag; the `/diff` panel/dialog behaviour and turn views; the `/code-review` contract and the `ReportFindings` shape.

**Not established (UNKNOWN):** whether the reference model takes the read-before-edit relaxation; the exact gate ordering; the precise semantics of `contentNotInModelContext`, `userModified`, and `staleRecovered` beyond the observed cases; the line-ending and trailing-newline policy; the CRLF-matching behaviour; the visual design of the diff panel; the `PostToolUse` hook payloads for file edits; and the observable shape of `bashEditDiffEnabled`'s change record.

**Recommended scope:** Tier 1 (items 1–10) is the parity core and is a self-contained, well-specified piece of engineering — an exact-string editing engine, one diff routine, a checkpoint store, and a permission-rule matcher. Tier 2 items 11–14 (the per-turn edit log, the two-base diff view, a structured findings tool, and review-as-a-skill with `--fix` routed through the normal edit path) are where an independent implementation can most cleanly differentiate, because they are *architectural* choices the reference documents only in prose. Items 16 and 17 (line-ending preservation and a proper notebook cell model) are cheap, concrete improvements over observable reference behaviour.

The compliance boundary held throughout: every fact above comes from a public Anthropic document or from the published CLI's own output. No decompilation, disassembly, source-map extraction, binary modification, credential access, or gateway reverse-engineering was performed, and REA's decompilation facilities were deliberately not invoked.
