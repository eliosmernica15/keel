# Independent distribution-journey QA (Agent G) — production distribution round, 2026-11-25

**Worktree:** `C:\Users\Admin\Desktop\keel-frontend-worktree`
**Branch:** `feat/frontend-completion-2026-11-24`
**Baseline (pre-round) commit:** `c80c2e1` (feature branch before the baseline doc); `origin/main` was `9a63be9`.
**Role:** independent QA of the *actual user journey*. No feature implementation, site/release source, or other agent's file was edited. No commits and no pushes were made.
**Rule:** every `pass` below is tied to a command run in this worktree. Raw logs live in `keel/fleet-next/tests/distribution-qa/qa-logs/` (git-ignored) and screenshots in `.../evidence/` (git-ignored). Anything not run is labelled `not run`, `mocked`, `static-only` or `blocked`.

---

## 1. What was built for repeatable QA (exclusive ownership)

| File | Purpose |
|---|---|
| `keel/fleet-next/tests/distribution-qa/server.mjs` | QA-owned static server for the real `keel/site` tree. Applies the real `vercel.json` redirects/rewrites/headers; serves a QA-only `/qa-installer.exe` fixture and a `/__qa_set_sw_version` control (test scaffolding only; never writes to site files). Optional `KEEL_QA_SITE_DIR` serves a git-archived pre-round tree for pixel comparison. Port 3310 (baseline: 3311). |
| `.../playwright.config.ts` | Dedicated Chromium project; fixed 1280×900 viewport (device-spread order corrected so the viewport is not silently replaced), one worker for SW/cache isolation. |
| `.../fixtures.ts` | Deterministic manifests: all-unavailable fallback, one verified HTTPS/GitHub-host installer, dishonest manifest (size 0, short SHA, non-approved host), 7 mocked platform profiles (Win x64/ARM64, macOS ARM64/x64, Linux, iOS, Android). Manifest responses are mocked at the page network boundary; the real handler is tested separately. |
| `.../01-download-journey.spec.ts` | 16 tests: render, OS/arch matrix, arch fallback, explicit macOS/Linux choices, manifest fallback/failure, honesty gate, primary URL. |
| `.../02-pwa-journey.spec.ts` | 7 tests: start URL, routing config, fleet-next manifest, contextual link, offline shell, no installer/manifest caching, SW update. |
| `.../03-desktop-first-launch.spec.ts` | 4 tests: renderer-selection source contract, **real Python bridge** on :8742 with `KEEL_UI_DIR=desktop/ui`, existing guided tour via keyboard, no duplicate setup wizard. |
| `.../04-landing-regression.spec.ts` | 3 tests: byte-identity of unrelated site files, app.html diff scope, pixel identity of `/`, `/privacy`, `/downloads` vs a git-archived baseline tree. |
| `.../05-api-contract.spec.ts` | 7 tests: real `/api/download-manifest` handler invoked with mock req/res (GET-only, 503/502/405 paths, size cap, byte-identical 200 with TTL, no embedded credentials). |
| `.../06-a11y.spec.ts` | 5 tests: accessible names, no dead hrefs, one h1, disabled controls cannot download, keyboard reachability of primary CTA and in-app link. |
| `.../qa-logs/**`, `.../evidence/**` | Raw run output and screenshots (git-ignored by a local `.gitignore`). |

**Distribution QA command (self-contained):**

```powershell
cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel\fleet-next
$env:KEEL_E2E_BRIDGE_TOKEN='local-e2e-bridge-token'
npx tsc --noEmit --incremental false
npx playwright test --config tests/distribution-qa/playwright.config.ts --reporter=list
```

Final result: **`TSC_EXIT=0`; 42 passed / 0 failed (33.6 s), `PW_EXIT=0`** — log `qa-logs/final-acceptance-run.txt`. The suite was re-run after each owner integration; it first ran 25/43 then 30/42 while other agents were still landing files, and reached 42/42 on the final integrated state (commit `fa57c06` plus the working-tree changes listed in §8).

---

## 2. Verification by journey step

### 2.1 Download page, detection and manifest honesty — PASS (browser, mocked manifests)

All assertions in `01-download-journey.spec.ts` pass on the integrated page. Evidence: `qa-logs/final-acceptance-run.txt`; failure screenshots from earlier iterations are retained under `test-results/` (git-ignored).

- **Rendering:** `/download` shows `Download Keel`, version `v9.9.9`, a live ARIA status and a single primary action. `download.html` loads both `download-clone.js` (chrome) and the manifest-driven `ui/download.js`.
- **OS/arch matrix (mocked UA + `navigator.platform` + `userAgentData.getHighEntropyValues`):** Windows x64 → `{windows,x64}`; Windows ARM64 → `{windows,arm64}` with an honest "Windows on ARM not published / x64 under emulation" note; macOS ARM64 → `{macos,arm64}`; macOS x64 → `{macos,x64}`; Linux x64 → `{linux,x64}`; iOS/Android → unsupported note, no installer offered. The page's own exported `detectPlatform()` was exercised in-browser for each profile.
- **Architecture fallback:** with high-entropy hints suppressed, the UA `Win64` string still yields Windows x64. macOS keeps arch unknown when hints are absent and asks for an explicit Apple Silicon/Intel choice (no silent wrong-architecture pick). Linux offers explicit DEB and RPM variants; the package family is never guessed from the UA.
- **Manifest loading/failure:** API 503 → valid committed fallback used; API and fallback both fail → honest "manifest unavailable" state with zero enabled installer links. The real handler's 405/503/502/200 contract is separately verified in `05-api-contract.spec.ts`.
- **Unavailable packages:** with the all-unavailable fallback or the dishonest manifest (`available:true` but size 0 / short SHA / non-approved host / missing URL), no enabled installer anchor is rendered; disabled actions are buttons with `aria-disabled`, not navigable installer links.
- **Primary action:** with a verified fixture (`available`, `verified`, `verified_at`, positive size, 64-hex SHA, first-party HTTPS host), exactly one enabled CTA carries the **exact manifest URL** (`https://github.com/.../Keel-Setup-9.9.9.exe`), `rel="noopener"`, an accessible "Download …" label, and relies on a real user gesture. No URL, size or checksum is fabricated.

### 2.2 PWA — PASS (browser, runtime + static)

- **Start URL:** `site/manifest.webmanifest` `start_url=/app.html`; following the real vercel rules resolves to `/app` and returns the app page (`<title>Keel - Desktop & Code</title>`), never `/download`. `fleet-next/app/manifest.ts` also has `start_url="/"`, not `/download`.
- **Routing config:** no rewrite/redirect whose source is `/app` or `/app.html` targets `/download`. The baseline document's claim that `/app` redirected to `/download` was already false at `c80c2e1` — see defect QA-G-D05.
- **Contextual link:** exactly one in-app link to `/download` (`site/app.html:132`, `#nav-download`, labelled "Download Keel"). It is keyboard focusable and resolves to the production download path. It is written as a same-origin relative URL; on the deployed `keel-desktop.vercel.app` origin it resolves to the contracted `https://keel-desktop.vercel.app/download`.
- **Offline shell:** after `/app` registers `sw.js` and the worker activates, setting the network offline and navigating to `/` renders the cached Keel landing shell.
- **No installer caching:** after fetching a same-origin fake installer plus `/download.json` and `/api/download-manifest`, none of the three is present in the SW cache; the shell cache is the only cache. Cross-origin requests are untouched by the origin guard.
- **Update behaviour:** the QA server served a changed SW version on demand; `registration.update()` activated `keel-shell-v99`, installed its shell cache and deleted the old `v16` cache (migration path verified). The site source itself was never edited for this test.

### 2.3 Desktop first launch — PASS (real bridge + source contract; packaged GUI not re-run)

- **Renderer selection (source):** `desktop-app/main.js` `uiRoot()` prefers `resources/desktop/ui`, then legacy `resources/ui`; `resources/site` is reachable only behind `KEEL_UI_PROFILE=mirror`. The window loads `http://127.0.0.1:<port>/?t=<token>` with `contextIsolation`, `sandbox` and no `nodeIntegration`; the sidecar is stopped on every exit path.
- **Real bridge (runtime):** spawned `python -m keel serve --port 8742` with `KEEL_UI_DIR=desktop/ui` and the QA token; `GET /?t=…` returned the **local renderer** title (not the `site/app.html` mirror title) and `GET /api/fleet/bots` returned HTTP 200 JSON. No mocked bridge was used for this check.
- **Existing onboarding, no duplicate setup:** the guided tour (`#tutorial-overlay`, `role=dialog`, `aria-modal`, `keel_tutorial_seen_v1`) opens from `#btn-tutorial` via keyboard (Enter), closes with Escape, and stays closed after reload. No second setup/onboarding wizard id was found, and `keel/desktop/ui` is unchanged vs `c80c2e1`.
- **Accessibility/keyboard:** covered by `06-a11y.spec.ts` plus the full 12-test a11y suite (§3). No screen-reader hardware was available; ARIA/dialog assertions are DOM-level only.

### 2.4 Landing-page and unrelated-page regression gate — PASS

- `git diff --name-only c80c2e1 -- keel/site` shows changes only in the distribution allowlist: `download.html`, `download.json`, `manifest.webmanifest`, `sw.js`, `ui/download.js`, `vercel.json` (plus test scaffolding `site/tests/**` and `ui/download-ux.css`). `index.html`, all other marketing pages, assets and shared CSS/JS are byte-identical. `app.html` changed only on the `/download` contextual-link line.
- Pixel comparison: `keel/site` was extracted from `c80c2e1` with `git archive`, served on :3311, and full-page screenshots were compared byte-for-byte with the current site at 1280×900: `/` 1280×3367 (identical), `/privacy` 1280×900 (identical), `/downloads` (identical). Evidence: `evidence/{landing,privacy,downloads}-{baseline,current}.png` (three matching pairs). The animated news toast was hidden in both captures and the project viewport was pinned to 1280×900; without those two harness fixes the comparison was flaky/false-positive, not a product change.

### 2.5 Native installers — honest evidence classification

| Platform / artifact | Classification | What was actually verified | What was **not** verified |
|---|---|---|---|
| Windows `Keel-Setup-0.1.1.exe` (NSIS) | **Built locally in a previous round; static-only this round; not publicly hosted; unsigned** | Local artifact exists (`keel/dist/Keel-Setup-0.1.1.exe`, 143,931,562 bytes); `python -m keel.release check-packaging` → `PASS (config)`; revised workflow adds per-OS static checks and a truthful `Get-AuthenticodeSignature` status step. | No fresh 0.1.1 install/launch/clean-VM test this round; no OS signature; no public URL; no download-back/SHA-256 comparison from a public asset. |
| macOS `Keel-0.1.1-macos-{arm64,x64}.pkg` | **Static-only / CI-configured; not executed; blocked on macOS hardware and owner credentials** | Native PKG targets, install location `/Applications`, bundle id and both architectures are in `desktop-app/package.json` and `release/packaging.py`; workflow compiles on native macOS runners and reports `pkgutil --check-signature` truthfully. | No PKG built here, no Gatekeeper/notarization check, no GUI launch. Compilation ≠ install. |
| Linux `.deb` / `.rpm` | **Static-only / CI-configured; not executed** | DEB primary + RPM alternative configured; dependencies/desktop entry/icon checks pass; workflow installs `dpkg-dev`, `desktop-file-utils`, `rpm` on a native Linux runner. | No package built here, no `apt`/`dnf` install or desktop launch on Linux. |
| Public availability | **Unavailable / owner-blocked** | `site/download.json` has every channel `available:false`, `verified:false`, `url:null`; real API returns `503 manifest_not_configured` when unset. | No published GitHub Release or verified public HTTPS asset; Ed25519 signing key, OS certificates/notarization and public binary feed are owner gates (`DISTRIBUTION-BASELINE.md` §4, `DISTRIBUTION-INSTALLATION.md` §7). |

**Rule applied:** a native install is never claimed from compilation or static configuration. The only claim supported here is "configured and statically checked"; macOS/Linux install is `not tested / blocked`.

---

## 3. Existing suites re-run after integration (exact counts)

Environment: QA-owned bridge on `:8739` (`KEEL_TOKEN=local-e2e-bridge-token`), no state-changing HTTP issued by QA. Commands run from `keel/fleet-next` unless noted.

| Check | Command | Result | Log |
|---|---|---|---|
| TypeScript | `npx tsc --noEmit --incremental false` | **exit 0**, no diagnostics | — |
| Static UI harness | `node tests/ui/verify-ui.mjs` | **`{"info":1,"pass":14,"skipped":4}`, exit 0** | `qa-logs/verify-ui-postround.txt` |
| Site download logic + UX tests (Agent A) | `node --test keel/site/tests/*.test.mjs` (from repo root) | **20 passed / 0 failed**, exit 0 | `qa-logs/site-tests.txt` |
| Accessibility (full 12) | `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | **12 passed / 0 failed (1.2 m)** | `qa-logs/a11y-postround.txt` |
| Feature suites | `npm run test:features` | Cowork **28**, Code+Duet **30**, Fleet **20**, Capabilities/Settings **17**, Onboarding **13** → **108 passed / 0 failed** | `qa-logs/features-postround.txt` |
| Production E2E | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line` | **144 passed / 0 failed (3.1 m)** | `qa-logs/prod-e2e-postround.txt` |
| Distribution QA (this agent) | see §1 | **42 passed / 0 failed (33.6 s)** | `qa-logs/final-acceptance-run.txt` |
| Distribution/release Python subset | `cd keel; $env:PYTHONPATH='src'; python -m pytest -q tests/verify_distribution_release.py tests/test_platform_targets.py tests/test_packaging_config.py tests/test_updater.py tests/test_release_verify_url_policy.py` | **45 passed in 9.13 s**, exit 0 | `qa-logs/distribution-python.txt` |
| Packaging static acceptance | `python -m keel.release check-packaging` (from `keel/`) | **`packaging checks: PASS (config)`**, exit 0 | — |

**Flaky cases:** none reproduced in this round. The historical bridge-504 console-gate flake (QA-G-003 / QA-F-011) did **not** recur — 144/144 on one run. Two transient failures were in my own harness, not the product: (a) the news toast's timed animation made the landing screenshot comparison false-positive, fixed by hiding `.l-news,.kp-news` in both captures; (b) the Playwright device preset overrode the configured 1280×900 viewport, producing a 720 px vs 900 px screenshot-height mismatch, fixed by pinning the project viewport. Both were re-verified green.

---

## 4. Reproducible defect / finding log

Severity is QA impact; owner is the owning workstream. `fixed` rows were retested by the command in §1/§3.

| ID | Severity | Owner | File:line | Finding | Status / retest |
|---|---|---|---|---|---|
| QA-G-D01 | High | Agent A | `keel/site/download.html:641` at `c80c2e1` (now `:644-645`) | Pre-round `/download` loaded only `download-clone.js`; the manifest-driven `ui/download.js` was never executed, so there was no OS detection, no manifest loading and no honest availability gate in the real page. | **fixed & re-verified** during this round: both modules are loaded; 42/42 distribution tests pass, including the full detection matrix and manifest-failure states. |
| QA-G-D02 | Medium | Agent A / Agent E | `keel/site/download.json:30,76` (pre-round) | Committed fallback advertised stale archive artifacts (`.dmg`/`.zip`/`.AppImage`) while the configured native products are PKG/DEB/RPM. | **fixed & re-verified**: fallback now lists `.pkg`/`.deb`/`.rpm` and still reports all channels unavailable. |
| QA-G-D03 | Medium (owner gate) | Lead / Agent E | `keel/site/download.json:19,20,34,35,60,61`; `site/api/download-manifest.js:25-27` | No public installer exists: every channel is unavailable and the API returns 503 without `KEEL_DOWNLOAD_MANIFEST_URL`. This is *intended honesty*, but it blocks the "download works for a real user" acceptance item. | **open / blocked** on owner signing key + public binary feed. No defect in the UI; do not flip availability without a real verified asset. |
| QA-G-D04 | High (evidence gap) | Agent E / Lead | `.github/workflows/build-desktop.yml` (native jobs), `keel/dist/Keel-Setup-0.1.1.exe` | macOS PKG and Linux DEB/RPM builds, installs and launches were **not executed** here; Windows EXE was only built in a previous round, not re-installed this round. Workflows are configured but no run evidence exists in the worktree. | **not tested / blocked** (no macOS/Linux hardware, no CI run artifact). Never claim a native install from compilation. |
| QA-G-D05 | Low (doc inaccuracy) | Lead | `keel/docs/DISTRIBUTION-BASELINE.md:13` | Baseline claims `/app` and `/app.html` redirect to `/download`; `git show c80c2e1:keel/site/vercel.json` shows `/app → /app.html` rewrite and `/app.html → /app` redirect, with no `/download` target. | **open (documentation only)**; runtime PWA routing verified correct by test. |
| QA-G-D06 | Low (hygiene) | Lead / QA | `keel/fleet-next/tests/ui/results.json` (tracked generated output) | Running the existing static harness dirties this tracked file (inherited QA-G-004). QA did not hand-edit it. | **open**; recommend untrack + `.gitignore`. |
| QA-G-D07 | Low (contract nuance, not a defect) | Agent A | `keel/site/app.html:132` | Contextual link is the relative `/download`, not the literal absolute `https://keel-desktop.vercel.app/download` named in the baseline. On the deployed origin it resolves to the same URL and is the only in-app download link. | **accepted**; test asserts pathname `/download` and one occurrence. |

No new application-code defect was confirmed in the integrated state; all 42 distribution QA tests and all existing frontend suites are green.

---

## 5. Largest assurance gaps

1. **No real public installer** (QA-G-D03): the whole "download → install" chain ends at an honest disabled CTA until an owner publishes a verified asset.
2. **Native macOS/Linux install/launch** (QA-G-D04): static config and CI workflow definitions only; no clean-VM, Gatekeeper/SmartScreen, uninstall/data-preservation re-test this round.
3. **PWA installation itself**: verified start URL, offline shell, cache hygiene and update mechanics in Chromium; an actual *installed PWA window* on a real OS was not launched.
4. **Screen reader / real browser zoom**: DOM-level ARIA and keyboard checks only; no NVDA/JAWS/VoiceOver and no native zoom UI.
5. **Live provider turn / credentials**: out of scope for this round; no token spend attempted.

---

## 6. Final acceptance checklist

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | `/download` renders; version and honest status visible | PASS | `01-download-journey.spec.ts` render test |
| 2 | OS/arch detection for Win x64/ARM64, macOS ARM64/x64, Linux; iOS/Android unsupported | PASS (mocked UA/platform) | 7 matrix tests |
| 3 | Architecture fallback from UA when hints unavailable; explicit macOS arch and Linux DEB/RPM choices | PASS | 3 fallback/choice tests |
| 4 | Manifest loads from API then fallback; both-failure empty state | PASS (API mocked at page boundary; real handler unit-tested) | 2 tests + `05-api-contract.spec.ts` |
| 5 | Unavailable packages cannot be downloaded; dishonest flags never enable a link | PASS | 2 honesty tests |
| 6 | Primary CTA href equals the verified manifest URL; user-gesture link | PASS | 1 test |
| 7 | PWA start URL opens `/app`, never `/download`; routing config clean | PASS | `02-pwa-journey.spec.ts` |
| 8 | Exactly one contextual in-app link to `/download`, keyboard reachable | PASS | PWA + a11y tests |
| 9 | Offline shell works; no installer/manifest cached; update replaces old cache | PASS | 3 SW tests |
| 10 | Desktop loads local renderer over real bridge; existing onboarding once; keyboard/a11y | PASS (real bridge; packaged GUI not re-run) | `03-desktop-first-launch.spec.ts`, a11y suite |
| 11 | Marketing homepage and unrelated pages byte- and pixel-identical to `c80c2e1` | PASS | `04-landing-regression.spec.ts`, 3 screenshot pairs |
| 12 | Native installers classified without overclaiming | PASS (classification recorded) | §2.5, QA-G-D04 |
| 13 | Defect log reproducible with owner/severity/file:line | PASS | §4 |
| 14 | Existing frontend suites re-run with exact counts | PASS | §3 |
| 15 | Public verified installer available for end users | BLOCKED (owner gate) | QA-G-D03 |

**Overall QA verdict:** the *site/PWA/desktop-renderer journey* is accepted on the integrated worktree (42/42 QA tests, 108/108 feature tests, 144/144 prod E2E, 12/12 a11y, 20/20 site tests, 45/45 release-python subset). The *distribution* half remains blocked by owner gates: no signed/public installer exists and no macOS/Linux native install was executed. Those are honestly classified, not silently passed.

---

## 7. Files I changed (exclusive ownership only)

- `keel/fleet-next/tests/distribution-qa/**` (new server, config, fixtures, 6 spec files, local `.gitignore`, logs and evidence).
- `keel/docs/DISTRIBUTION-QA.md` (new; this report).

Side effect: running the pre-existing `node tests/ui/verify-ui.mjs` regenerated the already-tracked `keel/fleet-next/tests/ui/results.json` (QA-G-D06). No app/feature/site/release source was edited; no commits or pushes.
