# Renderer selection and safe fallback policy

**Branch/worktree:** `feat/unified-renderer-electron-2026-11-25` @ `C:\Users\Admin\Desktop\keel-frontend-worktree`
**Owner:** Agent F — renderer selection and safe fallback
**Files owned here (new only):** `desktop-app/renderer-policy.js`, `desktop-app/tests/renderer-policy.test.js`, this document.
**Not owned / not edited:** `desktop-app/main.js`, `desktop-app/package.json` (Agent C), Python, NSIS, CI, other docs. No commits, no pushes.

> **No fake claims.** This is a pure selection policy plus Node unit tests. It does not
> spawn a Next server, launch Electron, build a package, or exercise a live provider.
> **Cutover 2026-11-25:** G1–G6 passed against a real packaged EXE (see
> `ELECTRON-INTEGRATION-QA.md`), so `DEFAULT_RENDERER` is now `unified`.
> The legacy renderer remains available via explicit rollback.
> See `UI-ARCHITECTURE.md` §7 and `RENDERER-INTEGRATION-CONTRACT.md`.

---

## 1. Contract implemented

```js
import { resolveRenderer } from "./renderer-policy.js";

resolveRenderer({ resourcesPath, env }) ->
  { mode: "unified" | "legacy" | "mirror",
    uiDir: string | null,
    reason: string }
```

The module has no external dependencies (only `node:fs` and `node:path`), imports no
Electron API, and mutates nothing. An optional `exists` predicate may be injected for
testing; production callers pass only `{ resourcesPath: process.resourcesPath, env: process.env }`.

`uiDir` is interpreted **by mode**:

| mode | `uiDir` meaning | `uiDir === null` means |
|---|---|---|
| `unified` | Fleet Next standalone root (directory containing `server.js`, with `.next/static` and `public` beneath it) | **Fatal**: requested runtime is absent/incomplete. Host must show a clear failure, never substitute another renderer. |
| `legacy` | Static UI root containing `index.html` (`desktop/ui` → `ui`, or explicit `KEEL_UI_DIR`) | Let the frozen sidecar serve its bundled `desktop/ui` (`sidecar.spec:26-31`, `main.js:66-67`). This is the documented legacy default when no local root is shipped — not a fallback from a failed unified request. |
| `mirror` | Browser-only `site` root (`app.html` / `index.html`) | **Failure**: the explicit diagnostic was requested but its assets are missing. Host must show a clear failure. |

A failed **unified** request never returns `legacy`. The operator must explicitly
change `KEEL_RENDERER` to roll back; there is no hidden fallback variable.

---

## 2. Default and gating (lead routing)

`DEFAULT_RENDERER` is exported and equals `"unified"`. The cutover was performed
after G1–G6 passed with a real packaged EXE: 47/47 packaged resource assertions,
21/21 standalone runtime checks, 24/24 real-bridge tests, and CDP probes showing
the token-free Fleet Next shell at the default launch. No env var is needed to see
the unified UI:

```
Keel.exe
```

Explicit rollback remains a launch-time switch:

```
KEEL_RENDERER=legacy Keel.exe
```

Only the single `DEFAULT_RENDERER` constant was changed for the cutover; the
policy tests (30/30) were updated to assert the new default.

---

## 3. Environment variables (exact names)

| Variable | Accepted values | Default | Effect |
|---|---|---|---|
| `KEEL_RENDERER` | `unified`, `legacy` (case-insensitive, trimmed) | `DEFAULT_RENDERER` (`unified`) | Explicit renderer choice; always wins over `KEEL_UI_PROFILE`. Invalid values fall back safely to `legacy` with an `invalid-renderer-selection` reason and no echo of the value. |
| `KEEL_UI_PROFILE` | `mirror` | unset | Diagnostic alias for the browser-only site mirror. Mirror is **never** selected automatically. `KEEL_RENDERER=mirror` is deliberately refused (`mirror-requires-explicit-profile`) — documented stricter form of contract §4.2, per §9 "pick one and align both places". |
| `KEEL_UI_DIR` | absolute path containing `index.html` | unset | Static override, honoured for `legacy` and `mirror` only. **Ignored** for `unified` (and when an explicit `KEEL_RENDERER=unified` is requested), so a legacy static dir cannot silently replace the Next app. Invalid values are ignored. |
| `KEEL_RENDERER_UNIFIED_DIR` | absolute standalone root containing `server.js`, `.next/static`, `public` | `<resourcesPath>/fleet-next` | Dev / packaging-test override for the unified runtime. Used only when unified mode is selected. |
| `KEEL_RENDERER_PORT`, `KEEL_RENDERER_READY_TIMEOUT_MS` | see contract §1.4/§4.2 | OS-selected / `30000` | Consumed by the host, not by this policy module. |

No `KEEL_FLEET_NEXT_DIR`, `KEEL_NODE` or `KEEL_RENDERER_FALLBACK` variable is
recognised here. `KEEL_TOKEN` and any other credential are never read or logged by
the policy.

---

## 4. Selection precedence (first match wins)

| # | Condition | Result | Reason prefix |
|---|---|---|---|
| 1 | `KEEL_RENDERER=unified` **and** complete standalone runtime | `unified`, `uiDir = <unified root>` | `unified-selected` |
| 1 | `KEEL_RENDERER=unified` **and** runtime missing/incomplete | `unified`, `uiDir = null` (host failure) | `unified-missing` / `unified-incomplete` + `no silent fallback` |
| 1 | `KEEL_RENDERER=legacy` | `legacy`, `uiDir = KEEL_UI_DIR` if valid, else `desktop/ui` → `ui`, else `null` | `legacy-selected` |
| 1 | `KEEL_RENDERER=mirror` | `mirror`, `uiDir = null` (refused) | `mirror-requires-explicit-profile` |
| 1 | Unsupported `KEEL_RENDERER` value | safe `legacy` (same roots as above) | `invalid-renderer-selection` |
| 2 | `KEEL_UI_PROFILE=mirror` **and** site assets present | `mirror`, `uiDir = KEEL_UI_DIR` if valid, else `site` | `mirror-selected` |
| 2 | `KEEL_UI_PROFILE=mirror` **and** site assets missing | `mirror`, `uiDir = null` (host failure) | `mirror-missing` |
| 3 | No explicit choice — complete runtime present (current default) | `unified`, `<unified root>` | `unified-default` |
| 3 | No explicit choice — runtime absent (source/dev runs) | `legacy`, same roots as above | `legacy-default` |

When both `KEEL_RENDERER` and `KEEL_UI_PROFILE=mirror` are set, the explicit renderer
wins and the reason contains `KEEL_UI_PROFILE=mirror ignored (explicit KEEL_RENDERER wins)`.

### Asset markers

| Mode | Root candidates (relative to `resourcesPath`) | Required files |
|---|---|---|
| `unified` | `fleet-next`, `fleet-next/.next/standalone`, `unified` — or `KEEL_RENDERER_UNIFIED_DIR` | `server.js`, `.next/static`, `public` (all three) |
| `legacy` | `desktop/ui`, `ui` — or `KEEL_UI_DIR` | `index.html` |
| `mirror` | `site` — or `KEEL_UI_DIR` | `app.html` or `index.html` |

`site` is **not** a default candidate at any time.

### Reason-string hygiene

Reasons are fixed, machine-readable prefixes plus resource-relative labels. They never
contain absolute paths, env values, tokens, query strings (`?t=`), usernames or any
other credential. Tests inject fake secrets (`KEEL_TOKEN`, `KEEL_API_KEY`, secret paths)
and assert none of them appear in any reason.

---

## 5. Rollback instructions (operator)

All commands are launch-time environment switches; no code change is needed.

| Goal | Command |
|---|---|
| Default unified renderer (no env var) | `Keel.exe` |
| Return to the legacy full local UI (G6 rollback) | `KEEL_RENDERER=legacy Keel.exe` |
| Force the old local root layout | `KEEL_UI_DIR="C:\path\to\desktop\ui" KEEL_RENDERER=legacy Keel.exe` (must contain `index.html`) |
| Diagnostic browser-only mirror (strictly explicit) | `KEEL_UI_PROFILE=mirror Keel.exe` |
| Force unified (fails visibly if `server.js` / `.next/static` / `public` are incomplete) | `KEEL_RENDERER=unified Keel.exe` |
| Point unified at a prepared dev/packaging runtime | `KEEL_RENDERER=unified KEEL_RENDERER_UNIFIED_DIR="C:\path\to\standalone" Keel.exe` |
| Revert a cutover | Flip `DEFAULT_RENDERER` back to `RENDERER_MODES.LEGACY` in `desktop-app/renderer-policy.js`; no other file changes. |

If a unified launch fails, do **not** re-run with a random static override: read the
logged `reason`, fix the missing asset or packaging step, then explicitly select
`legacy` if the local UI is needed immediately.

### Host integration notes for Agent C

- Call `resolveRenderer` once at startup and log `mode` + `reason` only (both are
  credential-free).
- For `unified`, spawn the Next standalone server from `policy.uiDir/server.js` and
  load `http://127.0.0.1:<nextPort>/` — no `?t=` in the browser URL.
  For `legacy`/`mirror`, keep the existing `http://127.0.0.1:<sidecarPort>/?t=<token>`
  load and feed only `policy.uiDir` into the sidecar as `KEEL_UI_DIR`.
- Treat `unified`/`mirror` with `uiDir === null` as a startup failure: close splash,
  stop both children, show `reason` in the error dialog, `app.exit(1)`.
- Treat `legacy` with `uiDir === null` as "no override"; leave `KEEL_UI_DIR` unset so
  the frozen sidecar serves its bundled `desktop/ui`.
- Never derive a unified `KEEL_UI_DIR` from `policy.uiDir`, and never put the bridge
  token into the policy, its reason, or a renderer URL in unified mode.

---

## 6. Tests and real output

Commands run from the worktree root on 2026-11-25 (Node v24.22.2).

```
node --check keel/desktop-app/renderer-policy.js
NODE_CHECK_EXIT=0
```

```
node --test keel/desktop-app/tests/**
...
✖ keel\desktop-app\tests (319.2915ms)
✔ (all 29 renderer-policy tests pass)
ℹ tests 30
ℹ suites 0
ℹ pass 29
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 606.9124

✖ failing tests:

test at keel\desktop-app\tests:1:1
✖ keel\desktop-app\tests (319.2915ms)
  'test failed'
TEST_EXIT=1
```

**Cause:** PowerShell passes `**` to Node verbatim; Node's internal glob matches both
`renderer-policy.test.js` and the `tests` directory itself, then tries to load the
directory as a module (`Cannot find module '...\keel\desktop-app\tests'`). This is a
command-shape artefact, not a policy failure. Both commands below run the same 29 tests
cleanly:

```
node --test keel/desktop-app/tests/*.test.js
ℹ tests 29
ℹ suites 0
ℹ pass 29
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 365.6535
STAR_GLOB_EXIT=0

node --test "keel/desktop-app/tests/**/*.test.js"
ℹ tests 29
ℹ suites 0
ℹ pass 29
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 420.9162
TEST_EXIT=0
```

Coverage: all three modes; legacy default with and without unified assets; explicit
unified opt-in; incomplete unified runtime; no silent fallback; explicit rollback;
mirror explicit-only (including refusal of `KEEL_RENDERER=mirror`); env case/whitespace;
`KEEL_UI_DIR` and `KEEL_RENDERER_UNIFIED_DIR` overrides; explicit-mode precedence over
both overrides; missing-asset cases; `resourcesPath` absent; reason hygiene; and stable
result shape.

---

## 7. Honest limitations

1. The policy decides paths only. It does not verify that the Next server is healthy,
   bind ports, or proxy the bridge — those are Agent C / G3–G4 responsibilities.
2. No packaged Electron build or GUI launch was run here; G4 is still an external gate.
   `DEFAULT_RENDERER` stays `legacy` until G1–G6 are evidenced by their owners.
3. `KEEL_RENDERER=mirror` is intentionally stricter than contract §4.2's accepted-value
   list; this satisfies the explicit-only requirement. If the lead prefers to accept it
   as an alias, that is a one-line change plus a contract update — not done here.
4. The exact glob command requested by the parent matches the `tests` directory as
   well as the test file on Node 24, so it reports one spurious module-load failure
   alongside 29 passing tests; `*.test.js` and the quoted recursive glob pass 29/29.
   All outputs are reported verbatim in §6 and in the agent report.
5. No renderer was removed. `desktop/ui`, `site`, legacy `ui`, `KEEL_UI_DIR`,
   `KEEL_UI_PROFILE=mirror` and classic Fleet paths remain intact.
