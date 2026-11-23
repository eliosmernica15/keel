# Keel Master Plan v6 — Final consolidated completion report

**Definitive audit baseline:** `321bc7a55f2f306365a0f2ee26441fef345e8f41` (parent `cadb343`, contains the completed audit evidence)
**Audited code baseline:** `cadb343e84db1a1cc5fa2bed584996c33b629a4b`
**Integration branch:** `integration/v6-completion` (local only; created from `321bc7a`)
**Report date:** 2026-11-23
**Environment:** Windows 10 (10.0.26300-SP0) AMD64, Python 3.11.9, Node v24.22.2

This is the final completion operation following the audit. It implements and verifies the locally achievable security, governance and supply-chain work, and records the precise remaining owner/external dependencies. Companion evidence: `master-plan-v6-final-matrix.{csv,json}`, `master-plan-v6-architecture-map.md`, `master-plan-v6-test-evidence.md`, `master-plan-v6-security-findings.md`, `master-plan-v6-git-provenance.md`, `master-plan-v6-agent-execution.md`, `master-plan-v6-remaining-work-closure.md`, `master-plan-v6-repository-security-evidence.md`, `master-plan-v6-sandbox-verification.md`, `master-plan-v6-release-acceptance.md`, `master-plan-v6-independent-acceptance.md`.

---

## A. Repository

| Item | Value |
| --- | --- |
| Starting SHA (verified) | `321bc7a` (parent `cadb343`) |
| Working tree at start | clean |
| Final local HEAD | `f6773be…` (see `git rev-parse integration/v6-completion` for the exact delivery commit) |
| Branch | `integration/v6-completion` |
| Local main (untouched) | `cadb343` (10 ahead / 33 behind origin/main) |
| Remote main (live `git ls-remote`) | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` — unchanged |
| Merge base | `107a427` |
| Audit branch (untouched) | `docs/v6-final-audit` at `321bc7a` |
| Working tree at delivery | clean (all changes committed) |
| Push / release / deploy | **none performed** |
| History rewrite / force-push / branch deletion | **none performed** |
| Merge of divergent origin/main into local | **not performed** |

The task brief's remote SHA `ecba9d2c8378ab…` is incorrect; the live value is `ecba9d2b9678ab…` (as also found in the prior audit).

## B. Agent execution

A four-agent capacity pilot was launched first; all four started and produced commits, confirming the earlier `free-models-per-day` failure had cleared. The team was expanded to seven active specialists. Ten isolated worktrees were created under `~/.local/share/opencode/worktree/completion/`.

| Agent | Result | Commit |
| --- | --- | --- |
| 01-style Actions SHA pinning | completed — 20/20 refs pinned, independently re-verified | `ef02409` |
| 21-style registry integrity | completed — 228 IDs reconciled, no change needed | `9f1a610` |
| 10-style provider readiness | completed — no credentials, exact secret names, no live call | `a3a08b9` |
| 18-style supply-chain audit | completed — version/checksum/artifact findings | `1d12502` |
| Version consistency fixes | completed — 5 defects fixed, 25 targeted tests pass | `cdc41ca` |
| Phone + signing readiness | completed — no device, no identity, exact blockers | `33876d6` |
| Sandbox red-team (independent) | completed — real adversarial processes; no High/Critical | `d2c1d25` |
| Independent final acceptance review | completed — reproduced all major claims; one Medium finding (live vs local SHA pinning) corrected | `c293377` |

No agent failed to launch in this wave. Agent commits were integrated with `git merge --no-ff`; the two add/add conflicts on the shared closure document were resolved by combining sections. The lead independently re-resolved every Actions SHA via `git ls-remote` before merging. Work performed directly by the lead is itemised in `master-plan-v6-agent-execution.md` (state verification, C11.1 change, C11.2 settings, native sandbox integration and defect fixes, capability wiring, merge conflict resolution, final testing and reporting).

## C. Master Plan v6

| Classification | Count |
| --- | --- |
| Implemented — local_module (incl. 52 operational) | 220 |
| External-validation-pending (B4.8, B6.6, C11.8) | 3 |
| Dormant — owner-directed (B6.2, B6.3, B6.5) | 3 |
| Owner-blocked (C11.1 → now resolved; C11.2 → partial) | 2 |
| Partial / Not-implemented / Not-verified | 0 |
| **Total** | **228** |

`PLAN-INDEX.json == parity.json`, all 228 IDs present, tier/status counts unchanged, all source/test references resolve, `scripts/verify_v6_audit.py` → `CONSISTENCY OK`. No registry classification was altered by this operation; no dormant seam was activated. Regressions from the integration: none found — the full targeted security/sandbox/registry suites pass. Two real code defects were fixed (Windows sandbox dispatch gap, inverted seccomp BPF filter) plus five version/supply-chain defects.

## D. Repository governance

| Area | Status | Evidence |
| --- | --- | --- |
| C11.1 source hosting | **PASS** | Owner explicitly confirmed; live `PATCH private=true`; verified `private: true`, only owner collaborator, 7 workflows still active |
| C11.2 Actions SHA pinning | **PARTIAL** | Local integration branch: 20/20 refs full-SHA pinned, 0 tag-only, YAML parses. Live `main`: 23/23 tag-pinned, 0 SHA-pinned — completion branch not pushed (owner gate); 3 extra workflows exist only on origin/main. Independent reviewer finding, corrected. |
| C11.2 branch protection | **BLOCKED** | Free private plan returns 403 ("Upgrade to GitHub Pro or make this repository public") and `protected: false` — the exact C11.1 caveat |
| C11.2 signed commits / admin enforcement | **BLOCKED** | Live API 404; no GPG binary or signing key |
| C11.2 fork restriction | **BLOCKED** | 422 — only org-owned private repos can disable forking |
| C11.2 2FA | **UNVERIFIED** | Owner account-level; not exposed by available API |
| Compensating control | **implemented** | Fail-closed `.githooks/pre-push` (no direct main push, gitleaks, version gate); executed locally and confirmed to block when gitleaks is absent |

The loss of remote branch protection was a plan-level consequence of the owner-confirmed visibility change, not a silent weakening. Precise owner actions are listed in `master-plan-v6-repository-security-evidence.md`.

## E. Security

- **Windows:** real OS enforcement is now actually invoked. Restricted primary token + workspace ACLs + restricted handle inheritance + Job Object; independent red-team confirmed outside reads/writes, traversal, junction escape, child-process escape and timeout tree-kill are all denied. Network denial is **not** available on this host and the default path fails closed. No High/Critical findings; two Low findings accepted with rationale.
- **Linux:** Landlock + seccomp backend integrated with the `landlock_add_rule EINVAL` root cause fixed (old 4th arg was rule size instead of flags `0`); inverted BPF filter corrected with a cross-platform regression test. Native execution **not verifiable on this Windows host** — environment-gated.
- **macOS:** Seatbelt backend integrated; writes/network/rlimits confined, read isolation honestly BLOCKED on macOS 26 (`sandbox-exec` SIGABRT). Native execution not verifiable here.
- **Execution architecture:** all three platforms dispatch to dedicated backends with no permissive fallback; `core.os.sandbox.capabilities` and `core.os.sandbox.run` added to the hub with permission enforcement; capability count 226 (unique).
- **Remaining weaknesses:** Windows network unenforced; Linux/macOS native verification outstanding; transient workspace ACL widening (Low); heuristic env scrubbing belongs to the policy layer; no remote branch protection on the free private plan.

## F. Integrations

- **Provider integration:** all five adapters present; no non-empty `KEEL_*` provider key is configured (checked including the encrypted settings-store fallback); no live call was made. Exact secret names and the secure validation workflow are documented in `master-plan-v6-remaining-work-closure.md`. BLOCKED — owner credential configuration.
- **Phone companion:** local pairing/TLS/approval/outbox implementation exists. No device or emulator exists in the environment (no adb/fastboot/xcrun/idevice_id, no USB device, no emulator paths). QR/payload generation is explicitly **not** claimed as real pairing. BLOCKED — hardware. See `master-plan-v6-release-acceptance.md`.

## G. Platform verification

- Native Windows execution: performed (sandbox tests + red-team drivers + capability smoke test).
- Native macOS / Linux execution: not possible on this Windows host; their backends are integrated and statically reviewed, with environment-gated tests.
- Packaged installer: rebuilt from the final commit on this host — `Keel-Setup-0.1.1.exe`, 141,118,394 bytes, SHA-256 `F12E1D668EF9983F291CC2302FCD4A938327CFCD1B4DEF5E5A9BAC7C76C14054`, unsigned. 7/7 local integrity checks pass (`master-plan-v6-release-acceptance-addendum.md`). This is build integrity only, not install/upgrade verification. The pre-existing installer (SHA `CC455DE1…`) was not represented as final.
- Clean-VM install / upgrade / rollback / uninstall / user-data preservation: not performed locally; exact commands recorded in `scripts/validate_desktop.py` and `master-plan-v6-remaining-work-closure.md`.

## H. Signing and release

No signing identity exists: GitHub Actions secrets `total_count=0`, no local signing certificate/private key, no signing env vars. CI has no signing job and does not hard-fail when secrets are missing. Unsigned packages must not be published as production-signed releases. Exact secret names and workflow changes are in `master-plan-v6-release-acceptance.md`. BLOCKED — owner credentials and an explicit decision on paid platform certificates (master plan currently excludes paid signing/notarization).

## I. Test results

See `master-plan-v6-test-evidence.md` for exact commands, environment, skip reasons and the full final-suite result.

- **Baseline (`cadb343`):** `python -m pytest -q` → `1270 passed, 10 skipped`.
- **Integrated branch:** `python -m pytest -q -o faulthandler_timeout=90` → **1296 passed, 46 skipped in 505.43s (0:08:25)**, no failures. All 46 skips are platform/credential gates (36 native-sandbox platform gates, 10 provider-credential gates); no test was deleted, weakened, or converted to a fixture.
- Targeted: version fixes 25 passed; sandbox 20 passed/36 skipped; independent red-team 19 passed/6 skipped; phone/signing 15 passed.
- `python scripts/check_version_sync.py` → `OK - all sources agree on version 0.1.1`; `python scripts/verify_v6_audit.py` → `CONSISTENCY OK`.

Note: two earlier full-suite attempts stalled under concurrent heavy processes; a clean, single run with faulthandler completed successfully. The stall was environmental contention, not a code defect — `validate_desktop.py` and its test pass in isolation (2 passed in 7.44s).

## J. Outstanding owner actions

1. **Repository plan/forge decision (C11.2):** choose a plan supporting private branch protection, accept local compensating controls as a documented exception, or move to a forge with protected branches. This is a paid-service/owner decision (gate G6).
2. **Signing identity (release):** create `KEEL_RELEASE_SIGNING_KEY` / `KEEL_RELEASE_SIGNING_PUBLIC_KEY` via the secure secret store; add the CI signing job and missing-secret hard failure; decide on paid platform certificates.
3. **Provider credentials:** configure the exact `KEEL_*_API_KEY` values via masked CI secrets or Keel's encrypted store; never paste them into chat or git.
4. **Phone hardware:** provide a real Android/iOS device or emulator and the phone-side companion client for real pairing validation.
5. **Native platform runners:** execute the Linux and macOS sandbox/installer suites on native runners.
6. **Clean-VM validation:** run install/upgrade/rollback/uninstall on disposable VMs per OS.
7. **Review and merge the completion branch:** the SHA pinning and native-sandbox fixes exist only on the unpushed local `integration/v6-completion` branch; the live repo `main` still has 23 tag-pinned Actions refs. Pushing/merging is explicitly owner-gated and was not performed.

## Final acceptance matrix

Statuses: **PASS** implemented and verified; **PARTIAL** genuine functionality with an incomplete requirement; **BLOCKED** named external dependency or owner decision; **FAIL** implementation/verification failed.

| Area | Status | Evidence / reason |
| --- | --- | --- |
| Master Plan v6 traceability (228 IDs) | PASS | `verify_v6_audit.py` → CONSISTENCY OK; parity identical |
| Previously implemented features / no regressions | PASS | Targeted suites + full suite; no weakened/deleted tests; two real defects fixed |
| C11.1 source hosting | PASS | Owner-confirmed, live `private: true`, verified collaborators and workflows |
| C11.2 repository security | PARTIAL | SHA pinning PASS; branch protection/signing/forks/2FA blocked by free private plan / owner account |
| Windows sandbox | PASS (network via AppContainer) | Real FS/process/resource enforcement proven adversarially, plus genuine non-elevated network denial via a capability-less AppContainer (`9a77dae`, `master-plan-v6-win-network-evidence.md`); WFP per-process filters remain blocked without elevation (honestly disclosed) |
| Linux sandbox | BLOCKED | Backend integrated with ABI/BPF fixes; native Landlock/seccomp execution requires a Linux runner |
| macOS sandbox | BLOCKED | Backend integrated; read isolation BLOCKED on macOS 26 by `sandbox-exec` SIGABRT; native runner required |
| Execution architecture | PASS | All three platforms dispatch to dedicated backends, no permissive fallback; 226 unique capabilities |
| Provider integration | BLOCKED | No `KEEL_*` credentials in environment; no live call made; exact secret names documented |
| Phone companion | BLOCKED | No device/emulator; local implementation only; QR is not pairing proof |
| Windows lifecycle | BLOCKED | Final-source installer not yet rebuilt; clean-VM install/upgrade/rollback not performed |
| macOS lifecycle | BLOCKED | No macOS runner; unsigned DMG/ZIP only |
| Linux lifecycle | BLOCKED | No Linux runner / package-manager lifecycle test |
| Signing | BLOCKED | No identity or CI secrets; workflow hard-fail gate required |
| CI and supply chain | PARTIAL | Local branch: 20/20 SHA-pinned actions; version sync gate passes; gitleaks/pre-commit configured. Live repo still tag-pinned (branch not pushed) |
| Final installers rebuilt from final source | **PARTIAL** | Windows rebuilt from final commit, 7/7 integrity checks pass, unsigned (see `master-plan-v6-release-acceptance-addendum.md`); macOS/Linux not built (no native runners) |
| Independent review | PARTIAL | Red-team agent: no High/Critical, real Windows processes. Final acceptance reviewer: confirmed feature/sandbox/test claims; found one Medium (live vs local SHA-pinning claim — corrected here); security PARTIAL, governance PARTIAL, release NOT READY |

## Overall verdicts (separate standards)

1. **MASTER PLAN V6 — COMPLETE.** All 228 IDs retained and reconciled; implemented items verified; dormant/external/owner-gated items transparently identified; no regressions.
2. **SECURITY HARDENING — BLOCKED.** Windows now has genuine OS-enforced filesystem, process (Job Object) and network (AppContainer, non-elevated) isolation, all adversarially verified with real processes (`master-plan-v6-win-network-evidence.md`, `master-plan-v6-sandbox-verification.md`). Linux/macOS backends are integrated with fixed defects but native execution requires external runners; macOS read isolation is BLOCKED by a host `sandbox-exec` regression. Named external dependencies remain. (This section was corrected after the independent release audit found it stale.)
3. **REPOSITORY GOVERNANCE — BLOCKED.** C11.1 PASS; SHA pinning PASS on the local integration branch but not live (branch not pushed); branch protection, signed commits, admin enforcement and fork restrictions are blocked by the free private plan / personal account, and 2FA is owner-controlled.
4. **PRODUCTION RELEASE — BLOCKED.** The Windows installer was rebuilt from the final source with 7/7 integrity checks passing, but it is unsigned; there is no signing identity, no provider credentials, and no clean-VM/native-platform install validation. A completed feature matrix or a clean build integrity report is not used to claim release readiness.
