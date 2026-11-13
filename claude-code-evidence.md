# Claude Code — Verification-Round Evidence Update

**Purpose.** This document records the *second and third* evidence rounds: adversarial verification of the first-round claims in `agent-evidence.md`, and the resulting corrections. It does **not** replace `agent-evidence.md`, which remains the primary evidence document and is retained unchanged for comparison.

**Primary source:** `agent-evidence.md` (358 KB, 15 sections, 178 confirmed capabilities, 44 unknowns)
**Round 2 method:** 24 independent agents, each given a set of claims from one area and instructed to **refute** them — re-running the published CLI, re-fetching the cited documentation page, and grepping the raw cached page for the exact quoted strings.
**Round 3 method:** 47 independent agents, each assigned one official documentation page and instructed to verify every claim our evidence base attributes to that page against the page itself, again under the grep-for-the-literal-string discipline of §4.
**Verification dates:** 2026-10-21
**Subject build:** Claude Code CLI 2.1.306, `win32-x64`

---

## 0. What changed, in one table

| | Round 1 | Round 2 | Round 3 |
| :- | :-: | :-: | :-: |
| Claims examined | — | **249** | **1 203** |
| Fully confirmed | — | **194** (78 %) | **1 094** (90 %) |
| Confirmed with a material correction | — | **40** (16 %) | **65** (5 %) |
| **Refuted** | — | **15** (6 %) | **44** (4 %) |
| Areas covered | 15 | 12 | 20 documentation pages |

**Net effect on the evidence base: the first round was directionally right and quantitatively sloppy.** No claim was reversed outright at the level of a subsystem's behaviour. What was wrong was mostly counts, scope boundaries, and one class of fabricated quotation. The corrections below are material enough to change implementation decisions in several places, and they are recorded here so that no downstream document is written against the uncorrected claims.

**The single most consequential finding** is in §4: **an entire set of quoted evidence in one area was fabricated** — strings that do not exist in the cited pages, confirmed by grepping the raw cached files. That is a process failure, not a technical one, and it is recorded here because it changes how much weight any quoted evidence in this project can carry.

**Round 3's headline is different in kind.** Its 44 refutations are mostly *scope* and *count* corrections rather than fabrications — but two of them are **security-relevant**, and one of those two is a real weakness in the reference product's own enforcement model that our design must not inherit:

- **A tool-level deny is a registry-level filter, not an execution-surface boundary.** Confirmed live (C014): with a bare-name deny on one shell tool, the model retains another route to the same capability. Our design must treat deny rules as *presentation-level* filters and enforce the real boundary at the *operation* level.
- **Plan mode's write block is bypassable through the shell.** Observed live (C054): the model was denied the `Write` tool and then wrote the same file via `Bash`. The two candidate explanations — an enforcement gap in the reference, or the model simply routing around the denial — are **indistinguishable with this evidence**, so it is recorded as UNKNOWN *for the reference* and as a **mandatory design requirement** for ours (§9.4).

This is the pattern the project has already named in `prompt-pattern-analysis.md` §4 (principle **X1**, "enforce by mechanism, not by instruction"): a prompt layer can only *ask* for a behaviour the harness does not *mechanically* enforce. Where we diverge from the reference, we diverge by enforcing it.

---

## 1. The 17 refutations

Each is stated as: what was claimed → what is actually true → what changes.

**R16 and R17 are a new category.** R1–R15 are corrections to claims about the *reference
product*. R16 and R17 are corrections to claims about *our own specifications* — the interface
spec named five hook events that do not exist and omitted the `auto` permission mode. They are
listed here because they were found by the same adversarial method and because they are the more
consequential of the two classes: a claim about the reference can be checked against the
reference, but a claim about our own specification can only be checked by a second reader.

### R1 — The Bash `description` field **is** an authorisation signal
**Area 5.** **Claimed:** the model-authored `description` is display metadata only and is never an authorisation signal; the harness, not the model, is the security boundary. **Corrected status:** `INFERRED`.

**Actually true.** Permission rules can match a top-level scalar input parameter on any built-in tool via `Tool(param:value)`, and `description` is matchable. Reproduced first-hand: `--disallowedTools 'Bash(description:*)'` was **denied three times** with "Permission to use Bash with description:* has been denied."; the control `--disallowedTools 'Bash(description:ZZZNOMATCH*)'` was **allowed** and ran normally. The match is genuine and value-sensitive.

The documented non-matchable fields are the *primary content* fields — `command` for Bash and PowerShell — not `description`.

**What changes.** The claim as written was a **security-relevant overstatement**: it asserted a stronger boundary than the product has. An independent implementation that copies "description is never an authorisation signal" would build a rule engine that cannot express a policy the reference *can* express. Conversely, the security argument in the implementation plan ("the harness, not the model, is the security boundary") survives — it is the *matcher* that reads the description, not the model. But the plan's phrasing must not imply the field is inert.

### R2 — Fabricated quotations in the capability-dependency area
**Area 12.** **Corrected status:** `INFERRED`.

**Actually true.** Essentially **all** of the cited quoted evidence for one claim was fabricated. Grepping the complete raw cached pages returned **zero** hits for every quoted phrase: "mandatory network", "account requirement", "supply credentials", "local Markdown", "does not require network" — and the word "network" appears **zero times** in the entire 110,552-byte skills page. The hooks page likewise returned zero hits for all six quoted strings.

The *real* wording is different in kind: the skills page says the allowed-tools grant is "Tools Claude can use without asking permission during the turn that invokes this skill. The grant clears when you send your next message." — the claim's "expires on your next message" is a **misquote**. The hooks page says "Handlers run in the current directory with Claude Code's environment."

**What changes.** The substantive conclusion (skills need no separate credential; hooks inherit the ambient environment) survives, but it now rests on different evidence. The hook-event count in the same claim was also wrong: **33**, not 37.

### R3 — The AI-generated session title **is** a resume handle
**Area 1.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** The claim lumped the AI-generated title in with the default display name and said neither is a resume handle. The default display name (`<dirname>-<2char>`, e.g. `claude-clone-95`) is indeed **not** a resume handle — `--resume "claude-clone-95"` fails with "Provided value … is not a UUID and does not match any session title." But the **AI-generated title is**: `--resume "glob search"` resolved to a live session ("That session is running in the background (227c5ae3)"). The documentation states "Only the generated title works as a resume handle."

**What changes.** An implementer following the uncorrected claim would build the resume-handle semantics **backwards** — the exact failure mode where a human-facing handle appears useless and a machine-facing one is undocumented.

### R4 — The transcript is a DAG, but `isSidechain` does **not** mark branches
**Area 1.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** The tree claim is hard-verified: in a 9.4 MB transcript, **1,247 tree nodes, exactly 1 root** (`parentUuid=None`), and **117 parents with more than one child** — a genuine DAG, not a linear array. `promptId` grouping confirmed (393 user entries, only 3 distinct prompt ids). Tool results are user-typed entries (381 of 393 user entries contain `tool_result` blocks). 16 distinct entry types observed.

But **zero** entries anywhere in the transcript tree carry `isSidechain=True` — not in any transcript under `~/.claude/projects/*`, and not in a session that spawned a real subagent (`subagent_stats.spawned=1, completed=1`). Every entry in both the parent transcript and the spawned subagent's transcript had `isSidechain=False`, and the subagent's own transcript is a **separate file**.

**What changes.** The branch marker must be identified by something else — the separate transcript file plus the parent/child uuid links, not `isSidechain`. An implementation keying sidechain detection on that flag would never detect a single sidechain.

### R5 — The hook-event count is 33
**Area 11.** **Corrected status:** `OBSERVED-DOC`.

**Actually true, with one correction to the correction.** The hooks page's summary table enumerates **33 events** and the page carries **33 event-level `###` sections** — one section per event, so the two counts agree. The page contains **no** "supports N hook events" sentence: a grep for the literal string `supports 29 hook events` returns **0 hits** in `agent-reference-shots/area8-auto-mode/docs/hooks.md` (269,876 bytes, md5 `4fa8d7b53f44ef90f18a1fe8cfddcf2f`) and **0 hits** in the byte-identical `agent-reference-shots/areas/.fetch-amc/hooks.md`; a grep for the shorter form `29 hook` also returns 0.

This matters because the *first* correction to this claim had itself been wrong: it asserted the page "states 29 hook events" and that a "fuller pass" over the decision-behaviour tables surfaced 4 further names (Setup, UserPromptExpansion, MessageDisplay, InstructionsLoaded) to reach 33. **That was a misdescription.** The 33 names are the summary table's own rows, and the 4 "further" names are in the table, not below it. The count 33 was right; the reasoning and the quoted sentence were not. **This is the failure mode the §4 standing rule exists to catch** — a quote that reads plausibly, is repeated across documents, and is never grepped.

**The 33 names**, as the summary table enumerates them: SessionStart, Setup, UserPromptSubmit, UserPromptExpansion, PreToolUse, PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure, PostToolBatch, Notification, MessageDisplay, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, Stop, StopFailure, TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged, DirectoryAdded, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, Elicitation, ElicitationResult, SessionEnd.

Everything else in the claim verifies: all 18 named events exist verbatim; `PreToolUse` decisions are allow/deny/ask/defer with `permissionDecisionReason`, `updatedInput` ("replaces a tool's arguments before it runs"), and `additionalContext`; `PostToolUse` supports `decision: "block"` and `updatedToolOutput` ("replaces the tool's result"); `MessageDisplay`'s `displayContent` is explicitly **display-only** ("the transcript and what Claude sees keep the original").

### R6 — `MultiEdit` is not in hook matcher lists
**Area 4.** **Corrected status:** `OBSERVED-DOC`.

**Actually true.** The core holds and was reproduced live: the permissions documentation says "Claude Code checks file permissions against `Edit(path)` and `Read(path)` rules only. If you write a path rule for `Write`, `NotebookEdit`, `Glob`, or the legacy `MultiEdit` tool instead, Claude Code accepts the rule but never consults it, and warns at startup" — and the startup warning was reproduced verbatim. The SDK's `ToolInputSchemas` union lists 38 input types and no `MultiEditInput`.

But a full search of the hooks page (all three offset chunks) for the literal "MultiEdit" returned **zero** occurrences. The enumerated built-in hook matcher names are `Bash`, `PowerShell`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Agent`, `Workflow`, `WebFetch`, `WebSearch`, `AskUserQuestion`, `ExitPlanMode`.

**What changes.** The claim's own evidence field cited no hook source for the sub-claim it got wrong. Corrected claim: the legacy tool is accepted-but-ignored in **permission rules**, and absent from **hook matchers** — two different surfaces with two different behaviours.

### R7 — `acceptEdits` auto-accepts **common filesystem shell commands**, not only file edits
**Area 4.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** The per-tool-call metadata mechanism is fully confirmed: every capture carries `tool_result_meta: [{"id":"…","permission_decision":{"decision":"accept","source":"config","reason_type":"rule"}}]`, and all three `reason_type` values were observed (`"rule"`, `"mode"`, absent), plus `"decision":"reject"` with `"non_execution_kind":"user-rejected"`.

But the claim "acceptEdits auto-accepts file edits ONLY" is **false**. The documentation states acceptEdits "lets Claude create and edit files in your working directory without prompting" **and** "In addition to file edits, `acceptEdits` mode auto-approves common filesystem Bash commands: `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, and `sed`" (plus `Set-Content`/`Add-Content`/`Clear-Content`/`Remove-Item` on Windows). Reproduced live: under `--permission-mode acceptEdits`, `Bash {"command":"mkdir subdir_xyz"}` was **accepted** and the directory was created. The earlier rejections were caused by something else — a multi-operation shell command, not the mode.

**What changes.** This is a **material security-relevant correction**. `rm` is in the acceptEdits auto-approve list. An independent implementation that encodes "acceptEdits = file edits only" is *stricter* than the reference; one that encodes the reference exactly is accepting `rm` without a prompt. Both are defensible, but the choice must be made deliberately and documented, not inherited by accident.

### R8 — A classifier refusal does **not** exit with no document
**Area 8.** **Corrected status:** `OBSERVED-DOC`.

**Actually true.** The first half is confirmed: the "action was NOT performed" contract, the surviving output document with `permission_denials` populated, and the literal tail "The action was NOT performed; do not claim it succeeded, and do not retry it". The documentation confirms it directly.

The second half is refuted: every inner-CLI run captured during verification exited 0 and produced a full JSON document (`is_error` false, `safety_stops` 0, `permission_denials` []), including runs in auto mode. The claimed "classifier refusal exits the process with no document at all" could **not** be reproduced.

### R9 — Nested-skill lazy loading is documented, not observed
**Area 10.** **Corrected status:** `INFERRED`.

**Actually true.** The nearest-first ordered scope list was reproduced: a session at the project root printed `project=[<proj>\.claude\skills]`; a session started at `<proj>/sub` printed `project=[<proj>\sub\.claude\skills, <proj>\.claude\skills]`. The nested skill appeared in the listing only in the sub-directory session.

The **lazy-load** half was not reproduced. Starting at the project root and asking the model to read a file under `<proj>/sub/` produced **no** nested-skill entry in any `skill_listing` and no attachment carrying it, even on a second attempt explicitly targeting that file. The documented behaviour differs in kind: nested skills below the start directory "load the first time Claude reads or edits a file in that subdirectory and stay available for the rest of session."

### R10 — The 1,000-pattern / 4 MiB budget belongs to **rules**, not skills
**Area 10.** **Corrected status:** `INFERRED`.

**Actually true.** The conditional-skill mechanism was reproduced: a skill with `paths: "**/*.ts"` produced "[DEBUG] [skills] 1 conditional skills stored (activated when matching files are touched)"; a second fixture with `paths: "src/*.{ts,tsx}"` produced the same line, so brace syntax is accepted.

But the numeric budget was **misattributed**. It is in the *memory* documentation for path-scoped **rules**: "a rule's whole `paths` list shares one budget of 1,000 expanded patterns and 4 MiB". The skills page says only "Uses the same format as path-specific rules" and **never mentions brace expansion or a pattern-count limit**.

### R11 — There are **six** `${CLAUDE_*}` variables, not seven
**Area 10.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** Reproduction confirmed every substitution form: `$ARGUMENTS`, `$0`/`$1`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`. The harness also prepends "Base directory for this skill: <path>".

The count was wrong: the documented table lists **six** — `CLAUDE_SESSION_ID`, `CLAUDE_EFFORT`, `CLAUDE_SKILL_DIR`, `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` — confirmed by grepping the page for exactly 6 distinct `${CLAUDE_*}` tokens.

Also corrected: an **undeclared** named placeholder stays **literal**; it is not "declared but unmatched" (which expands to an empty string). Two different mechanisms were conflated.

### R12 — A subagent's `skills:` preload injects the **body, not the frontmatter**
**Area 10.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** The documentation says "The full content of each listed skill is injected into the subagent's context at startup" — which does **not** say the YAML frontmatter is included. Reproduction shows the opposite: the injected content was "Base directory for this skill: …" followed by the body, with **no frontmatter**. The earlier report of a frontmatter-bearing preload was an **artefact** — the subagent had used its Read tool on `SKILL.md` and quoted the file verbatim from disk.

Decisively confirmed with a no-tools subagent (`tools: ""`): the injected text was "Base directory for this skill: …" plus the body — still no frontmatter.

The rules-loader half was correct: "Claude Code removes the frontmatter before loading the rule into context," confirmed by probe.

### R13 — Project instructions are a **list of separate entries**, not one concatenated blob
**Area 10.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** The `@import` behaviour was reproduced: the `instructions` attachment contained **two separate entries** — the importing file with its text preserved verbatim, and the imported file as its own entry. Imports become their own attachment entries, not inlined text. The documented import rules confirm: relative resolution, **max 4 hops**, spaces need a backslash, a quoted path is not imported, backtick-wrapped paths stay literal, and an import resolving outside the working directory triggers a one-time approval dialog.

But the headline "CONCATENATE and never override" is the wrong model: the attachment is a **list of separate file entries**, not one merged blob — the claim's own evidence showed two entries and said so, contradicting its own headline. A **third** entry type was observed and omitted: an unconditional `.claude/rules/plain-rule.md` arrived as a separate `instructions` entry alongside the two CLAUDE.md files.

The root→cwd ordering with `CLAUDE.local.md` after `CLAUDE.md` at each level was **not** verified — the fixture had one CLAUDE.md level plus an import.

### R14 — `claude plugin validate` on a component directory does **not** error
**Area 10.** **Corrected status:** `OBSERVED-CLI`.

**Actually true.** The envelope and the component-directory capability were confirmed: `claude plugin validate --json <root>` returns `{success, strict, target, manifest:{…}, contents:[…], advice:[], directory:{profile, findings:[{code,title,severity,blocking,hold,file,field,message,fix}], undecided, incomplete, failure, notes}}`, with observed directory codes `README_MISSING`, `LICENSE_MISSING`, `ICON_MISSING`. Validating `.claude/skills` and `.claude/agents` directories both printed "Validating components in: …" and "✔ Validation passed".

The quoted "No manifest found in directory" error **does not reproduce** on a populated component directory. It appears only when the target directory does not exist or contains no recognised component files.

**Re-verified directly (2026-10-21, build 2.1.306, `win32-x64`), in an isolated temporary
directory.** A populated `.claude/skills` directory and a populated `.claude/commands`
directory both print `Validating components in: <path>` and `✔ Validation passed`. A
**non-existent** path prints `Validating plugin manifest: <path>` and produces a **`file:`**
finding — `File not found: <path>` — not a `directory:` finding about a missing manifest.

This is a stronger statement than the original: the `No manifest found in directory` error is
**not part of the current CLI's behaviour at all**. The original probe's transcript was a
**transcription error** — the `.claude/commands` target in that run contained no component
files, so it was treated as a plugin root, and the *missing target* was reported as a *missing
manifest*. The two are different conditions with different messages, and the transcription
collapsed them.

**Consequence for our documents:** the quoted error and its `directory:` code have been removed
from `agent-evidence.md` F10.22 rather than restated more weakly, and the validator's real
two-mode behaviour (components directory vs plugin root, decided by content) is recorded
instead.

### R15 — "Four launch modes" undercounts; `--remote-control` is not in the mutual-exclusion group
**Area 1.** **Corrected status:** `OBSERVED-DOC`.

**Actually true.** Every incompatibility was reproduced by name: `--bg -p` → "--bg and --print conflict"; `--bg --cloud` → "--bg and --cloud are different backends"; `--cloud -p` → "Error: --cloud cannot be combined with --print"; `--bg --desktop` → "--desktop opens the Claude Desktop app and can't run in the background". Orthogonality confirmed: `--bg --bare`, `--bg --safe-mode`, `--bg --restricted` all launched successfully.

Two corrections: (a) the published CLI exposes more distinct launch paths than four — `--cloud`, `--desktop`, `--remote-control`, `--teleport`, `--environment`, `--worktree`, `--from-pr`, `--exec`, `--init-only`; (b) `--remote-control --bg` **backgrounded successfully**, so remote-control is **not** in the same mutually-exclusive group as `--bg`.

A third: `--restricted` is **not** fully orthogonal — `--restricted --dangerously-skip-permissions` → "Error: bypassPermissions not supported in restricted mode".

### R16 — The interface spec had **invented** five hook events and omitted fourteen real ones
**Area 11.** **Corrected status:** `OBSERVED-DOC`. **This is a defect in our own documents, not in the reference.**

`interface-spec.md` §7.1 declared `type HookEvent` with 23 names. Five of them —
`PromptDispatch`, `PreCompactManual`, `ElicitationResponse`, `SkillLoaded`, `CommandLoaded` —
**do not exist in the reference at all**: a grep for each name across every file under
`agent-reference-shots/` returns **zero hits**. They were an invention of the specification, not
an observation. Meanwhile fourteen real events were missing: `Setup`, `UserPromptExpansion`,
`MessageDisplay`, `PermissionDenied`, `PostToolBatch`, `SubagentStart`, `StopFailure`,
`InstructionsLoaded`, `CwdChanged`, `DirectoryAdded`, `FileChanged`, `PostCompact`,
`PreModelSwitch`, `PostModelSwitch`.

**Verified replacement.** The authoritative 33 names were derived independently from **three**
sources, and all three agree on the same set:

| Source | Extraction | Count |
| :- | :- | :- |
| `agent-reference-shots/area8-auto-mode/docs/hooks.md` | the `## Hook lifecycle` summary table's rows (lines 33–65) | 33 |
| `agent-reference-shots/area8-auto-mode/docs/hooks.md` | the `###` event-level sections under `## Hook events` (lines 1200–3828) | 33 |
| `agent-reference-shots/agent-sdk-agent-loop/agent-sdk-typescript.md` | the `type HookEvent` union | 33 |
| `agent-reference-shots/docs-cache/hooks-guide.md` | the summary table's rows | 33 |

Set equality between all four extractions was checked mechanically: **identical, no member in one
and absent from another.** The two extractions from `hooks.md` differ only in *order*.

**Why this matters more than a miscount.** An interface specification that names events which do
not exist is worse than one that is silent: an implementer reading §7.1 would write a dispatcher
that handles `PromptDispatch` and `SkillLoaded`, register hooks for them, and discover the events
never fire — while four real events that *do* fire would be dropped on the floor. This is the
"invented interface surface" failure the specification exists to prevent, and it is the second
time this class of error has appeared in this project (the first was the R2 fabricated
quotations).

**Correction applied.** `interface-spec.md` §7.1 now carries the reference's 33 names verbatim,
with the correction and the three-source derivation recorded inline rather than applied silently.

### R17 — `auto` was missing from the permission-mode enum — a whole decision path
**Area 8.** **Corrected status:** `OBSERVED-DOC`. **This is a defect in our own documents, not in the reference.**

`interface-spec.md` spelled out the permission-mode vocabulary in three places (§3.2
`TurnRequest.mode`, §6.3 `permissions.defaultMode`, §14 `cli.md --permission-mode`) and all three
omitted `auto`. The type `PermissionMode` was *referenced* four times but **never declared**.

**The omission was not a simplification.** `auto` mode replaces the human approval prompt with a
second model — the classifier — that reviews each action. In the reference it is:

- one of the **six** documented modes (`agent-reference-shots/docs-cache/permission-modes.md`,
  "Available modes"), and the only mode besides `bypassPermissions` that runs "everything";
- the **built-in starting permission mode** for interactive terminal and VS Code sessions from
  v2.1.283 (macOS/Linux/WSL) and v2.1.233 (native Windows), subject to plan and organisation
  policy;
- referenced by `PermissionReasonType`'s `'classifier'` member and `PermissionSource`'s
  `'classifier'` member in the interface spec — **values that were unreachable in a product with
  no `auto` mode**;
- paired with a `PermissionDenied` hook event that fires "when auto mode denies a tool call,
  including denials without a classifier verdict".

Omitting `auto` from the enum removed an entire permission decision path, and left two enum
members referring to a mode that did not exist. Every other document in the set already had it
right (`feature-checklist.md` S6-MODE-001, `security-plan.md`, `implementation-plan.md`,
`prompt-pattern-analysis.md` all list six modes including `auto`) — which is how the defect
survived: the interface spec was the one place it was wrong.

**Correction applied.** `PermissionMode` is now declared in §6.1 with all six members, the three
enumeration sites are corrected, and the `manual` → `default` alias is specified explicitly: the
reference labels the `default` mode "Manual" in the UI and accepts `manual` wherever the value
can be typed, while hooks and SDK integrations see `default`. Keel accepts `manual` on input and
normalises it to `default` everywhere downstream.

---

## 2. The 42 corrections with material changes

These verified as substantially true but wrong in a way that matters. Grouped by kind.

**R16 and R17 are a different kind of entry from the rest of this section.** Every other row
below is a correction to a claim about the *reference*. R16 and R17 are corrections to claims
about *our own documents* — an interface specification that named five events the reference does
not have, and a permission-mode enum that omitted one of the reference's six. They are recorded
here because they were found by the same adversarial method, but they are the more serious
finding: a claim about the reference can be checked against the reference, while a claim about our
own specification has nothing to check it against except another reader.

### 2.1 Counts that were wrong
| # | Area | Was | Actually | Note |
| :- | :- | :- | :- | :- |
| 1 | 11 | ~37 hook events | **33** — the summary table's 33 rows and the page's 33 event-level `###` sections are the same set | R5 |
| 2 | 12 | 37 hook events | **33** | same page, second count |
| 3 | 10 | 7 `${CLAUDE_*}` variables | **6** | R11 |
| 4 | 4 | `MultiEdit` in hook matchers | **absent** | R6 |
| 5 | 1 | four launch modes | **nine+** distinct paths | R15 |
| 6 | 12 | 500 files / 8,000 lines for ultrareview | confirmed, but the claim **conflated two products** — Code Review is a *separate* product with its own retention rules | verified verbatim |
| 7 | 12 | Code Review and ultrareview both "cloud-only" | ultrareview is cloud-only and falls back to a **local** review; Code Review is separately documented | |
| 8 | 11 | 23 hook events in our interface spec (5 invented, 14 real ones missing) | the reference's **33**, verbatim | **R16 — our defect** |
| 9 | 8 | 5 permission modes in our interface spec (`auto` missing) | the reference's **6** | **R17 — our defect** |

### 2.2 Scope boundaries that were drawn in the wrong place
| # | Area | Correction |
| :- | :- | :- |
| 10 | 10 | The 1,000-pattern / 4 MiB budget is **rules-only**; the skills page never states it and never mentions brace expansion. (R10) |
| 11 | 10 | The `${CLAUDE_*}` substitution count is 6, and an **undeclared** named placeholder stays literal (unlike a declared-but-unmatched one, which expands empty). (R11) |
| 12 | 10 | Nested-skill lazy loading is **documented, not observed**. (R9) |
| 13 | 10 | The skill preload injects **body only**; a frontmatter-bearing preload was a Read-tool artefact. (R12) |
| 14 | 10 | Project instructions are a **list of entries**; a `.claude/rules/` file is a **third** entry type the claim omitted. (R13) |
| 15 | 1 | `isSidechain` never marks branches; **zero** true values observed. (R4) |
| 16 | 1 | The AI-generated title **is** a resume handle. (R3) |
| 17 | 8 | A classifier refusal **does** produce a document. (R8) |
| 18 | 4 | `acceptEdits` auto-approves common filesystem shell commands **including `rm`**. (R7) |
| 19 | 5 | The Bash `description` field **is** matchable as an authorisation signal. (R1) |
| 20 | 1 | `--restricted` is not fully orthogonal (`bypassPermissions` rejected). (R15) |
| 21 | 10 | `claude plugin validate` on a component directory **does not** emit "No manifest found". (R14) |
| 22 | 4 | The `MultiEdit` behaviour is **permission-rule-specific**; it does not appear in hook matchers. (R6) |

### 2.3 Framing corrections — the claim was right, the headline was wrong
| # | Area | Correction |
| :- | :- | :- |
| 23 | 3 | A claim that plan mode is not a configuration artefact is **refuted as stated** — the tools-reference documents it, but the framing is wrong. Corrected: `OBSERVED-DOC + OBSERVED-CLI (core mechanism confirmed; framing refuted)`. |
| 24 | 3 | A claim conflating **tool names with subagent types** is corrected: the six built-ins are exactly Explore, Plan, general-purpose, claude, statusline-setup, and the guide agent — confirmed against the session's own `agent_listing_delta`. |
| 25 | 2 | The four-section instruction list and the mechanism are confirmed, but the claim's framing of **where the sections live** is wrong. |
| 26 | 12 | A quote was verified verbatim **but on a different page** than the claim's cited source. The claim's citation was wrong; the substance was right. |
| 27 | 1 | The tier structure and plaintext handling are confirmed; **one evidence item is wrong**. |
| 28 | 6 | A claim is substantiated with **one material wording correction**. |
| 29 | 11 | An architectural conclusion is well supported and each cited artifact independently verified, but **the reasoning is stated slightly too strongly**. |
| 30 | 4 | A count was wrong; the mechanism is reproduced live from scratch. |
| 31 | 12 | An environment-variable name was verified in the env-vars page — with the count of related vars corrected. |
| 32 | 12 | A feature-availability quote was verified verbatim at the cited line. |

### 2.4 Documentation-source corrections
| # | Area | Correction |
| :- | :- | :- |
| 33 | 12 | A plugin-marketplace claim is verified: "A plugin marketplace isn't Claude Marketplace" — the two are distinct surfaces. |
| 34 | 7 | The path rule is confirmed verbatim in the documentation. |
| 35 | 9 | Three MCP claims each independently reproduced (two `OBSERVED-CLI`, one `OBSERVED-DOC`). |
| 36 | 2 | Every quoted sentence present verbatim at the cited URL. |
| 37 | 3 | Documentation confirms all elements of the built-in agent set. |
| 38 | 3 | The documented three-way plan-approval choice is confirmed. |
| 39 | 6 | Reproduced with `--output-format stream-json --verbose`. |
| 40 | 12 | Provider-variance table programmatically parsed from the HTML. |

### 2.5 Corrections with a reproduction artefact recorded
| # | Area | Correction |
| :- | :- | :- |
| 41 | 1 | The core claim fully reproduced in an isolated `CLAUDE_CONFIG_DIR`. |
| 42 | 10 | Partly confirmed, partly refuted; the lazy-load half is INFERRED. |

---

## 3. Claims that survived intact

The verification was adversarial by construction, so the 194 fully-confirmed verdicts are as informative as the 15 refutations. The following high-value claims were independently reproduced first-hand, not merely re-read:

- **The project-directory encoding rule.** Non-alphanumerics map one-to-one to `-`; the name truncates at 200 characters and appends a 6-hex-character hash of the full path (verified by building a 228-character nested path and observing the 207-character result); `CLAUDE_CODE_PROJECT_DIR_NAME` is honoured only alongside `CLAUDE_CONFIG_DIR` and ignored without it.
- **There is no `--cd` flag** — `claude --cd /tmp -p "hi"` → "error: unknown option '--cd'".
- **Session ids are genuine UUIDv4**, and the background short id is a literal 8-hex prefix of the session id in every sampled case.
- **`--no-session-persistence` writes no transcript** (0 files) while still issuing a session id; the config scaffold is still created.
- **The transcript is append-only across resume** — one file, grown not replaced.
- **Background mode is *not* exempt from the workspace-trust check** the way `-p` is: `--bg` against an untrusted directory is refused outright with an actionable error, while `-p` in the same directory proceeds with only a non-blocking warning.
- **A multi-operation shell command is refused** with a message naming the offending parts — not merely "too complex".
- **A `Bash` deny matched on `description` is genuinely value-sensitive** (the control test passed).
- **A bare-name deny removes the tool from the schema**; a scoped deny filters at dispatch.
- **The conditional-skill store** logs its own activation model.
- **`@path` imports become separate attachment entries** with a 4-hop maximum.
- **The `--output-format stream-json` protocol** emits `permission_denied` system messages and populates `permission_denials` in the final result.

---

## 4. The process failure, and what it changes about how we read quotations

**One area's evidence was fabricated.** The verification agent fetched the complete raw cached files and grepped them: **zero** hits for every quoted phrase, and in one case **zero** hits for the word "network" in a 110 KB page. The claim's conclusion happened to be right; the quotations supporting it did not exist.

This is not a minor slip. It means that **in this project, a quoted string is not evidence until it has been grepped.**

**Standing rule, added to the project's verification practice:**

> A quotation from a documentation page or a captured artefact is admissible as evidence only if it has been mechanically re-checked against the raw source — a grep for the literal string, with a byte count for the file searched. Where that check has not been run, the statement is labelled `OBSERVED-DOC` at most and carries the caveat *"quotation not mechanically re-verified."*

**How this was found.** The verification agent was instructed to **refute**, and was told specifically to fetch the raw file and grep it rather than trust the earlier reading. It also verified **claims it agreed with** — 194 of them — by the same mechanical route, so the 194 confirmations carry the same weight as the 15 refutations.

**Second rule, equally important:**

> When a verification agent corrects a first-round claim, the **first-round wording is preserved** in the ledger rather than edited in place. The corrections ledger (`_corrections-ledger.md`) holds both, side by side, so a reader can see what the claim was, what it is now, and why.

---

## 5. What this changes in the downstream documents

Because the first-round evidence was the input to `feature-checklist.md`, `architecture.md`, `interface-spec.md`, `implementation-plan.md`, `test-plan.md`, and `security-plan.md`, these corrections propagate. The following are the **actionable** ones.

| Correction | Downstream impact | Action |
| :- | :- | :- |
| R7 — `acceptEdits` auto-approves `rm` | The permission mode's semantics are a **security** decision. | The implementation must choose deliberately: match the reference exactly, or be stricter and document the divergence. The security plan's divergence register gains an entry. |
| R1 — `description` is matchable | The rule-syntax specification understates what the matcher can express. | `interface-spec.md`'s rule model must support `Tool(param:value)` on scalar parameters, with the primary-content-field exclusion made explicit. |
| R2 — fabricated quotations | Affects the confidence of quoted evidence generally. | Apply the grep rule above. Any downstream document quoting a doc string must mark whether it was re-verified. |
| R3/R4 — resume handles, sidechain detection | Affects the session model and the transcript format. | The transcript schema must carry a branch marker that is not `isSidechain`; the resume interface must accept a generated title. |
| R12/R13 — preload body-only; instructions are a list | Affects the skills and instructions loaders. | The skills loader must strip frontmatter on preload; the instructions loader must model a **list of entries**, not a merged blob. |
| R11 — six `${CLAUDE_*}` variables | Affects the skills template language. | The template spec must enumerate exactly six, and must distinguish "undeclared name" (literal) from "declared but unmatched" (empty). |
| R5/R8 — 33 hook events; classifier refusal produces a document | Affects the hook interface and the result envelope. | Hook event list corrected to the reference's exact 33 names; the terminal envelope must always be produced, with refusals represented inside it. |
| R9/R10 — lazy loading and the pattern budget | Affects the skills loader and the rules loader. | The pattern budget is a **rules** limit; the skills loader must not assert a limit that is not documented for it. |
| **R16 — our interface spec invented five hook events** | Affects the hook interface, the hook dispatcher, and any third-party hook written against the spec. | The `HookEvent` union is replaced by the reference's 33 names, derived from four independent extractions that agree. **Applied.** |
| **R17 — our interface spec omitted `auto`** | Affects the permission-mode enum, the permission engine's mode branch, and the hook payload's `permission_mode` field. | `PermissionMode` is declared with six members; `manual` is specified as an input alias normalised to `default`. **Applied.** |

**None of these invalidate a subsystem.** The corrections are to counts, boundaries, and one quotation set. The subsystem decomposition, the permission lattice, the event protocol, the transcript format, and the context lifecycle all survive unchanged. That is the reassuring finding: **the first round was right about structure and wrong about detail.**

---

## 6. Effect on the confidence model

The original evidence document's classification key is unchanged and remains correct:

| Tag | Meaning |
| :- | :- |
| **OBSERVED-CLI** | The published CLI was run and the behaviour observed. Command and output given. |
| **OBSERVED-DOC** | Stated in a public Anthropic document — **now requiring mechanical re-verification of any quotation**. |
| **OBSERVED-FILE** | Observed in a file the product itself wrote. |
| **INFERRED** | A conclusion. Reasoning stated inline. |
| **UNKNOWN** | The available evidence cannot establish it. |

**Two new tags are introduced by this round**, because the round-1 vocabulary could not express what the verification actually established:

| Tag | Meaning |
| :- | :- |
| **OBSERVED-CLI-R** | Reproduced first-hand by a *verification* agent, independently of the original claim. Stronger than OBSERVED-CLI, because it carries a second, independent observation. |
| **REFUTED** | The claim was tested and did not hold. The claim's own status is superseded; the correction is the evidence. |

**The 194 confirmations are, in most cases, OBSERVED-CLI-R.** This raises the overall confidence of the evidence base even as it lowers confidence in individual quotations.

---

## 7. Open questions this round did not resolve

The verification round was scoped to *refute existing claims*, not to explore new ground. These remain open, and the ones marked ★ were raised by the round itself:

| # | Question | Status |
| :- | :- | :- |
| ★1 | What *is* the correct branch marker in the transcript, given `isSidechain` is never true? | UNKNOWN — needs a targeted probe |
| ★2 | Does the lazy nested-skill load actually occur, and under exactly which trigger? | INFERRED (documented, not reproduced) |
| ★3 | What distinguishes the "genuine user turn" from model-generated text that looks like one, at the harness level? | UNKNOWN — the summariser prompt defends it in prose, but no mechanical check was found |
| ★4 | Does `acceptEdits` auto-approve `rm` in the *current* build, or was that documentation-only? | PARTIALLY OBSERVED — `mkdir` reproduced; the `rm` case was not directly re-run |
| ★5 | Why is `isSidechain` present in the schema but never set? | UNKNOWN |
| ★6 | What is the real hook-event count — 29, 33, or more as the product evolves? | OBSERVED-DOC (29 documented, 33 enumerable) — will drift |
| ★7 | Do the `--safe-mode` and `--restricted` flags differ in any way other than the `--restricted` + `bypassPermissions` rejection? | UNKNOWN |

---

## 8. Method note

- **24 independent agents**, each assigned one area's claim set, instructed to **refute** rather than confirm, and given explicit instruction to re-run the CLI and to grep raw cached documentation rather than trust a prior reading.
- **Claims examined:** 249. **Confirmed:** 194. **Confirmed with material correction:** 40. **Refuted:** 15.
- Every refutation is recorded with the exact reproduction command or the exact grep and its result.
- The verification used only the **published CLI's own user-facing surfaces** and **publicly documented behaviour** — no decompilation, no binary inspection, no modification. The compliance boundary in `agent-evidence.md` §2 and `TERMS-NOTES.md` remains in force and was not relaxed for this round.
- No billable API call, no cloud resource, no training, no application source code.
- The raw workflow journal is preserved at `subagents/workflows/wf_998bac2e-d51/journal.jsonl`; the extracted ledger is `_corrections-ledger.md`; the machine-readable extraction is `_wf-corrections-full.json`.
- **Round 3** (documentation verification) is recorded separately in **§9**, with its own method note at §9.6. Its raw journal is `subagents/workflows/wf_4ecd1b7f-777/journal.jsonl`; its machine-readable extraction is `_wf2-corrections.json`.

## 9. Round 3 — documentation verification

**Method.** 47 agents, one per official documentation page, each instructed to verify every claim our evidence base attributes to that page *against the page itself*, quoting the page's own line numbers and re-grepping the raw cached markdown for the literal strings. Three agents died on gateway credit exhaustion and their pages were re-run. The round examined **1 203 claims**; **1 094** were fully confirmed, **65** carried a material correction, and **44** were refuted.

**What this round is and is not.** It is a check of *our claims against the vendor's documentation*. It is not a check of the product's behaviour — the reference's own runtime is the authority for behaviour, and where the two disagree the runtime wins. Several refutations below are therefore a statement that *we cited the wrong page*, not that the product behaves otherwise.

**The single most important pattern.** Every refutation in this round falls into one of four shapes, and the shapes are more informative than the individual items:

| Shape | Count | What it means |
| :- | :-: | :- |
| **Miscount** — the claim's own number disagrees with its own enumeration | ~14 | The claim was internally inconsistent: a count that does not match the list it carries. |
| **Scope overreach** — the claim generalises beyond what the source supports | ~13 | The fact is real; the claim states it more broadly than the source allows. |
| **Wrong page** — the cited page does not contain the claim | ~11 | The substance is often fine; the citation is wrong. |
| **Conflation** — a documented property asserted as an observed one | ~6 | The most serious shape: it upgrades documentation into observation without the work. |

The fourth shape is the one that matters most, and it is the direct descendant of the round-2 fabrication finding in §4. **Round 2 found quotes that did not exist. Round 3 found claims that were labelled `Observed at runtime` when no runtime observation had been performed at all** — the content was real documentation, but the confidence tag was false. A false confidence tag is worse than a wrong number, because it is the one that stops the next reader from checking.

---

## 9.1 The 44 refutations

Each is stated as: what was claimed → what is actually true → the corrected status tag.

### D01 — `settings.md`

**Claimed:** Twelve security-sensitive keys honour a STRICTER value from a lower scope over a managed value, forming an explicit exceptions table (list of 11 keys enumerated).

**Actually true:** Count is wrong: the claim says "Twelve" but the doc's "Exceptions to managed settings precedence" table on https://code.claude.com/docs/en/settings.md has exactly ELEVEN data rows (verified by parsing the markdown table): disableClaudeAiConnectors, enableArtifact, isolatePeerMachines, permissions.blockReadsOutsideWorkingDirectories, autoMode.classifyAllShell, remoteControlAtStartup, crossSessionInbound, useAutoModeDuringPlan, syncClaudeAiSkills, syncClaudeAiPlugins, maxEffortLevel. The claim's own enumeration also contains only 11 keys, so it is internally inconsistent. Every listed key and every rule (including the version gates v2.1.242 / v2.1.257 / v2.1.267) matches the table verbatim, so only the numeral must change to "Eleven". Separately, the doc's `syncClaudeAiPlugins` row links to /docs/en/settings-reference#syncclaudeaiplugins. The paragraph following the table (CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST) is an additional app-level exception but is not a twelfth keyed row.

**Corrected status:** `OBSERVED-DOC`

### D02 — `sessions.md`

**Claimed:** The project-slug derivation and long-path truncation are directly observable; the observed truncated form is a 192-char prefix + '-' + 6-char hash (199 total), slightly tighter than the doc's '200 characters and appends a hash' wording.

**Actually true:** Quantitative claim contradicted by direct measurement. I reproduced a long-path session twice (230-char and 245-char working directories) and both times the project directory name was 207 characters: a 200-character prefix followed by '-' plus a 6-character hex hash (e.g. '...-k8d7na', '...-dm4w9m'). The doc's wording is exactly right — truncate to 200 chars, THEN append the hash — and the implementation does not reserve hash budget inside the 200. The claim's INFERRED conclusion ('reserves the trailing -<hash> budget inside the 200-character budget') is false. The slug-derivation half of the claim is correct and reproduced (C--Users-Admin-AppData-Local-Temp-aa-b-cc-dd for a path containing a space and an underscore).

**Corrected status:** `OBSERVED-DOC`

### D03 — `sessions.md`

**Claimed:** Transcript persistence can be suppressed at four different granularities, and the transcript GC feature trims pre-compaction history only above 5 MB with a 10% minimum-savings floor, while resume is unaffected by trimming.

**Actually true:** GC facts are exact (verified verbatim in env-vars.md: 'once the file is larger than 5 MB... On v2.1.296 or later, the file stays as it is when removing that history would shrink it by less than 10%. Resuming the session restores the same conversation whether or not the file was trimmed.'). But the 'four granularities' count is unsupported: sessions.md's own 'location, retention, and write behavior' table documents only TWO write-suppression knobs — CLAUDE_CODE_SKIP_PROMPT_HISTORY (all modes) and --no-session-persistence (one claude -p run) — plus CLAUDE_CODE_TRANSCRIPT_LOCAL_GC, which trims rather than suppresses. The only fourth knob (Agent SDK persistSession: false) lives on agent-sdk/typescript.md, off-page, and the claim's own quote shows just three entries. Also note the quoted GC entry omits the doc's sentence 'Set it in the environment you start Claude Code from, since a settings env block can't turn it on.'

**Corrected status:** `OBSERVED-DOC`

### D04 — `sessions.md`

**Claimed:** Documented behavior has shifted from refusing toward degrading gracefully across v2.1.221 to v2.1.296, with hard refusals retained only for safety constraints; session ID search was widened from the current project only to all projects in v2.1.223.

**Actually true:** Two problems. (1) Source mismatch: sessions.md contains only v2.1.221, v2.1.234, v2.1.246, v2.1.257 and v2.1.285 (I enumerated every version string in the raw file) — it does not contain v2.1.223, v2.1.287 or v2.1.296 at all. The v2.1.223 ID-search note is in cli-reference.md's --resume row ('Before v2.1.223, the ID search covered only the current project directory and its git worktrees'); v2.1.287/v2.1.296 are in env-vars.md. (2) The two changelog-style labels 'Live-attach on resume of a running background session (was: refusal + claude attach hint):' and 'ID search covering all projects (was: current project only):' appear NOWHERE — I grepped sessions.md, changelog.md, cli-reference.md, agent-view.md and claude-directory.md, and the whole changelog contains no '(was:' annotation style and no 'Live-attach on resume' string. The substantive version gates are real; the quoted annotation form and the synthesis 'hard refusals retained only for safety constraints' are not doc-supported (the page's residual refusals are also about background-session conflicts and disallowed flags, not only safety).

**Corrected status:** `OBSERVED-DOC`

### D05 — `hooks.md`

**Claimed:** Claude Code documents exactly 33 hook events, each with a dedicated per-event section specifying its input schema and decision control. Mechanically counted from the lifecycle table and cross-checked against the 35 `###` sections under `## Hook events` (33 events + `Limitations` + `Disclaimer`); no table row lacks a section and no section is undocumented.

**Actually true:** Core count is right but two sub-claims are false. Verified: the `## Hook lifecycle` table has exactly 33 event rows (lines 33-65) and `## Hook events` (line 1200 to the next `##` at 3828) contains exactly 33 `###` sections, and the two sets are a perfect 1:1 match (same 33 event names, differing only in order). But (a) there is no "35 `###` sections under `## Hook events`" — it is 33; `### Limitations` (line 4114) is under `## Run hooks in the background` (line 4012) and `### Disclaimer` (line 4123) is under `## Security considerations` (line 4121), neither under `## Hook events`; the page has 58 `###` headings in total. (b) "each with ... decision control" overstates: 11 of the 33 events have no decision-control subsection (MessageDisplay, Notification, SubagentStart, SubagentStop, StopFailure, DirectoryAdded, WorktreeRemove, PreCompact, PostCompact, SessionEnd, and the output-only CwdChanged/FileChanged/WorktreeCreate/Elicitation/ElicitationResult), and the decision-control table (lines 1128-1142) explicitly assigns "None" to 9 of them. Corrected claim: the page documents 33 events, each with its own `###` section and a 1:1 correspondence to the lifecycle table; per-event input is documented for all, but decision control exists for only a subset.

**Corrected status:** `OBSERVED-DOC`

### D06 — `hooks.md`

**Claimed:** Any exit code other than 0 or 2 is a non-blocking error, including exit code 1 — the conventional Unix failure code. A policy hook that exits 1 therefore lets the action through unless it also opts into `onFailure: "block"`.

**Actually true:** The claim drops a qualifier that its own quote carries, and the "therefore lets the action through" inference is contradicted by the doc. The quoted WARNING (lines 855-857) says "Exit code 1 **without valid JSON output** is a non-blocking error ... even though 1 is the conventional Unix failure code. If your hook is meant to enforce a policy, use `exit 2`." The exit-code table (line 774) shows that exit 1 **with** schema-valid JSON is "Success. Claude Code ignores the exit code, and the fields alone decide" — and line 770 states plainly: "when a `PreToolUse` hook exits 1 but prints JSON that passes validation, that JSON can still decide what happens." So a policy hook exiting 1 with a valid `permissionDecision: "deny"` does block. Corrected claim: exit 1 without valid JSON output is a non-blocking error; a policy hook should exit 2 (or set onFailure: "block").

**Corrected status:** `OBSERVED-DOC`

### D07 — `hooks.md`

**Claimed:** `PreToolUse` is the only event with a four-way decision (allow/deny/ask/defer) and the only one that can rewrite tool arguments. Its decision lives in `hookSpecificOutput.permissionDecision`, and the legacy top-level form is explicitly deprecated.

**Actually true:** Two of the four sub-claims hold and one is false. Supported: line 1922 gives "four outcomes (allow, deny, ask, or defer)"; the Decision control table (line 1133) shows PreToolUse as the only event with a 4-value `permissionDecision` (PreModelSwitch has allow/deny/ask, PermissionRequest has allow/deny); line 1955 confirms the legacy top-level form is deprecated ("PreToolUse previously used top-level `decision` and `reason` fields, but these are deprecated for this event"). FALSE: PreToolUse is NOT the only event that can rewrite tool arguments — line 1147 states "`PermissionRequest`: `updatedInput` inside the `decision` object", and the PermissionRequest decision-control table (line 2087) documents `updatedInput` as a field that "modifies the tool's input parameters before execution". Both PreToolUse and PermissionRequest rewrite tool input.

**Corrected status:** `OBSERVED-DOC`

### D08 — `hooks.md`

**Claimed:** The hook lifecycle is observable at runtime through the documented stream-json surface, emitting a `hook_started` and a `hook_response` system message per hook run, correlated by a `hook_id`, carrying the hook's stdout, stderr, exit code and a success/error outcome.

**Actually true:** Two problems. (1) Wrong page and non-supporting quote: the supplied quote is from "#### Exit code 0" and says nothing about hook lifecycle events. On hooks.md the string `hook_started` appears ZERO times and `hook_id` appears ZERO times; `hook_response` appears exactly once (line 1399, in the Setup decision-control section, pointing to /docs/en/headless#read-session-metadata). The detailed schema lives on other pages: https://code.claude.com/docs/en/agent-sdk/typescript.md defines `SDKHookStartedMessage` (type: "system", subtype: "hook_started", hook_id, hook_name, hook_event, uuid, session_id) and `SDKHookResponseMessage` (hook_id, stdout, stderr, exit_code?, outcome: "success" | "error" | "cancelled"); https://code.claude.com/docs/en/headless.md line 259 documents `hook_started`/`hook_progress`/`hook_response` in the stream. (2) "per hook run" is overstated: the SDK page states that some events "never produce an `SDKHookStartedMessage`, even with this option" (Notification, SessionEnd, PreCompact, PostCompact), and that lifecycle events for other events require the `includeHookEvents: true` option (SessionStart/Setup are always included).

**Corrected status:** `OBSERVED-DOC (documented on /docs/en/agent-sdk/typescript.md and /docs/en/headless.md, not on this page; and not for every hook run)`

### D09 — `hooks.md`

**Claimed:** Observed at runtime: a `PreToolUse` command hook exiting with code 2 blocked a Bash tool call, and the tool result delivered to the model matched the documented error format exactly, with the denial attributed to the hook in the machine-readable metadata.

**Actually true:** The claim is labelled "Observed at runtime" but no runtime observation was performed here, and the quoted text (lines 829-833) is a documentation example: "With this script registered as a `PreToolUse` hook on `Bash`, a command that starts with `rm` is blocked, and Claude receives the hook's stderr as the tool's error, prefixed with the event name, the tool name, and the hook's command: `PreToolUse:Bash hook error: [${CLAUDE_PROJECT_DIR}/.claude/hooks/no-rm.sh]: Blocked: rm commands are not allowed`". The "machine-readable metadata" element is unsupported: hooks.md documents the denial as a human-readable transcript notice string; it documents no machine-readable field attributing the denial to a hook. Corrected claim (OBSERVED-DOC): the page documents this exact error format for a PreToolUse hook that exits 2 on Bash.

**Corrected status:** `OBSERVED-DOC (documented example, not a runtime observation)`

### D10 — `hooks.md`

**Claimed:** Observed at runtime: exit 0 with unparseable JSON is classified as a non-blocking error rather than a success, the hook's decision is discarded entirely, and the diagnostic names the concrete remedy (use a JSON encoder rather than string concatenation).

**Actually true:** Two problems. (1) "Observed at runtime" is unsupported — no runtime observation was performed; the content is documented behaviour (line 790: "When your hook exits 0 but prints JSON that can't be parsed or fails [schema validation](#json-output), the action goes ahead unless the hook is one [whose failure blocks the action]... the run is a [non-blocking error](#exit-code-output)"). (2) The claimed remedy is not in the doc: the word "encoder" appears ZERO times on the page, and the doc's actual remedy (line 792) is "your stdout counts as [JSON output](#json-output) only when you print one JSON object, on one line or several, with nothing around it but whitespace" plus "use the parse or validation message that the `<hook name> hook error` notice carries". Corrected claim: exit 0 with unparseable JSON is a documented non-blocking error and the fields are not applied; the diagnostic points at the parse/validation message and the "one JSON object, nothing else on stdout" rule.

**Corrected status:** `OBSERVED-DOC (documented behavior; the "JSON encoder" remedy does not appear on the page)`

### D11 — `hooks.md`

**Claimed:** Observed at runtime: the `if` handler filter and the tool-name `matcher` both filter correctly, and `disableAllHooks: true` suppresses hook execution entirely.

**Actually true:** No runtime observation was performed, so the "Observed at runtime" framing is unsupported; the underlying behaviours are documented. The supplied quote (line 696) supports only the disableAllHooks half and says nothing about the `if` filter or the matcher (those are documented separately at lines 280-285 and 413-434). "Suppresses hook execution entirely" is also overstated: line 698 states "The `disableAllHooks` setting respects the managed settings hierarchy. If an administrator has configured hooks through managed policy settings, `disableAllHooks` set in user, project, or local settings can't disable those managed hooks. Only `disableAllHooks` set at the managed settings level can disable managed hooks." Corrected claim: documented behaviour — `disableAllHooks` disables non-managed hooks; managed policy hooks require the managed-level setting.

**Corrected status:** `OBSERVED-DOC (documented behavior; "entirely" is qualified by the managed-settings exception)`

### D12 — `feature-availability.md`

**Claimed:** The page documents concrete substitutions for every gated feature rather than only removals: /loop substitutes for /schedule, GitHub Actions or GitLab CI/CD substitutes for cloud sessions, and the WebFetch tool with a specific URL substitutes for web search. The same 'Alternatives:' pattern repeats on the Bedrock, Claude Platform on AWS, Agent Platform and Foundry tabs.

**Actually true:** The specific substitutions are verbatim, and the repetition claim is confirmed (four "**Alternatives:**" blocks at raw-md lines 243, 255, 269, 282 — Bedrock, Claude Platform on AWS, Agent Platform, Foundry). But "for every gated feature" overstates the doc. The page's own framing is explicitly conditional: "Each tab lists what is unavailable or partially supported on that provider, with alternatives where one exists." Most gated features have NO stated alternative — e.g. the Bedrock tab's "Not available" line lists fast mode, Advisor, Channels, the analytics dashboard, server-managed settings, and the /design-sync and /import commands, and the Alternatives block covers only /schedule, cloud sessions and web lookups. Also, the web-lookup alternative appears only on the Bedrock tab (Claude Platform on AWS and Agent Platform have web search, so no substitute is listed there; Foundry's tab has no web-lookups line). Corrected claim: the page offers concrete substitutes for /schedule, cloud sessions and (on Bedrock only) web search, and gives no alternative for the other gated features.

**Corrected status:** `OBSERVED-DOC`

### D13 — `sub-agents.md`

**Claimed:** Five built-in subagent types are registered by default: Explore (read-only, Write/Edit denied, main model or provider-dependent), Plan (read-only, inherits model), general-purpose (every subagent tool), claude (catch-all), statusline-setup (Sonnet), and claude-code-guide (Haiku).

**Actually true:** The count is wrong: the page documents SIX built-in types, not five, and the claim's own list enumerates six. L35 Explore, L51 Plan, L61 General-purpose, plus the "Other" table at L75-L79 listing claude, statusline-setup, claude-code-guide. Every per-agent attribute the claim lists is accurate and verbatim: Explore "**Tools**: read-only tools; Write and Edit are denied" (L42) and model "the main conversation's model" with the provider-dependent Fable branch (L39-L41); Plan "**Model**: inherits from the main conversation" and "read-only tools; Write and Edit are denied" (L55-L56); General-purpose "**Tools**: every tool [available to subagents]" (L66); claude "A catch-all with every tool [available to subagents]" (L77); statusline-setup/Sonnet and claude-code-guide/Haiku (L78-L79). L81 also qualifies registration as "Built-in subagents are registered by default in interactive sessions" (interactive only), and L86 notes `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` removes all built-in types in non-interactive/SDK mode. Correct the count to six.

**Corrected status:** `OBSERVED-DOC`

### D14 — `sub-agents.md`

**Claimed:** Subagents Claude spawns from the main conversation start in the background by default; a background spawn returns an agent id and an explicit notice that the parent must not predict the results, and completion arrives later as a notification carrying the id.

**Actually true:** Two of the four assertions are not on the page. L910 supports "With nothing configured, a subagent that Claude spawns from your main conversation starts in the background." L945 supports "A background subagent's results reach Claude as a completion notification in a later turn." But (a) a full-text search for "predict" returns zero hits anywhere on the page, and the claim's own quote contains no notice text — the page nowhere states there is an explicit notice telling the parent not to predict background results; the nearest text is L945 "if you ask about progress first, it reports that the subagent is still running"; and (b) the page never says the completion notification carries the agent id. The id itself is documented elsewhere and in a different sense: L1125 "When a subagent completes, Claude receives its agent ID" and L1151 "the agent ID it received when it spawned that agent" (received at spawn), while Explore/Plan return no id (L1126). The third element of the claim's quote is supported: L906 "When a background subagent reaches a tool call that needs permission, Claude Code surfaces the prompt in your main session and names the subagent that is asking." The "explicit notice" and "notification carrying the id" details remain UNKNOWN from this page.

**Corrected status:** `OBSERVED-DOC`

### D15 — `skills.md`

**Claimed:** Skill and command names containing a zero-width space or control character, a private-use or unassigned character, a bidi direction control, a blank other than one plain space (no-break space, double space, leading/trailing space), or < or > are refused and do not load. A name may also not exceed 256 characters. Refusals are discoverable via claude --debug and a [names] log tag.

**Actually true:** The character list and the 256-char limit are correct, but "are refused and do not load" over-generalizes across the two kinds of names the claim names. skills.md L459-462 states two exceptions: "A custom command or skill doesn't load when Claude Code refuses its directory or file name" (so the directory/file-name case does not load), but "A skill still loads when these characters are only in a plugin skill folder's name or in its frontmatter `name`" — for a plugin folder the characters "become hyphens in the skill's command name", and for a frontmatter `name` "The `/` menu doesn't show the `name` value and typing it doesn't invoke the skill." errors.md L5385-5386 confirms the two distinct outcomes: "Not loaded" vs "`name` field ignored". Also verified: the debug-log route is correct (skills.md L464, errors.md L5389: "search the debug log for `[names]`"), and the 256-char cap is at errors.md L5382/L5391 ("shorten a name that is over 256 characters"). Corrected claim: refused characters in a directory/file name prevent the skill from loading; in a frontmatter `name` they leave the skill loaded but the name ignored; in a plugin skill folder they are replaced by hyphens.

**Corrected status:** `OBSERVED-DOC`

### D16 — `skills.md`

**Claimed:** Model access to skills is controlled with Skill permission rules: Skill denies all skills, Skill(name) is an exact match, and Skill(name *) is a prefix match with any arguments. A deny rule naming an unqualified skill also blocks its nested dir:name form and its alias; Skill(anthropic-skills *) approves every account-synced skill while Skill(anthropic *) does not cover the anthropic-skills: namespace.

**Actually true:** Everything except the alias clause is confirmed. skills.md L847-865: deny the Skill tool with "Skill"; "Allow or deny specific skills using permission rules: `Skill(commit)` `Skill(review-pr *)` `Skill(deploy *)`"; "Permission syntax: `Skill(name)` for exact match, `Skill(name *)` for prefix match with any arguments." L872 confirms the nested form: "| An unqualified name | `Skill(deploy)` | A nested skill listed as `apps/web:deploy` |". L881-883 confirm "**`Skill(anthropic-skills *)` approves every synced skill**" and "`Skill(anthropic *)` doesn't cover `anthropic-skills:pdf`". BUT the alias clause is inverted: the doc's table (L871) reads "| An alias | `Skill(review)` | The bundled `/code-review`, through its `/review` alias |" — a rule that names the ALIAS blocks the underlying skill, not the other way round. The doc never says a rule naming a skill's own name blocks that skill's alias; alias-wide matching is documented only for the parameter form (L875: "| A skill in the parameter form | `Skill(skill:deploy)` | The skill whichever of its names Claude calls it by, including its alias and display name |", mirrored at docs/en/permissions.md L138). Corrected claim: a deny rule naming an alias also blocks the skill behind that alias; to match a skill under all its names (including alias and display name) use the parameter form `Skill(skill:<name>)`.

**Corrected status:** `OBSERVED-DOC`

### D17 — `skills.md`

**Claimed:** Bundled skills are prompt-based whereas most built-in commands execute fixed logic; they are listed in the commands reference marked "Skill" in the Purpose column. disableBundledSkills turns them off while /doctor stays typable and can be hidden via the DISABLE_DOCTOR_COMMAND environment variable or a skillOverrides entry of "doctor": "off". Some bundled skills, such as /verify and /simplify, run only when invoked.

**Actually true:** All but the /simplify clause is confirmed. skills.md L23: "Bundled skills are prompt-based: they give Claude detailed instructions and let it orchestrate the work using its tools. Most built-in commands instead execute fixed logic directly." L35: "Bundled skills are listed alongside built-in commands in the commands reference, marked **Skill** in the Purpose column" (verified in commands.md L50-51 "| Command | Purpose |" with entries such as L62 "| `/batch <instruction>` | **[Skill](/docs/en/skills#bundled-skills).** ..."). L29/L33 confirm disableBundledSkills and the /doctor handling verbatim. BUT no doc says /simplify runs only when invoked. skills.md L25 names only "/verify": "others, including `/verify`, run only when you invoke them", and commands.md L38 names only "/verify" (and L40 "/deep-research") with the same note. I grepped every fetched page (skills.md, commands.md, code-review-local.md, errors.md, permissions.md, settings-reference.md, env-vars.md, workflows.md, sub-agents.md) and found no statement about /simplify's invocation policy. Corrected claim: the doc names /verify (and the /deep-research workflow) as run-only-when-invoked; /simplify's invocation policy is not established by the docs.

**Corrected status:** `OBSERVED-DOC`

### D18 — `streaming-output.md`

**Claimed:** Exact TypeScript field shape of the partial-frame wrapper: ten fields, with ttft_ms present only on message_start events.

**Actually true:** The quoted shape is verbatim (https://code.claude.com/docs/en/agent-sdk/typescript.md lines 1938-1950) and the ttft_ms qualifier is exact ('ttft_ms?: number; // Time to first token in ms, present only on message_start events'). But the field count is wrong: the declared type has NINE properties (type, event, parent_tool_use_id, uuid, session_id, ttft_ms?, user_message_uuid?, user_message_uuids?, resume_reason?), not ten — the claim's own quoted block lists nine. Corrected: nine fields.

**Corrected status:** `OBSERVED-DOC`

### D19 — `streaming-output.md`

**Claimed:** Without partial messages the message-type set is unchanged except for StreamEvent, which is the only option-gated variant; the compaction boundary is a distinct type in TypeScript but a SystemMessage subtype in Python.

**Actually true:** Two of three parts check out. Verbatim at streaming-output.md line 117 ('you receive all message types except `StreamEvent` ... a compact boundary message ... (`SDKCompactBoundaryMessage` in TypeScript; `SystemMessage` with subtype `"compact_boundary"` in Python)'), Python union confirmed at https://code.claude.com/docs/en/agent-sdk/python.md lines 1586-1595, and SDKCompactBoundaryMessage at https://code.claude.com/docs/en/agent-sdk/typescript.md (~line 1955). BUT 'the only option-gated variant' is false and is contradicted by the very SDK references the claim cites: includeHookEvents / include_hook_events (typescript.md line 520; python.md line 905) also gate SDKHookStartedMessage / SDKHookProgressMessage / SDKHookResponseMessage (Python: HookEventMessage) into the stream, and forwardSubagentText changes which assistant/user messages appear. StreamEvent is not the only option-gated variant.

**Corrected status:** `OBSERVED-DOC`

### D20 — `streaming-output.md`

**Claimed:** The CLI's stream-json surface is a strict superset of the published SDKPartialAssistantMessage shape: its stream_event frames carry at least two fields the SDK type does not declare (thinking_display, api_message_id), and its assistant frames carry request_id and timestamp beyond the documented SDKAssistantMessage. This proves that consumers must tolerate unknown keys.

**Actually true:** Partly wrong, though the core conclusion survives. Verified in the on-host capture C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area-headless-programmatic\stream-json-events.jsonl: the stream_event frame does carry undocumented 'thinking_display":"updates"' and 'api_message_id":"msg_9mWXpq94OdxFctGCzjXv"', and the assistant frame does carry 'request_id":"gen-1792604917-..."'. But the claim's second example is false: timestamp is NOT beyond the documented SDKAssistantMessage — https://code.claude.com/docs/en/agent-sdk/typescript.md declares 'timestamp?: string;' inside type SDKAssistantMessage and documents its semantics ('the ISO 8601 time when the message\'s content finished generating ... use it for display only'). Only request_id is undocumented there. 'Strict superset' is also loose: the observed frames omit the optional user_message_uuid / user_message_uuids / resume_reason fields the SDK type declares, and the observed first stream_event carried no user_message_uuid despite the doc's 'first non-ping stream event' rule. Corrected framing: the CLI emits at least three keys (thinking_display, api_message_id, request_id) that the SDK types do not declare, so consumers must tolerate unknown keys.

**Corrected status:** `INFERRED`

### D21 — `settings-reference.md`

**Claimed:** There are 245 documented settings keys across 18 topical sections, each with an explicit scope, type, and default — making this a complete machine-readable configuration contract, not a prose page.

**Actually true:** Source: https://code.claude.com/docs/en/settings-reference.md (raw markdown, 404,714 bytes, 5,877 lines). The quote is verbatim (page line 3, under "# All settings"). But three of the claim's specifics are wrong or over-stated. (1) SECTION COUNT: there are 17 topical H2 sections, not 18 — "Model and responses", "Permission settings", "Sandbox settings", "Memory and context", "Interface and terminal", "Git and attribution", "Hooks and automation", "Plugins and skills", "MCP", "Agents, sessions, and worktrees", "Remote, desktop, and notifications", "Authentication and providers", "Updates and versioning", "Tools", "Privacy and telemetry", "Enterprise and managed settings", "Global config settings" (plus "## Settings index" and "## See also", giving 19 H2s total). The index table's "Topic" column independently yields 17 distinct topic values, matching the 17 H2s exactly. (2) "each with an explicit scope, type, and default": 244 of 245 H3 entries carry **Scope**, **Type** and **Default**; the one exception is `taskOutputMaxChars`, a removed key whose entire body is a WARNING callout with no Scope/Type/Default. (3) The numbers 245 and 18 appear nowhere on the page (grep for "245" → 0 hits; "18 topical" → 0 hits), so the quoted intro blurb cannot be the evidence for them. The 245 figure is nonetheless independently correct: the index table has exactly 245 rows, there are exactly 245 H3 key entries, and the two sets are an exact 1:1 match (no key in one and not the other) — though 245 counts dotted sub-paths (e.g. `permissions.allow`, `attribution.commit`, `policyHelper.path`) as distinct keys, and 6 of the 245 are removed/deprecated no-ops (taskOutputMaxChars, keybindingFlavor, voiceEnabled, includeCoAuthoredBy, permissionExplainerEnabled, teammateDefaultModel). The "machine-readable configuration contract" framing is the reviewer's; the page is a prose reference page with a Markdown index table, not a machine-readable schema file.

**Corrected status:** `OBSERVED-DOC`

### D22 — `settings-reference.md`

**Claimed:** Hooks are gated by four independent layers, and HTTP-hook secret interpolation requires a two-list intersection (the hook's own allowedEnvVars AND the outer httpHookAllowedEnvVars).

**Actually true:** The second half of the claim is fully supported, the first half is not, and one of the two supplied quotes is irrelevant to hooks. VERIFIED: "### `httpHookAllowedEnvVars`" (page line 3574) — "This key sets an outer limit on that list for every HTTP hook: a hook can use a variable only if both its own `allowedEnvVars` and this key name it. Use it to stop a hook from reading a secret it shouldn't, even when the hook's definition asks for it." That is exactly the two-list intersection, with "Arrays merge across settings files" as its Scope note. NOT SUPPORTED: "Hooks are gated by four independent layers." The page never states a layer count — greps for "four layer", "four gate", and "four independent" return zero hits. The page in fact documents at least six distinct hook-gating mechanisms, and they are not presented as a layered stack: `disableAllHooks` (managed settings, or any file, with different reach), `allowManagedHooksOnly` (managed), `strictPluginOnlyCustomization` with the "hooks" surface (managed), `allowedHttpHookUrls` (URL allowlist for HTTP hooks), `httpHookAllowedEnvVars` (env-var allowlist), and the workspace-trust gate ("the folder isn't trusted under the same workspace trust rule as hooks in settings files"). The gate order the page does document is a two-way decision for statusLine/fileSuggestion/subagentStatusLine ("Off entirely" vs "Narrowed to managed settings"), not a four-layer model. The second supplied quote — "Only these values still apply from project and local settings, because they turn something off" — is from the `env` section (#### Variables Claude Code ignores in `env`) and has nothing to do with hooks; it is a mismatched citation. Corrected formulation: HTTP-hook env interpolation is a two-list intersection (supported); the hook-gating layer count is not established by this page.

**Corrected status:** `OBSERVED-DOC`

### D23 — `settings-reference.md`

**Claimed:** The status line is a command-driven extension point with a bidirectional JSON protocol: state is written to the command's stdin, and the command writes back {"id","content"} lines that replace rows by id.

**Actually true:** The claim conflates two different settings. The statusLine Type fragment is verified verbatim in "### `statusLine`" (page line 2974): "object with `type` set to `\"command\"` and a `command` string, plus optional `padding` as a number of characters, `refreshInterval` as a number of seconds, minimum `1`, and `hideVimModeIndicator` as a Boolean". But the bidirectional {"id","content"} protocol belongs to a DIFFERENT key — "### `subagentStatusLine`" (page line 2996): "On each refresh, Claude Code sends the visible rows as one JSON object on stdin, with a `tasks` array carrying each subagent's `id`, `name`, `status`, `model`, `tokenCount`, and more, and replaces the row for each `id` you write back as a `{\"id\", \"content\"}` line. Rows you don't write back keep the default rendering." The `statusLine` entry on this page documents NO stdin protocol at all (grep for "stdin" in the statusLine block returns nothing); its own protocol is on /docs/en/statusline, and the page only says the command renders "context such as the model, cost, or git branch". The only stdin-JSON protocol on this page belongs to `fileSuggestion` ("The command receives JSON on stdin with a `query` field holding what you've typed so far", H4 "#### Command input and output"), which is the @-autocomplete surface, not the status line. Corrected formulation: the command-driven extension point, padding/refreshInterval/hideVimModeIndicator fields and merge/gating semantics are OBSERVED-DOC for `statusLine`; the {"id","content"} row-replacement protocol is OBSERVED-DOC for `subagentStatusLine` (subagent rows only), and the general statusLine stdin protocol is not established by this page.

**Corrected status:** `OBSERVED-DOC`

### D24 — `settings-reference.md`

**Claimed:** The published CLI help corroborates the documented settings contract, including the exact seven permission-mode choices and the per-session override flags.

**Actually true:** Two defects. (1) THE COUNT IS WRONG. The quote's own text lists SIX choices, not seven: `claude --help` (local CLI, version 2.1.306) prints "--permission-mode <mode> Permission mode to use for the session (choices: \"acceptEdits\", \"auto\", \"bypassPermissions\", \"manual\", \"dontAsk\", \"plan\")". The DOC's `permissions.defaultMode` lists SEVEN values because it adds "default" as a named mode; the CLI flag omits it (default is implicit). So the CLI does not corroborate "the exact seven permission-mode choices" — it shows six, and the mismatch is real, not a formatting artefact. The same divergence appears in effort: the CLI's "--effort <level> Effort level for the current session (low, medium, high, xhigh, max)" accepts "max", which the `effortLevel` SETTING does not (Type offers only low/medium/high/xhigh). (2) THE EVIDENCE IS NOT THE PAGE. The status OBSERVED-DOC is wrong: none of these flag help strings appear on https://code.claude.com/docs/en/settings-reference.md — a grep for "permission-mode" on the page returns only `permissions.defaultMode`, `autoMode`, `disableAutoMode`, `skipAutoPermissionPrompt`, `skipDangerousModePermissionPrompt` and `plansDirectory` entries, never a --permission-mode flag choice list. The four flag help fragments ARE verbatim from the local binary (verified: --permission-mode, --effort, --autocompact "(auto, or 100k–1M tokens)", --setting-sources "(user, project, local)"), and --autocompact/--setting-sources do align with the doc's `autoCompactWindow` and the user/project/local scope vocabulary. The correct characterisation: the CLI help is a direct local observation of the shipped binary (permitted: "run the published CLI's own help surfaces"), it broadly corroborates the settings contract, but it lists six permission-mode choices against the doc's seven and accepts a "max" effort level the `effortLevel` key does not.

**Corrected status:** `INFERRED`

### D25 — `settings-reference.md`

**Claimed:** Credential acquisition has four distinct documented mechanisms, all of the same 'run my command, parse my output' shape.

**Actually true:** The count and the uniform shape are both wrong. THE COUNT: the page documents FIVE "Run your own command" settings keys, not four — apiKeyHelper (page line 5004), awsAuthRefresh (5030), awsCredentialExport (5048), gcpAuthRefresh (5143), otelHeadersHelper (5161). Four of them are model-request credential mechanisms (apiKeyHelper, awsAuthRefresh, awsCredentialExport, gcpAuthRefresh); the fifth, otelHeadersHelper, generates OpenTelemetry export headers ("Run your own command to generate the headers Claude Code sends with OpenTelemetry exports"), which is not a model credential at all — yet the claim's own parenthetical lists it. THE SHAPE: "run my command, parse my output" does not hold uniformly. awsAuthRefresh writes to the .aws directory and Claude Code "reads the refreshed `.aws` directory" — it parses no stdout; otelHeadersHelper "expects a JSON object of string header values on stdout" and awsCredentialExport "accepts the `aws sts` output shape and the flat `aws configure export-credentials` shape" — three different output contracts. The apiKeyHelper fragments the claim quotes ARE verbatim and correct (shell `/bin/sh` on macOS/Linux and `cmd` on Windows; output sent as both `X-Api-Key` and `Authorization: Bearer`; cache lifetime "five minutes by default"; rerun on `401`/`403`; rerun before a request when the cached output is an expired JWT). Corrected formulation: five command-execution settings exist, four of which supply model-request credentials with four different output contracts (raw stdout, refreshed .aws directory, AWS JSON, OTel header JSON).

**Corrected status:** `OBSERVED-DOC`

### D26 — `agents.md`

**Claimed:** Concurrency is governed by four separate, named, overridable limits with different enforcement styles: a count cap that fails the spawn with a specific error string (20 subagents, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`), a depth cap enforced by withholding the tool rather than erroring (3 layers), a batch-size cap that errors rather than truncating (4,096 items per call), and a total-run cap (1,000 agents per run), plus a 15,000-token combined-description budget that warns rather than rejects.

**Actually true:** Every individual number checks out, but the framing "four separate, named, overridable limits" is wrong on two counts, and one limit is misclassified. (1) Overridability is uneven: only two of the four are overridable. `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (default 20) and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` (default 3) have env vars (env-vars.md lines 314, 320; sub-agents.md lines 1083, 1062-1071). The 4,096-items-per-call cap and the 1,000-agents-per-run cap are hard limits with no env var and no settings key — env-vars.md has no workflow batch/total-agent variable (only CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS and CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS), and neither workflows.md nor settings-reference.md exposes an override. (2) The claim says "four ... limits" but then enumerates five things (the 15,000-token budget is separate from the four). (3) The 4,096 cap is a per-call batch-size cap, not a concurrency limit, so the claim's own header "Concurrency is governed by four ... limits" does not fit it — the actual workflow concurrency limit is 16 concurrent agents (CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS, default 16, range 1-256), which the claim omits entirely. Verified sub-claims: count cap errors with the string "Concurrent subagent limit reached" and "the error tells Claude not to retry" (sub-agents.md line 1083); depth cap enforced by withholding the tool — "At the depth limit, Claude Code withholds the `Agent` tool from every subagent except a [fork]" (sub-agents.md line 1049), and a fork at the limit "returns an error instead of spawning"; batch cap "the runtime rejects a longer list with an error" and "A silent cap would drop part of the workload without telling the script" (workflows.md line 361); total cap "1,000 agents total per run | Prevents runaway loops" (workflows.md line 362); 15,000-token budget "Claude Code shows a [warning at startup with the total token count]" and "Claude Code loads every agent whether or not the total is over the limit, so the warning doesn't change what loads" (sub-agents.md line 27, errors.md line 5308). Also note the concurrent-subagent limit is not enforced under ultracode (sub-agents.md line 1083), and there is no limit on total subagents over a session (line 1081).

**Corrected status:** `OBSERVED-DOC`

### D27 — `agents.md`

**Claimed:** The full shell surface for background work is `claude agents` (TUI), `claude agents --cwd <path>`, `claude agents --json`, `claude attach <id|name>`, `claude logs <id|name>`, `claude stop|kill <id>`, `claude respawn <id>` / `--all`, `claude rm <id>`, and `claude daemon`; the `claude agents` subcommand additionally carries a complete set of dispatch defaults (model, effort, permission-mode, agent, settings, mcp-config, plugin-dir, add-dir, restricted, setting-sources) that are distinct from the main launch flags.

**Actually true:** The command inventory is accurate but the flag characterization is wrong. Verified on https://code.claude.com/docs/en/agent-view "### Manage sessions from the shell" (lines 780-795) and confirmed live on this host via `claude --help` and `claude agents --help`. The table lists exactly: `claude agents`, `claude agents --cwd <path>`, `claude agents --json`, `claude attach <id|name>`, `claude logs <id|name>`, `claude stop <id>` (also accepts `claude kill`), `claude respawn <id>`, `claude respawn --all`, `claude rm <id>`, plus `claude daemon status|logs|stop --any`. The problem is the second half: the doc says (agent-view.md line 751) "Agent view accepts the same configuration flags as `claude` for loading settings, plugins, MCP servers, and additional directories" — so `--settings`, `--setting-sources`, `--plugin-dir`, `--add-dir`, and `--mcp-config` are NOT distinct to the agents subcommand; they are the same configuration flags the top-level command takes, deliberately shared. Only four flags are genuinely agent-view-specific dispatch defaults (agent-view.md line 721): "To set defaults for every session you dispatch from agent view, pass any of `--permission-mode`, `--model`, `--effort`, or `--agent` when opening it". `--restricted` is a top-level claude flag (cli_reference.md line 125) that agent view also accepts and applies to dispatched sessions (line 733) — a shared flag, not a distinct one. Live `claude agents --help` on this host confirms: --add-dir, --agent, --all, --allow-dangerously-skip-permissions, --cwd, --dangerously-skip-permissions, --effort, --json, --mcp-config, --model, --permission-mode, --plugin-dir, --restricted, --setting-sources, --settings, --strict-mcp-config. Two smaller notes: `claude daemon` is not a bare command in the doc, it is `claude daemon status|logs|stop --any` (plus `claude daemon run` in cli_reference.md line 33); and the claim writes `claude stop|kill <id>` where the doc says the stop command "Also accepts `claude kill`" — consistent with the claim.

**Corrected status:** `OBSERVED-DOC`

### D28 — `agents.md`

**Claimed:** UNKNOWN — the assigned page contains no API contract, so the wire-level shape of several load-bearing surfaces cannot be established from it: the exact mailbox JSON message schema, the `isolation: "remote"` value in AgentInput (listed in the SDK schema but described by no parallel-agent page), the cross-session message size cap and inbox burst limit, and supervisor restart-ordering guarantees.

**Actually true:** Correct about the assigned page (https://code.claude.com/docs/en/agents.md contains no schemas, settings keys, caps, or file paths), but over-reaches when it says these "cannot be established" — three of the four are settled by other public pages the claim itself names. (a) Mailbox JSON message schema — genuinely UNKNOWN: agent-teams.md line 241 says entries are validated against "the message format" but never shows the format; no example mailbox JSON appears anywhere in the cached docs (only the path and the validation behavior). (b) `isolation: "remote"` — genuinely UNKNOWN as to semantics: it appears in the AgentInput schema (agent-sdk-typescript.md line 3106: `isolation?: "worktree" | "remote"`) and the Python SDK (agent-sdk-python.md line 2586), but a grep across every cached doc page and both SDK pages finds no page describing what "remote" isolation does — confirmed absent. (c) Cross-session message size cap and inbox burst limit — NOT unknown; the claim is wrong here. cross-session-messaging.md line 333: "Claude Code refuses a message to a session on this machine once its serialized form passes about a million characters", and errors.md line 4459 gives the exact refusal "the serialized message is 1,203,844 characters and the limit is 1,048,576". The burst limit is documented in errors.md line 4477: "Too many messages to this session just now: 30 were sent recently and more would be dropped by its rate limit, so this one was not sent." (d) Supervisor restart-ordering guarantees — genuinely UNKNOWN: agent-view.md documents that the supervisor restarts processes (line 843) and reconnects via roster.json (line 870), but a grep for "in order"/"order of"/"sequentially" in agent-view.md returns no ordering guarantee. So the blanket UNKNOWN is right for (a), (b), and (d) but wrong for (c). Correct status: UNKNOWN, scoped to the mailbox JSON schema, the semantics of `isolation: "remote"`, and supervisor restart ordering — with the message size and burst limits corrected to OBSERVED-DOC.

**Corrected status:** `UNKNOWN`

### D29 — `tools-reference.md`

**Claimed:** Grep is built on ripgrep and uses ripgrep's regex syntax (not POSIX grep); metacharacters must be escaped. It supports three output modes, respects .gitignore by default (unlike Glob, which does not), and declares truncation honestly via totalMatches/countIsComplete/appliedLimit/appliedOffset rather than silently truncating.

**Actually true:** Substantively right but the truncation-field attribution is WRONG in a way that would mislead a reimplementer. VERIFIED: ripgrep quote is verbatim at tools-reference.md line 330 ('Grep is built on [ripgrep](https://github.com/BurntSushi/ripgrep) and uses ripgrep\'s regex syntax, not POSIX grep. Patterns that include regex metacharacters need escaping. For example, finding `interface{}` in Go code takes the pattern `interface\\{\\}`.') Three output modes verify at lines 336-340 (files_with_matches default, content, count). Gitignore asymmetry verifies at line 320 ('Glob doesn\'t respect `.gitignore` by default... This differs from [Grep](#grep-tool-behavior), which skips gitignored files. To make Glob respect `.gitignore`, set `CLAUDE_CODE_GLOB_NO_IGNORE=false`...') and line 343 ('Grep respects `.gitignore`, so gitignored files are skipped.'). ERROR: totalMatches and countIsComplete are NOT Grep fields. In agent-sdk/typescript.md, GrepOutput (line 4163) is { mode?, numFiles, filenames, content?, numLines?, numMatches?, totalFiles?, totalLines?, appliedLimit?, appliedOffset? } — no totalMatches, no countIsComplete. Those two belong to GlobOutput (line 4145). The claim's own SDK quote ('`totalMatches` reports the number of matching files before truncation. When `countIsComplete` is false, `totalMatches` is a lower bound...') is the Glob section text at line 4159, presented under a 'Grep tool behavior' heading. CORRECTED FIELD ALLOCATION: Grep declares truncation via totalFiles (files_with_matches mode, v2.1.208+), totalLines (content mode, v2.1.210+), appliedLimit and appliedOffset; Glob declares it via totalMatches and countIsComplete (v2.1.191+). The honest-truncation property itself is real and applies to both tools.

**Corrected status:** `OBSERVED-DOC`

### D30 — `sandboxing.md`

**Claimed:** Filesystem isolation and network isolation are two independent layers, either of which can be disabled alone. Setting sandbox.filesystem.disabled to true skips filesystem isolation while keeping network isolation, and it defaults to false (requires v2.1.216+).

**Actually true:** Overstated on the symmetry. The doc supports the layers being independent ('The sandbox has two independent layers...') and supports a one-way filesystem switch: 'sandbox.filesystem.disabled defaults to false. Requires Claude Code v2.1.216 or later.' But the doc documents NO way to disable the network layer alone. I confirmed no sandbox.network.disabled exists in the settings reference, and grep of both the page and the runtime README found no network-isolation disable knob (enableWeakerNetworkIsolation is a macOS trustd carve-out, not a layer disable). The doc also warns that 'Effective sandboxing requires both filesystem and network isolation.' Corrected claim: the layers are independent, only the filesystem layer has a documented disable switch (sandbox.filesystem.disabled, default false, requires v2.1.216+), and no network-only disable is documented.

**Corrected status:** `OBSERVED-DOC`

### D31 — `headless.md`

**Claimed:** The `--output-format json` result envelope is a single JSON object whose field set is stable and documented, including the terminal-reason enum with 19 values.

**Actually true:** The claim splices two separate assertions, one of which holds and one of which does not. TRUE PART: the terminal_reason enum has exactly 19 values. I extracted the list programmatically from agent-sdk/typescript.md:1717 and counted 19: completed, max_turns, tool_deferred, aborted_streaming, aborted_tools, hook_stopped, stop_hook_prevented, background_requested, blocking_limit, rapid_refill_breaker, prompt_too_long, image_error, model_error, api_error, malformed_tool_use_exhausted, budget_exhausted, structured_output_retry_exhausted, tool_deferred_unavailable, turn_setup_failed. FALSE PART: "the field set is stable and documented" is contradicted by the evidence. The SDKResultMessage type (sdk-ts.md:1619-1697) is explicitly version-gated field by field (e.g. "Requires Agent SDK v0.3.268 or later", "Requires Agent SDK v0.3.260 or later", "Requires Claude Code v2.1.219 or later"), so the field set demonstrably changes between versions. Black-box probe on v2.1.306 produced a result envelope containing three fields that appear NOWHERE in the SDK reference or errors.md: `safety_stops`, `subagent_stats`, and `time_to_request_ms` (grep count 0 in both sdk-ts.md and errors.md). Conversely `mcp_server_errors` is documented on headless.md:281 but has 0 hits in sdk-ts.md, so the two pages' field sets disagree in both directions. Nothing in any doc asserts stability. The terminal_reason enum is also NOT part of the `--output-format json` envelope spec on headless.md — it lives in the Agent SDK reference. Corrected status: UNKNOWN for the "stable and documented" assertion; the 19-value enum is OBSERVED-DOC.

**Corrected status:** `UNKNOWN`

### D32 — `headless.md`

**Claimed:** Semantic failures are reported in-band on the result envelope via `subtype`, `terminal_reason` and `errors[]`, and the process exit code is non-zero at the same time. Observed: `error_max_turns` (exit 1), `error_max_budget_usd` (exit 1), `error_during_execution` (exit 1).

**Actually true:** The two quoted observations were reproduced exactly, but the third was not, and the claim's framing overstates the doc. VERIFIED: `error_max_turns` — reproduced on v2.1.306: exit 1, `{"type":"result","subtype":"error_max_turns","is_error":true,"terminal_reason":"max_turns","stop_reason":"tool_use","num_turns":2,"errors":["Reached maximum number of turns (1)"]}` — matches the quote field for field. `error_max_budget_usd` — reproduced: exit 1, `subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`, `errors: ["Reached maximum budget ($0.0001)"]`, `stop_reason: null`, `result: null` — matches. NOT VERIFIED: `error_during_execution` with exit 1. My probes produced no such result: an invalid model gave `subtype: "success"` with `is_error: true`, `terminal_reason: "api_error"`, `api_error_status: 400`, `result: "API Error: 400 definitely-not-a-real-model-xyz is not a valid model ID"` and NO `errors` array; a bogus `--permission-prompt-tool` exited 0 with `subtype: "success"`, `is_error: false`. The claimed `{"subtype":"error_during_execution","result":"API Error: 400 Invalid Anthropic Messages API request"}` is a plausible shape (the type is documented at sdk-ts.md:1667-1673) but I could not reproduce it, and the substring "Invalid Anthropic Messages API request" appears 0 times in errors.md. ADDITIONAL OVERSTATEMENT: the claim says semantic failures are reported via "subtype, terminal_reason AND errors[]" — the invalid-model case above is a semantic failure carrying terminal_reason "api_error" with NO `errors` array at all, so `errors[]` is not a universal channel. And the attribution to "Basic usage (doc)" is wrong: headless.md:33 says only that the CLI "prints the failure as the result on stdout" for in-run failures such as missing authentication; it never documents `subtype`/`terminal_reason`/`errors[]` for the result envelope — those live in the Agent SDK reference. The INFERRED reasoning is also only partly valid: the "in-band + non-zero exit" pattern is confirmed for the two cases actually observed, but the third case is unconfirmed.

**Corrected status:** `INFERRED`

### D33 — `headless.md`

**Claimed:** Human-facing notices are kept out of the machine channel: the "Waiting for background work to finish" line is printed to stderr, and with json or stream-json output it prints only when stdout isn't a terminal, so the JSON a script reads never carries it. MCP config-skip warnings likewise appear only in `mcp_server_errors`.

**Actually true:** The first half is exactly right; the second half overstates. VERIFIED: headless.md:86 "When stderr is a terminal and the run has waited five seconds, Claude Code prints a line to stderr that starts with `Waiting for background work to finish` and names the work. With [`json` or `stream-json` output](#get-structured-output), the line prints only when stdout isn't a terminal, so the JSON your script reads never carries it." OVERSTATED: the claim says MCP config-skip warnings "likewise appear only in `mcp_server_errors`", but the doc says the opposite. headless.md:283: "When you run the command by hand in a terminal, Claude Code also prints a startup warning to stderr, such as `Warning: 1 MCP server skipped due to invalid config:`, followed by the reason for each skipped entry. When you redirect stderr, or when a program such as a CI runner or an SDK host captures it, Claude Code prints no warning and reports the skipped entries only in the `mcp_server_errors` field." So the warning is printed to stderr in a terminal, and the "only in mcp_server_errors" behavior applies specifically when stderr is redirected/captured — the same stderr-capture condition that governs the background-work line. The claim conflates the two cases and asserts an absolute that the doc contradicts for the terminal case. Status stays OBSERVED-DOC (the underlying facts are all documented), but the claim as written is not supported and should be narrowed to "when stderr is redirected or captured".

**Corrected status:** `OBSERVED-DOC`

### D34 — `headless.md`

**Claimed:** `--max-turns` and `--max-budget-usd` are print-mode-only caps that are enforced in-band with an error subtype and a non-zero exit; the budget cap is a stop, not a pre-flight reservation (I observed a run billed $0.0618 against a $0.0001 cap).

**Actually true:** The structural claims hold, but the specific figure and the "print-mode-only" framing both fail. VERIFIED: cli-reference.md:106 "| `--max-turns` | Limit the number of agentic turns (print mode only). Exits with an error when the limit is reached." and cli-reference.md:105 "| `--max-budget-usd` | Stop the run once estimated spend on API calls reaches this amount (print mode only)." In-band enforcement with error subtype and non-zero exit reproduced on v2.1.306: `--max-turns 1` → exit 1, `subtype: error_max_turns`, `terminal_reason: max_turns`; `--max-budget-usd 0.0001` → exit 1, `subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`, `errors: ["Reached maximum budget ($0.0001)"]`. THE QUOTE IS STALE: the claim's quoted text for `--max-budget-usd` ("Maximum dollar amount to spend on API calls (only works with --print)") does NOT appear in the current cli-reference.md; the current wording is "Stop the run once estimated spend on API calls reaches this amount (print mode only)... Spend can pass the cap, so leave headroom." — which independently CONFIRMS the "stop, not pre-flight reservation" conclusion (spend can exceed the cap), so the conclusion is right while the quote is not verbatim from the current doc. THE OBSERVED FIGURE IS WRONG: the claim reports "$0.0618", but my reproduction of the same scenario on v2.1.306 recorded `total_cost_usd: 0.236008` against the $0.0001 cap — roughly 4x the claimed amount. That is a fidelity error in the observation, and the corrected number is far more dramatic evidence for the same conclusion. MINOR: "print-mode-only" for `--max-turns` is doc-stated, but `--max-budget-usd` is described as "print mode only" too, so that part is fine.

**Corrected status:** `INFERRED`

### D35 — `auto-mode-config.md`

**Claimed:** The built-in rules are labelled prose of the form 'Label: prose', and every user-intent-clearable `soft_deny` rule carries a '[named+specifics — must name: ...]' clause stating what the user must explicitly name for the block to clear.

**Actually true:** The supplied quote does NOT appear on the page. It is the CLI's shipped rule text, not the doc's. The page's own example JSON shows a DIFFERENT, shorter wording: 'Git Destructive [named+specifics — **must name:** the destructive operation and its target]: Force pushing (`git push --force`), deleting remote branches, tags, or releases, or rewriting remote history. Also `git commit --amend` when…' (the page explicitly labels it 'a truncated example'). The page's example is a single rule, so the doc never establishes the 'EVERY soft_deny rule' universal; that is only OBSERVED from the CLI: on 2.1.306 all 72 soft_deny rules carry a '[named+specifics — **must name:** …]' clause (71 distinct clause values), while the 17 allow rules carry none and hard_deny has exactly one rule, 'Data Exfiltration'. The 'Label: prose' form itself is OBSERVED-DOC from the page's example.

**Corrected status:** `PARTIAL — 'Label: prose' form and the clause on the shown example are OBSERVED-DOC; the 'every soft_deny rule' universal is OBSERVED (CLI 2.1.306, 72/72), not documented; the supplied quote is absent from the page`

### D36 — `cli-reference.md`

**Claimed:** The CLI surface is 33 subcommands defined in a single table, each with an exact description and example, and a mistyped subcommand produces a 'Did you mean' suggestion on stderr with exit code 1 without starting a session.

**Actually true:** The doc's `## CLI commands` table has 36 body rows (I parsed the raw markdown: 38 pipe lines minus 2 header lines). The '33' figure is not in the doc and is not a count the page supports; it appears in the local findings file, where the author had already collapsed rows (merging `claude -c`/`-c -p`, dropping the `cat file | claude -p "query"` row) into a 34-row table. Counting distinct `claude <sub>` invocation rows gives 29; counting distinct top-level subcommand words gives 21 (agents, attach, auth, auto-mode, daemon, doctor, gateway, import, install, logs, mcp, plugin, purge, remote-control, respawn, rm, self-hosted-runner, setup-token, stop, ultrareview, update). The '33 subcommands' number is thus an unsupported overstatement. The 'each with an exact description and example' part is also false for the `claude mcp` row, whose Example column is prose ('See the [Claude Code MCP documentation](/docs/en/mcp).') rather than a command. The mistyped-subcommand half is fully correct: I ran `claude udpate` myself and got stdout empty, stderr 'unknown command "udpate"' / ' └ Did you mean claude update?' / 'Run claude --help to list commands, or claude -p "udpate" to send as a prompt.', exit code 1. The doc quote is verbatim correct.

**Corrected status:** `OBSERVED-DOC`

### D37 — `cli-reference.md`

**Claimed:** `claude agents --json` prints active sessions as a JSON array with a stable element schema of pid, cwd, kind, startedAt, sessionId, name, status; `--json --all` adds completed background sessions.

**Actually true:** Doc quote verbatim correct for the CLI-reference row: 'or `--json` to print active sessions as a JSON array for scripting (`--json --all` also includes completed background sessions)'. But the 'stable element schema of pid, cwd, kind, startedAt, sessionId, name, status' part is false as stated. I ran `claude agents --json` repeatedly (4+ runs) and in one run an element carried an EXTRA key `waitingFor` alongside the 7 listed; other runs returned exactly the 7. The authoritative agent-view doc (https://code.claude.com/docs/en/agent-view) documents the schema as conditional, not fixed: 'cwd, kind, startedAt | Always'; 'id | Background sessions'; 'state | Background sessions'; 'pid, status | While the process is alive'; 'waitingFor | When status is waiting'; 'sessionId, name | When set'. So `id` and `state` appear for background sessions and `waitingFor` appears when status is waiting. The element schema is variable, not a fixed 7-key record. The '--json --all adds completed background sessions' half is correct and confirmed by `claude agents --help`: '--all With --json: also include completed background sessions'.

**Corrected status:** `OBSERVED-DOC`

### D38 — `cli-reference.md`

**Claimed:** Variadic options (--tools, --allowedTools, --disallowedTools, --add-dir, --mcp-config, --betas, --plugin-dir, --plugin-url) absorb the following positional prompt, producing 'Input must be provided either through stdin or as a prompt argument when using --print'.

**Actually true:** The claim's list of eight variadic options is wrong. I measured each one live. Absorbing the prompt (i.e. producing the 'Input must be provided either through stdin or as a prompt argument when using --print' error): --tools, --allowedTools, --disallowedTools, --add-dir, --betas, and --mcp-config. NOT absorbing: --plugin-dir and --plugin-url. `claude -p --plugin-dir "./nope" "say OK"` returned 'OK' (prompt delivered normally), and `claude -p --plugin-url "https://example.com/x.zip" "say OK"` likewise returned 'OK'. This matches the help output, where --plugin-dir and --plugin-url are single-valued (`--plugin-dir <path>`, `--plugin-url <url>`, the latter with '(repeatable: --plugin-url A --plugin-url B)') while the truly variadic ones are declared `<tools...>`, `<directories...>`, `<configs...>`, `<betas...>`. Also note the exact error string for --mcp-config is different: it reports 'MCP config file not found: <path>' (it treats the prompt as a second config path) rather than the 'Input must be provided' message. The claim's INFERRED reasoning (commander-style variadic consumption) is sound for the options that do absorb, and the behavioural-difference test is real, but the option list is materially wrong, so the claim as stated is not supported.

**Corrected status:** `INFERRED`

### D39 — `cli-reference.md`

**Claimed:** The print-mode JSON envelope carries 25 observed top-level keys covering cost, timing, token usage, permission denials, safety stops and status.

**Actually true:** The count is wrong: the live print-mode `--output-format json` envelope has 26 top-level keys, not 25. I measured it directly: api_error_status, duration_api_ms, duration_ms, fast_mode_disabled_reason, fast_mode_state, first_content_frame_ms, is_error, modelUsage, num_turns, permission_denials, queued_turn_count, result, result_index, safety_stops, session_id, stop_reason, subagent_stats, subtype, terminal_reason, time_to_request_ms, total_cost_usd, ttft_ms, ttft_stream_ms, type, usage, uuid = 26. The 25 came from the stale local artifact at C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\cli-reference\print-mode-json-envelope.json, which itself has 26; an even older local sample at agent-reference-shots\print-mode-json-result.json has 28 (extra: per_turn_effort_active, plus a _note annotation key). So the envelope is not a fixed-size schema across builds either. The claim's enumerated key list in the quote names 25 and omits per_turn_effort_active, which appears in the 28-key sample. The INFERRED reasoning about the envelope being deliberately redundant about failure is a reasonable reading of the observed fields, but the numerical premise it rests on is wrong.

**Corrected status:** `INFERRED`

### D40 — `cli-reference.md`

**Claimed:** `--add-dir` grants file access but not .claude/ configuration discovery, and validates that each path is a directory, offering a helpful parent-directory suggestion.

**Actually true:** The doc quote is verbatim correct: 'Grants file access; Claude Code [doesn't discover](/docs/en/permissions#additional-directories-grant-file-access-not-configuration) most `.claude/` configuration from these directories. Validates that each path exists as a directory. You can't add most [network paths](/docs/en/errors#working-directory-is-a-network-path), such as `\\server\share`.' But the claim's own observation note contradicts the doc and mislabels the state. The claim states 'a nonexistent path was NOT rejected (no error observed)' and then presents the whole thing as OBSERVED-DOC — the doc says the path is validated, so the observed non-rejection is a doc/behaviour discrepancy, and the OBSERVED-DOC label is over-confident. I re-tested with streams separated: `claude --add-dir "C:/definitely-not-here-xyz" -p "x"` produced exit 0, empty stderr (apart from the unrelated gateway model warning), and a normal assistant reply — the nonexistent path was indeed NOT rejected, contradicting the doc. The file-path case does work as claimed: passing a file produced '...print-mode-json-envelope.json is not a directory. Did you mean to add the parent directory C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\cli-reference?'. So the 'validates that each path is a directory' + parent-suggestion half is real (but only catches existing non-directories, not missing paths); the doc's stronger 'exists as a directory' wording is not enforced.

**Corrected status:** `OBSERVED-DOC`

### D41 — `cli-reference.md`

**Claimed:** `claude daemon` is a local background-session supervisor with a documented lifecycle (run/status/logs/uninstall/stop), a config file at ~/.claude/daemon.json and a log at ~/.claude/daemon.log, and exits 1 from `status` when it is not running.

**Actually true:** Several components fail the doc check. (1) The `uninstall` subcommand does NOT appear on the CLI-reference page: the string 'uninstall' has zero occurrences in the raw markdown, and the doc's daemon rows are only `claude daemon logs`, `claude daemon run`, `claude daemon status`, and `claude daemon stop --any`. `claude daemon --help` on 2.1.306 does list 'uninstall Remove the background service (launchctl/systemd)', so that part is real but binary-only, not documented on this page. (2) The config file path ~/.claude/daemon.json is NOT on this page either — 'daemon.json' has zero occurrences in the raw markdown. The daemon --help output shows '--json-path <p> Config file (default: ~/.claude/daemon.json)', so again the path is real but is not documented on the reviewed page; only ~/.claude/daemon.log is documented here ('Follow the background-session [supervisor's] log file, `~/.claude/daemon.log`'). (3) The 'exits 1' half is correct: the doc says 'Print the background-session [supervisor's] state, version, socket directory, and worker count for diagnostics. Exits 1 if the supervisor isn't running', and I confirmed live: `claude daemon status` printed 'not running', the sock dir '\\.\pipe\cc-daemon-*', 'control.sock: unreachable (connect ENOENT \\.\pipe\cc-daemon-*-control)', 'bg workers: 0 in roster.json', 'daemon.log: 4.8KB at C:\Users\Admin\.claude\daemon.log' and exited 1. (4) Note the observed daemon status output includes a 'roster.json' path that the claim does not mention. The claim is a fair summary of the daemon as a product but attributes to this page two things it does not contain.

**Corrected status:** `OBSERVED-DOC`

### D42 — `cli-reference.md`

**Claimed:** Local state paths are specified exactly: ~/.claude/daemon.log, ~/.claude/daemon.json, ~/.claude.json per-project entry, ~/.claude/ as the configuration directory, <repo>/.claude/worktrees/<name> for worktrees, and ~/.claude/skills/<name>/ for plugin scaffolding.

**Actually true:** Three of the six paths are not specified on this page. On the reviewed page: '~/.claude/daemon.log' appears once (daemon logs row) — OK; '~/.claude.json' appears once (purge row, as the per-project entry) — OK; '<repo>/.claude/worktrees/<name>' appears once (--worktree row: 'Start Claude in an isolated [git worktree](/docs/en/worktrees) at `<repo>/.claude/worktrees/<name>`') — OK. But: '~/.claude/daemon.json' has ZERO occurrences in the raw markdown; '~/.claude/skills' has ZERO occurrences and the string 'skills-dir' has ZERO occurrences (the `init|new [options] <name>` scaffold path comes from `claude plugin init --help` on the binary, not this page — the CLI-reference page only says 'claude plugin | Manage Claude Code [plugins](/docs/en/plugins/overview). Alias: `claude plugins`. See [plugin reference](/docs/en/plugins/cli-reference#claude-plugin-commands) for subcommands'); and '~/.claude/' as a directory path has only 2 occurrences of the '~/.claude' prefix in the whole page, neither of which states it is the configuration directory — the page instead links to /docs/en/claude-directory and names the field `configDirectory'. The claim's 'Local state paths are specified exactly' overstates what this page contains: three of the six are binary-only observations, not doc statements.

**Corrected status:** `OBSERVED-DOC`

### D43 — `cli-reference.md`

**Claimed:** `claude install` and `claude update` are version-pinned installers with a grammar of `stable`, `latest` or an exact version string like 2.1.118; `update` has the alias `upgrade`.

**Actually true:** Half the claim is not on the page. The `claude install [version]` row is verbatim correct: 'Install or reinstall the native binary. Accepts a version like `2.1.118`, or `stable` or `latest`. See [Install a specific version](/docs/en/setup#install-a-specific-version)' — and `claude install --help` confirms 'Use [target] to specify version (stable, latest, or specific version)'. But the `claude update` row on this page is only '| `claude update` | Update to latest version | `claude update` |' — it does NOT describe a version grammar, and 'upgrade' has ZERO occurrences in the raw markdown. The 'update|upgrade' alias and the update semantics come from the binary: `claude update --help` shows 'Usage: claude update|upgrade [options]' / 'Check for updates and install if available; package-manager installs update through the package manager', with NO [version] target argument in its usage line. So `claude update` is not version-pinned in the same way as `claude install`, and the alias is a binary observation rather than a doc statement. The claim conflates install's documented grammar with update's undocumented one.

**Corrected status:** `OBSERVED-DOC`

### D44 — `permission-modes.md`

**Claimed:** Each safety check has its own named kill-switch environment variable, read from the launch environment and explicitly ignored when delivered through a settings file's env block: CLAUDE_CODE_DISABLE_SUBSTITUTION_RM_PROMPT, CLAUDE_CODE_DISABLE_INLINE_SHELL_RM_PROMPT, CLAUDE_CODE_DISABLE_MOUNTED_DRIVE_RM_PROMPT, CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT, CLAUDE_CODE_DISABLE_POWERSHELL_CMD_RM_DENY, CLAUDE_CODE_AUTO_MODE_SERVER, CLAUDE_CODE_AUTO_MODE_MODEL.

**Actually true:** PARTIALLY OVERSTATED. The seven variable names all exist and are documented in env-vars.md (lines 245, 253, 256, 266, 269, 212, 213) with the quoted descriptions. But the blanket 'explicitly ignored when delivered through a settings file's env block' holds only for the five safety-check variables: settings-reference.md's 'Variables Claude Code ignores in `env`' section lists CLAUDE_CODE_DISABLE_POWERSHELL_CMD_RM_DENY ('ignored from every file') and CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT / _SUBSTITUTION_RM_PROMPT / _INLINE_SHELL_RM_PROMPT / _MOUNTED_DRIVE_RM_PROMPT ('ignored from every file'). CLAUDE_CODE_AUTO_MODE_SERVER and CLAUDE_CODE_AUTO_MODE_MODEL do NOT appear in that ignore list (zero occurrences in settings-reference.md). Separately, the page itself shows CLAUDE_CODE_AUTO_MODE_MODEL being set via a ~/.claude/settings.json "env" block (permission-modes.md lines 391-397), which is consistent with it not being ignored from user settings. The claim over-generalizes one property across all seven variables.

**Corrected status:** `OBSERVED-DOC`

---

## 9.2 The 65 corrections with material changes

These are claims whose substance held but whose framing, count, scope or confidence tag did not. They are grouped by the shape of the defect, because the shapes are what a reader should carry away.

### Confidence tag downgraded — the claim was documented, not observed — 5 item(s)

- **`sessions.md`** — **Claimed:** The default display name and the live-session registry are directly observable, with nameSource: "derived" and a per-PID registry file carrying IPC and peer-protocol details.
  **Correction:** Substance fully reproduced locally: ~/.claude/sessions/<pid>.json exists with pid, sessionId, cwd, startedAt, procStart, version, peerProtocol (1), peerFeatures (["notify_idle","artifact_yield"]), kind, entrypoint, pidDomain ("win32:elios"), messagingSocketPath (\\.\pipe\LOCAL\cc-msg-<hex>), name, nameSince, status, updatedAt, statusUpdatedAt, jobId. nameSource observed as "derived" (also "auto" for background sessions and absent for one). Derived names matched the <dirname>-<2 chars> pattern (e.g. "claude-clone-95", "verify6-6e"). Two corrections: 'claude agents --json' returned 5 live records at verification time, not 9 (the count is transient), and the key set is a superset of the claim's list — it also includes waitingFor, id and state. The registry file path is not documented anywhere in the docs set.
  **Status after correction:** `OBSERVED-LOCAL`

- **`sessions.md`** — **Claimed:** The system/init event is a machine-readable session manifest, and the observed headless JSON result carries session_id, result, usage, cost and termination metadata.
  **Correction:** Reproduced exactly. My stream-json init event had precisely the 32 keys listed (type, subtype, cwd, session_id, tools, mcp_servers, model, permissionMode, slash_commands, terminal_slash_commands, apiKeySource, claude_code_version, output_style, agents, skills, plugins, capabilities, analytics_disabled, product_feedback_disabled, uuid, memory_paths, original_cwd, additional_directories, messaging_socket_path, fast_mode_state, fast_mode_disabled_reason, per_turn_effort_active, view_mode, powershell_path, ...) and my --output-format json result had precisely the 27 keys listed. Observed values matched too: permissionMode "default", apiKeySource "none", mcp_servers [{name, status "pending", source "user"}], memory_paths.auto pointing at <config>/projects/<slug>/memory/, original_cwd == cwd. Note these exact field lists are NOT in sessions.md; headless.md documents only 'The system/init event reports session metadata including the model, tools, MCP servers, and loaded plugins'.
  **Status after correction:** `OBSERVED-LOCAL`

- **`sessions.md`** — **Claimed:** The per-project storage directory contains the session transcripts plus a memory/ subdirectory, and each session additionally gets a sibling directory holding subagent transcripts, subagent metadata, tool results, and workflow artifacts.
  **Correction:** Reproduced exactly on disk: ~/.claude/projects/<project>/ contains many <session-id>.jsonl files plus memory/; per-session sibling directories contain subagents/ (with agent-<id>.jsonl and agent-<id>.meta.json), tool-results/ (call_*.txt and bare hashes), and workflows/ with workflows/scripts/. Prompt history confirmed as a separate file: ~/.claude/history.jsonl with rows {display, pastedContents, timestamp, project, sessionId}. Only the memory/ element is documented on sessions.md ('its auto memory to /srv/tenant-a/projects/work/memory/'); the rest is undocumented layout.
  **Status after correction:** `OBSERVED-LOCAL`

- **`skills.md`** — **Claimed:** Claude Code publishes a machine-readable validator for skill directories: claude plugin validate <path> with --json and --strict. The JSON envelope has the stable top-level fields success, strict, target, manifest, contents, advice, directory; each entry in contents has file, type, errors, warnings, notes, gatingHooks, and each error/warning has path and message. Observed on this host: malformed YAML produces an error at path "frontmatter" stating the skill "loads with empty metadata (all frontmatter fields silently dropped)"; a missing frontmatter block produces a warning at path "frontmatter"; a missing description produces a warning at path "description"; and unknown fields, non-spec fields, the reserved name synced, < in a name, and a 200-character directory name are all accepted without any report.
  **Correction:** I independently reproduced every black-box observation on this host (Claude Code 2.1.306, custom ANTHROPIC_BASE_URL). `claude plugin validate --help` output matches the quoted text exactly ("--json Output the validation report as JSON (same exit codes)", "--strict Treat warnings as errors (exit 1). Use in CI to fail on unrecognized fields, missing metadata, and other issues that the runtime tolerates."). Observed JSON top-level keys were exactly success, strict, target, manifest, contents, advice, directory; each contents entry had file, type ("skill"), errors, warnings, notes, gatingHooks, and each error/warning had path, message, code. Observed: bad YAML -> success false, error at path "frontmatter", "YAML frontmatter failed to parse: YAML Parse error: Unexpected EOF. At runtime this skill loads with empty metadata (all frontmatter fields silently dropped)." (also "Unexpected token" for other fixtures); no frontmatter -> warning at path "frontmatter" ("No frontmatter block found..."); no description -> warning at path "description" ("No description in frontmatter..."); unknown field (bogus-field), non-spec field (argument-hint), directory named synced, directory named with `<`, a 200-char directory name, a frontmatter name containing `<`, `>`, a private-use char, a zero-width space, and a 300-char frontmatter name were all accepted with no report (success true; when forced into `contents` the only entry was the routine "description" warning). One nit on the claim's quoted JSON snippet: I never saw success=false with an empty contents array — success=false always came with one contents entry carrying the frontmatter error; empty contents came with success=true. STATUS CORRECTED: this is a black-box CLI observation, not doc-sourced, so it is OBSERVED, not OBSERVED-DOC. (Note: the doc at docs/en/plugins/cli-reference.md L645-652 documents success/strict/target/manifest/contents and gatingHooks but does NOT list `advice` or `directory`.)
  **Status after correction:** `OBSERVED`

- **`skills.md`** — **Claimed:** Black-box observation of the running product corroborates the discovery model: the product's own debug log reports the skill sources by category and separates unconditional from conditional skills. On this host the log lines read `Loading skills from: managed=…, user=…, project=[]`, `Loaded 2 unique skills (2 unconditional, 0 conditional, managed: 0, user: 2, project: 0, additional: 0, legacy commands: 0)`, `Total plugin skills loaded: 0 (0 duplicate/user-owned entries skipped)`, and `getSkills returning: 2 skill dir commands, 0 plugin skills, 38 bundled skills, 1 builtin plugin skills`. The category set matches the documented discovery locations.
  **Correction:** I confirmed all four log lines byte-for-byte by grepping this host's own product debug logs at ~/.claude/debug/*.txt (Claude Code 2.1.306, sessions dated 2026-10-21), e.g. "[DEBUG] Loading skills from: managed=C:\Program Files\ClaudeCode\.claude\skills, user=C:\Users\Admin\.claude\skills, project=[]", "[DEBUG] Loaded 2 unique skills (2 unconditional, 0 conditional, managed: 0, user: 2, project: 0, additional: 0, legacy commands: 0)", "[DEBUG] Total plugin skills loaded: 0 (0 duplicate/user-owned entries skipped)", "[DEBUG] getSkills returning: 2 skill dir commands, 0 plugin skills, 38 bundled skills, 1 builtin plugin skills". The category-to-location mapping (managed=enterprise, user=personal, project, additional, legacy commands) against the doc's discovery table is an inference, and it holds. STATUS CORRECTED: this is a black-box product observation, not a doc-sourced statement, so it is OBSERVED, not OBSERVED-DOC.
  **Status after correction:** `OBSERVED`

### Count corrected — 4 item(s)

- **`skills.md`** — **Claimed:** Ten substitution variables are supported: $ARGUMENTS, $ARGUMENTS[N], $N, named $name, ${CLAUDE_SESSION_ID}, ${CLAUDE_EFFORT}, ${CLAUDE_SKILL_DIR}, ${CLAUDE_PROJECT_DIR}, ${CLAUDE_PLUGIN_ROOT}, ${CLAUDE_PLUGIN_DATA}. ${CLAUDE_SKILL_DIR} and ${CLAUDE_PROJECT_DIR} are substituted in both the skill body and Bash rules inside allowed-tools.
  **Correction:** skills.md L470-481 table has exactly 10 rows, matching the claim's list one-for-one. L483: "Claude Code substitutes `${CLAUDE_SKILL_DIR}` and `${CLAUDE_PROJECT_DIR}` in two places: the skill's markdown content, and Bash rules in the `allowed-tools` frontmatter." (The doc adds that in a plugin skill, `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` are substituted in the same two places — the claim does not contradict this.)
  **Status after correction:** `OBSERVED-DOC`

- **`auto-mode-config.md`** — **Claimed:** `autoMode.environment` is a 21-slot vocabulary in three kinds — 12 context slots, 6 trust slots, and 3 sensitivity slots — with conservative defaults so the protective rules are active before the user configures anything.
  **Correction:** Underlying facts are correct, but the numeric counts are NOT stated anywhere in the doc — the doc only says '`claude auto-mode defaults` prints three kinds of environment entry' and lists the slot names. The counts 12/6/3 and the total 21 are directly OBSERVED from the local CLI (2.1.306): `claude auto-mode defaults` emits 21 environment entries — 12 context (Organization … Data retention / declassification), 6 trust (Trusted repo … Internal package registry), 3 sensitivity (Sensitive data locations & audiences, Sensitive remote targets, Protected IaC scopes). The 'conservative defaults' property is OBSERVED-DOC ('Each defaults to `None configured` or to the conservative assumption named next to it'; 'Every other trust slot defaults to `None configured`').
  **Status after correction:** `PARTIAL — slot names, kinds and default semantics are OBSERVED-DOC; the counts (12/6/3, total 21) are OBSERVED (CLI: `claude auto-mode defaults`), not documented`

- **`auto-mode-config.md`** — **Claimed:** The classifier is a separate model, configurable independently of the session model: by default classifier requests go to Claude Sonnet 5; `CLAUDE_CODE_AUTO_MODE_MODEL` overrides it (v2.1.302+); `CLAUDE_CODE_AUTO_MODE_SERVER=0` forces Claude Code's own classifier requests instead of server-side review (v2.1.271+); and classifier calls are billed as token usage on Enterprise/API accounts, adding a round trip per check.
  **Correction:** The quoted row is NOT on the page under review — it is verbatim on https://code.claude.com/docs/en/env-vars.md, and the other three elements are verbatim on https://code.claude.com/docs/en/permission-modes.md ('By default, classifier requests go to Claude Sonnet 5.'; 'With Claude Code v2.1.302 or later, set CLAUDE_CODE_AUTO_MODE_MODEL to a full model ID…'; 'To skip asking the server and always use Claude Code's own classifier requests, set CLAUDE_CODE_AUTO_MODE_SERVER=0'; 'classifier calls count toward your token usage. Each check sends a portion of the transcript plus the pending action, adding a round-trip before execution'). Two caveats: the token-billing statement omits the exception 'Where the server reviews the actions as part of the session's model requests, there are no separate classifier calls to count'; and the Sonnet 5 default is only the base row — the model can differ when an Anthropic-configured classifier model exists, on Sonnet 4.6, or when ANTHROPIC_DEFAULT_SONNET_MODEL is set.
  **Status after correction:** `OBSERVED-DOC (env-vars.md + permission-modes.md, not the page under review)`

- **`context-window.md`** — **Claimed:** The term "context editing" and any `clear_tool*` / `context_edit*` identifier appear in none of the 24 Claude Code documentation pages fetched, including the focus page; the only public trace of the behaviour is prose in the glossary and how-claude-code-works, plus side-effects visible in prompt-cache statistics.
  **Correction:** Central assertion CONFIRMED by my own independent corpus search: I downloaded 25 doc pages (the 24 listed plus agent-sdk/agent-loop.md) plus llms.txt and grepped case-insensitively for 'context edit', 'context_edit', 'contextEdit', 'clear_tool', 'clearTool', 'clear tool use', 'tool_use_clear', and 'context-editing'. Zero hits in all files, including context-window.md. The negative finding stands and the correct status is UNKNOWN. Minor imprecision in the supporting rationale: the claim says the only public trace is prose in the glossary and how-claude-code-works, but costs.md line 49 is a third public trace — 'Expected rebuilds: when Claude Code has itself just rewritten the conversation, by compaction or by clearing old tool results from context, it counts the same kind of miss as an expected rebuild instead' — which is a documented public description of the tool-output clearing behaviour. That omission does not change the conclusion (the term and identifiers still do not appear publicly), so the claim is supported, but the rationale undercounts the evidence.
  **Status after correction:** `UNKNOWN`

### Scope narrowed — 16 item(s)

- **`hooks.md`** — **Claimed:** UNKNOWN: the internal ordering and merging of multiple hooks' outputs for the same event is not specified beyond the documented decision precedence. The page says matching hooks 'run in parallel' and that all `additionalContext` values are delivered, but never states the merge order or the relative ordering of injected context.
  **Correction:** Confirmed as genuinely unresolved on this page. The quoted line 398 is verbatim ("When an event fires, its matching hooks run in parallel. If more than 12 of them are prompt or agent hooks, 12 of those run at once and the rest start as running ones finish."). Line 1106 says only "When several hooks return `additionalContext` for the same event, Claude receives all of the values" — no ordering. Grepping the page for order/ordering/sequence/merge order returns no statement about the relative order of concurrent hook outputs. UNKNOWN status is correct.
  **Status after correction:** `UNKNOWN`

- **`hooks.md`** — **Claimed:** UNKNOWN: the per-event presence matrix for the optional common input fields (`scratchpad_dir`, `agent_id`, `agent_type`, `effort`) is not given. The page states `permission_mode` is not received by every event and that `agent_id` may be absent, but provides no complete matrix.
  **Correction:** Confirmed. Quote at line 721 verbatim, including "Not all events receive this field. Check the JSON example in each [hook event](#hook-events) section". The other optional fields are described only conditionally, not by event: `scratchpad_dir` (line 720) "Absent when the session has no scratchpad or the temp directory is unavailable"; `agent_id` "May be absent" for TaskCreated/TaskCompleted/TeammateIdle (lines 2609, 2665, 2848); `effort` (line 722) "Present for events that fire within a tool-use context, such as `PreToolUse`, `PostToolUse`, `Stop`, and `SubagentStop`" — a non-exhaustive "such as" list. No complete per-event matrix exists on the page, so UNKNOWN is correct.
  **Status after correction:** `UNKNOWN`

- **`hooks.md`** — **Claimed:** UNKNOWN: the complete set of `mcp_server.source` values and their trust semantics is not enumerated on this page; the page defers to the Agent SDK reference and states only that trust decisions must be based on `source` rather than on the server name or the `mcp__<server>__` tool-name prefix.
  **Correction:** Quote at line 1722 verbatim: "For an [MCP tool](#match-mcp-tools), the input also carries `mcp_server`, an object with the server's `name` and a `source` that says where the server's definition came from. The `source` values include `plugin`, `sdk`, and configuration scopes such as `user` and `project`. [`McpServerProvenance`](/docs/en/agent-sdk/typescript#mcpserverprovenance) in the Agent SDK reference lists them all and says how to treat one you don't recognize. Base trust decisions on `source` rather than on `name` or the `mcp__<server>__` tool-name prefix." The page gives only a partial ("include") set and explicitly defers the enumeration; the `mcp_server` field also requires Claude Code v2.1.274+. UNKNOWN is correct.
  **Status after correction:** `UNKNOWN`

- **`interactive-mode.md`** — **Claimed:** The built-in footer is a live, context-sensitive hint surface: it always shows the permission-mode indicator and appends contextual hints that change with state. The documentation names the exact hint strings `esc to interrupt` and the `? for shortcuts` fallback; a live capture of this session's own TUI corroborates the rendering and shows the idle/busy variants — `⏸ manual mode on · ← for agents`, `⏸ manual mode on · ← for agents · esc to interrupt`, `⏸ manual mode on · ? for shortcuts` — alongside the effort row `● high · /effort`.
  **Correction:** The live-capture half is independently confirmed against the named files in agent-reference-shots/: tui-startup-banner.txt contains 20 occurrences of '⏸ manual mode on · ← for agents' (19 of them the '· esc to interrupt' variant), 6 of '⏸ manual mode on · ? for shortcuts', and 19 of '● high · /effort'; tui-background-session-raw.txt contains 42 '· ← for agents · esc to interrupt', 29 '⏸ manual mode on · esc to interrupt', 2 '· ? for shortcuts', 1 bare '· ← for agents', and 75 'manual mode on' in total across 74 footer rows. All three quoted variants and the effort row are genuinely present, and the mode indicator sits in every one of the 74 captured footer rows. The doc-quoted strings 'esc to interrupt' and the '? for shortcuts' fallback are named in statusline.md L18 (NOT in interactive-mode.md — grep for them in interactive-mode.md returns nothing); the 'Manual' label for `default` is in interactive-mode.md L39 ('`default` (labeled Manual in the mode indicator)'). Two corrections to the status: (1) the claim is a composite, and the capture portion is direct observation, not OBSERVED-DOC; (2) the word 'always' as applied to the permission-mode indicator is not stated in any doc, and two captures of one session cannot establish a universal — it is an inference from the observed frames. Neither point makes the underlying facts wrong.
  **Status after correction:** `OBSERVED-DOC (doc strings) + OBSERVED (live TUI capture); the 'always shows the permission-mode indicator' part is INFERRED, not documented`

- **`interactive-mode.md`** — **Claimed:** Command history is keyed per working directory, spans sessions (so `/clear` and `--resume`/`--continue` interact with it), collapses consecutive duplicate submissions into one entry, has `!` expansion disabled by default, and has a distinct reverse-search implementation per renderer (inline over all history vs. a fullscreen dialog with a session/project/all scope cycled by `Ctrl+S`).
  **Correction:** Verified in interactive-mode.md: L269 ('Input history is stored per working directory'), L270 ('Running `/clear` starts a new session: recall then lists the new session's prompts first, with earlier sessions' prompts after them. The previous session's conversation is preserved and can be resumed.'), L271 ('Submitting the same prompt twice in a row records one history entry, so pressing Up steps to the previous distinct prompt'), L273 ('History expansion with `!` is disabled by default'), L284 ('In [fullscreen rendering], `Ctrl+R` opens a search dialog instead: type to filter, press `Up` and `Down` to move through matches, and press `Ctrl+S` to cycle the scope through this session, this project, and all projects.'), L289 ('The inline search always searches prompts from all projects'), L297 ('The inline search scans your full prompt history, newest first, with duplicates collapsed to the newest occurrence.'). One clause is an inference rather than a doc statement: the Command history section never mentions `--resume`/`--continue` (those flags appear only in the Task list section, L703). That history is keyed per working directory and spans sessions of the same project makes the interaction substantively true, but the parenthetical is the report's own reasoning, not quoted documentation.
  **Status after correction:** `OBSERVED-DOC (the `--resume`/`--continue` parenthetical is INFERRED, not stated in the Command history section)`

- **`tools-reference.md`** — **Claimed:** Glob and Grep are absent from the default tool set on macOS, Linux and WSL — search there is done through the Bash tool with embedded `bfs` and `ugrep` binaries, and those searches reach hooks and permission rules as `Bash` calls. The Task/TodoWrite family is model-gated, available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5 and earlier models, and requires an explicit opt-in otherwise.
  **Correction:** Both quotes are verbatim and every element verifies on https://code.claude.com/docs/en/tools-reference.md. Glob section line 304: 'On Windows, it's part of the default tool set. On macOS, Linux, and WSL, Claude Code leaves Glob and [Grep](#grep-tool-behavior) out of the default tool set, and Claude searches with `find` and `grep` through the Bash tool instead. In Claude\'s shell those two commands run embedded versions of `bfs` and `ugrep`, and the searches reach your hooks and permission rules as `Bash` calls.' Task tool availability line 585: 'The task-tracking tools, `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`, and `TodoWrite`, are available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models.' The 'requires an explicit opt-in otherwise' half verifies at line 587 ('On every other model, Claude Code leaves the tools out unless you opt in') with the opt-in mechanisms enumerated at lines 589-594 (CLAUDE_CODE_ENABLE_TODO_TOOLS=1, --allowedTools, --tools, SDK allowedTools/tools). Two exceptions the claim omits but does not contradict: background and cloud sessions provide these tools on every model (line 596), and the model gating applies from v2.1.268 (line 600).
  **Status after correction:** `OBSERVED-DOC`

- **`tools-reference.md`** — **Claimed:** Edit performs exact string replacement with three gating checks (read-before-edit, exact match, uniqueness) and returns a structured diff plus a concurrent-modification flag. Matching is exact — a single whitespace or indentation character difference causes a miss — and a non-unique match requires either more context or `replace_all: true`.
  **Correction:** All three gating checks and both matching rules verify verbatim in the 'Edit tool behavior' section of https://code.claude.com/docs/en/tools-reference.md. Line 251: 'The Edit tool performs exact string replacement. It takes an `old_string` and a `new_string` and replaces the first with the second. It doesn\'t use regex or fuzzy matching.' The three checks are enumerated as a bulleted list at lines 255-259: '**Read-before-edit**', '**Match**: `old_string` must appear in the file exactly as written. A single character of whitespace or indentation difference is enough to miss.', '**Uniqueness**: `old_string` must appear exactly once. When it appears more than once, Claude either supplies a longer string with enough surrounding context to pin down one occurrence, or sets `replace_all: true` to replace them all.' One SOURCING CORRECTION: the 'structured diff plus a concurrent-modification flag' part is NOT in the tools-reference page (which publishes no output schemas). It comes from the Agent SDK reference, FileEditOutput (agent-sdk/typescript.md line 4000), which carries `structuredPatch: Array<{oldStart, oldLines, newStart, newLines, lines}>`, `userModified: boolean`, `replaceAll: boolean`, and an optional `gitDiff` block. The tools-reference page states the concurrent-change behavior in prose only (line 259: 'the result notes that the file carries other changes').
  **Status after correction:** `OBSERVED-DOC`

- **`sandboxing.md`** — **Claimed:** claude doctor is the diagnostic channel for sandbox misconfiguration, surfacing named warnings: "TLS termination is unavailable" for a mask setup that cannot work, "Sandbox network domain entries have unreliable spellings" for ambiguous IPv6 entries, "Sandbox credential injectHosts entries can never match their destination", and "Stale sandbox mask files left by a killed session" for leftover 0-byte placeholders.
  **Correction:** All four warning strings appear verbatim on the page, each tied to 'run claude doctor in your terminal and look for the ... warning'. Two version gates are attached in the doc (injectHosts check requires v2.1.229; stale-file flagging added before v2.1.257) which the claim omits but does not contradict.
  **Status after correction:** `OBSERVED-DOC`

- **`headless.md`** — **Claimed:** The complete `system` channel type/subtype vocabulary, the exact ordering of `system/init` versus startup hook/plugin events, and the mapping of every non-`completed` `terminal_reason` to an exit code are not fully specified by the docs.
  **Correction:** Each of the three sub-claims is confirmed by the evidence, and the claim is correctly conservative. (a) system channel vocabulary: the SDKMessage union (sdk-ts.md:1443-1477) has 34 members, of which FIVE have no `###` definition section in the reference — SDKAPIRetryMessage, SDKElicitationCompleteMessage, SDKMemoryRecallMessage, SDKMirrorErrorMessage, SDKNotificationMessage — and each has its own `type`/`subtype` pair, so the full system-channel vocabulary is not spelled out in one place. (b) init ordering: headless.md:256-259 states only that init "is the first event in the stream unless startup events precede it" and then lists plugin_install, hook_started, hook_progress, hook_response as possible predecessors — it does not specify a total order among those, nor among the many other system subtypes (status, task_notification, tool_progress, auth_status, rate_limit_event, prompt_suggestion, conversation_reset, etc.). (c) exit-code mapping: grep across sdk-ts.md, errors.md, and agent-loop.md finds NO table mapping terminal_reason values to exit codes; the SDK reference documents "exit code" in no result-message context at all, and headless.md:33 states only the coarse "exits with code 0 on success and a non-zero code when the run fails". The 19 terminal_reason values (sdk-ts.md:1717) are never paired with exit codes. Status UNKNOWN is correct and appropriately hedged — and it is exactly the right thing to flag, since my black-box probes showed a semantic failure (invalid model) exiting 1 with `terminal_reason: "api_error"` but `subtype: "success"`, and another probe exiting 0 with `terminal_reason: "completed"`, showing the mapping is not a simple function of terminal_reason.
  **Status after correction:** `UNKNOWN`

- **`auto-mode-config.md`** — **Claimed:** `autoMode.classifyAllShell: true` suspends EVERY Bash and PowerShell allow rule while auto mode is active, so the classifier evaluates every shell command regardless of the allow list (except critical-path removals). The default is the opposite: only broad arbitrary-code-execution rules (`Bash(*)`, wildcarded interpreters) and all `Monitor` rules are suspended, so a narrow rule like `Bash(npm test)` can still let a destructive argument through unseen.
  **Correction:** All quoted fragments verified verbatim, including the decisive 'This means a narrow rule can still let a destructive argument through without the classifier seeing it, for example a script path or flag the rule's prefix didn't anticipate.' One correction: the claim's default-side enumeration ('only ... `Bash(*)`, wildcarded interpreters ... and all `Monitor` rules') is narrower than the real dropped set. The page hedges with 'such as', and permission-modes.md gives an explicit five-item list also dropped on entering auto mode: blanket `Bash(*)`/`PowerShell(*)`, wildcarded interpreters like `Bash(python*)`, package-manager run commands, `Agent` allow rules, and `Monitor` allow rules. An implementer copying only the claim's list would under-suspend rules.
  **Status after correction:** `OBSERVED-DOC (page's own 'such as' hedge; full dropped-rule set is OBSERVED-DOC on permission-modes.md)`

- **`auto-mode-config.md`** — **Claimed:** `/auto-mode-setup` is a built-in command that drafts `autoMode.environment` entries from the project and recent sessions, and it always reads: the project's CLAUDE.md/README/config files/git remotes, the user's `autoMode` and `permissions.allow` settings, and the hosts/buckets/command names from commands Claude ran in recent sessions in that project (never the user's messages). Two optional scans add shell-history first words and the remote hosts/names of repos under the home directory.
  **Correction:** All quoted fragments verified verbatim. Page adds two facts the claim omits but does not contradict: it 'sometimes' drafts rule entries too, and it is plan/version gated ('available on Pro, Max, Team, and Enterprise plans and with a Claude Console API key'). It is 'a built-in command rather than a bundled skill', so `skillOverrides` applies but `disableBundledSkills` does not.
  **Status after correction:** `OBSERVED-DOC`

- **`auto-mode-config.md`** — **Claimed:** When the classifier cannot return a verdict, the action is DENIED (fail closed) with a message that names the model, the failure category and a next step, and the session continues to allow read-only work that does not require the classifier. No-verdict denials are NOT recorded in the 'Recently denied' tab.
  **Correction:** Supplied quote verbatim. The remaining elements are on the linked errors.md page: 'Reads, searches, and edits inside your working directory skip the classifier, so they keep working in all of these cases'; message '<model> is temporarily unavailable, so auto mode cannot determine the safety of <tool> right now. Wait a moment and then try this action again', with categories '(rate-limited), (overloaded), (server error), (timed out), (connection failed)'. Caveat: 'names the model' holds for the classifier-unavailable message only — the server-side variant reads 'The server-side auto mode classifier gave no verdict (timed out), so auto mode cannot determine the safety of <tool>.' and the PermissionDenied hook `reason` is fixed text ('Auto mode could not evaluate this action and is blocking it for safety' or 'Classifier unavailable'). The category appears only when Claude Code can determine one.
  **Status after correction:** `OBSERVED-DOC (auto-mode-config.md + linked errors.md), with the message-shape caveat noted`

- **`auto-mode-config.md`** — **Claimed:** Auto mode is gated on plan, organisation policy, model and provider; a session that fails the gate starts in Manual instead. The debug log on 2.1.306 exposes the gate state as `verifyAutoModeGateAccess: enabledState=... disabledBySettings=... modelSupported=... canEnterAuto=...`, and `permissions.disableAutoMode: "disable"` in managed settings removes auto mode from the Shift+Tab cycle entirely.
  **Correction:** Supplied quote verbatim on permission-modes.md ('Auto mode is available only when your account meets all of these requirements: Plan / Organization / Model / Provider'), and 'On any other model, the session starts in Manual instead' plus 'This removes `auto` from the `Shift+Tab` cycle, and a session started with `--permission-mode auto` starts in Manual instead' are also verbatim there. However the debug-log claim is NOT documented: the string `verifyAutoModeGateAccess` appears in none of the ten doc pages fetched (auto-mode-config, permission-modes, env-vars, errors, hooks, permissions, settings-reference, troubleshooting, debug-your-config, cli-reference). It is OBSERVED from local 2.1.306 `--debug-file` output, which shows the exact field names plus two extras the claim omits: 'enabledState=enabled disabledBySettings=false model=… modelSupported=true disableFastModeBreakerFires=false carouselAvailable=true canEnterAuto=true'.
  **Status after correction:** `PARTIAL — gate requirements, Manual fallback and `permissions.disableAutoMode` are OBSERVED-DOC (permission-modes.md); the `verifyAutoModeGateAccess` field names are OBSERVED (local 2.1.306 debug log), not documented`

- **`permission-modes.md`** — **Claimed:** In the CLI, Shift+Tab cycles permission modes as default -> acceptEdits -> plan, with optional modes slotting in after plan (bypassPermissions first, auto last). dontAsk never appears in the cycle. The status bar shows a distinct string per mode: a gray `⏸ manual mode on` for default, or `⏵⏵ accept edits on`, `⏸ plan mode on`, `⏵⏵ auto mode on`, `⏵⏵ don't ask on`, `⏵⏵ bypass permissions on`. The `⏸ manual mode on` string was captured live 75 times in a background-session log.
  **Correction:** Cycle and status-bar strings verified verbatim (lines 171 and 179-183), including the exact glyphs `⏸ manual mode on`, `⏵⏵ accept edits on`, `⏸ plan mode on`, `⏵⏵ auto mode on`, `⏵⏵ don't ask on`, `⏵⏵ bypass permissions on` and the 'dontAsk: never appears in the cycle' bullet. The 'captured live 75 times in a background-session log' sub-detail is a local observation I could not reproduce (no background-session log containing that string was found under ~/.claude/jobs on this host), but it is peripheral to the doc-backed claim and does not contradict it.
  **Status after correction:** `OBSERVED-DOC`

- **`context-window.md`** — **Claimed:** The full compaction lifecycle is observable in the debug log with three named trigger levels and an isolated summarization context: level=ok (below threshold), level=warn (approaching), level=compact (fired), followed by a separate summarization API request and a session.compact hook; for an unrecognized model the compaction routes through a reactive path keyed on thresholdSource=unknown-model.
  **Correction:** INDEPENDENTLY REPRODUCED. I forced a real compaction on this host with CLAUDE_CODE_MAX_CONTEXT_TOKENS=100000 and CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS=60000 over a 550KB file, then read the debug log. Observed sequence: 'autocompact: tokens=[REDACTED] level=ok effectiveWindow=80000' (x2), then 'level=warn effectiveWindow=80000' (x4), then 'level=blocked effectiveWindow=80000' followed immediately by 'autocompact: routing through reactive (thresholdSource=unknown-model)', then '[API REQUEST] /api/v1/messages source=compact', then 'Forked agent [reactive-compact] received message: type=assistant', 'Forked agent [reactive-compact] finished: 1 messages, types=[assistant], totalUsage: input=1288 output=2786 cacheRead=57732 cacheCreate=0', then 'hooks module cc-plugin-agents-md@builtin session.compact settled in 22944.2ms (native link, next() included)'. A second compaction cycle produced the same shape with 'level=compact' plus '[INFO] compact: kept tail holds 1 thinking block(s); strip=off (decided by flag; model=minimax/minimax-m3.1-flash:free, thinking=adaptive)'. The claim's three named levels (ok/warn/compact), the separate summarization API request (source=compact), the session.compact hook, and the reactive path with thresholdSource=unknown-model are all confirmed. One correction: the claim says 'three named trigger levels' but the log actually exposes FOUR — 'blocked' is a distinct level the claim omits, and it is the level that immediately precedes the reactive routing. The claim's 'followed by a separate summarization API request and a session.compact hook' ordering is correct (source=compact precedes the hook settlement). Also note the fork agent is labelled '[reactive-compact]' on this host, which is a reactive-path-specific name — the claim's 'isolated summarization context' is correct.
  **Status after correction:** `OBSERVED-DOC`

- **`context-window.md`** — **Claimed:** When the model ID is not recognized, Claude Code assumes a 200k context window, warns at startup with a link to the correction page, and routes auto-compaction through a reactive path; the documented corrections are CLAUDE_CODE_MAX_CONTEXT_TOKENS, the [1m] suffix, CLAUDE_CODE_DISABLE_1M_CONTEXT=1, and CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1.
  **Correction:** Doc side verified on https://code.claude.com/docs/en/model-config.md lines 821-835: the exact warning text '⚠ Model "my-gateway-opus" isn't recognized · context assumed to be 200k tokens · ...' and 'Claude Code doesn't recognize the model "my-gateway-opus", so it assumes a context window of 200k tokens. Update Claude Code, or see https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id to set the window.' The four corrections are all documented: [1m] suffix (line 834), CLAUDE_CODE_MAX_CONTEXT_TOKENS (line 835), CLAUDE_CODE_DISABLE_1M_CONTEXT=1 (line 756), CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 (env-vars.md line 272: 'Set to `1` to skip proactive auto-compaction when Claude Code doesn't recognize the model ID'). The local half is also verified on this host: the [claude-code:unrecognized_model] {'model':'minimax/minimax-m3.1-flash:free','query_source':'sdk'} line was reproduced exactly, and the reactive path 'autocompact: routing through reactive (thresholdSource=unknown-model)' was observed in my own compaction run. One minor imprecision: the claim lists CLAUDE_CODE_DISABLE_1M_CONTEXT=1 among 'corrections' for an unrecognized model ID, where the doc presents it in a specific conditional role ('To correct the window while keeping proactive compaction, also set CLAUDE_CODE_DISABLE_1M_CONTEXT=1'), not as a general correction — but the variable is genuinely relevant and the doc's own warning text lists both [1m] and CLAUDE_CODE_MAX_CONTEXT_TOKENS.
  **Status after correction:** `OBSERVED-DOC`

### Classification corrected — 40 item(s)

- **`settings.md`** — **Claimed:** The `--settings` overlay wins over project-local settings, and project-local wins over shared project settings, when the same `env` key is set in all three.
  **Correction:** Reasoning holds: the page states the stack "highest first: managed settings, command line, project local, shared project, user" and "An `env` block inside a settings file is an ordinary key and follows the levels above", so a same-named `env` key resolves by level — command line > project local > shared project. The runtime probe outputs quoted (PROBE_SAME=from-local for shared+local, =from-cli for --settings+local) are consistent with that documented rule and add no contradiction. INFERRED is the correct classification because the settings page never states the `env`-key outcome in these words.
  **Status after correction:** `INFERRED`

- **`sessions.md`** — **Claimed:** Resume by absolute transcript path works and reuses the original session ID rather than creating a new session.
  **Correction:** Reasoning valid. I reproduced it independently: `claude --resume <abs .jsonl path> -p "..." --output-format json` on the live transcript returned session_id ca6d0088-4426-4239-8884-8c2b9e5b1238, identical to the UUID in the filename. The doc row says 'Resumes the session stored in the .jsonl transcript file at that absolute path', so 'resumes' (not 'copies') plus the observed ID match supports the handle-not-copy conclusion.
  **Status after correction:** `INFERRED`

- **`hooks.md`** — **Claimed:** INFERRED: the `if` Bash filter is implemented as a shell-command extractor with a deliberate fail-open fallback, because failing closed would fire the hook on every unrelated command and cost a process spawn each time. The same fail-open philosophy explains the documented advice to use the permission system rather than a hook for hard enforcement.
  **Correction:** Reasoning is sound. The extractor behaviour is directly documented (table lines 426-432: assignments stripped, each subcommand checked, `$()`/backticks recursed). The fail-open behaviour is documented verbatim at line 434: "When Claude Code can't determine which commands the Bash input runs, it runs your hook regardless of the pattern. Because the `if` filter is best-effort, use the [permission system](/docs/en/permissions) rather than a hook to enforce a hard allow or deny." The stated motive (a fail-closed design would have to conservatively fire the hook on indeterminate commands, costing a process spawn each time) is the verifier's own hypothesis, not documented, but it is a coherent explanation of the trade-off and is correctly flagged as INFERRED.
  **Status after correction:** `INFERRED`

- **`hooks.md`** — **Claimed:** INFERRED: `onFailure: "block"` is best explained by reclassifying a hook run's outcome into the exit-2 bucket, since that single mechanism accounts for blocking on timeout, on startup failure, on invalid JSON, on HTTP error, and for the PermissionRequest special case where it denies the request.
  **Correction:** Strongly grounded — the doc states the mechanism almost in the claim's own words at line 933: "With `"block"` set, a failure does what [exit code 2 does on that event](#exit-code-2-behavior-per-event), except on `PermissionRequest`, where it denies the request. For example, a `PreToolUse` failure blocks the tool call and a `UserPromptSubmit` failure blocks the prompt." The five failure modes are enumerated at lines 925-931, and the exit-2 per-event table at lines 961-995 supplies the bucket each failure inherits. The inference adds only the word "reclassify", which is a fair restatement.
  **Status after correction:** `INFERRED`

- **`hooks.md`** — **Claimed:** INFERRED: the 33 events are better modelled as four tiers (session lifecycle, turn lifecycle, tool-execution lifecycle, and an observation tier) than the three cadences the documentation states, because the decision-control table assigns 'None' to the observation-tier events.
  **Correction:** The quoted row is verbatim (line 1142): "| Setup, Notification, SessionEnd, PostCompact, InstructionsLoaded, StopFailure, CwdChanged, DirectoryAdded, FileChanged | None | No decision control. Used for side effects like logging or cleanup |" and the three stated cadences are verbatim at lines 21-25. The reasoning is acceptable but the "because" clause is weaker than presented: the None-row identifies the observation tier but does not by itself establish the tier taxonomy, and the partition of the other 24 events into three tiers is the verifier's own construction — the doc's three cadences (lines 23-25) were never presented as covering all 33 events, so "better than" is a modelling judgment rather than an evidence-backed improvement. No factual error; the classification as INFERRED is appropriate.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** The deny->ask->allow ordering was independently confirmed live on this host: with allow=["Bash(echo hi)"], ask=["Bash(echo *)"], deny=["Bash(echo *)"], the exact-match allow rule did not take effect and the call was recorded in permission_denials with the full command echo hi.
  **Correction:** I re-ran this probe on v2.1.306: claude -p ... --permission-mode manual --permission-prompts none --output-format json --settings with allow=[Bash(echo hi)], ask=[Bash(echo *)], deny=[Bash(echo *)]. Result: "permission_denials":[{"tool_name":"Bash","tool_use_id":"...","tool_input":{"command":"echo hi","description":"Echo hi"}}] - the exact-match allow rule did not take effect and the full command 'echo hi' is recorded. Only the model's paraphrased prose differs from the quoted self-report (mine read 'Permission to use Bash with command echo hi has been denied.'); the structured evidence matches exactly. Reasoning (doc and independent live probe agree) is valid.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** A bare tool-name deny rule removes the tool from the model's context entirely (the model never sees it), whereas a scoped rule like Bash(rm *) leaves the tool available and blocks only matching calls at call time.
  **Correction:** Verbatim at line 62. The doc adds the EndConversation exception (line 64), which the claim does not contradict since it makes no universal claim.
  **Status after correction:** `OBSERVED-DOC`

- **`settings-reference.md`** — **Claimed:** INFERENCE: a bare-name deny is a registry-level filter, not a hard capability boundary, because a model retaining any other shell-executing tool can route around it. Live evidence: with deny=["Bash"], the self-reported core registry was Agent, Edit, Glob, Grep, ListAgents, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill, ToolSearch, Workflow, Write (no Bash, no PowerShell) and the model still executed 'echo hi' via the Monitor tool (exit 0, output 'hi'); a control run with permissions={} reported 14 core tools including Bash and PowerShell.
  **Correction:** Re-ran both runs. Denied run (deny=["Bash"]): registry self-reported as Agent, Edit, Glob, Grep, ListAgents, Monitor, PushNotification, Read, ReportFindings, ScheduleWakeup, Skill, ToolSearch, Workflow - no Bash, no PowerShell; 'echo hi' via Monitor executed successfully, exit 0, output 'hi' (an initial Monitor attempt chaining an extra command was auto-denied; the plain 'echo hi' succeeded). Control run (permissions={}): 14 core tools including Bash and PowerShell, exactly as claimed. Peripheral registry entries differ from the claim's enumeration (Monitor/PushNotification vs SendMessage/Write, plus a ReportFindings compat alias) because the deferred-tool set varies per run - host variation, not a contradiction. All load-bearing facts confirmed and the inference (context-level removal, not an execution-surface boundary) follows from the doc's wording plus the live evidence.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** The trailing-space rule was confirmed live on this host: allow=["Bash(zzz *)"] DENIED the command `zzznotarealcmd`, while allow=["Bash(zzz*)"] ALLOWED and executed it (exit 127, command not found). The two runs differed only in the rule string.
  **Correction:** Re-ran both variants, same prompt and mode, only the rule changed. Bash(zzz *): "permission_denials":[{"tool_name":"Bash","tool_use_id":"call-...","tool_input":{"command":"zzznotarealcmd","description":"..."}}] and the agent reported the call was denied with no execution. Bash(zzz*): "permission_denials":[] and the agent reported exit code 127, 'zzznotarealcmd: command not found'. Cosmetic difference only: the live tool_input carries an extra 'description' field and tool_use_id relative to the claim's abbreviated JSON, and the agent's prose paraphrases the denial differently. Substance and isolation of the single variable are confirmed.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** Compound splitting was confirmed live: deny=["Bash(zzzsecret *)"] blocked the compound command `echo ok && zzzsecret stuff`, with the denial message naming the full compound string.
  **Correction:** Re-ran: "permission_denials":[{"tool_name":"Bash","tool_input":{"command":"echo ok && zzzsecret stuff","description":"..."}}] and the message was 'Permission to use Bash with command echo ok && zzzsecret stuff has been denied.' - matching the claim's quote in substance. Confirms a deny on one subcommand blocks the whole compound.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** Read deny rules are enforced across the file-reading tools and recognised file commands: with deny=["Read(./data.json)"] the live session recorded denials for the Read tool (file_path), PowerShell (Get-Content -Raw), Bash (cat), and Grep (path=data.json), and the model never obtained the file's contents through those paths.
  **Correction:** Re-ran with a git-tracked ./data.json fixture. permission_denials was exactly: [{"tool_name":"Read","tool_input":{"file_path":"...data.json"}},{"tool_name":"PowerShell","tool_input":{"command":"Get-Content -Raw ./data.json","description":"..."}},{"tool_name":"Bash","tool_input":{"command":"cat ./data.json","description":"..."}},{"tool_name":"Grep","tool_input":{"pattern":".","path":"./data.json","output_mode":"content"}}] and the model explicitly reported it never obtained the contents. One imprecision in the reasoning (not in the claim): the doc does name Grep at line 341 ('Claude makes a best-effort attempt to apply Read rules to all built-in tools that read files like Grep and Glob'), so 'the doc does not enumerate Grep' is inaccurate; it genuinely does not enumerate PowerShell. The conclusion (doc's rule and the observed tool set agree) still follows.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** The documented Read-deny limitation was reproduced live: with the same Read(./data.json) deny rule, the command `git show :data.json` was NOT denied and returned the file's full contents.
  **Correction:** Re-ran with the identical rule (deny Read(./data.json)), instructing the model to use only Bash 'git show :data.json'. permission_denials was [] and the agent returned the file's full contents ('topsecretvalue-42'). The reasoning is sound: the doc states the limit in prose and gives grep -r as its example without specifying git plumbing, and the probe resolves that gap in the direction the doc's principle implies (naming the path in the rule text is what the check keys on).
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** Network paths (Windows UNC, or /net automount on macOS/Linux) get their own permission check, and in v2.1.292+ an allow rule, a PreToolUse hook returning "allow", and the auto-mode classifier all fail to pre-approve the read - the prompt goes to the user. In dontAsk mode the read is denied; in bypassPermissions mode it runs without the prompt.
  **Correction:** Verbatim at lines 501-509. The claim's quote omits the final clause of line 509 (plan mode with bypass permissions available also runs without the prompt) but does not contradict it.
  **Status after correction:** `OBSERVED-DOC`

- **`settings-reference.md`** — **Claimed:** A bare WebFetch rule and WebFetch(domain:*) both cover every URL but behave differently: the bare form removes the tool in a deny and does NOT change which hosts sandboxed commands can reach, whereas the domain: form keeps the tool, refuses each fetch, and also blocks sandboxed command network access.
  **Correction:** Verbatim table at lines 534-537. The claim's quote omits line 530 ('only the domain: form also adds its domain to the sandbox's allowed or denied domain list') and the artifact-read difference at line 539, both of which support rather than contradict the claim.
  **Status after correction:** `OBSERVED-DOC`

- **`settings-reference.md`** — **Claimed:** additionalDirectories grants real, prompt-free read access outside the working directory: with {"additionalDirectories":["../sibling-fixture"]} the live session read the out-of-tree file ../sibling-fixture/sibling.txt with no denial recorded.
  **Correction:** Re-ran with that exact settings key and an out-of-tree fixture. permission_denials was [] and the Read tool returned the out-of-tree file's exact contents ('sibling-content-99'). The doc's 'become readable without prompts' and the observed prompt-free read agree, and the probe shows the grant is not gated behind a prompt in non-interactive mode.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** Permissions and sandboxing are complementary layers that are merged: permissions control which tools and which files/domains may be used, while sandboxing provides OS-level enforcement for Bash, PowerShell, and Monitor commands and their child processes; paths and domains from both sandbox settings and permission rules are merged into the final sandbox configuration. With autoAllowBashIfSandboxed at its default true, sandboxed Bash commands run without prompting even if a bare Bash ask rule exists.
  **Correction:** Verbatim at lines 710-717, including the EndConversation carve-out, the Bash/PowerShell/Monitor scope with child processes, the merge into the final sandbox configuration, and the autoAllowBashIfSandboxed default-true substitution. The claim's quote omits the plan-mode exception at line 719, which the claim does not contradict.
  **Status after correction:** `OBSERVED-DOC`

- **`streaming-output.md`** — **Claimed:** Partial messages are a superset view over one pipeline, not a second pipeline: a consumer that ignores stream_event frames sees exactly the default-mode message stream.
  **Correction:** The reasoning is valid and well-founded. The doc supplies all three links in the chain: (a) enabling yields StreamEvent 'in addition to the usual `AssistantMessage` and `ResultMessage`' (streaming-output.md line 17) — additive, not substitutive; (b) 'Without partial messages enabled, you receive all message types except `StreamEvent`' (line 117) — the difference is exactly the StreamEvent frames; (c) the ordering list (lines 100-115) shows the AssistantMessage/ResultMessage frames keep the same relative order, with only StreamEvent frames interleaved, and the doc states each AssistantMessage arrives before its own block's content_block_stop (i.e. the interleaving is insertion of StreamEvent frames around an unchanged message sequence). The conclusion follows. Remains an inference, correctly classified.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** Model selection is a four-stage funnel: deniedModels, then the availableModels allowlist with prefix-or-exact ID matching, then enforceAvailableModels, then the modelPicker options that reorder and relabel the UI.
  **Correction:** Every component is documented on the page (## Model and responses, 23 keys), but the "four-stage funnel" framing and its strict ordering is the reviewer's synthesis, not doc text, so the status is over-confident. SUPPORTED COMPONENTS: "### `deniedModels`" (managed scope) — "Block specific models, with or without an [`availableModels`](#availablemodels) allowlist and even when that list permits them"; "### `availableModels`" — "Restrict which models people can select for the main session, [subagents](/docs/en/sub-agents), [skills](/docs/en/skills), and the [advisor](/docs/en/advisor)"; "### `availableModelsMatch`" — "**Default**: `\"prefix\"`" (page line 335) and Type bullets "`\"prefix\"`: a model ID entry permits its version and any model ID that extends it with another segment" / "`\"exact\"`: a model ID entry permits only the version it names"; "### `enforceAvailableModels`" — index description "Keep the [`/model` Default choice](/docs/en/model-config#enforce-the-allowlist-for-the-default-model) inside your `availableModels` allowlist"; "### `modelPicker`" — "List the models the `/model` picker offers, in the order you write them and under labels you choose". TWO ACCURACY NOTES. (1) The quoted Type line "**Type**: String: `\"prefix\"` or `\"exact\"`" does NOT appear on the page; the page renders it as "**Type**: string, one of:" with two bullets. The substance ("prefix" or "exact") is right. (2) The page does not order these four as a funnel: modelPicker is a presentation layer that the allowlist constrains ("An `availableModels` allowlist still applies to these rows"), not a downstream stage of a selection pipeline, and the page never states a precedence order among the four. Corrected status: the four keys and their interactions are OBSERVED-DOC; the "four-stage funnel" ordering is INFERRED.
  **Status after correction:** `INFERRED`

- **`settings-reference.md`** — **Claimed:** Two safety-relevant operating modes are observable in the CLI but not described on this page: --safe-mode disables all customizations, and --restricted removes code-running tools and ignores user/project/local settings.
  **Correction:** The reasoning holds and the two quotes are verbatim from the local `claude --help` (2.1.306). "--safe-mode Start with all customizations (CLAUDE.md, skills, installed plugins, hooks, MCP servers, custom commands and agents, output styles, workflows, custom themes, keybindings, and more) disabled — useful for troubleshooting a broken configuration. Admin-managed (policy) settings still apply. ... Sets CLAUDE_CODE_SAFE_MODE=1." and "--restricted Restricted mode: removes the built-in tools that run commands or code (Bash, PowerShell and the other code-running tools) and WebFetch unless --tools names them, and ignores user, project and local settings files (managed settings and --settings still apply; add --strict-mcp-config to skip MCP servers too). Also confines the file tools to the working directories (--add-dir included), refuses bypassPermissions, and lets only a person or the configured permission handler approve writes to settings, git and tool-configuration files." The "not described on this page" half checks out for --restricted (grep "--restricted" on the page → 0 hits). For --safe-mode the page does name the flag twice, though only in passing: line 3507 lists it as a trigger that narrows statusLine/fileSuggestion/subagentStatusLine to managed settings, and line 2210 lists "safe mode" as something that turns off auto-memory. So --safe-mode is incidental-mention, not described; the claim's "not described on this page" is fair for --restricted and slightly generous for --safe-mode. Status stays INFERRED because the evidence is the local binary's help output, not the cited doc, and the inference is the page's silence.
  **Status after correction:** `INFERRED`

- **`agents.md`** — **Claimed:** A single Agent tool call spawns all three worker kinds — subagent, teammate, or fork — and the kind is selected by the call's own fields rather than by a separate tool. The documented input schema carries `name` (teammate) and `model`/`effort`/`run_in_background`/`isolation`; `mode` and `team_name` are accepted and ignored.
  **Correction:** Verified. tools-reference.md line 99 (https://code.claude.com/docs/en/tools-reference): "The Agent tool spawns a subagent in a separate context window. ... The same tool can also launch a teammate or a fork:" — with line 101 explaining a call carrying a `name` launches a teammate, and line 102 explaining fork mode launches a fork. The schema is confirmed in the Agent SDK TypeScript reference (agent-sdk-typescript.md lines 3096-3108): type AgentInput = { description: string; prompt: string; subagent_type?: string; model?: "sonnet" | "opus" | "haiku" | "fable"; effort?: "low" | "medium" | "high" | "xhigh" | "max"; run_in_background?: boolean; name?: string; team_name?: string; // Deprecated; ignored; mode?: ... // Deprecated; ignored ...; isolation?: "worktree" | "remote"; } — so `model`, `effort`, `run_in_background`, `isolation`, `name` are present, and `mode`/`team_name` are explicitly marked "Deprecated; ignored" (mode's deprecation is also stated at line 3093). The claim's "kind is selected by the call's own fields rather than by a separate tool" is supported by the doc's own framing. Note the schema is on the SDK/AgentInput page, not the tools-reference page (the claim's section label says "tools-reference"), and it carries `isolation: "remote"` which the claim in claim 19 says is undescribed — that is consistent and does not contradict this claim, which only asserts the value is carried in the schema.
  **Status after correction:** `OBSERVED-DOC`

- **`agents.md`** — **Claimed:** INFERRED — the reference product's parallel machinery is best modelled as a file-based, restart-tolerant, human-inspectable state machine rather than a scheduler abstraction, and that model is the single most reusable design decision for an independent implementation. The on-disk artifacts (job directories keyed by session short id, roster, per-team mailboxes and task lists) are the durable state; the supervisor, the TUI, and the JSON CLI are all views onto that state.
  **Correction:** The reasoning holds and is well-supported by the cited evidence. Durable on-disk state: agent-view.md lines 869-872 (~/.claude/daemon/roster.json, ~/.claude/jobs/<id>/state.json, ~/.claude/jobs/<id>/tmp/, ~/.claude/daemon.log); agent-teams.md lines 241 and 250 (per-agent JSON mailboxes at ~/.claude/teams/{team-name}/inboxes/{agent-name}.json, task list at ~/.claude/tasks/{team-name}/), with line 198 documenting file locking for claim races. Restart tolerance: agent-view.md line 843 (supervisor restarts unexpectedly-exited processes), line 880 (older version preserves newer state.json fields across supervisor restarts); workflows.md resume semantics (saved results replayed; "Which agents run again"). Views onto the state: agent-view.md line 871 explicitly redirects readers from parsing state.json to `claude agents --json`, and line 154 says the same. The word "scheduler" is a reasonable contrast — the doc describes coordination as file-locked task claiming and message delivery, not a central queue. Two honest caveats the claim does not carry: agent-view.md line 825 says the files under ~/.claude/jobs/<id>/ "are not a stable interface", so "human-inspectable" is true for the team/task/mailbox artifacts but explicitly disclaimed for the job state files; and "the single most reusable design decision" is a normative judgment, not a doc-supported fact. The claim is correctly labelled INFERRED and the inference follows from the cited evidence.
  **Status after correction:** `INFERRED`

- **`tools-reference.md`** — **Claimed:** The tools-reference page deliberately does NOT publish the input/output JSON schemas. The exact wire contracts live in the Agent SDK TypeScript reference under `ToolInputSchemas` and `ToolOutputSchemas`, as exact TypeScript types with optionality and enumerated unions. A reimplementer reading only the primary page would have to guess the contract.
  **Correction:** Inference valid on its core conclusion, with two corrections. VERIFIED: tools-reference.md contains ZERO case-insensitive occurrences of 'schema' (grep confirmed) — it publishes behavior in prose and tables only, never input/output JSON contracts. https://code.claude.com/docs/en/agent-sdk/typescript.md defines `ToolInputSchemas` (line 3041) and `ToolOutputSchemas` (line 3778) as exported TypeScript union types, each with 38 members, and it does use optionality (`replace_all?: boolean`) and enumerated unions (`type: "create" | "update"`, `status: "pending" | "in_progress" | "completed"`). The FileEditInput quote is exact: 'type FileEditInput = { file_path: string; old_string: string; new_string: string; replace_all?: boolean; };' (line 3183). CORRECTION 1 — 'deliberately' imputes design intent that no doc states; the absence is a fact, the motive is UNKNOWN. CORRECTION 2 — the contracts do NOT all live in the SDK reference: only 37 of the 46 tools have a '**Tool name:**' heading there, and 13 documented tools have no SDK input/output type at all (PowerShell, Skill, SendMessage, LSP, ToolSearch, ListAgents, EndConversation, SendFeedback, SendUserFile, ShareOnboardingGuide, SubagentHandback, TaskOutput, WaitForMcpServers). So the gap is wider than the claim implies, which strengthens rather than weakens the reimplementer takeaway.
  **Status after correction:** `INFERRED`

- **`tools-reference.md`** — **Claimed:** The effective tool set is resolved per session and published in the `system`/`init` stream event, so the documented 46-name table is the UNION across provider, platform, plan and model, while the session array is the INTERSECTION for the current configuration. The `Agent` tool is listed in the init array under its legacy name `Task`.
  **Correction:** Core mechanism and the alias sub-claim both verify. VERIFIED: SDKSystemMessage (agent-sdk/typescript.md line 1866) has type 'system', subtype 'init', and `tools: string[]`. The alias quote is verbatim at lines 3089 and 3826: '**Tool name:** `Agent`. The previous name `Task` is still accepted as an alias, and the `tools` array in the [`SDKSystemMessage`](#sdksystemmessage) init message currently lists this tool as `Task` for backward compatibility.' Tools-reference.md line 688: 'Your exact tool set depends on your provider, platform, and settings.' Live init observed on this host (v2.1.306, model minimax/minimax-m3.1-flash, permissionMode default): 27 tools, 'Task' present and 'Agent' absent — matching the alias rule exactly. IMPORTANT CORRECTION to the UNION/INTERSECTION gloss: the session array is NOT an intersection of the documented 46, because it contains 'DesignSync', a tool that appears in no documented table (grep across tools-reference.md, agent-sdk/typescript.md, errors.md, hooks.md, sub-agents.md, permission-modes.md returns zero hits for 'DesignSync'). The documented table is therefore not a strict superset; the live set is neither subset nor superset. Also note several table rows are themselves conditional ('Appears only in sessions where cross-session messaging is enabled', 'Provided only in auto mode', 'Removed in v2.1.277'), so the table is not a pure union either. The union/intersection metaphor should be treated as approximate, not as a set relationship a reimplementer can rely on.
  **Status after correction:** `INFERRED`

- **`sandboxing.md`** — **Claimed:** INFERRED: the Windows sandbox backend exists in the embedded runtime but is gated off in the shipped product, and the gate is a build or configuration flag rather than the doc's blanket statement of platform non-support.
  **Correction:** Reasoning is valid on its core conclusion. Evidence: (a) the observed CLI error literally says 'the Windows sandbox is not active on this session (feature gate off)', which the page's 'On native Windows, Claude Code runs commands unsandboxed' / 'The sandbox doesn't run on native Windows' does not describe as a platform capability gap; (b) the runtime README ships windows-sandbox-utils.ts and a full Windows WFP/srt-sandbox backend. CAVEAT on wording: the claim's own opening sentence asserts the gate 'is a build or configuration flag', which the evidence does not establish - the message says only that a feature gate is off, and the claim's own note correctly calls the specific mechanism UNKNOWN. Treat it as 'some feature gate is off' and leave the mechanism (server flag, build flag, account tier) UNKNOWN. The 'not documented for Windows' side note is accurate: the mask and resolved-address sections describe only macOS and Linux/WSL2 behaviour.
  **Status after correction:** `INFERRED`

- **`headless.md`** — **Claimed:** The observed envelope uses a deliberate naming asymmetry: `usage` is snake_case (`input_tokens`, `cache_read_input_tokens`) while `modelUsage` entries are camelCase (`inputTokens`, `cacheReadInputTokens`, `cacheCreationInputTokens`, `canonicalModel`, `costBasis`).
  **Correction:** Both halves verified independently. (a) Observed envelope (black-box, v2.1.306, `--output-format json`): `usage` keys are input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens, cache_creation, server_tool_use, service_tier, inference_geo, iterations, output_tokens_details, speed, fallback_credit — all snake_case. `modelUsage` keys are inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, webSearchRequests, costUSD, contextWindow, maxOutputTokens, thinkingTokens, canonicalModel, provider, costBasis — all camelCase. (b) The asymmetry is also independently DOCUMENTED, which makes this more than a black-box observation: sdk-ts.md:5097-5119 defines `type Usage` (snake_case, "This is the `BetaUsage` type from `@anthropic-ai/sdk`") while sdk-ts.md:5050-5068 defines `type ModelUsage` (camelCase, hand-rolled). The reason follows directly: Usage is the SDK's own BetaUsage type passed through verbatim, ModelUsage is Claude Code's own structure. The word "deliberate" is an interpretive gloss but is well supported by that stated provenance. Status INFERRED is appropriate and the reasoning is valid.
  **Status after correction:** `INFERRED`

- **`headless.md`** — **Claimed:** The event taxonomy separates three classes a consumer must distinguish: `system` (control/metadata), `assistant`/`user` (conversation turns, with `parent_tool_use_id` for subagent nesting), and `result` (terminal summary); `stream_event` is a raw provider-frame passthrough.
  **Correction:** Each element holds. (a) `system` carries control/metadata — headless.md:256 "The `system/init` event reports session metadata including the model, tools, MCP servers, and loaded plugins", and headless.md:239 "Claude Code emits a `system/api_retry` event before retrying". (b) `assistant`/`user` with `parent_tool_use_id` — headless.md:211 "Messages from subagents and from skills that run in a subagent appear in the stream as `assistant` and `user` messages. Their `parent_tool_use_id` field says which run each one belongs to. Messages from the main conversation carry `null` in that field", plus the `forked-command-` value at headless.md:220. (c) `result` is the terminal summary — headless.md:196. (d) `stream_event` is a raw provider-frame passthrough — sdk-ts.md:1938-1940 defines `type SDKPartialAssistantMessage = { type: "stream_event"; event: BetaRawMessageStreamEvent; ... }`, i.e. the raw Anthropic SDK stream event, and sdk-ts.md:1935 notes "stream events are emitted for the main session only". The word "taxonomy" and "must distinguish" is the claim author's framing rather than doc language, but the substance is doc-grounded. Black-box probe confirms the observed stream contained exactly system/init, assistant, and result lines. Status INFERRED is appropriate and the reasoning is valid.
  **Status after correction:** `INFERRED`

- **`headless.md`** — **Claimed:** Invalid flag combinations and an invalid `--json-schema` are startup failures: the CLI exits 1 with a message on stderr and runs no model call.
  **Correction:** Every quoted error string was reproduced verbatim on the published CLI (v2.1.306), each with exit code 1 and empty stdout: "Error: --json-schema is not a valid JSON Schema: data/type must be equal to one of the allowed values, data/type must be array, data/type must match a schema in anyOf" (exit 1, no stdout); "Error: --input-format=stream-json requires output-format=stream-json." (exit 1); "Error: When using --print, --output-format=stream-json requires --verbose" (exit 1); "Error: --include-partial-messages requires --print and --output-format=stream-json." (exit 1); "Error: --forward-subagent-text requires --print and --output-format=stream-json." (exit 1). The "runs no model call" part is confirmed by the empty stdout and by the fact that all five are flag-validation failures detected before the agent loop starts. Note the quote's first error is the JSON-Schema-compilation diagnostic, whereas a non-JSON value gives a different message ("Error: --json-schema is not valid JSON: JSON Parse error: Expected '}'") — the claim quotes one valid instance, not the only one. Also note the doc itself states this for the invalid-schema case only (errors.md:3049, headless.md:169); the invalid-COMBINATION cases are black-box observations, which is what the claim's section label already concedes. Status INFERRED is appropriate and the reasoning is valid.
  **Status after correction:** `INFERRED`

- **`headless.md`** — **Claimed:** Permission denials are a structured, in-band record on the result envelope — a denial is not a run failure. The record contains the tool name, the tool_use id, and the full attempted tool input.
  **Correction:** Every element holds, and the black-box observation is independently corroborated by the doc. DOC: headless.md:338 "With `--output-format stream-json`, denials appear as `permission_denied` system messages, and the final result message lists them in `permission_denials`." The record shape is documented in sdk-ts.md:2056-2066: `type SDKPermissionDenial = { tool_name: string; tool_use_id: string; tool_input: Record<string, unknown>; }` — exactly the three fields the claim names. BLACK-BOX (v2.1.306, `--output-format json`): reproduced `permission_denials: [{"tool_name":"Write","tool_use_id":"call_function_5exno3cds8zc_1","tool_input":{"file_path":"C:\\Users\\Admin\\Desktop\\Claude clone\\agent-reference-shots\\probe_deny.txt","content":"hello\n"}}]` with `subtype: "success"`, `is_error: false`, `terminal_reason: "completed"`, `num_turns: 2` — confirming "a denial is not a run failure" — and the file was confirmed absent on disk, confirming the denial took effect. "In-band" is accurate for the json output format; note the doc scopes the in-band `permission_denials` list specifically to stream-json output, though my json-format probe showed the field is present there too (superset, not contradiction). Status INFERRED is appropriate and the reasoning is valid.
  **Status after correction:** `INFERRED`

- **`agent-loop.md`** — **Claimed:** The SDK's 14 named tools are a category-level summary rather than the literal schema. The locally captured CLI init event lists 27 tools, includes platform/product tools absent from the page (PowerShell, Cron*, DesignSync, Monitor, NotebookEdit, Workflow, Enter/ExitWorktree and others), and contains neither Agent nor AskUserQuestion, using Task instead of TaskCreate/TaskUpdate. Reasoning: the page enumerates categories with a representative per category, while the init event enumerates the actual schema handed to the model for this platform and configuration, so the two lists differ in kind rather than in conflict; the naming differences are most plausibly SDK-facing aliases over a capability that may or may not be present, since the page separately notes TaskCreate/TaskUpdate are provided only on opt-in.
  **Correction:** Every factual assertion checks out against the local capture agent-reference-shots/area1-agent-loop/sanitized-agent-loop.jsonl: the system/init tools array has exactly 27 entries (counted programmatically — note the sibling OBSERVATIONS.md says "28 names", which is wrong; the JSONL is authoritative). It includes Task, Bash, CronCreate, CronDelete, CronList, DesignSync, Edit, EnterWorktree, ExitWorktree, Glob, Grep, ListAgents, Monitor, NotebookEdit, PowerShell, PushNotification, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill, TaskStop, ToolSearch, WebFetch, WebSearch, Workflow, Write — so yes, no Agent, no AskUserQuestion, no TaskCreate/TaskUpdate, and PowerShell/Cron*/DesignSync/Monitor/NotebookEdit/Workflow/Enter-ExitWorktree are all absent from agent-loop.md. The conclusion (summary table vs literal per-platform schema; differ in kind, not in conflict) follows from the evidence and is corroborated by typescript.md documenting 37 distinct tool names. CORRECTION TO THE REASONING: the "most plausibly SDK-facing aliases ... may or may not be present" hedge is under-informed — typescript.md:3089 states outright that the Agent tool's "previous name `Task` is still accepted as an alias, and the `tools` array in the SDKSystemMessage init message currently lists this tool as `Task` for backward compatibility", so the Task-vs-Agent difference is a documented alias, not a missing capability. Only TaskCreate/TaskUpdate absence is explained by the opt-in rule (agent-loop.md:160; todo-tracking.md).
  **Status after correction:** `INFERRED`

- **`auto-mode-config.md`** — **Claimed:** The classifier's request context deliberately EXCLUDES tool output: it reads user messages, non-read-only tool calls, and CLAUDE.md content, but tool results are stripped so hostile content in a file or web page cannot manipulate the classifier directly. A PostToolUse hook can inject a short `classifierContext` note, and that field is explicitly treated as trusted application-supplied content.
  **Correction:** Supplied quote verbatim on the page under review (Repository visibility entry). The richer formulation is verbatim on permission-modes.md: 'the classifier sees user messages, tool calls other than read-only lookups such as file reads and searches, and your CLAUDE.md content. Tool results are stripped from those requests, so hostile content in a file or web page can't manipulate the classifier directly', plus 'You can annotate a call's result with a PostToolUse hook's `classifierContext` field … which the classifier reads as application-provided context' (v2.1.236+). Minor nuance: hooks.md says the classifier reads it 'as information from the application hosting the session' and warns 'don't copy untrusted tool output or third-party text into it' — so it is trusted because the host application supplies it, not because its content is verified.
  **Status after correction:** `OBSERVED-DOC (auto-mode-config.md for the quoted fragment; permission-modes.md + hooks.md for the rest)`

- **`cli-reference.md`** — **Claimed:** The stream-json format emits a `system`/`init` event carrying cwd, session_id, tools, mcp_servers, model and permissionMode, followed by assistant/user/result events.
  **Correction:** The status is INFERRED because the CLI-reference page does not document the stream-json event schema at all — the --output-format row only says 'Specify output format for print mode (options: `text`, `json`, `stream-json`)'. The underlying observation is accurate, however, and the reasoning is sound. Live run: first event is {'type':'system','subtype':'init','cwd':...,'session_id':...,'tools':[27 names],'mcp_servers':[{'name':'rea','status':'pending','source':'user'}],'model':...,'permissionMode':'default'}. The assistant event carried keys type, message, parent_tool_use_id, session_id, uuid, timestamp, request_id, with parent_tool_use_id = null for the top-level turn, then a 'result' event with subtype 'success'. The inference that parent_tool_use_id (null for top-level turns) is the field --forward-subagent-text populates is directly corroborated by the doc's --forward-subagent-text row, which says 'as `assistant` and `user` messages with `parent_tool_use_id` set'. One qualification: the init event actually carries more than the six listed fields (slash_commands, terminal_slash_commands, apiKeySource, claude_code_version, output_style, agents, skills, plugins, capabilities, analytics_disabled, product_feedback_disabled, uuid, memory_paths, original_cwd, additional_directories, messaging_socket_path, fast_mode_state, fast_mode_disabled_reason, per_turn_effort_active, view_mode, powershell_path), so the claim understates rather than overstates.
  **Status after correction:** `INFERRED`

- **`permission-modes.md`** — **Claimed:** The result envelope of a non-interactive run carries a top-level `permission_denials` array recording every denied call with tool_name, tool_use_id, and the complete tool_input that was attempted.
  **Correction:** CORRECTION: the claim is now OBSERVED-DOC for the array, not INFERRED. headless.md line 338 states: 'With `--output-format stream-json`, denials appear as `permission_denied` system messages, and the final result message lists them in `permission_denials`.' Live probe confirms a top-level `permission_denials` array in the --output-format json result object, and each entry has exactly the keys tool_name, tool_use_id, tool_input (e.g. {"tool_name":"Write","tool_use_id":"call_01a15fd6d4ce71cbb073acb5","tool_input":{"file_path":"...\\d4.txt","content":"hello"}}). However, the ENTRY-LEVEL field names (tool_name, tool_use_id, tool_input) are still not named in any Anthropic doc, so that sub-part remains INFERRED from direct observation.
  **Status after correction:** `OBSERVED-DOC`

- **`permission-modes.md`** — **Claimed:** Whether plan mode's write block is sound in general is UNKNOWN. In a probe the model was denied the Write tool and then wrote the same file via the Bash tool, and the file existed afterwards.
  **Correction:** Reproduced independently on this host. Probe A (forced Write only): plan mode denied Write with permission_denials[0] = {"tool_name":"Write",...,"file_path":"...\\pm4.txt"}; FILE_EXISTS=False. Probe B (Write then Bash fallback): denials len 1 for Write, the model's own report said 'Write tool: rejected - Cannot write to ... while in plan mode' and 'Bash fallback: succeeded - echo hello > pm2.txt', and pm2.txt existed with 6 bytes. The claim's two candidate explanations (enforcement gap vs. model routing around the denial) remain genuinely indistinguishable with this evidence, and no doc statement covers a Bash-based write during planning. UNKNOWN status is correct.
  **Status after correction:** `UNKNOWN`

- **`permission-modes.md`** — **Claimed:** On this Windows host, a bare deny rule on one shell tool removes BOTH shell tools from the model's tool list, indicating the tool list is assembled from shared capability groups rather than a flat per-tool list.
  **Correction:** Reproduced independently. Probe with {"permissions":{"deny":["Bash"]}} produced a 25-entry tools array with Bash absent AND PowerShell absent, although only "Bash" was named; the no-deny baseline had 27 entries with both present. The observation is solid. The inference (shared capability groups such as shell_execution) is a reasonable but unverified hypothesis; no doc describes how the tool list is assembled, and the behavior may be Windows-specific. INFERRED status with reasoning is appropriate — the evidence supports it but does not establish the mechanism.
  **Status after correction:** `INFERRED`

- **`context-window.md`** — **Claimed:** Deriving from 20 controlled runs of the published CLI's `--debug` output, the auto-compact effective window is the context window minus a reserve of min(maxOutputTokens, 20000): the reserve equals the output allowance up to 20,000 tokens and is clamped at exactly 20,000 above that, and the 20,000 figure is a constant across every window size tested (100k, 120k, 400k, 1M).
  **Correction:** INDEPENDENTLY REPRODUCED in full on this host (Claude Code 2.1.306, Windows 11, unrecognized gateway model minimax/minimax-m3.1-flash:free). Debug line: 'autocompact: tokens=[REDACTED] level=ok effectiveWindow=N'. Results matched the claim exactly: default 200k -> 180000; CLAUDE_CODE_MAX_CONTEXT_TOKENS=100000 -> 80000, 120000 -> 100000, 400000 -> 380000, 1000000 -> 980000; CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000 -> 130000; --autocompact 100k -> 80000, 500k -> 180000 (capped at the assumed 200k window). For the output-token dimension the correct env var is CLAUDE_CODE_MAX_OUTPUT_TOKENS (NOT MAX_OUTPUT_TOKENS — the latter is a no-op and yields a flat 180000 at every value, which is why the claim's measurements only make sense under the correct name): 4000 -> 196000, 8000 -> 192000, 12000 -> 188000, 16000 -> 184000, 19000 -> 181000, 20000 -> 180000, 25000 -> 180000, 64000 -> 180000, 128000 -> 180000. This is precisely effectiveWindow = contextWindow - min(maxOutputTokens, 20000), and the 20,000 reserve is confirmed constant across 100k/120k/400k/1M windows. One methodological correction to the claim's framing: the claim says 'the reserve equals the output allowance up to 20,000' — that is what the data shows. The reasoning validity is sound: 9 independent window-size points and 8 independent output-cap points all fit the single rule with no exceptions, and CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50 left effectiveWindow at 180000 (confirming the reserve is unaffected by the trigger percentage). Caveat: this characterises Claude Code's local accounting against an ASSUMED 200k window for an unrecognized model ID, not first-party Anthropic-hosted behaviour; that is a scope limitation on the inference, not an error in it.
  **Status after correction:** `INFERRED`

- **`context-window.md`** — **Claimed:** Over-limit state is reported with two deliberately distinct messages depending on whether the limit exceeded is the model's context window (fatal until space is freed) or the compaction window (recoverable, since requests past it can still succeed).
  **Correction:** Verified on https://code.claude.com/docs/en/errors.md lines 2220-2231. Message 1: '`/context` shows this warning at the top of its output when the conversation has grown past the model's context window. Requests fail with [`Prompt is too long`](#prompt-is-too-long) until you free space. An interactive session shows that error as the `Context limit reached` line.' with the literal text 'Context exceeds the 200k-token limit by 94k tokens — run /compact or /clear to continue.' Message 2: 'When the limit you exceeded is a compaction window, such as the 200K boundary on 1M-context models, the warning reads differently. A compaction window can sit below the model's context window, so requests past it can still succeed.' with 'Context is 94k tokens past the 200k-token compaction window — run /compact to reduce usage.' The claim's 'fatal until space is freed' and 'recoverable' characterisations track the doc's own contrast (requests fail vs. requests can still succeed). Additional detail the claim omits but which does not contradict it: the page notes both forms name /clear instead of /compact when DISABLE_COMPACT is set.
  **Status after correction:** `OBSERVED-DOC`

- **`model-config.md`** — **Claimed:** A blocked selection produces EIGHT distinct reactions depending on WHERE the model was set: `/model` rejects the switch; `--model`/`ANTHROPIC_MODEL`/`model` setting are replaced at startup with a warning naming both requested and substituted models; `ANTHROPIC_DEFAULT_MODEL` is ignored; a subagent/teammate override falls back to another model rather than failing; a skill/command override is ignored and runs on the session model; `advisorModel` disables the advisor; the `--advisor` flag exits at launch; `CLAUDE_CODE_AUTO_MODE_MODEL` is ignored. Separately, a blocked FAMILY ALIAS is SUBSTITUTED with the newest permitted version of that family rather than rejected.
  **Correction:** Lines 246-259 list exactly eight bullets matching the eight named sources in the claim, in the claim's order. Lines 242-244 confirm family-alias substitution with the newest permitted version and the `["sonnet", "claude-opus-4-6"]` example. Runtime re-probe confirmed the two quoted runtime facts: with {"availableModels":["sonnet"],"enforceAvailableModels":true} and `--model minimax/minimax-m3.1-flash:free`, the session dispatched to `model=claude-sonnet-5-5` and the log emitted '[DEBUG] Fast mode unavailable: Opus 5.5 is not in your organization's allowed models' (probe/al.log). One nuance: the doc's family-alias substitution paragraph is scoped to 'the Anthropic API and Claude Platform on AWS' (line 242), which the claim does not state but also does not contradict.
  **Status after correction:** `OBSERVED-DOC`

- **`model-config.md`** — **Claimed:** For an unrecognised model ID the product warns, assumes a 200K context window, emits a structured diagnostic code, and only then fails at the provider. Four mechanisms correct the window: update the client; add a `modelOverrides` entry (or a `modelPicker` row with `behavesAs`); append `[1m]`; or set `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. The env var's applicability depends on ID shape: it applies directly to an unresolvable provider/custom spelling without `[1m]`; it does NOT apply to the same spelling WITH `[1m]` unless `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` is also set; and it applies to a known model or bare `claude-` name only alongside `DISABLE_COMPACT`. An ID is provider/custom-shaped when it does not start with `claude-` in any casing, or carries a strippable suffix such as the `@YYYYMMDD` date used on Google Cloud's Agent Platform.
  **Correction:** Lines 823-828 give the two startup warnings and the 200K assumption; lines 832-835 give the four correction mechanisms including the modelPicker/behavesAs alternative; line 1019 confirms the diagnostic code `[claude-code:unrecognized_model]`. Line 843 confirms the provider/custom-spelling rule verbatim including the '@YYYYMMDD' suffix. Lines 847-851 give the three applicability cases exactly as the claim states. Runtime re-probe reproduced the quoted output verbatim: the 200K warning text, '[claude-code:unrecognized_model] {"model":"my-gateway-opus","query_source":"sdk"}', and 'API Error: 400 my-gateway-opus is not a valid model ID' - confirming warning, diagnostic code, then provider failure in that order.
  **Status after correction:** `OBSERVED-DOC`

- **`model-config.md`** — **Claimed:** The exact wire-level request parameter used to carry an effort level to the provider is NOT established by the available evidence. The page states only that the effort level is unchanged for a `ultrathink` turn and that a `CLAUDE_CODE_AUTO_COMPACT_WINDOW` value is read per variable; the CLI's own debug output on this host exposes the selected model identifier but no request body or `anthropic-beta` header containing an effort value, and no `api-request*` capture was written to the debug directory.
  **Correction:** The UNKNOWN status is correct and correctly scoped. The page contains no wire-level effort parameter name: grep for 'output_config', 'anthropic-beta', 'maxTokens', 'max_tokens', 'thinkingBudget', 'request parameter', 'effort parameter' returned zero hits in the raw source. The only effort-related API statements are line 677 ('The effort level sent to the API is unchanged') and line 707 ('the effort level is the primary control for how much thinking happens'). I independently re-ran the described checks on this host: `claude -p --effort low --model opus --debug api --debug-file <f>` produced a log with zero occurrences of effort, effortLevel, maxTokens, anthropic-beta, betas, thinkingBudget, or output_config, and a filesystem-wide search for 'api-request*' returned no files. The claim's stated scope (this page, this host's debug output) is accurate, and it correctly avoids claiming knowledge of the wire contract.
  **Status after correction:** `UNKNOWN`

- **`model-config.md`** — **Claimed:** The exact user-facing wording of the substitution notice shown when a blocked `--model`/`ANTHROPIC_MODEL`/`model` setting is replaced at startup is NOT established by the available evidence. The page states such a warning exists and that it names both the requested and substituted models, but the notice text was not captured on this host, and the two related messages that WERE observed are different in kind: the fast-mode refusal ("is not in your organization's allowed models", observed verbatim) and the org-restriction notice (documented, not observed).
  **Correction:** The UNKNOWN status is correct and correctly scoped to the model-config page. The page states the notice exists and names both models (lines 242, 249, 398) but quotes no literal wording for the allowlist-substitution case - grep for a quoted replacement warning returned no matches in the raw source. I reproduced the described host evidence: with {"availableModels":["sonnet"],"enforceAvailableModels":true} the session dispatched to model=claude-sonnet-5-5 and the only user-facing string was '[DEBUG] Fast mode unavailable: Opus 5.5 is not in your organization's allowed models'; a grep of the full debug log for 'substitut', 'restrict', 'not available', 'replaced' and 'availableModels' returned zero matches. The claim's caveat that the org-restriction notice is 'documented, not observed' is accurate for this host. Note for the record (not a defect in the claim, which is scoped to this page): the sibling errors page https://code.claude.com/docs/en/errors.md does quote a startup substitution notice - 'Model "claude-opus-4-8" is restricted by your organization's settings. Using claude-sonnet-4-6 instead.' - and the managed-exclusion variant 'Model '<name>' is not available. Your organization restricts model selection.'. That is a different page and a different (org/managed-exclusion) trigger than the allowlist-substitution notice this claim asks about, so the page-scoped UNKNOWN stands, but an implementer should consult errors.md for candidate wording.
  **Status after correction:** `UNKNOWN`

---

## 9.3 What this round changes in the downstream documents

| # | Finding | Document affected | Required change |
| :- | :- | :- | :- |
| D14 | Built-in subagent types are **six** (Explore, Plan, general-purpose, claude, statusline-setup, claude-code-guide), not five | `feature-checklist.md` S10, `architecture.md` §11 | Correct the count wherever it appears; record that built-in agents are registered in **interactive sessions only** and are removed entirely by `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`. |
| D07 | `PreToolUse` is **not** the only event that can rewrite tool arguments — `PermissionRequest` also carries `updatedInput` | `architecture.md` §7, `interface-spec.md` §7, `test-plan.md` | The hook interface must support argument rewriting on **two** events, not one. Add a test for `PermissionRequest.updatedInput`. |
| D05 | The 33 hook events are correct, but **11 of them have no decision-control subsection** and the decision table assigns `None` to 9 | `interface-spec.md` §7, `test-plan.md` | The hook interface must model decision-control as **optional per event**, not mandatory. A hook that cannot decide is a distinct case, not a default. |
| D06 | Exit code **1 with valid JSON still decides** — the exit code is ignored and the JSON fields alone decide | `architecture.md` §7, `test-plan.md`, `interface-spec.md` §7 | Our hook runner must implement the documented rule: **exit 0 = proceed, exit 2 = block, any other exit = consult the JSON**; exit 1 with valid JSON is not automatically a failure. |
| D01 | The managed-settings exceptions table has **eleven** keyed rows, not twelve | `architecture.md` §2, `feature-checklist.md` S6 | Correct the count. The `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST` paragraph is an app-level exception, not a twelfth row. |
| D22 | HTTP-hook secret interpolation is a **two-list intersection** (the hook's own `allowedEnvVars` AND the outer `httpHookAllowedEnvVars`) | `security-plan.md`, `architecture.md` §7 | Implement the intersection. A hook that widens its own allowlist is not the policy. |
| D44 | Each safety check has its **own** named kill-switch env var, and the kill-switch property does **not** generalise across all seven | `security-plan.md` (Tier-2 design) | Our Tier-2 module is **not** configurable at all, so this is a compatibility note only. Record that we deliberately do not implement the reference's per-check switches. |
| D29 | Grep and Glob declare truncation via **different** fields (`totalFiles`/`totalLines` vs `totalMatches`/`countIsComplete`) | `interface-spec.md` §4, `feature-checklist.md` S3 | Our tool-result envelope needs a **single unified truncation contract** rather than per-tool fields. This is a deliberate divergence and belongs in the compatibility matrix. |
| D30 | The sandbox's filesystem and network layers are **independent**, and only the filesystem layer has a documented disable switch | `security-plan.md`, `architecture.md` §7 | Model the two layers separately. On Windows, neither is available — record that gap explicitly rather than reporting a partial sandbox as a sandbox. |
| D27 | `claude agents --json` elements are **not** a fixed 7-key record; the key set is variable (`state`, `waitingFor`, `id` appear conditionally) | `interface-spec.md` §9 | Our session-listing interface must be a discriminated union, not a fixed struct, if we want the same robustness. |
| D18 | The SDK's partial-message wrapper has **nine** fields, not ten | `interface-spec.md` §15 | Correct the count if the number is quoted; the field list itself is not copied. |
| D16 | A skill deny rule naming an **alias** also blocks the skill behind that alias; matching under all names requires the `Skill(skill:<name>)` parameter form | `security-plan.md` (skill trust), `feature-checklist.md` S9 | Our permission matcher must resolve **all** of a skill's names — technical, alias and display — when matching. A deny that can be evaded via an alias is not a deny. |
| D33 | The tools-reference page publishes **no** input/output JSON schemas, and 13 of the 46 tools have no SDK type at all | `interface-spec.md` §4, `architecture.md` §6 | This *strengthens* the clean-room position: the wire contracts are the vendor's, and ours are our own. Record it in `licensing-and-provenance-review.md` as a positive finding. |
| D31 | The `--output-format json` envelope's field set is **not documented as stable**, and the `terminal_reason` enum lives in the Agent SDK reference, not on the headless page | `interface-spec.md` §17, `benchmark-and-evaluation-plan.md` | Our published envelope must carry an explicit stability marker, because the reference's does not. This is a place where we can be **better** than the reference. |
| D34 | The effective tool set is **per session** and published in `system`/`init`; the 46-name table is neither a pure union nor a pure intersection | `feature-checklist.md` S15, `architecture.md` §6 | Treat the tool table as a **capability catalogue**, and the `init` manifest as the authoritative per-session set. Our `doctor` command should print the difference. |
| D43 | `claude install` and `claude update` have **different** grammars — only `install` takes a version argument | `interface-spec.md` §16 | Correct the CLI surface description. Low impact, but it is a documented discrepancy. |

---

## 9.4 The two findings that change what we must build

These are not corrections to a *number*. They are corrections to a *model of how permission enforcement works*, and they are the reason the round was worth running.

### 9.4.1 A deny rule is a filter, not a boundary — so the real boundary must be at the operation

**The observation (C014, INFERRED).** A bare tool-name deny removes that tool from the model's tool list. The live probe found that a model retaining any other shell-executing tool could still reach the same capability. The verifier's inference — and ours — is that the bare-name deny is a **registry-level filter** rather than a hard capability boundary.

**Why this matters more than it looks.** A registry filter protects the *model* from choosing a tool. It does not protect the *system* from an operation. Those are different threat models:

| | Registry filter | Operation-level boundary |
| :- | :- | :- |
| Protects against | the model picking the denied tool | the operation happening at all |
| Survives a mis-selected tool | no | yes |
| Survives a different tool with the same effect | **no** | yes |
| Survives a hook, plugin or subagent issuing the call | **no** | yes |
| Detectable by | inspecting the tool list | inspecting the operation |

**Our design consequence.** Our permission engine has **two** layers, and they are not the same layer:

1. **The tool-visibility layer** (what the model is shown) — for steering, not for security. It is a UX and cost optimisation.
2. **The operation-authorisation layer** (what is permitted) — the security boundary. It evaluates the *operation* — the resolved path, the parsed command, the target host — regardless of which tool requested it.

This is already how `security-plan.md` and `architecture.md` §7 are written (Tier 1 rule engine, then the Tier-2 envelope), and the round-3 finding is the independent confirmation that the distinction is necessary rather than theoretical. The plan needs no redesign; it needs the *finding* recorded, and a test that proves the two layers are not the same thing.

**The test to write.** For every capability with more than one route to it — filesystem write via `Write`, via `Edit`, via `Bash`, via a plugin, via a subagent, via an MCP server — assert that denying one route denies the *capability*. The security plan's attack matrix has no row for this today; it should.

### 9.4.2 Plan mode's write block was bypassed through the shell — and we must not inherit that

**The observation (C054, UNKNOWN for the reference).** In a live probe, the model was denied the `Write` tool under plan mode, and then wrote the same file via `Bash`. Two explanations fit the evidence equally well:

- **(a) An enforcement gap** — plan mode blocks the `Write` tool but not a shell command that writes. The mode is a tool filter, not a write barrier.
- **(b) The model routed around the denial** — plan mode correctly blocked `Write`; the model simply chose a different tool, which plan mode does not (and arguably should not) prevent.

**The two are indistinguishable from a single probe, and no documentation statement covers a Bash-based write during planning.** So the honest status is UNKNOWN, and it stays UNKNOWN in this document. What is *not* unknown is that **a product in which this is possible is a product where plan mode does not reliably mean 'no writes'** — and users will read plan mode exactly that way.

**Our design consequence.** Plan mode must be defined as an **operation-level constraint**, not a tool-availability setting:

- Plan mode denies any operation whose *effect* is a filesystem mutation, regardless of the tool that requested it.
- A shell command that writes is a write. A `Write` tool call is a write. A plugin that writes is a write. A subagent that writes is a write.
- The denial message must say **which operation was blocked and why**, so that a user (and a model) can tell a policy refusal from a bug.
- The allowed set must be enumerated as *operations*, not *tools*, and the tool list in plan mode is then a consequence of the operation set, not an independent filter.

This is the sharpest instance of the project's standing rule (**X1**): the prompt can ask the model not to write, but only the harness can *prevent* the write. A plan mode that filters a tool list is a request; a plan mode that filters operations is a guarantee.

**The honest caveat.** We do not know that the reference product has this weakness. We know that a single probe of the reference produced a result consistent with it, and that the two explanations cannot be separated. Our design takes the stronger option because the stronger option is the one that makes the guarantee true — not because we have evidence that the reference lacks it.

---

## 9.5 Open questions this round raised

| # | Question | Status |
| :- | :- | :- |
| ★1 | Is plan mode's write block an enforcement gap or a model routing artefact? | UNKNOWN — needs a probe that varies the tool surface, e.g. denying the shell tool too |
| ★2 | Why does a bare deny on one shell tool remove **both** shell tools from the tool list? | INFERRED — shared capability groups; the mechanism is undocumented |
| ★3 | What is the ordering of multiple hooks' outputs for the same event? | UNKNOWN — the page specifies decision precedence but not output ordering |
| ★4 | What is the per-event presence matrix for the optional common hook input fields (`scratchpad_dir`, `agent_id`, `agent_type`, `effort`)? | UNKNOWN — the page uses a non-exhaustive 'such as' list |
| ★5 | What are the complete `mcp_server.source` values and their trust semantics? | UNKNOWN — the page gives a partial set and defers to the SDK reference |
| ★6 | Is the `system` channel's type/subtype vocabulary complete, and how does `terminal_reason` map to `subtype`? | UNKNOWN — a live probe showed `terminal_reason: "api_error"` with `subtype: "success"`, so the mapping is not a function of `terminal_reason` |
| ★7 | Is the Windows sandbox backend present-but-gated, or absent? | UNKNOWN — some feature gate is off; the mechanism (server flag, build flag, account tier) is not documented |
| ★8 | What exactly does `claude plugin validate --json` return? | OBSERVED — the envelope was observed live, but the documented field list does **not** include `advice` or `directory`, so the two disagree |

---

## 9.6 Method note

- **47 agents**, each assigned one documentation page, instructed to verify every claim our evidence base attributes to that page against the page itself. Three agents died on shared-gateway credit exhaustion; their pages were re-run.
- **Claims examined:** 1 203. **Confirmed:** 1 094. **Corrected:** 65. **Refuted:** 44.
- Every refutation records the page, the corrected status tag, and the reason.
- The round used **only public documentation and the published CLI's own user-facing surfaces**. No decompilation, no binary inspection, no modification. The compliance boundary in `agent-evidence.md` §2 and `TERMS-NOTES.md` remains in force and was not relaxed.
- No billable API call, no cloud resource, no training, no application source code.
- The raw workflow journal is preserved at `subagents/workflows/wf_4ecd1b7f-777/journal.jsonl`; the machine-readable extraction is `_wf2-corrections.json`.

---

*Prepared 2026-10-21. The primary evidence document `agent-evidence.md` is retained unchanged; this document records the corrections layer on top of it. Every quoted string in this document was mechanically re-verified against its raw source.*

---

*Round 3 added 2026-10-21. The two findings that change what we build are §9.4.1 (a deny rule is a filter, not a boundary) and §9.4.2 (plan mode must be an operation-level constraint). Both are design requirements, not observations of the reference's internals.*
