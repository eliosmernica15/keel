# Keel — harness source tree

**Status:** Phase 0 (shell-AST spike, first cut), Phase 1 (vertical slice, running),
**Phase A (provider registry, done — fake-transport verified)** and
**Phase B (skills, done — 21 default skills)**.
**Not a release, not a parity claim, not a finished product.** See
`../FINAL-APPROVAL-GATE.md` for the programme context.

Clean-room rules apply (see `../architecture.md` §1.1): interface *facts* are
reproduced for compatibility; interface *descriptions* are ours.
Vendored default skills are Apache-2.0 Anthropic works — see
`resources/default-skills/PROVENANCE.md` and `docs/SKILLS-PROVENANCE.md`.

## What works today

```
python -m pytest -q                         # 386 tests
keel fleet                                  # serves Keel Fleet on 127.0.0.1 (roster, agents, groups, tasks, library, routines, PWA)
keel provider list                          # configured providers + status
keel provider smoke openrouter              # live 1-shot check — BLOCKED on this host: no KEEL_OPENROUTER_API_KEY set
keel skills list                            # 21 bundled default skills
keel skills audit pdf                       # sha256, licence, injection scan
keel -p "hello" --bare --seed 7             # print mode; scripted fake if no keys
```

**Keel Fleet (F4, complete + hardened)**: `keel fleet` — persistent roster of named agents, real
provider-backed execution via Keel's registry, notes as untrusted context, full turn history
persisted, SSE live rows. Inline F1 approval cards gate everything; F3 agent-to-agent `send_to_bot`
delegation with depth (2) and cycle caps; bounded 2–3-agent groups in a shared ledger; F2 fleet-wide
tasks (user + agents) and a per-agent Library for deliverables; F4 cron-driven, timezone-aware
Routine scheduling per agent (next/last run, run history, missed-run skip, F1-gated unattended
execution). Echo stays a labeled scripted test bot. Browser-verified (headless Chrome, desktop +
mobile): full UI suite green; live harness pass 2026-11-12 confirmed bridge/auth/migrations,
SSE delivery and kill+relaunch persistence of models, notes and transcripts (one replay defect
found and fixed). But **no provider credentials exist on this host — live model execution has
never been verified end-to-end**; smoke test exits 1 with `no API key`. See `docs/FLEET-ROADMAP.md`
(honest status) and `docs/PHASE1-SLICE-PROGRESS.md`.

Runs end-to-end under the scripted fake model: `init → assistant → (permission-gated
tool call → tool_result)* → result`. Task-tool delegation (`Task`) runs an inline
depth-1 subagent: same model, same executor, same permission rules minus `Task`
itself, `<subagent_output>` injected back to the parent as the tool result.
Provider failure mid-run yields a spec-shaped `error_during_execution` envelope (not
a traceback). With keys set, Phase A adapters drive the same
loop against OpenRouter / NVIDIA NIM / Google AI Studio (Anthropic opt-in).

Phase C (first slice): scoped settings registry (`settings.py`, spec §13) — files
(`<root>/settings.json`, `<project>/.claude/settings.json`, `settings.local.json`),
Project scope excluded from the dangerous keys, managed merge modes
(`merge|locks|highest-priority-only`), flags > local > project > user > env > defaults,
monotonic restrictive lattice, `$defaults` splice, `keel settings show/schema/validate`.
All diagnostics on stderr even headless (deliberate divergence from the reference).

## Layout

| Path | Phase | Contents |
| :- | :- | :- |
| `src/keel/shell_ast.py` | 0 | Decomposer + effect classifier. All-or-nothing: complete operation list or decline. |
| `src/keel/permissions.py` | 1 | Tier-1: `deny → ask → allow → mode`; bare-name deny drops the tool; dontAsk schema subtraction; bypassPermissions interlock (opt-in + POSIX root refusal). |
| `src/keel/events.py` | 1 | Event union (init/assistant/user/result). |
| `src/keel/toolresult.py` | 1 | Dual representation, `<persisted-output>` overflow, `<tool_use_error>` marker. |
| `src/keel/transcript.py` | 1 | Append-only JSONL. |
| `src/keel/session.py` | 1 | Headless turn loop. |
| `src/keel/runner.py`, `src/keel/cli/` | 1A | Print-mode runner, provider/skills CLI, flag validation. |
| `src/keel/providers/` | A | `ProviderAdapter` seam, OpenAI-compatible (OpenRouter/NIM/generic), Gemini (AI Studio), Anthropic (opt-in), registry + auto chain. |
| `src/keel/settings.py` | C | Scoped settings registry (spec §13): generic fold, provenance per key, monotonic lattice, `$defaults` splice, managed merge modes. |
| `src/keel/context.py` | C | Token accounting + compaction (M5 shape): deterministic estimator, `compact_boundary` + preserved UUIDs, monotonic cumulative, thrash breaker. |
| `src/keel/commands.py` | C | Print-mode `/commands`: builtins (`help/context/cost/version/doctor`) + custom templates from `.keel/commands/*.md`, `local_command` on the envelope. |
| `src/keel/hooks.py` | C | Command-handler hooks: 33-event open set (only PreToolUse/PostToolUse wired), verdict protocol (0 proceed / 2 block), updateInput + permission re-validation, `hooks` key in settings (deep merge), `hook_started`/`hook_response` events. |
| `src/keel/safety.py` | C | Tier-2 safety envelope: non-configurable, post-rule veto. Catastrophic commands by name; protected secret/system/raw-device targets; unparseable shell refused in every mode; `safety_stops` on the envelope. |
| `src/keel/mcp.py` | C | MCP stdio client: initialize/tools-list/tools-call, lazy-but-eager start, shutdown lifecycle, `mcp__server__tool` names (sanitised), output capped at 100 KB, project-scope servers inert until `keel mcp approve` (command-shape hash); `mcpServers` in settings (deep merge). |
| `src/keel/skills.py` | B | SKILL.md loader; never executes bodies; injection scan; scopes bundled/user/project. |
| `src/keel/instructions.py` | 1 | CLAUDE.md discovery (root→cwd), user-role attachment injection. |
| `resources/default-skills/` | B | 18 Apache-2.0 anthropics/skills + 3 Keel-authored skills + PROVENANCE.md. |
| `desktop/` | D | Tauri v2 desktop shell — **Rust 1.99.1 installed via winget (2026-11-12); `cargo fetch` done (crates resolved); VS Build Tools (VCTools) still installing in background on this host; app not yet built. `keel --version` wired to the shell's probe. See `desktop/README.md`. |
| `tests/` | 0/1/A/B | pytest suite. |

## Honest gaps

- Provider adapters are **fake-transport verified, not provider-verified**. Run
  `keel provider smoke <name>` with your keys for the live check.
- Permission modes implemented: `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`.
  `plan`/`auto` are Phase 4/later.
- No interactive renderer, settings registry (done: `keel/settings.py`),
  compaction (done: `keel/context.py`), hooks (done: `keel/hooks.py`),
  Tier-2 (done: `keel/safety.py`, M7 shape — 20 tests). MCP, subagents, plan/auto
  modes: not built. `anthropic` is opt-in only.
- PowerShell AST only on hosts with Windows PowerShell/pwsh; POSIX subset is lexed,
  declining outside it. No ≥2,000-case differential corpus yet.
- Python 3.11 + stdlib only (statically-typed steady-state is an open decision).

## Environment keys (never committed)

`KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY`, `KEEL_NVIDIA_API_KEY`,
`KEEL_ANTHROPIC_API_KEY` (opt-in), `KEEL_COMPAT_BASE_URL`/`KEEL_COMPAT_API_KEY`/
`KEEL_COMPAT_MODEL`. Model overrides: `KEEL_OPENROUTER_MODEL`, `KEEL_GOOGLE_MODEL`,
`KEEL_NVIDIA_MODEL`, `KEEL_ANTHROPIC_MODEL`. Settings env bindings (optional):
`KEEL_MODEL`, `KEEL_PERMISSION_MODE`, `KEEL_DEFAULT_PROVIDER`, `KEEL_MAX_TURNS`,
`KEEL_PERMISSIONS_ALLOW/ASK/DENY` (comma-separated), `KEEL_CLEANUP_PERIOD_DAYS`,
`KEEL_BYPASS_PERMISSIONS_ENABLED`, `KEEL_DANGER_ALLOW_UNCONFIRMED` (all parsed,
default on error).
