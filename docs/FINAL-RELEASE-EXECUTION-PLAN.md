# Final release execution plan — authoritative remaining-work inventory

Starting state (verified by fetch, not assumed): `origin/main` = `bcc91230fee72d41b7f267155156b6528e22a1c8`; PR #19 and #20 MERGED; completion commit `75d59260` is an ancestor of main; open PR #15 is owner macOS evidence. Execution branch: `release/final-execution-2026-11-25` created from exact main.

## Classification legend
- REPOSITORY_ACTIONABLE — can be fixed in code/config/docs and verified locally
- AUTOMATABLE_WITH_AVAILABLE_RESOURCES — implementable and locally reproducible now
- OWNER_ACTION_REQUIRED / EXTERNAL_* — genuinely needs owner credential/identity/host/billing
- ALREADY_VERIFIED — real evidence at current tree; recheck, don't redo

| ID | Requirement | Current status | Source/test | Missing work | Assigned | Acceptance | Validation command | Result | Evidence | Classification |
|---|---|---|---|---|---|---|---|---|---|---|
| R-01 | Recheck main/PR ancestry | done above | git/gh | none | lead | verified state recorded | `git rev-parse origin/main`, `gh pr view` | verified | this file | ALREADY_VERIFIED |
| R-02 | Master execution checklist | not created | this file | create + maintain | lead | every row classified | file review | pending | this file | REPOSITORY_ACTIONABLE |
| R-03 | GitHub Actions billing blocker | external; runs die at runner assignment | FINAL-CI-DIAGNOSIS.md | owner billing fix; no repo change can start runners | agent-ci | exact annotation + runbook | `gh api .../jobs` | external | FINAL-CI-DIAGNOSIS.md | EXTERNAL_ACCOUNT_OR_BILLING_REQUIRED |
| R-04 | Workflow code-side defects | previously fixed | 9 workflows, 42 SHA pins | recheck permissions/triggers/artifact trust | agent-ci | local reproduction green | YAML parse + local commands | pending | FINAL-CI-EVIDENCE.md | REPOSITORY_ACTIONABLE |
| R-05 | Windows native release | verified scoped | FINAL-PLATFORM-EVIDENCE.md | none; recheck real-process tests | agent-win | 31 sandbox + lifecycle pass | pytest Windows suites | pending | FINAL-PLATFORM-EVIDENCE.md | ALREADY_VERIFIED |
| R-06 | Linux legacy `_seccomp_deny_network` conformance defect | documented | sandbox_conformance.py | investigate/fix if on supported path | agent-linux | 4 conformance failures resolved or justified | WSL pytest + probes | pending | FINAL-PLATFORM-EVIDENCE.md | REPOSITORY_ACTIONABLE |
| R-07 | macOS native | no Darwin host; PR #15 open | FINAL-PLATFORM-EVIDENCE.md | Darwin runner + PR#15 disposition | agent-mac | genuine macOS 15 tests | GH macOS runner | external | FINAL-PLATFORM-EVIDENCE.md | EXTERNAL_HOST_REQUIRED |
| R-08 | Provider offline integration | verified | FINAL-PROVIDER-EVIDENCE.md | recheck harness safeguards | agent-provider | 139 tests; no paid fallback | pytest | pending | FINAL-PROVIDER-EVIDENCE.md | ALREADY_VERIFIED |
| R-09 | Live provider validation | no credential | scripts/verify_live_provider.py | owner free-tier credential + opt-in | agent-provider | one bounded request | harness with flags | external | FINAL-PROVIDER-EVIDENCE.md | EXTERNAL_CREDENTIAL_REQUIRED |
| R-10 | Signing mechanics | verified with ephemeral keys | FINAL-SIGNING-EVIDENCE.md | trusted identity | agent-signing | fail-closed modes + rotation | pytest | pending | FINAL-SIGNING-EVIDENCE.md | ALREADY_VERIFIED |
| R-11 | Trusted distribution signing | no real identity | FINAL-SIGNING-EVIDENCE.md | Authenticode/Developer ID/notary | agent-signing | signed installer verified | owner CI secrets | external | FINAL-SIGNING-EVIDENCE.md | EXTERNAL_IDENTITY_REQUIRED |
| R-12 | Install/upgrade/rollback | 13/13 local scenarios | FINAL-INSTALL-EVIDENCE.md | clean-VM drill | agent-install | local scenarios green; VM pending | pytest harness | pending | FINAL-INSTALL-EVIDENCE.md | ALREADY_VERIFIED / EXTERNAL_HOST_REQUIRED |
| R-13 | Database/state reliability | verified | FINAL-DATABASE-EVIDENCE.md | none | agent-db | concurrency + backup green | pytest | pending | FINAL-DATABASE-EVIDENCE.md | ALREADY_VERIFIED |
| R-14 | Security adversarial | verified; no HIGH | FINAL-SECURITY-VERIFICATION.md | recheck after final changes | agent-security | no HIGH reproduced | probes + pytest | pending | FINAL-SECURITY-VERIFICATION.md | REPOSITORY_ACTIONABLE |
| R-15 | EventBus/observability | integrated | FINAL-EVENTS-EVIDENCE.md, FINAL-OBSERVABILITY-EVIDENCE.md | recheck evidence≠authorization | agent-events | probes | pytest | pending | evidence docs | ALREADY_VERIFIED |
| R-16 | Release artifacts/metadata | stale published v0.1.1 vs tracked PKG/DEB/RPM | FINAL-RELEASE-ARTIFACTS.md | reconcile manifest/download metadata to real files | agent-artifacts | no nonexistent assets advertised; checksums real | manifest validation | pending | FINAL-RELEASE-ARTIFACTS.md | REPOSITORY_ACTIONABLE |
| R-17 | Owner action runbook | required path not present | docs/FINAL-OWNER-ACTIONS.md exists but target path differs | create docs/FINAL-OWNER-ACTION-RUNBOOK.md | agent-docs | A1–A5 exact steps + cost | file review | pending | new doc | REPOSITORY_ACTIONABLE |
| R-18 | Gate matrix reconciliation | 16+2+1+1=20 | FINAL-PRODUCTION-READINESS-MATRIX.md | update to final SHA/evidence | agent-docs | mutually exclusive; exact evidence | file review | pending | matrix | REPOSITORY_ACTIONABLE |
| R-19 | Full suite reproducibly green | 4724 passed at completion HEAD | pytest evidence | run on final main-derived candidate | agent-tests | 0 unexpected failures | pytest -q | pending | new evidence | REPOSITORY_ACTIONABLE |
| R-20 | Independent acceptance | prior BLOCK resolved | FINAL-INDEPENDENT-ACCEPTANCE.md | fresh independent review | agent-accept | PASS / PASS_WITH_EXTERNAL_LIMITATIONS | reviewer report | pending | new report | REPOSITORY_ACTIONABLE |
| R-21 | GitHub delivery | PR #19/#20 merged | git/gh | new PR for this operation | lead | merged + ancestor + clean tree | gh pr merge + verify | pending | final report | REPOSITORY_ACTIONABLE |
