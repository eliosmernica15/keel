# Claude Code — Model Configuration Evidence (page: `code.claude.com/docs/en/model-config.md`)

**Page studied.** <https://code.claude.com/docs/en/model-config.md> — "Model configuration:
Configure which model Claude Code uses, effort levels, extended context, and the auto-compact
window". Listed in the documentation index at <https://code.claude.com/docs/llms.txt> (lines 387
and 411) as "Model configuration".

**Compliance boundary.** Claude Code is proprietary. Anthropic's Consumer ToS §3 and Commercial
ToS §D.4 prohibit decompiling/reverse engineering/disassembling the Services, and the docs state
"The Claude Code binary must not be modified." **No decompilation, JS extraction, source-map
dumping, binary modification, credential/keychain/licence reading, or private-account access was
performed.** Everything below comes from (a) the public Anthropic documentation fetched over
HTTPS, and (b) the published CLI's own user-facing surfaces (`claude --help`, `claude -p`,
`claude --debug` diagnostic output, `--settings` files, stderr warnings). The CLI's own debug log
is a first-class diagnostic surface the product ships for this purpose; it was read only for
model identifiers and warning strings.

**Machine caveat that shapes every finding.** This host runs Claude Code **2.1.306**
(win32-x64) against a **custom `ANTHROPIC_BASE_URL`** (`https://openrouter.ai/api`) serving a
**non-Anthropic model** (`minimax/minimax-m3.1-flash:free`). `claude doctor` reports "Not
connected to the Anthropic API" and "Not signed in to claude.ai". Therefore anything gated on an
Anthropic subscription, on `api.anthropic.com`, on real alias→version resolution for non-Anthropic
providers, or on admin-console entitlements is **OBSERVED-DOC**, not observed here.

**Classification legend.**
`OBSERVED-DOC` = stated in a cited public Anthropic document (quoted).
`OBSERVED-CLI` = personally executed against the published CLI (exact command + output quoted).
`INFERRED` = a conclusion drawn from evidence, with the reasoning stated.
`UNKNOWN` = the available evidence cannot establish it.

No claim is made about internal model behaviour, private system prompts, proprietary source code,
training data, model weights, or hidden APIs.

---

## 1. Executive summary

**The page is not thin.** It is the single densest specification in the Claude Code docs for a
user-facing configuration subsystem, and it specifies four separate resolution systems that share
one shape:

| Subsystem | Resolution order (highest first) | Status |
| :- | :- | :- |
| **Model** | `/model` (in-session) → `--model` → `ANTHROPIC_MODEL` → `"model"` in a settings file → `ANTHROPIC_DEFAULT_MODEL` → org default → account-type default | OBSERVED-DOC + OBSERVED-CLI (partial) |
| **Effort** | `CLAUDE_CODE_EFFORT_LEVEL` → `--effort` → `/effort` → `modelSettings.<model>.effortLevel` → `effortLevel` → model's own default | OBSERVED-DOC |
| **Auto-compact window** | `CLAUDE_CODE_AUTO_COMPACT_WINDOW` → `--autocompact` → `/autocompact` (per-model) → `autoCompactWindow` → model-tuned default | OBSERVED-DOC + OBSERVED-CLI (warning text) |
| **Alias → model ID** | `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` → provider built-in default → alias table | OBSERVED-DOC + OBSERVED-CLI (partial) |

The **core insight for an implementer** is that this page is really about *three distinct
mechanisms* that the docs interleave:

1. **An alias layer** — `opus`, `sonnet`, `haiku`, `fable`, `best`, `default`, `opusplan`, plus
   `[1m]` suffix variants — that resolves to concrete model IDs. The alias table is
   **provider-specific** (`opus` is Opus 5.5 on the Anthropic API but Opus 4.6 on Microsoft
   Foundry) and **version-specific** (the page carries a `Version history` table of exactly when
   each alias moved).
2. **A policy layer** — `availableModels`, `enforceAvailableModels`, `deniedModels`,
   `availableModelsMatch`, org restrictions — that filters what a user may select, and specifies
   *per-surface* behaviour (reject vs. substitute vs. ignore vs. fall back to a different model)
   for every place a model can be named. This is the largest and least obvious part of the page.
3. **A provider-adaptation layer** — `modelOverrides`, the `ANTHROPIC_DEFAULT_*_MODEL` pins, the
   `*_NAME`/`*_DESCRIPTION`/`*_SUPPORTED_CAPABILITIES` companions, `[1m]` suffix stripping —
   that makes one Anthropic model catalogue usable over Bedrock / Vertex / Foundry / gateways,
   where model IDs are ARNs, version names, or deployment names.

**What I could confirm at runtime (OBSERVED-CLI).** Alias resolution is real and observable:
`--model opus` → `claude-opus-5-5`, `sonnet` → `claude-sonnet-5-5`, `haiku` → `claude-haiku-5-5`,
`fable` → `claude-fable-5-1`, `best` → `claude-fable-5-1`, `opusplan` → `claude-sonnet-5-5` (the
non-plan phase). The documented 200K-assumption warning fires verbatim for unrecognised IDs.
The `availableModels` allowlist demonstrably re-routes the session to a permitted model and
produces the documented fast-mode refusal string. `modelOverrides` demonstrably rewrites the
model ID sent to the provider. `deniedModels` and `availableModelsMatch` are demonstrably
**ignored outside managed settings**, with the documented warning naming the file and key.

**What a clean-room implementation must get right.** The precedence chain is the contract; the
alias table is data; and the *failure modes* are the hard part — the reference product does not
have one "invalid model" policy but at least five distinct ones (reject the switch / substitute
the newest permitted version / drop the value and warn / ignore the override and run on the
session model / disable the feature). An implementation that treats "model not allowed" as one
uniform error will be observably different from the reference product on every policy surface.

---

## 2. Concrete claims

### 2.1 Model aliases and the alias → version table

**Claim 1 — The `model` setting accepts either an alias or a model name, and the model-name form
is provider-specific.**
Status: **OBSERVED-DOC** · Section: `## Available models`
Source: <https://code.claude.com/docs/en/model-config.md>

> "For the `model` setting in Claude Code, you can configure either:
> * A **model alias**
> * A **model name**
>   * Anthropic API: a full **[model name](...)**
>   * Amazon Bedrock: an inference profile ARN
>   * Microsoft Foundry: a deployment name
>   * Google Cloud's Agent Platform: a version name"

Clean-room need: **yes** — this is the top-level type of the model setting; an implementation
whose model field only accepts Anthropic IDs breaks on every third-party provider.

---

**Claim 2 — The alias set is exactly `default`, `best`, `fable`, `sonnet`, `opus`, `haiku`,
`sonnet[1m]`, `opus[1m]`, `opusplan`.**
Status: **OBSERVED-DOC** · Section: `### Model aliases`
Source: <https://code.claude.com/docs/en/model-config.md>

> "| **`default`** | Special value that clears any model override and reverts to the [runtime default for your account](#default-model-setting). Not itself a model alias
> | **`best`** | Uses the model the [`fable` alias resolves to](#fable-alias-resolution) where Fable is available to you, otherwise the same model as `opus`
> | **`fable`** | Uses the [Fable model for your provider](#fable-alias-resolution) for your hardest and longest-running tasks
> | **`sonnet`** | Uses the latest Sonnet model for daily coding tasks
> | **`opus`** | Uses the latest Opus model for complex reasoning tasks
> | **`haiku`** | Uses the fast and efficient Haiku model for simple tasks
> | **`sonnet[1m]`** | Uses Sonnet with a [1 million token context window](...) for long sessions. No effect when `sonnet` already resolves to Sonnet 5.5 or Sonnet 5 with their native 1M window
> | **`opus[1m]`** | Uses Opus with a [1 million token context window](...) for long sessions. No effect when `opus` already resolves to Opus 4.7 or later with its native 1M window
> | **`opusplan`** | Special mode that uses `opus` during plan mode, then switches to `sonnet` for execution |"

Clean-room need: **yes** — the alias vocabulary is a public, user-facing contract.

---

**Claim 3 — Alias resolution is provider-dependent: `opus`/`sonnet`/`haiku` resolve to *newest*
on the Anthropic API and to *older* versions on other providers.**
Status: **OBSERVED-DOC** · Section: `### Model aliases`
Source: <https://code.claude.com/docs/en/model-config.md>

> "The `opus`, `sonnet`, and `haiku` aliases resolve to the newest version on the Anthropic API and to an earlier version on some other providers:
>
> | Provider | `opus` | `sonnet` | `haiku` |
> | Anthropic API | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 |
> | Claude Platform on AWS | Opus 5.5 | Sonnet 4.6 | Haiku 4.5 |
> | Amazon Bedrock, Google Cloud's Agent Platform | Opus 5.5 | Sonnet 4.5 | Haiku 4.5 |
> | Microsoft Foundry | Opus 4.6 | Sonnet 4.5 | Haiku 4.5 |"

And the pinning escape hatch:

> "Aliases point to the recommended version for your provider and update over time. To pin to a specific version, use the full model name, for example `claude-opus-5-5`, or set the corresponding environment variable like `ANTHROPIC_DEFAULT_OPUS_MODEL`."

Clean-room need: **yes** — an implementation that hardcodes one alias table will be wrong on three
of four providers.

---

**Claim 4 — Alias resolution is observable at runtime and matches the documented Anthropic-API
column.**
Status: **OBSERVED-CLI** · Section: `### Model aliases` (verified against the doc's table)
Source: local execution, Claude Code 2.1.306

Command pattern:
`claude -p --model <alias> --debug api --debug-file <file> "ok"`

Observed `model=` values in the debug log:

| `--model` value | Resolved model ID observed |
| :- | :- |
| `opus` | `claude-opus-5-5` |
| `sonnet` | `claude-sonnet-5-5` |
| `haiku` | `claude-haiku-5-5` |
| `fable` | `claude-fable-5-1` |
| `best` | `claude-fable-5-1` |
| `opusplan` | `claude-sonnet-5-5` (non-plan execution phase) |
| `default` | `claude-opus-5-5` |

The `default` result matches the documented account-type default ("Pro, Max, Team, Enterprise, and
Anthropic API: defaults to Opus 5.5"). The `best` result matches "Uses the model the `fable`
alias resolves to where Fable is available to you". The `opusplan` result matches "In execution
mode: automatically switches to `sonnet`". Caveat: this host is *not* signed in to claude.ai and
serves a non-Anthropic model, so "Fable is available to you" resolved to the Anthropic-ID
catalogue rather than to a subscription-entitlement check.

Clean-room need: **yes** — confirms the alias layer is a real runtime indirection, not just
documentation.

---

**Claim 5 — `opusplan` is a *mode*, not a model: it uses `opus` during plan mode and `sonnet`
during execution.**
Status: **OBSERVED-DOC** · Section: `### \`opusplan\` model setting`
Source: <https://code.claude.com/docs/en/model-config.md>

> "* **In plan mode**: uses `opus` for complex reasoning and architecture decisions
> * **In execution mode**: automatically switches to `sonnet` for code generation and implementation"

Plus the context-window coupling:

> "The plan-mode Opus phase uses the same context window as the `opus` model setting, and the execution phase uses the same window as `sonnet`. ... To request 1M context for both phases where they don't, [set the model](#setting-your-model) to `opusplan[1m]`, for example with `/model opusplan[1m]`."

Clean-room need: **yes** — a mode-switching alias is a distinct feature from a static alias, and
its `[1m]` variant is a third form.

---

**Claim 6 — The alias table is versioned, and the page publishes exactly when each alias moved.**
Status: **OBSERVED-DOC** · Section: `## Version history`
Source: <https://code.claude.com/docs/en/model-config.md>

> "| v2.1.293 | `haiku` resolves to Haiku 5.5 on the Anthropic API |
> | v2.1.284 | `sonnet` resolves to Sonnet 5.5 on the Anthropic API |
> | v2.1.280 | `opus` resolves to Opus 5.5 on the Anthropic API, Claude Platform on AWS, Amazon Bedrock, and Google Cloud's Agent Platform |
> | v2.1.257 | `fable` resolves to Fable 5.1, except in Claude apps gateway sessions |"

Clean-room need: **medium** — not needed for behaviour, but it demonstrates that the reference
product treats alias→version as *data with a release history*, which is the right design for an
implementation that must not hardcode one frozen table.

---

### 2.2 The model precedence chain

**Claim 7 — The five-level model precedence order is stated explicitly, and
`/model` writes the `model` key into user settings.**
Status: **OBSERVED-DOC** · Section: `### Setting your model`
Source: <https://code.claude.com/docs/en/model-config.md>

> "You can configure your model in several ways, listed in order of priority:
> 1. **During session**: use `/model <alias|name>` to switch immediately, or run `/model` with no argument to open the picker.
> 2. **At startup**: launch with `claude --model <alias|name>`
> 3. **Environment variable**: set `ANTHROPIC_MODEL=<alias|name>`
> 4. **Settings**: configure permanently in your settings file using the `model` field
> 5. **[Default for new sessions](#set-a-default-model-for-new-sessions)**: set `ANTHROPIC_DEFAULT_MODEL=<alias|name>`"

And the persistence behaviour:

> "`/model` saves your choice as the default for new sessions by writing the `model` field in your user settings. In the picker:
> * `Enter`: switch model and save as your default
> * `s`: switch model for this session only and leave your default unchanged."

Also the exact persistence path, which matters because it is a *failure* mode too:

> "**Claude Code couldn't save your choice.** `/model` writes `model` to `~/.claude/settings.json`. If you can't write to that file, for example because another tool generates it or links it to a read-only copy, the model you chose lasts for the session and the next launch reads the old value."

Clean-room need: **yes** — this is the central contract of the whole page.

---

**Claim 8 — The precedence chain is observable, and a settings-file `env` block outranks the
ambient shell environment.**
Status: **OBSERVED-CLI** + **INFERRED** · Section: `### Setting your model`
Source: local execution, Claude Code 2.1.306

Observed (`--debug api`, reading the `model=` field):

| Configuration | Resolved model observed |
| :- | :- |
| `--model opus` (with `ANTHROPIC_MODEL=minimax/...` in the environment) | `claude-opus-5-5` — **the flag wins** |
| `--settings` file containing `{"env":{"ANTHROPIC_MODEL":"sonnet"}}` | `claude-sonnet-5-5` — **the settings `env` block wins over the ambient shell `ANTHROPIC_MODEL`** |

Reasoning for the second row: the ambient shell sets `ANTHROPIC_MODEL=minimax/minimax-m3.1-flash:free`
and the user settings file also sets `ANTHROPIC_MODEL` to the same value; the `--settings` file's
`env` block took effect instead. This is consistent with the documented model-config precedence
("Environment variable: set `ANTHROPIC_MODEL`" ranks above "Settings") only if the *settings-file*
`env` block is itself injected into the process environment before the model is resolved — i.e. the
settings `env` block is effectively an env-var source, and among env-var sources the settings-file
one wins. The model-config page itself does not state this ordering; it is stated in the settings
docs. **INFERRED**, not asserted as documented on this page.

Clean-room need: **yes** — a precedence implementation must decide whether "environment variable"
means *process env* or *effective env after settings injection*, and this observation shows the
reference product does the latter.

---

**Claim 9 — A resumed session keeps the model it was using, but an explicit launch-time model
overrides it.**
Status: **OBSERVED-DOC** · Section: `### Setting your model`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Resumed sessions started with `claude --resume`, `--continue`, or the `/resume` picker keep the model they were using when the transcript was saved. If the restored model has been retired or is excluded by [`availableModels`](#restrict-model-selection), the session falls through to the normal precedence order. On providers that use provider-specific deployment IDs rather than Anthropic model IDs, such as Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry, the transcript model isn't restored at all and the session resolves its model through the normal precedence order."

> "If your `model` setting is `haiku`, a session saved on a Haiku model resumes on the model that `haiku` resolves to now. For example, once `haiku` resolves to Haiku 5.5, a session saved on Haiku 4.5 resumes on Haiku 5.5."

> "A model you pick for the new launch with `--model` or `ANTHROPIC_MODEL` still takes precedence over the restored model. As of v2.1.195, so does an [`ANTHROPIC_DEFAULT_OPUS_MODEL`](#environment-variables) family variable."

Clean-room need: **yes** — resume-model semantics are a distinct branch of the resolver and are
easy to get wrong.

---

**Claim 10 — `ANTHROPIC_DEFAULT_MODEL` is *conditional*: it applies only when nothing else
selects a model, and it is ignored for certain values.**
Status: **OBSERVED-DOC** · Section: `#### Set a default model for new sessions`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Claude Code starts a new session on the variable's model only when none of these selects a model:
> * The `--model` flag
> * `ANTHROPIC_MODEL`
> * A `model` value in any settings file, including the choice you save with `/model`
> * An [organization default model](#organization-default-model)"

> "Claude Code ignores the variable in these cases, and the Default option resolves as if you hadn't set it:
> * You set it to `default`, `inherit`, `opusplan`, or `haiku`
> * [`enforceAvailableModels`](#enforce-the-allowlist-for-the-default-model) is on
> * Your organization's [model restrictions](#restrict-model-selection) exclude the model
> * The model isn't available to your account"

And the label it produces in the picker:

> "When the Default option resolves to the variable's model, the Default row in the `/model` picker shows the label Set by ANTHROPIC\_DEFAULT\_MODEL."

Clean-room need: **yes** — this is a *conditional* default, and the "ignored for `haiku`" rule is
the kind of detail that separates a faithful reimplementation from an approximate one.

---

### 2.3 The policy layer: `availableModels` and friends

**Claim 11 — `availableModels` entries match by family alias, version prefix, or full model ID,
and a prefix also permits later versions that extend it.**
Status: **OBSERVED-DOC** · Section: `## Restrict model selection`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Entries match a model family such as `sonnet`, a version prefix such as `claude-sonnet-4-5`, or a full model ID such as `claude-sonnet-4-5-20250929`. A version prefix also matches later model IDs that extend it with another segment, so `claude-fable-5` permits both Fable 5 and Fable 5.1, while `claude-fable-5-1` permits Fable 5.1 only."

And the narrowing rule:

> "Within the effective list, an entry naming a specific model in a family, whether a version prefix or a full model ID, disables that family's wildcard entry: `["sonnet", "claude-sonnet-4-5"]` allows only Sonnet 4.5 versions, not every Sonnet model."

And the merge rule:

> "When the managed settings Claude Code applies define `availableModels`, that list alone applies, apart from a [host platform that supplies its own](...): entries in user, project, or local settings cannot extend it, and Claude Code never merges `availableModels` across managed sources either ... Otherwise, lists from user, project, and local settings are [concatenated and deduplicated](...) like other array settings. Before Claude Code v2.1.175, entries from lower-precedence scopes merged into the managed list instead of being replaced by it."

Clean-room need: **yes** — the allowlist is a *matching algorithm* with prefix semantics, family
narrowing, and scope-conditional merge behaviour.

---

**Claim 12 — A blocked selection produces five different behaviours depending on *where* it was
set. This is the single most important detail on the page for a reimplementation.**
Status: **OBSERVED-DOC** · Section: `## Restrict model selection`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Claude Code handles any other blocked selection according to where the model was set:
> * **`/model`**: Claude Code rejects the switch with an error
> * **`--model` flag, `ANTHROPIC_MODEL`, or the `model` setting**: Claude Code replaces the value at startup with a warning naming both the requested and substituted models, and the session starts on the default model
> * **[`ANTHROPIC_DEFAULT_MODEL`](#set-a-default-model-for-new-sessions)**: Claude Code ignores the variable
> * **Subagent or teammate override**: Claude Code runs the subagent or teammate on a fallback model rather than failing the request. ...
> * **Skill or command override**: Claude Code ignores the override, including a blocked family alias, and the skill or command runs on the session model. ...
> * **`advisorModel` setting**: the advisor is disabled for the session
> * **`--advisor` flag**: Claude Code exits with an error at launch. ...
> * **`CLAUDE_CODE_AUTO_MODE_MODEL`**: Claude Code ignores the variable and picks the model for its [auto mode classifier requests](...) as if you hadn't set it"

And the family-alias *substitution* rule (which is different from outright rejection):

> "On the Anthropic API and [Claude Platform on AWS](...), a model family alias, `opus`, `sonnet`, `haiku`, or `fable`, resolves to its usual model when the allowlist permits that model. When the allowlist blocks that model, Claude Code substitutes the newest version of the family that the allowlist permits and shows a notice naming both the requested and substituted models. With `["sonnet", "claude-opus-4-6"]`, for example, both `/model opus` and `--model opus` select Claude Opus 4.6, the newest permitted Opus."

Clean-room need: **yes, critical** — this is the difference between "the model is not allowed"
being an error and being a *silent substitution*. A naive implementation gets all eight wrong.

---

**Claim 13 — `enforceAvailableModels` extends the allowlist to the Default option, and when the
default is blocked it degrades through an explicit 3-step ladder.**
Status: **OBSERVED-DOC** · Section: `### Enforce the allowlist for the Default model` and
`### Block specific models or versions`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Set `enforceAvailableModels: true` alongside a non-empty `availableModels` in managed settings to extend the allowlist to the Default option. This requires Claude Code v2.1.175 or later."

> "Otherwise, a Default option that would resolve to a blocked model steps down in this order:
> 1. The newest permitted version of the same family
> 2. The newest permitted model of each lower-cost family in turn: Sonnet, then Haiku
> 3. The first `availableModels` entry that names a permitted model
>
> If none of those is permitted, a session starting on the Default option [refuses to start](...) with an error that names the key to fix."

Clean-room need: **yes** — a defined, ordered degradation ladder is directly implementable and
worth copying as *behaviour* (not as code).

---

**Claim 14 — `deniedModels` and `availableModelsMatch` are managed-only, and the CLI warns and
ignores them elsewhere. This is observable.**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Block specific models or versions`
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "Two managed settings let you hold a release back, and both require Claude Code v2.1.283 or later:
> * [`deniedModels`](/docs/en/settings-reference#deniedmodels): list the models to block. A listed model is blocked even when `availableModels` permits it, and the key also works with no allowlist at all. ...
> * [`availableModelsMatch`](/docs/en/settings-reference#availablemodelsmatch): set it to `"exact"` so that each model ID in `availableModels` permits only the version it names. ..."

> "Claude Code reads both keys from managed settings only. If you set either one in user, project, or local settings or with `--settings`, Claude Code ignores it with a warning."

Observed (`--settings` file, Claude Code 2.1.306):

```
$ claude -p --settings /tmp/dm.json --model opus "ok"
These settings entries were skipped; the rest of each file is in effect:
  C:\Users\Admin\AppData\Local\Temp\dm.json (deniedModels): "deniedModels" is only honored from managed settings and was ignored here.
```

```
$ claude -p --settings /tmp/amm.json --model opus "ok"
These settings entries were skipped; the rest of each file is in effect:
  C:\Users\Admin\AppData\Local\Temp\amm.json (availableModelsMatch): "availableModelsMatch" is only honored from managed settings and was ignored here.
```

Both observed messages exactly match the documented "ignored it with a warning" behaviour, and
confirm that the warning names the offending file and key while the rest of the file stays in
effect. `--model opus` still resolved to `claude-opus-5-5` (the denied model was not applied).

Clean-room need: **yes** — a scope-guard that *refuses silently* is worse than one that warns.

---

**Claim 15 — `availableModels` enforcement is observable: it re-routes the session to a permitted
model and produces the documented fast-mode refusal string.**
Status: **OBSERVED-CLI** (+ partially OBSERVED-DOC) · Section: `## Restrict model selection`
Source: local execution, Claude Code 2.1.306

```
$ printf '{"availableModels":["sonnet"],"enforceAvailableModels":true}\n' > /tmp/ms.json
$ claude -p --settings /tmp/ms.json --model "minimax/minimax-m3.1-flash:free" --debug api --debug-file /tmp/dbg_am/d.txt "ok"
```

Debug log showed:

```
[DEBUG] Fast mode unavailable: Opus 5.5 is not in your organization's allowed models
...
[DEBUG] [API:timing] dispatching to firstParty model=claude-sonnet-5-5
```

The requested model was `minimax/minimax-m3.1-flash:free`; the session instead dispatched to
`claude-sonnet-5-5`, the only family the allowlist permitted. The fast-mode line quotes the
documented message "is not in your organization's allowed models" from the `## Restrict model
selection` section.

Note on scope: `enforceAvailableModels` was supplied via `--settings` here, and the settings
reference states that when an organization deploys managed settings, "Claude Code reads this key
from the managed source alone and ignores it in your other files". On this host no managed source
is deployed, so `--settings` was honoured. The *documented* managed-source override was therefore
**not** exercised.

Clean-room need: **yes** — the enforcement is real, the message is stable, and the substitution
result is observable.

---

**Claim 16 — The allowlist is enforced across every surface that can name a model, and the
surfaces behave differently.**
Status: **OBSERVED-DOC** · Section: `## Restrict model selection` (bulleted surface list) and
`### Surface coverage`
Source: <https://code.claude.com/docs/en/model-config.md>

> "When `availableModels` is set, the allowlist applies everywhere a user can specify a model:
> * **Main session model**: `/model`, the `--model` flag, the `ANTHROPIC_MODEL` environment variable, the `model` setting, [`ANTHROPIC_DEFAULT_MODEL`](#set-a-default-model-for-new-sessions), and the model restored when [resuming a session](#setting-your-model)
> * **Alias resolution**: the `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, and `ANTHROPIC_DEFAULT_FABLE_MODEL` environment variables cannot redirect an allowed alias to a model outside the list
> * **Fast mode**: `/fast` refuses to toggle when it would implicitly switch to an Opus model outside the list, with the message "is not in your organization's allowed models"
> * **Subagent and teammate models**: the `model` field in [subagent](...) frontmatter, the Agent tool's `model` parameter, [agent team](...) teammate models, `CLAUDE_CODE_SUBAGENT_MODEL`, and, on v2.1.197 and earlier, the model picker in the `/agents` wizard
> * **Skill and command models**: the `model` frontmatter in [skills and commands](...)
> * **Advisor model**: the configured [`advisorModel`](...) setting and the `--advisor` flag
> * **Background agent model**: the model selected in the [dispatch picker](...)"

And the surface-coverage table (server-managed vs MDM/managed-file) plus:

> "The model pickers on claude.ai and in the Desktop app hide or grey out models excluded by your organization's allowlist. The picker state is a convenience for users; it doesn't enforce the allowlist."

Clean-room need: **yes** — the *enforcement point list* is a checklist for a reimplementation.

---

### 2.4 Model overrides and provider adaptation

**Claim 17 — `modelOverrides` maps Anthropic model IDs to provider-native IDs and is applied at
the request boundary. This is observable.**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Override model IDs per version`
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "`modelOverrides` maps individual Anthropic model IDs to the provider-specific strings that Claude Code sends to your provider's API. When a user selects a mapped model in the `/model` picker, Claude Code uses your configured value instead of the built-in default."

> "Keys must be Anthropic model IDs as listed in the [Models overview](...). For dated model IDs, include the date suffix exactly as it appears there. Unknown keys are ignored."

> "`modelOverrides` works alongside `availableModels`. The allowlist is evaluated against the Anthropic model ID, not the override value, so an entry like `"opus"` in `availableModels` continues to match even when Opus versions are mapped to ARNs."

Observed:

```
$ printf '{"modelOverrides":{"claude-opus-5-5":"my-custom-opus-id"}}\n' > /tmp/mo.json
$ claude -p --settings /tmp/mo.json --model opus --debug api --debug-file /tmp/dbg_mo/d.txt "ok"
API Error: 400 my-custom-opus-id is not a valid model ID
...
[DEBUG] [API:timing] dispatching to firstParty model=my-custom-opus-id
```

The Anthropic ID `claude-opus-5-5` was rewritten to `my-custom-opus-id` in the outbound request,
exactly as documented. The upstream gateway rejected it, which is expected — the override did
its job.

Clean-room need: **yes** — a provider-agnostic catalogue with a per-deployment remap is essential
for any non-Anthropic backend, including the OpenAI-compatible gateways most alternatives use.

---

**Claim 18 — Provider-specific IDs that Claude Code cannot pattern-match silently lose their
capabilities; three companion env vars per pinned model restore them.**
Status: **OBSERVED-DOC** · Section: `### Customize pinned model display and capabilities`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Claude Code may also not recognize which features a pinned model supports. You can set the display name and description yourself and declare capabilities with companion environment variables for each pinned model."

> "| Capability value | Enables |
> | `effort` | Effort levels and the `/effort` command
> | `xhigh_effort` | The `xhigh` effort level
> | `max_effort` | The `max` effort level
> | `thinking` | Extended thinking
> | `adaptive_thinking` | Adaptive reasoning that dynamically allocates thinking based on task complexity
> | `interleaved_thinking` | Thinking between tool calls |"

> "When `_SUPPORTED_CAPABILITIES` is set, Claude Code enables the listed capabilities and disables the unlisted ones for the matching pinned model. When the variable is unset, Claude Code falls back to built-in detection based on the model ID."

The variables are `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` plus the `_NAME`,
`_DESCRIPTION`, and `_SUPPORTED_CAPABILITIES` suffixes; `ANTHROPIC_CUSTOM_MODEL_OPTION` takes the
same three suffixes.

Clean-room need: **yes** — this is the mechanism by which an alternative agent can offer effort
levels and thinking controls over an arbitrary OpenAI-compatible endpoint whose model names it does
not recognise. It is directly reusable as a design.

---

**Claim 19 — The `[1m]` suffix is a *selector suffix*, stripped before the request is sent, and
its semantics differ between "model has native 1M" and "model needs the variant".**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Extended context`
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "Fable 5.1, Fable 5, Sonnet 5 and later, Haiku 5.5, Opus 4.6 and later, and Sonnet 4.6 support a [1 million token context window](...) for long sessions with large codebases."

> "Fable 5.1, Fable 5, Sonnet 5 and later, Haiku 5.5, and Opus 4.7 and later run with the 1M window by default, with no `[1m]` suffix needed."

> "* Claude Code strips the suffix before sending the model ID to your provider.
> * Only append `[1m]` when the underlying model [supports 1M context](...)."

Observed: with `--model "claude-opus-4-6[1m]"`, the debug log recorded
`model=claude-opus-4-6[1m]` as the *selected* model (the suffix is retained in the internal
identifier). With `--model "minimax/minimax-m3.1-flash:free[1m]"` the identifier was likewise
`minimax/minimax-m3.1-flash:free[1m]`. In the latter case the request succeeded
(`Hi! 👋 What can I help you with today?`), so the suffix did not break an arbitrary provider ID —
it is stripped from what the provider receives.

Also documented:

> "To keep sessions at a 200K window, set `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` in your shell or in a [settings file](...). Claude Code removes the `[1m]` model variants from the model picker."

Clean-room need: **yes** — the suffix is part of the *user-facing model vocabulary*, and an
implementation needs both the selector semantics and the "does this model even have a 1M variant"
knowledge.

---

### 2.5 Unrecognised models: the 200K assumption and how to correct it

**Claim 20 — For an unrecognised model ID the product warns, assumes 200K, emits a structured
diagnostic line, and only then fails at the provider. This is observable end-to-end.**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Correct the window for a gateway or custom model ID`
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "Either of these startup warnings means Claude Code doesn't recognize your session's model ID, so it can't tell the model's context window and assumes 200K tokens:
> ```
> ⚠ Model "my-gateway-opus" isn't recognized · context assumed to be 200k tokens · ...
> Claude Code doesn't recognize the model "my-gateway-opus", so it assumes a context window of 200k tokens. Update Claude Code, or see https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id to set the window.
> ```"

Observed (Claude Code 2.1.306, `claude -p --model "my-gateway-opus" "ok"`):

```
Claude Code doesn't recognize the model "my-gateway-opus", so it assumes a context window of 200k tokens. Update Claude Code, or see https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id to set the window.
[claude-code:unrecognized_model] {"model":"my-gateway-opus","query_source":"sdk"}
API Error: 400 my-gateway-opus is not a valid model ID
```

The warning text, the doc-anchored URL, and the `[claude-code:unrecognized_model]` diagnostic line
(all three documented on this page or the errors page) all matched. Note the doc shows the
warning with a `⚠` prefix; the observed text omitted the glyph in this rendering but kept the
sentence identical.

Clean-room need: **yes, critical** — "assume a default window for unknown models, warn, and keep
going" is the behaviour any agent must have to work over a non-Anthropic endpoint.

---

**Claim 21 — The correction mechanisms for an unrecognised window are four, with different
precedence and different applicability.**
Status: **OBSERVED-DOC** · Section: `### Correct the window for a gateway or custom model ID` and
`#### Which IDs \`CLAUDE_CODE_MAX_CONTEXT_TOKENS\` applies to`
Source: <https://code.claude.com/docs/en/model-config.md>

> "* **A model newer than your Claude Code version**: run `claude update` in your shell. ...
> * **Your gateway's or provider's name for a model Claude Code knows**: add a [`modelOverrides`](#override-model-ids-per-version) entry that maps the Anthropic model ID to your ID, such as `"claude-opus-4-8": "my-gateway-opus"`. You can instead list your ID in a [`modelPicker`](#settings-reference#fields-for-modelpicker) row with `behavesAs` set to that model. ...
> * **A model with a 1M window**: append `[1m]` to the ID where you set the model, such as `claude --model 'my-gateway-opus[1m]'` in your shell. ...
> * **Any other window**: set [`CLAUDE_CODE_MAX_CONTEXT_TOKENS`](/docs/en/env-vars) to the window size in tokens in the environment that starts Claude Code, such as `CLAUDE_CODE_MAX_CONTEXT_TOKENS=400000`."

The applicability rule for the env var is the subtle part:

> "Claude Code treats an ID as a provider or custom spelling when it doesn't start with `claude-`, in any casing, or when it carries a suffix that Claude Code strips when reading the ID, such as the `@YYYYMMDD` date used on Google Cloud's Agent Platform. ...
> * If Claude Code can't resolve a provider or custom spelling to a model it recognizes and the ID doesn't contain `[1m]`, the variable applies directly and proactive compaction continues at the declared window.
> * If Claude Code can't resolve a provider or custom spelling to a model it recognizes and the ID contains `[1m]`, in any casing, Claude Code assumes a 1M window for it and the variable doesn't apply on its own. To correct the window while keeping proactive compaction, also set [`CLAUDE_CODE_DISABLE_1M_CONTEXT=1`]...
> * If the ID resolves to a model Claude Code recognizes, or the ID is a bare `claude-` name with no suffix for Claude Code to strip, in any casing, the variable takes effect only when you also set [`DISABLE_COMPACT`]..."

Clean-room need: **yes** — this is the "model-name-aware context accounting" problem, and the
ID-shape rules (`claude-` prefix, `@` date suffix, `[1m]`) are a compact, implementable spec.

---

### 2.6 Effort levels

**Claim 22 — Effort levels are `low`, `medium`, `high`, `xhigh`, `max`, and which are available
depends on the model; an unsupported level degrades to the highest supported level at or below.**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Adjust effort level`
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "| Model | Levels |
> | Fable 5.1 and Fible 5 | `low`, `medium`, `high`, `xhigh`, `max` |
> | Opus 5.5, Sonnet 5.5, Haiku 5.5, Opus 5, Sonnet 5, Opus 4.8, and Opus 4.7 | `low`, `medium`, `high`, `xhigh`, `max` |
> | Opus 4.6 and Sonnet 4.6 | `low`, `medium`, `high`, `max` |"

> "If you set a level the active model does not support, Claude Code falls back to the highest supported level at or below the one you set. For example, `xhigh` runs as `high` on Opus 4.6."

Observed (invalid level):

```
$ claude -p --effort bogus --model "my-gateway-opus" "ok"
Warning: Unknown --effort value 'bogus' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.
```

The observed warning lists exactly the five documented level names. Note the policy: an invalid
level is **warned and ignored** (degrade gracefully), in contrast to the `--model` case where an
invalid value is **sent to the provider and fails** — a deliberate asymmetry.

Clean-room need: **yes** — the graceful-degradation rule for unsupported levels is implementable
directly.

---

**Claim 23 — The effort resolution order is a documented three-step ladder with an explicit
default table.**
Status: **OBSERVED-DOC** · Section: `### Adjust effort level`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Claude Code resolves the session's effort level in this order, taking the first that applies:
> 1. An explicit choice: the [`CLAUDE_CODE_EFFORT_LEVEL`](/docs/en/env-vars#variables) environment variable, launching with `--effort`, or `/effort` in the session
> 2. Your settings: the level you saved for the model or an [`effortLevel`](/docs/en/settings-reference#effortlevel) key, with the precedence between them and across settings files stated at [`modelSettings`](/docs/en/settings-reference#modelsettings)
> 3. The model's default effort: `high` on every model that supports effort, except that Opus 5.5, Sonnet 5.5, and Haiku 5.5 default to `medium`, Opus 4.7 defaults to `xhigh`"

And the per-model persistence mechanism:

> "Claude Code saves the level per model, under the [`modelSettings`](/docs/en/settings-reference#modelsettings) key in your user settings, so each model keeps its own saved level."

> "`max` is the deepest reasoning level. Unless you set it through the `CLAUDE_CODE_EFFORT_LEVEL` environment variable, Claude Code applies `max` to the current session only."

Clean-room need: **yes** — the per-model saved-effort model is a clean design that a
reimplementation can adopt wholesale.

---

**Claim 24 — `ultrathink` is a per-turn in-context instruction, not an effort change.**
Status: **OBSERVED-DOC** · Section: `#### Use ultrathink for one-off deep reasoning`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Include `ultrathink` anywhere in your prompt to request deeper reasoning on that turn without changing your session effort setting. Claude Code recognizes the keyword and adds an in-context instruction. The effort level sent to the API is unchanged. Claude Code passes other phrases such as "think", "think hard", and "think more" through as ordinary prompt text and doesn't recognize them as keywords."

Clean-room need: **medium** — a documented, in-band, per-turn override that does not alter the
wire-level effort parameter.

---

**Claim 25 — `ultracode` is a session setting that lives alongside the effort slider but is not an
effort level, and it is unavailable unless the model supports `xhigh`.**
Status: **OBSERVED-DOC** · Section: `### Adjust effort level`
Source: <https://code.claude.com/docs/en/model-config.md>

> "The `/effort` slider also has an **Ultracode** toggle. Ultracode is a Claude Code setting rather than a model effort level: with it on, Claude orchestrates [dynamic workflows](/docs/en/workflows) for substantive tasks, at whichever effort level the session runs at."

> "The `--effort ultracode` flag and the Agent SDK `effortLevel: "ultracode"` value turn it on and also set the level to `xhigh`."

> "Ultracode is unavailable when:
> * [Workflows are turned off](/docs/en/workflows#turn-workflows-off)
> * The model doesn't support `xhigh` effort"

> "The persisted `effortLevel` setting and the `CLAUDE_CODE_EFFORT_LEVEL` environment variable don't accept `ultracode`."

Clean-room need: **low** — orthogonal to model configuration, but it demonstrates the
"setting vs. parameter" distinction that keeps effort handling sane.

---

### 2.7 Fallback chains and automatic fallback

**Claim 26 — A fallback chain is a per-turn failover list, capped at three, that does not merge
across settings files and does not fall back to a smaller context window.**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Fallback model chains`
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "Configure one or more fallback models and Claude Code tries them in order, showing a notice when it switches. The switch lasts for the current turn only, so your next message tries the primary model first again. Claude Code caps chains at three models after duplicate removal and ignores extra entries."

> "Set a chain for one session with the `--fallback-model` flag, which accepts a comma-separated list: `claude --fallback-model sonnet,haiku`"

> "The `--fallback-model` flag takes precedence over the `fallbackModel` setting. Each entry accepts a model name or alias, and `"default"` expands to the default model."

> "* **Outside the allowlist**: Claude Code drops any entry not permitted by [`availableModels`](#restrict-model-selection) when it reads the chain.
> * **Smaller context window during compaction**: the chain also covers [compaction](...), but Claude Code won't fall back to a model with a smaller context window than the primary's, since summarizing there would cut off part of the conversation first. If every fallback is smaller, compaction shows the original error and you can retry."

Observed — the chain is walked and each entry is validated in turn:

```
$ claude -p --model "my-gateway-opus" --fallback-model "another-bogus" "ok"
Claude Code doesn't recognize the model "my-gateway-opus", so it assumes a context window of 200k tokens. ...
[claude-code:unrecognized_model] {"model":"my-gateway-opus","query_source":"sdk"}
[claude-code:unrecognized_model] {"model":"another-bogus","query_source":"sdk"}
API Error: 400 another-bogus is not a valid model ID
```

The primary was tried, then the single fallback entry, and the error reported was the fallback's.
This confirms the chain is walked in order and that each entry goes through the same
unrecognised-model validation.

Also: `claude --help` (2.1.306) shows the flag's own wording, which differs slightly from the
doc:

> "--fallback-model <model> Enable automatic fallback to specified model(s) when the default model is overloaded or not available. Accepts a comma-separated list to try each in order. Re-tries the primary at the start of each user turn."

Clean-room need: **yes** — a per-turn failover list with a hard cap and a context-window guard
is directly implementable.

---

**Claim 27 — Automatic (content-based) fallback is a different mechanism with a fixed, published
target table.**
Status: **OBSERVED-DOC** · Section: `### Automatic model fallback`
Source: <https://code.claude.com/docs/en/model-config.md>

> "* **Fable 5.1, Fable 5, and Opus 5.5**: biology-flagged requests re-run on Opus 5, and cybersecurity-flagged requests re-run on Opus 4.8.
> * **Sonnet 5.5**: cybersecurity-flagged requests re-run on Sonnet 5. Biology-flagged requests end with a refusal instead, because Sonnet 5.5 has no biology fallback model.
> * **Opus 5**: cybersecurity-flagged requests re-run on Opus 4.8. Biology-flagged requests end with a refusal instead, because Opus 5 runs its own biology classifiers with no fallback model."

> "The fallback model is checked against [`availableModels`](#restrict-model-selection). When it is blocked, no fallback occurs. The refusal is shown as a normal error and the session's model is unchanged."

> "After a fallback, the session continues on the fallback model. To return to your original model, run [`/model`](#setting-your-model)."

> "The fallback model must also have a context window at least as large as the session's, or Claude Code doesn't switch and the flagged request ends with the same refusal."

Clean-room need: **low for interface, high for policy** — the *mechanism* (content-classifier
failover with a configurable consent prompt, via `switchModelsOnFlag`) is implementable; the
specific target table is Anthropic policy content that an independent implementation should
substitute with its own routing rules rather than copy.

---

### 2.8 Auto-compaction window

**Claim 28 — The auto-compact window has five configuration sites with a documented precedence,
and its value grammar distinguishes "tokens" from "thousands".**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Set the auto-compact window` and
`### Values and warnings for \`CLAUDE_CODE_AUTO_COMPACT_WINDOW\``
Source: <https://code.claude.com/docs/en/model-config.md> and local execution

Documented:

> "* **For the current model, in this session and later ones**: run `/autocompact` with a value, like `/autocompact 500k`. Claude Code saves it to your user settings under the current model in [`modelSettings`] ...
> * **For every model**: set [`autoCompactWindow`] in a settings file, such as `"autoCompactWindow": 200000` in `~/.claude/settings.json`. ...
> * **For one launch**: pass [`--autocompact`] when starting Claude Code. The flag overrides your saved setting for that launch without changing it ...
> * **In scripts and cloud environments**: set [`CLAUDE_CODE_AUTO_COMPACT_WINDOW`] to a token count such as `200000`. Unless Claude Code [ignores the value](#values-and-warnings-for-claude_code_auto_compact_window), the variable takes precedence over the command, the flag, and the `autoCompactWindow` setting. `/autocompact` then reports the override without saving."

> "The command and the flag accept a window size from 100K to 1M tokens, in any of these forms:
> * A plain token count, such as `200000`
> * A `k` or `M` suffix, such as `500k` or `1M`
> * A bare number from 100 to 1000, meaning thousands, so `200` sets 200,000"

And the asymmetry between command and env var:

> "A number with no suffix is read as that many tokens, so `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200` means 200 tokens even though `/autocompact 200` means 200,000."

Observed — both branches of that asymmetry:

```
$ CLAUDE_CODE_AUTO_COMPACT_WINDOW=200 claude -p --model "my-gateway-opus" "ok"
CLAUDE_CODE_AUTO_COMPACT_WINDOW="200" reads as 200 tokens, so Claude Code treats it as the 100k minimum. Set it to a size from 100k to 1M, such as 200k or 200000, or unset it.

$ CLAUDE_CODE_AUTO_COMPACT_WINDOW=200k claude -p --model "my-gateway-opus" "ok"
(no warning — accepted)
```

The observed warning text matches the documented warning table row "`reads as <N> tokens, so
Claude Code treats it as the 100k minimum`", and the `200k` form produced no warning, matching
"On Claude Code v2.1.304 or later, you can also write the number with `k` for thousands or `M` for
millions".

Clean-room need: **yes** — the env-var/command asymmetry is a genuine footgun in the reference
product; a reimplementation should pick one grammar and *not* reproduce the asymmetry, but must
know it exists in order to read the reference behaviour correctly.

---

**Claim 29 — Default auto-compaction thresholds differ by model class, and the fallback for an
unrecognised model is "assume 200K".**
Status: **OBSERVED-DOC** · Section: `### Default auto-compact thresholds`
Source: <https://code.claude.com/docs/en/model-config.md>

> "If you don't set an auto-compact window, Claude Code compacts when the conversation reaches the model's context limit, except in these sessions:
> * [Cloud sessions](...) compact as the conversation approaches the model's limit
> * Sonnet 4.6 and Opus 4.6 without [extended context](#extended-context) compact at the 200K boundary
> * When you set [`CLAUDE_CODE_DISABLE_1M_CONTEXT=1`], models with a native 1M window, such as Sonnet 5 and the Fable models, compact at the 200K boundary
> * Models running with a native 1M window compact before the window fills, at about 967K tokens by default. These include the Fable models, Sonnet 5 and later, Haiku 5.5, and Opus 4.7 and later. ...
> * Sessions on a model ID Claude Code doesn't recognize, such as an [LLM gateway](...) alias, compact at the context window Claude Code assumes for the ID"

Clean-room need: **yes** — the "compact *before* the window fills" rule (967K for a 1M model) is
a distinct behaviour from "compact at the limit", and it is what prevents a hard context-limit
failure.

---

### 2.9 Error and diagnostic surfaces

**Claim 30 — The model subsystem has a distinct set of user-facing error messages, and the CLI
ships a stable machine-readable diagnostic code.**
Status: **OBSERVED-DOC** + **OBSERVED-CLI** · Section: `### Setting your model` and
`### Correct the window for a gateway or custom model ID`
Source: <https://code.claude.com/docs/en/model-config.md>, <https://code.claude.com/docs/en/errors.md>,
and local execution

Documented message shapes referenced from this page:

- `There's an issue with the selected model` — "If you set the model with the `--model` flag, the `ANTHROPIC_MODEL` environment variable, or the `model` setting, Claude Code doesn't check it up front, and a mistyped value produces [There's an issue with the selected model](/docs/en/errors#theres-an-issue-with-the-selected-model) on the first request." (Errors page: "There's an issue with the selected model (claude-...). It may not exist or you may not have access to it. Run /model to pick a different model.")
- `Model is not a recognized model id` — used when a model switch is refused *without* sending a request; the errors page says "The string you passed to a model switch isn't one Claude Code can use as a model, so it refused the switch without sending a request and the session keeps its current model."
- `Model "<name>" is restricted by your organization's settings. Using <model> instead.` — org restriction substitution notice.
- `Model '<name>' is restricted by your organization's settings. Run /model to choose a different model.` — org restriction rejection from `/model <name>`.
- `is not in your organization's allowed models` — the fast-mode refusal, observed verbatim.
- `[claude-code:unrecognized_model]` — the structured diagnostic code, observed verbatim.

The distinction between the *up-front* check and the *first-request* check is an explicit design
point:

> "If you set the model with the `--model` flag, the `ANTHROPIC_MODEL` environment variable, or the `model` setting, Claude Code doesn't check it up front, and a mistyped value produces [There's an issue with the selected model](...) on the first request."

> "When you switch models through the [Agent SDK] `setModel()` method, through an app such as the [Desktop app](...), or from a device connected through [Remote Control](...), Claude Code checks the value at the switch: ... it confirms the ID with your provider the first time the session switches to it. ... an ID your provider doesn't offer is refused at the switch instead of failing on your next request."

Clean-room need: **yes** — an implementation should choose one of the two policies and state it;
the reference product uses both, keyed by the *entry point*.

---

**Claim 31 — `claude --help` exposes four model-related flags, and their wording is close to but
not identical to the doc's flag table.**
Status: **OBSERVED-CLI** (+ OBSERVED-DOC for the doc's table) · Section: `### Setting your model`,
`### Fallback model chains`, `### Adjust effort level`, `### Set the auto-compact window`
Source: local `claude --help` (2.1.306) and <https://code.claude.com/docs/en/cli-reference.md>

Observed help text (verbatim excerpts):

```
  --autocompact <auto|tokens>           Auto-compact window size (auto, or
                                        100k–1M tokens)
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --fallback-model <model>              Enable automatic fallback to specified
                                        model(s) when the default model is
                                        overloaded or not available. Accepts a
                                        comma-separated list to try each in
                                        order. Re-tries the primary at the start
                                        of each user turn.
  --model <model>                       Model for the current session. Provide
                                        an alias for the latest model (e.g.
                                        'fable', 'opus', or 'sonnet') or a
                                        model's full name.
```

The doc's CLI-reference table gives the flag names and semantics but not the `100k–1M` range
hint, and does not mention `ultracode` in the `--effort` row the way the help text's shorter
list does (the CLI reference does: "`--effort` | Set the effort level for the current session.
Options: `low`, `medium`, `high`, `xhigh`, `max`, or `ultracode`"). The discrepancy is minor but
worth noting: **the CLI's own help and the doc's flag table are not identical strings**, so an
implementation should not treat either as canonical without checking the other.

Clean-room need: **medium** — flag names and value grammars are user-facing contract.

---

### 2.10 Account- and org-level model policy

**Claim 32 — Organisation default model and organisation model restrictions are server-side
features delivered with entitlements, and they reach only Anthropic-API sessions.**
Status: **OBSERVED-DOC** · Section: `## Organization default model` and
`### Organization model restrictions`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Organization admins on Claude Enterprise plans can set a default model for Claude Code members from the claude.ai admin console, for the whole organization or per custom role. When one is set, the Default option resolves to that model. Requires Claude Code v2.1.196 or later."

> "The organization default reaches only sessions authenticated with the Anthropic API. To set a default anywhere else, including [LLM gateway](...) deployments, use the `model` key in [managed settings](/docs/en/managed-settings) instead."

> "Organization admins on Claude Enterprise plans restrict which models members can run by disabling individual models in the claude.ai admin console. This restriction is delivered with the account's entitlements when Claude Code authenticates, separate from any `availableModels` list in settings, and the server enforces the same restriction independently when a session is created. Requires Claude Code v2.1.187 or later."

> "Organization-scoped credentials, such as organization service keys, are not tied to a user, so the restriction does not apply to them."

> "Haiku models are always available and can't be disabled, so every member keeps at least one usable model."

> "An access change takes effect on new requests within about a minute; the `/model` picker reflects it the next time a session starts."

Clean-room need: **low as a client feature, high as a policy model** — the *client-side
behaviour* (picker greying, substitution notice, rejection message) is implementable; the
*server-side entitlement delivery* is not reproducible without an Anthropic account.

---

**Claim 33 — Organisation effort limits are per-model, per-role, and the lower of client-side and
server-side caps wins.**
Status: **OBSERVED-DOC** · Section: `## Organization effort limits`
Source: <https://code.claude.com/docs/en/model-config.md>

> "Your organization can cap the [effort level](#adjust-effort-level) in two ways. On a Claude Enterprise plan, organization admins set per-role effort limits, described below. On any plan and any provider, including Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry, the [`maxEffortLevel`](/docs/en/settings-reference#maxeffortlevel) managed setting caps effort on the client instead. When both apply to a model, the lower cap applies."

> "* Levels above the cap aren't offered in the `/effort` picker, and naming a higher level with `--effort` or `/effort` runs at the cap instead. ...
> * Caps are per model, so switching models can change which levels are available.
> * When several of your roles grant the same model, the least restrictive cap applies."

The client-side `maxEffortLevel` is fully implementable:

> "Cap the [effort level](...) a session can use, leaving lower levels available. Any higher level runs at the cap instead, including one from `/effort`, the `/model` picker, `--effort`, [`CLAUDE_CODE_EFFORT_LEVEL`](/docs/en/env-vars), a skill's or subagent's `effort` frontmatter, or the model's own default. Claude Code applies the cap itself before each request, so it holds on every provider ... When several scopes set a cap, the lowest applies."

Clean-room need: **yes** — a client-side effort cap is straightforward and useful.

---

## 3. Capability table

| # | Capability | Status | Key contract (exact names) |
| :- | :- | :- | :- |
| 1 | Alias → model ID resolution | OBSERVED-DOC + OBSERVED-CLI | `opus`, `sonnet`, `haiku`, `fable`, `best`, `default`, `opusplan`; provider-dependent table |
| 2 | `[1m]` context variant selector | OBSERVED-DOC + OBSERVED-CLI | `opus[1m]`, `sonnet[1m]`, `opusplan[1m]`, `claude-opus-4-6[1m]` |
| 3 | Model precedence chain | OBSERVED-DOC + OBSERVED-CLI | `/model` → `--model` → `ANTHROPIC_MODEL` → `"model"` → `ANTHROPIC_DEFAULT_MODEL` |
| 4 | In-session model switch + persistence | OBSERVED-DOC | `/model <name>`; picker `Enter` = save default, `s` = this session only; writes `~/.claude/settings.json` |
| 5 | Account-type default resolution | OBSERVED-DOC + OBSERVED-CLI | `default` → Opus 5.5 (Pro/Max/Team/Enterprise/API); Sonnet 4.5 on Foundry |
| 6 | Per-model effort + auto-compact persistence | OBSERVED-DOC | `modelSettings.<model>.effortLevel` / `.autoCompactWindow` / `.maxEffortLevel` |
| 7 | Effort levels + graceful degradation | OBSERVED-DOC + OBSERVED-CLI | `low`,`medium`,`high`,`xhigh`,`max`; unsupported → highest supported ≤ requested |
| 8 | Per-turn reasoning boost | OBSERVED-DOC | `ultrathink` keyword; wire effort unchanged |
| 9 | `ultracode` session setting | OBSERVED-DOC | `ultracode` setting, `--effort ultracode` → `xhigh` |
| 10 | Model allowlist | OBSERVED-DOC + OBSERVED-CLI | `availableModels` (array); prefix + family-narrowing match |
| 11 | Allowlist enforcement on Default | OBSERVED-DOC | `enforceAvailableModels: true` |
| 12 | Version pinning / blocking | OBSERVED-DOC + OBSERVED-CLI | `deniedModels`, `availableModelsMatch: "exact"` (managed-only, warns elsewhere) |
| 13 | Per-surface blocked-model behaviour | OBSERVED-DOC | 8 distinct behaviours (reject / substitute / drop / ignore / fallback / disable) |
| 14 | Org default + org restrictions | OBSERVED-DOC | server entitlements; Anthropic-API sessions only |
| 15 | Provider ID remapping | OBSERVED-DOC + OBSERVED-CLI | `modelOverrides` map (Anthropic ID → provider ID) |
| 16 | Capability declaration for unknown models | OBSERVED-DOC | `*_SUPPORTED_CAPABILITIES`: `effort`, `xhigh_effort`, `max_effort`, `thinking`, `adaptive_thinking`, `interleaved_thinking` |
| 17 | Picker customisation | OBSERVED-DOC | `modelPicker.options[].{model,label,description,behavesAs}`, `replaceBuiltInOptions` |
| 18 | Custom picker entry | OBSERVED-DOC + OBSERVED-CLI | `ANTHROPIC_CUSTOM_MODEL_OPTION` (+`_NAME`, `_DESCRIPTION`, `_SUPPORTED_CAPABILITIES`) |
| 19 | Fallback chain | OBSERVED-DOC + OBSERVED-CLI | `--fallback-model a,b` / `fallbackModel` array; cap 3; per-turn only |
| 20 | Content-classifier failover | OBSERVED-DOC | `switchModelsOnFlag` bool; target table per model family |
| 21 | Auto-compact window | OBSERVED-DOC + OBSERVED-CLI | `/autocompact`, `--autocompact`, `autoCompactWindow`, `modelSettings.*.autoCompactWindow`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW` |
| 22 | Unknown-model window assumption | OBSERVED-DOC + OBSERVED-CLI | 200K default; `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `CLAUDE_CODE_DISABLE_1M_CONTEXT`, `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT` |
| 23 | Model-switch hook | OBSERVED-DOC | `PreModelSwitch` hook can block or confirm a switch |
| 24 | Startup model warnings | OBSERVED-DOC | retirement/remap warning; stderr in `-p`; `modelUsage` in result JSON |
| 25 | Prompt-cache control per tier | OBSERVED-DOC | `DISABLE_PROMPT_CACHING[_HAIKU|_SONNET|_OPUS|_FABLE]` |

---

## 4. Dependencies

| Dependency | Required for | Notes |
| :- | :- | :- |
| Anthropic API (`api.anthropic.com`) | Account-type defaults, real alias→ID table, `[1m]` plan entitlements, prices in the picker, org defaults | Not reachable from this host |
| A model provider (Bedrock / Vertex Agent Platform / Foundry / Claude Platform on AWS) | Provider-specific alias resolution, `modelOverrides` targets, startup availability checks | Model IDs are ARNs / version names / deployment names |
| An LLM gateway (`ANTHROPIC_BASE_URL`) | Gateway model discovery (`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`), custom picker entries, unknown-ID window assumption | The gateway's `/v1/models` supplies picker rows |
| claude.ai account (Enterprise) | Org default model, org model restrictions, per-role effort limits, Fable availability, usage-credit consent | Delivered as server entitlements at authentication |
| Network access | Every model call; fetching `availableModels` from server-managed settings; entitlement checks | |
| Anthropic Claude platform | Effort levels, adaptive thinking, extended thinking, 1M context | Declared via `*_SUPPORTED_CAPABILITIES` for third-party IDs |
| Local filesystem | `~/.claude/settings.json` (model + `modelSettings` persistence), managed settings file, per-project `.claude/settings.json` | |
| `claude` CLI ≥ v2.1.236 / v2.1.283 / v2.1.304 | `ANTHROPIC_DEFAULT_MODEL`; `deniedModels` + `availableModelsMatch`; `k`/`M` suffixes | Version gates are stated per feature |

---

## 5. Limitations of this investigation

1. **Not connected to the Anthropic API.** Alias→ID resolution was confirmed against the
   *Anthropic-API column* of the doc's table via the CLI's own debug output, but the entitlement
   logic behind `best`/`fable` ("where Fable is available to you") was not exercised.
2. **Non-Anthropic backend.** `ANTHROPIC_BASE_URL` points at OpenRouter. Provider-specific
   behaviour (Bedrock ARNs, Vertex version names, Foundry deployments, Mantle) is **OBSERVED-DOC
   only**.
3. **No managed settings deployed.** `deniedModels`, `availableModelsMatch`, and the
   managed-source override of `enforceAvailableModels` were exercised only through `--settings`,
   which the CLI (correctly) treats as non-managed and therefore ignored the first two. Their
   *managed* behaviour is **OBSERVED-DOC only**.
4. **No interactive TUI.** The `/model` picker, the `/effort` slider, `/autocompact`, the
   `Enter`/`s`/`Tab` key semantics, and the grayed-out picker rows could not be exercised; those
   are **OBSERVED-DOC only**.
5. **Organisation features not testable.** Org default model, org restrictions, per-role effort
   limits, usage-credit consent, and Fable credit prompts require an Enterprise account.
6. **Content-classifier fallback not testable.** Triggering a safety classifier is neither
   reproducible nor appropriate here; the target table is **OBSERVED-DOC only**.
7. **The API request body was not captured.** The debug log exposes the *selected model
   identifier* but the CLI did not write an `api-request*` capture to the debug directory in this
   configuration, so the exact wire-level JSON (`model`, `effort`, `thinking`, betas) was **not**
   directly observed. Effort's wire parameter is therefore **OBSERVED-DOC only**.

---

## 6. Unresolved questions (UNKNOWN)

1. **Exact wire-level request shape for effort.** Whether `effort` is sent as a top-level request
   parameter, an `anthropic-beta` header, or an output-config block — and its exact value
   vocabulary — is not established. The doc says only "The effort level sent to the API is
   unchanged" for `ultrathink`.
2. **The `[1m]` suffix's precise stripping point.** Observed only that the internal identifier
   retains the suffix (`model=claude-opus-4-6[1m]`) while the provider received a working
   request for a suffixed custom ID. Whether the suffix is stripped in the request body or by a
   header is not established.
3. **The exact wording and destination of the substitution notice** ("a warning naming both the
   requested and substituted models") for a blocked `--model`. On this host the allowlist
   substitution was visible only as the resolved model ID and the fast-mode refusal string; the
   user-facing notice text was not captured.
4. **Whether `availableModels` in a *managed* source replaces rather than concatenates across
   user/project/local scopes** was only exercised via `--settings`, where concatenation applies.
5. **The "account recorded model" mechanism** (an Enterprise account recording the user's `/model`
   choice on the claude.ai account) — how it is transmitted, and its exact interaction with
   `enforceAvailableModels`, is not observable without an Enterprise account.
6. **`modelPicker` `behavesAs` semantics at runtime.** Documented as applying "that known model's
   capabilities and effort defaults", but the observable effect was not measured.
7. **The exact mapping from `modelPicker` rows to the "Default" and "current session model" rows
   described for `replaceBuiltInOptions: true`** — the row set ("only these rows, **Default**, and
   a row for the model the session is already using") was not visually verified.
8. **How `opusplan` switches at the plan/execution boundary in a live session** — the observable
   here was only the execution-phase model (`claude-sonnet-5-5`).
9. **Whether the `best` alias falls back to `opus` in the absence of Fable entitlement.** The
   doc says it does; on this host Fable was always "available", so the fallback branch was not
   exercised.
10. **The internal meaning of "newest version of the family that the allowlist permits"** — the
    ordering used to pick among permitted versions of a family is not specified.

---

## 7. Clean-room implementation opportunity (per major feature)

### 7.1 Model resolution core

**Observable contract.** A single function `resolveModel(ctx) -> {modelId, source, contextWindow,
capabilities}` that, given the effective settings snapshot, returns the model *and where it came
from*.

**Idiomatic implementation.** Model it as a chain of *providers*, each of which proposes a
candidate, and take the first non-`nil` proposal:

```
sources (highest first):
  sessionOverride (/model, per-session)   -> {modelId, persist: false}
  cliFlag (--model)                       -> {modelId, persist: false}
  envVar (ANTHROPIC_MODEL)                -> {modelId, persist: false}
  settingsFile ("model")                  -> {modelId, persist: true}
  envVarDefault (ANTHROPIC_DEFAULT_MODEL) -> {modelId, conditional: true}
  orgDefault                               -> {modelId}
  accountTypeDefault                       -> {modelId}
```

Each source returns `nil` when it does not apply, which makes the precedence chain explicit
rather than a tangle of `if`s. Return the winning source's *name* alongside the value — the
reference product's own troubleshooting section ("A new session starts on a different model than
you picked") enumerates exactly the causes, which only works because provenance exists.

**Do not copy.** The Anthropic alias→version table. Instead, ship your own catalogue as
**data** — a JSON/YAML file mapping provider → family → default version — so it can be updated
without a release, exactly as the reference product's `## Version history` table implies it does.

### 7.2 Alias layer

**Observable contract.** Accept `opus`, `sonnet`, `haiku`, `fable`, `best`, `default`, `opusplan`
plus an optional `[1m]` suffix; resolve to a concrete ID for the *active provider*.

**Idiomatic implementation.** A `ModelRegistry` with per-provider alias tables and a
`resolve(alias, provider, opts)`. Make `best` and `default` *composites* (functions over other
aliases) rather than table rows, so "best = fable if available else opus" is expressed once.
Implement the `[1m]` suffix as a *modifier* applied after resolution — a boolean
`contextVariant: "1m"` — rather than by string surgery on the ID, and strip it at the request
boundary in one place.

### 7.3 Policy layer (`availableModels` and friends)

**Observable contract.** A named-model selection outside the allowlist produces a
*surface-specific* outcome, not a single error.

**Idiomatic implementation.** Two-phase design:

*Phase 1 — admission.* `isAllowed(modelId) -> {allowed, reason}`. Implement prefix matching as
described: an entry matches a model ID if the ID equals the entry or extends it with another
`-`-separated segment; a family alias matches its whole family; and a specific entry in a family
*narrows* that family's wildcard within the same list.

*Phase 2 — per-surface reaction.* A dispatch table keyed by the *origin* of the selection:

| Origin | Reaction |
| :- | :- |
| interactive switch | reject with an error |
| launch flag / env / settings key | substitute (newest permitted version of the family, else the default) and warn naming both |
| default-for-new-sessions | ignore the value |
| subagent / teammate | fall back to another model, do not fail the request |
| skill / command override | ignore the override, run on the session model |
| advisor config | disable the feature |
| fallback chain | drop the entry at chain-read time |

This table is the actual product knowledge. It is not Anthropic-specific and can be reimplemented
verbatim as *behaviour*.

**Design advice.** Do not implement the allowlist as a boolean. Implement it as a function that
returns `(permitted, resolution, explanation)` — the product repeatedly needs to explain
*which* model it chose and *why* ("a notice naming both the requested and substituted models"),
and a boolean forces you to reconstruct that later.

### 7.4 Provider adaptation (`modelOverrides` + capability declaration)

**Observable contract.** Users can remap each catalogue model to a provider-native ID, and can
declare which features a remapped model supports.

**Idiomatic implementation.** A `Map<CanonicalId, ProviderId>` applied at the transport
boundary, plus a `Map<ProviderId, Set<Capability>>` consulted by the feature layer. The
capability set is the elegant part: instead of pattern-matching model names to decide whether to
offer `/effort`, ask the registry. That converts a pile of `startsWith("claude-opus")` heuristics
into one explicit lookup, and it makes your agent work over any OpenAI-compatible endpoint whose
model names you do not control.

### 7.5 Unknown-model handling

**Observable contract.** An unrecognised model ID gets a *default* context window (200K), a
warning, and a machine-readable diagnostic code; the session continues.

**Idiomatic implementation.** Model the context window as a function of the ID:

```
contextWindow(id):
  if registry.knows(id):              return registry.window(id)
  if id ends with "[1m]":             return 1_000_000
  if id matches provider-shape:       return envOverride ?? 200_000
  else:                              return envOverride ?? 200_000   # only with DISABLE_COMPACT
```

and emit a structured diagnostic (`[your-agent:unrecognized_model] {model, assumed_window}`) on
stderr. This is directly reusable from the observed contract.

### 7.6 Effort levels

**Observable contract.** Five named levels; a per-model saved level; a resolution ladder
(explicit → settings → model default); graceful degradation to the highest supported level at or
below the requested one; a client-side cap; and a per-turn in-band override keyword.

**Idiomatic implementation.** An enum with an ordering; a `supports(level)` predicate per model;
a resolver returning `(level, source)`; and a cap applied as `min(requested, cap)` *after*
resolution. Keep the per-model saved level in a `map[modelId]level` structure — it is what lets
each model keep its own preference, and it makes the "top-level default vs per-model override"
precedence a two-line function.

### 7.7 Auto-compact window

**Observable contract.** Five configuration sites with a stated precedence, a value grammar, and a
per-model override.

**Idiomatic implementation.** One `compactWindow(ctx) -> tokens` resolver with the same
source-chain shape as the model resolver, plus a parser for the size grammar. **Recommendation:
use one grammar everywhere.** The reference product has an asymmetry (a bare `200` means 200,000
to `/autocompact` but 200 tokens to `CLAUDE_CODE_AUTO_COMPACT_WINDOW`); reproducing that would
be copying a defect, not a contract. Document the difference in your own release notes instead.

### 7.8 Fallback chain

**Observable contract.** An ordered list, per-turn scope, capped at three, deduplicated, filtered
by the allowlist at read time, and refusing to fail over to a smaller context window during
compaction.

**Idiomatic implementation.** A `FallbackChain` value object with `candidates(primary, ctx)`
returning a filtered, ordered list. The context-window guard is worth implementing explicitly:
without it, a failover during summarisation can truncate the conversation it was about to
summarise.

### 7.9 Diagnostic and error surface

**Observable contract.** Distinct, named error classes with stable identifiers, and a distinction
between a *rejected switch* (no request sent) and a *failed first request*.

**Idiomatic implementation.** Define error classes as data (a code, a human message, and the
remedy), so the CLI, the TUI, and the programmatic API all render the same underlying fact. Emit
the machine-readable diagnostic on stderr with a stable prefix, so scripts can grep it — the
observed `[claude-code:unrecognized_model]` line is exactly this pattern, and it is worth
reproducing as a *pattern* (stable code + JSON payload), not as a copy of the code string.

### 7.10 What *not* to reproduce

- The Anthropic alias→version table (data, and it changes per release).
- The content-classifier fallback target table (Anthropic policy, not an interface contract).
- The exact system-prompt text, internal routing, or the proprietary binary.
- The env-var vs command value-grammar asymmetry (a defect, not a contract).
- The fact that `--model`/`ANTHROPIC_MODEL` are not validated up front while SDK `setModel()` is
  — pick one policy and document it; the reference product's split is a consequence of two
  different integration surfaces, not a principle.

---

## 8. Evidence index

| Artifact | Path / source |
| :- | :- |
| Primary doc page (fetched markdown, 120,934 bytes, 1,058 lines) | `agent-reference-shots/docs-cache/model-config-fresh.md` |
| Doc page (live) | <https://code.claude.com/docs/en/model-config.md> |
| Doc index confirming the page exists | <https://code.claude.com/docs/llms.txt> (lines 387, 411) |
| Settings-key schemas (`availableModels`, `availableModelsMatch`, `deniedModels`, `effortLevel`, `maxEffortLevel`, `modelOverrides`, `modelPicker`, `modelSettings`, `fallbackModel`, `autoCompactWindow`, `switchModelsOnFlag`, `model`) | `agent-reference-shots/docs-cache/settings-reference.md` |
| Env-var definitions | `agent-reference-shots/docs-cache/env-vars.md` (lines 157, 210, 227, 272, 315) |
| CLI flag table | `agent-reference-shots/docs-cache/cli_reference.md` (lines 72, 88, 93, 108) |
| Error message texts | `agent-reference-shots/docs-cache/errors.md` (lines 168, 2425, 2444, 2528) |
| `claude --help` (model/effort/fallback/autocompact flags) | `agent-reference-shots/cli-help/claude-help.txt` (lines 28, 84, 94, 135) |
| CLI version | `claude --version` → `2.1.306 (Claude Code)` |
| Observed alias resolutions | `claude -p --model <alias> --debug api --debug-file <f> "ok"`, reading `model=` from the debug log |
| Sanitized observed transcript, part 1 (unrecognised-model warning, invalid `--effort`, fallback-chain walk, auto-compact window warnings) | `agent-reference-shots/model-config-observed/model-config-observed.txt` |
| Sanitized observed transcript, part 2 (alias table, alias pinning, `modelOverrides`, allowlist re-route, managed-only key warnings, settings-`env` precedence) | `agent-reference-shots/model-config-observed/model-config-observed-2.txt` |

**No screenshots.** The interactive surfaces that remain unverified (`/model` picker,
`/effort` slider, `/autocompact`, org-restriction greyed-out rows) are TUI-only, and this
investigation ran headless with no interactive terminal. Capturing them would require driving the
published CLI's interactive UI under a pseudo-terminal, which was out of scope for the
non-interactive evidence pass; those surfaces are therefore marked **OBSERVED-DOC only** rather
than shown.

**Sanitisation.** No secrets, tokens, or personal data are recorded in this document. The
`ANTHROPIC_AUTH_TOKEN` value present in the local user settings file was **not** read into any
artifact; only the `ANTHROPIC_BASE_URL` host and the (non-secret) model ID string are quoted.
