# FINAL-INSTALL-EVIDENCE — clean installation, upgrade, rollback and recovery lifecycle

**Verdict: `pass` for the local disposable-environment harness at completion HEAD
`35fb2b8`. This is explicitly NOT `production_verified` and NOT a clean-VM run.**
Every scenario below ran on this Windows 11 build host inside a brand-new venv
and fresh pytest `tmp_path` state roots with a synthetic HOME. Signing used an
**ephemeral Ed25519 development keypair generated at test time**: it proves the
verification *code path* only and confers **no trust and no production signing
authority**. Clean-VM validation is **pending** (no VM tooling, no installers,
no owner-supplied signing identity on this host). No push, publish or deploy was
performed.

---

## 1. Scope, provenance and constraints

| Item | Value |
| --- | --- |
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\final\install` |
| Branch | `agent/final-install` |
| Completion HEAD | `35fb2b8abfd784393b2b252e2b9e2927aba817dd` — `Merge pull request #17 from eliosmernica15/stabilization/post-promotion-production-2026-11-25` |
| Owned source changed | `keel/src/keel/start_health.py` (hardened corrupt-state handling, §6) |
| Owned source reviewed, unchanged | `keel/src/keel/release/updater.py`, `keel/src/keel/release/build.py` — correct for this scope; no defect found requiring a change |
| New files | `keel/tests/test_final_install.py`, this document |
| Other files | frontend, workflows, other source/tests: **untouched** |
| Push / publish / deploy | **none** |
| Paid services / credentials / production keys | **none**; only a loopback HTTP server and ephemeral dev keys |
| Disposable root | `C:\Users\Admin\AppData\Local\Temp\opencode\final-install` (`venv\`, `clean-home\`, `state-clean\`, `logs`, helper runner); all temp state and the venv are disposable; nothing was installed into the user's Python |

Host (exact):

```
OS: Windows-10-10.0.26300-SP0   Release: 10   Arch: 64bit
Microsoft Windows 11 Pro, build 26300, AMD Ryzen 7 5700U (8 cores / 16 logical)
Python 3.11.9 | pip 26.0.1 | SQLite 3.45.1 | pytest 9.0.2 | cryptography 50.0.1
```

VM/installer/signing probe (exact results):

```
VBoxManage NOT FOUND
qemu-system-x86_64 NOT FOUND
vmware-cmd NOT FOUND
hyperv NOT FOUND
INSTALLERS=0            # Keel-Setup-*.exe under keel\dist and keel\release
SIGNING_KEY_SET=False   # KEEL_RELEASE_SIGNING_KEY
```

Therefore a real clean-OS installer execution, a multi-OS/architecture matrix
and a production-signed release are **not locally achievable** and are **not**
claimed. They remain owner/CI-gated external work (§9).

---

## 2. Disposable harness design (venv + temp dirs, not a VM)

The harness is the committed, self-contained file
`keel/tests/test_final_install.py`. It can be run directly (it bootstraps a
fresh synthetic HOME before pytest imports the package) or through pytest with
an explicit clean-HOME wrapper. All state is isolated per scenario:

* **venv**: created from the system Python 3.11.9 with `--no-cache-dir
  --require-hashes` against `keel/requirements.lock.txt`, then the checkout is
  installed editable with `--no-deps --no-build-isolation`. No user site
  (`PYTHONNOUSERSITE=1`).
* **temp dirs**: every scenario gets a fresh pytest `tmp_path` containing
  `home/`, `state/`, `machine/{install,backup,staged,userdata}/` and a served
  release tree. No run reuses another run's state.
* **no VM**: fault injection is at the filesystem boundary (simulated `Path.rename`
  lock, truncated `Content-Length`, wrong-shaped JSON), and app starts are real
  `subprocess.run` calls of a tiny version-reporting stub — not an OS installer.
* **ephemeral keys only**: `signing.generate_keypair()` at fixture setup; public
  key supplied to `updater.check_for_update`/`download_update` so Ed25519
  verification is genuinely exercised. No key is persisted in the repo.

Harness entry point (committed):

```powershell
cd C:\Users\Admin\.local\share\opencode\worktree\final\install\keel
& "$root\venv\Scripts\python.exe" tests\test_final_install.py
# prints "[final] disposable root: ..." then per-scenario PASS lines
# result: 13 passed in 18.98s
```

Exact recorded output tail (`final-install\self-contained-harness.log`):

```
[final] rollback -> KEEL_APP_VERSION=0.1.0; sqlite_canary=final-install-canary
PASSED
tests/test_final_install.py::test_explicit_rollback_after_healthy_upgrade [final] explicit rollback: healthy 0.1.1 -> 0.1.0; data preserved
PASSED
tests/test_final_install.py::test_backup_before_migration_and_restore [final] pre-migration backup -> restore: records=1 canary=final-install-canary; digest 6822c6e4b1e5e012...
PASSED
tests/test_final_install.py::test_corrupt_health_entry_does_not_crash_failure_recording [final] corrupt health entry: no crash; 3 consecutive failures still trigger rollback
PASSED
tests/test_final_install.py::test_uninstall_preserves_user_data_and_reinstall [final] uninstall KEEP_DATA: only app dir removed; settings, health and sqlite canary survive; reinstall starts cleanly
PASSED

============================= 13 passed in 18.98s =============================
HARNESS_EXIT=0
```

---

## 3. Environment preparation (verbatim commands and results)

```powershell
$root = "C:\Users\Admin\AppData\Local\Temp\opencode\final-install"
New-Item -ItemType Directory -Force -Path $root | Out-Null
python -m venv "$root\venv"
& "$root\venv\Scripts\python.exe" -m pip install --no-cache-dir --require-hashes -r "...\keel\requirements.lock.txt"
& "$root\venv\Scripts\python.exe" -m pip install --no-deps --no-build-isolation -e "...\keel"
& "$root\venv\Scripts\python.exe" -c "import keel; print(keel.__version__, keel.__file__)"
```

Results:

```
PIP_EXIT=0
EDITABLE_EXIT=0
VERSION=0.1.1
MODULE=C:\Users\Admin\.local\share\opencode\worktree\final\install\keel\src\keel\__init__.py
```

The hashed install fetched real wheels from public PyPI (e.g.
`cryptography-50.0.1`, `pytest-9.0.2`, `pip-26.0.1`) and ended with
`Successfully installed ... zipp-3.23.0`; no hash mismatch.

Clean-HOME wrapper used for the full required-suite runs (stored at
`$root\run_clean.py`, shown here so the run is reproducible without a VM):

```python
from __future__ import annotations
import os, sys
from pathlib import Path
root = Path(__file__).resolve().parent
home = root / "clean-home"; home.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(home)
os.environ["USERPROFILE"] = str(home)
os.environ["KEEL_STATE_DIR"] = str(root / "state-clean")
os.environ["PYTHONNOUSERSITE"] = "1"
os.environ.pop("KEEL_START_HEALTH_FILE", None)
for key in ("KEEL_MIN_VERSION", "KEEL_BLOCKED_VERSIONS", "KEEL_ROLLOUT_MODE",
            "KEEL_ROLLOUT_PERCENTAGE", "KEEL_PUBLISHED_AT"):
    os.environ.pop(key, None)
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
```

Full-suite command:

```powershell
Push-Location "...\worktree\final\install\keel"
& "$root\venv\Scripts\python.exe" "$root\run_clean.py" -q -p no:cacheprovider `
  tests/test_final_install.py tests/test_updater.py tests/test_start_health.py `
  tests/test_prod_upgrade_rollback.py tests/test_stab_install_recovery.py `
  tests/test_version_sync.py
Pop-Location
```

---

## 4. Per-scenario results

All results are from the real shipped code paths against a loopback signed
release. Every row was produced by a test in `tests/test_final_install.py`.
“Manifest integrity” means: embedded signature verified with the ephemeral
public key, declared version checked, and each file's `bytes` and `sha256`
recomputed from the bytes on disk; “version gate” means standalone
`check_version_sync.py --tag v0.1.1` plus `common.load_versions()`.

| # | Scenario | Real mechanism | Result / observed output |
| --- | --- | --- | --- |
| 1 | Fresh install, first launch, config/state creation | Clean HOME subprocess writes `settings.json`, `start-health.json`, SQLite state via `settings_store`/`start_health` | **PASS** — `settings.json` + `start-health.json` + `keel.sqlite3` created; first save has no `.bak` yet; version gate OK |
| 2 | Upgrade 0.1.0 → 0.1.1 with user data | signed loopback manifest → SHA-256 + Ed25519 download → `atomic_install`; real subprocess starts | **PASS** — `active=0.1.1 backup=0.1.0 sqlite_canary=final-install-canary`; manifest signature+sha256 verified; version gate OK |
| 3 | Interrupted download | server declares `Content-Length` larger than body | **PASS** — `RuntimeError: Content-Length ... != downloaded ...`; no destination file; 0.1.0 still starts |
| 4 | Interrupted install | simulated lock on the staged dir between the two renames | **PASS** — compensation restored 0.1.0; no stale backup; user data intact |
| 5 | Corrupt manifest | manifest tampered after signing; also invalid JSON | **PASS** — both raise `UpdateError`; no backup/download; 0.1.0 still healthy |
| 6 | Corrupt checksum | validly signed manifest with a flipped `sha256` | **PASS** — `UpdateError: sha256 mismatch`; no file written; 0.1.0 still healthy |
| 7 | Corrupt signature | valid manifest, detached `.sig` replaced with junk | **PASS** — `UpdateError: signature invalid`; no file written; 0.1.0 still healthy |
| 8 | Failed startup | real broken app stub + `record_start` | **PASS** — attempts 1 and 2 recorded (`failures=1,2`), `rollback=False` (no early rollback) |
| 9 | 3 failed starts → rollback | three real `rc=1` starts, `record_start`, then `rollback` | **PASS** — flags `[False, False, True]`; rollback restores 0.1.0, `sqlite_canary=final-install-canary`, post-rollback start `rc=0` |
| 10 | Explicit rollback | manual `rollback` after a healthy upgrade | **PASS** — healthy 0.1.1 → 0.1.0; DB canary preserved |
| 11 | Backup before migration, restore | `backups.backup_database` (encrypted, verified), simulated `DROP TABLE`, `restore_database` into a fresh path | **PASS** — `records=1`, digest `6822c6e4b1e5e012...`, restored canary intact |
| 12 | Corrupt health-state entry | wrong-shaped but parseable `start-health.json` | **PASS after fix** (failed before, §6) — no crash; three consecutive failures still set `rollback=True` |
| 13 | Uninstall preserving user data, reinstall | `y4_d4_x7_backend.uninstall_plan(KEEP_DATA)` (dry-run plan, then app dir only removed) + fresh install | **PASS** — `would_delete == [app]`; settings, health and SQLite survive; reinstall starts; version gate OK |

Cross-cutting checks at every step: `_assert_manifest_integrity()` runs before
each download in `_upgrade()`, and `_assert_version_sync()` runs after each
upgrade and reinstall. Exact gate output:

```
$ & "$root\venv\Scripts\python.exe" scripts\check_version_sync.py --tag v0.1.1
OK - all sources agree on version 0.1.1 (tag v0.1.1)
VERSION_GATE_EXIT=0
SOURCES 7
DISTINCT ['0.1.1']
```

No version was bumped. `keel.__version__`, `release.__version__` and all seven
gated sources (`pyproject.toml`, both desktop-app package files,
`site/download.json`, both desktop native config files, `src/keel/__init__.py`)
remain `0.1.1`.

---

## 5. Verification run (required suite, clean HOME)

Exact command is in §3. Exact output (`final-install\final-verify.log`):

```
......................................                                   [100%]
38 passed in 23.04s
VERIFY_EXIT=0
```

Composition (`--collect-only -q`: `38 tests collected`): 13 new lifecycle tests
+ 6 `test_updater.py` + 3 `test_start_health.py` + 6
`test_prod_upgrade_rollback.py` + 7 `test_stab_install_recovery.py` + 3
`test_version_sync.py` = 38.

A verbose run (`-s -v`) retained at `final-verify-verbose.log` shows the drill
lines, including:

```
[drill] baseline: KEEL_APP_VERSION=0.1.0; sqlite canary=upgrade-rollback-canary
[drill] failed start 3: rc=1 failures=3 rollback_flag=True
[drill] rollback -> KEEL_APP_VERSION=0.1.0; sqlite_canary=upgrade-rollback-canary
[final] failed start 3: rc=1 failures=3 rollback_flag=True
[final] rollback -> KEEL_APP_VERSION=0.1.0; sqlite_canary=final-install-canary
======================= 38 passed in 111.02s (0:01:51) ========================
```

Broader regression (13 release/config files) result:

```
1 failed, 100 passed in 128.21s (0:02:08)
```

The single failure is
`test_release_integrity.py::test_integrity_cli_on_real_artifacts`
(`sidecar_version: reported='' expected='3.11.9'`). It is an **artifact fixture
limitation, not a regression from this work**: the fixture copies the running
`python.exe` into `dist/keel-sidecar/keel.exe` and runs `--version`; a copied
**venv** `python.exe` without its adjacent `pyvenv.cfg` exits 106 with
`No pyvenv.cfg file`, so the reported version is empty. Reproduced directly:

```
RC 106
OUT ''
ERR 'No pyvenv.cfg file\n'
```

The same test is recorded as a pre-existing baseline failure in
`STAB-INSTALL-EVIDENCE.md` §7. It does not touch any file changed here. It is
excluded from the required-suite verdict and should be re-run in CI with a
non-venv interpreter or a built sidecar.

---

## 6. Defect found, reproduced failing, then fixed and passing

**Defect: a parseable but wrong-shaped start-health state crashed the failure
recorder, defeating auto-rollback.** `start_health.record_start` did
`entry = dict(doc.get(version, {}) or {})`. If `start-health.json` contained a
valid JSON object whose version entry was not a mapping (manual edit, partially
recovered write, or a downgraded writer), this raised `ValueError`. A launcher
that crashes while recording a failed start can never accumulate three strikes,
so the three-failed-start rollback would never fire.

Before the fix — exact command/output (`final-install\defect-repro.log`):

```powershell
& "$root\venv\Scripts\python.exe" "$root\run_clean.py" -q -p no:cacheprovider `
  tests/test_final_install.py::test_corrupt_health_entry_does_not_crash_failure_recording
```

```
>       entry = dict(doc.get(version, {}) or {})
E       ValueError: dictionary update sequence element #0 has length 1; 2 is required
src\keel\start_health.py:61: ValueError
FAILED tests/test_final_install.py::test_corrupt_health_entry_does_not_crash_failure_recording
1 failed in 3.98s
REPRO_EXIT=1
```

Fix (`keel/src/keel/start_health.py`): `_load` now discards non-mapping entries
after parsing, consistent with its existing behaviour of discarding a
non-document root. This is defensive and preserves the working flow: valid
state is unchanged, atomic `_save` and version-scoped counters are unchanged.

After the fix — exact command/output (`final-install\defect-fixed.log`):

```
& "$root\venv\Scripts\python.exe" "$root\run_clean.py" -q -p no:cacheprovider `
  tests/test_final_install.py::test_corrupt_health_entry_does_not_crash_failure_recording
.                                                                        [100%]
1 passed in 3.73s
FIXED_EXIT=0
```

`updater.py` and `build.py` were reviewed for the same class of edge case
(atomic swap compensation, manifest/signature/sha256 gating, clean staging) and
found correct at this HEAD; no arbitrary change was made to them.

---

## 7. Local drill vs clean-VM — explicit distinction

| Gate | Verdict | Basis |
| --- | --- | --- |
| Disposable local harness (venv + temp dirs) | **pass (local)** | 13/13 scenarios; fresh venv, synthetic HOME, loopback server, real code paths (§2, §4) |
| Required suite in clean HOME | **pass (local)** | 38/38 (§5) |
| Version sync / manifest integrity | **pass** | 7/7 sources at 0.1.1; gate exit 0; signature + sha256 + size verified at every upgrade step (§4) |
| Defect remediation | **pass** | failing reproduction then passing regression (§6) |
| Trusted / production signing | **not exercised** | ephemeral dev key only; no signing identity, no production key, no built installer; no trust claimed |
| Clean-VM install on each OS/architecture | **pending (external)** | no VM tooling and no installers on this host (§1) |
| Upgrade from every prior release in a VM | **pending (external)** | only the 0.1.0 → 0.1.1 local drill was run |
| `production_verified` | **No** | no VM, no signed production release, no deployment/live evidence |

This document deliberately does **not** describe the local drill as VM evidence.
The loopback server, ephemeral keypair, filesystem fault injection and
subprocess app stub are local simulations of the OS-installer lifecycle.

---

## 8. External blockers / owner actions

1. **No VM tooling** (`VBoxManage`, `qemu-system-x86_64`, `vmware-cmd`, Hyper-V
   all absent). A disposable clean-OS run on Windows/macOS/Linux remains CI's
   job after a push.
2. **No installers** (`INSTALLERS=0`). `keel/release/build.py` builds native
   NSIS/PKG/DEB/RPM artifacts on a matching OS runner; none exist here.
3. **No signing identity** (`KEEL_RELEASE_SIGNING_KEY` unset). All Ed25519 keys
   in this evidence were generated in-process and discarded with `tmp_path`.
4. **Artifact-dependent baseline test** in §5 needs a proper sidecar binary or
   a non-venv interpreter in CI; it is out of scope for the owned files.

No push, publish, release, credential use or payment was involved.

---

## 9. Reproduction

```powershell
$root = 'C:\Users\Admin\AppData\Local\Temp\opencode\final-install'
$work = 'C:\Users\Admin\.local\share\opencode\worktree\final\install'
$py   = "$root\venv\Scripts\python.exe"

python -m venv "$root\venv"
& $py -m pip install --no-cache-dir --require-hashes -r "$work\keel\requirements.lock.txt"
& $py -m pip install --no-deps --no-build-isolation -e "$work\keel"

Push-Location "$work\keel"
& $py "tests\test_final_install.py"                       # 13/13, clean HOME bootstrap
& $py "$root\run_clean.py" -q -p no:cacheprovider `
    tests/test_final_install.py tests/test_updater.py `
    tests/test_start_health.py tests/test_prod_upgrade_rollback.py `
    tests/test_stab_install_recovery.py tests/test_version_sync.py   # 38/38
& $py "scripts\check_version_sync.py" --tag v0.1.1       # OK - all sources agree
Pop-Location
```

Exact logs are retained (not committed) at
`C:\Users\Admin\AppData\Local\Temp\opencode\final-install\`:
`pip-install.log`, `pip-editable.log`, `baseline-clean-tests.log`,
`defect-repro.log`, `defect-fixed.log`, `final-install-tests.log`,
`self-contained-harness.log`, `final-verify.log`,
`final-verify-verbose.log`, `version-gate.log`, `broader-regression.log`.
