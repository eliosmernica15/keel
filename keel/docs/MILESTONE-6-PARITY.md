# Milestone 6 — Parity (Keel vs. OpenCode)

Date: 2026-11-20
Status: PLAN MODE.

This document tracks high-level parity. Detailed per-package inventory remains in `docs/PARITY.md` and `docs/parity.json`.

## Summary

OpenCode is ~1.6 MLOC across 39 capability areas. Keel's Python runtime (~12.4 kLOC) plus Fleet (~large) covers a thin but real slice. Milestone 6 aims to close the gap in the capabilities that matter for a local-first harness, not to clone OpenCode's full surface (no TUI port, no cloud services).

## Parity table (target vs. current)

| Capability | OpenCode | Keel current | Milestone 6 target |
|---|---|---|---|
| Agent turn loop | Full | Verified | Unified runtime, extended |
| Tool registry | Full, typed | Partial (hardcoded list) | Central registry + discovery |
| Filesystem tools | read/write/patch/glob/grep | Partial | Complete set + patch/diff/move/watch |
| Terminal tools | Full | Partial (run_shell) | Full set + background |
| Web tools | search/fetch/browser | Missing | web_search/fetch + optional browser |
| Git/dev tools | Full | Partial (shell-out) | Dedicated tools |
| Skills | packages/skills | Partial (discovery) | Full lifecycle + auto-load |
| MCP | multi-transport + resources/prompts | Partial (stdio, tools) | HTTP + reconnect + health + resources/prompts |
| Plugins | packages/plugins, gui-plugins | Missing | Manifest + lifecycle + API |
| Connectors | Various | Partial (MCP) | Connector framework |
| Commands | Full | Partial (slash palette) | Manager + templates + workflows |
| Workflows | Full | Missing | Workflow engine |
| Subagents | Full | Partial (Task, send_to_bot, groups) | Specialized agents + real parallelism |
| Memory | Full | Partial (notes, transcripts) | Persistent memory + retrieval |
| Project intelligence | Full | Partial (file tree, projects) | Indexing, symbols, deps, ignore rules |
| Hooks | 33 events | Partial (2 wired) | All events + Python handlers |
| Browser/computer use | Full | Partial (iframe preview) | Optional browser tools |
| Providers | Many | 5 adapters | Keep; add rate-limit/fallback parity |
| Persistence | SQLite/Postgres | SQLite (local) | Keep SQLite |
| Desktop UI | Full Tauri | Electron + web | Management screens |
| TUI | Full | None | Out of scope (optional later) |
| Release/distribution | N/A | Verified (GitHub Releases) | Keep |

## Non-goals (explicit)

- No TUI port.
- No cloud backend / Supabase / Firebase.
- No copying upstream code without notices.
- No claiming parity without evidence.

## Status classification for every feature

Every feature in the milestone docs is classified as: Already implemented and verified; Implemented but incomplete; Needs integration; Needs implementation; Blocked (with reason). See `MILESTONE-6-AUDIT.md`.
