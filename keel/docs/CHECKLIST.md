# Keel — migration checklist

Branch: `main` (Keel repo, public)
Status legend: `done` (verified by tests/evidence), `partial` (exists, limited scope), `blocked` (needs credentials/hardware/decision), `not started`, `excluded` (documented reason), `open` (not inspected yet).

## This milestone (Completeness)

| Tag | Item | Status | Evidence |
|---|---|---|---|
| Audit | Full OpenCode source inspection | done | `docs/PARITY.md`, `docs/parity.json` |
| Notices | Third-party license notices | done | `docs/THIRD_PARTY_NOTICES.md` |
| Tracer | `/api/v2/sessions` POST/GET | done | `src/keel/compat.py`, tests green |
| Tracer | `/api/v2/sessions/:id/approve` | done | exists in `test_compat_tracer.py` |
| Tracer | `/api/v2/sessions/:id/messages` | done | same |
| Tracer | `/api/v2/sessions/:id/events` | partial | server-streaming shape, no real stream yet |
| Downloads | Mirror `/download` page | done | `site/download.html`, `/ui/download.js`, `/download.json` |
| Downloads | Download destinations configurable | done | destinations from `download.json` |
| Downloads | Route rewrites in `vercel.json` | done | `/download` -> `/download.html` |

## Not done yet (documented honestly)

- PostgreSQL / object storage — later milestone.
- macOS / Linux installer verification — CI-only, unverified on real hardware.
- Live-provider end-to-end verification — no keys/quota on this host.
- Full OpenCode feature port — multi-month work; not claimed.
- Public signing / SmartScreen-ready binary.
- Installer hosting verification (requires object-store bucket creds — none available).
- Port of OpenCode server routes, tools, plugins, MCP surface.
- PostgreSQL adapter / migration tooling.
- User accounts / PostgreSQL / object storage / sync.
- Production download verification — requires hosting credentials.
