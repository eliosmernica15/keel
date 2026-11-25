# STAB-TEST-EVIDENCE

Branch `agent/stab-tests`, base `f60b080`, fix commit `f440ddd`.
Worktree: `C:\Users\Admin\.local\share\opencode\worktree\stab\tests`.

All commands below are PowerShell, executed from `keel/` unless noted. A
"clean HOME" means `HOME`/`USERPROFILE` point to an empty temp directory and
ambient provider variables (`B4M_*`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GOOGLE_API_KEY`, `KEEL_*`) are removed **by name only** (no values recorded).
`PYTHONPATH` was set to the worktree's `keel/src` because the machine's editable
`keel-harness` install points at a different checkout.

Helper runner (outside the repo):

```powershell
$ch='C:\Users\Admin\AppData\Local\Temp\opencode\stab-clean-home'
$env:HOME=$ch; $env:USERPROFILE=$ch
$env:PYTHONPATH='C:\Users\Admin\.local\share\opencode\worktree\stab\tests\keel\src'
# provider env vars removed by name
Set-Location 'C:\Users\Admin\.local\share\opencode\worktree\stab\tests\keel'
python -m pytest @args
```

Environment leak proven before any edits:

```
PS> python -c "import keel; print(keel.__file__)"
C:\Users\Admin\Desktop\Claude clone\keel\src\keel\__init__.py
```

## 1. Baseline reproduction (clean HOME, current tree, 5 reported failures)

```
python -m pytest -q `
  tests/test_distribution_package.py::test_release_manifest_has_policy_fields `
  tests/test_distribution_package.py::test_checksums_file_matches_manifest_artifacts `
  tests/test_gap_closure.py::test_c12_package_manager_manifests `
  tests/test_gap_closure.py::test_c122_airgap_bundle_and_verification `
  tests/test_release_integrity.py::test_integrity_cli_on_real_artifacts
```

Output:

```
FFFFF                                                                    [100%]
================================== FAILURES ===================================
5 failed in 5.37s
```

Exact failing assertions / causes:

| Test | Assertion / error | Missing artifact |
| --- | --- | --- |
| `test_release_manifest_has_policy_fields` | `FileNotFoundError` at `read_text()` on `ROOT/release/RELEASE-MANIFEST.json` | `release/RELEASE-MANIFEST.json` |
| `test_checksums_file_matches_manifest_artifacts` | `FileNotFoundError` at `read_text()` on `ROOT/release/RELEASE-SHA256SUMS.txt` | `release/RELEASE-SHA256SUMS.txt` |
| `test_c12_package_manager_manifests` | `FileNotFoundError(path)` from `keel.release_gaps._manifest()` | `release/RELEASE-MANIFEST.json` |
| `test_c122_airgap_bundle_and_verification` | `FileNotFoundError(path)` from `keel.release_gaps._manifest()` | `release/RELEASE-MANIFEST.json` |
| `test_integrity_cli_on_real_artifacts` | `assert result.returncode == 0` failed; stdout was `[FAIL] checksums: RELEASE-SHA256SUMS.txt missing`, `[FAIL] manifest: RELEASE-MANIFEST.json missing`, `[FAIL] latest_yml: latest.yml or manifest missing`, `[FAIL] sidecar_version: sidecar not built`, `[FAIL] dependency_inventory: inventory missing`, `integrity: 2/7 passed` | all of the above plus `dist/latest.yml`, `dist/keel-sidecar/keel.exe`, `release/DEPENDENCY-LICENSES.json` |

The worktree has neither `keel/release/` nor `keel/dist/`:

```
PS> Test-Path ...\keel\release   -> False
PS> Test-Path ...\keel\dist      -> False
```

## 2. Root cause

The five tests read build outputs from the source tree. Both directories are
git-ignored (`keel/.gitignore`: `/release/`, `dist/`). They exist only in the
developer's main checkout (`C:\Users\Admin\Desktop\Claude clone\keel`), which
also owns the editable install. Consequently the tests could only pass when
run against that untracked developer state — exactly the behaviour reported.

The air-gap test additionally tampers with
`Keel-Setup-0.1.0.exe.blockmap`, so a fixture must include that name in its
checksum file; otherwise the tamper assertion is vacuous.

## 3. Fix (real cause, no weakened assertions)

New helper: `keel/tests/fixtures/release_tree.py` (+ package `__init__.py`).
`build_release_tree(tmp_path, version=...)` creates `release/` and `dist/` in
pytest's temp directory:

* seven deterministic text stand-ins with the canonical installer names, including
  `Keel-Setup-0.1.0.exe.blockmap`;
* `RELEASE-SHA256SUMS.txt` computed from the bytes actually written;
* `RELEASE-MANIFEST.json` with all policy fields (`version`, `min_version`,
  `blocked_versions`, `rollout`, `published_at`, `files`, `checksums_file`), version
  `0.1.1`, and per-file `bytes`/`sha256` computed from the same bytes;
* `DEPENDENCY-LICENSES.json` with real entries;
* `dist/latest.yml` with the real base64 SHA-512 and byte size of the dist artifact;
* a real executable at `dist/keel-sidecar/keel.exe` (copy of the running
  interpreter) so `verify_sidecar_version()` actually spawns it and compares
  the version it prints.

Because a production sidecar binary is unavailable (and must not be committed),
the integrity CLI test derives its manifest version from that executable via
`reported_sidecar_version()`. No hash, size, checksum, or `7/7` assertion was
relaxed; no `.sig` file or signature claim was fabricated; no binary is committed.

Modified owned tests only:

* `tests/test_distribution_package.py` — the two tests now take `tmp_path` and
  read the generated `release/`; the `version == "0.1.1"` assertion is unchanged.
* `tests/test_gap_closure.py` — the two failing tests pass the generated
  `release/` to `package_manager_manifests()` / `airgap_bundle()`; all original
  assertions (including the tamper check) are unchanged.
* `tests/test_release_integrity.py` — the CLI test passes absolute temp paths and
  explicitly prepends the worktree `src` to the child process `PYTHONPATH`;
  `returncode == 0` and `"7/7 passed"` assertions are unchanged.

## 4. Verification

### 4.1 Targeted in isolation (clean HOME, worktree)

```
python -m pytest -q <each of the 5 node ids, one invocation each>
```

```
=== ISOLATED test_release_manifest_has_policy_fields ===     1 passed in 1.85s
=== ISOLATED test_checksums_file_matches_manifest_artifacts === 1 passed in 1.52s
=== ISOLATED test_c12_package_manager_manifests ===          1 passed in 2.27s
=== ISOLATED test_c122_airgap_bundle_and_verification ===     1 passed in 5.76s
=== ISOLATED test_integrity_cli_on_real_artifacts ===         1 passed in 1.88s
```

### 4.2 Combined targeted runs, repeated 3x

```
python -m pytest -q <the 5 node ids>
```

```
=== REPEAT 1 === 5 passed in 3.24s
=== REPEAT 2 === 5 passed in 4.97s
=== REPEAT 3 === 5 passed in 4.94s
```

### 4.3 Fresh clean checkout (new clone of `agent/stab-tests` at `f440ddd`)

```
git clone --branch agent/stab-tests --single-branch <worktree> <temp>\stab-fresh-clone
Test-Path <clone>\keel\release  -> False
Test-Path <clone>\keel\dist     -> False
# PYTHONPATH=<clone>\keel\src, fresh empty HOME, provider vars removed
python -m pytest -q <each id individually>   -> 1 passed (x5)
python -m pytest -q <all 5 ids>              -> 5 passed in 2.43s
```

### 4.4 Full suite (one run, clean HOME, worktree)

```
python -m pytest -q
```

```
4442 passed, 51 skipped, 3707 subtests passed in 616.78s (0:10:16)
```

All five reported tests are part of this run and passed in its ordering.
The only unusual console text was a `socketserver` `ConnectionAbortedError`
traceback from a passing test's handler; it is not a failure (0 failed).

The three modified files alone: `19 passed in 8.83s`.

## 5. Residual pollution / order-dependence investigation

Only proven leaks get fixtures; none of the following produced a failure, so no
extra isolation fixtures were added.

* **Provider env vars**: `tests/test_fleet_credentials.py` uses `monkeypatch`
  exclusively (`setenv`/`delenv` at lines 36-37, 217, 228, 243); `conftest.py`
  deliberately sets `KEEL_TOKEN`. Reproducer: ran that module plus the five
  targets in one session → `127 passed in 59.42s`. No leak.
* **Shared `~/.keel`**: the real home contains a populated `.keel` tree. Running
  the five targets with real `HOME`/`USERPROFILE` and ambient provider variables
  still gave `5 passed in 4.30s`. No leak.
* **Shared ports**: fixed ports appear in other modules (`8792`, `8793`, `8796`,
  `8797`, `8798`, `8897`). The five targets bind no ports; pairing
  `test_release_manager.py` (8792/8793) before them was included in the
  `127 passed` reproducer. No leak.
* **`sys.modules` / `sys.path`**: `test_plan_corrections.py` and
  `test_y3_backend.py` insert the worktree `src` into `sys.path`,
  `test_offline_runtime.py` saves/restores `sys.modules`, and
  `test_api_contracts.py` has an ImportError-only fallback. Pairing those modules
  (plus `test_prod_api.py`, which monkeypatches `HOME`) before the five targets
  gave `127 passed in 59.42s`. No leak.
* **Editable-install shadowing** (proven, see §1): with no `PYTHONPATH`, `import
  keel` resolves to `C:\Users\Admin\Desktop\Claude clone\keel\src`. This is a
  harness-level concern: `conftest.py` imports `keel.webapp` before any test
  module, so a fixture in an owned test file cannot retroactively fix package
  identity. It was controlled at invocation time with `PYTHONPATH`, and the CLI
  child process is given the worktree `src` explicitly. No global fixture added.

## 6. Final counts and unfixed failures

* Targeted: 5/5 passed (isolated, combined x4 total, fresh clone isolated and combined).
* Modified modules: 19 passed.
* Full suite: **4442 passed, 51 skipped, 3707 subtests passed, 0 failed**.
* Unfixed failures: none.
