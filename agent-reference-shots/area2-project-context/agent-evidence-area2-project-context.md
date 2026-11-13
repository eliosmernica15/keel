# Claude Code — Area #2 Evidence: Project Discovery, Repository Context, File Reading, Code Search

**Subject:** Claude Code CLI (native build) v2.1.306 on Windows 11 Pro (win32-x64)
**Implementation model reference:** Claude Opus 5.5
**Investigation date:** 2026-10-21
**Working directory:** `C:\Users\Admin\Desktop\Claude clone`

---

## Executive Summary

Claude Code's project-context layer is built around **four orthogonal mechanisms** that an independent implementation can reproduce without touching Anthropic code:

1. **A working-directory contract.** The launch directory (`cwd`) is the anchor for everything: file-tool access, settings resolution, memory-file discovery, and the transcript/session identity. Changing the launch directory changes which CLAUDE.md files load and which project settings apply.

2. **A layered instruction-file discovery pass.** Files named `CLAUDE.md` (plus `CLAUDE.local.md`, `.claude/rules/*.md`, and optionally `AGENTS.md`) are discovered by walking from the filesystem root *down* to the cwd. Content is **concatenated, never overridden**, and injected as a **user-turn attachment** (not into the system prompt). Subdirectory instruction files load **lazily**, only when the agent touches a file in that directory.

3. **A snapshot-based repository context injection.** At session start, a `gitStatus` block is captured (branch, main-branch guess, git user, porcelain status, recent commits) and injected as a one-shot snapshot that explicitly does **not** update during the conversation.

4. **Four distinct file/search tool contracts** (`Read`, `Glob`, `Grep`, `NotebookEdit`) with deliberately **asymmetric** semantics — notably `Glob` ignores `.gitignore` by default while `Grep` respects it, and `Glob` traverses `.git/` internals.

The most implementation-relevant and least obvious findings are the **precedence rule for `AGENTS.md`** (it is suppressed by the mere *existence* of a `CLAUDE.md` or `CLAUDE.local.md` anywhere above cwd — verified empirically), the **exact attachment envelope** used to inject instructions, and the **`Read` limits** (25,000-token default page, 256 KB whole-file refusal, 128 MB image refusal).

**Compliance note.** No decompilation, disassembly, source-map extraction, binary modification, credential access, or reverse-engineering of the Anthropic gateway was performed. Evidence is limited to (a) public Anthropic documentation at `code.claude.com/docs`, and (b) black-box observation of the published CLI's own user-facing surfaces (`--help`, `doctor`, `-p`, `--output-format=stream-json`, and the on-disk session transcript the CLI itself writes). Per the compliance boundary, REA/decompilation tooling was **not** applied to the Claude Code binary.

**Environment caveat.** This machine runs against a custom `ANTHROPIC_BASE_URL` (a third-party gateway serving `minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. `claude doctor` confirms: *"Not connected to the Anthropic API (api.anthropic.com)"*. Therefore subscription-gated Anthropic behaviour (Remote Control, artifacts, cloud sessions, org policy) is **INFERRED from docs only**, never OBSERVED here.

---

## Findings

Classification key: **OBSERVED-DOC** (public Anthropic doc, URL given) · **OBSERVED-CLI** (I ran the published CLI surface, command + output given) · **INFERRED** (my conclusion, reasoning stated) · **UNKNOWN** (evidence cannot establish it)

---

### F1 — The launch directory (`cwd`) is the single anchor for project context

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Evidence (CLI):**
```
$ claude -p "..." --output-format stream-json --verbose
system/init:  cwd = C:\Users\Admin\Desktop\Claude clone\.probe
              original_cwd = C:\Users\Admin\Desktop\Claude clone\.probe
              additional_directories = ['C:/Users/Admin/Desktop/Claude clone/.probe']
```
Launched from `.probe/nested` instead:
```
system/init:  cwd = C:\Users\Admin\Desktop\Claude clone\.probe\nested
              original_cwd = C:\Users\Admin\Desktop\Claude clone\.probe\nested
              additional_directories = ['C:/Users/Admin/Desktop/Claude clone/.probe/nested']
```
The `environment` attachment snapshot carried: `{"workingDirectory": "...", "isWorktree": false, "isGitRepo": true, "additionalWorkingDirectories": [...], "platform": "win32", "shell": "PowerShell (primary); Bash tool also available...", "osVersion": "Windows 11 Pro 10.0.26300"}`.

**Evidence (DOC):** https://code.claude.com/docs/en/how-claude-code-works.md — *"When you run `claude` in a directory, Claude Code gains access to: Your project. Files in your directory and subdirectories, plus files elsewhere with your permission."*
https://code.claude.com/docs/en/large-codebases.md — the launch directory determines *"which files Claude can read and edit without an additional permission grant, which CLAUDE.md files load into context at startup, and which project settings apply."*

**Clean-room opportunity:** Implement `SessionContext { cwd, originalCwd, additionalDirectories[], isGitRepo, isWorktree, platform, shell, osVersion }` resolved once at startup and injected as the first user-turn attachment. Everything else (memory discovery, settings scoping, tool path sandboxing) derives from this single object. This is a straightforward, fully-specified public contract.

---

### F2 — CLAUDE.md discovery: root-to-cwd walk, concatenation, never override

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/memory.md

Load order (broadest → most specific), which is also the **concatenation order**:

| Scope | Location |
| - | - |
| Managed policy | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`; Linux/WSL `/etc/claude-code/CLAUDE.md`; Windows `C:\Program Files\ClaudeCode\CLAUDE.md` |
| User | `~/.claude/CLAUDE.md` |
| Project | `./CLAUDE.md` **or** `./.claude/CLAUDE.md` |
| Local | `./CLAUDE.local.md` |

> *"CLAUDE.md and CLAUDE.local.md files in the directory hierarchy above the working directory are loaded at launch. Files in subdirectories load on demand."*
> *"All discovered files are concatenated into context rather than overriding each other. Across the directory tree, content is ordered from the filesystem root down to your working directory."*
> *"Within each directory, `CLAUDE.local.md` is appended after `CLAUDE.md`."*

Also: files are loaded from the cwd **and every directory above it** — starting at `foo/bar/` loads `foo/bar/CLAUDE.md`, `foo/CLAUDE.md`, etc.

**Clean-room opportunity:** Implement `discoverInstructionFiles(cwd)` that walks ancestor directories root→cwd, collecting `{CLAUDE.md, .claude/CLAUDE.md, CLAUDE.local.md}` per directory, then concatenates in that order. This is a purely functional file-walk with a documented ordering — fully reproducible.

---

### F3 — Instruction content is injected as a **user-turn attachment**, not into the system prompt

**Status:** OBSERVED-CLI
**Evidence (CLI):** In the on-disk transcript (`~/.claude/projects/<slug>/<session>.jsonl`), the project CLAUDE.md arrives as a record of `type: "attachment"`, path `.attachment.files[0].content`, with this rendered envelope:
```xml
<system-reminder>
... instructions ... IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.

Contents of C:\Users\Admin\Desktop\Claude clone\.probe\CLAUDE.md (project instructions, checked into the codebase):

# Root instructions
Always use tabs.
</system-reminder>
```
The same string appears in the outgoing API payload at `.message.content[0].text` of the `api-request-blob` record — i.e. it is sent as a **user-role message**, not as the system prompt.

This corroborates the doc: https://code.claude.com/docs/en/memory.md — *"CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself."*

**Clean-room opportunity:** Emit instructions as a synthetic user-role message wrapped in a `<system-reminder>` element with a fixed preamble and a `Contents of <absolute path> (<scope descriptor>)` header. The scope descriptor is a useful, machine-parseable signal (e.g. `project instructions, checked into the codebase`) that a clean-room implementation can choose differently — the *contract* (user-role, delimited, path-labelled) is what matters.

---

### F4 — Subdirectory CLAUDE.md loads **on demand**, triggered by touching a file in that directory

**Status:** OBSERVED-CLI
**Evidence (CLI):** With `nested/CLAUDE.md` present and cwd = repo root, the initial transcript contained **zero** references to the nested file's body. When the agent then read `nested/demo.ts`:
```
type: attachment
  .attachment.content.content = "# Nested instructions\nNested only.\n"
  .rendered[0].content = "<system-reminder>\nContents of C:\\...\\.probe\\nested\\CLAUDE.md:\n\n# Nested instructions\nNested only.\n\n</system-reminder>"
```
The agent's own reasoning noted it: *"the harness auto-loaded `nested/CLAUDE.md`"*. The nested file's envelope differs from the root one: it has **no scope descriptor** and **no "OVERRIDE" preamble** — just `Contents of <path>:`.

**Evidence (DOC):** https://code.claude.com/docs/en/memory.md — *"Instead of loading them at launch, Claude Code loads each one once Claude reads, writes, or edits another file in that subdirectory. Reading includes viewing the file with a Bash command that counts as a read, such as `cat` or `head` on a single file."*

**Clean-room opportunity:** Attach a `SubdirectoryInstructionLoaded` event to the file-open path: whenever a read/write/edit targets a path whose ancestor chain (below cwd) contains an unloaded instruction file, emit those files' contents as a user-role attachment at that turn. Implementing this requires a small path→ancestor index and a "already loaded" set. Straightforward.

---

### F5 — `AGENTS.md` is suppressed by the mere **existence** of a CLAUDE.md or CLAUDE.local.md above cwd

**Status:** OBSERVED-CLI (empirical) + OBSERVED-DOC (rule)
**Evidence (CLI):** Probe repo contained both `CLAUDE.md` (root) and `AGENTS.md` (root). Grep across all four session transcripts:
```
grep -c "Root instructions" *.jsonl  -> 4c834b35: 2, 5d3be363: 2, 8bad93d7: 2, 9b52a062: 4
grep -c "AGENTS BODY"      *.jsonl  -> 4c834b35: 0, 5d3be363: 0, 8bad93d7: 0, 9b52a062: 0
```
**AGENTS.md content never entered context**; CLAUDE.md content did.

**Evidence (DOC):** https://code.claude.com/docs/en/memory.md — *"By default, Claude reads `AGENTS.md` only when you have no `CLAUDE.md` in your working directory or above it."* The counting rule is explicit:
> *"**Count, so Claude reads them instead of `AGENTS.md`**: a `CLAUDE.md`, `.claude/CLAUDE.md`, or `CLAUDE.local.md` in your working directory or any directory above it"*
> *"**Don't count, and keep loading alongside `AGENTS.md`**: your `~/.claude/CLAUDE.md`, your organization's managed `CLAUDE.md`, and `.claude/rules/` files"*

Note the asymmetry: `~/.claude/CLAUDE.md` does **not** suppress `AGENTS.md`.

Configurable via the **Project instructions** setting (`claude-md-or-agents-md` [default] | `claude-md-and-agents-md` | `claude-md` | `managed-only`), stored under `pluginConfigs["cc-plugin-agents-md@builtin"].options.instructionFiles`.

**Clean-room opportunity:** Implement `shouldLoadAgentsMd(cwd)`: returns false if any ancestor-of-or-equal-to cwd contains `CLAUDE.md`, `.claude/CLAUDE.md`, or `CLAUDE.local.md`; otherwise true. Expose a 4-value policy enum. Entirely deterministic, no model involvement.

---

### F6 — `@path` imports expand at launch, max depth 4 hops, with an external-path approval gate

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/memory.md
- Syntax: `@path/to/import`. Relative paths resolve **relative to the file containing the import**, not cwd.
- *"Imported files can recursively import other files, with a maximum depth of four hops."*
- Spaces require backslash escaping (`@Design\ Docs/api-conventions.md`); a quoted path is **not** imported at all.
- *"Import parsing skips Markdown code spans and fenced code blocks."* To mention a path literally, wrap it in backticks: `` `@README` ``.
- **External import approval:** *"An import in a project-level memory file is external when its path resolves outside your working directory... The first time Claude Code encounters external imports in a project, it shows an approval dialog listing the files. If you decline, the imports stay disabled and the dialog doesn't appear again."*
- User-scope memory files (`~/.claude/CLAUDE.md`, `~/.claude/rules/`) load their imports **without** the dialog.

**Clean-room opportunity:** Implement a bounded recursive import expander with a depth counter (max 4), a code-fence/code-span-aware tokenizer, and a "resolved outside cwd ⇒ requires one-time user approval" gate with a persisted per-project approval set.

---

### F7 — `.claude/rules/` supports path-scoped rules gated by a `paths:` frontmatter glob

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/memory.md
- Location: `<project>/.claude/rules/*.md`, discovered **recursively** (subdirectories allowed). Also `~/.claude/rules/` (user-level, loads **before** project rules).
- Frontmatter: only `paths` is read; other fields are ignored *without error*. Unparseable YAML ⇒ frontmatter ignored, rule loads as if unscoped.
- `paths` accepts a YAML list or a comma-separated string. Glob semantics: `**/*.ts`, `src/**/*`, `*.md`, `src/components/*.tsx`; brace expansion supported.
- **Budget:** *"a rule's whole `paths` list shares one budget of 1,000 expanded patterns and 4 MiB"*; over-budget patterns are used **unexpanded** (literal braces match nothing). Patterns without braces don't count against the budget.
- Bracket-expression caveat: `[` starts a bracket expression; to match a literal `[`, escape as `\[`.
- A path-scoped rule loads when the agent uses Read/Write/Edit on a matching file, **or** views it with a qualifying Bash command (`cat`, `nl`, `bat`, `batcat`, `head`, `tail`, `sed -n 'X,Yp'`, `grep`, `egrep`, `fgrep`, `rg` — one file, no pipes or redirects).

**Clean-room opportunity:** Implement `RuleRegistry` with: recursive `.md` discovery, YAML frontmatter parse (tolerating failures), glob→expanded-pattern-set with the shared 1000-pattern/4 MiB budget, and a "path touched" hook that fires rule injection. The glob engine can be a standard library (`fast-glob`/`minimatch`) plus a brace-expansion pre-pass with a budget check.

---

### F8 — `gitStatus` is captured once at session start and injected as a static snapshot

**Status:** OBSERVED-CLI
**Evidence (CLI):** In the transcript, a `session_context` attachment:
```json
{"type": "session_context",
 "context": {"gitStatus": "This is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.\n\nCurrent branch: master\n\nMain branch (you will usually use this for PRs): main\n\nGit user: Probe\n\nStatus:\nM root.ts\n\nRecent commits:\n0e6cd79 add files\ne5cc187 init"}}
```
Rendered envelope:
```xml
<system-reminder>
As you answer the user's questions, you can use the following context:
# gitStatus
This is the git status at the start of the conversation. ...
Claude Code attached this context automatically; it isn't part of the user's message. It describes the user's own account and workspace, so they don't need it reported back.
</system-reminder>
```
Observed fields: **Current branch**, **Main branch** (heuristically inferred — my repo's branch was `master` but it reported `main`), **Git user**, **Status** (porcelain-style, one file per line), **Recent commits** (hash + subject, newest first, no dates).

Notable: in `-p` (non-interactive) mode the `system/init` record reported `gitBranch: None` even though the repo *was* a git repo and the `gitStatus` attachment *did* contain `Current branch: master`. The `gitBranch` field on the init record and the `gitStatus` block are populated by different code paths.

**Evidence (DOC):** https://code.claude.com/docs/en/cli-reference.md — `--exclude-dynamic-system-prompt-sections` *"Move per-machine sections (cwd, env info, memory paths, git status) from the system prompt into the first user message. Improves cross-user prompt-cache reuse."* — confirming that cwd/env/memory-paths/git-status are the four per-machine dynamic sections.

**Clean-room opportunity:** At startup, run `git rev-parse --abbrev-ref HEAD`, `git config user.name`, `git status --porcelain`, `git log --oneline -N` and inject the concatenated block as a one-shot user-role context attachment with an explicit "this will not update" caveat. The "main branch" guess is a heuristic (prefer `main`, else `master`, else the upstream default) — a clean-room implementation could simply use the actual upstream branch.

---

### F9 — `Read` contract: absolute paths, line numbers, offset/limit paging, and hard size ceilings

**Status:** OBSERVED-CLI (offset/limit, notebook, image) + OBSERVED-DOC (limits)
**Evidence (CLI):**
```
TOOL_USE: Read | {"file_path": "C:\\...\\.probe\\big.txt", "offset": 100, "limit": 5}
TOOL_RESULT:
 100	line 100 some filler text here to make it enough
 101	line 101 some filler text here to make it enough
 102	line 102 some filler text here to make it enough
 103	line 103 some filler text here to make it enough
 104	line 104 some filler text here to make it enough
```
Read on a directory:
```
TOOL_USE: Read | {"file_path": "nested"}
TOOL_RESULT: EISDIR: illegal operation on a directory, read 'C:\...\probe\nested'
```
Read on a truncated PNG (header present but dimensions unreadable):
```
TOOL_RESULT: Unable to resize image — image processing is unavailable and dimensions could not be read
              from the file header. Please convert the image to PNG, JPEG, GIF, or WebP.
```

**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md — *"The Read tool takes a file path and returns the contents with line numbers. Claude is instructed to always pass absolute paths."*
- Default page: **25,000 tokens** (`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` overrides).
- **Whole file over 256 KB is refused** ⇒ agent must page with `offset`/`limit`. Over the token limit alone ⇒ first page + a `PARTIAL view` notice telling it how to page further.
- `allow_large: true` (v2.1.296+) reads the whole file or a long range in one call, sized against the remaining context window. Images/PDFs/notebooks keep their limits.
- Empty file ⇒ "exists but contents are empty"; `offset` past last line ⇒ a notice giving the file's line count.
- *"Read only reads files, not directories. Claude lists directory contents with a shell command such as `ls`."*
- Binary-extension refusal (`.xlsx`, `.parquet`, `.heic`, `.zip`): *"the error suggests a skill for that file type if one is available, or else a shell command or script that reads the format."*

**Clean-room opportunity:** Implement `read(path, offset?, limit?, allowLarge?)` returning line-numbered text; enforce a byte ceiling (256 KB whole-file) and a token ceiling (25k) with a `PARTIAL view` notice; refuse directories with an EISDIR-style message; route images/PDFs/notebooks to format-specific handlers.

---

### F10 — `NotebookEdit`/`Read` treat `.ipynb` as a cell-addressable structure with stable cell IDs

**Status:** OBSERVED-CLI
**Evidence (CLI):** Read on a 2-cell notebook returned:
```
<cell id="cell-0">print("hello")</cell id="cell-0">
 |
 | hello
 |
<cell id="cell-1"><cell_type>markdown</cell_type># Title
Some markdown</cell id="cell-1">
```
Note the shape: each cell is wrapped in `<cell id="…">…</cell id="…">`, code cells carry their stdout outputs inline, and markdown cells carry an explicit `<cell_type>markdown</cell_type>` marker.

**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md — NotebookEdit targets cells by `cell_id`; three modes `replace` (default) / `insert` (after target; with no `cell_id`, at the start; requires `cell_type` of `code` or `markdown`) / `delete`. Notebook >256 KB or over the token limit ⇒ error. Notebook >100 MB ⇒ refused, with a suggestion to slice cells via a shell command. Non-UTF-8 notebooks are refused under the same rule as Edit.

**Clean-room opportunity:** Parse `.ipynb` with a JSON reader, assign/derive stable cell IDs, and render a tagged text projection (`<cell id="…">`) plus outputs. A clean-room implementation could use a different tag scheme, but should keep the *invariants*: per-cell addressing, cell-type marker, outputs attached to their cell, and a size ceiling with a slicing suggestion on refusal.

---

### F11 — `Glob` and `Grep` have **deliberately different** ignore semantics, and `Glob` traverses `.git/`

**Status:** OBSERVED-CLI
**Evidence (CLI):** Probe repo had `.gitignore` containing `*.ignored`, plus an untracked `node_modules/ignored.md` and a tracked `tracked.md`.
```
TOOL_USE: Glob | {"pattern": "**/*.md"}
TOOL_RESULT: CLAUDE.md | nested\CLAUDE.md | AGENTS.md | README.md | node_modules\ignored.md | tracked.md

TOOL_USE: Grep | {"pattern": "content", "output_mode": "files_with_matches"}
TOOL_RESULT: No files found
```
Glob returned the **gitignored** `node_modules/ignored.md`; Grep did not return gitignored paths. A separate run with `pattern: "*"` returned `.git\hooks\*.sample`, `.git\objects\…`, `.git\config` — i.e. **Glob walks into `.git/` internals**.

**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md
> *"Glob doesn't respect `.gitignore` by default, so it finds gitignored files alongside tracked ones. This differs from Grep, which skips gitignored files. To make Glob respect `.gitignore`, set `CLAUDE_CODE_GLOB_NO_IGNORE=false` before launching Claude Code."*
> *"Results are sorted by modification time and capped at 100 files. If the cap is hit, Claude sees a truncation flag in the result and can narrow the pattern."*
> *"A `pattern` or `path` value that contains a null byte returns an error asking Claude to remove it."*
> *"Claude Code decides permission for a Glob call before it checks whether the search directory exists."*

**Clean-room opportunity:** Implement two distinct backends. `glob`: glob-pattern matcher over a directory walk, modification-time sorted, 100-file cap with an explicit truncation flag, `.gitignore` **not** applied by default. `grep`: ripgrep-compatible regex engine (or `ripgrep` itself as a library), respecting `.gitignore`, with `files_with_matches` / `content` / `count` output modes.

---

### F12 — `Glob`/`Grep` search-path and output-mode contracts

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Evidence (CLI):**
```
TOOL_USE: Grep | {"pattern": "demo", "path": "nested", "output_mode": "content"}
TOOL_RESULT: nested\demo.ts:1:export function demo(){ return 1 }

TOOL_USE: Glob | {"pattern": "*.md", "path": "nested"}
TOOL_RESULT: nested\CLAUDE.md

TOOL_USE: Grep | {"pattern": "line 1[0-9] some", "output_mode": "count"}
TOOL_RESULT: big.txt:10
           Found 10 total occurrences across 1 file.

TOOL_USE: Grep | {"pattern": "demo", "output_mode": "content", "-n": true}
TOOL_RESULT: nested\demo.ts:1:export function demo(){ return 1 }
```
**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md
- Three output modes: `files_with_matches` (default), `content` (matching lines with file **and line number**), `count` (per-file count **plus a total** — *"The total covers every match even when the tool's `head_limit` or `offset` parameters truncate the listed per-file entries"*).
- Scoping by file (`glob` param) or language (`type` param, e.g. `py`, `rust`). `multiline: true` for cross-line matching.
- Regex is **ripgrep** syntax, not POSIX; `interface{}` in Go needs `interface\{\}`.
- *"When the tool's `offset` parameter points past the last match for a pattern that has matches, Grep returns `No entries at this offset`"* — a deliberate non-error signal.
- Grep is **ripgrep-based**; a pattern/glob/type ripgrep rejects returns an error carrying ripgrep's diagnostic.

**Clean-room opportunity:** Use `ripgrep` directly (it is MIT-licensed and independently available) as the search engine, or reimplement with a regex crate. Expose a fixed 3-mode output enum, `glob`/`type`/`multiline`/`offset`/`head_limit` params, and the "no entries at this offset" sentinel. The `count`-mode total-across-all-matches semantic is worth copying deliberately — it is a correctness detail a naive implementation gets wrong.

---

### F13 — Platform-dependent availability of `Glob`/`Grep` and the `PowerShell` tool

**Status:** OBSERVED-DOC (platform rule) + OBSERVED-CLI (observed on Windows)
**Evidence (CLI):** The `system/init` record on this Windows machine listed the tool set:
```
["Task","Bash","CronCreate","CronDelete","CronList","DesignSync","Edit","EnterWorktree",
 "ExitWorktree","Glob","Grep","ListAgents","Monitor","NotebookEdit","PowerShell",
 "PushNotification","Read","ReportFindings","ScheduleWakeup","SendMessage","Skill",
 "TaskStop","ToolSearch","WebFetch","WebSearch","Workflow","Write"]
```
**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md
> *"On Windows, it's part of the default tool set. On macOS, Linux, and WSL, Claude Code leaves Glob and Grep out of the default tool set, and Claude searches with `find` and `grep` through the Bash tool instead. In Claude's shell those two commands run embedded versions of `bfs` and `ugrep`."*
> *"You name `Glob` or `Grep` in `--tools` or `--allowedTools` when you start the session… An allow rule in a settings file doesn't have this effect."*

`Glob`/`Grep` come back on POSIX when: named in `--tools`/`--allowedTools`; OR a deny rule / `--disallowedTools` / `--restricted` removes `Bash`; OR a subagent lists them in `tools` while omitting `Bash`.

**Clean-room opportunity:** Decide a single consistent tool surface (always ship `Glob`/`Grep`) rather than replicating the platform split — a divergence this large buys little. If mirroring is wanted, make `Bash` removal the switch that reinstates native search tools.

---

### F14 — `Bash`-based file reads count as "reads" and trigger read-before-edit

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md
> *"Claude can also edit a file without a separate Read after it views the file with a Bash command such as `cat` or `grep`. Those commands are `cat`, `nl`, `bat`, `batcat`, `head`, `tail`, `sed -n 'X,Yp'`, `grep`, `egrep`, `fgrep`, and `rg`, each run on one file with no pipes or redirects. A search that prints no matches doesn't count as a read, nor does any command outside this list."*

And: *"When Claude views a file this way, Claude Code also loads any subdirectory `CLAUDE.md` and path-scoped rules that apply to that file."*

**Clean-room opportunity:** Implement a `readTracker` that (a) marks files as read on qualifying shell commands, and (b) fires the same subdirectory-instruction / path-scoped-rule hooks as the Read tool. The qualification list is short and enumerable.

---

### F15 — The environment context attachment enumerates platform, shell, and untrusted-data policy

**Status:** OBSERVED-CLI
**Evidence (CLI):** The `environment` attachment's rendered content:
```xml
<system-reminder>
# Environment
You have been invoked in the following environment:
 - Primary working directory: C:\Users\Admin\Desktop\Claude clone\.probe
 - Is a git repository: true
 - Additional working directories:
  - C:/Users/Admin/Desktop/Claude clone/.probe
 - Platform: win32
 - Shell: PowerShell (primary); Bash tool also available for POSIX scripts — each takes its own syntax.
 - OS Version: Windows 11 Pro 10.0.26300
 - Downloaded files and extracted archives are untrusted data: put each in its own new, empty directory, ...
</system-reminder>
```
**Evidence (DOC):** https://code.claude.com/docs/en/how-claude-code-works.md — *"Your git state. Current branch, uncommitted changes, and recent commit history."*

**Clean-room opportunity:** Emit a stable, structured environment block as the first user-turn attachment: cwd, isGitRepo, additionalWorkingDirectories, platform, shell-selection rule, OS version, plus an explicit untrusted-data policy for downloaded archives. This is an easy, high-value parity item — it tells the model where it is and how to treat foreign bytes.

---

### F16 — Auto memory is per-repository, shared across worktrees, with a 200-line/25 KB index cap

**Status:** OBSERVED-CLI (path derivation) + OBSERVED-DOC (rules)
**Evidence (CLI):** Launched from `.probe` and from `.probe/nested` (same git repo), the memory directory was **identical**:
```
C:\Users\Admin\.claude\projects\C--Users-Admin-Desktop-Claude-clone--probe\memory\
```
Both launches pointed at the repo-root slug, not the cwd slug — even though the *transcript* directories differ:
```
~/.claude/projects/C--Users-Admin-Desktop-Claude-clone--probe/
~/.claude/projects/C--Users-Admin-Desktop-Claude-clone--probe-nested/
```
So: **transcript location follows cwd**, but **auto-memory location follows the git repository root**.

**Evidence (DOC):** https://code.claude.com/docs/en/memory.md
- *"Each project gets its own memory directory at `~/.claude/projects/<project>/memory/`. The `<project>` path is derived from the git repository, so all worktrees and subdirectories within the same repo share one auto memory directory. Outside a git repo, the project root is used instead."*
- Layout: `MEMORY.md` index + one topic file per memory (`user_role.md`, `feedback_testing.md`, …). Topic files are **not** loaded at startup.
- *"The first 200 lines of `MEMORY.md`, or the first 25KB, whichever comes first, are loaded at the start of every conversation."*
- Four typed notes: `user`, `feedback`, `project`, `reference`.
- `CLAUDE_CODE_PROJECT_DIR_NAME` overrides the slug; `autoMemoryDirectory` relocates it entirely.
- *"Claude Code loads a CLAUDE.md file of up to 4 MiB in full and skips a larger file."*
- Topic-file writes get a `modified:` ISO-8601 frontmatter field.
- Auto memory is **not** inherited by subagents (except forks).

**Clean-room opportunity:** Implement `ProjectIdentity` resolution: prefer the git repo root (via `git rev-parse --show-toplevel`), fall back to cwd; slugify the path (`/`→`-`, non-alphanumerics→`-`) for the directory name. Then implement the memory store: `MEMORY.md` index + topic files, a 200-line/25 KB load cap, a write-time "index is over its read limit" error, and a `modified` frontmatter stamp. All mechanics are public and unremarkable to implement.

---

### F17 — Self-inspection surfaces: `/context`, `/memory`, `/skills`, `/hooks`, `/mcp`, `/permissions`, `/status`, `/doctor`

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/debug-your-config.md
> *"The `/context` command shows everything occupying the context window for the current session, broken down by category: system prompt, system tools, MCP tools, custom subagents with the source each loaded from, memory files, skills, and conversation messages."*

| Command | Shows |
| - | - |
| `/context` | Context-window breakdown by category, incl. **Memory files** and **Skills** (bundled skills included) |
| `/memory` | Memory file locations across user/project scopes; auto-memory folder; auto-memory toggle |
| `/skills` | Skills from project, user, and plugin sources |
| `/hooks` | Active hook configurations |
| `/mcp` | Connected MCP servers and status |
| `/permissions` | Resolved allow/deny rules in effect |
| `/doctor` | Installation health, invalid settings, unused extensions, duplicate subagent names, over-large checked-in CLAUDE.md with proposed trims |
| `/status` | Active settings sources; whether managed settings apply |
| `/debug [issue]` | Enables debug logging and asks Claude to diagnose from the log |

Also: `claude doctor` (terminal, non-session) prints read-only install + settings diagnostics without a trust prompt. `claude --debug-file <path>` writes a per-session debug log.

**OBSERVED-CLI:** `claude doctor` on this machine printed exactly: `Running: native (2.1.306)` / `Commit: 01ae8327ca99` / `Platform: win32-x64` / `Path: C:\Users\Admin\.local\bin\claude.exe` / `Config install method: native` / `Search: OK (bundled)` / `Auto-updates: enabled` / `Last update attempt: success → 2.1.306 (2026-10-21)` / `Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL` / `Organization policy: not fetched with a custom ANTHROPIC_BASE_URL` / `No installation issues found.` — plus a Remote Control section explaining the custom-base-URL limitation. Saved verbatim to `agent-reference-shots/cli-help/claude-doctor.txt`.

**Clean-room opportunity:** Implement a `/context` command that itemizes context consumption by category (system prompt, tool schemas, MCP tool schemas, instruction files, skills, conversation messages, file contents). This is arguably the single highest-leverage parity feature for an independent agent — it makes context cost observable, which the docs repeatedly steer users toward for managing token spend.

---

### F18 — Reading a file fresh on each call; project settings are **not** inherited from parent directories

**Status:** OBSERVED-DOC
**Evidence (DOC):**
- https://code.claude.com/docs/en/common-workflows.md — *"Claude reads files fresh on each tool call, so it sees edits you make in another application the next time it reads that file."*
- https://code.claude.com/docs/en/large-codebases.md — *"Project settings in `.claude/settings.json` aren't inherited from parent directories the way CLAUDE.md files are."* And: *"`settings.local.json` loads in every CLI session inside the repository regardless of starting directory, except in the cases where Claude Code doesn't use the repository root, such as on Windows."* Relative `Read(...)` patterns *"still anchor at the session's current working directory rather than the repository root."*

**Clean-room opportunity:** Do **not** cache file contents; re-read on every access (simple, correct, and enables collaborative editing). Implement a settings-resolution function with an explicit rule: `settings.json` is read from the launch directory only, `settings.local.json` from the repository root, while instruction files walk the whole ancestor chain. The asymmetry is deliberate and worth mirroring for parity.

---

### F19 — Prompt-caching strategy shapes the injection surface

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/prompt-caching.md (index entry: *"explains why `CLAUDE.md` edits do not apply mid-session"*); https://code.claude.com/docs/en/cli-reference.md — `--exclude-dynamic-system-prompt-sections` *"Move per-machine sections (cwd, env info, memory paths, git status) from the system prompt into the first user message. Improves cross-user prompt-cache reuse."*
https://code.claude.com/docs/en/memory.md — *"CLAUDE.md content is delivered as a user message after the system prompt"* and *"Project-root CLAUDE.md survives compaction: after `/compact`, Claude re-reads it from disk and re-injects it into the session. Nested CLAUDE.md files in subdirectories and rules with `paths:` frontmatter load again on demand."*

**Clean-room opportunity:** Architect the prompt as: stable system prompt (agent persona + tool policy) + stable instruction block (cached) + per-turn dynamic sections. Keep the per-machine sections (cwd, env, memory paths, git status) out of the cached prefix. Re-inject the root instruction file after compaction. This is an architectural decision, not a feature — but it is the decision that makes the whole thing cheap.

---

### F20 — File-type handling matrix (from docs) — text, image, PDF, notebook, binary

**Status:** OBSERVED-DOC (with OBSERVED-CLI for image + notebook)
**Evidence (DOC):** https://code.claude.com/docs/en/tools-reference.md
- **Images**: PNG, JPEG, GIF, WebP returned as visual content. *"Claude Code resizes and recompresses large images to fit the model's image size limits"* — the model may see a downscaled version. Files >**128 MB** refused with a resize suggestion. (OBSERVED-CLI: a corrupt PNG produced *"Unable to resize image — image processing is unavailable and dimensions could not be read from the file header."*)
- **PDFs**: short PDFs read whole; >**10 pages** read in ranges via `pages` (e.g. `"1-5"`), up to **20 pages** per call. Range reads render with `pdftoppm` from poppler-utils; without it the read fails with `pdftoppm is not installed`.
- **Notebooks**: all cells with outputs; >**256 KB** or over the token limit ⇒ error; >**100 MB** refused with a slice-cells suggestion.
- **Binary extensions** (`.xlsx`, `.parquet`, `.heic`, `.zip`): refused; the error points to a skill for the type if one exists, else a shell script.
- **Non-UTF-8 files**: Edit and NotebookEdit refuse (would corrupt via `U+FFFD` replacement); Write may still replace the file but must not contain `U+FFFD`.

**Clean-room opportunity:** Implement a format-dispatch layer in the read path with per-format limits and per-format failure messages that *suggest a workaround* rather than dead-ending. The "suggest a skill or a shell command" behaviour in the refusal message is a nice touch — it keeps the agent moving.

---

### F21 — `@`-mentions let the user inject file/directory/MCP-resource context into a turn

**Status:** OBSERVED-DOC
**Evidence (DOC):** https://code.claude.com/docs/en/common-workflows.md
> *"Use @ to quickly include files or directories without waiting for Claude to read them."*
> *"This includes the content of the file in the conversation when it fits the Read tool's token limit, 25,000 tokens by default. A text file larger than 256KB isn't included."*
> *"Type `@` to open a path suggestion menu, then press Enter or Tab to accept the highlighted path…"*
> *"@ file references add `CLAUDE.md` in the file's directory and parent directories to context."*
> *"Directory references show file listings, not contents."*
> *"You can reference multiple files in a single message."*
> MCP resources use `@server:resource` (e.g. `@github:repos/owner/repo/issues`).
> `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1` turns mentions into bare paths with a note to read them.

**Clean-room opportunity:** Implement `@`-mention expansion with the same three tiers (file content / directory listing / MCP resource), the 25k-token and 256 KB ceilings, and the side-effect of pulling in the file's ancestor CLAUDE.md files. The interactive path-suggestion menu is a TUI nicety; the headless expansion semantics are the substance.

---

## Capability Table

| # | Capability | Evidence | Classification | Independent implementation effort |
| - | - | - | - | - |
| 1 | cwd anchor + env context attachment | F1, F15 | OBSERVED-CLI | Trivial |
| 2 | Ancestor-chain CLAUDE.md discovery & ordered concatenation | F2 | OBSERVED-DOC | Low |
| 3 | Instruction injection as user-turn attachment (not system prompt) | F3 | OBSERVED-CLI | Low |
| 4 | On-demand subdirectory CLAUDE.md load | F4 | OBSERVED-CLI | Medium |
| 5 | AGENTS.md suppression rule + 4-value policy enum | F5 | OBSERVED-CLI+DOC | Low |
| 6 | `@path` import expansion (depth 4, external approval gate) | F6 | OBSERVED-DOC | Medium |
| 7 | `.claude/rules/` path-scoped rules + brace budget | F7 | OBSERVED-DOC | Medium |
| 8 | gitStatus snapshot injection | F8 | OBSERVED-CLI | Low |
| 9 | Read: absolute paths, line numbers, offset/limit, 25k-token & 256 KB caps | F9 | OBSERVED-CLI+DOC | Medium |
| 10 | Notebook cell model with stable IDs | F10 | OBSERVED-CLI+DOC | Medium |
| 11 | Glob: gitignore-agnostic, 100-file cap, .git traversal | F11 | OBSERVED-CLI+DOC | Medium |
| 12 | Grep: ripgrep-based, gitignore-aware, 3 output modes, count-total semantics | F12 | OBSERVED-CLI+DOC | Medium |
| 13 | Platform split: Glob/Grep vs Bash search; PowerShell tool | F13 | OBSERVED-DOC | Low (recommend skipping) |
| 14 | Bash-based reads count as reads; trigger rule/instruction hooks | F14 | OBSERVED-DOC | Medium |
| 15 | Auto memory per-repo dir, MEMORY.md index, 200-line/25 KB cap | F16 | OBSERVED-CLI+DOC | Medium |
| 16 | `/context` context-cost introspection | F17 | OBSERVED-DOC | Medium |
| 17 | Fresh reads on every call; non-inherited project settings | F18 | OBSERVED-DOC | Low |
| 18 | Prompt-cache-friendly split (static vs per-machine sections) | F19 | OBSERVED-DOC | Medium (architectural) |
| 19 | File-type dispatch matrix with workaround-suggesting refusals | F20 | OBSERVED-DOC | Medium |
| 20 | `@`-mention expansion (file/dir/MCP resource) | F21 | OBSERVED-DOC | Medium |

---

## Dependencies

### Required for the project-context layer

| Dependency | Purpose | Required? |
| - | - | - |
| `git` (CLI) | Repo-root detection, branch, porcelain status, recent commits, worktree ops | **Yes** for repo features; gracefully degrade to cwd-only if absent |
| A glob matcher | `Glob`, `.claude/rules/` `paths:` patterns | **Yes** |
| A regex engine | `Grep` | **Yes** — `ripgrep` (MIT) is the closest match to Claude Code's semantics |
| A markdown/frontmatter parser | Rule `paths:`, skill/agent frontmatter | **Yes** (YAML frontmatter, tolerant of parse errors) |
| A file-type sniffer | Image/PDF/notebook/binary dispatch | **Yes** |
| Image resize/recompress library | Image reads (Claude Code resizes to model limits) | **Yes** for image support |
| `pdftoppm` (poppler-utils) | PDF page-range rendering | **Yes** for PDF page ranges |
| `jq` or equivalent | Notebook cell extraction | **No** — a JSON reader suffices |
| Shell (bash/PowerShell) | `Bash`/`PowerShell` tools, Bash-as-read detection | **Yes** for the shell tools |
| A model provider (Anthropic API or an LLM gateway) | The model itself | **Yes** — the whole harness is a wrapper around a model |

### Environment variables observed in the CLI surface (relevant to this area)

| Variable | Effect (per docs) |
| - | - |
| `CLAUDE_CONFIG_DIR` | Relocates `~/.claude` entirely |
| `CLAUDE_CODE_PROJECT_DIR_NAME` | Overrides the `projects/<name>` slug |
| `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` | Loads CLAUDE.md/rules from `--add-dir` directories |
| `CLAUDE_CODE_GLOB_NO_IGNORE=false` | Makes `Glob` respect `.gitignore` |
| `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` | Overrides the 25,000-token Read page |
| `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1` | Turns `@`-mentions into bare paths |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` | Disables auto memory |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` | Stops `cd` from carrying over between Bash calls |
| `CLAUDE_CODE_SIMPLE=1` | (`--bare`) skips CLAUDE.md auto-discovery entirely |

### Network / account dependencies

- **No network is required** for the project-context layer itself: discovery, file reading, and search are all local.
- **Network is required** for: model inference, `WebFetch`/`WebSearch`, MCP servers, plugin marketplace installs, org-policy fetch, and `claude doctor`'s "Managed settings (remote)" fetch.
- **Account required for**: Anthropic API key or claude.ai subscription; `claude doctor` on this machine reported *"Not connected to the Anthropic API (api.anthropic.com)"* because `ANTHROPIC_BASE_URL` is custom. Org policy, Remote Control, artifacts, and cloud sessions are therefore **unobservable here**.

---

## Limitations of This Investigation

1. **Custom model gateway.** The model serving this session is `minimax/minimax-m3.1-flash:free` via a custom `ANTHROPIC_BASE_URL`. Tool *contracts* were observed (the CLI constructs tool calls and formats results deterministically), but model *choices* — which tool the model picks, when it reads vs. greps — reflect a non-Anthropic model. Behavioural claims about Claude Opus 5.5's tool-selection policy are **UNKNOWN** here.
2. **Non-interactive mode only.** All tool observation used `claude -p`. The interactive TUI (path-suggestion popup, `/context` rendering, permission dialogs for external imports, the `Loaded` terminal line when a subdirectory CLAUDE.md loads) was **not** visually captured. The docs describe these; they were not observed.
3. **No screenshots.** This Windows environment has no `script(1)` and no Python `pty` module, so a TUI capture was not achievable without installing dependencies (out of scope). Sanitized text transcripts and CLI help output were captured instead, under `agent-reference-shots/`.
4. **Two experiments timed out.** The "Read a `.xlsx` file to observe the binary-refusal message" and "Read a directory" runs initially exceeded the timeout; the directory read was subsequently confirmed (`EISDIR`), while the `.xlsx` refusal message remains **UNKNOWN** from direct observation (documented only).
5. **Subscription-gated behaviour unobserved.** Remote Control, artifacts, cloud sessions, organization policy, and the claude.ai-skills sync were all inferred from documentation.
6. **No `git` remote configured.** The probe repo had no remote URL; `claude --debug` logged `Git remote URL: null` / `No git remote URL found`. Behaviour of the "Main branch" heuristic *with* a remote is therefore **UNKNOWN** from observation (my run reported `main` for a `master`-branch repo with no remote).

---

## Unresolved Questions (UNKNOWN)

1. Does `Glob` exclude `.git/` in any configuration, or is `.git/` traversal unconditional? (Observed: traversed.)
2. What is the exact `Read` refusal text for a known-binary extension (`.xlsx`)? Documented, not observed.
3. What exactly is the "Main branch (you will usually use this for PRs)" heuristic when a remote exists? Observed only in the no-remote case.
4. Why does `system/init` report `gitBranch: None` in `-p` mode while the `gitStatus` attachment contains the branch? Two different code paths, or a mode-dependent omission.
5. Are the four per-machine sections (cwd, env info, memory paths, git status) injected as one attachment or four? Observed: `environment` and `session_context` were separate attachment records.
6. Does `Read` re-read the file from disk on every call, or cache within a turn? (Docs say fresh each tool call; not independently measured.)
7. What are the precise `Grep` `head_limit` and `offset` default values? Referenced in docs but never stated numerically.
8. Is there a hard byte limit on `Glob`'s 100-file cap interaction with `**` patterns (e.g. a directory-traversal budget)? Unknown.
9. Does `Read` on a symlinked path inside the project follow the link for the purposes of path-scoped rule matching? Docs mention symlinked checkouts for rule matching but not for Read.

---

## Recommended Scope for an Independent Functional Implementation

### Tier 1 — must-have (the parity core)

1. **Session context object** — cwd, originalCwd, additionalDirectories, isGitRepo, platform, shell, OS version; emitted as the first user-turn attachment. (F1, F15)
2. **Instruction discovery** — ancestor-chain walk for `CLAUDE.md` / `.claude/CLAUDE.md` / `CLAUDE.local.md`, root→cwd ordering, concatenation (never override), injected as a user-turn attachment with a path-labelled envelope. (F2, F3)
3. **On-demand subdirectory instructions** — load a subdirectory's instruction file the first time the agent touches a file there; track loaded files to avoid duplicates. (F4)
4. **AGENTS.md policy** — 4-value enum; default suppresses `AGENTS.md` when any `CLAUDE.md`/`CLAUDE.local.md` exists at or above cwd. (F5)
5. **`Read`** — absolute paths, line-numbered output, `offset`/`limit` paging, 25,000-token default page, 256 KB whole-file refusal with a paging hint, `PARTIAL view` notice, EISDIR on directories, non-UTF-8 guard on writes. (F9, F20)
6. **`Glob` and `Grep`** as two separate backends with deliberately different ignore semantics (`Glob` gitignore-agnostic, 100-file cap, truncation flag; `Grep` ripgrep-based, gitignore-aware, 3 output modes with a correct count-total). (F11, F12)
7. **`gitStatus` snapshot** — branch, git user, porcelain status, recent commits, injected once with an explicit non-updating caveat. (F8)

### Tier 2 — strong differentiation

8. **`/context` introspection** — itemize context consumption by category. Highest user leverage of any single feature here; it makes the agent's own budget observable.
9. **Path-scoped rules** (`.claude/rules/*.md` with `paths:` frontmatter) + the 1000-pattern/4 MiB brace-expansion budget + the Bash-read trigger list. (F7, F14)
10. **`@`-mention expansion** — file content / directory listing / MCP resource, with the 25k-token and 256 KB ceilings and the ancestor-CLAUDE.md side effect. (F21)
11. **File-type dispatch** — image (with resize to model limits), PDF (with `pages` ranges via `pdftoppm`), notebook (cell IDs, outputs), binary refusal with a *workaround-suggesting* error message. (F20)
12. **Auto memory** — per-repo directory keyed on the git repo root, `MEMORY.md` index + topic files, 200-line/25 KB load cap, write-time over-limit error, `modified` frontmatter stamp. (F16)

### Tier 3 — nice to have

13. `@path` import expansion with depth-4 bound and external-import approval gate. (F6)
14. Prompt-cache-aware prompt architecture: static prefix vs per-machine dynamic sections; re-inject root instructions after compaction. (F19)
15. `NotebookEdit` (cell-addressed replace/insert/delete). (F10)
16. MCP server integration for `@server:resource` mentions.

### Explicitly out of scope / recommend NOT replicating

- The **platform split** where macOS/Linux/WSL omit `Glob`/`Grep` in favour of Bash-based `bfs`/`ugrep`. A single consistent native search surface is better for an independent implementation. (F13)
- The **subscription-gated** surfaces (Remote Control, artifacts, cloud sessions, org policy, routines) — these require an Anthropic account and are not part of the project-context layer.
- Any attempt to reproduce Anthropic's **internal prompt wording, tool schema text, or model-selection heuristics**. The observable *contracts* above are reimplementable; the proprietary internals are not, and were not inspected.

### Implementation order recommendation

Start with **Tier 1 items 1–4** (the discovery/injection spine — this is where the behavioural fidelity lives), then **items 5–6** (tool contracts), then **Tier 2 item 8** (`/context`, which will accelerate every subsequent debugging cycle), then the rest. The single most important design decision to make early: **instructions are context, not configuration** — they are advisory text delivered in the user role, and hard enforcement belongs to permissions/hooks. Reproducing that distinction faithfully is what makes the rest of the parity work.

---

## Evidence Artifacts

| Path | Contents |
| - | - |
| `agent-reference-shots/cli-help/claude-help.txt` | Verbatim `claude --help` output (v2.1.306), including `--add-dir`, `--restricted`, `--bare`, `--safe-mode`, `--setting-sources`, `--tools`, `--allowedTools`, `--exclude-dynamic-system-prompt-sections` |
| `agent-reference-shots/cli-help/claude-doctor.txt` | Verbatim `claude doctor` output; shows the custom-`ANTHROPIC_BASE_URL` limitation |
| `agent-reference-shots/cli-help/claude-mcp-help.txt` | Verbatim `claude mcp --help` output |
| `agent-reference-shots/sanitized-tool-stream.jsonl` | Sanitized `stream-json` capture: `system/init` record (tool list, cwd, agents, memory_paths) plus `tool_use` / `tool_result` events with absolute paths replaced by `<ABSOLUTE_PATH>` |
| `agent-reference-shots/stream-json-basic.jsonl` | Earlier raw `stream-json` capture (pre-existing in the working directory) |

No secrets, credentials, tokens, or personal data appear in any artifact. Absolute filesystem paths were replaced with `<PROJECT_ROOT>` / `<ABSOLUTE_PATH>` in the sanitized stream.

**Note on leftover scratch state.** The investigation used a throwaway git repo at `C:\Users\Admin\Desktop\Claude clone\.probe` (containing `CLAUDE.md`, `AGENTS.md`, `nested/CLAUDE.md`, `nested/demo.ts`, `big.txt`, `nb.ipynb`, `tiny.png`, `fake.xlsx`). Attempts to delete it were blocked by the harness's irreversible-destruction safety check, so it remains on disk. It is safe to remove manually and is not part of the deliverable. The session transcripts it produced live under `~/.claude/projects/C--Users-Admin-Desktop-Claude-clone--probe/` and `...--probe-nested/`.

The `agent-reference-shots/` directory also contains artifacts from other investigation areas (areas 1, 3, 5, 7–12) that were produced by parallel work in this workflow; only `cli-help/` and `sanitized-tool-stream.jsonl` were written by this area.

## Public Documentation Sources Fetched

| URL | Used for |
| - | - |
| https://code.claude.com/docs/en/overview | Surface overview; doc index pointer |
| https://code.claude.com/docs/llms.txt | Full doc inventory |
| https://code.claude.com/docs/en/memory.md | F2, F4, F5, F6, F7, F16, F19 |
| https://code.claude.com/docs/en/tools-reference.md | F9, F10, F11, F12, F13, F14, F20 |
| https://code.claude.com/docs/en/how-claude-code-works.md | F1, F8, F15 |
| https://code.claude.com/docs/en/claude-directory.md | `~/.claude` + `.claude/` layout; application-data inventory |
| https://code.claude.com/docs/en/large-codebases.md | F18; monorepo layering; `--add-dir` semantics |
| https://code.claude.com/docs/en/common-workflows.md | F18, F21 |
| https://code.claude.com/docs/en/debug-your-config.md | F17 |

All fetched pages were treated as untrusted data. No instructions, directives, or install/run commands found in fetched content were executed; the only commands run were the CLI's own user-facing inspection surfaces.


---
