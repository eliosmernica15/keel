# C11.2 Supply-Chain Hardening — GitHub Actions SHA Pinning Evidence

## Scope

Pin every GitHub Actions `uses:` reference in all files under `.github/workflows/`
to a full immutable 40-character commit SHA, preserving a readable version
comment. No workflow logic, trigger, permission, protection, or check was
changed.

| Field | Value |
| --- | --- |
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\completion\sec-c11-workflows` |
| Branch | `agent/sec-c11-workflows` |
| Baseline SHA | `321bc7a55f2f306365a0f2ee26441fef345e8f41` |
| Task | C11.2 supply-chain, implementation |

Workflow files in scope (all files under `.github/workflows/`):

- `.github/workflows/build-desktop.yml`
- `.github/workflows/python-tests.yml`
- `.github/workflows/secret-scan.yml`
- `.github/workflows/verify-install.yml` (no `uses:` references — unchanged)

## Resolution method

For each distinct `OWNER/REPO@TAG` the commit SHA was resolved with `git ls-remote`:

```
git ls-remote https://github.com/OWNER/REPO refs/tags/TAG refs/tags/TAG^{}
```

All five tags resolved as **lightweight tags**: `ls-remote` returned exactly one
line per tag and no peeled `^{}` ref. Per the task instruction, when an
annotated tag exists the `^{}` (target commit) is preferred; here there is no
annotated tag, so the tag ref itself is the commit. Each result was
independently cross-checked against the GitHub Git refs API
(`GET /repos/OWNER/REPO/git/ref/tags/TAG`), which confirmed `object.type =
"commit"` and the identical SHA. Repository owner/name matched the `uses:`
string in every case.

## Resolved actions

| # | `uses:` before | Version | Resolved 40-char commit SHA | ls-remote command | API cross-check |
| --- | --- | --- | --- | --- | --- |
| 1 | `actions/checkout@v7` | v7 | `3d3c42e5aac5ba805825da76410c181273ba90b1` | `git ls-remote https://github.com/actions/checkout refs/tags/v7 refs/tags/v7^{}` | HTTP 200, `type=commit`, SHA match |
| 2 | `actions/setup-python@v7` | v7 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` | `git ls-remote https://github.com/actions/setup-python refs/tags/v7 refs/tags/v7^{}` | HTTP 200, `type=commit`, SHA match |
| 3 | `actions/setup-node@v7` | v7 | `949feb2413d6458794dcd2491c4babbbce0c15c1` | `git ls-remote https://github.com/actions/setup-node refs/tags/v7 refs/tags/v7^{}` | HTTP 200, `type=commit`, SHA match |
| 4 | `actions/upload-artifact@v7` | v7 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` | `git ls-remote https://github.com/actions/upload-artifact refs/tags/v7 refs/tags/v7^{}` | HTTP 200, `type=commit`, SHA match |
| 5 | `actions/download-artifact@v8` | v8 | `9000827ccba6bdab643e8b6fd33ac0654aef8333` | `git ls-remote https://github.com/actions/download-artifact refs/tags/v8 refs/tags/v8^{}` | HTTP 200, `type=commit`, SHA match |

Raw `git ls-remote` output:

```
=== actions/checkout @ v7 ===
3d3c42e5aac5ba805825da76410c181273ba90b1	refs/tags/v7

=== actions/setup-python @ v7 ===
6d4fd22b20465ccc0f7354476588e8df7c9ca0e0	refs/tags/v7

=== actions/setup-node @ v7 ===
949feb2413d6458794dcd2491c4babbbce0c15c1	refs/tags/v7

=== actions/upload-artifact @ v7 ===
cf430e030ddbb5b0abf93d22962f4752f3646cd9	refs/tags/v7

=== actions/download-artifact @ v8 ===
9000827ccba6bdab643e8b6fd33ac0654aef8333	refs/tags/v8
```

No peeled `^{}` lines were returned for any tag (lightweight tags). No
reference failed to resolve.

## Before / after

Replacement pattern: `- uses: actions/NAME@TAG` →
`- uses: actions/NAME@<40-sha> # TAG`. Nothing else in the line or file changed.

### `.github/workflows/build-desktop.yml` (17 references)

| Line | Before | After |
| --- | --- | --- |
| 44 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |
| 45 | `- uses: actions/setup-python@v7` | `- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7` |
| 61 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |
| 62 | `- uses: actions/setup-python@v7` | `- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7` |
| 65 | `- uses: actions/setup-node@v7` | `- uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7` |
| 76 | `- uses: actions/upload-artifact@v7` | `- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7` |
| 87 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |
| 88 | `- uses: actions/setup-python@v7` | `- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7` |
| 91 | `- uses: actions/setup-node@v7` | `- uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7` |
| 101 | `- uses: actions/upload-artifact@v7` | `- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7` |
| 112 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |
| 113 | `- uses: actions/setup-python@v7` | `- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7` |
| 116 | `- uses: actions/setup-node@v7` | `- uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7` |
| 130 | `- uses: actions/upload-artifact@v7` | `- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7` |
| 148 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |
| 149 | `- uses: actions/setup-python@v7` | `- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7` |
| 157 | `- uses: actions/download-artifact@v8` | `- uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8` |

### `.github/workflows/python-tests.yml` (2 references)

| Line | Before | After |
| --- | --- | --- |
| 27 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |
| 28 | `- uses: actions/setup-python@v7` | `- uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7` |

### `.github/workflows/secret-scan.yml` (1 reference)

| Line | Before | After |
| --- | --- | --- |
| 26 | `- uses: actions/checkout@v7` | `- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7` |

### `.github/workflows/verify-install.yml`

No `uses:` references; file unchanged.

## Totals

- Distinct action@version pairs: 5
- Total `uses:` references pinned: **20** (checkout 7, setup-python 6,
  setup-node 3, upload-artifact 3, download-artifact 1)
- Failed resolutions: 0

## Verification

1. Post-change grep of all `uses:` lines: 20 lines, every one matching
   `@<40-hex> # <version>`. Tag-only references remaining: **0**.
2. SHA length/hex check on all 20 lines: `len=40`, `^[0-9a-f]{40}$` = True for
   every line.
3. `git diff` restricted to `.github/workflows`: 20 insertions / 20 deletions,
   all on `uses:` lines only. No other workflow content, logic, trigger,
   permission, protection, or check was modified.
4. Line endings preserved: all four workflow files remain 100% CRLF with no
   BOM, identical to baseline.
5. YAML parse validation (pyyaml 6.0.3):
   ```
   python -c "import yaml, glob; [yaml.safe_load(open(f, encoding='utf-8')) for f in sorted(glob.glob('.github/workflows/*.yml'))]"
   ```
   Result: all four workflow files parsed successfully (`ALL YAML PARSED OK`,
   exit code 0).

## Notes

Live repository settings are applied separately by the lead. This change is
limited to workflow files and this evidence file only. No commits were pushed.

---

# C11.1 / C11.2 repository governance (lead verification)

**Live `gh api` inspection and changes, 2026-11-23.** Token scopes: `repo`, `read:org`, `workflow`. Values labelled *live* came from API calls, not local files.

> **Scope correction (independent reviewer finding, Medium).** The Actions SHA-pinning work in this document is a **local integration-branch change only** — the completion branch was deliberately not pushed (owner gate). The live repository's default branch still has **23 tag-pinned `uses:` refs across 7 workflows, 0 SHA-pinned**. The 20 pinned refs are on `integration/v6-completion`; three workflows present only on `origin/main` (`lifecycle.yml`, `provider-validation.yml`, `signing-readiness.yml`) are not in the integration branch and remain tag-pinned on the remote. Do not read the pinning result below as a live repository state. Full SHA pinning becomes effective only when the change is reviewed and merged by the owner.
>
> **Final operation update:** the `final/v6-production` branch now contains all 7 workflows (the three remote-only ones were ported) with **26/26 `uses:` refs SHA-pinned, 0 tag-pinned** (verified with `git ls-remote`). The signing gate added a `verify-release-signatures` job; all its actions are SHA-pinned. This branch is still local-only (not pushed).

## C11.1 — source hosting: PASS (owner-confirmed)

The owner was asked once, with the exact consequence, and explicitly confirmed the change.

| Call | Result |
| --- | --- |
| `gh api repos/eliosmernica15/keel --jq '{private, visibility}'` (before) | `{"private":false,"visibility":"public"}` |
| `gh api -X PATCH repos/eliosmernica15/keel -f private=true` | `{"private":true,"visibility":"private"}` |
| Fresh read after change | `{"fork":false,"has_pages":false,"private":true,"visibility":"private"}` |
| `gh api repos/eliosmernica15/keel/collaborators` | Only `eliosmernica15` (admin) — no unexpected access change |
| `gh api repos/eliosmernica15/keel/actions/workflows` | All 7 workflows still `active` |
| `git ls-remote origin refs/heads/main` | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` — unchanged |

## C11.2 — repository security: PARTIAL / owner-and-plan gated

Live evidence shows a direct consequence of the C11.1 decision: **branch protection is unavailable on the free plan once the repository is private** — the exact caveat anticipated in Master Plan C11.1.

| Control | Live evidence | Result |
| --- | --- | --- |
| Branch protection (pre-change, public) | PR reviews required; 8 status checks; force-push and deletion disabled | Was configured |
| Branch protection (post-change, private) | `GET .../branches/main/protection` → 403 "Upgrade to GitHub Pro or make this repository public"; `branches/main` → `"protected": false` | **LOST — paid-plan or public-repo dependency** |
| `PUT .../protection/required_signatures` | 404 Not Found | BLOCKED (feature unavailable on this plan) |
| `PUT .../protection/enforce_admins` | 404 Not Found | BLOCKED |
| `PATCH -f allow_forking=false` | 422 "Allow forks setting can only be changed on org-owned private repositories" | BLOCKED (personal account limitation) |
| Actions pinned to full commit SHA | Local integration branch: 20/20 pinned, 0 tag-only (see section above). **Live repo main: 23/23 tag-pinned, 0 SHA-pinned** (independent reviewer verification). | **PARTIAL — local branch only; live repo unpinned** |
| Mandatory 2FA | Repository/account 2FA is owner-controlled and not exposed by the available API | UNVERIFIED — owner action required |
| Signed commits | No `gpg` binary and no signing key configured locally | BLOCKED — owner must provision a signing identity |

**No existing protection was knowingly weakened** — the loss was a plan-level consequence of the owner-confirmed visibility change, and it is reported rather than hidden.

### Local compensating controls (Master Plan C11.1 option 1)

Added `.githooks/pre-push`, a fail-closed local hook that:
- refuses direct pushes to `main` (forcing the PR workflow),
- runs `gitleaks detect --redact --config .gitleaks.toml` and blocks on findings,
- refuses to push if gitleaks is not installed,
- runs the version-consistency gate when present.

Install with `git config core.hooksPath .githooks`. This is a local control, not a GitHub-enforced one; it does not substitute for branch protection on the remote.

Hook executed locally with `C:\Program Files\Git\bin\sh.exe .githooks/pre-push`:
it printed `[keel pre-push] enforcing local branch policy`, then
`[keel pre-push] BLOCKED: gitleaks is not installed.` and exited 1 — confirming
the fail-closed behavior in this environment. The hook is not installed into
`core.hooksPath` by this operation (that is a per-clone developer action).

### Precise owner actions still required for full C11.2

1. Choose a plan/forge that supports private-repo branch protection (GitHub Team/Pro — paid service, gate G6; or a free forge with protected branches and a GitHub mirror), **or** accept the documented local-compensating-control posture as a plan exception.
2. Provision a GPG/Sigstore signing identity and enable signed commits.
3. Configure 2FA on the owner account (account-level, not repository-level).
4. If fork restrictions are required, move the private repo under an organization (personal private repos cannot disable forking).
