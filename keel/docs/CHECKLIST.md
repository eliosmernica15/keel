# Keel — migration checklist

Branch: `main` (Keel repo, public)
Status legend: `done` (verified by tests/evidence), `partial` (exists, limited scope), `blocked` (needs credentials/hardware/decision), `not started`, `excluded` (documented reason), `open` (not inspected yet).

## This milestone (Completeness)

| Tag | Item | Status | Evidence |
|---|---|---|---|
| Runtime milestone 3 | v2 surface provider-backed (full flow: session→message→provider→tools→approval→transcript→restart→replay) | done | `tests/test_compat_runtime.py` (12 acceptance tests), full suite green |
| Runtime milestone 4 | Browser end-to-end agent flow (serve site UI, send, approval card, allow/deny, file written, transcript restored after reload) | done (dev-bridge + scripted fake transport; packaged retry pending CI build) | manual browser drive of the real UI at `localhost:8798` on 2026-11-19 |
| Runtime milestone 4 | Desktop app serves the agent UI at `/` (not the landing page) | done | `webapp.py`: `/` → `app.html` when present, else `index.html`; cookie unchanged |
| Runtime milestone 4 | v2 session ids are opaque (`token_urlsafe`), not slugs | done | `create_bot(bot_id=…)` in the fleet store; v2 sessions pass random ids |
| Runtime milestone 4 | Cross-platform runtime CI (ubuntu/windows/macos) | done | `.github/workflows/python-tests.yml` — all three green on run `44556804615` (2026-11-19) |
| Runtime milestone 5 | MCP tools in the v2 agent loop (offer → approval → execution) | done | real turn exercises `mcp__fake__echo` through Tier-1 + F1 approval → executed (`tests/test_v2_mcp_usage_images.py`); MCP failures isolated to notices |
| Runtime milestone 5 | Usage accounting in fleet.db (v11 ledger, `/sessions/:id` aggregates) | done | per-turn rows + `usage` SSE events; survives restart (test asserts fresh store reload); cost never invented |
| Runtime milestone 5 | Image input for v2 messages | done | png/jpeg/gif/webp ≤ 4 MB, ≤ 8/message, 32 MB body cap; per-provider forwarding (image_url/inlineData/image block); 400 on bad mime/base64 |
| Runtime milestone 5 | Desktop UI: images via paperclip; usage tokens in the status bar; restore re-seeds totals | done | manual browser verification at `127.0.0.1:8798` (agent mode, fake transport) |
| Runtime milestone 5 | MCP test coverage in CI (deterministic stdio server) | done | `.github/workflows/python-tests.yml` matrix runs it |
| Live smoke | Live provider verification with a real key | blocked | needs operator keys; `tests/test_live_smoke.py` ready and skipping cleanly |
| Runtime milestone 4 | Packaged installer verified to serve the agent UI at `/` | done | milestone-4 artifact (run `44556804719`): silent install → packaged sidecar serves app UI at `/` (not landing), health `0.1.0` OK, uninstall clean, `~/.keel` preserved |
| Live smoke | Opt-in live provider tests (auth success/failure, streaming) | skipped cleanly (no keys on this host) | `tests/test_live_smoke.py` |
| Live smoke | Live provider verification with a real key | blocked | needs operator-configured keys; must not be done without them |
| Audit | Full OpenCode source inspection | done | `docs/PARITY.md`, `docs/parity.json` |
| Notices | Third-party license notices | done | `docs/THIRD_PARTY_NOTICES.md` |
| Tracer | `/api/v2/sessions` POST/GET list/delete | done | `src/keel/compat.py` (fleet-backed), tests green |
| Tracer | `/api/v2/sessions/:id/approve` (+ reject, 404 on unknown, busy 409) | done | `test_compat_runtime.py` (12 acceptance tests green) |
| Tracer | `/api/v2/sessions/:id/messages` POST/GET | done | same |
| Tracer | `/api/v2/sessions/:id` GET (session + messages) | done | same |
| Tracer | `/api/v2/sessions/:id/events` | done | replay+live SSE, seq cursor, token frames, `?since=`, ping keep-alive (`docs/EVENTS.md`) |
| Tracer | Provider-backed runtime | done | turn executes through `fleet/turn_core.py` + `Session` + real tool registry; fake transport in CI only |
| Tracer | Approval broker integration | done | F1 broker: pending → approve (allow once) / reject (deny, no standing policy); `test_tool_rejected_never_executes` proves the tool does not run |
| Tracer | SQLite persistence across restart | done | sessions are `fleet.db` bots (kind='session'); survives process restart; migration v10 |
| Tracer | Cancel active run | done | POST `/api/v2/sessions/:id/cancel`; `terminal_reason=cancelled` asserted in tests |
| Tracer | `sessions_list()` deadlock (non-reentrant lock) | fixed | `_LOCK` is now `RLock`; milestone 3 removed the in-memory store entirely |
| Downloads | Mirror `/download` page | done | `site/download.html`, `/ui/download.js`, `/download.json` |
| Downloads | Download destinations configurable | done | destinations from `download.json` |
| Downloads | Route rewrites in `vercel.json` | done | `/download` -> `/download.html`, `/app` -> `/app.html` |
| Site | Premium developer landing page | done | `site/index.html` + `site/ui/landing.css`/`landing.js`; mirror moved to `/app`; real screenshots; Lighthouse a11y/best-practices/SEO 1.0 |
| CI | Workflow discovered by GitHub Actions | done | `.github/workflows/build-desktop.yml` at repo root (was nested at `keel/.github/` where it was invisible) |
| CI | Windows build (runner, not this host) | done | run `44431591087` green 2026-11-19; NSIS artifact produced; sha256 `43a5eb7d…` |
| CI | macOS build (runner; arm64 only) | done | same run; `Keel-0.1.0-macos-arm64.dmg/.zip`; Intel untested; Gatekeeper unsigned |
| CI | Linux build | done | same run; `Keel-0.1.0-linux-x86_64.AppImage`, `Keel-0.1.0-linux-amd64.deb`; not run on a desktop Linux yet |
| Tests | Full suite | done | `pytest -q` -> 442 passed, 10 smoke skipped (2026-11-19, milestone 5) |
| Installer validation | Windows installer (CI artifact, run `44527352992`) | done | hash verified; silent install → launch → frozen sidecar on 127.0.0.1:8857; `/api/health` 403 (token-protected); `/ui/style.css` 200; reinstall OK; silent uninstall removed dir; `~/.keel` fully preserved |
| Installer validation | macOS DMG/ZIP (arm64) | partial | CI build green; hashes verified; zip structure inspected (Mach-O 64-bit, app.asar, frozen sidecar present, Info.plist sane, LSMinimum 12.0); UNSIGNED (no _CodeSignature); never mounted on a Mac; Intel unsupported |
| Installer validation | Linux AppImage + .deb | partial | hashes verified; `.deb` control/deps/desktop-entry/postinst inspected; AppImage ELF x86-64 type-2 w/ squashfs verified; not launched on desktop Linux |
| Release pipeline | version sync gate + release manifest + post-upload verification | done | `scripts/check_version_sync.py`, `make_release_manifest.py`; CI green incl. validate-versions |
| Website | `/download` correctness fixes (nav, brand icon, meta wrap, arch-aware OS detect) | done | verified locally; production re-verify pending deploy (will flip to done evidence with run id) |

## Not done yet (documented honestly)

- PostgreSQL / object storage — later milestone.
- Install-and-launch verification on real macOS/Linux hardware — CI built the artifacts, nobody ran them yet.
- Live-provider end-to-end verification — no keys/quota on this host.
- Full OpenCode feature port — multi-month work; not claimed.
- Public signing / SmartScreen / Gatekeeper-ready binaries — needs certificates.
- Installer hosting verification — artifacts exist as GitHub Actions workflow artifacts (run `44431591087`) but are NOT publicly distributed; needs object-store credentials.
- Port of OpenCode server routes, tools, plugins, MCP surface.
- PostgreSQL adapter / migration tooling.
- User accounts / PostgreSQL / object storage / sync.
- Production download verification — requires hosting credentials.
