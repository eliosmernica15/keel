# Production promotion — Supply-chain & repository security evidence

**Audit type:** read-only. No source, workflow, manifest, visibility, or licensing change was made by this audit.
**Branch:** `agent/prod-supply`
**Candidate audited:** `e57327378f56062db3b13d3db941ac2cf2a641a3` (`e573273`) — "build(release): include required version-sync constant so backend test suite collects", 2026-11-24 22:41:12 +0100.
**Base at audit start:** `e6e7efc50d098aaf55b80c5b35e799c0c2e25a86` (the worktree was checked out here; `e573273` is its direct child). The candidate was audited from its tree via `git show`/`git archive`; the branch was then fast-forwarded to the existing candidate commit so this evidence commit sits on it. No source content was edited.

**Methods (all offline):** `git ls-files`/`git show`/`git diff`/`git grep`, `git archive` of the candidate into a temp directory, installed distribution metadata (`importlib.metadata`), npm/Cargo lockfile parsing, Python regex secret heuristics, and direct execution of the repository's own gates. No network installs, no paid scanners, no `gh api` calls. Scanners present: `npm`, `cargo`, `gh` (not used for network), Python 3.11. Not installed: `gitleaks`, `pip-audit`, `trivy`, `osv-scanner`, `safety`, `actionlint`, `zizmor`.

**Severity key:** HIGH = must be resolved or explicitly owner-accepted before promotion; MEDIUM = should be fixed in the promotion batch; LOW/INFO = documented limitation/positive control.

---

## 1. Verdict

| Item | Result |
| --- | --- |
| Dependency inventory, licenses, native/transitive deps | **1 HIGH** (unpinned, non-reproducible Python build inputs); 2 MEDIUM; 1 LOW/INFO |
| GitHub Actions (all 8 workflows) | PASS on pinning/permissions/provenance/clean runners; **1 MEDIUM** (untrusted `workflow_run` artifact execution); 1 LOW (unused secrets) |
| Secret scan / gates | No real secrets found; **1 MEDIUM** (inert version step in local pre-push hook); 1 LOW (model-license gate only checks registry) |
| Privacy & license unchanged | No change made; private per in-repo live evidence; **offline re-verification not possible** |
| Branch protection | GitHub Free + private repo: unavailable (live 403 evidence in repo). Local hooks are **not** remote protection. Accepted owner exception — requires re-affirmation |

**HIGH finding: `DEP-01` — Python dependency resolution is unpinned and unreproducible. It blocks promotion unless the owner explicitly accepts a documented exception with per-build resolved-version/hash attestation.** No other finding is independently blocking.

---

## 2. Dependency audit (promoted backend)

### 2.1 Declared dependencies

`keel/pyproject.toml` (candidate):

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "keel-harness"
version = "0.1.1"
requires-python = ">=3.11"
license = { text = "Proprietary" }
dependencies = ["tzdata>=2024.1", "cryptography>=42.0", "keyring>=24.0", "Pillow>=10.0"]
```

Four runtime dependencies, **lower bounds only**; no upper bounds, no exact pins, no hashes. Build requirement `setuptools>=68` is also floating.

CI install steps (all 8 workflows checked):

- `python-tests.yml`: `pip install -e . pytest`; `pip install pyinstaller pillow`
- `build-desktop.yml` (Windows/macOS/Linux): `python -m pip install --upgrade pip`; `pip install -e . pyinstaller pillow`
- `verify-release-signatures` / `publish`: `python -m pip install --upgrade pip`; `pip install -e .`
- `offline-license.yml`: `pip install -e . pytest`
- `provider-validation.yml`: `pip install -e . pytest`

`pip`, `pyinstaller`, `pytest`, and all four runtime packages are therefore resolved fresh from PyPI at each run.

### 2.2 Lockfiles / checksums / reproducibility

| Ecosystem | Manifest | Lockfile | Integrity data |
| --- | --- | --- | --- |
| Python (backend) | `keel/pyproject.toml` | **NONE** (no `uv.lock`/`poetry.lock`/`Pipfile.lock`/`requirements.lock`/constraints file anywhere in tracked tree) | **NONE** |
| Node (Electron desktop) | `keel/desktop-app/package.json` (electron `^42.0.0`, electron-builder `^26.0.0`, no runtime deps) | `package-lock.json` v3, **284** entries | All resolved entries have `sha512` integrity; 0 non-registry URLs; 0 git-style versions |
| Node (fleet-next, unused) | `keel/fleet-next/package.json` (next `^15.1.6`, react/react-dom `^19.0.0`, TS `^5.7.3`, version **0.1.0**) | `package-lock.json` v3, **60** entries | All resolved entries have integrity; 33 native/optional `sharp`/libvips platform entries |
| Rust (Tauri, unused) | `keel/desktop/src-tauri/Cargo.toml` (tauri 2, serde 1, serde_json 1) | `Cargo.lock`, **420** packages, 419 checksums | All sources `registry+https://github.com/rust-lang/crates.io-index` |

Resolved versions in the two Node locks: electron `42.11.18`, electron-builder `26.18.0`, next `15.5.29`, react/react-dom `19.3.1`, typescript `5.9.3`.

**Critical build-path gap:** `keel/src/keel/release/build.py::npm_install()` runs `npm install --no-audit --no-fund` (only when `node_modules` is absent), then `electron_build()` runs `npx electron-builder ...`. It does **not** use `npm ci --require-integrity`; the existing lockfiles are therefore not enforced by the release build, and `npx` may fetch from the registry if the local package is missing. Electron's binary is downloaded by its install script; no pinned hash for that binary is recorded in the repository.

### 2.3 Installed metadata (offline inventory, 2026-11-24 host)

| Package | Version | License metadata | Role |
| --- | --- | --- | --- |
| cryptography | 50.0.1 | `License-Expression: Apache-2.0 OR BSD-3-Clause` (plain `License` field empty) | runtime |
| Pillow | 11.1.0 | `MIT-CMU` (HPND-style permissive) | runtime |
| setuptools | 84.0.0 | `License-Expression: MIT` | build |
| pip | 26.0.1 | `License-Expression: MIT` | build |
| pyinstaller | 6.19.0 | GPLv2-or-later **with special exception permitting commercial/non-free distribution** | build only |
| pytest | 9.0.2 | `License-Expression: MIT` | test |
| cffi / pycparser | 2.1.1 / 3.0 | MIT-0 / BSD-3-Clause | cryptography transitive (C extension) |
| packaging / iniconfig / pluggy / typing_extensions | 25.0 / 2.3.0 / 1.6.0 / 4.16.0 | MIT / MIT / MIT / PSF-2.0 | tooling transitive |
| pywin32-ctypes / altgraph / pyinstaller-hooks-contrib | 0.2.3 / 0.17.5 / 2026.2 | BSD-3-Clause / MIT / (empty) | Windows/PyInstaller transitive |
| **tzdata, keyring, jeepney, SecretStorage, tomli, wheel** | **NOT INSTALLED** | — | declared runtime deps / expected transitive deps absent from this host |

Consequence: the local environment is **not** a faithful install of the promoted project, so the full Python transitive closure (notably `keyring` → `jeepney`/`SecretStorage` on Linux and `pywin32-ctypes` on Windows) cannot be enumerated offline. No copyleft runtime dependency was observed; all observed runtime licenses are permissive and compatible with the declared `Proprietary` license. PyInstaller's GPLv2 + exception is acceptable **only while used as a build tool** — verify no PyInstaller runtime code is shipped inside the sidecar.

Native/transitive surface: cryptography→cffi (C), Pillow (C image libs), keyring→OS keyring backends, PyInstaller→pefile/pywin32-ctypes/altgraph/hooks-contrib, electron-builder→electron-winstaller (`hasInstallScript`), fleet-next→`sharp` native binaries (33 platform packages), Tauri→system GTK/WebKit libraries. These are not built or shipped by the promoted backend except the Electron/Python path.

### 2.4 License inventory generator

`keel/src/keel/release/licenses.py::collect_inventory()` emits only **direct** Python dependencies by name (4 entries), ignores transitive Python packages, and reads the legacy `License` header rather than `License-Expression` — so `cryptography` (and absent `keyring`) show as `UNKNOWN`. It lists `unresolved` but **does not fail the build**. Electron entries (283) come from the lockfile plus installed `node_modules` manifest licenses. Prior evidence records this exact gap ("cryptography/keyring marked unresolved — reported honestly").

### 2.5 Findings — dependencies

| ID | Severity | Finding | Evidence | Remediation |
| --- | --- | --- | --- | --- |
| **DEP-01** | **HIGH** | Python build inputs are unpinned: four lower-bound-only runtime deps, floating build/test tools, no lockfile, no hashes, no SBOM. Every "promoted" artifact can contain different dependency bits; a release cannot be byte-reproduced from source. | `keel/pyproject.toml`; all 8 workflows' `pip install` steps; no lock/constraints file in `git ls-tree -r e573273` | Add a committed Python lock (`uv.lock` or `requirements.txt` generated by `pip-compile --generate-hashes`) covering runtime + build + test packages; use `pip install --require-hashes -r <lock>` in every workflow; pin `pip`, `pyinstaller`, `pytest`; emit a CycloneDX/SPDX SBOM with hashes per release. Until then, record resolved versions+hashes in the release manifest and have the owner explicitly accept the reproducibility exception. **Blocks promotion.** |
| DEP-02 | MEDIUM | Release build does not enforce the npm lockfiles: `npm install` + `npx electron-builder`, conditional on `node_modules` existing. | `keel/src/keel/release/build.py::npm_install()` and `electron_build()` | Use `npm ci --ignore-scripts` where possible (then fetch Electron via a pinned URL + SHA256 check), and forbid `npx` registry fallback (`npm exec --no -- ...` or call `node_modules/.bin/electron-builder`). |
| DEP-03 | MEDIUM | Dead dependency trees retained in the promoted tree: `keel/fleet-next` (60 packages, 33 native `sharp` entries, version `0.1.0` drift from project `0.1.1`) and `keel/desktop/src-tauri` (420 crates) are referenced by **no** workflow; only their version constants are read by `keel/src/keel/release/common.py`. Candidate `e573273` itself only bumps `Cargo.toml` `0.1.0`→`0.1.1` to satisfy that gate. | workflow scan; `git diff e6e7efc e573273`; `release/common.py::VERSION_FILES` | Remove/archive the unused prototypes or move them out of the promotion scope, and update the version gate accordingly; if retained, add them to `check_version_sync.py` and pin/update their locks on a documented cadence. |
| DEP-04 | LOW | License inventory is incomplete and non-gating: direct-Python-only, ignores `License-Expression`, reports `UNKNOWN` without failing; model/voice registry has 11 entries, **0 bundled**, all `license: "UNKNOWN"`. | `release/licenses.py`; `scripts/check_model_licenses.py` | Fail CI on unresolved licenses; include transitive Python packages and SPDX expressions; cross-check packaged assets against the bundled-asset registry. |
| DEP-05 | INFO | No offline CVE/advisory database was available (`pip-audit`, `trivy`, `osv-scanner`, `safety` all absent), and network lookups were out of scope. Observed versions are current; **no claim of CVE-free status is made**. | tool inventory; installed versions above | Run `pip-audit`, `npm audit --omit=dev`, and `cargo audit` in the promotion pipeline with a cached advisory DB. |

---

## 3. GitHub Actions audit (all 8 workflows)

Files: `build-desktop.yml`, `lifecycle.yml`, `offline-license.yml`, `provider-validation.yml`, `python-tests.yml`, `secret-scan.yml`, `signing-readiness.yml`, `verify-install.yml`.

### 3.1 Third-party action pinning — PASS

- **30/30** `uses:` references across the 8 workflows are 40-character SHA pins; **0 tag-only** references.
- 5 distinct pairs, matching the prior `git ls-remote` + GitHub Git-ref API evidence in `master-plan-v6-repository-security-evidence.md`:

| Action | Pinned SHA | Refs |
| --- | --- | --- |
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` (# v7) | 12 |
| `actions/setup-python` | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (# v7) | 10 |
| `actions/setup-node` | `949feb2413d6458794dcd2491c4babbbce0c15c1` (# v7) | 3 |
| `actions/upload-artifact` | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` (# v7) | 3 |
| `actions/download-artifact` | `9000827ccba6bdab643e8b6fd33ac0654aef8333` (# v8) | 2 |

Only official `actions/*` repositories are used; no marketplace/third-party actions. `secret-scan.yml` additionally downloads the gitleaks binary from GitHub Releases with pinned `GITLEAKS_VERSION=8.30.1` and `GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`, checked with `sha256sum -c -` before extraction. **Limitation:** this offline audit verified SHA *shape* and consistency with prior evidence but did not re-resolve the five SHAs to upstream tags (no network). Note also that prior live evidence recorded `main` as tag-pinned (23 refs) — SHA pinning only becomes effective remotely when these workflows are merged/pushed to the default branch by the owner.

### 3.2 Token permissions — PASS

Top-level `permissions: contents: read` in all 8 workflows. Only `build-desktop.yml::publish` elevates to `contents: write` (required to create a GitHub Release); `lifecycle.yml` and `verify-install.yml` add `actions: read` for artifact download. No `security-events: write`, `packages: write`, `id-token: write`, or `pull-requests: write` anywhere. `GH_TOKEN` is not passed to the electron-builder packaging steps. No untrusted PR job has write permission.

### 3.3 Secrets — LOW issue

Secrets in use: `KEEL_RELEASE_SIGNING_KEY`, `KEEL_RELEASE_SIGNING_PUBLIC_KEY`, `GITHUB_TOKEN`, five provider API keys, and optional `KEEL_COMPAT_*` vars (secret fallback). Provider validation prints `CONFIGURED`/`MISSING` only and redacts exact values before logging; signing readiness prints names only.

`signing-readiness.yml` references **eight** secrets (`WINDOWS_SIGNING_CERTIFICATE_BASE64`, `WINDOWS_SIGNING_PASSWORD`, `MACOS_SIGNING_CERTIFICATE_BASE64`, `MACOS_SIGNING_PASSWORD`, `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`, `MACOS_NOTARIZATION_PASSWORD`, `LINUX_SIGNING_KEY_BASE64`) that **no build or publish job consumes** — it is a dispatch-only reporting workflow. This is unnecessary secret surface (GH-04, LOW). Recommendation: delete them if unused, or wire them into real code-signing jobs; keep only secrets that a job actually uses. No secrets are hardcoded in tracked files (see §4).

### 3.4 Unsafe PR workflows — MEDIUM issue

`verify-install.yml` triggers on `workflow_run` of "Build desktop installers" **completed**; that source workflow runs on `pull_request` (including forks). The `windows-install`/`macos-package`/`linux-package` jobs run whenever `github.event.workflow_run.conclusion == 'success'`, with no check of the triggering run's event, head repository, or actor, and they **execute** downloaded installers/AppImages on hosted runners. A fork PR can therefore cause attacker-controlled, unsigned artifacts to execute on a runner (read-scoped `GITHUB_TOKEN`, runner cache access). No write scope or extra secrets are exposed, so impact is bounded, but this is untrusted-code execution in a privileged context (GH-03, MEDIUM). Recommendation: add `if: github.event.workflow_run.event == 'push'` and/or verify `github.event.workflow_run.head_repository.full_name == github.repository`, or require an environment approval. `lifecycle.yml` is `workflow_dispatch`-only and operator-supplied, so lower risk.

### 3.5 Artifact provenance — PASS with limitation

`build-desktop.yml` is fail-closed: `validate-versions` precedes all builds; `electron-builder --publish never`; signing key staged in `RUNNER_TEMP` (outside artifact tree, `umask 077`); `verify-release-signatures` requires the owner public key and verifies every bundle before `publish`; `publish` depends on that gate, verifies published manifest and every detached signature, downloads public assets over HTTPS and compares status/size/SHA-256 before publishing `download.json`. `if-no-files-found: error` on uploads. **Limitation:** unsigned when the owner key is absent (documented); no SLSA/Sigstore provenance attestation and no SBOM attached to the release (prior evidence).

### 3.6 Clean-environment test execution — PASS

`python-tests.yml` runs the suite on fresh `ubuntu-latest`/`windows-latest`/`macos-latest`; `offline-license.yml` uses `unshare -n` and fails closed if unavailable; `verify-install.yml` installs/tests/uninstalls on fresh native runners with cleanup assertions. Signing keys are staged outside the artifact tree. Caveat: the packages installed in those clean runners are the floating versions of DEP-01.

---

## 4. Secret scan & repository gates

### 4.1 Candidate-tree secret scan — no real secrets (PASS with limitation)

Heuristic scan of **1,719** tracked text files at candidate `e573273` (11 regex families: AWS AKID, GitHub tokens, Slack, Google API key, Stripe, OpenAI/Anthropic keys, PEM private keys, JWT, high-entropy assignments) produced **89 raw matches**. Every inspected match is a synthetic test fixture, e.g. `sk-abcdefghijklmnopqrstuvwxyz`, `AKIAIOSFODNN7EXAMPLE` (AWS's documented example key), `ghp_abcdefghijklmnopqrstuvwxyz0123456789`, `"definitely-not-a-real-key"`, `whsec_test_secret_9f8e7d`, `synthetic-webhook-secret-for-tests`, and a sample JWT with `sub:1234567890`. **No workflow or configuration file contained a credential-like value.** Values were redacted in all scan output. Limitation: `gitleaks` is not installed locally, so a full-history gitleaks scan was not run here; `secret-scan.yml` performs that in CI with `fetch-depth: 0`, `--redact`, and the pinned binary above.

### 4.2 `.gitleaks.toml` — PASS

`[extend] useDefault = true`; 10 `[[allowlists]]`, each scoped with `condition = "AND"`, `targetRules = ["generic-api-key"]`, exactly one `commits = [...]` entry and one path regex. No global/repo-wide allowlist remains. Historical findings were classified as false positives in black-box reference captures and deleted demo UI strings. Re-review each entry before removal.

### 4.3 `.githooks/pre-push` — MEDIUM issue (inert version gate)

Fail-closed on step 2 (refuses push if `gitleaks` is absent) and blocks direct pushes to `main`. However step 3 checks `scripts/check_version_sync.py` at the **repository root**, which does not exist — the actual file is `keel/scripts/check_version_sync.py`. The `if [ -x ... ] || [ -f ... ]` guard is false, so the version-consistency gate is **silently skipped**. Additionally, `core.hooksPath` is unset in this worktree, so the hook is not installed here, and any developer can bypass it with `git push --no-verify`. Recommendation: correct the path to `keel/scripts/check_version_sync.py` (and run it from `keel/`), document one-time installation per clone, and treat the hook strictly as a compensating control.

### 4.4 Gates re-executed against the candidate tree — PASS

Run from a temp `git archive e573273` extraction (no repo files changed):

| Command | Result |
| --- | --- |
| `python keel/scripts/check_version_sync.py` | `OK - all sources agree on version 0.1.1 (tag v0.1.1)` (exit 0) |
| `python scripts/check_model_licenses.py` | `license registry: 11 entries, 0 bundled` / `LICENSE GATE OK` (exit 0) |
| `python scripts/verify_v6_audit.py` | `registry rows: 865`, `matrix rows: 865`, `CONSISTENCY OK` (exit 0) |
| `python keel/scripts/build_dependency_graph.py --check` | `FRESH` (exit 0) |

**Model/voice license gate limitation (LOW):** the gate only validates registry entries whose `bundled=true`; with **0 bundled entries** it passes without inspecting any packaged asset, and all 11 entries carry `license: "UNKNOWN"` with `commercial_use_allowed: false` (informational because unbundled). It is a registry-consistency check, not an asset scan. No model/voice assets are bundled in this backend-only promotion, so there is no current exposure.

---

## 5. Privacy, license, and branch protection

### 5.1 Repository remains private / license unchanged — no change made (PASS with caveat)

- `git remote -v` → `https://github.com/eliosmernica15/keel.git`; no visibility or license operation was performed by this audit.
- In-repo live evidence dated 2026-11-23 (`master-plan-v6-repository-security-evidence.md`): `gh api repos/eliosmernica15/keel --jq '{private,visibility}'` was changed to `{"private":true,"visibility":"private"}` and re-read as private; collaborators listed only `eliosmernica15` (admin). `DECISIONS.md` D-036 explicitly **rejects** making the repository public.
- `git diff origin/main e573273` restricted to license files shows only `MODEL-AND-VOICE-LICENSES.json` added (+175) and the `Cargo.toml` version bump; no license declaration changed. Project remains `"Proprietary"` in `keel/pyproject.toml`, `keel/desktop-app/package.json`, and `keel/desktop/src-tauri/Cargo.toml`; no root `LICENSE` file was added or altered.
- **Caveat:** live visibility cannot be re-verified in this offline audit. Recommended owner check before promotion: `gh api repos/eliosmernica15/keel --jq '{private,visibility}'`. Do not change either value.

### 5.2 Branch protection on the current plan — honest limitation (MEDIUM, accepted owner exception)

Direct live evidence recorded in the repository (2026-11-23, free plan, personal account, repo made private):

| Control | Live result |
| --- | --- |
| `GET /branches/main/protection` | `403 "Upgrade to GitHub Pro or make this repository public"`; branch `"protected": false` |
| `PUT /protection/required_signatures` | `404 Not Found` |
| `PUT /protection/enforce_admins` | `404 Not Found` |
| `PATCH -f allow_forking=false` | `422 "Allow forks setting can only be changed on org-owned private repositories"` |

On GitHub Free, branch protection is available for public repositories, **not private ones**; the private-repo feature requires a paid plan (Pro/Team/Enterprise) or a different forge. Consequently there are **no remote required reviews, required status checks, signed-commit requirements, or force-push/deletion blocks** on `main`. Mandatory 2FA is owner-account-controlled and was not verifiable here; no GPG/Sigstore signing identity is configured locally.

**Local hooks are not remote protection.** `.githooks/pre-push` only affects clones that opt in via `git config core.hooksPath .githooks` (unset in this worktree), can be bypassed with `--no-verify`, and enforces neither peer review nor required checks. There is no `CODEOWNERS` and no `dependabot.yml` in `.github/`. This is an accepted plan-level exception documented in `master-plan-v6-repository-security-evidence.md` and `Master Plan C11.1`; it should be **re-affirmed by the owner** at promotion. No plan was purchased and no protection was bypassed by this audit; the owner must decide whether to upgrade/move to an organization or formally accept the compensating-control posture.

---

## 6. Prioritized remediation summary

1. **DEP-01 (HIGH, blocks):** commit a hash-pinned Python lock for runtime/build/test deps; use `--require-hashes` in every workflow; pin `pip`, `pyinstaller`, `pytest`; generate an SBOM. Or record exact resolved versions/hashes per build and obtain a written owner exception.
2. **DEP-02 (MEDIUM):** switch the release build to `npm ci` and eliminate `npx` registry fallback; pin the Electron binary checksum.
3. **GH-03 (MEDIUM):** restrict `workflow_run` install jobs to trusted (push/default-branch) runs or require environment approval, so fork artifacts are never executed.
4. **SEC-02 (MEDIUM):** fix the pre-push version-gate path to `keel/scripts/check_version_sync.py`; document hook installation and its bypassability.
5. **DEP-03 (MEDIUM):** remove/archive unused `fleet-next` and Tauri prototype dependency trees from the promotion scope (and reconcile `fleet-next` version `0.1.0`).
6. **DEP-04 / GH-04 / SEC-03 / DEP-05 (LOW):** fail CI on unresolved licenses, include transitive deps, cross-check bundled assets; delete unused signing secrets; add `CODEOWNERS`/Dependabot; add offline CVE scanning.
7. **REPO-02 (MEDIUM, accepted):** owner re-affirms the no-remote-branch-protection exception or selects a plan/forge that supports it; re-verify repository privacy before promotion.

---

## 7. Statement of non-action

- No source file, workflow, manifest, hook, license, or registry file was modified.
- Repository visibility and licensing were not changed; no plan was purchased; no remote protection was bypassed.
- Nothing was pushed. The evidence file is committed locally on `agent/prod-supply` only.
- All commands were read-only with respect to the repository except the local, non-content-changing fast-forward to the existing candidate commit `e573273` and the creation of this evidence document.
