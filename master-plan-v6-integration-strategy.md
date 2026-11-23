# Master Plan v6 — PR-safe integration strategy

Baseline: `cc6240e4bd707b05bfeb650ff57c9e808ab605b1` on `integration/v6-completion` (verified).
Working branch: `final/v6-production` (created from `cc6240e`; local only, **not pushed**).
Remote main: `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` (live-verified). Divergence: local 39 ahead / 33 behind, merge base `107a427`.

## Constraints honoured

- No reset, no force-push, no history rewrite, no branch deletion.
- No direct push to `main`; no release, deploy, or publication.
- The complete local implementation and the remote-only work are both preserved.
- Each agent works in an isolated worktree on its own branch; no shared implementation files are edited concurrently.
- The lead reviews each diff and re-runs tests before merging; an agent's self-report is not sufficient.

## Divergence disposition

The remote-only history (origin/main) contains 33 commits of security/sandbox/CI work from PRs #1–#13. The local history contains the feature-completion, audit, and completion-operation work. Rather than merging the two histories wholesale (which would be a large, hard-to-review merge and could overwrite one side), required remote changes are **deliberately ported** as explicit cherry-picks/checkouts with review:

| Remote change | Disposition | Reason |
| --- | --- | --- |
| `sandbox_windows.py`, `sandbox_linux.py`, `sandbox_macos.py`, `os_sandbox.py`, conformance suite | ported in prior operation (`4c74ce3`, `5cd729a`) | genuine native backends |
| Multi-path sandbox escape, policy bypass fields, atomic writes, confirmation forwarding (`67db8e5`) | ported this operation (sandbox_policy/webapp/native_isolation + regression suites) | genuine security fixes; policy-enforcement half ported by secrets agent |
| `lifecycle.yml`, `provider-validation.yml`, `signing-readiness.yml` | ported this operation with SHA pinning | genuine CI validation, honest credential reporting |
| `SIGNING-PREPARATION.md`, research docs | signing prep ported; redundant research docs not ported | avoid duplicate evidence |
| Stale `os_sandbox.py` BPF (inverted jumps) | **not** ported | local branch has the corrected filter |
| Stale `mcp.py` version `0.1.0a0` | **not** ported | local branch uses canonical `__version__` |

## Integration sequence (in progress)

1. Verify baseline — done (`cc6240e`, clean tree, live remote re-checked).
2. Four-agent capacity pilot — done (3 of 4 produced commits; win-network still working).
3. Expand in waves — 12 agents launched across 3 waves (see `master-plan-v6-agent-commit-index.md`).
4. Review and merge agent branches individually — in progress; product-defect branch merged (`5362d91`).
5. Resolve shared-interface changes centrally — capability_registry.py changes (Duet score/evidence, Fleet bus wiring) queued to the exec-paths agent to avoid concurrent edits.
6. Run the complete suite on the integrated branch — in progress.
7. Independent adversarial review — red-team and acceptance agents from the prior operation are preserved; this operation's reviews are pending agent results.
8. Fix defects and retest — product defects fixed; more pending.
9. Rebuild final installers — Windows rebuilt in prior operation from `cc6240e`; will re-verify hash after final integration commits.
10. Final acceptance and reviewable PR preparation — pending.

## PR preparation (when owner authorizes)

- Base: `origin/main` (`ecba9d2`). Head: `final/v6-production` (or a dedicated `integration/v6-final` branch).
- Because histories diverged, open the PR with an explicit description listing deliberately ported changes; do not use force-push.
- Required checks on the PR: full pytest, native build matrix, gitleaks, version sync, artifact integrity.
- Do not publish a release or merge until the owner authorizes.

## Current status

No push has been performed. The branch is local and reviewable. All commits are preserved.
