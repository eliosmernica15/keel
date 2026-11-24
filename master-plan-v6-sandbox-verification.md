# Master Plan v6 — Adversarial Sandbox Verification (Agent 08)

Independent red-team verification of the integrated native sandbox implementations.

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\completion\sandbox-redteam`
- Branch: `agent/sandbox-redteam`
- Baseline SHA: `20bf5c3` ("C11.1 private + C11.2 local compensating controls and live evidence")
- Host: Windows (`win32`), Python 3.11.9, pytest 9.0.2, `os.name == 'nt'`, non-elevated token
- Files attacked (read/executed only, **not modified**):
  `keel/src/keel/sandbox_windows.py`, `keel/src/keel/os_sandbox.py`,
  `keel/src/keel/sandbox_linux.py`, `keel/tests/test_sandbox_windows.py`,
  `keel/tests/test_os_sandbox.py`, `keel/tests/sandbox_conformance.py`

> Note on environment: the `keel` package installed on this machine resolves to
> `C:\Users\Admin\Desktop\Claude clone\keel\src\keel`. A byte-for-byte
> `git diff --no-index` of all three implementation files against the worktree
> copies returned **no differences**, so the exact commands below exercise the
> baseline code under review. Re-running with `PYTHONPATH` pinned to the
> worktree `keel/src` produced identical results.

---

## 1. Exact commands and results

### 1.1 Existing adversarial tests (required command)

```
cd C:\Users\Admin\.local\share\opencode\worktree\completion\sandbox-redteam
python -m pytest -q -rs keel/tests/test_sandbox_windows.py keel/tests/test_os_sandbox.py
```

Result (first run):

```
...............s.sssss...                                                [100%]
=========================== short test summary info ===========================
SKIPPED [1] keel\tests\test_sandbox_windows.py:270: Python interpreter cannot start under the restricted token on this host (exit=3221225506, stderr=''); OS boundary itself is proven by the cmd.exe tests above
SKIPPED [4] keel\tests\test_os_sandbox.py:27: BLOCKED: OS enforcement unavailable: BLOCKED: BLOCKED: Windows network denial is NOT enforced — the AppContainer token path requires SeImpersonatePrivilege/SeAssignPrimaryTokenPrivilege (absent on non-elevated tokens), and no administrator-configured firewall rule is applied. Job Objects do not filter network traffic. Pass allow_network=True to run with filesystem/Job Object enforcement but no network boundary.
SKIPPED [1] keel\tests\test_os_sandbox.py:64: network enforcement requires Linux Landlock/seccomp or macOS profile
19 passed, 6 skipped in 10.20s
```

A verbose re-run (`python -m pytest -v -rs ...`) mapped the skips precisely:

| Skipped test | Reason |
| --- | --- |
| `test_sandbox_windows.py::test_main_bootstrap_escape_is_contained` | Python interpreter cannot start under the restricted token on this host (`exit=3221225506` = `0xC0000022` STATUS_ACCESS_DENIED). Honest skip with launch evidence, as designed. |
| `test_os_sandbox.py::test_workspace_read_and_outside_denied` | `confined_or_blocked()` → `SandboxUnavailable` (default `allow_network=False`) → `pytest.skip("BLOCKED: OS enforcement unavailable: ...")`. |
| `test_os_sandbox.py::test_network_denied_by_default` | `pytest.skip("network enforcement requires Linux Landlock/seccomp or macOS profile")`. |
| `test_os_sandbox.py::test_secret_environment_not_inherited` | same `SandboxUnavailable` → BLOCKED skip. |
| `test_os_sandbox.py::test_process_tree_termination` | same `SandboxUnavailable` → BLOCKED skip. |
| `test_os_sandbox.py::test_concurrent_confinement` | same `SandboxUnavailable` → BLOCKED skip. |

All 15 tests in `test_sandbox_windows.py` that ran **passed**, including real-process
assertions for: outside-file read denial, outside-write denial, path-trick
resistance, child-process inheritance, timeout tree kill, CPU limit, environment
scrubbing, and default fail-closed. The 3 `test_os_sandbox.py` tests that ran
(capabilities, main-bootstrap regression, BPF layout) passed.

### 1.2 Own adversarial driver (real confined processes)

Throwaway scripts were written outside the repo under
`C:\Users\Admin\AppData\Local\Temp\opencode\` (`agent08_redteam_driver.py`,
`agent08_redteam_followup.py`, `agent08_redteam_tree*.py`,
`agent08_bpf_sim.py`, `agent08_linux_bpf_sim*.py`). All launches used
`keel.sandbox_windows.run_confined(..., allow_network=True)` — the only mode
that runs on this Windows host — with `argv[0] = %COMSPEC%` (`cmd.exe`) and real
secret files placed outside the workspace. No implementation file was touched.

Observed `capabilities()`:

```json
{"os":"win32","windows_restricted_token":true,"windows_job_object":true,
 "windows_workspace_acl":true,"windows_appcontainer":false,
 "windows_restricted_handle_inheritance":true,"filesystem_enforcement":true,
 "network_enforcement":false,
 "mechanism":"windows-restricted-token+workspace-acl+job-object"}
```

---

## 2. Attack-by-attack observed outcomes

| # | Attack | Actual outcome | Verdict |
| --- | --- | --- | --- |
| 0 | Default `allow_network=False` | `SandboxUnavailable` raised with `BLOCKED: ... Windows network denial is NOT enforced ...`. No process launched. | **Denied / fails closed (confirmed)** |
| baseline | Read file inside workspace | `ok=True`, stdout `WORKSPACE-OK` | Allowed as intended |
| 1 | Read secret file outside workspace (`type <outside>\outside-secret.txt`) | `ok=False`, `exit_code=1`, secret **not** present in stdout | **Denied** |
| 2 | Write outside workspace (`echo PWNED > <outside>\pwned.txt`) | `ok=False`, `exit_code=1`, target file **not created** | **Denied** |
| 3 | Path traversal (`workspace\..\outside-secret.txt`) | `ok=False`, `exit_code=1`, secret **not** leaked | **Denied** |
| 4a | Junction escape: parent-created junction inside workspace → outside dir, read via `type` | Junction existed; read `ok=False`, `exit_code=1`, no leak. Decisive re-test with `dir /b` (a builtin that works under the token) also `ok=False`, empty stdout. | **Denied** |
| 4b | Symlink (`mklink`) escape | `mklink` failed even in the parent: `You do not have sufficient privilege to perform this operation.` Symlink not creatable on this host. | **Unavailable (not bypassed)** |
| 4c | Create junction from *inside* the sandbox | `mklink /J` succeeded (`ok=True`) — but reading through it was still denied because the target DACL does not grant the restricted SID. | **Creation allowed, escape denied** |
| 5a | Child process (`cmd.exe /c type <outside>`) reads outside file | child wrote empty output, `ok=False`, no secret in output file | **Denied (inherited)** |
| 5b | Child process can still run (marker write inside workspace) | marker file created — child execution works, so 5a is a genuine denial, not a launch failure | Confirmed control |
| 6 | Inherit secret environment variables | `KEEL_SANDBOX_SECRET_PROBE` and `API_TOKEN_LEAK` were scrubbed; an opaque-named `REDTEAM_OPAQUE_VAR=HEURISTIC-BYPASS-VALUE` **was inherited and visible** in `set` output | **Partially scrubbed (see F-02)** |
| 7 | Long-running loop / process tree + timeout | Direct loop: `timed_out=True`, heartbeat grew to 15,463 bytes, then **stopped** (size unchanged after 1.6 s). Direct `.bat` child: `timed_out=True`, heartbeat 7,714 bytes, then **stopped**. `start /b` grandchild and nested `cmd.exe /c busy.bat` failed to launch under the restricted token (probe limitation, not a bypass). | **Denied / tree killed** |
| 8 | Read a path explicitly granted to Everyone | Even `C:\Windows\System32\drivers\etc\hosts` and a `C:\Users\Public` file (Public DACL shows INTERACTIVE/SERVICE/BATCH `(M,DC)`, not Everyone) failed under the restricted token on this host. | **Denied (limitation not exploitable here)** |

### 2.1 Fail-closed claim — explicit verification

`run_confined([COMSPEC, "/c", "echo SHOULD-NOT-RUN"], workspace=ws)` with the
**default** `allow_network=False` raised:

```
SandboxUnavailable: BLOCKED: BLOCKED: Windows network denial is NOT enforced — the
AppContainer token path requires SeImpersonatePrivilege/SeAssignPrimaryTokenPrivilege
(absent on non-elevated tokens), and no administrator-configured firewall rule is
applied. Job Objects do not filter network traffic. Pass allow_network=True to run
with filesystem/Job Object enforcement but no network boundary.
```

The raise occurs before `capabilities()`, before any ACL change, and before
`CreateProcessAsUserW`. The same fail-closed behavior holds through the
dispatcher `keel.os_sandbox.run_confined` (4 skips in `test_os_sandbox.py` are
exactly this path) and through the capability wiring
(`capability_registry.py:677` defaults `allow_network` to `False`). **Claim confirmed.**

---

## 3. BPF filter simulations (no inversion)

### 3.1 Legacy in-process filter — `os_sandbox.build_inproc_network_filter()`

Independent interpreter of the returned instruction tuples (not the repo's own
`verdict()` helper):

- 32 instructions; opcodes only `0x06` (RET), `0x15` (JEQ), `0x20` (LD)
- Single load: `(0x20, 0, 0, 0)` — `BPF_LD|BPF_W|BPF_ABS` at offset 0 (`seccomp_data.nr`)
- Return values only: `0x00050001` (`SECCOMP_RET_ERRNO|EPERM`) and `0x7FFF0000` (`ALLOW`)
- `verdict(41 /* socket */) = 0x50001`, `verdict(42 /* connect */) = 0x50001`
- `verdict(0/read) = 0x7fff0000`, `verdict(1/write) = 0x7fff0000`, `verdict(60/exit) = 0x7fff0000`
- Exhaustive check over all 15 denied syscall numbers plus ordinary syscalls: **0 mismatches**
- Verdict: **NO_INVERSION**

### 3.2 Dedicated Linux filter — `sandbox_linux.build_network_filter()`

Executed the module source with shimmed `sys.platform='linux'` and
`os.uname().machine='x86_64'` so `_NETWORK_SYSCALLS` populated:

- 36 instructions; denied set = `41..55, 170, 171` (17 syscalls); approved IPC set empty
- `socket=0x50001`, `connect=0x50001`, `write/read/exit=0x7fff0000`
- Exhaustive check: **0 mismatches**, **NO_INVERSION**

**No remaining inversion found in either BPF builder.** (This is a pure-layout
simulation on Windows; it does not prove the kernel installs the filter as simulated.)

---

## 4. Linux backend static review — `landlock_add_rule EINVAL` cause

Cannot execute on Windows; the following is static plausibility analysis only.

| Check | Observation | Plausibility |
| --- | --- | --- |
| ABI detection | `landlock_abi()` calls syscall 444 with `flags=LANDLOCK_CREATE_RULESET_VERSION (1)`, returns `>0` only when `ret > 0 and err == 0`. | Correct UAPI usage. |
| `_ruleset_attr_size` | v1/v2 = 8, v3/v4 = 16, v5/v6 = 24 bytes. | Matches `struct landlock_ruleset_attr` evolution (`handled_access_fs`, `+handled_access_net`, `+scoped`). |
| Legacy ruleset struct | Declared 4×u64 = **32 bytes** (vs 8 for v1). | Oversized struct was a real ABI defect; new code builds raw byte buffers of the correct per-ABI size. Fixed. |
| Path-beneath struct | 16 bytes: u64 `allowed_access` at 0, s32 `parent_fd` at 8, 4 bytes padding. | Matches `struct landlock_path_beneath_attr`. Fixed. |
| **`landlock_add_rule` 4th arg** | Legacy `os_sandbox._linux_confine` passed `ctypes.sizeof(rule)` = **16** as the 4th syscall argument. That argument is `__u32 flags` and must be 0 → **EINVAL on every kernel**. New `_add_path_rule()` and the runtime bit-probe both pass **0**. | **This is the direct, correct root-cause fix.** The reported EINVAL is fully explained by the old argument. |
| Access-bit masks | Candidates per ABI (v1 `0x1FFF`, v2 `0x3FFF`, v3–v5 `0x7FFF`, v6 `0xFFFF`) then **each bit live-probed** with create_ruleset + add_rule before use; live probe passes flags 0 and the correct 16-byte attr. | Matches kernel UAPI bit positions (REFER=13, TRUNCATE=14, IOCTL_DEV=15) and is defensive. Plausible. |
| `handled_access_net` | Kept zero with a comment that WSL2 6.6 reports ABI 3 but rejects nonzero `handled_access_net` with E2BIG; network denied by seccomp instead. | Plausible and consistent with making the ruleset ABI-correct. |
| `landlock_restrict_self` | syscall 446 with flags 0. | Correct. |
| Pre-flight | `capabilities()` forks a real child, applies the full boundary and requires `fs_denied=True` and `net_denied=True` before advertising enforcement. | Strong fail-closed design; cannot be verified here. |

**Conclusion:** the fix is technically plausible and the previously reported
`landlock_add_rule EINVAL` cause (flags=16 instead of 0, plus wrong struct sizes)
is correctly identified and addressed in `sandbox_linux.py`.

**Cannot be verified without Linux:** actual kernel acceptance of the ABI-sized
rulesets and probed bits; whether this host's kernel reports ABI 3 and exhibits
the E2BIG behavior; real seccomp-BPF installation and EPERM results; rlimit and
`preexec_fn` interactions; the truth of the pre-flight `fs_denied`/`net_denied`
claims. The legacy `os_sandbox._linux_confine` path (still present but no longer
used by the dispatcher on Linux — `run_confined` delegates to `sandbox_linux`)
retains the old defective code; it is only reachable through a direct call and
is not part of the integrated path.

---

## 5. Severity-rated findings

No Critical or High severity vulnerability was found in the integrated Windows
enforcement path. All attempted filesystem, traversal, junction, child-process,
timeout/tree-kill and default-network attacks were denied or failed closed.

| ID | Severity | Finding & reproduction |
| --- | --- | --- |
| **F-01** | **Informational (accepted, disclosed)** | Windows network denial is not enforced. With the default `allow_network=False`, `run_confined` raises `SandboxUnavailable` (verified). With explicit `allow_network=True`, filesystem/token/Job boundaries apply but the network is fully open — the returned `limitations` state this. Residual risk is entirely at the caller: `capability_registry.py:677` must never default this flag to True. Currently it defaults to False. Not a bypass of a claimed boundary. |
| **F-02** | **Low** | Environment scrubbing is name-heuristic and only strict when `env is None`. Reproduction: `run_confined(..., env={**os.environ, "REDTEAM_OPAQUE_VAR": "HEURISTIC-BYPASS-VALUE"}, allow_network=True)` → `set` output contains `REDTEAM_OPAQUE_VAR=HEURISTIC-BYPASS-VALUE`. Variables whose names lack the `_SECRET_HINTS` substrings are inherited. The Windows module does more than documented; `sandbox_conformance.py::test_provider_env_secrets` and `test_os_sandbox.py::test_secret_environment_not_inherited` explicitly state that env scrubbing is the policy layer's responsibility, so this is a documented division of labor, not an OS-boundary escape. |
| **F-03** | **Low** | `_grant_sid_on_directory` adds an `Everyone` `GENERIC_ALL` ACE with inheritance flags `0x3` to the workspace DACL for the duration of the run, then restores the directory DACL. During the window, other local processes can access workspace files; child objects created in the window may retain the inherited ACE after the directory DACL is restored. Impact is limited because `workspace` is normally a per-run temp directory, but a caller supplying a persistent/sensitive workspace gets a transient ACL widening. No data escape from the confined child was observed. |
| **F-04** | **Informational** | On this host the restricted token cannot start the Python interpreter (`exit=0xC0000022 STATUS_ACCESS_DENIED`), so Python-payload attacks (e.g. `__main__` global-mutation escape) could not be exercised on Windows; the corresponding test skipped honestly. Only `cmd.exe` builtins could be used as the attack payload. |
| **F-05** | **Informational** | Attempts to spawn a grandchild via `start /b <bat>` or nested `cmd.exe /c <bat>` did not produce a running grandchild under the restricted token; a directly launched `.bat` child did run and was killed on timeout. This is a payload/launch limitation that narrows tree-kill coverage, not a bypass. The repo's own `test_timeout_terminates_process_tree` passed. |

No reproduction of a *successful* forbidden action (secret read/write, traversal,
junction escape, inherited secret env with a hinted name, or surviving process
tree) was obtained.

---

## 6. Verdict per OS

- **Windows — real enforcement (partially scoped).** Kernel-enforced restricted
  primary token + workspace DACL + Job Object were confirmed by real processes:
  filesystem denial (outside read/write, `..` traversal, junctions, child
  processes), CPU/memory/active-process limits, handle inheritance restriction,
  and timeout tree termination. Network denial is genuinely unavailable and
  **fails closed**; `allow_network=True` is a caller opt-in with no network
  boundary. Verdict: **real OS enforcement for filesystem/process/resources;
  network unenforced and honestly disclosed.**
- **Linux — unverified locally.** Static review supports the `landlock_add_rule
  EINVAL` fix (flags 0, correct ABI struct sizes, runtime-verified access bits)
  and shows no BPF inversion in `build_network_filter()`. No kernel execution
  was possible on this Windows host. Verdict: **unverified locally; plausible
  fix, requires on-Linux confirmation.**
- **macOS — unverified.** `sandbox-exec` profile in `os_sandbox._macos_profile`
  uses `(deny default)` + `(deny network*)` with scoped read/write allowances;
  no macOS host was available to execute it. Verdict: **unverified.**

---

## 7. What remains blocked

1. Linux/macOS backends cannot be executed from this Windows host; all their
   conclusions are static/simulated only.
2. AppContainer network denial cannot be tested — requires
   `SeImpersonatePrivilege`/`SeAssignPrimaryTokenPrivilege` absent from the
   non-elevated token (verified via `capabilities()['windows_appcontainer'] == False`).
3. Python-interpreter payloads cannot run under the restricted token on this
   host, blocking direct Windows reproduction of `__main__`-style Python escapes
   and of network probes that need a Python socket.
4. `mklink` symlink creation requires privileges unavailable here; only junctions
   could be tested (and were denied).
5. BPF correctness was verified by interpreting the instruction tuples, not by
   installing a filter in a kernel; actual seccomp behavior remains unverified.
6. Kernel-level correctness of the Landlock ABI sizes/bit probes and the
   pre-flight claims requires a real Linux run on the target kernel.

---

## 8. Integrity statement

Only `master-plan-v6-sandbox-verification.md` (this file) was added to the
worktree. No implementation or test file was modified. Throwaway adversarial
scripts live under `%TEMP%\opencode\` outside the repository and were not
committed. No push was performed.
