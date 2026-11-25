# Production Readiness Report — Keel backend, stabilization branch `stabilization/post-promotion-production-2026-11-25`

> **[SUPERSEDED — 2026-11-25]** The `<<CANDIDATE_HEAD_REFERENCE>>` placeholder,
> `f60b080` baseline and `18 external_validation_pending / 1 owner / 1 blocked`
> counts below are historical. At completion HEAD
> `35fb2b8abfd784393b2b252e2b9e2927aba817dd`, see
> `FINAL-PRODUCTION-READINESS-MATRIX.md` and `FINAL-RELEASE-COMPLETION-REPORT.md`.
> Retained unchanged as audit history; nothing was deleted.
>
**Authoritative branch:** `stabilization/post-promotion-production-2026-11-25`
**Current baseline tip (verified):** `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb`
**Exact final stabilization SHA:** `<<CANDIDATE_HEAD_REFERENCE — PLACEHOLDER, NOT YET FILLED>>` (see matrix §A)
**Documents reconciled here:** `BACKEND-OPERATIONS-RUNBOOK.md`, `BACKEND-DEPLOYMENT.md`,
`BACKEND-MONITORING.md`, `BACKEND-INCIDENT-RESPONSE.md`, `PRODUCTION-READINESS-MATRIX.md`,
and this report. **Scope:** backend/harness operations only — no frontend, no source,
test or workflow changes, no push.

> **Historical SHAs are NOT current evidence.** `CANDIDATE_HEAD…`, `e573273…`,
> `ac84fee…`, `fe6cdd…` and `ecba9d2b…` belong to the pre-promotion candidate family.
> Results recorded at those commits are labelled **[HISTORICAL]** below and do not
> certify the exact final stabilization SHA.

---

## 1. Honest verdict (provisional)

**Backend implementation is complete; backend local verification is historical, not
current; the backend is NOT production-ready; no desktop release is ready; no production
deployment has been completed.** These five states are tracked separately in §2.

There is no current evidence at the exact final stabilization SHA: no production
deployment, no signed/published installer, no clean-VM install/upgrade/rollback drill, no
native Linux/macOS run, and no live provider call. The stabilization baseline records all
six backend CI workflows failing on `origin/main` `9a63be92` with step logs no longer
retrievable (`POST-PROMOTION-STABILIZATION-BASELINE.md:9-20`). Consequently the matrix
records **0 `production_verified`** and **0 `pass locally`** gates until evidence at the
exact SHA is attached.

This is a **provisional** status, not a regression finding. The implementation itself was
completed and locally hardened in the prior candidate family; what is missing is current
evidence, not necessarily code changes.

---

## 2. The five distinct readiness states

| State | What it means | Current status | Evidence basis |
| --- | --- | --- | --- |
| **Backend implementation complete** | Source paths for the 20 mandatory gates exist and are wired | **YES** (code present at baseline tip) | Source anchors in `PRODUCTION-READINESS-MATRIX.md` §C; 865-ID registry unchanged |
| **Backend locally verified** | Source + tests execute green at the exact final SHA | **NOT CURRENTLY PROVEN** | [HISTORICAL] only: clean-venv `pass` at `ac84fee`, clean-HOME suite figures; baseline CI red on `9a63be92`; no `STAB-*-EVIDENCE.md` landed |
| **Backend production-ready** | All PR-01..PR-20 closed with current evidence | **NO** | 18 external_validation_pending, 1 owner_gated, 1 blocked (matrix §D) |
| **Desktop release-ready** | Signed, published, clean-VM-tested installers per OS | **NO** | Unsigned installer; macOS/Linux not built; signing identity absent |
| **Production deployment completed** | A live deployed instance / live provider call | **NO** | No deployment, push, publish or credential use in any evidence file |

Never collapse these into "done" or "production-ready". A passing evidence gate or 7/7
build integrity does not establish any of the last three states.

---

## 3. Matrix counts (authoritative, provisional)

| Classification | Count | Gates |
| --- | ---: | --- |
| `production_verified` | 0 | none |
| `pass locally` | 0 | none — exact final SHA not supplied; no current evidence |
| `external_validation_pending` | 18 | PR-01..PR-18 |
| `owner_gated` | 1 | PR-20 |
| `blocked` | 1 | PR-19 |
| **Total** | **20** | PR-01..PR-20 |

Two earlier, mutually contradictory count sets are now **historical/superseded**:
the matrix summary's "pass 17 / unverified 3 / blocked 2" (which listed only 13 pass IDs
and counted PR-19 twice), and this report's earlier "pass 13 / unverified 5 / blocked 2".
Both were keyed to historical candidate SHAs and disagreed with their own row verdicts.
See matrix §D.

---

## 4. Reconciled evidence links

### Operational documents produced here

| Document | What it establishes |
| --- | --- |
| `BACKEND-OPERATIONS-RUNBOOK.md` | Real start/stop, health, config, secrets, DB backup/restore/migration limits, logs, diagnostic export, worker recovery, provider config, incident levers — commands checked against the stabilization-tip CLI. |
| `BACKEND-DEPLOYMENT.md` | Clean setup, env validation, DB init, startup, readiness, shutdown, upgrade/recovery; separates backend deployment readiness from full installer release. |
| `BACKEND-MONITORING.md` | Real emitted signals, health vs readiness, redaction guarantees, bounded views; no invented exporter/dashboard. |
| `BACKEND-INCIDENT-RESPONSE.md` | Credential revocation, integration disable, unsafe-execution stop, log preservation, DB recovery, with explicit limits. |
| `PRODUCTION-READINESS-MATRIX.md` | Rebuilt 20-gate matrix with the five-state vocabulary and explicit SHA placeholder. |

### Evidence actually in the repo

| Area | Evidence | Status of that evidence |
| --- | --- | --- |
| PR-06 providers | `PROD-PROVIDER-EVIDENCE.md` | [HISTORICAL] offline injection only; no live call; live gap open |
| PR-09 / PR-17 rollback/upgrade | `PROD-ROLLBACK-EVIDENCE.md` | [HISTORICAL] six real-code drill tests; VM check 5 outstanding |
| PR-14 revocation | `PROD-REVOCATION-EVIDENCE.md` | [HISTORICAL] seven local tests; negative gap G1 (descriptor ≠ purge) |
| PR-16 clean setup | `PROD-CLEAN-SETUP-EVIDENCE.md` | [HISTORICAL] local `pass` at `ac84fee`; reproducibility disputed |
| PR-19 platforms | `PROD-PLATFORM-EVIDENCE.md` | [HISTORICAL] Windows scoped verified; Linux WSL2 scoped; macOS blocked |
| PR-20 supply chain | `PROD-SUPPLY-CHAIN-EVIDENCE.md` | Current pin count re-verified: 31/31 SHA refs; signing still absent |
| Baseline / CI | `POST-PROMOTION-STABILIZATION-BASELINE.md` | [CURRENT] main `9a63be92`; six workflows failing; logs gone |
| Other | `master-plan-v6-*.md`, `keel/docs/FINAL-RELEASE-OPERATIONS.md` | [HISTORICAL] candidate-family provenance |

No `STAB-*-EVIDENCE.md` file existed at the baseline tip. `POST-PROMOTION-STABILIZATION-REPORT.md`
is the structure for the lead to attach exact-SHA results as they land.

---

## 5. Reconciled history (two statements that looked contradictory)

**[HISTORICAL — stage 1.]** An independent acceptance pass
(`FINAL-RELEASE-ACCEPTANCE.md`) returned **BLOCK** for the pre-promotion candidate; the
mission rule that an `unverified` or `blocked` gate forbids promotion was applied, and
`main` was not modified by that operation. That verdict described the candidate at the
time, not the current branch.

**[HISTORICAL — stage 2.]** A later note recorded that the repository owner explicitly
authorized promotion after a final error sweep, with local gates PR-09, PR-14 and PR-16
closed by real tests and PR-06/PR-17/PR-19/PR-20 still externally blocked. The promotion
subsequently landed: commit `779ff942fff9dd106af7d7b3b4b35f95bfc5d2a4` is an ancestor of
the current `origin/main` `9a63be929d7b364411b856aaf61230817697c410`
(`POST-PROMOTION-STABILIZATION-BASELINE.md:4-5`).

**[CURRENT.]** Work now proceeds on `stabilization/post-promotion-production-2026-11-25`,
created from exact main SHA `9a63be92`, with the backend docs maintained in an isolated
worktree because the local main checkout has unrelated frontend work. No push, publish,
signing, credential use or deployment is part of this documentation reconciliation.

The two historical statements are therefore a sequence, not a contradiction; neither is
current evidence, and neither closes any gate in the matrix.

---

## 6. Known limits (evidence-backed; historical unless marked current)

1. **[CURRENT]** Exact final stabilization SHA not supplied; all six backend CI workflows
   fail on main `9a63be92` and step logs are unavailable.
2. **[HISTORICAL]** No production deployment, push, publish or signing in the candidate evidence.
3. **[HISTORICAL]** Windows 0.1.1 installer rebuilt with 7/7 local integrity checks but unsigned;
   macOS/Linux installers not built.
4. **[HISTORICAL]** No live provider evidence: no `KEEL_*` key configured, live checks SKIP.
5. **[HISTORICAL]** Native Linux/macOS gap: Linux backend scoped-verified on WSL2 6.6.87.2 only;
   macOS not run and read isolation BLOCKED by `sandbox-exec` SIGABRT.
6. **[HISTORICAL]** Six clean-VM external checks unrun; clean-checkout suite reproducibility disputed.
7. **[HISTORICAL]** DB migration forward-only (v1..v11); `SchemaApplySeam.apply()` is
   `NotImplementedError`; restoring older DB over newer schema is unsafe.
8. **[HISTORICAL]** Y3.9 sign-out/disconnect is descriptor + in-memory ledger, not a credential purge (gap G1).
9. **[HISTORICAL]** No bulk secret re-encryption CLI; rotation is provider-side plus manual re-entry.
10. **[HISTORICAL]** No alerting/exporter; proposed thresholds are unapproved.
11. **[HISTORICAL]** Raw `observability.jsonl` grows unbounded; only the diagnostic view is bounded to 20 errors.
12. **[HISTORICAL]** Some CLI paths default to relative `.keel`; set absolute `KEEL_STATE_DIR`.
13. **[HISTORICAL]** No SIGTERM handler, `keel stop`, or systemd unit; Ctrl+C is the graceful path.
14. **[HISTORICAL]** No `keel backup` CLI; backup/restore are capability or Python-API only.
15. **[HISTORICAL]** Owner gates open: signing identity, CI sign job, provider credentials,
    push/publish authorization, 2FA/branch protection, native runners.
16. **[CURRENT]** Action pinning is 31/31 SHA refs across eight workflows (was reported as
    30/30, 20 and 23 historically); pinning is necessary but not sufficient for release.

---

## 7. Proposed operational targets — NOT owner-approved

Recommendations only; not implemented, not default configuration, not accepted service levels.

| Proposed target | Requires |
| --- | --- |
| Poll `GET /api/health` every 30 s | Owner decision + external poller |
| Alert on `verify_chain().ok == false` | Owner decision |
| Alert at 2 failed starts (code threshold 3) | Owner decision |
| Alert on `health_snapshot().healthy == false` | Owner decision |
| Hourly review of `diagnostic_report()` error counts | Owner decision |
| Rotate `KEEL_TOKEN` via `POST /api/kill-switch` on suspected compromise | Owner decision + runbook adoption |
| Define retention for `observability.jsonl` | Owner decision + implementation |
| Run all six clean-VM checks per OS on exact SHA | Release owner + disposable VMs |
| Execute native Linux/macOS suites | Platform owner + runners |
| Provision signing identity + CI sign job with missing-secret hard failure | Owner |
| Configure live credentials and run `keel provider validate --live` | Provider owner |
| Implement or formally waive DB down-migration and credential purge | Owner decision |

---

## 8. Final statement

Backend operations are documented against real code at the stabilization tip, and the
five readiness states are tracked separately in §2. The implementation is complete,
local verification is historical rather than current, and the backend is **not**
production-ready. The 18 external-validation, 1 owner-gated and 1 blocked gates are named
with the exact artifact or owner action needed to close them. Nothing in these documents
should be read as a claim that Keel is a production-ready release on the evidence
available. When the lead supplies the exact final SHA and `STAB-*-EVIDENCE.md` files
land, re-run §3 counts and update `POST-PROMOTION-STABILIZATION-REPORT.md` before any
release decision.
