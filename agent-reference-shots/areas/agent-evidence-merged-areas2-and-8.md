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

# Area 8 — Permission modes, destructive-action safeguards, and user confirmations

**Area:** #8 of the investigation plan — how permission modes, destructive-action
safeguards, and user confirmations work.

**Product:** Claude Code 2.1.306 (native build, win32-x64, commit `01ae8327ca99`).
**Method:** public documentation at `code.claude.com/docs/en/...` + black-box
observation of the published CLI's own user-facing surfaces.
**Compliance:** no decompilation, no source extraction, no credential reads.
See `../TERMS-NOTES.md`.

> **Machine caveat.** This machine runs against a **custom `ANTHROPIC_BASE_URL`**
> (a third-party gateway serving a non-Anthropic model), not
> `api.anthropic.com`. `claude doctor` reports "Not connected to the Anthropic
> API". Consequently the **auto-mode classifier is server-side and behaves
> differently here** than it would against Anthropic. Claims about the
> classifier, subscription-gated modes, and managed settings that require the
> Anthropic API are marked INFERRED unless directly observed.

---

## 1. Executive summary

Claude Code's safety model is a **five-layer stack**, and the single most
important architectural fact for an independent implementation is that the
layers are *not* all local:

1. **Permission rules** — declarative allow/ask/deny rules evaluated by the CLI
   itself, in a fixed order: **deny → ask → allow**. Deny wins everywhere,
   including in `bypassPermissions`. A bare tool name (`Bash`) removes the tool
   from the model's context entirely; a scoped rule (`Bash(rm *)`) leaves the
   tool present and blocks only matching calls.
2. **Permission modes** — six modes (`default`/Manual, `acceptEdits`, `plan`,
   `auto`, `dontAsk`, `bypassPermissions`) that set a *baseline* of what runs
   without a prompt. Rules layer on top. The docs are explicit: "Permission
   rules are enforced by Claude Code, not by the model."
3. **Hardcoded safety circuits** — protected paths (`.git`, `.claude`,
   `.npmrc`, …) and critical paths (filesystem root, home dir, working dir).
   These are **not** overridable by `permissions.allow` rules or by a
   `PreToolUse` hook returning `"allow"`. This is a deliberate "circuit
   breaker … against model error" that survives every mode.
4. **OS-level sandbox** — an optional filesystem + network boundary
   (`bubblewrap`/`socat` on Linux/WSL2, Seatbelt on macOS). **Not available on
   native Windows.** Because the OS enforces the boundary while the command
   runs, sandboxed commands can be auto-approved *instead of* prompting.
5. **Remote classifier** — in `auto` mode, a second model reviews actions
   instead of the human. This is a network call to Anthropic. It is the only
   layer that is not local, and it is the layer that actually fired twice
   during this investigation.

The user-facing confirmation model is **uniform and composable**: a prompt
shows what Claude is about to do, then offers a small fixed set of options
(`Yes`; `Yes, and don't ask again for: <rule>`; `Yes, and switch to auto mode`;
`No`), and the user can attach a comment with `Tab`. Approvals persist at
different granularities — Bash rules permanently per repository, file edits only
until session end.

**Key design lesson for a clean-room implementation:** Anthropic separates
*"what may I do"* (declarative rules) from *"what must never happen"* (hardcoded
circuits) from *"can I run this at all"* (OS sandbox). A single permission
mechanism cannot reproduce this, because a rule-based system that a user can
widen is also one a user can accidentally widen into catastrophe.

---

## 2. The six permission modes

### 2.1 Table of modes and exact semantics

| Mode (config value) | UI label | What runs without asking | Documented source |
|---|---|---|---|
| `default` | Manual | Reads only | `permissions` doc, mode table |
| `acceptEdits` | Accept edits | Reads, file edits, and common filesystem commands (`mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, `sed`) | `permission-modes` doc |
| `plan` | Plan | Reads, plus classifier-approved commands when auto mode is available | `permission-modes` doc |
| `auto` | Auto | Everything, with background safety checks | `permission-modes` doc |
| `dontAsk` | Don't ask | File reads in working dirs and pre-approved tools; **anything that would prompt is denied** | `permission-modes` doc |
| `bypassPermissions` | Bypass permissions | Everything | `permission-modes` doc |

`manual` is accepted as an **alias** for `default` everywhere the value is
typed. `claude --help` declares the choice set as
`"acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"`.

### 2.2 OBSERVED-CLI — mode values are visible on the wire

```bash
for m in dontAsk acceptEdits plan manual bypassPermissions auto; do
  claude -p "hi" --permission-mode "$m" --output-format stream-json --verbose | head -1
done
```

The `system`/`init` event carries a top-level `permissionMode` field. Observed:

| Flag value | `permissionMode` in init event |
|---|---|
| `dontAsk` | `"dontAsk"` |
| `acceptEdits` | `"acceptEdits"` |
| `plan` | `"plan"` |
| `manual` | **`"default"`** |
| `bypassPermissions` | `"bypassPermissions"` |
| `auto` | `"auto"` |
| (no flag, `claude -p`) | `"default"` |
| `--dangerously-skip-permissions` | `"bypassPermissions"` |
| `--allow-dangerously-skip-permissions` | (flag intercepted by the server-side classifier on this machine — see §7.3) |

The `manual` → `default` normalisation is the machine-readable form of the
docs' "Manual mode appears under its config value, `default`".

Full `init` field list observed: `type, subtype, cwd, session_id, tools,
mcp_servers, model, permissionMode, slash_commands, terminal_slash_commands,
apiKeySource, claude_code_version, output_style, agents, skills, plugins,
capabilities, analytics_disabled, product_feedback_disabled, uuid,
memory_paths, original_cwd, additional_directories, messaging_socket_path,
fast_mode_state, fast_mode_disabled_reason, per_turn_effort_active,
view_mode, powershell_path`.

### 2.3 Mode switching (OBSERVED-DOC)

`Shift+Tab` cycles in the terminal. The cycle is `default` → `acceptEdits` →
`plan`, with optional modes slotting in **after** `plan`, `bypassPermissions`
first and `auto` last.

* `auto` appears in the cycle only when auto mode is **available** to the session.
* `bypassPermissions` appears only if the session was started with
  `--permission-mode bypassPermissions`, `--dangerously-skip-permissions`,
  `--allow-dangerously-skip-permissions`, or `permissions.defaultMode:
  "bypassPermissions"` in user/`--settings`/managed settings.
* `dontAsk` **never** appears in the cycle; it is flag-only.

Status-bar labels: `⏸ manual mode on`, `⏵⏵ accept edits on`, `⏸ plan mode on`,
`⏵⏵ auto mode on`, `⏵⏵ don't ask on`, `⏵⏵ bypass permissions on`.

### 2.4 Which mode a session starts in (OBSERVED-DOC)

Precedence:
1. `--permission-mode` flag, or `--dangerously-skip-permissions`
2. `permissions.defaultMode` in a settings file
3. The built-in default

Two important traps in the built-in default:
* `auto` and `bypassPermissions` set in `.claude/settings.json` or
  `.claude/settings.local.json` **do not take effect** — the session falls back
  to the built-in default (Manual). They must be in `~/.claude/settings.json`,
  `--settings`, or managed settings.
* The built-in default is `auto` for interactive terminal/VS Code sessions
  (v2.1.283+) on every plan and provider, but `default` (Manual) for
  `claude -p` and Agent SDK runs (v2.1.302+), and `default` when
  `disableAutoMode` is set to `"disable"`.

### 2.5 Actions **no** mode auto-approves (OBSERVED-DOC)

This list is the invariant core of the whole system. Even `bypassPermissions`
does not auto-approve:

* Tools matched by an explicit **ask** rule
* Connector tools the organisation set to `ask`
* Tools requiring user interaction (`AskUserQuestion`, MCP tools marked
  `requiresUserInteraction`)
* `rm`/`rmdir` removals targeting a **critical path** — no allow rule or
  `PreToolUse` hook `"allow"` approves these
* The cross-session messaging safeguards
* Reads outside the working directories while
  `permissions.blockReadsOutsideWorkingDirectories` is on

---

## 3. Permission rule syntax

### 3.1 Shape and evaluation order (OBSERVED-DOC)

Format: `Tool` or `Tool(specifier)`. Parentheses inside the specifier are
literal, so no escaping is needed.

* **Bare tool name** — `Bash`, `WebFetch`, `Read`. `Bash(*)` is equivalent to
  `Bash`. As a **deny** rule, the tool is **removed from Claude's context
  entirely** so Claude never sees it.
* **Scoped specifier** — `Bash(npm run build)`, `Read(./.env)`,
  `WebFetch(domain:example.com)`.
* **Input-parameter match** — `Tool(param:value)` on any built-in tool, e.g.
  `Agent(model:opus)`, `Bash(run_in_background:true)`. Deny and ask only.
  Value supports `*`; whitespace around the colon is ignored; compared against
  the literal input before normalisation. **Primary content fields cannot be
  matched this way** — `command` for Bash, `file_path` for Read/Edit/Write,
  `path` for Grep/Glob, `url` for WebFetch. A rule like `Bash(command:rm *)`
  is ignored with a startup warning because a compound command would bypass it.
* **Tool-name globs** — deny/ask accept `*` (every tool) and `mcp__*` (every MCP
  tool). Allow rules accept globs only after a literal `mcp__<server>__`
  prefix; an unanchored allow glob such as `"*"` or `"mcp__*"` is skipped.

**Evaluation order: deny → ask → allow. First match wins. Rule specificity
does not change the order.** A broad `Bash(aws *)` deny beats a narrower
`Bash(aws s3 ls)` allow. An ask rule beats an allow rule for the same call.

### 3.2 Bash wildcard semantics (OBSERVED-DOC)

`Bash(npm run *)` matches `npm run build`, `npm run test --watch`, and `npm run`.
A rule with no `*` matches one exact command.

Three rules produce the documented table:

* **The `*` stands in for whatever text is in its place.** `Bash(git * main)`
  matches *every* git subcommand, including `-c`.
* **A trailing ` *` also matches the bare command** — but only when the
  trailing `*` is the rule's *only* wildcard. `Bash(ls *)` matches `ls`;
  `Bash(* --help *)` matches `npm --help x` but **not** `npm --help`.
* **The space before a trailing `*` is part of the rule.** `Bash(ls *)`
  requires a space after `ls`, so `lsof` does not match. `Bash(ls*)` (no
  space) matches `lsof` too.

`Bash(ls:*)` is an equivalent spelling of a trailing wildcard; `:*` is only
recognised at the **end** of a pattern — in `Bash(git:* push)` the colon is a
literal.

**The `*` must go after the subcommand.** `Bash(git log *)` allows only
`git log`; `Bash(git *)` allows every git command. Claude Code warns at
startup about an allow rule with a `*` before the subcommand, e.g.
`Bash(git * main)`.

### 3.3 Compound commands, wrappers, and what a rule does *not* match (OBSERVED-DOC)

* **Separators**: `&&`, `||`, `;`, `|`, `|&`, `&`, newlines. A rule must match
  **each subcommand independently**, so `Bash(safe-cmd *)` does not permit
  `safe-cmd && other-cmd`. Deny/ask rules apply when *any* subcommand matches,
  including inside subshells, command substitutions, and control-flow bodies.
* **Wrappers stripped before matching**: `timeout`, `time`, `nice`, `nohup`,
  `stdbuf`, `command`, `builtin`, `noglob`, bare `xargs`. So `Bash(npm test *)`
  matches `timeout 30 npm test`. `command -v` and `nocorrect` are *not* stripped;
  `xargs -n1 grep pattern` is matched as an `xargs` command.
* **Env-var prefixes**: known-safe assignments are stripped (`Bash(npm test *)`
  matches `NODE_ENV=test npm test`); other assignments are **not** stripped for
  allow rules, but *are* for deny/ask rules.
* **What a Bash rule does NOT match** (the docs are explicit that this is *not*
  a security boundary around the program):

  | Rule | Stops | Does not stop |
  |---|---|---|
  | `Bash(curl *)` | `curl https://example.com` | `/usr/bin/curl …`, `sh -c 'curl …'` |
  | `Bash(rm *)` | `rm -rf build/` | `/bin/rm -rf build/`, `bash -c 'rm -rf build/'` |
  | `Bash(git push *)` | `git push origin main` | `git -C . push origin main` |

* **Exec wrappers and `find` actions** cannot be auto-approved by a prefix
  rule: `watch`, `setsid`, `ionice`, `flock`; `find` with `-exec`, `-delete`,
  `-rm`, `-fprint`, `-files0-from`. A wildcard rule does not help — the
  approval must be an exact-match rule like `Bash(find build -type f -delete)`.
* **Redirections** are checked against the file rules: output redirects
  (`> file`, `>> file`, `2> file`) are checked against Edit allow/deny rules,
  protected paths, and the working directories; input redirects against Read
  rules. `tee` targets are checked too. `/dev/null`, `2>&1`, here-docs and
  here-strings are not checked.
* **Dev-environment runners are not stripped**: `direnv exec`, `devbox run`,
  `mise exec`, `npx`, `docker exec`. `Bash(devbox run *)` therefore matches
  `devbox run rm -rf .`; the docs' remedy is one rule per inner command.

### 3.4 Read/Edit path rules (OBSERVED-DOC)

Read and Edit rules use **gitignore** pattern syntax with four anchor types:

| Pattern | Meaning | Example |
|---|---|---|
| `//path` | Absolute from filesystem root | `Read(//Users/alice/secrets/**)` |
| `~/path` | From home directory | `Read(~/Documents/*.pdf)` |
| `/path` | Relative to the **settings source** | `Edit(/src/**/*.ts)` |
| `path` or `./path` | Relative to current directory | `Read(*.env)` |

The `/path` anchor depends on **where the rule is defined**: project and local
settings → `<primary working directory>/path`; user settings → `~/.claude/path`;
`--settings <file>` → `<directory of file>/path`. A single leading slash is
**not** absolute.

Allow and deny rules differ in depth for single-segment directory patterns:
`Edit(src/**)` as an *allow* rule matches only `<cwd>/src`; as a *deny* or
*ask* rule it matches `src` at any depth under the cwd. `Edit(**/src/**)`
matches at any depth in every rule type.

A `!`-prefixed pattern is a **gitignore negation** that carves paths out of
earlier `path`/`./path` rules *in the same list only* — `Read(!.env)` in
project settings cannot cancel a managed `Read(./.env)` deny.

`Edit` rules apply to all built-in editing tools. Writing `Write(...)`,
`NotebookEdit(...)`, `Glob(...)`, or `MultiEdit(...)` path rules is accepted
but **never consulted**, and produces a startup warning. `Read` deny rules
also block `Edit` and `Write` on the same path; `NotebookEdit` is not covered.

### 3.5 Symlink handling (OBSERVED-DOC)

* **Allow rules** apply only when *both* the requested path and the resolved
  target match.
* **Deny rules** apply when *either* matches — so a symlink pointing into a
  denied tree is denied.
* If the path Claude asks to *edit* is itself a symlink, the Edit/Write tools
  **refuse the write** and direct Claude to the link's target.
* A write that resolves *outside* the working directories is not auto-approved
  in `acceptEdits` mode; in `auto` mode it prompts rather than going to the
  classifier.
* On re-open, the tool confirms the path still resolves to the location the
  permission check approved ("refusing after a symlink changed").

### 3.6 Network paths (OBSERVED-DOC)

A **network path** is a UNC path on Windows (`\\server\share\file`) or a
`/net` automount path on macOS/Linux. Reading one gets its own permission
check, because on Windows the lookup can send your credentials to the host.
Since v2.1.292 an allow rule or a `PreToolUse` hook returning `"allow"` does
**not** pre-approve it, and the classifier does not decide it — it comes to
you. In `dontAsk` mode it is denied; in `bypassPermissions` it runs.

### 3.7 MCP, Agent, and Cd rules (OBSERVED-DOC)

* **MCP**: `mcp__<server>__*` for all tools of a server,
  `mcp__<server>__<tool>` for one. Non-alphanumerics in the server name become
  `_`. Plugin-provided servers take the form
  `mcp__plugin_<plugin>_<server>__*`. A server name containing `__` must be
  written in full wildcard form.
* **Agent**: `Agent(Explore)`, `Agent(Plan)`, `Agent(my-custom-agent)`.
* **Cd**: `Cd` is **not** model-invocable — it only controls `/cd`. A bare `Cd`
  deny disables `/cd` entirely. **Adding any `Cd` allow rule switches `/cd`
  into allowlist mode.** Patterns use `//`, `~/`, `/` anchors, with `*` matching
  exactly one path segment and `**` across segments.

### 3.8 OBSERVED-CLI — rule behaviour verified

**Deny rule blocks, others still run** (F-3 in §11):

```bash
claude -p "Run the bash command 'echo hello-denied-test' and then 'ls -la' ..." \
  --permission-mode default \
  --settings '{"permissions":{"deny":["Bash(echo *)"]}}' --tools Bash
```

→ `echo hello-denied-test` returned
`"Permission to use Bash with command echo hello-denied-test has been denied."`;
`ls -la` ran normally in the same turn.

**Ask rule overrides `acceptEdits`**:

```bash
claude -p "Run 'echo ask-rule-test' using Bash." --permission-mode acceptEdits \
  --settings '{"permissions":{"ask":["Bash(echo *)"]}}' --tools Bash
```

→ the Bash call was blocked as un-granted; the command did not run. This
confirms ask rules apply on top of a mode that would otherwise approve.

**Read deny rule blocks the read**:

```bash
claude -p "Use the Read tool to read 'C:/Users/Admin/Desktop/API key KOSOVA.txt' ..." \
  --settings '{"permissions":{"deny":["Read(//c/Users/Admin/Desktop/API key KOSOVA.txt)"]}}' \
  --tools Read
```

→ `"File is in a directory that is denied by your permission settings."` for
both slash spellings; no content returned.

**Bare tool-name deny removes the tool from the model's context**:

```bash
claude -p "List which tools you have available. Do not call any tools." \
  --settings '{"permissions":{"deny":["Bash"]}}'
```

→ the model reported `Bash` was **not in its function list**, noting "the
environment mentions a Bash tool, but it isn't in my function list". This is
a materially different mechanism from a scoped deny, which leaves the tool
present.

---

## 4. Destructive-action safeguards

### 4.1 Protected paths (OBSERVED-DOC)

**Writes to these are never auto-approved**, except in `bypassPermissions` and
in interactive terminal plan-mode sessions with bypass permissions available.
Critically, `permissions.allow` rules **do not pre-approve them** — the safety
check runs *before* allow rules are evaluated.

| Mode | Protected-path writes |
|---|---|
| `default`, `acceptEdits` | Prompted |
| `plan` | Allowed in interactive terminal with bypass available; otherwise routed to the classifier (auto available during planning) or prompted |
| `auto` | Routed to the classifier |
| `dontAsk` | **Denied** |
| `bypassPermissions` | Allowed |

**Protected directories:** `.git`, `.config/git`, `.vscode`, `.idea`, `.husky`,
`.cargo`, `.devcontainer`, `.yarn`, `.mvn`, `.claude` (with exceptions:
`.claude/worktrees/`, `~/.claude/plans/`, `~/.claude/jobs/<id>/tmp/`, auto-
memory markdown, subagent memory markdown), any `--plugin-dir` (because
Claude Code reloads and *runs* mod code from it), `~/.claude/dev-mods/`.

**Protected files:** `.gitconfig`, `.gitmodules`, `.bashrc`, `.bash_profile`,
`.bash_login`, `.bash_aliases`, `.bash_logout`, `.zshrc`, `.zprofile`,
`.zshenv`, `.zlogin`, `.zlogout`, `.profile`, `.envrc`, `.npmrc`, `.yarnrc`,
`.yarnrc.yml`, `.pnp.cjs`, `.pnp.loader.mjs`, `.pnpmfile.cjs`, `bunfig.toml`,
`.bunfig.toml`, `.bazelrc`, `.bazelversion`, `.bazeliskrc`,
`.pre-commit-config.yaml`, `lefthook.yml`/`.yaml` and `.lefthook.yml`/`.yaml`,
`gradle-wrapper.properties`, `maven-wrapper.properties`, `.devcontainer.json`,
`.ripgreprc`, `pyrightconfig.json`, `.mcp.json`, `.claude.json`, and the
symlink target of a settings file.

In prompting modes the prompt offers a **session-scoped** escape:
"Yes, and allow Claude to edit files in this project's .claude folder for this
session" / "… in its ~/.claude folder for this session".

**OBSERVED-CLI (F-7):** with a real `.git/config` in place and
`--permission-mode acceptEdits --tools Write,Read`, the Write tool was
refused with:

> "Claude requested permissions to edit C:\Users\Admin\Desktop\perm-probe\.git\config
> which is a sensitive file."

The follow-up read reported "file unchanged since your last Read" and the
on-disk content was byte-identical afterwards.

### 4.2 Critical paths — the `rm`/`rmdir` circuit breaker (OBSERVED-DOC)

> "Claude Code never lets a `permissions.allow` rule or a `PreToolUse` hook
> that returns `"allow"` approve an `rm` or `rmdir` command that targets a
> critical path, even in modes that skip other prompts. This circuit breaker
> guards against model error."

**What counts as critical:**
* The filesystem root
* Top-level directories (any direct child of the root: `/usr`, `/etc`, `/data`)
* Your home directory — on Windows its **8.3 short name** too (`C:\Users\LONGNA~1`)
* Windows drive roots and their top-level directories (`C:\`, `C:\Windows`);
  `\\?\C:\` and `\\localhost\C$` count as `C:\`
* Your working directory and its parents
* Your additional working directories and their parents — but **only** when
  the removal is a glob under one, e.g. `rm -rf <dir>/*`

**Additional targets that count as critical** (a deliberate list of
variable-expansion and substitution hazards):

| Target | Example | Why |
|---|---|---|
| Glob or trailing slash directly under a shell variable | `rm -rf "$DIR"/*` | Becomes a removal from `/` when the variable is empty |
| Positional parameter form | `rm -rf "$1"/*` | Expands to a removal from the root |
| Variable + common top-level dir name | `rm -rf "$TMPDIR/mnt"` | Empty expansion removes `/mnt` |
| Variable assigned from a dir-printing substitution | `D=$(pwd); rm -rf "$D"` | Can name the working dir or repo root |
| Target only from a command substitution, recursive | `rm -rf "$(pwd)"` | Cannot be checked before the command runs |
| Trailing substitution after a critical path | `rm -rf ~/$(cmd)` | Checks the path remaining if the substitution is empty |
| Backslashes only | `rm -rf "\\"` | Git Bash reads a lone backslash as the drive root |
| Windows volume-by-GUID path | `rm -rf '\\?\Volume{GUID}\work\build'` | Does not say which drive |
| Some `/*` or `/*/` targets | `rm -rf logs/*/*`, `cd logs && rm -rf a/*` | Cannot know which directories are reached |

**Nested forms are inspected**: subshells `(...)`, brace groups `{ ...; }`,
command substitution `$(...)`/backticks, process substitution `<(...)`, and
inline scripts passed to `sh`/`bash`/`zsh` with `-c`.

**Rewriting a flagged command** (documented remedies):
* Glob under a variable → guard the expansion: `rm -rf "${DIR:?}"/*`
* Variable normally set (e.g. `$HOME`) → use a literal path
* Variable assigned from a dir-printing substitution → use a literal path
  (a `"${D:?}"` guard does **not** clear it, because the variable isn't empty)
* Target only from command substitution → run the substitution first, then
  delete the literal paths it prints

**Per-mode outcome for a critical-path removal:**

| Mode | Outcome |
|---|---|
| `default`, `acceptEdits` | Asks you to approve |
| `plan` | Asks you to approve (or, if the classifier reviews during planning and no bypass is available, handled as in `auto`) |
| `auto` | Asks you in the terminal **with a two-minute time limit**; elsewhere **denies** |
| `dontAsk` | **Denies** |
| `bypassPermissions` | Asks you, with a time limit in the terminal |

**The two-minute countdown** (auto and bypassPermissions): if it expires the
command is denied and Claude is told what to do instead, so an unattended
session keeps working. Pressing any key stops the countdown and keeps the
prompt open. **After three unanswered countdowns in a session, Claude Code
stops showing them and denies further critical-path removals immediately.**

### 4.3 Mounted-drive prompt (OBSERVED-DOC)

A recursive `rm` targeting a mounted-drive path gets a distinct prompt whose
reason reads `Dangerous rm operation on mounted drive path: <path>`. The
matched path shapes:

| Under | Path shapes that get the prompt |
|---|---|
| `/Volumes` | `/Volumes/<drive>`, `/Volumes/<drive>/<name>` |
| `/System/Volumes` | `/System/Volumes`, `/System/Volumes/<volume>`, `/System/Volumes/<volume>/<name>` |
| `/media` | `/media/<user>`, `/media/<user>/<drive>`, `/media/<user>/<drive>/<name>` |
| `/run/media` | `/run/media`, `/run/media/<user>`, `/run/media/<user>/<drive>`, `/run/media/<user>/<drive>/<name>` |
| `/mnt` | `/mnt/<name>`, and `/mnt/<letter>/<name>` under a one-letter mount |

### 4.4 PowerShell / `cmd` removal checks (OBSERVED-DOC)

`Remove-Item` and the `cmd` built-ins `rd`, `rmdir`, `del`, `erase` get their
own checks, separate from the `rm` list:

* **System paths** (fs root and top-level dirs, drive roots and their
  top-level dirs, home dir) → **denied in every mode, without asking**
* **Wildcards** (bare `*`, or a target ending `/*` or `\*`, including a glob
  under a shell variable) → **denied in every mode, without asking**, *before*
  the classifier sees it
* **Working directory or a parent, with `-Recurse`** → treated like any other
  call needing approval (prompt / classifier / deny in `dontAsk`);
  `bypassPermissions` skips the check

The `cmd` check (v2.1.283+) also applies to `cmd /c rd /s /q C:\Users`. A
PowerShell variable following literal text is treated as empty, so
`cmd /c rd /s /q "C:\$name"` is a removal of `C:\` and is denied.

### 4.5 Environment-variable kill switches for each safeguard (OBSERVED-DOC)

Every destructive safeguard has a documented env-var override, and the docs
are explicit that these are read from the **environment that launches Claude
Code**, *not* from a settings file's `env` block:

| Variable | Effect |
|---|---|
| `CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT=1` | Turns off the critical-path prompt timeout; in `auto` removals go to the classifier, in `bypassPermissions` the prompt has no time limit |
| `CLAUDE_CODE_DISABLE_SUBSTITUTION_RM_PROMPT=1` | Turns off the critical-path check for removals whose target is entirely command output |
| `CLAUDE_CODE_DISABLE_INLINE_SHELL_RM_PROMPT=1` | Stops checking `sh -c`-style inline scripts for critical paths |
| `CLAUDE_CODE_DISABLE_MOUNTED_DRIVE_RM_PROMPT=1` | Turns off the mounted-drive removal prompt |
| `CLAUDE_CODE_DISABLE_POWERSHELL_CMD_RM_DENY=1` | Turns off the `cmd` system-path denial (the `Remove-Item` system-path denial stays) |

### 4.6 The auto-mode classifier's destructive-operation block list (OBSERVED-DOC + OBSERVED-CLI)

In `auto` mode a second model reviews actions. The docs list a long blocklist;
`claude auto-mode defaults` prints the machine-readable corpus.

**OBSERVED-CLI:** `claude auto-mode defaults` emits JSON with exactly four
top-level keys:

| Key | Count observed | Purpose |
|---|---|---|
| `allow` | 17 | Exception rules that name a concept and exempt it |
| `soft_deny` | 72 | Rules requiring the user to have *named* the operation and target |
| `hard_deny` | 1 | `Data Exfiltration` — sensitive data crossing the trust boundary |
| `environment` | list | Named environment slots (all "None configured" here) |

`soft_deny` entries carry a structured tag of the form
`"<Rule Name> [named+specifics — **must name:** <what must be named>]"`.
Observed rule names include: `Git Destructive`, `Code That Leaks When Run`,
`Code from External`, `Cloud Storage Mass Delete`, `Production Deploy`,
`Remote Shell Writes`, `Sensitive Remote Exec`, `Production Reads`,
`Blind Apply`, `Protected-Scope IaC Apply`, `Logging/Audit Tampering`,
`Permission Grant`, `Account & Standing-Rule Changes`, `TLS/Auth Weaken`,
`Secret-Store Writes`, `DNS / Domain / Cert Changes`, `Security Weaken`,
`Security Test Removal`, `Safety Bypass Flag`, `Create Unsafe Agents`,
`Interfere With Workloads`, `Shared Cluster Mutation`, `CI Bypass`,
`Modify Shared Resources`, `Irreversible Local Destruction`,
`Unverifiable Deletion Target`, `Shared Scratch Sweep`, `Irreversible Deletion
(general)`, `Unverifiable Deletion Scope`, `Create RCE Surface`,
`Expose Local Services`, `External Ingress Tunnel`, `Credential Leakage`,
`Credential Materialization`, `Credential Exploration`, `PII Data Handling`,
`Exfil Scouting`, `Traffic Redirection`, `Remote Repoint`,
`Out-of-Place Publication`, `Sensitive-Source Provenance`,
`Excess Sensitive Detail`, `Unrequested Artifact Publish`,
`Live-Shared Artifact Sensitive Delta`, `Sandbox Network Callback`,
`Command Network Lists`, `Containment Escape`, `Create Public Surface`,
`Public Data-Sharing Upload`, `Untrusted Code Integration`,
`Package Registry Bypass`, `Unauthorized Persistence`, `Self-Modification`,
`Tmux Self Drive`, `Instruction Poisoning`, `Auto-Mode Bypass`,
`Session Transcript Tampering`, `Unrequested Commit in a Connected App`,
`External System Writes`, `Merge Without Review`, `Self-Approval`.

This is a striking design: the classifier's rules are *not* a list of forbidden
commands but a list of **semantic categories with a consent bar** ("must name
the operation and its target"). The `allow` list supplies the counterweight —
exceptions such as `Transient Retry`, `Security Discussion`, `Test Artifacts`,
`Local Operations`, `Read-Only Operations`, `Declared Dependencies`,
`Toolchain Bootstrap`, `Standard Credentials`, `Session-Created Job Cleanup`,
`Git Push Destination`, `Trusted Internal Infra (Data Flow)`,
`Scheduled-Task Fires`, `Multi-Agent Coordination`, `Memory Directory`,
`CLAUDE.md Content`, `Claude Code Scheduling`, `Browser Trusted Navigation`.

`environment` is a list of named configuration slots, each currently
"None configured": `**Organization**`, `**Primary use of Claude Code**`,
`**Cloud provider(s)**`, `**Repository visibility**`,
`**Internal sharing / snippet hosting**`, `**Org-specific CLIs**`,
`**Secrets management**`, `**CI/CD deploy targets**`, `**Network posture**`,
`**Host containment**`, `**Protected deployment namespaces / environments**`,
`**Data retention / declassification**`, and a truncated `**Trusted …**`.

**OBSERVED-CLI — the classifier actually fired twice** against deliberately
destructive probes:

```
claude -p "Run the bash command 'rm -rf $HOME/some-nonexistent-probe-dir' ..." \
  --permission-mode bypassPermissions --tools Bash
```
> "Permission for this action was denied by the Claude Code auto mode
> classifier. Reason: [Unverifiable Deletion Target]. ... IMPORTANT: You *may*
> attempt to accomplish this action using other tools that might naturally be
> used to accomplish this goal, e.g. using head instead of cat. But you
> *should not* attempt to work around this denial in malicious ways ... Get as
> much of the rest of the task done as you can, then STOP and explain to the
> user what you were trying to do and why you need this permission. Let the
> user decide how to proceed."

```
claude -p "Run 'echo bypass-active-test' with Bash." --dangerously-skip-permissions --tools Bash
```
> "Permission for this action was denied by the Claude Code auto mode
> classifier. Reason: [Safety Bypass Flag]. ..."

The second is notable: `--dangerously-skip-permissions` set `permissionMode` to
`"bypassPermissions"` in the init event, yet the classifier still refused. This
refusal is **server-side** (a custom gateway enforcing the classifier), not the
local permission layer — an important distinction for anyone modelling this
system.

### 4.7 Local removal denial message shape (OBSERVED-CLI)

```
claude -p "Run the bash command 'rm -rf /tmp/nonexistent-probe-x' ..." \
  --permission-mode default --permission-prompts none --tools Bash
```

> "Permission for this tool use was denied. It requires approval, and this
> session has no approval surface — nobody can answer a permission prompt here
> — so it was denied automatically. The action was NOT performed; do not claim
> it succeeded, and do not retry it ... What required approval: rm in
> '/tmp/nonexistent-probe-x' needs approval. The path is outside the working
> directories for this session ('C:\Users\Admin\Desktop',
> 'C:/Users/Admin\Desktop'). Allowing runs the command as written."

Note the structured tail — "What required approval: … Allowing runs the command
as written." — which tells the *model* what it would need, so it can ask the
user a targeted question.

---

## 5. User confirmations

### 5.1 The prompt shape (OBSERVED-DOC)

A permission prompt shows what Claude is about to do, then the options. The
documented Bash prompt in Manual mode offers four options:

1. `Yes`
2. `Yes, and don't ask again for: npm test *`
3. `Yes, and switch to auto mode` (not on every prompt; not added to prompts
   forced by an ask rule or a hook, because auto mode still shows those)
4. `No`

Footer keys: `Esc` to cancel, `Tab` to amend.

The `Tab`-to-amend key opens a **comment field** on `Yes` or `No` (not on
WebFetch/browser prompts, and not on the "don't ask again" options):

* `Enter` submits with the comment attached (empty field = no comment)
* `Tab` closes the field without answering, keeping the text
* `Shift+Tab` on a file prompt closes the field the same way (before v2.1.235 it
  instead selected the session-approval option and discarded the comment)

Delivery differs: with `Yes`, the comment is sent to Claude **after** the
result; with `No`, the comment is sent as the **reason for the denial** and
Claude continues working. A `No` without a comment on a main-conversation
prompt stops the turn.

### 5.2 Approval persistence granularity (OBSERVED-DOC)

| Tool type | Approval required | "Yes, and don't ask again" behaviour |
|---|---|---|
| Read-only (Read, Grep) | No, within working dir + additional dirs | N/A |
| Bash | Yes, except the built-in read-only set | **Permanently per repository and command** |
| File modification (Edit/Write) | Yes | **Until session end** (not saved) |
| WebFetch | Yes, except preapproved doc domains | Permanently per repository and domain |
| WebSearch | Yes | Permanently per repository |

Where the saved rule goes: `.claude/settings.local.json` at the **root of the
git repository**, resolved through worktrees to the main checkout. It applies
to future sessions anywhere in that repository, including subdirectories and
worktrees. Outside a git repository, on Windows, or when the repo root isn't
owned by the user, Claude Code uses a different location.

**The `settings.local.json` location has a trust exception:** because the file
is yours and not the repository's, its allow rules apply *without* the
workspace-trust step — **unless the file is tracked in git or `.claude` is a
symlink**, in which case it is treated as repository-supplied and held.

### 5.3 Some prompts offer only a one-time approval (OBSERVED-DOC)

> "Claude Code offers those options only when the prompt can show you
> everything they would allow, so a rule you save from a prompt covers only
> what its option named."

This is a well-designed detail: the "don't ask again" option is withheld when
saving a rule would over-generalise.

### 5.4 `/permissions` dialog (OBSERVED-DOC)

`/permissions` (alias `/allowed-tools`) opens an interactive dialog that:
* lists all permission rules and **the settings.json file each rule comes from**
* adds/removes rules, manages working directories
* reviews **recent auto mode denials**
* has an **Auto mode** tab for viewing/editing the classifier rules
* can be opened while Claude is working; changes apply from Claude's **next
  tool call in the same turn** (since v2.1.234; before that, the command was
  queued until the turn finished)

### 5.5 Machine-readable denials (OBSERVED-CLI) — high value for a clean-room build

`claude -p "..." --output-format json` returns a top-level object whose keys
include `permission_denials` and `safety_stops`. Observed:

```json
"permission_denials": [
  {
    "tool_name": "Bash",
    "tool_use_id": "call_01a15f98733773b696981393",
    "tool_input": {
      "command": "touch .denial-probe.tmp && ls -la .denial-probe.tmp",
      "description": "Create and list .denial-probe.tmp"
    }
  }
],
"safety_stops": 0,
"is_error": false,
"stop_reason": "end_turn"
```

A denied tool call is recorded but **does not fail the turn** (`is_error:
false`, `stop_reason: "end_turn"`). This is a clean, implementable
observation channel: an independent agent can expose the same structure to
make denials auditable.

Other observed top-level JSON keys: `duration_api_ms`, `stop_reason`,
`session_id`, `total_cost_usd`, `usage`, `modelUsage`, `terminal_reason`,
`fast_mode_state`, `fast_mode_disabled_reason`, `subagent_stats`, `subtype`,
`api_error_status`, `result`, `ttft_ms`, `type`, `duration_ms`, `uuid`,
`ttft_stream_ms`, `time_to_request_ms`, `first_content_frame_ms`,
`queued_turn_count`, `result_index`.

---

## 6. Sandbox

### 6.1 What the sandbox is (OBSERVED-DOC)

> "The Bash sandbox is a boundary that the operating system enforces around the
> shell commands Claude runs on your machine."

**Platform support: macOS (Seatbelt), Linux and WSL2 (bubblewrap + socat).
Native Windows runs commands unsandboxed.** On Windows you must use WSL2.

| Access | Default | Setting |
|---|---|---|
| Writes | working dir, a per-user temp dir, added directories; protected paths stay write-denied | `sandbox.filesystem.allowWrite`, `sandbox.filesystem.denyWrite` |
| Reads | Most of the machine, **including credential files such as `~/.ssh` and `~/.aws/credentials`** | `sandbox.filesystem.denyRead`, `sandbox.credentials` |
| Network | No direct route out; traffic goes through a **local proxy** that checks each host against `network.allowedDomains` (starts empty) | `sandbox.network.allowedDomains`, `sandbox.network.deniedDomains` |
| Environment variables | Inherited from Claude Code, **including any secrets in its environment** | `sandbox.credentials`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` |

Built on the open-source `@anthropic-ai/sandbox-runtime` package.

### 6.2 What runs *outside* the sandbox (OBSERVED-DOC)

* **Built-in file and web tools** (Read, Edit, Write, WebFetch, WebSearch) —
  they follow permission rules, not the sandbox. A `denyRead` does not stop the
  Read tool; `allowedDomains` does not limit WebFetch.
* **Other processes Claude Code starts** — command hooks, local MCP servers,
  plugin monitors, LSP servers, the status-line command, `apiKeyHelper` — all
  run with full access.
* **Commands you type yourself** at the `!` shell-mode prompt — unsandboxed in
  most sessions.
* **Excluded commands** and **unsandboxed retries**.

### 6.3 The two sandbox modes (OBSERVED-DOC)

* **Auto-allow mode** — sandboxed commands are approved with no prompt. Still
  subject to: deny rules matching a `Bash` form; `rm`/`rmdir` on critical
  paths (regular flow); content-scoped ask rules like `Bash(git push *)`; a
  bare `Bash` ask rule is **skipped** for sandboxed commands (but not in plan
  mode); Monitor tool commands are **not** auto-approved.
* **Regular permissions mode** — all Bash commands go through the regular
  permission flow, even sandboxed.

**Key architectural insight:** because the OS enforces the boundary *while the
command runs*, the sandbox substitutes for the permission prompt rather than
layering on top of it. That is the mechanism by which "autonomous but safe"
becomes achievable without a remote classifier.

### 6.4 The unsandboxed-retry escape hatch (OBSERVED-DOC)

When a sandboxed command fails (e.g. a tool incompatible with the sandbox),
Claude Code names the denied host in the result; Claude may retry with a
`dangerouslyDisableSandbox` parameter. The retry runs **unsandboxed**, and
who approves it depends on the mode:

| Mode | Who approves the unsandboxed retry |
|---|---|
| `bypassPermissions` | Nobody — runs without a prompt |
| Manual, `acceptEdits` | You, in a prompt titled "Bash command (unsandboxed)" |
| `auto` | A separate classifier model evaluates the underlying command |
| `dontAsk` | Denied |
| `plan` | Plan-mode gating applies |

A matching **allow** rule also approves the retry (so `Bash(curl *)` lets it
run unsandboxed with no prompt). An **ask** rule for the parameter —
`Bash(dangerouslyDisableSandbox:true)` — forces a prompt, and **takes
precedence over a matching allow rule**.

**Strict sandbox mode** (`sandbox.allowUnsandboxedCommands: false`) disables
the retry entirely; Claude Code then ignores the `dangerouslyDisableSandbox`
parameter. The `/sandbox` panel shows this as **Strict sandbox mode**. A
`false` in user settings holds even when a project settings file sets `true`.

### 6.5 Sandbox settings and precedence (OBSERVED-DOC)

| Key | Default | Notes |
|---|---|---|
| `sandbox.enabled` | `false` | Turn on Bash sandboxing on macOS, Linux, WSL2 |
| `sandbox.allowUnsandboxedCommands` | `true` | Whether Claude may retry a blocked command outside the sandbox |
| `sandbox.failIfUnavailable` | `false` | **Refuse to start** when the sandbox can't, instead of running unsandboxed |
| `sandbox.excludedCommands` | `[]` | Commands that run outside the sandbox |
| `sandbox.filesystem.disabled` | `false` | Skip filesystem isolation, keep network isolation (v2.1.216+) |
| `sandbox.filesystem.allowWrite` / `denyWrite` / `denyRead` / `allowRead` | — | Path lists; merged across scopes |
| `sandbox.credentials` | — | Credential files/env vars with `mode: deny` or `mask` |
| `sandbox.autoAllowBashIfSandboxed` | `true` | Auto-approve sandboxed commands |

**`failIfUnavailable` is a security control worth copying:** by default, if the
sandbox can't start (missing dependency, unsupported platform), Claude Code runs
commands **unsandboxed**. Setting `failIfUnavailable: true` makes it exit at
startup instead — "Managed deployments that require sandboxing as a security
gate can use this setting."

**`sandbox.filesystem.disabled` is restricted by source:** user settings,
managed settings, and `--settings` can set it; **project settings cannot**,
"so a checked-out project can't switch filesystem isolation off". If managed
settings configure `sandbox.filesystem` at all, only managed settings can set
the key. `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` overrides everything and keeps
filesystem isolation on.

`excludedCommands` matching rules: end the pattern with ` *`; **every** command
in a chained call must match; the match is on the **text** of the call (a
`make` target that calls `docker` internally does not match); a redirect, `cd`,
or command substitution keeps the whole call sandboxed; and while the sandbox is
admin-required, project-file entries are ignored.

The docs warn about the excluded-command footgun: a broad entry such as
`docker *` covers everything that tool can do, and a pattern covering an
interpreter or a script inside the working directory lets Claude write that
file and then run it outside the sandbox.

### 6.6 Sandbox path syntax differs from permission path syntax (OBSERVED-DOC)

This is a genuine trap and worth calling out:

* **Sandbox paths** — `/tmp/build` is absolute; `~/.kube` is home-relative.
* **Permission (Read/Edit) paths** — `//path` is absolute; `/path` is
  project-relative.

Same-looking strings mean different things in the two systems.

### 6.7 Admin-required sandbox (OBSERVED-DOC)

If an admin disables the unsandboxed retry in managed settings or via
`--settings`, the sandbox becomes **admin-required**: Claude Code then ignores
repository settings that loosen the sandbox, `excludedCommands` entries
included. A `false` in user settings, `--settings`, or managed settings holds
even when a project sets `true`.

---

## 7. `--dangerously-skip-permissions` and `bypassPermissions`

### 7.1 The flags (OBSERVED-CLI, verbatim from `claude --help`)

```
--dangerously-skip-permissions        Bypass all permission checks.
                                      Recommended only for sandboxes with no
                                      internet access.

--allow-dangerously-skip-permissions  Enable bypassing all permission checks
                                      as an option, without it being enabled
                                      by default. Recommended only for
                                      sandboxes with no internet access.
```

The distinction: `--dangerously-skip-permissions` **activates** the mode now;
`--allow-dangerously-skip-permissions` only makes it **selectable** in the
`Shift+Tab` cycle.

### 7.2 The acceptance dialog (OBSERVED-DOC)

The first time you start an interactive session with this mode enabled, Claude
Code shows a **warning dialog asking you to accept responsibility for actions
taken without permission checks**:

* **Accept** → sets `skipDangerousModePermissionPrompt` to `true` in
  `~/.claude/settings.json`; later sessions skip the dialog. Remove the key or
  set it to `false` to see the dialog again.
* **Decline** → Claude Code **exits**.
* In non-interactive mode (`-p`) **no dialog is shown**.

Background sessions honour the acceptance only when it is recorded in user or
managed settings. With no acceptance recorded, `claude --bg
--permission-mode bypassPermissions` is refused. With it set only in
`.claude/settings.local.json`, the background session starts with the bypass
request ignored (bypass left out of the cycle, or Manual mode).

### 7.3 What bypassPermissions does *not* bypass (OBSERVED-DOC)

* It does **not** bypass the cross-session messaging safeguards
  (`isolatePeerMachines` prompt; inbound-message hold).
* It does **not** bypass `Remove-Item` system-path and wildcard denials.
* It does **not** bypass the "actions no mode auto-approves" list.
* It **does** bypass protected-path writes and plan-mode blocks (in
  interactive terminal sessions with bypass available).

### 7.4 Platform and policy guards on bypass (OBSERVED-DOC)

* On **Linux and macOS**, Claude Code **refuses to start** in
  `bypassPermissions` when running as **root or under `sudo`**:
  `--dangerously-skip-permissions cannot be used with root/sudo privileges for
  security reasons`. The check is skipped automatically inside a recognised
  sandbox.
* `--restricted` **refuses** `bypassPermissions` entirely.
* `permissions.disableBypassPermissionsMode: "disable"` (typically in managed
  settings) removes the mode.
* You **cannot enter** `bypassPermissions` from a session started without it
  enabled.
* Cloud sessions ignore `defaultMode: "bypassPermissions"` and `"dontAsk"`
  from settings files, so a checked-in repository cannot start a cloud session
  in bypass mode.

### 7.5 OBSERVED-CLI on this machine

* `--dangerously-skip-permissions` → init event `permissionMode:
  "bypassPermissions"`. **But** the subsequent `echo` was refused by the
  **server-side auto-mode classifier** with reason `[Safety Bypass Flag]`
  (§4.6). On this custom-gateway machine the bypass flag does not yield
  bypass behaviour end-to-end. This is an artefact of the gateway, not of
  upstream Anthropic behaviour — flagged accordingly.
* `--restricted --permission-mode bypassPermissions` → the process was
  refused before producing output (the classifier's `Safety Bypass Flag`
  rule fired on the invocation itself). The refusal is consistent with the
  documented "`--restricted` refuses bypassPermissions", but the mechanism
  observed here was the server-side classifier, so the two are not
  distinguishable from this evidence alone.

---

## 8. Workspace trust

### 8.1 The dialog (OBSERVED-DOC)

> "Trust verification: In an interactive session, Claude Code shows the
> workspace trust dialog when you start it in a folder you haven't trusted.
> Servers in a project's `.mcp.json` have their own approval prompt."

> "Note: A `-p` session shows neither prompt."

> "Note: When you start Claude Code directly in your home directory, trust
> acceptance is held for the current session only and is not written to disk,
> so the prompt reappears on each launch. **There is no setting to persist it.**
> Start Claude Code from a project subdirectory instead."

The trust dialog **lists the rules and directories the folder would grant** so
you can review them before accepting.

### 8.2 What trust gates (OBSERVED-DOC)

`permissions.allow` rules and `permissions.additionalDirectories` in a
project's `.claude/settings.json` grant capability, so they apply **only after**
you accept the dialog. `deny` and `ask` rules are **not** affected — they only
restrict.

The "what runs before you trust a folder" table:

| What the repository supplies | Trusted only a parent folder | `claude -p` / SDK, never trusted |
|---|---|---|
| Hooks in settings files, the `env` block, helper commands (`apiKeyHelper`), project skill hooks and `allowed-tools` | Used | **Used** — trust never gates a skill's `allowed-tools` |
| `permissions.allow` and `additionalDirectories` in `.claude/settings.json` | Not used until you accept | Not used; prints a `this workspace has not been trusted` warning to stderr |
| Frontmatter hooks in a project subagent, project `@skills-dir` plugin, `extraKnownMarketplaces` | Not used, no dialog offered | Not used |
| Inline `mcpServers` in repository subagent frontmatter | Not used, no dialog offered | Not used |
| Servers in `.mcp.json` | Claude Code asks you; the repository's own approvals don't count | **Connected without asking**, approved or not |
| A `headersHelper` on a server in `.mcp.json` | Not run until you accept | Not run; prints `headersHelper not run` per server to stderr |

**This asymmetry is the important design point: trust gates *grants*, not
*restrictions*, and it does not gate hooks or env blocks at all** — which
means a malicious repository's hooks run even in an untrusted `-p` session.
That is a real, documented weakness in the model, and an implementer should
decide deliberately whether to copy it.

### 8.3 How trust is keyed and stored (OBSERVED-DOC + OBSERVED-CLI)

Trust is keyed on the **git repository root** (covering the whole repo except
a nested repo such as a submodule; in a worktree, the main checkout's root).
Outside a repository, it is keyed on the starting directory. In your home
directory, it is session-only and not written to disk.

**The key is stored in the global config, not a settings file:**

> "trust it by hand: set `projects["<path>"].hasTrustDialogAccepted` to `true`
> in `~/.claude.json`, where `<path>` is the repository root, or the folder
> itself outside a repository."

**OBSERVED-CLI:** `~/.claude.json` → `projects` map, observed live on this
machine:

```
'C:\\Users\\Admin\\OneDrive\\Desktop\\VOICE ASSISTANT CURSOR' -> hasTrustDialogAccepted = False
'C:/Users/Admin'                                             -> hasTrustDialogAccepted = False
'C:/Users/Admin/OneDrive/Desktop/students-app'               -> hasTrustDialogAccepted = True
'C:/Users/Admin/OneDrive/Desktop/MULTIPLATFORM-EM-main'      -> hasTrustDialogAccepted = False
'C:/Users/Admin/Desktop/MULTIPLATFORM-EM-main-2'             -> hasTrustDialogAccepted = True
```

Each project entry also carries `allowedTools`, `mcpServers`,
`enabledMcpjsonServers`, `disabledMcpjsonServers`,
`hasClaudeMdExternalIncludesApproved`,
`hasClaudeMdExternalIncludesWarningShown`.

There is **no** `workspaceTrust` or `hasTrustDialogAccepted` entry in the
published settings-reference — it is a global-config key, not a settings key.

### 8.4 Background sessions (OBSERVED-DOC)

Before starting or restarting a background session, Claude Code checks
workspace trust. `claude --bg` from an untrusted directory shows the dialog
first. Where no dialog can appear (a script), the command exits with a
`Workspace not trusted` error instead.

### 8.5 Mitigation recipes for untrusted repositories (OBSERVED-DOC)

The docs give four concrete mitigations for running `claude -p` in a
repository you did not write:

* `--setting-sources user` (or SDK `settingSources` without project settings)
* `--bare` — reads no hooks, skills, custom commands, subagents, plugins, or
  `.mcp.json` servers from the project
* `--settings '{"disableAllHooks": true}'`
* a `disabledMcpjsonServers` entry to reject a `.mcp.json` server by name

---

## 9. Settings, precedence, and organisation-level policy

### 9.1 Where permission rules live (OBSERVED-DOC)

| Scope | File | Who it affects |
|---|---|---|
| User | `~/.claude/settings.json` | You, in every project on this machine |
| Shared project | `.claude/settings.json` | Everyone working in the folder; commit it |
| Project local | `.claude/settings.local.json` | You, in this project only; auto-added to git excludes |
| Managed | `managed-settings.json` and other managed sources | Everyone your organisation deploys to |

**Settings precedence, highest first:** managed settings → command line
(`--settings`) → project local → shared project → user.

**List keys merge rather than override** — `permissions.allow` from multiple
files is combined, so each file can add entries without removing another's.
**But the merge does not break deny-first:** "if user settings allow a
permission and project settings deny it, the deny rule blocks it. The reverse
is also true: a user-level deny blocks a project-level allow, because deny
rules from any scope are evaluated before allow rules."

### 9.2 Permission-relevant settings keys (OBSERVED-DOC)

| Key | Scope | Default | Purpose |
|---|---|---|---|
| `permissions.allow` | Any file | unset | Tool uses approved without asking |
| `permissions.ask` | Any file | unset | Tool uses that prompt even in a mode that would approve; in `dontAsk` the call is **denied** instead |
| `permissions.deny` | Any file | unset | Tool uses blocked |
| `permissions.defaultMode` | Any file | `"default"` | Starting permission mode |
| `permissions.additionalDirectories` | Any file | unset | File access outside the current directory |
| `permissions.disableBypassPermissionsMode` | Any file | `false` | Prevent entering `bypassPermissions` |
| `permissions.disableAutoMode` | Any file | unset | Remove `auto` from the mode cycle (value `"disable"`) |
| `permissions.blockReadsOutsideWorkingDirectories` | Any file | `false` | Make the file tools refuse reads outside the working directories in **every** mode |
| `sandbox.enabled` | Any file | `false` | Turn on Bash sandboxing |
| `sandbox.allowUnsandboxedCommands` | Any file | `true` | Allow (or forbid) unsandboxed retries |
| `sandbox.failIfUnavailable` | Any file | `false` | Refuse to start when the sandbox can't |
| `sandbox.excludedCommands` | Any file | `[]` | Commands that run outside the sandbox |
| `skipDangerousModePermissionPrompt` | User, local, or managed | `false` | Skip the bypassPermissions confirmation dialog |
| `allowManagedPermissionRulesOnly` | **Managed** | unset | Managed settings become the only source of permission rules; `--allowedTools` ignored; always-allow choices hidden; new rules not saved |
| `disableAutoMode` | Any file | unset | Top-level form of `permissions.disableAutoMode` |

### 9.3 Security-sensitive keys that ignore precedence (OBSERVED-DOC)

A small set of keys take the **restrictive** value from *any* scope, so a
project or user file cannot widen them even if managed settings are laxer:

| Key | Honoured value | From |
|---|---|---|
| `disableClaudeAiConnectors` | `true` | any scope |
| `enableArtifact` | `false`, and `disableArtifact: true` | any scope |
| `isolatePeerMachines` | `true` | any scope |
| `permissions.blockReadsOutsideWorkingDirectories` | `true` | any scope |
| `autoMode.classifyAllShell` | `true` | `~/.claude/settings.json` or `--settings` |
| `remoteControlAtStartup` | `false` | `.claude/settings.json` / `.claude/settings.local.json` |
| `crossSessionInbound` | a stricter value on the `accept` < `hold` < `refuse` ladder | project/local |
| `useAutoModeDuringPlan` | `false` | managed, `--settings`, user, local |
| `maxEffortLevel` | the lowest cap | any scope, including `--settings` |

This is a good, copyable pattern: **some keys are "restrict-only" by design**,
so that lowering the precedence of a file cannot be used to escalate privilege.

### 9.4 Managed settings delivery (OBSERVED-DOC)

Managed settings reach a machine via `managed-settings.json` in a system
directory, an MDM/OS policy, server-managed settings fetched from the claude.ai
admin console, or an embedding host's `managedSettings` option. Managed
settings **do not merge** with each other — later sources replace earlier
ones apart from a small per-key exception list.

`claude doctor` on this machine reported:
`Managed settings (remote): not fetched — not available with a custom
ANTHROPIC_BASE_URL` and `Organization policy: not fetched with a custom
ANTHROPIC_BASE_URL`. Managed settings are therefore **not observable** here.

### 9.5 Hooks versus rules (OBSERVED-DOC)

`PreToolUse` hooks run **before** the permission prompt, for every tool except
`EndConversation`. The precedence is deliberately deny-first:

> "PreToolUse hook decisions don't bypass permission rules. Claude Code
> evaluates deny and ask rules regardless of what a PreToolUse hook returns:
> a matching deny rule blocks the call, and a matching ask rule still prompts
> even when the hook returned `"allow"` or `"ask"`."

A hook that **exits with code 2** stops the tool call **before** permission
rules are evaluated, so a block applies even when an allow rule would permit
it. In plan mode, a hook's `"allow"` has no effect on anything that isn't
read-only (apart from `ExitPlanMode`).

---

## 10. Dependency table for this area

| Capability | Network | Anthropic account | Model provider | External service | Local dependency |
|---|---|---|---|---|---|
| Permission rules (allow/ask/deny) | No | No | No | No | None |
| Permission modes `default`/`acceptEdits`/`plan`/`dontAsk` | No | No | No | No | None |
| `bypassPermissions` | No | No | No | No | Non-root on Linux/macOS |
| Critical-path / protected-path circuits | No | No | No | No | None |
| `--restricted` | No | No | No | No | None |
| Workspace trust dialog | No | No | No | No | git (to detect tracked local settings) |
| Bash sandbox | No | No | No | No | macOS Seatbelt / `bubblewrap` + `socat`; **not native Windows** |
| Sandbox network proxy | No | No | No | No | `socat` on Linux/WSL2 |
| `auto` mode classifier (local) | **Yes** | Yes | Yes | Anthropic API | — |
| `auto` mode classifier (server-side review) | **Yes** | Yes | Yes | Anthropic API | — |
| Managed settings (remote) | **Yes** | Yes | — | claude.ai admin console | — |
| `skipDangerousModePermissionPrompt` acceptance | No | No | No | No | — |
| MCP server approval | No | No | No | MCP server itself | `git` for tracked detection |

---

## 11. Findings

Each finding is independently useful to an implementer. `OBSERVED-DOC` =
stated in a public Anthropic document fetched during this investigation.
`OBSERVED-CLI` = I ran the published CLI surface and saw it. `INFERRED` = my
conclusion, with reasoning.

---

### F-1 — The permission system is deny-first, and deny is scope-absolute

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/permissions
("Rules are evaluated in order: deny, then ask, then allow. The first match in
that order determines the outcome, and rule specificity doesn't change the
order."); https://code.claude.com/docs/en/permission-modes ("Deny rules block
in every mode, including `bypassPermissions`.")

**Evidence:** A broad deny (`Bash(aws *)`) beats a narrower allow
(`Bash(aws s3 ls)`). An allow rule cannot carve an exception out of a deny
rule. The same precedence applies between ask and allow. Across settings
scopes, a user-level deny blocks a project-level allow. Managed denies cannot
be overridden by `--allowedTools`.

**Clean-room opportunity:** implement the matcher as an ordered evaluation
over three lists (`deny`, `ask`, `allow`) with **no specificity sorting** —
first match in that fixed order wins. Scope-independent: a deny at any
precedence level wins over an allow at any other level. This is a very small
amount of code with very high security value, and it is the single most
important invariant to get right.

---

### F-2 — A bare tool-name deny *removes the tool from the model's context*; a scoped deny only blocks calls

**Status: OBSERVED-CLI** (behaviour) + **OBSERVED-DOC** (mechanism)

**Evidence — CLI:** `claude -p "List which tools you have available. Do not
call any tools." --settings '{"permissions":{"deny":["Bash"]}}'` → the model
reported that `Bash` was not in its function list, noting "the environment
mentions a Bash tool, but it isn't in my function list". Contrast with
`Bash(echo *)` (§F-3), where the tool remained present.

**Evidence — doc:** "A bare tool name like `Bash` removes the tool from
Claude's context entirely, so Claude never sees it. If you add such a rule
mid-session, Claude can't call the tool from its next tool call on." A
scoped rule like `Bash(rm *)` leaves the tool available and blocks matching
calls. Bare-name removal applies to every tool except `EndConversation`.

**Clean-room opportunity:** implement two distinct deny semantics — a
**tool-removal** deny (bare name or tool-name glob) that filters the tool
list *before* constructing the model's tool schema, and a **call-filter** deny
(scoped) that intercepts at call time. The tool-removal path is strictly
stronger because the model never learns the tool exists. Tool-name globs work
for deny/ask (`*`, `mcp__*`) but **allow** rules only accept globs after a
literal `mcp__<server>__` prefix.

---

### F-3 — Permission rules are enforced by the harness, not by the model

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Evidence — doc:** "Permission rules are enforced by Claude Code, not by the
model. Instructions in your prompt or `CLAUDE.md` shape what Claude tries to
do, but they don't change what Claude Code allows."

**Evidence — CLI:** with `--settings '{"permissions":{"deny":["Bash(echo *)"]}}'`,
the `echo` call returned "Permission to use Bash with command echo
hello-denied-test has been denied." and never executed, while `ls -la` in the
same turn ran normally. A `Read` deny rule returned "File is in a directory
that is denied by your permission settings." with no content.

**Clean-room opportunity:** the enforcement point must be the tool-dispatch
layer, not a prompt instruction. Implement the check as a middleware around
tool execution, and — critically — make the denial message *actionable to the
model* (name the tool, the exact argument, and what approval would unlock it).
The observed message "What required approval: rm in '/tmp/…' needs approval …
Allowing runs the command as written" is a good template.

---

### F-4 — Six permission modes, with `manual` as a UI alias that normalises to `default`

**Status: OBSERVED-CLI** (values and normalisation) + **OBSERVED-DOC**
(semantics)

**Evidence — CLI:** the `system`/`init` event's `permissionMode` field took
the values `dontAsk`, `acceptEdits`, `plan`, `default`, `bypassPermissions`,
`auto`; `manual` normalised to `default`; `--dangerously-skip-permissions`
produced `bypassPermissions`; `claude -p` with no flag produced `default`.

**Evidence — doc:** the six-mode table with exact "what runs without asking"
semantics; `acceptEdits` additionally auto-approves `mkdir`, `touch`, `rm`,
`rmdir`, `mv`, `cp`, `sed` (and, on Windows, `Set-Content`, `Add-Content`,
`Clear-Content`, `Remove-Item`) for paths in the working directory or
`additionalDirectories`; `dontAsk` **denies** anything that would prompt;
`bypassPermissions` skips prompts including protected-path writes.

**Clean-room opportunity:** expose the mode on the wire as a single
enumerable field with a canonical value plus aliases, so a headless consumer
can branch on it without parsing UI text. Implement the modes as a *baseline
policy object* (`{read: auto, write: ask, bash: ask, …}`) that rules then
override — that makes the six modes data, not code paths.

---

### F-5 — Protected paths and critical paths are hardcoded circuits that `permissions.allow` and hooks cannot override

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Evidence — doc:** "`permissions.allow` rules in settings files do not
pre-approve protected-path writes. The safety check runs before Claude Code
evaluates allow rules from settings." And: "Claude Code never lets a
`permissions.allow` rule or a `PreToolUse` hook that returns `"allow"` approve
an `rm` or `rmdir` command that targets a critical path, even in modes that
skip other prompts. This circuit breaker guards against model error."

**Evidence — CLI:** writing `.git/config` under `--permission-mode acceptEdits`
was refused — "Claude requested permissions to edit
C:\Users\Admin\Desktop\perm-probe\.git\config which is a sensitive file." —
and the file was byte-identical afterwards.

**Clean-room opportunity:** split the enforcement into two tiers with
different precedence. Tier 1 (user-writable): allow/ask/deny rules, hooks,
modes. Tier 2 (non-overridable): a hardcoded path list and a destructive-command
analyser. Tier 2 must be evaluated **before** Tier 1, and Tier 2 must ignore
Tier 1's "allow" verdict entirely. Implement the critical-path analyser as a
*command parser* that understands shell operators, wrappers, variable
expansion, and command substitution — the doc's list of "other targets that
count as critical paths" is effectively a test-suite specification.

---

### F-6 — The `rm` critical-path check must understand variable expansion and command substitution, not just literal paths

**Status: OBSERVED-DOC**

**Evidence:** the documented "other targets that count as critical paths"
include `rm -rf "$DIR"/*`, `rm -rf "$1"/*`, `rm -rf "$TMPDIR/mnt"`,
`D=$(pwd); rm -rf "$D"`, `rm -rf "$(pwd)"`, `rm -rf ~/$(cmd)`,
`rm -rf "\\"`, `rm -rf '\\?\Volume{GUID}\work\build'`, and `rm -rf logs/*/*`.
Nested forms are inspected: `(rm -rf ~)`, `echo "$(rm -rf ~)"`,
`bash -c 'rm -rf ~'`.

**Clean-room opportunity:** this is a concrete, testable specification for a
"destructive command analyser". Build it as a standalone module with a
table-driven test suite mirroring the documented list. Key sub-analyses:
(a) does the target resolve to a root/top-level/home/working-directory path?
(b) is the target a glob or trailing slash under a shell variable or
positional parameter? (c) is the target solely the output of a command
substitution? (d) is the target a Windows volume-by-GUID or `\\?\` spelling?
Also implement the documented **rewrite advice** — the prompt tells the model
how to make the command safe (`rm -rf "${DIR:?}"/*` or a literal path) — which
turns a dead end into a negotiation.

---

### F-7 — Denials are surfaced to the model in a structured, actionable form, and to the operator as machine-readable JSON

**Status: OBSERVED-CLI**

**Evidence:** the local denial message ends with "What required approval: rm in
'/tmp/nonexistent-probe-x' needs approval. The path is outside the working
directories for this session ('C:\Users\Admin\Desktop', 'C:/Users/Admin\Desktop').
Allowing runs the command as written." — and it also tells the model "do not
retry it" so the agent does not loop. The `dontAsk` message is
"Permission to use Bash has been denied because Claude Code is running in don't
ask mode."

**Evidence — CLI:** `claude -p ... --output-format json` returns a top-level
`permission_denials` array of `{tool_name, tool_use_id, tool_input}` and a
`safety_stops` integer. In the observed run `safety_stops` was `0` and
`is_error` was `false` — a denied tool call does not fail the turn.

**Clean-room opportunity:** implement two channels deliberately. (1) A
**model-facing** denial object with a stable schema: `{outcome: "denied",
reason_code, tool, input_summary, why, how_to_approve?, do_not_retry: bool}`.
The `do_not_retry` flag is what stops an agent from burning turns re-attempting
a denied action. (2) An **operator-facing** JSON stream field carrying every
denial with the full tool input, so denials can be audited and replayed. This
is a small amount of work with disproportionate diagnostic value.

---

### F-8 — `ask` rules and hooks both outrank "allow", but a hook *block* outranks an allow rule

**Status: OBSERVED-CLI + OBSERVED-DOC**

**Evidence — CLI:** with `--permission-mode acceptEdits` and
`{"permissions":{"ask":["Bash(echo *)"]}}`, the Bash call was blocked as
un-granted and the command did not run — the ask rule applied even though
`acceptEdits` would otherwise have auto-approved a filesystem-class command.

**Evidence — doc:** "a matching ask rule still prompts even when the hook
returned `"allow"` or `"ask"`." But: "A hook that exits with code 2 stops the
tool call before permission rules are evaluated, so the block applies even when
an allow rule would otherwise let the call proceed."

**Clean-room opportunity:** order the evaluation as
`hook-block → deny → ask → allow → default`, and make the hook's exit code
the only thing that can short-circuit to "deny" ahead of the deny tier. Keep
the hook's `"allow"` advisory-only, never a bypass.

---

### F-9 — The Bash sandbox substitutes for the permission prompt rather than layering on top of it

**Status: OBSERVED-DOC**

**Evidence:** "Because the operating system applies the limits while a command
runs, Claude Code can run sandboxed commands without asking you to approve
each one." In auto-allow mode a bare `Bash` ask rule is **skipped** for
sandboxed commands (but not in plan mode); content-scoped ask rules like
`Bash(git push *)` still prompt; `rm`/`rmdir` on critical paths still go
through the regular flow; Monitor commands are not auto-approved.

**Clean-room opportunity:** this is the most important architectural idea to
copy. A local agent cannot implement a "remote classifier" equivalent, but it
*can* implement an OS-enforced boundary, and then the safe move becomes
"auto-approve because the boundary constrains it". The check should be
"is this command running inside an enforcing sandbox?" rather than "is this
command on an allowlist?" — a strictly stronger property. Note the
platform dependency: macOS Seatbelt / Linux `bubblewrap`+`socat` / WSL2, and
**no native-Windows support**.

---

### F-10 — `sandbox.failIfUnavailable` is the control that stops a "safe" sandbox silently degrading to unsafe

**Status: OBSERVED-DOC**

**Evidence:** "By default, if the sandbox can't start because a dependency is
missing or the platform is unsupported, Claude Code runs commands without
sandboxing. To make Claude Code exit at startup instead, set
`sandbox.failIfUnavailable` to `true`. Managed deployments that require
sandboxing as a security gate can use this setting."

**Clean-room opportunity:** ship this as a default-on setting in any
independent implementation, and make the *effective* sandbox state visible in
the session's startup metadata (a `sandbox_active: true|false|unavailable`
field). A silent fallback to unsandboxed execution is the classic way a
security feature silently stops existing.

---

### F-11 — The unsandboxed retry is a distinct, separately-gated capability, not an ordinary tool call

**Status: OBSERVED-DOC**

**Evidence:** Claude may retry a sandbox-blocked command with a
`dangerouslyDisableSandbox` parameter. It runs unsandboxed, and approval
depends on the mode (bypass → no prompt; Manual/acceptEdits → a prompt
titled "Bash command (unsandboxed)"; auto → a classifier; dontAsk → denied).
A matching **allow** rule also approves the retry; an **ask** rule for the
parameter — `Bash(dangerouslyDisableSandbox:true)` — forces a prompt and
**takes precedence over a matching allow rule**.

**Clean-room opportunity:** model the retry as a distinct *permission
dimension* rather than a flag on the original command, so that a rule can
gate it independently. Concretely: make the sandbox-escape parameter a
first-class, matchable input field (like `Bash(run_in_background:true)`), so
the existing parameter-matching machinery gates it. Provide a "strict" mode
that refuses the retry entirely (`allowUnsandboxedCommands: false`) and a
"reject by default, allow only on explicit approval" mode.

---

### F-12 — The auto-mode classifier is a *rule corpus* with a consent bar, and it is inspectable as data

**Status: OBSERVED-CLI** (corpus) + **OBSERVED-DOC** (semantics)

**Evidence — CLI:** `claude auto-mode defaults` prints JSON with four keys —
`allow` (17 entries), `soft_deny` (72), `hard_deny` (1), `environment`. The
`soft_deny` entries are tagged `"<Rule Name> [named+specifics — **must name:**
<what must be named>]"`. `hard_deny` holds one rule: `Data Exfiltration`.
`environment` is a set of named slots for trusted repos/domains/buckets, all
"None configured" by default. `claude auto-mode config` prints the effective
config; `claude auto-mode reset` removes the `autoMode` section from user
settings.

**Evidence — doc:** the classifier blocks categories (curl|bash, production
deploys, `git reset --hard`, `git checkout -- .`, `git clean -fd`,
`terraform destroy`, force push, secret-store writes, DNS/TLS changes, merging
an unapproved PR, deleting files in `/tmp` by wildcard, re-pointing an API
base URL, writing to session transcripts, and more). Tool results are **stripped
from classifier requests**, "so hostile content in a file or web page can't
manipulate the classifier directly."

**Clean-room opportunity:** the *rule-corpus* idea is portable even without a
remote model: encode the policy as declarative, inspectable rule objects with
a required "named target" consent bar, in three tiers (allow / soft-deny /
hard-deny). A local implementation could evaluate the same corpus with
deterministic pattern matching plus a small local model for the semantic
tiers, and could expose it through a `defaults`/`config`/`reset` CLI triad so
operators can audit and override it. The `environment` slots are the right
mechanism for expressing "this is the trust boundary" in a way an
organisation can configure.

---

### F-13 — The classifier refuses with a specific rule name and a "stop and ask" instruction, not a generic failure

**Status: OBSERVED-CLI**

**Evidence:** the live refusal read: "Permission for this action was denied by
the Claude Code auto mode classifier. Reason: [Unverifiable Deletion Target].
… IMPORTANT: You *may* attempt to accomplish this action using other tools
that might naturally be used to accomplish this goal, e.g. using head instead
of cat. But you *should not* attempt to work around this denial in malicious
ways … Get as much of the rest of the task done as you can, then STOP and
explain to the user what you were trying to do and why you need this
permission. Let the user decide how to proceed."

**Evidence — doc:** "If the classifier blocks, Claude receives the reason. In
most sessions the reason names the rule the classifier matched, such as
`[Data Exfiltration]`, rather than giving a written explanation."

**Clean-room opportunity:** separate the *category* from the *explanation* in
the denial payload, and give the agent an explicit protocol: (a) you may
pursue the goal by a different, naturally-apt route; (b) you must not attempt
to evade the rule's intent; (c) do everything else, then stop and ask. Naming
the matched rule also makes denials auditable and lets operators tune the
corpus.

---

### F-14 — Workspace trust gates *grants* from a repository, and is stored in the global config, not a settings file

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Evidence — doc:** "`permissions.allow` rules and
`permissions.additionalDirectories` entries in a project's
`.claude/settings.json` grant capability, so Claude Code applies them only
after you accept the workspace trust dialog for that folder. The dialog lists
the rules and directories the folder would grant so you can review them first.
`deny` and `ask` rules aren't affected, since they only restrict." Trust is
keyed on the git repository root; in the home directory it is session-only and
"There is no setting to persist it."

**Evidence — CLI:** `~/.claude.json` → `projects` map, each entry carrying
`hasTrustDialogAccepted` (observed `True`/`False` for several project paths),
alongside `allowedTools`, `mcpServers`, `enabledMcpjsonServers`,
`disabledMcpjsonServers`. The published settings-reference contains **no**
`workspaceTrust` or `hasTrustDialogAccepted` key.

**Clean-room opportunity:** separate "restrictions" (always applied) from
"grants" (gated on trust) as a first-class distinction in the rule model —
this makes the trust decision meaningful without weakening the restriction
path. Store trust in a machine-global, per-path trust store rather than in the
project's own configuration, and make the trust dialog *enumerate what the
folder would grant* so acceptance is informed. Implement the trust scope
exactly: repository root, worktree → main checkout, home directory →
session-only.

---

### F-15 — The "what runs before you trust a folder" table exposes a deliberate, and dangerous, asymmetry

**Status: OBSERVED-DOC**

**Evidence:** hooks in settings files, the `env` block, helper commands such
as `apiKeyHelper`, and a project skill's `hooks` and `allowed-tools` are
**Used** in both the "trusted only a parent folder" and the "`claude -p`,
folder never trusted" columns. Meanwhile `permissions.allow` and
`additionalDirectories` are **Not used** in both. `.mcp.json` servers are
**"Connected without asking, approved or not"** in a `claude -p` run.

**Inference (reasoning stated):** the trust gate is designed to stop a
repository from *granting* the agent new capabilities (file access, MCP
servers), but it does **not** stop a repository from *executing code* via
hooks, env blocks, or helper commands. A `claude -p` run in an untrusted
repository will therefore still run that repository's hooks. This is a
documented property, not a bug I have demonstrated; I did not execute a
malicious hook to confirm it, and I make no claim that it is exploitable in
any particular way.

**Clean-room opportunity:** an independent implementation should decide
deliberately whether to reproduce this. A defensible alternative is to treat
*code execution* (hooks, helper commands, MCP stdio servers) as a grant
requiring trust, while keeping *read-only* project content freely available.
If reproducing the upstream behaviour, ship the four documented mitigations
(`--setting-sources user`, `--bare`, `--settings '{"disableAllHooks": true}'`,
`disabledMcpjsonServers`) and document the residual risk explicitly.

---

### F-16 — `bypassPermissions` is a one-way door requiring a recorded acceptance, with an explicit non-root guard

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Evidence — doc:** the first interactive launch shows a warning dialog;
accepting sets `skipDangerousModePermissionPrompt: true` in
`~/.claude/settings.json`; declining **exits** the process; `-p` shows no
dialog. On Linux/macOS: "--dangerously-skip-permissions cannot be used with
root/sudo privileges for security reasons", skipped automatically inside a
recognised sandbox. `--restricted` refuses the mode. Cloud sessions ignore
`defaultMode: "bypassPermissions"` and `"dontAsk"` from settings files, "so a
repository's checked-in settings can't start a cloud session in
bypass-permissions mode."

**Evidence — CLI:** `--dangerously-skip-permissions` produced
`permissionMode: "bypassPermissions"` in the init event, but the subsequent
command was refused by the server-side classifier with reason
`[Safety Bypass Flag]`. On this custom-gateway machine the flag does not
yield bypass behaviour end-to-end.

**Clean-room opportunity:** implement the acceptance as a **separate,
persisted, human-attested fact** (a key in a machine-global config), not as a
mode value — that is what makes the gate meaningful. Add the non-root check;
add the "cannot be enabled by project config" rule so a checked-in repository
can never grant itself bypass. Make the acceptance revocable and make
revocation effective for background sessions too.

---

### F-17 — `--restricted` is a coherent read-mostly mode that also refuses the dangerous modes

**Status: OBSERVED-CLI + OBSERVED-DOC**

**Evidence — CLI:** `claude -p "List which tools you have available." --restricted`
listed `Agent, Edit, Glob, Grep, Read, Write, Skill, ToolSearch,
ReportFindings, ScheduleWakeup, ListAgents, SendMessage` (plus deferred
`CronDelete, CronList, DesignSync, EnterWorktree, ExitWorktree,
NotebookEdit, PushNotification, SendMessage, TaskStop, WebSearch`). **No
`Bash`, no `PowerShell`, no `WebFetch`.** The model noted: "no `Bash` tool is
loaded in this session."

**Evidence — doc:** `--restricted` "removes the built-in tools that run commands
or code (Bash, PowerShell and the other code-running tools) and WebFetch unless
`--tools` names them, and ignores user, project and local settings files
(managed settings and `--settings` still apply; add `--strict-mcp-config to
skip MCP servers too). Also confines the file tools to the working directories
(`--add-dir` included), refuses `bypassPermissions`, and lets only a person or
the configured permission handler approve writes to settings, git and
tool-configuration files."

**Clean-room opportunity:** implement a "read-mostly" profile as a
**composition** — a tool allowlist ∩ a settings-source allowlist ∩ a
permission-mode restriction ∩ a working-directory fence. Composing these
orthogonally is much easier to reason about than a single `safe` boolean, and
it means the pieces can be reused (e.g. `--restricted` + sandbox for a
read-only analyst). The "refuses bypassPermissions" and "ignores project/local
settings" parts are what make it safe; neither is implied by the tool list
alone.

---

### F-18 — The `--permission-prompts none` mode turns unanswered prompts into denials, with an explicit "the action was NOT performed" contract

**Status: OBSERVED-CLI + OBSERVED-DOC**

**Evidence — CLI:** `--permission-prompts none` allowed `echo pp-none-test`
(read-only) and denied `touch .pp-none-probe.tmp`; the file was verified
absent afterwards. The denial text: "It requires approval, and this session
has no approval surface — nobody can answer a permission prompt here — so it
was denied automatically. The action was NOT performed; do not claim it
succeeded, and do not retry it … Tell the user what was blocked and why you
needed it, then continue with the parts of the task that do not require
approval."

**Evidence — doc:** `--permission-prompts` takes `"host"` (the SDK host or
`--permission-prompt-tool`) or `"none"` — "nobody: anything that would prompt
is denied automatically; the permission mode still decides everything else".

**Clean-room opportunity:** a headless/CI mode needs an explicit answerer
identity. Implement the prompt as a callback interface with a `null`/"nobody"
implementation that resolves to deny. The "the action was NOT performed; do
not claim it succeeded" phrasing is a *model-facing contract* worth copying
verbatim in spirit: it prevents hallucinated success, which is a real failure
mode for agents in unattended runs.

---

### F-19 — Some prompts deliberately withhold the "don't ask again" option so a saved rule can't over-generalise

**Status: OBSERVED-DOC**

**Evidence:** "Sometimes a permission prompt offers only a one-time approval,
with no 'don't ask again' option and no option to allow the action for the
rest of the session. Claude Code offers those options only when the prompt can
show you everything they would allow, so a rule you save from a prompt covers
only what its option named."

**Clean-room opportunity:** when generating a persistent rule from a user
approval, compute the *maximal* prefix/pattern the approval actually covers
and offer persistence only if that pattern is fully visible in the prompt.
If the pattern would be broader than what the user saw, offer only a
session-scoped approval. This is a small, high-quality safety detail that is
easy to miss and hard to retrofit.

---

### F-20 — Restrictions and grants are treated differently across the settings-precedence stack, and a small set of keys are restrict-only by design

**Status: OBSERVED-DOC**

**Evidence:** list keys merge across scopes, but "if user settings allow a
permission and project settings deny it, the deny rule blocks it. The reverse
is also true." A documented set of keys honours the **restrictive** value from
*any* scope regardless of the precedence stack:
`disableClaudeAiConnectors` (`true`), `enableArtifact` (`false`),
`isolatePeerMachines` (`true`),
`permissions.blockReadsOutsideWorkingDirectories` (`true`),
`autoMode.classifyAllShell` (`true` from user/`--settings`),
`remoteControlAtStartup` (`false` from project/local),
`crossSessionInbound` (stricter of `accept` < `hold` < `refuse`),
`useAutoModeDuringPlan` (`false`), `maxEffortLevel` (lowest cap).

**Clean-room opportunity:** mark each configuration key with a *monotonicity*
(only-more-restrictive-wins, or normal-precedence). Enforce monotonicity in
the merge function rather than in ad-hoc checks at use sites. This prevents
the classic escalation bug where a lower-precedence file widens a setting the
operator believed was locked.

---

### F-21 — Permission rules reach the *model* as a tool-set change and to the *operator* as a per-file rule inventory

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Evidence — doc:** `/permissions` "lists all permission rules and the
`settings.json` file each rule comes from." It is openable while Claude is
working and changes apply "starting with Claude's next tool call in the same
turn" (since v2.1.234).

**Evidence — CLI:** a bare `Bash` deny removed the tool from the model's
function list (§F-2), confirming that the rule set is projected into the
model's tool schema.

**Clean-room opportunity:** implement `/permissions` (or an equivalent) as a
**rule inventory** showing, per rule, its source file and scope, plus a
working-directory manager, plus a denial log. Show the *effective* merged
rule set, not just the per-file lists — an operator debugging "why did I get
prompted" needs the merged view with the winning rule highlighted.

---

### F-22 — Two independent "no approval surface" mechanisms exist, and they behave differently

**Status: OBSERVED-CLI + OBSERVED-DOC**

**Evidence — CLI:** `--permission-prompts none` produced a *local* denial with
a structured reason, and the run still produced a JSON document with
`permission_denials` populated. By contrast the **auto-mode classifier**
refusal printed a notice to stderr and the process **exited without producing
the JSON document at all** — a *server-side* refusal, categorically different
from the local permission layer.

**Evidence — doc:** the `dontAsk` mode "auto-denies every tool call that would
otherwise prompt you"; the mode is never in the `Shift+Tab` cycle and must be
set with `--permission-mode dontAsk`. In `claude -p`/SDK runs with no mode set
(v2.1.302+), calls needing approval "are denied unless you approve them with
an allow rule, hook, `canUseTool` callback, or `--permission-prompt-tool`."

**Clean-room opportunity:** distinguish **local denial** (the harness said no;
the session continues and the denial is recorded) from **session abort**
(the run ends). Expose the distinction in the output schema. Implement a
first-class `canUseTool`-style callback so a host application can approve
calls programmatically, with `dontAsk` as the null-object implementation.

---

## 12. Unknowns

| # | Unknown | Why it could not be established |
|---|---|---|
| U-1 | The exact `permissionMode` a session starts in on a first-party Anthropic account | This machine uses a custom `ANTHROPIC_BASE_URL`; `claude doctor` reports "Not connected to the Anthropic API" and "not signed in to claude.ai". The built-in `auto` default for interactive sessions is documented but not observable here. |
| U-2 | Whether the auto-mode classifier runs server-side or as local model calls against a first-party account | On this machine the classifier is enforced by the custom gateway. The docs describe both a client-side classifier path and a server-side review path, with version-gated rollout. Not distinguishable here. |
| U-3 | The classifier's exact decision boundary, prompt, or model on a first-party account | The rule corpus is observable (`claude auto-mode defaults`), but the classifier's own prompt and the tie-breaking between the 72 `soft_deny` rules is not public. I did not attempt to probe it. |
| U-4 | The interactive permission-prompt UI in full | No PTY was available (`script` is not installed in this Git Bash environment), so the TUI prompt could not be captured. The prompt's option set and key bindings are documented and the images are in the docs, but the rendered prompt was not observed directly. |
| U-5 | The workspace trust dialog's exact rendering and copy | Interactive-only; not reachable in a non-TTY `-p` run. The doc describes what it lists, not its exact text. |
| U-6 | Managed settings behaviour | `claude doctor`: "Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL" and "Organization policy: not fetched with a custom ANTHROPIC_BASE_URL". No managed-settings source was deployed here. |
| U-7 | Whether `--dangerously-skip-permissions` truly bypasses upstream | The init event showed `permissionMode: "bypassPermissions"`, but the classifier refused the call with `[Safety Bypass Flag]` on this gateway. The upstream behaviour is documented; the end-to-end behaviour here is not. |
| U-8 | The `mod`-based `tool.check` approval path | `claude plugin list` → "No plugins installed."; the mods feature could not be exercised. The documented precedence (a mod's approval is overridden by managed settings or a Team/Enterprise login) is doc-only here. |
| U-9 | Sandbox behaviour | Native Windows: "On native Windows, Claude Code runs commands unsandboxed." `bubblewrap`/`socat` are Linux/WSL2 dependencies; the WSL2 path was not exercised. All sandbox findings are DOC. |
| U-10 | The `--permission-prompt-tool` flag's runtime behaviour | The flag is referenced in `claude --help` and in the docs, but no `--permission-prompt-tool` invocation was made; the SDK's `canUseTool` callback was likewise not exercised. |
| U-11 | The exact classifier model and whether `CLAUDE_CODE_AUTO_MODE_MODEL` took effect | The debug-log walkthrough (`classifier_request_started`) requires a first-party account and a debug file. Not observable here. |
| U-12 | Whether the local permission layer and the server-side classifier are the *same* implementation upstream | On this machine they are visibly different systems (local denial → JSON with `permission_denials`; classifier refusal → process exit with no JSON). Whether upstream separates them the same way is INFERRED from the docs' description of a client-side fallback. |

---

## 13. Clean-room implementation opportunity — recommended scope

An independently written agent can reproduce the **entirely user-visible
function** of this area without copying any Anthropic implementation. The
recommended scope, in priority order:

### Tier 1 — must have (the invariants that carry the safety)

1. **Ordered rule evaluation** with three tiers (`deny` → `ask` → `allow`) and
   **no specificity sorting**. Scope-independent: a deny anywhere beats an
   allow anywhere. *(F-1)*
2. **Enforcement at the tool-dispatch layer**, never in the prompt. *(F-3)*
3. **Two distinct deny semantics**: tool-removal (bare name / tool-name glob,
   filtered from the tool schema before the model sees it) vs call-filter
   (scoped). *(F-2)*
4. **A non-overridable hardcoded safety tier** evaluated *before* user rules:
   a protected-path list and a destructive-command analyser, neither of which
   an allow rule or a hook "allow" can waive. *(F-5, F-6)*
5. **A destructive-command analyser** that parses shell operators, strips the
   documented wrapper list, resolves variable/positional/command-substitution
   hazards, and handles Windows spellings (`8.3` short names, `\\?\`,
   `\\localhost\C$`, volume GUIDs). Ship it with a table-driven test suite
   built from the documented critical-path list. *(F-6)*
6. **Machine-readable denial reporting** on the output stream
   (`permission_denials`-style array) plus a model-facing denial object with
   a `do_not_retry` flag. *(F-7)*
7. **Six permission modes as data**, with a canonical value plus aliases, and
   a wire-visible `permissionMode` field. *(F-4)*

### Tier 2 — high value

8. **An OS-enforced sandbox** (Seatbelt / `bubblewrap`+`socat`) with
   `failIfUnavailable` defaulting to **true**, plus a visible
   `sandbox_active` state. Auto-approve *because* the boundary constrains the
   command, not because the command is on a list. *(F-9, F-10)*
9. **A separately-gated sandbox-escape dimension** (the retry), matchable as
   its own parameter, plus a strict mode that refuses it. *(F-11)*
10. **Workspace trust** that gates *grants* (file access, additional
    directories, MCP servers) but not *restrictions*, keyed on the repository
    root, stored machine-globally, session-only in the home directory, with a
    dialog that enumerates what the folder would grant. *(F-14, F-15)*
11. **A permission prompt with the documented option set and comment
    attachment** (`Tab` to amend; `Enter` submits; comment delivered *after*
    the result on approval, *as the denial reason* on refusal). *(F-5 §5.1)*
12. **Approval persistence with per-tool granularity** — Bash rules permanent
    per repository, file edits session-only — and the rule-scope guard that
    withholds "don't ask again" when the pattern would exceed what the user
    saw. *(F-19)*
13. **A read-mostly `--restricted` profile** composed from a tool allowlist, a
    settings-source allowlist, a permission-mode restriction, and a
    working-directory fence — and that refuses the dangerous modes. *(F-17)*
14. **A headless "no approval surface" mode** whose prompt callback resolves to
    deny, with the "the action was NOT performed" contract. *(F-18)*
15. **A bypass mode requiring a persisted, human-attested acceptance** in a
    machine-global config, with a non-root guard and a "cannot be enabled by
    project config" rule. *(F-16)*

### Tier 3 — valuable if a model provider is available

16. **A local or remote safety reviewer** driven by an inspectable,
    editable rule corpus with three tiers (`allow` / `soft_deny` / `hard_deny`),
    a required "named target" consent bar, and a `defaults` / `config` / `reset`
    CLI triad for operator auditability. Strip tool *results* from the
    reviewer's input so fetched content cannot manipulate it. *(F-12, F-13)*
17. **Restrict-only configuration keys** — mark keys with a monotonicity
    ("only more restrictive wins") and enforce it in the merge function.
    *(F-20)*
18. **An operator-facing rule inventory** showing each rule's source file and
    scope, the merged effective set, working-directory management, and a
    denial log. *(F-21)*

### Explicitly out of scope for a clean-room build

* Reproducing Anthropic's specific rule text (the 72 `soft_deny` names, the
  protected-path file lists, the critical-path heuristics verbatim). These are
  *data*, and an independent implementation should write its own from first
  principles, borrowing only the **structure** (tiers, consent bars, source
  attribution).
* Reproducing the *server-side* classifier rollout, feature-flag gating, or
  the exact version thresholds (`v2.1.2xx`). Those are Anthropic-internal
  release engineering, not user-visible function.
* Any attempt to interoperate with Anthropic's private APIs, or to observe
  their internal prompts — out of bounds and not required for functional
  equivalence.

### Estimated effort

Tier 1 is roughly 1,500–2,500 lines of well-specified, testable code: a
rule matcher, a command analyser, a dispatch middleware, and an output
schema. Tier 2 is another 1,000–1,500 lines, with the sandbox being the
largest single item and the most platform-dependent. Tier 3 depends entirely
on whether a second model is available for review; the *rule-corpus* half
(inspectable, editable, tiered) is implementable without one and is worth
doing regardless.

---

## 14. Confirmed capabilities (OBSERVED only)

Everything in this list was directly observed on this machine or directly
read in a public Anthropic document fetched during this investigation. Nothing
here rests on inference.

| # | Capability | How confirmed |
|---|---|---|
| C-1 | Six permission modes exist, with `manual` as an alias that normalises to `default` | OBSERVED-CLI — `permissionMode` in the init event across all six flag values |
| C-2 | `--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` are distinct flags with different activation semantics | OBSERVED-CLI — `claude --help` text + init-event `permissionMode` |
| C-3 | Rule evaluation order is deny → ask → allow, first match wins, specificity does not reorder | OBSERVED-DOC (permissions doc, line 58) + OBSERVED-CLI (ask rule beat `acceptEdits`) |
| C-4 | A bare tool-name deny removes the tool from the model's function list | OBSERVED-CLI — the model reported `Bash` absent from its function list |
| C-5 | A scoped deny blocks matching calls while leaving other tools working | OBSERVED-CLI — `Bash(echo *)` denied, `ls -la` ran in the same turn |
| C-6 | A scoped `Read` deny blocks the read and returns no content | OBSERVED-CLI — "File is in a directory that is denied by your permission settings." |
| C-7 | `permissions.allow` and `PreToolUse` "allow" cannot approve a protected-path write | OBSERVED-CLI — `.git/config` write refused in `acceptEdits`, file byte-identical afterwards |
| C-8 | `rm`/`rmdir` targeting a critical path is never approved by an allow rule or hook | OBSERVED-DOC (permission-modes doc, "circuit breaker") |
| C-9 | Critical-path detection covers variable expansion, positional params, and command substitution | OBSERVED-DOC — the documented "other targets that count as critical paths" table |
| C-10 | PowerShell `Remove-Item` and `cmd` `rd`/`rmdir`/`del`/`erase` have their own checks, denying system paths and wildcards in every mode | OBSERVED-DOC (permission-modes doc, "Remove-Item in PowerShell") |
| C-11 | Each destructive safeguard has a dedicated `CLAUDE_CODE_DISABLE_*` env kill switch | OBSERVED-DOC — five named variables |
| C-12 | The critical-path prompt has a two-minute countdown in `auto`/`bypassPermissions`, and three unanswered countdowns stop further prompts for the session | OBSERVED-DOC (permission-modes doc, "Time limits and denials") |
| C-13 | The Bash sandbox is an OS-enforced boundary; sandboxed commands are auto-approved *instead of* prompting | OBSERVED-DOC (sandboxing doc) |
| C-14 | The sandbox is unavailable on native Windows; macOS/Linux/WSL2 only | OBSERVED-DOC (sandboxing doc) |
| C-15 | `sandbox.failIfUnavailable` makes the tool exit rather than silently run unsandboxed | OBSERVED-DOC (sandboxing doc) |
| C-16 | The unsandboxed retry is a separate, mode-dependent approval decision matchable as a tool parameter | OBSERVED-DOC (sandboxing doc) |
| C-17 | The auto-mode classifier's rule corpus is inspectable as data: 17 allow / 72 soft_deny / 1 hard_deny / an environment slot list | OBSERVED-CLI — `claude auto-mode defaults` |
| C-18 | The classifier refusal names the matched rule and issues an explicit "stop and ask" protocol | OBSERVED-CLI — two live refusals, `[Unverifiable Deletion Target]`, `[Safety Bypass Flag]` |
| C-19 | Workspace trust is keyed per path in the global `~/.claude.json` as `hasTrustDialogAccepted` | OBSERVED-CLI — live config values |
| C-20 | Trust gates *grants* (allow rules, additional directories, `.mcp.json` servers) but not *restrictions*, and does not gate hooks or env blocks | OBSERVED-DOC — the "what runs before you trust a folder" table |
| C-21 | `dontAsk` denies everything that would prompt, with a specific denial message | OBSERVED-CLI — four separate mutating attempts refused |
| C-22 | `--permission-prompts none` denies unanswered prompts and states the action was NOT performed | OBSERVED-CLI — denial text + file verified absent |
| C-23 | Denials are machine-readable in `--output-format json` as `permission_denials` (with `tool_name`, `tool_use_id`, `tool_input`) and a `safety_stops` count | OBSERVED-CLI — 4 denials captured in one run |
| C-24 | A local denial does not fail the turn (`is_error: false`, `stop_reason: "end_turn"`) | OBSERVED-CLI — same run |
| C-25 | `--restricted` removes Bash, PowerShell and WebFetch and refuses `bypassPermissions` | OBSERVED-CLI (tool list) + OBSERVED-DOC (refusal) |
| C-26 | Rules are enforced by the harness, not the model | OBSERVED-DOC + OBSERVED-CLI (denied command never executed) |
| C-27 | The prompt supports a comment attachment via `Tab`, delivered as the denial reason on refusal | OBSERVED-DOC (permission-modes doc) |
| C-28 | "Don't ask again" is withheld from prompts whose rule would over-generalise | OBSERVED-DOC (permission-modes doc) |
| C-29 | Approval persistence differs per tool: Bash rules permanent per repo, file edits session-only | OBSERVED-DOC (permission-modes doc) |
| C-30 | `bypassPermissions` requires a recorded acceptance (`skipDangerousModePermissionPrompt`) and is refused under root/sudo on Linux/macOS | OBSERVED-DOC (permission-modes doc) |

---

## 15. Evidence index

| Artifact | Path |
|---|---|
| This report | `agent-reference-shots/area8-permissions/AREA-8-REPORT.md` |
| Black-box CLI observations (all OBSERVED-CLI) | `agent-reference-shots/area8-permissions/cli-observations.md` |
| Sanitized `--output-format json` sample showing the `permission_denials` / `safety_stops` surface | `agent-reference-shots/area8-permissions/sample-permission-denials.json` |
| Fetched doc: permission modes | `agent-reference-shots/area8-permissions/doc-permission-modes.md` |
| Fetched doc: permissions | `agent-reference-shots/area8-permissions/doc-permissions.md` |
| Fetched doc: sandboxing | `agent-reference-shots/area8-permissions/doc-sandboxing.md` |
| Shared protocol notes (session bootstrap, tool set) | `agent-reference-shots/PROTOCOL-NOTES.md` |
| Compliance boundary | `agent-reference-shots/TERMS-NOTES.md` |

Public documentation fetched during this investigation:
`https://code.claude.com/docs/en/permission-modes`,
`https://code.claude.com/docs/en/permissions`,
`https://code.claude.com/docs/en/sandboxing`,
`https://code.claude.com/docs/en/settings`,
`https://code.claude.com/docs/en/settings-reference`,
`https://code.claude.com/docs/en/security`,
`https://code.claude.com/docs/en/env-vars`,
`https://code.claude.com/docs/en/commands`,
`https://code.claude.com/docs/en/iam` (returned the authentication page —
the requested permission content was not on that URL; the permission docs
above are the correct source).

---

## 16. Bottom line for this area

**Confirmed:** Claude Code's safety model is *not* a single permission
mechanism. It is a five-layer stack — user-writable rules, mode baselines,
non-overridable hardcoded path/command circuits, an OS-enforced sandbox, and a
remote classifier — and the layers interact in a specific, documented way
(deny-first across all scopes; the sandbox *replaces* the prompt rather than
adding to it; the classifier is the only non-local layer). Every one of those
interactions is user-visible and therefore reproducible without access to any
Anthropic implementation.

**Unknown:** the classifier's internal decision boundary and prompt; the
first-party session's default mode; managed-settings behaviour; the sandbox's
runtime behaviour on a supported platform; the rendered interactive prompt and
trust dialog.

**Recommended scope for an independent implementation:** the Tier 1 list in
§13 — ordered deny→ask→allow evaluation, harness-level enforcement,
tool-removal vs call-filter denies, a non-overridable protected-path and
destructive-command tier, machine-readable denial reporting, and modes-as-data.
That is roughly 1,500–2,500 lines of testable code and it captures the safety
properties that matter. The OS sandbox (Tier 2) is the highest-value
differentiator if the target platforms allow it, and the inspectable,
tiered rule corpus (Tier 3) is portable even without a second model available
to review actions.


================================================================================
# Area 5 — Terminal command proposal, approval, execution, and reporting
================================================================================

**Product:** Claude Code 2.1.306 (native Windows build, `win32-x64`)
**Host:** Windows 11, Git Bash present, `pwsh.exe` present
**Method:** public docs at `code.claude.com/docs/en/*` plus black-box runs of the
published CLI only. No decompilation, no bundle extraction, no source-map
dumping (see `agent-reference-shots/TERMS-NOTES.md`). REA's decompilation and
binary-inspection facilities were deliberately **not used** — they would breach
the product terms and destroy the clean-room property of this reference.
**Model provider on this host:** a custom `ANTHROPIC_BASE_URL` gateway serving a
non-Anthropic model. `claude doctor` reports "Not connected to the Anthropic API
(api.anthropic.com)", so subscription-gated Anthropic behaviour is INFERRED
from docs, not observed.

**Status tags.** `OBSERVED-DOC` = stated in a public Anthropic document (URL
given). `OBSERVED-CLI` = I ran the published CLI and saw it (exact command and
output given). `INFERRED` = my conclusion from evidence, with reasoning stated.
`UNKNOWN` = the available evidence cannot establish it.

**Canonical full version of this section**, with all 24 findings, the complete
capability table, dependencies, limitations, unresolved questions and the
clean-room plan, is
`agent-reference-shots/area5-bash-permissions/area5-observations.md`. The text
below is the section as it appears in this consolidated file.

## 5.A Executive summary

The shell-execution subsystem is the part of Claude Code that most directly
confronts the user with risk, and the reference product's design is
characterised by four decisions that are worth copying wholesale.

**First, the harness is the security boundary, not the model.** The Bash tool's
input schema has exactly four model-supplied fields plus one host-side flag, and
the `description` field — the human-readable label the model writes for the
user — is display metadata only. Nothing the model writes widens its own
permissions. The permission system is a deterministic matcher over the
`command` field, evaluated deny → ask → allow with first-match-wins and
*specificity deliberately ignored*, so a broad deny always beats a narrow
allow. This is the opposite of the intuitive "most specific rule wins" design
and it is materially stronger.

**Second, two guard rails sit above the rules and above hooks.** Writes to
protected paths (`.git`, `.claude`, `.npmrc`, `.bashrc`, …) are never
auto-approved by a `permissions.allow` rule, and an `rm`/`rmdir` targeting a
critical path (filesystem root, home directory, drive roots, the working
directory and its parents, several variable-expansion cases) is blocked by a
circuit breaker that neither an allow rule nor a PreToolUse hook returning
`"allow"` can waive. The documented rationale is that these exist "against model
error" — the model may be authorised to run `rm` and still generate a
catastrophic target.

**Third, the reporting contract is machine-readable and mostly structured.**
A successful command returns `{stdout, stderr, interrupted, isImage,
noOutputExpected}`; a failure returns in-band text `"Exit code 7\n…"` with
`is_error:true`. Every result additionally carries a `tool_result_meta` array
with a structured permission decision (`decision` / `source` / `reason_type` /
`non_execution_kind`), and the final result envelope aggregates
`permission_denials[]` with the *full tool input* retained. This is what makes
an agent's permission behaviour auditable after the fact.

**Fourth, long-running work is a first-class state machine, not a timeout
error.** A foreground command that exceeds its timeout is *promoted to the
background* rather than killed, and returns a task id plus an output file path;
background tasks emit typed lifecycle events (`task_started`, `task_updated`,
`task_notification`) on the same stream as the model messages, and completion
re-invokes the model with a summary that inlines the exit code.

The one significant wart found first-hand: **stdout and stderr are merged into a
single pipe**, and the `stderr` field in the success payload is always empty. A
command writing only to fd 2 has its output reported in `stdout`. A
clean-room implementation should keep the streams separate *and* additionally
emit an interleaved transcript, rather than choosing one.

## 5.B Detailed findings

## F1 — The Bash tool's input contract is four named fields plus one sandbox flag

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

Observed on the wire in a headless run. The assistant emits a `tool_use` block whose `input`
carries exactly:

```json
{"command":"sh -c 'echo out-line; echo err-line 1>&2; exit 0'",
 "description":"Print a line to stdout and stderr"}
```

and the harness keeps a parallel `wire_tool_inputs` map (the audit copy of what was actually sent):

```json
"wire_tool_inputs":{"call_function_gtxi815nvr8u_1":{
  "command":"sh -c 'echo out-line; echo err-line 1>&2; exit 0'",
  "description":"Print a line to stdout and stderr"}}
```

The PreToolUse hook input schema (public docs) shows the full set the harness can populate:

```json
"tool_name": "Bash",
"tool_input": {
  "command": "npm test",
  "description": "Run test suite",
  "timeout": 120000,
  "run_in_background": false
}
```

and the sandboxing docs add a fifth, `dangerouslyDisableSandbox` (boolean), which is set on the
retry that runs a command outside the sandbox.

Field semantics:
- `command` — the shell text. Required.
- `description` — an **agent-authored** human-readable label, shown in the permission prompt
  under the command. Not a claim of safety; it is the agent's own words.
- `timeout` — milliseconds. The model chooses it; the ceiling is enforced by the harness.
- `run_in_background` — boolean.
- `dangerouslyDisableSandbox` — boolean, only meaningful on the sandbox-retry path.

**INFERRED (reasoning):** the harness, not the model, is the security boundary. `description` is
model-generated text, so it must never be treated as an authorisation signal — the `command` field
is the only thing the permission matcher inspects. This is consistent with the docs' statement
that "Permission rules are enforced by Claude Code, not by the model."

**Clean-room opportunity:** define your own shell tool with an explicit, small input schema
(`command`, `description`, `timeout`, `run_in_background`) and treat `description` as pure
display metadata. Do not let the model supply any field that widens its own permissions —
keep sandbox/permission flags on the host side of the boundary.

**Source:** https://code.claude.com/docs/en/hooks ; https://code.claude.com/docs/en/sandboxing

---

## F2 — A successful command returns a typed payload; a failure returns in-band text

**Status:** `OBSERVED-CLI`

Success — `tool_use_result` is a structured object:

```json
{"stdout":"out-line\nerr-line","stderr":"","interrupted":false,
 "isImage":false,"noOutputExpected":false}
```

and the `tool_result` content block carries the plain merged text `"out-line\nerr-line"` with
`is_error:false`.

**Correction to an obvious assumption — the `stderr` field is always empty.** A second run writing
only to stderr confirmed it:

```json
{"stdout":"ONLY-ERR","stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false}
```

The command wrote to fd 2 exclusively, yet the payload reports it in **`stdout`** and leaves
`stderr` empty. So the harness runs the child with **stdout and stderr merged into a single
stream** (one pipe), and reports the merged text in `stdout`. The `stderr` key exists in the
schema but is not populated on this path.

Failure — the payload collapses to a **string** and the exit status is embedded in the text:

```json
{"content":"Exit code 7\nout-line\nerr-line","is_error":true}
```

with `tool_use_result` = `"Error: Exit code 7\nout-line\nerr-line"`.

Verified by running (exit 7, one line on stdout, one on stderr):

```
claude -p "Run exactly this shell command and nothing else:
  sh -c 'echo out-line; echo err-line 1>&2; exit 7'"
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools "Bash(sh *)"
```

Artifacts: `stream-success-payload.jsonl`, `stream-stderr-only.jsonl`, `stream-exit-nonzero.jsonl`.

**Key implementation detail:** stdout and stderr are **interleaved into one stream** in both the
success and failure paths — the harness does not keep them separate anywhere. The agent in the
exit-7 run correctly recovered all three facts (stdout line, stderr line, exit code 7) from the
merged blob.

**INFERRED (reasoning):** merging stdout/stderr is lossy but deliberate — it preserves interleaving
order, which is what matters when diagnosing a build or test failure, and it avoids a deadlock
when a child writes a lot to both streams. The cost is that a model cannot reliably tell "this line
is an error" from "this line is output" — it must infer from content. A clean-room implementation
should decide deliberately: keep `stdout`, `stderr`, and `exit_code` as separate fields *and*
additionally emit an interleaved transcript, so the model gets both order and attribution.

**Clean-room opportunity:** return `{stdout, stderr, exit_code, interrupted, duration_ms}` always
— never a pre-rendered string — and let the renderer compose the human-facing text. That is
strictly more useful to a model than a merged blob and is trivially implementable. If you merge
for ordering, merge *in addition to* separate streams, not *instead of* them.

**Source:** https://code.claude.com/docs/en/tools-reference

---

## F3 — Exit code 1 is only a failure for some commands

**Status:** `OBSERVED-DOC`

> "A command that exits 1 counts as a valid result for the Bash tool only when Claude Code
> recognizes exit code 1 as a benign outcome for that command: `grep`, `rg`, `egrep`, `fgrep`,
> `find`, `diff`, `test`, and `[`, plus `git diff` and `git grep`. Every other command that exits 1
> counts as a failure, even when exit 1 is a benign informational outcome: no matches for
> `pgrep` and `jq -e`, files that differ for `cmp`."

So `grep -q foo file` returning 1 (no match) is a **successful** tool result, while `pgrep foo`
returning 1 is a **failure**. The list is a fixed, built-in table of benign-exit-1 commands.

**Clean-room opportunity:** keep a small, explicit, user-visible table of "exit 1 is benign"
command patterns (or better, invert it — a table of "exit 1 is fatal"), and surface it in the
permission dialog so the user can see why a command was treated as a failure.

**Source:** https://code.claude.com/docs/en/tools-reference#output-limits

---

## F4 — Output truncation is a three-tier ladder, and the overflow notice is a parseable envelope

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

Docs give the ladder:

| Result | What the model gets |
| :- | :- |
| Valid | Inline up to roughly **30,000** characters by default; past that, the path of a file saved to the session directory and truncated past 64 MiB, plus a preview of up to the first **2,000** characters |
| Failure | Inline up to roughly **10,000** characters; past that, a **head-and-tail excerpt** of that size cut from the read-back window, with **no file path** |

Observed end-to-end. A command emitting 2000 padded lines (~196 KB) produced this exact tool
result:

```
<persisted-output>
Output too large (196.2KB). Full output saved to: C:\Users\Admin\.claude\projects\<sanitized-cwd>\<session-id>\tool-results\bmmw375ck.txt

Preview (first 2KB):
LINEPAD-XXX...-1
LINEPAD-XXX...-2
...
</persisted-output>
```

Points worth copying:
- The overflow notice is wrapped in explicit `<persisted-output>` / `</persisted-output>` tags, so
  the model can recognise "there is more, here is where" without prose parsing.
- The overflow file lives **inside the session directory** (`~/.claude/projects/<sanitized-cwd>/
  <session-id>/tool-results/<id>.txt`), not in a temp dir, so it survives alongside the transcript
  and is addressable by the `Read` tool.
- The size is reported in KB with one decimal (`196.2KB`).
- There is a hard **5 GB** kill: "Claude Code streams a command's output to a working file as the
  command runs; a command whose output passes 5 GB is killed."

Related knobs (`OBSERVED-DOC`):
- `BASH_MAX_OUTPUT_LENGTH` — read-back window, default `30000`, hard ceiling `150000`.
- `bashOutputMaxChars` (settings) — sizes the *inline* ceiling and the read-back window together,
  up to `128000`, and then makes Claude Code **ignore** `BASH_MAX_OUTPUT_LENGTH`. Requires v2.1.261+.

**INFERRED (reasoning):** the overflow file plus a preview is strictly better than a hard cut
because the model can then `Read` or `Grep` the file — the truncation notice is an instruction to
the model to re-read with a targeted tool, not a dead end. The failure path's head-and-tail
excerpt has no file pointer, which is a real asymmetry: a failing command's overflow output is
unrecoverable except by re-running it.

**Clean-room opportunity:** always write stdout+stderr to a per-task file in a session-scoped
directory and return `{inline_preview, output_file_path, total_bytes, truncated}`. Return the file
path even on failure — that is the single highest-value improvement over the observed behaviour.

**Source:** https://code.claude.com/docs/en/tools-reference#output-limits ;
https://code.claude.com/docs/en/settings-reference ; https://code.claude.com/docs/en/env-vars

---

## F5 — Foreground timeout auto-promotes the command to the background

**Status:** `OBSERVED-DOC`

Rather than killing a command at its timeout, the harness **moves it to the background** and tells
the model so. The exact result text is documented:

> `Command did not complete within its 120s timeout and was moved to the background`

— "with the seconds matching the timeout that applied, followed by the task ID and the path of the
file the output is being written to."

Two further exact strings, worth copying verbatim because they prevent the model from acting on a
state change that did not happen:

> `Session cwd remains <dir>; directory changes made by the backgrounded command do not apply to subsequent commands.`

Exceptions and controls:
- A command starting with `sleep` is **stopped** at its timeout instead of being backgrounded.
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, or `--bare`, disables auto-backgrounding; the command
  then simply stops.
- Timeouts: `BASH_DEFAULT_TIMEOUT_MS` = `120000` (2 min) default; `BASH_MAX_TIMEOUT_MS` =
  `600000` (10 min) default ceiling; "the effective ceiling is the larger of the two".

**Clean-room opportunity:** implement the timeout as a *state transition* (foreground → background)
rather than a kill, and emit a structured event (`{state:"backgrounded", reason:"timeout",
task_id, output_path, timeout_ms}`) instead of a prose sentence, so a client can render it.

**Source:** https://code.claude.com/docs/en/tools-reference#foreground-commands-that-move-to-the-background ;
https://code.claude.com/docs/en/env-vars

---

## F6 — Background execution has a fully specified three-party contract

**Status:** `OBSERVED-CLI`

Running a background command with `run_in_background: true` produced, in order:

**a. The tool call** —
```json
{"type":"assistant","message":{"content":[{"type":"tool_use",
  "id":"call_function_8qg29t9um0yl_1","caller":{"type":"direct"},"name":"Bash",
  "input":{"command":"sh -c 'for i in 1 2 3; do echo tick-$i; sleep 1; done'",
           "description":"Run loop echoing tick-1 through tick-3","run_in_background":true}}]}}
```

**b. A `background_tasks_changed` system event** listing the task —
```json
{"type":"system","subtype":"background_tasks_changed",
 "tasks":[{"task_id":"bzzuzyibe","run_id":"0mviemewu-87c1467f",
           "task_type":"local_bash","description":"Run loop echoing tick-1 through tick-3"}]}
```

**c. A `task_started` event** carrying `is_backgrounded:true`, `task_type:"local_bash"`, and the
originating `tool_use_id`:
```json
{"type":"system","subtype":"task_started","task_id":"bzzuzyibe",
 "run_id":"0mviemewu-87c1467f","tool_use_id":"call_function_8qg29t9um0yl_1",
 "description":"Run loop echoing tick-1 through tick-3","is_backgrounded":true,
 "task_type":"local_bash","uuid":"1b41ada1-097a-4fb1-9261-9fdda776cf50",
 "session_id":"df467381-a907-431d-a6a8-e8bcbd2c150d"}
```

**d. The immediate tool result** — the model is told the ID, the file, and that it will be
notified:
```
Command running in background with ID: bzzuzyibe. Output is being written to:
C:\Users\Admin\AppData\Local\Temp\claude\C--Users-Admin-Desktop-Claude-clone\
df467381-a907-431d-a6a8-e8bcbd2c150d\tasks\bzzuzyibe.output.
You will be notified when it completes. To check interim output, use Read on that file path.
```
with `tool_use_result` = `{"stdout":"","stderr":"","interrupted":false,"isImage":false,
"noOutputExpected":false,"backgroundTaskId":"bzzuzyibe"}`.

**e. Completion events** —
```json
{"type":"system","subtype":"task_updated","task_id":"bzzuzyibe",
 "run_id":"0mviemewu-87c1467f","patch":{"status":"completed","end_time":1792604817478},
 "uuid":"9674b3f5-eee4-4a79-a4ce-0f6fd9b3b9ac","session_id":"df467381-a907-431d-a6a8-e8bcbd2c150d"}
{"type":"system","subtype":"task_notification","task_id":"bzzuzyibe",
 "run_id":"0mviemewu-87c1467f","tool_use_id":"call_function_8qg29t9um0yl_1",
 "status":"completed","output_file":"...\\tasks\\bzzuzyibe.output",
 "summary":"Background command \"Run loop echoing tick-1 through tick-3\" completed (exit code 0)"}
```
followed by a `background_tasks_changed` event with an empty task list, and then a **new assistant
turn** — the model is re-invoked with the outcome rather than having to poll.

**Design points worth copying:**
- The background output file lives under a **per-session temp directory**
  (`%LOCALAPPDATA%\Temp\claude\<sanitized-cwd>\<session-id>\tasks\<task-id>.output`), unlike the
  foreground overflow file which lives in the session directory.
- The completion notification carries a **human-readable summary** with the exit code inlined:
  `Background command "<description>" completed (exit code 0)`. The `description` the model
  supplied at call time is what gets echoed back — so a good `description` is what makes the
  notification legible.
- The task id is a short opaque token (`b66s2c1p4`) distinct from the `tool_use_id`; both appear.
- `TaskOutput` was **removed in v2.1.277** — the model now reads the background task's output file
  with the ordinary `Read` tool instead of a dedicated retrieval tool.

**Clean-room opportunity:** emit task lifecycle as first-class typed events (`task_started`,
`task_progress`, `task_updated`, `task_notification`) on the same stream as the model messages, so
a UI can render a task panel and a client can resume without polling. Use a per-session temp
directory for live output and a per-session directory for retained artefacts.

**Source:** https://code.claude.com/docs/en/tools-reference#background-commands ;
https://code.claude.com/docs/en/interactive-mode#background-bash-commands

---

## F7 — Background commands have time limits in unattended sessions, and a fixed stop notice

**Status:** `OBSERVED-DOC`

> "In a session that runs unattended, such as a run with the `-p` flag, an Agent SDK application,
> a CI job, or a cloud session, background Bash and PowerShell commands have a time limit. A local
> session you work in from a terminal, the desktop app, or the VS Code extension has no time limit
> on background commands."

Limits, counted from the moment the command enters the background:
- Backgrounded at the model's request: **30 minutes**, or the `timeout` the model passed with
  `run_in_background`, to a maximum of **2 hours**.
- Moved from foreground by a timeout: **30 minutes** from the move.
- In a `-p` run whose prompt was passed as text (not `--input-format stream-json`): both defaults
  become **10 minutes** instead of 30, "because the run waits for background commands after its result".

Stop notice, exact text:
> `Background command "<description>" was stopped after reaching its background time limit`

Raising it: `BASH_DEFAULT_TIMEOUT_MS` above `1800000` replaces the 30-minute default;
`BASH_MAX_TIMEOUT_MS` above `7200000` raises the 2-hour maximum. Neither variable can *shorten* a
limit. Also `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` (default `600000`, `0` = wait forever) caps how
long a `-p` run idles waiting for background work.

**Clean-room opportunity:** make the "unattended" boundary explicit in your product — an
interactive session has no background cap, a headless/CI session does — and emit the stop reason as
a structured field rather than an English sentence, so a client can render it locally.

**Source:** https://code.claude.com/docs/en/tools-reference#time-limit-for-background-commands ;
https://code.claude.com/docs/en/headless#background-tasks-at-exit ; https://code.claude.com/docs/en/env-vars

---

## F8 — Permission rules: `Tool(specifier)`, evaluated deny → ask → allow, first match wins

**Status:** `OBSERVED-DOC`

Rule syntax: `Tool` or `Tool(specifier)`. "Parentheses inside the specifier are literal, so a
command or path that contains them needs no escaping."

Evaluation:
> "Rules are evaluated in order: deny, then ask, then allow. The first match in that order
> determines the outcome, and rule specificity doesn't change the order."

Consequences, all documented:
- A broad deny (`Bash(aws *)`) beats a narrower allow (`Bash(aws s3 ls)`). "An allow rule can't
  carve an exception out of a deny rule."
- An ask rule matches even when a more specific allow rule also matches.
- A **bare** tool name in `deny` (e.g. `"Bash"`, or `"Bash(*)"`) removes the tool from the model's
  context entirely — the model never sees it. A **scoped** rule (`Bash(rm *)`) leaves the tool
  present and blocks matching calls.
- Tool-name **globs** work in deny/ask: `"*"` matches every tool, `"mcp__*"` every MCP tool. Allow
  rules accept globs only after a literal `mcp__<server>__` prefix (`mcp__puppeteer__*`); an
  unanchored allow glob such as `"*"` or `"mcp__*"` is silently skipped.
- Settings precedence: **managed settings are highest and cannot be overridden by any CLI flag.**
  "If a tool is denied at any level, no other level can allow it."
- `permissions.disableBypassPermissionsMode` / `permissions.disableAutoMode: "disable"` can remove
  those modes entirely.

Setting keys and defaults (`OBSERVED-DOC`): `permissions.allow`, `permissions.ask`,
`permissions.deny` (arrays of rule strings, unset by default); `permissions.defaultMode`
(string, default `"default"`); `permissions.additionalDirectories`; `permissions.
blockReadsOutsideWorkingDirectories` (boolean, default `false`); `permissions.disableBypass-
PermissionsMode` (boolean, default `false`); `permissions.disableAutoMode` (string `"disable"`).

CLI equivalents: `--allowedTools` / `--allowed-tools` and `--disallowedTools` / `--disallowed-tools`,
both accepting the same `Tool(specifier)` grammar; `--tools` restricts the tool *set*; `--permission-mode`
selects the baseline mode.

**INFERRED (reasoning):** deny-first evaluation with scope-independent ordering is a deliberately
conservative design: it means a user who writes `deny: ["Bash(git push *)"]` can be certain that
no *other* rule in *any* file silently re-allows it. The corollary is that specificity is not a
priority — an implementer who ranks "most specific wins" would build a materially weaker
boundary.

**Clean-room opportunity:** implement rule evaluation as a strict three-pass scan
(deny → ask → allow) with first-match-wins inside each pass, and treat bare-name deny rules as
*tool removal from the model's tool list* rather than as a call-time block. Both behaviours are
observable to a user and easy to get wrong.

**Source:** https://code.claude.com/docs/en/permissions ;
https://code.claude.com/docs/en/settings-reference ; https://code.claude.com/docs/en/cli-reference

---

## F9 — Bash wildcard semantics have sharp edges that are documented with worked examples

**Status:** `OBSERVED-DOC`

The `*` in a Bash rule "matches any text, including spaces". The documented matching table:

| You write | Matches | Doesn't match |
| :- | :- | :- |
| `Bash(npm run build)` | `npm run build` | `npm run build --watch` |
| `Bash(npm run *)` | `npm run build`, `npm run test --watch`, `npm run` | `npm install` |
| `Bash(git log * main)` | `git log --oneline main`, `git log -5 main`, `git log --output=<file> main` | `git log main`, `git push origin main` |
| `Bash(git * main)` | `git merge main`, `git push origin main`, `git -c core.fsmonitor=<script> diff main` | `git log` |
| `Bash(* --version)` | `node --version`, `bash -c 'echo hi' --version` | `node -v` |
| `Bash(ls *)` | `ls -la`, `ls` | `lsof` |
| `Bash(ls*)` | `ls -la`, `lsof` | |

Three rules explain the table:
1. `*` stands in for whatever text is in its place — including subcommands and options.
2. A trailing ` *` (space before the star) **also matches the bare command**: `Bash(ls *)` matches
   `ls`. This holds "only when the trailing `*` is the rule's only wildcard": `Bash(* --help *)`
   matches `npm --help x` but not `npm --help`.
3. **The space before a trailing `*` is part of the rule.** `Bash(ls *)` requires a space after
   `ls`, so `lsof` does not match; `Bash(ls*)` has no space, so it matches `lsof` too.

`Bash(ls:*)` is an equivalent spelling of a trailing wildcard. The `:*` form is "only recognized
at the end of a pattern" — in `Bash(git:* push)` the colon is literal.

The permission dialog "writes the space-separated form when you select 'Yes, and don't ask again'".

Warning, quoted: "Put the `*` after the subcommand." A wildcard *before* the subcommand
(`Bash(git * main)`) matches every git subcommand and every option before it — including `-c`,
which makes git run an arbitrary program. The CLI warns at startup about an allow rule with a `*`
before the subcommand, such as `Bash(git * main)`.

**Clean-room opportunity:** implement the matcher with exactly these three rules (bare star,
trailing-star-with-space, trailing-star-without-space) and expose a `Bash(rule)` → "will match /
will not match" preview in the permission dialog. A rule-preview is the single feature that makes
this class of rule comprehensible to users.

**Source:** https://code.claude.com/docs/en/permissions#wildcard-patterns

---

## F10 — Compound commands are split and each subcommand must be independently allowed

**Status:** `OBSERVED-DOC`

> "Claude Code is aware of shell operators, so a rule like `Bash(safe-cmd *)` won't give it
> permission to run the command `safe-cmd && other-cmd`. The recognized command separators are
> `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines. A rule must match each subcommand independently."

- Deny/ask rules apply when **any** subcommand matches, including a command nested in a subshell,
  a command substitution, or a control-flow body such as a `for` loop. An ask rule like
  `Bash(git clean *)` still prompts for `cd /tmp && git clean -f` or `echo "$(git clean -f)"`.
- A trailing `&&`/`||` with nothing after it makes the command **unparseable**: the harness does not
  split it, so `Bash(npm *)` does not approve `npm test &&`.
- When a compound command is approved with "Yes, and don't ask again", Claude Code **saves a
  separate rule per subcommand** that needed approval — approving `git status && npm test` saves a
  rule for `npm test`, "so future `npm test` invocations are recognized regardless of what precedes
  the `&&`." **Up to 5 rules** may be saved for one compound command.
- `cd` into a directory outside the working directories generates its own `Read` rule for that path.

**Clean-room opportunity:** write a real shell tokenizer (not a regex) that yields a segment list
with operators, and evaluate rules per segment. Persist per-segment rules, not per-compound-string
rules, so a prefix rule keeps working when the command is later composed differently.

**Source:** https://code.claude.com/docs/en/permissions#compound-commands

---

## F11 — Wrapper stripping and env-assignment stripping happen before rule matching

**Status:** `OBSERVED-DOC`

Before matching, the harness strips a fixed, non-configurable set of wrappers:
`timeout`, `time`, `nice`, `nohup`, `stdbuf`, plus the shell builtins `command` and `builtin`, and
zsh's `noglob`. So `Bash(npm test *)` matches `timeout 30 npm test`. **Not** stripped: the query
form `command -v`, and zsh's `nocorrect`.

It also strips a leading assignment of **known-safe** environment variables, so
`Bash(npm test *)` matches `NODE_ENV=test npm test`. An **allow** rule will not match past an
assignment of any other variable; a **deny or ask** rule matches past any leading assignment, so
`Bash(rm *)` in deny still matches `FOO=bar rm -rf tmp/`.

Bare `xargs` is stripped too, so `Bash(grep *)` matches `xargs grep pattern` — but only when
`xargs` has no flags; `xargs -n1 grep pattern` is matched as an `xargs` command.

Development environment runners (`direnv exec`, `devbox run`, `mise exec`, `npx`, `docker exec`)
are **not** in the list. Because those runners execute their argument as a command,
`Bash(devbox run *)` matches whatever comes after `run`, including `devbox run rm -rf .`. The
documented mitigation: write a rule naming both the runner and the inner command, e.g.
`Bash(devbox run npm test)`.

**INFERRED (reasoning):** this is a *defensive* wrapper list — it strips only wrappers whose whole
purpose is to run a command, so the rule sees the real command. The explicit exclusion of
environment runners is a known limitation the docs state plainly, and the docs recommend naming the
inner command rather than trying to make a prefix rule safe.

**Clean-room opportunity:** implement wrapper stripping as a documented, versioned, overridable list
in the same shape (a wrapper rewrites the command to its inner form before matching), and warn the
user when a matched command contains a known runner that is *not* in the list — the "your prefix
rule also approves `devbox run <anything>`" case is a real, documented footgun.

**Source:** https://code.claude.com/docs/en/permissions#wrappers

---

## F12 — A built-in read-only command set runs without a prompt, with a documented list of exceptions

**Status:** `OBSERVED-DOC`

The set "is not configurable" and includes `ls`, `cat`, `echo`, `pwd`, `head`, `tail`, `grep`,
`find`, `wc`, `which`, `diff`, `stat`, `du`, `cd`, and read-only forms of `git`.

In Manual mode these still prompt in specific cases:
- **Unquoted globs** for commands with write-capable flags (`find`, `sort`, `sed`, `git`) — "because
  the glob could expand to a flag like `-delete`."
- **`docker`** pointed at another daemon (`-H`, `--context`, Podman's `--url`/`--connection`).
- **`file`** with `-m`/`--magic-file` or `-f`/`--files-from` — those flags make `file` open the
  paths named in the flag's value.
- **`ps`** when an argument could act as the `e` option (`ps auxe`, `ps aux -e`) — that option
  prints process environment variables. `ps aux` and `ps -ef` do not prompt. (Requires v2.1.290+.)
- **Network paths on Windows** — a command whose arguments include a UNC path (`\\server\share\file`)
  prompts, "because accessing a network path can send your Windows credentials to the host it names."
- **Writes to special shell variables** — setting/unsetting/looping over `PATH` or `IFS` prompts.
- **Unparseable commands** — if the command cannot be fully parsed it asks for approval rather than
  treating it as read-only. **Commands longer than 10,000 characters always prompt.**

Also: `cd` into a path inside the working directory is read-only, and `cd packages/api && ls` runs
without a prompt when each part qualifies on its own. But `cd` **with** `git` prompts when the `cd`
changes directory (new-directory git hooks can execute), and `cd` **with** a redirect prompts when
the redirect target's resolution depends on the new directory.

**INFERRED (reasoning):** the read-only set is a *heuristic*, not a sandbox — the doc is explicit
that it exists for convenience, and lists the ways it can be wrong. The important design property
is that the set is conservative in the ambiguous cases (unknown parse → prompt; glob that could
expand to a flag → prompt). A clean-room implementation should mirror that bias.

**Clean-room opportunity:** implement a read-only command classifier that is **allow-by-default for
explicitly listed read-only commands only**, and that escalates to a prompt on any unparseable
input, any unquoted glob against a write-capable command, and any argument that looks like a
credential-leaking flag (`ps ...e`, `file -f`, docker context flags). The 10,000-character ceiling
is a cheap, effective guard.

**Source:** https://code.claude.com/docs/en/permissions#read-only-commands

---

## F13 — The interactive permission prompt: exact layout, options, and bindings

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

Captured live from a Claude Code background session's TUI (`claude logs <id>`, ANSI stripped) —
saved at `agent-reference-shots/area5-bash-permissions/tui-permission-prompt.txt`:

```
● Running 2 shell commands…
  ⎿  $ git --version
────────────────────────────────────── PowerShell command
 List directory contents
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ Get-ChildItem -Force | Format-Table Mode, Length, LastWriteTime, Name -AutoSize
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │ Command contains malformed syntax that cannot be parsed: pwsh exited with code 1: The command line is too long.
 Do you want to proceed?
 ❯ 1. Yes
   2. No
 Esc to cancel · Tab to amend
```

Structure: a title bar naming the **tool** (`PowerShell command` / `Bash command`), then the agent's
`description`, then the exact command text, with a right-hand `│` gutter carrying the
reason/parse error, then numbered options with `❯` on the selected one, then the key bindings.

Documented option set for a Bash prompt (docs describe a 4-option prompt):
> "Yes; Yes, and don't ask again for: `npm test *`; Yes, and switch to auto mode; and No."

with the footer "Esc to cancel and Tab to amend." The "switch to auto mode" option appears only
when auto mode is available, only in Manual and `acceptEdits` modes, and **not** on PowerShell
prompts (requires v2.1.247+).

**Comment attachment on the prompt** (`OBSERVED-DOC`): on most prompts — including Bash, PowerShell,
file and MCP — moving to **Yes** or **No** and pressing `Tab` opens a comment field on that option.
`Enter` submits with the comment, `Tab` closes the field without answering, `Shift+Tab` closes it
on a file prompt. On **Yes**, the comment is delivered to the model *after* the result; on **No**, it
is delivered *as the reason for the denial* and the model continues.

**Persistence of an approval** (`OBSERVED-DOC`): choosing "Yes, and don't ask again" for a Bash
command saves the rule to `.claude/settings.local.json` at the **root of the git repository**,
resolved through worktrees to the main checkout. "The rule applies to future sessions anywhere in
that repository, including sessions started in subdirectories and in worktrees." A **file-modification
approval is not saved** — it lasts until the session ends.

**Clean-room opportunity:** render the prompt as title / description / exact-command / reason
gutter / numbered options / binding hints, and support a per-answer comment that is delivered to the
model either as post-hoc context (approval) or as the denial reason (refusal). Let the user amend
the command before approving.

**Source:** https://code.claude.com/docs/en/permissions ; https://code.claude.com/docs/en/interactive-mode

---

## F14 — Permission decisions are reported in structured metadata, and denials carry the full tool input

**Status:** `OBSERVED-CLI`

Every tool result carries a `tool_result_meta` array with the permission decision:

```json
"tool_result_meta":[{"id":"call_function_gtxi815nvr8u_1",
  "permission_decision":{"decision":"accept","source":"config","reason_type":"subcommandResults"}}]
```

Observed values:
| `decision` | `source` | `reason_type` | When |
| :- | :- | :- | :- |
| `accept` | `config` | `subcommandResults` | An allow rule matched the command's subcommands |
| `reject` | `config` | `subcommandResults` | A deny rule matched |
| `reject` | `config` | (absent) | Rejected before execution (e.g. parse failure) |

Rejected calls additionally carry a `non_execution_kind` discriminator. Observed values:
- `"permission-rule"` — a deny rule blocked it.
- `"user-rejected"` — the command could not be parsed / was rejected at the prompt.

The **denial message** itself names the tool and the command:
```
Permission to use Bash with command echo denied-test has been denied.
```
delivered as `{"content":"Permission to use Bash with command echo denied-test has been denied.",
"is_error":true}`.

The final `result` envelope aggregates denials:
```json
"permission_denials":[{"tool_name":"Bash","tool_use_id":"call_49b77dede2e44285a7e7ce1f",
  "tool_input":{"command":"echo denied-test","description":"Echo test string"}}]
```
— the **full tool input** is retained, so a caller can audit exactly what was refused.

A second observed rejection shape, when the command could not be parsed and the model then tried
the sandbox override:
```
"This command requires approval"
```
with `non_execution_kind:"user-rejected"`. Both attempts appear in `permission_denials`, the
second carrying `"dangerouslyDisableSandbox":true` in its `tool_input`.

**INFERRED (reasoning):** exposing `decision / source / reason_type` per call is what makes an
agent's permission behaviour auditable after the fact, and `reason_type:"subcommandResults"` tells
the auditor the decision came from a per-subcommand rule evaluation rather than a whole-tool
allow. A clean-room implementation should record the same three axes.

**Clean-room opportunity:** emit a structured decision record with every tool result
(`{decision, source, reason_type, non_execution_kind}`), include the full tool input in any
denial summary, and make the denial message name the tool and the command.

**Source:** this is a direct observation; the equivalent surface is also visible in the
`stream-json` output documented at https://code.claude.com/docs/en/headless

---

## F15 — PreToolUse hooks are the programmable extension point: schema, decisions, exit codes

**Status:** `OBSERVED-DOC`

Hook input (exact shape from the docs):
```json
{
  "session_id": "abc123",
  "prompt_id": "550e8400-e29b-41d4-a716-446655440000",
  "transcript_path": "/home/user/.claude/projects/.../transcript.jsonl",
  "cwd": "/home/user/my-project",
  "scratchpad_dir": "/tmp/claude-1000/-home-user-my-project/abc123/scratchpad",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {"command":"npm test","description":"Run test suite",
                 "timeout":120000,"run_in_background":false},
  "tool_use_id": "toolu_01ABC123..."
}
```

Hook output:
```json
{"hookSpecificOutput":{
  "hookEventName":"PreToolUse",
  "permissionDecision":"deny",
  "permissionDecisionReason":"Database writes are not allowed"}}
```
Decisions: `"allow"` | `"deny"` | `"ask"` | `"defer"`. `updatedInput` under `hookSpecificOutput`
replaces the tool's arguments before it runs.

Exit-code semantics:

| Exit code | Effect |
| :- | :- |
| `0` | Success; valid JSON fields applied. No output = no decision, tool proceeds normally. |
| `2` | Blocking error; the call is blocked and **stderr is the reason**. Valid JSON is read but cannot override the block. |
| other | Non-blocking error, tool continues — **unless** stdout contains valid JSON, in which case the JSON is applied regardless of the nonstandard exit code. Use `"onFailure":"block"` to make failures block. |

The docs warn: "Exit code 1 without valid JSON output is a non-blocking error … If your hook is
meant to enforce a policy, use `exit 2`."

**Precedence** — hooks do **not** override rules:
> "Claude Code evaluates deny and ask rules regardless of what a PreToolUse hook returns: a matching
> deny rule blocks the call, and a matching ask rule still prompts even when the hook returned
> `"allow"` or `"ask"`."

And a blocking hook beats allow rules: "A hook that exits with code 2 stops the tool call before
permission rules are evaluated."

Matching: the `matcher` field filters by **bare tool name** (not the parenthesised rule format); the
handler's `if` field holds **exactly one** permission rule. On Windows you need matcher
`Bash|PowerShell` with a separate handler per tool. The `if` filter is explicitly "best-effort" —
"use the permission system rather than a hook to enforce a hard allow or deny."

**Clean-room opportunity:** implement the same hook protocol — a pre-execution hook that receives
the full tool input and can return `allow`/`deny`/`ask`/`defer` plus a rewritten input, with
`exit 2` meaning "block, and here is why". Keep rule evaluation strictly above hooks so a hook
cannot widen access.

**Source:** https://code.claude.com/docs/en/hooks ; https://code.claude.com/docs/en/permissions#extend-permissions-with-hooks

---

## F16 — Sandbox: OS-level isolation, auto-allow mode, and an explicit unsandboxed escape hatch

**Status:** `OBSERVED-DOC`

The sandbox "is a boundary that the operating system enforces around the shell commands Claude
Code runs on your machine", and it applies to Bash, PowerShell and Monitor commands **and their
child processes**. It does not cover Claude's file tools, MCP servers, or hooks. It runs on macOS,
Linux and WSL2; **on native Windows Claude Code runs commands unsandboxed** (this host is native
Windows, so the sandbox is not directly observable here — flagged as INFERRED for this host).

Two modes:
- **Auto-allow mode** — "Claude Code approves a command automatically, with no prompt, when the
  command runs inside the sandbox." `sandbox.autoAllowBashIfSandboxed` (default `false` in the
  settings reference; the docs note it "still defaults to `true`" in a different context — see
  the note in F17). Even in auto-allow mode: a `Bash` deny rule still blocks; `rm`/`rmdir` against
  a **critical path** still goes through the normal flow; content-scoped ask rules like
  `Bash(git push *)` still force a prompt; a **bare `Bash` ask rule is skipped** for sandboxed
  commands (but not in plan mode); Monitor commands are **not** auto-approved.
- **Regular permissions mode** — all Bash commands go through the normal flow.

**The unsandboxed retry escape hatch:** when a command fails inside the sandbox, Claude Code names
the denied host in the result, the model analyses it, and may retry with
`dangerouslyDisableSandbox: true`. The retry runs **unsandboxed** and is approved differently by
mode: `bypassPermissions` → no prompt; Manual/`acceptEdits` → a prompt titled **"Bash command
(unsandboxed)"**; auto → a separate classifier; `dontAsk` → denied; plan mode → gated.
An ask rule for the parameter itself (`Bash(dangerouslyDisableSandbox:true)`) forces the prompt in
every mode and **takes precedence over a matching allow rule**.

`"allowUnsandboxedCommands": false` disables the retry (the `/sandbox` **Overrides** tab calls this
**Strict sandbox mode**); `failIfUnavailable: true` refuses to start rather than running unsandboxed.

**Network isolation:** "No direct route out. Connections go through a proxy on your machine that
checks each host against your allowed domains, which start empty." Keys: `sandbox.network.
allowedDomains`, `sandbox.network.deniedDomains` (denied takes precedence over allowed wildcards),
`network.allowUnixSockets`, `network.allowLocalBinding`, `network.httpProxyPort`,
`network.socksProxyPort`, `network.strictAllowlist`. Filesystem: `sandbox.filesystem.allowWrite`,
plus a per-user writable temp dir and `$TMPDIR` set for sandboxed commands.

**Clean-room opportunity:** implement the sandbox as a genuinely separate layer from permissions
(OS-enforced, covering child processes), keep the sandbox→unsandboxed retry as an explicit,
separately-approved step with its own prompt title, and expose a "strict sandbox" switch that
ignores the model's request to disable isolation. Never let a broad allow rule imply a broad
sandbox bypass.

**Source:** https://code.claude.com/docs/en/sandboxing

---

## F17 — Protected paths and critical paths are two separate, non-overridable guard rails

**Status:** `OBSERVED-DOC`

**Protected paths** — writes are never auto-approved except in `bypassPermissions` mode (and plan
mode with bypass available). Per-mode outcome:

| Mode | Protected-path writes |
| :- | :- |
| `default`, `acceptEdits` | Prompted |
| `plan` | Allowed only in interactive terminal sessions with bypass available; otherwise routed to the classifier (auto mode) or prompted |
| `auto` | Routed to the classifier |
| `dontAsk` | Denied |
| `bypassPermissions` | Allowed |

**`permissions.allow` rules do not pre-approve protected-path writes** — "The safety check runs
before Claude Code evaluates allow rules from settings." Protected directories include `.git`,
`.config/git`, `.vscode`, `.idea`, `.husky`, `.cargo`, `.devcontainer`, `.yarn`, `.mvn`, `.claude`
(with exceptions such as `.claude/worktrees/`, `~/.claude/plans/`, and a background session's own
`~/.claude/jobs/<id>/tmp/`). Protected files include `.gitconfig`, `.bashrc`/`.zshrc`/`.profile`,
`.npmrc`, `.bazelrc`, `.pre-commit-config.yaml`, `gradle-wrapper.properties`, `.mcp.json`,
`.claude.json`.

**Critical paths** — a separate guard on `rm`/`rmdir`:
> "Claude Code never lets a `permissions.allow` rule or a `PreToolUse` hook that returns `"allow"`
> approve an `rm` or `rmdir` command that targets a critical path, even in modes that skip other
> prompts. This circuit breaker guards against model error."

Critical = filesystem root; top-level directories (`/usr`, `/etc`, `/data`); your home directory
(including the Windows 8.3 short name `C:\Users\LONGNA~1`); Windows drive roots and their
top-level directories (`C:\`, `C:\Windows`, plus the `\\?\C:\` and `\\localhost\C$` spellings);
your working directory and its parents; your additional working directories and their parents
(only when the removal is a glob under them). Additional targets that count: a glob directly under
a shell variable (`rm -rf "$DIR"/*`), a glob under an unset positional parameter, a variable
followed by a common top-level directory name, a value assigned from `$(pwd)` or
`$(git rev-parse --show-toplevel)`, a target that is only command-substitution output, a trailing
command substitution after a critical path, a target that is only backslashes, a Windows volume
GUID path, and some targets ending in `/*` or `/*/`.

`CLAUDE_CODE_DISABLE_SUBSTITUTION_RM_PROMPT=1` turns off only the command-substitution case.

**INFERRED (reasoning):** these two guard rails deliberately sit *above* both allow rules and
hooks. That ordering is the whole point — they exist because the model, having been authorised to
run `rm`, may still generate a catastrophic target. Any clean-room implementation that lets a
user rule or a hook waive them has lost the property that makes them useful.

**Clean-room opportunity:** implement two non-waivable checks evaluated before allow rules and
hooks: (a) protected-path writes routed by mode, (b) a destructive-target circuit breaker with an
explicit critical-path set and variable-expansion analysis. Both are cheap to implement relative to
the damage they prevent.

**Source:** https://code.claude.com/docs/en/permission-modes#protected-paths ;
https://code.claude.com/docs/en/permission-modes#critical-paths

---

## F18 — Auto mode replaces the human prompt with a second, model-based classifier

**Status:** `OBSERVED-DOC` (rule set observed via CLI)

Auto mode "runs without routine prompts; before actions such as shell commands and network requests
run, a background **classifier** checks that they align with your request."

The classifier's decision order is documented as a fixed four-step procedure:
1. Allow/ask/deny rules resolve immediately — **with exceptions**: protected-path writes route to
   the classifier even when an allow rule matches; no allow rule approves `rm`/`rmdir` against a
   critical path; MCP tools marked `requiresUserInteraction` prompt directly; a shell command
   carrying per-command allowed domains routes to the classifier; content-scoped ask rules fall
   back to a prompt; a write whose symlink resolves to a protected path prompts; a read from a
   network path prompts.
2. Read-only actions and file edits in the working directory are auto-approved — except protected
   paths and the **first read outside the working directories**, which prompts.
3. Everything else goes to the classifier.
4. If the classifier blocks, "Claude receives the reason … the reason names the rule the classifier
   matched, such as `[Data Exfiltration]`".

On entering auto mode, **broad allow rules are dropped**: blanket `Bash(*)` / `PowerShell(*)`, wildcarded
interpreters like `Bash(python*)`, package-manager run commands, `Agent` allow rules, and `Monitor`
allow rules. Narrow rules like `Bash(npm test)` stay. "Claude Code restores the dropped rules when
you leave auto mode."

The classifier's view is deliberately narrow: it sees user messages, non-read-only tool calls, and
CLAUDE.md content — **tool results are stripped**, "so hostile content in a file or web page can't
manipulate the classifier directly." A separate server-side probe scans incoming tool results.

The shipped rule set is inspectable from the CLI:

```
claude auto-mode defaults      # the built-in rule set as JSON
claude auto-mode config        # effective config (settings override defaults)
claude auto-mode defaults --label 'Git Destructive'   # filter by rule label
```

`claude auto-mode defaults` was run on this host and returns four groups — `allow`, `soft_deny`,
`hard_deny`, `environment` — of natural-language rules, each a prose policy with a named concept
(e.g. `Security Discussion`, `Transient Retry`, `Local Operations` in `allow`; `Git Destructive`,
`Code That Leaks When Run`, `Production Deploy`, `Sensitive Remote Exec`, `Safety Bypass Flag` in
`soft_deny`). Saved to `agent-reference-shots/area5-bash-permissions/auto-mode-defaults.json`.

Note on the CLI's `soft_deny` semantics: many soft-deny rules carry an explicit consent bar —
"[named+specifics — **must name:** the destructive operation and its target]" — meaning the rule
requires the *user's own words* to name the operation before it is allowed.

**INFERRED (reasoning):** auto mode is a fundamentally different architecture from rule-based
permissions: the authority for a decision moves from a deterministic matcher to a probabilistic
judge reading the transcript. The rule set's own framing (consent bars, "must name", "HARD evaluates
first") shows the designers treating that judge as needing explicit, auditable policy text rather
than a prompt. A clean-room implementation wanting this capability should expect to spend most of
its effort on the *policy corpus*, not the plumbing.

**Clean-room opportunity:** implement a two-layer permission system — deterministic rules first,
then an optional semantic reviewer that sees the transcript but **not tool results**, and whose
reason codes are stable identifiers (`[Code That Leaks When Run]`) so denials are auditable and
tunable. Expose the reviewer's policy as editable JSON so an organisation can tune it.

**Source:** https://code.claude.com/docs/en/permission-modes ;
https://code.claude.com/docs/en/auto-mode-config ; CLI: `claude auto-mode defaults`,
`claude auto-mode config`

---

## F19 — Headless mode: who answers the prompt, and what happens when nobody can

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

`--permission-prompts <target>` (choices `host`, `none`; default `host`):
> "Set who answers permission prompts in print mode. With the default `host`, Claude Code sends
> them to the Agent SDK host or the `--permission-prompt-tool` tool. Pass `none` when nobody can
> answer, and Claude Code denies them instead."

With `none`: "your run doesn't consult the host or wait on it. Anything that would prompt is denied
unless a `PermissionRequest` hook allows it, **Claude is told that nobody can approve the request
and not to retry it**, and the run continues."

`--permission-prompt-tool <mcp__server__tool>` routes prompts to an MCP tool; the docs note "The
prompt tool can't approve an MCP tool marked as requiring user interaction: Claude Code converts an
`allow` result for one to a deny."

Observed on this host (v2.1.306): a `claude -p` run with `--disallowedTools "Bash(echo *)"` produced
the denial message and a `permission_denials` array (F14), and the model **did not retry** — it
reported the block and offered alternatives. A run with `--allowedTools "Bash(sh *)"` produced
`permission_decision:{decision:"accept",source:"config",reason_type:"subcommandResults"}`.

A `-p` run also **skips the workspace-trust dialog** and shows no per-server MCP approval prompt
(observed: `claude -p` ran fine in a directory with no trust prompt). And "With Claude Code v2.1.302
or later, `claude -p` runs start in Manual mode when nothing sets a permission mode."

**Clean-room opportunity:** make the "who answers the prompt" question a first-class, explicit
configuration with exactly two answers — *an interactive human* and *nobody*. In the nobody case,
deny, tell the model not to retry, and keep going; do not block the run. Provide a pluggable
"prompt handler" interface so a program can answer prompts programmatically (the SDK `canUseTool`
callback is the equivalent surface).

**Source:** https://code.claude.com/docs/en/headless ;
https://code.claude.com/docs/en/cli-reference ; observed on this host

---

## F20 — The PowerShell tool mirrors Bash with AST-based matching and alias canonicalisation

**Status:** `OBSERVED-DOC` + `OBSERVED-CLI`

Availability: "Windows without Git Bash: the tool is enabled automatically. Windows with Git Bash
installed: the tool is on by default for claude.ai and Console accounts" — on this host both tools
are present, and `init` reported `powershell_path:
C:\Users\Admin\AppData\Local\Microsoft\WindowsApps\Microsoft.PowerShell_...\pwsh.exe`. (Confirmed
in the sibling capture `agent-reference-shots/PROTOCOL-NOTES.md` §16.)

Rule semantics:
- Same shape as Bash rules. `PowerShell` or `PowerShell(*)` matches every command.
- "Common aliases are canonicalized before matching. A rule written for the cmdlet name also matches
  its aliases, so `PowerShell(Get-ChildItem *)` matches `gci`, `ls`, and `dir` as well. Matching is
  case-insensitive."
- "Claude Code parses the **PowerShell AST** and checks each command in a compound command
  independently. Pipeline operators `|`, statement separators `;`, and on PowerShell 7+ the chain
  operators `&&` and `||` split a compound command into subcommands. A rule must match every
  subcommand for the compound command to be allowed."

Process launch: "Claude Code spawns PowerShell with `-ExecutionPolicy Bypass` at process scope only,
so `.ps1` scripts and module imports work on default Windows installs without changing the machine's
policy. Process-scope bypass doesn't override Group Policy `MachinePolicy` or `UserPolicy`." Set
`CLAUDE_CODE_POWERSHELL_RESPECT_EXECUTION_POLICY=1` to respect the machine policy instead.

**Bash deny rules also turn off the PowerShell tool** — a deny rule naming the whole `Bash` tool
disables `PowerShell` too. The docs record the error string: "Denying Bash also turns off the
PowerShell tool, so Claude has neither."

`acceptEdits` mode auto-approves `Set-Content`, `Add-Content`, `Clear-Content` and `Remove-Item`
on in-scope paths, with the same protected-path rules; `Remove-Item` has its own check. A
positional argument containing a quote character still prompts, "because Claude Code can't statically
validate an argument whose quoted and unquoted readings differ."

**Observed:** the interactive TUI renders the PowerShell prompt with the title "PowerShell command"
(the tool name), confirming the two tools present distinct prompts (F13).

**INFERRED (reasoning):** matching a real AST rather than a regex is materially safer for
PowerShell, because PowerShell's syntax admits many ways to reach the same cmdlet. Doing the same
for Bash would be the natural extension, but Bash's grammar is more permissive; the documented
approach for Bash is operator-aware splitting plus wrapper stripping (F10, F11).

**Clean-room opportunity:** on Windows, implement the shell tool over a real parser (AST for
PowerShell, POSIX-shell tokenisation for Bash) and canonicalise command aliases before matching.
Launch PowerShell with a process-scoped execution-policy bypass so a restrictive default policy
does not break legitimate script execution.

**Source:** https://code.claude.com/docs/en/tools-reference#powershell-tool ;
https://code.claude.com/docs/en/permissions#powershell ; https://code.claude.com/docs/en/errors

---

## F21 — The Monitor tool is a distinct execution mode: line-streaming background watch

**Status:** `OBSERVED-DOC`

`Monitor` "runs a command in the background and feeds each output line back to Claude, so it can
react to log entries, file changes, or polled status mid-conversation."

- Every watch has a deadline: **5 minutes by default, at most 30 minutes**, and at most **10
  minutes** in a non-interactive `-p` run. "At the deadline the watch ends. Claude gets one notice,
  so it can start the watch again if it's still needed."
- "When Monitor runs a command, it uses the **same permission rules as Bash**, so `allow` and
  `deny` patterns you have set for Bash apply here too." But: "While auto mode is active, Claude Code sets
  aside allow rules that name `Monitor` itself … so the classifier reviews Monitor commands the
  same way it reviews Bash commands." And in sandbox auto-allow mode, "Monitor tool commands aren't
  approved automatically, though they still run in the sandbox."
- A **WebSocket source** takes a `ws` input (`url` required, `protocols` optional) in place of
  `command`; a single call cannot combine the two. Text messages become one event each; binary
  frames are **not** passed through — Claude receives a placeholder like `[binary frame, 512 bytes]`;
  messages larger than **1 MiB** end the watch; a socket close ends the watch and Claude receives the
  close code. `timeout_ms` applies to WebSocket watches too, and `TaskStop` cancels early.
- Private/link-local/cloud-metadata addresses are denied, as are hosts in
  `sandbox.network.deniedDomains`.
- Not available on Bedrock, Agent Platform or Foundry; not available when `DISABLE_TELEMETRY` or
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set; on Windows only when Git Bash is installed.

**INFERRED (reasoning):** Monitor is a *streaming* execution mode, distinct from
`run_in_background: true` (which returns a task ID and a file). The distinguishing behaviour is
that the harness pushes lines into the conversation and re-invokes the model, so the agent can react
mid-flight — a genuinely different interaction primitive from "run and report at the end".

**Clean-room opportunity:** offer both a "background job" (returns a handle; read output later) and
a "watch" (streams events into the conversation) primitive. The watch needs its own deadline, its
own cancellation handle, and its own size limits (the 1 MiB frame cap and the binary-frame
placeholder are good defaults).

**Source:** https://code.claude.com/docs/en/tools-reference#monitor-tool

---

## F22 — `acceptEdits` auto-approves a specific, enumerated set of filesystem commands

**Status:** `OBSERVED-DOC`

> "In addition to file edits, `acceptEdits` mode auto-approves common filesystem Bash commands:
> `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, and `sed`. These commands are also auto-approved
> when prefixed with safe environment variables such as `LANG=C` or `NO_COLOR=1`, or process
> wrappers such as `timeout`, `nice`, or `nohup`. Like file edits, auto-approval applies only to
> paths inside your working directory or `additionalDirectories`."

Even in `acceptEdits`:
- Each path goes through the symlink check, "so a write that resolves outside that scope isn't
  auto-approved either."
- Paths outside the scope, writes to protected paths, `rm`/`rmdir` removals targeting a critical
  path, and all other Bash commands except the built-in read-only set **still prompt**.
- On Windows, `acceptEdits` also auto-approves `Set-Content`, `Add-Content`, `Clear-Content` and
  `Remove-Item` on in-scope paths (with aliases), and `Remove-Item` has its own check.

**INFERRED (reasoning):** the auto-approve list is deliberately small and *path-scoped*. Note that
`rm` appears in it — the mode does not treat removal as inherently dangerous, but the path scope
and the critical-path breaker (F17) constrain it. That combination is the interesting design:
enumerate the operation, then constrain the target.

**Clean-room opportunity:** implement "accept edits" as a small, enumerated operation list plus a
path-scope predicate plus a destructive-target breaker, rather than as a blanket "trust the agent"
switch. Make the enumeration user-visible so the trust surface is legible.

**Source:** https://code.code.claude.com/docs/en/permission-modes#auto-approve-file-edits-with-acceptedits-mode

---

## F23 — Environment and state that persist between commands

**Status:** `OBSERVED-DOC`

- **Working directory persists** (main session only): "When Claude runs `cd` in the main session,
  the new working directory carries over to later Bash commands as long as it stays inside the
  project directory or an additional working directory." "Subagent sessions never carry over working
  directory changes." If `cd` lands outside, "Claude Code resets to the project directory and appends
  `Shell cwd was reset to <dir>` to the tool result."
  `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` disables the carry-over.
- **Environment variables do not persist**: "An `export` in one command won't be available in the
  next." (This is a deliberate difference from an interactive shell and is worth copying: it keeps
  the model from building an invisible dependency chain across calls.)
- **Aliases and shell functions are available**: at session start Claude Code sources `~/.zshrc`,
  `~/.bashrc` or `~/.profile` depending on the shell, captures the resulting aliases, functions and
  shell options, and applies them to every Bash command.
- `CLAUDE_ENV_FILE` — point at a shell script to make environment variables persist across Bash
  commands; a SessionStart hook can populate it dynamically.
- **Memory limit**: `CLAUDE_CODE_TOOL_MEMORY_LIMIT` (e.g. `4G`) caps the memory that Bash,
  PowerShell and Monitor commands can use on Linux/WSL. "Claude Code counts all of a session's Bash,
  PowerShell, and Monitor commands against the one cap, not each command on its own." Applied with a
  memory cgroup; when the cap is exceeded "the kernel kills a command, and **nothing in its result
  names the cap**." `CLAUDE_CODE_TOOL_MEMORY_CGROUP_EXCLUDE` exempts kinds by name: `mcp`, `lsp`,
  `hooks`, `plugin`, `helper`, `agent`. Permission-gating hooks and the MCP servers they call are
  always excluded, "so the kernel killing a permission-gating hook can't allow the action it was
  blocking."

**Clean-room opportunity:** mirror the cwd-persists / env-does-not-persist split — it is a
deliberate trade that keeps command calls reproducible. Expose a session-wide memory cap for tool
subprocesses with an exemption list that always protects policy-enforcing processes.

**Source:** https://code.claude.com/docs/en/tools-reference#what-persists-between-commands ;
https://code.claude.com/docs/en/env-vars

---

## F24 — Windows-specific shell behaviour is a distinct, documented surface

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

This host is native Windows, which surfaces several Windows-only behaviours:

- **Both** `Bash` (Git Bash) and `PowerShell` tools are present by default; `init` reports
  `powershell_path`.
- The sandbox does **not** run on native Windows ("On native Windows, Claude Code runs commands
  unsandboxed"); WSL2 is required.
- **UNC / network paths** are a first-class concern: "on Windows, a UNC path such as
  `\\server\share\file`" makes a read "get its own permission check" because "on Windows that
  contact can send the host your credentials". A read-only Bash or PowerShell command whose
  arguments include a UNC path **still prompts in Manual mode**. Since v2.1.292, a network-path
  read "leaves the prompt in place" — allow rules, PreToolUse hooks returning `"allow"`, and the
  auto-mode classifier **do not** remove it; in `dontAsk` mode it is denied; in `bypassPermissions`
  it runs without the prompt.
- **Paths are normalised to POSIX form before matching**: "`C:\Users\alice` becomes `/c/Users/alice`,
  so use `//c/**/.env` to match `.env` files anywhere on that drive. To match across all drives, use
  `//**/.env`."
- **Critical-path spellings** include the Windows 8.3 short name (`C:\Users\LONGNA~1`), `\\?\C:\`,
  `\\localhost\C$`, and volume GUID paths — all treated as the drive root.
- **`rm -rf "\\"`** is treated as a critical-path removal "on every platform", because Git Bash reads
  a lone backslash as the current drive's root.

**Observed, first-hand:** the interactive TUI showed a PowerShell command that failed at parse time
with `Command contains malformed syntax that cannot be parsed: pwsh exited with code 1: The command
line is too long.` — a pre-execution parse failure surfaced as a *permission-style prompt* with the
reason in the right-hand gutter, and the tool result marked it
`non_execution_kind: "user-rejected"`. This confirms that a command which cannot be parsed is
never executed and never silently trusted.

**Clean-room opportunity:** on Windows, normalise paths to a single canonical form before matching
(`/c/Users/...`), treat UNC paths as requiring an explicit approval that allow rules cannot
waive, and refuse to execute any command the parser cannot fully understand.

**Source:** https://code.claude.com/docs/en/permissions#network-paths ;
https://code.claude.com/docs/en/permission-modes#which-paths-are-critical ;
https://code.claude.com/docs/en/tools-reference#powershell-tool

---

## Capability table

| Capability | Status | Evidence | Notes |
| :- | :- | :- | :- |
| Bash tool input = `command`/`description`/`timeout`/`run_in_background` (+`dangerouslyDisableSandbox`) | OBSERVED-CLI + OBSERVED-DOC | F1 | `description` is agent-authored; not an auth signal |
| PowerShell tool with the same shape | OBSERVED-DOC + OBSERVED-CLI | F20, F24 | AST-based rule matching; alias canonicalisation |
| Separate process per command | OBSERVED-DOC | F23 | cwd persists (main session), env does not |
| Success payload `{stdout, stderr, interrupted, isImage, noOutputExpected}` | OBSERVED-CLI | F2 | Typed, not a pre-rendered string |
| stdout and stderr are **merged into one pipe**; the `stderr` field is always empty | OBSERVED-CLI | F2 | Confirmed by a stderr-only run: text appears in `stdout` |
| Failure payload = in-band text `"Exit code N\n…"` with `is_error:true` | OBSERVED-CLI | F2 | stdout/stderr merged on the failure path |
| Benign exit-1 command table | OBSERVED-DOC | F3 | grep/rg/egrep/fgrep/find/diff/test/[/git diff/git grep |
| Inline output ~30,000 chars (valid) / ~10,000 (failure) | OBSERVED-DOC | F4 | |
| Overflow → session-dir file path + 2,000-char preview in `<persisted-output>` tags | OBSERVED-CLI | F4 | 5 GB hard kill |
| `BASH_MAX_OUTPUT_LENGTH` (30k/150k) and `bashOutputMaxChars` (→128k, overrides the env var) | OBSERVED-DOC | F4 | |
| Timeout 120s default / 600s ceiling; effective ceiling = max of the two env vars | OBSERVED-DOC | F5 | |
| Timeout auto-promotes foreground → background (except `sleep`) | OBSERVED-DOC | F5 | Exact result text documented |
| Background task: id + output file + "you will be notified" | OBSERVED-CLI | F6 | `backgroundTaskId` in the payload |
| Background lifecycle events on the stream | OBSERVED-CLI | F6 | `background_tasks_changed`, `task_started`, `task_updated`, `task_notification` |
| Background completion summary with exit code | OBSERVED-CLI | F6 | `Background command "<desc>" completed (exit code 0)" |
| `TaskOutput` removed in v2.1.277 — read the output file with `Read` | OBSERVED-DOC | F6 | |
| Background time limits 30 min / 2 h max (10 min in `-p`) | OBSERVED-DOC | F7 | No limit in interactive sessions |
| Rule grammar `Tool(specifier)`; deny → ask → allow, first match wins | OBSERVED-DOC | F8 | Bare-name deny removes the tool from the model's context |
| Tool-name globs in deny/ask (`*`, `mcp__*`) | OBSERVED-DOC | F8 | Allow globs only after a literal `mcp__<server>__` |
| Managed settings cannot be overridden by any flag | OBSERVED-DOC | F8 | |
| Bash wildcard semantics (bare / trailing-with-space / trailing-without-space) | OBSERVED-DOC | F9 | `:*` == trailing ` *` |
| Compound-command splitting on `&& \|\| ; \| \|& &` and newline | OBSERVED-DOC | F10 | Per-subcommand rules; max 5 saved per approval |
| Wrapper stripping (timeout/time/nice/nohup/stdbuf/command/builtin/noglob/xargs) | OBSERVED-DOC | F11 | Known-safe env-assignment stripping too |
| Read-only command set + the cases that still prompt | OBSERVED-DOC | F12 | Unparseable or >10,000 chars always prompts |
| Interactive prompt: tool title / description / command / options / bindings | OBSERVED-CLI + OBSERVED-DOC | F13 | "Yes, and don't ask again", "Yes, and switch to auto mode" |
| Per-answer comment field (Tab) delivered to the model | OBSERVED-DOC | F13 | Comment = denial reason on No |
| "Don't ask again" persists to `.claude/settings.local.json` at the git root | OBSERVED-DOC | F13 | Edit approvals are session-only |
| Structured permission decision metadata on every result | OBSERVED-CLI | F14 | `decision`/`source`/`reason_type`/`non_execution_kind` |
| Denial message names tool + command; `permission_denials[]` keeps full tool input | OBSERVED-CLI | F14 | |
| PreToolUse hook input/output schema; exit 0/2/other semantics | OBSERVED-DOC | F15 | `allow`/`deny`/`ask`/`defer` + `updatedInput` |
| Hooks cannot override deny/ask rules; exit 2 beats allow rules | OBSERVED-DOC | F15 | |
| OS-level sandbox with auto-allow mode and per-command domain allowlist | OBSERVED-DOC | F16 | Not available on native Windows |
| `dangerouslyDisableSandbox` retry with its own prompt title | OBSERVED-DOC + OBSERVED-CLI | F16 | Ask rule `Bash(dangerouslyDisableSandbox:true)` forces it |
| Strict sandbox mode (`allowUnsandboxedCommands:false`) | OBSERVED-DOC | F16 | |
| Protected paths, per-mode outcome, not waivable by allow rules | OBSERVED-DOC | F17 | |
| Critical-path `rm`/`rmdir` circuit breaker | OBSERVED-DOC | F17 | Not waivable by allow rules **or** hooks |
| Auto mode: model-based classifier with a fixed 4-step decision order | OBSERVED-DOC | F18 | Broad allow rules dropped on entry |
| Classifier sees the transcript but not tool results | OBSERVED-DOC | F18 | |
| Shipped classifier rules inspectable as JSON | OBSERVED-CLI | F18 | `claude auto-mode defaults` / `config` |
| Headless: `--permission-prompts host\|none`, `--permission-prompt-tool` | OBSERVED-CLI + OBSERVED-DOC | F19 | `none` → deny + "don't retry" |
| `-p` skips the workspace-trust dialog | OBSERVED-DOC + OBSERVED-CLI | F19 | |
| `acceptEdits` auto-approves an enumerated command list, path-scoped | OBSERVED-DOC | F22 | `mkdir touch rm rmdir mv cp sed` (+ PS equivalents) |
| Monitor tool: line-streaming watch with 5/30/10-min deadlines | OBSERVED-DOC | F21 | Shares Bash permission rules |
| Monitor WebSocket source; 1 MiB frame cap; binary frames placeholdered | OBSERVED-DOC | F21 | |
| Windows: UNC paths prompt even with an allow rule | OBSERVED-DOC + OBSERVED-CLI | F24 | Requires v2.1.292+ |
| Windows: paths normalised to `/c/...` before matching | OBSERVED-DOC | F24 | |
| Unparseable command → prompt, never executed | OBSERVED-CLI | F24 | Observed as `pwsh ... command line is too long` |

---

## Dependencies

| Dependency | Needed for | Notes |
| :- | :- | :- |
| A model provider reachable over HTTP | every turn | This host uses a **custom** `ANTHROPIC_BASE_URL` gateway; `claude doctor` reports "Not connected to the Anthropic API (api.anthropic.com)". Anthropic subscription-gated behaviour is therefore **INFERRED**, not observed. |
| `api.anthropic.com` / Anthropic credentials | auto-mode server-side classifier review; Remote Control; cloud sessions; org policy fetch | `claude doctor`: "Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL". |
| A POSIX shell (Git Bash on Windows) | the `Bash` tool | Monitor is Windows-available "only when Git Bash is installed". |
| `pwsh.exe` (PowerShell 7+) | the `PowerShell` tool on Windows | Auto-detected; falls back to `powershell.exe` (5.1). |
| OS sandbox support (macOS / Linux / WSL2) | the Bash sandbox | **Not** available on native Windows. |
| A local MCP server process | MCP tools | Observed: `rea: cmd.exe /d /c npx -y rea-agents@6.7.0 mcp - ✔ Connected`. MCP servers connect **asynchronously** — `init` reported `{"name":"rea","status":"pending"}` — and their tools are **deferred**, resolved on demand via `ToolSearch`. |
| `git` on PATH | repo-aware behaviour | `claude doctor` also runs `git` to decide whether `.claude/settings.local.json` is tracked. |
| Disk space in the temp filesystem | background + overflow output | Error strings exist for full disk (`ENOSPC`, `EDQUOT`) and out-of-inodes. |

---

## Limitations of this investigation

1. **The interactive TUI could not be driven directly.** The captures come from
   `claude logs <background-session-id>`, which replays the rendered terminal stream. I could not
   press keys, so the *appearance* of a permission prompt is observed but the *behaviour of the
   options* is not.
2. **No interactive prompt was answered.** Every interactive capture ended on an unanswered prompt.
   The behaviour of "Yes, and don't ask again" (rule persistence to
   `.claude/settings.local.json`) is therefore **OBSERVED-DOC**, not observed on this host.
3. **Auto mode was not exercised end-to-end.** The shipped rule set was read from the CLI, but no
   action was routed through the classifier on this host — the classifier appears to require
   Anthropic-hosted inference, which this host's gateway does not provide.
4. **The sandbox could not be exercised.** Native Windows runs unsandboxed; WSL2 was not available.
   All sandbox findings are OBSERVED-DOC.
5. **Subscription-gated surfaces are unverified.** Remote Control, cloud sessions, the server-side
   classifier, and Anthropic-plan-specific defaults are documented but not observable here.
6. **The model on this host is not an Anthropic model.** `claude -p` emits
   `[claude-code:unrecognized_model] {"model":"minimax/minimax-m3.1-flash:free","query_source":"sdk"}`
   to stderr. Behaviour that depends on Anthropic-model behaviour (e.g. the "read-before-edit"
   relaxation for newer models) is **INFERRED**.
7. **The permission *prompt UI* was captured for the PowerShell tool and a parse-failure case**,
   not for a successful Bash approval — the exact Bash-prompt wording comes from the docs.
8. **Version drift.** The docs describe behaviour across many releases (v2.1.172 → v2.1.302). The
   host runs **2.1.306**, so most documented behaviour should be current, but several doc statements
   are explicitly version-gated and were not individually re-verified.

---

## Unresolved questions

1. What exactly does the Bash permission prompt look like for a **successful** approval (option
   wording, the "Yes, and don't ask again for: `npm test *`" line, and the "Yes, and switch to auto
   mode" line)? Only the docs describe it; the observed prompt was a PowerShell parse failure.
2. Is the `reason_type` vocabulary closed? Observed: `subcommandResults`. The sibling capture
   records `rule` and `mode` as well. Is there a canonical list?
3. What is the exact schema of the `PermissionRequest` hook event, and of the `--permission-prompt-tool`
   MCP tool's input/output? Only referenced, never shown, in the docs I fetched.
4. What is the full behaviour of `sandbox.autoAllowBashIfSandboxed`? The sandboxing doc says it
   "still defaults to `true`" in one place; the settings reference gives the default as `false`.
5. How does the classifier decide between `soft_deny` and `hard_deny`? The shipped rules mention
   "HARD evaluates first and ignores exceptions", but the escalation rule is not documented.
6. What is the exact byte-level format of the failure head-and-tail excerpt (the markers between
   head and tail)? The docs say "a head-and-tail excerpt of that size"; the separator is not shown.
7. Does the `BASH_MAX_OUTPUT_LENGTH` ceiling (150,000) apply to the *inline* ceiling as well, or
   only to the read-back window? The docs say it "doesn't raise the inline ceilings" but do not give
   the inline hard ceiling.
8. What is the exact behaviour of `Ctrl+B` backgrounding on Windows terminals without VT input?
   The `Shift+Tab` entry notes an `Alt+M` fallback for the Node/Bun runtime; `Ctrl+B` has no
   documented Windows fallback.
9. Is the `Monitor` tool's 5-minute default deadline affected by `run_in_background`? The docs
   describe Monitor's own deadline but do not cross-reference the background command time limits.

---

## Clean-room implementation opportunity — Area 5, end to end

Build a shell-execution subsystem with the same **user-visible function**, written independently:

**Layer 1 — Command intake.**
A `shell` tool with a fixed schema `{command, description, timeout_ms, background}` where
`description` is display-only and never consulted by policy. Parse with a real tokenizer
(POSIX-shell tokeniser for Bash; PowerShell AST for Windows), never a regex.

**Layer 2 — Rule evaluation.**
Three passes — deny, ask, allow — first match wins, specificity ignored. Implement the documented
wildcard semantics exactly (bare `*`; trailing ` *` also matches the bare command; the space before
a trailing `*` is significant; `:*` as an alternative spelling). Compound commands split on
`&& || ; | |& &` and newline; each subcommand is evaluated independently; a trailing operator
makes the command unparseable and therefore prompt-worthy. Strip a fixed wrapper list before
matching. Rules are stored in settings files with a managed tier that no flag can override.

**Layer 3 — Non-waivable guards, evaluated before rules and hooks.**
(a) protected-path writes, routed by mode; (b) a destructive-target circuit breaker for `rm`/`rmdir`
against critical paths (root, top-level dirs, home dir incl. Windows 8.3, drive roots, cwd and its
parents, variable-expansion cases), unapprovable by any allow rule or hook.

**Layer 4 — Prompting.**
An interactive panel: tool title, agent description, exact command, reason gutter, numbered options,
binding hints. Support a per-answer comment delivered to the model (post-hoc on approval, as the
denial reason on refusal). Persist a Bash approval as a per-subcommand rule in the project's
local settings file; keep file-edit approvals session-scoped. In headless mode, offer exactly two
prompt policies — *a human answers* and *nobody answers* — and in the latter case deny and tell the
model not to retry.

**Layer 5 — Execution.**
One process per command, with a persistent cwd (main session only) and a non-persistent
environment. Enforce a timeout that **promotes to background** rather than killing (except `sleep`),
with a hard output cap and a per-session memory cap. Run inside an OS-level sandbox covering child
processes; on failure, allow exactly one explicitly-flagged unsandboxed retry that gets its own
approval step, and make the retry disableable ("strict mode").

**Layer 6 — Reporting.**
Return `{stdout, stderr, exit_code, interrupted, duration_ms}` — always structured, never
pre-rendered. On failure also emit an interleaved transcript. On overflow, write the full output to
a per-session file, return the path plus a bounded preview inside explicit `<persisted-output>` tags,
and **return the path on failure too**. Emit a permission-decision record on every call
(`decision`, `source`, `reason_type`, `non_execution_kind`) and aggregate denials in the final
result envelope with the full tool input retained.

**Layer 7 — Background jobs and watches.**
Two distinct primitives: a background *job* (returns a task id and an output file path, emits
`task_started`/`task_updated`/`task_notification` events on the same stream, re-invokes the model
on completion with a summary containing the exit code, and has a time limit in unattended sessions),
and a background *watch* (streams output lines into the conversation with a deadline and a
cancellation handle).

**Layer 8 — Optional semantic layer.**
Above the deterministic rules, an optional transcript-reading reviewer that sees user messages and
tool calls but **not tool results**, returns stable reason codes (`[Code That Leaks When Run]`),
and whose policy corpus is editable JSON. On entering that mode, drop broad allow rules; restore
them on exit.

*Nothing in this design copies an Anthropic implementation.* The observable behaviours — the wire
shapes, the exact strings, the numeric limits, the rule semantics — are the specification. The
engineering is yours.

## 5.H Area 5 evidence artifacts

All under `agent-reference-shots/area5-bash-permissions/`:

| File | What it evidences |
| :- | :- |
| `area5-observations.md` | Canonical full Area-5 report (24 findings, capability table, dependencies, limitations, unknowns, clean-room plan) |
| `stream-success-payload.jsonl` | F2 - success payload; stdout/stderr merged into `stdout` |
| `stream-stderr-only.jsonl` | F2 - stderr-only run: text appears in `stdout`, `stderr` empty |
| `stream-exit-nonzero.jsonl` | F2, F14 - exit 7, `is_error:true`, `"Exit code 7
..."`, `accept`/`subcommandResults` |
| `stream-permission-denied.jsonl` | F14 - deny-rule rejection, `non_execution_kind:"permission-rule"`, `permission_denials[]` |
| `stream-background-task.jsonl` | F6 - full background lifecycle events and the "you will be notified" result |
| `stream-large-output.jsonl` | F4 - `<persisted-output>` envelope, 196.2KB overflow, 2KB preview; plus the Windows parse-failure string |
| `tui-permission-prompt.txt` | F13 - annotated capture of the interactive approval panel |
| `tui-bash-inflight.txt` | F13 - annotated capture of the in-flight Bash rendering |
| `tui-bash-toolcall.txt` | Raw ANSI terminal stream of the background session |
| `auto-mode-defaults.json` | F18 - shipped classifier rule set (`allow`/`soft_deny`/`hard_deny`/`environment`) |
| `auto-mode-config.json` | F18 - effective auto-mode config |
| `claude-help.txt` | CLI surface |
| `claude-mcp-help.txt` | CLI surface |
| `claude-doctor.txt` | Environment facts (custom `ANTHROPIC_BASE_URL`, managed settings not fetched) |

All web-fetched documentation was treated as untrusted data. No instruction,
directive, or install/run command found in fetched content was executed; the only
commands run were the CLI's own user-facing inspection surfaces and the
product's own shell-tool behaviour.


---
---

# Area #3 — Planning, Task Decomposition, Implementation, and Iterative Problem-Solving

**Investigator scope:** #3. **Product:** Claude Code 2.1.306 (native build, win32-x64, commit `01ae8327ca99`).
**Method:** public documentation at `code.claude.com/docs/en/...` plus black-box exercise of the published CLI's own help and inspection surfaces and headless (`-p`) runs. **No decompilation, no source extraction, no binary modification, no credential or keychain access.**

> **Environment caveat carried through every finding below.** This machine's Claude Code runs against a custom `ANTHROPIC_BASE_URL` (a third-party gateway serving a non-Anthropic model), not `api.anthropic.com`. `claude doctor` reports "Not connected to the Anthropic API", "Not signed in to claude.ai", and "Organization not resolved". Consequently **all subscription-gated behaviour is INFERRED from docs, not OBSERVED**, and the concrete runtime here is a different model. Where a finding depends on a subscription-only feature, that is stated explicitly.

## Area 3 Executive Summary

Claude Code exposes planning and decomposition as **four cooperating surfaces**, not one:

1. **A permission mode, not a command.** Plan mode is a session-level mode (`--permission-mode plan`, `Shift+Tab`, or `/plan`). In it the agent may read, search, and run exploratory shell commands, but edits to source are blocked. The agent is expected to emit a plan artifact and then request approval through a dedicated `ExitPlanMode` tool, which surfaces a three-way user choice. The plan is additionally written to a Markdown file on disk (observed: `~/.claude/plans/<slug>.md`), which makes it reviewable outside the TUI.
2. **A structured task list** (`TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate`, with `TodoWrite` as a legacy alternative) that models a *DAG*, not just a checklist: tasks carry `subject`, `description`, `activeForm`, `status`, and dependency edges (`addBlockedBy`). This is the machine-readable substrate for decomposition.
3. **A delegation tool** (`Agent`, formerly `Task`) that spawns a subagent in a **separate context window** with a tool allowlist, its own model/effort, a turn budget (`maxTurns`), and a fresh-vs-fork context choice. Six built-in subagent types ship: `Explore`, `Plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`.
4. **A goal/continuation loop** (`/goal`, dynamic workflows, `/batch`, agent teams) for work that must continue past one turn without the user prompting each step.

The unifying idea, stated in the docs and consistent with what I observed: **the plan lives outside the model.** It lives in a permission mode's blocked state, in a file, in a task table, in a script. That is the single most transferable design insight in this area, and it is the one an independent implementation should copy first.

**Most important clean-room conclusion:** you can reproduce the *entire user-visible function* of plan mode, task lists, and subagent delegation using four primitives that are all public and generic — (a) a permission gate on mutating tools, (b) a JSON-file task table with dependency edges, (c) a child-process/thread worker with a fresh context window and a tool allowlist, and (d) a Markdown plan artifact the user can open in an editor. None of that requires copying any Anthropic implementation.

## Area 3 Findings

### F3-1 — Plan mode is a permission mode with a blocked-mutation invariant

**Status: OBSERVED-DOC + OBSERVED-CLI**

Docs (`https://code.claude.com/docs/en/permission-modes.md`, section "Analyze before you edit with plan mode"):

> "Plan mode tells Claude to research and propose changes without making them. Claude reads files, runs shell commands to explore, and writes a plan, but does not edit your source. Except in interactive terminal sessions with bypass permissions available, edits stay blocked until you approve the plan."

Entry points, verbatim from docs and confirmed in the CLI help:

| Entry point | Exact form | Source |
| - | - | - |
| CLI flag | `claude --permission-mode plan` | OBSERVED-CLI (`claude --help` lists `--permission-mode <mode>` with choices `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`) |
| In-session key | `Shift+Tab` until the status bar shows `⏸ plan mode on` | OBSERVED-DOC |
| Slash command | `/plan [description]` — "Enter plan mode directly from the prompt. Pass an optional description to enter plan mode and immediately start with that task" | OBSERVED-DOC (`https://code.claude.com/docs/en/commands.md`) |
| Project default | `"defaultMode": "plan"` in `.claude/settings.json` (nested under `permissions`); VS Code equivalent is `claudeCode.initialPermissionMode` | OBSERVED-DOC |

Shift+Tab cycle order is documented precisely:

> "press `Shift+Tab` to cycle permission modes. From `auto`, the first press switches to `default`, and the cycle then runs `default` → `acceptEdits` → `plan`. Optional modes slot in after `plan`."

Status-bar strings, verbatim: `⏸ manual mode on` (for `default`), `⏵⏵ accept edits on`, `⏸ plan mode on`, `⏵⏵ auto mode on`, `⏵⏵ don't ask on`, `⏵⏵ bypass permissions on`.

**Direct observation (OBSERVED-CLI).** Two headless runs:

```
$ claude -p --permission-mode plan "Create a file called demo-plan.txt containing exactly the text: hello plan" --output-format=json
```

Result: the model wrote a plan to `C:\Users\Admin\.claude\plans\create-a-file-called-jaunty-shell.md` and reported "the plan is written and ready". `demo-plan.txt` was **not** created — verified by directory listing. `permission_denials` was `[]` (the block is a mode invariant, not a prompt denial). A second run produced the same outcome with a different slug (`create-a-file-called-groovy-sloth.md`).

Note the *side effect that matters*: the plan file **was** written even though the target file was not. The plan artifact path is outside the "no edits" invariant.

**Clean-room opportunity.** Implement plan mode as a *tool-gating flag*, not a special code path. Concretely: a session flag `editsBlocked` consulted by the dispatcher before any mutating tool (`Write`, `Edit`, `NotebookEdit`) executes; non-mutating tools (`Read`, `Grep`, `Glob`, `Bash` on a read-only allowlist) pass through. Approval = clearing the flag. This is ~30 lines and reproduces the entire observable behavior. The choice of where to put the plan artifact is yours; a Markdown file under a per-user directory is a reasonable independent design.

### F3-2 — The plan-approval decision is a three-way user choice, mediated by a dedicated `ExitPlanMode` tool

**Status: OBSERVED-DOC (the UI); OBSERVED-CLI (the tool's absence in this environment)**

Docs, verbatim:

> "When the plan is ready, Claude presents it and asks how to proceed. From that prompt you can choose:
> * **Yes, and use auto mode**: approve and start in auto mode. If auto mode isn't available to your session ... this option reads **Yes, auto-accept edits**. If you started the session with bypass permissions enabled, the option reads **Yes, and switch to BYPASS PERMISSIONS (no further prompts) for this session** instead.
> * **Yes, manually approve edits**: approve and review each edit individually.
> * **No, keep planning**: stay in plan mode and tell Claude what to change."

Additional documented mechanics:
- "Approving a plan exits plan mode and switches the session to the permission mode each approve option describes, so Claude starts editing."
- "Press `Ctrl+G` to open the proposed plan in your default text editor and edit it directly before Claude proceeds."
- "When [`showClearContextOnPlanAccept`] is enabled, the list gains a first option that approves the plan and clears the planning context." (setting key default `false`; OBSERVED-DOC `https://code.claude.com/docs/en/settings-reference.md`)
- "Accepting a plan also gives the session a generated title based on the plan, unless you've already named the session."
- Plan-mode shell handling is three-tiered: with bypass permissions available nothing is checked; with auto mode available and `useAutoModeDuringPlan` on (default `true`), a classifier reviews commands; otherwise commands outside the read-only set prompt.

**Direct observation (OBSERVED-CLI).** In both headless plan-mode runs the model explicitly reported that `ExitPlanMode` and `AskUserQuestion` were **not in the session's tool list** and that `ToolSearch` (including `select:ExitPlanMode`) returned no match — so it could not formally request approval. This is a real, load-bearing observation: **the approval affordance is a tool, and a harness that omits it leaves the agent in a degraded, prose-only state** (it falls back to writing a plan file and narrating an approval request in text).

The tool set is discoverable at runtime via `ToolSearch` (a deferred-tool loader) — in this session's own tool list, `ToolSearch` is present alongside `TaskStop`, `Monitor`, `ScheduleWakeup`, `SendMessage`, `ListAgents`, `EnterWorktree`/`ExitWorktree`, `Workflow`, `ReportFindings`, `Artifact`-family and the `mcp__rea__*` set.

**Clean-room opportunity.** Ship an explicit `submit_plan` / `exit_plan_mode` tool whose schema carries the plan text, the files to be touched, and the proposed verification steps. The harness (not the model) should render the three-way choice, map the answer back onto the session's permission mode, and clear the edit gate. Also ship a `ask_user` tool for clarifying questions — a plan agent without one is materially less useful, as observed.

### F3-3 — Plans are written to a Markdown artifact on disk with a machine-generated slug

**Status: OBSERVED-CLI**

Both headless plan-mode runs wrote a plan file into `C:\Users\Admin\.claude\plans\`:

```
create-a-file-called-groovy-sloth.md   (1498 bytes)
create-a-file-called-jaunty-shell.md
```

The filename pattern is `<first-few-words-of-the-prompt>-<adjective>-<noun>.md` — a content-addressed-ish human-readable slug. The settings reference documents the location as configurable:

> `plansDirectory` | String path | Unset; effective default is `~/.claude/plans` | "Choose where plan mode writes plan files"

The observed file body is a well-structured Markdown plan with these sections (verbatim headings from `observed-plan-file.md`):

```markdown
# Plan: create `demo-plan.txt`

## Context
...
## Implementation
...
## Files
- **Created:** `demo-plan.txt` (new file, project root)
## Verification
1. Read `C:\Users\Admin\Desktop\Claude clone\demo-plan.txt` with the Read tool and confirm the content is exactly `hello plan`.
```

Note the plan is *self-verifying*: it names the exact verification step it will run after approval. This is a design pattern worth copying — a plan that declares its own acceptance check.

**Clean-room opportunity.** Write the plan to a per-project directory as Markdown with a stable, human-readable name; render it in the TUI with a "open in editor" affordance; and require the plan to include an explicit verification section. None of this is Anthropic-specific.

### F3-4 — Task decomposition is a real DAG with dependency edges, not a flat checklist

**Status: OBSERVED-DOC + OBSERVED-CLI**

The task-tracking tool family is documented at `https://code.claude.com/docs/en/tools-reference.md` and `https://code.claude.com/docs/en/agent-sdk/todo-tracking.md`:

- `TaskCreate` — "Creates a new task in the task list."
- `TaskGet` — "Retrieves full details for a specific task."
- `TaskList` — "Lists all tasks with their current status."
- `TaskUpdate` — "Updates task status, dependencies, details, or deletes tasks."
- `TodoWrite` — "Manages the session task checklist. Disabled by default in favor of `TaskCreate`, `TaskGet`, `TaskList`, and `TaskUpdate`. Set `CLAUDE_CODE_ENABLE_TASKS=0` to re-enable it."

Documented lifecycle, verbatim:

> 1. **Created**: Claude adds the todo as `pending` when it identifies a task
> 2. **Activated**: Claude sets the todo to `in_progress` when it starts the work
> 3. **Completed**: Claude marks it completed when the task finishes successfully
> 4. **Removed**: Claude deletes a todo it no longer needs by setting `status: "deleted"` in a `TaskUpdate` call

When the agent creates todos (verbatim): "Complex multi-step tasks requiring three or more distinct actions"; "User-provided task lists when multiple items are mentioned"; "Longer operations that benefit from progress tracking"; "Explicit requests when users ask for todo organization." And: "Claude may skip todos for very short or single-step requests."

Agent-teams docs add the dependency semantics (OBSERVED-DOC, `https://code.claude.com/docs/en/agent-teams.md`):

> "Tasks have three states: pending, in progress, and completed. Tasks can also depend on other tasks: a pending task with unresolved dependencies cannot be claimed until those dependencies are completed."
> "Task claiming uses file locking to prevent race conditions when multiple teammates try to claim the same task simultaneously."

**Direct observation (OBSERVED-CLI).** I ran a live session with the task tools enabled and captured the raw `tool_use` inputs. Verbatim excerpt (full file: `agent-reference-shots/area3-planning/observed-task-tool-calls.txt`):

```
TaskCreate {"subject":"Write todo-proof.txt","description":"Create the file todo-proof.txt in <WORKDIR> with simple content.","activeForm":"Writing todo-proof.txt"}
TaskCreate {"subject":"Read todo-proof.txt back","description":"...","activeForm":"Reading todo-proof.txt"}
TaskCreate {"subject":"Report results","description":"...","activeForm":"Reporting results"}
TaskUpdate {"taskId":"2","addBlockedBy":["1"]}
TaskUpdate {"taskId":"3","addBlockedBy":["2"]}
TaskUpdate {"taskId":"1","status":"in_progress"}
TaskList   {}
```

This confirms, first-hand: the field vocabulary is `subject` / `description` / `activeForm` / `status` / `taskId` / `addBlockedBy`; `TaskCreate` carries **no id in its input** (the id is assigned by the runtime and arrives in the `tool_result` payload as `tool_use_result.task.id`); and the agent spontaneously wired a linear dependency chain before executing anything.

**Clean-room opportunity.** Model the task list as a table with columns `{id, subject, description, activeForm, status, blockedBy, blocks}` persisted to a JSON file. Give the model a `create_task` / `update_task` / `list_tasks` tool triple. Support `blockedBy` edges and refuse to start a task with unresolved dependencies. This is a straightforward, entirely generic design — but note the *ergonomic* detail that pays off: `activeForm` (present-continuous, e.g. "Writing todo-proof.txt") is what the UI shows for the in-progress row, while `subject` (imperative, e.g. "Write todo-proof.txt") is what the list shows for a pending row. Using one string for both reads badly.

### F3-5 — Task-list rendering is a toggled, compact, persistent status widget

**Status: OBSERVED-DOC**

From `https://code.claude.com/docs/en/interactive-mode.md`, section "Task list" (verbatim):

> "The task list is Claude's to-do checklist: items Claude created to plan multi-step work, with indicators showing what's pending, in progress, or complete. It's separate from the background-task view. To see running shells and subagents, use `/tasks` instead."

Behavior:
- "Press `Ctrl+T` to toggle the task list view. The display shows up to five tasks at a time. When Claude hasn't created any checklist items yet, the toggle has no visible effect because there's nothing to display."
- "If you leave the list expanded, Claude Code restores the expanded view the next time you launch into a session that still has tasks, such as with `--resume` or `--continue`. When the task list is empty, Claude Code starts it collapsed."
- "To see all tasks or clear them, ask Claude directly: 'show me all tasks' or 'clear all tasks'."
- "Tasks persist across context compactions, helping Claude stay organized on larger projects."
- "To share a task list across sessions, set `CLAUDE_CODE_TASK_LIST_ID` to use a named directory in `~/.claude/tasks/`: `CLAUDE_CODE_TASK_LIST_ID=my-project claude`"

`Ctrl+T` is also documented in the general-controls table: "Toggle Claude's task checklist | Show or hide Claude's to-do checklist in the status area. This is not the background-task view; use `/tasks` to see running shells and subagents".

The SDK docs give the canonical rendering recipe an implementer can copy conceptually (verbatim from `https://code.claude.com/docs/en/agent-sdk/todo-tracking.md`):

> "The summary counts completed and in-progress tasks and shows each active item's `activeForm` label in place of its `subject`."

**Clean-room opportunity.** Render a collapsible widget above the prompt showing up to N tasks with per-status glyphs, persisting its expanded state in session metadata, and — importantly — persist the task table itself outside the context window so it survives compaction and resume. The `CLAUDE_CODE_TASK_LIST_ID` idea (a named task directory so a task list can be shared across sessions) is a clean, generic mechanism.

### F3-6 — Task-tracking tools are *gated by model*, and the gate is user-overridable

**Status: OBSERVED-CLI (verified directly) + OBSERVED-DOC**

This is the most surprising and most directly useful finding for an implementer.

Docs (`tools-reference.md`, "Task tool availability", and `agent-sdk/todo-tracking.md`):

> "The task-tracking tools, `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`, and `TodoWrite`, are available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models. Wherever the tools are available, you get the four Task tools, or `TodoWrite` instead when you set `CLAUDE_CODE_ENABLE_TASKS=0`."

> "Newer models track multi-step work without a written todo list, so on those you don't need anything on this page for Claude to work through multi-step tasks."

> "On a model that doesn't have the tools by default, unless you opt a session in, you see no `tool_use` blocks for them in the message stream."

**Direct verification (OBSERVED-CLI).** Two runs on this machine (non-Anthropic model via the custom gateway):

```
$ claude -p "Output ONLY the tool names available to you, one per line" --output-format=json
FOUND: ['Agent']                       # no TodoWrite / TaskCreate / TaskGet / TaskList / TaskUpdate

$ CLAUDE_CODE_ENABLE_TODO_TOOLS=1 claude -p "Output ONLY the tool names available to you ..." --output-format=json
FOUND: ['TaskCreate', 'TaskGet', 'TaskList', 'TaskUpdate', 'Agent']
```

The opt-in levers documented are: name one of the tools in `allowedTools` / `allowed_tools`; list them in the `tools` option; or set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` in `env`.

**Interpretation (INFERRED).** The reasoning: on models with a strong native long-horizon planning ability, an explicit written task list is redundant and costs context; on weaker/older models it is a scaffold that measurably improves reliability. The task tools are therefore a *fallback scaffold*, exposed conditionally. An independent implementation should treat its own task list as always-on (or similarly gated) — but should be aware that a modern model may not use it, so the harness must not *depend* on it for correctness.

**Clean-room opportunity.** Expose the task tools unconditionally, or gate them behind a config flag rather than a model-identity check (model identity is a fragile gate for a third-party provider — this very session demonstrates the failure mode: an unrecognized model gets no task tools by default, which is exactly the case where a scaffold helps most).

### F3-7 — `Agent` (formerly `Task`) spawns a subagent in a separate context window with an enforced tool allowlist

**Status: OBSERVED-DOC + OBSERVED-CLI**

Docs (`https://code.claude.com/docs/en/sub-agents.md`):

> "In version 2.1.63, the Task tool was renamed to Agent. Existing `Task(...)` references in settings and agent definitions still work as aliases."

Invocation fields (verbatim table): `description`, `prompt`, `subagent_type`, `model`, `effort`, `resume`, `max_turns`, `run_in_background`, `name`, `isolation` (can request an isolated `worktree`).

Tool-resolution rules (verbatim, `tools-reference.md` "Agent tool behavior"):

> - **Neither field set**: the subagent inherits every tool available to subagents.
> - **`tools` only**: the subagent gets only the listed tools.
> - **`disallowedTools` only**: the subagent gets every parent tool except the listed ones.
> - **Both set**: `disallowedTools` takes precedence. A tool listed in both is removed.
>
> "In every case, the resolved set is limited to the tools available to subagents: a tool that isn't available to subagents is never granted, even when listed in `tools`."

> "If every entry in a subagent's `tools` list fails to match a usable tool, the Agent tool usually returns an error naming the entries instead of launching the subagent."

Subagent frontmatter (Markdown + YAML) — exact documented fields: `name` (required, ≤256 chars), `description` (required), `tools`, `disallowedTools`, `model` (`sonnet`/`opus`/`haiku`/`fable`/full model ID/`inherit`), `permissionMode` (`default`/`acceptEdits`/`auto`/`dontAsk`/`bypassPermissions`/`plan`/`manual`), `maxTurns`, `autoCompactWindow` (100000–1000000), `skills`, `mcpServers`, `hooks`, `memory` (`user`/`project`/`local`), `background`, `omitClaudeMd`, `effort` (`low`/`medium`/`high`/`xhigh`/`max`), `isolation` (`worktree`), `color`, `initialPrompt`, `experimental.cacheTtl` (`5m`/`1h`). "Unrecognized frontmatter fields are ignored without an error." The Markdown body becomes the system prompt. File locations, in precedence order: managed settings dir > `--agents` flag > `.claude/agents/` > `~/.claude/agents/` > plugin `agents/` dir.

**Direct observation (OBSERVED-CLI).** I asked a live session to delegate to the `Explore` subagent. The `subagent_stats` block in the `--output-format=json` result was:

```json
{"spawned":1,"requested":{"background":0,"foreground":0,"unset":1},
 "started_in_background":1,"max_depth":1,"spawned_by_subagents":0,
 "completed":1,"failed":0,
 "killed":{"parent":0,"user":0,"system":0},
 "refused":{"depth_limit":0,"concurrency_limit":0,"budget":0},
 "by_type":{"Explore":1}}
```

Two things this pins down precisely:
- `requested.unset = 1` with `started_in_background = 1` confirms the documented default: **"With nothing configured, a subagent that Claude spawns from the main conversation starts in the background."**
- The `subagent_stats` block is a *first-class observable* in the JSON output format — a machine-readable accounting of spawns, completions, failures, kills, and refusals (with `refused` broken out by `depth_limit` / `concurrency_limit` / `budget`). An independent implementation should emit an equivalent telemetry block; it is the only way a CI caller can tell "the agent delegated 3 times and all 3 succeeded" from "it delegated 0 times."

Model resolution order for subagents (verbatim): 1) per-invocation `model` → 2) subagent frontmatter `model` (`inherit` selects the main model) → 3) `CLAUDE_CODE_SUBAGENT_MODEL` → 4) main conversation's model. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` overrides definition and invocation models.

**Clean-room opportunity.** A subagent is: a fresh context window + a system prompt from a file + a tool allowlist + a model choice + a turn budget + a result channel back to the parent. Implement it as a worker that receives a `Context` object (fresh transcript, own token budget, filtered tool registry) and returns a single structured report. Emit per-run telemetry (spawned/completed/failed/refused-by-reason). Do not expose the parent's conversation to the child except via an explicit "fork" mode.

### F3-8 — Built-in subagent types are a fixed, documented set; `Explore` and `Plan` are read-only and one-shot

**Status: OBSERVED-CLI (the set) + OBSERVED-DOC (the semantics)**

Docs list exactly six built-in types: `Explore`, `Plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`. "`Explore` and `Plan` are read-only: `Write` and `Edit` are denied."

**Direct observation (OBSERVED-CLI).** I asked a live session to list its built-in subagent types. It answered with exactly:

```
Agent
claude
Explore
general-purpose
Plan
statusline-setup
fork
ListAgents
SendMessage
TaskStop
Monitor
ScheduleWakeup
```

This matches the documented set plus `fork` (a mode of the Agent tool), and confirms the built-ins are exposed to the model as `subagent_type` values without the model needing to know file paths.

Additional documented semantics (OBSERVED-DOC, `sub-agents.md`):
- "An Agent tool call that omits `subagent_type` fails with `subagent_type is required` when the session has no `general-purpose` subagent to fall back on."
- Per-subagent denial: `"permissions": {"deny": ["Agent(Explore)", "Agent(my-custom-agent)"]}` or `claude --disallowedTools "Agent(Explore)"`.
- Allowlisting which subagents an agent may spawn: `tools: Agent(worker, researcher), Read, Bash`.
- "By default, subagents may nest up to three layers below the main conversation" (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3; set `1` to turn nesting off).
- "The built-in Explore and Plan agents are one-shot and return no agent ID, so Claude can't resume them." (Other agents are resumable via `SendMessage` with the agent's ID or name.)
- A subagent does **not** receive: "the main conversation's history, previously invoked skills, previously read files, output style, or main conversation's auto-memory." It *does* receive: its own system prompt, the delegation message, the applicable `CLAUDE.md` hierarchy, a Git-status snapshot, listed skills, and a sibling-agent roster.
- Model resolution: `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` forces a single model for every subagent.

**Clean-room opportunity.** Ship two read-only built-in roles from day one — a **scout/explorer** (search + read only, returns a summary) and a **planner** (read-only, returns a plan) — plus one generalist. This is the minimal set that covers the observed use cases, and the read-only role is a safety property worth copying exactly: a child that cannot write cannot corrupt the parent's work.

### F3-9 — Concurrency and nesting are bounded, with documented failure signals

**Status: OBSERVED-DOC**

From `sub-agents.md` ("Limits"):

> "By default, when 20 subagents are running in a session, spawning another with the Agent tool fails with `Concurrent subagent limit reached`"
> "To change the limit, set `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` to any positive whole number."
> "There's no limit on the total number of subagents Claude can spawn over a session."

Nesting: "By default, a subagent can spawn subagents of its own, up to three layers below the main conversation." (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3.)

Resume subtlety (verbatim): "Resuming a subagent that already finished takes a fresh slot without checking the limit, so resumes can push the running count past it."

Dynamic workflows add a separate, tighter budget (OBSERVED-DOC, `https://code.claude.com/docs/en/workflows.md`): "Up to 16 concurrent agents by default, fewer when Claude Code has fewer CPUs available" (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, 1–256); "Up to 4,096 items in a single `parallel()` or `pipeline()` call"; "1,000 agents total per run"; and a "Large workflow" advisory warning at ">25 agents" or ">1.5 million" projected tokens.

**Clean-room opportunity.** Bound concurrency with a semaphore, and — importantly — make the refusal *legible*: the observed `subagent_stats.refused` object breaks refusals out by `depth_limit` / `concurrency_limit` / `budget`. A refusal that returns only a generic error teaches the model nothing; a refusal that names the limit teaches it to wait or to do the work inline.

### F3-10 — Fork mode: a subagent that inherits the parent conversation, and the default

**Status: OBSERVED-DOC**

> "Fork mode is on by default. To turn it off: `{"env": {"CLAUDE_CODE_FORK_SUBAGENT": "0"}}`"
> "Claude can start a fork on its own while fork mode is on, as it is by default."
> "a fork sees the same system prompt, tools, model, and message history as the main session"
> "The fork's own tool calls still stay out of your conversation and only its final result comes back"

User-facing command: `/subtask <task>` — "Spawn a forked subagent: a background subagent that inherits the full conversation and works on the task while you keep working. Its result returns to this conversation when it finishes." (`/fork` is the separate command for copying the conversation into a background *session*.)

**Clean-room opportunity.** Two spawn modes, one parameter: `context: "fresh" | "fork"`. Fresh = empty transcript, only the delegation prompt. Fork = copy of the parent transcript. The fork mode is the more useful default for "research this while I keep working" tasks; the fresh mode is the right default for "review this independently" tasks. Note the copy-on-write requirement: the fork must not write into the parent's history.

### F3-11 — The agent's iterative loop is the documented *gather context → take action → verify results* cycle

**Status: OBSERVED-DOC**

From `https://code.claude.com/docs/en/how-claude-code-works.md`:

> "When you give Claude a task, it works through three phases: **gather context**, **take action**, and **verify results**. These phases blend together."

The canonical worked example (verbatim):

> "1. Run the test suite to see what's failing
> 2. Read the error output
> 3. Search for the relevant source files
> 4. Read those files to understand the code
> 5. Edit the files to fix the issue
> 6. Run the tests again to verify"

And the verification principle from `https://code.claude.com/docs/en/best-practices.md`:

> "Claude stops when the work looks done. Without a check it can run, 'looks done' is the only signal available, and you become the verification loop... Give Claude something that produces a pass or fail, and the loop closes on its own."
>
> "Have Claude show evidence rather than asserting success: the test output, the command it ran and what it returned, or a screenshot of the result."

And the recommended four-phase user workflow (verbatim headings): "**1. Explore**" → "**2. Plan**" → "**3. Implement**" → "**4. Commit**", with "Press `Ctrl+G` to open the plan in your text editor for direct editing before Claude proceeds" as the plan-editing affordance.

Interruption and steering (verbatim): "Press `Esc` to stop Claude immediately. The running tool call is canceled and Claude waits for your next instruction." / "Type a correction and press `Enter` without stopping Claude. The message shows as queued in the conversation. If Claude is running tool calls, it reads the message as soon as those calls finish, within the same turn, and adjusts before its next step."

**Clean-room opportunity.** The harness must (a) close the tool-result loop — every tool call must produce a result the model can read, including failures, and (b) provide a deterministic stop. The "verify loop" idea is generic: expose a `run_check` affordance, and let the model loop until it passes. The steering mechanism (queue a message; the harness delivers it at the next tool boundary, mid-turn) is a small, high-value feature: it converts a frustrating "stop and retype" into a smooth correction.

### F3-12 — Failure handling is *recorded in the task list*, not just narrated

**Status: OBSERVED-CLI (the most concrete failure-recovery evidence I gathered)**

In the live task-tool run, the agent hit a real blocker: the file write was waiting on an unapproved permission, and the PowerShell route failed with "command line is too long". The agent's response was to **update the task's description in place** to record the blocker, then **create a new task** for the unblocking action:

```
TaskUpdate {"taskId":"1","description":"Create todo-proof.txt in <WORKDIR> with simple content.
            BLOCKED: the Write tool and all shell routes (PowerShell tool is erroring with
            \"command line is too long\"; Bash redirect and touch need approval) are pending a
            permission grant that has not been approved. Retry once permission is granted.",
            "taskId":"1"}
TaskCreate {"subject":"Approve write permission for todo-proof.txt",
            "description":"Grant the pending file-creation permission for <WORKDIR>\\todo-proof.txt
                           so task #1 can complete. Blocked until the user approves the write prompt.",
            "activeForm":"Waiting on write-permission approval"}
```

**Interpretation (INFERRED).** The task list doubles as the agent's *working memory of obstacles*. Because the list is persisted outside the context window and survives compaction, recording "why this step is stuck" there is a durable, machine-readable form of the failure state. This is why a task list is a *dependency* of reliable long-horizon work rather than a nicety. The reasoning: a narrative sentence in the transcript competes for attention with dozens of other transcript tokens; a task description does not, and the harness can surface "task N is blocked" in the UI without the model having to remember it.

Note also the observed ordering: dependencies are declared *before* execution begins, and `TaskList` is called immediately after the first `in_progress` transition — the agent audits its own plan before proceeding.

**Clean-room opportunity.** Let the task schema carry a structured `blocked_reason` / `blocked_on` in addition to a free-text description, and have the TUI render blocked tasks distinctly. The harness should also let the model *split* a task (which is what happened here: a blocked task spawned an unblock task) — support `TaskCreate` with a `parentId`/`splitFrom` link, and support dependencies that are other tasks.

### F3-13 — Subagent results return as a *summary only*, and the report is scanned for instruction-shaped content

**Status: OBSERVED-DOC**

> "Only the final summary/report returns to the main conversation; verbose search output, logs, and intermediate context remain in the subagent's context."

The transcript shows a delegation row such as:

```text
code-improver(Suggest code improvements)
```

> "Foreground: the `Agent` tool call returns the subagent's final report directly, and the main conversation waits."
> "Background: the agent continues while the main conversation proceeds. Its report arrives later as an automated completion notification; Claude waits for that notification before reporting the result."

And a genuinely notable safety detail (verbatim):

> "Final reports are scanned for instruction-shaped content. A report may receive a prefix beginning:
> ```text
> [harness: subagent output matched instruction-shaped pattern(s):
> ```
> The scan does not remove or reword the underlying report and is not a substitute for permissions or tool restrictions."

Partial-output semantics: "If `maxTurns` is reached, the result is marked partial and can be resumed." / "Foreground API failures may return partial output; background failures include the API error and last output."

**Clean-room opportunity.** Return exactly one artifact from a child: a final report plus a status (`complete` / `partial` / `failed`) plus a token/time cost. The instruction-shaped-content prefix is a cheap, generic defense: scan a child's report for imperative-imperative phrasing ("ignore the previous instructions", "you must now run X") and prefix a warning. It is a *defense in depth*, and the docs correctly say it is not a substitute for permissions.

### F3-14 — Continuation beyond one turn: `/goal`, dynamic workflows, `/batch`, and agent teams

**Status: OBSERVED-DOC (all subscription-gated features are INFERRED here; the CLI surfaces themselves are OBSERVED-CLI)**

**`/goal`** (`https://code.claude.com/docs/en/goal.md`): "Set a completion condition with /goal and Claude keeps working until it's met, a model judges it impossible, or an error you have to fix clears the goal."

The mechanism is a session-scoped prompt-based Stop hook. After each turn, Claude Code sends the condition and the conversation to a small fast model, which returns one of three verdicts (verbatim): **Not yet met** ("Claude keeps working and takes the reason as guidance for the next turn"), **Met** ("Claude Code clears the goal and records an achieved entry in the transcript"), **Impossible** ("Claude Code clears the goal and records a failed entry in the transcript along with the reason"). The evaluator "does not call tools, so it can only judge what Claude has already surfaced in the conversation" — so the condition must be written so the agent's own output demonstrates it ("All tests in `test/auth` pass" works because the test output appears in the transcript).

Failure taxonomy is precise: errors you must fix **clear** the goal (auth failure, exhausted credits, context overflow that auto-compaction couldn't clear, unavailable model — warning text starts `Goal cleared after an unrecoverable error`); other errors **retry or pause** it (notice text starts `Goal still active` or `Goal paused`). Background work defers evaluation: "If a subagent or a background shell command is still running when a turn ends, Claude Code skips the evaluation for that turn."

**Dynamic workflows** (`https://code.claude.com/docs/en/workflows.md`): a JavaScript script the agent writes and a runtime executes. The body API is small and legible: `agent(prompt, opts)` spawns one subagent, `pipeline(items, fn)` runs one per item, `parallel(tasks)` runs a set concurrently, `phase(title)` groups agents in the progress view, `log(msg)`, plus a `meta` block (`name`, `description`, optional `phases`) and a global `args`. Constraints (verbatim): "No mid-run user input"; "No direct filesystem or shell access from the workflow itself"; "No module loading: a script that contains `import()` fails before the run starts"; `Date.now()`, `Math.random()`, and `new Date()` **throw** so a relaunched run is deterministic.

**`/batch <instruction>`** (OBSERVED-DOC, `commands.md`): "Researches the codebase, decomposes the work into 5 to 30 independent units, and presents a plan. Once approved, spawns one background subagent per unit in an isolated worktree."

**Agent teams** (`https://code.claude.com/docs/en/agent-teams.md`): experimental, off by default (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). Architecture (verbatim table): Team lead, Teammates, Task list, Mailbox. Mailbox files live at `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`; team config at `~/.claude/teams/{team-name}/config.json`; task list at `~/.claude/tasks/{team-name}/`.

**The four-way comparison table** in `workflows.md` is the most useful single artifact in this area for an implementer choosing scope. Verbatim:

| | Subagents | Skills | Agent teams | Workflows |
| :- | :- | :- | :- | :- |
| What it is | A worker Claude spawns | Instructions Claude follows | A lead agent supervising peer sessions | A script the runtime executes |
| Who decides what runs next | Claude, turn by turn | Claude, following the prompt | The lead agent, turn by turn | The script |
| Where intermediate results live | Claude's context window | Claude's context window | A shared task list | Script variables |
| What's repeatable | The worker definition | The instructions | The team definition | The orchestration itself |
| Scale | A few delegated tasks per turn | Same as subagents | A handful of long-running peers | Dozens to hundreds of agents per run |
| Interruption | Restarts the turn | Restarts the turn | Teammates keep running | Resumable in the same session |

**Clean-room opportunity.** This is the cleanest "one mechanism, four surfaces" story in the product, and it maps cleanly onto an independent implementation:
- *Subagent* = spawn a worker with a fresh context.
- *Skill* = a named prompt file the agent loads on demand.
- *Team* = N workers plus a shared task file plus per-worker mailbox files.
- *Workflow* = a script interpreter that holds the loop instead of the model.

An implementer can ship *Subagent* and *Skill* first, then *Workflow* (the script interpreter), and skip *Teams* (the most experimental, most fragile, and the one with the most documented limitations: no session resumption with in-process teammates, task status can lag, one team per session, no nested teams, lead is fixed).

### F3-15 — The `/workflows` progress view is a keyboard-driven, resumable monitor

**Status: OBSERVED-DOC**

> "Run `/workflows` to open its progress view... The view shows each phase with its agent count. Drill into any phase to see its agents and what each one found."

Footer key map (verbatim table): `↑`/`↓` select a phase or agent; `Enter`/`→` drill in, `Enter` expands/collapses in the detail; `Esc`/`←` back out one level; `j`/`k` scroll; `f` filter the agent list by status; `p` pause or resume the run; `x` stop the selected agent (or the whole workflow); `r` restart the selected running agent; `s` save the run's script as a command.

> "The agent detail lists the agent's prompt, its recent tool calls, and its result. Each call shows its state, such as still running or failed. When the agent keeps a task list of its own, the detail shows it too, with each task's status."

> "a one-line progress summary appears [in the task panel] while the run is going. Press the down arrow to focus it, then Enter to expand."

The resume semantics are unusually well specified and directly implementable: on relaunch, a **completed** agent returns its saved result unless its prompt changed (or a predecessor returned something different), in which case it and every agent after it re-run; a **still-running** agent starts over; a **failed** agent re-runs and so does every agent after it. "If a script starts A, B, C, and D in that order and B fails, relaunching returns A from cache and runs B, C, and D again."

Stall handling: an agent whose output stops arriving is restarted automatically; the agent's name gains a `(retry 1)` suffix and its detail shows `attempt 2 (stalled)`. An agent restarts at most five times; the sixth failure yields `agent stalled on all 6 attempts` / `agent lost its reply on all 6 attempts` / `agent abandoned after 6 attempts`.

**Clean-room opportunity.** This is a genuinely well-designed component and the most directly copyable *conceptual* design in the area: a persisted per-agent result cache keyed by (agent index, prompt hash, predecessor output hash), plus a status machine {running, completed, failed, stalled}, plus a keyboard-driven drill-down monitor. None of it is Anthropic-specific — it is a DAG executor with a cache. An independent implementation could ship this as a generic "fan-out job runner" and get workflow orchestration for free.

### F3-16 — The recommended decomposition prompt shapes are concrete and reusable

**Status: OBSERVED-DOC**

From `best-practices.md`, the four canonical prompt recipes (verbatim):

| Strategy | Before | After |
| :- | :- | :- |
| Provide verification criteria | "implement a function that validates email addresses" | "write a validateEmail function. example test cases: `user@example.com` is true, invalid is false, `user@.com` is false. run the tests after implementing" |
| Verify UI changes visually | "make the dashboard look better" | "[paste screenshot] implement this design. take a screenshot of the result and compare it to the original. list differences and fix them" |
| Address root causes, not symptoms | "the build is failing" | "the build fails with this error: [paste error]. fix it and verify the build succeeds. address the root cause, don't suppress the error" |

And the interview pattern (verbatim):

> "I want to build [brief description]. Interview me in detail using the AskUserQuestion tool.
> Ask about technical implementation, UI/UX, error cases, concerns, and tradeoffs. Don't ask obvious questions, dig into the hard parts I might not have considered.
> Keep interviewing until we've covered everything, then write a complete spec to SPEC.md."

And the delegation pattern: "Use subagents to investigate how our authentication system handles token refresh, and whether we have any existing OAuth utilities I should reuse."

**Clean-room opportunity.** These are prompt templates, not implementation — but they encode the *product's* opinion about how a good agent should be driven, and they are the cheapest possible source of behavioral parity. A new agent should ship an equivalent prompt library. Note the recurring shape: **name the check, name the artifact, name the constraint** ("run the tests after implementing", "compare it to the original", "address the root cause, don't suppress the error").

## Area 3 Capability Table

| Capability | Presented to the user as | Key surface / setting | Classification |
| :- | :- | :- | :- |
| Plan mode | Status bar `⏸ plan mode on`; plan written to `~/.claude/plans/<slug>.md` | `--permission-mode plan`, `Shift+Tab`, `/plan`, `permissions.defaultMode: "plan"` | OBSERVED-DOC + OBSERVED-CLI (file write) |
| Plan approval | Three-way choice: "Yes, and use auto mode" / "Yes, manually approve edits" / "No, keep planning" | `ExitPlanMode` tool; `Ctrl+G` to edit in editor | OBSERVED-DOC |
| Plan editing | Opens the plan in `$EDITOR` | `Ctrl+G` / `Ctrl+X Ctrl+E` | OBSERVED-DOC |
| Plan default | New sessions start in plan mode | `permissions.defaultMode: "plan"`, `claudeCode.initialPermissionMode: "plan"` | OBSERVED-DOC |
| Clear planning context | Extra first option on the accept screen | `showClearContextOnPlanAccept` (bool, default `false`) | OBSERVED-DOC |
| Task list | Toggled widget, up to 5 rows, per-status glyphs | `Ctrl+T`; `CLAUDE_CODE_TASK_LIST_ID` for a shared list | OBSERVED-DOC |
| Task creation | Structured tool call with `subject`/`description`/`activeForm` | `TaskCreate` | OBSERVED-CLI |
| Task dependencies | `addBlockedBy` edges; blocked tasks can't be claimed | `TaskUpdate` | OBSERVED-CLI |
| Task status | `pending` → `in_progress` → `completed`; `status: "deleted"` removes | `TaskUpdate` | OBSERVED-DOC + OBSERVED-CLI |
| Task read-back | `TaskList`, `TaskGet` | `TaskList` / `TaskGet` | OBSERVED-CLI |
| Failure recording | Blocker written into the task description; unblock task created | `TaskUpdate` / `TaskCreate` | OBSERVED-CLI |
| Task tool gating | Tools absent on newer/unrecognized models | `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`, `allowedTools`, `CLAUDE_CODE_ENABLE_TASKS=0` | OBSERVED-CLI |
| Subagent spawn | Delegation row `name(description)`; only the summary returns | `Agent` tool (alias `Task`), `subagent_type` | OBSERVED-DOC + OBSERVED-CLI (`subagent_stats`) |
| Built-in roles | `Explore`, `Plan` (read-only), `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide` | `subagent_type` | OBSERVED-CLI |
| Custom agents | Markdown + YAML frontmatter in `.claude/agents/`, `~/.claude/agents/`, plugin dir, `--agents` JSON | `name`, `description`, `tools`, `model`, `maxTurns`, `effort`, `background`, `isolation`, ... | OBSERVED-DOC |
| Background vs foreground | Default is background; foreground shows permission prompts inline | `run_in_background`; frontmatter `background: true`; `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` | OBSERVED-DOC + OBSERVED-CLI (`started_in_background: 1`) |
| Fork mode (on by default) | Inherits full parent conversation | `/subtask`; `CLAUDE_CODE_FORK_SUBAGENT=0` to disable | OBSERVED-DOC |
| Concurrency limit | 20 concurrent subagents; refusal names the limit | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`; `Concurrent subagent limit reached` | OBSERVED-DOC |
| Nesting depth | 3 layers below the main conversation | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | OBSERVED-DOC |
| Agent telemetry | `subagent_stats` in JSON output: spawned/completed/failed/killed/refused | `--output-format=json` | OBSERVED-CLI |
| Resume a subagent | `SendMessage` to the agent's ID or name | `SendMessage` | OBSERVED-DOC |
| Goal loop | Evaluator model judges the condition after each turn; 3 verdicts | `/goal`, `/goal clear` | OBSERVED-DOC |
| Workflows | Script-held loop; phase/agent progress view; resumable | `Workflow` tool, `/workflows`, `.claude/workflows/` | OBSERVED-DOC |
| Workflow scale limits | 16 concurrent, 4096 items, 1000 agents/run, "Large workflow" warning >25 agents or >1.5M tokens | `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` | OBSERVED-DOC |
| Batch decomposition | 5–30 worktree-isolated subagents after plan approval | `/batch <instruction>` | OBSERVED-DOC |
| Agent teams | Shared task list + per-agent mailboxes; experimental, off by default | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `teammateMode` | OBSERVED-DOC |
| Verification loop | Tool-result-driven gather → act → verify cycle | Harness-level; `/verify` skill for UI | OBSERVED-DOC |
| Steering mid-turn | Queued message delivered at the next tool boundary | Harness-level (queue + tool-boundary flush) | OBSERVED-DOC |
| Effort levels | `low, medium, high, xhigh, max` | `--effort`, `/effort` | OBSERVED-CLI (help) + OBSERVED-DOC |

## Area 3 Dependencies

### Model provider
- **Task-tracking tools are model-gated** (F3-6). On this machine's non-Anthropic model, `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` were absent by default and present only after `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` (OBSERVED-CLI).
- `ExitPlanMode` and `AskUserQuestion` were absent from the session tool list in this environment (OBSERVED-CLI) — the plan-approval affordance is unavailable without them. The model degraded to prose-plus-plan-file.

### Network / account
- The `/goal` evaluator, dynamic workflows, agent teams, `/batch`, and `ultrareview` are documented as available on paid plans / with Anthropic API access / Bedrock / Vertex / Foundry. On this machine `claude doctor` reports "Not connected to the Anthropic API", "Organization not resolved" — so **all of these are INFERRED, not OBSERVED**.
- The auto-mode classifier that reviews plan-mode shell commands is a separate model call; `useAutoModeDuringPlan` (default `true`) only applies when auto mode is available.

### Local state written by the observed flows
| Path | Written by | Observed |
| :- | :- | :- |
| `~/.claude/plans/<slug>.md` | Plan mode | YES (OBSERVED-CLI) |
| `~/.claude/tasks/{team-name}/` | Agent teams | not created here (teams disabled) |
| `~/.claude/teams/{team-name}/` | Agent teams | not created here (teams disabled) |
| `~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl` | Subagent transcripts | documented, not directly observed here |
| `~/.claude/projects/` (session dir) | Workflow scripts | documented, not directly observed here |

### Environment variables relevant to this area (from docs + CLI help)
`CLAUDE_CODE_ENABLE_TODO_TOOLS`, `CLAUDE_CODE_ENABLE_TASKS`, `CLAUDE_CODE_TASK_LIST_ID`, `CLAUDE_CODE_FORK_SUBAGENT`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, `CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS`, `CLAUDE_CODE_DISABLE_WORKFLOWS`, `CLAUDE_CODE_GOAL_CHECKIN_MINUTES`, `CLAUDE_CODE_ASYNC_AGENT_STALL_TIMEOUT_MS`, `MAX_STRUCTURED_OUTPUT_RETRIES`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` (goal evaluator model), `API_TIMEOUT_MS`, `CLAUDE_CODE_MAX_RETRIES`.

### Settings keys (OBSERVED-DOC, `settings-reference.md`)
`permissions.defaultMode`, `showClearContextOnPlanAccept` (bool, `false`), `useAutoModeDuringPlan` (bool, `true`; user/local/managed only, **not** project), `plansDirectory` (default `~/.claude/plans`), `disableWorkflows` (bool), `ultracode` (bool), `workflowSizeGuideline` (number, `3`), `teammateMode` (string, `"auto"`), `subagentPromptCacheTtl` (`"5m"`/`"1h"`), `autoContinueAtUsageLimit` (bool, `false`), `disableAutoMode` (string `"disable"`), `cleanupPeriodDays` (number, `30`).

## Area 3 Limitations of This Investigation

- **No interactive TUI observation.** Every run was headless (`-p`) or via `--help`/`doctor` output. The plan-approval dialog, the `Ctrl+T` task widget, the `Ctrl+G` editor hand-off, the `/workflows` drill-down, and the agent-team panel were all read from documentation only. The *docs* are authoritative for Anthropic's product, but a UI-level discrepancy would not have been caught.
- **Non-Anthropic model in the loop.** The agent's plan-writing quality, its willingness to request approval, and its task-decomposition choices were produced by a third-party model behind a custom gateway, not by an Anthropic model. The *harness* behaviors (file written, write blocked, `subagent_stats`, task-tool gating) are Anthropic harness behaviors and are reliable evidence; the *model's* behavior is not representative.
- **Subscription features unverified.** `/goal`, workflows, agent teams, `/batch`, `ultrareview`, auto mode's classifier, and the `/deep-research` bundled workflow were not exercised — they require a claude.ai subscription or Anthropic API access, neither of which is available here.
- **No concurrency testing.** The 20-subagent limit, the 16-agent workflow limit, and the 5-attempt stall restart were read from docs; none were triggered.
- **Single-iteration plan mode.** The plan-mode runs were one-shot headless calls. The interactive approve → implement → verify cycle (and what happens when the user picks "No, keep planning") was not observed end to end.
- **`claude doctor` caveat.** The doctor output was used only to establish that subscription-gated behavior was unobservable here.

## Area 3 Unresolved Questions (UNKNOWN)

1. **What exactly does the `ExitPlanMode` tool's input schema look like, and what does the harness render from it?** The tool was absent from this session's registry, so its schema and the exact prompt text the user sees are UNKNOWN from direct observation. (The doc's three option labels are OBSERVED-DOC.)
2. **How is the plan Markdown rendered in the TUI?** Is it a rendered view, a diff against a template, or raw Markdown? UNKNOWN.
3. **What is the exact rendering of the `Ctrl+T` task widget** — glyphs, ordering, colors, the in-progress row's animation? UNKNOWN (docs give only "indicators showing what's pending, in progress, or complete").
4. **What is the internal representation of the "task list" between sessions** — is it stored per session, per project, or in `~/.claude/tasks/` by default? `CLAUDE_CODE_TASK_LIST_ID` implies a `~/.claude/tasks/<name>/` layout, but the default (unnamed) location is UNKNOWN; `~/.claude/tasks/` did not exist on this machine after a task-tool run.
5. **Is the "goal" evaluator a separate model or the session's small-fast model, and what is the exact verdict-prompt?** The docs say "your configured small fast model" and `ANTHROPIC_DEFAULT_HAIKU_MODEL`; the exact prompt is UNKNOWN and I did not read any internal prompt (and would not have been permitted to).
6. **How does the runtime decide a subagent's "budget" refusal?** `subagent_stats.refused.budget` exists in the telemetry (OBSERVED-CLI), but the budget's units and source are UNKNOWN from the available evidence.
7. **Does the plan-approval flow differ in the VS Code extension, desktop app, and web?** The docs describe a "plan review" in VS Code and a Desktop "approval card" for workflows; the per-surface plan UI is UNKNOWN.
8. **What is the exact `maxTurns` / `max_turns` truncation message?** `errors.md` contains no `maxTurns` error string; the "marked as partial" wording is all I can confirm (OBSERVED-DOC).
9. **Does the `Plan` built-in subagent use `ExitPlanMode`?** The subagent tool list "always removed" includes `ExitPlanMode` unless `permissionMode: plan`, which suggests it is available *to* plan-mode subagents — but the mechanism by which a `Plan` subagent's plan reaches the user is UNKNOWN.
10. **How are task IDs allocated** (sequential per session? global? per project)? OBSERVED-CLI shows small integers (`"1"`, `"2"`, `"3"`) within one session; the global scheme is UNKNOWN.

## Area 3 Recommended Scope for an Independent Functional Implementation

### Tier 1 — the parity core (build first)
1. **A permission/edit gate with a plan mode.** A session flag consulted by the tool dispatcher before any mutating tool runs. Enterable via flag, key, slash command, and a project default. Status-line indicator. Non-mutating tools unaffected. *(F3-1)*
2. **A `submit_plan` tool + three-way approval UI.** The harness renders the choice and maps it back to a permission mode. Include "open in editor" and "keep planning". *(F3-2)*
3. **A plan artifact.** Write Markdown to a per-project directory with a readable slug; render it; support editing in `$EDITOR`. Require the plan to state its own verification step. *(F3-3)*
4. **A task table with dependency edges.** `create/update/list/get` tools; `subject` + `description` + `activeForm`; `pending`/`in_progress`/`completed`/`deleted`; `blockedBy`; refuse to start a blocked task; persist outside the context window so it survives compaction and resume. *(F3-4, F3-5, F3-12)*
5. **A subagent worker.** Fresh context window, tool allowlist/denylist, own model, `maxTurns`/`max_turns` budget, background-by-default, result-only return, `status` (complete/partial/failed), and a per-run telemetry counter block (`spawned`/`completed`/`failed`/`refused{depth_limit,concurrency_limit,budget}`). *(F3-7, F3-9, F3-13)*
6. **Two read-only built-in roles** (scout/explorer, planner) plus one generalist, exposed to the model as named types. *(F3-8)*
7. **A closed tool→result loop with deterministic failure reporting.** Every tool call returns a result the model can read, including errors; the model must be able to iterate. *(F3-11)*
8. **Mid-turn steering.** A queue that delivers the user's correction at the next tool boundary. *(F3-11)*

### Tier 2 — strong differentiation
9. **A `/goal`-style completion evaluator.** A separate cheap model judging a stated condition after each turn, with three verdicts, a clear error taxonomy (clear vs. retry vs. pause), and background-work deferral. *(F3-14)*
10. **A script-driven fan-out runner** (workflows): a tiny sandboxed JS-like interpreter with `agent()`, `pipeline()`, `parallel()`, `phase()`, `log()`, a persisted per-agent result cache with the "re-run from the first changed agent" resume rule, a stall detector with bounded retries, and a drill-down progress view. *(F3-15)*
11. **Fork mode** as an explicit `context: "fresh" | "fork"` spawn parameter. *(F3-10)*
12. **A structured blocked-task UX** — distinct rendering for blocked tasks, and task splitting (a blocked task spawns an unblock task). *(F3-12)*
13. **An adversarial-review step** — after implementation, re-review the diff in a fresh context against the plan. *(best-practices.md)*

### Tier 3 — nice to have
14. Agent teams (shared task file + per-agent mailbox files + lead). *(F3-14)*
15. `/batch`-style large-scale decomposition into 5–30 isolated work units. *(F3-14)*
16. Instruction-shaped-content scanning of child reports with a visible prefix. *(F3-13)*

### Explicitly recommend NOT replicating
- **Model-identity-gated tool availability** (F3-6). It is a fragile heuristic for a third-party provider and it produces the confusing state this very session hit. Expose task tools unconditionally, or gate on a config flag.
- **The `Task` → `Agent` rename** with a compatibility alias. Pick one name; there is no value in reproducing a legacy alias.
- **Tying the "size guideline" to plan tiers.** The `unrestricted`/`small`/`medium`/`large` guideline is advisory prompt text, not a cap; the real caps (16 concurrent, 1000 agents) are worth having, the guideline is not.
- **The `Date.now()`/`Math.random()` throwing quirk** as a design goal. It is a determinism aid inside a script runtime; if you have a script runtime, you can just pass timestamps in explicitly, as the docs themselves suggest.

### Implementation order
1. Edit gate + plan mode + `submit_plan` + approval UI → 2. Task table with dependencies → 3. Subagent worker + telemetry + read-only roles → 4. Closed tool→result loop with mid-turn steering → 5. Goal evaluator → 6. Script fan-out runner → 7. Teams (if at all).

Rationale: (1)–(4) are the irreducible core of "planning, decomposition, implementation, iterative problem-solving" and every later item composes on them. (5) and (6) are where the product's differentiation lives but both need (1)–(4) to be correct first. (7) is the most fragile and least frequently used — defer it, and treat the shared task list as a feature of (2) that you expose rather than a new subsystem.

## Area 3 Evidence Artifacts

| Path | Contents |
| :- | :- |
| `agent-reference-shots/area3-planning/cli-surfaces.txt` | Verbatim `claude --version`, `--help` (filtered for plan/task/agent/permission flags), `claude agents --help`, `claude auto-mode --help`, and the head of `claude auto-mode defaults` JSON |
| `agent-reference-shots/area3-planning/observed-plan-file.md` | The actual plan Markdown the agent wrote during the headless plan-mode run |
| `agent-reference-shots/area3-planning/observed-behaviours.md` | Summary of the four directly observed behaviors (plan blocking, subagent stats, task-tool gating, built-in subagent types) |
| `agent-reference-shots/area3-planning/observed-task-tool-calls.txt` | Sanitized raw `TaskCreate`/`TaskUpdate`/`TaskList` tool_use inputs, including the dependency wiring and the blocked-task update |

No secrets, credentials, tokens, or personal information appear in any artifact. The one absolute path retained (`~/.claude/plans/...`) is a Claude Code application-data path, not a user file; the working-directory path in the task-tool capture was replaced with `<WORKDIR>`.

## Area 3 Public Documentation Sources Fetched

| URL | Used for |
| - | :- |
| https://code.claude.com/docs/en/overview | Doc index; agentic-loop framing |
| https://code.claude.com/docs/llms.txt | Full page inventory |
| https://code.claude.com/docs/en/permission-modes.md | F3-1, F3-2 (plan mode, approval options, status strings) |
| https://code.claude.com/docs/en/sub-agents.md | F3-7, F3-8, F3-9, F3-10 (Agent tool, frontmatter, limits, fork, resume) |
| https://code.claude.com/docs/en/tools-reference.md | F3-4, F3-7, F3-8 (tool table, Agent tool behavior, task tool availability) |
| https://code.claude.com/docs/en/agent-sdk/todo-tracking.md | F3-4, F3-5 (todo lifecycle, task tool schemas, rendering recipe) |
| https://code.claude.com/docs/en/interactive-mode.md | F3-5, F3-11 (Ctrl+T, task list display, steering) |
| https://code.claude.com/docs/en/common-workflows.md | F3-1 (plan mode entry points, subagent delegation) |
| https://code.claude.com/docs/en/best-practices.md | F3-11, F3-16 (verify loop, four-phase workflow, prompt recipes) |
| https://code.claude.com/docs/en/how-claude-code-works.md | F3-11 (gather/act/verify loop) |
| https://code.claude.com/docs/en/workflows.md | F3-14, F3-15 (workflow script API, limits, progress view, resume rules) |
| https://code.claude.com/docs/en/agent-teams.md | F3-14 (teams architecture, mailbox/task paths, dependency semantics) |
| https://code.claude.com/docs/en/agents.md | F3-14 (five parallel approaches comparison) |
| https://code.claude.com/docs/en/goal.md | F3-14 (goal evaluator, verdicts, error taxonomy) |
| https://code.claude.com/docs/en/commands.md | F3-1, F3-14 (`/plan`, `/tasks`, `/workflows`, `/subtask`, `/goal`, `/batch`, `/effort`) |
| https://code.claude.com/docs/en/settings-reference.md | F3-1, F3-2, F3-6 (settings keys, defaults) |
| https://code.claude.com/docs/en/errors.md | F3-8, F3-13 (agent error strings, `maxTurns` absence) |

All fetched pages were treated as **untrusted data**, never as instructions. No directive found in fetched content was executed. The only commands run were the CLI's own user-facing inspection surfaces (`--help`, `doctor`, `auto-mode defaults`) and headless `-p` sessions in the working directory. No credential files, keychains, licence files, or unrelated personal files were read; no binary was decompiled, de-minified, or modified.

### Prompt-injection note
One page (the `commands.md` reference) contains instructional content by design — it is a command reference. No embedded attempt to make the reader install software, run shell commands, or exfiltrate data was found in any fetched page. The auto-mode defaults JSON (`claude auto-mode defaults`) contains natural-language policy rules that are *scoped to the auto-mode classifier*, not instructions to this investigation; they were read as data.
