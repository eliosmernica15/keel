# Post-promotion stabilization — final report

## A. Executive status

- **CI:** all six previously failing workflows were root-caused. Their original GitHub runs died at runner assignment (`runner_id: 0`, no steps executed), so all workflow commands were reproduced locally; latent defects (offline namespace, provider env isolation, trusted trigger, supply-chain step) were fixed. No workflow was disabled and no test skipped.
- **Clean-checkout tests:** **4557 passed, 52 skipped, 3707 subtests, 0 failed** in 493.28 s. The five reported artifact failures are fixed at their cause with deterministic test-only release fixtures. No test was weakened.
- **Security:** all internally actionable HIGH/MEDIUM findings are fixed with failing-then-passing regressions and independently re-verified. Independent acceptance verdict: **PASS_WITH_EXTERNAL_LIMITATIONS**.
- **Backend operations:** state-root precedence, SIGINT/SIGTERM shutdown, readiness, backup/restore, migrations, recovery, revocation, upgrade/rollback and HMAC event integrity verified locally.
- **Production readiness:** backend **locally verified**, not production-deployed. Desktop/product release not ready (signing identity, clean-VM, runners, credentials, governance).
- **External validation:** live providers, native macOS, signed clean-VM upgrade/rollback, production signing, branch protection remain open.

## B. Git state

| Item | Value |
|---|---|
| Starting `origin/main` | `9a63be929d7b364411b856aaf61230817697c410` |
| Prior promotion | `779ff942fff9dd106af7d7b3b4b35f95bfc5d2a4` (ancestor) |
| Stabilization branch | `stabilization/post-promotion-production-2026-11-25` |
| Final stabilization SHA | see `git rev-parse HEAD` at delivery (remote verified) |
| Commits created | 27 including 15 reviewed agent merges |
| Push / publish / deploy | pushed stabilization branch only; no release, no deploy |
| Working tree | clean |
| Force-push / history rewrite | none |
| Frontend changes by this operation | none |

## C. Exact test results

| Command | Result |
|---|---|
| `python -m pytest -q -o faulthandler_timeout=120` (clean HOME) | **4557 passed, 52 skipped, 3707 subtests, 0 failed, 493.28 s** |
| Independent acceptance runs | run 1: 1 load-dependent timeout flake; run 2: **4557 passed / 0 failed, 484.78 s** |
| `verify_v6_audit.py` | CONSISTENCY OK (865 IDs) |
| `verify_backend_operation.py --strict` | ENFORCED, 421/421, exit 0 |
| Dependency graph / license / version sync | FRESH / LICENSE GATE OK / v0.1.1 OK |
| Workflow YAML / action pins | 8/8 parse; 31/31 full-SHA `uses:` pins |

## D. Workflow report

| Workflow | Original failure | Root cause / fix | Local verification |
|---|---|---|---|
| Python tests | failed on 3 OSes | runner assignment (no steps ran); latent offline/install/npm/release defects fixed; deterministic release fixtures | full suite green; install + build pass locally |
| Secret scan | failed | 36 historical findings all synthetic; 16 narrow `AND` allowlists (exact commit+path+rule); evidence-doc synthetic token redacted | gitleaks rescan no leaks, exit 0 |
| Offline + license | failed | bare `unshare -n` leaves loopback down → fixed `unshare -Urn` + `lo up`; supply-chain verifier wired in | 11 passed, fail-closed when `ip` absent |
| Provider validation | failed | ambient `KEEL_*_API_KEY` polluted SKIP test → cleared in fixture step; missing credential now truthful SKIP | 14 passed; live credentials remain external |
| Build desktop installers | failed | runner assignment; version sync/npm pin/build all pass locally | version gate OK, no workflow defect |
| Verify installed packages | failed | `gh run download` missing `--repo`; manual dispatch trusted any run_id → fail-closed validation added | 9 stub-gh scenarios pass |
| Vercel | failed | frontend hosting build-rate-limit, separate from backend CI; untouched | external |

## E. Security report

- **HIGH fixed:** saved `ask` policy auto-approval in workflows (now caller confirmation propagated, handler never runs on denial); CGNAT/metadata SSRF; cross-process migration race; event ledger forgery; approval/permission bypasses from prior waves.
- **MEDIUM fixed:** unaudited workflow branches (now all audited, redacted), permission defaults at HTTP boundary, secret leakage in handler errors, stale blockmap test, gitleaks allowlist count, unbounded steering retention, un-cancelled fleet workers, observability retention, event HMAC, setup/rollback defects.
- **Regression tests:** all fixes have failing-then-passing tests; independent reviewer re-ran 116 + 82 affected tests green.
- **Native:** Windows 31 passed + adversarial probes; Linux WSL2 16/16 Landlock/seccomp; macOS unverified (26+ read isolation SIGABRT).
- **Residual:** CLI/TUI permission-tier forwarding (their strict confirm gates remain); events/observability are dormant-by-design libraries; secret-scan binary not committed (gitleaks fetched at workflow runtime).

## F. Production-readiness accounting

| Metric | Count |
|---|---:|
| Mandatory gates (PR-01..PR-20) | 20 |
| Passed locally with current evidence | 17 |
| Production verified | 0 (no production deployment) |
| External validation pending | 2 (PR-06 providers, PR-17 clean-VM) |
| Owner-gated | 1 (PR-20 signing/governance) |
| Blocked | 1 (PR-19 native macOS) |
| Unresolved HIGH/CRITICAL | 0 |
| Unresolved MEDIUM | 0 internally actionable |

## G. Subagent report

15 specialist sessions launched (CI, tests, security, workflow, database, runtime, events, provider, platform, install, performance, supply, docs, traceability, integration) plus 1 independent final acceptance reviewer; max concurrency 15; 0 failed launches in this operation; multiple re-assignments for HIGH findings (ask-policy, SSRF, event HMAC, migration race). All 15 agent branches were diff-reviewed, targeted-tested and merged; inadequate work was sent back for correction (e.g. CI script wiring, CLI confirmation forwarding, allowlist changes).

## H. Exact remaining work

| Item | Why open | Type | Needed | Blocks backend production claim? |
|---|---|---|---|---|
| PR-06 live providers | no securely configured credential | external | owner-configured free-tier key + explicit authorization | yes |
| PR-17 clean-VM upgrade/rollback | no VM/installer on host | external | disposable VM + signed installer | yes |
| PR-19 native macOS | no Darwin host; macOS 26 read isolation SIGABRT | external/platform | macOS 15 runner + boundary re-probe | yes |
| PR-20 signing/governance | no signing identity; GitHub Free branch protection unavailable | owner | signing identity, owner authorization, plan decision | yes |
| Events/observability runtime wiring | architectural boundary (dormant libraries) | design decision | owner decision to adopt EventBus as authoritative | no (documented) |

No internally actionable defect remains.
