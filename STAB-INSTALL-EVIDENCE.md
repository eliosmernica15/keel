# STAB-INSTALL-EVIDENCE — production installation & rollback (stabilization)

**Verdict: `pass` for the local, real-code installation/upgrade/rollback gate at
stabilization HEAD `f60b080`. Not `production_verified`.** All evidence below is
from this Windows 11 host. The rollback drill is a **local drill using the real
shipped code paths** (loopback HTTP release server, real Ed25519 dev keys, real
directory swaps, real subprocess app starts, real SQLite file). **No clean-VM
run was performed and none is claimed.** Production signing remains owner-gated:
no signing identity, no production key, no built installer, no publish, no push.

---

## 1. Scope, provenance and constraints

| Item | Value |
| --- | --- |
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\stab\install` |
| Branch | `agent/stab-install` |
| Stabilization HEAD | `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb` (`docs(stabilization): record verified baseline and failing CI workflows`) |
| Clean checkout used for Task 1 | detached `git worktree add --detach` at the exact SHA `f60b080`, under `C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\clean-checkout`; `git rev-parse HEAD` = `f60b080a1c...`, `git status --porcelain` = empty |
| Owned source files changed | `keel/src/keel/release/updater.py`, `keel/src/keel/start_health.py` |
| Owned files unchanged | `keel/src/keel/release/common.py`, `keel/src/keel/release/cli.py` (verified correct; no defect found requiring a change) |
| New files added | `keel/tests/test_stab_install_recovery.py`, `scripts/verify_stab_install.py`, this document |
| Frontend | untouched |
| Paid services / credentials / signing identity / network egress to production | none (only free public PyPI and loopback `127.0.0.1`) |
| Push / publish / deployment | none |
| Disposable root | `C:\Users\Admin\AppData\Local\Temp\opencode\stab-install` (`clean-checkout\`, `venv\`, `logs\`, `state-*\`, `clean-home\`); all temp state and venvs are disposable, nothing installed into the user's Python |

Host (exact):

```
OS: Windows-10-10.0.26300-SP0   Release: 10   Arch: AMD64   CPUs: 16
Microsoft Windows 11 Pro, build 26300, 64-bit
AMD Ryzen 7 5700U with Radeon Graphics (8 cores / 16 logical)
Python 3.11.9 | SQLite 3.45.1 | cryptography 50.0.1 | pytest 9.0.2
```

VM tooling probe: `VBoxManage` NOT FOUND, `qemu-system-x86_64` NOT FOUND,
`vmware-cmd` NOT FOUND. `keel\dist` and `keel\release` contain **0**
`Keel-Setup-*.exe` artifacts and `KEEL_RELEASE_SIGNING_KEY` is unset. A real
clean-VM installer run and a production-signed release are therefore not
locally achievable and are **not** claimed here.

---

## 2. Task 1 — clean setup from an exact clean checkout

All installs used a brand-new venv created by the system Python
(`C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe`, 3.11.9,
pip 26.0.1). The lock install used `--no-cache-dir` so every wheel is a real
download from free public PyPI, not a cache hit. Full logs are under
`...\stab-install\logs\`.

### 2.1 Commands (verbatim)

```powershell
git worktree add --detach C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\clean-checkout f60b080
python -m venv C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\venv
"C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\venv\Scripts\python.exe" -m pip install --no-cache-dir --require-hashes -r "C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\clean-checkout\keel\requirements.lock.txt"
"C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\venv\Scripts\python.exe" -m pip install --no-deps --no-build-isolation -e "C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\clean-checkout\keel"
"C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\venv\Scripts\python.exe" -c "import keel; print(keel.__version__, keel.__file__)"
```

### 2.2 Exact results

```
HEAD: f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb
STATUS: ''
VENV_EXIT=0
PIP_EXIT=0
EDITABLE_EXIT=0
VERSION=0.1.1
MODULE=C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\clean-checkout\keel\src\keel\__init__.py
IMPORT_EXIT=0
```

The pip log shows real downloads for all 32 selected wheels (e.g.
`Downloading cryptography-50.0.1-cp311-abi3-win_amd64.whl (3.8 MB)`,
`Downloading pytest-9.0.2-py3-none-any.whl (374 kB)`) and ends with
`Successfully installed altgraph-0.17.5 ... zipp-3.23.0`. Four lock entries
were skipped by marker (`exceptiongroup`, `tomli` for Python < 3.11; `macholib`
for Darwin; `secretstorage` for Linux) — expected on Python 3.11/Windows.
No hash mismatch occurred.

### 2.3 Runtime harness — 8/8 (clean venv, neutral cwd, clean HOME)

Harness: `scripts/verify_stab_install.py` (committed here); it was copied into
the detached clean checkout for execution so the code under test is exactly
`f60b080`. Subprocesses ran with `PYTHONPATH` cleared, `PYTHONNOUSERSITE=1`,
neutral cwd and a fresh `KEEL_STATE_DIR`/HOME.

```
python=C:\Users\Admin\AppData\Local\Temp\opencode\stab-install\venv\Scripts\python.exe
version=3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]
project=...\stab-install\clean-checkout\keel
state=...\stab-install\state-clean
PASS | clean_import | rc=0 version=0.1.1 module=...\clean-checkout\keel\src\keel\__init__.py stderr=''
PASS | cli_help | rc=0 stdout_lines=19 stderr=''
PASS | cli_capability_list_backend | rc=0 total_capabilities=230 backend_capabilities=['backend.describe', 'backend.invoke', 'backend.modules', 'backend.verify'] missing=[] stderr=''
PASS | db_init_fresh_state_dir | db=...\state-clean\fleet.db exists=True tables=17 schema_versions=[1,2,3,4,5,6,7,8,9,10,11] missing=[] store_db=...\fleet-service.db store_tables=17
PASS | api_health_authorized | url=http://127.0.0.1:49225/api/health status=200 body='{"ok": true, "version": "0.1.1"}'
PASS | api_health_token_gated | status_without_token=403
PASS | graceful_shutdown | thread_alive=False post_shutdown=connection_refused:URLError
PASS | version_consistency_gate | version=0.1.1 sources=7 distinct=['0.1.1']
SUMMARY: 8/8 checks passed
HARNESS_EXIT=0
```

Limitation stated honestly: shutdown is exercised through the HTTP server's
graceful `shutdown()`/`server_close()` API, not an OS Ctrl+C sent to a detached
`keel serve` process.

---

## 3. Task 2 — real upgrade path (signed manifest, SHA-256, optional Ed25519)

The shipped code path was read and exercised, not mocked:

| Stage | Real code path | Verified behaviour |
| --- | --- | --- |
| Discovery | `updater.check_for_update` → `verify.load_manifest` → `signing.verify_manifest` | Signed loopback manifest accepted; a manifest tampered after signing is rejected with `UpdateError`; syntactically corrupt JSON also fails closed. |
| Download | `updater.download_update` → `verify.fetch_bytes` | HTTPS-only except loopback with `--allow-http`; `Content-Length` enforced; SHA-256 enforced; detached Ed25519 `.sig` enforced **when a key is supplied**; bytes written only after every check, via temp file + `replace`. |
| Swap | `updater.atomic_install` | `install → backup`, `staged → install`; compensation restores the pre-call state on failure (hardened here, §6). |
| Recovery | `updater.rollback` | Refuses with "no backup"; restores known-good install, including when the live install is missing. |
| Failed starts | `start_health.record_start` | 3 consecutive failures → `rollback: True`; a success resets; counters are version-scoped; writes are now atomic (hardened here, §6). |

New test `test_signed_download_sha256_with_optional_ed25519` proves the
verification matrix with a real loopback server and ephemeral Ed25519 keys:

* signed manifest + supplied key → plan `0.1.2`;
* no key → SHA-256-only download succeeds (Ed25519 is genuinely optional);
* a different, valid keypair → `UpdateError: signature invalid`;
* same-length tampered artifact → `UpdateError: sha256 mismatch`, no file written.

User-data preservation: the drill keeps a real SQLite file at
`<machine>/userdata/keel.sqlite3` outside the swapped install directory and
reads canary `upgrade-rollback-canary` before upgrade, after upgrade and after
rollback (§4).

---

## 4. Task 3 — real local rollback drill (not clean-VM)

Exact command:

```powershell
cd C:\Users\Admin\.local\share\opencode\worktree\stab\install\keel
<venv>\Scripts\python.exe -m pytest -q -s -p no:cacheprovider tests/test_prod_upgrade_rollback.py -v
```

Exact output (`logs/step6-drill.log`):

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\Admin\.local\share\opencode\worktree\stab\install\keel
configfile: pyproject.toml
collected 6 items

tests\test_prod_upgrade_rollback.py [drill] baseline: KEEL_APP_VERSION=0.1.0; sqlite canary=upgrade-rollback-canary
[drill] check_for_update(http://127.0.0.1:53325/download.json) -> version=0.1.1 sha256=2DDEE880514C48E0...
[drill] download_update -> Keel-Setup-0.1.1.exe, bytes verified
[drill] atomic_install -> active=0.1.1 backup=0.1.0 sqlite_canary=upgrade-rollback-canary
[drill] failed start 1: rc=1 failures=1 rollback_flag=False
[drill] failed start 2: rc=1 failures=2 rollback_flag=False
[drill] failed start 3: rc=1 failures=3 rollback_flag=True
[drill] rollback -> KEEL_APP_VERSION=0.1.0; sqlite_canary=upgrade-rollback-canary
[drill] post-rollback start recorded ok; app is usable
.....[drill] interrupted swap -> PermissionError; atomic_install restored 0.1.0; app starts; sqlite intact
.

============================== 6 passed in 7.69s ==============================
DRILL_EXIT=0
```

Failure-mode coverage (all six tests in `test_prod_upgrade_rollback.py`, plus
the new recovery tests):

| Scenario | Real mechanism | Result |
| --- | --- | --- |
| Successful upgrade | signed loopback manifest → SHA-256 + Ed25519 download → atomic swap | active `0.1.1`, backup `0.1.0`, SQLite canary intact |
| N consecutive failed starts | three real subprocess starts of the broken build, `rc=1` each; `record_start` | `rollback_flag = False, False, True` |
| Automatic rollback decision + actual restoration | `rollback()` after the third failure | backup consumed, `0.1.0` active, app restarts with `rc=0`, canary intact |
| Tampered manifest | version edited after signing; also invalid JSON | `UpdateError`, no backup, no download, `0.1.0` still starts |
| Missing artifact | valid signed manifest, artifact URL 404 | `urllib.error.HTTPError`, no destination file, `0.1.0` still starts |
| Interrupted install (transfer) | server declares larger `Content-Length` than it sends | `RuntimeError: Content-Length ... != downloaded ...`, no file written |
| Interrupted install (swap) | real Windows directory lock between the two renames | `PermissionError`; compensation restores `0.1.0`; app starts; SQLite intact |
| Missing backup | `rollback()` with nonexistent backup dir | `UpdateError: no backup available for rollback`; live install untouched (new test) |
| Crash state: install missing, backup present | `atomic_install` refuses; `rollback` then restores | backup survives the failed attempt and recovers the install (new tests) |
| No spurious rollback | healthy `0.1.1` with three successful starts | never flags rollback; stays `0.1.1` |

**Local drill vs clean-VM:** this is a local drill on the build host using the
real shipped code and an ephemeral dev key. It is **not** a disposable-VM run of
the signed NSIS installers, not a clean-OS run, and not a production-key run.
`PRODUCTION-READINESS-MATRIX.md` external check 5 remains outstanding. Do not
record this as `production_verified`.

---

## 5. Task 4 — version consistency gate

```
$ <venv>\Scripts\python.exe scripts\check_version_sync.py --tag v0.1.1
OK - all sources agree on version 0.1.1 (tag v0.1.1)
VERSION_GATE_EXIT=0
```

`common.load_versions()` reports all 7 sources at `0.1.1`
(`pyproject.toml`, `desktop-app/package.json`, `desktop-app/package-lock.json`,
`site/download.json`, `desktop/src-tauri/tauri.conf.json`,
`desktop/src-tauri/Cargo.toml`, `src/keel/__init__.py`);
`validate_version('v0.1.1')` returns `0.1.1`. **No version was bumped.**
`test_version_sync.py` passes in the final run, including its standalone-gate
test that rejects a deliberately drifted `Cargo.toml`.

---

## 6. Defects found and fixed (with reproduction)

Both defects are in files owned by this task and were reproduced on the
unmodified `f60b080` sources before the fix (`logs/step4-defect-repro.log`:
`3 failed, 4 passed`), then verified fixed (`logs/step4-new-tests.log`:
`7 passed`).

1. **Failed swap destroyed the previous backup.** Original `atomic_install`
   called `shutil.rmtree(backup_dir)` *before* attempting the two renames. A
   failure of either rename (e.g. a lock on the live install, or a crash) left
   the installation with no fallback at all. Fix: move the existing backup
   aside to a `.backup.prior.<uuid>` sibling, attempt the swap, restore the
   prior backup on any failure, and delete it only after the new install is
   live (best-effort cleanup that cannot fail a successful upgrade).
   Regression tests: `test_failed_first_rename_preserves_existing_backup`,
   `test_failed_second_rename_restores_full_pre_state`.

2. **Torn health-state write silently re-armed auto-rollback.** Original
   `start_health._save` wrote JSON directly over `start-health.json`. A crash
   or disk error mid-write left a truncated file; `_load` treats unreadable JSON
   as empty state, so the consecutive-failure counter reset to 0 and three
   failed starts would never trigger rollback. Fix: write a sibling temp file
   and `replace()` atomically, with temp cleanup. Regression test:
   `test_torn_health_write_does_not_reset_failure_counter` — before the fix it
   observed `failures = 1` instead of `3`.

Additional regression coverage added without source change:
`test_missing_install_does_not_destroy_backup`,
`test_rollback_refuses_when_backup_missing`,
`test_rollback_recovers_when_install_missing`, and the signed-download
verification-matrix test. `common.py` and `cli.py` were reviewed and found
correct for this scope; no arbitrary change was made.

---

## 7. Verification runs (clean HOME, fresh state)

Environment for all final runs: `USERPROFILE`/`HOME` set to a fresh
`...\stab-install\clean-home`, `KEEL_STATE_DIR` fresh, `PYTHONPATH` set to the
worktree's `keel\src` (so the edited sources are under test),
`PYTHONNOUSERSITE=1`.

```
$ <venv>\python.exe -m pytest -q -p no:cacheprovider \
    tests/test_stab_install_recovery.py tests/test_updater.py \
    tests/test_start_health.py tests/test_prod_upgrade_rollback.py \
    tests/test_version_sync.py
.........................                                                [100%]
25 passed in 16.39s
FINAL_TESTS_EXIT=0
```

Broader release/install regression set:

```
13 files (release controls/hardening/integrity/manager/no_secrets/signing,
signing_gate, installer_smoke, distribution_package, distribution,
supply_chain, updater, start_health):
3 failed, 78 passed in 36.28s
```

The 3 failures are the **pre-existing, artifact-dependent baseline failures**
recorded in `POST-PROMOTION-STABILIZATION-BASELINE.md`:
`test_release_integrity.py::test_integrity_cli_on_real_artifacts` and two in
`test_distribution_package.py` (`test_release_manifest_has_policy_fields`,
`test_checksums_file_matches_manifest_artifacts`) — all fail because
`keel/release/RELEASE-MANIFEST.json` and `RELEASE-SHA256SUMS.txt` do not exist
in a source checkout. The identical 3 failures reproduce on the unmodified
clean checkout at `f60b080` (`logs/step7-baseline-failures.log`:
`3 failed, 2 passed`), confirming they are not caused by these changes. They
are outside this task's scope (no release artifacts are built here).

---

## 8. Gate verdicts

| Gate | Verdict | Basis |
| --- | --- | --- |
| Clean setup from exact clean checkout | **pass (local)** | Hash-pinned `--no-cache-dir` install, editable install, import, CLI, DB init, health, shutdown: 8/8 harness checks (§2). |
| Real signed upgrade path (SHA-256 + optional Ed25519) | **pass (local)** | Real loopback signed release, real verification matrix, atomic swap, SQLite preservation (§3–4). |
| Local rollback drill | **pass (local)** | 6/6 drill tests, including three-failed-start decision, actual restoration, restart, data preservation, and all failure modes (§4). |
| Version consistency | **pass** | All 7 sources at `0.1.1`; standalone gate exit 0; no bump (§5). |
| Defect remediation | **pass** | 3 reproducible defects on unmodified HEAD; fixed; 7/7 new tests and 25/25 required tests pass (§6–7). |
| Production signing gate | **owner-gated / not exercised** | No signing identity, no production key, no built installer, no publish. Only ephemeral dev keys were used. Must remain blocked until the owner supplies the identity. |
| Clean-VM external check 5 | **not performed** | No VM tooling and no installers on this host. Local drill is explicitly not clean-VM evidence. |
| `production_verified` | **No** | No deployment/live evidence, no signed production release, no clean-VM run, 3 pre-existing release-artifact test failures. |

**Overall: local installation/upgrade/rollback gate = `pass`; the two external
gates (production signing identity and disposable-VM check 5) remain open and
owner-gated. No push was performed.**

## 9. Reproduction

```powershell
$root = 'C:\Users\Admin\AppData\Local\Temp\opencode\stab-install'
$work = 'C:\Users\Admin\.local\share\opencode\worktree\stab\install'
$py   = "$root\venv\Scripts\python.exe"

git worktree add --detach "$root\clean-checkout" f60b080
python -m venv "$root\venv"
& $py -m pip install --no-cache-dir --require-hashes -r "$root\clean-checkout\keel\requirements.lock.txt"
& $py -m pip install --no-deps --no-build-isolation -e "$root\clean-checkout\keel"

$env:KEEL_SETUP_PROJECT = "$root\clean-checkout\keel"
$env:KEEL_STATE_DIR = "$root\state-clean"
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = ''
& $py "$root\clean-checkout\scripts\verify_stab_install.py"   # expect 8/8

$env:USERPROFILE = "$root\clean-home"; $env:HOME = $env:USERPROFILE
$env:KEEL_STATE_DIR = "$root\state-final"
$env:PYTHONPATH = "$work\keel\src"
Push-Location "$work\keel"
& $py -m pytest -q -p no:cacheprovider `
  tests/test_stab_install_recovery.py tests/test_updater.py `
  tests/test_start_health.py tests/test_prod_upgrade_rollback.py `
  tests/test_version_sync.py                                  # expect 25 passed
& $py -m pytest -q -s -p no:cacheprovider tests/test_prod_upgrade_rollback.py -v
Pop-Location
```

Exact logs are retained (not committed) at
`...\stab-install\logs\step1-install.log`, `step2-editable.log`,
`step3-verify.log`, `step3-baseline-tests.log`, `step4-new-tests.log`,
`step4-defect-repro.log`, `step5-final-tests.log`, `step6-drill.log`,
`step7-regression.log`, `step7-baseline-failures.log`.
