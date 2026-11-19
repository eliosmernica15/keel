# Keel — migration checklist

Branch: `main` (Keel repo, public)
Status legend: `done` (verified by tests/evidence), `partial` (exists, limited scope), `blocked` (needs credentials/hardware/decision), `not started`, `excluded` (documented reason), `open` (not inspected yet).

## This milestone (Completeness)

| Tag | Item | Status | Evidence |
|---|---|---|---|
| Audit | Full OpenCode source inspection | done | `docs/PARITY.md`, `docs/parity.json` |
| Notices | Third-party license notices | done | `docs/THIRD_PARTY_NOTICES.md` |
| Tracer | `/api/v2/sessions` POST/GET list/delete | done | `src/keel/compat.py`, tests green |
| Tracer | `/api/v2/sessions/:id/approve` (+ reject, 404 on unknown) | done | `test_compat_tracer.py` (8 tests green) |
| Tracer | `/api/v2/sessions/:id/messages` POST/GET | done | same |
| Tracer | `/api/v2/sessions/:id` GET (session + messages) | done | same |
| Tracer | `/api/v2/sessions/:id/events?since=` | partial | buffered replay with since-filter; not live SSE yet |
| Tracer | Latent deadlock in `sessions_list()` (non-reentrant lock) | fixed | caught by new tests; `_LOCK` is now `RLock` |
| Downloads | Mirror `/download` page | done | `site/download.html`, `/ui/download.js`, `/download.json` |
| Downloads | Download destinations configurable | done | destinations from `download.json` |
| Downloads | Route rewrites in `vercel.json` | done | `/download` -> `/download.html`, `/app` -> `/app.html` |
| Site | Premium developer landing page | done | `site/index.html` + `site/ui/landing.css`/`landing.js`; mirror moved to `/app`; real screenshots; Lighthouse a11y/best-practices/SEO 1.0 |
| CI | Workflow discovered by GitHub Actions | done | `.github/workflows/build-desktop.yml` at repo root (was nested at `keel/.github/` where it was invisible) |
| CI | Windows build (runner, not this host) | done | run `44431591087` green 2026-11-19; NSIS artifact produced; sha256 `43a5eb7d…` |
| CI | macOS build (runner; arm64 only) | done | same run; `Keel-0.1.0-macos-arm64.dmg/.zip`; Intel untested; Gatekeeper unsigned |
| CI | Linux build | done | same run; `Keel-0.1.0-linux-x86_64.AppImage`, `Keel-0.1.0-linux-amd64.deb`; not run on a desktop Linux yet |
| Tests | Full suite | done | `pytest -q` -> 427 passed (2026-11-19) |
| Installer validation | Windows installer (CI artifact, run `44527352992`) | done | hash verified; silent install → launch → frozen sidecar on 127.0.0.1:8857; `/api/health` 403 (token-protected); `/ui/style.css` 200; reinstall OK; silent uninstall removed dir; `~/.keel` fully preserved |
| Installer validation | macOS DMG/ZIP (arm64) | partial | CI build green; hashes known; zip structure not yet inspected; never mounted on a Mac; Intel unsupported |
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
