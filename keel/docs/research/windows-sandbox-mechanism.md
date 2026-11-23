# Windows OS sandbox mechanism (research + implementation report)

**Module:** `keel/src/keel/sandbox_windows.py`
**Tests:** `keel/tests/test_sandbox_windows.py`
**Interface:** drop-in match for `keel.os_sandbox` — `capabilities()` and
`run_confined(argv, *, workspace=None, timeout_s=15.0, cpu_s=10,
memory_mb=256, env=None, allow_network=False) -> ConfinementResult`.
`ConfinementResult` and `SandboxUnavailable` are imported from
`keel.os_sandbox`; this module defines neither.

## Test environment (all findings are from this host)

- Windows build `10.0.26300`, Python 3.11.9 (64-bit), pytest 9.0.2.
- Running user is **non-elevated** (`IsUserAnAdmin() == 0`), integrity level
  **Medium** (`S-1-16-8192`), with **no** `SeImpersonatePrivilege`,
  `SeAssignPrimaryTokenPrivilege`, `SeIncreaseQuotaPrivilege`, `SeTcbPrivilege`,
  `SeDebugPrivilege`, `SeSecurityPrivilege`, `SeBackupPrivilege`, or
  `SeRestorePrivilege`.
- Pytest must be run with the worktree's `src` first on `sys.path`
  (the globally installed `keel-harness` points at a different checkout):

  ```powershell
  $env:PYTHONPATH = "<worktree>\keel\src"
  python -m pytest tests/test_sandbox_windows.py -v
  ```

## What is actually enforced

| Boundary | Mechanism | Status |
|---|---|---|
| Filesystem read/write | Restricted primary token (restricted SID = Everyone) + workspace DACL ALLOW ACE for that SID | **Enforced (kernel DACL check)** |
| Process tree / descendants | Job Object, no breakaway, `KILL_ON_JOB_CLOSE`, `TerminateJobObject` | **Enforced** |
| CPU time | `JOB_OBJECT_LIMIT_PROCESS_TIME` + `JOB_OBJECT_LIMIT_JOB_TIME` (100 ns ticks) | **Enforced** |
| Memory | `JOB_OBJECT_LIMIT_PROCESS_MEMORY` + `JOB_OBJECT_LIMIT_JOB_MEMORY` | **Configured** (not exhaustion-tested, see below) |
| Active process count | `JOB_OBJECT_LIMIT_ACTIVE_PROCESS` | **Configured** |
| Handle inheritance | `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` with exactly two inheritable file handles (stdout/stderr) via `STARTUPINFOEXW` | **Enforced** |
| Environment | Unicode env block built from a scrubbed dict; secret-looking keys removed | **Enforced** (best-effort string filter) |
| Network | — | **BLOCKED — not enforced** |
| AppContainer | — | **BLOCKED — not available to a non-elevated token** |

### 1. Restricted primary token (F2)

`CreateRestrictedToken(current_token, DISABLE_MAX_PRIVILEGE | SANDBOX_INERT,
…)` is called with:

- **deny-only SIDs:** `S-1-5-32-544` (Administrators) with
  `SE_GROUP_USE_FOR_DENY_ONLY`;
- **restricted SIDs:** `S-1-1-0` (Everyone).

Every access check must then pass for both the normal SID set and the
restricted SID set. The token is installed with `CreateProcessAsUserW`. This
works from a non-elevated caller because the new token is *derived from the
caller's own token*; no `SeAssignPrimaryTokenPrivilege` is required. (Verified
empirically: launch succeeded, `pid != 0`, exit 0 for `cmd.exe /c echo …`.)

The child is created `CREATE_SUSPENDED`, assigned to the Job Object, then
resumed, so it cannot spawn a descendant before containment is in place.

### 2. Workspace-limited ACLs

`GetNamedSecurityInfoW` → `SetEntriesInAclW` adds a `GENERIC_ALL` ALLOW ACE for
the restricted SID to the workspace directory DACL; the original DACL is
restored in `finally`. Because no other path grants the restricted SID on the
user's files, reads and writes outside the workspace are denied by the kernel.

Measured with a real restricted process:

```
type <workspace/inside.txt>        -> exit 0, body INSIDE-OK
type <tmp_path/outside-secret>     -> exit 1, no secret in stdout
echo HACK > <tmp_path/outside>     -> exit 1, file not created
```

**Caveat, stated plainly:** the restricted SID is `Everyone`, not a unique
per-run SID. A unique SID cannot work because the OS loader itself is denied
(every `CreateProcessAsUserW` launch died with `0xC0000022 STATUS_ACCESS_DENIED`
on a synthetic SID). `Everyone` is granted on System32 and other OS paths, so
System32 binaries load. The trade-off is that any path whose DACL already
grants `Everyone` remains readable by the confined process. This is a
process-level boundary, not a VM.

### 3. Job Object

`SetInformationJobObject(JobObjectExtendedLimitInformation)` sets:
`KILL_ON_JOB_CLOSE | PROCESS_TIME | JOB_TIME | ACTIVE_PROCESS |
PROCESS_MEMORY | JOB_MEMORY`. `JOB_OBJECT_LIMIT_BREAKAWAY_OK` and
`JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK` are deliberately **not** set, so
descendants cannot leave the job. `TerminateJobObject` is called on timeout and
again in `finally`.

**Job Objects are resource/process-tree boundaries only. They enforce neither
filesystem nor network access, and this module never claims otherwise.**

Measured: a `for /l` busy loop with `timeout_s=3` returned `timed_out=True` in
~3 s; a descendant heartbeat file stopped growing after the call returned.
With `cpu_s=1`, the same loop was killed by the CPU limit in ~2.4 s with a
non-zero exit code and `timed_out=False`.

### 4. Restricted handle inheritance

`InitializeProcThreadAttributeList` + `UpdateProcThreadAttribute` with
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST` and `EXTENDED_STARTUPINFO_PRESENT` restrict
inheritance to exactly the two stdout/stderr file handles. `bInheritHandles`
must be TRUE for those two handles, but the attribute list guarantees no other
handle is inherited (all Python-opened handles are non-inheritable per
PEP 446). A subtle implementation detail: the handle array passed to
`UpdateProcThreadAttribute` must be kept alive until `CreateProcessAsUserW`
returns, or the call fails with `ERROR_INVALID_PARAMETER (87)`.

### 5. Environment scrubbing

Keys containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `CREDENTIAL`,
`KEEL_`, or `API_` are dropped. With `env=None`, only a minimal allowlist
(`SystemRoot`, `PATH`, `TEMP`, `TMP`, `COMSPEC`, `PATHEXT`, processor/OS vars)
is inherited. Verified: injected `KEEL_SANDBOX_SECRET_PROBE` and
`API_TOKEN_LEAK` values do not appear in child output.

## What is NOT enforced — brutally honest limitations

1. **Network (F6): BLOCKED.** A restricted token does not filter Winsock.
   The only per-process OS mechanism is AppContainer, and promoting a token to
   an AppContainer token is impossible here:
   - `SetTokenInformation(TokenAppContainerSid, …)` on a duplicate primary
     token fails with `ERROR_INVALID_PARAMETER (87)` for both a synthetic
     `S-1-15-2-…` SID and a real SID from `CreateAppContainerProfile`
     (exported by `userenv.dll`).
   - The undocumented `kernelbase!CreateAppContainerToken` has no stable
     documented signature; a plausible call faulted with an access violation.
   - Even with an AppContainer token, `CreateProcessWithTokenW` needs
     `SeImpersonatePrivilege` and `CreateProcessAsUserW` needs
     `SeAssignPrimaryTokenPrivilege` for a different user token — both absent.
   - Administrator-configured Windows Firewall rules are out of scope and not
     applied.

   Consequently `capabilities()["network_enforcement"] is False`, and
   `run_confined(..., allow_network=False)` **raises `SandboxUnavailable`
   (fail closed)**. Callers that pass `allow_network=True` get filesystem,
   Job Object, token, handle, and environment enforcement with the network
   left open; every such `ConfinementResult.limitations` says so explicitly.
   No caller is ever silently returned an unrestricted execution.

2. **Executable/DLL dependency constraint.** Only binaries whose DLLs are all
   accessible to the restricted SID can start. On this host `cmd.exe` works,
   but `python.exe` (installed under the user profile), `powershell.exe`,
   `curl.exe`, `ping.exe`, `whoami.exe`, and `hostname.exe` all fail to load
   under the restricted token (`0xC0000135 STATUS_DLL_NOT_FOUND`) even after
   granting `Everyone` read/execute on the interpreter directory and its
   parents. This is why the `__main__` regression test skips with the actual
   launch evidence instead of claiming a pass. A CI host whose interpreter is
   installed in a location granting `Everyone` (or an elevated caller that can
   use AppContainer) will not have this constraint. The module fails closed
   rather than retrying unrestricted when the target cannot start.

3. **Memory/active-process exhaustion is configured, not exhaustion-tested.**
   The limit flags are asserted in a test, but a genuine exhaustion test needs
   a controllable allocator process; the restricted token here can load only
   `cmd.exe` built-ins.

4. **F9 / F16 — out of ownership, documented only.** Python audit hooks
   (`sandbox_policy`, `sandbox_exec`) and fleet background shells are not OS
   confined by this module. They remain separate fail-open surfaces and must
   be addressed by their owners. This module does not touch them.

## Reviewer findings addressed

- **F2 (critical):** the old Windows branch was `cmd=argv; preexec_fn=None` —
  no isolation. This module applies a real restricted primary token
  (`DISABLE_MAX_PRIVILEGE | SANDBOX_INERT`, deny-only Administrators,
  restricted Everyone) via `CreateProcessAsUserW`, workspace-limited ACLs, a
  limiting/terminating Job Object, restricted handle inheritance, and a
  scrubbed environment. It reports network enforcement `False` and fails
  closed on the default path. It never claims AppContainer enforcement.
- **F4 (high):** the only command-bearing parameter is `argv: list[str]`; there
  is no `command`/`cmd`/`shell_command` string parameter and no shell. The lead
  should forward `env`, `timeout_s`, `cpu_s`, `memory_mb`, and `allow_network`
  in addition to the already-wired `argv` in `core.os.sandbox.run`. Tests assert
  (a) a string `command=` / `cmd=` kwarg is rejected and (b) absolute-path,
  `..`-traversal, and nested-`cmd` argv tricks still cannot read outside the
  workspace. Authorization policy must run *before* this module.
- **F6 (high):** no outside-file assertion is skipped. The network assertion is
  a positive test of the BLOCKED/fail-closed behavior, not a skip. The only
  skip (`__main__` escape) includes the real launch failure evidence.
- **F9 / F16:** listed as limitations above; no code changed outside ownership.

## Test results (this host)

```
15 passed, 1 skipped in 7.63s
```

The single skip is `test_main_bootstrap_escape_is_contained`, with the
evidence-backed reason that `sys.executable` cannot start under the restricted
token on this host. Filesystem, child-inheritance, tree-termination, timeout,
CPU-limit, handle/environment, and fail-closed behavior are all proven by
passing tests against real processes.
