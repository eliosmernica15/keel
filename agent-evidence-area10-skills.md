# Claude Code — Area 10 Evidence: Skills (`SKILL.md`), Invocation Control, and Reusable Instructions

> **File note.** The parent `agent-evidence.md` in this directory holds a
> sibling area's report and was left untouched. This file is Area 10's
> evidence.

**Scope of this document.** Area 10 of a multi-area study of Claude Code as the
reference product for an independently implemented AI coding agent. This
document covers one page of public documentation —
`https://code.claude.com/docs/en/skills.md` — plus black-box observation of the
published CLI's own skill-related surfaces.

**Method and compliance boundary.** Claude Code is proprietary. Anthropic's
Consumer Terms of Service §3 and Commercial Terms of Service §D.4 prohibit
decompiling, reverse engineering, and disassembling the Services, and the
product's own legal page states "The Claude Code binary must not be modified."
Accordingly:

- **Not performed:** decompiling `claude.exe` or the bundled `versions/2.1.306`
  blob; extracting, de-minifying, or de-obfuscating the bundled JavaScript;
  dumping source maps; modifying the binary; reading credential stores,
  keychains, licence files, or account data; probing Anthropic's private model
  gateway.
- **Performed:** reading public documentation at `code.claude.com/docs`; running
  the published CLI's own help and self-validation surfaces (`claude --help`,
  `claude plugin validate|init|details --help`); creating synthetic `SKILL.md`
  fixtures and running the product's own validator over them; reading the
  public `--debug` log the product writes about itself; reading the user's own
  `~/.claude/skills/*/SKILL.md` files.

REA was **not** applied to the Claude Code binary at all. The one place REA
could have been argued for — decompiling the CLI to recover the skill loader —
is exactly the case the licence and the clean-room requirement both forbid,
and using it would have destroyed the clean-room property this study exists to
preserve. The two constraints agree, so the decision was simple.

**Environment note.** This host runs Claude Code **2.1.306** (`claude --version`
→ `2.1.306 (Claude Code)`) against a **custom `ANTHROPIC_BASE_URL`**, not
`api.anthropic.com`. Features that depend on a claude.ai account sign-in,
feature-flag fetching, or the Anthropic API are therefore **not observable here**
and are marked `OBSERVED-DOC` (documented), never `OBSERVED`.

**Status labels used in this document.** The study's mandatory classification
enum is `OBSERVED-DOC` / `INFERRED` / `UNKNOWN`. This document additionally
uses `OBSERVED-CLI` for a narrower, unambiguous case: a fact read directly off
a **published, documented public surface** of the running product (its own
`--help` output, its own `--debug` log, its own validator report) rather than
off an Anthropic documentation page. `OBSERVED-CLI` is a subset of
`OBSERVED-DOC` in substance — both are publicly documented behaviour of the
published product — and is distinguished only so a reader can tell at a glance
whether a claim was read off a doc page or off the running binary's own
self-description output. Where the distinction matters, both are cited
explicitly. No claim anywhere in this document rests on anything other than
public documentation or the published CLI's own public output.

---

## 1. Executive summary

Claude Code's "skills" system is a **file-based, markdown-first extension
mechanism** whose entire public contract is a directory named `SKILL.md` with
YAML frontmatter and Markdown body. It is the product's most portable, most
documented, and most cleanly-specified subsystem — and the easiest to
reimplement faithfully, because almost everything about it is specified in
writing rather than hidden in behaviour.

Five things dominate the design:

1. **A skill is a directory, not a file.** `SKILL.md` is required and holds the
   frontmatter plus instructions; sibling files (`reference.md`, `examples.md`,
   `scripts/helper.py`) are supporting material that Claude reads on demand.
   The reference product explicitly recommends keeping `SKILL.md` under 500
   lines. This is progressive disclosure applied to the extension mechanism
   itself: the *description* is always loaded, the *body* only on invocation.

2. **Invocation is bifurcated and the frontmatter controls it.** Two independent
   switches — `disable-model-invocation` and `user-invocable` — decide whether
   *you* may invoke a skill and whether *Claude* may invoke it. Together with
   `description` visibility this produces three distinct context-loading
   behaviours (description always in context / description hidden / full
   content loaded) that a reimplementer must get exactly right, because they
   change what the model sees on every turn.

3. **Context budget is a first-class, tunable resource.** The skill *listing*
   (every name + every description) is injected into the model on **every
   turn** and is capped at `skillListingBudgetFraction` (default `0.01`, i.e.
   1% of the context window). Over budget, descriptions are dropped
   least-used-first while names are always retained. Each skill's combined
   `description` + `when_to_use` text is separately capped at
   `skillListingMaxDescChars` (default `1536`). This is an unusual and
   well-specified detail that most reimplementations miss.

4. **Skills are a *sibling* of slash commands, and the product says so.**
   `.claude/commands/deploy.md` and `.claude/skills/deploy/SKILL.md` both
   produce `/deploy`. The legacy format still works, accepts the same
   frontmatter *except* `name` and `paths`, and is superseded. Command-file
   names map to `/name`, nested command files map to `/dir:name`, and plugin
   skills are namespaced `/plugin:skill`.

5. **Skills can inject live data and can run in isolation.** `` !`git diff HEAD` ``
   executes a shell command at render time and substitutes its output;
   `context: fork` runs the skill body as a fresh subagent's prompt with no
   conversation history; `allowed-tools` pre-approves tools for the invoking
   turn only; `paths` scopes automatic activation to matching files. Each of
   these is separately observable, separately configurable, and separately
   constrained (e.g. injected commands never prompt; a failing injected command
   aborts the whole invocation).

**How strong is this evidence?** The page is unusually dense and unusually
specific — it names exact field names, exact paths, exact JSON keys, exact
error strings, exact version gates, and a machine-readable validation
contract. For a clean-room reimplementation this is close to a specification.
The area that is *not* well covered is the internals: how the loader ranks
duplicate names in edge cases, how the description-drop heuristic actually
orders "least used", and the internal ordering guarantees of the listing.
Those are marked `UNKNOWN` below.

**Nothing here requires Anthropic-proprietary assets.** A reimplementation
needs only: a markdown file format, a YAML parser, a directory-walking loader, a
substitute for "shell command execution at render time", and a policy engine for
tool permissions. All five are standard engineering.

---

## 2. Detailed findings

Each finding cites the exact URL and quotes the supporting sentence(s).

### F1 — A skill is a directory containing a required `SKILL.md`

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Getting started" → "Create your first skill"
- **Status:** `OBSERVED-DOC`

> "Every skill needs a `SKILL.md` file with two parts: YAML frontmatter between `---` markers that tells Claude when to use the skill, and markdown content with the instructions Claude follows when the skill runs."

> "```text theme={null}
> my-skill/
> ├── SKILL.md (required - overview and navigation)
> ├── reference.md (detailed API docs - loaded when needed)
> ├── examples.md (usage examples - loaded when needed)
> └── scripts/
>     └── helper.py (utility script - executed, not loaded)
> ```"

> "Keep `SKILL.md` under 500 lines. Move detailed reference material to separate files."

- **Reimplementation need:** Yes — this is the core data model. The "executed,
  not loaded" annotation for scripts is a meaningful semantic distinction: a
  `scripts/` sibling is a *program to run*, a `reference.md` sibling is *text to
  read*. A clean-room implementation should mirror this rather than treat
  every sibling file identically.

### F2 — The full frontmatter field set (exact names)

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Frontmatter reference"
- **Status:** `OBSERVED-DOC`

> "Configure a skill with YAML [frontmatter](/docs/en/glossary#frontmatter)
> between `---` markers at the top of `SKILL.md` … Field names use lowercase
> words separated by hyphens, except `when_to_use`."

The table lists, with `Required` column values:

| Exact field | Required | One-line doc summary (paraphrase of the table row) |
| :- | :- | :- |
| `name` | No | Command name shown in the `/` menu. Defaults to the directory name. |
| `description` | Recommended | What the skill does and when to use it. If omitted, uses the first non-empty line of the markdown content. |
| `when_to_use` | No | Additional context for when Claude should invoke the skill. Appended to `description` in the skill listing. |
| `argument-hint` | No | Hint shown during autocomplete, e.g. `[issue-number]`. |
| `arguments` | No | Named positional arguments for `$name` substitution. Accepts a space-separated string or a YAML list. |
| `disable-model-invocation` | No | Set to `true` to prevent Claude from automatically loading this skill. Default: `false`. |
| `user-invocable` | No | Set to `false` when only Claude should invoke the skill. Default: `true`. |
| `allowed-tools` | No | Tools Claude can use without asking permission during the turn that invokes this skill. |
| `disallowed-tools` | No | Tools removed from Claude's available pool while the skill is active. |
| `model` | No | Model to use when this skill is active; accepts `inherit`. |
| `effort` | No | `low`, `medium`, `high`, `xhigh`, or `max`. |
| `context` | No | Set to `fork` to run in a forked subagent context. |
| `agent` | No | Which subagent type to use when `context: fork` is set. |
| `background` | No | Only applies with `context: fork`. Set to `false` to wait. Default: `true`. |
| `hooks` | No | Hooks Claude Code registers when the skill is invoked. |
| `paths` | No | Glob patterns that limit when this skill is activated. |
| `shell` | No | `bash` (default) or `powershell`. |
| `metadata` | No | Free-form YAML map for your own key-value data. |
| `license` | No | Part of the Agent Skills spec. |
| `compatibility` | No | Environment requirements, up to 500 characters. |

Verbatim statements that constrain parsing:

> "All fields are optional. Only `description` is recommended so Claude knows
> when to use the skill. A field name must match the table exactly, hyphens
> included: Claude Code ignores a field it doesn't recognize without reporting
> an error."

> "Claude Code reads the frontmatter only when the opening `---` is the file's
> first line. Otherwise it treats the whole file, `---` markers included, as
> skill content. If the YAML between the markers doesn't parse, the skill still
> loads with no fields set."

> "Boolean fields accept `yes`, `no`, `on`, `off`, `1`, and `0` in any letter
> case, in addition to `true` and `false`."

- **Reimplementation need:** Yes — these are the *exact* keys. A clean-room
  implementation should use these names verbatim because user-authored skills
  in the wild use them, and because the spec subset (below) is a public
  standard.

### F3 — Six of the fields are the public Agent Skills spec; the rest are Claude Code extensions

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Using skill frontmatter outside Claude Code"
- **Status:** `OBSERVED-DOC`

> "Claude Code accepts every field in the table above. Outside Claude Code, you
> can use only the fields in the [Agent Skills](https://agentskills.io) spec:"

| Distribution path | Frontmatter fields you can use |
| :- | :- |
| Claude Code skills at any level, including plugin skills | Every field in the table above |
| claude.ai skill uploads, the Skills API, and packaging with `package_skill.py` | `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` |

> "If you include any field the spec doesn't allow, packaging or upload fails
> with a hard error instead of ignoring the field:
>
> ```text
> Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name
> ```"

> "Claude Code skills follow the [Agent Skills](https://agentskills.io) open
> standard, which works across multiple AI tools. Claude Code extends the
> standard with additional features like [invocation control], [subagent
> execution], and [dynamic context injection]."

- **Reimplementation need:** Yes, and this is the highest-leverage detail for
  an independent implementation. Because the six spec fields are a *public
  open standard* (`agentskills.io`), an independent agent can implement that
  subset and be interoperable with skills authored for Claude Code. The other
  fourteen fields are Claude Code extensions that can be implemented as
  supersets. A clean-room implementer should implement the six spec fields
  first and treat the rest as optional extras.

### F4 — Seven discovery locations with a documented precedence order

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Choose where skills load"
- **Status:** `OBSERVED-DOC`

| Location | Exact path | Loads in |
| :- | :- | :- |
| Enterprise | `.claude/skills/<skill-name>/SKILL.md` in the managed settings directory | All users on machines where your organization deploys it |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | All your projects on this machine, but not Cowork or cloud sessions |
| Project | `.claude/skills/<skill-name>/SKILL.md` | Sessions in this repository |
| Nested | `<subdir>/.claude/skills/<skill-name>/SKILL.md` | Sessions started in or below `<subdir>` |
| Additional directory | `.claude/skills/<skill-name>/SKILL.md` in a directory passed with `--add-dir` | That session |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` | Wherever the plugin is enabled, as `/plugin-name:skill-name` |
| claude.ai account | Skills enabled for your claude.ai account | Cowork sessions, cloud sessions, and eligible terminal sessions |

Enterprise example path: `/etc/claude-code/.claude/skills/<skill-name>/`

Duplicate-name resolution (same page, "Resolve skills that share a name"):

> "Enterprise over personal, and personal over project. With `deploy` in both
> `~/.claude/skills/` and the project's `.claude/skills/`, `/deploy` runs the
> personal one"

> "Your skill replaces the bundled command, but not its aliases. A project
> `code-review` skill replaces `/code-review`, and the bundled alias `/review`
> never runs your skill"

> "A skill and a file in `.claude/commands/` | The skill"

> "A plugin skill and a skill at any of the locations above | Both load,
> because plugin skills are namespaced as `/plugin-name:skill-name`"

Additional documented discovery rules:

> "Claude Code loads project skills from `.claude/skills/` in the directory
> where you start it and in every parent directory up to the repository root"

> "Skills in a `.claude/skills/` directory below where you started don't load
> at startup. They load the first time Claude reads or edits a file in that
> subdirectory and stay available for the rest of the session. Until then they
> don't appear in the `/` menu and you can't invoke them by name."

> "When you add a directory with `--add-dir` or `/add-dir`, Claude Code loads
> the skills in that directory's `.claude/skills/`, along with its
> `.claude/commands/` and `.claude/agents/`. … The
> `permissions.additionalDirectories` setting in `settings.json` grants file
> access only and loads none of these."

> "Claude Code watches `.claude/skills/` in a directory you pass with
> `--add-dir` at launch … It doesn't watch the added directory's
> `.claude/commands/` or `.claude/agents/`, so restart the session after
> changing a file there."

Reserved names:

> "**Reserved name `synced`**: don't name a skill folder `synced`, in any
> capitalization."

> "**Reserved name `anthropic-skills`**: outside a plugin, a skill folder or
> command file whose name is `anthropic-skills` or starts with
> `anthropic-skills:` doesn't load."

Symlink rule:

> "**Symlinked folders**: a `<skill-name>` entry in the enterprise, personal, or
> project location can be a symlink to a directory elsewhere on disk. Claude
> Code reads `SKILL.md` from the target and loads the skill once even if
> several locations point at the same target."

- **Reimplementation need:** Yes — discovery is the whole feature. The
  parent-directory walk, the nested-lazy-load rule, the precedence order, and
  the "load a symlink target only once" rule are all load-bearing and all
  observable from the outside.

### F5 — Command-name derivation is a documented function of path and frontmatter

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "How a skill gets its command name"
- **Status:** `OBSERVED-DOC`

| Skill location | Command name source | Example |
| :- | :- | :- |
| Skill directory under `~/.claude/skills/` or `.claude/skills/` | Frontmatter `name` or the directory name | `.claude/skills/deploy-staging/SKILL.md` → `/deploy-staging`, or `/deploy` with `name: deploy` |
| Nested `.claude/skills/` directory, when the directory name clashes with another skill | Subdirectory path relative to the working directory, then the skill directory name | `apps/web/.claude/skills/deploy/SKILL.md` → `/apps/web:deploy` |
| File under `.claude/commands/` | File name without extension | `.claude/commands/deploy.md` → `/deploy` |
| File in a subdirectory of `.claude/commands/` | Subdirectory path relative to `commands/` with each `/` replaced by `:`, then the file name without extension | `.claude/commands/frontend/component.md` → `/frontend:component` |
| Plugin `skills/` subdirectory | Frontmatter `name` or the directory name, namespaced by plugin | `my-plugin/skills/review/SKILL.md` → `/my-plugin:review`, or `/my-plugin:fancy` with `name: fancy` |
| Plugin root `SKILL.md` | Frontmatter `name`, with the plugin directory name as a fallback | `my-plugin/SKILL.md` with `name: review` → `/my-plugin:review` |
| Skill synced from claude.ai | The skill's name on your claude.ai account, prefixed with `anthropic-skills:` | Account skill `deploy` → `/anthropic-skills:deploy` |

> "The directory name also invokes the skill."

> "If the `name` you write already starts with the plugin's own prefix, Claude
> Code doesn't add the prefix again on v2.1.246 or later."

Rejected characters (same section, "Characters a skill name can't hold"):

> "Claude Code refuses a command name or a frontmatter `name` that contains
> characters such as these:
>
> * A zero-width space or a control character
> * A private-use or unassigned character, such as a glyph from an icon font
> * A character that changes the direction of the text around it
> * A blank other than one plain space between words, such as a no-break space,
>   two spaces in a row, or a space at the start or end
> * `<` or `>`"

- **Reimplementation need:** Yes. This is a pure function from
  (path, frontmatter, collision state) → command string. It is exactly the kind
  of thing a clean-room implementation can and should reproduce, because user
  muscle memory depends on it. Note the subtlety: the *nested* qualified form
  only applies "when the directory name clashes with another skill", otherwise
  the plain name is used.

### F6 — Invocation control: two orthogonal switches, three context states

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Control who invokes a skill"
- **Status:** `OBSERVED-DOC`

> "By default, both you and Claude can invoke any skill. You can type
> `/skill-name` to invoke it directly, and Claude can load it automatically when
> relevant to your conversation. Two frontmatter fields let you restrict this"

> "Here's how the two fields affect invocation and context loading:"

| Frontmatter | You can invoke | Claude can invoke | When loaded into context |
| :- | :- | :- | :- |
| (default) | Yes | Yes | Description always in context, full skill loads when invoked |
| `disable-model-invocation: true` | Yes | Not on its own | Description not in context, full skill loads when invoked |
| `user-invocable: false` | No | Yes | Description always in context, full skill loads when invoked |

Enforcement on a model attempt:

> "If Claude tries anyway, Claude Code blocks the call and instructs it not to
> reproduce the deploy steps another way, so expect Claude to suggest running
> `/deploy` yourself."

Slash-position semantics:

| Where | Example | What happens |
| :- | :- | :- |
| At the start of your message | `/deploy staging` | Claude Code runs the skill directly |
| After plain text, as a separate word with no punctuation attached | `go ahead and /deploy to staging` | Nothing runs directly. The name counts as your permission for that message |
| (omitting the slash) | `deploy staging` | To write about the skill without permitting a run, leave off the slash |

- **Reimplementation need:** Yes — highest-priority behaviour to match. The
  three-row table is the precise contract, and the "description not in context"
  row for `disable-model-invocation: true` is a genuine privacy property (the
  skill becomes invisible to the model, not merely un-invocable).

### F7 — Skill content lifecycle: injected once, persists, re-appends on change, survives compaction under a budget

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Skill content lifecycle"
- **Status:** `OBSERVED-DOC`

> "When you or Claude invoke a skill, the rendered `SKILL.md` content enters
> the conversation as a single message and stays there across later turns.
> This persistence applies to the skill's instructions, not its permissions: an
> `allowed-tools` grant clears when you send your next message. Claude Code does
> not re-read the skill file on later turns"

> "When Claude re-invokes a skill whose rendered content is identical to the
> copy already in context, Claude Code adds a short note that the skill is
> already loaded rather than a second copy of the content. When the rendered
> content differs, because the arguments changed or a dynamic context command
> produced new output, Claude Code appends the full content again."

> "[Auto-compaction] carries invoked skills forward within a token budget.
> When the conversation is summarized to free context, Claude Code re-attaches
> the most recent invocation of each skill after the summary, keeping the first
> 5,000 tokens of each. Re-attached skills share a combined budget of 25,000
> tokens. Claude Code fills this budget starting from the most recently invoked
> skill, so older skills can be dropped entirely after compaction if you have
> invoked many in one session."

- **Reimplementation need:** Yes. Three constants to reproduce exactly:
  **5,000 tokens per re-attached skill**, **25,000 tokens combined**, and
  **most-recently-invoked-first** fill order. Also note the split between
  *content* persistence (across turns) and *permission* persistence (only for
  the invoking turn) — that asymmetry is easy to get wrong.

### F8 — `allowed-tools` / `disallowed-tools`: turn-scoped, additive vs. subtractive

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Pre-approve tools for a skill"
- **Status:** `OBSERVED-DOC`

> "The `allowed-tools` field grants permission for the listed tools during the
> turn that invokes the skill, so Claude can use them without prompting you for
> approval. The grant clears when you send your next message … It does not
> restrict which tools are available: every tool remains callable"

> "Workspace trust doesn't gate this field. Claude Code applies a project
> skill's `allowed-tools` even in a `-p` run in a folder you've never trusted.
> A skill can grant itself broad tool access, so review the `allowed-tools` of
> skills checked into a repository before you run Claude Code there."

> "To remove tools from Claude's available pool while a skill is active, list
> them in `disallowed-tools` in the skill's frontmatter. The restriction clears
> when you send your next message. Like deny rules, the field can't remove
> `EndConversation` while any other tool remains."

Managed-override:

> "When your organization sets `allowManagedPermissionRulesOnly` in managed
> settings, Claude Code ignores `allowed-tools` in project and personal skills
> and in the other sources the setting's entry lists. This requires Claude Code
> v2.1.282 or later."

> "Run `/status` to list each skill whose `allowed-tools` Claude Code has
> ignored so far in the session."

- **Reimplementation need:** Yes. `allowed-tools` is additive (does not
  restrict), `disallowed-tools` is subtractive (removes from the pool), both
  are turn-scoped. The "workspace trust doesn't gate this field" behaviour is
  a genuine security-relevant difference that a reimplementation should decide
  deliberately rather than copy blindly.

### F9 — String substitution: exact variable names and exact expansion semantics

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Available string substitutions"
- **Status:** `OBSERVED-DOC`

| Exact substitution | Description (from the table) |
| :- | :- |
| `$ARGUMENTS` | All arguments passed when invoking the skill. When no placeholder receives an argument, Claude Code appends them as `ARGUMENTS: <value>`. |
| `$ARGUMENTS[N]` | Access a specific argument by 0-based index, such as `$ARGUMENTS[0]` for the first argument. |
| `$N` | Shorthand for `$ARGUMENTS[N]`, such as `$0` for the first argument or `$1` for the second. |
| `$name` | Named argument declared in the `arguments` frontmatter list. Names map to positions in order. |
| `${CLAUDE_SESSION_ID}` | The current session ID. |
| `${CLAUDE_EFFORT}` | The current effort level: `low`, `medium`, `high`, `xhigh`, or `max`. |
| `${CLAUDE_SKILL_DIR}` | The directory containing the skill's `SKILL.md` file. For plugin skills, this is the skill's subdirectory within the plugin, not the plugin root. |
| `${CLAUDE_PROJECT_DIR}` | The project root directory. |
| `${CLAUDE_PLUGIN_ROOT}` | The plugin's installation directory. Substituted only in plugin skills. |
| `${CLAUDE_PLUGIN_DATA}` | The plugin's persistent data directory. Substituted only in plugin skills. |

Expansion-order and edge-case rules:

> "Claude Code substitutes `${CLAUDE_SKILL_DIR}` and `${CLAUDE_PROJECT_DIR}` in
> two places: the skill's markdown content, and Bash rules in the
> `allowed-tools` frontmatter."

> "Indexed arguments use shell-style quoting, so wrap multi-word values in
> quotes to pass them as a single argument. For example, `/my-skill "hello
> world" second` makes `$0` expand to `hello world` and `$1` to `second`. The
> `$ARGUMENTS` placeholder always expands to the full argument string as typed."

> "An indexed placeholder with no corresponding argument, such as `$2` when
> only one argument was passed, stays in the content unchanged. A named
> placeholder from the `arguments` frontmatter with no matching argument
> expands to an empty string."

> "If you pass an argument value that itself contains text such as `$1` or
> `$ARGUMENTS`, Claude Code inserts it as literal text and doesn't expand it."

> "To include a literal `$` before a digit, `ARGUMENTS`, or a declared argument
> name, such as `$1.00` in prose, escape it with a backslash: `\$1.00`. A
> backslash before any other `$` is left unchanged. Only a single backslash
> directly before the token escapes it. A doubled backslash such as `\\$1`
> leaves both backslashes in place, and `$1` still expands to the argument
> value."

> "Claude Code still replaces `${CLAUDE_*}` variables such as
> `${CLAUDE_SKILL_DIR}` after it inserts the arguments."

- **Reimplementation need:** Yes, and this is the subtlest part of the whole
  area. The ordering rule (arguments substituted first, then `${CLAUDE_*}`
  variables) plus the no-recursive-expansion rule plus the backslash-escape
  rules together define a small, precisely specified templating language. A
  clean-room implementation should implement it as an explicit two-pass
  substitution with an escaping pass, and unit-test the interaction cases.

### F10 — Dynamic context injection: shell executed at render time, single-pass, abort-on-failure

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Advanced patterns" → "Inject dynamic context"
- **Status:** `OBSERVED-DOC`

> "The `` !`<command>` `` syntax runs shell commands before the skill content
> is sent to Claude. The command output replaces the placeholder, so Claude
> receives actual data, not the command itself."

Multiline form:

> "````markdown
> ## Environment
> ```!
> node --version
> git status --short
> ```
> ````"

Behaviour rules:

> "- Injection runs once over the original file.
> - Output is not rescanned for more injection placeholders.
> - Inline injection is recognized only at the start of a line or immediately
>   after whitespace."

> "`disableSkillShellExecution` replaces commands with:
>
> ```text
> [shell command execution disabled by policy]
> ```"

> "Bundled and managed skills are unaffected by that setting. Synced skills
> never execute `!` commands locally."

Shell selection:

> "- `shell: powershell` uses the PowerShell tool when enabled.
> - `shell: bash` requires Bash and fails if Git Bash is unavailable.
> - Other combinations use Bash when available and otherwise PowerShell.
> - Commands use the session shell's current working directory.
> - Bash merges stderr into stdout.
> - Commands use the Bash tool's default two-minute timeout."

Failure semantics:

> "A failed injected command aborts the entire skill invocation, not just its
> own placeholder. Claude never sees the skill content for that invocation. The
> abort shows `Shell command failed for pattern "..."`. The error message
> includes the command's output under `[stderr]`."

> "With the default `bash` shell, any non-zero exit code counts as a failure.
> One carveout applies: Claude Code treats exit code 1 from search and
> comparison commands as a normal result and injects their output. Exit codes
> of 2 or higher fail even for those commands."

> "With the default `bash` shell, append `|| true` to any other command you
> expect to exit non-zero."

Control-character semantics:

> "`No shell command in <name> was run` means one of the file's `!` commands
> contains a raw control character other than tab or newline, so none of them
> runs."

Permission semantics:

> "Injected commands never prompt for permission while the skill renders.
> Claude Code checks each one against your permission rules first. A command a
> deny rule matches aborts the invocation with `Shell command permission check
> failed for pattern "..."`."

> "Outside [auto mode], when a command's permission check returns anything
> other than allow, Claude Code aborts the invocation with the same error.
> This includes a rule that would normally ask you. To keep an unmatched
> command from aborting here, pre-approve it with `allowed-tools`. … Deny and
> ask rules still override `allowed-tools`."

> "In auto mode, a command that would otherwise need your approval doesn't
> abort the invocation. The skill loads with an instruction telling Claude to
> run the command first, and Claude's own call then goes through auto mode's
> usual checks."

- **Reimplementation need:** Yes. This is the highest-risk area in the whole
  skill system from a security standpoint, and the semantics are unusually
  precise. Key properties a clean-room implementation must reproduce:
  **single-pass** (output is not re-scanned), **abort-on-failure** (the entire
  invocation dies, not just the placeholder), **no prompting at render time**,
  **deny/ask override `allowed-tools`**, and the **exit-code-1 carveout for
  search/comparison commands only**. The "output is not rescanned" rule is
  also the correct security posture — it prevents injected output from
  triggering further shell execution.

### F11 — `context: fork`: the skill body becomes a subagent prompt

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Advanced patterns" → "Run skills in a subagent"
- **Status:** `OBSERVED-DOC`

> "Add `context: fork` to your frontmatter when you want a skill to run in
> isolation. Claude Code starts a new subagent of the type set in the `agent`
> field and gives it the skill content as its prompt. The subagent doesn't see
> your conversation history, so the skill's instructions have to stand on their
> own."

> "Despite the name, a skill with `context: fork` doesn't run in a fork of the
> current conversation"

> "The forked subagent runs in the background … Set `background: false` in the
> frontmatter to instead wait for the result in the turn that invoked the
> skill."

Cases where it waits regardless:

> "* In non-interactive mode, with the `-p` flag or the Agent SDK
> * When you set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` to `1`, which also
>   turns off all other background task features
> * When you invoke a forked skill while an earlier invocation of the same
>   skill is still running
> * A session-scoped scheduled task fires with the skill as its prompt"

> "A forked skill that runs in the background applies its edits outside your
> session's checkpoints. After one, `/rewind` restores only the files Claude
> had already edited in your conversation. The skill's edits to other files
> stay, so use git to revert them."

> "The `agent` field specifies which subagent configuration to use. Options
> include built-in agents (`Explore`, `Plan`, `general-purpose`) or any custom
> subagent from `.claude/agents/`. If omitted, uses `general-purpose`."

- **Reimplementation need:** Yes, and note the contrast with the inverse
  pattern (a subagent's `skills:` field preloading skills into a subagent) —
  the doc tabulates both directions. Also note the checkpoint caveat, which is
  a real data-loss hazard for a reimplementation to consider.

### F12 — The skill *listing* is a per-turn context artifact with a tunable budget

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Troubleshooting" → "Skill descriptions are cut short"
- **Status:** `OBSERVED-DOC`

> "Claude Code loads a listing of skill names and descriptions into context so
> Claude knows what's available. The listing always contains every skill name,
> but if you have many skills, Claude Code drops some descriptions to fit the
> listing's character budget … The budget scales at 1% of the model's context
> window. When the listing overflows, Claude Code drops descriptions starting
> with the skills you invoke least, so the skills you use most keep their full
> text."

> "The Skills row in `/context` reports the size of the listing after the
> budget is applied, so it matches what the model receives."

> "To raise the budget, set the `skillListingBudgetFraction` setting (for
> example, `0.02` = 2%) or the `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment
> variable to a fixed character count. … each entry's combined text is capped
> at 1,536 characters regardless of budget. The cap is configurable with
> `skillListingMaxDescChars`."

Cross-checked against `https://code.claude.com/docs/en/settings-reference.md`:

> "### `skillListingBudgetFraction` … **Type**: number, a fraction greater than
> `0` and at most `1` … **Default**: `0.01`, which reserves 1% of the context
> window"

> "### `skillListingMaxDescChars` … **Type**: number of characters, a positive
> integer … **Default**: `1536`"

- **Reimplementation need:** Yes — and this is the single most valuable
  under-appreciated detail in the area. The mechanism ("names always kept,
  descriptions dropped least-used-first, budget = 1% of context window") is
  unusual and directly portable. A reimplementation can implement it exactly
  with a usage-frequency counter and a character budget.

### F13 — `skillOverrides`: visibility controlled from settings without editing `SKILL.md`

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Override skill visibility from settings"
- **Status:** `OBSERVED-DOC`

| Value | Listed to Claude | In `/` menu |
| :- | :- | :- |
| `"on"` | Name and description | Yes |
| `"name-only"` | Name only | Yes |
| `"user-invocable-only"` | Hidden | Yes |
| `"off"` | Hidden | Hidden |

> "A skill that is absent from `skillOverrides` is treated as `"on"`."

> "The `/skills` menu writes it for you: highlight a skill and press `Space` to
> cycle states, then `Esc` to save to `.claude/settings.local.json`."

> "In user, project, and local settings, Claude Code matches entries against
> skill names only. If you set an entry for `review` there, it applies to a
> skill named `review`, not to the bundled `/code-review` through its `/review`
> alias."

> "Plugin skills are not affected by `skillOverrides`. Manage those through
> `/plugin` instead."

Cross-checked against `https://code.claude.com/docs/en/settings-reference.md`:

> "### `skillOverrides` … **Scope**: `Any file`. The `/skills` menu writes to
> `.claude/settings.local.json`. **Type**: object mapping skill name to one of
> … **Default**: unset, so every skill is `"on"`"

- **Reimplementation need:** Yes. Four-state visibility with a documented
  default and a documented source-sensitivity rule.

### F14 — Access control over the Skill tool uses `Skill(...)` permission-rule syntax

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Configure skills" → "Restrict Claude's skill access"
- **Status:** `OBSERVED-DOC`

> "**Disable all skills** by denying the Skill tool in `/permissions`:
>
> ```text
> Skill
> ```"

> "**Allow or deny specific skills** using permission rules:
>
> ```text
> Skill(commit)
> Skill(review-pr *)
> Skill(deploy *)
> ```"

> "Permission syntax: `Skill(name)` for exact match, `Skill(name *)` for prefix
> match with any arguments."

Deny-rule reach (from the table):

| Your `deny` rule names | Example rule | Claude Code also blocks |
| :- | :- | :- |
| An alias | `Skill(review)` | The bundled `/code-review`, through its `/review` alias |
| An unqualified name | `Skill(deploy)` | A nested skill listed as `apps/web:deploy` |
| A skill synced from claude.ai | `Skill(anthropic-skills:deploy)` | That skill when Claude Desktop delivers it to a session as a plugin |
| The plugin form of a synced skill | `Skill(deploy:deploy)` | The synced skill |
| A skill in the parameter form | `Skill(skill:deploy)` | The skill whichever of its names Claude calls it by, including its alias and display name |

> "Claude Code matches an `allow` rule only against the skill's own name and
> the name in Claude's invocation."

> "**Hide individual skills** by adding `disable-model-invocation: true` to
> their frontmatter. This removes the skill from Claude's context entirely."

- **Reimplementation need:** Yes. The `Skill` tool + `Tool(name)` /
  `Tool(name *)` permission-rule grammar is a general permission-engine
  feature that the skills area consumes; a clean-room implementation needs the
  tool-permission layer anyway.

### F15 — Legacy slash commands are the *same* mechanism minus two fields

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Choose where skills load" (bullet "**Command files**") and the
  top-of-page note
- **Status:** `OBSERVED-DOC`

> "**Custom commands have been merged into skills.** A file at
> `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md`
> both create `/deploy` and work the same way. Your existing `.claude/commands/`
> files keep working. Skills add optional features: a directory for supporting
> files, frontmatter to control whether you or Claude invokes them, and the
> ability for Claude to load them automatically when relevant."

> "**Command files**: a Markdown file in `.claude/commands/` is the older format
> and still works. It supports the same frontmatter except `name` and `paths`.
> … Prefer a skill for new work, since skills also support supporting files."

Cross-checked against `https://code.claude.com/docs/en/commands.md`:

> "A command is only recognized at the start of your message. Text that follows
> the command name becomes its arguments. At the terminal prompt, you can start
> one message with several skills: typing `/skill-a /skill-b do XYZ` loads both
> skills and passes the trailing text to each as arguments. Up to six skills
> can be chained."

> "| **Skill** | A bundled skill. It works like skills you write yourself: a
> prompt handed to Claude. |"

- **Reimplementation need:** Yes, and this is the answer to "how does a skill
  differ from a slash command". The difference is **not** a separate
  mechanism: a command file is a skill with a degenerate directory, missing
  `name` and `paths` support, and a different command-name derivation rule
  (filename → `/name`, subdirectory path with `/` → `:` → `/dir:name`).
  Implementing one loader that handles both is simpler and matches the
  reference product's own direction.

### F16 — Bundled skills, and the settings that control them

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Bundled skills"
- **Status:** `OBSERVED-DOC` for the list and settings; the count of bundled
  skills on a given install is `UNKNOWN` from docs alone (see §7).

> "Claude Code includes a set of bundled skills, such as `/doctor`,
> `/code-review`, `/batch`, `/debug`, `/loop`, and `/claude-api`. Bundled
> skills are prompt-based: they give Claude detailed instructions and let it
> orchestrate the work using its tools. Most built-in commands instead execute
> fixed logic directly."

> "You invoke a bundled skill the same way as any other skill, by typing `/`
> followed by the skill name. Claude invokes some bundled skills automatically
> when relevant; others, including `/verify`, run only when you invoke them"

> "To turn bundled skills off, use the `disableBundledSkills` setting."

> "The `/doctor` setup checkup stays typable when `disableBundledSkills` is
> on. To hide it, set the `DISABLE_DOCTOR_COMMAND` environment variable or a
> `skillOverrides` entry of `"doctor": "off"`."

> "Claude Code includes a set of bundled skills, such as … `/workflow-authoring`
> is available only when dynamic workflows are enabled."

Cross-checked against `https://code.claude.com/docs/en/commands.md` — the
`Purpose` column marks each entry **Skill** for bundled skills and plain
commands for built-ins, which is itself the observable distinction the docs
draw: bundled skills are prompts handed to the model; built-in commands are
fixed logic.

- **Reimplementation need:** Partially. The *mechanism* is fully specified
  (a bundled skill is just a skill shipped with the product). The *list* is
  version-dependent and not exhaustive in the docs.

### F17 — Live change detection and the reload escape hatches

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Choose where skills load" → "Edit a skill during a session"
- **Status:** `OBSERVED-DOC`

> "Claude Code watches skill directories for file changes, except in bare mode.
> When you add, edit, or remove a skill under `~/.claude/skills/`, the project
> `.claude/skills/`, or a `.claude/skills/` inside an `--add-dir` directory,
> Claude Code picks up the change within the current session, without a
> restart."

> "If you create a top-level skills directory that didn't exist when the
> session started, run `/reload-skills` to pick up the skills you put there."

> "Live change detection covers `SKILL.md` text only. For a skill folder that
> is also a plugin, changes to `hooks/`, `.mcp.json`, `agents/`, and
> `output-styles/` need `/reload-plugins` to take effect."

Cross-checked against `https://code.claude.com/docs/en/commands.md`:

> "| `/reload-skills` | Re-scan skill and command directories so skills added
> or changed on disk during the session become available without restarting.
> Reports how many skills are available and how many were added or removed |"

> "| `/skills` | List available skills. Type to filter the list by name,
> description, or source. Press `t` to sort by token count, `Space` or `Enter`
> to cycle a skill's visibility to Claude and the `/` menu, and `Esc` to save
> and close. |"

> "| `/skill-doctor` | Show what each of your skills costs in context and how
> often it gets used, so you can find skills to turn off. Requires Claude Code
> v2.1.252 or later and feature-flag fetching |"

- **Reimplementation need:** Yes. A filesystem watcher over the skill
  directories, plus an explicit re-scan command that reports counts. The
  "watch `SKILL.md` text only" boundary is a documented, implementable
  distinction.

### F18 — The claude.ai sync path: a whole second distribution channel

- **URL:** `https://code.claude.com/docs/en/skills.md`
- **Section:** "Choose where skills load" → "Skills synced from claude.ai"
- **Status:** `OBSERVED-DOC` (not observable on this host — requires a claude.ai
  account sign-in and Anthropic feature-flag fetching)

> "In your terminal, Claude Code syncs those skills in sessions where you sign
> in with your claude.ai account. When the session starts, Claude Code downloads
> your account's skills into `~/.claude/skills/synced/` in the background"

> "* **While you or Claude work in the session**: a check runs about every 10
> minutes.
> * **While the session is idle**: a check runs about every 40 minutes."

> "The sync never delays startup, because Claude waits for a skill's download
> only when it invokes that skill."

> "Claude Code syncs only in a session that signs in with your claude.ai
> account and fetches feature flags from Anthropic. It doesn't sync in these
> sessions:
>
> * A session that doesn't use a sign-in stored by `/login`, such as one that
>   authenticates with an API key, or one where `ANTHROPIC_AUTH_TOKEN`,
>   `CLAUDE_CODE_OAUTH_TOKEN`, or an `apiKeyHelper` script supplies the credential
> * A session that doesn't fetch feature flags, such as one on Amazon Bedrock or
>   one where you set `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
> * A session in bare mode or one you start with `--safe-mode`
> * A session where your organization's managed settings lock skills to plugin
>   sources, or one you start with a `--setting-sources` list that leaves out
>   `user`"

> "Claude Code downloads synced skills and never uploads them."

> "To stop syncing on a machine, set `syncClaudeAiSkills` to `false` in your
> user settings. … the next time it starts it moves the skills it already
> synced to `~/.claude/skills/.trash/`"

> "In any other session on your machine, Claude Code doesn't run `!` commands,
> doesn't attach the files that `@` references name the way it does for a local
> skill, and doesn't substitute the `${CLAUDE_PROJECT_DIR}` and
> `${CLAUDE_SESSION_ID}` placeholders, so the `@` references and both
> placeholders reach Claude as literal text."

Also: the `CLAUDE_CODE_SYNC_SKILLS=1` environment variable makes a
non-interactive run wait for the skill list; and synced skills are namespaced
`/anthropic-skills:<name>` with the `anthropic-skills` namespace reserved.

- **Reimplementation need:** Only if a claude.ai-account channel is wanted.
  The generalisable pattern is worth stealing: **a namespaced distribution
  channel with a reserved namespace, a quarantine directory for removed
  items, download-only (never upload), and a disabled-by-policy switch.**
  A clean-room implementation with its own account backend should copy the
  *shape*, not the endpoint.

### F19 — Error and diagnostic strings (exact text)

- **URL:** `https://code.claude.com/docs/en/skills.md` (primary) and
  `https://code.claude.com/docs/en/errors.md` (cross-check)
- **Section:** "When an injected command fails" / "Control characters in
  injected commands" / "Permission checks on injected commands" / "Characters
  a skill name can't hold"
- **Status:** `OBSERVED-DOC`

| Condition | Exact message |
| :- | :- |
| Injected command exits non-zero | `Shell command failed for pattern "..."` |
| Injected command blocked by a deny rule | `Shell command permission check failed for pattern "..."` |
| `!` command contains a raw control character | `No shell command in <name> was run` |
| Shell injection disabled by policy | `[shell command execution disabled by policy]` |
| `shell: bash` requested but Git Bash missing | `Skill <name> requires bash (`shell: bash` in frontmatter) but Git Bash was not found` |
| Non-spec frontmatter key submitted for packaging | `Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name` |

From `errors.md`:

> "```text
> 1 skill or command name refused: run with --debug to see which ([names]), rename, then restart — a name may not hold hidden, direction-changing or blank-like characters, < or >, or be over 256 characters
> ```"

> "```text
> Not loaded: rename .claude/skills/anthropic-skills, then restart — its name uses "anthropic-skills", a name reserved for the skills synced from your claude.ai account
> ```"

> "Its line in the debug log reads `<name> is not offered`." /
> "Its line in the debug log reads `<name value> is not shown for <skill>`."

- **Reimplementation need:** Yes — as *observable contract*. Exact error text is
  part of a user-visible interface, and matching it makes a reimplementation
  feel identical without copying any code.

### F20 — Black-box observation of the validator (the machine-readable contract)

- **Method:** the published CLI's own `claude plugin validate` command, run
  against synthetic fixtures created in a scratch directory and deleted after
  the run. This is a self-description surface the product publishes for
  exactly this purpose.
- **URL for the documented behaviour:** `https://code.claude.com/docs/en/skills.md`
  → "Troubleshooting" → "Skill not triggering":
  > "To find `SKILL.md` files whose frontmatter doesn't parse, run
  > [`claude plugin validate`](https://code.claude.com/docs/en/plugins/cli-reference#validate-a-directory)
  > on the skills directory, for example `claude plugin validate
  > .claude/skills` for project skills or `claude plugin validate
  > ~/.claude/skills` for personal skills. Requires Claude Code v2.1.233 or later."
- **Status:** `OBSERVED-CLI` (directly observed on this host, 2.1.306)

`claude plugin validate --help` (verbatim, from the local binary's help):

> "Usage: claude plugin validate [options] <path>
>
> Validate a plugin or marketplace manifest, or the skills, agents, and commands
> in a directory
>
> Options:
>   -h, --help        Display help for command
>   --json            Output the validation report as JSON (same exit codes)
>   --profile <name>  Also exit 1 when the plugin directory … would refuse a
>                     submission of the plugin on a check this command runs …
>                     (choices: "directory")
>   --strict          Treat warnings as errors (exit 1). Use in CI to fail on
>                     unrecognized fields, missing metadata, and other issues
>                     that the runtime tolerates."

The JSON envelope observed (stable field names):

```json
{
  "success": false,
  "strict": false,
  "target": "…\\.claude\\skills",
  "manifest": null,
  "contents": [],
  "advice": [],
  "directory": null
}
```

Per-file entry shape:

```json
{
  "file": "…\\SKILL.md",
  "type": "skill",
  "errors":   [ { "path": "frontmatter", "message": "…", "code": null } ],
  "warnings": [ { "path": "description",  "message": "…", "code": null } ],
  "notes": [],
  "gatingHooks": []
}
```

Observed behaviours (all reproduced in
`agent-reference-shots/area10-skills/plugin-validate-probes.json`):

| Fixture | Observed result |
| :- | :- |
| All 20 documented frontmatter fields set | `success: true` in both normal and `--strict` mode; no errors, no warnings |
| `name` + `description` + `context: fork` + `agent` + `background` + `paths` + `hooks` + `metadata` | `success: true` under `--strict` |
| Misspelled `description` key + unknown key `totally-unknown-field` | `--strict` → `success: true`, **no** warning about the unknown field; a warning at `path: "description"`: "No description in frontmatter. A description helps users and Claude understand when to use this skill." |
| Malformed YAML frontmatter | `success: false`, one **error** at `path: "frontmatter"`: "YAML frontmatter failed to parse: YAML Parse error: Unexpected token. At runtime this skill loads with empty metadata (all frontmatter fields silently dropped)." |
| No frontmatter block at all | `success: true` with one **warning** at `path: "frontmatter"`: "No frontmatter block found. Add YAML frontmatter between --- delimiters at the top of the file to set description and other metadata." |
| Non-spec field `argument-hint` | `success: true` under `--strict`; **not** flagged |
| Skill folder named `synced` | `success: true`; **not** flagged by the validator |
| Folder / frontmatter `name` containing `<` | `success: true`; **not** flagged by the validator |
| 200-character directory name | `success: true`; **not** flagged by the validator |
| Legacy `.claude/commands/<name>.md` file | `success: true`; **not** listed in `contents` |
| Directory without `.claude-plugin/plugin.json` or `marketplace.json` | `success: false`, error at `path: "directory"`: "No manifest found in directory. Expected .claude-plugin/marketplace.json or .claude-plugin/plugin.json" |

Three conclusions:

1. **The validator is frontmatter-shape-aware but not semantic-policy-aware.**
   It knows the field *names* (it reports "No description in frontmatter") but
   does not enforce reserved names, forbidden characters, the 256-character
   limit, or the Agent Skills spec subset. Those checks live in the *runtime
   loader*, not the validator. A reimplementer needs both layers.
2. **The malformed-YAML behaviour matches the docs exactly** — the tool's own
   message says the skill "loads with empty metadata (all frontmatter fields
   silently dropped)", which is precisely what the doc says: "If the YAML
   between the markers doesn't parse, the skill still loads with no fields
   set."
3. **Unknown fields are tolerated even in `--strict` mode** on this path,
   which is consistent with the doc's "Claude Code ignores a field it doesn't
   recognize without reporting an error" — though the `--strict` help text
   promises to "fail on unrecognized fields". Whether `--strict` applies the
   unknown-field rule only to plugin manifests rather than skill frontmatter is
   `UNKNOWN`.

Also observed on this host (product's own debug log, public log lines only):

> `Loading skills from: managed=…, user=…, project=[]`
> `Loaded 2 unique skills (2 unconditional, 0 conditional, managed: 0, user: 2, project: 0, additional: 0, legacy commands: 0)`
> `getPluginSkills: Processing 3 enabled plugins`
> `Total plugin skills loaded: 0 (0 duplicate/user-owned entries skipped)`
> `getSkills returning: 2 skill dir commands, 0 plugin skills, 38 bundled skills, 1 builtin plugin skills`

The debug log's internal category names (`managed`, `user`, `project`,
`additional`, `legacy commands`) corroborate the four-source discovery model
in F4, and the counters distinguish "unconditional" from "conditional" skills
— i.e. skills whose activation depends on `paths` matching. Sanitized copy:
`agent-reference-shots/area10-skills/debug-log-skill-discovery.txt`.

Two real `SKILL.md` files installed on this machine were read to confirm the
format in the wild. One uses
`allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/discover.py:*) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/discover.py:*)`
— i.e. the `${CLAUDE_SKILL_DIR}` substitution inside `allowed-tools` exactly as
documented in F9 — and another uses a `metadata:` map with `version` and
`tool_count` keys. Sanitized copy:
`agent-reference-shots/area10-skills/observed-skill-frontmatter.txt`.

---

## 3. Evidence references

### 3.1 Public documentation fetched (all `OBSERVED-DOC`)

| Page | URL | Retrieved as |
| :- | :- | :- |
| Skills (primary) | `https://code.claude.com/docs/en/skills.md` | raw markdown, 110,552 bytes, saved to `scratch-probe/_docfetch/skills.md` |
| Settings reference | `https://code.claude.com/docs/en/settings-reference.md` | cross-check for `skillListingBudgetFraction`, `skillListingMaxDescChars`, `skillOverrides`, `syncClaudeAiSkills`, `disableBundledSkills`, `disableSkillShellExecution`, `allowManagedPermissionRulesOnly` |
| Commands reference | `https://code.claude.com/docs/en/commands.md` | cross-check for `/skills`, `/reload-skills`, `/skill-doctor`, `/doctor`, and the Skill-vs-built-in-command distinction |
| Tools reference | `https://code.claude.com/docs/en/tools-reference.md` | cross-check: "To extend Claude with reusable prompt-based workflows, write a skill, which runs through the existing `Skill` tool rather than adding a new tool entry." |
| Sub-agents | `https://code.claude.com/docs/en/sub-agents.md` | cross-check: the inverse `skills:` preload field, "up to the first 32 distinct names" |
| Errors | `https://code.claude.com/docs/en/errors.md` | cross-check: exact "name refused" and "name reserved" startup notices |
| Hooks guide | `https://code.claude.com/docs/en/hooks-guide.md` | cross-check: the `ConfigChange` hook matcher value `skills` |

### 3.2 Commands executed against the published CLI (all `OBSERVED-CLI`)

```
claude --version                                # 2.1.306 (Claude Code)
claude --help                                   # skill/plugin-related flags
claude plugin validate --help
claude plugin init --help
claude plugin details --help
claude plugin list                              # "No plugins installed. …"
claude plugin validate <path> --json            # ~14 fixture variants
claude plugin validate <path> --strict --json
```

### 3.3 Artifacts saved

| Path | Contents |
| :- | :- |
| `agent-reference-shots/area10-skills/README.md` | Index of the artifacts below, with the compliance note |
| `agent-reference-shots/area10-skills/plugin-validate-probes.json` | 14 validator runs against synthetic `SKILL.md` fixtures |
| `agent-reference-shots/area10-skills/cli-skill-surfaces.txt` | The CLI's own skill/plugin help text |
| `agent-reference-shots/area10-skills/debug-log-skill-discovery.txt` | Sanitized skill-discovery lines from the product's `--debug` log |
| `agent-reference-shots/area10-skills/observed-skill-frontmatter.txt` | Frontmatter of two real installed `SKILL.md` files |
| `scratch-probe/_docfetch/skills.md` | The raw documentation markdown (110,552 bytes) |

---

## 4. Capability table — Area 10 (skills)

| # | Capability | Status | Source |
| :- | :- | :- | :- |
| 1 | `SKILL.md` = required frontmatter + Markdown body | `OBSERVED-DOC` | F1 |
| 2 | 20 frontmatter fields with exact names | `OBSERVED-DOC` | F2 |
| 3 | Unknown fields ignored silently; bad YAML → skill loads with no fields | `OBSERVED-DOC` + `OBSERVED-CLI` | F2, F20 |
| 4 | Boolean coercion: `yes/no/on/off/1/0` in any case, plus `true/false` | `OBSERVED-DOC` | F2 |
| 5 | Six spec fields portable outside Claude Code; others are extensions | `OBSERVED-DOC` | F3 |
| 6 | Seven discovery locations + parent-directory walk to repo root | `OBSERVED-DOC` | F4 |
| 7 | Nested skills lazy-load on first file access in that subtree | `OBSERVED-DOC` | F4 |
| 8 | Precedence: enterprise > personal > project; skill > command file | `OBSERVED-DOC` | F4 |
| 9 | Symlinked skill folders loaded once per target | `OBSERVED-DOC` | F4 |
| 10 | Reserved folder names `synced`, `anthropic-skills` | `OBSERVED-DOC` | F4 |
| 11 | Command-name derivation (dir name / `name` / `:ns` / `plugin:`) | `OBSERVED-DOC` | F5 |
| 12 | Forbidden characters in names; 256-char limit; debug tag `[names]` | `OBSERVED-DOC` | F5, F19 |
| 13 | Two invocation switches; three context-loading states | `OBSERVED-DOC` | F6 |
| 14 | Slash-at-start = run; slash-mid-sentence = permission only | `OBSERVED-DOC` | F6 |
| 15 | Model attempt at a `disable-model-invocation` skill is blocked | `OBSERVED-DOC` | F6 |
| 16 | Skill body persists across turns; identical reinvocation does not duplicate | `OBSERVED-DOC` | F7 |
| 17 | Compaction re-attaches skills: 5,000 tokens each, 25,000 combined, newest first | `OBSERVED-DOC` | F7 |
| 18 | `allowed-tools` pre-approval, turn-scoped, additive, not gated by trust | `OBSERVED-DOC` | F8 |
| 19 | `disallowed-tools` removes tools from the pool, turn-scoped | `OBSERVED-DOC` | F8 |
| 20 | `allowManagedPermissionRulesOnly` nullifies `allowed-tools` in project/personal skills | `OBSERVED-DOC` | F8 |
| 21 | 10 substitution variables with exact names | `OBSERVED-DOC` | F9 |
| 22 | Two-pass substitution (args then `${CLAUDE_*}`), no recursive expansion, `\` escape | `OBSERVED-DOC` | F9 |
| 23 | `` !`cmd` `` and ``` ! ``` blocks inject live shell output at render time | `OBSERVED-DOC` | F10 |
| 24 | Single-pass injection; output not rescanned | `OBSERVED-DOC` | F10 |
| 25 | Failing injected command aborts the whole invocation | `OBSERVED-DOC` | F10 |
| 26 | Exit-1 carveout for search/comparison commands only | `OBSERVED-DOC` | F10 |
| 27 | Injected commands never prompt; deny/ask override `allowed-tools` | `OBSERVED-DOC` | F10 |
| 28 | `disableSkillShellExecution` substitutes a placeholder | `OBSERVED-DOC` | F10 |
| 29 | `context: fork` runs the body as a subagent prompt; no history | `OBSERVED-DOC` | F11 |
| 30 | `background: false` forces a wait; several contexts always wait | `OBSERVED-DOC` | F11 |
| 31 | Forked-skill edits escape session checkpoints | `OBSERVED-DOC` | F11 |
| 32 | Per-turn skill listing with a 1%-of-context budget, least-used-first drop | `OBSERVED-DOC` | F12 |
| 33 | `skillListingBudgetFraction` (default 0.01), `skillListingMaxDescChars` (default 1536) | `OBSERVED-DOC` | F12 |
| 34 | `skillOverrides` four-state visibility, default `"on"` | `OBSERVED-DOC` | F13 |
| 35 | `Skill` / `Skill(name)` / `Skill(name *)` permission-rule grammar | `OBSERVED-DOC` | F14 |
| 36 | Legacy `.claude/commands/` files accepted; same frontmatter minus `name`/`paths` | `OBSERVED-DOC` | F15 |
| 37 | Up to six skills stacked in one terminal message; SDK/`-p` loads only the first | `OBSERVED-DOC` | F15 |
| 38 | Bundled skills are prompt-based; `disableBundledSkills` turns them off | `OBSERVED-DOC` | F16 |
| 39 | Live `SKILL.md` change detection; `/reload-skills`, `/reload-plugins` | `OBSERVED-DOC` | F17 |
| 40 | `/skills` and `/skill-doctor` introspection surfaces | `OBSERVED-DOC` | F17 |
| 41 | claude.ai account sync into `~/.claude/skills/synced/`, download-only | `OBSERVED-DOC` | F18 |
| 42 | Machine-readable `claude plugin validate --json` report | `OBSERVED-CLI` | F20 |
| 43 | Exact error strings for injection, permission, and name failures | `OBSERVED-DOC` | F19 |
| 44 | `paths` glob restricts automatic activation | `OBSERVED-DOC` | F2, F4 |
| 45 | `model` / `effort` overrides scoped to the invoking turn | `OBSERVED-DOC` | F2 |
| 46 | `hooks` frontmatter registers hooks for the rest of the session | `OBSERVED-DOC` | F2 |
| 47 | Subagent `skills:` field preloads up to 32 distinct skills | `OBSERVED-DOC` | §3.1 cross-check |

---

## 5. Dependencies

### 5.1 Requires network access
- **claude.ai skill sync** (F18) — periodic checks every ~10 min active / ~40 min idle; requires the claude.ai account API.
- **Plugin marketplace** operations (`/plugin install`, `claude plugin eval`) — `https://code.claude.com/docs/en/skills.md` → "Run evals with skill-creator" documents `/plugin marketplace add anthropics/claude-plugins-official`.
- Everything else in this area — loading, parsing, discovery, invocation, injection, forking — works fully offline once skills are on disk.

### 5.2 Requires a supported account
- claude.ai sign-in (`/login`) for the sync channel, for `anthropic-skills:` namespacing, and for account-enabled skills in Cowork/cloud.
- `/skill-doctor` "isn't available in sessions that skip feature-flag fetching" — i.e. it needs Anthropic feature flags.
- `/doctor`'s usage check is plan-gated (Pro, Max, Team, Enterprise) and "requires Claude Code v2.1.305 or later"; it is "omitted while Remote Control is connected".

### 5.3 Requires a model provider
- Any skill with `context: fork` requires a working model for the subagent.
- Skills that are purely *reference* material and are never invoked still consume context on every turn (the listing), which requires a model with a context window to hold it.
- The `model` and `effort` frontmatter fields are only meaningful against a provider that supports them, and a value excluded by an organization's `availableModels` allowlist "isn't used, and the session keeps its current model".

### 5.4 Requires external services
- None for local skills. Injected `!` commands may call any external service the user configures (e.g. `gh pr diff`); that is user-supplied, not product-supplied.

### 5.5 Minimal viable dependency set for a clean-room Area-10 implementation
1. A **YAML frontmatter parser** — a standard library, or a small hand-rolled subset reader (the field set is flat and small; `metadata` is a map).
2. A **directory walker** that resolves the seven locations and the parent-to-repo-root walk, with symlink de-duplication by real path.
3. A **name validator** implementing the forbidden-character set and the 256-character limit.
4. A **substitution engine** implementing the two-pass, non-recursive, backslash-escaped template rules.
5. A **shell executor** for `!` injection, with the failure/permission semantics of F10 and a single-pass guarantee.
6. A **tool-permission layer** capable of `Tool(name)` / `Tool(name *)` allow/deny/ask rules, plus per-turn grant scoping.
7. A **context-budget accountant** for the per-turn skill listing.
8. **No Anthropic-proprietary asset is required.** Every item above is standard engineering.

---

## 6. Limitations of this investigation

1. **One documentation page.** This document covers
   `https://code.claude.com/docs/en/skills.md` in depth, with cross-checks
   against seven related pages. It does not cover the plugin packaging
   system, the hooks system, or the subagent system in their own right —
   those are separate areas.
2. **Subscription-gated behaviour is documented, not observed.** This host
   runs against a custom `ANTHROPIC_BASE_URL` with no claude.ai account
   sign-in. The sync channel, Cowork/cloud skill loading, account-enabled
   skills, `/doctor`'s usage check, and `/skill-doctor` are all marked
   `OBSERVED-DOC`.
3. **The runtime loader was not observed under load.** I confirmed the
   *validator's* behaviour exhaustively (F20) but did not observe the runtime
   loader's ordering guarantees, its duplicate-resolution in ambiguous cases,
   or its behaviour under a deliberately conflicting `.claude/skills` tree in a
   live session.
4. **No live `/skills` menu screenshot.** The `/skills` menu is an interactive
   TUI surface; capturing it in a scripted, non-interactive run is unreliable
   on this host, so the documentation's description of it is reported as
   `OBSERVED-DOC` rather than as an observation.
5. **No measurement of the description-drop heuristic.** "Drops descriptions
   starting with the skills you invoke least" is documented, but the actual
   ordering when usage counts tie is `UNKNOWN`.
6. **Version gates are numerous and moving.** The page cites minimum versions
   for at least a dozen behaviours (`v2.1.196`, `v2.1.218`, `v2.1.228`,
   `v2.1.233`, `v2.1.246`, `v2.1.252`, `v2.1.257`, `v2.1.260`, `v2.1.269`,
   `v2.1.273`, `v2.1.277`, `v2.1.280`, `v2.1.281`, `v2.1.282`, `v2.1.286`,
   `v2.1.295`, `v2.1.305`). They are reported as stated, but a reimplementation
   should not treat them as requirements.

---

## 7. Unresolved questions (`UNKNOWN`)

1. **The exact ranking algorithm for "least used" skills when the listing
   overflows.** Documented as "least-used-first"; the tie-break and the
   treatment of never-invoked skills are not specified.
2. **The internal ordering of the skill listing** as presented to the model —
   alphabetical, by location, by recency? The docs show the listing as a set
   with names and descriptions but do not pin the order.
3. **How the runtime loader resolves a name collision between a *nested*
   skill and a *plugin* skill**, or between a legacy command file and a plugin
   skill. The precedence table covers several pairs but not all.
4. **Whether `--strict` is supposed to fail on unknown skill frontmatter
   fields.** The `--strict` help says it will "fail on unrecognized fields",
   but the observed run on a skill with `totally-unknown-field` returned
   `success: true`. Possibly the rule applies only to plugin manifests, or
   only when a `description` is also malformed. Not resolvable from the docs.
5. **Whether the validator ever enforces the reserved names, forbidden
   characters, the 256-character limit, or the Agent Skills spec subset.**
   Observed: it does not. Documented: the runtime does. The exact split
   between validator and runtime is not documented.
6. **How `paths` matching interacts with `disable-model-invocation: true`,
   with `context: fork`, and with skills in `--add-dir` directories.**
7. **The precise semantics of `arguments` when the same name appears twice,
   or when a name collides with a shell variable.**
8. **How `!` injection interacts with a session whose working directory has
   changed** ("That directory moves when Claude runs `cd`") — is the directory
   re-read per command, or captured at render time?
9. **The behaviour of `!` injection when the command writes to stderr under
   PowerShell** (the docs only state the bash behaviour: "Bash merges stderr
   into stdout").
10. **Whether the `hooks` frontmatter accepts the same schema as the
    `hooks` settings key**, and what the `once` option does. The skills page
    defers to `/docs/en/hooks#hooks-in-skills-and-agents`.
11. **The exact number and identity of bundled skills** on any given release.
    Observed on this host: 38 bundled skills were reported in the debug log,
    but the list is version-, provider- and account-specific and is not
    enumerated in the docs.
12. **Whether `/skills` can cycle visibility for a skill whose frontmatter
    sets `disable-model-invocation: true`** — the commands page says no, but
    the interaction with `skillOverrides` in managed settings is described
    only partially.

---

## 8. Recommended scope for an independent functional implementation

### 8.1 In scope — build these (this is the whole Area-10 feature)

| P | Component | What it must do | Anchored in |
| :- | :- | :- | :- |
| **P0** | **Skill loader** | Walk the discovery roots (user, project, parent-to-repo-root, nested-lazy, added dirs, plugin, enterprise); parse `SKILL.md`; tolerate bad YAML and unknown fields; de-duplicate symlink targets; expose a stable in-memory skill record | F2, F4, F20 |
| **P0** | **Frontmatter schema** | The 20 exact field names; `description` optional with fallback to the first non-empty Markdown line; boolean coercion `yes/no/on/off/1/0/true/false`; `metadata` must be a map or is dropped; `compatibility` capped at 500 chars | F2 |
| **P0** | **Command-name resolver** | Directory name or `name` → command; `:`-qualified nested form on clash; `plugin:skill` namespacing; the forbidden-character validator and the 256-char limit; reserved namespaces | F5, F4 |
| **P0** | **Invocation control** | `disable-model-invocation` and `user-invocable` with the exact three-row context-loading table; slash-at-start vs slash-mid-message; block-and-redirect when the model tries a non-invocable skill | F6 |
| **P0** | **Listing + budget** | Per-turn listing of all names; descriptions dropped least-used-first over a `skillListingBudgetFraction` of the context window; per-entry `skillListingMaxDescChars` cap | F12 |
| **P0** | **Content lifecycle** | Render once into a single message; persist across turns; identical-rerender → note instead of duplicate; changed render → re-append; compaction re-attaches at 5,000/25,000 tokens, newest-first | F7 |
| **P1** | **Substitution engine** | All 10 variables; `$ARGUMENTS`/`$ARGUMENTS[N]`/`$N`/named `$name`; the `ARGUMENTS: <value>` append fallback; two-pass order (args → `${CLAUDE_*}`); no recursive expansion; single-backslash escaping | F9 |
| **P1** | **Dynamic injection** | `` !`cmd` `` and ```` ```! ```` blocks; single-pass, never rescanned; abort the whole invocation on failure; exit-1 carveout for search/comparison commands; never prompt at render time; deny/ask override `allowed-tools`; `disableSkillShellExecution` placeholder | F10 |
| **P1** | **Tool permissions** | `allowed-tools` / `disallowed-tools`, turn-scoped, additive vs. subtractive; `Skill` / `Skill(name)` / `Skill(name *)` rule grammar; a managed-policy override that nullifies project `allowed-tools` | F8, F14 |
| **P1** | **Legacy command files** | `.claude/commands/<name>.md` and nested `/dir:name` mapping; same frontmatter minus `name` and `paths`; the skill-wins-over-file rule | F15 |
| **P2** | **Forked execution** | `context: fork` → subagent with the body as prompt, no history; `background: false` to wait; the always-wait cases; checkpoint interaction | F11 |
| **P2** | **Visibility overrides** | `skillOverrides` with the four states and the default `"on"`; source-sensitivity (alias keys only in managed/`--settings`); plugin skills excluded | F13 |
| **P2** | **Live reload** | Watch `SKILL.md` in the watched roots; `/reload-skills` re-scan reporting counts; `/reload-plugins` for plugin components | F17 |
| **P2** | **Introspection** | `/skills` list with filter and sort by token cost; `/skill-doctor` cost + usage report; `/context` listing-size row | F12, F17 |
| **P2** | **Validator** | A JSON validator with the same envelope (`success`, `strict`, `target`, `manifest`, `contents`, `advice`, `directory`), per-file `errors`/`warnings` with `path` and `message`, and a `--strict` mode | F20 |
| **P3** | **Account sync** | Namespaced `/provider:skill` channel, download-only, a quarantine/trash directory, a policy switch, and the reserved namespace | F18 |

### 8.2 Explicitly out of scope for a first implementation
- **Plugin packaging, marketplaces, and `claude plugin eval`** — a separate area with a large surface; the skills area only needs the `plugin:skill` namespacing convention.
- **The claude.ai account sync channel** — requires an account backend and a server-side catalog. Implement the *shape* (namespace, quarantine, download-only, policy switch) with a local directory first.
- **Bundled skills as a product feature** — shipping a skill library is content, not mechanism. The mechanism (`disableBundledSkills`, `skillOverrides` on a bundled alias) is what matters.
- **Byte-level parity of the `/skills` menu** — match the *information architecture* (what's listed, what the keys do), not the glyphs.
- **Reproducing the reference product's internal transcript schema for skills** — not documented, and the docs warn the transcript schema changes between versions.

### 8.3 Design decisions a clean-room implementer should make deliberately
1. **Implement the Agent Skills spec subset first and make the Claude Code
   extensions an optional superset.** Six fields (`name`, `description`,
   `license`, `compatibility`, `metadata`, `allowed-tools`) are a public
   standard; everything else is a local extension. Choosing the spec as the
   base makes your skills portable to other tools for free.
2. **Make the skill listing an explicit, budgeted, observable artifact.** The
   reference product exposes its listing size in `/context` and its cost in
   `/doctor`. Publishing your own listing size is cheap and turns a
   performance problem into a visible number.
3. **Never let a skill's own frontmatter widen its own trust beyond the turn
   it was invoked in.** `allowed-tools` is turn-scoped and `disallowed-tools`
   is turn-scoped; keeping that invariant prevents a skill from permanently
   arming the toolset.
4. **Decide deliberately about `allowed-tools` and workspace trust.** The
   reference product applies a project skill's `allowed-tools` even in an
   untrusted workspace, and the docs explicitly warn about it. That is a
   defensible choice; a clean-room implementation should make the same choice
   consciously and document it, or invert it deliberately.
5. **Implement injection as a single-pass, abort-on-failure, never-prompting
   preprocessor.** This is both the reference product's documented behaviour
   and the correct security posture: the output of an injected command must
   never be re-scanned for further injection, and a failure must not
   half-render a skill.
6. **Treat skill content as data, never as instructions to your own
   runtime.** A `SKILL.md` is authored by whoever committed it; it should be
   able to direct the *model*, but it should never be able to alter the
   agent's own configuration, expand its own permissions beyond the turn, or
   cause further shell execution from its own output.
7. **Version your frontmatter schema and keep a validator in CI.** The
   reference product's own validator is the pattern: a fast, offline,
   machine-readable check that a skill's frontmatter parses and has the
   fields the product understands. The strict/non-strict split and the
   `success`/`contents[].errors`/`contents[].warnings` envelope are worth
   copying because they are an observable contract, not an implementation
   detail.
8. **Ship the discovery precedence table as configuration, not as code.** The
   reference product hard-codes it (enterprise > personal > project) but also
   documents it. Making it a policy table lets an organisation add a scope
   without a code change — and makes the precedence behaviour testable.

### 8.4 What an implementer can rely on as *specified* (vs. merely observed)

- **Fully specified by public documentation:** every frontmatter field name and
  its semantics; the seven discovery locations and their paths; the
  precedence order; the command-name derivation rules; the three
  invocation/context states; the substitution variable names and the
  escape rules; the injection syntax and its failure and permission
  semantics; the listing-budget defaults (`0.01`, `1536`); the
  `skillOverrides` states; the `Skill(...)` permission-rule grammar; the
  exact error strings; the compaction re-attachment constants (5,000 /
  25,000); the legacy-command-file compatibility rule.
- **Observable on this host but not fully specified in the docs:** the
  validator's JSON envelope and its field-level warnings and errors; the
  debug-log discovery counters and their categories; the fact that unknown
  frontmatter fields are tolerated even under `--strict`; that the validator
  does *not* enforce reserved names, forbidden characters, or the spec subset.
- **Not available at all:** the runtime loader's internal ordering and
  tie-breaking; the model-side description-matching behaviour; the system
  prompt; the internal model behaviour; the model weights; the provider
  gateway's private API; the source code.

---

*End of Area 10. Other areas of the multi-area study have their own artifacts
under `agent-reference-shots/areaN-*/`; the parent `agent-evidence.md` covers
CLI startup, project selection, user input, and the conversation loop.*
