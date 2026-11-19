# Keel — roadmap (next milestones)

Caveats up front:

- Judgment about timelines is approximate. The remaining scope is a multi-month project; the biggest risk left in the desktop pipeline is signing and per-OS first-run UX, not building.
- CI now builds and verifies Windows/macOS/Linux installers on every push (workflow at `.github/workflows/build-desktop.yml`), but **no installer is publicly downloadable yet** — that needs Keel-controlled object storage plus credentials, and `site/download.json` stays `available: false` until a real download has been tested end to end.
- macOS/Linux signing is not possible from this Windows machine; the .dmg/.AppImage/.deb are unsigned and will be blocked or warned about by Gatekeeper/SmartScreen/distro policies. An Apple Developer ID and a code-signing strategy are prerequisites for frictionless installs.

## Milestone 2 — Python runtime to OpenCode contract parity (3–6 months)

Done in milestone 3 (2026-11-19):

- Real event streaming on `/api/v2/sessions/:id/events` over SSE — **done** (replay + live, `docs/EVENTS.md`).
- Provider-backed agent runtime — **done** (turn through `Session` + real tool registry, approvals via the F1 broker, transcript persisted in SQLite; fake-transport-verified in CI).
- Local persistence of sessions — **done** via existing SQLite (`fleet.db`, migration v10); sessions survive restart. PostgreSQL deliberately not introduced.
- Automated test matrix on Windows + macOS + Linux via CI — **done** (`.github/workflows/python-tests.yml` runs the suite on all three runners).

Done in milestone 4 (2026-11-19):

- Desktop browser end-to-end: agent chat in the app UI (token streaming, inline approval cards, allow/deny through the real broker, stop button, session restore across reloads, folder-bound cwd via `/api/workdir`, opaque session ids).

Done in milestone 5 (2026-11-19):

- MCP servers (from `settings.json` / `keel fleet`) are started concurrently per turn on the v2 agent path; `mcp__server__tool` names flow through the same F1 approval gate as native tools; failures degrade to notices, never to a broken turn.
- Per-turn usage accounting persisted to `fleet.db` (migration v11; provider-reported counts only; `cost_basis=unknown`); aggregate shown on the session; SSE `usage` events replay across restarts.
- Image input (`image/png|jpeg|gif|webp`, ≤ 4 MB, ≤ 8) forwarded per-provider; desktop UI sends attachments automatically.

Still open:

- Live-provider end-to-end verification with a real key (no keys on this host; must be run by the operator).
- OpenCode surface coverage beyond v2 sessions (schemas, plugins, more of `packages/server`).
- First measured parity report like this document — with coverage numbers, not claims.

## Milestone 3 — Desktop packaging distribution

- CI builds Windows / macOS / Linux artifacts — done in CI (run `44431591087`, 2026-11-19): `Keel-Setup-0.1.0.exe`, `Keel-0.1.0-macos-arm64.dmg/.zip`, `Keel-0.1.0-linux-x86_64.AppImage`, `Keel-0.1.0-linux-amd64.deb`. Not publicly distributed; not install-tested on macOS/Linux hardware.
- sha256 manifest and `latest.json`-style release manifest — `SHA256SUMS-*.txt` produced per OS in CI; combined `RELEASE-SHA256SUMS.txt` staged for tags via `prepare-installers`. A `latest.json` manifest for the mirror is not built yet.
- SmartScreen / Gatekeeper readiness (signing certificate, notarization) — not started; needs certificates.
- Distribution via Keel-controlled R2/S3 bucket with the `/download` page pointing at hosted objects (never public GitHub Releases) — blocked on Cloudflare R2 (or S3) credentials; see `docs/HOSTING.md`. The `upload-to-hosting` CI job is in place and gated on the `R2_UPLOAD_ENABLED` repository variable.

## Milestone 4 — Provider & model ecosystem parity

- OpenCode `/api/models` semantics where Keel is weaker (fallback, rate-limit disable).
- Provider smoke runner with real keys and real 402/401 ground truth.
- Token tracking and cost reporting.

## Milestone 5 — TUI / CLI parity (optional)

- Audit-only today. Not a priority until the backend works end-to-end.
