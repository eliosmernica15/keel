# Fleet Next standalone build (Electron renderer)

This folder is owned by the Fleet Next production-build workstream. It documents
the reproducible traced-server build consumed by Electron; no static export is
used because `app/api/bridge/[...path]/route.ts` is a live Node BFF with a raw
`node:http` SSE pipe and server-side token injection.

## Commands

From `keel/fleet-next` (packaging default — `KEEL_DIST_DIR` **unset**):

```powershell
Remove-Item Env:KEEL_DIST_DIR -ErrorAction SilentlyContinue
npm ci
npm run build:standalone     # writes .next/standalone, .next/static overlay
npm run verify:standalone    # runtime smoke test of the same artifact
```

`KEEL_DIST_DIR` is only a parallelism feature: it lets several agents build
simultaneously into isolated trees (for example `.next-agent-b-standalone`).
It must **not** be set for the final packaging build, because electron-builder
reads the plain `.next` tree. With it unset the inventory records
`distDir: ".next"` and `standaloneRoot: ".next/standalone"`.

`build:standalone` runs `next build` directly (no `next start`), then:

1. copies `<distDir>/static` to `<distDir>/standalone/<distDir>/static`;
2. copies `public/` to `<distDir>/standalone/public/`;
3. hardens the generated `server.js` by replacing Next's
   `const hostname = process.env.HOSTNAME || '0.0.0.0'` with a literal
   `const hostname = '127.0.0.1'`;
4. asserts every required asset, route, manifest, CSP header and runtime-env
   reference; and
5. writes `docs/standalone-asset-inventory.json` and
   `docs/standalone-build.log`.

Important: plain `npm run build` regenerates `.next/standalone/server.js` from
Next's template, removing both the overlay copies and the loopback patch. Always
run `npm run build:standalone` last, and never run a plain build afterwards.

`verify:standalone` starts a throwaway loopback bridge with a dummy token,
launches the built server with `HOSTNAME=0.0.0.0` (to prove the patch ignores
it), checks 21 behaviours, then relaunches the same artifact without credentials
to prove env is read at runtime. It also probes a non-loopback interface.

## Output layout (contract paths)

With `KEEL_DIST_DIR` unset, the build produces:

| Source after `build:standalone` | Packaged destination | Purpose |
|---|---|---|
| `fleet-next/.next/standalone/**` | `<resources>/fleet-next/**` | `server.js`, traced `node_modules`, `.next/server` |
| `fleet-next/.next/static/**` | `<resources>/fleet-next/.next/static/**` | client JS/CSS chunks (pre-overlaid into standalone by the script) |
| `fleet-next/public/**` | `<resources>/fleet-next/public/**` | `sw.js`, manifest icons, fonts (pre-overlaid into standalone by the script) |

The three electron-builder `extraResources` entries therefore match what the
packaged app sees: `fleet-next/server.js`, `fleet-next/.next/static`,
`fleet-next/public`. The script's pre-overlay means copying only
`.next/standalone` to `fleet-next` would also be sufficient; the three-entry
mapping is idempotent. Do **not** ship `.env.local` or `tests/`.

## Runtime environment (Electron)

The standalone server reads these from its own process environment at runtime;
they are never inlined into the client or the compiled route:

- `KEEL_BRIDGE_URL` — bridge base URL without `?t=`;
- `KEEL_BRIDGE_TOKEN` — bare token injected server-side as `x-keel-token`;
- `PORT` — OS-chosen loopback port (reserve-then-release; never `PORT=0`);
- `HOSTNAME` — ignored by the hardened artifact (always `127.0.0.1`).

`npm run start:standalone` is the Node development launcher and forces
`HOSTNAME=127.0.0.1`. In a packaged Electron app, spawn
`join(nextDir, "server.js")` with `process.execPath` and
`ELECTRON_RUN_AS_NODE=1` in the **child** env instead of using this launcher;
there is no system Node in a packaged app. Attach `error` and `exit` listeners,
and use HTTP polling of `GET /` (status 200) for readiness.

The BFF reads bridge env once at module load: a bridge token rotation makes the
running renderer stale. Electron must restart the Next child on rotation rather
than retrying with a guessed token.

## Packaging requirements to verify in G4

- Electron 42's Node version must run Next 15.5.29 / React 19 (probe with
  `ELECTRON_RUN_AS_NODE=1 -e "console.log(process.version)"`).
- `next/image` is not used in app code; `sharp` native binaries are therefore
  not expected to be needed. The inventory must still be checked on the target
  OS/arch.
- `npmRebuild: false` means nothing is rebuilt by electron-builder; the traced
  `node_modules` subset is shipped as-is.
- No `NEXT_PUBLIC_KEEL_BRIDGE_*` variable may ever be defined.

## Evidence (authoritative packaging run)

Commands (with `KEEL_DIST_DIR` unset):

```powershell
npm run build:standalone    # exit 0, all 30 build checks passed
npm run verify:standalone   # exit 0, 21/21 runtime checks passed
```

Generated evidence:

- `fleet-next/.next/standalone/server.js` (6,550 bytes) contains the literal
  `const hostname = '127.0.0.1'` and no `0.0.0.0`.
- `fleet-next/.next/standalone/public/sw.js`, `.next/standalone/public/icons…`,
  `.next/standalone/public/fonts/…` and
  `.next/standalone/.next/static/chunks/…` all exist (the script pre-overlays them).
- `docs/standalone-build.log` — full build stdout/stderr.
- `docs/standalone-asset-inventory.json` — per-file path, category, byte size and
  SHA-256; `distDir: ".next"`, `standaloneRoot: ".next/standalone"`,
  build ID `vjVZt4qP08iFXxAxJgQVw`, Next `15.5.29`.

Exact inventory totals (files under `.next/standalone`, including the
pre-overlaid static/public assets):

| Category | Files | Bytes |
|---|---:|---:|
| serverEntry (`server.js`) | 1 | 6,550 |
| serverBuild (manifests, BUILD_ID, `.next/server` data) | 45 | 1,075,891 |
| routeHandlers (compiled BFF + manifest routes) | 6 | 78,755 |
| staticAssets (client chunks/CSS) | 22 | 1,483,712 |
| publicAssets (sw, icons, fonts) | 7 | 122,434 |
| tracedNodeModules | 1,907 | 59,412,355 |
| other (`package.json`) | 1 | 1,209 |
| **Total** | **1,989** | **62,180,906** (59.30 MiB) |

The three electron-builder source paths are:

- `fleet-next/.next/standalone` — 1,989 files, 62,180,906 bytes (self-contained);
- `fleet-next/.next/static` — 22 files, 1,483,712 bytes (idempotent overlay);
- `fleet-next/public` — 7 files, 122,434 bytes (idempotent overlay).

Runtime verification covered: HTTP 200 hydration shell, production CSP without
`unsafe-eval`, nosniff/no-referrer, no `X-Powered-By`, PWA manifest + icons,
service worker and its `/api/` bypass, all icons/fonts, live BFF proxy with
runtime dummy token injection, SSE path, loopback-only bind (including a
negative LAN probe), and a no-credentials relaunch returning 502
`bridge_unavailable` from the same artifact.
