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
