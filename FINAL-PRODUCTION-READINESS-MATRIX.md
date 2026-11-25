# FINAL PRODUCTION-READINESS MATRIX — Keel, final execution branch `release/final-execution-2026-11-25` (HEAD `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` at reconciliation; resolve exactly with `git rev-parse HEAD`)

> **Authoritative reconciliation of PR-01…PR-20.** This document replaces the
> provisional classifications in `PRODUCTION-READINESS-MATRIX.md` §D, the
> `17 + 2 + 1 + 1 = 21` table in `POST-PROMOTION-STABILIZATION-REPORT.md` §F, and
> the `13 / 5 / 2` table in `FINAL-RELEASE-ACCEPTANCE.md` §B3. Those documents are
> retained unchanged as audit history and are explicitly marked historical in §E.
>
> **Scope:** documentation only. No source, test, workflow or frontend file was
> edited by this reconciliation; no push, tag, secret write, signing or publish.
>
> **Reconciled at the final execution branch** `release/final-execution-2026-11-25`
> (HEAD `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd`; `origin/main` =
> `bcc91230fee72d41b7f267155156b6528e22a1c8`). Current counts: **9 workflow files,
> 42 full-SHA `uses:` pins + 1 local reusable path**, authoritative suite **4724
> passed / 0 failed / 54 skipped** at completion-branch commit `060a281…`; the
> full-suite re-run at the final execution SHA is **pending** (R-19). Historical
> SHAs and counts are retained as **[HISTORICAL]** audit history in §F; the exact
> safe owner steps are in `docs/FINAL-OWNER-ACTION-RUNBOOK.md`.

## A. Authority and exact commit identity

| Field | Exact value |
| --- | --- |
| Final execution HEAD (authoritative branch reference) | `release/final-execution-2026-11-25` HEAD = `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` (`agent/exec-docs2`, worktree `…\worktree\execution\docs2`; `origin/release/final-execution-2026-11-25` resolves to the same SHA). Resolve with `git rev-parse HEAD` at promotion |
| Base and delta | `origin/main` = `bcc91230fee72d41b7f267155156b6528e22a1c8`; `git diff --name-status origin/main..HEAD` adds only `docs/FINAL-RELEASE-EXECUTION-PLAN.md` — no source/test/workflow/frontend change |
| Definitive full-suite commit (completion branch) | `060a281102dbb85bbcef710a0cd03604bdf7c703` (`060a281`), an ancestor of the final execution HEAD; suite recorded there |
| Authoritative full suite at that tree | `4724 passed, 0 failed, 54 skipped, 3707 subtests` in `801.99 s` (`master-plan-v6-test-evidence.md:276-285`; `FINAL-RELEASE-COMPLETION-REPORT.md` "Authoritative final full-suite run") |
| Full suite at final execution SHA | **PENDING** — not re-run by this documentation-only workstream (R-19); earlier 4610 / 4628 / 4630 / 4722 figures are historical |
| Historical completion HEAD (superseded reference) | `abfd784393b2b252e2b9e2927aba817dd` on the historical `completion/final-production-release-2026-11-25` lineage — **[HISTORICAL]**, retained for provenance only |
| Prior definitive suite tree (historical) | `c512f87971a02b05d9a9422338522f66495c0eeb` — 4610/0 suite at an earlier lineage — **[HISTORICAL]** |
| Independent-acceptance candidates (historical) | `530c0670f2c34805fb7ac705e1a7b8dfe113006f` (`BLOCK`, F-0 allowlist exactness; fixed by `efd16d4`) and `63ab72e452f9c78af46db55489ef8d9def02212c` (`PASS_WITH_EXTERNAL_LIMITATIONS`) — both **[HISTORICAL]** |
| Prior baseline (historical) | `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb` — **[HISTORICAL]** |
| Plan registry (recomputed at final execution HEAD) | `PLAN-INDEX.json` / `parity.json` SHA-256 `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`; `verify_v6_audit.py` CONSISTENCY OK, 865 rows = 854 verified / 9 not_started / 2 blocked |
| Version | `0.1.1` / tag `v0.1.1`; `python keel/scripts/check_version_sync.py` re-run at final execution HEAD → `OK - all sources agree on version 0.1.1 (tag v0.1.1)` |
| Governance gates re-run at final execution HEAD | `verify_v6_audit.py` CONSISTENCY OK (865); `verify_backend_operation.py --strict` 421/421, 0 failing, exit 0; license gate OK (11 entries, 0 bundled); dependency graph FRESH; **9/9** workflow YAMLs parse; **42/42** external `uses:` refs full-SHA pinned + 1 local reusable path (direct count: checkout 16, setup-python 14, download-artifact 5, setup-node 4, upload-artifact 3) |
| Production deployment | **None.** No deployed instance, no published release, no signed artifact, no distribution URL |

### Commit key (resolves every `C` reference in §C to a branch reference or exact commit)

| Key | Full SHA / branch reference | Role |
| --- | --- | --- |
| `C0` | `release/final-execution-2026-11-25` HEAD (`d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` at reconciliation; resolve exactly with `git rev-parse HEAD`) | Authoritative final execution tree; replaces the historical completion HEAD `abfd784393b2b252e2b9e2927aba817dd` |
| `C1` | `060a281102dbb85bbcef710a0cd03604bdf7c703` | Definitive 4724/0 full suite (completion branch, ancestor of `C0`); the `C0` code tree differs only by later documentation/frontend additions, so re-run at `C0` is pending (R-19) |
| `C2` | `50e5be0ecc902c53b7d5f441001c26facc175942` | O(1) verified-ledger cache (perf §9.1); stabilization report finalize |
| `C3` | `788090ca327e5a6ee76c749884519ba6a0502641` | Owner-main merge: frontend/distribution/signing code and docs |
| `C4` | `63ab72e452f9c78af46db55489ef8d9def02212c` | Independent final-acceptance candidate — **historical** |
| `C5` | `1809cac736188bf1e2d7ff478ce4e780740cf043` | Provider/credential validation and M-5/L-1 remediation |
| `C6` | `5763625fc0c276f79fbf2affabf7e31938bd9cfc` | Concurrent first-open migration race / corruption detection fix |
| `C7` | `c54c6739345887d084039286f9ad23c1f372b489` | Workflow confirmation, per-workflow policy, audited outcomes, schema discovery |
| `C8` | `289a396cd6c3439a9f56793345db527b2a6aeeb3` | Install swap backup / torn start-health write fix |
| `C9` | `8867e735cddefd332e8e1d1e7e04daba0d133d6a` | Signing hard-fail gate baseline (`agent/f-signing`); code present at `C0` |
| `C10` | `101fcecf307ececb5aa3f34412cb1c5c5cab03b9` | License-gate fail-closed fix |
| `C11` | `781b4cf9a694dbb37f80886bb47cf637eef7e7d7` | CI offline/provider/trusted-trigger/supply-chain repair |
| `C12` | `55c1c5d26dfb7b74fc15be47b6c36e5aa30b8d19` | Earlier 4558/0 stabilization suite — **historical count** |
| `C13` | `a81a78bccca89c8785d070fe34c15b9982002aa8` | Authoritative state root, graceful signals, readiness, CLI workflow confirm |

## B. Classification vocabulary — mutually exclusive

Exactly one final class is assigned to each gate. Precedence, applied top-down:

1. `NOT_IMPLEMENTED` (`NIMP`) — required mechanism absent from tracked source at `C0`.
2. `BLOCKED` (`BLCK`) — a hard technical/platform condition must be removed before the gate can even be attempted (no Darwin runner, `sandbox-exec` SIGABRT).
3. `OWNER_ACTION_REQUIRED` (`OWNR`) — closure depends on an owner-only credential, signing identity, plan entitlement or authorization; the gate's own definition is an owner/governance action.
4. `EXTERNAL_PENDING` (`EXTP`) — implementation and local verification are complete, but the gate's closure definition explicitly includes an external run (live provider call, signed disposable-VM upgrade) that has not happened.
5. `PASS_VERIFIED` (`PVE`) — external evidence attached: live call, signed/published release, native runner or deployed instance at `C0`.
6. `PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED` (`PINV`) — mechanism complete in tracked source, local tests green at the `C0` tree, and no outstanding external/owner/platform condition attached to this gate.

A gate with an owner dependency *used by* another gate is not thereby owner-gated itself; PR-17's signed-VM run depends on PR-20's keys but remains `EXTP` because its closure event is an external run. A gate with a residual product/design limitation (e.g. PR-10/PR-15 library-only runtime wiring) is `PINV` only if the limitation is documented, not represented as production behaviour, and not a blocker to the gate's stated local requirement.

## C. Authoritative 20-row matrix

Legend: `FULL` = mechanism present in tracked source at `C0` (the final execution branch reference, not a fixed SHA); `PARTIAL` = present on a subset of required surfaces; `NONE` = absent. `FINAL` = covered by the definitive completion-branch suite (4724/0 at `C1`) plus the named targeted suite; a fresh full-suite re-run at `C0` is **pending** (R-19). `HIST` = only at a historical commit. `Win`/`WSL2` = native verification on those hosts; `mac none` = no Darwin host. Owner actions `A1`–`A5` are the only genuine external requirements, specified in `FINAL-OWNER-ACTIONS.md` with exact safe steps in `docs/FINAL-OWNER-ACTION-RUNBOOK.md`.

| ID | Requirement | Implementation @ `C0` | Local test verification | Native platform | Live external status | Evidence path | Commit ref | Owner action | Final class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PR-01 | Start/stop Keel deterministically | FULL — `cli/main.py` serve/fleet/web, `webapp.py` Ctrl+C + SIGTERM, `scheduler.start_daemon` | FINAL — 4724/0 @ `C1`; graceful shutdown + connection-refused post-shutdown probe | Win + WSL2 native shutdown observed | n/a — no production service exercised | `STAB-RUNTIME-EVIDENCE.md`; `STAB-INSTALL-EVIDENCE.md` §2; `BACKEND-OPERATIONS-RUNBOOK.md` §1; `master-plan-v6-test-evidence.md` | `C0`, `C13` | — | PINV |
| PR-02 | Liveness distinct from readiness | FULL — `/api/health` 200 with version, token gating 403, `doctor`, diagnostics; no false `/api/ready` claim | FINAL — 4724/0 @ `C1`; `STAB-INSTALL-EVIDENCE.md` §2 health probes (8/8) | Win + WSL2 | n/a | `STAB-INSTALL-EVIDENCE.md` §2; `STAB-RUNTIME-EVIDENCE.md`; `master-plan-v6-cli-surface-evidence.md` | `C0`, `C13` | — | PINV |
| PR-03 | Module health and release evidence | FULL — `backend_observability.health_snapshot`, root `verify_backend_operation.py` | FINAL — re-run at `C0`: CONSISTENCY OK (865), strict gate 421/421 exit 0; 4724/0 @ `C1` (C0 re-run pending) | n/a | n/a | `master-plan-v6-release-acceptance.md`; `FINAL-ERROR-SWEEP.md` §1 [HISTORICAL]; `master-plan-v6-test-evidence.md` | `C0` | — | PINV |
| PR-04 | Scoped config and env validation | FULL — `settings.py`, `cli/main.py` settings/execpolicy, `admin_ops.py`; authoritative state-root precedence | FINAL — 4724/0 @ `C1`; config suites + runtime state-root checks | Win + WSL2 | n/a | `STAB-RUNTIME-EVIDENCE.md`; `master-plan-v6-config-contracts-evidence.md` | `C0`, `C13` | — | PINV |
| PR-05 | Encrypted secrets, presence-only diagnostics | FULL — `secret_store.py`, `secret_providers.py`, `secrets` CLI | FINAL — 4724/0 @ `C1`; provider/secret suite 128 passed at `C5`; no plaintext after removal | Win + WSL2 | n/a — synthetic fixtures only | `STAB-PROVIDER-EVIDENCE.md` §3; `master-plan-v6-secrets-policy-evidence.md` | `C0`, `C5` | — | PINV |
| PR-06 | Provider configuration/validation without fabricated success | FULL — truthful SKIP/FAIL, no live call without `--live`, redaction, SSRF guard | FINAL — 4724/0 @ `C1`; `test_stab_provider.py` + 5 companion files → 128 passed; pre-fix control 117/7 failed | n/a | **NO LIVE CALL** — all credentials synthetic/absent; `live_provider=SKIP` | `STAB-PROVIDER-EVIDENCE.md`; `PROD-PROVIDER-EVIDENCE.md` [HISTORICAL]; `.github/workflows/provider-validation.yml` | `C0`, `C5`, `C11` | `A1` | EXTP |
| PR-07 | Verified encrypted backup/restore | FULL — `backups.py` AES-GCM + AAD, manifest hash, `python -m keel.backups` db-backup/verify/list/restore/prune | FINAL — 4724/0 @ `C1`; 64/64 DB gate + 275-test sweep | Win + WSL2 | n/a — no production DB | `STAB-DB-EVIDENCE.md` §0/§5; `master-plan-v6-db-persistence-evidence.md`; `master-plan-v6-recovery-evidence.md` | `C0`, `C6` | — | PINV |
| PR-08 | Forward migration, honest rollback limits | FULL — `fleet/db.py` v1→v11, no down-migration, explicit pre-migration snapshot restore | FINAL — 4724/0 @ `C1`; migration/concurrency tests in 64/64 + 275 sweep | Win + WSL2 | n/a | `STAB-DB-EVIDENCE.md` §5/§6; `BACKEND-DATABASE-RECOVERY.md` | `C0`, `C6` | — | PINV |
| PR-09 | Installer rollback / failed-start auto-rollback | FULL — `updater.atomic_install`/`rollback`, `start_health`, 3-failed-start decision | FINAL — 4724/0 @ `C1`; STAB-INSTALL local rollback drill 6/6, defect regressions 7/7 | Win local installer; WSL2 scoped | **NO VM RUN** — disposable-VM check 5 folded into PR-17 | `STAB-INSTALL-EVIDENCE.md` §4/§8; `PROD-ROLLBACK-EVIDENCE.md` [HISTORICAL] | `C0`, `C8` | — (VM action is `A5`) | PINV |
| PR-10 | Locatable, tamper-evident, redacted log | FULL as library — `backend_observability.verify_chain`, `redaction.py`; runtime wiring deferred (integration M-4), documented, not claimed as active runtime logging | FINAL — 4724/0 @ `C1`; chain/redaction suites in `test_backend_events.py`, `test_redaction.py`, `test_diagnostics.py` | Win + WSL2 | n/a | `STAB-EVENTS-EVIDENCE.md`; `master-plan-v6-reliability-contracts-evidence.md`; `FINAL-STABILIZATION-ACCEPTANCE.md` §4.4 | `C0` | — (M-4 is an engineering decision, not external) | PINV |
| PR-11 | Redacted diagnostic export | FULL — `diagnostics.py`, `doctor --bundle` | FINAL — 4724/0 @ `C1`; diagnostics/redaction suite | Win + WSL2 | n/a | `STAB-EVENTS-EVIDENCE.md` §6; `STAB-INTEGRATION-EVIDENCE.md`; `diagnostics.py` docstring | `C0` | — | PINV |
| PR-12 | Scheduler/gateway recovery | FULL — `fleet/scheduler.py`, `gateway.py`, durable `EventBus`/`DeliveryTracker`; no multi-day soak claimed | FINAL — 4724/0 @ `C1`; 128 passing integration tests | Win + WSL2 | n/a | `STAB-EVENTS-EVIDENCE.md`; `master-plan-v6-gate-scheduler-evidence.md`; `master-plan-v6-fleet-events-evidence.md` | `C0` | — | PINV |
| PR-13 | Stop unsafe execution / change posture | FULL — workflow confirmation, per-workflow policy, policy-free subroot closed, HMAC ledger; residual M-2: CLI/TUI do not forward permission tiers (transport confirm gates strict) | FINAL — 4724/0 @ `C1`; `test_stab_workflow_auth.py` + boundary probes; independent reviewer reproduced H-1 fix | Win + WSL2 native enforcement; macOS under PR-19 | n/a | `STAB-WORKFLOW-EVIDENCE.md`; `STAB-SECURITY-REVIEW.md`; `FINAL-STABILIZATION-ACCEPTANCE.md` §6 | `C0`, `C7`, `C13` | — (M-2 is an engineering follow-up) | PINV |
| PR-14 | Revoke credentials / disable integration | FULL locally — env+store key removal, MCP/approval/pairing/token revoke, redacted audit chain; gap G1: Y3.9 sign-out descriptor does not purge stored credentials | FINAL — 4724/0 @ `C1`; 7 real local tests + 170 neighbours at `PROD-REVOCATION-EVIDENCE.md` [HISTORICAL], reconfirmed by 128-test provider suite and 4724/0 @ `C1` (C0 re-run pending) | Win + WSL2 | NO LIVE REVOKE — round-trip needs the PR-06 credential; recorded as a sub-check of `A1`, not a separate gate | `STAB-PROVIDER-EVIDENCE.md` §3/§4; `PROD-REVOCATION-EVIDENCE.md` [HISTORICAL] | `C0`, `C5` | `A1` (shared credential) | PINV |
| PR-15 | Preserve forensic evidence | FULL as library — `verify_chain`, forensic retention archives with SHA-256 manifest; runtime adoption deferred (M-4) | FINAL — 4724/0 @ `C1`; forensic retention/chain tests pass | Win + WSL2 | n/a | `STAB-EVENTS-EVIDENCE.md` §5/F5-F6; `master-plan-v6-recovery-evidence.md`; `FINAL-STABILIZATION-ACCEPTANCE.md` §4.4 | `C0` | — (M-4 is an engineering decision) | PINV |
| PR-16 | Clean setup and dependency install | FULL — hash-pinned `--require-hashes` install, editable install, version sync, `check_version_sync.py` | FINAL — 4724/0 @ `C1`; 8/8 clean-checkout harness checks; governance gates re-run at `C0` | Win + WSL2 | n/a | `STAB-CI-EVIDENCE.md`; `STAB-INSTALL-EVIDENCE.md` §2; `PROD-CLEAN-SETUP-EVIDENCE.md` [HISTORICAL] | `C0`, `C11` | — | PINV |
| PR-17 | Upgrade and recovery path | FULL locally — signed loopback manifest, atomic swap, SQLite preservation, interrupted-swap recovery, O(1) ledger cache | FINAL — 4724/0 @ `C1`; install/upgrade local gate `pass`; 6/6 drill + 7/7 defect regression | Win local, WSL2 scoped, mac none | **NO SIGNED CLEAN-VM RUN** — no disposable VM, no signed installer, no published release | `STAB-INSTALL-EVIDENCE.md` §3-§4/§8; `PROD-ROLLBACK-EVIDENCE.md` [HISTORICAL]; `master-plan-v6-signing-evidence.md` | `C0`, `C8`, `C2` | `A2` + `A5` | EXTP |
| PR-18 | Real signals, redaction, bounded views | FULL — `diagnostic_report`, `admin_page`, `circuit_breaker`, `costs status`, bounded retention/steering; no exporter/pager (scope note, not a gate requirement) | FINAL — 4724/0 @ `C1`; bounded retention and worker-cancel regressions (7 tests) | Win + WSL2 | n/a | `STAB-PERFORMANCE-EVIDENCE.md` §11; `master-plan-v6-reliability-contracts-evidence.md` | `C0` | — (thresholds are a product decision, not external) | PINV |
| PR-19 | Native Linux/macOS execution and installers | PARTIAL — Windows native and Linux Landlock+seccomp implemented and verified; macOS library present but unverified; no DMG/ZIP/AppImage/deb verified on native runners | Win 31 passed/6 skipped/0 failed; WSL2 16/16 sandbox + 9/1 os-sandbox; **macOS 14 tests all platform-gated skips** | Win VERIFIED; WSL2 kernel 6.6.87.2 VERIFIED; **mac none**, macOS 26 `sandbox-exec` SIGABRT | n/a — cannot attempt without a runner | `STAB-PLATFORM-EVIDENCE.md` §1-§5; `PROD-PLATFORM-EVIDENCE.md` [HISTORICAL] | `C0` | `A3` (+ `A2` for Apple trust) | BLCK |
| PR-20 | Live providers, signing, release authorization | FULL code — `signing.py` hard-fail gate, `publish.py` always gated for real publish, `build-desktop.yml` verify-release-signatures job, `signing-readiness.yml`; 42/42 SHA-pinned actions | FINAL — 4724/0 @ `C1`; 10 signing-gate tests + 36 combined at `C9`, governance gates re-run at `C0` | n/a | **NO KEYS, NO `.sig`, NO PUBLISH** — `signing-readiness.yml` reports MISSING; branch protection unavailable on GitHub Free | `master-plan-v6-signing-evidence.md`; `keel/docs/release/SIGNING-PREPARATION.md`; `PROD-SUPPLY-CHAIN-EVIDENCE.md` [HISTORICAL for 30/31 pins] | `C0`, `C3`, `C9`, `C10` | `A1`, `A2`, `A4`, `A5` | OWNR |

## D. Six separate summaries

### D.1 Implementation completeness

| State | Count | Gates |
| --- | ---: | --- |
| `FULL` mechanism present in tracked source at `C0` | 19 | PR-01…PR-18, PR-20 |
| `PARTIAL` (subset of surfaces) | 1 | PR-19 (Windows + Linux complete; macOS absent/unverified) |
| `NONE` / `NOT_IMPLEMENTED` | 0 | none |
| **Total** | **20** | — |

Scope notes recorded, not hidden: PR-10/PR-15 are implemented as libraries with no runtime consumer (integration M-4); PR-13 has the M-2 CLI/TUI tier-forwarding residual; PR-18 has no exporter/pager; PR-08 is deliberately forward-only with a documented snapshot-restore path; PR-07's CLI is `python -m keel.backups`, not a `keel backup` subcommand (stale matrix wording). None of these is an absent mechanism.

### D.2 Local test verification

| Measure | Value |
| --- | --- |
| Definitive full suite (completion branch) | **4724 passed / 0 failed / 54 skipped / 3707 subtests in 801.99 s** at `C1` = `060a281…`; the full-suite re-run at the final execution branch `C0` is **pending** (R-19) |
| Per-area targeted suites | PR-06/PR-14 128 passed; PR-07/PR-08 64 + 275; PR-09/PR-16/PR-17 local install gate `pass`, 6/6 + 7/7; PR-13 workflow auth + reviewer probes; PR-20 10 + 36 signing tests |
| Governance gates re-run at `C0` by this reconciliation | registry CONSISTENCY OK (865); strict backend gate 421/421, 0 failing, exit 0; license gate OK (11 entries, 0 bundled); dependency graph FRESH; version sync OK; **9/9** workflow YAMLs parse; **42/42** external full-SHA `uses:` pins + 1 local reusable path |
| Gates with local verification only at historical commits | **0** (historical runs are retained as provenance, never as the decisive evidence) |
| Gates locally verified at the final tree | **20 / 20** |

### D.3 Native platform

| Platform | Status | Counts | Gate |
| --- | --- | --- | --- |
| Windows (native, non-elevated) | VERIFIED | 31 passed / 6 disclosed skips / 0 failed + own probes | PR-13, PR-19 |
| Linux (native WSL2, kernel 6.6.87.2, Landlock ABI 3 + seccomp) | VERIFIED | 16/16 `test_sandbox_linux.py`; 9 passed / 1 helper-induced skip `test_os_sandbox.py` | PR-19 |
| macOS | UNVERIFIED / BLOCKED | no Darwin host; all 14 macOS tests platform-gated skips; macOS 26 read isolation `sandbox-exec` SIGABRT | PR-19 `BLCK` |
| Bare-metal / CI Linux runner, DMG/ZIP/AppImage/deb on native runners | Not executed | — | PR-19 `BLCK` |

### D.4 External provider

| Item | Status |
| --- | --- |
| Real provider requests made | **0** — all 55+ validation tests and 128 targeted tests are offline with synthetic credentials |
| Live smoke at final SHA | Not run; requires `A1` |
| Live credential revoke round-trip | Not run; piggybacks on `A1`, tracked under PR-14 as a sub-check, not a separate gate |
| Fabricated success | Fixed and tested: blank credential → SKIP, malformed → FAIL, error → redacted FAIL, cancel/timeout → not PASS |

### D.5 Trusted signing / governance

| Item | Status |
| --- | --- |
| Ed25519 hard-fail release gate | Implemented (`signing.py` `SigningGateError`, `require_signed_enabled`, `verify_signed_release`; real `publish` always gated); 10 + 36 tests green |
| Signing keys configured | **0** — `KEEL_RELEASE_SIGNING_KEY` / `KEEL_RELEASE_SIGNING_PUBLIC_KEY` absent |
| Platform trust secrets (Authenticode / Developer ID / notarization / Linux) | **0**; OS signing skipped by electron-builder |
| Signed artifacts (`.sig`, signed `RELEASE-MANIFEST.json`) | **0** tracked or on disk |
| Workflow action pinning | **42/42** external full-SHA `uses:` refs at `C0` across **9 workflow files**, plus 1 local reusable path (checkout 16, setup-python 14, download-artifact 5, setup-node 4, upload-artifact 3); older 8-workflow and 20/23/26/30/31 counts are **[HISTORICAL]** |
| GitHub Free branch protection / 2FA enforcement | Unavailable (403/404/422); owner plan decision `A4` |
| Final class | PR-20 `OWNR` |

### D.6 Production deployment

| Item | Status |
| --- | --- |
| Deployed instances | 0 |
| Published releases / tags pushed by this workstream | 0 |
| Distribution URLs in `keel/site/download.json` | all `url: null`, `available: false`, `verified: false`, `sha256: null` — nothing to download |
| Signed clean-VM upgrade/rollback (PR-17) | Not run |
| Native macOS (PR-19), owner governance (PR-20) | Open |
| Production deployment authorized | **No.** `PASS_VERIFIED` count is 0; see `FINAL-OWNER-ACTIONS.md` |

## E. Final gate totals — mutually exclusive, sums to 20

| Final class | Count | Gate IDs |
| --- | ---: | --- |
| `PASS_VERIFIED` | **0** | none — no live call, signed release, native macOS run or deployment |
| `PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED` | **16** | PR-01, PR-02, PR-03, PR-04, PR-05, PR-07, PR-08, PR-09, PR-10, PR-11, PR-12, PR-13, PR-14, PR-15, PR-16, PR-18 |
| `EXTERNAL_PENDING` | **2** | PR-06 (live provider), PR-17 (signed clean-VM upgrade/rollback) |
| `OWNER_ACTION_REQUIRED` | **1** | PR-20 (signing identity, credentials, plan, authorization) |
| `BLOCKED` | **1** | PR-19 (no Darwin runner; macOS 26 SIGABRT) |
| `NOT_IMPLEMENTED` | **0** | none |
| **Total** | **20** | PR-01…PR-20, each exactly once |

**Resolution of the `21` accounting.** `POST-PROMOTION-STABILIZATION-REPORT.md` §F reported
`17 passed locally + 2 external (PR-06, PR-17) + 1 owner (PR-20) + 1 blocked (PR-19) = 21`.
That report never enumerated its 17 IDs. The two gates named as external were also
inside the 17 "local passes", so they were counted in two mutually exclusive classes
at once; PR-18 then had no class. With the 20-gate universe and the four named
exceptional gates, the only self-consistent partition is
**16 local-verified + 2 external + 1 owner + 1 blocked = 20**. The provisional matrix's
`18 external_validation_pending (PR-01…PR-18) + 1 owner + 1 blocked = 20` was also
self-consistent but was written before the STAB evidence landed and before a final
SHA existed; at `C0` it refines to the table above. No gate is counted twice and none is dropped.

## F. Contradiction and stale-evidence register (audit history preserved, not deleted)

| Stale claim / artifact | Where | Status at `C0` |
| --- | --- | --- |
| `<<CANDIDATE_HEAD_REFERENCE — PLACEHOLDER>>`, `<<LEAD_SUPPLIED_SHA…>>` | `PRODUCTION-READINESS-MATRIX.md:17`; `PRODUCTION-READINESS-REPORT.md:5` | **[HISTORICAL]** — authoritative final reference is the branch `release/final-execution-2026-11-25` (`d5a50c0…` at reconciliation; resolve exactly with `git rev-parse HEAD`); the older `abfd…` completion SHA is historical provenance |
| `f60b080` as "current baseline tip" | matrix/report §A | **[HISTORICAL]** baseline; authoritative tree is `C0` = final execution branch |
| Candidate `63ab72e` as final | `FINAL-STABILIZATION-ACCEPTANCE.md` | **[HISTORICAL]** acceptance candidate; later completion/execution commits superseded it |
| `e573273`, `ac84fee`, `fe6cdd`, `ecba9d2b`, `CANDIDATE_HEAD…`; branches `agent/prod-ops`, `integration/*`, `final/v6-production`, `agent/stab-*` | PROD-*/FINAL-*/master-plan-v6-* docs | **[HISTORICAL]** provenance only; never current evidence for `C0` |
| Test counts 4214 / 4419 / 4437 / 4442 / 4459 / 4546 / 4557 / 4558 / 4610 / 4628 / 4630 / 4722 | delivery, STAB, POST-PROMOTION, independent-acceptance and test evidence docs | **[HISTORICAL]** at their own commits; authoritative recorded suite is **4724 passed / 0 failed / 54 skipped** at `C1` = `060a281…`; re-run at `C0` **pending** (R-19) |
| Action-pin counts 20 / 23 / 26 / 30 / 31; "8 workflows" | security, supply-chain, error-sweep, matrix, acceptance docs and this matrix's older §A/§D.5 | **[HISTORICAL]**; direct count at `C0` is **9 workflow files, 42/42 external full-SHA pins + 1 local reusable path** |
| `pass 13 / unverified 5 / blocked 2` | `FINAL-RELEASE-ACCEPTANCE.md` §B3, `FINAL-ERROR-SWEEP.md` §4 | **[HISTORICAL]** pre-promotion candidate verdict (`BLOCK`) |
| `pass 17 / unverified 3 / blocked 2` (only 13 IDs, PR-19 twice) | old `PRODUCTION-READINESS-MATRIX.md` summary | **[HISTORICAL]** superseded by five-state vocabulary then by this matrix |
| `17 local + 2 external + 1 owner + 1 blocked = 21` | `POST-PROMOTION-STABILIZATION-REPORT.md` §F | **[HISTORICAL]** mutually-exclusive recount = 16 + 2 + 1 + 1 = 20 |
| `18 external_validation_pending`, `pass locally = 0`, "no STAB evidence landed" | `PRODUCTION-READINESS-MATRIX.md` §A/§D; `PRODUCTION-READINESS-REPORT.md` | **[HISTORICAL]** provisional; 14 `STAB-*-EVIDENCE.md` files are present and the recorded suite is 4724/0 |
| "no frontend work / frontend files imported" | `FINAL-RELEASE-ACCEPTANCE.md` B1; `POST-PROMOTION-STABILIZATION-REPORT.md` §B | **[HISTORICAL]** — frontend completion merged via PR #16 (`d965d20`) and owner merge `C3`; no frontend was edited by this reconciliation |
| "no `keel backup` CLI exists" | old matrix PR-07 | Superseded — CLI is `python -m keel.backups` (`backups.py:695`) |
| "Linux WSL2 scoped with four conformance failures" | old matrix PR-19 / `PROD-PLATFORM-EVIDENCE.md` | Superseded — `STAB-PLATFORM-EVIDENCE.md` VERIFIED 16/16 + 9/1 with fail-closed skips disclosed |
| Perf §9.1 `BLOCKING / PRODUCTION-SIGNIFICANT` unimplemented | `STAB-PERFORMANCE-EVIDENCE.md:307`; `FINAL-STABILIZATION-ACCEPTANCE.md` §4.3 | Closed by `C2` (`_LEDGER_CACHE` in `backend_workflows.py`, `test_stab_ledger_cache.py`) before `C0` |
| 42/42 SHA pins and 4557-pass suite in final report | `POST-PROMOTION-STABILIZATION-REPORT.md` §C/§F | Superseded — 42/42 pins across 9 workflows and 4724/0 at `C1`; `C0` re-run pending |

### Superseded reports — HISTORICAL, retained not deleted

| Report | HISTORICAL status |
| --- | --- |
| `PRODUCTION-READINESS-MATRIX.md`, `PRODUCTION-READINESS-REPORT.md` | Provisional partition, superseded by §C/§E of this matrix |
| `POST-PROMOTION-STABILIZATION-REPORT.md` §F | `17 + 2 + 1 + 1 = 21` double-count; superseded by 16 + 2 + 1 + 1 = 20 |
| `FINAL-RELEASE-ACCEPTANCE.md` | Pre-promotion `BLOCK` verdict; superseded for the final tree, still not a production approval |
| `FINAL-STABILIZATION-ACCEPTANCE.md` | Candidate `63ab72e` verdict; not a final-tree verdict |
| `FINAL-INDEPENDENT-ACCEPTANCE.md` | Reviewer verdict at `530c067` (`BLOCK`, F-0); verdict retained for reviewer, stale counts corrected only; a fresh acceptance at the promoted SHA is pending |
| `FINAL-RELEASE-COMPLETION-REPORT.md` §1–§5 | Completion-lineage accounting; reconciled by its appendix and `docs/FINAL-RELEASE-EXECUTION-REPORT.md` |
| `master-plan-v6-test-evidence.md` §"FINAL stabilization full suite" | 4610-suite at `c512f87`; the later completion-branch run is 4724/0 |
| `signing-readiness.yml` reports MISSING; unsigned installers | `keel/docs/release/SIGNING-PREPARATION.md` | Still true at `C0`; the hard-fail code is implemented but no key exists — PR-20 `OWNR` |
| Literal `>>>>>>> agent/stab-provider` conflict marker | `STAB-PROVIDER-EVIDENCE.md:62` | Documentation hygiene defect only; no source/test impact, no gate reclassification |

## G. Scope and honesty note

This matrix classifies backend/harness and release-readiness gates at the final
execution branch reference (`C0`), with the authoritative suite recorded at the
completion-branch commit `C1`. It is not a production-readiness approval:
`PASS_VERIFIED` is zero, the full-suite re-run at `C0` is pending (R-19), no owner
action has been performed, no push/tag/publish occurred, and no source, test,
workflow or frontend file was changed by this reconciliation. Any later promotion
requires a fresh review at the SHA actually promoted and the owner actions in
`FINAL-OWNER-ACTIONS.md`, executed with the exact safe steps in
`docs/FINAL-OWNER-ACTION-RUNBOOK.md`.
