# UI Architecture & Renderer Decision Record

**Branch:** `feat/frontend-unified-workspace` (worktree `C:\Users\Admin\Desktop\keel-frontend-worktree`)
**Base:** `integration/v6-addenda-complete` @ `c297d7a`
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
