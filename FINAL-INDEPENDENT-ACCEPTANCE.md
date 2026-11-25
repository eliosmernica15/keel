# FINAL INDEPENDENT ACCEPTANCE — candidate `530c067`

**VERDICT: `BLOCK`**

> Independent, read-only final release acceptance. The reviewer did not implement or
> previously review this work. No tracked source, test, workflow, frontend or evidence
> file was edited by this review: the only file changed on `agent/final-accept2` is this
> report. No push, tag, secret write, signing, publish or deployment was performed.
>
> Report date: 2026-11-25.

## 0. Review identity

| Field | Value |
| --- | --- |
| Reviewer | independent final-acceptance subagent (read-only) |
| Worktree / branch | `C:\Users\Admin\.local\share\opencode\worktree\final\accept2` / `agent/final-accept2` |
| Exact SHA reviewed | `530c0670f2c34805fb7ac705e1a7b8dfe113006f` (`fix(security): redact natural-language PIN/code disclosures`) |
| Base for scope diff | `origin/main` = `FINAL_COMPLETION_HEADabfd784393b2b252e2b9e2927aba817dd` |
| Candidate branch | local `completion/final-production-release-2026-11-25` (same SHA) |
| Clean test HOME | `C:\Users\Admin\AppData\Local\Temp\opencode\final-accept2-cleanhome\{home,state}`; `PYTHONPATH` pinned to this worktree's `keel/src`; `PYTHONNOUSERSITE=1` |

---

## 1. Git scope and provenance

`git diff --name-status origin/main..HEAD` contains **51 paths**: 5 `.github` files
(`CODEOWNERS`, `PULL_REQUEST_TEMPLATE.md`, `build-desktop.yml`, `lifecycle.yml`, new
`release-authorization.yml`), one `.gitleaks.toml` change, 16 `FINAL-*.md` documents,
4 other documentation files, 17 backend `keel/src/keel/*.py` modules, 6 new
`keel/tests/test_final_*.py` regression files and 2 new `scripts/*.py` verifiers.
`git diff --check` is clean.

| Scope question | Result |
| --- | --- |
| Frontend edits by this operation | **None.** `git diff --name-only origin/main..HEAD -- keel/site keel/desktop keel/desktop-app keel/fleet-next` is empty; no `.ts/.tsx/.js/.jsx/.css/.html` path changed. `keel/src/keel/webapp.py` is backend Python (health/readiness payload only). |
| Temp files / secrets / binaries | **None.** All added files are text (`*.md`, `*.py`, `*.yml`, `*.toml`); no temp runner such as the previously rejected `_prod_suite_tmp.py`. Secret-pattern scan over the 26 added files found one synthetic test fixture string (`sk-abcdefghijklmnopqrstuv` in `keel/tests/test_final_events.py`), explicitly a test constant, not a credential. |
| Force-push | **None observed.** The candidate branch reflog is linear from `branch: Created from origin/main` at `FINAL_COMPLETION_HEAD` through merges and commits; no reset/force-update. Live remote branch protection is unavailable on this Free plan (`FINAL-GOVERNANCE-EVIDENCE.md` §5), so force-push cannot be remotely *prevented*; that is an owner limitation, not an observed event. |
| `origin/main` | Unchanged at `FINAL_COMPLETION_HEAD` locally and via `git ls-remote origin refs/heads/main`. |
| Remote SHA for candidate | **None.** No remote ref equals `530c067` (`git ls-remote origin`); the newest PR is #17 (merged 2026-11-25T02:56Z) ending at `FINAL_COMPLETION_HEAD`. `release-candidate/final` (`16977a3`) is an ancestor of the candidate. The candidate is a local-only branch with no PR/CI review. |

---

## 2. Evidence-claim verification (fix commit + regression test)

For every `FINAL-*-EVIDENCE.md` claim I located the fix commit in
`git log origin/main..HEAD -- <file>`, confirmed the named regression file exists, and
re-ran the affected tests in a clean HOME. All six `test_final_*.py` files were executed
(45 tests in one batch, 69 in a second batch — **114 passed, 0 failed** in total).

| Evidence document | Fix commit(s) | Regression test | Re-run result |
| --- | --- | --- | --- |
| `FINAL-DATABASE-EVIDENCE.md` (state-root D1) | `491ee24` `fix(db): align fleet.db with authoritative state root` | `keel/tests/test_final_db.py` | 18 passed; state-root probe also passed |
| `FINAL-EVENTS-EVIDENCE.md` (EventBus integration + M-1) | `711728b` (workflow wiring + empty-ledger fail-closed), `c28d2c7` | `keel/tests/test_final_events.py` | 14 passed; dedicated M-1 truncation probe passed |
| `FINAL-GOVERNANCE-EVIDENCE.md` (release gate) | `dea9a39` / `e028c60` (policy and workflow gate), `27ce45f` (gitleaks narrow allowlists — **defective, see F-0**) | `scripts/verify_release_authorization.py` (dedicated verifier); `tests/test_release_controls.py` (allowlist exactness) | Verifier: 13/13 positive/negative cases passed with stub `gh`; real inert marker rejected. Gitleaks allowlist test **fails** — see F-0. |
| `FINAL-INSTALL-EVIDENCE.md` (corrupt health entry) | `4eaca4d` + `4b51d5a` | `keel/tests/test_final_install.py` | 13 passed |
| `FINAL-OBSERVABILITY-EVIDENCE.md` (D1–D5) | `7447f7f` / `7bb16ae` | `keel/tests/test_final_observe.py` | 20 passed; readiness probes re-probed |
| `FINAL-PLATFORM-EVIDENCE.md` (read-only audit) | `ad3b8b8` (docs only; no source fix claimed) | n/a — evidence collection, not a code claim | Blockers re-probed live (see §5) |
| `FINAL-PROVIDER-EVIDENCE.md` (cancel classification) | `91fbecf` / `7f31777` | `keel/tests/test_final_provider.py` | 31 passed; no credential present |
| `FINAL-SIGNING-EVIDENCE.md` (modes, rotation, fail-closed) | `7f880aa` / `1466998` | `keel/tests/test_final_signing.py` | 18 passed; mode/distribution probes passed |
| `FINAL-SECURITY-VERIFICATION.md` (M-1, DLP PIN/code, gitleaks) | `711728b` (M-1), `530c067` (PIN/code redaction), `27ce45f` (allowlists) | `test_final_events.py`, `test_final_observe.py`, `redaction.py` | all passed; natural-language PIN/code redaction probe passed |
| `FINAL-CI-DIAGNOSIS.md` (billing blocker) | `4974e58` (docs) + `27ce45f` (allowlists) | n/a — external blocker; allowlist diff verified | billing annotation re-fetched live (see §5) |

**Unverified / partially verified claims (listed explicitly):**
1. `FINAL-PLATFORM-EVIDENCE.md` macOS section relies on a historical PR #15 CI run
   (`macos-26-arm64`, 1286 passed); the backend/test files were byte-identical at `FINAL_COMPLETION_HEAD`,
   but I could not re-run it (no Darwin host, billing blocker). Correctly classified as
   `BLOCKED`, never as a local pass.
2. `FINAL-CI-DIAGNOSIS.md` §6 gitleaks result: the four narrow allowlist entries in
   `.gitleaks.toml` were verified by diff and found to use short commit IDs, which fails
   the repository's own allowlist-exactness test (F-0). A full-history gitleaks binary
   scan was not re-executed locally; the claimed secret-scan closure is therefore
   **not verified**.
3. All evidence documents are pinned to completion HEAD `FINAL_COMPLETION_HEAD`; none references the
   reviewed candidate `530c067`. This is a traceability/staleness gap, not a false green
   (see §7 findings).

---

## 3. Governance gates re-run

| Gate | Command | Result |
| --- | --- | --- |
| Plan registry consistency | `python scripts/verify_v6_audit.py` | `CONSISTENCY OK`, 865 rows; exit 0 |
| Strict backend operation | `python scripts/verify_backend_operation.py --strict` | 421/421 attributed IDs passing, 0 failing; `BACKEND OPERATION VERIFICATION OK`; exit 0 |
| Dependency graph | `python keel/scripts/build_dependency_graph.py --check` | `FRESH`; exit 0 |
| License gate | `python scripts/check_model_licenses.py` | `LICENSE GATE OK`, 11 entries / 0 bundled; exit 0 |
| Version sync | `python scripts/check_version_sync.py` (in `keel/`) | `OK - all sources agree on version 0.1.1 (tag v0.1.1)`; exit 0 |
| YAML parse | `yaml.safe_load` over `.github/workflows/*.yml` | **9/9** parse; 0 `pull_request_target` occurrences |
| Action pin count (from workflow files) | regex `uses:` + 40-hex suffix check | **42/42** external refs full-SHA, 1 local reusable path `./.github/workflows/release-authorization.yml`; breakdown checkout 16, setup-python 14, download-artifact 5, setup-node 4, upload-artifact 3 |
| Release-authorization verifier | stub `gh` harness, 1 positive + 12 negative cases | **13/13** as expected; real inert marker (`RELEASE-APPROVED: NOT-APPROVED by @nobody`) → exit 1 |

Note: the matrix/completion report claim **9/9 YAML** and **42/42 pins**; at the reviewed
candidate the true values are **9/9** and **42/42** (the new governance workflow added one
YAML file and two SHA-pinned actions). The governance evidence document records the
correct 9/9 and 42/42. See finding F-2.

---

## 4. Full suite in clean HOME

Command: `python <runner> -q --tb=short` from this worktree's `keel/` directory, with the
clean HOME/state root and worktree-pinned `PYTHONPATH` described in §0.

```
2 failed, 4722 passed, 54 skipped, 3707 subtests passed in 3267.15s (0:54:27)
EXIT=1  (wall-clock with shell setup: 00:54:36)
```

The suite is **red**, not green. The two failures are:

1. **`tests/test_release_controls.py::test_gitleaks_config_is_present_and_narrowly_scoped`
   — deterministic, candidate-introduced regression.** It asserts every allowlist block
   in `.gitleaks.toml` has exact 40-hex commit SHAs. The four blocks added by `27ce45f`
   use 7-character SHAs (`ce78f10`, `ce78f10`, `781b4cf`, `c949891`); the assertion
   `all(len(c) == 40 for c in block["commits"])` fails. I reproduced this **in isolation**
   (1 failed, 1 passed in 5.98 s) and confirmed the config contents by parsing the TOML.
   This is a real defect in a security-gating fix, not a flake: it is **BLOCKER F-0**.
2. **`tests/test_cli_surface_hardening.py::test_broken_saved_policy_is_a_clean_cli_error`
   — full-suite-only timing flake.** `subprocess.run(..., timeout=60)` raised
   `TimeoutExpired: ... timed out after -2379.155999999959 seconds` (a negative computed
   remaining time). Re-run in isolation it passed, and the entire
   `test_cli_surface_hardening.py` file passed (9 passed in 24.13 s). No global
   `time.monotonic`/`subprocess` monkeypatch was found in the test tree. Classified as a
   cross-file timing/isolation flake, not a deterministic regression, but it still makes
   the candidate suite non-deterministically red.

Because of failure 1, the `4610 passed / 0 failed` baseline cited in the FINAL documents
does **not** hold at the reviewed candidate `530c067`.

---

## 5. Real probes of the remaining HIGH/MEDIUM areas and external gates

A dedicated probe (`final-accept2-cleanhome/probe_final.py`) ran with a fresh HOME/state
root and worktree-pinned `PYTHONPATH`: **18/18 checks passed**.

* **Workflow authorization/audit (prior HIGH-1 / M-2):** `backend_workflows.py` now calls
  `policy_enforcement.enforce_workflow` and `capabilities.record_audit`; real workflow
  denial and "forged allow event cannot widen a denial" are covered by the passing
  `test_final_events.py`. The residual permission-tier gap is disclosed in matrix PR-13
  (`M-2`), not presented as production behaviour.
* **EventBus integration (prior MEDIUM-6):** real call sites exist via
  `automation.publish_durable` in `backend_workflows.py` and `capabilities.py`; a live
  `job_completed` publish through the adapter produced a terminal record. `backend_events`
  is no longer dormant. `backend_observability` remains a library contract for the
  workflow surface, as documented.
* **M-1 ledger truncation:** an appended ledger was truncated to zero bytes;
  `_read_jsonl` raised `ledger_integrity`, the MAC-protected head was unchanged, and a
  subsequent append could not launder the truncation (file remained empty).
* **State-root consistency:** with `KEEL_STATE_DIR` set, `settings.default_state_root()`
  and `fleet.db.default_db_path()` are identical absolute paths and the DB lives under
  the state root.
* **Observability readiness:** `dependency_health({})` returns `healthy=False`,
  `dependency_count=0`; the four real probes (database, provider, worker, event_log)
  all execute and pass, and the provider probe is an adapter construction, not a
  module-presence flag.
* **Natural-language redaction:** `the PIN is 4821`, `the code is Alpha 7744` and
  `The password is Harbor Seal42 Tango Mike` all redact to `[REDACTED]` (commit `530c067`).
* **Signing modes:** `resolve_mode({})` is `dev`; `test` parses; an unknown mode raises
  `SignatureError`; distribution mode reports 4 missing owner identity items and both
  native platform verifiers are unregistered — fail-closed, no trusted distribution.
* **Workflow gate wiring (static inspection):** `build-desktop.yml` defines a tag-gated
  `release-authorization` job (`if: startsWith(github.ref, 'refs/tags/v')`), and both
  `verify-release-signatures` and `publish` list it in `needs`; `lifecycle.yml` installer
  jobs all depend on `trust-gate`. `release-authorization.yml` is `workflow_call` /
  `workflow_dispatch` with `contents: read` only and runs the verifier against the tagged
  commit. This was not executed on GitHub (billing + local-only candidate).
* **GitHub billing blocker (live):** `gh api .../check-runs/138944015384/annotations`
  returns *"The job was not started because recent account payments have failed or your
  spending limit needs to be increased…"*; `.../actions/runs/45536422111/timing` shows
  `duration_ms: 0` for all three OS jobs and `run_duration_ms: 3000`. Confirmed external.
* **No Darwin host:** `sys.platform == 'win32'`, `platform.system() == 'Windows'`,
  `shutil.which('sandbox-exec') is None`; only WSL2 Linux is available locally.
* **No provider credentials:** presence-only check of the approved `KEEL_*_API_KEY`
  variables is all false; no live request was made.
* **No trusted signing identity:** all signing secret variables absent; live
  `GET .../actions/secrets` → `total_count=0`.

None of these four external gates is marked verified anywhere in the candidate evidence;
each is classified `BLCK`, `EXTP` or `OWNR` in `FINAL-PRODUCTION-READINESS-MATRIX.md` §C/§E
and expanded in `FINAL-OWNER-ACTIONS.md` A1–A5.

---

## 6. Gate-matrix reconciliation

`FINAL-PRODUCTION-READINESS-MATRIX.md` §E parsed programmatically:

| Class | Count | Members |
| --- | ---: | --- |
| `PASS_VERIFIED` | 0 | none |
| `PASS_IMPLEMENTED_NOT_EXTERNALLY_VERIFIED` | 16 | PR-01…05, 07…16, 18 |
| `EXTERNAL_PENDING` | 2 | PR-06, PR-17 |
| `OWNER_ACTION_REQUIRED` | 1 | PR-20 |
| `BLOCKED` | 1 | PR-19 |
| `NOT_IMPLEMENTED` | 0 | none |
| **Total** | **20** | PR-01…PR-20, each exactly once |

Mutually exclusive, no duplicates or omissions, sum = 20; the same counts appear in
`FINAL-RELEASE-COMPLETION-REPORT.md` §1. Of 54 evidence paths extracted from §C, 53 exist
at the worktree root; the single non-resolving token is `diagnostics.py` in PR-11 (a
docstring shorthand; the real module is `keel/src/keel/diagnostics.py`). See finding F-3.

---

## 7. Findings requiring correction or disclosure

| ID | Severity | Finding | Required action |
| --- | --- | --- | --- |
| F-0 | **BLOCKER** | `27ce45f` added four `.gitleaks.toml` allowlist blocks with 7-character commit IDs (`ce78f10`, `781b4cf`, `c949891`); existing `test_release_controls.py::test_gitleaks_config_is_present_and_narrowly_scoped` requires exactly 40-hex SHAs. Full suite and isolation re-run both fail. | Replace all four SHAs with their full 40-hex commit IDs, re-run `tests/test_release_controls.py` and the full suite to green. Until then the candidate is not releasable. |
| F-6 | Low (flake) | Full-suite-only `subprocess.TimeoutExpired` with a negative timeout in `test_cli_surface_hardening.py::test_broken_saved_policy_is_a_clean_cli_error`; passes in isolation and as a whole file. | Investigate cross-file clock/timing state; re-run the full suite after F-0 is fixed and require a clean exit. |
| F-1 | Medium | Every `FINAL-*` evidence/matrix document names completion HEAD `FINAL_COMPLETION_HEAD` and the `4610 passed` baseline; none references reviewed candidate `530c067`, which adds 6 new test modules and 17 backend source changes. The matrix is therefore not the authoritative classification of the artifact under review. | Re-issue the matrix/acceptance counts at the exact promoted SHA before citing them for promotion; do not treat `FINAL_COMPLETION_HEAD` totals as evidence for `530c067`. |
| F-2 | Low | Matrix §A / completion report claim 9/9 YAML and 42/42 SHA pins; the candidate actually has 9 workflows and 42 SHA pins. The governance evidence file is correct. | Update those two rows if the documents are carried forward. |
| F-3 | Low | PR-11 evidence cell cites `diagnostics.py` without a repo-relative path. | Replace with `keel/src/keel/diagnostics.py`. |
| F-4 | Low | The candidate's `FINAL-INDEPENDENT-ACCEPTANCE.md` was an unfilled reviewer shell (`<<REVIEWER_SUPPLY: …>>`, explicitly "NOT A VERDICT"). | This report replaces it with observed results; no placeholder remains. |
| F-5 | External | GitHub Actions cannot run (billing annotation), the candidate SHA is not pushed and has no PR; no Darwin host, no provider credential, no signing identity. | Owner actions A1–A5 in `FINAL-OWNER-ACTIONS.md`; production authorization remains **No**. |

No HIGH-severity security defect was reproduced. Prior M-1 (ledger truncation), the DLP
PIN/code gap and the EventBus dormancy each have a fix commit and a passing regression
check at the candidate. However, **F-0 is an internally actionable, deterministic
regression in the gitleaks allowlist fix**: the commit intended to close the CI
secret-scan finding violates an existing governance test and leaves the full suite red.
The gitleaks gap cannot be called closed. Documented residuals (M-2 permission tiers,
M-4 library-only wiring, G1 Y3 revocation descriptors, forward-only migrations, no
exporter/pager) are disclosed rather than represented as production behaviour.

---

## 8. Placeholder and honesty check

`FINAL-*.md` files were scanned for `<<…>>`, `REVIEWER_SUPPLY`, `TODO`, `TBD`,
`FIXME`, `CANDIDATE_HEAD` and similar markers. The only live unfilled fields were in the
reviewer shell that this report replaces (F-4). All other occurrences are explicitly
quoted as **historical** citations of stale placeholders in
`FINAL-PRODUCTION-READINESS-MATRIX.md` §F, `FINAL-STABILIZATION-ACCEPTANCE.md` §7 and the
historical `FINAL-RELEASE-ACCEPTANCE.md` (marked `[HISTORICAL]` at its header); none is
presented as a current result. `PASS_VERIFIED` is 0, `production_verified` is not claimed,
`download.json` has all channels `url: null`/`available: false`/`verified: false`, and
no deployed instance, signed artifact or published release is asserted.

---

## 9. Limitations of this review

* Tests and probes ran on this Windows 11 host only; no bare-metal Linux, no macOS.
* The `observe/provider/signing` batch took 5536.71 s (~92 min) wall-clock despite
  reporting 69 passed — a local performance anomaly worth watching, not a failure.
* The release-authorization verifier was exercised with a stub `gh`; live API calls and
  the `workflow_dispatch` gate were not executed (billing blocker + candidate not pushed).
* Full-history gitleaks, VM installer lifecycle, live provider smoke, trusted-signature
  verification and native macOS verification were not re-performed; each remains an
  explicitly open external item.
* The CLI subprocess failure was seen only once in the full suite and could not be
  reproduced in isolation or as a whole file; its root cause (a negative computed
  remaining timeout) was not positively identified.

## 10. Sign-off

**Verdict: `BLOCK`** for the reviewed candidate `530c067`. The blocking finding is F-0:
the gitleaks allowlist fix committed as `27ce45f` uses short commit IDs and fails the
repository's own `test_release_controls.py` exactness test, so the full suite exits 1
(`2 failed, 4722 passed, 54 skipped, 3707 subtests passed`). All other internally
verifiable fixes, regression tests and governance gates pass, and every external gate is
honestly classified rather than verified — but a deterministic red test plus the
unresolved external limitations preclude a pass verdict.

**Production deployment and promotion are NOT authorized.** Required before a new
acceptance review: fix F-0 with full 40-hex commit IDs, re-run the full suite to green
(and re-check F-6), complete owner actions A1–A5, and re-issue the matrix at the exact
SHA actually promoted.

Independent final-acceptance subagent — 2026-11-25.
