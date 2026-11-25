# FINAL-PLATFORM-EVIDENCE — native platform verification (read-only audit)

Branch `agent/final-platform`, worktree `C:\Users\Admin\.local\share\opencode\worktree\final\platform`,
completion HEAD `35fb2b8` (`Merge pull request #17 from eliosmernica15/stabilization/post-promotion-production-2026-11-25`).
No source/test/frontend file was edited; only this evidence file was added. Temporary probe scripts and
logs live under `C:\Users\Admin\AppData\Local\Temp\opencode\final-platform\` and are not committed.
Skips, mocks and static inspection are never counted as native verification.

---

## 0. BLOCKERS (read first)

1. **GitHub Actions is currently unusable — billing.** Every recent workflow run, including all three
   `pytest` jobs, did not start. Exact annotation from `gh run view 45536422111` (push to `main`,
   2026-11-25T02:56:04Z, merge of PR #17): *"The job was not started because recent account payments
   have failed or your spending limit needs to be increased"* for `pytest (windows-latest)`,
   `pytest (ubuntu-latest)` and `pytest (macos-latest)`. The same annotation blocks
   `validate-versions` in `Build desktop installers` run `45536422157`. **No fresh CI verification of
   completion HEAD is possible until the owner fixes billing/the spending limit.** The macOS runner is
   therefore *defined and historically used* but *currently unavailable*.
2. **There is no Darwin host on this machine.** The only native OS here is Windows; the only Linux is
   **WSL2** (virtualised, not bare metal). Windows/WSL results are **not** macOS verification.
3. **macOS 26 read isolation is BLOCKED by a real host defect.** On the `macos-26-arm64` runner, any
   path-filtered `file-read*` rule makes `sandbox-exec` abort with **exit -6 (SIGABRT), empty stderr**;
   the documented fallback grants global `file-read*`. Host file *contents* remain readable and
   `capabilities()["read_isolation"] == "BLOCKED"`. This must not be described as enforced read
   confidentiality on macOS 26+.
4. **No local release artifacts exist.** `keel/release/` and `keel/dist/` are absent in this worktree
   (gitignored build outputs), and there are no generated NSIS/macOS/Linux icon assets. The published
   v0.1.1 GitHub Release is an older artifact lineage (DMG/ZIP/AppImage, no PKG/RPM) and is **unsigned**
   (no `.sig` assets, no signature field); the repository has **0 Actions secrets**.

---

## 1. Verdict summary

| Platform | Verdict | Basis |
| --- | --- | --- |
| **Windows** (native, this host) | **VERIFIED (scoped)** | 31 passed / 6 skipped / 0 failed native sandbox tests; 49 passed / 1 skipped lifecycle tests; 7/7 + 8/8 clean-setup harnesses; 2/2 restart cycles + 2-process restart; own adversarial probes. Non-elevated token. |
| **Linux** (native kernel in **WSL2**, not bare metal) | **VERIFIED for the integrated backend on this kernel; conformance suite NOT green** | 67 passed / 1 skipped canonical platform set; Landlock ABI 3 + seccomp preflight `fs_denied=True net_denied=True`; own probes. Explicit `sandbox_conformance.py` run: **4 failed / 45 passed / 2 skipped** (3 test-contract mismatches + 1 genuine fail-closed legacy-path defect). Bare-metal Linux and other kernels **UNVERIFIED**. |
| **macOS** (Darwin) | **CI-VERIFIED historically on macOS 26 arm64; locally UNVERIFIED/BLOCKED** | No local Darwin host. PR #15's free `macos-latest` job ran on **macOS 26.7.2 / image macos-26-arm64**, Python 3.11.9 arm64: `1286 passed, 56 skipped`. `sandbox_macos.py`, `test_sandbox_macos.py` and the research doc are byte-identical to completion HEAD. **Not a fresh run at completion HEAD** (billing blocker), Intel runner not run, and read isolation is BLOCKED. |

Fail-closed behaviour: **verified natively on Windows and Linux** (no unrestricted fallback). macOS has
only the documented, disclosed narrow global-read fallback for the exact SIGABRT; all other failures are
fail-closed (static inspection only on this host).

---

## 2. Host / runner inventory (exact)

Windows (native):
```
Caption:           Microsoft Windows 11 Pro
Version / Build:   10.0.26300 / 26300
Registry UBR:      9711   (DisplayVersion 26H2; registry ProductName string says "Windows 10 Pro")
CPU:               AMD Ryzen 7 5700U with Radeon Graphics, 8 cores / 16 logical
RAM:               14,870,306,816 bytes (~13.85 GiB)
sys.platform:      win32 ; os.name = nt
Python:            3.11.9, C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe
pytest:            9.0.2 (xdist 3.8.0)
Integrity:         Mandatory Label\Medium  S-1-16-8192
IsUserAnAdmin():   0  (BUILTIN\Administrators is DENY-ONLY)
```
Linux (WSL2 — **virtualised, explicitly not bare metal**):
```
wsl --status:      Default Distribution Ubuntu; Default Version 2 (WSL1 unsupported)
wsl --list -v:     * Ubuntu  Stopped  2
uname -a:          Linux Elios 6.6.87.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun  5 18:30:46 UTC 2025 x86_64 GNU/Linux
/proc/version:     Linux version 6.6.87.2-microsoft-standard-WSL2 (root@439a258ad544) (gcc 11.2.0)
Ubuntu:            26.04 LTS (resolute) ; uid=1000(elios), sudo group
Python/pytest:     3.14.4 (/usr/bin/python3), pytest 9.0.2
Tools:             /usr/bin/unshare, /usr/bin/bwrap, /usr/bin/dpkg-deb ; no rpm/rpmbuild
Seccomp field:     Seccomp: 0 / Seccomp_filters: 0 in the *unconfined* parent
Landlock:          syscall 444 -> ABI 3
```
macOS: none locally. `sys.platform` is `win32` on Windows and `linux` in WSL2; `sandbox-exec` is absent
on both (`capabilities()["macos_sandbox_exec"] == False` in WSL). Free hosted runner: `macos-latest`
(actually `macos-26-arm64`), currently blocked by billing (§0.1).

---

## 3. Windows — VERIFIED (native, non-elevated)

Import guard used for every Windows command (host has an editable install pointing at a different clone):
```
$env:PYTHONPATH = "C:\Users\Admin\.local\share\opencode\worktree\final\platform\keel\src"
keel.__file__ == ...\worktree\final\platform\keel\src\keel\__init__.py
```

### 3.1 Native sandbox/process/ACL/Job Object/network tests
```
cd ...\worktree\final\platform\keel
python -m pytest -q -rs tests/test_os_sandbox.py tests/test_sandbox_windows.py tests/test_win_network.py
```
```
.sssss...................s...........                                    [100%]
SKIPPED [4] tests\test_os_sandbox.py:38: BLOCKED: sandbox could not launch this
            executable on this host (exit=3221225781):
SKIPPED [1] tests\test_os_sandbox.py:85: network enforcement requires Linux
            Landlock/seccomp or macOS profile
SKIPPED [1] tests\test_sandbox_windows.py:281: Python interpreter cannot start
            under the restricted token on this host (exit=3221225506, stderr='')
31 passed, 6 skipped in 30.01s
```
The 6 skips are disclosed, not counted: 4 + 1 are the documented inability of a **Python payload** to
start under this host's restricted token (the boundary itself is proven by `cmd.exe`/PowerShell
children); 1 is a hard Linux/macOS-only network gate (Windows network denial is covered by
`test_win_network.py`, which ran). Zero failures.

### 3.2 Clean install / startup / shutdown / restart
```
python -m pytest -q -rs tests/test_installer_smoke.py tests/test_process_shutdown.py \
  tests/test_start_health.py tests/test_updater.py tests/test_stab_lifecycle.py \
  tests/test_stab_install_recovery.py tests/test_platform_targets.py \
  tests/test_release_manager.py tests/test_version_sync.py
-> 49 passed, 1 skipped in 25.57s
   SKIPPED [1] SIGINT cannot be sent to a Windows console child in a new process group
```
A fresh venv was created at `%TEMP%\opencode\final-platform\venv` (`--system-site-packages`; wheel 0.48.0
installed from local pip cache), and **the worktree package installed editable with no dependencies and
no build isolation**. `pip` reported `Successfully installed keel-harness-0.1.1`; `keel.__file__`
resolved to the worktree. (`--system-site-packages` is disclosed honestly: the base interpreter's pinned
site-packages were reused instead of a fully network-isolated dependency install.)
```
$env:KEEL_SETUP_PROJECT = <worktree>
$env:KEEL_STATE_DIR     = <fresh temp state dir>
<venv>\Scripts\python.exe scripts\verify_clean_setup.py
-> clean_import PASS (version=0.1.1, worktree module)
   python_m_keel_help PASS (19 lines)
   capability_list_backend PASS (230 capabilities; backend.* all present)
   db_init_fresh_state_dir PASS (17 tables, schema versions 1..11, two DB files)
   api_health_authorized PASS (200, {"ok":true,"version":"0.1.1","ready":true,...})
   api_health_token_gated PASS (403 without token)
   graceful_shutdown PASS (thread stopped; post-shutdown connection_refused:URLError)
   SUMMARY: 7/7 checks passed

<venv>\Scripts\python.exe scripts\verify_stab_install.py
-> same six checks PASS + version_consistency_gate PASS
   (version=0.1.1 sources=7 distinct=['0.1.1'])
   SUMMARY: 8/8 checks passed
```
Restart probes (own scripts, real server lifecycles, version 0.1.1):
```
restart_probe.py            -> CYCLE 1 OK, CYCLE 2 OK ; RESTART_SUMMARY: 2/2 cycles passed
process_restart_probe.py init -> INIT: tables=17 marker_written=True
process_restart_probe.py restart -> RESTART: marker='keel-restart-marker' status=200
                                    version=0.1.1 thread_alive=False refused=True OK=True
```
Persisted state after the two-process restart: `fleet.db` (180,224 B), `fleet.db-wal`,
`fleet.db-shm`, `fleet.db-migrate.lock`, `restart-marker.txt`.

### 3.3 Own adversarial native probes (no mocks)
Script `%TEMP%\opencode\final-platform\win_probe.py` plus a corrected outside-write probe.
```
CAPABILITIES: {"appcontainer_profile":"Keel.Sandbox.NetworkDeny.v1",
 "filesystem_enforcement":true, "mechanism":"windows-appcontainer+workspace-acl+job-object",
 "network_enforcement":true, "os":"win32", "wfp_filter_add_error":5,
 "windows_appcontainer":true, "windows_job_object":true,
 "windows_restricted_handle_inheritance":true, "windows_restricted_token":true,
 "windows_workspace_acl":true, ...limitations...}
WFP_STATUS: (0, 5)        # FwpmEngineOpen0=0, FwpmFilterAdd0=ERROR_ACCESS_DENIED
APP_SID: S-1-15-2-208410879-1010705460-3932305904-2288491663-4286961640-2579492024-3916182861
inside workspace read:  ok=True  exit=0  stdout='INSIDE-OK'
outside host file read: ok=False exit=1  stderr='Access is denied.'
outside host file write: ok=False exit=1  marker_exists=False  stderr='Access is denied.'
```
Verified mechanisms: restricted token + workspace DACL (filesystem), restricted handle list
(configured; negative inheritance proven by the passing test suite), Job Object CPU/memory/
active-process limits with suspended start and `KILL_ON_JOB_CLOSE` tree kill, non-elevated zero-
capability AppContainer network denial inherited by descendants, and fail-closed behaviour.
Honest limits (not claimed): WFP per-process rules need elevation; `socket()` creation still succeeds
but traffic is denied; DACL-based filesystem denial (paths granting Everyone stay readable); Python
payloads cannot launch under either Windows token on this host; a *real* clean-VM installer lifecycle
needs CI.

**Verdict: VERIFIED (scoped) on Windows 11 Pro 10.0.26300.9711, non-elevated.**

---

## 4. Linux — VERIFIED on WSL2 kernel 6.6.87.2 for the integrated backend

Worktree `keel/` copied byte-for-byte to `~/final-platform/keel` in WSL ext4; every command pinned
`PYTHONPATH=$DEST/keel/src` and verified `keel.__file__ == /home/elios/final-platform/keel/src/keel/__init__.py`
(the host's editable install would otherwise shadow it).

Live capabilities (exact):
```
landlock_abi: 3
{'os':'linux','linux_landlock':True,'linux_seccomp':True,'linux_landlock_abi':3,
 'linux_network_denial':True,
 'preflight_evidence':'abi=3 fs_bits=0x7fff fs_denied=True net_denied=True',
 'filesystem_enforcement':True,'network_enforcement':True,
 'limitations':['This is process-level OS isolation, not a complete VM boundary;
                 bwrap/unshare are not used by this backend']}
```

### 4.1 Canonical platform tests (native kernel)
```
wsl -e bash .../wsl_more.sh
# inside WSL: python3 -m pytest -q -rs tests/test_sandbox_linux.py tests/test_os_sandbox.py \
#   tests/test_sandbox_multipath.py tests/test_sandbox_isolation.py tests/test_sandbox_hardened.py \
#   tests/test_sandbox_exec.py tests/test_native_isolation.py tests/test_process_shutdown.py \
#   tests/test_platform_targets.py tests/test_distribution.py tests/test_distribution_package.py \
#   tests/test_installer_smoke.py
..................s................................................. [100%]
SKIPPED [1] tests/test_os_sandbox.py:38: BLOCKED: sandbox could not launch this executable
            on this host (exit=1): Traceback ... import socket; s=socket.socket(); s.settim
67 passed, 1 skipped in 48.46s
```
A separate `test_native_isolation.py ... test_installer_smoke.py` batch: `20 passed in 5.28s`.
The single skip is helper-induced: `confined_or_blocked()` misclassifies a successful socket denial
as "could not launch". It is not counted; network denial is proven by the passing
`test_tcp_udp_and_dns_denied` and the own probe below. All 16 `test_sandbox_linux.py` tests pass
(Landlock FS denial, seccomp socket denial, inherited-fd closure, rlimits, tree kill, concurrency,
fail-closed).

### 4.2 Explicit conformance suite — NOT green (classified, not hidden)
```
python3 -m pytest -q -rs tests/test_sandbox_linux.py tests/sandbox_conformance.py tests/test_os_sandbox.py
-> 4 failed, 45 passed, 2 skipped in 43.33s
   conformance counts: {'PASS':19,'PARTIAL':1,'BLOCKED':1,'FAIL':4}
```
| Test | Observed | Classification |
| --- | --- | --- |
| `test_unauthorized_process_execution` | `BREACH:EXEC` — confined child executed `/usr/bin/python3` | Test-contract mismatch with a documented scope limit: `sandbox_linux.py` intentionally allows read/exec of interpreter directories, and `sys.executable` is `/usr/bin/python3`. Own probe with a non-system victim returned `PermissionError: [Errno 13]`, so that boundary holds. |
| `test_concurrent_execution` | `markers=['READY']`, `files_ok=False` | Test-contract mismatch: the test writes markers to `ws/c{i}.txt` while confining each worker to `ws/sub{i}` — outside the declared workspace. |
| `test_process_exhaustion` | `BREACH:PROC spawned 12` | Documented limit: `RLIMIT_NPROC=(256,256)` is deliberate (small values break shells on busy runners). Own probe read back `(256, 256)`; 12 is within the configured limit. |
| `test_seccomp_filter_denies_socket_allows_write` | `FILTER_SETUP_ERROR:SandboxUnavailable:seccomp filter install failed`, exit 4 | **Genuine fail-closed defect in the legacy inline path** `os_sandbox._seccomp_deny_network`, which is not the integrated `sandbox_linux` backend. It fails closed rather than running unrestricted; the integrated filter works (own probe: `SOCKET_DENIED:1` = EPERM). |

`sandbox_conformance.py` is not part of default pytest collection (filename does not start with
`test_`), so the canonical suite is green while this explicitly-requested research suite is red.

### 4.3 Own native Linux probes
```
PROBE_SYSTEM_PY_EXEC:       EXEC_OK                       (by design: interpreter roots allowed)
PROBE_OUTSIDE_VICTIM_EXEC:  PermissionError: [Errno 13]   (arbitrary outside executable denied)
OUTSIDE_READ:               PermissionError [Errno 13]; caught variant 'READ_DENIED:13'
SOCKET:                     ok=True exit=0 stdout='SOCKET_DENIED:1'   (EPERM, seccomp)
SOCKET_ALLOWED_OPTIN:       ok=True exit=0 stdout='SOCKET_OK'          (allow_network=True, disclosed)
PROBE_RLIMIT_NPROC:         (256, 256)
PROBE_LEGACY_FILTER:        FILTER_FAILCLOSED:SandboxUnavailable:seccomp filter install failed
```
**Verdict: VERIFIED for the integrated Landlock+seccomp backend on this WSL2 kernel; NOT production-
cleared for Linux generally.** Bare-metal distro, other kernel versions, and the CI `ubuntu-latest` /
Python 3.11 runner were not executed from this host.

---

## 5. macOS — CI-VERIFIED historically on macOS 26 arm64; locally UNVERIFIED/BLOCKED

### 5.1 Availability determination
- Local machine: no Darwin host, no macOS VM, no `sandbox-exec`; only `win32` and WSL2 `linux`.
- Free hosted runner: yes — the repo's `.github/workflows/python-tests.yml` matrix includes
  `macos-latest`, and `build-desktop.yml` / `lifecycle.yml` declare macOS jobs. **Currently blocked**
  by the billing annotation in §0.1; no new run can be started from this read-only audit.

### 5.2 PR #15 (`lead/macos-blocked-test`) — open
```
gh pr view 15 --repo eliosmernica15/keel --json ...
-> number=15, state=OPEN, base=main, head=lead/macos-blocked-test, author=eliosmernica15,
   title="Native macOS Seatbelt sandbox backend (BLOCKED read isolation)",
   body="Restrictive Seatbelt profile: write confinement, network denial, rlimits PASS.
         Host read isolation BLOCKED on macOS 26 with exact SIGABRT evidence;
         reported as evidence-bearing skip."
gh pr checks 15
-> pytest (macos-latest) pass 5m28s ; build-macos pass 3m2s ; 11 checks total
```
CI log (`gh run view 45091803272 --job 137422803438 --log`):
```
Operating System: macOS 26.7.2 (25G332) ; Image: macos-26-arm64 20261117.0516.1
Python 3.11.9, /Users/runner/hostedtoolcache/Python/3.11.9/arm64
command: python -m pytest -q
result: 1286 passed, 56 skipped in 304.91s (0:05:04)
```
`-q` was used without `-rs`, so per-test skip reasons are not in the log; the platform suite includes
`tests/test_sandbox_macos.py`, which is collected on Darwin. Code identity check:
```
git diff HEAD..lead/macos-blocked-test -- keel/src/keel/sandbox_macos.py \
    keel/tests/test_sandbox_macos.py keel/docs/research/macos-sandbox-mechanism.md
-> (empty)  # byte-identical to completion HEAD
git diff HEAD..lead/macos-blocked-test -- keel/src/keel/os_sandbox.py keel/tests/sandbox_conformance.py
-> os_sandbox.py | 103 +--- ; sandbox_conformance.py | 1079 --------  (PR branch is older)
```
So the macOS **backend, its 14 native tests and the research doc** in that CI run are exactly the code at
completion HEAD; the PR branch's shared dispatcher/conformance suite are older and were **not** the
completion HEAD versions.

### 5.3 Documented macOS 26 SIGABRT (from `keel/docs/research/macos-sandbox-mechanism.md` §6)
```
(allow file-read*) global                       -> exit 0
(allow file-read*) + (deny network*)            -> exit 0
(allow file-read* (subpath "/usr"))             -> exit -6 (SIGABRT), stderr b''
file-read-data / prefix / literal variants      -> all exit -6
two narrow file-read* rules                     -> exit -6
merged narrow rule with 10 canonical roots      -> exit -6
broad reads + filtered writes + deny network    -> exit 0
```
Independent report: macOS 27.0.1, `coccinella-labs/harper#926`. Malformed profiles instead print an
error and exit 65, so this is a host regression, not SBPL syntax. `sandbox-exec(1)` is deprecated by
Apple; no Electron App Sandbox entitlement is used. The 14 macOS tests are gated by
`pytestmark = pytest.mark.skipif(sys.platform != "darwin", ...)`. Local confirmation:
```
python -m pytest -q -rs tests/test_sandbox_macos.py
-> 14 skipped in 2.93s  (all: "native macOS Seatbelt sandbox tests (require sandbox-exec)")
```
**All 14 skip on this host and none were counted as verification.**

**Verdict: no local macOS verification. Historical CI evidence is genuine but partial: macOS 26 arm64
passed with identical backend/test files, read isolation is BLOCKED, Intel is unrun, and completion
HEAD has no green CI run because of billing.**

### 5.4 Required owner action for macOS (exact)
1. Fix GitHub Actions billing / spending limit so jobs start again (currently every job is skipped by
   the payment annotation).
2. At completion HEAD (or the release tag), dispatch and require green:
   - `python -m pytest -q -rs keel/tests/test_sandbox_macos.py keel/tests/sandbox_conformance.py`
     on **both** `macos-latest` (arm64) and a macOS Intel (`x64`) runner, Python 3.11;
   - `Build desktop installers` (PKG arm64 + x64) and `Upgrade and rollback lifecycle (Windows)`'s
     `macos-lifecycle` job, with the real `pkgutil --check-signature` status reported.
3. Explicitly accept or remediate the macOS 26+ read-isolation block: either document `read_isolation:
   BLOCKED` as an accepted production limitation (host file contents remain readable), or implement
   an App Sandbox entitlement/helper and re-verify. Do not claim file confidentiality on macOS 26+.
4. Decide the disposition of the still-open PR #15 (merge as evidence-bearing, or close as superseded
   by the code already present at completion HEAD).
5. Configure the free Ed25519 release-signing secrets (`KEEL_RELEASE_SIGNING_KEY`,
   `KEEL_RELEASE_SIGNING_PUBLIC_KEY`) if a signed release is required; no paid certificate was used or
   requested in this audit.

---

## 6. Distribution artifacts — version 0.1.1, checksums, manifest, signature state

### 6.1 Local worktree
```
Get-ChildItem keel\release, keel\dist  -> no such directories (both gitignored build outputs)
git ls-files | Select-String '^keel/(release|dist)/|\.exe$|\.pkg$|\.deb$|\.rpm$|SHA256SUMS'
-> only keel/site/download.json (no binary artifacts tracked)
python scripts/check_version_sync.py            -> OK - all sources agree on version 0.1.1 (tag v0.1.1)
python scripts/check_version_sync.py --tag v0.1.1 -> OK (same)
<venv harness> version_consistency_gate           -> version=0.1.1 sources=7 distinct=['0.1.1']
```
Tracked fallback `keel/site/download.json`: `version 0.1.1`, `tag v0.1.1`, `generated: fallback`,
`published_at/verified_at/base_url: null`; channels list native PKG/DEB/RPM with `size/sha256/url:
null`, `available: false`, `verified: false` everywhere. No false availability is advertised.

Release-manager checks on the empty tree (all fail closed, as expected before a build):
```
python -m keel.release check-packaging
-> FAIL: missing NSIS asset build/header.bmp / sidebar.bmp / icon.ico
   FAIL: missing macOS icon .../desktop-app/build/icon.icns
   FAIL: missing Linux icon directory .../desktop-app/build/icons
   packaging checks: 5 failure(s)
python -m keel.release integrity --dist dist --artifacts release
-> [FAIL] checksums / manifest / latest_yml / sidecar_version / dependency_inventory
   [OK] secret_scan ; [OK] signature_paths  -> integrity: 2/7 passed
python -m keel.release dry-run --dist dist --artifacts release --require-signed
-> ERROR: signing verification requires --public-key ...
   RELEASE SIGNING GATE FAILED - refusing to treat this release as signed
```
`desktop-app/node_modules` is absent, so a real electron-builder build was not attempted: it would
require network downloads and would dirty the read-only worktree. The tracked toolchain permits a build
in CI after `npm ci` + `generate_assets.py`; CI cannot currently run (billing).

### 6.2 Published GitHub Release v0.1.1 (read-only, `gh api`)
```
8 assets: download.json, Keel-Setup-0.1.1.exe, Keel-0.1.1-linux-amd64.deb,
          Keel-0.1.1-linux-x86_64.AppImage, Keel-0.1.1-macos-arm64.dmg,
          Keel-0.1.1-macos-arm64.zip, RELEASE-MANIFEST.json, RELEASE-SHA256SUMS.txt
published_at 2026-11-19T21:45:58Z; not draft, not prerelease
```
Manifest (`generated: release-pipeline`) lists 5 files. Cross-check of manifest SHA-256/bytes against
GitHub's asset digests: **5/5 sha256 match, 5/5 size match**. `RELEASE-SHA256SUMS.txt` contains only 2
lines (`.deb`, `.AppImage`) — incomplete relative to the 5-file manifest. **Signature state: unsigned** —
0 `.sig` assets, no signature field in the manifest, and `gh api .../actions/secrets` reports
`total_count=0`. Artifact names are the *old* lineage (DMG/ZIP/AppImage; no PKG and no RPM), so the
published set does not match the current tracked native-installer toolchain
(`Keel-0.1.1-macos-{arm64,x64}.pkg`, `Keel-0.1.1-linux-x86_64.rpm`).

---

## 7. Live download page (`https://keel-desktop.vercel.app/download`)

Read-only investigation only; no frontend file was modified, no deploy was performed.

Live HTTP probe of 18 routes (status/length and content markers):
```
/                    200 len=38045  :: download.json=1, "Download apps"=3   (footer link only)
/download            200 len=41749  :: "Download Keel"=5, "Not publicly available yet"=4,
                                       "Download for Windows"=1, "Get started"=3, "Download apps"=3
/downloads           200 len=24917  :: "Download Keel"=1, "Download for Windows"=1
/app                 200 len=55177  :: "Download Keel"=1  (nav/CTA link only)
/new /plugins /projects /artifacts /keel-in-chrome ... :: "Download apps" nav links only
/login /chrome-web-store /privacy /terms /eula /notices /roadmap /trademark /requirements :: no download content
```
Source cross-check in `keel/site`: only `download.html` includes `/ui/download.js` and
`/ui/download-clone.js`, whose comment states verified installer rows are rendered from
`/api/download-manifest` with fallback `/download.json`. `downloads.html` includes only
`/ui/downloads.js` (the "Apps and extensions" page); `app.html`/`plugins.html` contain plain `href="/download"`
links; `index.html` has a footer link to `/download.json`.

Rendered content of `/download`: heading **Download Keel**, Desktop/Mobile/extension cards, platform
rows for macOS/Windows/Windows arm64/Microsoft Store/Flutter/Slack, and FAQ. Every installer link is a
self-link to `/download` with `title="Not publicly available yet"`. `/downloads` shows one
`Download for Windows` card with `title="No verified installer published yet — see the download page for
details"` and text *"No verified Windows installer is published yet. The download page lists every
platform and its verification status."*

**Conclusion: full desktop download content exists only on the intended `/download` page.** Other pages
contain global-navigation "Download apps" links, a single CTA, or a pointer to `/download` — not the
download content itself.

Discrepancy recorded (not fixed): the **live** `/download.json` is stale relative to completion HEAD —
it still advertises the old DMG/ZIP/AppImage filenames while the tracked `keel/site/download.json`
lists PKG/DEB/RPM. Both mark all channels `available:false`, `verified:false` with no URLs, so no
downloadable installer is falsely advertised on either version. The live page also contains old
FAQ/section text about AppImage and Microsoft Store that is not in the current fallback manifest.

---

## 8. Git hygiene

`git status --short` in the worktree was empty before this file was added. This audit adds exactly one
file, `FINAL-PLATFORM-EVIDENCE.md`, on `agent/final-platform`. No push, no source edits, no paid signing,
no frontend modification.
