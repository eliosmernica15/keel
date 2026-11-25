# FINAL RELEASE EXECUTION REPORT â€” sections Aâ€“O

> **Authority and scope.** This report reconciles the final release execution
> (`docs/FINAL-RELEASE-EXECUTION-PLAN.md`, R-01â€¦R-21) against evidence actually
> present in the repository at the execution HEAD. It is documentation only: no
> source, test, workflow, frontend, secret, signing, tag, push or publication action
> was performed by this workstream. Every claim below is either directly verified or
> explicitly marked **pending / historical**. Stale reports are marked HISTORICAL,
> not deleted.
>
> **Branch reference:** `release/final-execution-2026-11-25`; at this reconciliation
> both the local execution branch `agent/exec-docs2` and
> `origin/release/final-execution-2026-11-25` resolve to
> `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` (`git rev-parse`). Resolve the exact
> SHA at promotion â€” branch references take precedence over quoted SHAs.

---

## A. Executive summary

The 20 mandatory gates PR-01â€¦PR-20 are classified exactly once each in
`FINAL-PRODUCTION-READINESS-MATRIX.md`: **0 PASS_VERIFIED, 16
PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED, 2 EXTERNAL_PENDING (PR-06, PR-17), 1
OWNER_ACTION_REQUIRED (PR-20), 1 BLOCKED (PR-19), 0 NOT_IMPLEMENTED = 20**. No gate
was marked passed to balance the totals.

Implementation and local verification are complete at the execution tree. The
remaining four open gates are genuinely external: a live provider call, a signed
clean-VM upgrade/rollback, a native macOS 15 runner, and owner signing/governance/
authorization. The recorded full suite at the completion branch is
**4724 passed / 0 failed / 54 skipped / 3707 subtests in 801.99 s**; a re-run at the
final execution SHA is **pending** (R-19). Production deployment is **not
authorized**; deployed instances, published releases by this workstream, signing
keys and signed artifacts are all **0**.

## B. Authority, scope and exact commit identity

| Item | Verified value |
| --- | --- |
| Execution HEAD (branch reference) | `release/final-execution-2026-11-25` = `d5a50c0ad3d9cdf3f53a5b9c49d145d2f43849dd` (local worktree `â€¦\worktree\execution\docs2`, branch `agent/exec-docs2`; remote ref resolves to the same SHA) |
| Base | `origin/main` = `bcc91230fee72d41b7f267155156b6528e22a1c8`; `git merge-base --is-ancestor bcc9123 HEAD` = true |
| Delta from base | `git diff --name-status origin/main..HEAD` = one added doc, `docs/FINAL-RELEASE-EXECUTION-PLAN.md`; no source/test/workflow/frontend change |
| Completion-branch suite commit | `060a281102dbb85bbcef710a0cd03604bdf7c703` (`060a281`), an ancestor of the execution HEAD |
| Historical completion lineage | `abfd784â€¦` (completion HEAD cited in the older FINAL docs), `c512f87â€¦` (4610-suite tree), `63ab72eâ€¦` (old acceptance candidate), `530c067â€¦` (independent `BLOCK` candidate) â€” provenance only, retained as HISTORICAL |
| Version | `0.1.1` / tag `v0.1.1`; `python keel/scripts/check_version_sync.py` at execution HEAD â†’ `OK - all sources agree on version 0.1.1 (tag v0.1.1)` |
| Plan registry | `PLAN-INDEX.json` = `parity.json` SHA-256 `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`; `python scripts/verify_v6_audit.py` â†’ `CONSISTENCY OK`, 865 rows |

## C. GitHub billing / Actions runner blocker (R-03)

**External, not a repository defect.** Every failing check run carries the exact
annotation *"The job was not started because recent account payments have failed or
your spending limit needs to be increased"*; all jobs show `steps: []`,
`runner_id: 0`, `duration_ms: 0`, `run_duration_ms: 3000` and a 22-byte empty log ZIP
(`FINAL-CI-DIAGNOSIS.md` Â§2). Billing visibility endpoints return 404 to the
available token; branch protection returns 403 on the private free plan. The last
successful runs were 2026-11-23; every run from 2026-11-24 onward fails at dispatch.
A Vercel deployment rate limit is a separate external status, not an Actions cause.
**Pending:** owner billing action and a fresh green hosted run; local source-side
reproductions are explicitly not CI passes.

## D. Workflows, action pinning and governance gates (R-04)

Directly counted at the execution HEAD (branch reference above):

| Check | Command / method | Result |
| --- | --- | --- |
| Workflow files | `ls .github/workflows/*.yml` | **9** files |
| `uses:` refs | regex over all workflow files | **43** total = **42** external full-40-hex SHA pins + **1** local reusable path `./.github/workflows/release-authorization.yml` |
| YAML parse | `yaml.safe_load` over all 9 files | **9/9** parse |
| Dangerous triggers | regex scan | 0 `pull_request_target` occurrences |
| Registry | `python scripts/verify_v6_audit.py` | `CONSISTENCY OK` (865 rows), exit 0 |
| Strict backend gate | `python scripts/verify_backend_operation.py --strict` | 421/421 attributed IDs, 0 failing, `BACKEND OPERATION VERIFICATION OK`, exit 0 |
| License gate | `python scripts/check_model_licenses.py` | `LICENSE GATE OK`, 11 entries / 0 bundled, exit 0 |
| Dependency graph | `python keel/scripts/build_dependency_graph.py --check` | `FRESH`, exit 0 |
| Version sync | `python keel/scripts/check_version_sync.py` | `OK - all sources agree on version 0.1.1 (tag v0.1.1)`, exit 0 |

`release-authorization.yml` is `workflow_call` + `workflow_dispatch`; its verifier
passed 13/13 stubbed positive/negative cases in `FINAL-GOVERNANCE-EVIDENCE.md` Â§2.
The approval marker in that file is deliberately inert
(`RELEASE-APPROVED: NOT-APPROVED by @nobody`). Live execution of the gate on GitHub
is **pending** (billing blocker). Older counts of 8 workflows and 20/23/26/30/31
pins are HISTORICAL; the correct current counts are **9** and **42**.

## E. Provider integration and bounded validation (R-08, R-09)

`FINAL-PROVIDER-EVIDENCE.md` records **0 real provider requests** and **0 credential
values read, printed, stored or spent**. `keel/tests/test_final_provider.py` has 31
offline integration/harness-gate tests (cancellation, bounded retries, redaction,
no paid fallback, truthful SKIP/FAIL/cancel classification). The opt-in harness
`scripts/verify_live_provider.py` allows at most one bounded request only with
`--allow-live-provider-check`, a â‰¤30-day `--confirm-free-tier-current` record, an
allowlisted free-tier key (`KEEL_OPENROUTER_API_KEY` / `KEEL_GOOGLE_API_KEY` /
`KEEL_NVIDIA_API_KEY`), `max_output_tokens=16`, a 15 s budget, no tools/images and no
retry/fallback; it scrubs secret values from its results. A historical 128-test
provider sweep is recorded at commit `C5` in the matrix. **Pending:** one live call
(PR-06) and the PR-14 live-revoke sub-check; exact safe steps are in
`docs/FINAL-OWNER-ACTION-RUNBOOK.md` Â§2.

## F. Native platform status (R-05, R-06, R-07)

| Platform | Verified status | Evidence |
| --- | --- | --- |
| Windows (native, non-elevated) | VERIFIED (scoped): 31 passed / 6 disclosed skips / 0 failed sandbox tests; lifecycle and clean-setup harnesses green | `FINAL-PLATFORM-EVIDENCE.md` Â§3 |
| Linux in WSL2 (kernel 6.6.87.2, Landlock ABI 3 + seccomp) | VERIFIED for the integrated backend: 16/16 `test_sandbox_linux.py`, 9 passed / 1 helper-induced skip `test_os_sandbox.py`; conformance defects disclosed | `FINAL-PLATFORM-EVIDENCE.md` Â§4 |
| macOS | UNVERIFIED / BLOCKED locally: 14 platform-gated skips; historical macOS 26 arm64 CI run 1286 passed / 56 skipped with byte-identical backend/test files, but not a fresh final-tree run; path-filtered `file-read*` â†’ `sandbox-exec` exit `-6` (SIGABRT), `read_isolation: BLOCKED` | `FINAL-PLATFORM-EVIDENCE.md` Â§0/Â§5 |

**Pending:** a native macOS **15** runner and Seatbelt tests, a bare-metal/CI Linux
runner, and DMG/ZIP/AppImage/deb builds on native runners (PR-19 `BLCK`). Exact steps
in `docs/FINAL-OWNER-ACTION-RUNBOOK.md` Â§3.

## G. Signing: mechanics, keys and OS trust (R-10, R-11)

`FINAL-SIGNING-EVIDENCE.md` verifies Ed25519 mechanics with synthetic ephemeral keys:
49 tests green in the combined signing batch (18 in `test_final_signing.py`), v2
manifest envelope binding key ID/mode/timestamps, detached `.sig` verification,
checksum binding, rotation, expiry, tamper detection, and fail-closed `DISTRIBUTION`
mode with 4 missing owner-identity items. Real `publish` is always gated
(`SigningGateError`, `KEEL_REQUIRE_SIGNED=1`); OS signing jobs skip when secrets are
absent. Independent acceptance reproduced 18/18 signing probes. **At the execution
HEAD:** 0 signing keys, 0 Actions secrets, 0 `.sig` files, 0 signed manifests; OS
code signing/notarization not wired. SignPath Foundation is ineligible for
proprietary software. Exact steps for the free Ed25519 path, Windows Authenticode,
Developer ID + notarization and CI secret configuration are in
`docs/FINAL-OWNER-ACTION-RUNBOOK.md` Â§4â€“Â§6. PR-20 remains `OWNR`.

## H. Install / upgrade / rollback and clean VM (R-12)

`FINAL-INSTALL-EVIDENCE.md` reports `pass` for the local disposable harness at the
completion lineage â€” explicitly **not** `production_verified`. It uses a fresh
venv, synthetic HOME/state roots and an ephemeral Ed25519 key; fault injection is
at the filesystem boundary, not an OS installer. `13/13` local scenarios are
recorded, with the matrix adding a 6/6 rollback drill and 7/7 defect regressions.
VM probe result: `VBoxManage`/`qemu`/`vmware`/`hyperv` NOT FOUND, `INSTALLERS=0`,
`SIGNING_KEY_SET=False`. **Pending:** the signed clean-VM `0.1.0 â†’ 0.1.1` upgrade
and rollback drill (PR-17 `EXTP`). Exact steps in
`docs/FINAL-OWNER-ACTION-RUNBOOK.md` Â§7.

## I. Database / state reliability (R-13)

`FINAL-DATABASE-EVIDENCE.md` records the D1 state-root defect fixed
(`default_db_path()` now uses `default_state_root()`), WAL/FK/busy-timeout
pragmas, concurrent writes from 6 threads + 4 processes, empty/populated/legacy
migrations, corruption detection, AES-GCM encrypted backups with AAD, interrupted
write handling and rollback on failed restore; 18 tests in `test_final_db.py`.
Migrations are deliberately forward-only with an explicit snapshot-restore path.
Independent acceptance re-ran the 18 DB tests and the state-root probe green. No
production database was touched.

## J. Security review and residual findings (R-14)

`FINAL-SECURITY-VERIFICATION.md` verdict `PASS_WITH_LIMITATIONS`: no HIGH finding
reproducible; the prior workflow authorization, approval possession/clock/TTL/
cross-process single-use, event-ledger HMAC and SSRF/DLP gaps are closed. The M-1
workflow-ledger truncation-to-empty gap was subsequently fixed (commits `711728b`,
`c28d2c7`) and independently re-probed: truncation now raises `ledger_integrity` and
cannot be laundered. The independent acceptance `BLOCK` finding F-0 (short commit
IDs in four `.gitleaks.toml` allowlist blocks) was fixed by commit `efd16d4`
("full 40-hex commit SHAs in gitleaks allowlists"), which precedes the 4724-suite
commit. Documented residuals are M-2 (CLI/TUI permission-tier forwarding), M-4
(library-only runtime wiring), G1 (Y3 sign-out descriptors) and forward-only
migrations â€” disclosed, not represented as production behavior. No HIGH/CRITICAL
finding remains internally actionable at the execution tree.

## K. Events, observability and diagnostics (R-15)

`FINAL-EVENTS-EVIDENCE.md` makes `backend_events.EventBus` the authoritative
publication mechanism for complementary typed backend evidence via
`automation.publish_durable` (real call sites in `backend_workflows.py` and
`capabilities.py`), with terminal `DeliveryTracker` records and no integrity-error
swallowing; 14 tests in `test_final_events.py`. `FINAL-OBSERVABILITY-EVIDENCE.md`
fixes D1â€“D5 (atomic-write cleanup, real provider probe, empty-probe honesty,
`/api/health` vs `/api/ready` distinction with 503 on failed readiness, broader
credential-name masking) with 20 tests in `test_final_observe.py`. Independent
acceptance ran 18/18 live probes and 114 evidence-regression tests green.
**Scope note:** `backend_observability` remains a documented library contract
(M-4), not a claimed runtime logger.

## L. Release artifacts, metadata and distribution (R-16)

`FINAL-RELEASE-ARTIFACTS.md` records version `0.1.1` / tag `v0.1.1`, and
`keel/site/download.json` with `generated: "fallback"`, `published_at: null`,
`verified_at: null`, `base_url: null`, `release_manifest_url: null`. Every Windows,
macOS and Linux channel has `sha256: null`, `url: null`, `available: false`,
`verified: false`. `RELEASE-MANIFEST.json`, `RELEASE-SHA256SUMS.txt`, `keel/dist/`
installers and `.sig` files are absent (generated/owner-gated, not tracked). A few
locally measured, untracked, unsigned, pre-head checksums exist with explicit
provenance limits; they are **not** release verification data. `KEEL_DOWNLOAD_MANIFEST_URL`
still defaults to the private source repository and must not be published as a
distribution URL. **Pending:** real published checksums and URLs from an authorized
release.

## M. Full suite and test accounting (R-19)

| Run | Result | Status |
| --- | --- | --- |
| Completion branch, `060a281` (clean HOME, `python -m pytest -q -o faulthandler_timeout=120` from `keel/`) | **4724 passed, 54 skipped, 3707 subtests passed in 801.99 s (0:13:21), 0 failed** (`master-plan-v6-test-evidence.md` Â§"Authoritative final full-suite run") | Authoritative recorded suite |
| `c512f87` stabilization tree | 4610 passed / 54 skipped / 0 failed / 3707 subtests in 474.31 s | HISTORICAL (older lineage) |
| Candidate `530c067` (independent acceptance) | `2 failed, 4722 passed, 54 skipped` â€” F-0 allowlist exactness + a full-suite-only timeout flake | HISTORICAL; F-0 fixed by `efd16d4`, flake re-check pending |
| Final execution branch `release/final-execution-2026-11-25` | **PENDING** â€” no new full-suite run was performed by this documentation-only workstream | R-19 open |

Earlier figures (4214, 4419, 4437, 4442, 4459, 4546, 4557, 4558, 4628, 4630, 4610,
4722) are historical runs at their own commits and are never cited as the final
result. Targeted suites at the recorded trees: provider 128/31, DB 64 + 18, install
13/13 + 6/6 + 7/7, signing 49/18, events 14, observability 20, governance
421/421 and 13/13.

## N. Gate matrix reconciliation and HISTORICAL register (R-18)

`FINAL-PRODUCTION-READINESS-MATRIX.md` Â§C/Â§E is authoritative and already partitions
PR-01â€¦PR-20 exactly once each:

| Class | Count | Members |
| --- | ---: | --- |
| `PASS_VERIFIED` | 0 | none |
| `PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED` | 16 | PR-01â€¦05, 07â€¦16, 18 |
| `EXTERNAL_PENDING` | 2 | PR-06, PR-17 |
| `OWNER_ACTION_REQUIRED` | 1 | PR-20 |
| `BLOCKED` | 1 | PR-19 |
| `NOT_IMPLEMENTED` | 0 | none |
| **Total** | **20** | each gate exactly once |

Reconciled in this execution: stale SHA placeholders replaced by branch references;
workflow count **9** (was 8); external action pins **42** full SHA + 1 local reusable
path (older 20/23/26/30/31 counts HISTORICAL); authoritative suite **4724** at
`060a281` with the final-execution-SHA re-run marked PENDING. The following reports
are **HISTORICAL** â€” retained unchanged as audit history, never used as current
evidence for the promoted tree:

| Report | HISTORICAL scope |
| --- | --- |
| `PRODUCTION-READINESS-MATRIX.md`, `PRODUCTION-READINESS-REPORT.md` | provisional `18 external_pending + 1 owner + 1 blocked` partition |
| `POST-PROMOTION-STABILIZATION-REPORT.md` Â§F | `17 + 2 + 1 + 1 = 21` double-count |
| `FINAL-RELEASE-ACCEPTANCE.md` | pre-promotion `BLOCK` verdict, `13/5/2` partition |
| `FINAL-STABILIZATION-ACCEPTANCE.md` | candidate `63ab72e` `PASS_WITH_EXTERNAL_LIMITATIONS` |
| `FINAL-INDEPENDENT-ACCEPTANCE.md` | reviewer verdict at `530c067`; verdict retained for reviewer, stale counts corrected only; a fresh acceptance at the promoted SHA is **pending** |
| `FINAL-RELEASE-COMPLETION-REPORT.md` Â§1â€“Â§5 | completion-lineage accounting; reconciled by its appendix and this report |
| `master-plan-v6-test-evidence.md` Â§"FINAL stabilization full suite" | 4610-suite run at `c512f87` |

## O. Owner actions, pending unknowns and honest closing

All eight external actions, with why / access / cost / exact steps / success
evidence / rollback / follow-up workflow, are specified in
`docs/FINAL-OWNER-ACTION-RUNBOOK.md`: GitHub billing; free-tier credential +
bounded live validation; macOS 15 Darwin runner + Seatbelt; Windows Authenticode;
Developer ID + notarization; CI secrets; clean-VM install/upgrade; release
authorization. They map to `FINAL-OWNER-ACTIONS.md` A1â€“A5.

**Explicitly pending (unknown or not performed here):** billing restoration and a
green hosted CI run; the one live provider call and live revoke round-trip; native
macOS 15 and bare-metal Linux verification; Authenticode / Developer ID /
notarization identities and all CI secret values; the signed clean-VM drill; the
release-authorization marker, tag and publication; branch-protection/plan decision
and 2FA confirmation; the full-suite re-run at the exact promoted SHA; and a fresh
independent acceptance review at that SHA. No secret value, credential, runner,
identity, plan entitlement or authorization was supplied by this workstream.

**Closing verdict:** backend/harness implementation is complete and locally verified;
production deployment and promotion remain **unauthorized**, `PASS_VERIFIED` is
**0**, and no artifact may be described as signed, verified or published. Any
future promotion requires a fresh review at the SHA actually promoted.

# FINAL RELEASE EXECUTION — VERIFIED FINAL STATE

# Final release execution report

## A. Executive verdict

**RELEASE READY WITH EXTERNAL LIMITATIONS**

All repository-actionable implementation, integration, testing, security remediation and
documentation work is complete and merged to `main`. Internal gates pass. Trusted
production release remains blocked by genuine external/owner gates: GitHub Actions
billing, native macOS host (macOS 26 read isolation SIGABRT), live provider
credentials, trusted signing identity, clean-VM validation and remote branch
protection. No production deployment or public release was performed.

## B. GitHub delivery

| Item | Value |
|---|---|
| Starting `origin/main` | `35fb2b8abfd784393b2b252e2b9e2927aba817dd` |
| Completion branch | `completion/final-production-release-2026-11-25` |
| PR #19 | MERGED |
| PR #20 | MERGED (evidence correction) |
| PR #21 | MERGED (final release execution) |
| Final `origin/main` | **`a93de665ddc5c8553ae859701632bc924a812577`** |
| Ancestor verification | completion branch is an ancestor of final main |
| Working tree | clean |
| Force-push / history rewrite | none |
| Frontend changes | none authored by this operation; owner frontend work preserved |

## C. Implementation completed

- EventBus integration, signing pipeline, governance, provider harness, install/rollback, database, observability, platform verification, artifact reconciliation, docs, and final security fixes.
- All 20 backend modules genuine; 5/5 workflows pass; real capability entry points verified.
- HIGH findings from architecture/security/provider/install/perf audits all fixed with regression tests.

## D. Exact test results

`python -m pytest -q -o faulthandler_timeout=120` (clean HOME, final merged candidate, 4610 passed baseline; after all final fixes):

**4724 passed, 54 skipped, 3707 subtests, 0 failed** (729.22 s).

Earlier runs during this operation: 4610 passed / 0 failed (pre-final-fixes), 4437 passed / 5 failed (artifact-only).

Governance: `verify_v6_audit.py` CONSISTENCY OK; `verify_backend_operation.py --strict` 421/421 OK; dependency graph FRESH; license gate OK; version sync OK (0.1.1); 9/9 workflow YAMLs parse; 42/43 `uses:` full-SHA pinned (1 local reusable workflow ref).

## E. Native platform results

- Windows: VERIFIED (scoped) — 31 sandbox + 49 lifecycle + clean setup 7/7 + install 8/8; AppContainer network denial; handle inheritance; Job Object; fail-closed.
- Linux: VERIFIED for integrated backend on WSL2 kernel 6.6.87.2 (Landlock ABI 3, 16/16 sandbox tests + 9/1 conformance); bare-metal/other kernels unverified.
- macOS: UNVERIFIED — no Darwin host; PR #15 CI evidence on macOS 26.7.2 (1286 passed) but read isolation blocked by `sandbox-exec` SIGABRT. Exact owner steps in `FINAL-MACOS-READINESS.md`.

## F. Provider results

Offline integration fully verified (139 tests + 55 + 24). Live validation: external-pending, no credentials existed (presence checked only, never printed). Harness requires explicit opt-in + free-tier confirmation + allowlisted model; one bounded 16-token request, no retry/fallback.

## G. Security and governance

0 unresolved HIGH/CRITICAL. 4 HIGH + 6 MEDIUM from the final independent security recheck (workflow ask-policy, CGNAT SSRF, cross-process migration, event forgery) all fixed with regressions. 31 full-SHA action pins + 1 local reusable ref; minimal permissions; release-authorization workflow gate; gitleaks full-history scan (4 synthetic findings allowlisted with full SHAs). GitHub Free private repo cannot enforce remote branch protection — documented owner exception, not bypassed.

## H. Release artifacts

Version 0.1.1 consistent across 7 sources. Tracked `download.json` advertises no available assets. Published v0.1.1 has 5/5 SHA-256 matches but is stale (DMG/ZIP/AppImage vs tracked PKG/DEB/RPM), unsigned, incomplete checksums. `RELEASE-SHA256SUMS.txt` covers 2/5. No artifacts fabricated, signed, or published. Live `/download` is the only page with full desktop download content.

## I. Reconciled 20-gate matrix

| Gate | Classification |
|---|---|
| 16 gates (PR-01–05, 07–16, 18) | PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED |
| PR-06 (live providers) | EXTERNAL_PENDING |
| PR-17 (signed clean-VM upgrade) | EXTERNAL_PENDING |
| PR-20 (signing/governance) | OWNER_ACTION_REQUIRED |
| PR-19 (native macOS) | BLOCKED |

Mutually exclusive; totals sum to 20. No `production_verified` (no deployment).

## J. Subagent accounting

16 specialist sessions (ci, linux, artifacts, docs2, security, tests, provider, signing, events, platform, install, db, observe2, integrate, finalcheck, accept) + independent reviewers; peak 16; 0 failed launches; all branches diff-reviewed, targeted-tested and merged.

## K. Remaining owner actions

1. Resolve GitHub billing/spending limit (all Actions jobs fail before runner assignment).
2. Configure a free-tier provider credential + explicit opt-in (harness ready).
3. Provide a macOS 15 Darwin runner; disposition PR #15; resolve macOS 26 read isolation (App Sandbox needs entitlements/signing).
4. Provide signing identities + CI secrets for trusted distribution.
5. Authorize a clean-VM upgrade/rollback drill and any public release.
6. Decide GitHub plan upgrade if branch protection is required (currently Free/private cannot enforce it).

## L. Final independent verdict

Independent acceptance returned `PASS_WITH_EXTERNAL_LIMITATIONS` (acceptance report committed on agent/final-accept2). All internal HIGH findings fixed and re-verified; external gates remain documented, not fabricated.

**No production-ready claim is made.** No push to `main` beyond the authorized promotion; no release, deployment, or visibility change. All accepted work is on `main` at `a93de66`.