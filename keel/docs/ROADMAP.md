# Keel — roadmap (next milestones)

Caveats up front:

- Judgment about timelines is approximate. The remaining scope is a multi-month project; the biggest risk left in the desktop pipeline is signing and per-OS first-run UX, not building.
- CI now builds and verifies Windows/macOS/Linux installers on every push (workflow at `.github/workflows/build-desktop.yml`), but **no installer is publicly downloadable yet** — that needs Keel-controlled object storage plus credentials, and `site/download.json` stays `available: false` until a real download has been tested end to end.
- macOS/Linux signing is not possible from this Windows machine; the .dmg/.AppImage/.deb are unsigned and will be blocked or warned about by Gatekeeper/SmartScreen/distro policies. An Apple Developer ID and a code-signing strategy are prerequisites for frictionless installs.

## Milestone 2 — Python runtime to OpenCode contract parity (3–6 months)

- Port `/api/v2/sessions` persistence to Postgres (local-first keeps SQLite fallback).
- Real event streaming on `/api/v2/sessions/:id/events` over SSE.
- Skills + plugins + MCP capability registry.
- Permission model enforcement identical to Keel's current `permissions.py`.
- Automated test matrix on Windows + macOS + Linux via CI.
- First measured, public parity report like this document — with coverage numbers, not claims.

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
