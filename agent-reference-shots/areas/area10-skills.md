# Area 10 — Skills, reusable instructions, project instructions, and subagent workflows

**Product observed:** Claude Code 2.1.306 (native build, win32-x64)
**Investigated:** 2026-10-21
**Public docs consulted:** https://code.claude.com/docs/en/skills.md, `/en/memory.md`, `/en/sub-agents.md`, `/en/workflows.md`, `/en/output-styles.md`, `/en/plugins/manifest-reference.md`, `/en/settings-reference.md`, `/en/env-vars.md`
**Artifacts:** `agent-reference-shots/area10-skills/` (13 sanitized files)

## Area 10 Executive summary

This is the product's **extension layer** — the part that lets a user or an
organisation teach the agent how to work without editing the binary. It is also
the part with the **highest ratio of machine-checkable contract to prose**.
Almost every rule below was confirmed twice: once against the public
documentation, and once against the product's own debug log, its own `init`
event, and its own transcript attachment records.

Seven structural facts dominate.

1. **Three scopes, one resolver.** Skills load from managed
   (`C:\Program Files\ClaudeCode\.claude\skills`), personal
   (`~/.claude/skills`), and project (`.claude/skills`) scopes, plus nested
   directories, `--add-dir` directories, plugins, and claude.ai-synced skills.
   The resolver's own debug line names every scope and its exact path
   (OBSERVED-CLI). Name collisions are resolved **at name-resolution time,
   not at load time** — the loader counts both copies of a same-named skill but
   only one description reaches the model (OBSERVED-CLI).
2. **Two invocation-control flags that are *not* opposites.**
   `disable-model-invocation: true` removes the skill's description from the
   model's context while keeping it in the `/` menu; `user-invocable: false`
   does the reverse. Both were read directly out of the model's own
   `skill_listing` attachment and cross-checked against the `init.skills` and
   `init.slash_commands` registries (OBSERVED-CLI). This is the single most
   commonly-misunderstood detail in the whole extension layer.
3. **The loader is a code-execution surface.** `` !`cmd` `` inside a skill body
   is executed by the harness **at render time**, before the content reaches
   the model — not by the model via a tool call. It is recognised only at the
   start of a line or after whitespace; `KEY=!`cmd`` is left literal
   (OBSERVED-CLI). A policy setting (`disableSkillShellExecution`) substitutes
   `[shell command execution disabled by policy]` for the command, confirmed
   end-to-end (OBSERVED-CLI).
4. **Project instructions are a *concatenation*, never an override.** Every
   `CLAUDE.md` from the filesystem root down to the cwd is concatenated in
   order, `CLAUDE.local.md` is appended after `CLAUDE.md` at each level, and
   `@path` imports are expanded into their own entries (OBSERVED-CLI). A
   path-scoped `.claude/rules/*.md` rule is not in the launch-time context at
   all — it arrives later as a `nested_memory` attachment when a matching file
   is touched (OBSERVED-CLI).
5. **AGENTS.md is a built-in plugin, and its setting has an unusually tight
   scope.** The `cc-plugin-agents-md@builtin` plugin implements the
   AGENTS.md fallback; its `instructionFiles` option is read from user
   settings, `--settings`, or managed settings **only** — the debug log says
   explicitly "(project settings are not read)" (OBSERVED-CLI).
6. **The extension layer publishes a complete machine-readable registry.**
   `init.skills`, `init.agents`, `init.plugins`, `init.slash_commands`,
   `init.terminal_slash_commands`, `init.output_style`, `init.memory_paths`,
   plus the `skill_listing`, `agent_listing_delta`, `instructions` and
   `nested_memory` attachments. An implementer can copy these shapes verbatim
   (OBSERVED-CLI).
7. **`claude plugin validate --json` is a real, scriptable validator** with a
   stable JSON envelope and per-file findings — and it is *more* than the
   documentation says: it validates a whole components directory
   (`.claude/skills`, `.claude/agents`) as well as a plugin manifest
   (OBSERVED-CLI).

Two contradictions between doc and binary are worth recording up front:
`claude import --dry-run` is documented but **not available in this build**
(OBSERVED-CLI), and `claude plugin init --with` does not accept `commands`
even though the runtime still loads legacy `.claude/commands/` files
(OBSERVED-CLI).

### Area 10 compliance boundary

Claude Code is proprietary and closed source. Anthropic's Consumer ToS §3 and
Commercial ToS §D.4 prohibit decompiling, reverse engineering, disassembling,
or reducing the Services to human-readable form, and the docs state *"The
Claude Code binary must not be modified."* Anthropic has enforced this via DMCA
takedown.

**The REA reverse-engineering toolset available in this session was therefore
deliberately NOT used against the Claude Code binary.** No binary was opened, no
JavaScript bundle extracted or de-minified, no source map dumped, no
credential store or keychain read, no licence file read, no private account
data accessed, no binary modified.

Permitted and used:
(a) public documentation at `code.claude.com/docs/en/...` and
`anthropic.com/legal`;
(b) the published CLI's own user-facing inspection surfaces — `claude --help`,
`claude plugin validate|list|details|init|marketplace`, `claude agents
--json`, `claude doctor`, `claude --debug` — which exist to be read by users;
(c) black-box observation of the published CLI's behaviour, including the
`init` event, the debug log, and the session transcript's own attachment
records, which are the product's record of what it injected.

All configuration mutation was confined to **temporary directories** under the
system temp dir with `CLAUDE_CONFIG_DIR` redirected, so the real `~/.claude`
was never modified. No `claude plugin install`, `claude mcp add`, `claude
import`, or any other command that writes to a real install location was run.

**Machine caveat.** This host runs Claude Code against a **custom
`ANTHROPIC_BASE_URL`** (a third-party gateway serving a non-Anthropic model,
`minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. `claude doctor`
reports "Not connected to the Anthropic API". Consequently:
- behaviour that depends on the **model obeying an instruction** (e.g. does an
  output style actually change the model's tone?) is **model-limited, not
  product-limited** — such findings are marked UNKNOWN or INFERRED, never
  OBSERVED;
- claude.ai-account-gated behaviour (skills synced from claude.ai, Cowork and
  cloud sessions, managed/org policy) is **OBSERVED-DOC only**;
- the `Agent` tool's `model` enum (`sonnet|opus|haiku|fable`) was observed as a
  schema, but the gateway serves a model id outside that set, so per-model
  behaviour is UNKNOWN.

**Prompt-injection note.** All fetched web content and all tool output was
treated as **untrusted data**. No directive found in a fetched page or in a
transcript was followed, and no command found in fetched content was executed.
One incidental observation worth recording: a skill body is *content the
harness executes*, so a third-party skill in a repository is executable content
by construction — see F18 and §10.

## Area 10 Findings

### F10-1 — Skill discovery is a three-scope resolver that prints its own search paths

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/skills.md — § "Choose where skills load"
**Evidence:** `agent-reference-shots/area10-skills/discovery-and-budget-probes.txt` P1

The documented scope table:

| Location | Path | Loads in |
| :- | :- | :- |
| Enterprise | `.claude/skills/<name>/SKILL.md` in the managed settings directory | All users on managed machines |
| Personal | `~/.claude/skills/<name>/SKILL.md` | All projects on this machine |
| Project | `.claude/skills/<name>/SKILL.md` | Sessions in this repository |
| Nested | `<subdir>/.claude/skills/<name>/SKILL.md` | Sessions started in or below `<subdir>` |
| Additional directory | `.claude/skills/...` in a `--add-dir` directory | That session |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | Wherever the plugin is enabled, as `/plugin:skill` |
| claude.ai account | Skills enabled for the claude.ai account | Cowork / cloud / signed-in terminal sessions |

**OBSERVED-CLI** — the loader's own debug line names the scopes and their exact
paths, and counts what it found:

```
[DEBUG] Loading skills from: managed=C:\Program Files\ClaudeCode\.claude\skills,
        user=<SCRATCH_CFG>\skills,
        project=[<PROJ>\.claude\skills]
[DEBUG] Loaded 4 unique skills (4 unconditional, 0 conditional, managed: 0,
        user: 2, project: 2, additional: 0, legacy commands: 0)
[DEBUG] Loaded 1 skills-as-plugins
[DEBUG] getPluginSkills: Processing 4 enabled plugins
[DEBUG] Checking plugin probe-scaffold: skillsPath=exists, skillsPaths=0 paths
[DEBUG] Attempting to load skills from plugin probe-scaffold default skillsPath:
        <SCRATCH_CFG>\skills\probe-scaffold\skills
[DEBUG] Loaded 1 skills from plugin probe-scaffold default directory
[DEBUG] Total plugin skills loaded: 1 (0 duplicate/user-owned entries skipped)
[DEBUG] getSkills returning: 4 skill dir commands, 1 plugin skills,
        38 bundled skills, 1 builtin plugin skills
[DEBUG] Watching for changes in skill/command directories: ...
```

Three contract details worth copying:
- the counts are **per-scope** (`managed/user/project/additional`) and
  `legacy commands` is counted **separately** from skills, even though both
  surface in the same `/` command list;
- the final line splits the result into four populations: skill-directory
  commands, plugin skills, bundled skills, and builtin-plugin skills;
- the loader **watches** the skill and command directories for live changes
  (`Watching for changes in skill/command directories: ...`).

**Clean-room opportunity.** Implement discovery as an ordered list of
`(scope, path)` roots with a per-scope counter and a single
`getSkills()`-equivalent that returns the four populations separately. Emit
the same one-line-per-scope diagnostic; it is the cheapest possible
support tool and it makes every precedence question answerable without
guessing.

### F10-2 — Scope precedence is applied at name resolution, not at load time

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Resolve skills that share a name"
**Evidence:** `discovery-and-budget-probes.txt` P2

Fixture: skill name `precedence-test` present in **both** the user scope and the
project scope, with different descriptions.

The loader counted both: `Loaded 4 unique skills (... user: 2, project: 2 ...)`.
The `skill_listing` attachment the model received contained:

```
- precedence-test: PERSONAL scope version of the precedence probe skill.
```

So the **user-scope** description is the one that reaches the model; the
project-scope copy is shadowed. This matches the documented precedence
("Enterprise over personal, and personal over project").

The non-obvious part is the *timing*: the loader's counter says four skills
were loaded, but only one of the two same-named skills survives into the
listing. A reimplementation that resolves collisions during the scan (rather
than after) will produce a different counter and different diagnostics. The
product's behaviour — load everything, resolve at naming time — is the one to
copy, because it lets `project` skills exist without being clobbered by
`personal` ones at the file level.

**Clean-room opportunity.** Separate *loading* (collect every candidate with
its scope tag) from *resolution* (choose a winner per command name, with
enterprise > personal > project). Keep both: the loaded set drives `/doctor`
and the resolved set drives the model listing. Document the precedence table
as data, not as code.

### F10-3 — Nested `.claude/skills/` is a *startup* scope only when the session starts inside it

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Load skills in monorepos and subdirectories"
**Evidence:** `discovery-and-budget-probes.txt` P3

The same project tree, two working directories:

```
# session started at <PROJ>
[DEBUG] project=[<PROJ>\.claude\skills]
[DEBUG] Loaded 4 unique skills (4 unconditional, 0 conditional, managed: 0,
        user: 2, project: 2, additional: 0, legacy commands: 0)

# session started at <PROJ>/sub
[DEBUG] project=[<PROJ>\sub\.claude\skills, <PROJ>\.claude\skills]
[DEBUG] Loaded 5 unique skills (5 unconditional, 0 conditional, managed: 0,
        user: 2, project: 3, additional: 0, legacy commands: 0)
```

The scope list is an **ordered array of directories**, nearest-first, and the
parent's `.claude/skills` is still searched. The nested skill `deep-skill`
appeared only in the sub-directory session.

The doc adds the completion of the rule: a `.claude/skills/` directory
**below** the start directory does not load at startup — it loads the first
time Claude reads or edits a file in that subdirectory, and does not appear in
the `/` menu until then (`/add-dir` with the subdirectory path forces it to
load sooner).

**Clean-room opportunity.** Model the project scope as a list, not a single
path, and add a `conditional` bucket for skills whose activation depends on
file access. The debug line already distinguishes `N unconditional, M
conditional` — copy that vocabulary.

### F10-4 — `paths:` frontmatter creates a *conditional* skill, held in a separate store

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — frontmatter table, `paths` row
**Evidence:** `discovery-and-budget-probes.txt` P4

Fixture: `<PROJ>/.claude/skills/pathscond/SKILL.md` with `paths: "**/*.ts"`.

```
[DEBUG] [skills] 1 conditional skills stored (activated when matching files are touched)
[DEBUG] Loaded 2 unique skills (1 unconditional, 1 conditional, managed: 0,
        user: 1, project: 1, additional: 0, legacy commands: 0)
```

A path-scoped skill is stored **outside** the unconditional listing and
activates when a matching file is touched. `paths` accepts a comma-separated
string or a YAML list, uses the same glob format as path-specific rules, and
supports brace expansion (`src/**/*.{ts,tsx}`) with a shared budget of 1,000
expanded patterns and 4 MiB per rule.

**Clean-room opportunity.** Implement path-conditioned skills as a distinct
lifecycle: *registered → dormant → active on matching file access*. This is a
genuine context-saving feature that most agents lack, and it is cheap to build
once the glob matcher exists.

### F10-5 — The two invocation-control flags are **not** opposites

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Control who invokes a skill"
**Evidence:** `agent-reference-shots/area10-skills/skill-rendering-probes.txt` P3; `invocation-control-and-instruction-probes.txt` P1

Documented table:

| Frontmatter | You can invoke | Claude can invoke | When loaded into context |
| :- | :- | :- | :- |
| (default) | Yes | Yes | Description always in context, full skill on invoke |
| `disable-model-invocation: true` | Yes | Not on its own | **Description not in context**, full skill on invoke |
| `user-invocable: false` | No | Yes | Description always in context, full skill on invoke |

**OBSERVED-CLI** — read directly out of the model's own `skill_listing`
attachment against the `init.skills` and `init.slash_commands` registries:

| Skill | in `init.skills` | in `/` menu | in model listing |
| :- | :- | :- | :- |
| `dmi` (`disable-model-invocation: true`) | **yes** | **yes** | **no** |
| `uif` (`user-invocable: false`) | **no** | **no** | **yes** |
| `plain` (neither) | yes | yes | yes |

So `disable-model-invocation` removes the **description** (so the model cannot
choose the skill) but keeps the command available to the user;
`user-invocable: false` keeps the **description** (so the model can use it as
background knowledge) but removes the command from the user's menu.

The typed error returned when the model tries the first one:

```
<tool_use_error>Skill dmi cannot be used with Skill tool due to
disable-model-invocation. Ask the user to run /dmi themselves - it cannot be
invoked via the Skill tool. Do not replicate this skill's workflow by other
means - it is reserved for explicit user invocation.</tool_use_error>
```

The error text is a **policy instruction to the model**, not just a failure
message — it explicitly tells the model not to achieve the same effect another
way. That is a design pattern worth copying verbatim in spirit.

**Clean-room opportunity.** Expose two independent booleans
(`model_may_invoke`, `user_may_invoke`) rather than one enum, derive the three
surfaces (listing visibility, menu visibility, tool-call permission) from
them, and make the refusal error carry an explicit "do not work around this"
directive. Most agent frameworks conflate these into one flag and get the
semantics wrong.

### F10-6 — `skillOverrides` has four states that affect three different surfaces

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/settings-reference.md — `skillOverrides`
**Evidence:** `invocation-control-and-instruction-probes.txt` P1

Fixture: three project skills with
`{"ovr-one":"name-only","ovr-two":"user-invocable-only","ovr-three":"off"}`.

| State | `init.skills` | `/` menu | model listing |
| :- | :- | :- | :- |
| `on` (default) | yes | yes | name + description |
| `name-only` | yes | yes | **name only** |
| `user-invocable-only` | yes | yes | **hidden from the model** |
| `off` | **no** | **no** | hidden |

Observed `init.skills` = `['ovr-one','ovr-two']`; observed `init.slash_commands`
= `['ovr-one','ovr-two']`; the listing contained exactly `- ovr-one` for these
three.

The naming is counter-intuitive: `user-invocable-only` is the state that
**hides the skill from the model** and leaves it in the user's menu. The
`/skills` menu labels that state `user-only`.

Two further documented facts: a skill absent from `skillOverrides` is treated
as `"on"`; and plugin skills are **not** affected by `skillOverrides` at all.

**Clean-room opportunity.** Implement overrides as a four-state enum applied
*after* frontmatter resolution, applied uniformly to all three surfaces, and
expose a one-command "cost and usage report" (`/skill-doctor`) so the user can
see which skills are costing context. The doc notes `/doctor` reports the
listing's context cost and its biggest contributors.

### F10-7 — The skill listing is a plain-text attachment with a hard character budget

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Skill descriptions are cut short"; https://code.claude.com/docs/en/settings-reference.md — `skillListingBudgetFraction`, `skillListingMaxDescChars`; https://code.claude.com/docs/en/env-vars.md — `SLASH_COMMAND_TOOL_CHAR_BUDGET`
**Evidence:** `discovery-and-budget-probes.txt` P5, P6; `registry-and-tool-contracts.txt` § 4

**OBSERVED-CLI** — the loader warns on overflow and names both remedies:

```
[DEBUG] Sending 17 skills via attachment (initial)
[WARN] Skill listing over budget: 17 skills, 6484 chars > 6000 budget
        - descriptions will be truncated. Run /skills to disable some, or
        raise skillListingBudgetFraction in settings.
```

The attachment itself:

```json
{ "type": "skill_listing",
  "content": "- precedence-test: PERSONAL scope version of the precedence probe skill.\n- probe-scaffold\n- nested-only: A skill that lives only in the project root .claude/skills.\n...",
  "skillCount": 17, "isInitial": true,
  "names":  ["precedence-test","probe-scaffold", ...],
  "digests": ["24709798e5b55fc0","0e2f2269d902ca43", ...] }
```

Format: `- <name>: <description>`, or `- <name>` alone when the description was
dropped. **Names are never dropped** — only descriptions — so the model can
still invoke a skill it can no longer match.

The documented budget: 1% of the context window, with an 8,000-character
fallback, overridable by `SLASH_COMMAND_TOOL_CHAR_BUDGET` (legacy name) or
`skillListingBudgetFraction` (default `0.01`); per-entry cap
`skillListingMaxDescChars` (default 1536, applied to `description` +
`when_to_use` combined). Overflow drops descriptions **starting with the
least-used skills**, so frequently-used skills keep their text.

The parallel `names` / `digests` arrays (16 hex chars per skill) are a
content-hash per entry — evidently used to detect that a rendered description
changed and to decide whether a re-invocation is a repeat of one already in
context.

**Clean-room opportunity.** Implement the listing as a **budgeted, ordered,
always-name-inclusive** channel, with per-entry caps, a usage-ranked
truncation policy, and a machine-readable `names`+`digests` sidecar so the
listing can be diffed and resent incrementally. This is one of the few places
where a naive implementation ("just concatenate all descriptions") will
blow up a context window, and the product's design here is directly
copyable.

### F10-8 — `SKILL.md` frontmatter is a fixed, hyphen-cased field set with three distinct failure modes

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Frontmatter reference"
**Evidence:** `agent-reference-shots/area10-skills/plugin-validate-probes.json`, `plugin-cli-probes.txt` P5

Field names use lowercase words separated by hyphens, except `when_to_use`.
Recognised fields: `name`, `description`, `when_to_use`, `argument-hint`,
`arguments`, `disable-model-invocation`, `user-invocable`, `allowed-tools`,
`disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`,
`hooks`, `paths`, `shell`, `metadata`, `license`, `compatibility`.

Three distinct failure modes, all observed:

1. **Unknown field** → silently ignored, no error. Observed: a skill with
   `descripton:` produced no validator finding at all.
2. **Missing frontmatter block** → the file loads with **no fields set**; the
   validator emits a *warning*:
   `"No frontmatter block found. Add YAML frontmatter between --- delimiters at the top of the file to set description and other metadata."`
3. **Unparseable YAML** → the skill still loads, but with **all frontmatter
   fields silently dropped**. The validator emits an *error*:
   `"YAML frontmatter failed to parse: YAML Parse error: Unexpected EOF. At runtime this skill loads with empty metadata (all frontmatter fields silently dropped)."`

Other observed contract points: the opening `---` must be the file's **first
line**, otherwise the whole file (markers included) is treated as body text;
boolean fields accept `yes/no/on/off/1/0` in any case as well as `true/false`;
an omitted `description` falls back to the first non-empty line of the body.

Outside Claude Code (claude.ai uploads, the Skills API, `package_skill.py`),
only six fields are allowed — `name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools` — and an extra field is a **hard
error**: `Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed
properties are: allowed-tools, compatibility, description, license, metadata, name`.

**Clean-room opportunity.** Implement a two-tier frontmatter schema: a
superset for the agent runtime and a strict subset for a packaging/upload
path, with an explicit error listing the allowed keys. Make the parse-failure
path **non-fatal but loud** (drop fields, report the error) exactly as the
reference does — a skill that fails to parse should still be usable, and the
author should be told why it is not behaving.

### F10-9 — The skill body is a template language: `$ARGUMENTS`, `$N`, `$name`, and `${CLAUDE_*}` variables

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Available string substitutions", § "Pass arguments to skills"
**Evidence:** `skill-rendering-probes.txt` P1

Substitution table:

| Variable | Meaning |
| :- | :- |
| `$ARGUMENTS` | all arguments as typed; if no placeholder consumes one, `ARGUMENTS: <value>` is appended |
| `$ARGUMENTS[N]` / `$N` | argument by 0-based index |
| `$name` | named argument declared in the `arguments:` frontmatter list |
| `${CLAUDE_SESSION_ID}` | current session id |
| `${CLAUDE_EFFORT}` | current effort level |
| `${CLAUDE_SKILL_DIR}` | directory containing the skill's `SKILL.md` |
| `${CLAUDE_PROJECT_DIR}` | project root |
| `${CLAUDE_PLUGIN_ROOT}` | plugin install dir (plugin skills only) |
| `${CLAUDE_PLUGIN_DATA}` | plugin data dir (plugin skills only) |

**OBSERVED-CLI** — skill body `ARGS=[$ARGUMENTS] IDX0=[$0] NAMED=[$thing]
SID=[${CLAUDE_SESSION_ID}]`, invoked as `/argtest hello world`:

```
ARGS=[hello world] IDX0=[hello] NAMED=[$thing] SID=[afeba6c6-0ceb-4520-bf05-a1cb3e49607a]
```

and the harness additionally prepended a `Base directory for this skill: <path>`
line and appended an `ARGUMENTS: <value>` line.

`$thing` was **not** expanded because the skill declared no `arguments:`
frontmatter — an unknown named placeholder is left literal. Documented
behaviours not re-probed here: an indexed placeholder with no corresponding
argument stays literal; a named placeholder with no matching argument expands
to the empty string; an argument value containing `$1` is inserted literally
(not re-expanded); a backslash escapes a literal `$` before a digit,
`ARGUMENTS`, or a declared name.

`${CLAUDE_SKILL_DIR}` and `${CLAUDE_PROJECT_DIR}` are substituted in **two**
places: the skill's markdown body **and** the Bash rules inside its
`allowed-tools` frontmatter — which is the trick that lets a skill
pre-approve its own bundled script without a permission prompt.

**Clean-room opportunity.** Implement substitution as an explicit, ordered
expansion pass with a documented precedence (`$ARGUMENTS`/`$N`/`$name` first,
then `${CLAUDE_*}`), applied to *both* the body and the tool-allow rules so a
skill can pre-approve a script it references by an absolute path. Document
the "argument values are never re-scanned" rule — it is a security property,
not an implementation detail.

### F10-10 — The loader executes `` !`cmd` `` inside a skill body itself — a code-execution surface

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Inject dynamic context", § "How injected commands run", § "Permission checks on injected commands"
**Evidence:** `skill-rendering-probes.txt` P2; `invocation-control-and-instruction-probes.txt` P2

Skill body:

```
Start of line:
!`echo INJECTED_INLINE_OK`
After whitespace:
VALUE !`echo INJECTED_WS_OK`
```

Rendered content delivered to the model:

```
Start of line:
INJECTED_INLINE_OK
After whitespace:
VALUE INJECTED_WS_OK
```

**The harness ran both shell commands at skill-render time.** No tool call was
made by the model; the substitution happened in the loader, before the content
reached the model. In the same probe series, `INJECTED=!"echo INJECTED_OK"`
was left **literal**, because the `!` was preceded by `=`.

The documented rules, all consistent with the observation:
- the inline form is recognised only when `!` is at the start of a line or
  immediately after whitespace;
- multi-line commands use a fenced block opened with ```` ```! ````;
- substitution runs **once** over the original file, so command output is not
  re-scanned for further placeholders — "a command cannot emit a placeholder
  for a later pass to expand";
- a **failed** command aborts the entire skill invocation (not just its own
  placeholder): `Shell command failed for pattern "..."`, with output under
  `[stderr]`; exit code 1 from search/comparison commands is a carveout, exit
  ≥2 always fails;
- a command denied by a permission rule aborts with `Shell command permission
  check failed for pattern "..."`;
- injected commands never prompt, but they *are* permission-checked.

**Policy control, OBSERVED-CLI** — with
`{"disableSkillShellExecution": true}` in project settings, the rendered body
was:

```
START [shell command execution disabled by policy] END
```

The command did not run and no shell was spawned. Documented scope: the setting
applies to skills and commands from user, project, plugin, and
additional-directory sources; **bundled and managed skills are unaffected**; it
is intended for managed settings where users cannot override it.

**Clean-room opportunity.** This is the highest-risk surface in the whole
extension layer and the one most worth getting right. A clean-room
implementation should: (a) make injection execution explicit and auditable —
log every executed command with its resolved pattern; (b) default to a
**prompt** (or deny) for injected commands unless the skill is trusted, rather
than running them silently; (c) implement the `disableSkillShellExecution`
policy and make it settable from *managed* configuration so an organisation can
switch it off globally; (d) never re-scan injected output. The reference
implementation's silent-execute default is the thing to beat.

### F10-11 — `context: fork` runs a skill in an isolated subagent, and is not counted as a spawned subagent

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Run skills in a subagent"
**Evidence:** `skill-rendering-probes.txt` P4

Fixture: skill with `context: fork` and `agent: Explore`, body "Reply with
exactly the token FORKED_OK."

`claude -p ... --output-format json` returned:

```
"result": "FORKED_OK"
```

with `subagent_stats: {"spawned": 0, ...}` and `"num_turns": 7`.

So the skill body ran in an isolated context and only its final text came back
to the caller — but the harness's own accounting does **not** count a
`context: fork` skill as a spawned subagent (`spawned: 0`). An implementer
building a cost or concurrency ledger must decide whether a forked skill
counts; the reference says no, which is arguably an accounting bug worth
flagging rather than copying.

Documented semantics: the forked subagent gets the agent type's system prompt
plus the skill content as its task; it does **not** see the conversation
history; `Explore` and `Plan` start without CLAUDE.md and git status; the fork
runs in the background by default unless `background: false`; and Claude Code
waits for the result anyway in `-p`/SDK mode, when
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, when the same skill is already
running, and when a scheduled task fires it.

**Clean-room opportunity.** Implement `context: fork` as a first-class
execution mode of the skill runner — isolated context, agent-type system
prompt, result-only return — and **count it in the subagent ledger**. Making
the accounting honest is a differentiator, not a copy.

### F10-12 — Subagent definitions are a camelCase frontmatter schema with a documented "skip" list

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/sub-agents.md — § "Frontmatter reference", § "Subagent files Claude Code skips"
**Evidence:** `registry-and-tool-contracts.txt` § 3; `invocation-control-and-instruction-probes.txt` P3

Subagent files live in `.claude/agents/*.md` (project), `~/.claude/agents/`
(user), a plugin's `agents/`, or the managed directory, and may also be
supplied via a `--agents` JSON flag. Field names use **camelCase** (unlike
skills, which use hyphens) and must match exactly.

Documented fields: `name` (required), `description` (required), `tools`,
`disallowedTools`, `model`, `permissionMode`, `maxTurns`, `autoCompactWindow`,
`skills`, `mcpServers`, `hooks`, `memory`, `background`, `omitClaudeMd`,
`effort`, `isolation`, `color`, `initialPrompt`, `experimental`.

The documented **skip list** — a file is treated as documentation, not an
agent, when the frontmatter has any of these problems: no `name`; an opening
`---` that isn't the file's first line; a `name` that starts with `-`, contains
`:`, or is longer than 256 characters; a `name` but no `description`; or YAML
that does not parse. Each skip is written to the debug log.

**OBSERVED-CLI** — `claude plugin validate <PROJ>/.claude/agents` validates an
agents directory and reports `✔ Validation passed`; the same command is
documented as the way to find agents-directory files whose frontmatter does
not parse.

**Clean-room opportunity.** Adopt the same discipline: a strict, documented
schema with camelCase (or hyphen-case — but pick one and enforce it), a
machine-checkable skip list, and a **validator that can be pointed at a
directory** rather than only at a manifest. The "invalid file becomes
documentation, not an error" rule is a good one: it degrades gracefully
instead of blocking the session.

### F10-13 — A subagent's `skills:` field preloads the **entire `SKILL.md`, frontmatter included**

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/sub-agents.md — § "Preload skills into subagents"; https://code.claude.com/docs/en/skills.md — § "Run skills in a subagent"
**Evidence:** `invocation-control-and-instruction-probes.txt` P3

Documented: *"The full skill content is injected, not only the description."*

**OBSERVED-CLI** — a subagent with `skills: [preload-me]` reported the content
it received:

```
---
name: preload-me
description: A skill whose full body should be preloaded into a subagent.
---
PRELOAD_TOKEN_ZZZ first line of the skill body.
Second line.
```

The **YAML frontmatter is included**, not stripped. That is a difference from
the normal listing (`- <name>: <description>`) and from the `.claude/rules/`
loader (which removes the frontmatter before injecting the rule).

The run's own ledger is a useful shape for an implementer:

```json
"subagent_stats": { "spawned": 1,
  "requested": { "background": 0, "foreground": 1, "unset": 0 },
  "started_in_background": 0, "max_depth": 1, "spawned_by_subagents": 0,
  "completed": 1, "failed": 0,
  "killed": { "parent": 0, "user": 0, "system": 0 },
  "refused": { "depth_limit": 0, "concurrency_limit": 0, "budget": 0 },
  "by_type": { "preload-agent": 1 } }
```

Note the `refused` sub-object (depth/concurrency/budget) — refusals are
recorded as first-class outcomes rather than as errors.

The documented inverse direction is a skill with `context: fork`: the skill
supplies the *task* and the agent type supplies the *system prompt*; a
subagent supplies the *system prompt* and the delegation message, and
`skills:` supplies the reference material.

**Clean-room opportunity.** Implement the two directions as one composition
matrix and document it (skill→task / agent→prompt; agent→prompt /
skill→reference). Include the frontmatter in the preload (it is cheap and
lets the subagent see the skill's own metadata), and keep a per-agent-type
ledger with a `by_type` breakdown and explicit refusal reasons.

### F10-14 — The delegation tool is `Task` in the harness registry and `Agent` in the model's schema

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Evidence:** `invocation-control-and-instruction-probes.txt` P4; `registry-and-tool-contracts.txt` § 2

`init.tools` for the observed session:

```
["Task","Bash","CronCreate","CronDelete","CronList","DesignSync","Edit",
 "EnterWorktree","ExitWorktree","Glob","Grep","ListAgents","NotebookEdit",
 "Read","ReportFindings","ScheduleWakeup","SendMessage","Skill","TaskStop",
 "ToolSearch","WebFetch","WebSearch","Workflow","Write"]
```

`Task` is present; `Agent` is **not**. But the tool definition actually sent to
the model (captured from the API request shape) is named **`Agent`**:

```json
{ "name": "Agent",
  "input_schema": { "type": "object", "properties": {
    "description": {...}, "prompt": {...}, "subagent_type": {...},
    "model": { "enum": ["sonnet","opus","haiku","fable"] },
    "effort": { "enum": ["low","medium","high","xhigh","max"] },
    "run_in_background": { "type": "boolean" },
    "isolation": { "enum": ["worktree","remote"] } },
  "required": ["description","prompt"], "additionalProperties": false } }
```

The model-facing description also states the fork semantics: `"fork"` forks
the current conversation (inheriting full context, ignoring a `model`
override); any other type starts a fresh agent, `general-purpose` by default.

**Clean-room opportunity.** Pick one canonical tool name and be consistent
across the registry, the schema, and the transcripts. If transcript
compatibility matters, note that `init.tools` uses `Task` while the API request
uses `Agent` — a reimplementation that must read Claude Code transcripts should
tolerate both.

### F10-15 — The agent registry the model sees is a structured, incremental attachment

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Evidence:** `registry-and-tool-contracts.txt` § 3; `invocation-control-and-instruction-probes.txt` P5

```json
{ "type": "agent_listing_delta",
  "addedTypes": ["claude","Explore","general-purpose","Plan","preload-agent",
                 "probe-scaffold:example","statusline-setup"],
  "addedLines": [
    "- claude: Catch-all for any task ... (Tools: *)",
    "- Explore: Read-only search agent ... (Tools: All tools except Agent, Artifact, ArtifactComments, ArtifactData, ArtifactCheck, ExitPlanMode, Edit, Write, NotebookEdit)",
    "- preload-agent: A probe agent that preloads one skill ... (Tools: Read, Grep)"],
  "builtInTypes": ["claude","Explore","general-purpose","Plan","statusline-setup"],
  "builtInPluginTypes": [], "removedTypes": [],
  "isInitial": true, "showConcurrencyNote": true }
```

Each line is `- <type>: <description> (Tools: <list>)`. The tool list is
rendered as an **explicit exclusion list** when the agent inherits most tools
("All tools except Agent, Artifact, … Edit, Write, NotebookEdit") and as an
inclusion list when it is restricted ("(Tools: Read, Grep)"). `builtInTypes`
separates built-ins from plugin/user/project agents; `removedTypes` supports
removing an agent mid-session; `isInitial` distinguishes the first payload
from an incremental delta.

**Clean-room opportunity.** Publish the agent registry as a **delta
attachment** with a stable line format, an explicit built-in/user/project
split, and removal support. The exclusion-list rendering is a nice touch: it
keeps the line short for the common "inherits everything" case while still
being unambiguous.

### F10-16 — Project instructions are concatenated in a defined order, and `@path` imports become separate entries

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "How CLAUDE.md files load", § "Import additional files"
**Evidence:** `agent-reference-shots/area10-skills/instructions-attachment-probe.txt` A, B, C

Documented loading rules:
- `CLAUDE.md` and `CLAUDE.local.md` load from the cwd **and every directory
  above it**;
- all discovered files are **concatenated, not overridden**;
- across the tree, content is ordered **from the filesystem root down to the
  working directory**, so instructions closer to the launch point are read
  last;
- within each directory, `CLAUDE.local.md` is appended **after** `CLAUDE.md`;
- subdirectory files load **lazily**, on first read/write/edit of a file
  there, not at launch;
- block-level HTML comments are stripped before injection (comments inside code
  blocks are preserved);
- a CLAUDE.md may exceed 4 MiB — the file is then skipped;
- `claudeMdExcludes` skips specific files.

**OBSERVED-CLI** — the product's own `instructions` attachment records each
file separately with its path, a `type` (`Project`), and its content:

```json
{ "type": "instructions", "files": [
  { "path": "...\\proj\\CLAUDE.md", "type": "Project", "content": "..." } ] }
```

With a `CLAUDE.md` containing `@sub/CLAUDE.md`, the attachment had **two**
entries — the import became its own file entry rather than being inlined into
the parent's content:

```json
{ "type": "instructions", "files": [
  { "path": "...\\proj5\\CLAUDE.md", "type": "Project",
    "content": "# Project instructions\nBase instructions. Import the sub guide with @sub/CLAUDE.md" },
  { "path": "...\\proj5\\sub\\CLAUDE.md", "type": "Project",
    "content": "# Sub instructions\nSub-directory instructions." } ] }
```

Documented import rules: relative and absolute paths both allowed; relative
paths resolve **relative to the file containing the import**, not the working
directory; imports may nest to a **maximum depth of four hops**; a path with
spaces needs a backslash before each space; a **quoted** path is not imported
at all; import parsing skips Markdown code spans and fenced code blocks; and a
path wrapped in backticks stays literal.

Security rule worth copying: an import in a project-level file whose path
resolves **outside the working directory** is "external" and triggers a
one-time approval dialog listing the files; declining keeps them disabled
permanently.

**Clean-room opportunity.** Implement instruction loading as an ordered list of
`(path, type, content)` records with an explicit precedence order
(managed → user → root→cwd concatenation, `CLAUDE.local.md` after
`CLAUDE.md` per level), a separate import-resolution pass with a 4-hop depth
cap and cycle detection, and a per-project "external import" approval record.
Keeping the *file identity* of each instruction (rather than concatenating to
one blob) makes the context auditable — the user can see exactly which files
shaped the session.

### F10-17 — `.claude/rules/` gives a path-scoped instruction channel that is injected on file access, not at launch

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "Organize rules with `.claude/rules/`", § "Path-specific rules"
**Evidence:** `instructions-attachment-probe.txt` D, E

Rules live in `.claude/rules/*.md` and are discovered **recursively**. A rule
with no `paths` frontmatter loads **unconditionally at launch**, with the same
priority as `.claude/CLAUDE.md`. A rule **with** `paths` loads only when
Claude uses Read, Write, or Edit on a matching file (or views it with a Bash
command that counts as a read).

**OBSERVED-CLI** — the unconditional rule was in the launch-time
`instructions` attachment:

```json
{ "type": "instructions", "files": [
  { "path": "...\\proj8\\.claude\\rules\\plain-rule.md", "type": "Project",
    "content": "# Plain rule\nAlways answer with the token RULE_PLAIN_LOADED." } ] }
```

The path-scoped rule was **not** there. It arrived later, as a
`nested_memory` attachment, when the session read `sample.ts`:

```json
{ "type": "attachment",
  "attachment": {
    "type": "nested_memory",
    "path": "<PROJ>/.claude/rules/ts-rule.md",
    "content": { "type": "Project",
      "content": "# TS rule\nAlways answer with the token RULE_TS_LOADED.\n",
      "globs": ["**/*.ts"],
      "contentDiffersFromDisk": true,
      "rawContent": "---\npaths:\n  - \"**/*.ts\"\n---\n# TS rule\n...",
      "displayPath": ".claude\\rules\\ts-rule.md" },
    "rendered": [ { "content": "<system-reminder>\nContents of <PROJ>/.claude/rules/ts-rule.md:\n\n# TS rule\n...\n\n</system-reminder>" } ],
    "renderedRole": "system" } }
```

The attachment is richly structured: `globs` (the patterns), `rawContent`
(the file **with** frontmatter), `content` (frontmatter stripped), and
`rendered` (the actual system-reminder text, with `renderedRole: "system"`).

Documented rule frontmatter: `paths` is the **only** field read; anything else
is ignored without error; if the YAML does not parse, the frontmatter is
ignored and the rule loads as if it had no `paths`; the frontmatter is removed
before the rule enters context. Pattern budget: a rule's whole `paths` list
shares one budget of 1,000 expanded patterns and 4 MiB; patterns without
braces do not count against it; a pattern that would exceed the budget is used
**unexpanded** (and its literal braces then match nothing).

**Clean-room opportunity.** Implement a rules directory as a first-class
*conditional instruction channel* with glob scoping, brace expansion under a
shared budget, frontmatter stripping, and a documented rule for what happens
when a pattern set is too large. The `nested_memory` attachment shape — with
`globs`, `rawContent`, `content`, and `rendered` — is a good, auditable design
to copy.

### F10-18 — AGENTS.md is a built-in plugin, and its switch is readable only from user/`--settings`/managed scopes

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "AGENTS.md", § "Choose which instruction files load"
**Evidence:** `instructions-attachment-probe.txt` A, B; `invocation-control-and-instruction-probes.txt` P7

Documented default table:

| Your repository has | Claude reads |
| :- | :- |
| `AGENTS.md`, no `CLAUDE.md`/`CLAUDE.local.md` in cwd or above | your `AGENTS.md` |
| `AGENTS.md` **and** a `CLAUDE.md`/`CLAUDE.local.md` in cwd or above | your `CLAUDE.md` files only |
| `CLAUDE.md` that imports `AGENTS.md` | your `CLAUDE.md`, with `AGENTS.md` included through the import |

Files that **count** (and therefore suppress `AGENTS.md`): `CLAUDE.md`,
`.claude/CLAUDE.md`, `CLAUDE.local.md` in the cwd or above. Files that **do
not** count: `~/.claude/CLAUDE.md`, the managed `CLAUDE.md`, and `.claude/rules/`.

**OBSERVED-CLI** — with both files present, only `CLAUDE.md` was in the
`instructions` attachment; with only `AGENTS.md` present, `AGENTS.md` was.

The switch is `pluginConfigs["cc-plugin-agents-md@builtin"].options.instructionFiles`
with values `claude-md-or-agents-md` (default), `claude-md-and-agents-md`,
`claude-md`, `managed-only`.

**OBSERVED-CLI** — passing it via `--settings` produced an attachment with
**both** files:

```json
[ { "path": "...\\proj\\CLAUDE.md", "type": "Project", "content": "# Project instructions..." },
  { "path": "...\\proj\\AGENTS.md",   "type": "Project", "content": "# Agents instructions..." } ]
```

But writing the **same** JSON into the project's `.claude/settings.json` did
**nothing**, and the debug log says why:

```
[DEBUG] plugin cc-plugin-agents-md: no pluginConfigs["agents-md@builtin" or
        "cc-plugin-agents-md@builtin"].options in user, --settings or managed
        settings (project settings are not read); every option is its default
```

The same log line also shows the **legacy plugin ID** still being accepted:
`agents-md@builtin` or `cc-plugin-agents-md@builtin` (the ID changed in
v2.1.285).

**Clean-room opportunity.** Implement `AGENTS.md` as an *optional* alternative
instruction file with an explicit four-value mode, and — importantly — make
the mode itself readable from every settings scope the user might plausibly
use. The reference's project-scope exclusion is a usability trap: a user who
commits the setting to a repo gets silently ignored behaviour. A clean-room
implementation should either honour it everywhere or **warn loudly** when it
is set in a scope that will not be read.

### F10-19 — `skillOverrides`, `disableSkillShellExecution`, `disableBundledSkills`, `disableWorkflows` and `pluginConfigs` form one settings surface

**Status:** OBSERVED-DOC (+ OBSERVED-CLI where noted)
**Source:** https://code.claude.com/docs/en/settings-reference.md, `/en/skills.md`, `/en/workflows.md`
**Evidence:** `invocation-control-and-instruction-probes.txt` P1, P2, P7

| Setting | Scope | Effect |
| :- | :- | :- |
| `skillOverrides` | any file | four-state visibility override (F10-6) |
| `skillListingBudgetFraction` | any file | fraction of the context window for the skill listing (default 0.01) |
| `skillListingMaxDescChars` | any file | per-entry description cap (default 1536) |
| `disableSkillShellExecution` | any file | replaces injected commands with `[shell command execution disabled by policy]` (F10-10, OBSERVED-CLI) |
| `disableBundledSkills` | — | removes bundled skills from the listing |
| `disableWorkflows` / `CLAUDE_CODE_DISABLE_WORKFLOWS=1` | — | disables dynamic workflows |
| `pluginConfigs` | user, `--settings`, managed | per-plugin options, incl. the AGENTS.md mode (F10-18, OBSERVED-CLI) |

**Clean-room opportunity.** Put all extension-layer knobs in one typed
settings schema with an explicit scope table, and make the scope table part of
the documentation *and* of the runtime — a setting that is read in one scope
and ignored in another should produce a diagnostic, not silence.

### F10-20 — Dynamic workflows are a sandboxed, deterministic script layer over subagents

**Status:** OBSERVED-DOC (the runtime was not executed — the gateway build has workflows behind a paid-plan/feature-flag gate that could not be exercised)
**Source:** https://code.claude.com/docs/en/workflows.md

A workflow is a JavaScript file at `.claude/workflows/*.js` or
`~/.claude/workflows/*.js` whose first statement is a pure-literal metadata
block:

```javascript
export const meta = {
  name: 'audit-routes',
  description: 'Audit every route handler for missing auth checks',
}

const found = await agent('List every .ts file under src/routes/.', {
  schema: { type: 'object', required: ['files'], properties: { files: { type: 'array', items: { type: 'string' } } } },
})

const audits = await pipeline(found.files, file =>
  agent(`Audit ${file} for missing authentication checks.`, { label: file })
)
```

Runtime surface: top-level `await`; `agent()`, `pipeline()`, `parallel()`,
`phase()`, `log()`, and a global `args`. The body is plain JavaScript with
**no module loading** — a script containing `import()` fails before the run
starts.

Determinism is enforced by *prohibition*: `Date.now()`, `Math.random()`, and a
no-argument `new Date()` **throw** inside the script, so a relaunched run
repeats the same `agent()` calls; a timestamp must be passed in through `args`.
`meta` must be a plain object literal — if it contains a variable, a function
call, or a spread, `/<name>` is dropped from autocomplete.

Documented limits:

| Limit | Value |
| :- | :- |
| Concurrent agents | 16 by default (fewer on fewer CPUs); `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` 1–256 |
| Items per `parallel()`/`pipeline()` | 4,096 — a longer list is **rejected**, not silently truncated |
| Agents per run | 1,000 |
| Fan-out prefix stagger | up to 5,000 ms (`CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS`) so shared prompt-cache prefixes are reused |
| Agent restarts | at most five; the sixth stalled attempt fails the `agent()` call |
| Per-agent stall | `stallMs` option on the `agent()` call |
| Mid-run user input | none — a run pauses only for agent permission prompts and usage-limit waits |

`agent()` resolves to `null` if stopped or on an unrecoverable API error, and
`pipeline()` keeps the `null` in the results array. A `schema` on an `agent()`
call makes the subagent return JSON of that shape; the schema is checked
**before** the subagent starts, and a provably self-contradictory schema fails
the call without starting the agent.

Bundled: `/deep-research`. The `ultracode` keyword in a prompt makes Claude
write a workflow; `/effort ultracode` makes it plan one for every substantive
task. `/workflows` opens a progress view with phase/agent drill-down and the
keys `j/k` scroll, `f` filter by status, `p` pause/resume, `x` stop, `r`
restart an agent, `s` save the run's script as a reusable command.

**Clean-room opportunity.** This is the most copyable "many-agent" design in
the product, because it is a *script* rather than a model-driven loop: the plan
lives in code, the intermediate results live in script variables, and the
agent's context holds only the final answer. Copy the whole shape — the
pure-literal `meta`, the banned non-determinism, the hard limits with **rejection
rather than silent truncation**, the `null`-on-failure convention, and the
schema pre-flight. Do not copy the exact plan templates; those are content.

### F10-21 — Output styles are a named, switchable instruction bundle with an exact settings key

**Status:** OBSERVED-DOC + OBSERVED-CLI (registration only)
**Source:** https://code.claude.com/docs/en/output-styles.md
**Evidence:** `agent-reference-shots/area10-skills/init-registries.txt` (proj3)

A custom output style is a Markdown file with frontmatter, at
`~/.claude/output-styles/`, `.claude/output-styles/`, or the managed
directory's `.claude/output-styles/`. Frontmatter fields: `name`,
`description`, `keep-coding-instructions`, `force-for-plugin`.

Built-ins: **Default** (no style selected), **Proactive**, **Concise**,
**Explanatory**, **Learning**. Each built-in *keeps* the standard instructions
and adds its own; `Concise` additionally exempts "anything you need in order to
act safely" (error reports, failing test output, security warnings,
destructive-action confirmations) from being shortened.

Selection: `/output-style <style>`, `/config` → Output style, or the
`outputStyle` settings key. The value is **case-sensitive** (`"Explanatory"`,
not `"explanatory"`); a value that does not match a style name exactly falls
back to Default, while the `/output-style` command ignores case. The command
and both menus save to `.claude/settings.local.json` (local project level).

Scope: an output style applies to the **main conversation and to a fork**
(which inherits the parent's conversation and system prompt). Other subagents
run their own system prompt, so styles do not change how they respond. On the
full system prompt, a custom style leaves out Claude Code's built-in software
engineering instructions unless `keep-coding-instructions: true`; on the
shorter prompt that field has no effect.

**OBSERVED-CLI** — the registry reports the resolved style name: with a custom
style installed and `"outputStyle": "Probe Style"` in settings, `init.output_style`
was `"Probe Style"`; in every other probe project it was `"default"`.
Registration and resolution are therefore observed. **Whether the style
actually changes the model's output is model-limited, not product-limited** —
this host serves a non-Anthropic model through a custom gateway, and the
behavioural probe returned an answer rather than an adherence signal. That
half remains **UNKNOWN**.

**Clean-room opportunity.** Implement output styles as a named registry with
exactly the documented selection semantics (case-sensitive key, exact-match
fallback to default, case-insensitive interactive command) and an explicit
"applies to forks, not to subagents" rule. Also implement the
`keep-coding-instructions` switch — it is the only documented way to keep a
persona from degrading the agent's engineering behaviour, and it is easy to
miss.

### F10-22 — `claude plugin validate --json` is a real validator with a stable envelope, and it validates *directories* too

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/plugins/manifest-reference.md — § "Validate the manifest"
**Evidence:** `agent-reference-shots/area10-skills/plugin-cli-probes.txt` P3–P6; `plugin-validate-probes.json`

The JSON envelope:

```json
{ "success": true, "strict": false, "target": "<path>",
  "manifest": { "file": ..., "type": "plugin",
                "errors": [], "warnings": [], "notes": [], "gatingHooks": [] },
  "contents": [],
  "advice": [],
  "directory": { "profile": null, "findings": [], "undecided": [],
                 "incomplete": false, "failure": null, "notes": [] } }
```

`contents` entries are per-file records
(`{file, type, errors[], warnings[], notes[], gatingHooks[]}`, each finding
carrying `path`, `message`, `code`). `directory.findings` entries carry
`{code, title, severity, blocking, hold, file, field, message, fix}`; observed
codes: `README_MISSING`, `LICENSE_MISSING`, `ICON_MISSING`.

Results are tiered exactly as the doc describes:
- `Validation passed` — the manifest loads;
- `Validation passed with warnings` — it loads, but something should be fixed
  (an unknown top-level field that will be stripped, a non-kebab-case `name`, a
  missing `version`/`description`/`author`); `--strict` turns warnings into
  failures in CI;
- `Validation failed` — a type mismatch, a path that is missing or escapes the
  plugin root, or an unknown key inside a strict object.

**OBSERVED-CLI — the command also validates a components directory**, which
the documentation mentions only for `.claude/agents`:

```
$ claude plugin validate <PROJ>/.claude/skills
Validating components in: <PROJ>\.claude\skills
✔ Validation passed

$ claude plugin validate <PROJ>/.claude/commands
✘ Found 1 error:
  ❯ directory: No manifest found in directory. Expected
    .claude-plugin/marketplace.json or .claude-plugin/plugin.json
✘ Validation failed
```

**OBSERVED-CLI — the validator does not enforce the directory-submission
findings**, and says so explicitly:

```
✘ Found 1 problem the plugin directory refuses a submission for:
  ❯ README.md: README missing (README_MISSING). ...
    Fix: Add a README.md to the plugin folder describing what the plugin
    does, how to use it, and any setup it needs, in at least 40 words. ...
⚠ Found 1 plugin directory warning:
  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING). ...
These plugin directory checks do not change the result below. To fail on
problems the directory refuses a submission for, run this command with
--profile directory.
The directory also runs a safety scan and a policy review that this command
does not.
✔ Validation passed
```

**Clean-room opportunity.** Build the validator first, as a standalone tool
with a stable JSON envelope, and point it at **both** manifests and component
directories. Adopt the reference's three-tier result model (passed / passed
with warnings / failed), give every finding a `fix` string, and — better than
the reference — make the submission-profile findings *blocking* under a flag
rather than merely reported. A machine-readable `fix` per finding is what
makes a validator usable from CI.

### F10-23 — A skill folder with a `.claude-plugin/plugin.json` becomes a plugin with id `<name>@skills-dir`

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Where skills live"; https://code.claude.com/docs/en/plugins/manifest-reference.md — § "Standard layout"
**Evidence:** `agent-reference-shots/area10-skills/plugin-cli-probes.txt` P1, P2

**OBSERVED-CLI** — `claude plugin list --json`:

```json
[ { "id": "probe-scaffold@skills-dir", "version": "0.1.0", "scope": "user",
    "enabled": true,
    "installPath": "<SCRATCH_CFG>\\skills\\probe-scaffold" } ]
```

`claude plugin details probe-scaffold@skills-dir` produced a component
inventory and a **token-cost projection**:

```
Component inventory
  Skills (1)  example
  Agents (1)  example
  Hooks (0)
  MCP servers (0)
  LSP servers (0)

Projected token cost
  Always-on:   ~69 tok   added to every session

Per-component (rounded)
  component  always-on  on-invoke
  example          ~50       < 20
  example         < 20       < 20
  On-invoke cost is paid each time a skill or agent fires.
  Token counts are estimates and may differ from actual usage.
```

So the product distinguishes the **always-on** cost (the description the model
sees every turn) from the **on-invoke** cost (the body). This is the same
distinction F10-7's budget enforces, surfaced as a number.

Documented plugin surface: the manifest lives at `.claude-plugin/plugin.json`
and `name` is the only required key. Standard layout: `skills/`, `commands/`,
`agents/`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `output-styles/`,
`workflows/`, `themes/`, `monitors/monitors.json`, `bin/` (added to the Bash
tool's `PATH` while the plugin is enabled), `settings.json` (only `agent` and
`subagentStatusLine` take effect).

Path rules: every component path is relative to the plugin root and must
start with `./`; it must resolve **inside** the plugin root and must **exist**;
a path containing `..` is reported as `Path contains ".." which could be a
path traversal attempt`. Component keys either **replace** their default
location (`commands`, `agents`, `outputStyles`, `workflows`,
`experimental.themes`, `experimental.monitors`), **add** to it (`skills`), or
**merge** with it (`hooks`, `mcpServers`, `lspServers`).

Plugin-name rules: `claude-`, `anthropic-`, `anthropics-` and `cc-plugin-`
prefixes are errors; `claude`, `anthropic`, `anthropics`, `claude-code`,
`claude-mods` are errors; `official` beside `claude`/`anthropic` is an error;
`claude`/`anthropic`/`anthropics` as a whole word elsewhere is a warning. The
error text is `Plugin name "<name>" is reserved: it passes as one of
Anthropic's own`.

Environment variables: `${CLAUDE_PLUGIN_ROOT}` (the installed version),
`${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`, survives updates),
`${CLAUDE_PROJECT_DIR}`. They resolve inline in hook commands, MCP `command`/
`args`/`env`, LSP configs, and **skill, command, and agent Markdown bodies**.

**Clean-room opportunity.** Implement plugins as a packaging layer over the
same skill/agent/hook registries, with a strict path-containment check
(`./`-prefixed, inside the root, exists) and a **reserved-name check** so a
third-party plugin cannot be confused with a first-party one. Expose the
always-on vs on-invoke token projection as a first-class command — it is the
best UX idea in this area and it falls straight out of the budget model.

### F10-24 — `claude agents` is a background-session registry, and `claude import` is unavailable in this build

**Status:** OBSERVED-CLI
**Evidence:** `agent-reference-shots/area10-skills/plugin-cli-probes.txt` P9, P10

**OBSERVED-CLI** — `claude agents --json` returned `[]`, and its own help
describes it as:

```
Usage: claude agents [options]
Manage background agents
  --json   Print active sessions (interactive and background) as a JSON array
           and exit (for scripting; does not require a TTY)
```

So `claude agents` lists **background sessions**, not subagent *definitions*.
Subagent definitions live in `init.agents` and in the `agent_listing_delta`
attachment. The naming collision is real and cost me time: an implementer
reading "agents" will look in the wrong place.

**OBSERVED-CLI** — `claude import --dry-run <spec>`:

```
`claude import` is not yet available in this build.
```

This contradicts the published CLI reference's description of the command. The
command exists in the docs but is gated out of this binary. Recorded as an
OBSERVED-CLI fact about *this build*; the doc remains the specification of the
intended behaviour.

**Clean-room opportunity.** Name the two registries distinctly in your own
design (`sessions` vs `agent definitions`) and expose both in JSON from the
start. For the "import an agent/command from another tool" capability, note
that the reference does not ship it here — so there is an **empty space** in
the reference product for an importer that converts a competitor's agent
definitions into your own format.

### F10-25 — Auto memory is an index-plus-topics directory with an enforced read cap

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "Auto memory"

Auto memory is on by default in local sessions (off by default in self-hosted
environments). Each project gets `~/.claude/projects/<project>/memory/`, with
`<project>` derived from the git repository, so worktrees and subdirectories of
one repo share a directory. The layout:

```
~/.claude/projects/<project>/memory/
├── MEMORY.md           # Index, one line per memory, loaded into every session
├── user_role.md        # One memory
├── feedback_testing.md # One memory
└── ...                 # Any other topic files Claude creates
```

The **first 200 lines of `MEMORY.md`, or the first 25 KB, whichever comes
first, are loaded at session start**; content beyond that is not loaded. If
`MEMORY.md` is over the limit, the write still succeeds but the harness returns
an error telling the model to rewrite the index, "because everything past the
limit is dropped on the next load". The limit applies only to `MEMORY.md` — a
`CLAUDE.md` up to 4 MiB is loaded in full and a larger file is skipped.

Four note types are recorded as a `type` frontmatter field: `user`, `feedback`,
`project`, `reference`. The model is told to keep derivable facts (architecture,
file paths, debugging fixes) out of memory and to skip anything the CLAUDE.md
files already say. Writes to a memory file that begins with YAML frontmatter
get a `modified` frontmatter field with an ISO-8601 timestamp.

The main conversation's auto memory is **not** loaded into subagents; a
subagent's own memory is enabled with the subagent `memory` frontmatter field
(`user`/`project`/`local`) and lives in a separate directory. A *fork* of the
conversation inherits the parent's memory, because it inherits the parent
conversation.

**Clean-room opportunity.** Implement memory as an index-plus-topics layout
with an enforced read cap and an explicit "the index is over its limit" error,
give each subagent a separate memory scope, and stamp writes with a
machine-readable `modified` field. The "the write succeeds but the index must
be rewritten" contract is a good, explicit one to copy — it makes the failure
mode legible to the model instead of silently truncating memory.

### F10-26 — Legacy `.claude/commands/*.md` still load, and are counted separately from skills

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Where skills live"
**Evidence:** `agent-reference-shots/area10-skills/skill-rendering-probes.txt` P5

Fixtures: `<PROJ>/.claude/commands/deploy.md` and
`<PROJ>/.claude/commands/frontend/component.md`.

`init.slash_commands` for that session included `"deploy"` and
`"frontend:component"`, and the debug log recorded:

```
[DEBUG] Loaded 3 unique skills (3 unconditional, 0 conditional, managed: 0,
        user: 1, project: 0, additional: 0, legacy commands: 2)
```

So legacy command files are **counted separately** from skills but surface in
the same `/` command list. A nested command file's name is the subdirectory
path relative to `commands/` with each `/` replaced by `:`, plus the file name
without its extension. Command files accept the same frontmatter as a skill
**except `name` and `paths`**.

**OBSERVED-CLI** — the command-name table is confirmed by the registry:
`.claude/commands/deploy.md` → `/deploy`;
`.claude/commands/frontend/component.md` → `/frontend:component`.

**Clean-room opportunity.** Support the legacy command format as a
first-class alias of a skill with no `name`/`paths` fields, count it in a
separate bucket in the diagnostics, and apply the same `:`-namespacing rule.
Implementing the legacy path is cheap and removes a whole class of "why doesn't
my old command work" support questions.

## Area 10 capability table

| Capability | Status | Evidence | Notes |
| :- | :- | :- | :- |
| Three skill scopes + nested + `--add-dir` + plugin + synced | OBSERVED-DOC + OBSERVED-CLI | F10-1, F10-3 | Loader prints its own scope paths and per-scope counts |
| Scope precedence (enterprise > personal > project) | OBSERVED-CLI + OBSERVED-DOC | F10-2 | Resolved at name-resolution time, not load time |
| Nested `.claude/skills/` startup scope | OBSERVED-CLI | F10-3 | Ordered list of project directories, nearest first |
| `paths:`-conditioned skills | OBSERVED-CLI + OBSERVED-DOC | F10-4 | Stored in a separate "conditional" bucket |
| `disable-model-invocation` hides the description | OBSERVED-CLI | F10-5 | Typed error names the field and forbids a workaround |
| `user-invocable: false` hides the command | OBSERVED-CLI | F10-5 | Opposite of the intuitive reading |
| `skillOverrides` four states | OBSERVED-CLI + OBSERVED-DOC | F10-6 | Affects registry, menu, and model listing |
| Skill-listing character budget + overflow warning | OBSERVED-CLI + OBSERVED-DOC | F10-7 | 1% of context window; observed 6000 chars on this host |
| `skill_listing` attachment with `names` + `digests` | OBSERVED-CLI | F10-7 | Names never dropped; only descriptions |
| `SKILL.md` frontmatter field set + 3 failure modes | OBSERVED-CLI + OBSERVED-DOC | F10-8 | Unknown field ignored; bad YAML drops all fields |
| Argument substitution `$ARGUMENTS` / `$N` / `$name` | OBSERVED-CLI + OBSERVED-DOC | F10-9 | Also applied to `allowed-tools` Bash rules |
| `${CLAUDE_*}` variables | OBSERVED-CLI + OBSERVED-DOC | F10-9 | 7 variables; plugin ones plugin-only |
| Loader-side `` !`cmd` `` execution | OBSERVED-CLI + OBSERVED-DOC | F10-10 | Recognised at line start or after whitespace only |
| `disableSkillShellExecution` policy | OBSERVED-CLI + OBSERVED-DOC | F10-10 | Replaces the command with a literal marker |
| `context: fork` skill execution | OBSERVED-CLI + OBSERVED-DOC | F10-11 | Isolated context; not counted as a spawned subagent |
| Subagent frontmatter schema + skip list | OBSERVED-DOC + OBSERVED-CLI | F10-12 | camelCase; `claude plugin validate` checks a directory |
| Subagent `skills:` preloads the whole file | OBSERVED-CLI + OBSERVED-DOC | F10-13 | Frontmatter included |
| `Agent`/`Task` tool naming split | OBSERVED-CLI | F10-14 | `init.tools` says `Task`; the API request says `Agent` |
| `agent_listing_delta` incremental registry | OBSERVED-CLI | F10-15 | Built-ins vs user types separated; removal supported |
| CLAUDE.md concatenation + `@path` imports | OBSERVED-CLI + OBSERVED-DOC | F10-16 | Imports become their own attachment entries |
| `.claude/rules/` conditional injection | OBSERVED-CLI + OBSERVED-DOC | F10-17 | `nested_memory` attachment with `globs`/`rawContent` |
| AGENTS.md fallback + 4-value mode | OBSERVED-CLI + OBSERVED-DOC | F10-18 | Mode readable only from user/`--settings`/managed |
| Dynamic workflows (`agent`/`pipeline`/`parallel`) | OBSERVED-DOC | F10-20 | Not executed — feature-gated on this host |
| Output styles | OBSERVED-DOC + OBSERVED-CLI (registration) | F10-21 | Adherence UNKNOWN (non-Anthropic model) |
| Plugin manifest + validator JSON envelope | OBSERVED-CLI + OBSERVED-DOC | F10-22 | Validates directories as well as manifests |
| Plugin ids `@skills-dir` / `@builtin` / `@marketplace` | OBSERVED-CLI + OBSERVED-DOC | F10-23 | `plugin details` projects always-on vs on-invoke tokens |
| `claude agents` = background sessions | OBSERVED-CLI | F10-24 | Not the agent-definition registry |
| `claude import` | OBSERVED-CLI (unavailable) | F10-24 | Documented but gated out of this build |
| Auto memory (`~/.claude/projects/<project>/memory/`) | OBSERVED-DOC | F10-25 below | 200 lines / 25 KB index cap |
| Legacy `.claude/commands/*.md` | OBSERVED-CLI | F10-26 below | Counted separately, same `/` menu |
| Synced-from-claude.ai skills | OBSERVED-DOC only | — | Requires a claude.ai account |

## Area 10 dependencies

| Surface | Network | Account | Model provider | External service |
| :- | :- | :- | :- | :- |
| Skill / rule / subagent discovery | no | no | no | — |
| Skill rendering (substitution, injection) | **yes** for injected commands only | no | no | the skill's own command |
| `claude plugin validate` | no | no | no | — |
| `claude plugin list` / `details` | no | no | no | — |
| `claude plugin install` / `marketplace add` | yes | Anthropic account for the directory | no | the marketplace host |
| Synced skills (`~/.claude/skills/synced/`) | yes | claude.ai | no | claude.ai |
| Managed skills / managed rules | no (deployed by the org) | enterprise | no | — |
| Dynamic workflows | yes | paid plan or Anthropic API access (per doc) | yes | — |
| Output styles | no | no | yes (affects the model's answers) | — |
| AGENTS.md mode | no | no | no | — |

## Area 10 limitations of this investigation

- **Model-limited behaviour.** This host serves `minimax/minimax-m3.1-flash:free`
  through a custom `ANTHROPIC_BASE_URL`. Anything that requires the model to
  *obey* an instruction — does the output style change the tone, does the
  model choose the right skill from its listing — could not be measured as
  product behaviour. Only harness behaviour (parsing, substitution, injection,
  registration, error text) was treated as observed.
- **Workflows were not executed.** The `/deep-research` workflow and the
  workflow runtime are behind a plan/feature-flag gate that a custom-gateway
  build does not satisfy, so F10-20 is OBSERVED-DOC only.
- **claude.ai-synced skills were not observed** (no claude.ai account, and the
  host is not connected to the Anthropic API). The `~/.claude/skills/synced/`
  location, the reserved `synced` and `anthropic-skills` names, and the
  `anthropic-skills:` command prefix are documented only.
- **Enterprise/managed scope was not exercised.** The managed directory
  `C:\Program Files\ClaudeCode\.claude\skills` was observed as a search path in
  the debug log but is empty on this machine, so the enterprise-wins
  precedence was not observed in practice (only the personal-over-project
  case was).
- **Only `personal` vs `project` precedence was observed**, not
  enterprise-over-personal, because there was no enterprise skill to shadow.
- **The `disallowed-tools` / `allowed-tools` semantics were not probed
  behaviourally** — the grant-clears-next-message rule and the
  `allowManagedPermissionRulesOnly` interaction are documented but were not
  exercised, because doing so would have required running a model turn with a
  modified permission state.
- **One host-specific number**: the observed listing budget was 6,000
  characters for 17 skills. That is a function of this host's context window
  and skill mix; the documented rule (1% of the context window, 8,000-char
  fallback) is the portable statement.
- **No decompilation, no source extraction, no binary modification, no
  credential or licence-file access.** REA's decompilation facilities were
  deliberately not invoked for this target; the reverse-engineering toolset was
  used for nothing in this area.

## Area 10 unknowns

- Whether the model’s **skill-selection quality** is affected by the listing
  budget’s least-used-first truncation in a way an implementer should try to
  improve (UNKNOWN — model-limited on this host).
- The exact algorithm behind the "least-used skills" ordering: the reference
  tracks usage per skill, but the usage signal's source and decay are not
  observable from outside.
- The `digests` values in the `skill_listing` attachment: 16 hex chars, almost
  certainly a content hash, but the hash function and the comparison rule are
  not observable.
- Whether `contentDiffersFromDisk` on a `nested_memory` attachment means the
  in-memory rule differs from the file (an edit-during-session case) or is
  simply always true for rules (whose frontmatter is stripped). One probe
  cannot distinguish the two.
- The exact byte budget of the `allowed-tools` grant and whether a
  `disallowed-tools` entry can remove `EndConversation` in this build.
- Whether the `Task` → `Agent` tool rename has a compatibility shim for old
  transcripts, or whether `Task` is simply the internal name.
- Whether `claude import` is gated by plan, by build, or by feature flag, and
  what its import format is.
- The behaviour of `skillOverrides` when a skill's name changes, and of the
  `alias` mapping (the doc says an entry under an alias in *managed* settings
  applies to the skill behind the alias, but not in user/project/local
  settings — only the managed case was documented, not probed).
- The exact semantics of `force-for-plugin` when two enabled plugins both set
  it ("the first one loaded" — which plugin loads first is not observable
  without two conflicting plugins).
- Whether the workflow runtime's `agent()` schema pre-flight can reject a
  schema that is contradictory but not provably so (documented only for the
  provable case).
- The claude.ai-synced skill behaviour in every mode (terminal, Cowork, cloud,
  desktop), and the exact rule for when a synced skill's body is stripped of
  `` !`cmd` ``.

## Area 10 clean-room implementation opportunity

Recommended scope for an independent functional implementation of the
extension layer. Tier 1 is the parity core; Tier 2 is where an independent
implementation can be *better*; Tier 3 is optional.

### Tier 1 — parity core (must have)

1. **A unified extension registry.** One resolver over an ordered list of
   `(scope, path)` roots producing (a) a *loaded* set tagged by scope, (b) a
   *resolved* set keyed by command name, (c) two slash-command lists (user
   menu and terminal-only), and (d) a model-facing listing. Copy the reference's
   per-scope counters and the "skill-directory commands vs plugin skills vs
   bundled skills" split. Emit a one-line diagnostic naming every scope and
   its path — this is the single highest-value diagnostic in the whole
   product.
2. **A `SKILL.md` loader with a declared schema.** Hyphen-cased fields (or
   camelCase — pick one, enforce it), documented booleans accepting
   `yes/no/on/off/1/0`, unknown fields ignored, frontmatter stripped from the
   body, frontmatter parse failure → load with empty metadata + a loud
   diagnostic, and a machine-readable validator (`validate` subcommand,
   JSON envelope, per-file findings with `path`/`message`/`code`/`fix`).
   Support a **strict subset** profile for a packaging/upload path that hard-errors
   on unknown keys.
3. **Invocation control as two independent booleans** —
   `model_may_invoke` and `user_may_invoke` — derived into three surfaces
   (model listing, user menu, tool permission), plus a `skillOverrides`-style
   four-state override applied after frontmatter. Make the refusal error carry
   an explicit "do not achieve this another way" directive to the model.
4. **A budgeted model-facing listing.** Names always present, descriptions
   budgeted (fraction-of-context, with a fixed-char override), per-entry cap,
   least-used-first truncation, a debug warning that names the measured size,
   the budget, and the two remedies, and a `names`+`digests` sidecar for
   incremental re-sending.
5. **A template language for skill and agent bodies.** `$ARGUMENTS`, `$N`,
   `$ARGUMENTS[N]`, declared `$name`, and `${CLAUDE_SESSION_ID}` /
   `${CLAUDE_EFFORT}` / `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PROJECT_DIR}` /
   `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}`. Substitute in **both**
   the body and the tool-allow rules. Never re-scan substituted values.
6. **Project instructions as an ordered, auditable list.** Managed → user →
   root-to-cwd concatenation, `CLAUDE.local.md` after `CLAUDE.md` per level,
   lazy subdirectory loading, HTML-comment stripping, `@path` imports with a
   4-hop cap and cycle detection, backtick suppression, and a per-project
   approval record for imports outside the working directory. Keep each
   instruction file's identity in the context record.
7. **A conditional instruction channel.** `.claude/rules/*.md` with `paths`
   glob scoping, brace expansion under a shared budget, frontmatter stripping,
   and injection on matching file access — emitted as a distinct attachment
   type, not concatenated into the main instruction blob.
8. **Subagents as a first-class registry.** A declared frontmatter schema, a
   documented skip list (invalid → documentation, not an error), a per-agent
   system prompt, tool allow/deny lists, model/effort/permission overrides, a
   `skills:` preload that injects the **whole** `SKILL.md`, and a `context:
   fork` mode that runs a skill in an isolated context.
9. **A delegation tool with a machine-readable ledger.** One canonical name,
   an input schema with `description`/`prompt`/`subagent_type`/`model`/
   `effort`/`run_in_background`/`isolation`, and a `subagent_stats` block with
   `spawned`, `by_type`, `completed`, `failed`, and explicit `refused`
   sub-counters for depth, concurrency, and budget.
10. **A plugin/packaging layer.** `.claude-plugin/plugin.json` with `name`
    required, the standard component layout, strict path rules (`./`-prefixed,
    inside the root, exists, no `..`), the replace/add/merge semantics per
    component key, reserved-name checks, and `<name>@<source>` ids.
11. **A validator that runs in CI.** Stable JSON envelope, three-tier result
    model, per-finding `fix` strings, and the ability to point it at a
    *components directory* as well as a manifest.

### Tier 2 — strong differentiation (do these deliberately)

12. **Make injected shell commands safe by default.** The reference executes
    `` !`cmd` `` in a skill body silently at render time. A clean-room
    implementation should default to **prompting** (or denying) for injected
    commands from untrusted sources, log every execution with its resolved
    pattern, and make the policy settable from managed configuration so an
    organisation can disable it globally. This is the single largest
    defensible improvement available in this area.
13. **Count forked skills honestly.** The reference's `subagent_stats.spawned`
    is `0` for a `context: fork` skill that demonstrably ran. Report forked
    skills in the ledger with their own counter.
14. **Make the settings scope table explicit and enforced.** The reference
    silently ignores `pluginConfigs` set in project settings. A clean-room
    implementation should either honour it everywhere or emit a
    machine-greppable warning naming the ignored scope.
15. **Ship an importer.** `claude import` is documented but unavailable in the
    reference build. Converting a competitor's agent/command definitions into
    your own format is open space.
16. **Make the always-on/on-invoke token projection first-class.** The
    reference surfaces it in `claude plugin details`; make it a per-session
    `/cost`-style view for *all* skills, with a "turn this one off" action
    wired to the override mechanism.
17. **Give the rules channel a richer match model.** Support `paths` on skills
    *and* rules with one glob implementation, one brace-expansion budget, and
    a preview command that shows which rules a given file would pull in.

### Tier 3 — nice to have

18. **Dynamic workflows.** The script-over-subagents model (pure-literal
    `meta`, banned non-determinism, hard limits that *reject* rather than
    truncate, `null` on failure, schema pre-flight) is fully specified in
    public docs and is the most copyable many-agent design available.
19. **Output styles** with the exact documented selection semantics, the
    `keep-coding-instructions` switch, and the "applies to forks, not to
    subagents" rule.
20. **Auto memory** with the `MEMORY.md` index + topic files layout, the
    200-line/25 KB cap with a "rewrite the index" error, per-scope
    (`user`/`project`/`local`) subagent memory, and a `modified` ISO-8601
    frontmatter stamp on writes.

### Explicitly not to copy

- Anthropic's bundled-skill *content* (`dataviz`, `claude-api`,
  `plugin-authoring`, …) — that is product content, not interface.
- The exact system-prompt text, internal model routing, or the proprietary
  binary.
- The reserved-name list (`claude-`, `anthropic-`, `anthropics-`,
  `cc-plugin-`) as a *legal* device; copy the mechanism (a namespace
  reservation check) but choose your own names.
- The Anthropic plugin-directory submission policy (`README_MISSING`,
  `LICENSE_MISSING`, `ICON_MISSING`, "at least 40 words") — that is a
  marketplace policy, not a technical contract.

## Area 10 evidence index

| Artifact | Path |
| :- | :- |
| Area 10 evidence directory | `agent-reference-shots/area10-skills/` |
| Artifact guide | `agent-reference-shots/area10-skills/README.md` |
| Skill discovery, precedence, nesting, budget | `agent-reference-shots/area10-skills/discovery-and-budget-probes.txt` |
| Invocation control, subagent preload, instruction selection | `agent-reference-shots/area10-skills/invocation-control-and-instruction-probes.txt` |
| Skill rendering, substitution, injection, fork | `agent-reference-shots/area10-skills/skill-rendering-probes.txt` |
| Init-event registries (6 probe projects) | `agent-reference-shots/area10-skills/init-registries.txt` |
| Instruction attachments (CLAUDE.md / AGENTS.md / rules) | `agent-reference-shots/area10-skills/instructions-attachment-probe.txt` |
| Tool schemas and registry attachments | `agent-reference-shots/area10-skills/registry-and-tool-contracts.txt` |
| Plugin CLI surfaces and validator contract | `agent-reference-shots/area10-skills/plugin-cli-probes.txt` |
| Validator JSON probes | `agent-reference-shots/area10-skills/plugin-validate-probes.json` |
| CLI help surfaces | `agent-reference-shots/area10-skills/cli-skill-surfaces.txt` |
| Debug-log skill discovery | `agent-reference-shots/area10-skills/debug-log-skill-discovery.txt` |
| Observed frontmatter from installed skills | `agent-reference-shots/area10-skills/observed-skill-frontmatter.txt` |
| Worked examples | `agent-reference-shots/area10-skills/example-SKILL.md`, `example-skill-with-forking.md` |

Public documentation consulted (all treated as untrusted data; no instruction
in any page was followed and no command found in fetched content was executed):

- https://code.claude.com/docs/en/skills.md
- https://code.claude.com/docs/en/memory.md
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/workflows.md
- https://code.claude.com/docs/en/output-styles.md
- https://code.claude.com/docs/en/plugins/manifest-reference.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/env-vars.md

### Auto memory (supplementary, OBSERVED-DOC)

Auto memory is enabled by default in local sessions and stores notes at
`~/.claude/projects/<project>/memory/` (one directory per git repository, so
worktrees and subdirectories share it). The directory holds a `MEMORY.md`
index — one line per memory, loaded into every session — plus one topic file
per memory. The **first 200 lines of `MEMORY.md`, or the first 25 KB,
whichever comes first, are loaded at session start**; content beyond that is
not loaded. If `MEMORY.md` is over the limit, the write still succeeds but the
harness returns an error telling the model to rewrite the index, because
everything past the limit is dropped on the next load. The limit applies only
to `MEMORY.md`; a `CLAUDE.md` up to 4 MiB is loaded in full and a larger one is
skipped. Four note types are recorded as a `type` frontmatter field: `user`,
`feedback`, `project`, `reference`. The main conversation's auto memory is not
loaded into subagents; a subagent's own memory is enabled with the subagent
`memory` frontmatter field (`user`/`project`/`local`) and is a separate
directory.

**Clean-room opportunity.** Implement memory as an index-plus-topics layout
with an enforced read cap and an explicit "the index is over its limit"
error, and give the agent a *separate* memory scope per subagent so a
worker does not inherit the parent's memory. The "write succeeds but the index
must be rewritten" behaviour is a good, explicit contract to copy.
