# FINAL OWNER ACTIONS — the only genuine external requirements

> **Scope:** final execution branch `release/final-execution-2026-11-25` (HEAD
> `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` at reconciliation; resolve exactly with
> `git rev-parse HEAD`), version `0.1.1` / tag `v0.1.1`.
> This file lists **only** actions that engineering cannot perform: owner-controlled
> credentials, an owner-provided Darwin host, an owner signing identity, an owner plan
> entitlement, and owner deployment authorization. No engineering follow-up is listed
> here; none of these actions has been performed in this workstream. No push, tag,
> secret write, signing or publish occurred.

Each action names the exact gate(s) it unlocks. Gate IDs and classifications are from
`FINAL-PRODUCTION-READINESS-MATRIX.md` §C/§E. **Exact, safe, step-by-step instructions
for every action — including required access, cost/free status, success evidence,
rollback/recovery, and which workflow to run afterwards — are in
`docs/FINAL-OWNER-ACTION-RUNBOOK.md`.** Never paste a secret value into chat, logs,
files, issues or PRs; configure values only in the owner's provider account or the
GitHub Secrets UI.

---

## A1 — Provider credentials (unlocks PR-06; completes the live part of PR-14)

**Why external:** every provider test at the final tree is offline with synthetic
credentials; zero real requests were made. A credential cannot be minted inside the
repository, the chat or a test fixture.

**Exact steps**

1. Generate a disposable, free-tier provider key outside the repository and outside
   chat, in an owner-controlled account. Do not commit it, paste it, or write it to any
   evidence document.
2. Configure it as the matching `KEEL_*_API_KEY` variable in the owner-controlled CI
   environment or host environment for the run only; use a fresh disposable state
   directory (`KEEL_STATE_DIR`) and a clean `HOME`/`USERPROFILE`.
3. Re-confirm current free-tier terms (≤30 days old) in a private confirmation
   record. From the repository root, with `PYTHONPATH=<final-tree>/keel/src`, run the
   one-shot harness with explicit opt-in:
   `python scripts/verify_live_provider.py --allow-live-provider-check --confirm-free-tier-current --provider <google|openrouter|nvidia> --confirmation-file <private-path> --results-json <private-path>`.
   It makes at most one bounded request (16 output tokens, 15 s, no retry/fallback)
   and records only provider, model, timestamp, commit, result summary and quota
   context — never the key, prompt, response text or headers.
4. In the same disposable environment, exercise the live revoke round-trip used by
   PR-14 (save key → `settings_store.remove_provider_key` → confirm env and encrypted
   store cleared with the presence-only `keel secrets has <KEY>` → confirm no re-apply
   after a fresh interpreter). Never use `keel secrets get`, which reveals values.
5. Remove and rotate the disposable credential immediately afterwards; delete the
   private confirmation/result files. See runbook §2 for all steps and follow-up
   workflow.

**Unlocks:** PR-06 `EXTERNAL_PENDING` → `PASS_VERIFIED` for the live-provider claim;
PR-14's live revoke sub-check (its local half is already verified). Does **not** unlock
PR-20 by itself — PR-20 also needs A2/A4/A5.

---

## A2 — Signing identity (unlocks PR-20 signing; supplies the signed installer required by PR-17)

**Why external:** the release code is complete and fails closed — `signing.py`
(`SigningGateError`, `require_signed_enabled`, `verify_signed_release`), `publish.py`
(real publish always gated), `build-desktop.yml` (`verify-release-signatures` job) and
10 + 36 signing tests all exist at the final tree. No key material exists, so no
artifact can be signed. The gate is deliberately not downgraded to a pass on code
strength alone.

**Exact steps**

1. Generate an Ed25519 keypair outside the repository, the CI runner and chat. Never
   let the build generate a release keypair; `generate_keypair()` is for ephemeral
   tests only.
2. Store the PKCS#8 **private** key as CI secret `KEEL_RELEASE_SIGNING_KEY` and the
   matching SubjectPublicKeyInfo **public** key as `KEEL_RELEASE_SIGNING_PUBLIC_KEY`.
   Never print either value; `signing-readiness.yml` must continue to report only
   `=CONFIGURED` / `=MISSING`.
3. Ensure the CI `sign` job passes `--signing-key` to `python -m keel.release build`
   and that `publish` verifies with `--public-key` / `KEEL_REQUIRE_SIGNED=1`; the
   `verify-release-signatures` job must upload every `*.sig` and the signed
   `RELEASE-MANIFEST.json` before publish.
4. Decide separately whether to purchase OS-level trust: Windows Authenticode
   (`WINDOWS_SIGNING_CERTIFICATE_BASE64`, `WINDOWS_SIGNING_PASSWORD`), macOS Developer
   ID + notarization (`MACOS_SIGNING_CERTIFICATE_BASE64`, `MACOS_SIGNING_PASSWORD`,
   `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`,
   `MACOS_NOTARIZATION_PASSWORD`), and optional Linux provenance
   (`LINUX_SIGNING_KEY_BASE64`, `LINUX_SIGNING_PASSWORD`). If declined, release notes
   must keep saying "unsigned" and document SmartScreen/Gatekeeper steps.
   SignPath Foundation is not eligible for proprietary software
   (`Keel_Master_Plan_v6.md` §4.3 D3).
5. Verify before publication with
   `python -m keel.release verify --manifest release/download.json --public-key <PUBLIC_KEY_PEM>`
   and `python -m keel.release integrity --dist dist --artifacts release`.

**Unlocks:** the signing half of PR-20 `OWNR`; the signed installer prerequisite for the
PR-17 clean-VM run; OS trust (SmartScreen/Gatekeeper) if step 4 is authorized.
Authenticode, Developer ID + notarization and CI secret entry are specified step by
step in runbook §4–§6.

---

## A3 — Darwin host and native runners (unlocks PR-19)

**Why external:** there is no Darwin machine, VM or reachable macOS runner in the
environment. `STAB-PLATFORM-EVIDENCE.md` records all 14 macOS tests as platform-gated
skips and a documented read-isolation `BLOCKED` fallback on macOS 26
(`sandbox-exec` SIGABRT). This is a hard technical blocker, not a preference.

**Exact steps**

1. Provide a native macOS **15** runner (not 26+) with Xcode command-line tools, and a
   bare-metal or CI Linux runner in addition to WSL2.
2. On the macOS runner, re-run `keel/tests/test_sandbox_macos.py` and
   `test_os_sandbox.py` against the exact final tree with
   `PYTHONPATH=<final-tree>/keel/src`, including the read-isolation boundary that
   SIGABRTs on 26; count skips separately and do not treat them as passes.
3. On the Linux runner, repeat the Landlock/seccomp conformance suite outside WSL2.
4. Build and validate DMG/ZIP (macOS) and AppImage/deb (Linux) on those native
   runners; combine with A2 for Apple Developer ID/notarization if OS trust is desired.

**Unlocks:** PR-19 `BLCK` → verified native platform status. Windows (31 passed /
6 disclosed skips / 0 failed) and Linux-in-WSL2 (16/16 + 9/1) are already verified and
do not need repeating for the local claim. Runbook §3 gives the exact macOS 15
Seatbelt commands, skip accounting, SIGABRT rollback and follow-up workflows.

---

## A4 — GitHub plan limitation (governance part of PR-20)

**Why external:** the repository is owner-controlled and private on GitHub Free.
Branch protection / required checks and 2FA enforcement return 403/404/422 on that
plan. Engineering cannot upgrade the plan or change repository governance.

**Exact steps**

1. Owner decides: upgrade the plan to enable branch protection/required status checks
   and enforce 2FA, **or** record a signed, documented acceptance of the limitation.
2. If upgrading, set required checks to the final-tree gates already green locally:
   registry consistency, `verify_backend_operation.py --strict` (421/421),
   dependency-graph freshness, license gate, version sync, workflow YAML parse and the
   42/42 full-SHA `uses:` pin check.
3. Confirm the **42** external full-SHA-pinned action refs across **9 workflow files**
   (plus 1 local reusable path) are effective on the default branch after the
   owner-authorized merge (the local final execution tree has 42/42; the live default
   branch may still lag until that merge happens). Older 40/8-workflow counts are
   historical.

**Unlocks:** the governance portion of PR-20 `OWNR`. A1/A2/A5 are still required.

---

## A5 — Deployment authorization (unlocks PR-17 clean-VM and any production deployment)

**Why external:** no push, tag, release, deploy or publication has been performed in
this workstream. A disposable VM, a first-party binaries-only download endpoint and
permission to publish are owner-controlled.

**Exact steps**

1. Approve version tag `v0.1.1` and authorize merging/pushing the reviewed final tree.
2. Provide a disposable clean VM (distinct from the build host) with A2's signing key
   available, then perform the signed `0.1.0 → 0.1.1` upgrade and rollback drill at the
   exact final SHA; retain the verification log, not the key.
3. Configure `KEEL_DOWNLOAD_MANIFEST_URL` to a first-party, public, binaries-only HTTPS
   endpoint. The current default points at the private source repository and must not
   be published as a distribution URL.
4. Authorize the first publication only after the signature verification in A2, the
   clean-VM drill in step 2 and the governance decision in A4 are recorded.
5. Name the deployment target (if any) and authorize deployment explicitly. Until
   then the deployed-instance count remains 0 and `PASS_VERIFIED` remains 0.

**Unlocks:** PR-17 `EXTP` → `PASS_VERIFIED`; the deployment half of PR-20; any
`production_verified` classification. `keel/site/download.json` currently has
`url: null`, `available: false`, `verified: false` for every channel — these values
must only change as a result of this authorized publication. Runbook §7 (clean-VM
drill) and §8 (tag, approval marker, release authorization) give the exact steps,
rollback and follow-up workflows.

---

## Explicitly excluded from this file

These are engineering/product decisions, **not** external owner requirements; they are
tracked in the readiness matrix and acceptance notes and must not be added here:

- M-2: forwarding real permission tiers on CLI/TUI callers of `capabilities.invoke`.
- M-4: deciding whether to wire `backend_events` / `backend_observability` into the
  runtime lifecycle (PR-10/PR-15 remain documented library-only).
- A committed pytest regression for the license-gate fail-closed fix (`C10`).
- A narrow `.gitleaks.toml` allowlist for the historical synthetic finding.
- Approval of alert thresholds / an observability exporter (PR-18 scope note).
- The forward-only migration policy waiver decision (PR-08 is already honest).

No credential value, signing identity, runner, plan entitlement or authorization has
been supplied by this agent.
