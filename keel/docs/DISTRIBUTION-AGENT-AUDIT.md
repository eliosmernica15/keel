# Agent C — production distribution round: agent execution / desktop runtime audit

**Date:** 2026-11-25
**Worktree:** `C:\Users\Admin\Desktop\keel-frontend-worktree`, branch `feat/frontend-completion-2026-11-24`
**HEAD at audit start:** `f70a368` (docs baseline); merge under test `c80c2e1` (reconcile `origin/main`, 2026-11-25 01:59:56 +0100)
**Ownership respected:** read-only source audit; only the three new `keel/tests/verify_distribution_agent_*.py` files and this document were created. No source files, generated registry files, other agents' files, git state, commits or pushes.

---

## 1. Question and verdict

**Question:** did the installer/distribution work replace the packaged desktop execution path with a fake or simulated agent runtime, and did the `origin/main` merge break session continuity, event delivery, approvals/permissions or workspace trust?

**Verdict:** **No fake execution was introduced, and no execution-path regression was found.** The packaged Electron shell still spawns the real Python bridge (bundled PyInstaller sidecar in production; `python -m keel serve` in dev), loads the full local `desktop/ui`, and the renderer takes the live `/api/run` branch whenever it is served over `http://127.0.0.1` with a token. The demo/fixture branch is reachable only from a standalone `file:` page and labels itself explicitly. A real local Echo turn was driven through the live HTTP bridge with rows, SSE frames, cancel signalling and SQLite restart continuity all verified.

Two honest caveats are recorded in §6: (a) with no provider credential, the *Python runtime itself* falls back to a labelled scripted fake model — the process and gates are real, the model reply is not; (b) the packaged EXE present in `dist/` was built ~3.5 h before the merge, so a fresh package build remains Agent E's gate.

---

## 2. Real local runtime execution vs fixture-based tests

| Class | What actually ran | Evidence |
|---|---|---|
| **Real packaged binary** | `dist/keel-sidecar/keel.exe serve --port 8899`, spawned as a child, health-polled, HTTP `GET /`, `/ui/app.js`, `/api/fleet/bots`, killed with `taskkill /T /F` | §4.2 — `ready=True`, full-UI markers present, mirror badge absent, unauthenticated API `403` |
| **Real local bridge + real Echo turn** | `keel.webapp.make_server(0)` on 127.0.0.1, real HTTP POST/GET, real `FleetStore`/SQLite on `tmp_path`, real worker thread running `fleet.echo.start_turn`, real SSE socket | §4.1 — `3 passed` for the fixed run; assertions on row kinds, engine tag, SSE frames, cancel, restart |
| **Real local Python subprocess** | `POST /api/run` → `python -m keel -p … --output-format stream-json` child; parsed init/result/done NDJSON | §4.1 — `apiKeySource: "none"`, `model: "keel-fake-1"`, `exit_code: 0` |
| **Package assertions (no Electron GUI)** | `node desktop-app/scripts/test-ui-root.js` and `node …/assert-ui-entrypoints.js --resources …` — source-extracted and on-disk layout checks | §4.3 — 8/8 and 31/31 PASS, including `app.asar main.js` hash match |
| **Fixture-based / deterministic** | `evaluate()` permission decisions, `ApprovalBroker` cards, `FleetStore` objects on tmp SQLite, source-text assertions | §4.1 — these use real objects but no network/process; explicitly labelled in the test docstrings |

No live provider key, external network call, real user workspace or user credential was used in any check.

---

## 3. Static trace of the packaged execution path

### 3.1 Renderer selection — full local UI wins

| Contract | Evidence |
|---|---|
| `uiRoot()` candidates are `resources/desktop/ui` then `resources/ui`; `resources/site` exists only inside the `KEEL_UI_PROFILE=mirror` branch | `keel/desktop-app/main.js:61-82` (mirror gate `72-75`, local candidates `76-80`, deliberate `null` return `81`) |
| Explicit `KEEL_UI_DIR` override is honoured only when `<dir>/index.html` exists | `main.js:68-71` |
| Packaged sidecar gets `KEEL_UI_DIR = uiRoot() \|\| undefined`; `undefined` means the frozen sidecar serves its bundled `desktop/ui` | `main.js:143-149`; `keel/desktop-app/sidecar.spec:29` |
| Dev path uses real system Python + repo `desktop/ui` | `main.js:155-164` (`PYTHONPATH=<repo>/src`, `python -m keel serve --port …`) |
| electron-builder ships `../desktop/ui → resources/desktop/ui` (and `../site → resources/site` as rollback) | `keel/desktop-app/package.json:32-53` |
| Bridge resolves UI from `KEEL_UI_DIR` or `<bundle>/desktop/ui`, correctly handling `sys._MEIPASS` | `keel/src/keel/webapp.py:62-72` |
| `GET /` serves `UI_DIR/app.html` then `index.html`; `/ui/*` serves only files under `UI_DIR` | `webapp.py:424-461` |
| Demo mode is gated on neither `http:` nor `https:` nor Tauri — it is the `file:` fallback and says "no model and no keel backend are connected" | `keel/desktop/ui/app.js:62-156` (live `75-127`, demo `128-155`) |
| Electron loads the sidecar URL, never a static `file:` root; non-loopback schemes are refused in `setWindowOpenHandler` | `main.js:258`, `main.js:264-278` |

### 3.2 Real Python runtime and bridge token

- `main.js:135-140` generates an 18-byte base64url `KEEL_TOKEN`, passes it to the sidecar env and to the URL.
- `main.js:84-132` parses the printed URL with `new URL`, requires `http:`, `hostname === 127.0.0.1` and a non-empty `?t=`; `webapp.py:1452-1458` prints exactly that line to stderr.
- `webapp.py:79` reads the same token; `webapp.py:324-349` accepts it from `X-Keel-Token`, `?t=`/`&t=` or the `keel_token` cookie, compared with `secrets.compare_digest` on bytes; `webapp.py:316-322` enforces same-origin on mutating requests.
- `webapp.py:411-416` (GET) and `660-668` (POST) call the Fleet dispatcher first, then apply the same token/origin gate to every other API route.
- `webapp.py:1384-1444` (`_stream_run`) spawns `sys.executable -m keel … --output-format stream-json` with `cwd` = chosen workdir, streams real stdout lines as NDJSON and appends a `bridge/done` frame with the real exit code.
- `KEEL_FAKE_SCRIPT` exists **only** as an explicit opt-in at `webapp.py:1023-1025` (quick-ask) and `1400-1402` (run). No installer, workflow, NSI, spec or packaging config sets it; the only other references are in tests. Conftest pins a throwaway `KEEL_TOKEN` (`keel/tests/conftest.py:12-17`).

### 3.3 Agent execution path after the merge

| Step | Path | Evidence |
|---|---|---|
| Message → echo engine | `POST /api/fleet/bots/<id>/messages` appends user row then starts the engine; `engine == "echo"` branch is explicit | `fleet/routes.py:1439-1483` |
| Turn worker | per-bot lock, worker thread, 3×(step running/done), assistant row tagged `engine: echo`, `turn_end` | `fleet/echo.py:18-37`, `61-93`, `96-118` |
| Durable rows + SSE fan-out | `append_row` commits to SQLite and publishes the same event dict; `list_rows(after_seq)` is the history cursor | `fleet/service.py:648-668`, `671-691`, `127-168` |
| SSE wire format | `event: row\ndata: <json>\n\n`, `: ping` keep-alive | `fleet/routes.py:1748-1776` |
| Cancel | `POST …/cancel` → `turn_core.cancel_active_turn`; registered Event is set for provider turns | `fleet/routes.py:1485-1488`; `fleet/turn_core.py:39-77` |
| Restart continuity | Fleet DB is the source of truth; pending approvals/asks are expired on reopen | `fleet/service.py:50-124` |
| Approval gate | Fleet broker creates card + audit, decision transitions `pending → approved/denied`, `never` pins a standing policy | `fleet/approvals.py:135-233`, `fleet/service.py:731-784` |
| Permission gate | mode table now emits a real `deny` for explicit deny rows; non-interactive asks fail closed | `permissions.py:292-316` |
| Workspace trust | `_require_project_trust` before disk I/O, plus route-level 403s | `fleet/service.py:299-307`, `390`, `423`, `451`; `fleet/routes.py:372-379`, `386-390`, `424-430`, `896-903`, `976-983` |

---

## 4. Exact commands and results

### 4.1 New regression tests (real bridge / real runtime where noted)

```
$env:PYTHONPATH='src'; python -m pytest -q tests/verify_distribution_agent_renderer.py tests/verify_distribution_agent_echo.py tests/verify_distribution_agent_execution.py -rxX
3 failed, 6 passed in 216.08s (0:03:36)
```
The three failures were defects in the *new tests* (mirror string ordering assumption, an over-broad config scan that matched a comment and two read-only assertion scripts, and an SSE assertion that read the user row before the assistant row). They were corrected in the test files; no source file was changed:

```
$env:PYTHONPATH='src'; python -m pytest -q <the three corrected tests> -rxX
3 passed in 136.37s (0:02:16)
```

**Final clean run:**

```
$env:PYTHONPATH='src'; python -m pytest -q tests/verify_distribution_agent_renderer.py tests/verify_distribution_agent_echo.py tests/verify_distribution_agent_execution.py -rxX
.........                                                                [100%]
9 passed in 33.64s
```

Files added (all under Agent C ownership):

- `keel/tests/verify_distribution_agent_renderer.py` — 4 tests: source selection of full local renderer; no fake-execution env in shipped config; live bridge serves full local UI (real HTTP); live bridge token/origin auth (real HTTP).
- `keel/tests/verify_distribution_agent_echo.py` — 1 test: real local Echo turn through the bridge, rows + SSE + cancel + restart continuity + second turn after restart (real HTTP+SSE+SQLite).
- `keel/tests/verify_distribution_agent_execution.py` — 4 tests: permission gate deny/ask; approval card redaction + decision/policy audit; workspace trust enforced over HTTP; real `python -m keel` NDJSON smoke with no credentials.

### 4.2 Packaged sidecar — real binary probe

Script: temp PowerShell probe (not part of deliverable), `dist/keel-sidecar/keel.exe serve --port 8899`, env `KEEL_TOKEN=agentc-packaged-probe-token`, `KEEL_NO_BANNER=1`, `KEEL_FAKE_SCRIPT`/`KEEL_UI_DIR`/`KEEL_UI_PROFILE` removed; process killed with `taskkill /PID … /T /F`.

```
ready=True
page_bytes=47660
marker_KeelCowork=True
marker_ExecutionPolicies=True
marker_safe_mode_badge=False
app_js_status=200 has_api_run=True
no_token_status=403
```

Interpretation: the packaged Python sidecar serves the full local renderer, the live `/api/run` wiring is present in the served JS, the restricted mirror is not served, and the API refuses unauthenticated requests. This is **real packaged runtime execution**, not a source-text check.

### 4.3 Packaging/renderer assertions (Node, no Electron GUI)

```
$ node desktop-app/scripts/test-ui-root.js
SUMMARY: 8/8 uiRoot() cases passed
Renderer precedence verified: full local UI by default, mirror rollback-only.

$ node desktop-app/scripts/assert-ui-entrypoints.js --resources "…\keel\dist\win-unpacked\resources"
SUMMARY: 31/31 checks passed
All entry-point assertions hold: local UI wins, mirror is rollback-only.
```
Notable individual checks: `packaged default uiRoot() resolves to desktop/ui, not site`; `packaged default root is the full local UI (no mirror badge)`; `packaged app.asar main.js matches source main.js — e60eba8bc5ee vs e60eba8bc5ee`; `Tauri frontendDist resolves to desktop/ui`; `fleet-next is NOT a static export`.

### 4.4 Merge regression suites

```
$env:PYTHONPATH='src'; python -m pytest -q tests/audit_agent_execution_lifecycle.py tests/audit_agent_execution_control.py tests/test_fleet.py tests/test_fleet_approvals.py tests/verify_security_round2_trust.py tests/test_packaged_ui_serving.py tests/test_desktop_hardening.py -rxX
...........................................................             [100%]
59 passed in 33.14s
```

These include the prior agent's execution-lifecycle/control suites (whose A-1/A-2/A-3 xfails now pass unmarked against the fixed source), the Fleet HTTP suite, the approvals suite, the workspace-trust suite, the packaged-UI acceptance test and the Electron hardening tests. All green after the merge.

---

## 5. Requirements matrix (merged tree)

| Requirement | Status | Evidence |
|---|---|---|
| Packaged path uses full local renderer, not mirror | **verified** | §3.1, §4.2, §4.3; `test_live_bridge_serves_full_local_ui_not_browser_mirror` |
| Packaged path uses real Python runtime, not simulated agent exec | **verified** | `main.js:143-164`, `webapp.py:1384-1444`, §4.2, `test_real_python_runtime_smoke…` |
| No fake-execution env injected by installer work | **verified** | `test_shipped_configs_do_not_inject_fake_execution`; `KEEL_FAKE_SCRIPT` only at `webapp.py:1023,1400` |
| Real local Echo turn: rows + events + persistence | **verified** | §4.1 echo test; `fleet/echo.py:61-93`; `fleet/service.py:648-685` |
| Cancel signalling | **verified (provider path); echo no-op by design** | `test_real_local_echo_turn…`; `fleet/turn_core.py:39-77` |
| Session continuity across reload/restart | **verified** | echo test: restart with same DB, identical seq list, `latest_seq`, second turn appends |
| Streaming / event delivery | **verified** | SSE frames read off a real socket; NDJSON from real child process |
| Approval / permission enforcement | **verified** | `permissions.py:292-316`; `fleet/approvals.py:135-233`; two new tests + existing approval suites |
| Workspace trust enforcement | **verified at HTTP boundary in merged tree** | `fleet/routes.py` + `service.py` lines in §3.3; new HTTP test covers tree/read/review/write/exec and revocation |
| Prior audit gaps A-1/A-2/A-3 | **closed in merged tree** | `service.py:106` `json_extract`; `asks.py:80-88` pop on answer/timeout; `permissions.py:305-309` deny verdict |

---

## 6. Findings, limitations, non-regressions

1. **F-1 — no-credential runs use a labelled scripted fake model (honest, by design).** A real `python -m keel -p …` child with no provider keys emits `apiKeySource: "none"`, `model: "keel-fake-1"` and a text reply "Keel scaffold: no model provider is wired yet. This run used the built-in scripted fake." The *process, bridge, SQLite, permission and event machinery are real*; the model reply is not. Any claim that a credential-free run exercised a live provider would be false. Evidence: manual CLI probe and `test_real_python_runtime_smoke_streams_ndjson_without_credentials`.
2. **F-2 — packaged artifacts predate the merge (packaging-owner gate, not an execution regression).** `dist/keel-sidecar/keel.exe` and `dist/Keel-Setup-0.1.1.exe` are stamped 2026-11-24 22:38–22:41 local, while `c80c2e1` is 2026-11-25 01:59:56 +0100. `app.asar`'s `main.js` hash matches source, but the sidecar payload should be rebuilt/reverified by Agent E so the new trust/ask/permission code is inside the shipped EXE.
3. **F-3 — Echo has no mid-stream Stop (inherited limitation A-7, not introduced here).** Echo turns never call `turn_core._register_active_turn`, so `POST …/cancel` correctly reports `cancelled: false` before, during and after an echo turn (there is no registered cancel event to signal). Provider turns do register and are signalled. No distribution change touched this.
4. **F-4 — Fleet UI still lacks ask-answer and per-agent Stop affordances (inherited A-5).** `keel/desktop/fleet/fleet.js` contains no `/asks/` or `/cancel` request. Runtime endpoints exist and are verified; this is a UI discoverability gap for the frontend owner, not a distribution regression.
5. **F-5 — static checks are not a GUI click-through.** The Electron window was not driven by a browser automation tool in this round; the packaged probe used the same sidecar the shell spawns plus Node assertions over the packaged layout. The previous round's packaged GUI evidence (`UI-DESKTOP-PACKAGING.md`) remains the GUI-level record.

No source regression is claimed. No files outside Agent C ownership were modified.
