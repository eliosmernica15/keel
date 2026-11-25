# Post-promotion stabilization baseline

## Git state (verified by fetch)
- `origin/main`: `9a63be929d7b364411b856aaf61230817697c410`
- Prior backend promotion `779ff942fff9dd106af7d7b3b4b35f95bfc5d2a4` is an ancestor of main.
- Stabilization branch: `stabilization/post-promotion-production-2026-11-25` created from exact main SHA.
- Local main checkout has unrelated uncommitted frontend work; all operation work happens in an isolated worktree.

## GitHub Actions (verified via `gh run list`, 2026-11-25)
All six backend-related workflows FAIL on main SHA `9a63be92`:
| Run ID | Workflow | Jobs | Result |
|---|---|---|---|
| 45519531326 | Python tests | pytest (windows/macos/ubuntu) | failure |
| 45519531394 | Secret scan | – | failure |
| 45519531412 | Offline + license gates | – | failure |
| 45519531459 | Build desktop installers | validate-versions + downstream | failure |
| 45519531612 | Provider validation | – | failure |
| 45519543337 | Verify installed packages | trusted-trigger guard | failure |

Step-level logs are no longer retrievable from GitHub (`BlobNotFound`), so root causes must be reproduced locally from workflow definitions and source. No CI result is claimed fixed without a local reproduction and a fresh run.

## Known test baseline (historical, must be reproduced)
- Last pre-promotion full suite: 4437 passed / 5 failed / 51 skipped / 3707 subtests.
- 5 failures: `test_distribution_package.py` (2), `test_gap_closure.py` (2), `test_release_integrity.py` (1) — release-artifact dependent.
- Historical order/env pollution: provider API key leakage from tests; fixed by autouse env isolation, must re-verify.

## Known security findings to re-verify
- Workflow policy/audit symmetry, permission defaults, approval possession/TTL/consume, SSRF redirects/DNS pinning, filesystem containment, cross-process locks, event/ledger integrity, secret redaction.

## External blockers carried forward
Live provider credentials; signed clean-VM upgrade/rollback; native macOS runner (macOS 26 `sandbox-exec` SIGABRT); signing identity; GitHub Free private-repo branch protection; Vercel build-rate-limit (frontend hosting, separate from backend).

## Authoritative production gates
PR-01..PR-20 in `PRODUCTION-READINESS-MATRIX.md`; must be reconciled against exact final SHA, not stale candidate placeholders.
