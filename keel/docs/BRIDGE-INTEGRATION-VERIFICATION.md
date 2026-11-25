# Bridge Integration Verification (unified frontend ↔ real Python bridge)

**Status:** verified against a live local bridge, not just source. **24/24 tests passed.**
Evidence: `fleet-next/tests/bridge-integration/**`. No backend, frontend, Electron,
config or other docs were changed by this workstream.

This document upgrades `UI-BACKEND-CONTRACT.md` from "verified against source" to
"verified against a real bridge round-trip" for the endpoints listed below. Where
the live runtime disagrees with the written contract, the runtime wins and the
difference is recorded in §6.

---

## 1. Reproduction

From `<worktree>/keel/fleet-next`:

```powershell
npx playwright test --config tests/bridge-integration/playwright.config.ts
```

Final run (2026-11-25): **`24 passed (2.0m)`**, exit code 0.
Earlier runs during development were `21 passed / 2 failed` (two test-side
expectations corrected, no backend change) and `23 passed`, then the final
`24 passed`. Commands are quoted exactly as executed in §2.

The harness starts five processes (all loopback, all disposable):

| Process | Port | Source | Purpose |
|---|---|---|---|
| Real Python fleet bridge | 8797 | `tests/bridge-integration/bridge_server.py` → **this worktree's** `keel/src` (`sys.path.insert` at `bridge_server.py:17-18`) | genuine round-trips, throwaway token `bridge-int-throwaway-4f8c2a91`, fresh `KEEL_STATE_DIR` in `%TEMP%` |
| FIXTURE mock upstream | 8798 | `mock_bridge.py` | header echo + canned statuses only |
| Real Next.js BFF | 3311 | `app/api/bridge/[...path]/route.ts`, `KEEL_BRIDGE_URL=http://127.0.0.1:8797` | real same-origin proxy |
| FIXTURE Next BFF → mock | 3312 | same route, upstream = 8798 | header/error inspection only |
| FIXTURE unconfigured Next BFF | 3313 | same route, empty bridge env | `bridge_unavailable` path only |

`bridge_server.py` imports the unmodified `keel.webapp` handler and adds only a
token-free `/__bridge_ready` probe for Playwright readiness; it does **not** add,
remove or alter any API route. Tests titled `FIXTURE` or `FIXTURE-SEEDED` are the
only ones that use a fixture; all others are genuine BFF → real bridge HTTP
requests.

---

## 2. Exact commands and results

```text
$ cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel\fleet-next
$ npx playwright test --config tests/bridge-integration/playwright.config.ts
  ... (servers ready)
  Running 24 tests using 1 worker
  24 passed (2.0m)
```

A benign `ConnectionAbortedError: [WinError 10053]` is printed by the Python
bridge's `http.server` when a test intentionally aborts an SSE stream. It is a
disconnected client, not a failed request, and never affected a test result.

---

## 3. Endpoint coverage (live bridge unless marked FIXTURE)

Backend evidence points at `src/keel/fleet/routes.py`; frontend evidence at
`fleet-next/lib/api.ts`. Test locations are `fleet-next/tests/bridge-integration/<file>:<line>`.

### 3.1 BFF / security (`01-bff-security.spec.ts`)

| Check | Evidence | Test |
|---|---|---|
| Token injected server-side (`x-keel-token`) | `route.ts:34`, `route.ts:60` | `:14` REAL, `:42` FIXTURE |
| Browser Origin/Referer stripped (a forwarded Origin would 403 upstream) | `route.ts:32-33`; `webapp.py:493-499` | `:26` REAL |
| Cookie stripped | `route.ts:27`; `webapp.py:504-509` | `:42` FIXTURE |
| Direct bridge without token refused | `webapp.py:501-519`; `routes.py:113-116` | `:14` REAL |
| Path traversal rejected before upstream | `route.ts:16-21`, `:143-146` | `:80` REAL |
| `bridge_unavailable` when BFF unconfigured | `route.ts:12-14`, `:137-142` | `:62` FIXTURE |
| Upstream 502/400/text forwarded honestly | `route.ts:123-132`; `client.ts:52-67` | `:70` FIXTURE |
| Token absent from HTML, JS, source maps, localStorage, BFF response | `webapp.py:80`, `route.ts:9-10` (no `NEXT_PUBLIC_*`) | `:94` REAL |

### 3.2 Agents / Cowork (`02-agents-cowork.spec.ts`)

| Endpoint | Backend | Frontend | Test |
|---|---|---|---|
| `GET bots`, `POST bots` | `routes.py:136`, `:734` | `api.ts:60`, `:62` | `:16` REAL |
| `GET bots/:id/rows` (after/limit) | `routes.py:315-325` | `api.ts:61` | `:16` REAL |
| `GET bots/:id/latest_seq` | `routes.py:326` | *(cursor helper)* | `:16` REAL |
| `POST bots/:id/messages` | `routes.py:1439-1483` | `api.ts:66` | `:16` REAL |
| `POST bots/:id/{update,fork,rewind,restore,cancel,delete}` | `routes.py:1485-1506`, `:1367-1415` | `api.ts:63-74` | `:16` REAL |
| `GET bots/:id/export.md` | `routes.py:344-357` | `api.ts:164` | `:16` REAL |
| `GET bots/:id/policies|audit`, `POST policies/revoke` | `routes.py:330-343`, `:1508-1531` | `api.ts:75-78` | `:65` REAL |
| `POST bots/:id/approvals/:id/decide` (once/never/invalid/missing) | `routes.py:1533-1565` | `api.ts:69-70` | `:80` **FIXTURE-SEEDED** (pending card written to the real bridge DB by `seed_approval.py`; the decision itself is a real HTTP round-trip) |
| `POST bots/:id/asks/:id/answer` | `routes.py:1417-1437` | `api.ts:71-72` | `:106` REAL (400/404 envelopes; success needs a live provider turn) |
| `GET groups`, `POST groups`, `GET groups/:id[/rows]`, `POST .../messages`, `POST .../delete` | `routes.py:153`, `:760`, `:281-301`, `:1310-1355` | `api.ts:80-87` | `:117` REAL |
| `GET events` (SSE, raw `node:http`) | `routes.py:1748-1776`, named frame at `:1769` | `api.ts:169-185`, `route.ts:44-95` | `:145` REAL (browser `EventSource`, named `"row"` listener only) and `:171` REAL (wire-level `event: row`) |

### 3.3 Code / projects (`03-code-projects.spec.ts`)

| Endpoint | Backend | Frontend | Test |
|---|---|---|---|
| `GET/POST projects` | `routes.py:360`, `:988` | `api.ts:98-99` | `:20` REAL |
| `GET projects/:id/tree` (trust gate) | `routes.py:372-379`; `service.py:409-412` | `api.ts:104` | `:20` REAL |
| `GET projects/:id/file/read` (+ escape refusal) | `routes.py:415-432`; `service.py:442-468` | `api.ts:105` | `:20` REAL |
| `POST projects/:id/file/write` | `routes.py:966-983` | `api.ts:106-107` | `:20` REAL |
| `POST projects/:id/{trust,open,model,chat,remove}` | `routes.py:879-887`, `:938-965`, `:953-956` | `api.ts:100-103` | `:20` REAL |
| `GET projects/:id/review` (read-only git text, trust gate) | `routes.py:380-414` | `api.ts:108` | `:74` REAL |
| `POST projects/:id/terminal/exec` → handle | `routes.py:891-931` | `api.ts:109-110` | `:89`, `:118` REAL |
| `GET shells/:id/output`, `GET shells`, `POST shells/:id/kill`, `GET shells/clear/finished` | `routes.py:528-551`, `:792-796` | `api.ts:114-119` | `:89` REAL |

### 3.4 Fleet / capabilities / settings (`04-fleet-capabilities.spec.ts`)

| Endpoint family | Backend | Frontend | Test |
|---|---|---|---|
| Tasks: `GET/POST tasks`, `GET tasks/:id`, `GET .../events`, `POST .../{update,assign,undo,cancel,delete}`, `POST tasks/reorder` | `routes.py:158-172`, `:1009-1135`, `:1043` | `api.ts:121-127`, `:135` | `:13` REAL |
| Routines: `GET/POST routines`, `GET .../runs`, `POST .../{update,enable,disable,pause,resume,run,delete}` | `routes.py:175-199`, `:1138-1229` | `api.ts:128-134` | `:50` REAL (run conflict 409 for disabled/paused) |
| Library: `GET/POST library`, `GET library/:id[/download|/preview]`, `POST .../delete` | `routes.py:201-279`, `:1231-1308` | `api.ts:136-138`, `:165-166` | `:87` REAL |
| Providers: `GET providers`, `POST providers/{catalog,credential,credential/clear,save,remove}` | `routes.py:144-151`, `:573-732` | `api.ts:89-95` | `:118` REAL (offline catalog + validation/error envelopes; never a real key) |
| Skills: `GET skills`, `GET skills/manage`, `POST skills/{install,remove,enable}` | `routes.py:436-468`, `:1567-1627` | `api.ts:140-145` | `:155` REAL |
| MCP: `GET mcp/servers`, `POST mcp/health` | `routes.py:505-516`, `:1696-1715` | `api.ts:150-151` | `:155` REAL |
| Connectors: `GET connectors`, `POST connectors/{add,test,remove}` | `routes.py:518-521`, `:799-876` | `api.ts:152-155` | `:155` REAL |
| Commands/workflows: list + execute | `routes.py:470-503`, `:1629-1694` | `api.ts:146-149` | `:155` REAL |
| `GET usage`, `GET/POST keep-awake` (`{"on":…}`) | `routes.py:364-366`, `:523-526`, `:780-790` | `api.ts:157-162` | `:155` REAL |

Every method in `lib/api.ts:58-167` has a live-bridge route. No orphan frontend
call was found.

---

## 4. Security findings (all passed)

- **Token injection is server-side only.** With no browser-supplied credential,
  `GET /api/bridge/bots` succeeds while a direct `GET /api/fleet/bots` to the
  bridge returns 403 `{"refused": "token required or mismatch"}` (`test :14`).
  A fixture upstream that echoes headers observed exactly `x-keel-token:
  bridge-int-throwaway-4f8c2a91` and no `cookie`, `origin` or `referer`
  (`test :42`). The upstream HTTP client legitimately re-adds `host` for its own
  target; the browser's host/port is not forwarded.
- **Token never reaches the browser.** The app HTML, all fetched JS/CSS/source
  maps, `localStorage`, and BFF response bodies/headers were scanned for the
  exact token string with zero hits (`test :94`). `route.ts:9-10` reads the secret
  only in the Node runtime, and Next only exposes `NEXT_PUBLIC_*` to the client.
- **Origin/Referer stripping is functional, not just declarative:** a POST with
  `Origin: http://evil.example` succeeds through the BFF (`test :26`); forwarding
  it would make `webapp.py:493-499` refuse the request.
- **Path traversal** using a literal `..` segment returns 400 `{"error":"bad_path"}`
  (`test :80`).
- **Error truthfulness:** unconfigured BFF → 502 `bridge_unavailable` (`:62`);
  upstream 502/400 bodies pass through with their status (`:70`); unknown bot →
  404 `bot_not_found` (`:88`). `errMessage()`/`isBridgeUnavailable()`
  (`api.ts:31-56`) therefore receive stable codes.

---

## 5. Fixture policy

Fixtures were used **only** for deterministic or error cases, and every such
test is labelled:

- `FIXTURE:` in `01-bff-security.spec.ts:42,62,70` — mock upstream / unconfigured
  BFF for header inspection and fixed statuses.
- `FIXTURE-SEEDED` in `02-agents-cowork.spec.ts:80` — one pending approval row
  written into the real bridge's SQLite DB so the HTTP `decide` contract can be
  exercised without a live provider turn. The decision, policy update, audit
  and response all come from the real bridge.
- All other 20 tests are genuine BFF → real Python bridge round-trips.

---

## 6. Contract discrepancies and missing APIs (file:line evidence)

1. **`mcp/health` response shape is wrong in the contract doc.**
   `UI-BACKEND-CONTRACT.md:52` documents `{health:[...]}`. The authoritative
   runtime returns a **name → bool map**: `mcp.py:385`
   (`def health_all(self) -> dict[str, bool]`) forwarded verbatim at
   `routes.py:1710`. Verified live in test `:155`; the test asserts the real
   object shape. No frontend bug: `api.ts:151` is untyped and merely returns it.
   **Action:** update the doc's envelope row; no backend change needed.

2. **No general settings endpoint on the BFF path.** The BFF prefixes every
   upstream with `/api/fleet/` (`route.ts:101`), but general settings are served
   only at `/api/settings` (`webapp.py:841` GET, `webapp.py:1118` POST), outside
   that prefix. There is no `/api/fleet/settings` route (`routes.py:107-1717`
   contains no settings branch). Provider keys are *not* affected — they use
   `providers/save` (`routes.py:682`). Frontend UI state is deliberately
   `localStorage`-only (`UI-BACKEND-CONTRACT.md:137`). **Impact:** the unified
   UI cannot read/write global settings through this BFF; that is a missing API
   if such a surface is ever required.

3. **No browser-preview route.** No route in `routes.py` serves a project
   preview; every unrecognised project sub-route falls through to
   `{"error":"not_found"}` at `routes.py:433`. Already documented as a known gap
   at `UI-BACKEND-CONTRACT.md:113,148`. Do not build fake browser controls.

4. **No file-level diff / apply / revert.** `projects/:id/review` returns only
   git `status`, `log`, `diff_stat` text (`routes.py:380-414`); any other
   sub-route is `not_found` (`routes.py:433`). Already documented at
   `UI-BACKEND-CONTRACT.md:111,149`.

5. **Group creation constraint is stricter than the contract doc.**
   `create_group()` requires 2–3 distinct agents (`service.py:894-897`), while
   `UI-BACKEND-CONTRACT.md:92` only shows `{name, bot_ids:[...]}`. The first
   test run sent one bot and got 400; the corrected test sends two. **Action:**
   document the 2–3 rule in the contract doc.

6. **Benign noise:** aborting an SSE stream makes the stdlib bridge print
   `ConnectionAbortedError [WinError 10053]` from `socketserver.py`; the bridge
   keeps serving and no test regressed. Informational only.

---

## 7. Honest limitations (not verified here)

- **Live provider turn / real model reply:** no provider credentials in this
  environment (same gate as `UI-BACKEND-CONTRACT.md:147`). Echo-engine turns
  were exercised end-to-end; provider-engine tool use, real approval cards
  raised by a model, and the `ask_user` success path were not. The HTTP routes
  for approval/ask were verified (success `decide` via a seeded card; 400/404
  for `answer`).
- **Electron/Tauri host root assertion:** packaging is a separate workstream
  (`UI-BACKEND-CONTRACT.md:150`). This verification covers the browser/Next BFF
  path only.
- **Credentials:** no real key was saved; `providers/save` was exercised only
  through validation errors, and the documented 4-character `hint`
  (`routes.py:712`) was confirmed by source review, not by persisting a key.

---

## 8. Files added

```text
fleet-next/tests/bridge-integration/playwright.config.ts
fleet-next/tests/bridge-integration/helpers.ts
fleet-next/tests/bridge-integration/bridge_server.py
fleet-next/tests/bridge-integration/mock_bridge.py
fleet-next/tests/bridge-integration/seed_approval.py
fleet-next/tests/bridge-integration/01-bff-security.spec.ts
fleet-next/tests/bridge-integration/02-agents-cowork.spec.ts
fleet-next/tests/bridge-integration/03-code-projects.spec.ts
fleet-next/tests/bridge-integration/04-fleet-capabilities.spec.ts
docs/BRIDGE-INTEGRATION-VERIFICATION.md   (this file)
```
