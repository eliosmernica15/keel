# Keel Master Plan v6 — Independent Release Audit

**Auditor:** Agent 50 — independent release auditor (review only; no implementation or evidence edits)
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\final\release-audit`
**Branch / baseline:** `agent/f-release-audit` @ `a9a040e3369c7e8fa2882b1720edb1bde30b8af4` (baseline SHA `a9a040e`)
**Date:** 2026-11-23
**Scope:** complete final source, CI evidence, artifact hashes, signatures, release checklist and the four acceptance verdicts.

---

## Independent checks

### 1. Registry verification (`python scripts/verify_v6_audit.py`)

Exact output (exit code `0`):

```
evidence files: 8 present: 8
registry count: 228 matrix rows: 228
parity identical: True
tier counts: {'operational': 52, 'local_module': 168, 'external_dependency': 3, 'descriptor': 3, 'owner_gated': 2}
verified: 220
flagged: ['B4.8', 'B6.2', 'B6.3', 'B6.5', 'B6.6', 'C11.1', 'C11.2', 'C11.8']
CONSISTENCY OK
EXIT_CODE=0
```

This confirms internal consistency only (as the prior independent reviewer also stated), not the existence of 220 separate implementations.

### 2. CI workflow review

Command (Python; PowerShell `grep` avoided as instructed) enumerated `.github/workflows/*.yml`:

| Workflow | `uses:` refs |
| --- | --- |
| build-desktop.yml | 17 |
| lifecycle.yml | 0 |
| provider-validation.yml | 2 |
| python-tests.yml | 2 |
| secret-scan.yml | 1 |
| signing-readiness.yml | 1 |
| verify-install.yml | 0 |
| **Total** | **23** |

- **7 workflow files**, all active on the live repo (verified via `gh api repos/eliosmernica15/keel/actions/workflows`).
- **23/23 `uses:` refs are full 40-hex SHAs**; 0 tag-only, 0 local actions. Result of the SHA check: `remote refs WITHOUT 40-hex SHA: 0`.
- Distinct pinned actions: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`, `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`, `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1`, `actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9`, `actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333`.
- Each SHA was independently resolved via `gh api repos/<repo>/commits/<sha> --jq .sha` — all 5 returned the identical SHA (real commits), and each matches its `# v7` / `# v8` tag comment via `gh api repos/<repo>/git/ref/tags/<tag> --jq .object.sha` (`match=True` for all 5).
- **Signing gate references:** none. A full-workflow search for `SIGN|signing|NOTARIZATION` matched only `.github/workflows/signing-readiness.yml` lines 3–39, which *reports* credential presence (CONFIGURED/MISSING) and contains no signing step, no `--signing-key` / `--public-key`, and no hard-fail gate. `build-desktop.yml` has no sign job; its `publish` job depends only on `[build-windows, build-macos, build-linux]`. This matches the disclosure in `master-plan-v6-release-acceptance.md:100,129,148` and `master-plan-v6-final-report.md:98`.
- **No secrets printed:** static scan of all 7 workflows found no direct interpolation of `${{ secrets.* }}` into `echo`/`run` and no `echo` of any secret-bound environment variable. `signing-readiness.yml` and `provider-validation.yml` deliberately print names/presence only; the latter applies value redaction to captured subprocess output.

### 3. Artifact hashes

- `keel/dist/Keel-Setup-0.1.1.exe` **does not exist in this worktree** (`keel/dist` and `keel/release` directories are absent because they are gitignored). **I could not recompute SHA-256.**
- Recorded value in `master-plan-v6-release-acceptance-addendum.md:27`: size `141,118,394` bytes, SHA-256 `F12E1D668EF9983F291CC2302FCD4A938327CFCD1B4DEF5E5A9BAC7C76C14054`, unsigned. `master-plan-v6-final-report.md:93` repeats this value.
- `RELEASE-MANIFEST.json` and `RELEASE-SHA256SUMS.txt` **do not exist anywhere in the worktree**, so no manifest/checksum consistency check was possible. `keel/site/download.json` exists but is an honest `fallback` manifest with `size: null`, `sha256: null`, `available: false` for every channel — it makes no hash claim.
- See Finding H-3: the recorded hash is not attributable to the audited final source.

### 4. Signing / repository state (read-only GitHub API; no secret values read or printed)

```
gh api repos/eliosmernica15/keel/actions/secrets --jq .total_count   -> 0
gh api repos/eliosmernica15/keel --jq '.private'                     -> true
gh api repos/eliosmernica15/keel --jq '.full_name'                   -> eliosmernica15/keel
gh api repos/eliosmernica15/keel/actions/workflows                   -> 7 workflows, all active
gh api repos/eliosmernica15/keel/branches/main/protection            -> HTTP 403 "Upgrade to GitHub Pro or make this repository public..."
```

Live `main` pinning check (`gh api .../contents/.github/workflows?ref=main` + per-file fetch): **23 refs, 0 SHA-pinned, 23 tag-pinned** — consistent with the disclosure in `master-plan-v6-final-report.md:67` and `master-plan-v6-independent-acceptance.md:14,51`.

### 5. Claim reproduction on the final source

- Commands run with `$env:PYTHONPATH` pointed at this worktree's `keel/src` (confirmed `keel from: ...\release-audit\keel\src\keel\__init__.py`) to avoid the globally installed editable package contaminating results.
- Windows network enforcement is present in the final source: `keel/src/keel/sandbox_windows.py:663,666` sets `windows_appcontainer` / `network_enforcement` from a live AppContainer probe; `git log` shows `9a77dae` (AppContainer implementation) and `d4a24d6` (test assertions updated).
- Full-suite / "no regressions" claim: **reproduced as FAILING** — see Finding H-1.

---

## Claims confirmed / contradicted

### Confirmed

| Claim | Independent result |
| --- | --- |
| Registry 228/220, parity, 8 flagged, `CONSISTENCY OK` | CONFIRMED — exact output reproduced above. |
| Local CI Actions refs SHA-pinned | CONFIRMED — 23/23 refs, all 40-hex, all resolve to real commits, all match tag comments. |
| Live repo `main` still tag-pinned (branch not pushed) | CONFIRMED — 23/23 tag-pinned via live API. |
| Repo private; C11.1 PASS | CONFIRMED — `private: true`, 7 active workflows. |
| Branch protection BLOCKED on free private plan | CONFIRMED — live HTTP 403. |
| No signing identity; no CI signing job; no fabricated signature | CONFIRMED — secrets `total_count=0`; no signing steps in any workflow; release notes/download.json say unsigned. |
| Windows AppContainer network denial is genuinely implemented in the final source | CONFIRMED — code path and tests present; `test_win_network.py` 11 passed per `master-plan-v6-win-network-evidence.md:94-97`; real child-process results `LOCALHOST=FAIL`, `DNS=FAIL`, grandchild `CHILD-LOCALHOST=FAIL`, control `OK` (evidence §2). |
| No push / publish / deploy performed | CONFIRMED as far as local state and live API show (no release action taken by this audit). |

### Contradicted

| Claim | Independent result |
| --- | --- |
| `master-plan-v6-final-completion-report.md:27` — "Integration validation: PASS … full suite green"; `master-plan-v6-final-report.md:60,128` — "no regressions … full suite" | **CONTRADICTED** — see H-1. |
| `master-plan-v6-final-report.md:78,82,94,148` — "network denial is not available on this host", "Windows network unenforced", skip reason "Windows network denial unavailable" | **CONTRADICTED by the final source and by the other final report** — see H-2. |
| `master-plan-v6-final-report.md:93` / addendum header — installer "rebuilt from the final commit" / "Final-source artifact" | **CONTRADICTED** — see H-3. |
| `.github/workflows/signing-readiness.yml:4` comment — "The real signing jobs are guarded by these same secrets and are skipped when they are absent" | **CONTRADICTED (medium, documentation only):** no signing jobs exist in any workflow. The acceptance reports correctly disclose this; the CI comment is misleading and should be corrected. |
| `master-plan-v6-release-acceptance.md:100-101` — "CI workflows present: 4 … The only secret references in CI are `secrets.GITHUB_TOKEN`" | Stale for the final tree (7 workflows; signing-readiness and provider-validation reference additional secrets). That evidence file is baselined at `20bf5c3`, so this is a low-severity documentation staleness, not a release blocker. |
| `master-plan-v6-final-report.md:38,67` — "20/20 refs pinned" | Stale count: the audited tree has 23/23 SHA-pinned refs (7 workflows). Same conclusion, different denominator. Low severity. |

### Review of the four acceptance verdicts

| Report / verdict | Audit assessment |
| --- | --- |
| `master-plan-v6-final-report.md:147` — **MASTER PLAN V6 — COMPLETE** | Registry-level completeness CONFIRMED; verdict acceptable **with scope note** (registry consistency + spot-check, not re-verification of 220 implementations). |
| `master-plan-v6-final-report.md:148` — **SECURITY HARDENING — BLOCKED** ("Windows network enforcement unavailable on this host") | Status BLOCKED is defensible (Linux/macOS native verification outstanding), **but the stated reason about Windows network is stale and contradicted** by the final source and by `master-plan-v6-final-completion-report.md:12`. Should be PARTIAL with the correct reason. |
| `master-plan-v6-final-report.md:149` — **REPOSITORY GOVERNANCE — BLOCKED** | CONFIRMED live (private PASS, SHA pinning local-only, branch protection 403, signed commits/forks/2FA owner-gated). No change. |
| `master-plan-v6-final-report.md:150` — **PRODUCTION RELEASE — BLOCKED** | CONFIRMED and correct. Additionally, H-1/H-2/H-3 must be resolved before any future upgrade of this verdict. |
| `master-plan-v6-final-completion-report.md:22-28` (seven-row verdict table) | "Product functionality PASS (with environment limits)", "Security hardening PARTIAL", "Repository governance PARTIAL", "Production release BLOCKED" are consistent with evidence. **"Integration validation PASS … full suite green" (row 27) should be PARTIAL/BLOCKED** per H-1. |

---

## Critical/high findings

### H-1 [HIGH] Clean-checkout full suite is red; "full suite green / no regressions" is unsupported for the audited final source

Evidence — exact command and result on a clean checkout of baseline `a9a040e` with `PYTHONPATH` pinned to the worktree source:

```
$env:PYTHONPATH = "...\release-audit\keel\src"   # verified: keel from ...\release-audit\keel\src\keel\__init__.py
cd ...\release-audit\keel
python -m pytest -q tests/test_distribution_package.py::test_release_manifest_has_policy_fields \
  tests/test_distribution_package.py::test_checksums_file_matches_manifest_artifacts \
  tests/test_gap_closure.py::test_c12_package_manager_manifests \
  tests/test_gap_closure.py::test_c122_airgap_bundle_and_verification \
  tests/test_plan_index.py::test_authoritative_source_hashes_unchanged \
  tests/test_release_integrity.py::test_integrity_cli_on_real_artifacts --tb=line

FFFFFF                                                                   [100%]
6 failed in 3.45s
EXIT=1
```

Five failures are deterministic `FileNotFoundError`s for `keel/release/RELEASE-MANIFEST.json` / `RELEASE-SHA256SUMS.txt` (those files are absent and gitignored). The sixth is **not** environmental: `test_plan_index.py:56-67` hard-codes the authoritative SHA of `keel/docs/plan-sources/Keel_Master_Plan_v5.md` as `da1dd5dc81d7f85fadbc5e10143c937e7fc63fd34b86f0f0d3659f7af67d427f`, but the committed file hashes to `47b346bc9b7ee26a51e5fe2576e9a9fa5cc6e75e339ab554e90aa2bfd79c1f13` (verified by direct `hashlib.sha256`). This is a genuine stale source-hash guard in the final source.

CI impact: `.github/workflows/python-tests.yml:36-38` runs exactly `python -m pytest -q` on a clean checkout with **no step that generates release artifacts**, so this workflow will be red for the final source. The only recorded green full-suite run (`master-plan-v6-test-evidence.md:85`: 1296 passed, 46 skipped) is for the **earlier** `integration/v6-completion` branch and predates the 40 source-changing commits that follow. Later recorded full-suite runs in the repository are all red: `master-plan-v6-cli-surface-evidence.md:166` (7 failed, 1311 passed), `master-plan-v6-recovery-evidence.md:179` (7 failed, 1315 passed), `master-plan-v6-secrets-policy-evidence.md:199` (8 failed, 1299 passed). No green full-suite run is recorded for the audited HEAD. The agent-level explanations ("environmental artifacts", "transient flakes") do not change the fact that the shipped CI command fails on a clean clone, and one failure is a genuine committed defect.

Required downgrade: "no regressions" → PARTIAL/UNVERIFIED for the final source; provide a full-suite green run at the final commit with generated artifacts, or make the tests generate/skip artifacts deterministically and fix the stale v5 plan hash.

### H-2 [HIGH] The two "final" reports give mutually contradictory Windows network-enforcement verdicts; the older one is stale

Evidence:

```
master-plan-v6-final-report.md:78   "Network denial is not available on this host and the default path fails closed."
master-plan-v6-final-report.md:82   "Remaining weaknesses: Windows network unenforced"
master-plan-v6-final-report.md:94   skip reason "Windows network denial unavailable; fail-closed behaviour asserted elsewhere"
master-plan-v6-final-report.md:148  "Windows network enforcement unavailable on this host"

master-plan-v6-final-completion-report.md:12  "Windows network isolation is now genuinely enforced... This disproves the prior 'network unavailable' finding..."
master-plan-v6-final-completion-report.md:24  "Windows FS+network+process enforced and adversarially verified"
```

Independent resolution: the completion report is correct for the audited source. `keel/src/keel/sandbox_windows.py:637,663-666,701` derives `network_enforcement` from a real AppContainer probe, and `git log 7fd9a6a..HEAD` includes `9a77dae Implement non-elevated Windows network denial via capability-less AppContainer` and `d4a24d6 Update Windows sandbox tests to assert real AppContainer network enforcement`. The intermediate run in `master-plan-v6-win-network-evidence.md:87-89` (`2 failed, 24 passed, 1 skipped`) was superseded when those two obsolete assertions were updated; the current `keel/tests/test_sandbox_windows.py:66-67,81-94` asserts `network_enforcement is True` / `windows_appcontainer is True`.

Impact: a release decision that reads `master-plan-v6-final-report.md` (the document the matrix/addendum point to as definitive) gets the opposite security answer from one that reads the completion report. One of the two acceptance verdict sets must be corrected and a single authoritative document named. Note also that `master-plan-v6-win-network-evidence.md:4` describes a "kernel-enforced network boundary" while its §5 honestly records that WFP per-process filters remain `ERROR_ACCESS_DENIED (5)` and `socket()` creation still succeeds — the claim is supported only for traffic denial via AppContainer, not for WFP filtering.

### H-3 [HIGH] The "final-source" installer hash is from a commit 43 before the audited HEAD and cannot be recomputed

Evidence:

```
master-plan-v6-release-acceptance-addendum.md:4,7,27
  "Branch / commit built: integration/v6-completion @ 7fd9a6a (final evidence commit; all implementation commits merged)"
  SHA-256 F12E1D668EF9983F291CC2302FCD4A938327CFCD1B4DEF5E5A9BAC7C76C14054
master-plan-v6-final-report.md:93
  "Packaged installer: rebuilt from the final commit on this host ... SHA-256 F12E1D66..."

git rev-list --count 7fd9a6a..HEAD            -> 43
git rev-list --count 7fd9a6a..a9a040e         -> 43
git rev-list --count 7fd9a6a..f6773be         -> 2   (a043d85, f6773be: report/addendum/.gitignore only)
git diff --stat 7fd9a6a..HEAD -- keel/src keel/package.json keel/tests
  -> 44 files changed, 5372 insertions(+), 369 deletions(-)
```

Source-changing commits merged *after* the installer was built include `9a77dae` (AppContainer network denial), `4cf944c` (secrets/policy hardening), `ab31d5e` (CLI/TUI gates), `06a6365` / `f915408` (recovery/backup hardening), `c224c9e` (bridge E2E), `e37017b` (atomic rename), `77a157d` / `0fbe667` (Fleet/webhook), `dc41147` (exec-path guards), `5362d91` (product defects). The binary with hash `F12E1D66…` therefore cannot represent the audited final source `a9a040e`. `keel/dist/Keel-Setup-0.1.1.exe` is absent so the hash cannot be recomputed or tied to any content in this worktree, and no `RELEASE-MANIFEST.json` / `RELEASE-SHA256SUMS.txt` exists to cross-check it.

Impact: the acceptance matrix row "Final installers rebuilt from final source — PARTIAL" overstates artifact provenance. A release built from the audited source would be a *different* binary with an unknown hash. Required: rebuild from `a9a040e` (or the actual release commit), publish `RELEASE-MANIFEST.json` + `RELEASE-SHA256SUMS.txt`, and record a recomputable hash.

---

## Release-readiness verdict

**BLOCKED.**

Reasons (already-disclosed owner gates): no signing identity (`gh api .../actions/secrets` → `total_count=0`), no CI signing job or hard-fail gate, unsigned Windows installer, no clean-VM install/upgrade/rollback/uninstall validation, no native Linux/macOS runner verification, no provider credentials, no phone/device pairing validation, branch not pushed (live `main` 23/23 tag-pinned, no branch protection — HTTP 403).

Additional audit-raised blockers that must be cleared before any future readiness upgrade:

1. **H-1** — clean-checkout full suite fails (6 reproducible failures, including a stale authoritative plan hash) and the shipped `python-tests.yml` command is red; correct the "full suite green / no regressions" verdicts.
2. **H-2** — reconcile the contradictory Windows network-enforcement verdicts between the two final reports.
3. **H-3** — the recorded installer hash is not from the final source; rebuild and publish recomputable artifact hashes/manifests.

No implementation, CI, or evidence file was modified by this audit. Only `master-plan-v6-release-audit.md` was created and committed; nothing was pushed.
