# Area 7 — Model selection, conversation context, long sessions, session resumption

Black-box observations from the published Claude Code CLI (v2.1.306, native build,
win32-x64). No decompilation. See `../../TERMS-NOTES.md`.

Machine note: `ANTHROPIC_BASE_URL` points at a third-party gateway serving a
non-Anthropic model, so `api.anthropic.com`-gated behaviour (subscription
picker rows, real alias resolution, gateway model discovery) is **not** directly
observable here and is flagged INFERRED from docs.

---

## 1. Model-selection flags and their help text (verbatim from `claude --help`)

```
  --model <model>                       Model for the current session. Provide
                                        an alias for the latest model (e.g.
                                        'fable', 'opus', or 'sonnet') or a
                                        model's full name.
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --fallback-model <model>              Enable automatic fallback to specified
                                        model(s) when the default model is
                                        overloaded or not available. Accepts a
                                        comma-separated list to try each in
                                        order. Re-tries the primary at the start
                                        of each user turn.
  --autocompact <auto|tokens>           Auto-compact window size (auto, or
                                        100k–1M tokens)
```

## 2. Effort-value validation (OBSERVED-CLI)

`claude -p --effort banana "hi"`:

```
Warning: Unknown --effort value 'banana' — ignoring it and using the default
effort. Valid values: low, medium, high, xhigh, max.
```

The run continued and answered normally. `low`, `medium`, `high`, `xhigh`, `max`
and `ultracode` were each accepted with no warning.

Note the divergence from `--autocompact`: an unknown *effort* is a **warning
and is ignored**; an unknown *autocompact* value is a **hard error** (§4).

## 3. Unrecognised model IDs (OBSERVED-CLI)

`claude -p --model totally-not-a-model "hi"`:

```
Claude Code doesn't recognize the model "totally-not-a-model", so it assumes a
context window of 200k tokens. Update Claude Code, or see
https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id
to set the window.
[claude-code:unrecognized_model] {"model":"totally-not-a-model","query_source":"sdk"}
API Error: 400 totally-not-a-model is not a valid model ID
```

The same two-line warning appears on **every** launch against this machine's
gateway model (`minimax/minimax-m3.1-flash:free`), because the gateway serves
a model ID Claude Code does not know.

## 4. `--autocompact` value grammar (OBSERVED-CLI)

| Input | Result |
|---|---|
| `banana` | error (exit) |
| `50k` | error (exit) |
| `2M` | error (exit) |
| `200` | accepted |
| `500k` | accepted |
| `auto` | accepted (per `--help`) |

Verbatim error text:

```
error: option '--autocompact <auto|tokens>' argument 'banana' is invalid.
It must be 'auto', or between 100k and 1M (e.g. 500k, 200000, or 200 as shorthand)
```

The shorthand rule is baked into the error message: a bare `200` means 200,000.
Note `2M` is rejected — the accepted range ceiling is 1M, and `M` suffix parsing
appears to be bounded by the range check rather than a general suffix parser.

## 5. `--session-id` and `--resume` error paths (OBSERVED-CLI)

```
$ claude -p --session-id "not-a-uuid" "x"
Error: Invalid session ID. Must be a valid UUID.

$ claude --resume 00000000-0000-0000-0000-000000000000
No conversation found with session ID: 00000000-0000-0000-0000-000000000000

$ claude --resume            # no TTY
Error: --resume requires a valid session ID or session title when used with
--print. Usage: claude -p --resume <session-id|title>
```

## 6. Session storage layout (OBSERVED-CLI)

Transcripts live at `~/.claude/projects/<sanitised-cwd>/<session-id>.jsonl`.
Observed on this machine:

```
C:\Users\Admin\.claude\projects\
  C--Users-Admin-Desktop-Claude-clone\
    851dac83-ef64-4023-8fd0-20a44d3dd001.jsonl   (9.6 MB)
    ca6d0088-4426-4239-8884-8c2b9e5b1238.jsonl
    39ebbcfb-5014-48de-91ab-0f7f82f23063\          (per-session subdir)
```

The directory name is the working-directory path with non-alphanumerics
replaced by `-`. `claude auth status` reports
`"projectsDirectory": "C:\\Users\\Admin\\.claude\\projects"` and
`"configDirectory": "C:\\Users\\Admin\\.claude"`.

## 7. Transcript entry types (OBSERVED-CLI)

Histogram over the 9.6 MB session `851dac83-…jsonl`:

```
{'mode':147, 'permission-mode':147, 'atis-latch':147, 'file-history-snapshot':3,
 'user':393, 'attachment':104, 'last-prompt':147, 'assistant':750, 'system':8,
 'api-request-shape':7, 'api-request-blob':131, 'api-request':269, 'ai-title':144,
 'queue-operation':2, 'file-history-delta':5, 'cost-state':2}
```

Metadata entries carry the session-level state:

```json
{"type":"mode","mode":"normal","sessionId":"851dac83-…"}
{"type":"permission-mode","permissionMode":"default","sessionId":"851dac83-…"}
{"type":"last-prompt","lastPrompt":"hi","leafUuid":"bf0a676d-…","sessionId":"851dac83-…"}
{"type":"ai-title","aiTitle":"REA Claude Code setup","sessionId":"851dac83-…"}
```

`cost-state` is a running accumulator:

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

`ai-title` is the machine-generated session title (a short summary of the first
prompt, produced by a background request to the small/fast model).

## 8. Auto-compaction observed in the transcript (OBSERVED-CLI) — most important observation

Five `compact_boundary` system entries were captured in the long session. Verbatim
shape (first entry):

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
   "preservedMessages":{"anchorUuid":"c7a67394-…","uuids":[...]}}},
 "parentUuid":null,"logicalParentUuid":"9137bccf-…"}
```

All five observed compactions in that session:

| # | trigger | preTokens | postTokens | cumulativeDropped | durationMs |
|---|---|---|---|---|---|
| 1 | auto | 207387 | 18950 | 188437 | 40314 |
| 2 | auto | 155601 | 103813 | 240225 | 47875 |
| 3 | auto | 169688 | 33403 | 376510 | 55410 |
| 4 | auto | 315078 | 26223 | 665365 | 56456 |
| 5 | auto | 246881 | 26319 | 885927 | 64386 |

Observations an implementer can take away:

* The compaction trigger is recorded as `"auto"` (a manual `/compact` would
  presumably record a different trigger value — not observed here).
* `preTokens` and `postTokens` are a per-event measurement of context size
  before and after summarisation. Reduction is large but not uniform: entry 2
  kept 67% of tokens, entry 1 kept 9%.
* `cumulativeDroppedTokens` is monotonic across the session (188437 → 240225 →
  376510 → 665365 → 885927) and exceeds the single-event drop. It is a
  session-lifetime counter of tokens discarded, which is the number that
  actually reflects how much work was compacted away.
* Compaction took **40–64 seconds** of wall time — a visible pause in the UI.
* `preservedSegment` / `preservedMessages` name the message UUIDs that were
  **not** summarised (head, anchor, tail). This is a structured, addressable
  notion of "what survived", not just a summary blob.
* `preCompactDiscoveredTools` records the tool set known at compaction time —
  a snapshot of the tool surface, useful for audit and replay.
* The compaction summary itself is written as a `user`-type entry with
  `isCompactSummary: true` (observed: `('user','True',...)` adjacent to the
  boundary).

## 9. `system` entries of subtype `turn_duration` (OBSERVED-CLI)

```json
{"type":"system","subtype":"turn_duration","durationMs":1312862,
 "messageCount":550,"timestamp":"2026-10-21T16:21:21.737Z",
 "entrypoint":"cli","cwd":"…","sessionId":"851dac83-…","version":"2.1.306",
 "gitBranch":"HEAD","slug":"breezy-fluttering-flurry"}
```

A per-turn timing record with the message count, the CLI entrypoint, the git
branch, and a generated `slug` (the default session display name, e.g.
`my-app-3f` shape — here `breezy-fluttering-flurry`).

## 10. Background sessions — `claude agents --json` (OBSERVED-CLI)

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

Field semantics match the documented schema: `id` (short) is absent for
interactive sessions; `sessionId` is the full UUID; `kind` is `interactive` or
`background`; `status` is `busy` / `waiting` / `idle`; `startedAt` is Unix
milliseconds.

## 11. Background supervisor state (OBSERVED-CLI)

`claude daemon status`:

```
not running

bg sessions:
  sock dir:     \\.\pipe\cc-daemon-*
  control.sock: unreachable (connect ENOENT \\.\pipe\cc-daemon-*-control)
  bg workers:   0 in roster.json (control unreachable)
  roster.json:  updated 68s ago
  daemon.log:   1.3KB at C:\Users\Admin\.claude\daemon.log
```

`~/.claude/daemon/roster.json`:

```json
{"proto": 1, "supervisorPid": 14296, "updatedAt": 1792605218096, "workers": {}}
```

`~/.claude/jobs/<short-id>/state.json` (observed for job `17989b89`):

```json
{"state":"stopped","detail":"stopped","tempo":"idle","tokens":171,"output":null,
 "template":"bg","respawnFlags":["--model","minimax/minimax-m3.1-flash:free"],
 "providerEnv":{"ANTHROPIC_MODEL":"…","ANTHROPIC_SMALL_FAST_MODEL":"…"},
 "intent":"Run the shell command: ls -la, then run: git --version",
 "name":"ls git version","nameSource":"auto",
 "sessionId":"17989b89-2134-48e8-9a0f-aeaacb4bf08b",
 "resumeSessionId":"17989b89-2134-48e8-9a0f-aeaacb4bf08b"}
```

Key detail: `respawnFlags` and `providerEnv` persist the launch-time model
selection, so `claude respawn` can restart a session onto the same model after
a binary upgrade. `sessionId` and `resumeSessionId` are both present so a
respawned session can be linked back to its original transcript.

`~/.claude/jobs/pins.json` is `[]` (pin/unpin list, `Ctrl+T` in agent view).

## 12. `claude auth status` (OBSERVED-CLI)

```json
{"loggedIn": true, "authMethod": "oauth_token", "apiProvider": "firstParty",
 "analyticsDisabled": false,
 "projectsDirectory": "C:\\Users\\Admin\\.claude\\projects",
 "configDirectory": "C:\\Users\\Admin\\.claude"}
```

`--text` form:

```
Auth token: ANTHROPIC_AUTH_TOKEN
Anthropic base URL: https://openrouter.ai/api
```

`authMethod` is one of `none | claude.ai | oauth_token | api_key |
api_key_helper | third_party`. `apiProvider` was `firstParty` here even though
the base URL is a third-party gateway — the provider classification and the
actual endpoint are separate facts.

## 13. `stream-json` init event — model/effort state (OBSERVED-CLI)

First line of `claude -p --output-format stream-json --verbose`:

```json
{"type":"system","subtype":"init","cwd":"…","session_id":"7f8d26a1-…",
 "tools":[…],"mcp_servers":[…],
 "model":"minimax/minimax-m3.1-flash:free",
 "permissionMode":"default",
 "apiKeySource":"none","claude_code_version":"2.1.306",
 "output_style":"default",
 "fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required",
 "per_turn_effort_active": false,
 "view_mode":"default"}
```

`per_turn_effort_active` is the machine-readable form of "effort applies from
the next request only". `fast_mode_disabled_reason: "sdk_opt_in_required"`
explains why fast mode was off in SDK/print mode.

## 14. Print-mode result JSON — context and model accounting (OBSERVED-CLI)

`claude -p --output-format json` (sanitised; see `sample-print-json-result.json`):

```json
{
  "type": "result", "subtype": "success",
  "session_id": "fc9143ca-1b09-4693-a363-aa16da4a438f",
  "num_turns": 1, "is_error": false,
  "duration_ms": 2382, "total_cost_usd": 0.0028998,
  "result": "OK", "permission_denials": [],
  "fast_mode_state": "off",
  "usage": { … },
  "modelUsage": { "minimax/minimax-m3.1-flash:free": {
      "contextWindow": 200000, "maxOutputTokens": 32000,
      "canonicalModel": "minimax/minimax-m3.1-flash:free",
      "provider": "firstParty", "costBasis": "unknown",
      "inputTokens": …, "outputTokens": …, "thinkingTokens": …,
      "cacheReadInputTokens": …, "cacheCreationInputTokens": …,
      "webSearchRequests": 0, "costUSD": … } }
}
```

`contextWindow: 200000` is the *assumed* window for the unrecognised model ID.
`costBasis: "unknown"` is how unpriced gateway models are reported.
`hasUnknownModelCost: true` in the transcript `cost-state` entry is the
matching signal.

`usage` carries `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `output_tokens_details.thinking_tokens`,
`service_tier`, `speed`, `iterations`, and a nested `cache_creation` object
with `ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`.

## 15. `claude doctor` (OBSERVED-CLI)

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
Remote Control is only available when using Claude via api.anthropic.com. …
- Not connected to the Anthropic API (api.anthropic.com)
- Not signed in to claude.ai
- claude.ai subscription auth not active
…

No installation issues found.
```

The `Commit:` line is a build identifier, not source code.

## 16. `claude --help` — session/background flags (verbatim)

```
  -c, --continue                        Continue the most recent conversation in
                                        the current directory
  --fork-session                        When resuming, create a new session ID
                                        instead of reusing the original (use
                                        with --resume or --continue)
  -r, --resume [value]                  Resume a conversation by session ID or
                                        name, or open interactive picker with
                                        optional search term
  --session-id <uuid>                   Use a specific session ID for the
                                        conversation (must be a valid UUID)
  -n, --name <name>                     Set a display name for this session
                                        (shown in the prompt box, /resume
                                        picker, and terminal title)
  --bg, --background                    Start the session in the background and
                                        return immediately. Prints the id that
                                        `claude attach`, `logs`, `stop` and `rm`
                                        take; `claude agents` lists them. With
                                        --resume <session-id>, continues that
                                        session in the background under the same
                                        ID, or starts a copy and says so when
                                        the session is already running
  --teleport [session]                  Resume a teleport session, optionally
                                        specify session ID
  --from-pr [value]                     Resume a session linked to a PR by PR
                                        number/URL, or open interactive picker
                                        with optional search term
  --no-session-persistence              Disable session persistence - sessions
                                        will not be saved to disk and cannot be
                                        resumed (only works with --print)
  --system-prompt-snapshot <on|off>     Record the system prompt once per
                                        conversation and reuse it verbatim on
                                        every request and resume. …
```

Subcommands: `agents`, `attach <id|name>`, `logs <id|name>`, `stop|kill <id>`,
`rm <id>`, `respawn [id]`, `purge [path]`, `doctor`, `auth`, `mcp`, `plugin`,
`auto-mode`, `import`, `setup-token`, `ultrareview`, `update|upgrade`.

## 17. Environment-variable surface (from the machine's own settings)

`~/.claude/settings.json` on this box carries an `env` block with
`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL`,
`ANTHROPIC_SMALL_FAST_MODEL` and
`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY: "1"`, plus a top-level
`"model": "minimax/minimax-m3.1-flash:free"`.

This confirms the documented pattern that **environment variables can be
supplied through a settings file's `env` object**, and that a settings file can
carry a top-level `model` key. (The token value is deliberately not reproduced
here.)
