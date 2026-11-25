# Agent G — packaged Electron QA harness

Independent QA of the **actual** Electron → Python sidecar → Fleet Next
integration. This folder is the only owned test area for this agent; it does
not modify app/source/config/Electron/Python/CI files.

All commands assume CWD `keel/fleet-next` unless noted.

## Evidence categories used in the report

| Tag | Meaning |
|---|---|
| `[S]` | Source assertion (static read of source/config). |
| `[ED]` | Real Electron **development** launch (CDP-attached). |
| `[PE]` | Real **packaged EXE** launch (CDP-attached). |
| `[B]` | Browser-only test. |
| `[X]` | Blocked / not run — never promoted to a pass. |

## Files

- `01-source-contract.spec.ts` — Playwright suite of static contracts. Baseline
  invariants always run; the unified contracts are skipped with an explicit
  reason if the integration is absent.
- `electron-probe.mjs` — launches `electron .` (dev) or `dist/win-unpacked/Keel.exe`
  with `--remote-debugging-port`, attaches over CDP, records window URL/title/
  text/localStorage/sessionStorage, child processes, netstat listeners, token
  leak scan, optional UI walk, then closes and verifies child shutdown.
- `lifecycle-probe.mjs` — branded failure screen and single-instance checks.
- `prepare-unified-runtime.mjs` — assembles a complete standalone runtime from
  build **output** into `tmp/unified-runtime` for `KEEL_RENDERER_UNIFIED_DIR`.
- `qa-logs/` — timestamped JSON + text evidence.
- `evidence/` — timestamped screenshots.

## Commands

```powershell
cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel\fleet-next

# 1. Static contracts
npx playwright test --config tests/packaged-qa/playwright.config.ts

# 2. Prepare a complete dev standalone runtime (build output only)
node tests/packaged-qa/prepare-unified-runtime.mjs

# 3. Unified Electron dev launch (token-free URL, real bridge, real BFF)
node tests/packaged-qa/electron-probe.mjs dev `
  KEEL_RENDERER=unified `
  KEEL_RENDERER_UNIFIED_DIR="C:\Users\Admin\Desktop\keel-frontend-worktree\keel\fleet-next\tests\packaged-qa\tmp\unified-runtime" `
  KEEL_RENDERER_READY_TIMEOUT_MS=45000 KEEL_QA_UI_CHECK=1

# 4. Legacy fallback / baseline render path
node tests/packaged-qa/electron-probe.mjs dev KEEL_RENDERER=legacy

# 5. Packaged EXE (only meaningful AFTER a rebuild containing fleet-next)
node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=unified KEEL_QA_UI_CHECK=1

# 6. Failure screen + single instance
node tests/packaged-qa/lifecycle-probe.mjs failure
node tests/packaged-qa/lifecycle-probe.mjs single

# 7. Renderer policy unit cases (owned by another agent; read-only here)
cd .. ; node --test desktop-app/tests/renderer-policy.test.js
```

The probe kills the Electron process tree (`taskkill /PID … /T /F`) in `finally`,
then re-queries child processes so orphaned sidecars/servers are detected.

A packaged EXE is only "unified" when
`dist/win-unpacked/resources/fleet-next/server.js` exists and
`dist/win-unpacked/Keel.exe` has a mtime later than the packaging-config edit.
The harness never infers this from source alone.
