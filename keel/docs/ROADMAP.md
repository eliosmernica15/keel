# Keel — roadmap (next milestones)

Caveats up front:

- Judgment about timelines is approximate. The remaining scope is a multi-month project; the single biggest risk is in shipping a broken 122 MB binary into a CI pipeline I have not seen succeed.
- The hosting decision (GitHub Releases vs. Keel Cloud) is still unresolved enough that download destinations are hardcoded in `site/download.json` today. That must change before public CI artifacts are published.
- macOS/Linux signing is not possible from this Windows machine without a Mac or Linux runner and an Apple Developer ID.

## Milestone 2 — Python runtime to OpenCode contract parity (3–6 months)

- Port `/api/v2/sessions` persistence to Postgres (local-first keeps SQLite fallback).
- Real event streaming on `/api/v2/sessions/:id/events` over SSE.
- Skills + plugins + MCP capability registry.
- Permission model enforcement identical to Keel's current `permissions.py`.
- Automated test matrix on Windows + macOS + Linux via CI.
- First measured, public parity report like this document — with coverage numbers, not claims.

## Milestone 3 — Desktop packaging distribution

- CI builds Windows / macOS / Linux artifacts.
- sha256 manifest and `latest.json`-style release manifest.
- SmartScreen / Gatekeeper readiness (signing certificate, notarization).
- GitHub Releases workflow for public downloads, or Keel Cloud bucket install.

## Milestone 4 — Provider & model ecosystem parity

- OpenCode `/api/models` semantics where Keel is weaker (fallback, rate-limit disable).
- Provider smoke runner with real keys and real 402/401 ground truth.
- Token tracking and cost reporting.

## Milestone 5 — TUI / CLI parity (optional)

- Audit-only today. Not a priority until the backend works end-to-end.
