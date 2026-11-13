# Claude Code — Area 7 Evidence: Model Selection, Conversation Context, Long Sessions, Session Resumption

**Scope of this document.** Area 7 of a multi-area black-box study of Claude Code as a
reference product for an independently implemented AI coding agent. The area covers:
model selection (`/model`, aliases, `--model`, settings/env precedence), effort
levels, auto-compaction and context-window management, `--resume` / `--continue` /
`--fork-session` / `/branch`, background session attach/stop/respawn, and the
`--autocompact` flag.

**Compliance boundary.** Claude Code is proprietary and closed source. Anthropic's
Consumer ToS §3 and Commercial ToS §D.4 prohibit decompiling, reverse engineering,
disassembling, or reducing the Services to human-readable form, and the
`code.claude.com/docs/en/legal-and-compliance` page states "The Claude Code binary
must not be modified." **No decompilation, disassembly, de-minification, source-map
extraction, binary modification, credential-store reading, or private-API
reconstruction was performed.** The only inspections used were (a) public
Anthropic documentation fetched over HTTPS, and (b) the published CLI's own
user-facing help and inspection surfaces, plus the JSONL session files the CLI
itself writes to the user's own data directory as a normal product side effect.
See `agent-reference-shots/TERMS-NOTES.md`.

**Machine caveat that shapes every finding.** This machine runs Claude Code
2.1.306 (native build, win32-x64) against a **custom `ANTHROPIC_BASE_URL`**
(`https://openrouter.ai/api`) serving a **non-Anthropic model**
(`minimax/minimax-m3.1-flash:free`). `claude doctor` reports "Not connected to the
Anthropic API" and "Not signed in to claude.ai". Therefore any behaviour gated on
an Anthropic subscription, on `api.anthropic.com`, on real alias resolution
(`opus` → Opus 5.5 etc.), or on gateway `/v1/models` discovery is **INFERRED from
docs**, not OBSERVED here. Everything marked OBSERVED-CLI was actually executed
and its output is quoted.

**Classification legend.**
`OBSERVED-DOC` = stated in a public Anthropic document fetched during this
investigation (URL given). `OBSERVED-CLI` = personally executed against the
published CLI (exact command + output given). `INFERRED` = a conclusion drawn
from evidence, with the reasoning stated. `UNKNOWN` = the available evidence
cannot establish it. No claim is made about internal model behaviour, private
system prompts, proprietary source code, training data, model weights, or hidden
APIs.

---

## 1. Executive summary

Claude Code exposes model choice as a **four-layer resolution system** that is
consistent everywhere it appears — picker, flag, environment variable, settings
file — and that same layering reappears for effort and for the auto-compact
window. The precedence for the model is:

> `/model <alias|name>` (live, in-session) → `--model` → `ANTHROPIC_MODEL` →
> `"model"` in a settings file → `ANTHROPIC_DEFAULT_MODEL`

The precedence for **effort** is:

> `CLAUDE_CODE_EFFORT_LEVEL` → `--effort` → `/effort` → `modelSettings.*.effortLevel`
> → `effortLevel` → the model's own default

The precedence for the **auto-compact window** is (highest first):
`CLAUDE_CODE_AUTO_COMPACT_WINDOW` (env) → `--autocompact` → `/autocompact`
(per-model, saved) → `autoCompactWindow` (top-level setting) → the model's tuned
default.

Three findings dominate the implementation picture.

**First, model selection is a *policy* surface, not just a dropdown.** Beyond
`opus`/`sonnet`/`haiku`/`fable` aliases, the reference product ships a full
governance layer: `availableModels` (allowlist), `enforceAvailableModels`,
`deniedModels`, `availableModelsMatch`, `modelOverrides` (map Anthropic IDs to
Bedrock ARNs / Foundry deployment names), `modelPicker` (replace the picker
lineup), `switchModelsOnFlag` (safety-classifier behaviour), `fallbackModel`
(availability chain, capped at three), and `maxEffortLevel` (client-side effort
cap). An independent implementation that only offers a model dropdown will be
markedly less capable at enterprise deployment, which is where this product
actually differentiates itself.

**Second, context management is a first-class, *measurable* subsystem.** The
reference product does not treat "the context ran out" as an error condition: it
compacts, and it records what it did in a structured, machine-readable way. Five
auto-compaction events were captured directly in a session transcript on this
machine, each a `system`/`compact_boundary` entry carrying `trigger: "auto"`,
`preTokens`, `postTokens`, a monotonic `cumulativeDroppedTokens` session counter,
`durationMs` (40–64 s of wall time), a `preCompactDiscoveredTools` snapshot, and
`preservedSegment` / `preservedMessages` naming the specific message UUIDs that
survived un-summarised. That is a durable, auditable record of context
management, not a log line. An independent implementation can do the same thing
and thereby gain a genuine advantage the reference product does not offer: a
**versioned, documented** schema for it.

**Third, session resumption is layered over a durable append-only transcript.**
Transcripts are JSONL at `~/.claude/projects/<sanitised-cwd>/<session-id>.jsonl`
(confirmed on disk). Resumption restores conversation history, model, agent,
permission mode, active goal, and unexpired scheduled tasks — but explicitly does
*not* restore `--mcp-config`, `--settings`, `--plugin-dir`, `--fallback-model`, or
`/add-dir` directories. The product's own docs warn that the JSONL entry format
"is internal to Claude Code and changes between versions, so scripts that parse
these files directly can break on any release" — a deliberate warning that a
clean-room implementation should take seriously and improve on.

**Also notable.** The two validation behaviours differ in kind, and this is
directly observable: an **unknown effort value is a warning and is ignored**
(`Warning: Unknown --effort value 'banana' — ignoring it and using the default
effort`), while an **unknown `--autocompact` value is a hard error** that
aborts the launch. An unknown *model* ID is neither: Claude Code warns that it
cannot determine the context window, assumes 200 000 tokens, emits a
`[claude-code:unrecognized_model]` diagnostic, and then lets the request fail at
the provider with `API Error: 400 … is not a valid model ID`. Three different
failure policies for three different kinds of bad input — a clean-room
implementation should pick one coherent policy per class and document it.

**What an independent implementation should build.** A model-resolution layer
with an explicit, testable precedence chain and a policy/admin surface; an
effort layer with per-model defaults and caps; a context manager that measures
and *records* every compaction decision; a session store that is durable,
append-only, and resumable with well-specified restore semantics; and a
background-session supervisor that can attach, stop, and respawn. All of this is
achievable from public documentation plus black-box observation; none of it
requires reading Anthropic's implementation.

---

## 2. Detailed findings

### F1 — Model selection precedence is a documented, five-level chain

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/model-config

| Priority | Mechanism | Scope |
|---:|---|---|
| 1 | `/model <alias\|name>` during a session | Immediate session change |
| 2 | `claude --model <alias\|name>` | Current launch |
| 3 | `ANTHROPIC_MODEL=<alias\|name>` | Current launch |
| 4 | `"model": "<alias\|name>"` in a settings file | Persistent; settings-scope precedence applies |
| 5 | `ANTHROPIC_DEFAULT_MODEL=<alias\|name>` | Default for new sessions |

Settings-file precedence itself is layered: **managed > local > project > user**
for most keys, with `--settings` overriding `settings.json` files for the keys
it names.

`/model` with no argument opens a picker; `/model <name>` switches directly and
behaves like pressing `Enter` in the picker. In the picker, `Enter` switches
**and saves the choice as the default**; `s` switches for the current session
only. `/model` saves to the `model` field in `~/.claude/settings.json`. In
non-interactive mode `/model` applies to the current session only and is not
saved (v2.1.205+). `PreModelSwitch` hooks can block a model switch or require
confirmation. A typo in `--model`, `ANTHROPIC_MODEL`, or the `model` setting is
**not validated up front** — it fails on the first request.

**Clean-room opportunity:** implement model resolution as a *pure function*
`resolve_model(effective_config) -> ModelRef` over an ordered list of sources,
with a resolver registry keyed by source name. Make the resolved result part of
your startup manifest and emit it on every turn, so the "which model am I
actually on, and why" question is always answerable. Implement `PreModelSwitch`
as a generic pre-action hook point rather than a model-specific one.

---

### F2 — Model aliases are a moving, pinnable set with a special "not-an-alias" default

**Status: OBSERVED-DOC** (alias *resolution* is not observable on this machine)
**Source:** https://code.claude.com/docs/en/model-config

| Alias | Behaviour |
|---|---|
| `default` | Special value that **clears** a model override and resolves to the runtime/account default. Explicitly *not* itself a model alias. |
| `best` | Uses what `fable` resolves to where Fable is available; otherwise the same model as `opus`. |
| `fable` | The provider's Fable model. |
| `sonnet` | Latest Sonnet for daily coding. |
| `opus` | Latest Opus for complex reasoning. |
| `haiku` | Fast, efficient Haiku model. |
| `sonnet[1m]` | Sonnet with a 1 M-token context window; no effect if `sonnet` already resolves to a natively-1M model. |
| `opus[1m]` | Opus with a 1 M-token context window; no effect on Opus 4.7+ which is natively 1M. |
| `opusplan` | `opus` during plan mode, then `sonnet` during execution. |
| `opusplan[1m]` | Requests 1 M context for both the Opus planning phase and the Sonnet execution phase. |

Aliases move over time. To pin a version, use the full model name or one of:
`ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`,
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_FABLE_MODEL`.

The docs also state plainly that "`ANTHROPIC_BASE_URL` changes the request
destination; it does **not** select the model."

**INFERRED (reasoning):** the alias layer is a *deferred binding*, not a fixed
name. Each alias resolves at (or near) request time to a concrete provider model
ID, and the resolution can change when the vendor ships a new version. A
transcript that recorded "haiku" and is resumed later will run on whatever
`haiku` resolves to *now* — the docs say this explicitly. This means an alias
recorded in a durable session record is **not** a stable identity, and a resume
must re-resolve it. A clean-room implementation must therefore store both the
alias the user asked for and the concrete ID that was actually used, and must
re-resolve the alias on resume.

**Clean-room opportunity:** model your aliases as a two-level indirection
(`AliasSpec -> ProviderModelRef`) with an explicit, inspectable resolution
record. Record both in every session entry. Provide a "pin" mechanism
(per-family override) as a first-class feature rather than a workaround, and
expose a command that prints the current alias→ID resolution table, because
users will need to debug it.

---

### F3 — The `/model` picker doubles as the effort slider

**Status: OBSERVED-DOC**
**Sources:** https://code.claude.com/docs/en/model-config, https://code.claude.com/docs/en/commands

`/model` opens the picker; in the picker, **left/right arrow keys adjust the
effort level while selecting a model**. The `/effort` command opens an effort
slider where `Enter` saves the level as the model's default, `s` applies it only
to the current session (v2.1.257+), and `Tab` toggles Ultracode.

Because a switch can invalidate the prompt cache, `/model` and `/effort` may
present a **cache warning** for confirmation. From
https://code.claude.com/docs/en/interactive-mode: "`/model`: once you confirm
the cache warning, if Claude Code shows one, Claude Code applies your change to
the next request it makes in that turn" and the same for `/effort`. `/fast` is
different: "Claude Code keeps the fast mode setting that was active when the turn
started, so your speed change applies from your next turn."

**INFERRED (reasoning):** the reference product treats the model and its effort
as **one user-facing decision surface** (a picker whose left/right axis is
effort) even though they are separate machine-level settings. The
"applies to the next request in that turn" semantics (rather than "from your
next turn") is a deliberate, more precise contract: the change is applied at the
next *provider request* boundary rather than the next *turn* boundary, so a
multi-request turn can still pick it up.

**Clean-room opportunity:** build the picker with a two-axis selection
(model × effort) exactly as described; implement the "next request, not next
turn" semantics explicitly, because it is a genuinely better contract and is
observable; and surface a cache-invalidation warning whenever a change will
break prompt-cache reuse, telling the user what will be re-sent.

---

### F4 — Effort has five levels, per-model support matrices, and a cap mechanism

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/model-config

Supported levels depend on the model:

| Models | Supported levels |
|---|---|
| Fable 5.1, Fable 5 | `low`, `medium`, `high`, `xhigh`, `max` |
| Opus 5.5, Sonnet 5.5, Haiku 5.5, Opus 5, Sonnet 5, Opus 4.8, Opus 4.7 | `low`, `medium`, `high`, `xhigh`, `max` |
| Opus 4.6, Sonnet 4.6 | `low`, `medium`, `high`, `max` |

"If a selected level is unsupported, Claude Code uses the highest supported
level at or below it. For example, `xhigh` runs as `high` on Opus 4.6."

Defaults: Opus 5.5 / Sonnet 5.5 / Haiku 5.5 → `medium`; Opus 4.7 → `xhigh`;
every other effort-capable model → `high`.

Resolution order (first that applies wins):
1. Explicit choice — `CLAUDE_CODE_EFFORT_LEVEL`, `--effort`, `/effort`
2. Settings — per-model level in `modelSettings`, then `effortLevel`
3. The model's default effort

Quirk worth noting: **a top-level `effortLevel` in user settings does not apply
to Opus 5.5**, whereas a top-level `effortLevel` in project, local, or managed
settings (or one supplied via `--settings`) applies to every model. The
`effortLevel` setting accepts only `low|medium|high|xhigh` — **not** `max` and
not `ultracode`.

Effort caps: `maxEffortLevel` is a managed setting that caps effort
client-side on any plan/provider. "When both apply, the lower cap wins."
"Higher levels are hidden from `/effort`; explicitly requesting one clamps it to
the cap." Skill/subagent effort overrides the session level but not
`CLAUDE_CODE_EFFORT_LEVEL`; effort caps still apply.

`ultracode` is **not** an effort level but a separate workflow setting;
`--effort ultracode` also sets effort to `xhigh`. `ultrathink` in a prompt asks
for deeper reasoning for that turn without changing the session effort setting
or the effort sent to the API.

**Clean-room opportunity:** implement effort as a value that is *negotiated*
with the model, not just stored: `clamp(requested, model_supported_levels) ->
highest_supported_at_or_below`. Hide unsupported levels from the picker but
still clamp explicit requests. Implement caps as a separate, lower-priority
layer that always wins. Model the "default per model" as data on the model
descriptor so a new model is added with one entry.

---

### F5 — An invalid `--effort` value is a warning, not an error

**Status: OBSERVED-CLI**

Command:
```
claude -p --effort banana "hi"
```
Output (verbatim, first line):
```
Warning: Unknown --effort value 'banana' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.
```
The session continued and produced a normal answer; exit code 0.

`--effort low`, `medium`, `high`, `xhigh`, `max`, and `ultracode` were each
accepted with no warning.

**INFERRED (reasoning):** the CLI validates the effort *name* locally because
the set of valid names is knowable without contacting the provider, but it does
**not** validate the *level* against the selected model's supported set at
launch — that is deferred to the model-aware layer described in F4. The
asymmetry with `--model` (F6) is deliberate: effort is advisory and degrades
gracefully; a model ID is a hard identifier the provider must recognise.

**Clean-room opportunity:** mirror the graceful-degradation policy for advisory
parameters (effort, verbosity, output style) — validate the name, warn, fall
back to default, and keep going — and reserve hard failures for parameters
that are semantically required (model ID, session UUID, path). Emit the
effective value in the startup manifest so the fallback is visible rather than
silent.

---

### F6 — An unrecognised model ID triggers a 200 K context assumption and a diagnostic

**Status: OBSERVED-CLI**
**Source for the correction path:** https://code.claude.com/docs/en/model-config

Command:
```
claude -p --model totally-not-a-model "hi"
```
Output (verbatim):
```
Claude Code doesn't recognize the model "totally-not-a-model", so it assumes a context window of 200k tokens. Update Claude Code, or see https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id to set the window.
[claude-code:unrecognized_model] {"model":"totally-not-a-model","query_source":"sdk"}
API Error: 400 totally-not-a-model is not a valid model ID
```

The same two-line warning appears on **every** launch on this machine,
because the gateway serves `minimax/minimax-m3.1-flash:free`, an ID Claude Code
does not recognise:
```
Claude Code doesn't recognize the model "minimax/minimax-m3.1-flash:free", so it assumes a context window of 200k tokens. …
[claude-code:unrecognized_model] {"model":"minimax/minimax-m3.1-flash:free","query_source":"sdk"}
```

The documented correction mechanisms are:
- `CLAUDE_CODE_MAX_CONTEXT_TOKENS=400000` — set the assumed window for a
  custom gateway or provider model ID;
- `modelOverrides` — map the Anthropic ID to your gateway's spelling, e.g.
  `{"modelOverrides": {"claude-opus-4-8": "my-gateway-opus"}}`;
- `modelPicker` rows with `behavesAs` set to a known model;
- `ANTHROPIC_CUSTOM_MODEL_OPTION` — add one custom entry to the `/model`
  picker without replacing the built-in aliases;
- `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1` — skip proactive
  auto-compaction when the model ID is unrecognised, so compaction happens only
  after the API returns a recognised "too long" error.

**INFERRED (reasoning):** the "assume 200 K" default is a *conservative*
fallback — it is smaller than every real model window, so an unrecognised model
will compact earlier rather than overflow. The trade-off is wasted context and
more frequent compactions. The docs also note that a gateway that rewrites the
provider's error into wording the client does not recognise will defeat the
error-driven recovery path, which is why the *proactive* enforcement mode
exists as an option.

**Clean-room opportunity:** make the assumed-window a first-class, explicitly
configurable property of a model descriptor with a conservative default
(choose the smallest window among plausible values, not the largest). Emit a
structured diagnostic on the diagnostic channel, not in the data channel, and
make the diagnostic actionable — say exactly which env var or setting key fixes
it. Provide the "disable proactive enforcement" switch, since over-eager
compaction is a real cost.

---

### F7 — `--autocompact` has a strict value grammar and fails hard on bad input

**Status: OBSERVED-CLI**
**Sources:** https://code.claude.com/docs/en/cli-reference, https://code.claude.com/docs/en/model-config

`claude --help` (verbatim):
```
  --autocompact <auto|tokens>           Auto-compact window size (auto, or
                                        100k–1M tokens)
```

Probing the parser with `claude -p --autocompact <value> --max-turns 1 "say OK"`:

| Input | Result |
|---|---|
| `banana` | **error**, launch aborted |
| `50k` | **error**, launch aborted |
| `2M` | **error**, launch aborted |
| `200` | accepted |
| `500k` | accepted |
| `auto` | accepted (per `--help` and docs) |

Verbatim error text:
```
error: option '--autocompact <auto|tokens>' argument 'banana' is invalid. It must be 'auto', or between 100k and 1M (e.g. 500k, 200000, or 200 as shorthand)
```

The accepted forms, per the docs, are:
- a plain token count, e.g. `200000`;
- a `k` or `M` suffix, e.g. `500k` or `1M`;
- a bare number from 100 to 1000, meaning **thousands**, so `200` sets 200 000;
- `auto` — the window tuned for the model.

Range: **100 K to 1 M tokens**, always capped at the model's own context window.
"Whichever way you set the window, Claude Code caps it at the model's context
window."

Note the sharp contrast with the environment variable: "A number with no suffix
is read as that many tokens, so `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200` means 200
tokens even though `/autocompact 200` means 200,000." Two surfaces, same-looking
input, different meaning.

**INFERRED (reasoning):** the *command* and the *flag* use a human-friendly
shorthand grammar (bare number = thousands) because a human types them; the
*environment variable* uses a machine-exact grammar (bare number = tokens)
because a machine writes them. The reference product makes that distinction
explicit in its own error message, which is good design. Note also that `2M`
is rejected — the range check runs before/independent of suffix parsing, so
"1M" is the ceiling and there is no larger legal value regardless of suffix.

**Clean-room opportunity:** define one canonical window type (an integer token
count) and one parser per *surface*, with the surface's grammar named in the
error message ("a bare number here means thousands, not tokens"). Validate at
parse time, report the valid range, and reject out-of-range values loudly
rather than silently clamping — an operator who typed `2M` meant something
specific. Keep the canonical form integer-token-count internally so all
downstream code (compaction, status display, cost accounting) works in one unit.

---

### F8 — Four independent surfaces set the auto-compact window, with a specific precedence

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/model-config

1. **Per model, this session and later** — `/autocompact 500k`. Saves to user
   settings under the current model in `modelSettings` and applies immediately.
   If a higher-priority settings scope (e.g. managed) sets its own window, the
   command saves the value but the session keeps the scope's window and *says
   so*. `/autocompact auto` returns to the model-tuned window. (Before v2.1.288
   this saved one window for every model as the top-level `autoCompactWindow`.)
2. **Every model** — `"autoCompactWindow": 200000` in a settings file. A
   model-specific `modelSettings` value takes precedence for that model in the
   same file.
3. **One launch** — `--autocompact <value>`. Overrides the saved setting for
   that launch without changing it. "`claude --autocompact auto` runs the
   session at the tuned window even if your saved setting has a value." Unlike
   `/autocompact`, **the flag is not preempted by a higher-priority settings
   scope** such as managed settings.
4. **Scripts and cloud environments** — `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000`.
   "Unless Claude Code ignores the value, the variable takes precedence over the
   command, the flag, and the `autoCompactWindow` setting." `/autocompact` then
   reports the override *without saving*.

The env var is warned about when out of range: values outside 100 000–1 000 000
or that are not token counts produce a warning naming the specific problem
("reads as <N> tokens, so Claude Code treats it as the 100k minimum", "is too
large, so Claude Code treats it as the 1M maximum", "isn't a usable size, so
Claude Code ignores it") and the resulting window.

**INFERRED (reasoning):** the *ordering* is not arbitrary — it follows "most
explicit and most operationally urgent wins". An environment variable is
typically set by an operator who needs a hard constraint right now (a gateway
that rejects >200 K, a cost cap); a command is set by a human interactively; a
flag is set for one launch; a settings file is the persistent default. The
deliberate asymmetry that the *env var* beats even managed settings, but the
*flag* does not, indicates two different trust models: managed settings are
policy that only the administrator may override, whereas an environment
variable is an operator's emergency control that bypasses everything.

**Clean-room opportunity:** implement the window as a single
`resolve_autocompact_window(sources) -> (value, provenance)` call that returns
**both the value and where it came from**, and always display the provenance in
`/status` and in the startup manifest. This makes an otherwise invisible
precedence chain auditable — the single most valuable thing in this finding.
Let an operator-level override beat admin policy but be loudly reported.

---

### F9 — Default auto-compact thresholds are model-dependent, and 1 M models compact early

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/model-config

"If you don't set an auto-compact window, Claude Code compacts when the
conversation reaches the model's context limit, except in these sessions:"

- Cloud sessions compact **as the conversation approaches** the model's limit.
- Sonnet 4.6 and Opus 4.6 without extended context compact at the **200 K**
  boundary.
- With `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`, models with a native 1 M window
  compact at the **200 K** boundary.
- **Models running with a native 1 M window compact before the window fills, at
  about 967 K tokens by default.** These include the Fable models, Sonnet 5 and
  later, Haiku 5.5, and Opus 4.7 and later.
- Sessions on an unrecognised model ID compact at the context window Claude Code
  assumes for the ID (200 K).

So the effective default is `min(model_context_window, 967 K)` for 1 M-capable
models and `200 K` for the 200 K-capable ones. The ~967 K figure is a **safety
margin below the hard limit** — approximately 97 % of the window.

The docs also mention an `idleCompaction` setting that controls compaction of a
long conversation left idle, and that "The selected window is always capped at
the model's context window."

**INFERRED (reasoning):** the 967 K default is a reserve, not a limit. Roughly
3 % of a 1 M window (≈33 K tokens) is held back — plausibly for the summarisation
request itself plus the re-injection of project files and skills after
compaction (see F10), which is consistent with the docs' statement that after
compaction Claude Code re-reads up to five recently-modified files and
re-injects skill bodies (capped at 5 000 tokens per skill and 25 000 total).

**Clean-room opportunity:** make the compaction threshold a *fraction* of the
model's window with an explicit, configurable reserve, not an absolute token
number, so it scales automatically to 200 K and 1 M models. Compute the reserve
from what you actually re-inject after compaction. Document the arithmetic.

---

### F10 — What survives compaction is specified per-mechanism, and it is re-read from disk

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/context-window

| Mechanism | After compaction |
|---|---|
| System prompt and output style | Both still apply |
| Project-root CLAUDE.md and unscoped rules | Re-injected from disk |
| Auto memory | Re-injected from disk |
| Skill descriptions | Rebuilt from current skills and re-injected (v2.1.304+) |
| Git status snapshot | A fresh one is read from the repository |
| The plan written in plan mode | Re-injected from disk |
| Rules with `paths:` frontmatter | Reloaded **on demand** |
| Nested CLAUDE.md in subdirectories | Reloaded **on demand** |
| Files Claude read or edited | **Re-read up to five, most recently modified first** |
| Invoked skill bodies | Re-injected, capped at 5 000 tokens per skill and 25 000 total; oldest dropped first |
| Background commands and background subagents | Keep running; Claude is reminded which are still running |
| Context that hooks added earlier | Summarised with the rest |
| `SessionStart` hooks matching the `compact` source | Run; their output is added to the compacted context |

Additional rules: "Right after compaction, Claude Code re-reads up to five of the
files Claude has read or edited in the session, choosing the ones modified most
recently. A file over 5 000 tokens comes back as a path reference without its
content, shown as `Referenced file` instead of `Read`." Path-scoped rules and
nested CLAUDE.md load into message history when Claude touches their trigger
file, so compaction summarises them away with everything else — the docs
recommend dropping the `paths:` frontmatter or moving such rules to the
project-root CLAUDE.md if they must persist.

**INFERRED (reasoning):** this table is the product's **context-rehydration
contract**. It draws a hard line between two categories: things that live
*outside* the conversation and are therefore re-loaded from their source of
truth (system prompt, project instructions, skills, plans), and things that
*live inside* the conversation and are therefore lost to summarisation (file
contents, path-scoped rules, hook-added context). The five-file re-read limit
and the per-skill token caps are the mechanism that keeps rehydration itself
bounded — otherwise rehydration would be an unbounded second context growth
right after compaction. The "Referenced file" degradation for large files is a
graceful-sizing rule: keep the pointer, drop the payload.

**Clean-room opportunity:** publish this contract as a *rehydration policy
table* in your own product and implement it literally — it is the difference
between a session that survives compaction coherently and one that silently
loses its project instructions. Enforce the "up to N most-recent files" and
"per-skill token cap" rules in code, not by hope. When a file exceeds the cap,
substitute a pointer rather than truncating blindly. Document that
conversation-resident context is lossy under compaction, so users know to put
durable rules in project-level files rather than in chat.

---

### F11 — Auto-compaction is recorded in the transcript as structured metadata (direct observation)

**Status: OBSERVED-CLI**

Five auto-compaction events were captured in the session transcript
`~/.claude/projects/C--Users-Admin-Desktop-Claude-clone/851dac83-ef64-4023-8fd0-20a44d3dd001.jsonl`.
Each is a `system` entry with `subtype: "compact_boundary"`:

```json
{"type":"system","subtype":"compact_boundary","content":"Conversation compacted",
 "level":"info",
 "compactMetadata":{
   "trigger":"auto",
   "preTokens":207387,
   "postTokens":18950,
   "cumulativeDroppedTokens":188437,
   "durationMs":40314,
   "preCompactDiscoveredTools":["WebFetch","WebSearch"],
   "preservedSegment":{"headUuid":"ee36493a-…","anchorUuid":"c7a67394-…",
                       "tailUuid":"9137bccf-…"},
   "preservedMessages":{"anchorUuid":"c7a67394-…","uuids":["ee36493a-…", …]}},
 "parentUuid":null,
 "logicalParentUuid":"9137bccf-…"}
```

All five observed events:

| # | trigger | preTokens | postTokens | cumulativeDroppedTokens | durationMs |
|---|---|---|---|---|---|
| 1 | auto | 207 387 | 18 950 | 188 437 | 40 314 |
| 2 | auto | 155 601 | 103 813 | 240 225 | 47 875 |
| 3 | auto | 169 688 | 33 403 | 376 510 | 55 410 |
| 4 | auto | 315 078 | 26 223 | 665 365 | 56 456 |
| 5 | auto | 246 881 | 26 319 | 885 927 | 64 386 |

Adjacent to each boundary is a `user`-type entry with `isCompactSummary: true`
— the summary text itself is stored as a user-role message.

What this establishes, concretely:

- **`trigger`** distinguishes automatic compaction from a manual `/compact`
  (a manual one would carry a different value; the manual variant was not
  observed here).
- **`preTokens` / `postTokens`** are a per-event measurement of context size
  before and after summarisation. The reduction ratio varies widely: event 1
  kept 9 % of tokens, event 2 kept 67 %. A summary is therefore *lossy by a
  variable amount*, and the transcript says exactly how lossy.
- **`cumulativeDroppedTokens`** is a **monotonic session-lifetime counter**
  (188 437 → 240 225 → 376 510 → 665 365 → 885 927). It exceeds any single
  event's drop, so it is the honest measure of total work compacted away — the
  per-event drop alone would understate it.
- **`durationMs`** shows compaction took **40–64 seconds** of wall time on this
  gateway. This is a long, visible pause and is a UX cost the product must
  absorb (spinner, progress indication, resumability).
- **`preCompactDiscoveredTools`** is a snapshot of the tool surface known at
  compaction time — a natural audit point ("could the summary have referred to a
  tool that no longer exists?").
- **`preservedSegment`** (head/anchor/tail UUIDs) and **`preservedMessages`**
  (anchor + a UUID list) name the **specific messages that were not
  summarised**. This is a structured, addressable notion of "what survived" —
  materially better than a summary blob, and it makes a resumed session
  reconstructible.
- **`parentUuid` is null** on the boundary while **`logicalParentUuid`** points
  at the tail of the preserved segment — i.e. the boundary deliberately breaks
  the ordinary parent chain and supplies a *logical* parent instead. A resume
  implementation that follows only `parentUuid` would lose the connection
  across a compaction boundary.

**INFERRED (reasoning):** the boundary entry is the anchor that makes a
compacted session resumable. Because the preserved segment is named by UUID,
a resume can reconstruct the conversation as
`[surviving head messages] + [summary] + [unsummarised tail] + [messages since
the boundary]` — which is exactly what the docs describe for
https://code.claude.com/docs/en/sessions ("the conversation opens at a
`Conversation compacted` row. Claude continues with the last compaction's
summary, the messages that compaction left unsummarised, and every message
since. The messages that the last compaction summarized aren't loaded again.").

**Clean-room opportunity:** adopt this as the design for your own compaction
record — and go one step better, because the reference product's own docs warn
that its JSONL schema changes between versions. Define a **versioned**,
documented compaction record: `{schema_version, trigger, pre_tokens,
post_tokens, cumulative_dropped_tokens, duration_ms, tool_snapshot,
preserved_message_ids[], summary_ref}`. Emit it as a first-class event on a
stable event stream *and* into the durable transcript. Give the client two
parent links (physical and logical) as the reference product does, so a
compaction boundary is navigable. Expose the cumulative dropped-token counter
in `/context` and `/status` — a user who has lost 885 927 tokens to compaction
deserves to know, and no other product tells them.

---

### F12 — `/context` visualises the live breakdown; `/compact` summarises on demand

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/commands

- `/context [all]` — "Visualize current context usage as a colored grid. Shows
  optimization suggestions for context-heavy tools, memory bloat, and capacity
  warnings. When the conversation exceeds the context window, the output includes
  a warning showing how far over the limit you are and which command frees
  space. In fullscreen mode, `/context` collapses the per-item breakdown to
  keep the grid visible. Pass `all` to expand it."
- `/compact [instructions]` — "Free up context by summarizing the conversation so
  far. Optionally pass focus instructions for the summary."
- `/clear [name]` — "Start a new conversation with empty context. Pass a name to
  label the previous conversation in the `/resume` picker. … Aliases: `/reset`,
  `/new`."
- `/autocompact [auto|<tokens>]` — "Set the auto-compact window … Pass a size
  such as `500k`, or `auto` to return to the window tuned for your model. …
  Without an argument, opens a dialog that shows the current window. Requires
  Claude Code v2.1.221 or later."

Docs also note that `/compact` with instructions can be used *before* the
automatic pass runs, so the summary reflects what the user cares about rather
than what the automatic heuristic guesses is important. And `/rewind` offers
"Summarize from here" / "Summarize up to here" for partial compaction.

**INFERRED (reasoning):** the existence of `/context` as a *category breakdown*
(not a single percentage) implies the implementation tracks context by
**provenance** — system prompt vs. project files vs. tool results vs. skills vs.
conversation — because only a per-category accounting can power both a
"colored grid" and actionable "optimization suggestions for context-heavy tools,
memory bloat". A single token counter cannot produce "memory bloat" advice.
This is a design commitment: attribute every token to a bucket as you build the
request, not just at send time.

**Clean-room opportunity:** build a per-category context accounting from the
start. It is nearly free if you tag content at the point you add it, and
expensive to retrofit. Expose it not just as a grid but as a **"freed space"
menu**: for each category, name the action that reduces it (`/compact`, `/clear`,
remove a skill, trim a project file, delegate reads to a subagent). The
reference product's suggestions are a good model. Make `/context` report the
cumulative dropped-token count from F11 alongside the live breakdown.

---

### F13 — Transcripts are durable JSONL at a predictable path, and the docs warn against parsing them

**Status: OBSERVED-CLI**
**Source:** https://code.claude.com/docs/en/sessions

Documented location:
```
~/.claude/projects/<project>/<session-id>.jsonl
```
where `<project>` is the working-directory path with non-alphanumeric characters
replaced by `-`. If the converted name exceeds 200 characters, it is truncated
to 200 and a hash of the full path is appended. Confirmed on disk:

```
C:\Users\Admin\.claude\projects\
  C--Users-Admin-Desktop-Claude-clone\
    851dac83-ef64-4023-8fd0-20a44d3dd001.jsonl    (9.6 MB)
    2c16e244-9468-4385-89ab-59bfdcc088af.jsonl
    39ebbcfb-5014-48de-91ab-0f7f82f23063\          (per-session subdirectory)
```

`claude auth status` (OBSERVED-CLI) confirms the directories:
```json
{"projectsDirectory": "C:\\Users\\Admin\\.claude\\projects",
 "configDirectory": "C:\\Users\\Admin\\.claude"}
```

Documented configuration of the location/retention:

| To | Set | Where |
|---|---|---|
| Move storage off `~/.claude` | `CLAUDE_CONFIG_DIR` | env var |
| Name the `<project>` directory yourself | `CLAUDE_CODE_PROJECT_DIR_NAME` | env var |
| Change the 30-day retention | `cleanupPeriodDays` | `settings.json` |
| Limit a `-p`/SDK transcript's growth | `CLAUDE_CODE_TRANSCRIPT_LOCAL_GC` | env var |
| Suppress transcript writes in all modes | `CLAUDE_CODE_SKIP_PROMPT_HISTORY` | env var |
| Suppress writes for one non-interactive run | `--no-session-persistence` | CLI flag |

The docs are explicit about the stability of the format: "Each line is a JSON
object for a message, tool use, or metadata entry. **The entry format is
internal to Claude Code and changes between versions, so scripts that parse
these files directly can break on any release.** To build on session data, use
`/export` or the script interfaces instead."

The documented supported script interfaces are: (a) `claude -p --output-format
json|stream-json`; (b) `claude -p --resume <session-id>` to ask an existing
session a question; (c) the `transcript_path` field delivered to hooks and
status-line commands; (d) the Agent SDK.

**Observed entry types** (histogram over the 9.6 MB transcript, OBSERVED-CLI):
```
{'mode':147, 'permission-mode':147, 'atis-latch':147, 'file-history-snapshot':3,
 'user':393, 'attachment':104, 'last-prompt':147, 'assistant':750, 'system':8,
 'api-request-shape':7, 'api-request-blob':131, 'api-request':269, 'ai-title':144,
 'queue-operation':2, 'file-history-delta':5, 'cost-state':2}
```

Sample metadata entries (OBSERVED-CLI):
```json
{"type":"mode","mode":"normal","sessionId":"851dac83-…"}
{"type":"permission-mode","permissionMode":"default","sessionId":"851dac83-…"}
{"type":"last-prompt","lastPrompt":"hi","leafUuid":"bf0a676d-…","sessionId":"851dac83-…"}
{"type":"ai-title","aiTitle":"REA Claude Code setup","sessionId":"851dac83-…"}
```
and a running accumulator:
```json
{"type":"cost-state","sessionId":"851dac83-…","totalCostUSD":17.91,
 "totalAPIDuration":3830472,"totalToolDuration":724437,
 "totalLinesAdded":207,"totalLinesRemoved":17,"totalDuration":5438019,
 "startTime":1792597591938,
 "modelUsage":{"minimax/minimax-m3.1-flash:free":{"inputTokens":1081251,
   "outputTokens":486487,"thinkingTokens":325307,
   "cacheReadInputTokens":19277252,"costUSD":17.91}},
 "hasUnknownModelCost":true}
```

**INFERRED (reasoning):** the entry taxonomy shows a deliberate separation of
concerns within one file: *conversation* entries (`user`, `assistant`,
`attachment`), *session-state* entries (`mode`, `permission-mode`,
`last-prompt`, `cost-state`, `ai-title`), *turn-level* entries (`system` with
subtypes `turn_duration` and `compact_boundary`), and *request-capture* entries
(`api-request`, `api-request-shape`, `api-request-blob`). The request-capture
entries are the ones most likely to hold sensitive data, and the presence of
`api-request-blob` alongside `api-request-shape` suggests shape-vs-content
separation — a metadata-only record next to the full payload.

**Clean-room opportunity:** separate the transcript into (a) a **stable,
versioned, documented** conversation log that third parties may rely on, and
(b) an optional, separately-encryptable, separately-deletable **request-capture
log** for debugging. Ship a `schema_version` on every record and a documented
migration path. Offer `/export` (documented: "Export the current conversation
as plain text … With a filename, writes directly to that file") as the stable
human-readable interface, and document the JSONL as unstable or versioned —
do not repeat the reference product's "changes between versions, scripts can
break" situation as a design goal. Make `cleanupPeriodDays` and per-session
retention user-visible, and provide a clean deletion path that removes
transcripts, task lists, debug logs, file-edit history and prompt history
together (the reference product's `claude purge` does exactly this).

---

### F14 — Resumption restores a documented set of state, and explicitly does not restore the rest

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/sessions

Entry points:

| Command | What it does |
|---|---|
| `claude --continue` | Reopens the most recent session in the current directory |
| `claude --resume` | Opens the session picker |
| `claude --resume <name>` | Resumes the named session directly |
| `claude --resume <transcript-path>` | Resumes the session stored in that absolute `.jsonl` path |
| `claude --from-pr <number>` | Opens the picker filtered to sessions linked to that PR |
| `/resume` | Switches to a different session from inside a session |

**What a resumed session restores:** conversation history (messages, tool
calls, results); if the session was compacted, it opens at a
`Conversation compacted` row and continues with the last compaction's summary,
the messages that compaction left unsummarised, and every message since;
interrupted tool calls are shown as cut off with an instruction to check
whether they took effect; **model**; **agent** (looked up in the session's
original directory and then the directory you resume from, so project-scoped
agents still load); **permission mode** (in the terminal case); **active goal**
(its turn count, timer and token-spend baseline reset); **session-scoped
scheduled tasks** that have not expired; and a note for background work that
did not finish.

**What is NOT restored:** `--mcp-config`, `--settings`, `--plugin-dir`,
`--fallback-model`, and directories added with `--add-dir` (including
mid-session `/add-dir`). The standard settings files are re-read at launch, so
configuration living in them does not need to be passed again.

**Model on resume** (https://code.claude.com/docs/en/model-config): a resumed
session "normally retain[s] the model saved with the transcript", but an
explicit `--model` or `ANTHROPIC_MODEL` takes precedence; provider-specific
deployment IDs (Bedrock, Google Cloud's Agent Platform, Foundry) are **not**
restored from transcripts; and "If a transcript was saved with the `haiku`
alias, it resumes on whatever `haiku` resolves to now."

**Observed error paths (OBSERVED-CLI):**
```
$ claude --resume 00000000-0000-0000-0000-000000000000
No conversation found with session ID: 00000000-0000-0000-0000-000000000000

$ claude --resume            # non-TTY
Error: --resume requires a valid session ID or session title when used with --print. Usage: claude -p --resume <session-id|title>

$ claude -p --session-id "not-a-uuid" "x"
Error: Invalid session ID. Must be a valid UUID.
```

**INFERRED (reasoning):** the restore/not-restore split follows a clean rule —
**process-scoped configuration is not restored; conversation-scoped state is.**
`--mcp-config`, `--settings`, `--plugin-dir`, `--fallback-model` and `--add-dir`
all define *the capabilities and reach* of a process, so re-applying them
silently on resume could change what the agent can do in ways the user did not
intend at resume time. The product's choice to make the user re-supply them is
a safety decision, not an oversight. Meanwhile the model is restored because it
is part of the *conversation's* meaning, but an explicit flag still wins.

**Clean-room opportunity:** publish a **restore matrix** — a table of
"restored / not restored / re-read" with a one-line rationale for each row — and
make the agent's startup banner state what it inherited and what it did not. For
every unrestored item, offer a resumable *session manifest* (a saved, named
launch profile) so the user can restore reach without re-typing flags. Reject
resume of an unknown session ID with a message that offers the nearest
alternatives (same directory, same branch, most recent) rather than a bare
"not found".

---

### F15 — Resuming a *running* background session is a distinct, well-specified path

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/sessions

When the session you resume belongs to a background session that is still
running, Claude Code **opens the running session itself** rather than loading
the transcript. From the shell, `claude --resume <session>` effectively runs
`claude attach` on that session. A command-line prompt is delivered as the
session's next turn first, with `Sent your prompt to the background session
(<id>); opening it…` printed before attaching. `claude -p --resume <session>
"prompt"` does the same, so `-p` does not keep that run non-interactive.

Claude Code **does not** open the session when the command line has:
- piped or redirected input or output;
- flags that configure the session (`--permission-mode`, `--model`, `--settings`);
- flags that read the output (`--output-format json`, `--json-schema`);
- flags that limit or rewind the run (`--max-turns`, `--max-budget-usd`).

In those cases it sends nothing and exits with status 1, printing that the
session is running in the background plus the `claude attach <id>` command.
"Add `--fork-session` to resume a copy of the conversation instead." A prompt
starting with `/` or `!` is not sent, and neither is a prompt while the session
awaits an answer; the message includes `Your prompt was not sent to it` with
the reason.

From inside a session, `/resume` moves the current conversation to the
background and attaches this terminal to the running session, printing
`Opening "<title>", running in the background (<id>)`. Press `←` on an empty
prompt to return to agent view.

**INFERRED (reasoning):** the exclusion list is a coherent "this command is
asking for a *different kind of run*" test. Configuration flags, output-format
flags and limit flags all change what the run *is*, so attaching a live session
whose semantics were chosen at dispatch time would be incoherent. The
`--fork-session` escape hatch is provided in every refusal case, which shows
the design intent: **never silently do something other than what was asked;
always offer the nearest alternative that does what was asked.**

**Clean-room opportunity:** implement a single rule — "attaching to a live
session requires that the run configuration matches the live session's" — and
when it does not, refuse with a specific reason and offer `--fork-session`.
The reference product's phrasing ("Sent your prompt to the background session
(<id>); opening it…", "Your prompt was not sent to it", with the reason) is
good UX worth copying: name the session, name the reason, name the next
command.

---

### F16 — The session picker is a searchable, grouped, multi-scope browser

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/sessions

Run `/resume` inside a session or `claude --resume` with no arguments.

| Shortcut | Action |
|---|---|
| `↑`/`↓` or `k`/`j` | Navigate between sessions |
| `→`/`←` | Expand or collapse grouped sessions |
| `Enter` | Resume the highlighted session |
| `1`–`9` | Resume the session at that position in the list |
| `Space` | Preview the session content (`Ctrl+V` also works) |
| `Ctrl+R` | Rename the highlighted session |
| `/` or any printable char other than `Space`, `j`, `k`, or a digit | Enter search mode and filter sessions |
| `Ctrl+A` | Show sessions from all projects on this machine (press again to return) |
| `Ctrl+W` | Show sessions from all worktrees of the current repository |
| `Ctrl+B` | Filter to the current git branch (press again to show all) |
| `Esc` | Exit the picker or search mode |

"Each row shows the session name if you set one, otherwise the AI-generated
session title, conversation summary, or first prompt, along with time since last
activity, git branch, and file size." Sessions created with `/branch` or
`--fork-session` get their own session IDs and appear as separate rows; when the
picker finds more than one entry for the same session it groups them under a
single row, expandable with `→`.

**Default scope:** the current worktree, including background sessions (marked
`bg` in the list), plus sessions started elsewhere that added the current
directory with `/add-dir`. `Ctrl+W` widens to all worktrees of the repository;
`Ctrl+A` widens to every project on the machine.

**Sessions deliberately excluded from the picker:** those created with `claude -p`
or the Agent SDK, and those whose first prompt was `/loop`. "`claude --continue`
skips them too" — but "`claude -p --continue` includes `-p`, SDK, and `/loop`
sessions." Such a session can still be resumed explicitly by session ID.

**Name resolution:** `claude --resume <name>` on an exact match resumes
directly; on an ambiguous name it opens the picker with the name pre-filled as
a search term. `/resume <name>` on an ambiguous name reports an error and tells
you to run `/resume` with no argument. Name resolution searches the current
repository and its worktrees.

**ID resolution order** (`claude --resume <session-id>` works from any
directory): (1) the current project directory and its git worktrees, (2) every
other project on this machine. "The cross-project search resolves the ID only
when exactly one other project holds a transcript with messages for it, so a
hand-copied duplicate makes Claude Code report not-found rather than resume an
arbitrary copy."

**Naming (documented):** `claude -n <name>` at startup; `/rename <name>` during
a session (also available in non-interactive mode); `Ctrl+R` in the picker;
accepting a plan in plan mode generates a title from the plan. Names are
sanitised: control and invisible characters become spaces, and the name is
capped at 200 characters; an empty-after-sanitisation name is rejected with
`That name is empty once invisible characters are removed. Usage: /rename <name>`.

Unnamed sessions still get two labels: a **default display name** combining the
working directory's name with a two-character suffix (e.g. `my-app-3f`), which
identifies the session in listings but is **not** a resume handle; and a
**generated title** — "a short summary of your first prompt, written by a
background request to the small/fast model, normally a Haiku-class model" — which
**is** usable as a resume handle. A `claude -p` run started directly from a
shell does not get a generated title.

**INFERRED (reasoning):** the picker's scope model (current worktree → all
worktrees → all projects) mirrors the way developers think about work, and the
`Ctrl+B` branch filter is a strong signal that the intended unit of navigation
is the *branch*, not the directory. The distinction between the default display
name (a listing label) and the generated title (a resume handle) is a careful
piece of API design: it prevents a label that changes as sessions are listed
from being mistaken for a stable identifier.

**Clean-room opportunity:** build the picker as a filterable, grouped,
keyboard-first list with an explicit scope ladder, and make every identifier
distinction explicit in your own code (a `display_label` that is not a handle, a
`title` that is, a `uuid` that always is). Implement cross-project ID lookup
with the same "only if unambiguous" rule — resolving an ID to the wrong
transcript is far worse than reporting not-found. Sanitise session names on
input, cap the length, and reject names that sanitise to empty. Generate a
title with a cheap, fast model and make clear that the title is derived.

---

### F17 — Branching copies a conversation and a transcript; in-process vs. in-place matters

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/sessions

Two ways to branch:

- In-session: `/branch [name]` — creates a copy of the conversation so far and
  switches you into it, leaving the original intact. If you omit the name, the
  branch is named after the first prompt in the conversation. The confirmation
  prints **two session IDs**: the new branch you are now in and the original.
  The original is unchanged on disk and remains in the picker.
- From the command line: `claude --continue --fork-session` (or
  `claude --resume <id> --fork-session`) — "When resuming, create a new session
  ID instead of reusing the original."

**The distinction that matters:** "`/branch` copies the transcript and switches
the running Claude Code process to write to it." Consequences:

| State | After `/branch` |
|---|---|
| Conversation history | Copied into the branch up to the point you ran `/branch` |
| "Allow for this session" permission grants | Carried over — the branch runs in the same process, so existing grants still apply. **If you fork into a separate process with `--fork-session`, the new process starts without them and you re-approve there.** |
| In-flight background subagents and background Bash commands | Keep running; their output appears in the new branch |
| Remote Control connection | Stays connected; a phone or browser follows you into the branch |

**INFERRED (reasoning):** this is a clean separation of two concepts that are
often conflated. `/branch` is a *transcript-level* copy performed inside one
process — cheap, keeps in-memory grants, keeps background work attached.
`--fork-session` is a *process-level* copy — a new process, fresh permission
grants, an isolated run. The product's own `--fork-session` help text says
"create a new session ID instead of reusing the original," and the docs add
that it is required in the "resume a running background session" refusal path
where the caller needs "a copy of the conversation" rather than the live one.

**Clean-room opportunity:** name these two operations distinctly in your own
API — `branch_in_place` vs. `fork_session` — and document that permission
grants are process-scoped, so a fork re-approves. Copy the transcript *at the
point of the branch* (not the whole file) so the branch is cheap and the
original is provably untouched. Print both session IDs on branch, and make the
original reachable by name from the branch.

---

### F18 — Background sessions: a supervisor, short IDs, a job directory, and a JSON registry

**Status: OBSERVED-CLI** (surface) + **OBSERVED-DOC** (semantics)
**Sources:** https://code.claude.com/docs/en/agent-view, https://code.claude.com/docs/en/cli-reference

**CLI surface (OBSERVED-CLI, `claude --help`):**
```
  --bg, --background                    Start the session in the background and
                                        return immediately. Prints the id that
                                        `claude attach`, `logs`, `stop` and `rm`
                                        take; `claude agents` lists them. With
                                        --resume <session-id>, continues that
                                        session in the background under the same
                                        ID, or starts a copy and says so when
                                        the session is already running
```
Subcommands: `agents`, `attach <id|name>`, `logs <id|name>`, `stop|kill <id>`,
`rm <id>`, `respawn [id]`.

**Observed `claude agents --json` output (OBSERVED-CLI):**
```json
[
  { "pid": 21488, "cwd": "C:\\Users\\Admin\\Desktop\\Claude clone",
    "kind": "interactive", "startedAt": 1792603034892,
    "sessionId": "ca6d0088-4426-4239-8884-8c2b9e5b1238",
    "name": "claude-clone-95", "status": "busy" },
  { "pid": 10472, "cwd": "C:\\Users\\Admin\\REA-Test",
    "kind": "interactive", "startedAt": 1792604140104,
    "sessionId": "96b5c88f-3cb8-4d8f-b8d5-2a5df0a0c6f4",
    "name": "rea-test-f8", "status": "idle" }
]
```

Documented fields (OBSERVED-DOC): `cwd`, `kind` (`interactive`|`background`),
`startedAt` (Unix ms), `id` (short ID), `state` (`working`|`blocked`|`done`|
`failed`|`stopped`), `pid`, `status` (`busy`|`waiting`|`idle`), `waitingFor`
(`permission prompt`|`input needed`|`sandbox request`|`worker request`|
`dialog open`), `sessionId` (full UUID), `name`.

**Observed supervisor state (OBSERVED-CLI, `claude daemon status`):**
```
not running

bg sessions:
  sock dir:     \\.\pipe\cc-daemon-*
  control.sock: unreachable (connect ENOENT \\.\pipe\cc-daemon-*-control)
  bg workers:   0 in roster.json (control unreachable)
  roster.json:  updated 68s ago
  daemon.log:   1.3KB at C:\Users\Admin\.claude\daemon.log
```
`~/.claude/daemon/roster.json` (OBSERVED-CLI):
```json
{"proto": 1, "supervisorPid": 14296, "updatedAt": 1792605218096, "workers": {}}
```
Note `"proto": 1` — a **versioned protocol field** in the supervisor roster.

**Observed per-job state (OBSERVED-CLI,
`~/.claude/jobs/17989b89/state.json`):**
```json
{"state":"stopped","detail":"stopped","tempo":"idle","tokens":171,"output":null,
 "template":"bg",
 "respawnFlags":["--model","minimax/minimax-m3.1-flash:free"],
 "providerEnv":{"ANTHROPIC_MODEL":"minimax/minimax-m3.1-flash:free",
                "ANTHROPIC_SMALL_FAST_MODEL":"minimax/minimax-m3.1-flash:free"},
 "intent":"Run the shell command: ls -la, then run: git --version",
 "name":"ls git version","nameSource":"auto",
 "sessionId":"17989b89-2134-48e8-9a0f-aeaacb4bf08b",
 "resumeSessionId":"17989b89-2134-48e8-9a0f-aeaacb4bf08b"}
```
`~/.claude/jobs/pins.json` contains `[]` (the pin list; `Ctrl+T` in agent view
pins a session and keeps its process running).

**Documented semantics (OBSERVED-DOC):**
- A background session has a **short ID** (usable with `attach`, `logs`, `stop`,
  `respawn`, `rm`), a **full UUID** (exposed as `sessionId`, usable with
  `claude --resume`), an optional **display name**, and a job directory named
  after the short ID: `~/.claude/jobs/<id>/`.
- `--bg` cannot be combined with `-p`/`--print`. An untrusted workspace shows
  the trust dialog first; where no dialog can appear, dispatch fails with
  `Workspace not trusted`.
- `--bg` with `--continue`, a bare `--resume`, or a name/path-based resume
  always creates a **copy**; `--fork-session` makes that copy intentional. With a
  full session UUID, `--bg --resume` may continue the same ID or create a copy
  and print a `note:` explaining why.
- `claude --bg` prints the short ID and the management commands:
  ```
  backgrounded · 7c5dcf5d · flaky-test-fix
    claude agents             list sessions
    claude attach 7c5dcf5d    open in this terminal
    claude logs 7c5dcf5d      show recent output
    claude stop 7c5dcf5d      stop this session
  ```
- **What carries over when backgrounding:** permission mode (including
  `acceptEdits` or `auto`), model ("changes made with `/model` survive later
  supervisor restarts"), effort (same), and configuration
  (`--mcp-config`, `--strict-mcp-config`, `--settings`, `--setting-sources`,
  `--add-dir`, `--plugin-dir`, `--fallback-model`,
  `--allow-dangerously-skip-permissions`). Backgrounding "starts a fresh process
  that resumes from the saved conversation, and in-flight background work moves
  to it."
- **Supervisor behaviour:** started on first backgrounding or agent-view open;
  each background session gets its own process; a completed session waiting for
  another prompt has its process stopped after roughly an hour when unattached;
  an unexpected process exit is restarted automatically; after a Claude Code
  update the supervisor restarts itself onto the new version without
  interrupting working, blocked, or attached sessions; session state survives
  supervisor restarts, auto-updates and machine sleep.
- **Shutdown semantics:** a machine shutdown stops running background sessions;
  within 48 hours after shutdown, interrupted sessions appear *failed*; after 48
  hours they appear *stopped* with `ended while the background service was off`.
- **Deletion:** `claude rm <id>` removes the session from the list; the
  transcript stays on disk and remains available through `claude --resume`. A
  Claude-created worktree is removed only when safe — kept if there are
  uncommitted changes, if another session uses it, or if unpushed commits exist.
- **Respawn:** `claude respawn <id>` restarts a running or stopped session "so it
  picks up the current Claude binary", with its conversation intact.
  `claude respawn --all` restarts every running session. "If transcript cleanup
  removed the saved conversation, `claude respawn <id>` runs the original prompt
  again."
- **Files under `~/.claude/jobs/<id>/` are "explicitly not a stable scripting
  interface; use the JSON command instead."** The exact state paths are
  `~/.claude/daemon.log`, `~/.claude/daemon/roster.json`,
  `~/.claude/jobs/<id>/state.json`, `~/.claude/jobs/<id>/tmp/`,
  `~/.claude/daemon.lock`. The docs do **not** specify a fixed literal path for
  the daemon socket directory — it is a runtime value printed by
  `claude daemon status` (on this machine, a Windows named pipe:
  `\\.\pipe\cc-daemon-*`).

**INFERRED (reasoning):** the `respawnFlags` + `providerEnv` fields in the
observed `state.json` are the mechanism behind two documented promises: (a)
"a model changed with `/model` survives later supervisor restarts," and (b)
`claude respawn` re-runs the session on the *new* binary while preserving the
*old* model choice. The respawn path is therefore a **relaunch with a persisted
effective configuration**, not a bare restart — it must persist enough of the
original launch to reproduce it. This is a genuinely useful design: a
supervisor that only stored "which session" could not honour either promise.

**Clean-room opportunity:** build background sessions around a **persisted
effective-configuration record** per session, from which a respawn is
reconstructed — the same record can drive "carry over what carries over" and
"respawn onto the new binary". Expose a **versioned** JSON registry for
scripting and declare the on-disk job directory explicitly unstable, exactly as
the reference product does; the `--json` command is the supported interface.
Give each session both a short human-handle ID and a full UUID, and make the
short ID the thing users type. Persist the *transcript* separately from the
*list entry* so deleting a session never destroys the conversation. Implement
the 48-hour "failed vs. stopped" distinction — it is a small, honest touch that
tells the user whether to respawn or to accept the loss.

---

### F19 — The startup manifest reports the resolved model, effort state, and context-window assumption

**Status: OBSERVED-CLI**
**Sources:** https://code.claude.com/docs/en/cli-reference, https://code.claude.com/docs/en/model-config

The first event on the `--output-format stream-json --verbose` stream is
`{"type":"system","subtype":"init"}`. Observed fields (OBSERVED-CLI, this
machine):
```
model = 'minimax/minimax-m3.1-flash:free'
permissionMode = 'default'
per_turn_effort_active = False
fast_mode_state = 'off'
fast_mode_disabled_reason = 'sdk_opt_in_required'
output_style = 'default'
claude_code_version = '2.1.306'
apiKeySource = 'none'
session_id = '7f8d26a1-ecf6-45f9-86a1-32e57e60f927'
cwd = 'C:\Users\Admin\Desktop\Claude clone'
```
Full observed key list: `type, subtype, cwd, session_id, tools, mcp_servers,
model, permissionMode, slash_commands, terminal_slash_commands, apiKeySource,
claude_code_version, output_style, agents, skills, plugins, capabilities,
analytics_disabled, product_feedback_disabled, uuid, memory_paths,
original_cwd, additional_directories, messaging_socket_path, fast_mode_state,
fast_mode_disabled_reason, per_turn_effort_active, view_mode, powershell_path`.

Two model-related fields deserve attention:
- **`per_turn_effort_active`** is the machine-readable form of "the effort
  change applies from the next request, not the next turn" (F3).
- **`fast_mode_disabled_reason`** explains *why* a capability is unavailable
  rather than merely reporting that it is — here `sdk_opt_in_required`, i.e.
  fast mode is opt-in in SDK/print mode.

The documented status surfaces are `/status` ("Open the Settings interface on
the Status tab, showing version, model, account, and connectivity"; it also
reads `background job · attached` / `background job · unattended` /
`interactive`) and the status line ("You can see which model you're currently
using in two places: in the status line, if you have one configured; in
`/status`").

**INFERRED (reasoning):** `per_turn_effort_active` on the init event is
evidence that the effort change semantics are a *state machine property of the
client*, not a property of the request payload — the client must know whether
the effort it is about to send applies to the request in flight or the next
one. Similarly, `fast_mode_disabled_reason` is an example of the general
pattern: **capabilities are reported with a reason**, which is far more
debuggable than a bare boolean.

**Clean-room opportunity:** publish a single startup manifest that resolves
*every* user-visible knob — model, resolved model ID, alias, effort, effort
provenance, assumed context window and its provenance, permission mode, tool
set, and each disabled capability **with a reason**. Ship it on a stable event
stream at session start and in a machine-readable file. This is the single
highest-leverage observability feature for a coding agent, and it is cheap.

---

### F20 — Cost, usage and context accounting are reported per model, with an explicit cost basis

**Status: OBSERVED-CLI**
**Source:** https://code.claude.com/docs/en/model-config, https://code.claude.com/docs/en/commands

`claude -p --output-format json` (OBSERVED-CLI, sanitised — full file at
`agent-reference-shots/area7-model-context-sessions/sample-print-json-result.json`):
```json
{
  "type": "result", "subtype": "success",
  "session_id": "fc9143ca-1b09-4693-a363-aa16da4a438f",
  "num_turns": 1, "is_error": false,
  "duration_ms": 2382, "total_cost_usd": 0.0028998,
  "result": "OK", "permission_denials": [],
  "fast_mode_state": "off",
  "usage": { "input_tokens", "output_tokens",
             "cache_read_input_tokens", "cache_creation_input_tokens",
             "output_tokens_details.thinking_tokens", "service_tier", "speed",
             "iterations", "cache_creation.ephemeral_5m_input_tokens",
             "cache_creation.ephemeral_1h_input_tokens", "server_tool_use",
             "fallback_credit", "inference_geo" },
  "modelUsage": { "<model-id>": {
      "inputTokens", "outputTokens", "thinkingTokens",
      "cacheReadInputTokens", "cacheCreationInputTokens",
      "webSearchRequests", "costUSD",
      "contextWindow": 200000, "maxOutputTokens": 32000,
      "canonicalModel": "…", "provider": "firstParty",
      "costBasis": "unknown" } }
}
```

The transcript's `cost-state` entry carries the same accounting for the session
as a whole, plus `hasUnknownModelCost: true` when the model has no known
pricing, and `totalLinesAdded` / `totalLinesRemoved` (207 / 17 in the observed
session).

Documented cost surfaces: `/usage` ("Show session cost, plan usage limits, and
activity stats"), with `/cost` and `/stats` as aliases; `--max-budget-usd
<amount>` ("Stop the run once estimated spend on API calls reaches this amount
(only works with --print)"), which "checks the cap against its client-side cost
estimate, which can differ from your bill" and where "spend from subagents
counts toward the cap"; spend "can pass the cap, so leave headroom"; and "When
you return to a conversation with `--continue` or `--resume`, totals restored
from earlier runs don't count toward it."

**INFERRED (reasoning):** `costBasis: "unknown"` and `hasUnknownModelCost:
true` show the product tracks *cost provenance* rather than pretending a number
is authoritative. A gateway serving an unpriced model gets a **known-unknown**
marker instead of a fabricated price. `contextWindow: 200000` in the same
object is the assumed window from F6, carried all the way into the result
payload so a consumer can see the assumption that was actually in force.

**Clean-room opportunity:** attach provenance to every reported number —
`cost_basis: known|estimated|unknown`, `context_window_source:
model_descriptor|user_override|conservative_default`, `cost_is_estimate:
true`. Never present an estimate as a bill. Carry the *effective* context
window into the result payload so downstream tooling (and the user) can see
the assumption that was in force. Make the budget cap a soft cap with a
documented overshoot allowance, and state that resumed totals are excluded —
an honest cap, not a false promise.

---

### F21 — The system prompt is snapshotted per conversation, and the flag controls it

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/cli-reference

```
  --system-prompt-snapshot <on|off>     Record the system prompt once per
                                        conversation and reuse it verbatim on
                                        every request and resume. on (the
                                        default, except under --bare outside
                                        cloud and background sessions): the
                                        prompt is rendered on the conversation's
                                        first request — a --system-prompt or
                                        --append-system-prompt included — sent,
                                        and recorded; every later request and
                                        resume sends the record as-is, even when
                                        a later launch passes different text,
                                        until the conversation is compacted.
                                        off: never record; the prompt is
                                        rendered fresh every request (for
                                        iterating on prompt text).
```

Docs also note: "Before v2.1.265, passing any of the system prompt flags also
turned recording off unless you passed `--system-prompt-snapshot on`." In bare
mode recording stays off unless `--system-prompt-snapshot on` is passed.
Recording is scoped to the conversation, not the process, and **ends at
compaction** ("until the conversation is compacted").

Related flags: `--system-prompt` (replace), `--system-prompt-file` (replace
from file), `--append-system-prompt`, `--append-system-prompt-file`. A line
containing only `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` splits the prompt so the
static part stays cached and the dynamic part changes (v2.1.275+).

**INFERRED (reasoning):** snapshotting exists to serve **prompt-cache reuse**
and **resumption fidelity** simultaneously. If the prompt were re-rendered per
request, a resumed session would send a different prompt than the one it was
built with, and the cached prefix would be invalidated on every turn. Tying
the snapshot's lifetime to the *conversation* and ending it at *compaction*
means the snapshot and the cached prefix have exactly the same lifetime — a
clean, self-consistent design. The `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` marker
extends the same idea to a custom prompt: split the prompt so the static part
can be cached and the volatile part can change.

**Clean-room opportunity:** implement the prompt as a **recorded artefact with
a defined lifetime**, not a value recomputed per request. Tie the recording's
lifetime to the cache-prefix lifetime so the two never disagree. Provide a
"rebuild every request" mode for prompt iteration, and a static/dynamic split
marker so users can keep the cacheable prefix stable while per-run context
varies. Snapshot the prompt *with* the session so a resumed session is
byte-identical to the original unless the user asked otherwise.

---

### F22 — Fallback models, safety-classifier switching, and the advisor

**Status: OBSERVED-DOC**
**Source:** https://code.claude.com/docs/en/model-config

**Availability fallback.** `--fallback-model sonnet,haiku` (comma-separated,
tried in order) or the `fallbackModel` setting (an array). `--fallback-model`
takes precedence over `fallbackModel`. The chain is capped at **three** models
after duplicate removal. "A fallback switch lasts for the current turn only;
the next message tries the primary model again." Entries outside
`availableModels` are removed. "A fallback with a smaller context window than
the primary is not used for compaction." The chain also applies to subagents.

**Safety-classifier fallback.** For Fable 5.1 / Fable 5 / Opus 5.5: Biology →
Opus 5, Cybersecurity → Opus 4.8. For Sonnet 5.5: Cybersecurity → Sonnet 5,
Biology → refusal. For Opus 5: Cybersecurity → Opus 4.8, Biology → refusal. The
fallback target is checked against `availableModels`; if blocked, the request
ends in refusal. `switchModelsOnFlag: false`, or **Switch models when a
message is flagged** → **Ask each time** in `/config`, makes it ask first.
"After an automatic fallback, the current effort level is normally retained,
even if the fallback model's default differs."

**Advisor.** `--advisor <model>` enables a server-side advisor tool for the
session; `advisorModel` in settings selects it; the advisor "must be at least
as capable as the main model."

**INFERRED (reasoning):** the availability fallback's "current turn only"
semantics is a *retry* semantic, not a *migration* semantic — the client
re-attempts the same work on a different model and then returns to the primary
on the next user turn. The safety fallback is different in kind: it is a
*policy* decision about what the model will answer, and it can end in refusal.
The "smaller context window not used for compaction" rule shows the client
distinguishes "model that can answer" from "model that can summarise the
conversation" — a subtle and important distinction that a naive fallback
implementation gets wrong.

**Clean-room opportunity:** implement fallback as a per-request *retry chain*
that reverts to the primary on the next turn, with a hard cap on chain length.
Enforce the rule that a fallback model may not be used for summarisation if its
context window is smaller than the primary's. Keep safety-classifier routing
separate from availability routing, and make "ask before switching" a real
option. When a fallback model has a different default effort, retain the
current effort rather than silently resetting it.

---

### F23 — `claude doctor` reports the endpoint/auth reality, which constrains what is observable

**Status: OBSERVED-CLI**
**Source:** https://code.claude.com/docs/en/cli-reference

`claude doctor` (verbatim, abbreviated):
```
Claude Code doctor

Running: native (2.1.306)
Commit: 01ae8327ca99
Platform: win32-x64
Path: C:\Users\Admin\.local\bin\claude.exe
Config install method: native
Search: OK (bundled)
Auto-updates: enabled
Auto-update channel: latest
Last update attempt: success → 2.1.306 (2026-10-21)
Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL
Organization policy: not fetched with a custom ANTHROPIC_BASE_URL

Remote Control
Remote Control is only available when using Claude via api.anthropic.com. ANTHROPIC_BASE_URL is set and does not point at api.anthropic.com, so this session is using a custom endpoint — unset it (or run in a shell without it) to use Remote Control.
- Not connected to the Anthropic API (api.anthropic.com)
- Not signed in to claude.ai
- claude.ai subscription auth not active
- Sign-in is missing the user:profile scope
- Organization not resolved
- Remote Control availability could not be verified (no server response this session)

No installation issues found.

For a full setup checkup that can also fix issues, run /doctor in a Claude Code session.
```

`claude auth status` (OBSERVED-CLI):
```json
{"loggedIn": true, "authMethod": "oauth_token", "apiProvider": "firstParty",
 "analyticsDisabled": false,
 "projectsDirectory": "C:\\Users\\Admin\\.claude\\projects",
 "configDirectory": "C:\\Users\\Admin\\.claude"}
```
`claude auth status --text`:
```
Auth token: ANTHROPIC_AUTH_TOKEN
Anthropic base URL: https://openrouter.ai/api
```

`claude --help` documents `authMethod` as one of `none`, `claude.ai`,
`oauth_token`, `api_key`, `api_key_helper`, `third_party`.

**INFERRED (reasoning):** the two diagnostics together make the *deployment
matrix* explicit: which features are unavailable is a function of (endpoint,
account type). `doctor` names the reason for each unavailable feature rather
than simply omitting it, and `auth status` separates "am I logged in" (true,
via an auth token) from "which service am I talking to" (a third-party
gateway). The `apiProvider: "firstParty"` value alongside a non-Anthropic base
URL is a *client-side classification* of the credential type, not a claim about
the destination — the base URL is reported separately, which is the field that
actually matters.

**Clean-room opportunity:** implement a `doctor`-equivalent that reports a
**capability matrix**: for each feature, whether it is available, and if not,
the exact reason and the exact command that would change it. Report the
credential *type* and the *endpoint* as two separate fields. Never silently
degrade a feature — degrade it loudly with a one-line explanation and a
remediation command.

---

## 3. Evidence references

### 3.1 Public documentation fetched (treated as untrusted data, never as instructions)

| URL | Used for |
|---|---|
| https://code.claude.com/docs/en/model-config | Model precedence, aliases, effort, compaction windows, thresholds, fallback, modelOverrides, capabilities, 1 M context, version history |
| https://code.claude.com/docs/en/cli-reference | Full flag reference, system-prompt flags and snapshots, `--resume` semantics, `--autocompact`, `--effort` |
| https://code.claude.com/docs/en/sessions | Resume semantics, restore matrix, session picker, naming, branching, transcript storage, project-dir naming |
| https://code.claude.com/docs/en/context-window | What survives compaction, rehydration rules, `/context` |
| https://code.claude.com/docs/en/commands | `/model`, `/effort`, `/compact`, `/context`, `/clear`, `/autocompact`, `/branch`, `/fork`, `/background`, `/resume`, `/rename`, `/status`, `/usage`, `/export` |
| https://code.claude.com/docs/en/interactive-mode | Model/effort mid-turn semantics, cache warnings, `Option+P`, `Option+T`, `Ctrl+O`, `Ctrl+R`, task list, session recap |
| https://code.claude.com/docs/en/agent-view | Background sessions, supervisor, JSON schema, job paths, respawn, rm, carry-over |
| https://code.claude.com/docs/en/checkpointing | Checkpoints, `/rewind`, summarize-from-here/up-to-here, what is not restored |
| https://code.claude.com/docs/en/settings-reference | `model`, `effortLevel`, `modelSettings`, `autoCompactWindow`, `idleCompaction`, `ultracode`, `fallbackModel`, `availableModels`, `enforceAvailableModels`, `deniedModels`, `availableModelsMatch`, `advisorModel`, `modelOverrides`, `modelPicker`, `switchModelsOnFlag`, `maxEffortLevel` |
| https://code.claude.com/docs/en/env-vars | `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `CLAUDE_CODE_DISABLE_1M_CONTEXT`, `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT`, `CLAUDE_CODE_EFFORT_LEVEL`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_MODEL`, `ANTHROPIC_CUSTOM_MODEL_OPTION`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` |
| https://code.claude.com/docs/en/legal-and-compliance | Compliance boundary (see TERMS-NOTES.md) |

### 3.2 Commands executed against the published CLI (all non-mutating)

```
claude --version
claude --help
claude agents --help
claude respawn --help
claude doctor
claude auth status
claude auth status --text
claude daemon status
claude agents --json
claude -p --effort banana "hi"
claude -p --effort {low|medium|high|xhigh|max|ultracode} --max-turns 1 "say OK"
claude -p --model totally-not-a-model "hi"
claude -p --autocompact {banana|50k|2M|200|500k} --max-turns 1 "say OK"
claude -p --session-id "not-a-uuid" "x"
claude --resume 00000000-0000-0000-0000-000000000000
claude --resume                       # non-TTY
claude -p --continue --max-turns 1 "say OK"
claude -p --output-format json --max-turns 1 "reply with the single word OK"
claude -p --output-format stream-json --verbose --max-turns 1 "say OK"
```

Plus read-only inspection of the CLI's own data directory:
`~/.claude/projects/<project>/*.jsonl`, `~/.claude/daemon/roster.json`,
`~/.claude/daemon.log`, `~/.claude/jobs/*/state.json`, `~/.claude/jobs/pins.json`.

No credential store, keychain, licence file, or unrelated personal file was
read. `~/.claude/settings.json` was read because it is a *settings* file that
directly governs model selection (and is documented as such) — its embedded
token value is deliberately **not** reproduced in any artifact.

### 3.3 Local artifacts produced by this area

| Path | Contents |
|---|---|
| `agent-reference-shots/area7-model-context-sessions/cli-observations.md` | All raw CLI observations, with commands and verbatim output |
| `agent-reference-shots/area7-model-context-sessions/sample-print-json-result.json` | Sanitised `--output-format json` result shape |
| `agent-reference-shots/area7-model-context-sessions/agent-evidence-area7.md` | This document (standalone copy) |

---

## 4. Capability tables

### 4.1 Model selection

| Capability | Surface | Status | Evidence |
|---|---|---|---|
| Pick a model interactively | `/model` (picker), `/model <name>` (direct) | OBSERVED-DOC | model-config |
| Pick a model at launch | `--model <alias\|name>` | OBSERVED-CLI (`--help` text) | `claude --help` |
| Pick a model via environment | `ANTHROPIC_MODEL` | OBSERVED-DOC | model-config |
| Pick a model via settings | `"model"` in `settings.json` | OBSERVED-CLI (present in this machine's `~/.claude/settings.json`) | local file |
| Pick a default for new sessions | `ANTHROPIC_DEFAULT_MODEL` | OBSERVED-DOC | model-config |
| Save a model as default from the picker | `Enter` in the `/model` picker; `s` for session-only | OBSERVED-DOC | model-config, commands |
| Aliases | `default`, `best`, `fable`, `opus`, `sonnet`, `haiku`, `[1m]` variants, `opusplan` | OBSERVED-DOC | model-config |
| Pin an alias to a version | `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` | OBSERVED-DOC | model-config |
| 1 M context window | `[1m]` suffix; `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` to force 200 K | OBSERVED-DOC | model-config |
| Custom context window | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | OBSERVED-DOC | env-vars |
| Model allowlist | `availableModels` + `enforceAvailableModels` | OBSERVED-DOC | settings-reference |
| Model denylist | `deniedModels` (managed only) | OBSERVED-DOC | settings-reference |
| Exact-version matching | `availableModelsMatch: "exact"` (managed only) | OBSERVED-DOC | settings-reference |
| Provider ID remapping | `modelOverrides` | OBSERVED-DOC | model-config |
| Custom picker lineup | `modelPicker` (+ `behavesAs`, `replaceBuiltInOptions`) | OBSERVED-DOC | settings-reference |
| One custom picker row | `ANTHROPIC_CUSTOM_MODEL_OPTION` (+ `_NAME`, `_DESCRIPTION`) | OBSERVED-DOC | model-config |
| Declare a pinned model's capabilities | `ANTHROPIC_DEFAULT_*_MODEL_SUPPORTED_CAPABILITIES` | OBSERVED-DOC | model-config |
| Gateway model discovery | `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` → `/v1/models` | OBSERVED-DOC (env var present locally; discovery not exercised) | env-vars, model-config |
| Availability fallback | `--fallback-model` / `fallbackModel` (≤3) | OBSERVED-DOC | model-config |
| Safety-classifier fallback | `switchModelsOnFlag` | OBSERVED-DOC | model-config |
| Second-model advisor | `--advisor` / `advisorModel` | OBSERVED-DOC | cli-reference, settings-reference |
| Block a switch | `PreModelSwitch` hook | OBSERVED-DOC | model-config |
| Unknown model ID | warn, assume 200 K, diagnostic, provider error | **OBSERVED-CLI** | `claude -p --model totally-not-a-model` |
| Show the current model | `/status`, status line | OBSERVED-DOC | model-config, commands |

### 4.2 Effort

| Capability | Surface | Status | Evidence |
|---|---|---|---|
| Levels | `low`, `medium`, `high`, `xhigh`, `max` (+ `ultracode` as a separate setting) | OBSERVED-CLI (`--help`), OBSERVED-DOC | `claude --help`; model-config |
| Set for the session | `/effort <level>`, slider, `Option+P`-style picker arrows | OBSERVED-DOC | model-config, commands |
| Set for one launch | `--effort <level>` | OBSERVED-CLI | `claude --help` |
| Set via environment | `CLAUDE_CODE_EFFORT_LEVEL=<level\|auto>` | OBSERVED-DOC | env-vars |
| Set in settings | `effortLevel` (top-level) / `modelSettings.<model>.effortLevel` | OBSERVED-DOC | settings-reference |
| Per-model defaults | `modelSettings` | OBSERVED-DOC | settings-reference |
| Cap effort | `maxEffortLevel` (lowest cap wins) | OBSERVED-DOC | settings-reference |
| Show the effective level | `/effort status` | OBSERVED-DOC | commands |
| Invalid value | warning, ignored, default used | **OBSERVED-CLI** | `claude -p --effort banana` |
| Mid-turn application | "applies to the next request in that turn" | OBSERVED-DOC | interactive-mode |
| Machine-readable state | `per_turn_effort_active` in the init event | **OBSERVED-CLI** | stream-json init |
| Ultracode | `/effort ultracode [on\|off]`, `ultracode` setting, `CLAUDE_CODE_EFFORT_LEVEL` rejects it | OBSERVED-DOC | model-config, commands |

### 4.3 Context window and compaction

| Capability | Surface | Status | Evidence |
|---|---|---|---|
| Manual compaction | `/compact [instructions]` | OBSERVED-DOC | commands |
| Focused manual compaction | `/compact focus on the auth bug fix` | OBSERVED-DOC | context-window |
| Partial compaction | `/rewind` → Summarize from here / up to here | OBSERVED-DOC | checkpointing |
| Set the auto-compact window | `/autocompact <auto\|<tokens>>` | OBSERVED-CLI (`--help` + parser probe) | `claude --help`; probe |
| Set for one launch | `--autocompact <auto\|tokens>` (100 K–1 M; `200` = 200 000) | **OBSERVED-CLI** | probe: `banana`/`50k`/`2M` rejected, `200`/`500k` accepted |
| Set for all models | `autoCompactWindow` setting | OBSERVED-DOC | settings-reference |
| Set per model | `modelSettings.<model>.autoCompactWindow` | OBSERVED-DOC | settings-reference |
| Operator override | `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | OBSERVED-DOC | env-vars |
| Default threshold | ~967 K for native-1 M models; 200 K otherwise | OBSERVED-DOC | model-config |
| Idle compaction | `idleCompaction` setting | OBSERVED-DOC | context-window, settings-reference |
| View usage | `/context [all]` — per-category grid + suggestions | OBSERVED-DOC | commands |
| Compaction record | `system`/`compact_boundary` with `preTokens`, `postTokens`, `cumulativeDroppedTokens`, `durationMs`, `preservedSegment` | **OBSERVED-CLI** | transcript `851dac83-….jsonl` |
| Compaction summary storage | a `user`-type entry with `isCompactSummary: true` | **OBSERVED-CLI** | same transcript |
| Rehydration rules | project files re-read (≤5, most recent first); skills re-injected (≤5 000/skill, ≤25 000 total) | OBSERVED-DOC | context-window |
| Assume a window for an unknown model | 200 K default, or `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | **OBSERVED-CLI** (default) / OBSERVED-DOC (override) | probe |

### 4.4 Session resumption and long sessions

| Capability | Surface | Status | Evidence |
|---|---|---|---|
| Continue the most recent | `claude --continue` / `-c` | OBSERVED-CLI (`--help`) | `claude --help` |
| Resume by ID, name, or path | `claude --resume <id\|name\|path>` | OBSERVED-CLI (`--help`) + error paths | probe |
| Open the picker | `claude --resume` (no arg), `/resume` | OBSERVED-CLI (non-TTY error) / OBSERVED-DOC | probe; sessions |
| Picker navigation, search, scope | `↑↓/jk`, `Enter`, `1`–`9`, `Space`, `Ctrl+R`, `Ctrl+A`, `Ctrl+W`, `Ctrl+B`, `Esc` | OBSERVED-DOC | sessions |
| Name a session | `-n/--name`, `/rename`, `Ctrl+R` in the picker | OBSERVED-CLI (`--help`) / OBSERVED-DOC | `claude --help`; sessions |
| Set a session ID | `--session-id <uuid>` | OBSERVED-CLI (validation error) | probe |
| Branch in place | `/branch [name]` | OBSERVED-DOC | sessions |
| Fork to a new session | `--fork-session` | OBSERVED-CLI (`--help`) | `claude --help` |
| PR-linked sessions | `--from-pr <number>` | OBSERVED-CLI (`--help`) / OBSERVED-DOC | `claude --help`; cli-reference |
| Durable transcript | `~/.claude/projects/<project>/<session-id>.jsonl` | **OBSERVED-CLI** (on disk) | local FS |
| Disable persistence | `--no-session-persistence`, `CLAUDE_CODE_SKIP_PROMPT_HISTORY` | OBSERVED-CLI (`--help`) / OBSERVED-DOC | `claude --help`; sessions |
| Customise the store location | `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PROJECT_DIR_NAME` | OBSERVED-CLI (config dir reported by `auth status`) / OBSERVED-DOC | probe; sessions |
| Retention | `cleanupPeriodDays` (30-day default) | OBSERVED-DOC | sessions |
| Delete local state | `claude purge [path]` | OBSERVED-CLI (`--help`) | `claude --help` |
| Export | `/export [filename]` | OBSERVED-DOC | commands |
| Rewind / checkpoint | `/rewind`, double `Esc` | OBSERVED-DOC | checkpointing |
| Restore matrix (what does / does not come back) | conversation, model, agent, permission mode, goal, scheduled tasks restored; `--mcp-config`, `--settings`, `--plugin-dir`, `--fallback-model`, `--add-dir` not restored | OBSERVED-DOC | sessions |
| Resume of a *running* background session | attaches; refuses when the run config differs; offers `--fork-session` | OBSERVED-DOC | sessions |
| Prompt snapshot | `--system-prompt-snapshot on\|off` | OBSERVED-CLI (`--help`) / OBSERVED-DOC | `claude --help`; cli-reference |
| Transcript entry types | `user`, `assistant`, `attachment`, `system`, `mode`, `permission-mode`, `last-prompt`, `ai-title`, `cost-state`, `file-history-*`, `api-request*`, `queue-operation` | **OBSERVED-CLI** | transcript histogram |
| Cost accounting | `total_cost_usd`, `modelUsage[*].costUSD`, `costBasis`, `hasUnknownModelCost` | **OBSERVED-CLI** | print-json result; transcript `cost-state` |
| Budget cap | `--max-budget-usd` | OBSERVED-CLI (`--help`) / OBSERVED-DOC | `claude --help`; cli-reference |

### 4.5 Background sessions

| Capability | Surface | Status | Evidence |
|---|---|---|---|
| Start in the background | `claude --bg "<prompt>"` | OBSERVED-CLI (`--help`) | `claude --help` |
| Dashboard | `claude agents` (+ `--cwd`, `--json`, `--all`) | **OBSERVED-CLI** | `claude agents --json` |
| Attach / logs / stop / rm | `claude attach\|logs\|stop\|rm <id\|name>` | OBSERVED-CLI (`--help`) | `claude --help` |
| Respawn onto a new binary | `claude respawn <id>\|--all` | OBSERVED-CLI (`--help`) | `claude respawn --help` |
| Supervisor status | `claude daemon status\|logs\|run\|stop --any` | **OBSERVED-CLI** | `claude daemon status` |
| Background from inside a session | `/background` / `/bg`, `←` on an empty prompt | OBSERVED-DOC | agent-view |
| Copy to a new background session | `/fork [prompt]` | OBSERVED-DOC | agent-view |
| Carry-over semantics | permission mode, model, effort, config flags, added dirs, environment | OBSERVED-DOC | agent-view |
| Persisted effective config | `respawnFlags`, `providerEnv`, `sessionId`, `resumeSessionId` in `state.json` | **OBSERVED-CLI** | `~/.claude/jobs/17989b89/state.json` |
| Supervisor roster | `{"proto":1,"supervisorPid":…,"updatedAt":…,"workers":{}}` | **OBSERVED-CLI** | `~/.claude/daemon/roster.json` |
| State/log paths | `~/.claude/daemon.log`, `~/.claude/daemon/roster.json`, `~/.claude/jobs/<id>/state.json`, `~/.claude/jobs/<id>/tmp/`, `~/.claude/daemon.lock` | **OBSERVED-CLI** / OBSERVED-DOC | local FS; agent-view |
| Socket directory | runtime value, printed by `claude daemon status` (`\\.\pipe\cc-daemon-*` here) | **OBSERVED-CLI** | `claude daemon status` |
| Worktree isolation for background sessions | `<repo>/.claude/worktrees/`; disable with `{"worktree":{"bgIsolation":"none"}}` | OBSERVED-DOC | agent-view |
| Shutdown semantics | <48 h → *failed*; >48 h → *stopped* with `ended while the background service was off` | OBSERVED-DOC | agent-view |

---

## 5. Dependencies

| Dependency | Required for | Status on this machine | Notes |
|---|---|---|---|
| Anthropic API (`api.anthropic.com`) or a compatible endpoint | Every model call | **Not available** — custom `ANTHROPIC_BASE_URL` (`https://openrouter.ai/api`) | Remote Control, org policy, managed settings, and subscription features are unavailable here |
| A model provider (Anthropic, Bedrock, Google Cloud's Agent Platform, Foundry, Claude Platform on AWS) | Model resolution, provider-native IDs, model discovery | Partially — a third-party gateway with one unpriced model | `modelOverrides` exists precisely to bridge Anthropic IDs to provider IDs |
| A model account / subscription | Subscription-gated features: org default model, saved model on the claude.ai account (v2.1.280+), usage limits, `/usage-credits`, feature-flag fetching | **Not available** | `doctor`: "Not signed in to claude.ai" |
| An LLM gateway exposing `/v1/models` | Gateway model discovery in the `/model` picker | Enabled by env var; not exercised | `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` |
| Local filesystem, writable at `~/.claude` | Transcripts, project state, jobs, roster, logs, debug logs, file history, auto memory | Available | `CLAUDE_CONFIG_DIR` relocates it |
| Background-session supervisor process | `claude agents`, `--bg`, attach/stop/respawn | Present but **not running** at observation time; `roster.json` shows `supervisorPid` and an empty `workers` map | `claude daemon status` reported "not running" |
| A local IPC transport | Supervisor control | Windows named pipe (`\\.\pipe\cc-daemon-*`) here; a Unix socket elsewhere | Runtime value; not a stable path |
| Git | Worktree isolation for background sessions, branch filtering in the picker | Directory is not a git repo | Non-git directories are not isolated |
| Network (general) | Auto-updates, telemetry, feature-flag fetching, release notes, PR status, `/feedback` | Available | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` disables all of it (any non-empty value, including `0`/`false`) |
| A small/fast model | Session title generation, prompt suggestions, background functionality | Unpriced on this gateway | `ANTHROPIC_DEFAULT_HAIKU_MODEL`; `ANTHROPIC_SMALL_FAST_MODEL` is deprecated in favour of it |
| `apiKeyHelper` / `ANTHROPIC_API_KEY` / OAuth | Authentication | `ANTHROPIC_AUTH_TOKEN` via `~/.claude/settings.json` `env` | `authMethod: "oauth_token"` |
| MCP servers | Subagent tool surface | Present (`rea`) | Out of this area's scope |

---

## 6. Limitations of this investigation

1. **No subscription-gated behaviour was directly observable.** The endpoint is a
   third-party gateway serving a non-Anthropic model. Everything about real
   alias resolution (`opus` → Opus 5.5), the account/org default model, the
   `/model` picker's actual rows, usage limits, and claude.ai-recorded model
   choices is INFERRED from docs.
2. **The interactive TUI was not driven by a human at a terminal** for this
   area. The picker, the effort slider, the model picker arrows, `/context`'s
   grid, and `/rewind`'s menu are documented but not observed here. The
   `stream-json` `init` event and the transcript were used instead, both of
   which are machine-readable and richer for this purpose.
3. **The full 1 M-context and `[1m]` behaviour was not exercised** — it
   requires a 1 M-capable model.
4. **The manual `/compact` path was not observed**; only `trigger: "auto"`
   compaction events were captured. The manual trigger's value is UNKNOWN.
5. **`claude agent view` was not opened interactively** (it requires a TTY).
   The `--json` view and the on-disk job/roster state were used instead.
6. **Token counts are provider-reported.** `preTokens`/`postTokens` are
   whatever the gateway reported; on a different provider the absolute numbers
   would differ, though the *structure* of the record is what matters.
7. **Cost figures are gateway-specific and unpriced** (`costBasis:
   "unknown"`), so no cost conclusion should be drawn from the absolute values.
8. **The reference product's own docs warn that the transcript entry format
   changes between versions.** All transcript-structure observations here are
   specific to v2.1.306 and must not be treated as a stable contract.
9. **No deep inspection was performed**, by design. Anything requiring the
   binary, its bundled JavaScript, source maps, or the private API gateway was
   out of scope and is listed under UNKNOWN.
10. **Timing figures come from one gateway and one machine.** The 40–64 s
    compaction durations are not representative of the reference product against
    `api.anthropic.com`.

---

## 7. Unresolved questions (UNKNOWN)

1. The exact JSONL schema and the semantic contract of the non-obvious entry
   types — `atis-latch`, `api-request-shape`, `api-request-blob`,
   `api-request`, `file-history-snapshot`, `file-history-delta`,
   `attachment`, `queue-operation`. Observed to exist and to be frequent, but
   their contents were not interpreted (and `api-request-blob` may contain
   sensitive payload data, so it was deliberately not dumped).
2. Whether `api-request-blob` stores the full request body, and therefore
   whether transcripts can contain credentials. Relevant to the design of any
   transcript store.
3. The exact `trigger` value used for a **manual** `/compact` (only `"auto"`
   was observed).
4. Whether the *rehydration* behaviour documented in F10 (five-file re-read,
   per-skill token caps) is actually implemented in v2.1.306 — the docs describe
   it, and one compact boundary in the observed transcript carries
   `preservedSegment`, but no direct observation of a file being re-read after
   compaction was made.
5. The precise summary prompt and summary format used for compaction — this is
   an internal prompt and is explicitly out of scope for verification.
6. The exact contents and layout of the `/model` picker on a real Anthropic
   account (which rows, which order, which are marked `bg`/experimental).
7. Whether `PreModelSwitch` hooks are usable from a non-Anthropic endpoint.
8. The exact behaviour of `/autocompact` when a higher-priority settings scope
   sets a different window — the docs say the command "says so", but the exact
   wording was not observed.
9. The precise `startup` sequence for the background supervisor: when it is
   spawned, whether it is a separate process tree, and how it reattaches after
   a machine sleep on Windows specifically.
10. Whether the 967 K default compaction threshold is computed as a fixed
    fraction of the window or a per-model constant.
11. The behaviour of `claude --continue` when the most recent conversation is a
    *running* background session — the docs say it exits with
    "Your most recent conversation is running in the background" and the
    session's ID; that message was not observed here.
12. Whether `claude --resume <id>` cross-project lookup can be slow at scale
    (it scans every project on the machine). No performance data was collected.
13. The behaviour of session resumption when the transcript file has been
    truncated or partially written (crash during a write).
14. Whether `effortLevel` in **user** settings truly fails to apply to the
    newest model family, as the docs state. Documented, but not exercised
    (no Anthropic model available on this machine).

---

## 8. Recommended scope for an independent functional implementation

### 8.1 Must have — the core of a usable, non-toy product

| # | Capability | Concrete minimum |
|---|---|---|
| 1 | **Model resolution** | One pure function over an ordered source list; the resolved value *and its provenance* are in the startup manifest. Alias layer (≥4 aliases) with per-family pinning. |
| 2 | **Effort** | 5 levels, per-model supported sets, "highest supported at or below" clamping, a separate cap layer that always wins, per-model saved defaults. |
| 3 | **Context accounting** | Per-category token attribution at the point content is added; a `/context`-style view; the "which command frees space" advice. |
| 4 | **Compaction** | Threshold as a fraction of the model's window with a configurable reserve; a summarisation step; a **structured, versioned compaction record**; a rehydration policy (re-read ≤N recent files, re-inject skills with per-skill and total caps). |
| 5 | **Durable session store** | Append-only JSONL under a documented, configurable path; a **versioned** schema; per-turn and per-session metadata (model, effort, permission mode, cost) recorded with the entries. |
| 6 | **Resumption** | `--continue`, `--resume <id\|name>`, a picker, and a **published restore matrix** stating what is and is not restored, with reasons. |
| 7 | **Branching** | `branch_in_place` (transcript copy, same process) and `fork_session` (new process, fresh grants) as two distinct operations. |
| 8 | **Startup manifest** | One machine-readable document resolving every user-visible knob, including *why* each disabled capability is disabled. |

### 8.2 Should have — what makes it deployable and operable

| # | Capability | Concrete minimum |
|---|---|---|
| 9 | **Model policy layer** | Allowlist, denylist, exact-vs-prefix matching, provider ID remapping, custom picker lineup, fallback chain (≤3, turn-scoped, reverts to primary). |
| 10 | **Background sessions** | A supervisor, short + full IDs, a job directory, a versioned JSON registry, attach/stop/respawn/rm, a persisted effective-configuration record so respawn reproduces the original launch. |
| 11 | **Cost and usage reporting** | Per-model accounting with an explicit `cost_basis` (known / estimated / unknown); a soft budget cap with a documented overshoot allowance. |
| 12 | **Provider portability** | Model descriptors carrying context window, max output tokens, supported effort levels, supported capabilities, and a conservative default for unknown IDs; a way to declare a pinned model's capabilities explicitly. |
| 13 | **Checkpointing** | Per-turn file snapshots, a rewind menu, and "summarize from here / up to here" as a targeted alternative to full compaction. |
| 14 | **Diagnostics** | A `doctor`-equivalent capability matrix with a reason and a remediation command for every unavailable feature. |

### 8.3 Nice to have — the differentiators

| # | Capability | Note |
|---|---|---|
| 15 | **Prompt snapshot with a defined lifetime** | Tie the recorded prompt's lifetime to the cached prefix's lifetime; end both at compaction. |
| 16 | **Cumulative context-loss reporting** | Surface the session's total dropped-token count and the ratio lost at the last compaction — the reference product records it but does not (as far as this investigation could establish) surface it prominently. |
| 17 | **Versioned transcript schema** | The reference product explicitly warns that its format changes between versions. A clean-room implementation can publish a stable, versioned, documented schema and a migration path — a real advantage. |
| 18 | **Stateless summarisation** | Treat the summariser as a separate, tool-less, independently-configured context so compaction quality does not depend on the main conversation's tools. |
| 19 | **Explicit token arithmetic** | Show, in the UI, what each compaction will cost in tokens and what the reserve is for. |
| 20 | **Cross-session context sharing** | A named, shared task/context store across sessions (the reference product has `CLAUDE_CODE_TASK_LIST_ID` for named task directories — a narrow version of this). |

### 8.4 Deliberately out of scope for a clean-room implementation

- Reproducing Anthropic's specific system prompts, private APIs, model
  behaviour, weights, or training data. All of this is explicitly out of scope
  and was not inspected.
- Copying the reference product's exact picker layout, wording, or internal
  file format. The *function* is re-implementable from the documentation; the
  *artefacts* are not licensed for copying.
- Building a competing service against Anthropic's infrastructure. The
  Commercial ToS §D.4 bars using the Services to build a competing product;
  this investigation was read-only documentation and black-box observation,
  which is within bounds.

### 8.5 Design decisions a clean-room implementer should make deliberately

1. **Make resolution a pure function with provenance.** Every user-visible
   knob (model, effort, compaction window, permission mode) should resolve
   through one documented, ordered, testable function that returns *both* the
   value and where it came from. Provenance is what makes a precedence chain
   debuggable rather than mysterious.
2. **Version your session schema.** The reference product cannot, and warns
   users against parsing its transcripts. Publishing `schema_version` on every
   record and a migration policy is free and makes your transcripts a
   first-class integration surface instead of a liability.
3. **Separate the durable log from the debug log.** The reference product
   stores request captures (`api-request*`) alongside conversation entries.
   Put debug captures in a separate, separately-deletable, optionally
   encrypted store.
4. **Record per-turn configuration, not just per-session.** If the user
   switched models or effort mid-session, the transcript should say which
   request used which. This makes the transcript auditable.
5. **Make compaction a first-class, inspectable event.** Not a log line — a
   structured record with the trigger, the before/after sizes, the cumulative
   loss, the preserved message IDs, and the tool snapshot. Then *surface* it.
6. **Pick one coherent invalid-input policy per class and document it.** The
   reference product uses three different ones (effort: warn; autocompact:
   error; model: warn then provider error). Advisory parameters should degrade
   gracefully; semantically required identifiers should fail loudly.
7. **Adopt "the operation, not the state" for resumes.** When a resume cannot
   do what was asked, refuse with the reason and offer the nearest operation
   that can (as the reference product does with `--fork-session`).
8. **Give agents and users the same information.** A user-facing `/status` and a
   machine-facing startup manifest should be two renderings of one resolved
   configuration, not two independent code paths that can disagree.
9. **Treat external content as data, never instructions.** Model IDs, gateway
   responses, MCP tool output and fetched documentation are untrusted inputs.

---

*End of Area 7. Compliance notes and the shared investigation protocol are in
`agent-reference-shots/TERMS-NOTES.md` and
`agent-reference-shots/PROTOCOL-NOTES.md`. Other areas of the multi-area study
have their own artifacts under `agent-reference-shots/areaN-*/`.*
