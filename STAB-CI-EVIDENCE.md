# STAB-CI-EVIDENCE — CI repair on `agent/stab-ci`

Base: stabilization HEAD `9c03487` (fast-forwarded from `f60b080`, which contains the
failing-CI baseline for main `9a63be92`). All work is confined to
`.github/workflows/*.yml` plus this report; no frontend, backend source, tests,
`.gitleaks.toml`, or other agents' files were modified. No push was made.

## 0. Original GitHub failure context (important)

The six failing runs were inspected through the Jobs API. **Every job failed in
1–2 seconds with `runner_id: 0`, `runner_name: ""` and `steps: []`** — no runner
was ever assigned, so no step ever executed. Example:

```
$ gh api repos/eliosmernica15/keel/actions/runs/45519531459/jobs \
    --jq '.jobs[] | {name, conclusion, runner_id, steps}'
{"conclusion":"failure","name":"validate-versions","runner_id":0,"steps":[]}
{"conclusion":"skipped","name":"build-linux","runner_id":null,"steps":[]}
...
```

The same pattern holds for runs 45519531326/394/412/459/612/43337. The GitHub
step logs are gone (`BlobNotFound`) and the API no longer returns step data, so
the *original* failure is an external runner/account-level blocker, not a
workflow logic error. Per the task, each workflow's commands were therefore
reproduced locally (Windows 11 + WSL2 Ubuntu with Python 3.11, clean `HOME`) and
the genuine latent defects below were fixed without weakening any gate.

## 1. Python tests — run 45519531326

| | |
|---|---|
| Original failure | All three `pytest` jobs failed before a runner was assigned (see §0). |
| Local reproduction | `python -m pip install --require-hashes -r requirements.lock.txt` and `pip install --no-deps --no-build-isolation -e .` succeed on Windows (py3.11.9, pip 26.0.1) and Linux (py3.11.18, clean HOME). Lock-freshness inline check: `LOCK FRESHNESS OK: 34 pinned packages, 8 required pins checked`. `npm ci` + electron-builder pin check: `electron-builder pinned from lockfile: 26.18.0`. `python -m keel.release build --platform auto --out release` and `licenses` succeed. Full `python -m pytest -q`: **3 failed, 4442 passed, 48 skipped, 3707 subtests passed** in 574.88s. |
| Root causes found | (a) `test_release_integrity.py::test_integrity_cli_on_real_artifacts` — `latest.yml` was never generated: `integrity: 6/7 passed` with `[FAIL] latest_yml: latest.yml or manifest missing`. electron-builder only emits it with a publish target. (b) `test_gap_closure.py::test_c122_airgap_bundle_and_verification` hard-codes a `Keel-Setup-0.1.0.exe.blockmap` while the release is 0.1.1 — a test/source defect. (c) `test_prod_observe.py::test_cross_process_event_integrity` hits `PermissionError` on Windows' exclusive-lock emulation — a backend source defect. |
| Fix | Added a platform-aware step before the suite that regenerates `latest.yml` from the verified manifest and the real installer using the documented `keel.release_integrity.regenerate_latest_yml` helper. No test was skipped; no platform job disabled. |
| Verification | `python .../regenerate_latest.py` → `latest.yml regenerated from verified Windows artifact` (exit 0). `python -m keel.release integrity --dist dist --artifacts release` → `integrity: 7/7 passed` (exit 0). `python -m pytest -q tests/test_release_integrity.py` → `3 passed` (exit 0). |
| Remaining blockers | (b) and (c) are in backend tests/source (outside this worktree's ownership). macOS runner behaviour cannot be reproduced locally; the historical macOS `sandbox-exec` SIGABRT remains external. Full-suite re-run on CI is still required. |

## 2. Secret scan — run 45519531394

| | |
|---|---|
| Original failure | Job failed before a runner was assigned (§0). |
| Local reproduction | Verified the pinned asset: `sha256(gitleaks_8.30.1_linux_x64.tar.gz) = 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`, matching `.github/workflows/secret-scan.yml` and the GitHub release digest — the download/checksum step is correct. Windows x64 binary zip SHA also matched. `gitleaks detect --no-banner --redact --config .gitleaks.toml ... .` on the pre-fix tree scanned 625 commits and reported **36 leaks** (exit 1): 9×`test_z_backend.py`, 3×`test_composition_contracts.py`, 3×`test_w1_security_backend.py`, 3×`test_w4_backend.py`, 3×`verify_local_provider_credentials.py`, 2×`artifacts.js`, 2×`AUDIT-SECURITY.md`, 2×`test_secret_storage.py`, plus `AUDIT-MODULES-B.md`, `probes/*`, `test_release_no_secrets.py`, `test_redaction.py`. Manual classification: all are synthetic fixtures, example JWTs/placeholders, or a localStorage key — no real credential. |
| Fix | None in this worktree. Stabilization commit `101fcec`/`c949891` had already added 157 lines of narrowly scoped (commit + path + rule) allowlists to `.gitleaks.toml`; that file belongs to another agent and was left untouched. |
| Verification | Re-ran the same gitleaks command on the merged tree: 644 commits scanned, **1 leak** remaining (down from 36). |
| Remaining blocker | The single remaining finding is `aws-access-token` at `STAB-SUPPLY-EVIDENCE.md:102`, commit `c9498911ac99`, where an evidence table quotes the synthetic literal `AKIAABCDEFGHIJKLMNOP`. It needs a narrow allowlist entry (commit + path + rule) in `.gitleaks.toml` by the security/supply-chain owner. This repo must not be claimed as secret-scan-clean until that is done. |

## 3. Offline + license gates — run 45519531412

| | |
|---|---|
| Original failure | Both jobs failed before a runner was assigned (§0). |
| Local reproduction | `python scripts/check_model_licenses.py` → `LICENSE GATE OK`; `python scripts/verify_v6_audit.py` → `CONSISTENCY OK` (865 rows); `python keel/scripts/build_dependency_graph.py --check` → `FRESH`; `python scripts/verify_supply_chain.py` → `SUPPLY CHAIN VERIFICATION OK` (exit 0). The offline step with the original `unshare -n python -m pytest ...` reproduced **4 failures** in WSL2: `test_e2e_local.py::{test_app_shell_and_auth,test_settings_flow,test_surfaces_and_file_search,test_fleet_chat_flow}` → `urllib.error.URLError: <urlopen error [Errno 101] Network is unreachable>`, 7 passed. |
| Root cause | A bare `unshare -n` creates a network namespace with **loopback DOWN**, so the local HTTP server used by the e2e tests cannot bind/connect on 127.0.0.1. The workflow's comment ("no outbound route") was true but the gate was unusable. |
| Fix | (1) Follow-up request: added `python scripts/verify_supply_chain.py` with `working-directory: keel` to the `license-gate` job. (2) Replaced the offline invocation with `unshare -Urn bash -c 'ip link set lo up; assert no default route; python -m pytest ...'`, with fail-closed checks that both `unshare` and `iproute2` exist. Outbound is still blocked; only loopback is raised. |
| Verification | Exact step commands in WSL2, clean HOME, all provider keys unset: `11 passed in 30.64s` (exit 0). Negative test with `ip` removed from `PATH`: `offline CI requires iproute2 (ip); failing closed` (exit 1). `python scripts/verify_supply_chain.py` (from `keel/`) → `SUPPLY CHAIN VERIFICATION OK` (exit 0). |
| Remaining blocker | End-to-end proof on a GitHub `ubuntu-latest` runner (where unprivileged user namespaces must be enabled) is still needed; macOS has no equivalent `unshare` path and is out of scope for this Linux-only job. |

## 4. Build desktop installers — run 45519531459

| | |
|---|---|
| Original failure | `validate-versions` failed before a runner was assigned; all build/signing/publish jobs were skipped (§0). |
| Local reproduction | Version sync on the exact main SHA `9a63be92` and on current HEAD: all seven sources (`pyproject.toml`, `desktop-app/package.json`, `package-lock.json`, `site/download.json` version+tag, `tauri.conf.json`, `Cargo.toml`, `src/keel/__init__.py`) agree on `0.1.1` / `v0.1.1`. `python scripts/check_version_sync.py` → `OK - all sources agree on version 0.1.1 (tag v0.1.1)`; `--tag v0.1.1` also exits 0. `npm ci` + electron-builder pin check pass; `python -m keel.release build --platform windows --out release` produced and staged 8 artifacts including `Keel-Setup-0.1.1.exe` (exit 0). |
| Root cause | No version, path, pin, or build defect reproduced on Windows. The original failure is the runner-assignment blocker in §0. Linux system deps and macOS build are not reproducible on this host. |
| Fix | None required in workflow/script code; gates left intact. |
| Remaining blockers | macOS build (historical `sandbox-exec` SIGABRT), owner-supplied signing key/public key for tag releases, and GitHub Free private-repo runner/branch-protection limits. Vercel build-rate-limit is a **frontend hosting** issue listed in the stabilization baseline; it is not touched by any workflow here and is explicitly out of scope for this agent. |

## 5. Provider validation — run 45519531612

| | |
|---|---|
| Original failure | Job failed before a runner was assigned (§0). |
| Local reproduction | Install and fixture suite: `14 passed` (both Windows and Linux, clean HOME). Live-check script with no credentials printed all seven `*_KEY=MISSING`, `live_provider=SKIP (no fully configured credential)` and exited 0 — correct SKIP semantics. However, with an ambient key present the fixture suite fails: `test_no_credentials_means_no_live_success` → `AssertionError: assert ['openrouter'] == []` (1 failed, 2 passed). |
| Root cause | The deterministic fixture step assumed an ambiently clean environment. Any `KEEL_*_API_KEY` inherited by the runner makes the "no credentials ⇒ SKIP" fixture fail, even though the live-check step is the only step that should see secrets. |
| Fix | Explicitly clear the five provider keys via step-level `env: ...: ""` on the fixture step; the live-check step still receives the repository secrets unchanged. No assertion or gate was removed. |
| Verification | Ambient key run → exit 1 as above; cleared-env run of the exact three fixture files → `14 passed` (exit 0). Live-check script with no keys → SKIP, exit 0. |
| Remaining blocker | A real configured credential can still make the single live smoke request fail for external reasons (credential validity/quota/network); that is the documented "live provider credentials" blocker, not a workflow defect. |

## 6. Verify installed packages — run 45519543337

| | |
|---|---|
| Original failure | `Trusted trigger guard (fail closed)` failed before a runner was assigned; the three install/package jobs were skipped. The guard failure is a cascade of the failed upstream build (§0). |
| Local reproduction | (a) In a directory without a git checkout, `gh run view 45519531459` → `failed to determine base repo: fatal: not a git repository`; with `--repo eliosmernica15/keel` it works. `verify-install.yml` had no `actions/checkout`, yet all three `gh run download` steps omitted `--repo`. (b) The guard trusted any `workflow_dispatch` solely because it is an operator action, without validating `inputs.run_id` — a named fork/PR run could have been downloaded and executed. |
| Fix | Added `--repo "$GITHUB_REPOSITORY"` (PowerShell: `$env:GITHUB_REPOSITORY`) to all three downloads; manual dispatch now resolves the referenced run with `gh api repos/$THIS_REPO/actions/runs/$RUN_ID` and requires workflow name `Build desktop installers`, `event=push`, `conclusion=success`, `head_repository = this repo`, `head_branch = default branch`; non-numeric run_id fails closed. Factored the checks into `assert_trusted_run`, reused for the `workflow_run` path. Added a job-level `if` so a failed/untrusted upstream build does not create a second red verification run — every run that installs artifacts still passes the same assertions. Hardened the macOS sidecar lookup with `find -print -quit` (no `xargs`/space breakage). |
| Verification | Extracted the exact step `run:` from the YAML and executed it under bash with a stubbed `gh`. Nine cases matched expectations: trusted push/main/success → 0; PR → 1; fork → 1; failed build → 1; dispatch with verified run → 0; dispatch with fork run → 1; dispatch with failed run → 1; wrong workflow → 1; non-numeric run_id → 1. `gh` repo-inference failure reproduced as above. |
| Remaining blocker | Real installer install/health/uninstall cannot be exercised without artifacts from a successful `Build desktop installers` run (which itself needs a runner); signed clean-VM upgrade/rollback remains an external gate. |

## 7. Other workflows (not in the failing set)

- `lifecycle.yml` and `signing-readiness.yml` are manual-dispatch-only and were not among the six failing runs. No changes made. Their commands and permissions were reviewed by the policy checks below.

## 8. Cross-cutting verification performed

| Check | Command / result |
|---|---|
| Hash-pinned install path correctness | All `python -m pip install --require-hashes -r requirements.lock.txt` steps use `working-directory: keel`, where the lock lives. Installed successfully on Windows py3.11.9 and Linux py3.11.18 with clean `HOME`. A PyPI cross-check script compared every pinned version's SHA set with all published files for that version: `checked 34 pinned packages`, zero missing digests. No path or hash defect found; no change needed. |
| Version validation | `python scripts/check_version_sync.py` and `--tag v0.1.1` both exit 0; all version sources also verified directly from main SHA `9a63be92`. Gate left unchanged. |
| gitleaks download integrity | Linux asset SHA and Windows zip SHA both match the pinned/expected values. |
| YAML parse | `python workflow_policy_check.py` (PyYAML) → all 8 workflows parse, job maps intact. |
| Third-party `uses:` | All 31 `uses:` entries across the 8 workflows are 40-hex SHA pinned (20 build-desktop, 4 offline, 3 python-tests, 2 provider, 1 secret-scan, 1 signing-readiness; lifecycle has none). |
| Minimal permissions | Top-level `contents: read` everywhere; `actions: read` only where `gh run` is used (verify-install, lifecycle); `contents: write` only in the tag-gated publish job. No `write-all`. |
| Python/OS compatibility | Python 3.11 worked on Windows and Linux; macOS could not be tested locally and remains an external blocker. |

## 9. Files changed

- `.github/workflows/offline-license.yml` — supply-chain step (follow-up), offline namespace fix.
- `.github/workflows/python-tests.yml` — `latest.yml` regeneration for integrity tests.
- `.github/workflows/provider-validation.yml` — hermetic credential-free fixture step.
- `.github/workflows/verify-install.yml` — trusted trigger guard, `gh --repo`, sidecar lookup.
- `STAB-CI-EVIDENCE.md` — this report.

No frontend (`keel/site`, `keel/desktop*`, `site/`), backend source, tests,
`.gitleaks.toml`, or other agents' scripts were modified.
