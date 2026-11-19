# Keel x OpenCode parity matrix — honest audit

Upstream inspected at `anomalyco/opencode` `dev` (2026-11-18), tree is 11,577 files (`.git` excluded).

**Honesty rule:** unless a path is marked `Verified`, it means *inspected as text in this repo only* — not compiled, not run, not API-validated. Nothing in OpenCode is marked `Implemented`, `Tested`, or `Verified` yet.

## Summary

- 33 packages + 3 services + 3 SDKs = **39 capability areas** inspected
- **7,615 source files**, **~1,595,611 LOC** examined (text-only, not run)
- **Almost nothing in OpenCode is present in Keel today.** Keel's entire Python runtime (~12.4 kLOC) overlaps with only a thin slice of what OpenCode covers.
- `docs/parity.json` is the machine-readable source of truth for per-package `files`, `loc`, and `inspected` flags.

## What Keel already covers (from the existing codebase)

These are the closest analogues, not full equivalents.

| Capability area | OpenCode reference | Keel status | Notes |
|---|---|---|---|
| Desktop shell | `packages/desktop` | **Reused** (`desktop-app/`) | Electron + Python sidecar; working installer |
| Local agent runtime | `packages/core` `ai/*` | **Ported-to-Python (partial)** | `runner.py`, `session.py` (full loop), `fleet/turn_core.py` — token streaming over SSE, tool execution with permission gates, compaction |
| SQLite persistence | `packages/core` `database/*` | **Reused** | `fleet/db.py` (v10) — bots/rows/approvals; sessions as `kind='session'` bots; survives restart |
| File tools | `search/glob/grep/read/write/patch` | **Ported-to-Python** | `shell_ast.py`, `permissions.py`, `hooks.py`, `fleet/tools.py` — real registry, Tier-1+2 gates |
| Provider routing | `packages/providers` | **Ported-to-Python** | `providers/` — OpenRouter, Google, NVIDIA, OpenAI-compatible, Anthropic (opt-in); auto-chain; fake-transport-verified |
| PWA / web UI | `packages/app` `ui` `session-ui` | **Reused (closely related UI)** | `site/`, `desktop/ui` — similar visual design, not the same build |
| Skills | `packages/skills` (not listed) | **New in Keel** | `_parse_frontmatter` in `skills.py`, `/api/skills` endpoint |
| MCP | `packages/core/mcp` | **Reused — wired into the v2 agent runtime** | `mcp.py` stdio client; servers from `settings.json` started per turn (concurrent), failures isolated to notices; Tier-1 + F1 broker gates; `mcp__server__tool` names; output capped; step rows emitted |
| v2 sessions compat surface | `packages/server` (partial) | **Implemented + fake-transport tested** | `/api/v2/sessions*` in `src/keel/compat.py` — real provider-backed runtime: tools via real registry, approvals, SSE token streaming with replay, SQLite persistence, cancel; images (png/jpeg/gif/webp); per-turn usage accounting (fleet_usage, v11) — never invents cost |

### Keel-side v2 runtime (2026-11-19, milestones 3+4+5)

The `/api/v2/*` surface is no longer a demo tracer. It is wired into Keel's actual agent runtime: HTTP → `compat.py` → `fleet.provider_turn.start_provider_turn` → `session.Session` (agent loop) → `fleet.tools` (real tool registry, F1 approval broker, MCP client) → `providers/` adapters (fake transport in CI, real keys in production). Messages persist as `fleet.db` rows (`kind=message`), tool steps as `kind=step`, approvals as `fleet_approvals`, usage as `fleet_usage`. Sessions survive restart and replay with `?since=<seq>`.

The desktop app (`site/` UI served by the Python bridge) drives this runtime from the composer — token streaming, inline approval cards, stop button, images via the paperclip, session restore after reload. On the static mirror, the same page falls back to client-side BYOK chat.

- **Implemented**: provider-backed turns; token streaming over SSE (live fan-out + persisted replay with seq dedup); tool execution through the real registry; approve/reject (once/reject — no standing policy), `409` busy, cancel endpoint; provider auth/billing errors recorded honestly in transcript notices + `turn_end.terminal_reason=provider_error`; cancellation with `terminal_reason=cancelled`.
- **MCP in the agent loop** (milestone 5): servers from `settings.json` started per turn (concurrent, failures isolated to notices); `mcp__server__tool` through the same permission + F1 approval path as native tools; capped output; step rows emit running/done/error.
- **Usage accounting** (milestone 5): `fleet_usage` migration v11; provider-reported token counts only (never invented); `GET /api/v2/sessions/:id` returns session aggregate; SSE `usage` events per turn; UI accumulates session tokens.
- **Image input** (milestone 5): `POST .../messages {images:[...]}` with mime/base64/size validation (400s), forwarded per-provider (OpenAI image_url, Gemini inlineData, Anthropic image blocks), desktop UI sends attachments automatically.
- **Tested with fake transport + a deterministic MCP stdio server**: 18 v2-path acceptance tests across `test_compat_runtime.py` / `test_compat_tracer.py` / `test_v2_mcp_usage_images.py`; full suite 442 passed (+10 opt-in live-smoke tests, skipped without keys).
- **End-to-end through the real browser** (milestone 4): a full open → message → streamed tokens → write_file approval card → Allow once → file written to disk, and a Deny run (file never created); transcript restored after reload; stop button and busy-409 confirmed. Simulated provider — a real provider call has NOT been made.
- **Verified with a live provider**: NOT YET — no provider keys on this host; `tests/test_live_smoke.py` skips cleanly and must be run by the operator with real keys.
- **Deliberately not implemented**: OpenCode event taxonomy/schema layer, plugins, PTY/computer use, standing-policy management via v2 (approve/reject never touch policy; `once` only), Postgres.

## What Keel does not cover

The remaining 30+ packages (CLI, TUI, app, session-ui, ui, ai, codemode, gui-plugins, protocol, schema, plugins, etc.) have no Keel equivalent in this milestone.

## Package status inventory (OpenCode only)

Statuses: `Not inspected`, `Inspected` (text visited), `Ported`, `Implemented`, `Tested`, `Verified`.

| Package | Files | LOC | Status | Keel equivalent |
|---|---|---|---|---|
| `packages/ai` | 824 | 110,553 | Inspected | none |
| `packages/app` | 1,260 | 358,616 | Inspected | none (`site/` is analogous, not same) |
| `packages/cli` | 214 | 27,671 | Inspected | partial (primitive `keel serve`) |
| `packages/client` | 74 | 25,777 | Inspected | none |
| `packages/codemode` | 148 | 51,220 | Inspected | none |
| `packages/core` | 929 | 231,455 | Inspected | partial (`runner.py`, `session.py` — not the same architecture) |
| `packages/data` | 132 | 34,487 | Inspected | `fleet/db.py` |
| `packages/desktop` | 247 | 29,755 | Inspected | `desktop-app/` (different architecture; analogous role) |
| `packages/gui-plugins` | 1,033 | 114,601 | Inspected | none |
| `packages/protocol` | 57 | 37,110 | Inspected | none (Keel has no schema layer) |
| `packages/schema` | 135 | 10,353 | Inspected | none |
| `packages/sdk` | 33 | 3,104 | Inspected | none |
| `packages/server` | 122 | 13,746 | Inspected | partial (`/api/*` — very different handler model) |
| `packages/session-ui` | 272 | 55,554 | Inspected | none (mirror UI only) |
| `packages/tui` | 556 | 124,484 | Inspected | none |
| `packages/ui` | 375 | 73,530 | Inspected | none |
| `packages/util` | 77 | 7,088 | Inspected | none |
| `services/*` | ~60 | ~8,000 | Inspected | none |
| `sdks/vscode` | 37 | ~2,500 | Inspected | none |

Every package above is marked `Inspected` only: we have read/classified the source files. None of them are `Tested`, `Implemented`, or `Verified` in Keel.

## New Keel capabilities (not in OpenCode)

- Windows installer + NSIS ceremony (Keel-branded sidebar, header)
- Local PWA + Settings + BYOK provider config
- Keel Fleet subagent framework (and SQLite schema v10)
- `shell_ast.py` safe command analysis
- `/download` page (installer validation milestone)
- `/api/v2/*` v2 runtime: provider-backed turns, SSE token streaming, SQLite persistence, approvals (milestone 3)

## Notices

See `THIRD_PARTY_NOTICES.md`. Keel ships no upstream OpenCode code as of this commit.
