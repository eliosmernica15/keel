# Master Plan v6 — Live GitHub governance evidence (this operation)

Date: 2026-11-23. All values from live read-only `gh api` / `git ls-remote`, using the owner's authenticated account `eliosmernica15`.

## C11.1 — source hosting: PASS (live-verified)

| Check | Command | Result |
| --- | --- | --- |
| Visibility | `gh api repos/eliosmernica15/keel --jq '{private,visibility}'` | `{"private":true,"visibility":"private"}` |
| Fork setting | same, `allow_forking` | `true` (cannot be disabled on a personal private repo — 422 from prior attempt) |
| Collaborators | `gh api .../collaborators` | only `eliosmernica15` (admin) |
| Remote main | `git ls-remote origin refs/heads/main` | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` |
| Workflows | `gh api .../actions/workflows` | 7 active |

The private-source requirement is satisfied and preserved. No visibility change was made in this operation.

## C11.2 — repository security: plan-limited (live-verified)

| Control | Live command | Result | Verdict |
| --- | --- | --- | --- |
| Branch protection on `main` | `gh api .../branches/main/protection` | HTTP 403 "Upgrade to GitHub Pro or make this repository public to enable this feature." | BLOCKED — plan limitation |
| Branch `protected` flag | `gh api .../branches/main --jq .protected` | `false` | not enforced |
| Account type | `gh api user --jq '{login,type,plan}'` | `{"login":"eliosmernica15","type":"User","plan":null}` | personal account, free plan |
| Organizations available | `gh api user/orgs` | `Tech-Lab-Gen-3`, `Front-End-Students-Gen-3` | possible migration target for fork control (owner decision) |
| 2FA | `gh api user` / headers | not exposed by token; no `two_factor_authentication` field | UNVERIFIED — owner-controlled account setting |
| Actions SHA pinning (live main) | local workflow scan vs `gh api` | live main has 23 tag-pinned refs across 7 workflows; local branch 20/20 SHA-pinned | PARTIAL — local only, branch not pushed |
| Commit signature enforcement | prior `PUT .../required_signatures` | HTTP 404 | BLOCKED on this plan |

### Precise limitation

GitHub Free private repositories do not support branch-protection rules (confirmed by the live 403). The available legitimate options are:

1. **Upgrade the account** to a paid plan that supports private branch protection (gated by Master Plan G6 — requires explicit owner approval). This operation does not purchase or enable paid services.
2. **Accept a documented exception** using the Master Plan C11.1 option of local compensating controls (`.githooks/pre-push` with no-direct-main-push, gitleaks, version gate; already implemented and verified fail-closed).
3. **Move the private repo under an organization** — this enables fork restriction (currently 422 on a personal private repo) but does not by itself provide branch protection on the free tier.
4. **Do not** make the repository public to obtain protection — explicitly prohibited by the owner's instruction and Master Plan §0.1.

2FA is an account-level control not reportable through the available API; only the owner can verify/enable it at `https://github.com/settings/security`.

No setting was changed. C11.2 remains PARTIAL with the above named blockers.
