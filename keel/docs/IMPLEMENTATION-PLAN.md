# Keel — OpenCode-as-a-starting-point implementation plan

Working rule: **audit → notices → tracer bullet → download page → tests → checklist/roadmap.**

No upstream code is copied before `docs/THIRD_PARTY_NOTICES.md` is committed.  
No parity claims are made without tests/evidence.

## Phase 1 — Audit (done)

See `docs/PARITY.md` and machine-readable inventory `docs/parity.json`.

## Phase 2 — Third-party notices (done)

See `docs/THIRD_PARTY_NOTICES.md`.

## Phase 3 — Tracer bullet (this milestone) → **superseded by milestones 3+4 (2026-11-19)**

The tracer became the real thing. `/api/v2/sessions` is now wired to the actual
agent runtime (`fleet/turn_core.py`, `session.py`, `fleet/tools.py`, real
provider adapters), persists in SQLite (`fleet/db.py` v10), streams tokens over
SSE (`docs/EVENTS.md`), is covered by 12 acceptance tests in
`tests/test_compat_runtime.py`, and is driven end-to-end from the desktop
browser UI (token streaming, approval cards, stop, session restore across
reloads). The "tracer bullet — not a port" caveat still applies: no OpenCode
schema/event taxonomy, no plugins, no standing-policy management via v2.
See `docs/PARITY.md` for the honest status table.

Historical contract (still the live shape):

```
POST   /api/v2/sessions              -> 201 { id, title, ... }
POST   /api/v2/sessions/:id/messages -> 202 { ok, runId, ... }
GET    /api/v2/sessions/:id/events   -> text/event-stream (replay + live)
GET    /api/v2/sessions/:id          -> 200 { session, messages }
GET    /api/v2/sessions/:id/pending  -> 200 { approvals: [...] }
POST   /api/v2/sessions/:id/approve  -> 200 { ok, ... }
POST   /api/v2/sessions/:id/reject   -> 200 { ok, ... }
POST   /api/v2/sessions/:id/cancel   -> 200 { ok, cancelled: true }
DELETE /api/v2/sessions/:id          -> 200 { ok: true }
```

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
