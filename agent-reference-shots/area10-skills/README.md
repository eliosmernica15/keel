# Area 10 — Skills, instructions, and subagent workflows: black-box artifacts

All artifacts here are sanitized. No credentials, tokens, personal files, or
account data. Nothing was decompiled, extracted, or reverse-engineered; see
`../TERMS-NOTES.md` for the compliance boundary.

## Method

Every probe ran the **published** Claude Code CLI (2.1.306, native win32-x64)
against throwaway projects under the system temp directory, with
`CLAUDE_CONFIG_DIR` pointed at a scratch config directory. The real
`~/.claude` was never modified, no credential store was read, and no
decompilation, disassembly, or source-map extraction was performed.

Three observation surfaces were used:

1. **The CLI's own help and inspection commands** (`claude plugin validate
   --json`, `claude plugin list --json`, `claude plugin details`,
   `claude plugin init --help`, `claude agents --json`).
2. **The product's own `--debug` log** (`--debug-file`), which prints skill
   discovery, plugin resolution, and budget warnings.
3. **The session transcript's attachment records** (`skill_listing`,
   `agent_listing_delta`, `instructions`, `nested_memory`) - the product's own
   record of exactly what it injected into context.

## Files

| File | What it is | How produced |
| :- | :- | :- |
| `plugin-validate-probes.json` | A concatenated series of `claude plugin validate --json` runs against deliberately malformed and well-formed `SKILL.md` files | Public CLI surface; probe fixtures created in a scratch directory and deleted afterwards |
| `cli-skill-surfaces.txt` | `claude plugin validate --help`, `claude plugin init --help`, `claude plugin details --help`, and the skill/plugin-relevant lines of `claude --help` | Published CLI's own help surfaces |
| `debug-log-skill-discovery.txt` | Skill-discovery lines from the product's own `--debug` log (`Loading skills from:`, `Loaded N unique skills`, `getSkills returning:`) | The product writes this log itself; only the public log lines were extracted |
| `observed-skill-frontmatter.txt` | The frontmatter of two real `SKILL.md` files installed under `~/.claude/skills/` on this machine | Plain file read of the user's own skill files |
| `example-SKILL.md` | A minimal worked example: a user-invocable-only skill with shell injection | Authored from the documented "Create your first skill" example |
| `example-skill-with-forking.md` | A worked example exercising `context: fork`, `agent`, `background`, `allowed-tools`, and `paths` | Authored from the documented `pr-summary` example |
| `init-registries.txt` | The `init` event's `skills`, `agents`, `plugins`, `slash_commands`, `terminal_slash_commands`, `output_style`, `memory_paths`, `mcp_servers`, `model`, `permissionMode` registries for six probe projects | `claude -p ... --output-format stream-json --verbose` |
| `instructions-attachment-probe.txt` | The `instructions` and `nested_memory` attachments: CLAUDE.md vs AGENTS.md selection, `@path` import expansion, and `.claude/rules/` conditional injection | The product's own transcript attachment records |
| `registry-and-tool-contracts.txt` | The `Skill` and `Agent` tool input schemas, and the `agent_listing_delta` / `skill_listing` attachments | The product's own transcript attachment records and API request shape |
| `skill-rendering-probes.txt` | Argument substitution (`$ARGUMENTS`, `$0`, `$thing`, `${CLAUDE_SESSION_ID}`), inline `!`cmd`` injection at line-start vs after-whitespace, `disable-model-invocation` / `user-invocable` semantics, `context: fork`, legacy `.claude/commands/` | `claude -p ... --output-format stream-json --verbose` plus the debug log |
| `discovery-and-budget-probes.txt` | Skill discovery scopes and their exact paths, scope precedence, nested `.claude/skills/` discovery, `paths:`-conditioned skills, and the skill-listing character budget with its overflow warning | `--debug-file` + the `init` event + the `skill_listing` attachment |
| `invocation-control-and-instruction-probes.txt` | `skillOverrides` states, `disableSkillShellExecution`, subagent `skills:` preloading, the `Task` vs `Agent` tool-name split, and the `AGENTS.md` built-in-plugin option | `--debug-file`, the transcript attachment records, and `--settings` |
| `plugin-cli-probes.txt` | `claude plugin list --json`, `claude plugin details`, `claude plugin validate --json` envelope, `claude plugin init --help`, `claude plugin marketplace --help`, `claude agents --json`, `claude import --dry-run` | The published CLI's own inspection surfaces |

## Probe fixtures used

All created under a scratch directory, all removed after the run:

- a skill with every documented frontmatter field set
- a skill with a typo'd `description` plus an unknown field (`descripton`)
- a skill whose frontmatter YAML does not parse
- a skill with no frontmatter block at all
- a skill with a non-spec field (`argument-hint`)
- a skill folder named `synced` (a reserved name)
- a skill with `context: fork` / `agent: Explore` / `paths` / `hooks` / `metadata`
- a skill with `paths:` glob frontmatter (path-conditioned)
- a skill with `disable-model-invocation: true`, one with `user-invocable: false`,
  one with both, one with neither
- a skill with `disableSkillShellExecution` active in project settings
- three skills under the four `skillOverrides` states
- the same skill name present in both the user scope and the project scope
- a nested `<subdir>/.claude/skills/` directory
- a legacy `.claude/commands/<name>.md` and `.claude/commands/frontend/component.md`
- a project with `CLAUDE.md` + `AGENTS.md`, one with `AGENTS.md` only
- a `CLAUDE.md` with an `@sub/CLAUDE.md` import
- a `.claude/rules/` pair (one unconditional, one path-scoped)
- a subagent with a `skills:` preload list
- a custom output style + `outputStyle` settings key

## What the probes established

`claude plugin validate` is a real, scriptable, machine-readable validator for
`SKILL.md` files. It emits a stable JSON envelope (`success`, `strict`,
`target`, `manifest`, `contents`, `advice`, `directory`) and reports per-file
`errors` and `warnings` with a `path` and `message`. This is the single most
useful observable contract for a clean-room reimplementation, because it
specifies the parse-and-report behaviour of frontmatter without exposing any
implementation detail.

Beyond that, the probes established five facts that the public documentation
states but does not make machine-checkable, and that a reimplementer would
otherwise have to guess:

1. **The two invocation-control flags are not opposites.** `disable-model-invocation:
   true` removes the skill's *description* from the model's context (the skill
   disappears from the listing) while keeping it in the `/` menu;
   `user-invocable: false` keeps the description visible to the model but
   removes the skill from the `/` menu. Both were confirmed by reading the
   `skill_listing` attachment and the `init.skills` / `init.slash_commands`
   registries side by side.
2. **The loader executes `!`cmd`` in a skill body itself**, at render time,
   before the content reaches the model. It is recognised only at the start of a
   line or after whitespace - `INLINE=!`cmd`` is left literal. A policy setting
   (`disableSkillShellExecution`) replaces the command with
   `[shell command execution disabled by policy]`.
3. **`init` and the attachment records are a complete machine-readable registry
   surface** - `init.skills`, `init.agents`, `init.plugins`,
   `init.slash_commands`, `init.terminal_slash_commands`, `init.output_style`,
   `init.memory_paths`, plus the `skill_listing`, `agent_listing_delta`,
   `instructions`, and `nested_memory` attachments. An implementer can copy
   these shapes directly.
4. **`skillOverrides` has four states that affect three different surfaces**
   (the skill registry, the `/` menu, and the model-facing listing), and the
   mapping is not the intuitive one.
5. **Scope precedence is applied at name-resolution time, not load time.** The
   loader counts both the user-scope and project-scope copies of a same-named
   skill (`user: 2, project: 2`), but only the user-scope *description* reaches
   the model.
