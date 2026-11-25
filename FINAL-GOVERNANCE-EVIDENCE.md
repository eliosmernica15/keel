# Final governance evidence — repository governance on GitHub Free

Branch: `agent/final-governance` · base HEAD: `35fb2b8` · owner account: `@eliosmernica15` · repository: `eliosmernica15/keel` (private, personal, free plan) · default branch: `main`.

Owned files in this operation:

- `.github/CODEOWNERS` (new)
- `.github/PULL_REQUEST_TEMPLATE.md` (new)
- `.github/workflows/release-authorization.yml` (new)
- `.github/workflows/build-desktop.yml` and `.github/workflows/lifecycle.yml` (permission/trust hardening + gate wiring only)
- `scripts/verify_release_authorization.py` (new)
- this evidence file

No source or frontend file was changed. Nothing was pushed. Repository visibility, billing and admin settings were not touched.

---

## 1. What was actually changed

### 1.1 Workflow-level release authorization (enforced at runtime on GitHub Actions)

`.github/workflows/release-authorization.yml` is a reusable (`workflow_call`) and manually dispatchable (`workflow_dispatch`) job that runs `scripts/verify_release_authorization.py`. The script fails closed on **every** finding; there is no warn-only mode.

`build-desktop.yml` now defines a `release-authorization` job that calls that workflow on every `v*` tag push, and both privileged release jobs depend on it:

- `verify-release-signatures.needs` includes `release-authorization`
- `publish.needs` includes `release-authorization`

A failed gate job skips the signing gate and publish job. This is a real GitHub-side dependency, not a local convention.

The gate verifies, on the tagged commit:

| # | Check | Implementation |
|---|---|---|
| 1 | Tag | `^v\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$` plus `gh api repos/{repo}/git/ref/tags/{tag}` must resolve |
| 2 | Head branch | must be `main` or the tag ref itself; `gh api repos/{repo}/compare/main...{tag}` status must be `behind` or `identical` (tagged commit contained in `main`) |
| 3 | Actor trust | non-bot GitHub login in the owner allowlist, `triggering_actor == actor`, repo `owner.login` and `full_name` from `gh api` must match the allowlisted owner/repository |
| 4 | Evidence | `FINAL-GOVERNANCE-EVIDENCE.md`, `PRODUCTION-PROMOTION-MANIFEST.md`, `FINAL-STABILIZATION-ACCEPTANCE.md`, `PROD-SUPPLY-CHAIN-EVIDENCE.md`, `STAB-WORKFLOW-EVIDENCE.md` all present and non-empty |
| 5 | Approval marker | exactly one explicit `RELEASE-APPROVED: <tag> by @<owner>` line in `FINAL-GOVERNANCE-EVIDENCE.md`, outside a fenced code block, with a matching tag and allowlisted approver |

### 1.2 Artifact trust in privileged jobs

`build-desktop.yml` already built and verified artifacts within one run before publishing, with no `pull_request_target`. `verify-install.yml` already had a fail-closed `workflow_run` trust gate. `lifecycle.yml` previously downloaded and **executed** installers from an operator-supplied `run_id` with no validation; it now has a `trust-gate` job that requires all three lifecycle jobs, verifies the run is a numeric, successful `push` of `Build desktop installers` from this repo's default branch, and that the actor is the allowlisted owner. A fork/PR/failed run is refused before any installer executes.

### 1.3 Least privilege and pinning

All nine workflows declare top-level `permissions`. The only `write` scope is `contents: write` on `build-desktop.yml`'s `publish` job, which is required to create a GitHub Release and is now downstream of the gate. `actions: read` is present only where `gh run download` / `gh api /actions/runs` needs it (`lifecycle.yml` and `verify-install.yml`); the gate-wiring job in `build-desktop.yml` uses `contents: read` only. Every external `uses:` ref is a full 40-hex commit SHA with a version comment; the one non-SHA `uses:` is the local reusable workflow path `./.github/workflows/release-authorization.yml`, which is a path by design.

---

## 2. Exact verification performed

All commands were run locally in the worktree; the `gh` CLI was replaced by a stub for the authorization script because this agent has no network/permission to call the live API. The stub implements the four read-only endpoints (`repos/{repo}`, `git/ref/tags/{tag}`, `compare/{base}...{tag}`) and is the only substitution — the gate's decision logic is unchanged.

| Check | Command / method | Result |
|---|---|---|
| YAML parses | `python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]"` (PyYAML 6.0.3) | **9 / 9** workflows parse |
| No dangerous trigger | regex scan of all workflow trigger keys for `pull_request_target` | **0** occurrences |
| Action pinning | regex scan `^\s*-?\s*uses:\s*(\S+)` over all workflow files; SHA checked with `^[0-9a-f]{40}$` | **42 / 42** external action refs are full SHAs; **1** local reusable-workflow path (not an action) |
| Permission minimality | parse `permissions:` at workflow and job level; enumerate every `write`/`all` | only `build-desktop.yml` / `publish` / `contents: write`; no `all` |
| Gate wiring | read `needs:` of `verify-release-signatures` and `publish` in `build-desktop.yml` | both include `release-authorization` |
| Artifact trust | read `needs:` of all three `lifecycle.yml` installer jobs | all three include `trust-gate` |
| Combined harness | `python C:\Users\Admin\AppData\Local\Temp\opencode\governance-verify\verify_governance_local.py` | **43 checks, 43 passed, 0 failed** |
| Authorization script, positive | stub `gh` returns owner=`eliosmernica15`, full_name matching, tag exists, compare status=`behind`; temp evidence tree with a valid marker for the test tag | exit **0**, `RESULT: AUTHORIZED` |
| Authorization script, negative | see cases below | all exit **1**, `RESULT: NOT AUTHORIZED` |

Negative cases exercised against the stub (each one changed a single input):

1. malformed tag (`release-latest`)
2. tag does not exist in repository
3. head branch is a feature branch
4. compare status `ahead` (tag not contained in `main`)
5. compare status `diverged`
6. untrusted actor (`attacker`)
7. bot actor (`eliosmernica15[bot]`)
8. `triggering_actor` mismatch
9. repository owner not allowlisted
10. repository `full_name` mismatch
11. `gh` lookup fails / wrong repository
12. required evidence file missing
13. approval marker missing
14. approval marker for a different tag
15. approval marker signed by a non-owner
16. two conflicting approval markers
17. approval marker only inside a fenced code block
18. real repository evidence with the deliberately inert placeholder marker and a real-looking tag — blocked

The reproduction harness lives outside the repository at `C:\Users\Admin\AppData\Local\Temp\opencode\governance-verify\verify_governance_local.py`; it is not committed. It creates a disposable stub `gh` and a temporary evidence tree, runs the script for every case above, and prints a pass/fail line per case plus a total.

### Approval marker state in this repository

RELEASE-APPROVED: NOT-APPROVED by @nobody

The line above is deliberately inert. It is a structural placeholder, not an approval: the tag is not a semver release tag and the approver is not the owner allowlist. It exists so the marker format is demonstrable while making it impossible for this governance commit to authorize any real release. To authorize a release, the owner replaces that single line with `RELEASE-APPROVED: <exact-tag> by @eliosmernica15` in this file, commits it to `main`, and tags that commit — the gate then checks it on the tagged commit.

---

## 3. Genuinely enforceable on GitHub Free (active once merged)

| Control | Where | Enforcement |
|---|---|---|
| Release cannot publish unless tag, branch containment, actor, evidence and marker checks pass | `release-authorization.yml` called as a job from `build-desktop.yml` | **GitHub Actions runtime job dependency** — enforced on every `v*` tag push |
| No `pull_request_target`; PR runs use plain `pull_request` with read-only token | all workflows | **GitHub Actions runtime** token/scoping |
| Actions resolved by immutable commit SHA | all workflows | **GitHub Actions runtime** resolution |
| Fork/PR/failed-run artifacts refused before installer execution | `verify-install.yml`, `lifecycle.yml` trust gates | **GitHub Actions runtime** (job skips/fails) |
| Signing public-key gate fails closed when secret missing | `verify-release-signatures`, `publish` | **GitHub Actions runtime** |
| Publish needs verified artifacts from the same run plus the authorization job | `build-desktop.yml` | **GitHub Actions runtime** |

These are implemented in workflow YAML and Python that GitHub executes. They do not depend on repository settings that this plan does not offer, and they cannot be bypassed with `--no-verify`.

## 4. Documented / config-only (NOT enforceable on this plan)

| Item | Status | Why |
|---|---|---|
| `.githooks/pre-push` (no direct push to `main`, gitleaks, version gate) | **Local compensating control only** | Opt-in per clone via `git config core.hooksPath .githooks`, bypassable with `--no-verify`, and runs on a contributor's machine — it is **not** remote branch protection and never blocks a push made through the web UI or by another clone. |
| `.github/CODEOWNERS` | **Advisory / intent** | Requires branch protection with "require review from Code Owners" to become a merge requirement. That setting returned HTTP 403 on this private free repo. It currently routes review intent only when a PR UI chooses to show it. |
| `.github/PULL_REQUEST_TEMPLATE.md` | **Documentation** | A template cannot reject a PR or a merge. |
| Explicit approval marker in this file | **Runtime input, not independent approval** | It is enforced by the gate, but the same owner who can publish can also edit the file. It provides an auditable, commit-bound intent record — not a second-party veto. |
| `FINAL-RELEASE-ACCEPTANCE.md` / readiness matrix statuses | **Evidence, not a gate** | The gate only checks presence/non-emptiness of these files; it does not interpret their verdict text. |
| Dependabot / environment approvals / required status checks | **Not configured** | Out of scope for this operation and unavailable/plan-limited for private free repos. |

## 5. Residual owner limitations

1. **No remote branch protection.** Live `GET /repos/eliosmernica15/keel/branches/main/protection` previously returned HTTP 403 ("Upgrade to GitHub Pro or make this repository public"), and `.protected` was `false`. Direct pushes to `main`, force pushes and deletion cannot be blocked by GitHub on this plan.
2. **No required reviews or required status checks.** A PR can be merged without review; CODEOWNERS and the PR template cannot change that.
3. **No environment approval gate.** Environment protection rules (required reviewers, wait timers) cannot be relied on here, so the authorization gate is implemented as an ordinary job instead.
4. **No signature enforcement.** `GET .../required_signatures` previously returned 404. Signed commits are a convention, not a requirement.
5. **No fork restriction.** Personal private repo `allow_forking` could not be disabled (422 from a prior attempt). A move to an organization is the owner's decision and does not by itself add free-tier branch protection.
6. **2FA is unverifiable from the available API.** The owner must confirm it at `https://github.com/settings/security`; this operation cannot attest to it.
7. **The gate's trust anchor is the repository owner.** With admin access the owner can change the marker, the allowlist default, or the workflow itself. The controls protect against accidental/untrusted release paths and fork-origin artifacts; they are not a separation-of-duties control against the owner.
8. **Live `main` is not yet hardened by this worktree.** These changes are committed on `agent/final-governance` and must be merged by the owner. Prior live evidence recorded tag-pinned refs on `main`; the local branch had SHA pins. Merging is the owner's action and was not performed here.
9. **Not retested against the live GitHub API from this agent.** Network/permission was unavailable; the stub results above prove the gate logic, not live API availability or token scopes. The owner should run `workflow_dispatch` on the gate once after merge to confirm the real `gh` calls succeed with `contents: read`.

## 6. Owner actions required after merge

1. Merge `agent/final-governance` into `main` through a reviewed PR (the local hook cannot enforce this remotely).
2. Dispatch the release-authorization workflow with a candidate tag and confirm the live `gh` lookups succeed.
3. For a real release, replace the inert marker line in this file with the exact-tag approval line, commit to `main`, and tag that commit. The gate reads the marker from the tagged commit.
4. Confirm 2FA in account settings; decide whether to upgrade the plan or move to an organization if remote branch protection is required.
