# UI Architecture & Renderer Decision Record

**Branch:** `feat/frontend-unified-workspace` (worktree `C:\Users\Admin\Desktop\keel-frontend-worktree`)
**Original base:** `integration/v6-addenda-complete` @ `c297d7a`
**Current baseline:** reconciled with `0865817` (merge `5a670c3`) and then `5dbc5f9` / `integration/v6-backend-complete` (merge `07a15fa`). Both merges were conflict-free and changed no frontend file; the only API-adjacent change was additive capability-hub registrations. No fleet bridge route, webapp route or payload shape changed.
**Scope:** unified frontend only. No backend, packaging or public-site behaviour was repointed.

---

## 1. Renderer inventory (Phase 0 result)

| Entry point | Asset root (source) | Role | Decision |
|---|---|---|---|
| `src/keel/webapp.py` (local bridge / `keel serve`) | `desktop/ui/` (default `UI_DIR`) | Current shipped local app | **Unchanged.** Stable product until parity gate. |
| `desktop-app/main.js` (Electron) | `uiRoot()` checks `site` before `desktop/ui` | Packaged desktop shell | **Unchanged in this branch.** Ambiguity recorded as a packaging workstream gate. |
| `desktop/src-tauri/tauri.conf.json` | `frontendDist: ../ui` | Tauri shell | **Unchanged.** |
| `site/app.html`, `site/ui/app.js` | public `/app` mirror | Browser-only BYOK mirror, no local agent/disk | **Unchanged.** Must stay visibly constrained. |
| `desktop/fleet/` | classic Fleet UI | Fleet reference implementation | **Preserved.** No deletion or retirement. |
| `fleet-next/` | Next.js 15 / React 19 / PWA + BFF proxy | Candidate unified product UI | **This workstream's implementation target.** |

### Critical path-selection risk

Electron's `uiRoot()` preference (`site` over `desktop/ui`) conflicts with the local bridge default and Tauri's `frontendDist`. This is a **packaging** decision that must be resolved with a real package build and an assertion that the intended local entry point loads. This frontend branch deliberately does **not** change it: repointing Electron to `fleet-next` before the parity/verification gate would risk removing local agent, filesystem and trust behaviour from the shipped app.

**2026-11-25 evidence update (Agent G, distribution QA — source + real bridge, not a packaged GUI run):** the current `desktop-app/main.js` `uiRoot()` prefers `resources/desktop/ui`, then legacy `resources/ui`; `resources/site` is reachable only behind `KEEL_UI_PROFILE=mirror`. `tests/distribution-qa/03-desktop-first-launch.spec.ts` verifies that source contract and, against a **real** `python -m keel serve --port 8742` with `KEEL_UI_DIR=desktop/ui`, that `GET /?t=…` returns the local-renderer title (not the `site/app.html` mirror) and `/api/fleet/bots` returns HTTP 200. The earlier `site`-first ambiguity is therefore **resolved in source and in a real-bridge round-trip**; a fresh packaged Electron GUI assertion (G4) is still not verified. No `fleet-next` default cutover is claimed.

## 2. Decision record

1. **Canonical unified renderer:** `fleet-next` is the implementation target for the unified Cowork/Code/Duet/Fleet experience because it already models all four surfaces, talks to the real Python bridge through a same-origin BFF, and is buildable/testable on this host. It is **not** declared the default shipped renderer for Electron/Tauri by this branch.
2. **Stable renderer:** `desktop/ui` remains the local bridge's default and the fallback until the feature-parity and packaged-build gates pass.
3. **Public mirror:** `site` stays a separate, reduced-capability browser surface. No desktop-only operation is exposed there.
4. **Backend authority:** Python owns execution, tools/MCP, permissions, trust, secrets, history and audit. The React app only renders state and sends intent through existing endpoints.
5. **Rollout:** surface-by-surface, with `desktop/ui` and classic Fleet retained as rollback paths. No legacy deletion in this branch.

## 3. Structure after decomposition

The 3,823-line `app/page.tsx` monolith was decomposed:

```
fleet-next/
├── app/
│   ├── layout.tsx          # theme-before-paint, metadata, PWA
│   ├── globals.css         # single source of colour tokens (Obsidian & Gold)
│   ├── ui.css              # semantic aliases, primitives, shell, responsive drawers
│   ├── page.tsx            # shell composition only
│   └── api/bridge/[...path]/route.ts   # unchanged BFF security boundary
├── components/
│   ├── ui.tsx              # shared primitives (one implementation per control)
│   └── icons.tsx           # original inline SVG icon set
├── lib/
│   ├── client.ts           # unchanged fetch helper
│   ├── api.ts              # typed, real endpoint catalogue
│   ├── types.ts            # shared domain types
│   └── state.tsx           # AppProvider / useApp (theme, surface, panels, notices)
└── features/
    ├── cowork/             # Subagent A
    ├── code/  duet/        # Subagent B
    ├── fleet/              # Subagent C
    ├── capabilities/  settings/  # Subagent D
    └── onboarding/         # Subagent E
```

**Ownership rule:** `app/*`, `lib/*`, `components/*` and `docs/*` are lead-owned. Each feature folder has exactly one owner. Feature code imports shared primitives; it never redefines them.

## 4. State and navigation model

- `Destination = Surface | "capabilities" | "settings"`. Surfaces are Cowork, Code, Duet, Fleet.
- Shell owns: top bar, surface switcher, left nav, resizable right context panel, status strip, command palette (`Ctrl/Cmd+K`), notices, keyboard shortcuts (`1`–`4`, `[`, `\`), onboarding layer.
- Feature modules own: their own data fetching, loading/empty/error states and internal layout. They receive no required props (except `Onboarding`'s `onDone`), which keeps them independently testable.
- Preferences persist in `localStorage`; agent data never does.

## 5. Migration map (not executed here)

| Gate | Requirement | Owner |
|---|---|---|
| G1 | All four surfaces reachable from one shell | frontend (this branch) |
| G2 | Feature-parity matrix green vs classic Fleet | frontend + Fleet owner |
| G3 | Real bridge round-trip exercised (needs provider credentials) | backend / operator |
| G4 | Electron and Tauri load the intended local build, asserted in packaging | packaging workstream |
| G5 | Public `/app` still browser-only and labelled | web workstream |
| G6 | Rollback flag to `desktop/ui` retained | packaging workstream |

Only after G1–G6 pass should the default renderer be changed, in a separate coordinated branch.

## 6. Finalization evidence (2026-11-25)

Gate status re-read against the current worktree. A source contract or a browser-only check is
recorded as such and is **not** promoted to a packaged-build claim.

| Gate | Evidence now available | Status |
|---|---|---|
| G1 — four surfaces + two destinations in one shell | browser walkthrough, `tests/e2e/` production suite **144 passed / 0 failed** after Agent G's integration | verified in browser |
| G2 — Fleet parity vs classic | `tests/features/fleet/` **20 passed**; `UI-FEATURE-PARITY.md` finalization reconciliation (rewind/export remain gaps) | verified for the listed flows; parity gaps remain documented |
| G3 — real bridge round-trip | Agent G `03-desktop-first-launch.spec.ts`: real `keel serve` on `:8742`, local renderer title, `/api/fleet/bots` HTTP 200; earlier 11 read-only endpoints HTTP 200 | verified for read-only/first-launch paths; live provider turn still blocked (no credentials) |
| G4 — Electron/Tauri packaged entry assertion | source contract verified; packaged GUI and fresh build not run (no Electron build tools, Tauri linker `link.exe` absent) | **not verified / external gate** |
| G5 — public `/app` stays browser-only and labelled | Agent G `02-pwa-journey.spec.ts` + `04-landing-regression.spec.ts`: start URL `/app` never `/download`, no `/app* → /download` rewrite, one contextual download link, landing/privacy/downloads pixel-identical | verified in browser on the site tree; no installed PWA window on a real OS |
| G6 — rollback flag to `desktop/ui` | still owner-gated packaging decision; legacy `desktop/ui` and classic Fleet are present and unchanged | **owner gate** |

Renderer decision is unchanged: `fleet-next` remains the candidate unified UI, `desktop/ui` the
shipped local fallback, `site` a visibly constrained browser mirror. No production-readiness
claim is made here; see `FINAL-STABILIZATION-ACCEPTANCE.md` (`PASS_WITH_EXTERNAL_LIMITATIONS`).
