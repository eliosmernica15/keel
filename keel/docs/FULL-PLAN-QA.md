# Full-plan independent QA (Agent G) — 2026-11-24

**Worktree:** `C:\Users\Admin\Desktop\keel-frontend-worktree`
**Branch:** `feat/frontend-completion-2026-11-24`
**Role:** independent QA / full-plan completion verification. No app, feature, lib or component file was edited. No commits and no pushes were made.

**Rule applied:** every `pass` below is tied to a command actually run in this worktree. Raw output is kept in `keel/fleet-next/tests/ui/qa-logs/` (git-ignored). Anything not run is labelled `not run` or `blocked`.

---

## 1. Verification categories (what kind of evidence each check is)

| Category | Checks in this report | Limits |
|---|---|---|
| **Automated — static** | `node tests/ui/verify-ui.mjs` (14 checks, 4 skipped), `npx tsc --noEmit --incremental false`, secret-marker scan | Static heuristics cannot prove rendered behaviour; a pass is not a browser guarantee. |
| **Automated — fixture-based** | `npm run test:features` (5 configs, mocked/local provider), `tests/e2e/12-new-requirements.spec.ts` honest-unavailable assertions | Controlled fixtures prove honest states and error handling, not real provider behaviour. |
| **Automated — real-runtime** | Playwright prod E2E against a real Next production build + real Python bridge on `:8739` with real `~/.keel` (7 real agents / 2 real tasks); `probe_bridge.py` GETs; pytest acceptance tests against real bridge fixtures | Live model turn needs credentials (absent). |
| **Automated — real-browser measurement** | a11y computed-WCAG contrast suite, focus-trap/Dialog specs, 6-viewport screenshot suite, 200 % zoom CSS-viewport proxy | Contrast is computed from styles, not from a screen reader; 200 % zoom is a 720×450 CSS viewport proxy, not native browser zoom. |
| **Manual / human** | Contact-sheet visual inspection, screen-reader walkthrough, packaged-GUI inspection | Contact sheets were inspected in an earlier Agent F pass (recorded in `UI-TEST-MATRIX.md`); **I did not repeat the visual inspection in this round**, and no screen reader or packaged GUI was available. |
| **Externally blocked** | Live provider turn/streaming, Electron/Tauri packaged launch, repo visibility/2FA/branch-protection owner decisions, real long-history provider stream | Named owner gates in `MASTER-PLAN-INVENTORY.md` §2 and `UI-REQUIREMENTS-MATRIX.md` final assessment. |

---

## 2. Independent sample verification of registry "verified" claims

The registry (`PLAN-INDEX.json`, 865 features; 854 `verified`) cites Python test files. **No registry feature cites `fleet-next` sources** — frontend acceptance is tracked separately in `UI-REQUIREMENTS-MATRIX.md` (150 criteria, 131 verified). I therefore sampled 24 registry IDs across five domains plus 5 frontend criteria.

### 2.1 Commands and exact results

```powershell
cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel
$env:PYTHONPATH='src'
python -m pytest -q tests/test_cli_e2e.py tests/test_vertical_slice.py `
  tests/test_resource_limits.py tests/test_runtime_contracts.py tests/test_y3_backend.py `
  tests/test_eval_tools.py tests/test_identity_contracts.py tests/test_repo_contracts.py `
  tests/test_screen_safe_mode.py
# -> 232 passed, 635 subtests passed in 13.40s ; PYTEST_EXIT=0

python -m pytest -q tests/test_session_export.py tests/test_z_backend.py `
  tests/test_agent_contracts.py tests/test_duet.py tests/test_inline_completion.py `
  tests/test_circuit_breaker.py tests/test_status_page.py tests/test_ops_tools.py `
  tests/test_w7_x1_y5_d1_backend.py
# -> 186 passed, 4 subtests passed in 11.45s ; PYTEST_EXIT=0

python -m pytest -q tests/test_tui_functional.py tests/test_tui.py
# -> 5 passed in 1.27s ; PYTEST_EXIT=0

# post-integration re-run (after commits 7a5cd22 / e76aed0 landed), all 18 files combined:
# -> 418 passed, 639 subtests passed in 13.75s ; PYTEST_EXIT=0
```

Raw logs: `registry-sample-runtime-security.txt`, `registry-sample-persistence-agents.txt`, `registry-sample-tui.txt`, `registry-sample-postintegration.txt`.

### 2.2 Sampled registry IDs (24)

| ID | Domain | Cited test(s) located | Result |
|---|---|---|---|
| A1.1 | Runtime / CLI | `test_cli_e2e.py`, `test_vertical_slice.py` | pass (cmd 1) |
| A1.3 | Runtime / TUI | `test_tui_functional.py`, `test_tui.py` | pass (5 tests) |
| A1.11 | Runtime / limits | `test_resource_limits.py` | pass (cmd 1) |
| A1.16 | Persistence | `test_session_export.py` (`test_export_import_roundtrip`, `test_statistics_counts_rows_and_tokens`, `test_bad_bundle_and_unknown_session`, `test_cli_session_commands`) | pass (cmd 2) |
| A3.7 | Runtime / status | `test_status_page.py`, `test_ops_tools.py` | pass (cmd 2) |
| Y3.6 | Runtime contracts | `test_runtime_contracts.py` (48 tests) | pass (cmd 1) |
| Y3.7 | Runtime / scheduler | `test_y3_backend.py` (33 tests) | pass (cmd 1) |
| C11.6 | Security / release hash | `test_eval_tools.py` (3 tests) | pass (cmd 1) |
| Y4.13 | Security / zero secrets | `test_identity_contracts.py` (69 tests; `test_badge_never_claims_clean_without_a_scan`, `test_secret_blocks_release_and_badge_stays_honest`, `test_multiple_secret_families_detected`) | pass (cmd 1) |
| Y5.4 | Security / webhook HMAC | `test_repo_contracts.py` (`TestWebhookSignatures`, `test_no_secret_rejects_every_request`) | pass (cmd 1) |
| Z15 | Security / prompt injection | `test_z_backend.py` (92 tests) | pass (cmd 2) |
| C1.4 | Security / screen-safe mode | `test_screen_safe_mode.py` (4 tests) | pass (cmd 1) |
| Z4 | Persistence / journal | `test_repo_contracts.py` (`TestCrashSafeJournal`) | pass (cmd 1) |
| Z6 | Persistence / local sync | `test_z_backend.py` | pass (cmd 2) |
| Z3 | Persistence / redacted replay | `test_z_backend.py` (`test_write_replay_persists_verified_html`, `test_summary_and_anonymized_export`) | pass (cmd 2) |
| W2.1 | Agents / contracts | `test_agent_contracts.py` | pass (cmd 2) |
| W2.2 | Agents / contracts | `test_agent_contracts.py` | pass (cmd 2) |
| Z2 | Agents / contract tests | `test_z_backend.py` | pass (cmd 2) |
| B2.3 | Agents / Duet reviewer | `test_duet.py` | pass (cmd 2) |
| C2.3 | Agents / inline completion | `test_inline_completion.py`, `test_duet.py` | pass (cmd 2) |
| Y3.8 | Agents / device approval | `test_w7_x1_y5_d1_backend.py` (34 tests) | pass (cmd 2) |
| B3.11 | Runtime / circuit breaker | `test_circuit_breaker.py` (5 tests) | pass (cmd 2) |
| Z16 | Runtime / cost budget | `test_z_backend.py` | pass (cmd 2) |
| Y6.2 | Governance / artifacts | `test_repo_contracts.py` (`TestArtifactHandling`) | pass (cmd 1) |

**Sample verdict:** all 24 sampled `verified` claims had their cited test file present and passing (423 test functions + 639 subtests across the three pre-integration commands; 418 tests + 639 subtests post-integration). No sampled claim was unsupported. This is a sample, **not** a re-verification of all 854 registry IDs.

### 2.3 Frontend criteria sampled (via `UI-REQUIREMENTS-MATRIX.md`)

| Criterion (final matrix) | Evidence re-run in this round | Result |
|---|---|---|
| Fleet Board / Delegation map / Live wall / Cost real panels | `tests/e2e/12-new-requirements.spec.ts:59` (prod config) | pass post-integration |
| Fleet board columns = real task statuses | `12-new-requirements.spec.ts:91` | pass |
| Cowork conversation search (Ctrl+F, match count, step, Escape) | `12-new-requirements.spec.ts:105,129` | pass |
| Onboarding Help & troubleshooting | `12-new-requirements.spec.ts` (prod run) | pass |
| Duet builder/reviewer identity + comment-only reviewer | `12-new-requirements.spec.ts:209,219` | pass |

---

## 3. Full frontend suite re-runs after this round's integrations

Environment: QA-owned bridge on `:8739` (`tests/ui/start_bridge.py`, throwaway token `local-e2e-bridge-token`, real `~/.keel`); QA-owned production build in `.next-e2e` on `:3300`; a11y dev server on `:3302`. The lead's `:3200`/`.next` and `:3000` were never touched. Integration commits present at the final run: `dee01be`, `7a5cd22`, `ea3f20b`, `e76aed0`.

```powershell
cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel\fleet-next
$env:KEEL_E2E_BRIDGE_TOKEN='local-e2e-bridge-token'
npx tsc --noEmit --incremental false
node tests/ui/verify-ui.mjs
npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line
npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line
npm run test:features
```

| Check | Exact result | Evidence log |
|---|---|---|
| TypeScript | `TSC_EXIT=0`, no output (also clean after the zoom-a11y helper landed) | `tsc-final.txt`, `tsc-after-zoom-edit.txt` |
| Static UI harness | `UI verification: {"info":1,"pass":14,"skipped":4}`, exit 0 | `verify-ui-final.txt`, `verify-ui-postintegration.txt` |
| Production build (inside prod config) | compiled successfully; 5/5 pages; server started | `playwright-prod-postintegration.txt` |
| Prod E2E, first attempt this round | webServer build failed twice on another agent's in-flight `tests/zoom-a11y/helpers.ts` TS errors (see QA-G-001) | `playwright-prod-final.txt`, `playwright-prod-final-2.txt` |
| Prod E2E, first successful run (mid-integration) | **131 passed / 13 failed (144 tests, 6.1 min)**; 13 failures = 11 bridge-504 console gates + 2 QA-control race (my own spec, later fixed) | `playwright-prod-final-3.txt` |
| Prod E2E, **final post-integration run** | **142 passed / 2 failed (144 tests, 3.4 min)**; both failures are 504 console-gate noise (QA-F-011) | `playwright-prod-postintegration.txt` |
| Single-worker re-run of the 2 failures | `1 passed` (Fleet panels) and `2 passed` (dark/light 1440×900 cowork) — no app change | `prod-rerun-2-failures.txt`, `prod-rerun-dark-cowork.txt` |
| Earlier 11-failure set, single-worker re-run | `10 passed` (01/02/05) and `108 passed` (07+09) — all environmental | `prod-rerun-core.txt`, `prod-rerun-responsive.txt` |
| Accessibility (full 12) | first run **8 passed / 4 failed (3.6 m)**; targeted re-run **2 passed / 2 failed**; final post-integration **12 passed / 0 failed (1.2 min)** | `a11y-final.txt`, `a11y-rerun-4.txt`, `a11y-postintegration.txt` |
| QA hydration-gate control spec (new, QA-owned) | **4 passed** in dev config and **4 passed** against the production server | `qa-hydration-control.txt`, `qa-hydration-control-prod.txt` |
| Feature suites `npm run test:features` | Cowork **28**, Code+Duet **30**, Fleet **20**, Capabilities/Settings **17**, Onboarding **13** → **108 passed / 0 failed** | `features-final.txt` |
| Live bridge GET probe (harness `LIVE-01`) | 11 read-only endpoints HTTP 200; explicit `GET /api/fleet/bots` → HTTP 200 | `verify-ui-postintegration.txt` |

**Functional bottom line:** with the strict console gate, production E2E is 142/144; the two non-passes reproduce as green on single-worker re-runs and are attributed to the known bridge 504 issue, not to app behaviour. With the console gate excluded for those two, all 144 functional assertions pass.

### 3.1 Retests of previously open defects delivered by owners

| Defect | Prior status | This-round retest |
|---|---|---|
| QA-F-013 (Cowork search Escape after match-nav buttons) | open | `12-new-requirements.spec.ts:129` passes in prod runs → **fixed and re-verified** (commit `e038550`). |
| QA-F-016 / 017 / 018 (owner fixture drift) | open | All five feature suites 108/108 → **fixed by owners**. |
| QA-F-011 (bridge 504) | open / environmental | Recurred (99 console entries in the first run, 12 in the final run); **still open / environmental**. |
| QA-F-009 / 010 / 015 (CSS purity, Fleet tabs) | fixed | Production build compiles and Fleet panel E2E passes → **still fixed**. |
| QA-001…QA-008 | fixed | Static harness guards `API-03`/`EVT-01`/`FAB-02` pass (`{"pass":14}`) → **still fixed**. |

---

## 4. Generated-file discipline

Byte-accurate Git blob comparison (`git hash-object` vs `git rev-parse HEAD:<path>`) plus `git status`/`git diff --quiet`:

| File | Worktree blob == HEAD blob | Changed since round-start commit `3863a2b`? |
|---|---|---|
| `PLAN-INDEX.json` | yes (`c707d96…`) | no |
| `parity.json` (root) | yes (`c707d96…`) | no |
| `Keel_Master_Plan_v6.md` | yes (`0135d29…`) | no |
| `keel/docs/parity.json` | yes (`1701d43…`) | no |

`git diff --stat 3863a2b..HEAD -- <the four files>` is empty. Registry last changed at `da81b31` (02:37), before this round. No agent hand-edited a generated file. (A naive `Get-FileHash`/`git show` comparison reports differences for CRLF-normalised files; the Git blob comparison is authoritative.)

---

## 5. Secret scan and commit-artifact hygiene

```powershell
git grep -n -E 'sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|...|PRIVATE KEY' -- .
# -> NONE in tracked files
python -c "from keel.dev_tools import security_scan; ..."   # repo's own scanner
# -> 36 flagged files / 128 matching lines in src/, tests/, fleet-next/tests/
```

Triage of all 128 flagged lines (redacted preview saved in `secret-scan-triage.txt`): every match is a **synthetic test fixture** such as `sk-abc…`, `sk-live-SECRET-DO-NOT-ECHO-9876543210`, `sk-ant-not-a-real-key-7Qw9`, `ghp_abc…`, `AKIAIO…` or a fake PEM header used to test redaction. No real credential was found in tracked files or in my untracked QA spec. The identity-contracts secret/release-gate tests (`test_identity_contracts.py`, 69 tests) pass.

Commit-artifact check over the last 25 commits:
- No `.next*`, `node_modules`, `qa-logs`, `test-results`, `*.log`, `.pytest_cache`, `dist/` or `build/` output was added.
- `.gitignore` covers `node_modules/`, `.next/`, `.next-*/`, `.next-e2e/`, `**/tests/e2e/test-results/`, `**/test-results/`, `**/qa-logs/`, `*.log`.
- **Exception (QA-G-004):** `keel/fleet-next/tests/ui/results.json` and `viewport-results.json` are tracked generated harness outputs (added in `f29a76f` / `e038550`) and show dirty after every harness run. `agent-reference-shots/denied-tool-results.json`, `desktop-app/build/*` and `site/**/screenshots/*` are intentional checked-in reference/build sources, not this round's generated artifacts.

---

## 6. Reproducible defect table

Severity is QA impact; "owner" is the owning workstream from `MASTER-PLAN-INVENTORY.md` §3.

| ID | Severity | Owner | File:line | Finding | Status / retest |
|---|---|---|---|---|---|
| QA-G-001 | Medium (build blocker, transient) | Agent A / zoom-a11y | `fleet-next/tests/zoom-a11y/helpers.ts:170` and `:101` (owner file) | `next build` (prod E2E webServer) failed twice on TS errors in an untracked, in-flight test helper; `tsconfig.json` includes `**/*.ts`, so any test helper error blocks the production build. | **fixed & re-verified** — owner committed stable file in `e76aed0`; post-integration build compiled and prod suite ran. Structural risk remains: a test-only TS error can block release build. |
| QA-G-002 | Low (fixture flake) | Agent A (a11y) | `fleet-next/tests/a11y/helpers.ts:4-24` vs robust gate `tests/e2e/fixtures.ts:68` | `openAppThemed` waits for server-rendered markup only, not the mount-effect `html[data-reduced-motion]` hydration marker. Full a11y run 8/12, targeted re-run 2/4, post-integration 12/12 → flaky keyboard/dialog assertions. QA control spec passes 4/4 in dev and prod with the robust gate. | **open (fixture reliability)**; not an app defect. Fix: wait for `html[data-reduced-motion]` in `openAppThemed`. |
| QA-G-003 | Medium (environmental) | Backend / lead | `fleet-next/app/api/bridge/[...path]/route.ts:149-154`; bridge `ConnectionAbortedError [WinError 10053]` in `bridge-8739.log` | Intermittent `GET /api/bridge/* 504` under parallel load trips the strict console gate; 99 entries in first 144-test run, 12 in final run. All affected tests pass single-worker; 13/13 read-only route probe passes. | **open / environmental** (recurrence of QA-F-011). GET retry in `lib/client.ts` is write-safe but cannot erase the browser console entry. |
| QA-G-004 | Low (hygiene) | Agent G / lead | `fleet-next/tests/ui/results.json`, `viewport-results.json` | Generated harness outputs are version-controlled; every run dirties the worktree (this round: `results.json` modified). | **open** — recommend untrack and add to `.gitignore`; keep evidence in QA docs/logs instead. |
| QA-F-013 | Medium (a11y/UX) | Cowork (A) | `features/cowork/Search.tsx:47-52` | Escape did not close search after match-nav buttons had focus. | **fixed & re-verified** this round (`12-new-requirements.spec.ts:129` passes; commit `e038550`). |
| QA-F-016/017/018 | Low (fixture/copy) | Cowork (A), Onboarding (E) | owner feature specs | Owner fixture drift after idempotent-GET retry/honest error copy. | **fixed & re-verified** — feature suites 108/108. |

No new app-code defect was confirmed in this round.

---

## 7. Open / externally blocked checks

1. **Live provider turn and streaming** — no provider credentials on the host. Fixtures verify honest `provider_not_configured` states; no real token spend was attempted.
2. **Real 200 % browser zoom** — verified via 720×450 CSS-viewport proxy (`tests/a11y/04`, `tests/e2e/13-qa-hydration-gate.spec.ts`); native browser zoom UI not available in Playwright. Screen-reader hardware (NVDA/JAWS/VoiceOver) unavailable; ARIA/announcement checks are DOM-level only.
3. **Packaged Electron/Tauri GUI** — no fresh signed build / MSVC `link.exe`; only source entry-point assertions were available (21/21, 26/26 with unpacked resources in the earlier Agent F pass; **not repeated by me**).
4. **Bridge 504 root cause** — QA-G-003; reproducible under parallel load, not under single worker.
5. **Governance owner gates** — repo visibility, 2FA, branch protection, signed commits (C11.1, C11.2, Y6.4) are owner decisions; not performed and not recommended to perform.
6. **Whole-registry re-verification** — 854 `verified` IDs inherited from the registry; 24 sampled here. The 98.7 % registry figure is a claim about recorded evidence, not a fresh proof of every acceptance criterion.

---

## 8. Files I changed (exclusive ownership only)

- `keel/docs/FULL-PLAN-QA.md` (new).
- `keel/docs/UI-TEST-MATRIX.md` (appended verified-run section).
- `keel/fleet-next/tests/e2e/13-qa-hydration-gate.spec.ts` (new QA control spec).
- `keel/fleet-next/tests/ui/qa-logs/**` (raw evidence; git-ignored by the lead's `.gitignore`).
- `keel/fleet-next/tests/ui/results.json` is regenerated by the harness (already tracked — see QA-G-004).

No commits, no pushes, no app/feature/lib/component edits, no generated-file edits.
