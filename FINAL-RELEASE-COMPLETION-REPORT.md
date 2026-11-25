# FINAL RELEASE COMPLETION REPORT — reconciliation of PR-01…PR-20

**Completion HEAD:** `completion/final-production-release-2026-11-25 HEAD (resolve with `git rev-parse HEAD`)abfd784393b2b252e2b9e2927aba817dd` (branch
`agent/final-docs2`, worktree `…\worktree\final\docs2`).
**Date:** 2026-11-25. **Scope:** documentation only. No source, test, workflow or
frontend file was edited; no push, tag, secret write, signature, release or deployment.

## 1. Executive result

The 20 mandatory gates PR-01…PR-20 are now classified exactly once each, at one exact
tree, with one mutually exclusive vocabulary. The authoritative document is
`FINAL-PRODUCTION-READINESS-MATRIX.md`; this report is the index and the accounting
proof.

| Final class | Count | Gate IDs |
| --- | ---: | --- |
| `PASS_VERIFIED` | **0** | none |
| `PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED` | **16** | PR-01, 02, 03, 04, 05, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 18 |
| `EXTERNAL_PENDING` | **2** | PR-06 (live provider), PR-17 (signed clean-VM upgrade/rollback) |
| `OWNER_ACTION_REQUIRED` | **1** | PR-20 (signing identity, credentials, plan, authorization) |
| `BLOCKED` | **1** | PR-19 (no Darwin runner; macOS 26 `sandbox-exec` SIGABRT) |
| `NOT_IMPLEMENTED` | **0** | none |
| **Total** | **20** | each of PR-01…PR-20 appears once |

**Production readiness:** backend/harness implementation is complete and locally
verified at the final tree; production deployment is **not** authorized. The product is
not production-ready while PR-06, PR-17, PR-19 and PR-20 remain open. This is an
honest limitation, not a regression: no internally actionable HIGH/CRITICAL finding
remains, and the definitive full suite at the tree is `4610 passed, 0 failed,
54 skipped, 3707 subtests`.

## 2. What was reconciled

### 2.1 The `21` accounting error

`POST-PROMOTION-STABILIZATION-REPORT.md` §F reported `20` mandatory gates as
`17 passed locally + 2 external (PR-06, PR-17) + 1 owner (PR-20) + 1 blocked (PR-19) = 21`.
It never enumerated the 17 IDs. The two gates named as external were also inside the
"local pass" count, so they occupied two mutually exclusive classes simultaneously,
and PR-18 had no class. The only self-consistent partition of the 20-gate universe
with those four named exceptions is **16 + 2 + 1 + 1 = 20**:

- 16 gates are implemented and locally verified at the final tree with no external
  condition attached (PR-01…05, PR-07…16, PR-18);
- PR-06 and PR-17 need external runs (live provider call; signed disposable-VM run);
- PR-20 needs owner-only actions;
- PR-19 is blocked by a missing Darwin host and the macOS 26 SIGABRT.

The provisional `PRODUCTION-READINESS-MATRIX.md` §D count of
`18 external_validation_pending + 1 owner + 1 blocked = 20` was self-consistent but
was written before the STAB evidence landed and before the final SHA existed; its
`pass locally = 0` was a provenance consequence, not a finding of regression. At the
completion HEAD it refines to the table in §1.

### 2.2 Exact commit identity

- Completion HEAD `completion/final-production-release-2026-11-25 HEAD (resolve with `git rev-parse HEAD`)abfd784393b2b252e2b9e2927aba817dd`.
- The definitive suite was recorded at `c512f87971a02b05d9a9422338522f66495c0eeb`;
  `git diff --stat c512f87..completion/final-production-release-2026-11-25 HEAD (resolve with `git rev-parse HEAD`)` is empty, so the two trees are byte-identical and
  that result is evidence for the completion HEAD.
- `63ab72e452f9c78af46db55489ef8d9def02212c` is the historical independent-acceptance
  candidate (`PASS_WITH_EXTERNAL_LIMITATIONS`); five commits followed it, including the
  O(1) ledger-cache fix (`50e5be0…`) that closed the acceptance review's only
  BLOCKING performance item, and the owner-main merge (`788090c…`) that added the
  distribution/signing code.
- All older SHAs and candidate branch names are retained as **[HISTORICAL]** provenance
  in `FINAL-PRODUCTION-READINESS-MATRIX.md` §F; none was deleted.

### 2.3 Stale counts superseded

| Stale | Superseded value at `C0` |
| --- | --- |
| Suite counts 4214 / 4419 / 4437 / 4442 / 4459 / 4546 / 4557 / 4558 | **4610 passed / 0 failed / 54 skipped** |
| Action-pin counts 20 / 23 / 26 / 30 / 31 | **42/42** full-SHA `uses:` refs across 8 workflows (direct count: checkout 15, setup-python 13, download-artifact 5, setup-node 4, upload-artifact 3) |
| Pass counts 13/5/2, 17/3/2, 17/2/1/1=21, 18/1/1 | **16/2/1/1/0/0** in six mutually exclusive classes |
| "No `STAB-*-EVIDENCE.md` landed"; "pass locally = 0" | 14 STAB evidence files present; 20/20 gates locally covered at the final tree |
| "Linux WSL2 scoped with four conformance failures" | VERIFIED 16/16 + 9/1 with fail-closed skips disclosed (`STAB-PLATFORM-EVIDENCE.md`) |
| "No `keel backup` CLI" | CLI is `python -m keel.backups` (`backups.py:695`) |
| `FINAL-RELEASE-ACCEPTANCE.md` verdict `BLOCK` | Historical pre-promotion candidate verdict; superseded for the final tree by `FINAL-STABILIZATION-ACCEPTANCE.md` (`PASS_WITH_EXTERNAL_LIMITATIONS`) — still **not** a production approval |

The `>>>>>>> agent/stab-provider` literal in `STAB-PROVIDER-EVIDENCE.md:62` is recorded
as a documentation-hygiene defect; it changes no classification.

## 3. Six summaries (detail in matrix §D)

1. **Implementation completeness:** 19/20 mechanisms `FULL` at the final tree, 1
   `PARTIAL` (PR-19 macOS), 0 `NOT_IMPLEMENTED`. Documented residuals: PR-10/PR-15
   library-only runtime wiring (M-4), PR-13 M-2 CLI/TUI tier forwarding, PR-18 no
   exporter/pager, PR-08 forward-only with explicit snapshot restore.
2. **Local test verification:** definitive suite `4610/0/54 skipped` at a tree identical
   to the completion HEAD; governance gates re-run directly at `C0` (registry OK 865,
   strict backend gate 421/421 exit 0, license OK, dependency graph FRESH, version sync
   OK, YAML 8/8, pins 42/42); 0 gates rely solely on historical runs.
3. **Native platform:** Windows native VERIFIED (31/6 skips/0 failed), Linux native in
   WSL2 VERIFIED (16/16 + 9/1), macOS UNVERIFIED/BLOCKED (no runner; macOS 26
   read-isolation SIGABRT).
4. **External provider:** 0 real provider requests; all validation offline and synthetic;
   truthful SKIP/FAIL semantics tested; PR-06 `EXTERNAL_PENDING`; PR-14 live revoke is
   a sub-check of the same credential action, not a second external gate.
5. **Trusted signing/governance:** hard-fail Ed25519 gate implemented and tested, 0 keys
   configured, 0 `.sig` files, 0 signed manifests, OS signing not wired, 42/42 SHA pins,
   GitHub Free branch protection unavailable → PR-20 `OWNER_ACTION_REQUIRED`.
6. **Production deployment:** 0 deployed instances, 0 published releases, all
   `download.json` channels `url: null`/`available: false`, no signed clean-VM run →
   `PASS_VERIFIED = 0`.

## 4. Documents produced by this reconciliation

| File | Purpose |
| --- | --- |
| `FINAL-PRODUCTION-READINESS-MATRIX.md` | Authoritative 20-row matrix, vocabulary, six summaries, totals, contradiction register |
| `FINAL-RELEASE-COMPLETION-REPORT.md` | This report — accounting proof and index |
| `FINAL-OWNER-ACTIONS.md` | The five genuine external actions (A1–A5), exact steps and what each unlocks; nothing else |
| `FINAL-RELEASE-ARTIFACTS.md` | Actual tracked `0.1.1` metadata, real-but-limited checksums, honest signature status, no invented links |
| `FINAL-INDEPENDENT-ACCEPTANCE.md` | Placeholder shell for the lead/reviewer; few clearly marked blanks, no invented verdict |
| `PRODUCTION-READINESS-MATRIX.md`, `PRODUCTION-READINESS-REPORT.md`, `POST-PROMOTION-STABILIZATION-REPORT.md`, `FINAL-RELEASE-ACCEPTANCE.md` | Appended with explicit `[SUPERSEDED]` pointers; original audit text preserved unchanged |

## 5. Honest closing statement

No gate was marked passed to make the totals agree. The change is a re-partition of
20 real gates into mutually exclusive classes at one exact SHA, with historical
evidence labelled and retained. Engineering cannot close PR-06, PR-17, PR-19 or PR-20:
the required credentials, Darwin host, signing identity, plan entitlement and
deployment authorization are listed in `FINAL-OWNER-ACTIONS.md` and none was performed
here. Until those actions are taken and a fresh acceptance review is written at the
promoted SHA, promotion remains unauthorized.

## Authoritative final full-suite run (completion branch)

Command (clean local HOME, from `keel/`):
`python -m pytest -q -o faulthandler_timeout=120`

```
4724 passed, 54 skipped, 3707 subtests passed in 801.99s (0:13:21)
```

0 failed. Prior figures (4610, 4628, 4630, 4722) are historical runs at earlier commits.
