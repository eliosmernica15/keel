# FINAL ERROR SWEEP — pre-promotion read-only audit

**Verdict: FINDINGS (BLOCKER). `ac84fee` is NOT safe to promote to `main`.**

| Field | Value |
|---|---|
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\production\finalcheck` |
| Branch | `agent/final-finalcheck` |
| Candidate HEAD | `ac84feebd8e889ad0afdc21e972fe162d3fd736c` |
| Baseline | `origin/main` = `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` (unchanged) |
| Diff | 422 paths vs `origin/main` |
| Audit date | 2026-11-25 |
| Method | Read-only. No source was edited; only this report was added. |

The decisive reason for the verdict is that the candidate's **own** release report says
promotion is blocked (`PRODUCTION-READINESS-REPORT.md:173`), with 5 `unverified` and
2 `blocked` mandatory gates (`:175`, matrix `PRODUCTION-READINESS-MATRIX.md:1,3,14`).
The mission rule treats either status as forbidding promotion. All internal technical
gates pass, but they do not close those external/owner gates.

---

## 1. Governance gates — all PASS

Run from the candidate worktree; exact outputs:

| Gate | Command | Result | Exit |
|---|---|---|---|
| v6 registry consistency | `python scripts/verify_v6_audit.py` | `registry rows: 865`; tiers `operational 52 / local_module 805 / external_dependency 3 / descriptor 3 / owner_gated 2`; `P0 share: 27.7%`; `matrix rows: 865`; **`CONSISTENCY OK`** | 0 |
| Backend operation (strict) | `python scripts/verify_backend_operation.py --strict` | `features: 865 status: {'verified': 854, 'blocked': 2, 'not_started': 9}`; `backend modules: 20 attributed IDs: 421`; `=== EVIDENCE-BASED GATE (ENFORCED) ===`; `audited: 421`, `passing: 421`, `failing: 0`; **`BACKEND OPERATION VERIFICATION OK`** | 0 |
| Dependency graph | `python keel/scripts/build_dependency_graph.py --check` | **`FRESH`** | 0 |
| License gate | `python scripts/check_model_licenses.py` | `license registry: 11 entries, 0 bundled`; **`LICENSE GATE OK`** | 0 |
| Version sync | `python keel/scripts/check_version_sync.py` | **`OK - all sources agree on version 0.1.1 (tag v0.1.1)`** | 0 |
| YAML parse | `yaml.safe_load` over `.github/workflows/*.yml` | 8 files, 0 parse failures | 0 |
| Full-SHA `uses:` pin | regex `@[0-9a-fA-F]{40}(\s+#.*)?$` over all `uses:` lines | 31 refs, **0** non-full-SHA | 0 |

Note: evidence docs report 26 or 30 `uses:` refs (see F-08); the live count is **31** after
`ea04276` added `actions/setup-node` to `python-tests.yml:31`.

## 2. Hygiene / scope

* Working tree clean: `git status --short --branch` → `## agent/final-finalcheck` only;
  `git ls-files --others --exclude-standard` → empty.
* **Temp runner still committed — see F-02.** `keel/_prod_suite_tmp.py` is tracked.
* Secret scan over all 422 changed text files (AWS AKID, `sk-*`, GitHub, Slack, PEM,
  password/secret assignments): 68 raw matches, all synthetic fixtures/documented examples
  in tests and review docs. No real credential found. No generated user data, session
  transcripts, `.jsonl` user logs, binaries, archives or temp paths (other than F-02) in
  the diff.
* Scope vs `origin/main`: only `keel/desktop/src-tauri/Cargo.toml` under frontend/desktop
  paths, and its diff is exactly one line (`version = "0.1.0"` → `"0.1.1"`). No site /
  desktop JS, CSS, HTML or pages. The site files from `6970867` were removed by `7a9b021`.
* All **422/422** diff paths appear exactly once in the path-classification table of
  `PRODUCTION-PROMOTION-MANIFEST.md:26-449` (0 missing, 0 extra). Caveats: F-02 and F-04.
* Backend substance: 20 modules (`backend_hub.modules()`), 421 attributed IDs, 421/421
  strict traceability, registry 865 / 854 verified / 9 not_started / 2 blocked — all
  independently reproduced (§1).

## 3. Representative error-focused tests — clean HOME

Environment: fresh `C:\Users\Admin\AppData\Local\Temp\opencode\prodhome-finalcheck`
(HOME + USERPROFILE), `PYTHONPATH=keel/src`, from worktree root.

```
python -m pytest -q -o faulthandler_timeout=120 \
  keel/tests/test_prod_secfix.py \
  keel/tests/test_prod_api.py \
  keel/tests/test_prod_auth_hardening.py \
  keel/tests/test_prod_mcp.py \
  keel/tests/test_prod_db_recovery.py \
  keel/tests/test_prod_perffix.py \
  keel/tests/test_backend_workflows.py
```

**Result: `160 passed in 37.89s`, exit 0, 0 failures / 0 errors.** Working tree stayed clean.

---

## 4. Findings

### F-01 — BLOCKER — candidate forbids its own promotion

`PRODUCTION-READINESS-REPORT.md:173` — "IMPLEMENTATION PRODUCTION-HARDENED — PROMOTION
BLOCKED BY UNVERIFIED MANDATORY GATES". `PRODUCTION-READINESS-REPORT.md:177-182` enumerates
the outstanding owner/external work; `PRODUCTION-READINESS-MATRIX.md:1,3,14,33` and
`FINAL-RELEASE-ACCEPTANCE.md:29,67-78` report 13 pass / **5 unverified** / **2 blocked** /
0 `production_verified`. Nothing in `745ac86..ac84fee` closes those gates.
**Fix:** obtain the owner/external evidence and re-issue the matrix against the final SHA,
or reaffirm the block and do not promote.

### F-02 — HIGH — temp runner with hardcoded personal path is still committed

`keel/_prod_suite_tmp.py:1-7` — a scratch pytest launcher containing
`home = r"C:\Users\Admin\AppData\Local\Temp\opencode\prodhome"`, mutating `HOME`/
`USERPROFILE` and `sys.path`, then calling `pytest.main(...)`. It is not imported by any
source or test (repo-wide grep returns only this report, the acceptance report and the
manifest). `PRODUCTION-PROMOTION-MANIFEST.md:89` falsely labels it
`REQUIRED_BACKEND_DEPENDENCY / Required local dependency`, and
`FINAL-RELEASE-ACCEPTANCE.md:27,53-65,139-140` already identified it as B2 and required
its deletion; the deletion was never done.
**Fix:** `git rm keel/_prod_suite_tmp.py`, remove its manifest row, and record the removal
in the promotion classification.

### F-03 — HIGH — review evidence is attributed to stale SHAs, so it does not certify `ac84fee`

Exact locations (claim → reality at `ac84fee`):

* `PRODUCTION-PROMOTION-MANIFEST.md:6` — `Source SHA fe6cdd77…` (stale).
* `PRODUCTION-PROMOTION-MANIFEST.md:13` — `Changed paths 383`; actual 422.
* `PRODUCTION-PROMOTION-MANIFEST.md:490` — `Authoritative candidate SHA cbdfc28…`; actual `ac84fee`.
* `PROMOTION-PATH-INVENTORY.txt:1` — 383-path inventory; actual 422.
* `PRODUCTION-READINESS-MATRIX.md:1,3,14,33` and `PRODUCTION-READINESS-REPORT.md:1,3,150` — candidate `e573273…`, line numbers keyed to it.
* `FINAL-RELEASE-ACCEPTANCE.md:3,9,15` — verdict for `5783474…`, not the final candidate.
* `PROD-SUPPLY-CHAIN-EVIDENCE.md:5,24,156,169,188,346,419` — "current candidate tip `5783474`" and results from `e573273`/`5783474`.
* `PROD-OBSERVABILITY-EVIDENCE.md:3`, `BACKEND-DEPLOYMENT.md:3`,
  `BACKEND-INCIDENT-RESPONSE.md:3`, `BACKEND-MONITORING.md:3`,
  `BACKEND-OPERATIONS-RUNBOOK.md:3` — `Candidate HEAD: e573273`.
* `PRODUCTION-REQUIREMENT-RECONCILIATION.md:13-19,66,76` — still discusses the
  `e573273` vs candidate mismatch as open.
**Fix:** re-issue or explicitly re-base each evidence header at `ac84fee`, or add a single
authoritative addendum that maps every prior SHA to the final candidate and states which
results were re-run at the final SHA (§1 and §3 of this report supply the re-run data).

### F-04 — MEDIUM — `promotion-classification.json` is stale and internally inconsistent

`promotion-classification.json:classification` has **383** entries, while the candidate
has **422** paths: 67 candidate paths are unclassified (all `PROD-*-EVIDENCE.md`, 5 new
backend sources, 12 `test_prod_*.py`, 22 `perf-harness/*`, the temp runner, etc.) and 28
entries are stale frontend/probe paths no longer in the diff
(`keel/site/app.html`, `keel/site/ui/app.js`, `keel/site/ui/style.css`, `keel/desktop/sw.js`,
`keel/desktop-app/main.js`, `probe/*`, etc.). The human-readable manifest is correct
(422/422), but the machine-readable companion contradicts it.
**Fix:** regenerate the JSON from `git diff --name-only origin/main...HEAD` at `ac84fee`
using the manifest's classifications.

### F-05 — MEDIUM — clean full suite is not green; 8 failures are documented, not fixed

`PRODUCTION-READINESS-REPORT.md:175` records `4419 passed / 8 failed / 51 skipped /
3707 subtests`; `master-plan-v6-test-evidence.md:220-240` accounts for them: 2
load-dependent tests (`test_tool_requires_approval_then_approved_runs`,
`test_e2e_milestone_6b`) and 6 tests needing untracked generated artifacts
(`keel/release/RELEASE-MANIFEST.json`, `RELEASE-SHA256SUMS.txt`, `keel/dist/`,
`keel/downloads/Keel_Master_Plan_v5.md`). A promote-to-`main` checkout/CI run cannot be
called green on that basis. The representative error-focused set is green (§3), but it
does not cover these paths.
**Fix:** make the 6 artifact tests skip with an explicit reason when artifacts are absent
(or have CI generate `downloads/` too), and quarantine/stabilise the 2 order-dependent
tests; then require a fully green clean-checkout run.

### F-06 — MEDIUM — stale verdicts contradicted by current code

These are not merely old SHAs; the stated condition no longer holds in the candidate:

* `PRODUCTION-ARCHITECTURE-AUDIT.md:20,106-110,220,221,227,230,275-278` treats HIGH-1
  ("workflow path bypasses capability boundaries") as open. Current code
  `keel/src/keel/backend_workflows.py:1547-1601` now calls
  `policy_enforcement.enforce()` and `capabilities.record_audit()` on the workflow path,
  and returns typed `policy_denied` / `policy_error` / `confirmation_required`. The
  "no fix commit / no regression test" verdict (also `FINAL-RELEASE-ACCEPTANCE.md:82-96,131`)
  is stale as to the fix and still accurate as to the missing dedicated test (F-07).
* `PRODUCTION-ARCHITECTURE-AUDIT.md:245` claims
  `PRODUCTION-PROMOTION-MANIFEST.md:66-68,102-106` classifies frontend files as
  `UNRELATED_EXCLUDED`; the current manifest contains no `UNRELATED_EXCLUDED` rows at all
  (the files are simply absent).
* `PROD-AUTH-EVIDENCE.md:162-166,183-190` documents limitation L1 — "`invoke` ignores an
  `ask` verdict; only `deny` aborts". `keel/src/keel/capabilities.py:117-122` now fails
  closed on `ask` without `confirm is True`, and `test_prod_cap_gate.py` covers it.
* `PROD-PERFORMANCE-EVIDENCE.md:37,266-267,269-307` says "None of these were implemented"
  and marks three issues BLOCKING. Current code has all three fixed:
  `backend_hub.py:389-401` (no import-time `assert_dispatch_targets()` /
  `_publish_schemas_on_import()`), `fleet/service.py:197-215` (slug select + INSERT in one
  lock), `fleet/service.py:99-106` (`json_extract(..., '$.status') = 'pending'`).
* `PRODUCTION-READINESS-REPORT.md:184-186` claims "All internally actionable HIGH/MEDIUM
  findings … were fixed with failing-then-passing regression tests and re-reviewed."
  Two are still open in code: MEDIUM-4 (`capabilities.py:80,88-89` defaults
  `allowed_permissions` to all three tiers; repo-wide grep finds no caller passing it —
  only the definition and the default) and MEDIUM-6 (`backend_events` /
  `backend_observability` have no runtime consumer outside tests; grep across
  `src/keel` finds only `backend_events.py:96` `SCHEMA_ID`). Neither is formally
  descoped in the manifest.
**Fix:** update each cited line to "closed at `ac84fee` (test …)" or "accepted residual
risk", and either fix or formally descope MEDIUM-4/MEDIUM-6 before repeating the blanket
claim.

### F-07 — MEDIUM — workflow enforcement/audit path is still asymmetric and untested

`keel/src/keel/backend_workflows.py:1564-1601`: `record_audit()` runs only after a
handler succeeds (`:1591-1598`). `bad_params`, `unknown_workflow`, `bad_state_root`,
`policy_error`, `policy_denied` and `confirmation_required` all return early (`:1555-1589`)
with **no audit record**, whereas the capability path audits denials and errors too
(`webapp.py:710-743`). No test exercises saved-policy enforcement or audit on the
workflow path: `keel/tests/test_backend_workflows.py` has no `policy`/`record_audit`
reference beyond `test_delegation_workflow_enforces_child_bound` at line 221;
`test_prod_api.py:307-317` exercises workflow-local `deny_rules`, not the saved exec
policy. This is the residual part of the prior HIGH-1 requirement
(`FINAL-RELEASE-ACCEPTANCE.md:141`: "add a regression test asserting one enforcement/audit
path").
**Fix:** emit `record_audit(..., ok=False, code=...)` on every early-return branch (a
`finally` block with a computed outcome is simplest) and add a test that saves a
`forbidden` exec policy, calls `run_workflow("request", ...)` / the HTTP route, and
asserts both `policy_denied` and an audit record with `surface="workflow"`.

### F-08 — MEDIUM — SHA-pin counts are stale

Actual: 31 `uses:` refs, 0 tag-only. Claims: `master-plan-v6-test-evidence.md:48` (26),
`:121` and `:151` (30); `PROD-SUPPLY-CHAIN-EVIDENCE.md:56,114,310` (30/30) — while the
same file at `:378,381` correctly says 31 and explains the new `setup-node` ref;
`master-plan-v6-final-report.md:46,75,149` (20/20) refers to the older integration branch.
**Fix:** update the earlier counts to 31 and mark the 20/20 figures historical.

### F-09 — LOW — classification inventory header drift

`PRODUCTION-PROMOTION-MANIFEST.md:5-13` names branch `integration/backend-completion…`
and SHA `fe6cdd7…`, and `:487-492` names `cbdfc28…` as authoritative, while the actual
final candidate is `ac84fee…`. `PROMOTION-PATH-INVENTORY.txt` still lists 383 paths.
This is covered by F-03 but called out separately because it is the artifact a promoter
would consult first. **Fix:** regenerate both at the final SHA.

---

## 5. What is confirmed good

* All mandatory local governance gates green, with `--strict` evidence enforcement
  passing 421/421.
* 20 backend modules import and integrate; registry arithmetic (865 = 854 + 9 + 2) and
  the 421 attributed IDs are consistent.
* Scope is backend-only plus the documented one-line `Cargo.toml` version bump; no
  frontend/desktop source in the candidate; all 422 changed paths appear in the manifest.
* Clean working tree; no real secrets or generated user data found; no untracked artifacts.
* Representative error-focused suite: 160/160 passed in a fresh HOME.

## 6. Recommendation

**Do not promote.** Close F-01 (owner/external gates) first; then remove the temp runner
(F-02), re-base the evidence on `ac84fee` (F-03/F-08/F-09), regenerate the classification
JSON (F-04), obtain a green clean full suite (F-05), and close/descope F-06/F-07. Re-audit
after those changes.
