# FINAL-STABILIZATION-ACCEPTANCE.md — independent final acceptance review

> Read-only review of the actual candidate tree (no source was edited). Reviewer worktree:
> `C:\Users\Admin\.local\share\opencode\worktree\stab\accept`, branch `agent/stab-accept`.
> Candidate: `63ab72e452f9c78af46db55489ef8d9def02212c`
> on `stabilization/post-promotion-production-2026-11-25`.

## VERDICT: PASS_WITH_EXTERNAL_LIMITATIONS

No unresolved HIGH/CRITICAL **security or correctness** finding blocks this candidate: the
red-team HIGH ask-policy bypass (H-1) and the database HIGH migration race are fixed, and I
reproduced the fixes myself. All governance gates re-run locally pass. The candidate is
**not** production-ready and must not be promoted as such: 18 gates remain
`external_validation_pending`, 1 `owner_gated` and 1 `blocked` (matrix §D), and several
documentation artifacts were never finalized at the exact final SHA (§7). The open items are
external/platform/owner actions and documented performance limitations, not hidden defects.

`STAB-PERFORMANCE-EVIDENCE.md:307` labels §9.1 (workflow-ledger verification O(n) per call)
**BLOCKING / PRODUCTION-SIGNIFICANT**, and §9.3–9.5 are HIGH; all remain "Recommended (not
implemented)" at this HEAD (§4.3). They are documented baseline limitations, not regressions
claimed fixed by stabilization. **If the acceptance rule is read strictly — any unresolved
HIGH/BLOCKING finding blocks — this verdict must be downgraded to BLOCK.** This verdict accepts
the stabilization work only; it is not a production-readiness approval, and promotion remains
blocked by the 20 gates in matrix §D.

---

## 1. Provenance and git scope

| Check | Observation |
| --- | --- |
| `git ls-remote --heads origin` | `main` = `9a63be929d7b364411b856aaf61230817697c410`; `stabilization/post-promotion-production-2026-11-25` = `63ab72e452f9c78af46db55489ef8d9def02212c` |
| Local HEAD | `63ab72e452f9c78af46db55489ef8d9def02212c` — equals remote stabilization tip; no local/remote divergence |
| `git merge-base --is-ancestor origin/main HEAD` | exit 0 — candidate is a clean descendant of main |
| Branch reflog | created from `origin/main` (`9a63be9`) at `@{25}`, linear 25-step progression, no `reset:` or rewrite — **no force-push** |
| Working tree | clean before and after this review; all probes used temp directories |

`git diff --name-status origin/main..HEAD` classifies as follows (no deletions; all entries M/A):

| Class | Paths | Assessment |
| --- | --- | --- |
| CI workflow config | `.github/workflows/{offline-license,provider-validation,python-tests,verify-install}.yml` | in scope |
| Secret-scan config | `.gitleaks.toml` | in scope |
| Source (backend Python) | `keel/src/keel/*.py` (24 files incl. `backend_workflows.py`, `capabilities.py`, `webapp.py`, `backend_events.py`, `fleet/db.py`, `runner.py`, `redaction.py`, `settings.py`) | in scope |
| Verification scripts | `scripts/{verify_backend_operation,check_model_licenses,verify_stab_install,verify_v6_audit,build_v6_audit_matrix,plan_p0_batches,verify_clean_setup}.py`, `keel/scripts/{verify_supply_chain,check_version_sync,build_dependency_graph}.py` | in scope |
| Tests / fixtures | `keel/tests/*` (15 files, 8 new) | in scope; no test deleted or weakened to obtain green |
| Evidence / planning docs | `STAB-*-EVIDENCE.md` (13 new), `POST-PROMOTION-*`, `PRODUCTION-*`, `BACKEND-*`, `master-plan-v6-*`, `AUDIT-REMEDIATION-SUMMARY.md`, `FINAL-ENGINEERING-REPORT.md`, `REGISTRY-EVIDENCE-INTEGRITY.md`, `REMAINING-WORK-MATRIX.md` | in scope |
| Performance harness | `perf-harness/stab/*.py`, `perf-harness/stab-results/result_*.json` | intentional read-only measurement artifacts, no user data |

- **Frontend edits: none.** No `.js/.jsx/.ts/.tsx/.css/.html/.vue/.svelte` path appears in the diff;
  frontend directories (`keel/site`, `keel/desktop`, `keel/fleet-next`, `keel/desktop-app`) exist in the
  tree but are untouched.
- **Temp files / secrets / generated user data: none.** No deletions, no binary additions, no
  `*.log`/`__pycache__`/`.pyc`/temp-runner files remain. Commit `7fe7674` removed an accidentally
  committed temp CI-log script, and `566e1fd` redacted a synthetic `AKIA…` placeholder in
  `STAB-SUPPLY-EVIDENCE.md:102`. Sensitive-looking strings in new tests/evidence are synthetic
  redaction fixtures.
- **Unrelated branch merges: none.** All 15 merges in range are stabilization agent branches
  (`agent/stab-events`, `agent/stab-workflow`, `agent/stab-ci`, `agent/stab-perf`, `agent/stab-db`,
  `agent/stab-supply`, `agent/stab-install`, `agent/stab-security`, `agent/stab-provider`,
  `agent/stab-tests`, `agent/stab-integrate`, `agent/stab-trace`, `agent/stab-docs`, `agent/stab-platform`,
  `agent/stab-runtime`) or the stabilization branch itself.

---

## 2. HIGH/MEDIUM fix claims — commit + regression-test verification

Fix commits were inspected with `git log`/`git show --stat`; affected tests were run in a fresh
`HOME`/`USERPROFILE` (`C:\Users\Admin\AppData\Local\Temp\opencode\stab-accept-testhome`).

| Claim (source) | Fix commit | Regression test | Verified by me |
| --- | --- | --- | --- |
| H-1 saved `ask`/prompt policy bypass (STAB-SECURITY-REVIEW.md:15) | `c54c673`, `8a9c84c`, CLI confirmation `a81a78b`/`63ab72e` | `test_stab_workflow_auth.py` (17 tests), `test_stab_lifecycle.py` | yes — real CLI + direct boundary probe (§7) |
| H-DB concurrent first-open migration race (STAB-DB-EVIDENCE.md:38) | `5763625` / `9c03487` | `test_stab_db_recovery.py::test_first_open_migration_is_serialized_across_threads_and_processes` | yes (test file passed) |
| F1/F2/F3 event-log HIGH (Windows binary writes, cross-process lock, unkeyed digest = M-4) (STAB-EVENTS-EVIDENCE.md:83–85) | `bc553b4`, `7a47db7`, `92f8d0f`, `25dac8a` | `test_stab_events_integration.py`, `test_backend_events.py` | yes (both files passed) |
| M-1 unaudited workflow branches; M-1b success HTTP 500 (STAB-SECURITY-REVIEW.md:61; STAB-INTEGRATION-EVIDENCE.md:300) | `c54c673`, `8a9c84c` | `test_stab_workflow_auth.py`, `test_backend_workflows.py` | yes |
| M-2 permission gate fails open (STAB-SECURITY-REVIEW.md:80; STAB-INTEGRATION-EVIDENCE.md:317) | `8a9c84c`, `c54c673` (HTTP boundary only) | `test_stab_workflow_auth.py` | **partial — see §4.1** |
| M-3 capability handler error echoes secrets (STAB-SECURITY-REVIEW.md:100) | `8a9c84c`, `c54c673` | `test_stab_workflow_auth.py` | yes |
| M-4 forgeable `backend_events` ledger (STAB-SECURITY-REVIEW.md:117) | `bc553b4`, `7a47db7` | `test_backend_events.py::test_forged_record_with_recomputed_plain_digest_is_rejected`, `…test_truncated_log_with_recomputed_head_is_rejected`, `test_stab_events_integration.py` | yes |
| M-5 CGNAT/metadata SSRF (STAB-SECURITY-REVIEW.md:132) | `2e3194e`, `17c4420`, `85f5ae8` | `test_stab_provider.py`, `test_security_remediation.py` | yes (both passed) |
| L-1 natural-language password disclosure (STAB-SECURITY-REVIEW.md:146) | `650fc7a`, `17c4420` | `test_stab_provider.py::test_l1_natural_language_password_is_redacted_in_validation_report`, `test_redaction.py` | yes (82-test run passed) |
| MEDIUM truncated DB backed up as empty (STAB-DB-EVIDENCE.md:64) | `5763625` / `9c03487` | `test_stab_db_recovery.py::test_corruption_detection_rejects_byte_flips_fk_violations_and_truncation` | yes |
| Events F4–F7 MEDIUM (legacy fail-closed, forensic retention, readiness/deps) (STAB-EVENTS-EVIDENCE.md:86–89) | `bc553b4`, `7a47db7` | `test_stab_events_integration.py`, `test_backend_events.py` | yes |
| Integration M-3 empty function schemas (STAB-INTEGRATION-EVIDENCE.md:334) | `8a9c84c`, `c54c673` | `test_stab_workflow_auth.py` (schema discovery) | yes |
| Perf 9.2 unbounded steering retention; 9.6 uncancelled timed-out workers (STAB-PERFORMANCE-EVIDENCE.md:330,376) | `65170e4` / `e0ec4d7` | `test_stab_perf_fixes.py` (7 tests) | yes |
| Install swap backup loss / torn start-health write (STAB-INSTALL-EVIDENCE.md:225,235) | `289a396` / `9c3e994` | `test_stab_install_recovery.py` (7 tests) | yes |
| CI supply-chain enforcement gap (STAB-SUPPLY-EVIDENCE.md:20) | `781b4cf` / `51147f2` | workflow step `offline-license.yml:31–33` | yes — step present; not locally runnable (CI-only) |
| MEDIUM license gate accepted unknown licenses (STAB-SUPPLY-EVIDENCE.md:32) | `101fcec` | **no committed regression test** — ad-hoc probes only (STAB-SUPPLY-EVIDENCE.md:160–173) | fix verified by my own probe (§4.2) |
| Integration M-4 no runtime consumer (STAB-INTEGRATION-EVIDENCE.md:349) | **none** — documented residual | none | **not fixed — see §4.4** |

**Affected-test runs (clean HOME), exact counts:**

```
python -m pytest -q -o faulthandler_timeout=120 -p no:cacheprovider \
  tests/test_stab_workflow_auth.py tests/test_stab_events_integration.py \
  tests/test_backend_events.py tests/test_stab_db_recovery.py \
  tests/test_security_remediation.py tests/test_stab_perf_fixes.py \
  tests/test_stab_install_recovery.py
=> 116 passed in 28.69s (exit 0)

python -m pytest -q -o faulthandler_timeout=120 -p no:cacheprovider \
  tests/test_stab_provider.py tests/test_redaction.py \
  tests/test_supply_chain.py tests/test_release_controls.py
=> 82 passed in 2.70s (exit 0)
```

---

## 3. Governance gates re-run (clean HOME)

| Gate | Command | Result |
| --- | --- | --- |
| v6 audit consistency | `python scripts/verify_v6_audit.py` | `CONSISTENCY OK`, 865 registry rows, exit 0 |
| Backend operation (strict) | `python scripts/verify_backend_operation.py --strict` | `EVIDENCE-BASED GATE (ENFORCED)`, audited 421 / passing 421 / failing 0, `BACKEND OPERATION VERIFICATION OK`, exit 0 |
| Dependency graph | `python keel/scripts/build_dependency_graph.py --check` | `FRESH: …DEPENDENCY-GRAPH.md`, exit 0 |
| License gate | `python scripts/check_model_licenses.py` | 11 entries, 0 bundled, `LICENSE GATE OK`, exit 0 |
| Version sync | `python keel/scripts/check_version_sync.py` | `OK — all sources agree on version 0.1.1 (tag v0.1.1)`, exit 0; negative control `--tag v9.9.9` → `VERSION MISMATCH`, exit 1 |
| Supply-chain verifier | `python keel/scripts/verify_supply_chain.py` | 34 lock entries / 8 pins checked, 34 SBOM packages matched, `SUPPLY CHAIN VERIFICATION OK`, exit 0 |
| YAML parse | `yaml.safe_load` on all `.github/workflows/*.yml` | 8/8 parse OK |
| Full-SHA `uses:` count | regex over workflow files | **31** refs, **31** full 40-hex SHA pins, 0 mutable refs; breakdown checkout 12 / setup-python 10 / setup-node 4 / upload-artifact 3 / download-artifact 2 (matches matrix §A) |

---

## 4. Claims without complete code/test evidence (open items)

1. **M-2 permission tiers — partial.** `capabilities.invoke` still defaults to
   `{read, write, execute}` when neither `allowed_permissions` nor
   `context["allowed_permissions"]` is supplied (`capabilities.py:128–138`). HTTP now passes a
   real tier set (`webapp.py:893–905`), but CLI (`cli/main.py:289–293`) and TUI omit it, so the
   shipped CLI/TUI and all legacy in-process callers retain all-tier behaviour and rely only on
   their own boolean confirm gate. This matches the residual acknowledged at
   `STAB-WORKFLOW-EVIDENCE.md:124–130` and the unfixed `STAB-INTEGRATION-EVIDENCE.md:317–332`.
   No security HIGH remains (the transport confirm gates are strict), but the declarative tier
   separation is not enforced on every surface.
2. **License gate MEDIUM — fix real, committed test absent.** My own negative probe reproduced
   `bundled+UNKNOWN → rc=1`, `bundled+unlisted → rc=1`, `bundled+MIT → rc=0`, but the only
   evidence is ad-hoc shell output in `STAB-SUPPLY-EVIDENCE.md:160–173`; fix commit `101fcec`
   added no pytest regression test.
3. **Six performance findings remain unimplemented** in the read-only audit at
   `STAB-PERFORMANCE-EVIDENCE.md:307–394`: §9.1 **BLOCKING / PRODUCTION-SIGNIFICANT** — O(n) ledger
   verification (I confirmed full `_read_jsonl()` scans still execute on every workflow call at
   `backend_workflows.py:500,561,618`, with no in-process idempotency index/LRU); §9.3 cold first
   backend call ~1.57 s, §9.4 HTTP burst queueing, §9.5 SQLite write tail (HIGH); §9.7 unbatched
   recovery (MEDIUM). (§9.2 unbounded steering retention and §9.6 uncancelled timed-out workers
   were fixed by `65170e4`/`e0ec4d7`.) These are measured baseline limitations, not regressions
   claimed fixed, and the perf report explicitly marks them "Recommended (not implemented)".
   They are open HIGH/BLOCKING-labelled items and must be prioritised or formally accepted.
4. **Integration M-4 (no runtime consumer of `backend_events`/`backend_observability`) is not
   fixed.** `STAB-EVENTS-EVIDENCE.md:47–69,138–141` and `STAB-INTEGRATION-EVIDENCE.md:349–361`
   defer runtime wiring to the lead. The matrix keeps PR-10/PR-15 `external_validation_pending`,
   so no gate falsely claims production-verified logging; but the tamper-evident-logging and
   readiness claims are not realised at runtime today.
5. **Secret-scan gate not established at final SHA.** `STAB-CI-EVIDENCE.md:47–48` records one
   remaining historical `aws-access-token` finding (synthetic `AKIA…` at
   `STAB-SUPPLY-EVIDENCE.md:102`, commit `c949891`). Commit `566e1fd` redacted the current-tree
   literal, but no matching `.gitleaks.toml` allowlist for `c949891` was added and `gitleaks` is
   not installed locally, so I could not re-run the scan. It is synthetic, not a real credential.

---

## 5. Full-suite reproduction

Command (from `keel/`, fresh `HOME`/`USERPROFILE` each run):
`python -m pytest -q -o faulthandler_timeout=120` with
`PYTHONPATH=<worktree>/keel/src`.

| Run | Result | Exit |
| --- | --- | ---: |
| 1 | `1 failed, 4556 passed, 52 skipped, 3707 subtests passed in 527.59s (0:08:47)` | 1 |
| 2 (confirmation, fresh clean HOME) | `4557 passed, 52 skipped, 3707 subtests passed in 484.78s (0:08:04)` | 0 |

The single run-1 failure was
`tests/test_compat_runtime.py::test_tool_requires_approval_then_approved_runs`
(`assert done` after `_wait_for_row(store, sid, "turn_end", timeout=10.0)` at
`test_compat_runtime.py:202`, helper at `:76`). Isolation checks in fresh clean HOMEs:
the single test **1 passed in 2.25s**; the whole file **12 passed in 23.61s**. Run 2 then
passed all 4557. This is an order/load-dependent 10-second timing flake, not a deterministic
defect at this HEAD; no test was removed or weakened to obtain green.

**Does the prior agent's claim reproduce?** No. `4546 passed / 0 failed` does **not** reproduce
at candidate HEAD `63ab72e`. The current tree yields **4557 passed / 0 failed / 52 skipped**
(run 2), i.e. 11 more passing tests than the earlier figure — consistent with the later runtime
commits (`a81a78b`/`63ab72e`) adding `test_stab_lifecycle.py` and updating related tests. Both
runs collected the same 4609 tests.

---

## 6. Authorization / audit code review and HIGH spot-check

Inspected `backend_workflows.py`, `capabilities.py`, `policy_enforcement.py`, `webapp.py` and the
CLI workflow command at final HEAD:

- `run_workflow(...)` no longer hardcodes `confirmed=True`; it defaults to `False` and forwards
  the caller's explicit confirmation (`backend_workflows.py:1586–1623`). Every exit branch funnels
  through `_failure()` and a single `_audit_workflow()` with a trusted-base fallback
  (`:1554–1583`, `:1661`).
- `enforce_workflow()` evaluates **both** the caller-selected state root and the trusted base and
  keeps the strictest decision (`policy_enforcement.py:169–201`), closing the policy-free
  subdirectory bypass; the workflow name is part of the enforced command, enabling per-workflow
  rules (`:181`).
- HTTP requires a literal `confirm is True` before dispatch and audits its own early refusals
  (`webapp.py:961–1016`); capability POST derives real session tiers (`:893–905`); CLI requires
  `--confirm` and now forwards it (`cli/main.py:334–338`).
- Handler/policy errors are redacted (`capabilities.py:249`, `backend_workflows.py:1569`); audit
  writes are redacted and atomically locked.

**Real CLI probe** (fresh state, saved `prompt` policy, real `python -m keel.cli.main`): no
`--confirm` → exit 1, "approval requires --confirm" (transport fails closed); `--confirm` →
exit 0, `code=ok`; `forbidden` + `--confirm` → exit 1, `code=policy_denied`.

**Real API-boundary probe** (direct `run_workflow` with saved policy):

```
prompt / no-confirm                     -> ok=False code=confirmation_required http=409  handler NOT run
prompt / with-confirm                   -> ok=True  code=ok                   http=200
prompt / no-confirm, policy-free subroot-> ok=False code=confirmation_required http=409  (bypass closed)
per-workflow rule / no-confirm          -> ok=False code=confirmation_required http=409
forbidden / with-confirm                -> ok=False code=policy_denied         http=403
no policy / with-confirm                -> ok=True  code=ok                   http=200
```

The red-team HIGH H-1 is therefore genuinely fixed at the authoritative boundary.

---

## 7. Documentation defects (exact file:line)

`PRODUCTION-READINESS-MATRIX.md` and `PRODUCTION-READINESS-REPORT.md` were never finalized at the
candidate SHA. They are conservative (they under-claim, not over-claim), so no gate is falsely
marked passed, but they are stale:

| File:line | Defect |
| --- | --- |
| `PRODUCTION-READINESS-MATRIX.md:17` | `<<LEAD_SUPPLIED_SHA — PLACEHOLDER, NOT YET FILLED>>` still present although final SHA `63ab72e…` exists |
| `PRODUCTION-READINESS-REPORT.md:5` | same unresolved `<<LEAD_SUPPLIED_SHA …>>` placeholder |
| `PRODUCTION-READINESS-MATRIX.md:16`, `PRODUCTION-READINESS-REPORT.md:4` | `f60b080…` presented as "current baseline tip (verified)"; actual final HEAD is `63ab72e…` |
| `PRODUCTION-READINESS-MATRIX.md:29–30,92`; `PRODUCTION-READINESS-REPORT.md:43,97–98` | "no `STAB-*-EVIDENCE.md` landed" and "`pass locally` = 0" — stale; 14 STAB files are in the candidate and local verification exists |
| `POST-PROMOTION-STABILIZATION-REPORT.md:27` (and 36 other `<<LEAD>>` fields) | the "final results" report is still a shell (`<<LEAD_SUPPLIED_SHA — PLACEHOLDER>>`, `<<LEAD>>`), never filled at the final SHA |

No stale SHA is presented as *current evidence* in a way that marks a gate passed: the matrix
labels `e573273…`, `ac84fee…`, `fe6cdd…`, `CANDIDATE_HEAD…` as historical (MATRIX:24–28, REPORT:11–14).
`PRODUCTION-PROMOTION-MANIFEST.md:6–9` still cites promotion-era SHAs (`fe6cdd…`, `ecba9d2b…`) but
does not present them as the stabilization SHA.

---

## 8. Gate classification (final)

| Gate class | Gates | Status in candidate | Misrepresented as verified? |
| --- | --- | --- | --- |
| Native macOS | PR-19 | `blocked` — no macOS runner; macOS 26 `sandbox-exec` SIGABRT (matrix §E.6) | No |
| Live providers | PR-06 | `external_validation_pending` — offline injection only, no live credential (matrix §E.1) | No |
| Signing / owner governance | PR-20 | `owner_gated` — unsigned installers, no signing identity, no CI sign job, 2FA/branch protection (matrix §E.7) | No |
| Other external/clean-VM checks | PR-01..PR-18 except PR-06 | `external_validation_pending` | No |
| `production_verified` / `pass locally` | none | **0 / 0** in matrix §D | No |

The candidate is explicitly documented as "not production-ready" (REPORT §1, §2, §8). No native
macOS, live-provider, signing or owner-governance gate is claimed as verified.

---

## 9. Required follow-ups before this candidate is cited as authoritative

1. Fill `PRODUCTION-READINESS-MATRIX.md:17`, `PRODUCTION-READINESS-REPORT.md:5`, update the "current
   baseline tip" SHAs (MATRIX:16, REPORT:4) to `63ab72e…`, and re-derive §D counts from the exact-SHA
   evidence; complete or retire `POST-PROMOTION-STABILIZATION-REPORT.md`.
2. Close M-2 by passing real permission tiers on CLI/TUI (or make `capabilities.invoke` fail
   closed when no tier set is supplied).
3. Add a committed regression test for the license-gate fail-closed fix.
4. Decide (owner) whether to wire `backend_observability` into runtime lifecycle/audit paths or keep
   it formally classified as a non-runtime library excluded from readiness claims.
5. Resolve the historical gitleaks finding with a narrow allowlist (or confirm the redaction closed
   it) before claiming the secret-scan gate clean.
6. Prioritise or formally accept the measured BLOCKING/HIGH/MEDIUM performance findings (§4.3).

---

## 10. Sign-off

Independent final acceptance reviewer — verdict **PASS_WITH_EXTERNAL_LIMITATIONS**.

---

## 11. Post-acceptance engineering follow-up (2026-11-26)

This follow-up is on `backend/surface-fix-2026-11-25`, after the candidate reviewed above;
it does not rewrite or change that candidate's historical findings.

- `349c9f4` forwards confirmation-derived permission tiers through CLI and TUI capability
  invocation, matching the HTTP boundary. Its focused CLI/TUI/HTTP tests passed 62/62.
- `9405110` adds committed fail-closed license-gate cases for bundled `UNKNOWN`, an unreviewed
  license, unbundled `UNKNOWN`, and bundled MIT.
- `37b069a` changes `keel/site/download.json` to the canonical unavailable fallback. The prior
  Windows URL had release size/checksum evidence that did not reconcile; this disables that
  unverified download locally and does not publish or authorize a release.
- `f376999` adds a per-ledger idempotency index and updates it incrementally on appends. Warm
  workflow lookups and appends avoid full record-list scans; a changed file signature still
  triggers the existing full HMAC-chain verification. Duplicate-key lookup preserves first
  record semantics for replay and latest-record semantics for finalization.

Validation:

| Scope | Command/result |
| --- | --- |
| Full Python suite before `f376999` | `python -m pytest -q -o faulthandler_timeout=90` — 4,790 passed, 49 skipped, 3,707 subtests passed |
| Capability permission boundaries | `python -m pytest -q tests/test_capability_cli_tui.py tests/test_stab_workflow_auth.py tests/test_prod_auth_hardening.py tests/test_bridge_e2e_hardening.py tests/test_security_validation.py` — 62 passed |
| Release metadata | `python -m pytest -q tests/test_final_artifacts.py` — 18 passed |
| Workflow ledger/index | `python -m pytest -q tests/test_stab_ledger_cache.py tests/test_backend_workflows.py tests/test_prod_secfix.py tests/test_final_events.py` — 65 passed |
| 300-entry synthetic ledger probe after `f376999` | first 50 p50 25.453 ms; last 50 p50 24.033 ms; last 50 p95 27.251 ms (not a public-workflow SLA) |

The full suite has not been rerun after `f376999`; the focused ledger/integrity suite and the
synthetic probe cover that last change. Native macOS/Linux builds, signing, public deployment,
remaining performance findings, and the 70 unmerged branch tips remain outside this follow-up.
Commit on `agent/stab-accept`; **no push**.

## 12. Follow-up verification (2026-11-26)

This follow-up records additional work on `backend/surface-fix-2026-11-25`;
it does not change the prior acceptance verdict or make a whole-product
completion claim.

- `a682f53` isolates the Quick Ask subprocess test from host HOME, USERPROFILE
  and Keel state, preventing tests from loading a developer's configured MCP
  servers.
- `5ecd364` makes the milestone web-fetch E2E deterministic and offline by
  mocking the resolver/opener seam while retaining the unsafe-local-URL check.
- `4f6dd5c` labels the desktop chat pane “Keel Chat” without changing the
  site/landing UI or the backend's existing `cowork` surface. It also updates
  stale desktop-renderer assertions, narrows a false-positive environment
  scanner, isolates the webapp runtime test, and cleans up the packaged Windows
  sidecar process tree.
- Rebuilt the local Windows PyInstaller sidecar at `dist/keel-sidecar/keel.exe`.
  This is an ignored local build artifact; no Electron installer was rebuilt
  or published.
- `82479e2` hardens the macOS Seatbelt fallback: broad file reads are allowed
  only when both the cached host probe and the invocation probe reproduce
  `SIGABRT` with empty stderr. Other failures now fail closed and report read
  isolation as unavailable. PR #15's intentional macOS read-isolation
  limitation remains blocked; no confinement claim is inferred from its skip.
- `155d7f1` serializes Windows AppContainer profile creation/reuse to avoid
  concurrent `CreateAppContainerProfile` failures. The known `E_UNEXPECTED`
  result can recover only by deriving the existing profile SID; otherwise the
  operation remains fail-closed.
- Reviewed the attached Universal AI Harness plan and the current `main`-only
  branch changes. The plan is a multi-phase P0–P3 roadmap, not a bounded
  implementation ticket. `main` was not merged wholesale: review found
  regressions in the workflow artifact trust gate, execution-policy enforcement
  and sandbox path validation. No reference-repository code was copied.
- PR #15's three files already match `origin/main`; PR #31 has no patch to
  integrate and its CI is red. Neither PR was merged or cherry-picked.
- Rechecked the public Ship article on 2026-11-27: the site home and download
  route return content, but `/resources/articles/introducing-keel-ship` and
  `/resources/articles/introducing-keel-code` return 404. The tracked Ship
  HTML and Vercel rewrite both exist locally, and a new browser regression test
  confirms the rewrite serves the article from the current source tree. No
  public deployment was created: the linked Vercel CLI resolves the site root
  twice when run from the nested directory, while a repository-root preview
  attempts to upload the 1.6 GB monorepo and is rejected at Vercel's 100 MB
  per-file limit. Production remains unchanged.

Validation:

| Scope | Command/result |
| --- | --- |
| Full Python suite before sandbox fallback hardening | `python -m pytest -q -o faulthandler_timeout=90` with a fresh `KEEL_STATE_DIR` and `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` — 4,792 passed, 49 skipped, 3,707 subtests passed |
| Full Python suite after sandbox fallback hardening | Same command and environment — 1 failed, 4,797 passed, 48 skipped, 3,707 subtests passed. The failure is `tests/test_os_sandbox.py::test_concurrent_confinement`: concurrent Windows `CreateAppContainerProfile` returned `HRESULT 0x8000ffff` in `win_network.appcontainer_sid`; no Windows sandbox files changed in this follow-up. |
| Isolated Windows concurrency follow-up | `python -m pytest -q -rs tests\test_os_sandbox.py::test_concurrent_confinement` — 1 skipped because network enforcement could not be established on this host |
| AppContainer concurrency regression tests | `python -m pytest -q tests\test_win_network_profiles.py tests\test_win_network.py` — 14 passed |
| Full Python suite after AppContainer fix | `python -m pytest -q -o faulthandler_timeout=90` with a fresh `KEEL_STATE_DIR` and `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` — 4,800 passed, 49 skipped, 3,707 subtests passed |
| Concurrent confinement after AppContainer fix | `python -m pytest -q -rs tests\test_os_sandbox.py::test_concurrent_confinement` — 1 skipped because Python could not launch in AppContainer on this host; concurrent profile creation itself is covered by the passing mocked API race test |
| Quick Ask | `python -m pytest -q tests\test_quick_ask.py` — 3 passed |
| Milestone 6B | `python -m pytest -q tests\test_e2e_milestone_6b.py` — 1 passed |
| Desktop labels and packaged UI | `python -m pytest -q tests\test_product_labels.py tests\test_packaged_ui_serving.py` — 7 passed; packaged smoke re-run after cleanup fix: `python -m pytest -q tests\test_packaged_ui_serving.py` — 2 passed |
| Renderer/bridge verification | `python -m pytest -q tests\verify_distribution_agent_renderer.py` — 4 passed |
| Webapp runtime isolation | `python -m pytest -q tests\test_webapp.py::test_run_streams_events_and_done_marker` — 1 passed |
| Sandbox fallback hardening | `python -m pytest -q tests\test_sandbox_macos_probe.py tests\test_sandbox_macos.py tests\test_sandbox_hardened.py tests\test_native_isolation.py` — 20 passed, 14 skipped (native macOS tests cannot execute on this Windows host) |
| Windows sandbox regressions | `python -m pytest -q tests\test_sandbox_windows.py tests\test_security_remediation.py` — 17 passed, 1 skipped |
| Static website routes and download UX | `node --test keel\site\tests\*.test.mjs` — 25 passed, including the Ship article clean route and honest unavailable release states |
| Desktop JavaScript syntax | `node --check desktop\ui\app.js` — passed |
| Windows sidecar build | `python -m PyInstaller desktop-app\sidecar.spec --noconfirm --distpath dist\keel-sidecar` — passed |

The attached plan remains substantially incomplete: this follow-up does not
implement or certify the full provider, orchestration, plugin, browser,
workflow, IDE, compatibility, enterprise or release roadmap. macOS/Linux
artifacts, signing/notarization, the public Ship-article deployment, and
production release authorization remain unverified. The public download
metadata remains fail-closed pending verified release artifacts. Versal and
landing-page files were not changed.

A fresh read of GitHub release `v0.1.1` confirms that Windows, macOS arm64
and Linux assets are present, but the release records are inconsistent:
the current Windows asset is 315,605,830 bytes with SHA-256
`dd585d898e00a5e1621821d18ba2a6e846392c6178e49a78b356d0ecfc549604`;
the published `RELEASE-MANIFEST.json` instead records 122,153,124 bytes and
SHA-256 `917a58ff527b5ccb831329d6a761ed2a1ba9cefe9ea12e967e30ad8becb0a0bf`,
while the published `download.json` has the current digest but a different
size. The macOS/Linux files match the release manifest and GitHub asset
digests, but the published download metadata marks them unavailable and the
checksums file does not cover the macOS files. Therefore the local download
fallback remains unavailable until an owner reconciles and re-verifies the
release records; the assets should not be advertised as a verified release
from this checkout.
Evidence command: `gh release view v0.1.1 --repo eliosmernica15/keel --json tagName,name,isDraft,isPrerelease,publishedAt,assets,url` (read 2026-11-26).
