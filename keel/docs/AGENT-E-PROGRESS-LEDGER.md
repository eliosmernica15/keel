# Integration Progress Ledger (Agent E) — 2026-11-25

Owned doc: this ledger + the edits to `UI-ARCHITECTURE.md`, `UI-TEST-MATRIX.md`,
`UI-FEATURE-PARITY.md`, plus the new `RELEASE-2026-11-25.md`.

Rule (from existing practice): no row moves to `pass` without a recorded command result or an existing cited artifact; `not run` / `pending` are not passes.

## 1. Worktree state at start of Agent E work

- Branch `feat/unified-renderer-electron-2026-11-25`, base `bcc9123` ("Merge pull request #20 ... final-production-release-2026-11-25").
- `git status --short`: modified `keel/desktop-app/main.js`, `keel/desktop-app/package.json`,
  `keel/desktop-app/scripts/assert-ui-entrypoints.js`, `keel/docs/UI-ARCHITECTURE.md`,
  `keel/docs/UI-FEATURE-PARITY.md`, `keel/docs/UI-TEST-MATRIX.md`,
  `keel/fleet-next/app/page.tsx`, `keel/fleet-next/next.config.mjs`,
  `keel/fleet-next/package.json`, `keel/fleet-next/tsconfig.json`;
  untracked `keel/desktop-app/renderer-policy.js`, `keel/desktop-app/tests/`,
  `keel/docs/BRIDGE-INTEGRATION-VERIFICATION.md`, `keel/docs/ELECTRON-INTEGRATION-QA.md`,
  `keel/docs/RENDERER-FALLBACK-POLICY.md`, `keel/docs/RENDERER-INTEGRATION-CONTRACT.md`,
  `keel/docs/UNIFIED-DESKTOP-INTEGRATION.md`, `keel/fleet-next/docs/`,
  `keel/fleet-next/scripts/`, `keel/fleet-next/tests/bridge-integration/`,
  `keel/fleet-next/tests/packaged-compat/`, `keel/fleet-next/tests/packaged-qa/`.
- Session moved to this worktree via `tools.opencode.session.move` (dir `C:\Users\Admin\Desktop\keel-frontend-worktree`).

## 2. Agents — what each did (status at Agent E start)

| Agent | Scope (files) | Report doc | Expected/recorded result |
|---|---|---|---|
| A — renderer-integration contract | source audit of `keel/docs/RENDERER-INTEGRATION-CONTRACT.md` | same doc | source-evidence audit, read-only; recorded 15 observation rows (incl. `HOST`→`HOSTNAME` defect, `DEFAULT_RENDERER=UNIFIED` governance flip) |
| B — execution audit | `keel/docs/AGENT-EXECUTION-AUDIT.md`, `keel/tests/audit_agent_execution_lifecycle.py`, `keel/tests/audit_agent_execution_control.py` | same doc | 7 passed / 3 xfailed (A-1/A-2/A-3, non-strict); regression run 100 passed / 3 xfailed |
| C — agent audit | `keel/docs/DISTRIBUTION-AGENT-AUDIT.md`, `keel/tests/verify_distribution_agent_{renderer,echo,execution}.py` | same doc | 9 passed (33.64 s); F-1 no-credential scripted fake, F-2 sidecar predates merge (rebuilt by Agent E 2026-11-25 01:20:28Z), F-3/F-4 inheritied echo/ask gaps |
| D — bridge verification | `keel/docs/BRIDGE-INTEGRATION-VERIFICATION.md`, `keel/fleet-next/tests/bridge-integration/**` | same doc | 24/24 (2.0 min) against a real Python bridge on :8797; token never in browser bundle/network/localStorage |
| G — QA + Agent G probes | `keel/docs/ELECTRON-INTEGRATION-QA.md`, `keel/docs/DISTRIBUTION-QA.md`, `keel/docs/FRONTEND-FINALIZATION-QA.md` + `fleet-next/tests/packaged-qa/**` | same docs | packaged EXE probes: default launch (15:24–15:26Z) unified, G6 legacy (15:24:38Z), mirror (15:19:23Z); 42/42 distribution QA; 144/144 prod E2E |

Not run by/to Agent E (no conflict, Agent E only touches doc + this ledger):
Agent E/F packaging docs, Team G run of `assert-ui-entrypoints.js` (23/25 red gate, R10), `next build:standalone` (1 failed attempt recorded), etc.

## 3. Commands run by Agent E (verbatim)

```powershell
# EXE measurements (run 1, then re-verified run 2)
Get-FileHash -Algorithm SHA256 -Path keel\dist\win-unpacked\Keel.exe, keel\dist\Keel-Setup-0.1.1.exe | Select-Object Hash, Path
Get-FileHash -Algorithm SHA256 -Path keel\dist\win-unpacked\Keel.exe
Get-FileHash -Algorithm SHA256 -Path keel\dist\Keel-Setup-0.1.1.exe
Get-ChildItem -Path keel\dist\win-unpacked\Keel.exe, keel\dist\Keel-Setup-0.1.1.exe | Select-Object Name, Length, LastWriteTimeUtc

# Source default renderer
node -e 'const src=require("fs").readFileSync("desktop-app/renderer-policy.js","utf8"); const m=src.match(/DEFAULT_RENDERER\s*=\s*"([^"]+)"/); console.log("DEFAULT_RENDERER =", m && m[1]); const m2=src.match(/RENDERER_MODES\s*=\s*\{[^}]*\}/); console.log(m2 && m2[0].slice(0,220)); const i=src.indexOf("function resolveRenderer"); console.log(src.slice(i, i+300));'
```

Results (verified twice, identical):

| Item | Value |
|---|---|
| `Keel.exe` size | 235,419,136 bytes |
| `Keel.exe` SHA-256 | `D52DB523BE65DE981320A175B9DA3C29B5B2F5925D3AED787CAA0F0254288B20` |
| `Keel-Setup-0.1.1.exe` size | 158,152,373 bytes |
| `Keel-Setup-0.1.1.exe` SHA-256 | `170F1361C786D80DC8B6ECCE5C5561592D6C42A5BFE2FB2010D98C0C491667BC` |
| `keel/dist/keel-sidecar/keel.exe` (bundled) | 31,436,836 bytes / `B091538D9E2E1284DAD3F85AC0B31DC532073331D140777B2FFA282EBD8431FF` |
| `desktop-app/renderer-policy.js` source default | `DEFAULT_RENDERER = RENDERER_MODES.UNIFIED` (line 46) |

Other inputs read (not run again): `keel/site/download.json` (all channels `available:false`),
`keel/src/keel/release/build.py:163` + `publish.py:122` (public base `https://github.com/eliosmernica15/keel/releases/download`),
`keel/fleet-next/tests/distribution-qa/01-download-journey.spec.ts` (16 tests, 42/42 with Agent G),
`keel/site/tests/*.test.mjs` (20 passed), `keel/docs/UI-DEFECT-LOG.md` QA-F-010 (Kanban drag).

## 4. Pass/fail summary

| # | Action | Status | Evidence |
|---|---|---|---|
| A-1 | Read Agent A contract | done | `docs/RENDERER-INTEGRATION-CONTRACT.md` (396 lines) |
| A-2 | Read Agent B execution audit | done | `docs/AGENT-EXECUTION-AUDIT.md` |
| A-3 | Read Agent C distribution audit | done | `docs/DISTRIBUTION-AGENT-AUDIT.md` |
| A-4 | Read Agent D bridge verification | done | `docs/BRIDGE-INTEGRATION-VERIFICATION.md` (24/24) |
| A-5 | Read download page / installer evidence (G1–G6-era docs) | done | `DISTRIBUTION-QA.md` §2.1/§2.5, `DISTRIBUTION-SMART-DOWNLOAD.md`, `DISTRIBUTION-INSTALLATION.md` |
| A-6 | Read Agent E/G packaging docs | done | `UI-DESKTOP-PACKAGING.md`, `ELECTRON-INTEGRATION-QA.md`, `UNIFIED-DESKTOP-INTEGRATION.md` |
| B-1 | EXE hash + size measurement (2 runs) | **pass** | `Keel.exe` 235,419,136 B, SHA `D52DB523…288B20`; installer 158,152,373 B, SHA `170F1361…1667BC` |
| B-2 | Verify installer-hash discrepancy (older docs) | **open (noted)** | `ELECTRON-INTEGRATION-QA.md` §0 cites `B25C0977…`; worktree file measures `170F1361…` — recorded both, doc is `pending` a correction |
| C-1 | G4/G6 packaged-EXE verification status | **recorded** | `UI-ARCHITECTURE.md` §7.8; `ELECTRON-INTEGRATION-QA.md` §3.3/§3.4 — G4 pass (15:14:55Z cutover build), G6 pass (15:24:38Z legacy) |
| C-2 | Cutover state (unified default active) | **recorded** | `renderer-policy.js:46` + `ELECTRON-INTEGRATION-QA.md` §3.7 (default launch, 15:24–15:26Z) |
| C-3 | Download-page device detection evidence | **recorded** | `DISTRIBUTION-QA.md` §2.1, `01-download-journey.spec.ts` (42/42) |
| D-1 | Installer publishing / public URLs (artifacts, SHA-256, URLs) | **recorded** | `DISTRIBUTION-SMART-DOWNLOAD.md` §3–§5, `DISTRIBUTION-INSTALLATION.md` §2, `keel/src/keel/release/{build,publish}.py`, `DISTRIBUTION-QA.md` §2.5 |
| D-2 | Kanban drag fix result | **recorded** | `UI-DEFECT-LOG.md` QA-F-010 "fixed & re-verified" |
| E-1 | Write `RELEASE-2026-11-25.md` | **done** | new file (EXE name/size/SHA-256, public URL, what's new, rollback, blockers) |
| E-2 | Write `AGENT-E-PROGRESS-LEDGER.md` | **done** | this file |
| E-3 | Edit `UI-ARCHITECTURE.md` — download page, installer publishing, packaged EXE G4/G6, cutover state | done | appended §8 (verify) |
| E-4 | Edit `UI-TEST-MATRIX.md` — download QA rows, Kanban drag, packaged EXE launch/rollback rows | done | new section (verify) |
| E-5 | Edit `UI-FEATURE-PARITY.md` — preserve 150-criterion history + download page/installer parity | done | appended section (verify) |
| E-6 | No commits, no pushes | **done (observed)** | `git status`/`git log` runs (see §3) |

## 5. Artifacts produced by Agent E

- `keel/docs/RELEASE-2026-11-25.md` (new)
- `keel/docs/AGENT-E-PROGRESS-LEDGER.md` (this file — new)
- Edits: `keel/docs/UI-ARCHITECTURE.md`, `keel/docs/UI-TEST-MATRIX.md`, `keel/docs/UI-FEATURE-PARITY.md`

## 6. Known limits / honesty notes

- **No production publication claimed** (user rule): `DISTRIBUTION-AGENT-AUDIT.md` F-2 — the fresh package build
  after the merge is Agent E's gate; the ledger/release notes mark publication status explicitly.
- Installer-hash discrepancy between docs (`B25C0977…`) and the worktree file (`170F1361…`) is recorded, not resolved.
- Packaged GUI evidence is dominated by Agent G's probes; Agent E did not launch Electron.
