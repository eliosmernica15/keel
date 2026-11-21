# AGENTS.md — Keel repository guide

This file is for agents working **inside** the Keel codebase. It is injected
as untrusted project context; the operator's latest instruction still wins.

## Layout

- `src/keel/` — authoritative Python runtime (sessions, permissions, fleet,
  providers, tools, web bridge, release pipeline).
- `src/keel/fleet/` — multi-agent fleet, approvals, policies and task rounds.
- `src/keel/release/` — build, signing, verification and updater.
- `src/keel/providers/` — provider adapters and the session-facing client.
- `tests/` — pytest acceptance suite; run it before claiming completion.
- `desktop-app/` — Electron shell; Python remains authoritative.
- `site/` — downloadable web UI and static pages.
- `scripts/` — plan registry and v6 plan generation.
- `docs/IMPLEMENTATION-PROGRESS.md` — batch ledger and evidence.
- `PLAN-INDEX.json` / `parity.json` — canonical feature registry and its
  synchronized projection (generated; never hand-edit either).
- `Keel_Master_Plan_v6.md` — canonical roadmap (generated; do not hand-edit).

## Commands

- `python -m pytest -q` — full suite (must pass before a batch commit).
- `python -m pytest tests/<file>.py -q` — targeted tests during a batch.
- `python -m keel ...` — CLI entry point (`init`, `serve`, `tools`, `attach`,
  `costs`, `model`, `release`).
- `python scripts/build_plan_index.py && python scripts/build_v6_plan.py` —
  regenerate the registry and v6 plan after changing registry metadata.
- `node --check site/ui/*.js` — syntax check UI JavaScript.

## Conventions

- One focused batch at a time: implement, add tests, run targeted and full
  suites, update the progress ledger and registry, then commit locally.
- Never push, publish, deploy, rotate production credentials, or change repo
  visibility without explicit owner approval.
- Never fabricate evidence. Cite the actual command output and its result.
- Preserve local-first behaviour: no mandatory cloud service, account or paid
  dependency. New libraries require license/security/packaging review.
- All destructive operations use recoverable trash, approval or dry-run paths.
- Secrets are encrypted at rest; redact credentials before remote calls.
- Keep feature IDs from both addenda unchanged; no silent omissions.

## Evidence before claims

A feature is `verified` only when its tests and real-runtime checks pass.
Code alone is `implemented`; blocked features name their specific owner gate.
Prefer reporting "not verified" to an optimistic "done".
