# FINAL-CI-DIAGNOSIS

**BLOCKER VERDICT (report first): the GitHub Actions failures are an external GitHub **account billing / payment** blocker, not a repository defect.** Every failing job carries the authoritative check-run annotation:

> `The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings`

No repository change can make these jobs start. The account owner must resolve billing (failed payment and/or spending limit) in GitHub **Settings → Billing & plans**, then re-run. Only after runners are actually assigned can workflow/source issues be assessed. A separate, secondary repository-side issue was found locally: `secret-scan` would likely report 4 (synthetic) gitleaks findings once jobs can run — see §6.

Scope: read-only investigation of worktree `C:\Users\Admin\.local\share\opencode\worktree\final\ci` (branch `agent/final-ci`, HEAD `35fb2b8`), repo `eliosmernica15/keel` (private, personal account), `gh` v2.83.2, token scopes `gist, read:org, repo, workflow`. No source was edited; no push.

---

## 1. Root-cause classification (precise split)

| Classification | Finding | Fixable in repo? |
|---|---|---|
| **External account blocker — ROOT CAUSE** | GitHub refused to dispatch *every* job on 2026-11-24/25 because account payments failed or the spending limit needs raising. Exact annotation on every failing check run. 0 steps, 0 billable ms, `runner_id: 0`, empty log archive. | **No.** Owner billing action required. |
| External visibility limitation | Billing endpoints return 404 to this token; exact balance/payment state not observable via API. Annotation is authoritative. | No. |
| External plan limitation (not causal) | Branch-protection API returns 403 ("Upgrade to GitHub Pro or make this repository public"). Private free plan; all-runs history shows heavy macOS/Windows matrix usage. | No (plan). |
| External integration blocker (separate from Actions) | Commit status `Vercel`: `Deployment rate limited — retry in 24 hours.` target `https://vercel.com/losis-projects?upgradeToPro=build-rate-limit`. | No. |
| Repository follow-up (secondary, not the current cause) | gitleaks on the final tree reports 4 findings (synthetic fixtures / evidence-doc examples) that are not covered by narrow allowlists in `.gitleaks.toml`. | **Yes** — security/supply-chain owner. |
| Repository follow-up (unproven) | One local full-suite failure (`test_api_contracts.py::test_conformance_audit_confirms_current_nonconformance`) with Windows socket abort `WinError 10053`. Not reproduced on a hosted runner. | Maybe; do not treat as CI evidence yet. |
| **Not a cause** | Workflow syntax, action SHA pins, missing secrets, runner labels, first-time-contributor approval, job-level `if` gates. Evidence in §4. | n/a |

---

## 2. Exact API evidence — failing runs (2026-11-25T02:56Z)

### 2.1 Run-level (identical signature for all four)

`GET /repos/eliosmernica15/keel/actions/runs/{id}` (trimmed to exact relevant fields):

```json
{"id":45536422111,"name":"Python tests","event":"push","status":"completed","conclusion":"failure",
 "created_at":"2026-11-25T02:56:04Z","run_started_at":"2026-11-25T02:56:04Z","updated_at":"2026-11-25T02:56:07Z",
 "head_branch":"main","head_sha":"35fb2b8abfd784393b2b252e2b9e2927aba817dd",
 "head_repository":{"full_name":"eliosmernica15/keel"},"actor":{"login":"eliosmernica15"},
 "triggering_actor":{"login":"eliosmernica15"},"run_attempt":1,"workflow_id":424013782}
```
Same for `45536422136` ("Secret scan", workflow_id 425398937), `45536422156` ("Offline + license gates", 429275896), `45536422231` ("Provider validation", 427226798). All: `created_at == run_started_at == 02:56:04Z`, `updated_at == 02:56:07Z`, conclusion `failure`.

### 2.2 Jobs — steps count and runner assignment

`GET /repos/eliosmernica15/keel/actions/runs/{id}/jobs?per_page=100` (exact fields; all `status: completed`, `conclusion: failure`, `steps: []`, `runner_group_id: 0`, `runner_group_name: ""`, `runner_name: ""`, `run_attempt: 1`):

| Run | Job ID | Job name | Labels | created | started | completed | steps | runner_id |
|---|---|---|---|---|---|---|---|---|
| 45536422111 | 138944015384 | pytest (windows-latest) | `windows-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422111 | 138944015628 | pytest (ubuntu-latest) | `ubuntu-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422111 | 138944015709 | pytest (macos-latest) | `macos-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422136 | 138944015866 | gitleaks (full history) | `ubuntu-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422156 | 138944015512 | model/voice license gate | `ubuntu-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422156 | 138944015781 | offline boot + coding task (no network namespace) | `ubuntu-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422231 | 138944016198 | provider-validation | `ubuntu-latest` | 02:56:05Z | 02:56:05Z | 02:56:06Z | 0 | 0 |
| 45536422157 | 138944016888 | validate-versions | `ubuntu-latest` | 02:56:05Z | 02:56:05Z | 02:56:07Z | 0 | 0 |

Full single-job example (`GET /actions/jobs/138944015384`):

```json
{"id":138944015384,"name":"pytest (windows-latest)","status":"completed","conclusion":"failure",
 "created_at":"2026-11-25T02:56:05Z","started_at":"2026-11-25T02:56:05Z","completed_at":"2026-11-25T02:56:06Z",
 "runner_id":0,"runner_name":"","runner_group_id":0,"runner_group_name":"",
 "labels":["windows-latest"],"steps":[],"workflow_name":"Python tests","run_attempt":1}
```

### 2.3 Timing — zero runner time billed

`GET /actions/runs/{id}/timing` (exact output):

```json
{"billable":{"MACOS":{"job_runs":[{"duration_ms":0,"job_id":138944015709}],"jobs":1,"total_ms":0},
"UBUNTU":{"job_runs":[{"duration_ms":0,"job_id":138944015628}],"jobs":1,"total_ms":0},
"WINDOWS":{"job_runs":[{"duration_ms":0,"job_id":138944015384}],"jobs":1,"total_ms":0}},"run_duration_ms":3000}
```
```json
{"billable":{"UBUNTU":{"job_runs":[{"duration_ms":0,"job_id":138944015866}],"jobs":1,"total_ms":0}},"run_duration_ms":3000}
```
```json
{"billable":{"UBUNTU":{"job_runs":[{"duration_ms":0,"job_id":138944015512},{"duration_ms":0,"job_id":138944015781}],"jobs":2,"total_ms":0}},"run_duration_ms":3000}
```
```json
{"billable":{"UBUNTU":{"job_runs":[{"duration_ms":0,"job_id":138944016198}],"jobs":1,"total_ms":0}},"run_duration_ms":3000}
```
Every job has `duration_ms: 0`; every run `run_duration_ms: 3000`. A runner was never assigned.

### 2.4 Annotations — the decisive evidence

`GET /repos/eliosmernica15/keel/check-runs/{job_id}/annotations?per_page=100` (note: `/actions/runs/{id}/annotations` returns 404; annotations live on check runs):

```json
[{"annotation_level":"failure",
  "message":"The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing \u0026 plans' section in your settings",
  "path":".github","raw_details":"","start_line":1,"end_line":1,
  "start_column":null,"end_column":null,"title":""}]
```

This exact failure annotation was returned for **all 8 failing jobs listed in §2.2** (3 pytest, gitleaks, 2 offline/license, provider-validation, validate-versions). One additional non-causal notice exists only on `pytest (macos-latest)`:

```json
{"annotation_level":"notice",
 "message":"Due to capacity constraints, jobs targeting macOS arm64 runners may experience longer queue times.",
 "path":".github"}
```
A notice about queue capacity cannot explain a 0-second, `runner_id: 0` failure that also hits Linux and Windows jobs simultaneously; it is informational only.

### 2.5 Logs — nothing was ever executed

- `GET /actions/runs/{id}/logs` returns a **22-byte ZIP with zero entries** (just the EOCD `PK\x05\x06`) for all four runs. A normal run returns a ZIP containing per-step text logs.
- `GET /actions/jobs/138944015384/logs` returns HTTP 404 with Azure `BlobNotFound`: `The specified blob does not exist.`
- `GET /actions/runs/{id}/annotations` → 404 `Not Found` (annotations are on check runs, not runs).
- Check-run `output` for failed jobs: `{"annotations_count":1,"summary":null,"text":null,"title":null}` — no step output because no step ran.

### 2.6 Build desktop installers (run 45536422157) and verify-install (run 45536434875)

`validate-versions` (138944016888) failed with the same billing annotation, steps 0, runner_id 0. All 8 downstream jobs were `conclusion: skipped`, `steps: []`, `runner_id: null`, **no annotations** — normal `needs:` propagation after the root job was refused by GitHub, not independent failures.

`Verify installed packages (clean runners)` (45536434875, event `workflow_run`, `conclusion: skipped`) had all four jobs `skipped` with no annotations:

```json
[{"name":"macos-package","conclusion":"skipped","steps":0,"runner_id":null},
 {"name":"windows-install","conclusion":"skipped","steps":0,"runner_id":null},
 {"name":"linux-package","conclusion":"skipped","steps":0,"runner_id":null},
 {"name":"Trusted trigger guard (fail closed)","conclusion":"skipped","steps":0,"runner_id":null}]
```
Cause is the workflow's own fail-closed `if:` guard (upstream build did not succeed), plus skipped `needs:` dependents. This is correct behavior, not the blocker.

---

## 3. Temporal evidence — the blocker predates the final tree

`GET /actions/runs?per_page=100&page=2`, sorted, shows a hard cutoff:

- **Last successful runs:** 2026-11-23T00:53:01Z (push, `main` — Python tests, Secret scan, Build desktop, Provider validation), 2026-11-23T01:01:10Z and 01:02:01Z (`workflow_run` verify-install). All had real runners and steps.
- **First failing runs:** 2026-11-24T16:21:38Z (pull_request `feat/frontend-completion-2026-11-24`, head_sha `0ed470b…`). Its job 138594594557 has the same billing annotation, steps 0, runner_id 0, and timing `duration_ms: 0`.
- Every subsequent run on 2026-11-24/25 fails the same way, including pushes to `main` by the repo owner at commit `35fb2b8`.

Contrast with a successful run (`GET /actions/runs/45091349713/jobs`, commit `ecba9d2b`, 2026-11-23T00:53Z):

```json
[{"name":"validate-versions","conclusion":"success","runner_id":1000002601,"steps":7},
 {"name":"build-linux","conclusion":"success","runner_id":1000002608,"steps":11},
 {"name":"build-windows","conclusion":"success","runner_id":1000002607,"steps":10},
 {"name":"build-macos","conclusion":"success","runner_id":1000002618,"steps":10}]
```
`GET /check-runs/137421396682/annotations` → `[]`. Job steps in that run include `Set up job`, `Run actions/checkout@v7`, etc., with real runner names `GitHub Actions 1000002601` etc.

The action pins changed from `@v7` tags to commit SHAs between the last success and the first failure. All five pinned SHAs used by these workflows resolve to real commits (`actions/checkout@3d3c42e5…` "prep v7.0.1 release", `setup-python@6d4fd22b…`, `setup-node@949feb24…`, `upload-artifact@cf430e03…`, `download-artifact@9000827c…`). The platform annotation explicitly names billing, so this change is a red herring, not the cause.

---

## 4. Hypotheses explicitly ruled out (with API output)

**Repository Actions settings — enabled, no dispatch restriction:**
```json
GET /repos/eliosmernica15/keel/actions/permissions
{"allowed_actions":"all","enabled":true,"sha_pinning_required":false}
GET /repos/eliosmernica15/keel/actions/permissions/workflow
{"can_approve_pull_request_reviews":false,"default_workflow_permissions":"read"}
```

**Secrets/variables:** `GET /actions/secrets` → `{"secrets":[],"total_count":0}`; `GET /actions/variables` → `{"total_count":0,"variables":[]}`. Missing secrets cannot cause a pre-run failure: no step executed, and provider/live-signing steps are designed to skip or fail open on absence. The annotation is billing, not `secrets.*`.

**Account/actor context — no first-time-contributor approval gate:**
```json
GET /repos/eliosmernica15/keel
{"full_name":"eliosmernica15/keel","private":true,"owner":{"login":"eliosmernica15","type":"User"},
 "default_branch":"main","permissions":{"admin":true,"maintain":true,"pull":true,"push":true,"triage":true}}
```
`actor` and `triggering_actor` are `eliosmernica15` (admin/owner), `head_repository.full_name` equals `github.repository`, and the first failing run was a pull_request from the same repository. Historical `workflow_dispatch` runs (e.g. 45069689246, 45080790571) succeeded on 2026-11-22, so manual approvals are not blocking. An approval gate would show a "waiting" state, not an immediate billing annotation.

**Organization context:** personal account only — `GET /user/organizations` → 404 `Not Found`; owner `type: User`. There is no org policy/ruleset in scope.

**Runner availability / labels:** all jobs use GitHub-hosted `ubuntu-latest`, `windows-latest`, `macos-latest` (matrix expanded correctly); `GET /actions/runners` → `{"runners":[],"total_count":0}` is expected for hosted runners; historical jobs on the same labels ran with real runner IDs. No `environment:` approval keys exist in any workflow; no job-level `if` exists on any failing job (only tag-gated publish/signing and verify-install trust-gate, all of which are *skipped*, not failed).

**Workflow syntax:** all 8 workflows are `state: active` in `GET /actions/workflows`; local PyYAML parse succeeds and yields the expected job names. GitHub created correctly named jobs and check runs (not an "Invalid workflow file" job). No syntax annotation exists.

**Branch protection:** `GET /branches/main/protection` → 403 `Upgrade to GitHub Pro or make this repository public to enable this feature.` This is a free-private-plan limitation, unrelated to job dispatch (and no protection rules are in force).

**Billing/quota visibility through this token:** all of `GET /user/billing/actions`, `/user/billing/ghe`, `/repos/eliosmernica15/keel/actions/billing`, `/orgs/eliosmernica15/billing/actions` → 404 `Not Found`. `GET /user` exposes no `plan` field. Therefore the exact balance/card state cannot be asserted from the API; the check-run annotation is the authoritative statement of the blocker.

**Separate external status (not Actions):** `GET /commits/{sha}/status` →
```json
{"state":"failure","statuses":[{"context":"Vercel","state":"failure",
 "description":"Deployment rate limited — retry in 24 hours.",
 "target_url":"https://vercel.com/losis-projects?upgradeToPro=build-rate-limit"}]}
```
This affects deployment only, not runner assignment.

---

## 5. Local reproduction from the final tree (clean HOME)

Commands were run from the final tree with `HOME`/`USERPROFILE` redirected to an empty temp directory
(`C:\Users\Admin\AppData\Local\Temp\opencode\clean-home-ci`). `PYTHONPATH` was pinned to this worktree's
`keel\src`: without that, an editable install in `C:\Users\Admin\Desktop\Claude clone\keel\src` shadows the
final tree and causes false collection errors. These results confirm **source-side health only**; they do **not**
mean any GitHub Actions workflow passed.

| Workflow command (as written in the workflow) | Local result |
|---|---|
| `python scripts/check_model_licenses.py` | `LICENSE GATE OK` (11 entries, 0 bundled) |
| `python scripts/verify_supply_chain.py` (in `keel/`) | `SUPPLY CHAIN VERIFICATION OK` (34 lock entries, 8 required pins, SBOM matched) |
| `python scripts/verify_v6_audit.py` | `CONSISTENCY OK` (865 rows) |
| `python keel/scripts/build_dependency_graph.py --check` | `FRESH: …\DEPENDENCY-GRAPH.md` |
| `python scripts/check_version_sync.py` (in `keel/`) | `OK - all sources agree on version 0.1.1 (tag v0.1.1)` |
| Python-tests lock-freshness heredoc (extracted verbatim from the workflow) | `LOCK FRESHNESS OK: 34 pinned packages, 8 required pins checked` |
| Provider fixtures: `pytest -q tests/test_provider_validation_ready.py tests/test_provider_validation.py tests/test_secret_storage.py` | `14 passed` |
| Offline test files (run directly; `unshare` is Linux-only and unavailable on Windows): `pytest -q tests/test_offline_runtime.py tests/test_cli_e2e.py tests/test_e2e_local.py`, `KEEL_TOKEN=offline-ci-token` | `11 passed` |
| `node --check desktop-app/main.js` | exit 0 |
| `node desktop-app/scripts/test-ui-root.js` | `SUMMARY: 8/8 uiRoot() cases passed` |
| `node desktop-app/scripts/assert-ui-entrypoints.js` | `SUMMARY: 25/25 checks passed` |
| Gitleaks download from workflow URL | SHA-256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` — matches `GITLEAKS_SHA256` exactly |
| Gitleaks `detect --no-banner --redact --config .gitleaks.toml … .` (v8.30.1 via WSL, standalone clone at HEAD `35fb2b8`, config from final tree) | **671 commits scanned, 4 leaks, exit 1** — see §6 |
| Full suite `pytest -q` with `KEEL_TOKEN=ci-test-token` | **4609 passed, 1 failed, 54 skipped, 3707 subtests passed** (875 s). Failure: `tests/test_api_contracts.py::test_conformance_audit_confirms_current_nonconformance`, `ConnectionAbortedError: [WinError 10053]` on a local HTTP connection. Not reproduced on a hosted runner; do not treat as CI evidence. |

Not fully reproduced locally: PyInstaller/electron-builder packaging and native DEB/RPM/PKG/NSIS builds (build-desktop),
`unshare -Urn` network namespace (Linux-only), and verify-install/upgrade-lifecycle artifacts (need successful
build-run artifacts on native runners). `verify_keel_runtime.py`/`verify_keel_chrome.py` were not used as a substitute
for the workflow commands.

---

## 6. Secondary repository-side finding — gitleaks would fail after billing is restored

Local scan of the exact final-tree commit (`35fb2b8`, clone HEAD verified) with the pinned binary/config:

```
INF 671 commits scanned.
WRN leaks found: 4
EXIT=1
```

Findings (all `Secret`/`Match` values redacted by `--redact`; no secret values are reproduced here):

| Rule | Path | Line | Commit | Classification |
|---|---|---|---|---|
| generic-api-key | `keel/tests/verify_distribution_provider_hardening.py` | 49 | `ce78f10` | synthetic fixture (`sk-fixture-secret-…`) |
| generic-api-key | `keel/tests/verify_distribution_provider_onboarding.py` | 185 | `ce78f10` | synthetic fixture |
| aws-access-token | `STAB-CI-EVIDENCE.md` | 48 | `781b4cf` | evidence text quoting a synthetic `AKIA…` example |
| aws-access-token | `STAB-SUPPLY-EVIDENCE.md` | 102 | `c949891` | known documented remaining finding |

The repository's own `STAB-CI-EVIDENCE.md` already records that `STAB-SUPPLY-EVIDENCE.md:102` needs a narrow
allowlist and says "This repo must not be claimed as secret-scan-clean until that is done." Current
`.gitleaks.toml` has no allowlist entry for any of these four commit+path+rule combinations. This is a **real
repository-side follow-up**, but it is not the cause of the current pre-run failures (which happen before any
gitleaks step exists).

---

## 7. Recommendations for the lead

1. **Blocker action (external, owner only):** check GitHub **Settings → Billing & plans** for the failed payment and/or spending limit, restore Actions service, then re-run the five workflows at `35fb2b8`. Until the check-run annotation changes, treat all red CI statuses as infrastructure, not code regressions. Capture a UI screenshot of the billing page as evidence: billing APIs return 404 to this token.
2. **Do not "fix" this by editing workflows.** There is no job-level `if`, runner label, secret, syntax, or SHA-pin change that can address a pre-dispatch billing refusal. Do not report workflows as passing based on the local runs in §5.
3. **After billing is restored, expect `Secret scan` to fail** unless the four findings in §6 are addressed. Ask the security/supply-chain owner to add narrow (commit + path + rule) allowlist entries or rewrite the synthetic fixtures, then re-run gitleaks locally to a clean result.
4. **Cost hardening (optional, after restore):** heavy three-OS build/test matrices consume multiplied macOS/Windows minutes on a private plan. Restrict the heaviest matrix to release tags, add caching, and keep `concurrency` cancel-in-progress for non-tag pushes (already present in build-desktop.yml). This reduces recurrence risk but does not remove the current blocker.
5. **Re-evaluate the single local pytest failure** (`test_api_contracts…` / WinError 10053) only when a hosted runner actually executes the suite; it is likely local Windows socket behavior, but no CI claim should be made until observed there.
6. **Track Vercel separately** as an external deployment rate limit (`retry in 24 hours` / upgrade prompt) — it is not an Actions blocker and has no repository-side fix.
