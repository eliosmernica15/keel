# Claude Code — Area 9 Evidence: Built-in Tools Reference (Tool Surface, Schemas, Permission Matrix)

**Subject:** Claude Code 2.1.306 (native build, win32-x64) — reference product
**Area:** Tools reference page (per-task assignment: "Every built-in tool: exact names, exact input parameters, exact output/result shapes, and which tools exist.")
**Date:** 2026-10-21
**Primary page:** https://code.claude.com/docs/en/tools-reference.md
**Method:** public documentation + black-box observation of the published CLI's own surfaces.
**Compliance:** No decompilation, no JS extraction, no source-map dumping, no binary modification, no credential/keychain/licence access. All evidence is (a) Anthropic's public docs fetched over HTTPS and (b) the published `claude` executable's own user-facing help and stream output. See `agent-reference-shots/TERMS-NOTES.md`.

**Classification legend:**

| Tag | Meaning |
|---|---|
| `OBSERVED-DOC` | Stated verbatim in a cited public Anthropic document (quote given, URL given) |
| `OBSERVED-CLI` | I personally ran the published CLI and saw it (exact command + output given) |
| `INFERRED` | My conclusion from evidence; reasoning stated explicitly |
| `UNKNOWN` | The available evidence cannot establish it |

**Environment caveat:** this host runs Claude Code against a **custom `ANTHROPIC_BASE_URL`** (a third-party gateway serving `minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. Subscription-gated features (Remote Control, cloud sessions, artifact publishing, org policy, managed settings) are therefore **not observable here** and are marked `OBSERVED-DOC` from the docs, never `OBSERVED-CLI`.

---

## 1. Executive summary

Claude Code's tool surface is a **fixed, named registry of 46 built-in tools**, documented in a single table with three columns: tool name, one-line description, and a boolean `Permission required` column. The names are load-bearing public API — they are the exact strings used in permission rules, hook matchers, subagent `tools` lists, and CLI flags. A clean-room implementation that reproduces the *names* and the *wire schemas* reproduces the product's integration surface; nothing else about the tool layer is secret.

**The single most important finding for a reimplementer: the tools-reference page is deliberately a *behavioural* page, not a *schema* page.** It documents tool names, permission posture, and per-tool semantics in depth (exit-code handling, output-size ceilings, encoding refusals, retry behaviour) but it **does not publish the input/output JSON schemas**. Those schemas live in a different public document — the **Agent SDK TypeScript reference** (`https://code.claude.com/docs/en/agent-sdk/typescript`), under `ToolInputSchemas` and `ToolOutputSchemas` — which publishes exact TypeScript types for every tool's input and output, including optionality and enumerated unions. A reimplementer targeting the tools-reference page alone would have to *guess* the wire contract; a reimplementer who also reads the SDK reference gets it exactly.

**The tool set is not fixed at runtime — it is resolved per session and published.** The `system`/`init` stream event carries a `tools` array listing the tools actually available. I observed 27 tools on this host's default session, versus 46 in the docs table, and the difference is itself informative: the *documented* 46 is the union across providers, platforms, plans and model generations; the *session* array is the intersection of what this provider/platform/plan/model actually ships. Notably, `Glob` and `Grep` are present here (Windows) but **absent by default on macOS, Linux and WSL**, where search is done via `Bash` with embedded `bfs`/`ugrep`. `Task*`/`TodoWrite` are **absent** on newer models by default and only appear if you opt in.

**The permission model is a two-axis matrix.** A tool is either *permission-required* (15 of 46 in the doc table: `Artifact`, `Bash`, `Edit`, `EnterWorktree`, `ExitPlanMode`, `Monitor`, `NotebookEdit`, `PowerShell`, `ShareOnboardingGuide`, `Skill`, `WebFetch`, `WebSearch`, `Workflow`, `Write` — and `Monitor` is permission-gated by the *Bash* ruleset) or it is not. But the doc is explicit that the column reflects **Manual mode, for paths inside the working directory**: file-access tools marked "No" still prompt for paths *outside* the working directory, and `Bash` is marked "Yes" but runs a **built-in set of read-only commands without prompting**. So the boolean is a *default prompt posture*, not an access-control decision.

**A second permission layer sits above the first.** Permission rules are a *string-matching* system with exactly one syntax — `ToolName(specifier)` — and the specifier vocabulary is per-tool but shared across families: `Bash(npm run *)` applies to both `Bash` and `Monitor`; `Read(~/secrets/**)` applies to `Read`, `Grep`, `Glob` and `LSP`; `Edit(/src/**)` applies to `Edit`, `Write` and `NotebookEdit`. Above this sits **auto mode**, where a server-side classifier decides most prompts instead of the user, and it *drops broad allow rules* so the classifier sees them.

**Error handling is a first-class tool result, not an exception.** Tool failures come back to the model as an ordinary result marked `is_error: true`, with the error text in-band; the agent's turn continues and it can retry. Several tools have carefully specified refusal semantics: `Edit`/`NotebookEdit` **refuse to touch non-UTF-8 files** (because they save the whole file back as UTF-8 and would corrupt undecodable bytes) with an exact, quotable error message; `Grep` returns ripgrep's own diagnostic for a rejected pattern; `Glob` returns an error for a null byte in `pattern` or `path`; `WebFetch` refuses `localhost` and any dotless hostname *before* making a request.

**Recommended scope for an independent functional implementation:** implement the *tool registry as data* — one table of names, one table of JSON schemas, one permission table, one rule-matching engine — rather than as hand-written per-tool code. Then implement the six tools that carry the real product weight: `Read`, `Edit`, `Write`, `Glob`, `Grep`, `Bash`. Those six cover file discovery, reading, patching, writing and command execution, and they alone reproduce the observable developer experience. The remaining 40 are thin, and several (Artifacts, Remote Control, SendUserFile, PushNotification, ShareOnboardingGuide) are subscription-gated and not implementable as parity targets at all. See §7.

---

## 2. Detailed findings

### F1 — The canonical tool list: 46 names, 15 permission-required

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (section: the opening tool table, immediately under the "Tools reference" H1)

The page opens with:

> "Claude Code has access to a set of built-in tools that help it understand and modify your codebase. The tool names are the exact strings you use in [permission rules](/docs/en/permissions#tool-specific-permission-rules), [subagent tool lists](/docs/en/sub-agents), and [hook matchers](/docs/en/hooks)."

> "To add custom tools, connect an [MCP server](/docs/en/mcp). To extend Claude with reusable prompt-based workflows, write a [skill](/docs/en/skills), which runs through the existing `Skill` tool rather than adding a new tool entry."

**Full documented list, in page order** (46 entries):

`Agent`, `Artifact`, `AskUserQuestion`, `Bash`, `CronCreate`, `CronDelete`, `CronList`, `Edit`, `EndConversation`, `EnterPlanMode`, `EnterWorktree`, `ExitPlanMode`, `ExitWorktree`, `Glob`, `Grep`, `ListAgents`, `ListMcpResourcesTool`, `LSP`, `Monitor`, `NotebookEdit`, `PowerShell`, `PushNotification`, `Read`, `ReadMcpResourceTool`, `RemoteTrigger`, `ReportFindings`, `ScheduleWakeup`, `SendFeedback`, `SendMessage`, `SendUserFile`, `ShareOnboardingGuide`, `Skill`, `SubagentHandback`, `TaskCreate`, `TaskGet`, `TaskList`, `TaskOutput`, `TaskStop`, `TaskUpdate`, `TodoWrite`, `ToolSearch`, `WaitForMcpServers`, `WebFetch`, `WebSearch`, `Workflow`, `Write`.

**The `Permission required` column** — the tools marked `Yes` are exactly:

`Artifact`, `Bash`, `Edit`, `EnterWorktree`, `ExitPlanMode`, `Monitor`, `NotebookEdit`, `PowerShell`, `ShareOnboardingGuide`, `Skill`, `WebFetch`, `WebSearch`, `Workflow`, `Write`

(14 names. `Monitor` is `Yes` but, per its own row, "it uses the same permission rules as Bash", so the same `Bash(...)` allow/deny patterns govern it.)

**The column's semantics are explicitly qualified** — quoted verbatim:

> "The `Permission required` column shows whether the tool prompts in [Manual mode](/docs/en/permission-modes) for paths inside the working directory. File-access tools marked No, including `Read`, `Grep`, and `Glob`, still prompt for paths outside the [working directory and additional directories](/docs/en/permissions#working-directories). `Bash` is marked Yes but runs a built-in set of [read-only commands](/docs/en/permissions#read-only-commands) without prompting."

**Reimplementation need: CRITICAL.** The *names* are a public contract consumed by three independent configuration surfaces (permissions, hooks, subagents) plus two CLI flags. Renaming any of them breaks user configuration. A clean-room implementation must adopt this exact 46-name vocabulary.

---

### F2 — The tools-reference page is a behaviour page; the wire schemas live in the Agent SDK reference

**Status: `OBSERVED-DOC` + `INFERRED`**

**Source:** https://code.claude.com/docs/en/tools-reference.md · https://code.claude.com/docs/en/agent-sdk/typescript.md (sections `ToolInputSchemas`, `ToolOutputSchemas`)

This is a structural finding worth stating explicitly, because it changes where a reimplementer looks for the contract.

The tools-reference page names parameters *in prose* but does **not** publish their JSON types. For example, it says of `Edit`:

> "The Edit tool performs exact string replacement. It takes an `old_string` and a `new_string` and replaces the first with the second. It doesn't use regex or fuzzy matching."

and of `Grep`:

> "Three output modes control what comes back:
> * `files_with_matches`: file paths only, no line content. This is the default.
> * `content`: matching lines with file and line number. ...
> * `count`: match count per file, followed by a total across all matching files."

The **exact** optionality and enumerated unions live in the SDK reference:

```typescript theme={null}
type GrepInput = {
  pattern: string;
  path?: string;
  glob?: string;
  type?: string;
  output_mode?: "content" | "files_with_matches" | "count";
  "-i"?: boolean;
  "-o"?: boolean; // print only the matched parts of each line; requires output_mode: "content"
  "-n"?: boolean;
  "-B"?: number;
  "-A"?: number;
  "-C"?: number;
  context?: number;
  head_limit?: number;
  offset?: number;
  multiline?: boolean;
};
```

Note the **quirky literal key names** `"-i"`, `"-o"`, `"-n"`, `"-B"`, `"-A"`, `"-C"` — hyphen-prefixed, which is not valid TS identifier syntax without quoting, and therefore an easy thing to get wrong in a hand-written schema. A reimplementer who reads only the tools-reference prose would likely miss both the hyphenated keys and the `output_mode` union.

**Reimplementation need: CRITICAL.** The full input/output schema set is the primary artefact for a clean-room implementation of the tool layer.

---

### F3 — The tool set is resolved per session and published in the `init` event

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**Source:** local run of the published CLI · https://code.claude.com/docs/en/tools-reference.md (§ "Check which tools are available") · https://code.claude.com/docs/en/agent-sdk/typescript.md (§ `Agent`)

**`OBSERVED-CLI`** — `claude -p "..." --output-format stream-json --verbose`, first event, `tools` array verbatim (27 entries):

```json
"tools":["Task","Bash","CronCreate","CronDelete","CronList","DesignSync","Edit",
"EnterWorktree","ExitWorktree","Glob","Grep","ListAgents","Monitor","NotebookEdit",
"PowerShell","PushNotification","Read","ReportFindings","ScheduleWakeup","SendMessage",
"Skill","TaskStop","ToolSearch","WebFetch","WebSearch","Workflow","Write"]
```

**`OBSERVED-CLI`** — restricting the session with `--tools Read` collapses the array to exactly `["Read"]`, confirming the array is the *effective* set and not a static list.

**`OBSERVED-DOC`** — the SDK reference explains one entry:

> "**Tool name:** `Agent`. The previous name `Task` is still accepted as an alias, and the `tools` array in the [`SDKSystemMessage`](#sdksystemmessage) init message currently lists this tool as `Task` for backward compatibility."

**`OBSERVED-CLI` — diff of documented vs. observed set.** Doc has 46; this session had 27.

| Direction | Names |
|---|---|
| In docs, **not** in this session (19) | `Agent`, `Artifact`, `AskUserQuestion`, `EndConversation`, `EnterPlanMode`, `ExitPlanMode`, `ListMcpResourcesTool`, `LSP`, `ReadMcpResourceTool`, `RemoteTrigger`, `SendFeedback`, `SendUserFile`, `ShareOnboardingGuide`, `SubagentHandback`, `TaskCreate`, `TaskGet`, `TaskList`, `TaskOutput`, `TaskUpdate`, `TodoWrite`, `WaitForMcpServers` |
| In this session, **not** in the docs table (2) | `Task` (the `Agent` alias), `DesignSync` (undocumented on this page) |

**`INFERRED`** — reasoning: each of the 19 absences is explained by a documented, session-level condition, and no absence is unexplained by the docs. Specifically: `Agent` is present but *renamed* to `Task` in the array; `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate`/`TodoWrite` are absent because the docs say the task tools are "available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models" and this session runs an unrecognised model id (`minimax/minimax-m3.1-flash:free`); `AskUserQuestion`/`EndConversation`/`EnterPlanMode`/`ExitPlanMode`/`SubagentHandback` are interactive-only or model/provider-gated; `Artifact`/`SendUserFile`/`ShareOnboardingGuide`/`PushNotification`/`RemoteTrigger` require a claude.ai Pro/Max/Team/Enterprise subscription; `LSP` requires an installed code-intelligence plugin; `ListMcpResourcesTool`/`ReadMcpResourceTool`/`WaitForMcpServers` are tool-search-gated; `TaskOutput` was **removed** in v2.1.277 (still listed in the doc table, marked as removed). **Conclusion: the 46-name table is the *union*; the `init` array is the *intersection* of provider × platform × plan × model × config.** `DesignSync` is a genuine doc gap on this page (a real tool in this build with no entry in the tools-reference table) — I could not find it in the tools-reference, skills, mcp or sub-agents pages I fetched.

**Reimplementation need: HIGH.** The "publish the effective manifest" pattern is what makes the product debuggable. A clean-room implementation should emit its own resolved tool manifest at session start, and should support the same *narrowing* controls (`--tools`, `--allowedTools`, `--disallowedTools`, `--restricted`, `--bare`).

---

### F4 — `Edit`: exact string replacement with three gates and an exact-match uniqueness rule

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Edit tool behavior") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`FileEditInput`, `FileEditOutput`)

> "The Edit tool performs exact string replacement. It takes an `old_string` and a `new_string` and replaces the first with the second. It doesn't use regex or fuzzy matching."

> "These checks must pass for an edit to apply. Before any of them, a path matched by a [`Read` deny rule](/docs/en/permissions#tool-specific-permission-rules) is refused, including creating a new file there.
> * **Read-before-edit**: Claude reads the file in the current conversation before editing it, and a read cut short with a [`PARTIAL view` notice](#large-files) doesn't count. ...
> * **Match**: `old_string` must appear in the file exactly as written. A single character of whitespace or indentation difference is enough to miss.
> * **Uniqueness**: `old_string` must appear exactly once. When it appears more than once, Claude either supplies a longer string with enough surrounding context to pin down one occurrence, or sets `replace_all: true` to replace them all."

**Input schema (SDK reference):**
```typescript
type FileEditInput = {
  file_path: string;
  old_string: string;
  new_string: string;
  replace_all?: boolean;
};
```

**Output schema — note it returns a structured diff, not just a status:**
```typescript
type FileEditOutput = {
  filePath: string;
  oldString: string;
  newString: string;
  originalFile: string | null;
  structuredPatch: Array<{
    oldStart: number; oldLines: number; newStart: number; newLines: number; lines: string[];
  }>;
  userModified: boolean;
  replaceAll: boolean;
  gitDiff?: {
    filename: string;
    status: "modified" | "added";
    additions: number; deletions: number; changes: number;
    patch: string;
    repository?: string | null;
  };
};
```

**`INFERRED`** — `structuredPatch` is a unified-diff-shaped structure (`oldStart`/`oldLines`/`newStart`/`newLines`/`lines[]` with ` `/`-`/`+` prefixes) and `gitDiff` is a second, git-native diff. Both are *presentations* of the same change, and `userModified: boolean` is a **concurrent-edit guard** — it reports that the file changed on disk since it was last read, forcing the agent to re-read before making context-dependent edits. Reasoning: the docs describe the concurrent-change case as one where the edit "still can be edited when `old_string` matches the current content exactly and unambiguously ... and the result notes that the file carries other changes so Claude re-reads it". A boolean flag is the minimal machine-readable form of that note. `userModified:false` was independently observed in the local `init`/stream capture (`agent-reference-shots/area9-tools-reference/`).

**Reimplementation need: CRITICAL.** `Edit` is one of the two highest-traffic tools. The `structuredPatch` shape is what a clean-room TUI renders as a diff; the `userModified` guard is a safety property worth copying.

---

### F5 — `Read`: polymorphic output discriminated on `type`, with four distinct sub-shapes

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Read tool behavior", § "Large files") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`FileReadInput`, `FileReadOutput`)

**Input schema:**
```typescript
type FileReadInput = {
  file_path: string;
  offset?: number;
  limit?: number;
  pages?: string;
  allow_large?: boolean;
};
```

**Output schema — a discriminated union on `type`:**
```typescript
type FileReadOutput =
  | { type: "text"; file: { filePath: string; content: string; numLines: number;
      startLine: number; totalLines: number; truncatedByTokenCap?: boolean } }
  | { type: "image"; file: { base64: string;
      type: "image/jpeg" | "image/png" | "image/gif" | "image/webp";
      originalSize: number; dimensions?: { originalWidth?: number; originalHeight?: number;
        displayWidth?: number; displayHeight?: number } } }
  | { type: "notebook"; file: { filePath: string; cells: unknown[] } }
  | { type: "pdf"; file: { filePath: string; base64: string; originalSize: number } }
  | { type: "parts"; file: { filePath: string; originalSize: number; count: number;
      outputDir: string }; firstPage?: number; pages?: {...}[] }
  | { type: "file_unchanged"; file: { filePath: string }; source?: "seeded" };
```

**`OBSERVED-CLI`** — live `Read` of `hello.py` produced exactly the `type: "text"` arm:
```json
"tool_use_result":{"type":"text","file":{"filePath":"C:\\...\\hello.py",
  "content":"def greet(n):\n    return f'Goodbye, {n}!'\n\nprint(greet('world'))\n\n",
  "numLines":6,"startLine":1,"totalLines":6}}
```
and the *user-facing* content block was line-numbered text (`"1\tdef greet(n):\n2\t    return ..."`).

**Documented limits (tools-reference, § "Large files"):**
> "By default one call returns at most 25,000 tokens, or the value you set in [`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS`](/docs/en/env-vars), and refuses a whole file over 256 KB, so Claude reads a larger file in pages with `offset` and `limit`."

> "* **Whole file over the token limit**: the first page of the file, with a `PARTIAL view` notice saying how much of the file it received and how to read more with `offset` and `limit`
> * **Whole file over 256 KB, or an `offset` or `limit` read over the token limit**: an error telling it to read a portion with `offset` and `limit`, or to search for specific content with [Grep](#grep-tool-behavior) instead"

**Other documented `Read` behaviours:** images are "returned as visual content that Claude can see, not as raw bytes" and are "resized and recompress[ed] ... to fit the model's image size limits"; a file over 128 MB is refused for image reads; PDFs are read whole under 10 pages and by `pages` range above that (max 20 pages/request, rendered via `pdftoppm`); notebooks over 100 MB are refused; "Read only reads files, not directories."

**`INFERRED`** — the `file_unchanged` arm with `source?: "seeded"` is a **de-duplication** mechanism: repeated reads of an unchanged file are collapsed to avoid re-flooding context, and `source: "seeded"` distinguishes a match against a startup-seeded entry (CLAUDE.md / nested memory) from a match against a prior `Read` result. Reasoning: the SDK comment says the field is "Set when the dedup matched a startup-seeded entry (CLAUDE.md / nested memory) rather than a prior Read tool_result" — the word "dedup" is explicit.

**Reimplementation need: CRITICAL.** The `type` discriminator with 6 arms is the whole "read any file type" story, and it is the natural place to put a clean-room implementation's own limits (max bytes, max pages, dedup).

---

### F6 — `Write`: full-content overwrite with a `create`/`update` discriminator and a diff

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Write tool behavior") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`FileWriteInput`, `FileWriteOutput`)

> "The Write tool creates a new file or overwrites an existing one with the full content provided. It doesn't append or merge."

**Input schema:**
```typescript
type FileWriteInput = { file_path: string; content: string; };
```

**Output schema:**
```typescript
type FileWriteOutput = {
  type: "create" | "update";
  filePath: string;
  content: string;
  structuredPatch: Array<{ oldStart: number; oldLines: number; newStart: number;
    newLines: number; lines: string[] }>;
  originalFile: string | null;
  gitDiff?: { filename: string; status: "modified" | "added"; additions: number;
    deletions: number; changes: number; patch: string; repository?: string | null };
  userModified?: boolean;
};
```

**Documented semantics for the diff fields** (SDK reference):
> "* For a newly created file, `originalFile` is null and `structuredPatch` is empty
> * On an overwrite, `originalFile` carries the previous content, except when that content is larger than about 10 MB: Claude Code then skips the diff and returns `originalFile` null and `structuredPatch` empty
> * `structuredPatch` is also empty when the write changed nothing or the diff timed out"

**Documented read-before-write rule (tools-reference):**
> "Claude Opus 4.6, Claude Haiku 4.5, and older models always require the read, so a Write to an unread existing file fails with an error.
> * Newer models can overwrite a file they never read this session under the same conditions as [read-before-edit](#edit-tool-behavior): reading it wouldn't need a permission prompt and the Read tool is available.
> * Jupyter notebooks, and files Claude has read only partially with a [`PARTIAL view` notice](#large-files), require the read on every model."

**`INFERRED`** — `type: "create" | "update"` is the machine-readable form of "did this create a new file or replace an existing one"; combined with `originalFile: string | null` (null on create) it lets a UI render a diff without re-reading the file. The 10 MB diff-skip threshold is a **context-protection** rule: the previous content is too big to return, so the diff is silently dropped rather than the file's prior state being truncated.

**Reimplementation need: HIGH.**

---

### F7 — `Bash`: separate process per command, cwd carries over, env vars do not, and output is size-capped by *result class*

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Bash tool behavior", § "What persists between commands", § "Timeout and output limits", § "Background commands") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`BashInput`, `BashOutput`)

**Input schema:**
```typescript
type BashInput = {
  command: string;
  timeout?: number; // milliseconds. Foreground: capped at 600000 by default, higher values are clamped.
  description?: string;
  run_in_background?: boolean;
  dangerouslyDisableSandbox?: boolean;
};
```

**Output schema:**
```typescript
type BashOutput = {
  stdout: string;
  stderr: string;
  rawOutputPath?: string;
  interrupted: boolean;
  isImage?: boolean;
  backgroundTaskId?: string;
  backgroundedByUser?: boolean;
  timedOutAfterMs?: number;
  backgroundCwdHint?: string;
  backgroundEndsWithFinalResponse?: true;
  dangerouslyDisableSandbox?: boolean;
  returnCodeInterpretation?: string;
  noOutputExpected?: boolean;
  structuredContent?: unknown[];
  persistedOutputPath?: string;
  persistedOutputSize?: number;
  staleReadFileStateHint?: string;
  ghRateLimitHint?: string;
  gitOperation?: {
    commit?: { sha: string; kind: "committed" | "amended" | "cherry-picked"; branch?: string };
    push?: { branch: string };
    branch?: { ref: string; action: "merged" | "rebased" };
    pr?: { number: number; url?: string; action: "created" | "edited" | "merged" | "commented" |
      "closed" | "reopened" | "ready" | "draft" | "auto-merge-enabled" | "auto-merge-disabled" };
  };
};
```

**The state-persistence contract** (tools-reference, § "What persists between commands"):
> "* When Claude runs `cd` in the main session, the new working directory carries over to later Bash commands as long as it stays inside the project directory or an [additional working directory](/docs/en/permissions#working-directories) you added with `--add-dir`, `/add-dir`, or `additionalDirectories` in settings. ...
>   * Subagent sessions never carry over working directory changes.
>   * If `cd` lands outside those directories, Claude Code resets to the project directory and appends `Shell cwd was reset to <dir>` to the tool result.
>   * To disable this carry-over so every Bash command starts in the project directory, set `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`.
> * Environment variables don't persist. An `export` in one command won't be available in the next.
> * Aliases and shell functions defined in your shell startup file are available. At session start, Claude Code sources `~/.zshrc`, `~/.bashrc`, or `~/.profile` depending on your shell, captures the resulting aliases, functions, and shell options, and applies them to every Bash command."

**The output-limit table** (verbatim, § "Output limits"):
> | Result | What Claude gets |
> | :- | :- |
> | Valid | Inline up to roughly 30,000 characters by default; past that, the path of a file saved to the session directory and truncated past 64 MiB, plus a preview of up to the first 2,000 characters, and Claude reads or searches the file when it needs the rest |
> | Failure | Inline up to roughly 10,000 characters; past that, a head-and-tail excerpt of that size cut from the read-back window, with no file path |

**The exit-code-1 rule** — a precise, testable behavioural spec:
> "A command that exits 1 counts as a valid result for the Bash tool only when Claude Code recognizes exit code 1 as a benign outcome for that command: `grep`, `rg`, `egrep`, `fgrep`, `find`, `diff`, `test`, and `[`, plus `git diff` and `git grep`. Every other command that exits 1 counts as a failure, even when exit 1 is a benign informational outcome: no matches for `pgrep` and `jq -e`, files that differ for `cmp`."

**Timeout defaults** (env-vars reference, https://code.claude.com/docs/en/env-vars.md):
> "`BASH_DEFAULT_TIMEOUT_MS` — Default timeout for a foreground Bash or PowerShell tool command, in milliseconds (default: 120000, or 2 minutes)."
> "`BASH_MAX_TIMEOUT_MS` — Maximum timeout the model can set for a foreground Bash or PowerShell tool command, in milliseconds (default: 600000, or 10 minutes). The effective ceiling is the larger of this and `BASH_DEFAULT_TIMEOUT_MS`."

**`OBSERVED-CLI`** — I observed the "multiple operations" permission split live: a compound command `wc -l "…"; echo "---"; od -c "…"` was denied with
> "This Bash command contains multiple operations. The following part requires approval: …"

and a subsequent single `wc -l` was blocked by a *different* mechanism:
> "wc in '/c/Users/Admin/Desktop/Claude clone/scratch-probe/hello.py' was blocked. For security, Claude Code may only count lines/words/bytes in files from the allowed working directories for this session: 'C:\Users\Admin\Desktop\Claude clone\scratch-probe'."

**`INFERRED`** — reasoning: the second message reveals a **shell-command-level sandbox** that parses the command's *arguments*, not just its path. It permits `wc` on the file but the *path form* it received was a Git-Bash-style `/c/Users/…` path, which is not recognised as inside the Windows working directory, so the check failed. This is a real, observable behaviour of the reference product on Windows and a known hazard for any clean-room implementation that mixes POSIX and native path spellings. It also shows that the permission engine operates at *subcommand* granularity — the denial metadata `decision_reason_type: "subcommandResults"` (observed in the stream) names the specific sub-commands that needed approval.

**Reimplementation need: CRITICAL.** `Bash` is the tool with the most surface area and the most idiosyncratic rules. A clean-room implementation must at minimum implement: per-command process isolation, cwd carry-over with a reset notice, the exit-code-1 allowlist, the two-tier output caps, the timeout ceiling, and background execution with a task id.

---

### F8 — `Glob` and `Grep`: platform-dependent availability, and a documented capability split

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Glob tool behavior", § "Grep tool behavior")

**Platform gating — a surprising and important rule:**
> "On Windows, it's part of the default tool set. On macOS, Linux, and WSL, Claude Code leaves Glob and [Grep](#grep-tool-behavior) out of the default tool set, and Claude searches with `find` and `grep` through the Bash tool instead. In Claude's shell those two commands run embedded versions of `bfs` and `ugrep`, and the searches reach your hooks and permission rules as `Bash` calls."

> "On macOS, Linux, and WSL, you get the Glob and Grep tools back in these cases:
> * You name `Glob` or `Grep` in [`--tools` or `--allowedTools`] when you start the session, or in the equivalent [Agent SDK](/docs/en/agent-sdk/overview) options. With `--tools` you get the ones you list, and naming either tool in `--allowedTools` restores both. An allow rule in a settings file doesn't have this effect.
> * A permissions [deny rule], the `--disallowedTools` flag, or [`--restricted`] removes `Bash` from the session.
> * A [subagent] lists `Glob` or `Grep` in its `tools` field and leaves out `Bash`."

**`Glob` semantics:**
> "Results are sorted by modification time and capped at 100 files. If the cap is hit, Claude sees a truncation flag in the result and can narrow the pattern."

> "Glob doesn't respect `.gitignore` by default, so it finds gitignored files alongside tracked ones. This differs from [Grep](#grep-tool-behavior), which skips gitignored files. To make Glob respect `.gitignore`, set `CLAUDE_CODE_GLOB_NO_IGNORE=false` before launching Claude Code."

> "A `pattern` or `path` value that contains a null byte returns an error asking Claude to remove it."

Output schema (SDK reference):
```typescript
type GlobOutput = {
  durationMs: number; numFiles: number; filenames: string[];
  truncated: boolean; totalMatches?: number; countIsComplete?: boolean;
};
```

**`Grep` semantics:**
> "Grep is built on [ripgrep](https://github.com/BurntSushi/ripgrep) and uses ripgrep's regex syntax, not POSIX grep. Patterns that include regex metacharacters need escaping. For example, finding `interface{}` in Go code takes the pattern `interface\{\}`."

> "A pattern, glob, or file type that ripgrep rejects returns an error that includes ripgrep's diagnostic, so Claude can correct the input and search again. Before v2.1.208, Claude Code reported a rejected input as `No files found` instead of an error, even when the searched-for text existed in the target files."

> "Claude respects `.gitignore`, so gitignored files are skipped. To search a gitignored file, Claude passes its path directly."

> "When the tool's `offset` parameter points past the last match for a pattern that has matches, Grep returns `No entries at this offset`, so Claude widens or resets the offset instead of concluding the pattern doesn't match."

Output schema:
```typescript
type GrepOutput = {
  mode?: "content" | "files_with_matches" | "count";
  numFiles: number; filenames: string[]; content?: string; numLines?: number;
  numMatches?: number; totalFiles?: number; totalLines?: number;
  appliedLimit?: number; appliedOffset?: number;
};
```

**`INFERRED`** — the `truncated` / `countIsComplete` / `totalMatches` triple on `Glob` is a **degradation-loud** design: the result says whether the count is a lower bound. The SDK comment is explicit: "`totalMatches` reports the number of matching files before truncation. When `countIsComplete` is false, `totalMatches` is a lower bound because the underlying search truncated its own output." Likewise `Grep`'s `appliedLimit`/`appliedOffset` echo the pagination that was actually applied, and the SDK notes that before v2.1.208 "a `head_limit` or `offset` that truncated the listed entries also truncated those totals" — i.e. the totals were made honest over time. **Conclusion: the product deliberately distinguishes "no more results" from "more results, truncated"**, and a clean-room implementation should do the same rather than silently truncating.

**Reimplementation need: CRITICAL.** Both tools. Ripgrep is the idiomatic choice and is what the reference product itself uses; `bfs` and `ugrep` are the embedded fallbacks.

---

### F9 — The permission rule language: one syntax, `ToolName(specifier)`, with a small fixed specifier vocabulary

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Configure tools with permission rules and hooks") · https://code.claude.com/docs/en/permissions.md

> "All of these accept the same rule format, `ToolName(specifier)`. The specifier depends on the tool, and several tools share a format:"

| Rule format | Applies to | Details |
| :- | :- | :- |
| `Bash(npm run *)` | Bash, Monitor | Command pattern matching |
| `PowerShell(Get-ChildItem *)` | PowerShell | Command pattern matching |
| `Read(~/secrets/**)` | Read, Grep, Glob, LSP | Path pattern matching |
| `Edit(/src/**)` | Edit, Write, NotebookEdit | Path pattern matching |
| `Skill(deploy *)` | Skill | Skill name matching |
| `Agent(Explore)` | Agent | Subagent type matching |
| `WebFetch(domain:example.com)` | WebFetch | Domain matching |
| `WebSearch` | WebSearch | No specifier; allow or deny the tool as a whole |

> "Tools not listed here, such as `ExitPlanMode` or `ShareOnboardingGuide`, accept only the bare tool name with no specifier."

**Cross-tool consequences of the shared format** (same section):
> "An `Edit(...)` allow rule also grants read access to the same path, so you don't need a matching `Read(...)` rule. A `Read(...)` deny rule also blocks the Edit and Write tools on the same path, including creating a new file there, because both tools change content Claude has to be able to read back. For the Write tool, the `Read` deny check requires Claude Code v2.1.228 or later."

> "Hook `matcher` fields use bare tool names, not the parenthesized rule format."

**Where tool names are accepted** (same section): `permissions.allow` / `permissions.deny` in settings and the `/permissions` interface; the `--allowedTools` and `--disallowedTools` CLI flags; the Agent SDK's `allowedTools` / `disallowedTools` options; a skill's `allowed-tools` frontmatter; a hook's `if` condition.

**`OBSERVED-CLI`** — `claude --help` confirms the flags exist with the documented shape:
> `--allowedTools, --allowed-tools <tools...>` — "Comma or space-separated list of tool names to allow (e.g. \"Bash(git *) Edit\")"
> `--disallowedTools, --disallowed-tools <tools...>` — "Comma or space-separated list of tool names to deny (e.g. \"Bash(git *) Edit\")"
> `--tools <tools...>` — "Specify the list of available tools from the built-in set. Use \"\" to disable all tools, \"default\" to use the default set, or specify tool names (e.g. \"Bash,Edit,Read\")."

**`OBSERVED-CLI`** — `claude --help` on `--restricted`:
> "Restricted mode: removes the built-in tools that run commands or code (Bash, PowerShell and the other code-running tools) and WebFetch unless --tools names them, and ignores user, project and local settings files … Also confines the file tools to the working directories (--add-dir included), refuses bypassPermissions, and lets only a person or the configured permission handler approve writes to settings, git and tool-configuration files."

**`INFERRED`** — the shared-specifier design means a *single* rule can be evaluated against several tools, so the rule engine must be structured as (tool-family, specifier-kind) → matcher, not (tool) → matcher. A clean-room implementation with a per-tool matcher table would not reproduce the documented cross-effects (`Read(...)` deny blocking `Edit`/`Write`; `Bash(...)` matching `Monitor`). **This is the single most commonly mis-implemented piece of the permission system.**

**Reimplementation need: CRITICAL.**

---

### F10 — Auto mode: a second, model-based layer that *drops* broad allow rules

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (page note) · https://code.claude.com/docs/en/permission-modes.md

> "In [auto mode](/docs/en/permission-modes#eliminate-prompts-with-auto-mode), a classifier decides most permission prompts instead of you."

> "While [auto mode](/docs/en/permission-modes#eliminate-prompts-with-auto-mode) is active, Claude Code sets aside allow rules that name `Monitor` itself, along with the other [broad allow rules it drops](/docs/en/permission-modes#how-the-classifier-evaluates-actions), so the classifier reviews Monitor commands the same way it reviews Bash commands."

**`OBSERVED-CLI`** — the local build exposes the classifier's shipped rule set as inspectable JSON via `claude auto-mode defaults`, with rule groups `allow`, `soft_deny`, `hard_deny`, `environment` (observed rule names include "Irreversible Local Destruction", "Sensitive-Source Provenance", "Credential Exploration", "Exfil Scouting", "Auto-Mode Bypass"). Local `auto-mode` denials observed: `[Safety Bypass Flag]` for `--dangerously-skip-permissions` on a tool call, and `[Self-Modification]` for writes to the harness's own settings file or to `CLAUDE.md`.

**`INFERRED`** — auto mode is **not** a permissions-mode variant that merely swaps the prompt source; it is a *layer that invalidates part of the user's own allow list*. The rule "sets aside broad allow rules" means a user who has allow-listed `Bash` wholesale gets *less* auto-approval in auto mode than in manual mode with the same config. Reasoning: the doc sentence says the classifier "reviews Monitor commands the same way it reviews Bash commands" — i.e. the `Monitor`-named allow rule is discarded so the classifier must adjudicate it.

**Reimplementation need: MEDIUM-HIGH.** A clean-room implementation should treat auto mode as an *independent adjudication layer* over the same rule set, with an explicit "this rule was not applied" reason so the decision is auditable.

---

### F11 — `Monitor`: a background watch with a deadline, line-delimited events, and a WebSocket alternative

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Monitor tool", § "WebSocket source") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`MonitorInput`, `MonitorOutput`)

**Input schema:**
```typescript
type MonitorInput = {
  description: string;
  timeout_ms: number;
  command?: string;
  ws?: { url: string; protocols?: string[] };
};
```
SDK note: "`timeout_ms` is the watch's deadline in milliseconds. It defaults to 300000 and accepts values up to 3600000. The effective deadline is at most 1800000, which is 30 minutes, so a larger accepted value is shortened to that." And: "Provide exactly one of `command` or `ws`."

**Output schema:**
```typescript
type MonitorOutput = { taskId: string; timeoutMs: number; persistent?: boolean };
```

**Documented behaviour:**
> "Every watch Claude starts has a deadline: 5 minutes by default, at most 30 minutes, and at most 10 minutes in a [non-interactive](/docs/en/headless) run given a single prompt with `-p`."

> "* **Text messages**: each one becomes one event, even when the message spans multiple lines.
> * **Binary messages**: not passed through. Claude receives a placeholder line such as `[binary frame, 512 bytes]` instead.
> * **Messages larger than 1 MiB**: the watch ends, so subscribe to a filtered feed where one exists.
> * **Socket close**: the watch ends and Claude receives the close code."

> "A WebSocket watch takes a `ws` input in place of `command`, and a single Monitor call can't combine the two."

**Network safety for the WebSocket source:**
> "Claude Code denies URLs that point at a private, link-local, or cloud-metadata address, including hostnames that resolve to one. It also denies hosts in `sandbox.network.deniedDomains`, and when [`allowManagedDomainsOnly`](/docs/en/settings-reference#sandbox-network-allowmanageddomainsonly) is set in managed settings, any host outside the managed allowlist."

**Availability:** "The tool is not available on Amazon Bedrock, Google Cloud's Agent Platform, or Microsoft Foundry. It is also not available when `DISABLE_TELEMETRY` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set. On Windows, the tool is available only when [Git Bash](/docs/en/setup#set-up-on-windows) is installed."

**`INFERRED`** — the `[binary frame, 512 bytes]` placeholder is a **deliberate lossy-by-design** event encoding: the model gets a human-readable marker rather than the bytes, so the agent can react ("a binary frame arrived") without a data path. A clean-room implementation can use any event envelope as long as it is line-oriented and text-only.

**Reimplementation need: MEDIUM.** This is a differentiating feature (a real event loop rather than polling) but it is separable.

---

### F12 — `WebFetch` and `WebSearch`: provider-backed, quota'd, and lossy by construction

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "WebFetch tool behavior", § "WebSearch tool behavior", § "Session search limit") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`WebFetchInput`, `WebFetchOutput`, `WebSearchInput`, `WebSearchOutput`)

**`WebFetch` schemas:**
```typescript
type WebFetchInput = { url: string; prompt: string; offset?: number };
type WebFetchOutput = {
  bytes: number; code: number; codeText: string; result: string;
  durationMs: number; url: string;
  artifactRead?: { slug: string; ver?: string; seeded?: false };
};
```

> "WebFetch takes a URL and a prompt describing what to extract. It fetches the page and converts the response to Markdown when the server returns HTML. For most fetches, it then runs the prompt against the content in a separate model call, and Claude receives the result of that call rather than the raw page. The conversion step is not configurable."

> "This makes WebFetch lossy by design. The extraction prompt determines what reaches Claude, so a result that says a page doesn't mention something may only mean the prompt didn't ask about it."

> "WebFetch refuses `localhost` and any other hostname without a dot, such as a bare intranet name, before making a request."
> "HTTP URLs are automatically upgraded to HTTPS."
> "WebFetch reads up to 100,000 characters of a page's content per call."
> "WebFetch caches each response for 15 minutes by default … set [`CLAUDE_CODE_WEBFETCH_CACHE_TTL_MS`] to change how long WebFetch keeps each response."
> "A page that hasn't finished downloading within five minutes … fails with a deadline error. … set [`CLAUDE_CODE_WEBFETCH_DEADLINE_MS`] to change the limit, or to `0` to remove it."
> "When a URL redirects to a different host, WebFetch returns a text result that names the original URL and the redirect target instead of following it."
> "WebFetch sets a `User-Agent` header beginning with `Claude-User`, and an `Accept` header that prefers Markdown over HTML so servers that support content negotiation can return Markdown directly."

**`WebSearch` schemas:**
```typescript
type WebSearchInput = { query: string; allowed_domains?: string[]; blocked_domains?: string[] };
type WebSearchOutput = {
  query: string;
  results: Array<{ tool_use_id: string; content: Array<{ title: string; url: string }> } | string>;
  durationSeconds: number; searchCount?: number;
};
```

> "The tool may issue up to eight backend searches per call, refining the search internally before returning results. Claude can scope results with `allowed_domains` to include only certain hosts, or `blocked_domains` to exclude them. The two lists can't be combined in a single call."

> "The search backend is not configurable. To search with a different provider, add an [MCP server](/docs/en/mcp) that exposes a search tool."

**Session quota:**
> "An interactive terminal session has a limit of 200 WebSearch calls. Searches from the main conversation and from [subagents](https://code.claude.com/docs/en/sub-agents), such as a parallel research fan-out, count against the same limit."

> "In [non-interactive mode](https://code.claude.com/docs/en/headless) with `-p` and in the Agent SDK, the limit applies per turn, not per session."

**`INFERRED`** — `WebSearch` is a **server-side tool**, not a client-side scraper: "The search backend is not configurable" and the "up to eight backend searches per call" with internal refinement means the *provider* does the fan-out. A clean-room implementation targeting a non-Anthropic provider must supply its own search backend or route it through MCP. `WebFetch`'s two-stage design (fetch → convert to Markdown → separate model call to extract) is a *provider-cost* design: it keeps the page out of the context window, replacing it with only the extracted answer. The `offset` field (v2.1.290+) exists to page through a long page without re-fetching, which implies the fetch is cached server-side for the session.

**Reimplementation need: MEDIUM-HIGH** for the *contract* (the tool signature, the refusal rules, the caching, the quota) — LOW for exact parity, since the backend is Anthropic-specific.

---

### F13 — `AskUserQuestion`: a structured multi-choice prompt with a programmatic answer path

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "AskUserQuestion tool behavior", § "Question auto-continue timeout") · https://code.claude.com/docs/en/agent-sdk/typescript.md (`AskUserQuestionInput`)

**Input schema:**
```typescript
type AskUserQuestionInput = {
  questions: Array<{
    question: string;
    header: string;
    options: Array<{ label: string; description: string; preview?: string }>;
    multiSelect: boolean;
  }>;
  answers?: Record<string, string>;
  annotations?: Record<string, { preview?: string; notes?: string }>;
  metadata?: { source?: string };
};
```

**Documented behaviour:**
> "Claude uses `AskUserQuestion` to ask you multiple-choice questions when it needs a decision or a clarification. Answer by picking an option, or type your own text through the `Other` row or the notes field."

> "When you answer by typing your own text, Claude Code relays the answer with neutral wording so Claude follows what you wrote, including a request to wait or explain first."

**Auto-continue timeout** — a documented unattended-mode affordance:
> "Questions stay open until you answer them. If you want a question you leave unanswered to eventually close and let Claude continue without you, set the [`askUserQuestionTimeout`](/docs/en/settings-reference#askuserquestiontimeout) setting to `60s`, `5m`, or `10m`, either in your user `settings.json` or from the **Question auto-continue timeout** row in `/config`."

> "After a question sits that long with no input, the dialog closes on its own: it submits any options you'd already selected and tells Claude you may be away from your keyboard, so Claude proceeds on its own judgment and can re-ask later. You see a countdown for the last 20 seconds."

> "The timer never starts for a question Claude asks in a [background session], in [screen reader mode], or while the session is connected to [Remote Control]."

Setting schema (https://code.claude.com/docs/en/settings-reference.md, `askUserQuestionTimeout`):
> "* **Type**: string, one of `"60s"`, `"5m"`, `"10m"`, or `"never"`
> * **Default**: `"never"`"

**`INFERRED`** — the `answers` map is keyed by **question text** (`{"Which framework?": "React"}`), which the SDK comment confirms is populated via `updatedInput` by a `PreToolUse` hook rather than by the model ("Claude doesn't set this field; supply it via `updatedInput` to answer programmatically"). This is a **headless-answering hook**: an embedder can answer the question without a human, by intercepting the tool call and rewriting its input. That is the mechanism a clean-room implementation needs for CI.

**Reimplementation need: HIGH.** This is the primary mechanism for a non-interactive agent to consult a human, and the `updatedInput` hook path is what makes it scriptable.

---

### F14 — Subagent tool-scoping: two orthogonal filters plus an allow/deny intersection

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Agent tool behavior") · https://code.claude.com/docs/en/sub-agents.md (§ "Available tools")

**Filter 1 — removed from every subagent, even if listed in `tools`:**
> "* `Agent`, when the subagent is at the depth limit; in a fork the tool stays listed but returns an error instead of spawning
> * `AskUserQuestion`
> * `EndConversation`, which can end only the main conversation
> * `EnterPlanMode`
> * `ExitPlanMode`, unless the subagent's `permissionMode` is `plan`
> * `ScheduleWakeup`
> * `WaitForMcpServers`
> * `Workflow`"

**Filter 2 — background subagents keep only a specific subset:**
> "a background subagent keeps every MCP tool but only these built-in tools: `Read`, `Grep`, `Glob`, `LSP`, `Bash`, `PowerShell`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, `WebSearch`, `TodoWrite`, `Skill`, `ToolSearch`, `EnterWorktree`, `ExitWorktree`, `Monitor`, `TaskStop`, `SendMessage`, and `Artifact`, plus `SubagentHandback` for a subagent that reports through it. Claude Code removes every other built-in tool from a background subagent, whether inherited or listed in the `tools` field, so the same definition can resolve to different tools in the foreground and the background."

**Resolution order for `tools` vs `disallowedTools`** (tools-reference, § "Agent tool behavior"):
> "* **Neither field set**: the subagent inherits every [tool available to subagents].
> * **`tools` only**: the subagent gets only the listed tools.
> * **`disallowedTools` only**: the subagent gets every parent tool except the listed ones.
> * **Both set**: `disallowedTools` takes precedence. A tool listed in both is removed."

> "In every case, the resolved set is limited to the [tools available to subagents]: a tool that isn't available to subagents is never granted, even when listed in `tools`."

**`INFERRED`** — the "same definition can resolve to different tools in the foreground and the background" consequence is the sharpest edge here: a subagent YAML with `tools: Artifact` is valid in the foreground and silently absent in the background, with **no error**. Reasoning: the doc says "The removal reports no error unless it leaves the `tools` list resolving to nothing." A clean-room implementation must therefore resolve the tool set **at spawn time, after the foreground/background decision**, not at definition-parse time — and it must not warn, matching the documented behaviour.

**Reimplementation need: HIGH.** Any implementation with subagents must reproduce this resolution order exactly, or subagent definitions will behave differently from the reference product in a way users will notice.

---

### F15 — Task tools: model-gated, opt-in, and mutually exclusive with `TodoWrite`

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/tools-reference.md (§ "Task tool availability") · https://code.claude.com/docs/en/env-vars.md

> "The task-tracking tools, `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`, and `TodoWrite`, are available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models. Wherever the tools are available, you get the four Task tools, or `TodoWrite` instead when you set [`CLAUDE_CODE_ENABLE_TASKS=0`]."

> "On every other model, Claude Code leaves the tools out unless you opt in. The same applies to a model ID Claude Code doesn't recognize, such as a custom model name served through an [LLM gateway](/docs/en/llm-gateway). On newer models, Claude keeps track of multi-step work without a written checklist, and the tools' definitions and reminders take up context."

Opt-in mechanisms (documented):
> "* Export [`CLAUDE_CODE_ENABLE_TODO_TOOLS=1`] before you start Claude Code … Claude Code then provides the same tools on every model and every provider
> * Name one of the tools in [`--allowedTools`], for example `claude --allowedTools TaskCreate`
> * List the tools in [`--tools`], which restricts the session's built-in tools to the ones it names.
> * In the Agent SDK, the `allowedTools` and `tools` options work the same way as the two flags"

**`OBSERVED-CLI`** — confirmed: this session's `init.tools` array contained **no** `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate`/`TodoWrite`, consistent with the model-gating rule (this host runs an unrecognised model id).

**Schemas (SDK reference):**
```typescript
type TaskCreateInput  = { subject: string; description: string; activeForm?: string; metadata?: Record<string, unknown> };
type TaskCreateOutput = { task: { id: string; subject: string } };

type TaskUpdateInput  = { /* id + fields to change */ };
type TaskUpdateOutput = { success: boolean; taskId: string; updatedFields: string[];
                          error?: string; statusChange?: { from: string; to: string } };

type TaskGetOutput    = { task: { id: string; subject: string; description: string;
                          status: "pending" | "in_progress" | "completed";
                          blocks: string[]; blockedBy: string[] } | null };

type TaskListOutput   = { tasks: Array<{ id: string; subject: string;
                          status: "pending" | "in_progress" | "completed";
                          owner?: string; blockedBy: string[] }> };

type TodoWriteInput   = { todos: Array<{ content: string;
                          status: "pending" | "in_progress" | "completed"; activeForm: string }> };
type TodoWriteOutput  = { oldTodos: [...]; newTodos: [...] };
```

**`INFERRED`** — the task system is a **dependency graph**, not a checklist: `TaskGet` exposes `blocks: string[]` and `blockedBy: string[]` (a task can be blocked by other task ids), and `TaskCreate` accepts a `metadata` bag. `TaskList` adds `owner?: string` — a task can be *owned*, which is what makes the same store usable for agent teams. `TaskUpdateOutput.updatedFields: string[]` reports exactly which fields changed, and `statusChange: {from, to}` reports a transition. `TodoWriteOutput` returns *both* the old and new list, so a client can render a diff of the checklist.

**Reimplementation need: MEDIUM.** The task tools are a nice-to-have; their **data model** (ids, status enum, `blockedBy`/`blocks`, `owner`, `metadata`) is the reusable part, and the model-gating/opt-in behaviour is what a non-Anthropic provider will need, since a custom model id will not be in the default set.

---

### F16 — Error contract: tool failures are results, and the refusal messages are exact

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/errors.md · https://code.claude.com/docs/en/tools-reference.md

**`OBSERVED-CLI`** — from the live session, a denied command came back as a normal tool result with `is_error: true` and the message in-band:
```json
{"content":"Error: This Bash command contains multiple operations. The following part requires approval: …",
 "is_error":true,"tool_use_result":"Error: …",
 "tool_result_meta":[{"non_execution_kind":"user-rejected",
   "permission_decision":{"decision":"reject","source":"config"}}]}
```
The `non_execution_kind` annotation marks a **pre-execution** failure — the command never ran.

**`OBSERVED-DOC`** — the non-UTF-8 refusal message is quoted verbatim in the errors doc:
> "File is not valid UTF-8. It may use a legacy encoding such as Windows-1252, Shift-JIS or GBK, or be binary. This tool saves the whole file as UTF-8, which would replace every byte it cannot decode with U+FFFD. Nothing was written. Make the change with a shell command that reads and writes the file in its own encoding, or ask the user whether to convert it to UTF-8 first."

The tools-reference gives the rationale:
> "The tools refuse because they save the whole file back as UTF-8, which would replace every byte they can't decode with the replacement character `U+FFFD`."

And the `Write` exception:
> "Claude can still replace such a file with Write, unless the new content contains `U+FFFD`, the character Read shows Claude in place of bytes it can't decode. That guard stops Claude from writing back the garbled text it read."

**The zero-tools error** (https://code.claude.com/docs/en/errors.md, § "Agent would be spawned with zero tools"):
> "The message groups your entries by what went wrong:
> * **Unrecognized**: the entry matches no tool name, usually a typo such as `Grpe` for `Grep`.
> * **Not available to subagents**: the entry names a real tool that subagents can't use. Background subagents keep a smaller built-in tool set, so an entry that only a foreground subagent can use lands here when the subagent would run in the background, which is the default.
> * **Matched no tools in this session**: the entry is valid but no tool in the current session matches it right now, such as `mcp__github__*` with no GitHub MCP server connected, or `Agent` for a subagent at the depth limit."

**`INFERRED`** — the three-way grouping of the zero-tools error is a **diagnostic taxonomy for configuration mistakes**, and it distinguishes "you typed it wrong" from "you asked for something this context can't do" from "it exists but isn't loaded right now". A clean-room implementation should reproduce this taxonomy: it is the difference between a helpful error and a dead end. The `is_error: true` + in-band-text pattern (rather than a thrown exception) is also what makes the agent loop resilient: a failed tool call is just another observation.

**Reimplementation need: HIGH.** The failure-as-result pattern is foundational.

---

### F17 — `NotebookEdit`, `PowerShell`, `LSP`, `ReportFindings`, `EnterWorktree`/`ExitWorktree`: the remaining contracts

**Status: `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/tools-reference.md · https://code.claude.com/docs/en/agent-sdk/typescript.md

**`NotebookEdit`:**
> "NotebookEdit modifies a Jupyter notebook one cell at a time, targeting cells by their `cell_id`. It doesn't perform string replacement across the notebook the way [Edit](#edit-tool-behavior) does on plain files.
> * `replace`: overwrite the cell's source. This is the default.
> * `insert`: add a new cell after the target. With no `cell_id`, the new cell goes at the start of the notebook. Requires `cell_type` set to `code` or `markdown`.
> * `delete`: remove the target cell."

```typescript
type NotebookEditInput  = { notebook_path: string; cell_id?: string; new_source: string;
                             cell_type?: "code" | "markdown"; edit_mode?: "replace" | "insert" | "delete" };
type NotebookEditOutput = { new_source: string; old_source?: string; cell_id?: string;
                             cell_type: "code" | "markdown"; language: string; edit_mode: string;
                             error?: string; notebook_path: string; original_file: string; updated_file: string };
```

**`PowerShell`** — platform availability and the Bash-deny coupling:
> "* **Windows without Git Bash**: the tool is enabled automatically.
> * **Windows with Git Bash installed**: the tool is on by default for claude.ai and Console accounts; set `CLAUDE_CODE_USE_POWERSHELL_TOOL=1` to enable it in Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry sessions, or `0` to turn it off.
> * **Linux, macOS, and WSL**: the tool is opt-in."

> "On Windows with Git Bash installed, denying Bash also turns the PowerShell tool off for the session. This applies to scoped rules such as `Bash(git push *)` as well as a bare `Bash`, and to rules from one of your settings files or `--disallowedTools`. Claude Code does this because a `Bash` rule doesn't restrict the PowerShell tool, which has [its own permission rules]. With PowerShell left on, Claude could run there what your rule denies in Bash."

> "On Windows, Claude Code auto-detects `pwsh.exe` for PowerShell 7+ with a fallback to `powershell.exe` for PowerShell 5.1. When the tool is enabled, Claude treats PowerShell as the primary shell."

> "PowerShell commands follow the [same main-session working-directory reset behavior] as Bash commands, including the `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` environment variable."

> "Exit code 1 from `grep`, `rg`, `egrep`, `fgrep`, `findstr`, and `git grep` means no matches. Exit code 1 from `git diff` means differences exist. Neither result is reported to Claude as a command failure."

**`LSP`:**
> "The LSP tool gives Claude code intelligence from a running language server. After each file edit, it automatically reports type errors and warnings so Claude can fix issues without a separate build step. Claude can also call it directly to navigate code:
> * Jump to a symbol's definition
> * Find all references to a symbol
> * Get type information at a position
> * List symbols in a file
> * Search for a symbol by name across the workspace
> * Find implementations of an interface
> * Trace call hierarchies"

> "Claude Code keeps the tool inactive until you install a [code intelligence plugin](/docs/en/plugins/code-intelligence) for your language. … Claude Code takes the language server's configuration from the plugin, and you install the server binary yourself."

**`ReportFindings`:**
```typescript
type ReportFindingsInput = {
  level?: "low" | "medium" | "high" | "xhigh" | "max";
  findings: Array<{
    file: string; line?: number; summary: string; failure_scenario: string;
    short_summary?: string; category?: string;
    verdict?: "CONFIRMED" | "PLAUSIBLE";
    outcome?: "fixed" | "skipped" | "no_change_needed";
  }>;
};
```
SDK note: "Findings are ordered most-severe first, with at most 32 per call, and the array is empty when none survived."

**`EnterWorktree` / `ExitWorktree`:**
```typescript
type EnterWorktreeInput = { name?: string; path?: string };
```
SDK note: "`name` and `path` are mutually exclusive."

> "A `path` outside `.claude/worktrees/` prompts for your approval before entering, since it moves the session's working directory and write access to that location. New-worktree creation and paths under `.claude/worktrees/` don't prompt."

**`INFERRED`** — `ReportFindings` is a **structured-output escape hatch**: it exists so a code-review subagent can return machine-renderable findings instead of prose, with a `verdict` field distinguishing a verified finding (`CONFIRMED`) from a plausible one, and an `outcome` field for the re-report-after-fix workflow. A clean-room implementation can adopt the same idea for any "the model should return structured results" tool, and should copy the 32-per-call cap.

**Reimplementation need: MEDIUM** for each individually; `NotebookEdit` is MEDIUM (the `edit_mode` tri-state is a clean design), `PowerShell` is HIGH on Windows (the Bash-deny coupling is a security property worth copying), `LSP` is MEDIUM (plugin-gated; the LSP protocol itself is standard), `ReportFindings` is MEDIUM (a good pattern), `EnterWorktree`/`ExitWorktree` is LOW-MEDIUM.

---

## 3. Evidence references

| # | Source | URL | What it supported |
|---|---|---|---|
| E1 | Claude Code — Tools reference (primary page) | https://code.claude.com/docs/en/tools-reference.md | Tool list, permission column, per-tool behaviour, rule formats, limits |
| E2 | Agent SDK — TypeScript reference | https://code.claude.com/docs/en/agent-sdk/typescript.md | `ToolInputSchemas` / `ToolOutputSchemas` — exact JSON wire shapes |
| E3 | Claude Code — Hooks reference | https://code.claude.com/docs/en/hooks.md | `PreToolUse` `tool_input` field tables per tool; `updatedInput` mechanism |
| E4 | Claude Code — Subagents reference | https://code.claude.com/docs/en/sub-agents.md | Subagent tool filters, `tools`/`disallowedTools` resolution, frontmatter fields |
| E5 | Claude Code — Permissions reference | https://code.claude.com/docs/en/permissions.md | Rule syntax, per-tool specifiers, parameter-rule restrictions |
| E6 | Claude Code — MCP reference | https://code.claude.com/docs/en/mcp.md | `mcp__<server>__<tool>` naming, tool search, deferred loading, 128-char limit |
| E7 | Claude Code — Settings reference | https://code.claude.com/docs/en/settings-reference.md | `askUserQuestionTimeout`, `bashOutputMaxChars`, `feedbackDrafts`, `cleanupPeriodDays`, `sandbox.network.*` |
| E8 | Claude Code — Environment variables | https://code.claude.com/docs/en/env-vars.md | `BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`, `BASH_MAX_OUTPUT_LENGTH`, `CLAUDE_CODE_*` names + defaults |
| E9 | Claude Code — Errors reference | https://code.claude.com/docs/en/errors.md | Exact refusal messages, zero-tools taxonomy |
| E10 | Claude Code — CLI reference | https://code.claude.com/docs/en/cli-reference.md | `--tools` / `--allowedTools` / `--disallowedTools` / `--restricted` |
| E11 | Claude Code — Skills reference | https://code.claude.com/docs/en/skills.md | `allowed-tools` frontmatter, `disable-model-invocation` |
| E12 | Local CLI | `claude --help`, `claude --version`, `claude mcp list`, `claude -p --output-format stream-json --verbose` | Observed tool arrays, flag help text, permission denials |
| E13 | Local captures | `agent-reference-shots/area9-tools-reference/` | `init-tools-array.jsonl`, fetched `tools-reference.md`, fetched `agent-sdk-typescript.md` |

**Local CLI observations recorded:** `claude --version` → `2.1.306 (Claude Code)`. `claude --help` → the `--tools`, `--allowedTools`, `--disallowedTools`, `--restricted`, `--permission-mode` (`acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`) and `--permission-prompts` (`host`, `none`) surfaces. `claude mcp list` → 4 configured servers, all non-connecting on this host (`rea` timed out after 30000 ms; `probe-srv` shown as "⏸ Pending approval"; two HTTP servers failed with `ENOTFOUND`).

---

## 4. Capability table

### 4.1 The 46 documented tools, with input/output contract and implementation priority

| Tool | Input (exact fields) | Output (exact shape) | Perm. | Reimpl. priority |
|---|---|---|---|---|
| `Read` | `file_path`, `offset?`, `limit?`, `pages?`, `allow_large?` | union on `type`: `text` \| `image` \| `notebook` \| `pdf` \| `parts` \| `file_unchanged` | No* | **P0** |
| `Edit` | `file_path`, `old_string`, `new_string`, `replace_all?` | `filePath`, `oldString`, `newString`, `originalFile`, `structuredPatch[]`, `userModified`, `replaceAll`, `gitDiff?` | Yes | **P0** |
| `Write` | `file_path`, `content` | `type: "create"\|"update"`, `filePath`, `content`, `structuredPatch[]`, `originalFile`, `gitDiff?`, `userModified?` | Yes | **P0** |
| `Glob` | `pattern`, `path?` | `durationMs`, `numFiles`, `filenames[]`, `truncated`, `totalMatches?`, `countIsComplete?` | No* | **P0** |
| `Grep` | `pattern`, `path?`, `glob?`, `type?`, `output_mode?`, `"-i"?`, `"-o"?`, `"-n"?`, `"-B"?`, `"-A"?`, `"-C"?`, `context?`, `head_limit?`, `offset?`, `multiline?` | `mode?`, `numFiles`, `filenames[]`, `content?`, `numLines?`, `numMatches?`, `totalFiles?`, `totalLines?`, `appliedLimit?`, `appliedOffset?` | No* | **P0** |
| `Bash` | `command`, `timeout?`, `description?`, `run_in_background?`, `dangerouslyDisableSandbox?` | `stdout`, `stderr`, `rawOutputPath?`, `interrupted`, `isImage?`, `backgroundTaskId?`, `backgroundedByUser?`, `timedOutAfterMs?`, `backgroundCwdHint?`, `backgroundEndsWithFinalResponse?`, `returnCodeInterpretation?`, `noOutputExpected?`, `structuredContent?`, `persistedOutputPath?`, `persistedOutputSize?`, `staleReadFileStateHint?`, `ghRateLimitHint?`, `gitOperation?` | Yes | **P0** |
| `PowerShell` | same fields as `Bash` | same as `Bash` | Yes | **P1** (Windows) |
| `Agent` | `description`, `prompt`, `subagent_type?`, `model?`, `effort?`, `run_in_background?`, `name?`, `isolation?` | `status: "completed"\|"async_launched"`, `agentId`, `content[]`, `resolvedModel`, `modelsUsed?`, `totalTokens?`, `totalDurationMs?`, `totalToolUseCount?`, `usage?` | No | **P1** |
| `AskUserQuestion` | `questions[]` (`question`, `header`, `options[]`, `multiSelect`), `answers?`, `annotations?`, `metadata?` | answers map keyed by question text | No | **P1** |
| `TaskCreate` | `subject`, `description`, `activeForm?`, `metadata?` | `task: {id, subject}` | No | **P1** |
| `TaskUpdate` | task id + changed fields | `success`, `taskId`, `updatedFields[]`, `error?`, `statusChange?` | No | **P1** |
| `TaskGet` | task id | `task: {id, subject, description, status, blocks[], blockedBy[]} \| null` | No | **P1** |
| `TaskList` | — | `tasks[]: {id, subject, status, owner?, blockedBy[]}` | No | **P1** |
| `TodoWrite` | `todos[]: {content, status, activeForm}` | `oldTodos[]`, `newTodos[]` | No | **P2** (legacy) |
| `NotebookEdit` | `notebook_path`, `cell_id?`, `new_source`, `cell_type?`, `edit_mode?` | `new_source`, `old_source?`, `cell_id?`, `cell_type`, `language`, `edit_mode`, `error?`, `notebook_path`, `original_file`, `updated_file` | Yes | **P2** |
| `WebFetch` | `url`, `prompt`, `offset?` | `bytes`, `code`, `codeText`, `result`, `durationMs`, `url`, `artifactRead?` | Yes | **P2** |
| `WebSearch` | `query`, `allowed_domains?`, `blocked_domains?` | `query`, `results[]`, `durationSeconds`, `searchCount?` | Yes | **P2** |
| `EnterPlanMode` / `ExitPlanMode` | `ExitPlanModeInput` = `allowedPrompts?` (deprecated) + free-form | `plan: string\|null`, `isAgent`, `filePath?`, `hasTaskTool?`, `planWasEdited?`, `awaitingLeaderApproval?`, `requestId?` | No / Yes | **P1** |
| `Monitor` | `description`, `timeout_ms`, `command?`, `ws?: {url, protocols?}` | `taskId`, `timeoutMs`, `persistent?` | Yes | **P2** |
| `ReportFindings` | `level?`, `findings[]` | structured findings list | No | **P2** |
| `EnterWorktree` | `name?`, `path?` (mutually exclusive) | worktree path | Yes | **P2** |
| `ExitWorktree` | `action?` | — | No | **P2** |
| `Skill` | `skill` | skill output | Yes | **P1** |
| `ToolSearch` | query | `matches[]`, `query`, `total_deferred_tools`, `pending_mcp_servers?` | No | **P1** (if MCP) |
| `ListMcpResourcesTool` | `server?` | `[{uri, name, mimeType?, description?, server}]` | No | **P2** (if MCP) |
| `ReadMcpResourceTool` | `server`, `uri` | resource contents | No | **P2** (if MCP) |
| `WaitForMcpServers` | server list | wait result | No | **P3** (if MCP) |
| `CronCreate` / `CronDelete` / `CronList` | cron spec / id / — | task list | No | **P2** |
| `ScheduleWakeup` | interval, `stop?` | wakeup state | No | **P2** |
| `ListAgents` / `SendMessage` | — / `to`, `message`, `summary?` | agent list / delivery receipt | No | **P2** |
| `TaskStop` | `task_id?`, `shell_id?` (deprecated) | `message`, `task_id`, `task_type`, `command?` | No | **P1** (if background) |
| `Workflow` | `script?`, `name?`, `scriptPath?`, `args?`, `resumeFromRunId?` | `status`, `taskId`, `taskType?`, `workflowName?`, `runId?`, `summary?`, `transcriptDir?`, `scriptPath?`, `sessionUrl?`, `warning?`, `error?` | Yes | **P3** |
| `LSP` | language-server request | diagnostics / navigation result | No | **P2** (plugin-gated) |
| `Artifact`, `SendUserFile`, `PushNotification`, `RemoteTrigger`, `ShareOnboardingGuide` | — | — | mixed | **Out of scope** (subscription-gated) |
| `EndConversation` | — | — | No (undenyable) | **P3** |
| `SubagentHandback` | `message` | — | No | **P3** |
| `TaskOutput` | — | — | — | **Removed in v2.1.277** |

\* `Permission required` = "No" in the docs, **but** these tools still prompt for paths outside the working directory.

### 4.2 Dependency / platform matrix

| Capability | Network | Account | Model provider | External service |
|---|---|---|---|---|
| `Read`/`Edit`/`Write`/`Glob`/`Grep` | No | No | No | No (poppler for PDF page ranges) |
| `Bash`/`PowerShell` | No | No | No | No |
| `NotebookEdit` | No | No | No | No |
| `LSP` | No | No | No | **Yes** — language server binary, installed by the user |
| `Monitor` (command) | No | No | No | No |
| `Monitor` (WebSocket) | **Yes** | No | No | **Yes** — the WS server |
| `WebFetch` | **Yes** | No | **Yes** (extraction call) | Yes — the site |
| `WebSearch` | **Yes** | No | **Yes** | **Yes** — Anthropic search backend (not configurable) |
| `Artifact` | **Yes** | **Yes** — Pro/Max/Team/Enterprise + `/login` | No | Yes — claude.ai |
| `SendUserFile`, `PushNotification`, `RemoteTrigger` | **Yes** | **Yes** | No | Yes — Anthropic-hosted infra |
| `ShareOnboardingGuide` | **Yes** | **Yes** — Team/Enterprise | No | Yes |
| `SendFeedback` | No (queues locally) | Yes (Claude API sessions only) | — | Only on send |
| MCP tools | **Yes** (usually) | No | No | **Yes** — the MCP server |
| `Skill` | No | No | No | No |
| `Agent` / `Workflow` | Yes | No | **Yes** | Optional |
| Task tools | No | No | No (but **model-gated**) | No |

---

## 5. Limitations of this investigation

1. **No decompilation, no source inspection.** Per the compliance boundary, I did not extract the bundle, dump source maps, or modify the binary. Everything technical is from public docs + the CLI's own surfaces.
2. **The tools-reference page does not publish the wire schemas.** I sourced them from the Agent SDK TypeScript reference (E2). A reimplementer who reads only the primary page will have behavioural prose but not exact JSON contracts.
3. **Subscription-gated tools were not observable on this host** — `Artifact`, `SendUserFile`, `PushNotification`, `RemoteTrigger`, `ShareOnboardingGuide`, `SendFeedback`, cloud sessions, Remote Control, org policy. All such statements are `OBSERVED-DOC`.
4. **The local model is unrecognised** (`minimax/minimax-m3.1-flash:free` via a custom `ANTHROPIC_BASE_URL`). This materially changes the observed tool set: the task tools are absent (model-gated), and the `init` array lists `Task` (the `Agent` alias) rather than `Agent`. I could not observe Anthropic-model-gated behaviour directly.
5. **`DesignSync` is a documentation gap.** It is present in this build's tool array and has no entry in the tools-reference table, and I could not find it in the skills, mcp, or sub-agents pages. Its input/output contract is `UNKNOWN`.
6. **`TaskOutput` is listed in the doc table but marked removed** ("Removed in v2.1.277"). The table therefore contains a non-existent tool; a reimplementer should read the removal annotation.
7. **I did not exercise every tool.** `Artifact`, `RemoteTrigger`, `SendUserFile`, `PushNotification`, `ShareOnboardingGuide`, `SubagentHandback`, `EndConversation`, `LSP`, `Workflow`, `Monitor` (WebSocket mode) and the cron/scheduled-task family were not run. Their schemas come from E2; their *behaviour* is `OBSERVED-DOC` only.
8. **The `MCP` server on this host is non-functional** (`rea` timed out; two HTTP servers `ENOTFOUND`; one pending approval), so the deferred-tool discovery path could only be partially observed.
9. **Windows-specific path handling produced a surprising denial** (the `wc` path check) that I could not fully characterise — the precise path-normalisation rules inside the permission layer are `UNKNOWN` from public documentation.

---

## 6. Unresolved questions (`UNKNOWN`)

| # | Question | Why it is unknown | How to resolve it |
|---|---|---|---|
| U1 | The exact `input`/`output` schema for `Artifact`, `SendUserFile`, `PushNotification`, `RemoteTrigger`, `ShareOnboardingGuide`, `EndConversation`, `SubagentHandback`, `SendFeedback`, `ListAgents`, `SendMessage`, `Skill`, `Cron*`, `ScheduleWakeup`, `EnterPlanMode`, `ExitWorktree`, `LSP` | Not in the SDK `ToolInputSchemas`/`ToolOutputSchemas` unions I could extract, and not in the tools-reference | Run them on a claude.ai session with the tool present; or read the SDK reference sections I did not extract |
| U2 | `DesignSync` — existence, contract, purpose | Present in the tool array; absent from every public page I fetched | Run it; check `/context`; check the `design-sync` skill in this build |
| U3 | The precise implementation of the `Bash` "subcommandResults" splitting (which shell metacharacters split a command) | Not documented; observed only in aggregate ("This Bash command contains multiple operations") | Experiment with `;`, `&&`, `\|\|`, `\|`, subshells, heredocs |
| U4 | The exact path-normalisation rules the permission layer uses on Windows (why `/c/Users/…` was rejected but `C:\Users\…` accepted) | Not documented; observed as a single denial | Systematic test matrix of path spellings |
| U5 | The `Read` token-accounting formula behind "25,000 tokens" and the 256 KB refusal | The numbers are documented; the estimator is not | Empirically bisect the threshold with controlled file sizes |
| U6 | The `Grep` `count`-mode total semantics pre/post v2.1.208 in practice | Documented only as a changelog claim | Run both modes with `head_limit`/`offset` set |
| U7 | Whether the `init.tools` array is sorted, and in what order | It is neither alphabetical nor the doc order in my capture | Collect several captures with different configs |
| U8 | The `auto mode` classifier's decision inputs beyond the shipped rule names | `claude auto-mode defaults` shows rule *names*, not the classifier's runtime inputs | Not resolvable publicly |
| U9 | The full list of "read-only commands" that `Bash` runs without prompting | Linked from the permissions doc as "built-in set of read-only commands"; I did not extract that section | Read https://code.claude.com/docs/en/permissions#read-only-commands |
| U10 | `ToolSearch` result schema in the *docs* (the local capture showed `matches[]`, `query`, `total_deferred_tools`, `pending_mcp_servers?`) | The tools-reference only says "Searches for and loads deferred tools" | Cross-check against the SDK reference / MCP doc |

---

## 7. Recommended scope for an independent functional implementation

### 7.1 P0 — the core that reproduces the developer experience

| Item | The observable contract | The idiomatic way to build it |
|---|---|---|
| **Tool registry as data** | One table of 46 names → {description, permission-posture, JSON-schema-in, JSON-schema-out, availability predicate} | A single declarative registry (JSON/YAML/TS) loaded at startup. The registry *is* the product surface; hand-writing per-tool code is the mistake to avoid. |
| **Six core tools** | `Read` (6-arm discriminated output), `Edit` (exact-replace + 3 gates + `structuredPatch` + `userModified`), `Write` (create/update + diff), `Glob` (mtime sort, 100 cap, `truncated`/`countIsComplete`), `Grep` (3 output modes, ripgrep syntax, `.gitignore` respected, pagination with honest totals), `Bash` (per-command process, cwd carry-over + reset notice, exit-1 allowlist, 30k/10k output caps, timeout ceiling, background tasks) | Ripgrep (`rg`) for search — the reference product uses it too; a `glob`-style matcher with gitignore support for file names; `child_process.spawn` with an explicit `cwd` and env; `diff`-style line matching for `structuredPatch` (the `oldStart/oldLines/newStart/newLines/lines` shape is a standard unified-diff projection). |
| **Permission engine** | `ToolName(specifier)` with 8 specifier families; the cross-tool sharing (`Bash`→`Monitor`, `Read`→`Grep`/`Glob`/`LSP`, `Edit`→`Write`/`NotebookEdit`); `Read` deny blocking `Edit`/`Write`; `Edit` allow granting read | A (tool-family, matcher-kind) table + a glob matcher. Implement as a *pure function* `(toolName, input, ruleSet, mode) → allow | deny | ask` so it is unit-testable and so the auto-mode classifier can sit above it. |
| **Prompt posture** | The doc's "Permission required" column is a *default*, overridden by (a) mode, (b) rules, (c) the working-directory boundary, (d) auto mode | Resolve prompt-ness in a fixed precedence: hard deny → rule deny → rule ask → mode default → classifier (if auto). Emit the *reason* with the decision so the UI can show it. |
| **Failure-as-result** | Every tool error returns `is_error: true` with the message in-band; the loop continues | Never throw out of a tool handler. Return a result envelope with a discriminated error type. The reference product's own observed denial carries `non_execution_kind: "user-rejected"` — copy that distinction between "failed at runtime" and "never ran". |
| **Manifest publication** | The `init` event carries the effective tool set | Emit a `system/init`-equivalent event with the resolved tool list, config, model, and permission mode. This is the single highest-leverage decision for debuggability. |

### 7.2 P1 — high value, moderate cost

- `AskUserQuestion` with a **programmatic answer path** (the `updatedInput` hook) — needed for CI.
- The `Agent` tool with the two-filter subagent scoping and the `tools`/`disallowedTools` resolution order.
- `TaskCreate`/`TaskUpdate`/`TaskGet`/`TaskList` as a **dependency graph** (`blockedBy`/`blocks`, `owner`, `metadata`), plus the model-gating/opt-in behaviour a custom provider will need.
- `Skill` — a prompt-based tool that runs through the same `Skill` entry point rather than adding new tool names.
- `ExitPlanMode` with a plan written to disk before approval.
- `TaskStop` + background task lifecycle.
- `PowerShell` on Windows, **including the Bash-deny coupling** (a security property: a `Bash` deny must not leave an unconstrained alternate shell).
- `ToolSearch` + deferred MCP tool loading, if MCP is in scope.

### 7.3 P2 — include only if the corresponding backend exists

`NotebookEdit`, `WebFetch`/`WebSearch` (needs a search backend; MCP is the documented escape hatch), `Monitor` (both command and WebSocket modes), `LSP` (needs a language server), `ReportFindings` (structured-output pattern), `EnterWorktree`/`ExitWorktree`, the cron/scheduled-task family, `Workflow`.

### 7.4 Explicitly out of scope

- **Subscription-gated tools** (`Artifact`, `SendUserFile`, `PushNotification`, `RemoteTrigger`, `ShareOnboardingGuide`) — no non-Anthropic provider can offer parity; build your own equivalent and don't chase these.
- **Byte-level TUI parity.** Match the *information architecture* — which indicators exist, where they live — not the glyphs.
- **Reproducing the reference product's internal transcript schema.** The docs warn it changes between versions. Design a *documented, versioned* schema of your own.
- **`EndConversation`'s undenyable status.** That is a deliberate safety design ("a safeguard of this kind holds only if the session it applies to can't turn it off"); replicate the principle, not the exact tool.

### 7.5 Design decisions a clean-room implementer should make deliberately

1. **Treat the tool registry as the product.** The names are a public API consumed by permissions, hooks, subagents, and CLI flags. Version it; publish it; test it.
2. **Make the permission engine a pure function** with an explicit decision precedence, and make every decision carry a *reason*. The reference product exposes `permission_decision: {decision, source, reason_type}` in its stream — that shape is worth copying verbatim in spirit.
3. **Make truncation loud.** `truncated`, `countIsComplete`, `totalMatches`, `appliedLimit`, `appliedOffset` — the reference product distinguishes "no more results" from "more results, cut off". A clean-room implementation that silently truncates will mislead the agent.
4. **Make concurrent modification loud.** `userModified` on `Edit`/`Write` is a safety property: the agent must re-read before context-dependent edits.
5. **Refuse dangerous file mutations loudly, with a quotable message.** The non-UTF-8 refusal is a model example: state what was *not* done, why, and the sanctioned alternatives.
6. **Separate the diagnostic channel from the data channel.** `permission_denials`, `non_execution_kind`, `permission_decision`, `subagent_stats` belong beside the payload, never inside it.
7. **Scope subagent tool sets at spawn time, not parse time** — after the foreground/background decision — and match the reference product's silence when a tool is removed by a background filter.
8. **Design the deferred-tool path with a real answer.** `ToolSearch` returning "no matching deferred tools, but these servers are still connecting" is a *guidance* string, not an error. A clean-room implementation should distinguish "not found", "not loaded yet", and "not available in this context" — the same three-way split the reference product uses in its zero-tools error.
9. **Make the manifest the debugging surface.** Emit the resolved tool set, permission mode, model, and config at session start; make it diffable across configurations.

---

*End of the tools-reference area. This document covers the built-in tool surface: names, input/output schemas, permission posture, and per-tool behaviour. Other areas of the multi-area study have their own artifacts; the top-level `agent-evidence.md` covers CLI startup, project selection, user input, and the conversation loop.*
