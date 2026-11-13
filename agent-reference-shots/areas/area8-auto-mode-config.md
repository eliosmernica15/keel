# Area 8b — Auto mode configuration (`autoMode` settings block)

**Primary source page:** https://code.claude.com/docs/en/auto-mode-config.md
**Supplementary sources:** https://code.claude.com/docs/en/permission-modes.md,
https://code.claude.com/docs/en/settings-reference.md,
https://code.claude.com/docs/en/sandboxing.md,
https://code.claude.com/docs/en/env-vars.md,
https://code.claude.com/docs/en/hooks.md,
https://code.claude.com/docs/en/errors.md,
https://code.claude.com/docs/en/commands.md,
https://code.claude.com/docs/en/server-managed-settings.md
**Product:** Claude Code 2.1.306 (native Windows build)
**Date:** 2026-10-21
**Method:** public documentation + black-box observation of the published CLI's own
`claude auto-mode` subcommands. No decompilation, no source extraction, no credential
reads. See `../../TERMS-NOTES.md`.
**Raw captures:** `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-auto-mode\`

> **Machine caveat.** This host runs Claude Code against a **custom
> `ANTHROPIC_BASE_URL`** (a third-party gateway serving a non-Anthropic model), not
> `api.anthropic.com`. Subscription- and model-gated behaviour is marked OBSERVED-DOC
> unless directly observed. The `autoMode` **configuration surface** is fully local and
> was fully observable here; the **classifier model** was not.

---

## 1. Executive summary (one page)

Claude Code's "auto mode" replaces the human in the permission-approval loop with a
**separate classifier model**. The page under investigation,
`/docs/en/auto-mode-config.md`, is the **configuration reference** for that classifier —
not a description of auto mode itself (that lives on
`/docs/en/permission-modes#eliminate-prompts-with-auto-mode`).

Five things define the whole design:

1. **Two independent decision layers.** The declarative permission system
   (`permissions.allow` / `.ask` / `.deny`) runs *first* and is local. The classifier
   is a *second* gate that only sees what the first layer did not already resolve.
   Deny rules and explicit ask rules are evaluated **before** the classifier and
   cannot be overridden by it. This ordering is the single most important fact for a
   reimplementation: the classifier is an **advisory second opinion**, not the
   authority.

2. **The classifier's rules are prose, not patterns.** `autoMode.environment`,
   `autoMode.allow`, `autoMode.soft_deny`, and `autoMode.hard_deny` are arrays of
   **natural-language strings**, read by a model as instructions. They are not regexes,
   not tool globs, not structured predicates. The idiomatic implementation is
   therefore "render the rules into the classifier's prompt", not "write a matcher".

3. **Four-tier precedence inside the classifier.** `hard_deny` (unconditional) >
   `soft_deny` (cleared by explicit user intent) > `allow` (exceptions to
   `soft_deny`) > general user intent. "General requests don't count as explicit
   intent" — asking Claude to "clean up the repo" does **not** authorise a force-push;
   asking it to "force-push this branch" does. This is the mechanism that makes the
   layer usable rather than merely annoying.

4. **`"$defaults"` is a splice token, not a boolean.** Including the literal string
   `"$defaults"` in an array splices the built-in entries in *at that position*, so
   custom entries can go before or after them and future built-in updates still
   arrive. Omitting it **replaces the entire list** for that section. Each of the four
   sections is evaluated independently. This is a clean, easily-misread contract, and
   it was verified on the CLI.

5. **The `autoMode` block is deliberately *not* readable from project scope.** It is
   read from `~/.claude/settings.json`, managed settings, and `--settings`/SDK inline
   JSON — but **not** from `.claude/settings.json` or `.claude/settings.local.json`,
   because those live in the repo and a checked-in repo could otherwise inject its own
   allow rules. Verified on the CLI: a project-scope `autoMode` block was ignored.

The scope combination is **additive, not a hard policy boundary**: a developer-level
`allow` entry can override an organisation-level `soft_deny` entry, because allow
rules act as exceptions to soft blocks *inside* the classifier. The page says this
outright and then points you at `permissions.deny` in managed settings for a real
boundary. That admission is architecturally significant and worth copying in spirit.

**The reimplementation takeaway:** the observable contract is
`(scope, section) -> ordered list of prose rules -> classifier prompt`, plus a
precedence algebra over `{hard_deny, soft_deny, allow, explicit-intent}` and a
"deny/ask wins, classifier second" ordering against the declarative layer. A clean-room
build can implement this with any rule-subsetting model of its choosing.

---

## 2. Detailed findings

### 2.1 The four `autoMode` sections and their semantics (OBSERVED-DOC)

Section: **Override the block and allow rules**

> Three additional fields let you replace the classifier's built-in rule lists:
>
> * `autoMode.hard_deny`: unconditional security boundaries
> * `autoMode.soft_deny`: destructive actions that user intent can clear
> * `autoMode.allow`: exceptions to soft block rules
>
> Each is an array of prose descriptions, read as natural-language rules. For
> tool-pattern-based hard blocks that run before the classifier, use
> [`permissions.deny`](/docs/en/permissions).

**Reimplementation need:** yes — the section names, their types, and the four-tier
precedence are the entire public contract. Section names are load-bearing
(`soft_deny` vs `hard_deny` are not interchangeable).

### 2.2 The four-tier precedence algebra (OBSERVED-DOC)

Section: **Override the block and allow rules**

> Inside the classifier, precedence works in four tiers:
>
> * `hard_deny` rules block unconditionally. User intent and `allow` exceptions don't apply.
> * `soft_deny` rules block next. User intent and `allow` exceptions can override these.
> * `allow` rules then override matching `soft_deny` rules as exceptions.
> * Explicit user intent overrides the remaining soft blocks: if the user's message
>   directly and specifically describes the exact action Claude is about to take, the
>   classifier allows it even when a `soft_deny` rule matches.
>
> General requests don't count as explicit intent. Asking Claude to "clean up the repo"
> doesn't authorize force-pushing, but asking Claude to "force-push this branch" does.

**Reimplementation need:** yes, and it is the hardest part. A clean-room build needs a
precise operationalisation of "directly and specifically describes the exact action".
The natural implementation is to give the classifier a labelled taxonomy
(`HARD_DENY` / `SOFT_DENY` / `ALLOW` / `EXPLICIT_INTENT`) and require it to emit a
verdict plus a matched-rule label, exactly as Anthropic's own rules are labelled
(observed: `Git Destructive`, `Data Exfiltration`, `Self-Modification`, …).

### 2.3 `"$defaults"` splice semantics (OBSERVED-DOC + OBSERVED-CLI)

Section: **Define trusted infrastructure** and **Override the block and allow rules**

> To add your own entries alongside the defaults, include the literal string
> `"$defaults"` in the array. The default entries are spliced in at that position, so
> your custom entries can go before or after them.

> [!CAUTION]
>
> Setting any of `environment`, `allow`, `soft_deny`, or `hard_deny` without
> `"$defaults"` replaces the entire default list for that section. If you set an
> array without `"$defaults"`, you discard the built-in rules for that section:
>
> * `soft_deny`: every built-in soft block rule, including force push, `curl | bash`,
>   production deploys, and auto-mode bypass
> * `hard_deny`: the built-in data exfiltration rule
>
> Each section is evaluated independently, so setting `environment` alone leaves the
> default `allow`, `soft_deny`, and `hard_deny` lists intact.

**OBSERVED-CLI (Claude Code 2.1.306)** — verified all three behaviours:

| Probe | Result |
| :- | :- |
| `--settings {"autoMode":{"environment":["$defaults","CUSTOM"],"soft_deny":["Never run terraform apply"]}}` | `environment` = 22 (21 defaults + 1 custom); `soft_deny` = **1** (the 72 built-ins were discarded) |
| `--settings {"autoMode":{"environment":["FIRST","$defaults","SECOND"]}}` | 23 entries: `[0]`=FIRST, `[1..21]`=defaults, `[22]`=SECOND — the token is replaced **in place** |
| `claude --settings override.json auto-mode defaults` | byte-identical to plain `claude auto-mode defaults` (72 `soft_deny` both) — `defaults` is scope-independent |

### 2.4 Which scopes are read — and which are deliberately excluded (OBSERVED-DOC + OBSERVED-CLI)

Section: **Where the classifier reads configuration**

> The classifier reads `autoMode` from the following scopes:
>
> | Scope | File | Use for |
> | :- | :- | :- |
> | One developer | `~/.claude/settings.json` | Personal trusted infrastructure |
> | Organization-wide | [Managed settings](/docs/en/server-managed-settings) | Trusted infrastructure distributed to all developers |
> | `--settings` flag or Agent SDK | Inline JSON | Per-invocation overrides for automation
>
> The classifier doesn't read `autoMode` from project settings in `.claude/settings.json`
> or `.claude/settings.local.json`. Both files live in the repo directory, so a
> checked-in repo or a build step could otherwise inject its own allow rules. Move any
> `autoMode` block in `.claude/settings.local.json` to `~/.claude/settings.json`.

**OBSERVED-CLI** — confirmed both halves:

- Project scope (`.claude/settings.json` with `autoMode.allow = ["PROJECT_SCOPE_ALLOW_RULE"]`)
  → effective `allow` = 17 (the defaults); the custom entry was **absent**.
- User scope (throwaway `$HOME/.claude/settings.json` with `autoMode.allow =
  ["USER_SCOPE_ALLOW_RULE"]`) → effective `allow` = 1 (defaults replaced) and the
  custom entry was **present**.

**Reimplementation need:** yes. The trust-boundary reasoning (repo-resident config is
attacker-reachable) is the whole point; a clean-room build should keep the same
scope list.

### 2.5 Scope combination is additive, not a policy boundary (OBSERVED-DOC + OBSERVED-CLI)

Section: **Where the classifier reads configuration**

> Entries from each scope are combined. A developer can extend `environment`, `allow`,
> `soft_deny`, and `hard_deny` with personal entries but can't remove entries that
> managed settings provide. Because allow rules act as exceptions to soft block rules
> inside the classifier, a developer-added `allow` entry can override an organization
> `soft_deny` entry: the combination is additive, not a hard policy boundary.

> [!NOTE]
>
> The classifier is a second gate that runs after the [permissions system](/docs/en/permissions).
> For actions that must never run regardless of user intent or classifier
> configuration, use `permissions.deny` in managed settings, which blocks the action
> before the classifier is consulted and can't be overridden.

**OBSERVED-CLI** — user scope + `--settings` scope, each with `"$defaults"`:
`soft_deny` resolved to **74** entries (72 defaults + USER_SCOPE_RULE +
SETTINGS_FLAG_RULE), with the `--settings` entry last. Order: user scope, then the
`--settings`/inline scope. Managed-settings order was not observable here (no managed
settings file present on this host).

**Reimplementation need:** yes, including the *admission* that this is not a hard
boundary. A clean-room implementation should either reproduce the same weakness
faithfully or deliberately close it — but it must tell the user which it is doing.

### 2.6 `autoMode.environment` — 21 slots in three kinds (OBSERVED-DOC + OBSERVED-CLI)

Section: **Define trusted infrastructure**

The page describes three kinds of entry, printed by `claude auto-mode defaults`:

- **Context slots** (12): Organization, Primary use of Claude Code, Cloud provider(s),
  Repository visibility, Internal sharing / snippet hosting, Org-specific CLIs,
  Secrets management, CI/CD deploy targets, Network posture, Host containment,
  Protected deployment namespaces / environments, Data retention / declassification.
  "Each defaults to `None configured` or to the conservative assumption named next to
  it".
- **Trust slots** (6): Trusted repo, Source control, Trusted internal domains, Trusted
  cloud buckets, Key internal services, Internal package registry. "The repo and
  source-control entries default to the working repository and its configured remotes.
  Every other trust slot defaults to `None configured`".
- **Sensitivity slots** (3): Sensitive data locations & audiences, Sensitive remote
  targets, Protected IaC scopes. "Each defaults to a broad heuristic, such as treating
  any host or namespace whose name carries `prod` or `production` as a sensitive remote
  target, so the protective rules are active before you configure anything."

**OBSERVED-CLI** — `claude auto-mode defaults` returned exactly **21** `environment`
entries with these labels (verbatim): `**Organization**`, `**Primary use of Claude
Code**`, `**Cloud provider(s)**`, `**Repository visibility**`, `**Internal sharing /
snippet hosting**`, `**Org-specific CLIs**`, `**Secrets management**`, `**CI/CD deploy
targets**`, `**Network posture**`, `**Host containment**`, `**Protected deployment
namespaces / environments**`, `**Data retention / declassification**`, `**Trusted
repo**`, `**Source control**`, `**Trusted internal domains**`, `**Trusted cloud
buckets**`, `**Key internal services**`, `**Internal package registry**`, `**Sensitive
data locations & audiences**`, `**Sensitive remote targets**`, `**Protected IaC scopes**`.

Representative defaults observed verbatim:

> **Trusted repo**: The git repository the agent started in (its working directory) and
> its configured remote(s). …

> **Sensitive remote targets**: any namespace, host, or container whose name carries
> `prod` or `production` as a whole word or name segment (hyphen/underscore/dot-delimited
> — e.g. matches `prod-db`, not `producer`)

> **Host containment**: None configured — assume Claude Code runs on an ordinary
> developer machine or CI runner with open internet; …

**Reimplementation need:** yes. The slot taxonomy is the user-facing API for
"describe your infrastructure". A clean-room build should offer the same slot
vocabulary because it is what makes prose rules unambiguous.

### 2.7 Entries are prose, not patterns (OBSERVED-DOC)

Section: **Define trusted infrastructure**

> Entries are prose, not regex or tool patterns. The classifier reads them as
> natural-language rules. Write them the way you would describe your infrastructure to
> a new engineer.

**Reimplementation need:** yes — this determines the entire storage format. A clean-room
build should store strings, not compiled matchers.

### 2.8 The classifier also reads `CLAUDE.md` (OBSERVED-DOC)

Section: **Where the classifier reads configuration**

> The classifier reads the same [CLAUDE.md](/docs/en/memory) content Claude itself loads,
> so an instruction like "never force push" in your project's CLAUDE.md steers both
> Claude and the classifier at the same time.

Note the implication: `CLAUDE.md` is a *lower-trust* input surface than `autoMode`
(it is repo-resident), and it is a **block** signal, not an allow signal. A reimplementation
should keep the "instructions in CLAUDE.md are honoured as constraints" behaviour but
must not let repo-resident text *widen* permissions.

### 2.9 `autoMode.classifyAllShell` (OBSERVED-DOC)

Section: **Route all shell commands through the classifier**

> By default, narrow Bash and PowerShell allow rules such as `Bash(npm test)` stay in
> effect in auto mode. Claude Code resolves them before the classifier runs, unless the
> command carries [per-command allowed domains]. Claude Code suspends only the broad
> rules that grant arbitrary code execution, such as `Bash(*)` or wildcarded
> interpreters, together with every rule that names [`Monitor`], because Monitor
> commands run through the shell. This means a narrow rule can still let a destructive
> argument through without the classifier seeing it, for example a script path or flag
> the rule's prefix didn't anticipate.
>
> Set `autoMode.classifyAllShell` to `true` to suspend every Bash and PowerShell allow
> rule while auto mode is active, so the classifier evaluates every shell command
> regardless of your allow list, except [critical-path removals].
>
> This trades latency for coverage: a command that an allow rule would have approved
> instantly now waits for a classifier decision, and each shell command counts as a
> classifier call.

`settings-reference.md` adds the scope and default: **Scope** `User or managed`;
**Type** Boolean; **Default** `false`; **Requires Claude Code v2.1.193 or later.**

**Reimplementation need:** yes, including the "suspend only the *dangerous* allow
rules, keep narrow ones" heuristic, because it is the performance/coverage knob.

### 2.10 The `auto-mode` CLI subcommands (OBSERVED-DOC + OBSERVED-CLI)

Section: **Inspect the defaults and your effective config**

| Command | Purpose (doc) | Observed behaviour |
| :- | :- | :- |
| `claude auto-mode defaults` | "Print the built-in `environment`, `allow`, `soft_deny`, and `hard_deny` rules as JSON" | Returns one JSON object with those four keys; `allow`=17, `soft_deny`=72, `hard_deny`=1, `environment`=21 entries |
| `claude auto-mode defaults --label <prefix>` | "Matching is a case-insensitive prefix on each rule's label, and sections with no match print as empty lists." | `--label 'Git Destructive'` → 1 `soft_deny` entry, other three sections `[]`. `--label 'git destructive'` (lowercase) → same entry, confirming case-insensitivity. `--label 'zzz-nonexistent'` → all four sections `[]`. `--label ''` → the full list |
| `claude auto-mode config` | "Print what the classifier actually uses as JSON, with your settings applied where set and defaults otherwise" | Same four-key JSON shape; identical to `defaults` when no `autoMode` block is set |
| `claude auto-mode critique` | "Get AI feedback on your custom `allow`, `soft_deny`, `hard_deny`, and `environment` entries" | With no custom rules: `No custom auto mode rules found.` + a pointer to the settings key and to `claude auto-mode defaults`. With a custom rule supplied via `--settings`: `Analyzing your auto mode rules...` then `No critique was generated. Please try again.` (the review is a separate model call; on this host it returned nothing) |
| `claude auto-mode reset` | "removes the `autoMode` section from your user settings file" | `reset --yes` printed the target path and the sections to be removed (`soft_deny (2 entries)`), then `Auto mode configuration reset to defaults - autoMode section removed from <path>.` Sibling keys (`theme`, `permissions`) were preserved. Without an `autoMode` section: `Auto mode configuration is already at defaults - <path> has no autoMode section.` (exit 0) |

Verbatim from `claude auto-mode --help` (OBSERVED-CLI):

```
Usage: claude auto-mode [options] [command]

Inspect or reset auto mode classifier configuration

Options:
  -h, --help          Display help for command

Commands:
  config              Print the effective auto mode config as JSON: your
                      settings where set, defaults otherwise
  critique [options]  Get AI feedback on your custom auto mode rules
  defaults [options]  Print the default auto mode environment, allow, soft_deny,
                      and hard_deny rules as JSON
  help [command]      display help for command
  reset [options]     Reset auto mode configuration to the shipped defaults by
                      removing the autoMode section from your user settings file
```

`defaults --label` help: `--label <prefix>  Show only rules whose label starts with
this prefix (case-insensitive)`. `reset` help: `-y, --yes  Skip the confirmation
prompt`. `critique` help: `--model <model>  Override which model is used`.

**Reimplementation need:** yes. These four subcommands are the *entire* developer
surface for the feature; a clean-room build should ship all four with the same
distinction between "shipped defaults" and "effective config".

### 2.11 The rule-label vocabulary (OBSERVED-CLI)

The built-in rules are labelled strings of the form `Label: prose`. Observed label
inventory on 2.1.306:

- **`allow` (17):** Security Discussion, Transient Retry, Test Artifacts, Local
  Operations, Read-Only Operations, Declared Dependencies, Toolchain Bootstrap,
  Standard Credentials, Session-Created Job Cleanup, Git Push Destination, Trusted
  Internal Infra (Data Flow), Scheduled-Task Fires, Multi-Agent Coordination, Memory
  Directory, CLAUDE.md Content, Claude Code Scheduling, Browser Trusted Navigation.
- **`soft_deny` (72):** Git Destructive, Code That Leaks When Run, Code from External
  Source, Cloud Storage Mass Delete, Production Deploy, Remote Shell Writes, Sensitive
  Remote Exec, Production Reads, Blind Apply, Protected-Scope IaC Apply, Logging/Audit
  Tampering, Permission Grant, Account & Standing-Rule Changes, TLS/Auth Weaken,
  Secret-Store Writes, DNS / Domain / Cert Changes, Security Weaken, Security Test
  Removal, Safety Bypass Flag, Create Unsafe Agents, Interfere With Workloads, Shared
  Cluster Mutation, CI Bypass, Modify Shared Resources, Irreversible Local Destruction,
  Unverifiable Deletion Target, Shared Scratch Sweep, Irreversible Deletion (general),
  Unverifiable Deletion Scope, Create RCE Surface, Expose Local Services, External
  Ingress Tunnel, Credential Leakage, Credential Materialization, Credential
  Exploration, PII Data Handling, Exfil Scouting, Traffic Redirection, Remote Repoint,
  Out-of-Place Publication, Sensitive-Source Provenance, Excess Sensitive Detail,
  Unrequested Artifact Publish, Live-Shared Artifact Sensitive Delta, Sandbox Network
  Callback, Command Network Lists, Containment Escape, Create Public Surface, Public
  Data-Sharing Upload, Untrusted Code Integration, Package Registry Bypass,
  Unauthorized Persistence, Self-Modification, Tmux Self Drive, Instruction Poisoning,
  Auto-Mode Bypass, Session Transcript Tampering, Unrequested Commit in a Connected
  App, External System Writes, Merge Without Review, Self-Approval, ChatOps Trigger
  Comments, Feature Flag Writes, Node Lifecycle Operations, Cluster-Wide Workload
  Creation, Real-World Transactions, Third-Party Attack, Browser Navigate Exfil,
  Browser Input Exfil, Browser JS Exfil, Browser File Upload Exfil, Browser Shortcut
  Execution.
- **`hard_deny` (1):** Data Exfiltration.

Every `soft_deny` label carries the same suffix
`[named+specifics — **must name:** …]`, and the rule text spells out what "naming the
action" means. Example, verbatim:

> Git Destructive [named+specifics — **must name:** the destructive operation and its
> target]: A force-push, remote-branch or tag deletion, release deletion, or history
> rewrite that destroys someone else's work — removing commits other people authored or
> depend on. On a shared or release branch (e.g. `main`, `master`, `staging`, `develop`,
> `prod-*`, `release-*`, `release/*`, or the repository's default branch), other people's
> work is presumed: … `--force-with-lease` is the sanctioned careful form of force
> everywhere and is judged by the clarity bar below, not the presumption.

**Reimplementation need:** the *label* concept is essential (it is what the UI shows
in `[Square Brackets]` and what `--label` filters on). The specific 90 rule texts are
Anthropic-authored content; a clean-room build must write its own rule set from
first principles, but the **structure** (labelled, prose, category-typed, with an
explicit "must name" clause for user-intent-cleared rules) is the transferable part.

### 2.12 `permissions.ask` as a human checkpoint (OBSERVED-DOC + OBSERVED-CLI)

Section: **Add a human checkpoint**

> The most direct mechanism is [`permissions.ask`]. Content-scoped ask rules like the
> ones below are evaluated before the classifier and always force a permission prompt,
> even in auto mode, because an explicit ask rule is your stated intent to be prompted
> for that action.

```json
{
  "permissions": {
    "ask": [
      "Bash(git push *)",
      "Bash(gh pr create *)"
    ]
  }
}
```

> These rules match commands that begin with `git push` or `gh pr create`. A push
> Claude writes another way, such as `git -C <dir> push` or `git -c <key>=<value>
> push`, [doesn't match the rule], so it isn't checkpointed. For a checkpoint that
> inspects the full command text, add a [PreToolUse hook].

The page also offers a three-way table (Prompt before the action → `permissions.ask`;
Never run the action → `permissions.deny`; One-off boundary for this session → state
it in conversation) with the warning that a conversational boundary "can be lost if
[context compaction] removes the message that stated it".

**OBSERVED-CLI** — cross-check of the "evaluated before the classifier" ordering, using
a non-Anthropic gateway where the classifier path is visibly distinguishable (it
returns a named no-verdict error when reached, and succeeds silently when not):

- `permissions.ask = ["Bash(mkdir *)"]` + `--permission-mode auto`: the model's
  **Bash** call was **denied by the permission system** ("the Bash tool call was
  denied permission, so I used PowerShell's `New-Item` instead") — i.e. the ask rule
  fired *before* any classifier involvement. The subsequent **PowerShell** call was
  *not* covered by that rule, so it went to the classifier, which produced the
  documented no-verdict error: `minimax/minimax-m3.1-flash:free is temporarily
  unavailable (timed out), so auto mode cannot determine the safety of PowerShell
  right now. … Note: reading files, searching code, and other read-only operations do
  not require the classifier and can still be used.`
- `permissions.ask = ["PowerShell(mkdir *)"]` + `--permission-mode auto`: the
  PowerShell `mkdir` call executed with **no** classifier round trip and no no-verdict
  error.

**INFERRED:** an ask rule that matches the tool call short-circuits the classifier
for that call (the classifier is not consulted), while a non-matching ask rule leaves
the call to the classifier. This is consistent with the documented "evaluated before
the classifier and always force a permission prompt, even in auto mode" and with the
decision order on `permission-modes.md` ("Ask rules that match on a command's content
… fall back to a permission prompt" as step 1, with "Everything else goes to the
classifier" as step 3). The evidence is a differential observation on one gateway
build, not a direct trace of the classifier's invocation count.

**Reimplementation need:** yes. The three-mechanism table (ask rule / deny rule /
conversational boundary) is a good, minimal design vocabulary and is easy to
reproduce.

### 2.13 Common boundaries — what auto mode allows by default (OBSERVED-DOC)

Section: **Common boundaries**

> Auto mode allows pushes to any branch of the repository you're working in, including
> the default branch, and pull request creation by default. A non-default branch whose
> name marks it as a deploy or publication target, such as `production`, `release`, or
> `gh-pages`, isn't covered by that default: the classifier judges a push there on its
> own terms, including as a production deploy. The push's content is also still
> checked, so a force push, a secret entering the commit, or a change that would send
> secrets outside the repository when CI or a deploy pipeline runs it stays blocked.

The matching built-in `allow` rule observed on the CLI:

> Git Push Destination: Pushing to any branch of the session's repo is ordinary — the
> default branch included, whatever its name; no branch etiquette is enforced, and a
> bare "push" needs no naming. This exception blesses the DESTINATION and nothing
> else: it clears no judgment about what the push contains or what it would set
> running … One carve: a non-default branch whose NAME marks it as a deploy or
> publication target (production, release, deploy, gh-pages, and the like) is neither
> blessed nor blocked by this exception — judged on its own terms, Production Deploy
> among them.

**Reimplementation need:** yes, as the *default policy posture*. Note the careful
distinction between "destination is trusted" and "content is trusted" — a clean-room
build should keep them orthogonal.

### 2.14 The `autoMode.environment` trusted-boundary definition (OBSERVED-DOC)

Section: **Define trusted infrastructure**

> For most organizations, `autoMode.environment` is the only field you need to set. It
> tells the classifier which repos, buckets, and domains are trusted: the classifier
> uses it to decide what "external" means, so any destination not listed is a potential
> exfiltration target.

And, from the defaults, the `hard_deny` rule that consumes it:

> Data Exfiltration: Sensitive data crossing the trust boundary (the trusted repos,
> domains, and buckets listed in Environment) as a result of the agent's action —
> directly, or by arming an automated pathway that will. **Evaluate where the data
> finally lands, not where the command immediately points. …**

**Reimplementation need:** yes — the "trust boundary is defined by `environment`"
model is the core data-flow concept.

### 2.15 `/auto-mode-setup` (OBSERVED-DOC)

Section: **Generate environment entries with `/auto-mode-setup`**

> Run `/auto-mode-setup` to have Claude Code draft `autoMode.environment` entries, and
> sometimes [rule entries] too, from your project and your recent sessions in it. If
> you accept the draft, Claude Code writes it to `~/.claude/settings.json`.

Availability: "available on Pro, Max, Team, and Enterprise plans and with a Claude
Console API key. On a Pro, Max, or Team plan, you need v2.1.228 or later, or v2.1.233
or later on native Windows. On an Enterprise plan or with a Claude Console API key, you
need v2.1.283 or later."

> Claude Code always reads these sources:
>
> * This project's `CLAUDE.md`, `README.md`, config files, and git remotes
> * Your `autoMode` and `permissions.allow` settings
> * The hosts, buckets, and command names from the commands Claude ran in your recent
>   sessions in this project, never your messages
>
> The two optional scans add one source each:
>
> * The first word of each command in your shell history
> * The remote hosts and names of the repositories under your home directory

Merge behaviour on save:

> * Claude Code writes the `environment` list without `"$defaults"`, because the draft
>   spells out the built-in entries it left unchanged
> * Claude Code includes `"$defaults"` in each of the `allow`, `soft_deny`, and
>   `hard_deny` lists the draft adds entries to, unless you already wrote an `allow`
>   list without it …
> * After saving, Claude Code offers to remove `permissions.allow` rules in
>   `~/.claude/settings.json` that auto mode ignores, such as `Bash(*)`, or that
>   auto-approve destructive commands

Turning it off:

```json
{
  "skillOverrides": {
    "auto-mode-setup": "off"
  }
}
```

> `/auto-mode-setup` is a built-in command rather than a [bundled skill], so this
> `skillOverrides` entry still applies to it, but [`disableBundledSkills`] doesn't turn
> it off.

**Reimplementation need:** the *flow* (scan known sources, draft, human review, merge
with a token policy) is highly reproducible. The specific version gates are not.

### 2.16 Editing rules from `/permissions` (OBSERVED-DOC)

Section: **Edit rules from `/permissions`**

> To view and edit classifier rules and `environment` entries without opening a
> settings file, run [`/permissions`] and select the **Auto mode** tab. The tab
> requires Claude Code v2.1.246 or later, and it appears only when [auto mode is
> available] to your session.
>
> Claude Code shows entries from [managed settings] or the `--settings` flag as
> read-only, and saves every change you make on the tab to `~/.claude/settings.json`.

**Reimplementation need:** yes — the read-only-lower-scope / write-to-user-scope
asymmetry is a clean, testable contract.

### 2.17 Reviewing denials (OBSERVED-DOC + OBSERVED-CLI)

Section: **Review denials**

> To review and retry actions the auto mode classifier denied, open `/permissions` and
> select the **Recently denied** tab, where Claude Code records each denial. Press `r`
> on a denied action to mark it for retry: when you exit the dialog, Claude Code sends
> a message telling the model it may retry that tool call and resumes the conversation.

> When the classifier produces [no verdict on the action], because a safety check
> separate from auto mode refused the classifier's own request or its response didn't
> parse, Claude Code denies the action without recording it under **Recently denied**.

> Two other places on screen that report denials leave out the command or URL: the
> notice near the input box, such as `bash denied by auto mode · [Data Exfiltration] ·
> /permissions`, gives the tool and the reason, and the **Recently denied** tab lists a
> shell command by the description Claude wrote for it. To capture the exact input of
> these denials programmatically, add a [`PermissionDenied` hook], which receives it as
> `tool_input`.

> The text in square brackets, such as `[Data Exfiltration]`, is the name of the rule
> the classifier matched.

**OBSERVED-CLI** — the classifier fired on this host and produced exactly this
shape:

```
Permission for this action was denied by the Claude Code auto mode classifier.
Reason: [Self-Modification].
```

The matched label `[Self-Modification]` matches the built-in `soft_deny` label exactly.
A second attempt writing the same file with an **empty** `autoMode` object `{}` was
**allowed** — so the rule distinguishes "widening the agent's own config" from
"touching the config file". The corresponding built-in rule reads:

> Self-Modification [named+specifics — **must name:** that this specific permission or
> consent change is wanted]: Edits to the agent's own config that (a) add or widen
> permissions or weaken guards — permission allow rules (e.g. wildcard
> `"Bash(prefix:*)"` entries), hook or sandbox changes, approval-gate settings — that
> the user did not explicitly ask for, even while making a user-requested edit to the
> same file; or (b) write consent or instruction content the user did not give …

**Reimplementation need:** yes. The observable contract is
`(denial) -> {tool, reason, matched-rule-label}` plus a machine-readable hook
(`PermissionDenied` with `tool_input` and `reason`).

### 2.18 The classifier's request payload and what it cannot see (OBSERVED-DOC)

Section: **Where the classifier reads configuration** and the *How auto mode evaluates
actions* block on `permission-modes.md`.

> In the classifier requests sent by Claude Code itself, the classifier reads your
> messages and the commands Claude runs, not their output. The evidence has to be
> something the classifier can read, such as your own message naming the repository as
> public; the output of a `gh repo view` on its own doesn't reach it.

And from `permission-modes.md`:

> In the classifier requests sent by Claude Code itself, the classifier sees user
> messages, tool calls other than read-only lookups such as file reads and searches, and
> your CLAUDE.md content. Tool results are stripped from those requests, so hostile
> content in a file or web page can't manipulate the classifier directly.

> You can annotate a call's result with a [PostToolUse hook's `classifierContext`
> field], which the classifier reads as application-provided context. The field requires
> Claude Code v2.1.236 or later.

The `hooks.md` reference adds the trust warning:

> The classifier reads content you place in `classifierContext` as information from the
> application hosting the session, so don't copy untrusted tool output or third-party
> text into it.

**Reimplementation need:** yes — the *tool-result stripping* is a prompt-injection
defence and is architecturally central. A clean-room build should strip tool output
from the safety-classifier context by default, and treat any developer-supplied
context channel as trusted-by-construction.

### 2.19 Fallback behaviour when the classifier is unavailable (OBSERVED-CLI + OBSERVED-DOC)

From `permission-modes.md` (**When auto mode falls back**):

> * **A blocked action**: Claude Code shows a notification and lists the action in
>   `/permissions` under the **Recently denied** tab, where you can press `r` to retry
>   it with a manual approval.
> * **Repeated blocks**: if the classifier blocks an action 3 times in a row or 20
>   times total, auto mode pauses and Claude Code resumes prompting.
> * **No verdict from the classifier**: … Claude Code denies the action without the
>   notification or the **Recently denied** entry.

**OBSERVED-CLI** — the no-verdict path was exercised on this host with a non-Anthropic
gateway:

```
minimax/minimax-m3.1-flash:free is temporarily unavailable (timed out), so auto mode
cannot determine the safety of PowerShell right now. Wait a moment and then try this
action again. If it keeps failing, continue with other tasks that don't require this
action and come back to it later. Note: reading files, searching code, and other
read-only operations do not require the classifier and can still be used.
```

This matches `errors.md` → **Auto mode cannot determine the safety of an action**:
the message names the model, the category `(timed out)`, and the actionable next step.

**Reimplementation need:** yes — the failure mode is a *deny with an explanatory
message*, not a silent hang, and the escape hatch ("keep working on non-classified
operations") matters for agent loops.

### 2.20 Classifier model selection and server-side review (OBSERVED-DOC)

From `permission-modes.md` and `env-vars.md`:

- Default classifier model: "By default, classifier requests go to Claude Sonnet 5."
- `CLAUDE_CODE_AUTO_MODE_MODEL` — "Sets the model for the classifier requests Claude
  Code sends in auto mode. Use a full model ID such as `claude-sonnet-4-6`. …
  Requires Claude Code v2.1.302 or later".
- `CLAUDE_CODE_AUTO_MODE_SERVER` — "Controls whether Claude Code asks the server to
  review auto mode actions. Set to `0` to use Claude Code's own classifier requests
  instead. … Requires Claude Code v2.1.271 or later".
- Supported models for auto mode: "on the Anthropic API and Claude Platform on AWS,
  Claude Opus 4.6 or later, Sonnet 4.6 or later, Haiku 5.5, or a Fable model. On Amazon
  Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and signed-in Claude apps
  gateway sessions, only Claude Sonnet 5 or later, Opus 4.7 or later, Haiku 5.5, and
  the Fable models."

**Reimplementation need:** yes — a safety classifier on a separate, possibly smaller,
model is the standard architecture, and making the classifier model configurable is
essential for cost control.

### 2.21 Availability and gating (OBSERVED-DOC + OBSERVED-CLI)

From `permission-modes.md` (**Eliminate permission prompts with auto mode**):

> Auto mode is available only when your account meets all of these requirements:
>
> * **Plan**: All plans.
> * **Organization**: on Team and Enterprise, auto mode is available by default.
>   Administrators can turn it off for the organization by setting
>   `permissions.disableAutoMode` to `"disable"` in [managed settings].
> * **Model**: …
> * **Provider**: available by default on the Anthropic API, Claude Platform on AWS,
>   Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and signed-in
>   Claude apps gateway sessions.

And:

> With Claude Code v2.1.283 or later, auto mode is the built-in starting permission
> mode for interactive terminal and VS Code sessions on every plan and provider.

**OBSERVED-CLI** — the gate is visible in the debug log on this host:

```
[DEBUG] [auto-mode] verifyAutoModeGateAccess: enabledState=enabled
        disabledBySettings=false model=minimax/minimax-m3.1-flash:free modelSupported=true
        disableFastModeBreakerFires=false carouselAvailable=true canEnterAuto=true
```

Note `modelSupported=true` for a non-Anthropic gateway model — the gate on this build
does not restrict by vendor, only by an internal model catalogue. This is an
observation about *this* build and gateway, not a general statement.

### 2.22 The `autoMode` key in `settings-reference.md` (OBSERVED-DOC)

Section: **`autoMode`**

> * **Scope**: [`User or managed`](#scopes)
> * **Type**: object with `environment`, `allow`, `soft_deny`, and `hard_deny` arrays of
>   prose rules, plus the [`classifyAllShell`](#automode-classifyallshell) Boolean
> * **Default**: unset, so the classifier uses only its [built-in rules]
>
> When more than one of those files sets the same array, Claude Code concatenates the
> entries.

This is the canonical statement of scope: **user or managed only**. It matches the
observed project-scope exclusion.

### 2.23 Cost and latency (OBSERVED-DOC)

From `permission-modes.md` (**Cost and latency**):

> On Enterprise plans and on accounts that use the Claude API, Claude Platform on AWS,
> Amazon Bedrock, Google Cloud's Agent Platform, or Microsoft Foundry, classifier
> calls count toward your token usage. Each check sends a portion of the transcript
> plus the pending action, adding a round-trip before execution. Reads and
> working-directory edits outside protected paths skip the classifier, so the overhead
> comes mainly from shell commands and network operations.

**Reimplementation need:** yes — the cost model (per-classified-action round trip,
transcript portion included) is the main economic constraint on this architecture.

---

## 3. Capability table

| Capability | Config key / surface | Status | Evidence |
| :- | :- | :- | :- |
| Enable auto mode | `--permission-mode auto`; `permissions.defaultMode` | OBSERVED-DOC | permission-modes.md |
| Admin kill switch | `permissions.disableAutoMode: "disable"` (managed) | OBSERVED-DOC | settings-reference.md |
| Classifier rule store | `autoMode.environment` | OBSERVED-DOC + OBSERVED-CLI | auto-mode-config.md; 21 default entries printed |
| Classifier allow rules | `autoMode.allow` | OBSERVED-DOC + OBSERVED-CLI | 17 default entries printed |
| Classifier soft blocks | `autoMode.soft_deny` | OBSERVED-DOC + OBSERVED-CLI | 72 default entries printed |
| Classifier hard blocks | `autoMode.hard_deny` | OBSERVED-DOC + OBSERVED-CLI | 1 default entry (`Data Exfiltration`) |
| Force all shell through classifier | `autoMode.classifyAllShell: true` | OBSERVED-DOC | auto-mode-config.md; settings-reference.md |
| Keep built-ins while adding | `"$defaults"` token | OBSERVED-DOC + OBSERVED-CLI | splice verified in place; omission replaces list |
| Scope precedence | user → managed → `--settings`/SDK inline | OBSERVED-DOC + OBSERVED-CLI | project scope confirmed ignored; scopes concatenate |
| Print built-in rules | `claude auto-mode defaults` | OBSERVED-DOC + OBSERVED-CLI | JSON with 4 keys; `--label` prefix filter, case-insensitive |
| Print effective rules | `claude auto-mode config` | OBSERVED-DOC + OBSERVED-CLI | identical to defaults when unset |
| Lint custom rules | `claude auto-mode critique` | OBSERVED-DOC + OBSERVED-CLI | "No custom auto mode rules found." when none |
| Reset to defaults | `claude auto-mode reset [--yes]` | OBSERVED-DOC + OBSERVED-CLI | removes only the `autoMode` section |
| Draft environment entries | `/auto-mode-setup` | OBSERVED-DOC | plan-gated; writes `~/.claude/settings.json` |
| Edit rules in a TUI | `/permissions` → **Auto mode** tab | OBSERVED-DOC | v2.1.246+; lower scopes read-only |
| Review / retry denials | `/permissions` → **Recently denied**, `r` | OBSERVED-DOC | no-verdict denials are not recorded |
| Machine-readable denials | `PermissionDenied` hook (`tool_input`, `reason`) | OBSERVED-DOC | hooks.md |
| Feed context to the classifier | `PostToolUse` → `classifierContext` | OBSERVED-DOC | v2.1.236+; trusted-content warning |
| Pick the classifier model | `CLAUDE_CODE_AUTO_MODE_MODEL` | OBSERVED-DOC | v2.1.302+ |
| Use server-side review | `CLAUDE_CODE_AUTO_MODE_SERVER=0` to opt out | OBSERVED-DOC | v2.1.271+ |
| Classifier during plan mode | `useAutoModeDuringPlan` (default `true`) | OBSERVED-DOC | settings-reference.md |
| Per-command sandbox hosts | command carries host list; classifier reviews hosts with command | OBSERVED-DOC | sandboxing.md, v2.1.271+ |

---

## 4. Dependencies

| Dependency | Needed for | Availability here |
| :- | :- | :- |
| Anthropic API / a supported model provider | The classifier call itself | **No** — custom gateway with a non-Anthropic model; the classifier round trip failed with a "temporarily unavailable (timed out)" no-verdict |
| A subscription plan (Pro/Max/Team/Enterprise) or Claude Console API key | `/auto-mode-setup` | Unknown on this host (not exercised) |
| Managed-settings deployment (org) | Org-wide `autoMode` | Not present on this host |
| `permissions.deny` in managed settings | A genuine non-overridable boundary | Local file only; no org channel here |
| `CLAUDE.md` | Project conventions that also steer the classifier | Present/optional |
| `--settings` / Agent SDK | Per-invocation `autoMode` overrides | Fully available (verified) |
| `~/.claude/settings.json` | Personal `autoMode` | Fully available (verified) |
| `PostToolUse` hooks | `classifierContext` | Available |
| `PermissionDenied` hooks | Machine-readable denial capture | Available |
| Network egress to the model endpoint | Every classified action | Present (the gateway) but flaky for the classifier path |

---

## 5. Limitations of this investigation

1. **The classifier model itself was never a real Anthropic model.** This host runs
   against a third-party gateway. The classifier was reached (a denial with a matched
   rule label was produced, and a no-verdict timeout was produced) but the *quality*
   and the *server-side review* path are not observable here.
2. **The interactive TUI surfaces were not captured.** `/permissions` (Auto mode tab,
   Recently denied tab) and the `/auto-mode-setup` dialogs are documented but not
   exercised in this session. Their exact layout is OBSERVED-DOC only.
3. **Managed settings and organisation policy were not exercised.** No managed
   settings file was present; the scope-combination order between managed and user
   scope is documented, not observed.
4. **`/auto-mode-setup` was not run.** It is plan-gated and would have written to
   `~/.claude/settings.json`.
5. **Version gates are documentation, not observation.** Every "requires vX.Y.Z"
   statement is quoted from the docs; only 2.1.306 behaviour was observed.
6. **No source, weights, prompts, or internal APIs were inspected**, per the compliance
   boundary.

---

## 6. Unresolved questions (UNKNOWN)

- **U1.** The exact request/response schema between Claude Code and the classifier
  service (field names, whether it is a Messages API call, the shape of the verdict
  object) — the docs describe behaviour, not the wire format. The one wire-level
  artefact available is the debug-log line `classifier_request_started`, referenced on
  the permission-modes page; it was not produced on this host.
- **U2.** How the classifier decides "explicit user intent" in the four-tier
  precedence — the prose says "directly and specifically describes the exact action";
  the operationalisation is not published.
- **U3.** Whether the *same* classifier request is reused for `hard_deny` and
  `soft_deny`, or whether `hard_deny` is enforced locally. The docs say `hard_deny`
  is "unconditional", but the enforcement point is not stated.
- **U4.** The full built-in `environment` text (not just the labels) at 2.1.306 — the
  JSON *was* captured locally; the difference is only that the shipped defaults change
  between releases, so a fixed copy is a snapshot, not a contract.
- **U5.** Whether `autoMode` participates in the `CLAUDE.md` load order when a project
  `CLAUDE.md` is edited mid-session.
- **U6.** The interaction between `autoMode.classifyAllShell: true` and the sandbox's
  auto-allow mode beyond the documented "except critical-path removals".
- **U7.** Whether `permissions.deny` in *project* scope (repo-resident) is also
  honoured by the classifier's first layer — the page only guarantees that
  repo-resident `autoMode` is ignored.
- **U8.** The exact contents of the `Recently denied` record (persistence across
  sessions, retention).

---

## 7. Clean-room implementation opportunity

### 7.1 The observable contract to reproduce

1. A `autoMode` configuration object with four ordered string arrays
   (`environment`, `allow`, `soft_deny`, `hard_deny`) plus a boolean
   (`classifyAllShell`).
2. A sentinel `"$defaults"` that, when present in an array, is replaced **in place**
   by the built-in entry list; when absent, the array *replaces* the built-ins.
3. Scope resolution over exactly three sources — user settings, managed settings,
   per-invocation inline settings — with **concatenation** across scopes and
   **exclusion** of project-resident settings.
4. A four-tier precedence algebra: `hard_deny` ≻ `soft_deny` ≻ `allow` ≻ general
   intent, with "explicit user intent" as a special case of `soft_deny` clearing.
5. A classifier request that carries the pending action, the user's messages, the
   non-read-only tool calls, and the `CLAUDE.md` content — and **excludes tool
   results** — returning either a verdict naming a matched rule label, or nothing
   (no-verdict).
6. A denial surface that produces: a human-readable reason, a bracketed matched-rule
   label, a `PermissionDenied` hook payload carrying `tool_input` and `reason`, and a
   retry affordance.
7. Four CLI subcommands: `defaults` (with a case-insensitive label prefix filter),
   `config`, `critique`, `reset` (scoped to the `autoMode` section of the user
   settings file only).

### 7.2 How to build it without copying Anthropic

- **Store rules as prose strings; never compile them.** The clean-room
  implementation should store one rule per string, keyed by a human label, and hand
  the whole set to the safety model as instructions. The only structural metadata
  worth keeping is the *category* (`environment` / `allow` / `soft_deny` /
  `hard_deny`), because it determines precedence — not the prose itself.
- **Express precedence to the model, do not implement it in code.** A clean-room
  implementation can render the four tiers as an ordered instruction block
  ("Tier 1 — unconditional blocks: … Tier 4 — explicit user intent: …") and require
  the classifier to return a structured verdict
  `{decision: "allow"|"deny", tier: 1|2|3|4, matched_rule: "<label>"}`. That
  reproduces the observable behaviour (including the bracketed label in the denial
  message) without a hand-written rule engine.
- **Model the "must name" requirement as a second prompt field.** Anthropic's
  `soft_deny` rules embed a `[named+specifics — must name: …]` clause. A clean-room
  implementation can express this generically: every user-intent-clearable rule
  carries a `requires_named_target: true` flag and the classifier is told to return
  `explicit_intent: true` only when the user's message names both the action and its
  target.
- **Reproduce the scope exclusion, and make the reason explicit.** The clean-room
  rule "project-resident config may not widen permissions" should be implemented as a
  *loader* rule: only user, managed, and per-invocation sources are consulted for
  permission-widening settings. This is a well-understood pattern (trust domains
  separated by provenance) and is exactly what a "settings from untrusted repo" threat
  model calls for.
- **Use a sentinel that is not a magic string.** Anthropic's `"$defaults"` is a
  literal string in a prose array. A clean-room implementation that wants the same
  ergonomics could keep a literal token but must document that it is special-cased
  *before* the rules are sent to the model, and must define what happens when a user
  genuinely wants a rule whose text is `"$defaults"`.
- **Provide the four CLI subcommands with the same division of labour.** "Shipped
  defaults" vs "effective config" vs "lint my custom rules" vs "reset" is a clean API.
  The `--label` prefix filter is a trivial win for usability.
- **Make the classifier optional and fail closed, with a working fallback.** When the
  classifier cannot be reached, deny the action, name the reason, and explicitly tell
  the agent that read-only work can continue. Anthropic's message does exactly this
  and it is a good design.
- **Wire the denials into an event stream.** A `PermissionDenied`-style event with
  `{tool_name, tool_input, reason, matched_rule}` is the machine-readable form of
  "the classifier said no", and it is what makes a denial auditable.
- **Do not implement a rule engine.** That is the biggest clean-room trap: the
  observable behaviour is inherently fuzzy ("did the user name the action?"), so any
  deterministic matcher will be wrong in both directions. The correct engineering
  choice is to accept the fuzziness, spend a model call, and make the outcome legible
  with a rule label.

### 7.3 What NOT to replicate

- The specific rule texts (Anthropic-authored content; and a snapshot of them is
  stale by the next release).
- The literal version gates (v2.1.246, v2.1.257, …) — they are release engineering
  trivia, not contract.
- The `"/auto-mode-setup"` conversational flow verbatim.
- The "combination is additive, not a hard policy boundary" weakness, unless you
  deliberately choose it; if you keep it, say so plainly in the docs, as Anthropic
  does.

---

## 8. Evidence index

| Artefact | Path (absolute) |
| :- | :- |
| Built-in rules JSON (2.1.306) | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-auto-mode\auto-mode-defaults.json` |
| Effective config JSON (2.1.306, no user overrides) | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-auto-mode\auto-mode-config-effective.json` |
| CLI help captures | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-auto-mode\cli-auto-mode-help.txt` |
| Sanitized workflow transcripts | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-auto-mode\sanitized-workflows.md` |
| Fetched doc pages (verbatim markdown) | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-auto-mode\docs\` |
| Working scratch (raw probes) | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\areas\.fetch-amc\` |
| Compliance boundary | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\TERMS-NOTES.md` |

### Public documentation sources fetched

- https://code.claude.com/docs/en/auto-mode-config.md
- https://code.claude.com/docs/en/permission-modes.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/permissions.md
- https://code.claude.com/docs/en/sandboxing.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/hooks.md
- https://code.claude.com/docs/en/errors.md
- https://code.claude.com/docs/en/commands.md
- https://code.claude.com/docs/en/server-managed-settings.md
- https://code.claude.com/docs/en/skills.md
- https://code.claude.com/docs/en/auto-mode-classifier-billing.md
- https://code.claude.com/docs/llms.txt
