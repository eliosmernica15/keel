# Production platform verification — sandbox evidence (read-only audit)

- **Branch / candidate:** `agent/prod-sandbox` @ `e6e7efc50d098aaf55b80c5b35e799c0c2e25a86`
  (`build(release): create production candidate with classified backend-only promotion from origin/main`)
- **Host:** Windows 11 Pro, build `10.0.26300`, AMD64; `os.name == 'nt'`, `sys.platform == 'win32'`; **non-elevated** token (`IsUserAnAdmin() == 0`).
- **Python:** host `3.11.9` (pytest `9.0.2`); WSL2 Ubuntu `Python 3.14.4` (pytest `9.0.2`). Package requires `python >= 3.11` (`keel/pyproject.toml:10`); CI pins `3.11`.
- **Method:** no implementation or test file was edited. The installed `keel` resolves to `C:\Users\Admin\Desktop\Claude clone\keel\src\keel`, so every command pins `PYTHONPATH` to the worktree `keel/src`. `git diff --no-index` of `sandbox_windows.py`, `os_sandbox.py`, `sandbox_linux.py`, `sandbox_macos.py`, `win_network.py` against that install returned **no differences**. Throwaway probe scripts live outside the repo under `%TEMP%\opencode\prod-probe\` and are not committed.
- **Counting rule:** skipped, mocked and statically-inspected tests are **never** counted as native verification. Only real processes launched on this host count.

---

## 1. Authoritative supported platform matrix

Sources: the code dispatch in `keel/src/keel/os_sandbox.py:269-283`, `master-plan-v6-platform-compatibility.md`, `master-plan-v6-win-network-evidence.md`, `ADDENDA-OPERATION-STATUS.md:14`, `keel/docs/research/macos-sandbox-mechanism.md`, and `.github/workflows/{python-tests,build-desktop,lifecycle}.yml`.

| Platform | Native backend in candidate code | Stated OS requirement | Python | CI declaration | Native verification here |
| --- | --- | --- | --- | --- | --- |
| Windows | Restricted primary token + workspace DACL + restricted handle inheritance + Job Object; **AppContainer (zero capabilities) for the default `allow_network=False` path** | No explicit minimum Windows version in code; verified on Windows 11 Pro `10.0.26300`; non-elevated tokens supported; AppContainer needs a per-user profile (created via `userenv!CreateAppContainerProfile`) | `>=3.11`, tested `3.11.9` | `windows-latest`, Python `3.11` (`python-tests.yml`); installer + lifecycle jobs (`build-desktop.yml`, `lifecycle.yml`) | **Yes — VERIFIED** (real `cmd.exe`/PowerShell children; see §2) |
| Linux | Landlock filesystem + seccomp-BPF network deny + `no_new_privs` + capability drop + rlimits + process-group kill | Kernel **≥ 5.13** with Landlock and seccomp enabled (`platform-compatibility.md:23`); ABI detected at runtime; `sandbox_linux.py` documents WSL2 6.6 handling | `>=3.11`, tested here `3.14.4` on WSL2 | `ubuntu-latest`, Python `3.11` (`python-tests.yml`); installer + lifecycle jobs | **Yes — VERIFIED on WSL2 kernel `6.6.87.2-microsoft-standard-WSL2`** (real forked/exec'd children; see §3). Not verified on a bare-metal distro runner or other kernel versions from this host. |
| macOS | Seatbelt via `/usr/bin/sandbox-exec`: `(deny default)`, workspace-only writes, `(deny network*)` by default, rlimits, process-group kill | `sandbox-exec` present; **deprecated by Apple**; read isolation **BLOCKED on macOS 26 arm64** (filtered `file-read*` aborts with empty-stderr SIGABRT); no Electron App Sandbox entitlement relied upon | `>=3.11`, CI `3.11` | `macos-latest` (arm64) pytest + installer; Intel `x64` dmg/zip artifacts; macOS lifecycle job | **No — UNVERIFIED / BLOCKED** (no Darwin host here; see §4) |

> **Doc discrepancy recorded, not hidden:** `master-plan-v6-platform-compatibility.md` (baseline `cc6240e`) and `master-plan-v6-architecture-map.md` still say Windows network denial is *not* enforced and only fails closed. That describes an older lineage. Candidate HEAD `e6e7efc` contains `win_network.py` and the AppContainer path in `sandbox_windows.py:36-47, 700-713, 731-795`; the tests at HEAD assert `network_enforcement is True` (`test_sandbox_windows.py:66`, `test_win_network.py:91`). Code + live probes supersede the stale prose. `ADDENDA-OPERATION-STATUS.md:14` and `master-plan-v6-win-network-evidence.md` agree with the code.

---

## 2. Windows — VERIFIED (native, real processes)

### 2.1 Required test files, exact command and result

```
$env:PYTHONPATH='C:\Users\Admin\.local\share\opencode\worktree\production\sandbox\keel\src'
python -m pytest -q -rs keel/tests/test_os_sandbox.py keel/tests/test_sandbox_windows.py keel/tests/test_win_network.py
```

**Result: `31 passed, 6 skipped in 89.90s`. Zero failures.** Output saved to `%TEMP%\prod-platform-native-tests.txt`.

The 6 skips are honest and are **not** counted as verification:

| Skip | Reason (exact) |
| --- | --- |
| `test_os_sandbox.py:38` ×4 | Python cannot launch under the AppContainer token on this host (`exit=3221225781` = `0xC0000135` STATUS_DLL_NOT_FOUND). The filesystem/network boundary is instead proven by `cmd.exe`/PowerShell tests. |
| `test_os_sandbox.py:85` | Hard platform gate: "network enforcement requires Linux Landlock/seccomp or macOS profile". Windows network denial is covered by `test_win_network.py`, which ran. |
| `test_sandbox_windows.py:281` | Python cannot start under the restricted token (`exit=3221225506` = `0xC0000022` STATUS_ACCESS_DENIED). |

### 2.2 Independently observed `capabilities()`

```json
{"os":"win32","windows_restricted_token":true,"windows_job_object":true,
 "windows_workspace_acl":true,"windows_appcontainer":true,
 "windows_restricted_handle_inheritance":true,"filesystem_enforcement":true,
 "network_enforcement":true,"wfp_filter_add_error":5,
 "appcontainer_profile":"Keel.Sandbox.NetworkDeny.v1",
 "mechanism":"windows-appcontainer+workspace-acl+job-object"}
```

`os_sandbox.capabilities()` (dispatcher) independently reports `network_enforcement=True` and `windows_appcontainer=True`. `FwpmFilterAdd0` returns live `ERROR_ACCESS_DENIED (5)` from the non-elevated token, as claimed.

### 2.3 Own adversarial probes (real child processes)

Script: `%TEMP%\opencode\prod-probe\prod_platform_probes.py`; output: `...\prod-probe\out.txt`. All launches used candidate code.

| Probe | Result |
| --- | --- |
| FS read inside workspace | **PASS** — `WORKSPACE-OK` emitted under AppContainer mechanism |
| FS read outside workspace | **PASS (denied)** — `ok=False`, exit 1, secret absent |
| FS write outside workspace | **PASS (denied)** — target file not created |
| `..\` path traversal | **PASS (denied)** — secret absent |
| Junction escape (parent-created junction inside workspace → outside dir, `dir /b`) | **PASS (denied)** — `ok=False`, no secret |
| Hinted env secret (`KEEL_PROD_SECRET_PROBE`) | **PASS** — not inherited |
| Opaque env var (`OPAQUE_PROBE_VAR`) | **LIMITATION** — inherited (heuristic name scrubbing only) |
| Restricted-token path (`allow_network=True`): outside read/write, inside read | **PASS** on all three; `mechanism=windows-restricted-token+workspace-acl+job-object` |
| Job Object timeout + tree kill (heartbeat child) | **PASS** — `timed_out=True`, heartbeat grew to 7,546 B then stayed at 7,546 B after 1.5 s |
| Job Object CPU limit | **PASS** — no wall-clock timeout, child killed by job (`exit=3221225540`) |
| Handle list positive evidence | **PASS** — stdout/stderr handles inherited via `PROC_THREAD_ATTRIBUTE_HANDLE_LIST`; negative inheritance of arbitrary parent handles is code-verified (`sandbox_windows.py:563-596, 759-770`) but not directly observable with the available `cmd.exe`/PowerShell payloads |
| Network control (unconfined PowerShell → parent TCP listener) | **PASS** — `LOCALHOST=OK`, listener accepted 1 |
| AppContainer loopback connect | **PASS (denied)** — `LOCALHOST=FAIL`, listener accepted **0** |
| `socket()` creation vs traffic | **PASS** — `SOCKET_CREATE=OK`, `LOCALHOST=FAIL`, accepted 0 (AppContainer blocks traffic, not Winsock) |
| Fail-closed: force `network_enforcement=False` | **PASS** — `SandboxUnavailable`, no marker file created |
| Fail-closed: force APIs unavailable | **PASS** — `SandboxUnavailable`, no marker file created |

Verified Windows mechanisms: token/ACL filesystem confinement, restricted handle inheritance configuration, Job Object CPU/memory/active-process limits, suspended start + `KILL_ON_JOB_CLOSE` tree termination, non-elevated AppContainer network denial inherited by descendants, and fail-closed behaviour.

Known Windows limits (honest, not claimed): WFP per-process BLOCK filters need elevation and were never applied (`ERROR_ACCESS_DENIED 5`); `socket()` API still succeeds; filesystem denial is DACL-based (paths granting Everyone remain readable); the workspace DACL is temporarily widened to the AppContainer/Everyone SID during a run and restored afterwards; env scrubbing is name-heuristic and only strict when `env is None`; Python payloads cannot launch under either Windows token on this host; installer clean-VM lifecycle was not re-run here.

**Verdict: VERIFIED (native, this host) for the sandbox enforcement claims above. Not a VM boundary.**

---

## 3. Linux — VERIFIED natively on WSL2 for the integrated backend; conformance suite not green

A real Linux kernel is available on this host through **WSL2 Ubuntu** (`6.6.87.2-microsoft-standard-WSL2`). Candidate `keel/` was copied byte-for-byte into WSL's ext4 home (`~/prod-sandbox/keel`) and imported via `PYTHONPATH=src`; no source file was modified.

Kernel capabilities observed: `Landlock ABI = 3`, seccomp filter installation works, and the backend's own forked-child pre-flight reports `abi=3 fs_bits=0x7fff fs_denied=True net_denied=True`. (`/proc/self/status` shows `Seccomp: 0` for the *unconfined* parent; the integrated filter nevertheless installs and denies `socket()` with `EPERM` in a real child.)

### 3.1 Required test command and result (native Linux kernel)

```
wsl -e bash /mnt/c/Users/Admin/AppData/Local/Temp/opencode/prod-probe/wsl_tests.sh
# inside WSL: cd ~/prod-sandbox/keel && PYTHONPATH=src python3 -m pytest -q -rs \
#   tests/test_sandbox_linux.py tests/sandbox_conformance.py tests/test_os_sandbox.py \
#   tests/test_sandbox_multipath.py tests/test_sandbox_isolation.py \
#   tests/test_sandbox_hardened.py tests/test_sandbox_exec.py
```

**Result: `4 failed, 67 passed, 2 skipped in 63.67s`.** All 16 native `test_sandbox_linux.py` tests passed, including:

`test_capabilities_report_real_preflight_enforcement`, `test_landlock_abi_query_is_real`, `test_bpf_program_uses_correct_load_and_return_actions`, `test_network_filter_forked_child_socket_denied_write_ok`, `test_authorized_workspace_read_and_write`, `test_unauthorized_host_file_read_denied`, `test_unauthorized_host_file_write_denied`, `test_path_traversal_and_symlink_escape_denied`, `test_tcp_udp_and_dns_denied`, `test_child_process_inherits_filesystem_and_network_restrictions`, `test_unauthorized_inherited_fd_is_closed`, `test_cpu_limit_kills_busy_loop`, `test_memory_limit_blocks_large_allocation`, `test_process_limit_is_applied_but_allows_normal_children`, `test_timeout_kills_whole_process_group`, `test_concurrent_confinement_is_isolated`.

### 3.2 The four conformance failures — classified, not hidden

| Test | Observed | Assessment |
| --- | --- | --- |
| `sandbox_conformance.py::test_unauthorized_process_execution` | `BREACH:EXEC` — confined child executed `sys.executable` outside the workspace | **Test-contract mismatch, with a real scope limit.** `sandbox_linux.py:614-631` intentionally adds read/exec rules for interpreter directories; on this host `sys.executable` is `/usr/bin/python3` (a standard system dir). My own probe with a non-system victim (`/tmp/.../outside/victim.sh`) returned `EXEC_DENIED PermissionError 13` — that boundary holds. The conformance test classifies *any* outside executable as unauthorized, which contradicts the documented design. |
| `sandbox_conformance.py::test_concurrent_execution` | `markers=['READY']`, `files_ok=False` | **Test-contract mismatch.** The test writes markers to `ws/c{i}.txt` while confining each worker to `ws/sub{i}` — i.e. outside the declared workspace. My own probe with markers inside each declared workspace produced 4/4 successes (`cw0..cw3`). |
| `sandbox_conformance.py::test_process_exhaustion` | `BREACH:PROC spawned 12` | **Test-contract mismatch / documented limit.** `sandbox_linux.py:412-414` deliberately sets `RLIMIT_NPROC=(256,256)` (comment: a small value breaks ordinary shells on busy runners). Spawning 12 is within the configured limit; my probe read back `(256, 256)`. The test assumes a limit below 8. |
| `sandbox_conformance.py::test_seccomp_filter_denies_socket_allows_write` | `FILTER_SETUP_ERROR:SandboxUnavailable:seccomp filter install failed`, exit 4 | **Real fail-closed defect in the LEGACY inline path.** The test calls `keel.os_sandbox._seccomp_deny_network`, which is *not* the integrated Linux backend (`os_sandbox.run_confined` delegates to `sandbox_linux` at line 275). It raises rather than running unrestricted, but the repo's own conformance suite is red on this kernel. The integrated `sandbox_linux` filter works: my confined child got `SOCKET_DENIED 1` (EPERM) while an unconfined control created a socket successfully. |

The 2 skips: a conformance case where a secret env var was readable (env scrubbing is explicitly the policy layer's responsibility per `test_os_sandbox.py:101-103`, not an OS-boundary escape), and `test_os_sandbox.py:85`, whose helper misclassifies a successful socket denial as "could not launch this executable" (false skip — network denial is actually proven by `test_sandbox_linux.py::test_tcp_udp_and_dns_denied` and my own probe).

### 3.3 Own native Linux probes

Script: `%TEMP%\opencode\prod-probe\linux_probes.py` (+ `linux_recheck.py`); invoked via `wsl_linux_probes.sh` / `wsl_recheck.sh`. **16 checks, all passing after correcting two probe-side bugs** (an uncaught `OSError` that was itself the denial, and broken nested quoting in a grandchild payload). Key results:

- workspace read/write allowed; outside read `EACCES 13`; outside write blocked; `..` traversal `EACCES 13`.
- arbitrary outside executable denied (`PermissionError 13`); system `/usr/bin/python3` allowed **by design**.
- `socket()` denied with `errno 1` (EPERM) under the integrated filter; unconfined control succeeds; `allow_network=True` deliberately leaves the network open.
- CPU rlimit kills a busy loop (`exit=-9`); `RLIMIT_NPROC=(256,256)` confirmed as configured.
- timeout kills parent + grandchild process group (heartbeat 280 B at return, 280 B after 1.5 s).
- 4/4 concurrent confined runs succeed with markers inside their own workspaces.
- forcing `filesystem_enforcement=False` or `network_enforcement=False` raises `SandboxUnavailable`; no marker file created.

**Verdict: VERIFIED (native kernel, WSL2 `6.6.87.2`, Python 3.14.4) for the integrated Landlock+seccomp backend.** Qualification: the full repo conformance suite is **not green** on this kernel (4 failures above), one of which is a genuine fail-closed legacy-path defect. Bare-metal Linux, other kernel versions, and the CI `ubuntu-latest` / Python 3.11 runner were **not** executed from this host and remain **UNVERIFIED**.

---

## 4. macOS — UNVERIFIED / BLOCKED (no native host)

- `sys.platform` is `win32` on this host and `linux` inside WSL2; there is no Darwin runner, no `sandbox-exec`, and no macOS VM. `test_sandbox_macos.py` is gated by `pytestmark = pytest.mark.skipif(sys.platform != "darwin", ...)`, so all 14 tests skip here. **No mocked or skipped macOS result is counted as verification.**
- Implementation inspected: `keel/src/keel/sandbox_macos.py` builds an SBPL profile with `(deny default)`, workspace-only `file-write*`, `(deny network*)` by default, `(allow network*)` only on explicit opt-in, `process-exec`/`process-fork`, global `file-read-metadata`, and rlimits. It runs `/usr/bin/sandbox-exec` after a fail-closed `/usr/bin/true` pre-flight probe and rejects SBPL injection in paths (`sandbox_macos.py:73-77, 136-190, 202-272, 308-420`).
- Documented host regression (`keel/docs/research/macos-sandbox-mechanism.md:126-131, 181-194`): on macOS 26 arm64 any path-filtered `file-read*` rule aborts with SIGABRT and empty stderr. The backend falls back to `(allow file-read*)` and reports `read_isolation: "BLOCKED"`; host file **contents** are then readable. Writes and network remain confined. `sandbox-exec` is deprecated by Apple.
- CI declares `macos-latest` (arm64) pytest and installer jobs (`python-tests.yml`, `build-desktop.yml`, `lifecycle.yml`) and Intel `x64` dmg/zip artifacts (`test_platform_targets.py`), but no CI run results were retrievable from this host; those are **external, unverified claims**.

### Exact tests that must run on a native macOS runner (arm64 **and** Intel)

Command: `python -m pytest -q -rs keel/tests/test_sandbox_macos.py` (Python 3.11, real `sandbox-exec`).

1. `test_capabilities_are_honest`
2. `test_build_profile_is_restrictive`
3. `test_profile_rejects_injection_in_workspace_path`
4. `test_python_launches_inside_profile`
5. `test_workspace_read_write_allowed`
6. `test_unrelated_host_file_read_denied` (expected `BLOCKED`/skip on macOS 26 — read isolation cannot be proven)
7. `test_unauthorized_write_denied`
8. `test_network_denied_by_default`
9. `test_child_processes_inherit_write_and_network_restrictions`
10. `test_timeout_terminates_child_process_group`
11. `test_cpu_rlimit_terminates_runaway`
12. `test_memory_ceiling_is_reported_and_applied`
13. `test_scratch_files_land_inside_workspace`
14. `test_launch_failure_is_reported_not_passed`

Also required on native macOS: `keel/tests/sandbox_conformance.py` (macOS cases) and the macOS install/upgrade/rollback lifecycle job. **Until these run on real macOS hardware, macOS is BLOCKED for production verification.**

---

## 5. Permissive fallback / fail-closed analysis

**Finding: no permissive fallback exists in the integrated paths.** A backend that cannot establish its boundary raises `SandboxUnavailable`; it never launches the child unrestricted.

- `os_sandbox.run_confined` (`os_sandbox.py:269-283`) dispatches only to `sandbox_windows`, `sandbox_linux` or `sandbox_macos`; unknown platforms raise `SandboxUnavailable` at line 338. The legacy inline path is unreachable for the three supported platforms.
- Windows: `sandbox_windows.py:689-704` raises when APIs are missing, filesystem enforcement is false, AppContainer is unavailable in the default mode; creation failures at lines 794-807 raise before resuming the child; `finally` (825-852) always terminates the job and restores the DACL. **Empirically confirmed by two probes** (network forced off; APIs forced off) — no marker file created in either case.
- Linux: `sandbox_linux.py:589-600` raises when ABI/filesystem/network enforcement is unavailable. **Empirically confirmed by two probes** — `SandboxUnavailable` raised, no marker file created.
- macOS: `sandbox_macos.py:325-355` raises off-Darwin, without `sandbox-exec`, or when the pre-flight profile cannot launch. Static only (no macOS host).
- The only deliberate relaxation is the caller opt-in `allow_network=True`, which is disclosed in `ConfinementResult.limitations` and verified here (`allow_network=True` leaves the network open on both Windows and Linux). `capability_registry.py` must not default that flag to `True`; no code change was made in this audit.

---

## 6. Verdict summary

| Platform | Native execution on this host | Sandbox claims verified | Verdict |
| --- | --- | --- | --- |
| **Windows** (11 Pro 10.0.26300, AMD64, Py 3.11.9, non-elevated) | Yes — real processes | FS/token/ACL, handle-list config, Job Object limits + tree kill, AppContainer network denial (incl. descendants), fail-closed | **PRODUCTION-VERIFIED (scoped)** — with the documented limits in §2 |
| **Linux** (WSL2 kernel 6.6.87.2, Py 3.14.4) | Yes — real forked/exec'd children | Integrated Landlock+seccomp FS/network denial, rlimits, tree kill, concurrency, fail-closed | **VERIFIED on this kernel for the integrated backend**; **not fully production-cleared** — conformance suite has 4 failures (3 contract mismatches + 1 legacy-path fail-closed defect); bare-metal/other kernels **UNVERIFIED** |
| **macOS** (arm64 / Intel, Seatbelt) | No | None | **BLOCKED / UNVERIFIED** — requires native macOS runners; read isolation additionally BLOCKED on macOS 26 |

No implementation or test file in the worktree was modified. Only this report is added. The probe scripts and raw outputs are outside the worktree under `%TEMP%\opencode\prod-probe\` and `%TEMP%\prod-platform-native-tests.txt`. No push was performed.
