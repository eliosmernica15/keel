# Linux native sandbox mechanism — root-cause analysis and implementation

**Scope:** `keel/src/keel/sandbox_linux.py`, `keel/tests/test_sandbox_linux.py`.
No shared files (`os_sandbox.py`, `capability_registry.py`) were modified.

**Reproduction environment:** WSL2 Ubuntu 26.04, kernel
`6.6.87.2-microsoft-standard-WSL2`, CPython 3.14.4, pytest 9.0.2. Landlock ABI
version query returns **3**.

---

## 1. Root cause of `landlock_add_rule` EINVAL

The old `os_sandbox.py` called:

```python
libc.syscall(445, ruleset_fd, 1, ctypes.byref(rule), ctypes.sizeof(rule))
```

The actual syscall signature (`security/landlock/syscalls.c`) is:

```c
SYSCALL_DEFINE4(landlock_add_rule,
    const int,           ruleset_fd,
    const enum landlock_rule_type, rule_type,   /* 1 = PATH_BENEATH */
    const void __user *, rule_attr,
    const __u32,         flags);                /* MUST be 0 */
```

**There is no size argument.** The old code passed `ctypes.sizeof(rule)` (16) as
the fourth argument — i.e. as `flags`. The kernel rejects any nonzero `flags`
with `EINVAL`. This is the whole reason `landlock_add_rule` failed; the ruleset
creation itself succeeded.

Reproduction (same ruleset and attr buffer, varying only the 4th argument):

```
add_rule flags=  0 -> r=0   errno=0   OK
add_rule flags= 16 -> r=-1  errno=22  Invalid argument
add_rule flags=  1 -> r=-1  errno=22  Invalid argument
add_rule flags= 32 -> r=-1  errno=22  Invalid argument
```

Running the unmodified `keel.os_sandbox._linux_confine()` in WSL reproduced
`SandboxUnavailable: landlock_add_rule failed` (errno 22).

### Secondary defects found in the old implementation

1. **Wrong access-bit table.** `LL_READ_FILE = 1<<0`, `LL_EXECUTE = 1<<3`,
   `LL_READ_DIR = 1<<5`, `LL_REFER = 1<<11`, `LL_ALL_FS = (1<<13)-1` etc. are
   shifted relative to `include/uapi/linux/landlock.h`. Correct positions
   (verified against the installed 7.0 header and by runtime probing) are
   `EXECUTE=1<<0`, `WRITE_FILE=1<<1`, `READ_FILE=1<<2`, `READ_DIR=1<<3`, …,
   `REFER=1<<13`, `TRUNCATE=1<<14`, `IOCTL_DEV=1<<15`. The requested mask
   `0x9ab` did not include `READ_FILE` at all.
2. **`reserved=0` kwarg** was passed to `_LandlockPathBeneathAttr`, which has
   no such field (harmless on CPython 3.14, a `TypeError` on older versions).
3. **Ruleset struct size was hard-coded to 32 bytes.** ABI v1/v2 need 8,
   v3/v4 need 16, v5/v6 need 24. Oversized buffers with trailing zeros are
   tolerated on 6.6 but are not portable.
4. **Broken seccomp filter** (see §3 / F1 below).

### Bit-support evidence (F7)

Per-bit probe on this kernel (create ruleset with `handled_access_fs = 1<<bit`,
then add a path-beneath rule with the same bit):

```
bits 0..14: create=ok add=0 errno=0  (SUPPORTED)
bit 15+:    create fail errno=22     (requires a newer ABI)
supported mask = 0x7fff
```

`_supported_fs_bits()` repeats this probe at runtime for every candidate bit
and gates `handled_access_fs` and every rule's `allowed_access` on the result.
The ABI version is queried first and determines the candidate set **and** the
correct `struct landlock_ruleset_attr` size; unsupported bits are dropped
individually and reported in `capabilities()["preflight_evidence"]` — never
silently removed.

Additional finding: this WSL kernel reports ABI 3 but returns **E2BIG (errno 7)**
from `landlock_create_ruleset` when `handled_access_net` is nonzero. Therefore
we keep that field zero and enforce network denial exclusively with seccomp,
which is consistent across kernels.

---

## 2. Landlock filesystem enforcement

Order in the forked child:

1. `prctl(PR_SET_NO_NEW_PRIVS, 1)` — must precede `restrict_self` and seccomp.
2. Best-effort `PR_CAPBSET_DROP` for caps 0..63 (unprivileged users cannot drop
   the bounding set; this is reported in `limitations`).
3. Create ruleset with ABI-correct attr size and runtime-verified fs bits.
4. Add path-beneath rules:
   - `/` → `EXECUTE` only (absolute path traversal).
   - **workspace → all verified bits** (full read/write/create/rename/truncate).
   - `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/lib32`, `/etc`, `/opt` →
     `EXECUTE|READ_FILE|READ_DIR` (interpreter, dynamic loader, libraries).
   - Optional extra executable directory (e.g. a virtualenv outside those
     paths) → same read+exec set.
   - `/dev` → `EXECUTE|READ_DIR`; `/dev/null`, `/dev/zero`, `/dev/urandom`,
     `/dev/random` → `READ_FILE|WRITE_FILE`.
5. `landlock_restrict_self(ruleset_fd, 0)` — irrevocable, inherited by all
   descendants across `fork()` and `execve()`.

Because Landlock is a whitelist over *handled* access types, any access not
covered by a rule is denied with `EACCES`. A file outside the allow-list cannot
be read or written, including through `../` traversal or symlinks (Landlock
checks the resolved final object).

The 4th argument of `landlock_add_rule` is **always 0** in the new code.

---

## 3. seccomp-BPF network denial (F1)

`build_network_filter()` emits:

```
insn[0]  = (BPF_LD|BPF_W|BPF_ABS = 0x20, jt=0, jf=0, k=0)  ; seccomp_data.nr
for each denied nr:
   (BPF_JMP|BPF_JEQ|BPF_K = 0x15, jt=0, jf=1, k=nr)        ; match -> next
   (BPF_RET|BPF_K        = 0x06, jt=0, jf=0, k=0x00050001) ; ERRNO|EPERM
(approved-IPC block — empty by default)
default: (BPF_RET|BPF_K = 0x06, jt=0, jf=0, k=0x7fff0000)  ; ALLOW
```

Denied syscalls (x86_64): 41–55 (`socket`, `connect`, `accept`, `sendto`,
`recvfrom`, `sendmsg`, `recvmsg`, `shutdown`, `bind`, `listen`, `getsockname`,
`getpeername`, `socketpair`, `setsockopt`, `getsockopt`) plus 170/171
(`sethostname`/`setdomainname`). Aarch64/generic uses 198–212 and 161/162.
`DNS` is covered because resolution needs `socket`/`connect`/`sendto` and
`/etc/resolv.conf` reads are separately constrained by Landlock.

For the *network* class this is deny-by-default: the explicitly-approved IPC
set is empty, so every network syscall returns `EPERM`. Non-network syscalls
are left to the default ALLOW because a hand-written full allowlist is
architecture/libc dependent and would break ordinary interpreters; filesystem
confinement remains provided by Landlock, and all network creation is denied.

The reviewer's original defects in `os_sandbox.py` are all avoided:

| Reviewer finding | Old code | New code |
|---|---|---|
| Load opcode | `0x00` (BPF_IMM) | `0x20` (BPF_LD\|BPF_W\|BPF_ABS) |
| Load offset | 4 (`arch`) | 0 (`nr`) |
| Branch polarity | inverted (allowed denied syscalls, killed others) | `jeq nr, jt=0, jf=1` → EPERM on match |
| Return action | `k=1` = `SECCOMP_RET_KILL_THREAD` → SIGSYS (−31) | `k=0x00050001` = `SECCOMP_RET_ERRNO\|EPERM` |
| Default | `k=0x7fff0000` but unreachable due to inversion | `k=0x7fff0000` for non-network |

`test_bpf_program_uses_correct_load_and_return_actions` asserts the exact
instruction tuples, and `test_network_filter_forked_child_socket_denied_write_ok`
forks a child, installs only this filter, and verifies over a pipe that
`write()` succeeds while `socket.socket()` raises `PermissionError`.

---

## 4. Other controls

* **no_new_privs** set first; prevents privilege gains via setuid binaries.
* **FD hygiene:** `subprocess.Popen(close_fds=True, ...)` closes every inherited
  descriptor except stdio before `execve`; test proves an unpassed secret FD
  is `EBADF`/closed in the child.
* **rlimits:** `RLIMIT_CPU=cpu_s`, `RLIMIT_AS=memory_mb MiB`,
  `RLIMIT_NPROC=256`, `RLIMIT_FSIZE=64 MiB`, `RLIMIT_NOFILE=64`,
  `RLIMIT_CORE=0`. 256 (not a tiny value) because `RLIMIT_NPROC` counts all
  processes of the real UID on the host — a value of 16 broke ordinary shells
  on the test runner. Tests prove CPU kill, memory cap, applied process limit,
  and that normal grandchildren still start.
* **Timeout + process tree:** `start_new_session=True` and `communicate(timeout=…)`;
  on timeout the whole process group receives `SIGKILL`. Test verifies a
  grandchild scheduled to write a marker after 2 s never runs.
* **Fail closed:** `SandboxUnavailable` is raised if pre-flight does not
  *actually* demonstrate both denials, or if any primitive fails in preexec.
  There is no unrestricted fallback.
* **Cleanup:** auto-created temporary workspaces are removed in `finally`.

---

## 5. Capability flags come from a real pre-flight (F7)

`capabilities()` never infers enforcement from feature detection alone.
`_preflight()` forks a child that:

1. creates a temporary workspace plus a *secret file outside it*;
2. applies the full restriction chain (`_child_restrictions`);
3. verifies that reading the outside secret fails (`fs_denied=True`);
4. verifies that `socket.socket()` raises `OSError` (`net_denied=True`).

Only a clean exit with both flags true sets `filesystem_enforcement` and
`network_enforcement`. The result is cached and exposed as
`preflight_evidence`, e.g.:

```
abi=3 fs_bits=0x7fff fs_denied=True net_denied=True
```

If any step fails, the flags are False and the exact error is reported in
`limitations`; `run_confined()` then refuses to start.

---

## 6. Tests (F6)

`pytest tests/test_sandbox_linux.py -q` → **16 passed** on the reproduction
kernel. All tests launch real restricted processes. On Linux,
`SandboxUnavailable` is **never** converted to `pytest.skip`; a missing kernel
boundary fails the test. Non-Linux runners skip the module via a
`pytest.mark.skipif` marker.

Coverage: authorized workspace read/write; unauthorized host read/write;
`../` traversal and symlink escape; TCP/UDP/DNS denial; exact BPF structure;
forked-child `socket() → PermissionError` with `write()` working; child-process
inheritance of both boundaries; unpassed FD closure; CPU, memory, process-count
and timeout limits; process-group kill of grandchildren; concurrent runs.

---

## 7. Requirements and limitations

* **Kernel:** Landlock requires Linux ≥ 5.13 (`CONFIG_SECURITY_LANDLOCK=y`);
  seccomp requires `CONFIG_SECCOMP`. The pre-flight fails closed if either is
  missing or blocked by runner seccomp. Landlock ABI ≥ 1 is enough; ABI ≥ 3
  changes the ruleset attr size, which is handled.
* **Architectures:** syscall tables are provided for x86_64 and the asm-generic
  family (aarch64, riscv64, …). Other 32-bit ABIs (e.g. i386 `socketcall`) are
  unsupported and fail closed.
* **Not a VM:** this is process-level isolation sharing the host kernel, /proc,
  IPC namespaces, and network namespace. `bwrap`, `unshare`, user/mount/network
  namespaces are **not used** by this backend (F8). Granting read access to
  `/etc`, `/usr`, etc. is intentional so interpreters work; those paths are not
  writable.
* `allow_network=True` opts out *only* of the seccomp network filter; Landlock
  filesystem confinement and all other controls remain active.
* Capability dropping is best-effort under unprivileged users.
* `RLIMIT_NPROC` is per real UID on the host, not a per-sandbox cgroup limit.
* If the caller supplies `env`, it is passed through unchanged; if omitted, an
  empty environment is used, so ambient host secrets are not inherited.
* The pre-flight result is cached for the process lifetime; a kernel that
  changes enforcement mid-process is out of scope.
