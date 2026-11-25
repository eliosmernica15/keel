# Production Readiness Report — Keel backend candidate `CANDIDATE_HEAD`

**Candidate SHA:** `CANDIDATE_HEAD78f56062db3b13d3db941ac2cf2a641a3`
**Branch:** `agent/prod-ops` (worktree `.../worktree/production/ops`)
**Documents produced:** `BACKEND-OPERATIONS-RUNBOOK.md`, `BACKEND-DEPLOYMENT.md`,
`BACKEND-MONITORING.md`, `BACKEND-INCIDENT-RESPONSE.md`,
`PRODUCTION-READINESS-MATRIX.md` (this file + the matrix are the consolidated verdict).
**Scope:** backend/harness operations only. No frontend, no source changes, no push.

---

## 1. Honest verdict

**The backend is deployable and locally verified on Windows; the candidate is NOT a
production release.** There is no production deployment, no signed or published
installer, no clean-VM install/upgrade/rollback evidence, no native Linux/macOS
execution, and no live provider call. The authoritative project documents state this
plainly: `keel/docs/FINAL-RELEASE-OPERATIONS.md:12-18` ("Not a production release") and
`master-plan-v6-final-report.md:158` ("PRODUCTION RELEASE — BLOCKED").

The matrix therefore records **0 `production_verified`** gates. A completed feature
matrix or a 7/7 build-integrity report must not be used to claim release readiness
(`master-plan-v6-final-report.md:158`).

---

## 2. Evidence links (consolidated)

### Operational documents produced here

| Document | What it establishes |
| --- | --- |
| `BACKEND-OPERATIONS-RUNBOOK.md` | Real start/stop, health, config, secrets, DB backup/restore/migration/rollback limits, log locations, diagnostic export, worker recovery, provider config, incident levers, common failures — every command traced to code. |
| `BACKEND-DEPLOYMENT.md` | Clean setup, dependency install, config generation, env validation, DB init, startup, readiness, graceful shutdown, upgrade, recovery; explicit separation of backend deployment readiness from full installer release. |
| `BACKEND-MONITORING.md` | Real signals, health vs readiness, alert-worthy conditions, redaction guarantees, bounded views; no invented exporter or dashboard. |
| `BACKEND-INCIDENT-RESPONSE.md` | Credential revocation, integration disable, stopping unsafe execution, log preservation, DB recovery, secret rotation, with explicit limits. |
| `PRODUCTION-READINESS-MATRIX.md` | 20 mandatory gates with source/code/test/operational/security/platform/status evidence. |

### Authoritative evidence consumed

| Area | Link |
| --- | --- |
| Release operations, exact CI commands, signing/provider/owner gates | `keel/docs/FINAL-RELEASE-OPERATIONS.md` |
| Final status vocabulary and overall verdicts | `master-plan-v6-final-report.md:108-158` |
| Test evidence and definitive suite | `master-plan-v6-test-evidence.md:200-210` (4214 passed / 48 skipped / 3707 subtests / 0 failed, 571.95 s, clean local HOME) |
| Release audit / reproducibility caveat | `master-plan-v6-release-audit.md:140`; `REVIEW-FINAL-QUALITY.md:134` |
| Backend evidence gate | `scripts/verify_backend_operation.py:1-34`, `448-475` (20 modules, 421 attributed IDs, 865 features; reported-only unless `--strict`) |
| Version consistency | `keel/scripts/check_version_sync.py`; `keel/pyproject.toml:7`; `keel/src/keel/__init__.py:3` (all `0.1.1`) |
| Windows sandbox (adversarial, real processes) | `master-plan-v6-win-network-evidence.md`; `master-plan-v6-sandbox-verification.md`; `FINAL-RELEASE-OPERATIONS.md:172` |
| Platform blockers | `master-plan-v6-platform-compatibility.md:13`; `FINAL-RELEASE-OPERATIONS.md:173-176` |
| Provider credentials (names only) | `FINAL-RELEASE-OPERATIONS.md:181-201`; `keel/src/keel/provider_validation.py:40-58`, `106-132` |
| Secrets policy | `master-plan-v6-secrets-policy-evidence.md`; `keel/src/keel/secret_store.py`; `keel/src/keel/secret_providers.py` |
| DB persistence and recovery | `master-plan-v6-db-persistence-evidence.md`; `master-plan-v6-recovery-evidence.md`; `keel/src/keel/fleet/db.py:237-365`; `keel/src/keel/backups.py:119-235` |
| Observability and redaction | `master-plan-v6-reliability-contracts-evidence.md`; `keel/src/keel/backend_observability.py`; `keel/src/keel/diagnostics.py`; `keel/src/keel/redaction.py` |
| Config and execution policy | `master-plan-v6-config-contracts-evidence.md`; `keel/src/keel/settings.py`; `keel/src/keel/exec_policy.py`; `keel/src/keel/policy_enforcement.py` |

### Matrix counts

| Classification | Count |
| --- | --- |
| pass | 13 |
| unverified | 5 |
| blocked | 2 |
| production_verified | 0 |
| **Total mandatory gates** | **20** |

Unverified: PR-06 (live providers), PR-09 (rollback drill), PR-14 (credential purge /
live revoke), PR-16 (clean-checkout reproducibility), PR-17 (clean-VM upgrade/recovery).
Blocked: PR-19 (native Linux/macOS), PR-20 (signing, live providers, governance/release
authorization).

---

## 3. Known limits (evidence-backed)

1. **No production deployment.** No push, publish, signing, or deployment was performed
   (`FINAL-RELEASE-OPERATIONS.md:271-273`).
2. **Unsigned installer.** Windows 0.1.1 installer rebuilt from final source with 7/7
   local integrity checks but unsigned; macOS/Linux installers not built
   (`FINAL-RELEASE-OPERATIONS.md:96-126`, `168-178`).
3. **No live provider evidence.** No `KEEL_*` key configured; `keel provider validate`
   reports SKIP for live checks without `--live` plus credentials
   (`master-plan-v6-final-report.md:143`; `provider_validation.py:106-132`).
4. **Native platform gap.** Linux Landlock/seccomp and macOS Seatbelt backends are
   integrated but not executed on this Windows host; macOS 26 read isolation is BLOCKED
   by `sandbox-exec` SIGABRT (`FINAL-RELEASE-OPERATIONS.md:173-174`).
5. **Clean-VM checks unrun.** All six external checks (install, startup, backend
   shutdown, uninstall, upgrade+rollback, signed launch) are reported UNVERIFIED
   (`FINAL-RELEASE-OPERATIONS.md:241-249`).
6. **Suite reproducibility disputed.** The release audit records a genuine committed
   defect and that `python -m pytest -q` on a clean checkout was red on the audited HEAD;
   a "definitive final suite" is not reproducible there
   (`master-plan-v6-release-audit.md:140`, `REVIEW-FINAL-QUALITY.md:134`).
7. **DB migration is forward-only.** Schema versions 1..11 apply on connect; there is no
   down-migration, and `SchemaApplySeam.apply()` is `NotImplementedError`
   (`fleet/db.py:258-365`, `config_contracts.py:799-804`). Restoring an older DB over a
   newer schema is unsafe.
8. **Sign-out/disconnect is a descriptor, not a purge.** `build_revocation()` and
   `RevocationLedger.apply()` are pure bookkeeping; they do not delete stored credentials
   (`config_contracts.py:888-967`).
9. **No secret rotation CLI.** Encryption/decryption helpers exist but there is no bulk
   re-encryption command (`secret_store.py:111-131`); rotation requires provider-side
   action and manual re-entry.
10. **No alerting stack.** Signals exist (event log counts, chain status, failed-start
    state, gateway ticks, provider checks) but no exporter, pager, or policy is
    implemented (`BACKEND-MONITORING.md`).
11. **Unbounded raw log.** `observability.jsonl` is append-only with no automatic
    rotation; only the diagnostic view is bounded to 20 recent errors
    (`backend_observability.py:45`, `551-566`).
12. **State-root inconsistency.** Some CLI paths default to relative `.keel`, others to
    `~/.keel`; an absolute `KEEL_STATE_DIR` is required for coherent operations
    (`cli/main.py:286-287`, `827-847`, `893`; `settings.py:475-476`).
13. **No service-management shutdown.** Ctrl+C is the graceful path; there is no
    SIGTERM handler, `keel stop`, or systemd unit (`webapp.py:1321-1327`).
14. **No `keel backup` CLI.** Backup/restore are capability or Python-API only
    (`capability_registry.py:1798-1820`).
15. **Owner gates remain open.** C11.2 repository security, signing identity, push/publish
    authorization, 2FA, native runners (`FINAL-RELEASE-OPERATIONS.md:262-273`).

---

## 4. Proposed operational targets — NOT owner-approved

These are recommendations only. They are **not implemented, not default configuration,
and not accepted service levels**; no owner has approved them.

| Proposed target | Why | Requires |
| --- | --- | --- |
| Liveness poll of `GET /api/health` every 30 s | Cheap token-gated check | Owner decision + a poller outside this codebase |
| Alert on `verify_chain().ok == false` | Fail-closed integrity signal already in code | Owner decision |
| Alert at 2 consecutive failed starts (code threshold 3) | Early warning before rollback advice | Owner decision |
| Alert on `health_snapshot().healthy == false` | Real module import failure | Owner decision |
| Hourly review of `diagnostic_report()` error counts | Bounded view is last 20 errors | Owner decision |
| Rotate `KEEL_TOKEN` via `POST /api/kill-switch` on suspected client compromise | Real revocation lever | Owner decision + runbook adoption |
| Define a retention window for `observability.jsonl` | No rotation exists | Owner decision + implementation |
| Run clean-VM install/startup/shutdown/uninstall/upgrade/rollback per OS before any release | Six external checks are UNVERIFIED | Release owner + disposable VMs |
| Execute Linux and macOS native sandbox and installer suites | Platform gates blocked | Platform owner + runners |
| Provision signing identity and a CI sign job with missing-secret hard failure | Installers are unsigned | Owner |
| Configure live provider credentials via masked secrets and re-run `keel provider validate --live` | No live provider evidence | Provider owner |
| Implement or formally waive DB down-migration and real credential purge | Known limits 7 and 8 | Owner decision |

---

## 5. Final statement

Backend operations are **documented against real code**, and the local Windows
candidate satisfies the 13 `pass` gates with source, test and operational evidence.
The five `unverified` and two `blocked` gates are named with the exact artifact or
owner action needed to close them. Nothing in these six documents should be read as a
claim that Keel `CANDIDATE_HEAD` is a production-ready release: on the evidence available it
is not.

## FINAL PROMOTION DECISION — NOT PROMOTED TO MAIN

Authoritative candidate: `release/backend-production-readiness-2026-11-24-v2`
(frontend from concurrent user work was excluded; the earlier candidate branch remains
untouched). `origin/main` was not modified and remains `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee`.

Independent release acceptance (`FINAL-RELEASE-ACCEPTANCE.md`) returned **BLOCK**. Its
scope and temp-artifact findings were closed in v2; its matrix finding stands:

| Classification | Count | Gates |
|---|---:|---|
| pass | 13 | PR-01..05, 07, 08, 10..13, 15, 18 |
| unverified | 5 | PR-06 live providers, PR-09 rollback drill, PR-14 credential revocation, PR-16 clean setup, PR-17 upgrade/recovery |
| blocked | 2 | PR-19 native Linux/macOS + macOS 26 read isolation, PR-20 governance/signing/release authorization |
| production_verified | 0 | no deployed production instance or live evidence |

The mission rule says a gate marked `unverified` or `blocked` forbids promotion. Therefore
**main was NOT modified**. No force-push, no visibility/license change, no paid service,
no credentials, no history rewrite.

Verdict: **IMPLEMENTATION PRODUCTION-HARDENED — PROMOTION BLOCKED BY UNVERIFIED MANDATORY GATES**.

Final full suite on candidate: 4419 passed / 8 failed / 51 skipped / 3707 subtests — 2 load-dependent tests pass in isolation; 6 require untracked generated release artifacts or downloaded plan docs. See `master-plan-v6-test-evidence.md`.

What remains to authorize promotion: free/native Linux and macOS runner execution (macOS
read isolation currently blocked by `sandbox-exec` SIGABRT), a disposable free-tier provider
credential for live smoke tests, a clean-VM upgrade/rollback drill, a real credential-revocation
round trip, clean-environment setup evidence, a signed installer and owner release authorization,
and remote branch protection on a plan that supports it (currently GitHub Free private repo
cannot enforce it — documented owner exception, not bypassed).

All internally actionable HIGH/MEDIUM findings from the architecture, security, database,
reliability, provider, tool, MCP, API, platform, performance, observability, supply-chain,
and requirement audits were fixed with failing-then-passing regression tests and re-reviewed.

## Owner-authorized promotion after final checks

The repository owner explicitly authorized promotion to `main` after a final error sweep.
Locally achievable gates PR-09 (rollback drill), PR-14 (local credential revocation),
PR-16 (clean setup) and workflow-audit defects were closed with real tests. PR-06 (live
providers), PR-17 (signed clean-VM upgrade), PR-19 (native macOS) and PR-20 (signing
identity) remain externally blocked and are recorded, not concealed. Promotion proceeds
under this explicit owner authorization; `main` is updated only after the final gates
and remote SHA verification.
