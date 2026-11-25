# STAB-PLATFORM-EVIDENCE — native platform & sandbox verification

Read-only audit on host `C:\Users\Admin\.local\share\opencode\worktree\stab\platform`
(branch `agent/stab-platform`, stabilization HEAD `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb`).
No source files were modified. All tests were executed against the **worktree** code by
exporting `PYTHONPATH=<worktree>\keel\src` — the host has an editable install whose `.pth`
would otherwise resolve `keel` to `C:\Users\Admin\Desktop\Claude clone\keel\src` (the main
clone). Skips and simulations are **not** counted as native verification.

## Verdict (first)

| Platform | Verdict | Basis |
| --- | --- | --- |
| **Windows (native, this host)** | **VERIFIED** | 31 passed / 6 skipped / 0 failed across real-process suites + own probes; all claimed boundaries exercised natively, non-elevated. |
| **Linux (native in WSL2 on this host)** | **VERIFIED** | 16/16 `test_sandbox_linux.py` passed natively on kernel 6.6.87.2 (Landlock ABI 3, seccomp) + 9 passed/1 helper-induced skip in `test_os_sandbox.py`. |
| **macOS** | **UNVERIFIED** | No Darwin host exists here. All 14 macOS tests are platform-gated skips on both available hosts. Requires native macOS runners (see §5). |

Fail-closed behavior: **VERIFIED for Windows and Linux**; macOS has one *documented,
disclosed* narrow fallback (global file reads on the macOS 26 SIGABRT host) but no
unrestricted launch fallback — see §4.

---

## 1. Host environment (exact)

Windows (native):
```
OS Name:        Microsoft Windows 11 Pro
OS Version:     10.0.26300 N/A Build 26300
Build Type:     Multiprocessor Free
BuildLabEx:     LENOVO JTCN60WW, 4/10/2025
sys.platform:   win32
Python:         3.11.9 (C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe)
pytest:         9.0.2 (plugins: anyio-4.15.1, hypothesis-6.152.9,
                platformdirs-4.12.4, xdist-3.8.0)
Integrity:      Mandatory Label\Medium  S-1-16-8192  (BUILTIN\Administrators is DENY-ONLY)
IsUserAnAdmin() = 0   -> non-elevated token
```
Linux availability probe (this is a real, usable Linux environment):
```
wsl --status : Default Distribution Ubuntu; Default Version 2
               WSL1 is not supported with your current machine configuration
wsl --list --verbose : * Ubuntu  Stopped  2   (started successfully on demand)
wsl -e sh -c 'uname -a':
Linux Elios 6.6.87.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun  5 18:30:46 UTC 2025 x86_64 GNU/Linux
/proc/version: Linux version 6.6.87.2-microsoft-standard-WSL2
               (root@439a258ad544) (gcc (GCC) 11.2.0, GNU ld (GNU Binutils) 2.37)
Python: 3.14.4 (/usr/bin/python3); pytest 9.0.2; uid=1000(elios), groups include sudo
Landlock: syscall 444 -> ABI 3 ; /proc/self/status contains "Seccomp: 0" (field present)
```
macOS availability: **none**. Host is `win32`; the only Linux environment is WSL2
(`linux`). There is no Darwin machine, VM, or remote macOS runner reachable from this
session.

Import-path guard used for every command below (prevents accidentally auditing the main clone):
```
Windows: $env:PYTHONPATH = "C:\Users\Admin\.local\share\opencode\worktree\stab\platform\keel\src"
WSL:     export PYTHONPATH=/mnt/c/Users/Admin/.local/share/opencode/worktree/stab/platform/keel/src
verified: keel.__file__ == C:\Users\Admin\.local\share\opencode\worktree\stab\platform\keel\src\keel\__init__.py
```

---

## 2. Windows — native adversarial verdict: VERIFIED

### 2.1 Command and result

```
cd "...\stab\platform\keel"
python -m pytest -v -ra tests/test_os_sandbox.py tests/test_sandbox_windows.py tests/test_win_network.py
```
```
platform win32 -- Python 3.11.9, pytest-9.0.2 -- ...\python.exe
rootdir: ...\stab\platform\keel   configfile: pyproject.toml
collected 37 items
... (all 37 individual PASS/SKIP lines captured; see summary below) ...
=========================== short test summary info ===========================
SKIPPED [4] tests\test_os_sandbox.py:38: BLOCKED: sandbox could not launch this
            executable on this host (exit=3221225781):
SKIPPED [1] tests\test_os_sandbox.py:85: network enforcement requires Linux
            Landlock/seccomp or macOS profile
SKIPPED [1] tests\test_sandbox_windows.py:281: Python interpreter cannot start
            under the restricted token on this host
            (exit=3221225506, stderr=''); OS boundary itself is proven by the
            cmd.exe tests above
======================= 31 passed, 6 skipped in 39.63s ========================
```

The 6 skips are disclosed, not hidden failures: 4 are `confined_or_blocked()` treating
the *Python interpreter* failing to start under the token/AppContainer as BLOCKED
(exit `0xC0000135`-class / DLL dependency issue documented in the module docstring),
1 is an intentional Linux/macOS-only network gate, and 1 is the same Python-under-token
launch limitation in `test_main_bootstrap_escape_is_contained`. None of them were counted
as verification. Every Windows assertion below passed with real child processes.

### 2.2 Claim-by-claim native evidence (all real processes)

| Claim | Native test(s) — result | What was actually observed |
| --- | --- | --- |
| Restricted primary token | `test_capabilities_honest_about_network_and_appcontainer`, `test_default_call_is_network_denied_or_fails_closed` — PASS | `CreateRestrictedToken(DISABLE_MAX_PRIVILEGE\|SANDBOX_INERT)`, Administrators S-1-5-32-544 deny-only, Everyone S-1-1-0 as restricted SID; live `capabilities()` reports `windows_restricted_token: true`. |
| Workspace ACL / filesystem containment | `test_workspace_file_access_succeeds`, `test_unrelated_host_file_read_denied`, `test_write_outside_workspace_denied`, `test_outside_read_not_bypassable_via_path_tricks`, `test_outside_file_read_denied_under_appcontainer` — PASS | workspace file readable; outside `OUTSIDE-TOP-SECRET` unreadable; outside write file not created; `type ..\`, nested `cmd.exe /c type` path tricks all denied. Live `windows_workspace_acl: true`. |
| Restricted handle inheritance | **own probe** (below) — PASS | Inheritable parent secret handle inherited by an ordinary child, **not** by the confined AppContainer child. |
| Job Object limits / no breakaway | `test_active_process_limit_and_no_breakaway_are_configured`, `test_cpu_limit_terminates_job_before_timeout`, `test_memory_limit_is_applied_without_breaking_normal_process` — PASS | Flags include KILL_ON_JOB_CLOSE, ACTIVE_PROCESS, PROCESS_TIME, JOB_TIME, PROCESS_MEMORY, JOB_MEMORY; breakaway flags absent; busy loop killed by CPU limit before wall timeout; 64 MB limit did not break `cmd.exe`. |
| Process-tree termination | `test_timeout_terminates_process_tree` — PASS | Heartbeat file stopped growing after timeout (descendant did not keep writing); `TerminateJobObject` + `KILL_ON_JOB_CLOSE` in `finally`. |
| Child inherits FS restrictions | `test_child_process_inherits_filesystem_restrictions` — PASS | `cmd.exe` → child `cmd.exe` denied outside read; allowed inside read/write succeeded. |
| Network restriction (non-elevated) | `test_loopback_connect_denied_while_control_succeeds`, `test_dns_resolution_denied_while_control_succeeds`, `test_socket_creation_allowed_but_traffic_blocked`, `test_child_inherits_the_network_denied_token`, `test_default_run_confined_applies_appcontainer_boundary` — PASS | Real TCP listener + PowerShell control connected (`LOCALHOST=OK`, DNS OK); confined child reported `LOCALHOST=FAIL`/`DNS=FAIL`, listener accepted no extra connections; `socket()` creation succeeded but traffic blocked; cmd.exe→PowerShell child also denied. |
| WFP per-process rules genuinely unavailable | `test_wfp_filter_add_is_denied_without_elevation` — PASS | `FwpmEngineOpen0` = 0, `FwpmFilterAdd0` = 5 (`ERROR_ACCESS_DENIED`) on a non-elevated token; live `wfp_filter_add_status()` = `(0, 5)`. |
| AppContainer profile/SID | `test_appcontainer_profile_yields_stable_derived_sid` — PASS | Stable derived SID `S-1-15-2-208410879-...-3916182861`, profile `Keel.Sandbox.NetworkDeny.v1`, zero capabilities. |
| Environment scrubbing | `test_secret_environment_is_scrubbed` — PASS | `KEEL_SANDBOX_SECRET_PROBE`, `API_TOKEN_LEAK` absent from confined `set` output. |
| No shell-string command surface | `test_no_string_command_parameter_in_run_entry_point` — PASS | `command=`/`cmd=` raise `TypeError`; argv-only. |
| `__main__` escape regression | `test_regression_main_bootstrap_escape` (pure, PASS); OS-level variant skipped per documented Python-under-token launch limit | Python-level containment verified; OS boundary covered by cmd.exe tests. |

Live capability probe (exact output captured):
```
=== sandbox_windows.capabilities() ===
{"appcontainer_profile":"Keel.Sandbox.NetworkDeny.v1",
 "filesystem_enforcement":true, "mechanism":"windows-appcontainer+workspace-acl+job-object",
 "network_enforcement":true, "os":"win32", "wfp_filter_add_error":5,
 "windows_appcontainer":true, "windows_job_object":true,
 "windows_restricted_handle_inheritance":true, "windows_restricted_token":true,
 "windows_workspace_acl":true, "limitations":[ ... WFP blocked (5), DACL caveat,
 "Job Objects do not filter network", "socket() creation allowed", ... ]}
=== win_network.wfp_filter_add_status() === (0, 5)
=== IsUserAnAdmin === 0
```

### 2.3 Own probe: restricted handle inheritance (decisive)

Script: `C:\Users\Admin\AppData\Local\Temp\opencode\stab_platform_probe.py`
(run with the same `PYTHONPATH`). It marks a parent file handle holding
`HANDLE-SECRET-DO-NOT-LEAK` inheritable via `SetHandleInformation`, then has PowerShell
read that handle value inside an ordinary child vs. a confined AppContainer child:
```
PROBE_PARENT_HANDLE_INHERITABLE=PASS (handle=788)
PROBE_CONTROL_OUTPUT='HANDLE_INHERITED\nPROBE_RAN'
PROBE_CONFINED_RC=0 OUT='HANDLE_NOT_INHERITED: MethodInvocationException\r\nPROBE_RAN' ERR=''
ALL_OWN_PROBES=PASS
```
The unconfined control read the secret; the confined child could not use the handle.
This confirms `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` (only stdout/stderr) really strips
other inheritable handles rather than merely being configured.

---

## 3. Linux — native verdict in WSL2: VERIFIED

```
wsl -e bash -lc 'export PYTHONPATH=/mnt/c/.../stab/platform/keel/src;
 cd /mnt/c/.../stab/platform/keel; python3 -m pytest -v -ra tests/test_sandbox_linux.py'
```
```
platform linux -- Python 3.14.4, pytest-9.0.2
collected 16 items
test_capabilities_report_real_preflight_enforcement PASSED
test_landlock_abi_query_is_real PASSED
test_bpf_program_uses_correct_load_and_return_actions PASSED
test_network_filter_forked_child_socket_denied_write_ok PASSED
test_authorized_workspace_read_and_write PASSED
test_unauthorized_host_file_read_denied PASSED
test_unauthorized_host_file_write_denied PASSED
test_path_traversal_and_symlink_escape_denied PASSED
test_tcp_udp_and_dns_denied PASSED
test_child_process_inherits_filesystem_and_network_restrictions PASSED
test_unauthorized_inherited_fd_is_closed PASSED
test_cpu_limit_kills_busy_loop PASSED
test_memory_limit_blocks_large_allocation PASSED
test_process_limit_is_applied_but_allows_normal_children PASSED
test_timeout_kills_whole_process_group PASSED
test_concurrent_confinement_is_isolated PASSED
============================== 16 passed in 18.80s ==============================
```
These are real forked/exec'd restricted children: Landlock filesystem confinement,
seccomp-BPF network syscall denial, inherited-fd closure, rlimits, and process-group
kill all exercised natively. Live capabilities (exact):
```
{"filesystem_enforcement":true, "linux_landlock":true, "linux_landlock_abi":3,
 "linux_network_denial":true, "linux_seccomp":true, "network_enforcement":true,
 "os":"linux", "preflight_evidence":"abi=3 fs_bits=0x7fff fs_denied=True net_denied=True",
 "limitations":["This is process-level OS isolation, not a complete VM boundary;
                 bwrap/unshare are not used by this backend"]}
```
Cross-platform suite in the same WSL environment:
```
python3 -m pytest -v -ra tests/test_os_sandbox.py
-> 9 passed, 1 skipped in 10.70s
   SKIPPED [1] test_network_denied_by_default: BLOCKED ... exit=1 (traceback)
```
The single skip is induced by `confined_or_blocked()` treating the denied socket run as
BLOCKED; it is **not** counted as verification. Network denial is independently verified
natively by `test_tcp_udp_and_dns_denied` (PASSED) and the seccomp forked-child test
(`SOCKET_PERMISSION_ERROR`, PASSED).

---

## 4. No permissive fallback — VERIFIED (Windows + Linux), macOS caveat

* Dispatch is authoritative and unconditional: `os_sandbox.run_confined()` routes to the
  per-platform backend and contains no unrestricted fallback
  (`keel/src/keel/os_sandbox.py:269-283`).
* Windows: `sandbox_windows.run_confined()` raises `SandboxUnavailable` when APIs are
  missing, `filesystem_enforcement` is false, or (default `allow_network=False`)
  `network_enforcement` is false (`sandbox_windows.py:689-704`). The launch is created
  SUSPENDED, assigned to the Job Object, then resumed (`805-808`); all failure paths run
  cleanup in `finally` (`825-852`).
* Linux: `sandbox_linux.run_confined()` raises `SandboxUnavailable` if Landlock or
  seccomp is unavailable, and on any launch failure (`sandbox_linux.py:589-600, 663-665`).
* Native fail-closed tests all passed:
  `test_fail_closed_when_token_boundary_unavailable`,
  `test_fail_closed_when_filesystem_enforcement_reported_false`,
  `test_fails_closed_when_appcontainer_is_unavailable` (marker file absent),
  `test_default_call_is_network_denied_or_fails_closed`.
* Own probe (top-level dispatch, exact output):
  ```
  PROBE_FAIL_CLOSED_TOPLEVEL=PASS (SandboxUnavailable: 'BLOCKED: BLOCKED: Windows network
                                   denial is NOT enforced on this host ...')
  PROBE_FALLBACK_MARKER_ABSENT=PASS
  ```
  Patching `network_enforcement=False` made `os_sandbox.run_confined()` raise
  `SandboxUnavailable` and no `must-not-run.txt` was created — no unrestricted launch.
* macOS caveat (documented, not a hidden permissive fallback): on the macOS 26 SIGABRT
  host the backend retries only that *exact* diagnosed abort with a broad-read profile
  (`sandbox_macos.py:350-365`); writes, network and rlimits stay confined and
  `read_isolation="BLOCKED"` is reported. Every other failure is fail-closed. The
  consequence is important: **on macOS 26+ host file contents remain readable, so macOS
  read confidentiality is not enforced and must not be claimed there.**

---

## 5. macOS — UNVERIFIED; SIGABRT investigation and version boundary

### 5.1 Availability (why UNVERIFIED)
```
Windows host: sys.platform == 'win32'  -> test_sandbox_macos.py => 14 skipped in 2.09s
WSL2 host:    sys.platform == 'linux'  -> test_sandbox_macos.py => 14 skipped in 20.23s
sandbox_macos.capabilities() on this host:
  available=False, read_isolation='UNAVAILABLE', sandbox_exec=False
```
All 14 skips are the module-level `pytest.mark.skipif(sys.platform != "darwin")`
gate. Zero macOS tests executed; skips are not counted.

### 5.2 Source/evidence findings on the macOS 26 `sandbox-exec` SIGABRT
* `keel/src/keel/sandbox_macos.py:17-26` documents the host regression: on the current
  `macos-latest` (macOS 26 arm64), Apple's `sandbox-exec` aborts with **SIGABRT, exit -6,
  empty stderr** for *any* path-filtered `file-read*` rule — even `(subpath "/usr")` —
  while unfiltered `(allow file-read*)` works. macOS 27 is independently reported
  (`coccinella-labs/harper#926`).
* `keel/src/keel/sandbox_macos.py:350-365`: the fallback is gated so that only this exact
  abort (restrictive probe fails, broad probe succeeds) may switch to global reads;
  otherwise `SandboxUnavailable`. `capabilities()` reports `read_isolation: "BLOCKED"`.
* `keel/docs/research/macos-sandbox-mechanism.md:169-194` (native runner evidence):
  runner image `macos-26-arm64` (image `20261117.0516.1`), framework Python
  `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3`. Decisive probe matrix:
  global `(allow file-read*)` = exit 0; `+ (deny network*)` = exit 0;
  `(allow file-read* (subpath "/usr"))` = **exit -6, stderr b''**;
  `file-read-data`/`prefix`/literal variants, two narrow rules and a merged 10-root rule
  = **all exit -6**; broad reads + filtered writes + `(deny network*)` + process/IPC
  rules = exit 0. Malformed profiles exit 65, so the abort is not a syntax error.
  Reproduced for macOS 27.0.1 in `coccinella-labs/harper#926`.
* `keel/src/keel/sandbox_macos.py:231-233` limitation text: "This backend works on
  **macOS 15** but is not guaranteed on future releases." Corroborated by
  `PROD-PLATFORM-EVIDENCE.md:140`, `keel/docs/FINAL-RELEASE-OPERATIONS.md:174`,
  `master-plan-v6-platform-compatibility.md:28`.

**Supported version boundary (from source + evidence):** full restrictive read isolation
is supported/verified on **macOS 15 and earlier**. On **macOS 26 (arm64 decisively) and
27 (reported)** the filtered-read path is **BLOCKED** by the SIGABRT regression: writes,
network and rlimits remain enforced, read isolation does not. `sandbox-exec(1)` is
deprecated by Apple; App Sandbox is the supported replacement; no Electron entitlement
is relied upon. Because no Darwin host exists here, none of this was re-run natively.

### 5.3 Required native runners to close the macOS gap
1. **macOS 15 arm64 and macOS 15 Intel (x64)** runners with Python 3.11 + pytest: run
   `test_sandbox_macos.py` and assert `read_isolation == "RESTRICTIVE"` and all 14 tests
   pass (this is the version boundary where full confinement is claimed).
2. **macOS 26 arm64** (and optionally 27) runner: reproduce the probe matrix from
   `macos-sandbox-mechanism.md §6`, assert the `-6 / b''` abort, assert
   `read_isolation == "BLOCKED"` and that the broad fallback still confines writes and
   network; build arm64 + x64 DMG/ZIP artifacts.
3. Native macOS install/sidecar (`TMPDIR` inside workspace) tests; no entitlement assumed.

---

## 6. Required native runners summary

| Platform | Runner | Status |
| --- | --- | --- |
| Windows | Windows 11 Pro build 26300, non-elevated medium IL, Python 3.11.9 — **this host** | VERIFIED |
| Linux | WSL2 Ubuntu, kernel 6.6.87.2-microsoft-standard-WSL2, Landlock ABI 3, Python 3.14.4 — **this host** | VERIFIED |
| macOS | macOS 15 arm64 + x64 (full profile); macOS 26/27 arm64 (SIGABRT/boundary + artifacts) | **UNVERIFIED — no Darwin host** |

## 7. Discrepancy flagged for follow-up

`master-plan-v6-sandbox-verification.md:38,48-52,86,106` still records the *old* state
("Windows network denial NOT enforced / AppContainer needs SeImpersonatePrivilege /
no firewall rule"). The current worktree source uses capability-less AppContainer via
`CreateProcessW` and the live probe here reports `network_enforcement: true`, WFP add
error 5, stable `S-1-15-2-…` SID, and all real-process network tests passing. That
document is stale relative to HEAD `f60b080` and should be reconciled by the owning
agent; it does not affect the runtime verdicts above.

Captured raw outputs (audit artifacts, outside the repo):
`C:\Users\Admin\AppData\Local\Temp\opencode\stab-win-tests.txt`,
`stab-win-capabilities.txt`, `stab-win-probes.txt`, `stab-wsl-linux-tests.txt`,
`stab-wsl-os-sandbox-tests.txt`, `stab-wsl-capabilities.txt`.
