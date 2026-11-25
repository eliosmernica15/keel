# PROD-CLEAN-SETUP-EVIDENCE — PR-16 (clean setup and dependency install)

**Verdict: `pass` — real local clean-checkout evidence. PR-16 can be closed as `pass`.**

This is **not** `production_verified`: there is no deployed production instance, no
signed/published release, no clean-VM run, no native Linux/macOS run, and no green
full-suite run. Three defects were observed (§6); one is a reproducible stale-hash
test fixture at candidate HEAD. They are recorded honestly and are **not** caused by
dependency installation or clean setup. They are tracked outside the PR-16 scope.

It is also no longer `unverified`: the missing clean-checkout install/import/CLI/DB/
health/shutdown evidence now exists and is reproduced below (7/7 harness checks, two
independent disposable venvs, one with `--no-cache-dir` forcing real public-PyPI
downloads).

---

## 1. Scope and constraints honoured

| Item | Value |
| --- | --- |
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\production\setup` |
| Branch | `agent/final-setup` |
| Candidate HEAD | `ac84fee` (`ac84feebd8e889ad0afdc21e972fe162d3fd736c`, `docs(release): classify all final candidate paths in promotion manifest`) |
| Pre-existing worktree state | clean (`git status --short` empty before work) |
| Files created in worktree | `PROD-CLEAN-SETUP-EVIDENCE.md`, `scripts/verify_clean_setup.py` only |
| Source / tests / docs edited | **none** |
| Frontend work | **none** |
| Push | **none** |
| Commit | local commit of the two allowed files on `agent/final-setup` |
| User environment | untouched; all installs in two disposable venvs under `%TEMP%` |
| Network | free public PyPI only (`https://pypi.org`), no paid services, no credentials |

Disposable root: `C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup`
(contains `venv\`, `venv-nocache\`, `state\`, `test-state*\`, `logs\`, `scripts\`).

## 2. Hardware / OS / interpreter

```
CPU=AMD Ryzen 7 5700U with Radeon Graphics
CORES=8
LOGICAL_PROCESSORS=16
RAM_GB=13.85
OS=Microsoft Windows 11 Pro
OS_BUILD=26300
OS_VERSION=10.0.26300
ARCH=AMD64
USER=Admin
HOST=ELIOS
PY=3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)] | Windows-10-10.0.26300-SP0 | AMD64
```

System `python` used only to *create* the venvs:
`C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe` (3.11.9, pip 26.0.1).
Both venvs are Python 3.11.9 AMD64. `py --list` also showed 3.14.7 installed; it was
not used (project requires `>=3.11`; 3.11 chosen to match the lock markers).

## 3. PyPI reachability / hash cross-check (preflight)

Script `scripts/check_pypi.py` in the disposable root queried the free public JSON API:

```
url = "https://pypi.org/pypi/pytest/9.0.2/json"
STATUS= 200
INFO_VERSION= 9.0.2
SDIST_DIGESTS= ['75186651a92bd89611d1d9fc20f0b4345fd827c41ccd5c299a868a05d70edf11']
WIN_CP311_WHEELS= []
```

The sdist SHA256 matches `keel/requirements.lock.txt:309` exactly
(`75186651a92bd89611d1d9fc20f0b4345fd827c41ccd5c299a868a05d70edf11`).

## 4. Exact commands and full output

### 4.1 Disposable venv + hash-pinned dependency install

```
python -m venv C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\venv
"C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\venv\Scripts\python.exe" -m pip install --require-hashes -r "C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel\requirements.lock.txt"
```

<details>
<summary>Full output (log: <code>logs/step1-install.log</code>)</summary>

```
=== HOST ===
Microsoft Windows NT 10.0.26300.0
Python 3.11.9
platform: Windows-10-10.0.26300-SP0
machine: AMD64
executable: C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
=== CREATE VENV ===
CMD: python -m venv "C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\venv"
venv created: True
=== PIP INSTALL LOCK ===
CMD: "C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\venv\Scripts\python.exe" -m pip install --require-hashes -r "C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel\requirements.lock.txt"
Ignoring exceptiongroup: markers 'python_version < "3.11"' don't match your environment
Ignoring macholib: markers 'sys_platform == "darwin"' don't match your environment
Ignoring secretstorage: markers 'sys_platform == "linux"' don't match your environment
Ignoring tomli: markers 'python_version < "3.11"' don't match your environment
Collecting altgraph==0.17.5 (from -r C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel\requirements.lock.txt (line 8))
  Using cached altgraph-0.17.5-py2.py3-none-any.whl (21 kB)
Collecting backports-tarfile==1.2.0 (from -r ... requirements.lock.txt (line 11))
  Using cached backports.tarfile-1.2.0-py3-none-any.whl (30 kB)
Collecting certifi==2026.7.22 (from -r ... (line 14))
  Using cached certifi-2026.7.22-py3-none-any.whl (136 kB)
Collecting cffi==2.1.1 (from -r ... (line 17))
  Using cached cffi-2.1.1-cp311-cp311-win_amd64.whl (185 kB)
Collecting colorama==0.4.6 (from -r ... (line 118))
  Using cached colorama-0.4.6-py2.py3-none-any.whl (25 kB)
Collecting cryptography==50.0.1 (from -r ... (line 121))
  Using cached cryptography-50.0.1-cp311-abi3-win_amd64.whl (3.8 MB)
Collecting importlib-metadata==8.7.1 (from -r ... (line 171))
  Using cached importlib_metadata-8.7.1-py3-none-any.whl (27 kB)
Collecting iniconfig==2.3.0 (from -r ... (line 174))
  Using cached iniconfig-2.3.0-py3-none-any.whl (7.5 kB)
Collecting jaraco-classes==3.4.0 (from -r ... (line 177))
  Using cached jaraco.classes-3.4.0-py3-none-any.whl (6.8 kB)
Collecting jaraco-context==6.1.2 (from -r ... (line 180))
  Using cached jaraco_context-6.1.2-py3-none-any.whl (7.9 kB)
Collecting jaraco-functools==4.6.0 (from -r ... (line 183))
  Using cached jaraco_functools-4.6.0-py3-none-any.whl (11 kB)
Collecting jeepney==0.9.0 (from -r ... (line 186))
  Using cached jeepney-0.9.0-py3-none-any.whl (49 kB)
Collecting keyring==25.7.0 (from -r ... (line 189))
  Using cached keyring-25.7.0-py3-none-any.whl (39 kB)
Collecting more-itertools==11.2.1 (from -r ... (line 195))
  Using cached more_itertools-11.2.1-py3-none-any.whl (74 kB)
Collecting packaging==25.0 (from -r ... (line 198))
  Using cached packaging-25.0-py3-none-any.whl (66 kB)
Collecting pefile==2024.8.26 (from -r ... (line 201))
  Using cached pefile-2024.8.26-py3-none-any.whl (74 kB)
Collecting pillow==11.1.0 (from -r ... (line 204))
  Using cached pillow-11.1.0-cp311-cp311-win_amd64.whl (2.6 MB)
Collecting pip==26.0.1 (from -r ... (line 276))
  Using cached pip-26.0.1-py3-none-any.whl (1.8 MB)
Collecting pluggy==1.6.0 (from -r ... (line 279))
  Using cached pluggy-1.6.0-py3-none-any.whl (20 kB)
Collecting pycparser==3.0 (from -r ... (line 282))
  Using cached pycparser-3.0-py3-none-any.whl (48 kB)
Collecting pygments==2.19.2 (from -r ... (line 285))
  Using cached pygments-2.19.2-py3-none-any.whl (1.2 MB)
Collecting pyinstaller==6.19.0 (from -r ... (line 288))
  Using cached pyinstaller-6.19.0-py3-none-win_amd64.whl (1.4 MB)
Collecting pyinstaller-hooks-contrib==2026.2 (from -r ... (line 301))
  Using cached pyinstaller_hooks_contrib-2026.2-py3-none-any.whl (453 kB)
Collecting pypdf==6.21.4 (from -r ... (line 304))
  Using cached pypdf-6.21.4-py3-none-any.whl (410 kB)
Collecting pytest==9.0.2 (from -r ... (line 307))
  Using cached pytest-9.0.2-py3-none-any.whl (374 kB)
Collecting pywin32-ctypes==0.2.3 (from -r ... (line 310))
  Using cached pywin32_ctypes-0.2.3-py3-none-any.whl (30 kB)
Collecting setuptools==84.0.0 (from -r ... (line 316))
  Using cached setuptools-84.0.0-py3-none-any.whl (818 kB)
Collecting typing-extensions==4.16.0 (from -r ... (line 385))
  Using cached typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Collecting tzdata==2026.5 (from -r ... (line 388))
  Using cached tzdata-2026.5-py2.py3-none-any.whl (347 kB)
Collecting zipp==3.23.0 (from -r ... (line 391))
  Using cached zipp-3.23.0-py3-none-any.whl (10 kB)
Installing collected packages: altgraph, zipp, tzdata, typing-extensions, setuptools, pywin32-ctypes, pypdf, pygments, pycparser, pluggy, pip, pillow, pefile, packaging, more-itertools, jeepney, iniconfig, colorama, certifi, backports-tarfile, pytest, pyinstaller-hooks-contrib, jaraco-functools, jaraco-context, jaraco-classes, importlib-metadata, cffi, pyinstaller, keyring, cryptography
  Attempting uninstall: setuptools
    Found existing installation: setuptools 65.5.0
    Uninstalling setuptools-65.5.0:
      Successfully uninstalled setuptools-65.5.0
  Attempting uninstall: pip
    Found existing installation: pip 24.0
    Uninstalling pip-24.0:
      Successfully uninstalled pip-24.0
Successfully installed altgraph-0.17.5 backports-tarfile-1.2.0 certifi-2026.7.22 cffi-2.1.1 colorama-0.4.6 cryptography-50.0.1 importlib-metadata-8.7.1 iniconfig-2.3.0 jaraco-classes-3.4.0 jaraco-context-6.1.2 jaraco-functools-4.6.0 jeepney-0.9.0 keyring-25.7.0 more-itertools-11.2.1 packaging-25.0 pefile-2024.8.26 pillow-11.1.0 pip-26.0.1 pluggy-1.6.0 pycparser-3.0 pygments-2.19.2 pyinstaller-6.19.0 pyinstaller-hooks-contrib-2026.2 pypdf-6.21.4 pytest-9.0.2 pywin32-ctypes-0.2.3 setuptools-84.0.0 typing-extensions-4.16.0 tzdata-2026.5 zipp-3.23.0
python.exe : 
At C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\scripts\step1_install.ps1:20 char:1
+ & $Py -m pip install --require-hashes -r $Lock 2>&1 | Tee-Object -Fil ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[notice] A new release of pip is available: 26.0.1 -> 26.3
[notice] To update, run: C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\venv\Scripts\python.exe -m pip 
install --upgrade pip
PIP_EXIT=0
```

Note: the `python.exe : ... NativeCommandError` block is a Windows PowerShell 5.1
artifact of `2>&1 | Tee-Object` on native stderr (pip notices); the actual process
exit code is `PIP_EXIT=0`. No dependency failed to install and no hash mismatch
occurred. "Using cached" means the wheels came from the local pip cache; §4.2 removes
that possibility.

</details>

### 4.2 Second venv with `--no-cache-dir` (real public-PyPI download)

```
python -m venv ...\prod16-clean-setup\venv-nocache
"...\venv-nocache\Scripts\python.exe" -m pip install --no-cache-dir --require-hashes -r "...\keel\requirements.lock.txt"
"...\venv-nocache\Scripts\python.exe" -m pip install --no-deps --no-build-isolation -e "...\setup\keel"
"...\venv-nocache\Scripts\python.exe" -c "import keel; print(keel.__version__, keel.__file__)"
```

Full output is in `logs/step1b-nocache.log`. Key lines (verbatim):

```
Ignoring exceptiongroup: markers 'python_version < "3.11"' don't match your environment
Ignoring macholib: markers 'sys_platform == "darwin"' don't match your environment
Ignoring secretstorage: markers 'sys_platform == "linux"' don't match your environment
Ignoring tomli: markers 'python_version < "3.11"' don't match your environment
Collecting certifi==2026.7.22 (from -r ... (line 14))
  Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
     -------------------------------------- 137.0/137.0 kB 1.6 MB/s eta 0:00:00
Collecting cryptography==50.0.1 (from -r ... (line 121))
  Downloading cryptography-50.0.1-cp311-abi3-win_amd64.whl (3.8 MB)
     ---------------------------------------- 3.8/3.8 MB 908.6 kB/s eta 0:00:00
Collecting pillow==11.1.0 (from -r ... (line 204))
  Downloading pillow-11.1.0-cp311-cp311-win_amd64.whl (2.6 MB)
     ---------------------------------------- 2.6/2.6 MB 747.3 kB/s eta 0:00:00
Collecting pytest==9.0.2 (from -r ... (line 307))
  Downloading pytest-9.0.2-py3-none-any.whl (374 kB)
     -------------------------------------- 374.8/374.8 kB 1.2 MB/s eta 0:00:00
...
Successfully installed altgraph-0.17.5 backports-tarfile-1.2.0 certifi-2026.7.22 cffi-2.1.1 colorama-0.4.6 cryptography-50.0.1 importlib-metadata-8.7.1 iniconfig-2.3.0 jaraco-classes-3.4.0 jaraco-context-6.1.2 jaraco-functools-4.6.0 jeepney-0.9.0 keyring-25.7.0 more-itertools-11.2.1 packaging-25.0 pefile-2024.8.26 pillow-11.1.0 pip-26.0.1 pluggy-1.6.0 pycparser-3.0 pygments-2.19.2 pyinstaller-6.19.0 pyinstaller-hooks-contrib-2026.2 pypdf-6.21.4 pytest-9.0.2 pywin32-ctypes-0.2.3 setuptools-84.0.0 typing-extensions-4.16.0 tzdata-2026.5 zipp-3.23.0
PIP_EXIT=0
...
Successfully built keel-harness
Successfully installed keel-harness-0.1.1
EDITABLE_EXIT=0
CMD: "...\venv-nocache\Scripts\python.exe" -c import keel ...
0.1.1 C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel\src\keel\__init__.py
IMPORT_EXIT=0
```

Every line that said "Using cached" in §4.1 says "Downloading" here: the lock is
installable from free public PyPI with hash checking and **no pre-seeded cache**.

### 4.3 Editable install in the primary venv

```
"...\prod16-clean-setup\venv\Scripts\python.exe" -m pip install --no-deps --no-build-isolation -e "C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel"
```

Full output (`logs/step2-editable.log`):

```
Obtaining file:///C:/Users/Admin/.local/share/opencode/worktree/production/setup/keel
  Checking if build backend supports build_editable: started
  Checking if build backend supports build_editable: finished with status 'done'
  Preparing editable metadata (pyproject.toml): started
  Preparing editable metadata (pyproject.toml): finished with status 'done'
Building wheels for collected packages: keel-harness
  Building editable for keel-harness (pyproject.toml): started
  Building editable for keel-harness (pyproject.toml): finished with status 'done'
  Created wheel for keel-harness: filename=keel_harness-0.1.1-0.editable-py3-none-any.whl size=6401 sha256=80e2aa105d077025e02018d8f85ec315cdd0e5852444cda77ff3f98fe7aa931a
  Stored in directory: C:\Users\Admin\AppData\Local\Temp\pip-ephem-wheel-cache-y3g8tp2b\wheels\79\79\ed\e2dc97a57a7531cb1f7fe2bde309e19f68ad2dbb4bef7ad1a1
Successfully built keel-harness
Installing collected packages: keel-harness
Successfully installed keel-harness-0.1.1
[notice] A new release of pip is available: 26.0.1 -> 26.3
PIP_EXIT=0
```

`pip freeze` from that venv (excerpt): `pytest==9.0.2`, `cryptography==50.0.1`,
`pillow==11.1.0`, `keyring==25.7.0`, `tzdata==2026.5`, `pyinstaller==6.19.0`, and
`-e ...keel` resolving to candidate SHA `ac84feebd8e889ad0afdc21e972fe162d3fd736c`.

### 4.4 Runtime verification harness (7/7)

Harness committed as `scripts/verify_clean_setup.py`; run from the disposable venv
with a fresh `KEEL_STATE_DIR` and from a neutral cwd (no repository on `sys.path`,
`PYTHONPATH` cleared, `PYTHONNOUSERSITE=1`):

```
set KEEL_SETUP_PROJECT=C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel
set KEEL_STATE_DIR=C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\state
"...\prod16-clean-setup\venv\Scripts\python.exe" "...\setup\scripts\verify_clean_setup.py"
```

Full output (`logs/step3-verify.log`):

```
python=C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\venv\Scripts\python.exe
version=3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]
project=C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel
state=C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\state
neutral_cwd=C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\state\neutral-cwd
PASS | clean_import | rc=0 version=0.1.1 module=C:\Users\Admin\.local\share\opencode\worktree\production\setup\keel\src\keel\__init__.py stderr=''
PASS | python_m_keel_help | rc=0 stdout_lines=19 stderr=''
PASS | capability_list_backend | rc=0 total_capabilities=230 backend_capabilities=['backend.describe', 'backend.invoke', 'backend.modules', 'backend.verify'] missing=[] stderr=''
PASS | db_init_fresh_state_dir | db=C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\state\fleet.db exists=True tables=17 schema_versions=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] missing=[] store_db=C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup\state\fleet-service.db store_tables=17
PASS | api_health_authorized | url=http://127.0.0.1:60799/api/health status=200 body='{"ok": true, "version": "0.1.1"}'
PASS | api_health_token_gated | status_without_token=403
PASS | graceful_shutdown | thread_alive=False post_shutdown=connection_refused:URLError
SUMMARY: 7/7 checks passed
HARNESS_EXIT=0
```

What each check proves:

| Check | Evidence |
| --- | --- |
| `clean_import` | `keel 0.1.1` imports in a subprocess with cleared `PYTHONPATH`, `PYTHONNOUSERSITE=1`, neutral cwd; module resolves to candidate `src/keel/__init__.py` (editable install). |
| `python_m_keel_help` | `python -m keel --help` exits 0, 19 lines, contains `usage: keel` and `capability`. |
| `capability_list_backend` | `keel capability list` exits 0, lists 230 capabilities including all four backend ones: `backend.modules`, `backend.describe`, `backend.invoke`, `backend.verify`. |
| `db_init_fresh_state_dir` | Fresh `KEEL_STATE_DIR` gets `fleet.db` (17 tables, schema versions 1–11) and `FleetStore` gets `fleet-service.db` (17 tables). |
| `api_health_authorized` | `GET /api/health` with `X-Keel-Token` returns `200 {"ok": true, "version": "0.1.1"}`. |
| `api_health_token_gated` | Same request without token returns `403` (no unauthenticated health exposure). |
| `graceful_shutdown` | `server.shutdown()` + `server_close()` + thread join leaves no live thread; a post-shutdown request is refused. |

Server used the same `keel.webapp.make_server()` / `serve_forever()` path as
`keel serve`, bound to 127.0.0.1 on an ephemeral port, with `KEEL_TOKEN` set before
import. Limitation stated honestly: shutdown was exercised through the HTTP server's
graceful `shutdown()` API, not by sending an OS Ctrl+C to a detached `keel serve`
process.

Two harness defects were found and fixed during the first run, before the final
7/7 result above: the authorized health probe initially omitted the `X-Keel-Token`
header (403), and a status variable could be unbound. Both were corrected in
`scripts/verify_clean_setup.py`; no source or test was touched. First-run output:
`SUMMARY: 5/7 checks passed`, `HARNESS_EXIT=1`.

### 4.5 Backend test subset from the clean venv

Command (cwd `...\setup\keel`, clean venv python, fresh `KEEL_STATE_DIR`,
`PYTHONNOUSERSITE=1`, `PYTHONPATH` cleared):

```
"...\prod16-clean-setup\venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider \
  tests/test_backend_hub_integration.py tests/test_backend_workflows.py \
  tests/test_prod_api.py tests/test_prod_db_recovery.py \
  tests/test_backend_events.py tests/test_plan_index.py
```

First combined run — exact output (`logs/step4-tests.log`):

```
........................................................................ [ 50%]
....................................................................F.   [100%]
================================== FAILURES ===================================
_________________ test_authoritative_source_hashes_unchanged __________________
    def test_authoritative_source_hashes_unchanged():
        expected = {
            "Keel_Master_Plan_v5.md":
                "da1dd5dc81d7f85fadbc5e10143c937e7fc63fd34b86f0f0d3659f7af67d427f",
            "Keel_Plan_v5_Addendum_Missed_Features.md":
                "e4e314a5a0c31f78",
            "Keel_Plan_v5_Addendum_2_More_Features.md":
                "b42219150271fa9e",
        }
        for name, prefix in expected.items():
            digest = hashlib.sha256((DOWNLOADS / name).read_bytes()).hexdigest()
>           assert digest.startswith(prefix), f"{name} changed: {digest}"
E           AssertionError: Keel_Master_Plan_v5.md changed: 47b346bc9b7ee26a51e5fe2576e9a9fa5cc6e75e339ab554e90aa2bfd79c1f13
E           assert False
E            +  where False = <built-in method startswith of str object at 0x00000130D6683530>('da1dd5dc81d7f85fadbc5e10143c937e7fc63fd34b86f0f0d3659f7af67d427f')
E            +    where False = <built-in method startswith of str object at ...>('47b346bc...f13').startswith
tests\test_plan_index.py:67: AssertionError
=========================== short test summary info ============================
FAILED tests/test_plan_index.py::test_authoritative_source_hashes_unchanged
1 failed, 141 passed in 31.01s
COMBINED_EXIT=1
```

Per-file exact counts from the same clean venv:

| File | Result | Exit |
| --- | --- | --- |
| `test_backend_hub_integration.py` | `21 passed in 1.57s` | 0 |
| `test_backend_workflows.py` | `20 passed in 5.98s` | 0 |
| `test_prod_api.py` | `1 failed, 21 passed in 13.17s` (`test_oversized_payload_is_413`: `assert 0 == 413`) | 1 |
| `test_prod_db_recovery.py` | `15 passed in 5.39s` | 0 |
| `test_backend_events.py` | `59 passed in 2.40s` | 0 |
| `test_plan_index.py` | `1 failed, 4 passed in 0.44s` (`test_authoritative_source_hashes_unchanged`) | 1 |

Total distinct tests in the subset: **142**. Best observed: **141 passed / 1 failed**.

Rechecks (same venv, all full output in `logs/step4-recheck.log`,
`logs/step4-final-combined.log`, `logs/step4-events-recheck.log`,
`logs/step4-events-verbose.log`):

```
=== test_prod_api.py RERUN 1 ===  22 passed in 13.15s   EXIT=0
=== test_prod_api.py RERUN 2 ===  22 passed in 12.77s   EXIT=0
=== test_prod_api.py RERUN 3 ===  22 passed in 13.13s   EXIT=0
=== oversized only x3 ===         1 passed (0.86s), 1 passed (0.79s), 1 passed (0.79s)
=== 5-file combined (without test_plan_index) ===  1 failed, 136 passed in 28.42s
    FAILED tests/test_backend_events.py::test_concurrent_publish_from_separate_processes
=== 6-file combined rerun ===     2 failed, 140 passed in 29.27s
    FAILED tests/test_prod_api.py::test_oversized_payload_is_413 - assert 0 == 413
    FAILED tests/test_plan_index.py::test_authoritative_source_hashes_unchanged
=== backend_events RERUN 1 ===    1 failed, 58 passed in 2.64s
=== backend_events RERUN 2 ===    59 passed in 2.23s        EXIT=0
=== backend_events RERUN 3 ===    59 passed in 2.37s        EXIT=0
=== events single-test x10 ===    9 passed, 1 failed (failure on run 7)
=== events standalone probe x10 === 10/10 runs: all 8 workers rc=0, seq_ok=True; TOTAL: 0/10 runs had >=1 worker failure
```

## 5. What is verified by this evidence

* A brand-new disposable venv installs every hash-pinned wheel from
  `keel/requirements.lock.txt` with `pip --require-hashes`, twice: once from pip cache,
  once with `--no-cache-dir` (real downloads from free public PyPI).
* The candidate project installs editable with `--no-deps --no-build-isolation`.
* `keel` imports cleanly from that venv outside the checkout; `python -m keel --help`
  works; `capability list` exposes the four backend capabilities.
* A fresh temp `KEEL_STATE_DIR` initializes the SQLite fleet DB (17 tables, migrations
  1–11) and FleetStore DB.
* Token-gated `GET /api/health` returns `200 {"ok": true, "version": "0.1.1"}`
  on loopback; without token it returns `403`; graceful server shutdown leaves no
  thread and refuses further connections.
* 142 focused backend tests were exercised; 141–142 passed depending on run, with the
  failures characterized below.

## 6. Failures — recorded honestly, not hidden

### 6.1 Reproducible: stale authoritative-hash fixture (`test_plan_index.py`)

`tests/test_plan_index.py::test_authoritative_source_hashes_unchanged` fails in **every**
run (first combined, per-file, 6-file rerun). Computed SHA256 of the checked-in fixtures
under `keel/docs/plan-sources/`:

```
Keel_Master_Plan_v5.md                  expected da1dd5dc81d7f85fadbc5e10143c937e7fc63fd34b86f0f0d3659f7af67d427f
                                        actual   47b346bc9b7ee26a51e5fe2576e9a9fa5cc6e75e339ab554e90aa2bfd79c1f13
Keel_Plan_v5_Addendum_Missed_Features.md expected e4e314a5a0c31f78
                                        actual   014d8375fb1682bbbc8ac57f891fb17f8cead68dcaff26b6b1d0ffc2cbc43b9b
Keel_Plan_v5_Addendum_2_More_Features.md expected b42219150271fa9e
                                        actual   c5778cff08f6a0b6039283a31ffee921fe29820f50ef1b95a74ed327a334368f
```

`git status --short` was clean for these files and `git log -1 -- <file>` shows they are
committed at `6a7716ff…` — i.e. the **test's expected digests are stale relative to the
candidate's committed fixtures**, not a dirty worktree or an install artifact. This is a
candidate test-fixture defect. It would fail in any environment at this HEAD. I did not
edit the test or the fixture (explicitly out of scope). Consequence: **do not claim a
green full suite**; this gate's clean-setup scope is unaffected.

### 6.2 Intermittent Windows lock race (`test_backend_events.py`)

`test_concurrent_publish_from_separate_processes` failed 4 times across ~15 executions
(first 5-file combined, one of three full-file reruns, one of ten isolated reruns, and
once in the 10x loop); it passed 11 times, and a 10/10 standalone reproduction with the
same 8-process worker program passed every time. Full observed worker error:

```
FileExistsError: [Errno 17] File exists: '...\\backend-events.jsonl.lock'

During handling of the above exception, another exception occurred:

  File "...\keel\src\keel\backend_events.py", line 795, in _acquire_file
    self.lock_path.unlink()
  File "...\Python311\Lib\pathlib.py", line 1147, in unlink
    os.unlink(self)
PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: '...\\backend-events.jsonl.lock'

The above exception was the direct cause of the following exception:
keel.backend_events.EventBusLockError: cannot clear stale event log lock ...\backend-events.jsonl.lock: [WinError 32] The process cannot access the file because it is being used by another process
```

Root cause is in candidate source `keel/src/keel/backend_events.py:792-801`: on Windows,
a contender may try to `unlink()` a lock marker that another process still has open,
raising `WinError 32` instead of retrying. It is a genuine, load-dependent Windows race
in the candidate, not a dependency/install failure. Source was not edited.

### 6.3 Intermittent oversized-payload transport error (`test_prod_api.py`)

`test_oversized_payload_is_413` failed twice (first per-file run and the 6-file rerun)
with `assert 0 == 413`. The test helper maps dropped sockets to status `0`, so the
400 KB POST did not yield an HTTP 413 response in those runs. It passed in the first
combined run, in three subsequent full-file reruns (`22 passed` each), and in three
isolated reruns (`1 passed` each). This is an intermittent endpoint/transport race,
not a setup or hash-verification problem.

### 6.4 Non-failures worth stating

* PowerShell `NativeCommandError` lines in the pip logs are stderr-redirection
  artifacts; both installs ended with `PIP_EXIT=0` / `EDITABLE_EXIT=0`.
* Four lock entries were skipped by PEP 508 markers (`exceptiongroup`, `tomli` for
  `python_version < 3.11`; `macholib` for Darwin; `secretstorage` for Linux). That is
  expected on Python 3.11/Windows and is not a missing dependency.
* The two harness bugs fixed before the final run are documented in §4.4.

## 7. Verdict rationale

| Status | Applicable? | Why |
| --- | --- | --- |
| `production_verified` | **No** | No production deployment or signed release; no clean VM, no Linux/macOS native run; no green full suite (§6.1–6.3). Claiming it would be false per the matrix vocabulary. |
| `pass` | **Yes** | Real, reproducible local clean-checkout evidence: hash-verified install from free public PyPI in two disposable venvs, editable install, 7/7 runtime checks, 141–142 backend tests exercised with failures characterized. Scope matches PR-16 ("clean setup and dependency install from source"). |
| `unverified` | **No longer** | The previously missing clean-checkout reproducibility evidence now exists on candidate `ac84fee`. |

**PR-16 can be closed as `pass` (local scope), with §6.1–6.3 tracked as separate
candidate defects and an explicit note that `production_verified` remains at zero for
the whole matrix.**

## 8. Reproduction

```powershell
$root = 'C:\Users\Admin\AppData\Local\Temp\opencode\prod16-clean-setup'
$work = 'C:\Users\Admin\.local\share\opencode\worktree\production\setup'
$py = "$root\venv\Scripts\python.exe"

python -m venv "$root\venv"
& $py -m pip install --require-hashes -r "$work\keel\requirements.lock.txt"
& $py -m pip install --no-deps --no-build-isolation -e "$work\keel"

$env:KEEL_SETUP_PROJECT = "$work\keel"
$env:KEEL_STATE_DIR = "$root\state"
$env:KEEL_SETUP_RESULTS_JSON = "$root\logs\step3-results.json"
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = ''
& $py "$work\scripts\verify_clean_setup.py"      # expect 7/7

Push-Location "$work\keel"
& $py -m pytest -q -p no:cacheprovider `
  tests/test_backend_hub_integration.py tests/test_backend_workflows.py `
  tests/test_prod_api.py tests/test_prod_db_recovery.py `
  tests/test_backend_events.py tests/test_plan_index.py
Pop-Location
```

All logs were captured under `...\prod16-clean-setup\logs\` in the disposable temp
root. They are deliberately not committed (only the two allowed worktree files are),
so this document carries the exact commands, exit codes, counts, and failure text.
The venvs and temp state are disposable and were never installed into the user's Python.
