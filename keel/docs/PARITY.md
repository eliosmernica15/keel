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
| Local agent runtime | `packages/core` `ai/*` | **Ported-to-Python (partial)** | `runner.py`, `fleet/turn_core.py` — no streaming, no resume, no compaction |
| SQLite persistence | `packages/core` `database/*` | **Reused** | `fleet/db.py`, `session.py` — similar role, not the same schema |
| File tools | `search/glob/grep/read/write/patch` | **Ported-to-Python** | `shell_ast.py`, `permissions.py`, `hooks.py` — subset |
| Provider routing | `packages/providers` | **Ported-to-Python** | `providers/` — OpenRouter + Google working; no fallbacks |
| PWA / web UI | `packages/app` `ui` `session-ui` | **Reused (closely related UI)** | `site/`, `desktop/ui` — similar visual design, not the same build |
| Skills | `packages/skills` (not listed) | **New in Keel** | `_parse_frontmatter` in `skills.py`, `/api/skills` endpoint |
| MCP | `packages/core/mcp` | **Reused** | `src/keel/mcp.py` — partial overlap only |

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
- Keel Fleet subagent framework (and SQLite schema)
- `shell_ast.py` safe command analysis
- `/download` page (this milestone)
- `/api/v2/*` OpenCode-compat surface (this milestone, tracer bullet)

## Notices

See `THIRD_PARTY_NOTICES.md`. Keel ships no upstream OpenCode code as of this commit.
