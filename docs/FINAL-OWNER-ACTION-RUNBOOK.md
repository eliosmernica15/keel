# FINAL OWNER ACTION RUNBOOK — exact, safe steps for the eight external gates

> **Status:** implementation-ready instructions only. Nothing in this runbook has been
> performed by the engineering workstream. No push, tag, secret write, signing,
> publication or deployment has occurred.
>
> **Authority:** `FINAL-PRODUCTION-READINESS-MATRIX.md` §C/§E and
> `FINAL-OWNER-ACTIONS.md` A1–A5. Gate IDs below are the PR-01…PR-20 gate IDs from
> that matrix. Final execution branch reference: `release/final-execution-2026-11-25`
> (local HEAD `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` at the reconciliation date,
> 2026-11-25). Resolve the exact SHA at the moment of promotion with
> `git rev-parse HEAD`; branch references are authoritative over any SHA quoted here.

## Safety invariant — read once, applies to all eight sections

**Never paste a secret value into chat, an issue, a PR, a log, a test fixture, an
evidence document, or any file inside this repository.** Secret *names* only are
recorded here. All values are entered directly into the owner-controlled provider
account or the GitHub Secrets UI, or exported into a single shell session for a
one-shot command and unset immediately afterwards. `signing-readiness.yml` reports
only `=CONFIGURED` / `=MISSING` and must never be modified to print a value.
`verify_live_provider.py` records only provider, model, timestamp, commit, a result
summary and quota context; it scrubs all known credential values from its output.
Do not relax a fail-closed flag (`--allow-live-provider-check`,
`--confirm-free-tier-current`, `KEEL_REQUIRE_SIGNED`) to make a red gate green.

---

## 1. GitHub billing / Actions runner assignment

**Gate unlocked:** CI execution for every workflow; prerequisite for PR-06, PR-17,
PR-19 and PR-20 evidence collected on GitHub.

- **Why (external):** every failing job was refused *before* runner assignment —
  `steps: []`, `runner_id: 0`, `duration_ms: 0`, `run_duration_ms: 3000`, log ZIP 22
  bytes with zero entries. The authoritative check-run annotation on all eight jobs
  is *"The job was not started because recent account payments have failed or your
  spending limit needs to be increased"* (`FINAL-CI-DIAGNOSIS.md` §2). No repository
  edit can start a runner.
- **Required access:** GitHub account owner / billing administrator for the personal
  account `eliosmernica15` (repository `eliosmernica15/keel`, private).
- **Cost / free status:** paid action. The account's Actions minutes and payment
  method govern dispatch; macOS and Windows matrix minutes are billed at a higher
  multiplier than Linux on private plans. Confirm the current rate in the UI before
  enabling a large matrix. Billing endpoints return HTTP 404 to the available token,
  so the UI is the only authoritative view.
- **Exact UI steps:**
  1. Open `https://github.com/settings/billing` → **Billing & plans** →
     **Payment information**; update or replace the failed payment method.
  2. In **Spending limit**, raise the limit enough for the intended matrix, or set a
     hard cap if cost control is preferred.
  3. Confirm Actions minutes are available for the private repository.
  4. Capture a screenshot of the billing page in the owner's private location as
     evidence (not in the repository).
  5. Re-run one cheap workflow from the Actions tab to prove dispatch. Diagnose with:
     `gh api repos/eliosmernica15/keel/actions/runs/<run-id>/jobs` and
     `gh api repos/eliosmernica15/keel/check-runs/<job-id>/annotations`.
- **Success evidence:** a fresh run has `runner_id != 0`, non-empty `steps`, real
  `duration_ms`, and the payment annotation no longer appears on any check run.
- **Rollback / recovery:** if the charge or spending limit was unintended, revert it
  in the same UI and set a lower cap; cancel queued matrix runs. No source change is
  involved. Until dispatch succeeds, treat all red CI statuses as infrastructure,
  not code regressions.
- **Workflow to run after:** `Python tests` (`.github/workflows/python-tests.yml`),
  then `Secret scan`, `Offline + license gates` and `Provider validation`. Dispatch
  example: `gh workflow run python-tests.yml --ref release/final-execution-2026-11-25`.

---

## 2. Free-tier provider credential + one bounded live validation

**Gate unlocked:** PR-06 `EXTERNAL_PENDING` → live-provider portion verified; PR-14
live-revoke sub-check (its local half is already verified).

- **Why (external):** every provider test at the final tree is offline with synthetic
  credentials; **zero** real requests were made. A credential cannot be minted in the
  repository, the chat or a test fixture (`FINAL-PROVIDER-EVIDENCE.md` §0/§2).
- **Required access:** owner-controlled free-tier account at one allowlisted provider:
  OpenRouter, Google or NVIDIA. Anthropic is opt-in only (licensing review OPEN-Q1)
  and an OpenAI-compatible endpoint has unknown billing; neither is allowed by the
  harness.
- **Cost / free status:** free tier only. The operator must re-confirm *current*
  free-tier terms within 30 days and record `no_paid_usage: true`. The harness makes
  **one** request, `max_output_tokens=16`, a 15-second wall-clock budget, no tools,
  no images, no retry, no fallback and no paid route.
- **Exact steps (all values stay outside the repository):**
  1. In the provider's own UI, create a fresh disposable key. Do not commit it,
     paste it, or write it to any evidence document.
  2. In one shell session only, export the matching variable:
     `KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY` or `KEEL_NVIDIA_API_KEY`.
     Use a fresh disposable state directory (`KEEL_STATE_DIR`) and clean HOME.
  3. Create a private JSON confirmation record *outside the repository* with keys
     `schema_version: 1`, `provider`, `model`, `operator`, `confirmed_at` (ISO date
     within 30 days), `free_tier_current: true`, `no_paid_usage: true`. For
     OpenRouter the model must carry the `:free` marker.
  4. From the repository root, with `PYTHONPATH=<promoted-tree>/keel/src`, run:
     `python scripts/verify_live_provider.py --allow-live-provider-check --confirm-free-tier-current --provider <google|openrouter|nvidia> --confirmation-file <private-path>/confirmation.json --results-json <private-path>/result.json`
  5. In the same disposable environment, verify the PR-14 revoke round-trip:
     save the key, call `settings_store.remove_provider_key(<name>)`, then confirm
     with the presence-only command `keel secrets has <KEEL_*_API_KEY>` that neither
     the environment nor the encrypted store still reports it, and repeat in a fresh
     interpreter. **Never use `keel secrets get`** — it reveals the value to stdout.
  6. In the provider UI, delete/rotate the disposable key immediately. Unset the
     environment variable and delete the private confirmation/result files.
- **Success evidence:** the harness records a successful bounded call with
  `provider`, `model`, `timestamp`, `commit`, result summary and quota context — no
  credential value, prompt text, response text, header or raw payload; the revoke
  probe reports the key absent after removal and after a fresh interpreter.
- **Rollback / recovery:** revoke the key in the provider UI at once; if any charge
  appears, dispute it with the provider. If a gate refuses (`blocked`, exit 2), stop
  and re-check the confirmation record — do not bypass the flags. A failed or
  ambiguous call is never written up as a PASS.
- **Workflow to run after:** `Provider validation`
  (`.github/workflows/provider-validation.yml`). With the key configured as a CI
  secret, the workflow still validates offline/truthful SKIP semantics; the live
  one-shot result is recorded by the harness, not auto-retried by CI.

---

## 3. macOS 15 Darwin runner + Seatbelt tests

**Gate unlocked:** PR-19 `BLOCKED` → genuine native macOS verification.

- **Why (external):** there is no Darwin host. All 14 macOS tests are platform-gated
  skips locally, and on `macos-26-arm64` a path-filtered `file-read*` rule makes
  `sandbox-exec` abort with exit `-6` (SIGABRT, empty stderr), so read isolation is
  `BLOCKED` (`FINAL-PLATFORM-EVIDENCE.md` §0/§5.3). This is a host defect, not a
  preference.
- **Required access:** owner with GitHub Actions on a working billing account, or an
  owner-provided self-hosted macOS **15** runner with Xcode command-line tools
  (`xcode-select --install`). A bare-metal/CI Linux runner is also needed to repeat
  the Landlock/seccomp conformance suite outside WSL2.
- **Cost / free status:** GitHub-hosted macOS minutes are billed at the higher
  private-plan multiplier; a self-hosted macOS 15 machine uses owner-owned hardware
  and no Actions minutes. No paid Apple developer identity is needed for the
  Seatbelt tests themselves (that is section 5).
- **Exact steps:**
  1. First complete section 1 (billing) — otherwise no runner is dispatched.
  2. In a clean checkout of the promoted branch on macOS 15, with
     `PYTHONPATH=<promoted-tree>/keel/src`, run:
     `python -m pytest -q -rs keel/tests/test_sandbox_macos.py keel/tests/sandbox_conformance.py`
     and `python -m pytest -q -rs keel/tests/test_os_sandbox.py`.
  3. Count skips separately; a skip is not a pass. Require zero SIGABRT and assert
     `capabilities()["read_isolation"]` is enforced, *or* explicitly accept the
     documented global-read fallback in a signed owner decision — never claim file
     confidentiality on macOS 26+.
  4. On the Linux runner (outside WSL2), repeat:
     `python3 -m pytest -q -rs keel/tests/test_sandbox_linux.py keel/tests/sandbox_conformance.py keel/tests/test_os_sandbox.py`.
  5. Build and validate DMG/ZIP (macOS) and AppImage/deb (Linux) on the native
     runners; combine with section 5 if Apple OS trust is required. Decide the
     disposition of the still-open PR #15 (merge as evidence or close as
     superseded).
- **Success evidence:** native pytest output with zero failures and enumerated
  skips; `sandbox-exec` no longer exits `-6` for path-filtered reads (or the
  fallback is accepted in writing); signed PKG/DMG validation status reported by
  `pkgutil --check-signature` and `spctl`.
- **Rollback / recovery:** if SIGABRT recurs, retain the exit `-6` probe as evidence,
  keep PR-19 `BLOCKED`, do not downgrade a skip to a pass, and remove the temporary
  runner after the run. An owner-accepted `read_isolation: BLOCKED` limitation keeps
  the gate honest without claiming confidentiality.
- **Workflow to run after:** `Python tests` (`python-tests.yml`) on `macos-15` /
  `macos-15-intel` and Linux labels, then `Build desktop installers`
  (`build-desktop.yml`), then `Verify installed packages (clean runners)`
  (`verify-install.yml`).

---

## 4. Windows Authenticode code signing

**Gate unlocked:** OS trust for Windows installers (part of PR-20; supplies trusted
artifacts for PR-17).

- **Why (external):** no code-signing certificate exists; electron-builder reports
  "no code signing certificate configured, signing is skipped", so SmartScreen
  warnings remain (`SIGNING-PREPARATION.md` §1).
- **Required access:** owner purchase/provision of an Authenticode code-signing
  certificate (PFX/P12 + password) and repository admin rights to add CI secrets.
- **Cost / free status:** paid certificate. SignPath Foundation is **not** eligible
  for proprietary software (`Keel_Master_Plan_v6.md` §4.3 D3). If declined, ship
  unsigned and keep release notes saying "unsigned" with SmartScreen instructions.
- **Exact steps:**
  1. Obtain the certificate in the owner's own environment. Export the PFX locally.
  2. Base64-encode it locally without printing the value:
     `[Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\private\cert.pfx'))`
     (capture directly into the GitHub UI field; do not save to the repository or
     a report).
  3. GitHub UI → repository → **Settings → Secrets and variables → Actions → New
     repository secret**: add `WINDOWS_SIGNING_CERTIFICATE_BASE64` and
     `WINDOWS_SIGNING_PASSWORD`. Never use a PR, issue or chat message as the
     transport.
  4. In the CI signing job, materialize the PFX into a temporary runner file,
     sign the installer with a RFC 3161 timestamp, then delete the temp file.
     Verification command: `signtool verify /pa /v <installer>`.
- **Success evidence:** `signtool verify /pa /v` exits 0 with a valid, timestamped
  signature; the release artifact is the signed `.exe`; release notes no longer
  label the Windows channel unsigned. No secret value appears in any log.
- **Rollback / recovery:** delete/rotate the two secrets in the GitHub UI and revoke
  the certificate with the CA if compromised; re-run `Signing readiness` to confirm
  `=MISSING`. If signing fails, the OS job must be **skipped, not failed**, and the
  release must stay honestly unsigned.
- **Workflow to run after:** `Signing readiness` (`signing-readiness.yml`), then
  `Build desktop installers` (`build-desktop.yml`), then `Verify installed packages
  (clean runners)` (`verify-install.yml`).

---

## 5. macOS Developer ID + notarization

**Gate unlocked:** macOS Gatekeeper trust (part of PR-20; supplies trusted DMG/PKG).

- **Why (external):** no Apple identity and no notarization exist; Gatekeeper
  warnings remain, and macOS native installers cannot be described as trusted.
- **Required access:** owner-controlled Apple Developer Program membership, a
  Developer ID Application certificate in the owner's Keychain, an app-specific
  password, the Apple Team ID, and repository admin rights to add CI secrets.
- **Cost / free status:** paid annual Apple Developer Program membership. There is
  no free trusted-notarization path for proprietary distribution. If declined, keep
  shipping unsigned with documented Gatekeeper steps.
- **Exact steps:**
  1. Enroll in the Apple Developer Program, create the **Developer ID Application**
     certificate, export the `.p12` locally, and base64-encode it locally (do not
     print or save the value into the repository).
  2. Create an app-specific password at `https://appleid.apple.com` and record the
     Team ID from the Apple Developer membership page.
  3. GitHub UI → **Settings → Secrets and variables → Actions → New repository
     secret**: add `MACOS_SIGNING_CERTIFICATE_BASE64`, `MACOS_SIGNING_PASSWORD`,
     `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`,
     `MACOS_NOTARIZATION_PASSWORD`. (The `CSC_LINK` / `APPLE_ID` aliases in older
     evidence are not required by `signing-readiness.yml`.)
  4. In the CI signing job on the macOS 15 runner:
     `codesign --force --options runtime --sign "Developer ID Application: <name> (<TEAMID>)" --deep <app>`;
     `xcrun notarytool submit <dmg> --apple-id <id> --team-id <team> --password <app-specific> --wait`;
     `xcrun stapler staple <dmg>`.
  5. Verify on the owner's machine / runner:
     `codesign --verify --deep --strict <dmg>`, `spctl -a -vv <dmg>`,
     `xcrun stapler validate <dmg>`, `pkgutil --check-signature <pkg>`.
- **Success evidence:** notarytool status `Accepted`, staple validation exit 0,
  `codesign --verify --deep --strict` exit 0, `spctl` accepted. No credential value
  in logs; only status lines.
- **Rollback / recovery:** revoke the Developer ID certificate / app-specific
  password if compromised and delete the five secrets in the GitHub UI; re-run
  `Signing readiness` to confirm `=MISSING`. Notarization can be repeated; if it
  cannot be completed, keep the macOS channel unsigned with Gatekeeper instructions.
- **Workflow to run after:** `Signing readiness`, `Build desktop installers`
  (PKG arm64 + x64), `Upgrade and rollback lifecycle (Windows)`'s macOS lifecycle
  job, then `Verify installed packages (clean runners)`.

---

## 6. CI secrets (all secret names, configured safely)

**Gate unlocked:** the governance/signing part of PR-20 and the live-provider part of
PR-06.

- **Why (external):** `GET .../actions/secrets` reported `total_count=0`;
  `signing-readiness.yml` reports `=MISSING` for every required name. Engineering
  must not write or guess secret values.
- **Required access:** repository admin; owner-provided key material/certificates
  from sections 2, 4 and 5.
- **Cost / free status:** configuring secret names is free on GitHub Free; the
  underlying credentials cost as stated in sections 2, 4 and 5.
- **Exact steps:**
  1. GitHub UI → **Settings → Secrets and variables → Actions → New repository
     secret**; type the name and paste the value **directly into the browser field**.
     Do not use chat, issues, PRs, evidence files, or a shell history as transport.
  2. Add only the names that correspond to an owner-provided identity:
     - `KEEL_RELEASE_SIGNING_KEY`, `KEEL_RELEASE_SIGNING_PUBLIC_KEY` (free Ed25519
       release-signing pair — generate outside the repository; never let the build
       generate a release pair);
     - `WINDOWS_SIGNING_CERTIFICATE_BASE64`, `WINDOWS_SIGNING_PASSWORD`;
     - `MACOS_SIGNING_CERTIFICATE_BASE64`, `MACOS_SIGNING_PASSWORD`,
       `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`,
       `MACOS_NOTARIZATION_PASSWORD`;
     - optional `LINUX_SIGNING_KEY_BASE64`, `LINUX_SIGNING_PASSWORD` and
       `KEEL_DOWNLOAD_MANIFEST_URL` (a public URL, not a secret value).
  3. For any local one-shot command, export the value in a single disposable shell
     with a clean HOME/`KEEL_STATE_DIR`, and `unset` it immediately afterwards.
  4. Dispatch `Signing readiness` and read only `=CONFIGURED` / `=MISSING` output.
- **Success evidence:** the readiness report shows `=CONFIGURED` for exactly the
  names supplied and `=MISSING` for the rest; no log, artifact or report contains a
  value; `verify-release-signatures` verifies real `.sig` files with the matching
  public key before publish.
- **Rollback / recovery:** delete or rotate each secret in the same UI; re-dispatch
  readiness to see `=MISSING` again. The release gate is fail-closed: missing keys
  produce `RELEASE SIGNING GATE FAILED`, never an unsigned "success".
- **Workflow to run after:** `Signing readiness` (`signing-readiness.yml`), then
  `Build desktop installers` (`build-desktop.yml`).

---

## 7. Clean-VM install / upgrade / rollback drill

**Gate unlocked:** PR-17 `EXTERNAL_PENDING` → `PASS_VERIFIED`; the deployment half
of PR-20.

- **Why (external):** the local disposable harness passes (`pass`, not
  `production_verified`) but uses an ephemeral Ed25519 key and a version-reporting
  stub; there is no VM tooling, no signed installer and no published manifest on
  this host (`FINAL-INSTALL-EVIDENCE.md` §1).
- **Required access:** owner-provided disposable clean VM, distinct from the build
  host, with rights to install signed artifacts and restore a snapshot; the Ed25519
  public key from section 6; a first-party binaries-only HTTPS download endpoint.
- **Cost / free status:** a local VM or free-tier cloud VM can be used; no paid
  service is required for the drill itself. The signing identity (section 6) is the
  only credential needed.
- **Exact steps:**
  1. Take and record a VM snapshot **before** any install.
  2. Set `KEEL_DOWNLOAD_MANIFEST_URL` to a first-party, public, binaries-only HTTPS
     endpoint. The current default points at the private source repository and must
     never be published as a distribution URL.
  3. Install version `0.1.0` from the signed channel; verify with
     `python -m keel.release verify --manifest release/download.json --public-key <PUBLIC_KEY_PEM>`
     and `python -m keel.release integrity --dist dist --artifacts release`.
  4. Perform the signed `0.1.0 → 0.1.1` upgrade using the signed loopback manifest;
     confirm SQLite state is preserved and the service restarts cleanly.
  5. Perform the rollback drill by restoring the pre-upgrade VM snapshot. Migrations
     are **forward-only** — do not attempt a down-migration; use the encrypted
     backup restore path if a snapshot is unavailable.
  6. Retain the verification log in the owner's private location. Never include the
     private key or its path in that log.
- **Success evidence:** signed upgrade completes with signature verification exit 0,
  database rows preserved, rollback restores the prior state, and the log shows the
  exact promoted SHA/branch and both outcomes.
- **Rollback / recovery:** restore the VM snapshot immediately; if state was written
  to a shared store, use the encrypted backup/restore CLI (`python -m keel.backups`)
  with a verified manifest. A failed drill is recorded as a failure, never as a
  partial pass.
- **Workflow to run after:** `Build desktop installers` (`build-desktop.yml`, to
  produce the signed artifacts), then `Upgrade and rollback lifecycle (Windows)`
  (`lifecycle.yml`, `workflow_dispatch` — its `trust-gate` refuses fork/PR/failed
  runs), then `Verify installed packages (clean runners)` (`verify-install.yml`).

---

## 8. Release authorization (tag, gate and first publication)

**Gate unlocked:** the final governance part of PR-20 and any `production_verified`
claim.

- **Why (external):** the release-authorization gate requires a tag, branch
  containment, a trusted actor, five evidence files and an explicit approval marker.
  The current marker is deliberately inert:
  `RELEASE-APPROVED: NOT-APPROVED by @nobody` (`FINAL-GOVERNANCE-EVIDENCE.md` §2).
  No push, tag or publish has been performed.
- **Required access:** repository admin, tag-push rights and an explicit owner
  decision on the GitHub Free plan limitation (branch protection / required checks
  return 403/404/422 on this private free plan).
- **Cost / free status:** the gate itself is free and runs on GitHub Actions once
  section 1 is resolved. The plan-upgrade alternative (for remote branch
  protection) is a paid decision; the documented-acceptance alternative is free.
- **Exact steps:**
  1. Decide: upgrade the plan to enable branch protection/required status checks
     and enforce 2FA at `https://github.com/settings/security`, **or** record a
     signed, documented acceptance of the limitation (A4).
  2. Preflight the gate without side effects: dispatch
     `Release authorization gate` (`release-authorization.yml`, `workflow_dispatch`)
     against the promoted commit; with the inert marker it must report
     `NOT AUTHORIZED` (all negative cases are expected).
  3. When the owner is ready, replace **only** the inert marker line in
     `FINAL-GOVERNANCE-EVIDENCE.md` with
     `RELEASE-APPROVED: <exact-semver-tag> by @<allowlisted-owner>` (for example
     `RELEASE-APPROVED: v0.1.1 by @eliosmernica15`), commit it to `main`, then create
     and push the matching annotated tag:
     `git tag -a v0.1.1 <tagged-commit> -m "release v0.1.1"`,
     `git push origin main`, `git push origin v0.1.1`.
  4. Verify the tag resolves: `gh api repos/eliosmernica15/keel/git/ref/tags/v0.1.1`.
     Pushing a `v*` tag triggers `Build desktop installers`, whose
     `release-authorization` job gates both `verify-release-signatures` and
     `publish`.
  5. Authorize publication only after: signature verification (section 6), the
     clean-VM drill (section 7) and the governance decision (step 1) are recorded.
     `keel/site/download.json` may change from `url: null` / `available: false` /
     `verified: false` only as a result of this authorized publication.
- **Success evidence:** the gate job exits 0 with `RESULT: AUTHORIZED`,
  `verify-release-signatures` and `publish` execute (not skipped), every artifact
  has a matching `.sig`, and the published manifest records real SHA-256 values.
- **Rollback / recovery:** before publication, delete the tag with
  `git push --delete origin v0.1.1` and revert the marker commit — the gate then
  fails closed again. After publication, never rewrite a public tag; issue a new
  patch release with a fresh marker and tag. Remove the marker to invalidate any
  further release from that commit.
- **Workflow to run after:** `Release authorization gate`
  (`release-authorization.yml`), then `Build desktop installers`
  (`build-desktop.yml`) on the tag push, then `Verify installed packages (clean
  runners)` (`verify-install.yml`).

---

## Ordering summary

| # | Action | Unlocks | Workflow to re-run |
| --- | --- | --- | --- |
| 1 | Billing / spending limit | all GitHub Actions evidence | `Python tests` + `Secret scan` + `Offline + license gates` + `Provider validation` |
| 2 | Free-tier credential + one bounded call | PR-06, PR-14 sub-check | `Provider validation` |
| 3 | macOS 15 runner + Seatbelt | PR-19 | `Python tests`, `Build desktop installers`, `Verify installed packages` |
| 4 | Windows Authenticode | Windows OS trust | `Signing readiness`, `Build desktop installers`, `Verify installed packages` |
| 5 | Developer ID + notarization | macOS OS trust | `Signing readiness`, `Build desktop installers`, lifecycle macOS job, `Verify installed packages` |
| 6 | CI secrets | PR-20 signing/governance, PR-06 CI side | `Signing readiness`, `Build desktop installers` |
| 7 | Clean-VM install/upgrade/rollback | PR-17 | `Build desktop installers`, `Upgrade and rollback lifecycle (Windows)`, `Verify installed packages` |
| 8 | Release authorization | PR-20, any deployment | `Release authorization gate`, `Build desktop installers`, `Verify installed packages` |

**Nothing here is a substitute for a fresh independent acceptance review at the SHA
actually promoted.** Until these actions are performed and that review is written,
`PASS_VERIFIED` remains 0 and production deployment remains unauthorized.
