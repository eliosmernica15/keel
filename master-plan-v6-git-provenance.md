# Master Plan v6 — Git provenance report

**Audit baseline (definitive):** `cadb343e84db1a1cc5fa2bed584996c33b629a4b`
**Audited working tree:** clean at baseline; audit work performed on branch `docs/v6-final-audit` (created from `cadb343`).
**Date of audit:** 2026-11-23
**Remote:** `origin = https://github.com/eliosmernica15/keel.git`
**Remote main at audit time:** `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee`
**Merge base of local main and origin/main:** `107a4271723ac01305395b59eb4205cbb13c78ca`

> Note: the prior acceptance report stated `origin/main = ecba9d2c83730eb0578c1e3332d00142f01c6520b`. The actual remote head is `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` — the prior report's hash is incorrect. Both share the prefix `ecba9d2b`; the suffix differs.

## Commands and evidence

All commands run from the repository root. Read-only inspection only; no history rewrite, reset, force-push, branch deletion, or push was performed.

```
git status -sb                 # ## main...origin/main [ahead 10, behind 33]
git rev-parse HEAD             # cadb343e84db1a1cc5fa2bed584996c33b629a4b
git rev-parse origin/main      # ecba9d2b9678ab7a3a744c62683eea28a1ce01ee
git rev-list --count origin/main..HEAD   # 10
git rev-list --count HEAD..origin/main   # 33
git merge-base origin/main HEAD          # 107a4271723ac01305395b59eb4205cbb13c78ca
```

## Resolving the reported SHA discrepancies

| Reported SHA | Actual object | Relationship to audited baseline | Verdict |
| --- | --- | --- | --- |
| `cadb343…` | commit (Release validation: native OS process limits, clean-runner install CI, repository protection) | = local main HEAD | **Definitive audit baseline** |
| `dad6a09…` | commit (Fix concurrency test to use tmp_path (no repo artifacts)) | **Ancestor of `cadb343`** (`git merge-base --is-ancestor` → true) | An earlier commit on the *same local line*, not a competing state. The prior report's "final commit" label was stale; `cadb343` supersedes it by 23 commits. |
| `c662acb…` | commit (Merge PR #8 ci/linux-lifecycle-path) | Ancestor of `origin/main`; **not** an ancestor of `cadb343` (rc=false) | Belongs to the divergent remote history. |
| `f8f47a6…` | commit (Merge PR #6 release/final-security) | Ancestor of `origin/main`; **not** an ancestor of `cadb343` (rc=false) | Belongs to the divergent remote history. |
| `107a427…` | commit (Phase 2 batch 10) | Merge base; ancestor of **both** local main and origin/main | Shared divergence point. |

`git log --oneline 107a427..dad6a09` is empty → `dad6a09` sits on the shared local line before the merge base. Local history is linear: `… → dad6a09 → … → 107a427 → … → cadb343`.

## The exact divergence

Local main and origin/main are genuinely diverged at `107a427`: local has 10 commits the remote lacks, and origin/main has 33 commits local lacks.

**10 local-only commits (`origin/main..HEAD`):**

| Hash | Subject |
| --- | --- |
| `cadb343` | Release validation: native OS process limits, clean-runner install CI, repository protection |
| `bed0dc4` | Release acceptance: fix packaged sidecar UI serving and add independent audit |
| `9e48e4b` | Close all 14 remaining roadmap gaps with real local implementations and E2E evidence |
| `78f6ef3` | Remove accidental electron-builder cache artifact from repository |
| `8a3a788` | Final roadmap batch: B6.x seams, policy UI, browser E2E fixes, rebuilt installer |
| `ac93b2b` | Enforce exec policy at runtime boundaries and seal sandbox policy state |
| `d4261a0` | Source research: register all references and integrate Codex execpolicy semantics |
| `af9dee2` | Phase 2 UI batch: A3.9 real operator Admin page (P1) |
| `a753b4a` | Phase 2 UI batch: C10.5 voice control and live-region accessibility (P1) |
| `7ae44e7` | Phase 2 UI batch: C10.1 real interactive tutorial in desktop and mirror UI |

These are the feature-completion, UI, and release-validation batches that carry the full 228-feature registry and the passing test suite.

**33 origin-only commits (`HEAD..origin/main`)** are the security/sandbox/CI/release-hardening work merged via PRs #1–#13, including Windows Job Object + restricted-token sandbox, Linux Landlock+seccomp backend, macOS Seatbelt BLOCKED reporting, shared OS sandbox conformance suite, external-readiness report, and Linux install CI fixes. They are summarized in the log; they are not present on the audited local baseline.

## Branches and worktrees

- Branches: `main` (plus audit branch `docs/v6-final-audit`, and pre-existing `final-acceptance`, `final-verification`, `release-*`, `ci/*`, `agent/*`, `lead/*` lines).
- Multiple pre-existing agent worktrees under `~/.local/share/opencode/worktree/e3c464/...` and a fresh audit set under `.../worktree/audit/...`.
- Open pull request at audit time: **PR #15 "Native macOS Seatbelt sandbox backend (BLOCKED read isolation)"** (`lead/macos-blocked-test`), OPEN.

## Does previous test evidence belong to the audited commit?

Yes. Running the full suite on the clean baseline `cadb343` reproduced the prior claim: **1270 passed, 10 skipped** (Python 3.11.9, Windows 10 AMD64). The 10 skips are credential-gated live provider smoke tests; see `master-plan-v6-test-evidence.md`.

## Safe integration recommendation

- Treat `cadb343` as the feature-complete baseline for this audit; do not reset or discard the 10 local commits.
- Treat origin/main's 33 commits as parallel security/sandbox/CI hardening. They are not on the audited baseline; if the owner wants them, integrate via an explicit, reviewable merge/PR — never force-push, never rewrite history.
- C11.1 (source-hosting decision) and C11.2 (repo security enforcement) remain owner-gated and are deliberately not actioned here (see `master-plan-v6-security-findings.md`).
- No push, release, deploy, or repository-setting change was performed *during the audit*.

## Completion operation (post-audit)

The owner subsequently authorized the C11.1 visibility change and a completion operation. The audit branch and `main` were left untouched; a dedicated local integration branch was created from the verified audit evidence commit:

```
git checkout -b integration/v6-completion 321bc7a
```

Starting state re-verified before any change: `321bc7a` present with parent `cadb343`; working tree clean; local main `cadb343` still 10 ahead / 33 behind origin/main; merge base `107a427`; live `git ls-remote origin refs/heads/main` = `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` (unchanged). The completion task's reported remote hash `ecba9d2c8378ab…` remains incorrect.

All completion commits are on `integration/v6-completion` (locally committed only; **nothing was pushed**). Isolated agent worktrees/branches were created under `~/.local/share/opencode/worktree/completion/`. No history was rewritten, no branch deleted, no force-push performed, and no merge of the divergent origin/main history was attempted merely to synchronize the two lines.
