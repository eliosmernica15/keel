# Keel — OpenCode-as-a-starting-point implementation plan

Working rule: **audit → notices → tracer bullet → download page → tests → checklist/roadmap.**

No upstream code is copied before `docs/THIRD_PARTY_NOTICES.md` is committed.  
No parity claims are made without tests/evidence.

## Phase 1 — Audit (done)

See `docs/PARITY.md` and machine-readable inventory `docs/parity.json`.

## Phase 2 — Third-party notices (done)

See `docs/THIRD_PARTY_NOTICES.md`.

## Phase 3 — Tracer bullet (this milestone)

New package `src/keel_compat/` — OpenCode-compatible REST/stream surface over the Keel runtime:

```
POST   /api/v2/sessions              -> 201 { id, title, createdAt }
POST   /api/v2/sessions/:id/messages -> 202 { runId }   (SSE stream on events)
GET    /api/v2/sessions/:id/events   -> text/event-stream   (session events)
GET    /api/v2/sessions/:id          -> 200 { session, messages }
POST   /api/v2/sessions/:id/approve  -> 200 { ok }          (F1-style approval)
```

- Real local tool calls only (`read_file`, `ls` — via existing Keel runtime)
- Real F1 approval gate (existing `permissions.py`)
- `tests/test_compat.py` — contract tests for the v2 surface

Honesty: this is a **tracer bullet**, not a port. Event shapes, persistence, and
streaming are simplified to prove the path. Real parity is tracked in
`docs/parity.json` with explicit `Not inspected` / `Ported` / `Verified` statuses.

## Phase 4 — Keel download experience

Mirror landing page (`site/`) is the download destination. A `/download` route will
be added to the static build:

- OS + arch auto-detect (x64/arm64; Windows / macOS / Linux)
- Manual platform override
- Displays version, size, SHA-256, release notes pointer
- Download destinations are **configurable at build time** (env vars), not hardcoded
- Documented blocker: hosted installer files require object-store/bucket credentials

## Phase 5 — Checklist + roadmap

`docs/CHECKLIST.md` enumerating every OpenCode capability with the actual status.
`docs/ROADMAP.md` for the next milestone.

## Explicit exclusions (this milestone)

- PostgreSQL, object storage, remote auth (later milestone)
- TUI port
- macOS/Linux installer verification (CI-only, unverified here)
- Live-provider end-to-end verification (no keys/quota on this host)
- Full OpenCode feature parity
