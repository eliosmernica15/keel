# macOS native sandbox: mechanism, defect analysis and limits

**Scope.** `keel/src/keel/sandbox_macos.py` is a standalone macOS backend
(`capabilities()` / `run_confined()` / shared `ConfinementResult` /
`SandboxUnavailable`). It does not modify `os_sandbox.py`,
`capability_registry.py` or any shared module. Baseline: `c662acb5`.

## 1. Why the existing profile was BLOCKED on `macos-latest`

Two *independent* defects made a confined Python fail. Fixing only one would
still leave tests blocked.

### 1.1 The interpreter was outside every allowed read root

The old profile allowed content reads only under hard-coded roots:
`/usr`, `/bin`, `/System`, `/opt`, `/Library`, `/etc`, `/dev`,
`/private/var/db` and the workspace. On GitHub `macos-latest`,
`actions/setup-python` installs CPython under the runner toolcache:

```
/Users/runner/hostedtoolcache/Python/<3.11.x>/x64/bin/python3
/Users/runner/hostedtoolcache/Python/<3.11.x>/x64/lib/python3.11/...
/Users/runner/hostedtoolcache/Python/<3.11.x>/x64/lib/python3.11/lib-dynload/...
```

None of those paths is under an allowed root. With `(deny default)`:

* `execve` of the interpreter / dyld mapping of the Mach-O and its dylibs
  is denied (`EPERM`);
* CPython cannot import `encodings`, `site` or stdlib modules;
* an editable Keel install puts `keel` in the repo, also outside the
  workspace, so `-m keel` likewise fails.

The fix derives the roots at runtime from `sys.prefix`, `sys.base_prefix`,
`sys.executable` and `sysconfig.get_paths()` (`stdlib`, `platstdlib`,
`purelib`, `platlib`, `scripts`, `data`), plus the resolved target `argv[0]`
and its two parent directories. That is precise: it covers toolcache,
Homebrew, framework and venv layouts without granting global reads.

### 1.2 `RLIMIT_AS=256 MB` is incompatible with dyld on modern macOS

Since macOS 11 the kernel maps the signed **dyld shared cache** into every
process at exec time. It occupies roughly **1–2 GiB of virtual address space
per process** (the cache file is 3–5 GiB on disk on Apple Silicon and lives in
`/System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/` on macOS 13+).
`RLIMIT_AS` counts this mapping. A 256 MB address-space cap therefore fails
before `main()` — even for a trivial program — with dyld errors such as
`dyld: cache ... not loaded: syscall to map cache into shared region failed`.
This is why even a perfect profile alone would not unblock the tests.

`RLIMIT_NPROC=8` is also unsafe on macOS: the limit counts **all processes of
the UID**, not just the confined tree, so on a busy runner any `fork()` in the
confined Python fails with `EAGAIN`. The backend skips it and says so.

The backend raises the address-space ceiling to a macOS floor of **4096 MB**
and reports `address_space: "PARTIAL"` plus an explicit limitation string.
`RLIMIT_CPU` and the timeout remain fully enforced.

## 2. Chosen mechanism

`/usr/bin/sandbox-exec -p <SBPL v1 profile> <argv...>`, with a pre-flight
probe (`/usr/bin/true`) that fails closed with `SandboxUnavailable` if the
profile cannot be compiled/applied. `sandbox(7)` states that **new processes
inherit the sandbox of their parent**, so the child-process restriction test
is meaningful.

Profile (generated, not hand-fixed):

| Operation | Grant | Why |
| --- | --- | --- |
| `process-exec`, `process-fork` | yes | launch interpreter and its subprocesses |
| `sysctl-read` | yes | dyld/CPython host introspection |
| `file-read-metadata` | yes, **global** | dyld and CPython stat ancestor paths; reveals names/sizes, never contents |
| `file-ioctl` | yes | libSystem/tty handling on pipes |
| `mach-lookup`, `ipc-posix-shm*`, `system-socket` | yes, broad | dyld/libSystem startup and directory services; **not confined** (documented) |
| `file-read*` | workspace + interpreter roots + `/System`, `/Library`, `/usr`, `/bin`, `/sbin`, `/opt`, `/etc`, `/private/etc`, dyld/timezone DB dirs + `/dev/{null,zero,random,urandom}` | dyld cache, system dylibs, stdlib, zoneinfo, entropy |
| `file-write*` | workspace only | authorized mutation; raw `/dev` devices deliberately not writable/readable |
| `network*` | **denied** by default; all-or-nothing `allow network*` on `allow_network=True` | no per-host filtering in SBPL |

Paths are validated before interpolation: absolute, no `"`/`\`/`(`/`)` and no
control characters. Injection attempts raise `SandboxUnavailable` (fail
closed). No shell is used, and the process tree is started in its own session
so a timeout kills the whole process group via `SIGKILL`.

### Alternatives considered and rejected

* **App Sandbox entitlement (Electron).** The desktop app spawns the Python
  sidecar with `child_process.spawn` (`keel/desktop-app/main.js`). Whether a
  child inherits App Sandbox depends on the parent actually running with
  `com.apple.security.app-sandbox` and on the launch path; the repo ships no
  `.entitlements` file for the app. We do **not** rely on it. This module
  applies its own profile to the Python process directly, so it is correct
  regardless of Electron packaging.
* **A helper/daemon.** A privileged helper would add code-signing,
  XPC/entitlement and distribution complexity, and still need Seatbelt or
  App Sandbox underneath. It does not remove the dyld/RLIMIT constraints.
* **Global `(allow file-read*)`.** Used by several tools to make interpreters
  launch, but it lets confined code read SSH keys, keychains and dotfiles.
  Rejected; that is exactly the over-broad rule this work set out to remove.

## 3. The PyInstaller sidecar

`keel/desktop-app/sidecar.spec` builds a **one-file** `keel.exe`. At startup
the bootloader unpacks its payload into `$TMPDIR/_MEIxxxxxx`, which on macOS
defaults to `/private/var/folders/...` or `/private/tmp`. That path is outside
the workspace and therefore **denied** by this profile. Two consequences:

* `run_confined()` sets `TMPDIR=<workspace>/.tmp` when the caller does not
  supply `env`, so a one-file sidecar can unpack inside the write allowlist;
* if a caller passes an explicit `env` with a host `TMPDIR`, startup of the
  packaged sidecar will be denied. This is a real, documented limitation, not
  a silent fallback.

The sidecar imports third-party wheels from the interpreter's site-packages
(covered by the derived prefix roots) and reads bundled resources from its
own extraction directory (inside the workspace). The HTTP bridge binds a
loopback port only if `allow_network=True`; by default networking is denied.

## 4. Honest limitations / deprecation

1. **`sandbox-exec(1)` is DEPRECATED.** Its own man page says so and directs
   developers to App Sandbox. It is present and functional on macOS 15
   (Sequoia), including GitHub `macos-latest`, but Apple can remove it; this
   backend is best-effort, not a supported long-term API. It may print a
   deprecation notice to stderr — tests never assert empty stderr.
2. **Filesystem isolation is PARTIAL.** Global `file-read-metadata` exposes
   path existence, names and sizes. File *contents* outside the allowlist are
   denied and writes are confined to the workspace (`FULL` for writes).
3. **System IPC is not confined.** `mach-lookup`, POSIX shared memory and
   `system-socket` are allowed so dyld/libSystem and user-lookup calls work.
4. **Already-open descriptors bypass later checks.** `sandbox(7)` is explicit
   that restrictions are applied when a resource is acquired; an fd opened
   before confinement stays usable. This backend does not close inherited
   descriptors.
5. **No PID/IPC namespace.** Confined code shares the host PID space. The
   timeout kills only the confined session's process group; unrelated host
   jobs are untouched. `process-info*` and `signal` are not granted.
6. **Memory ceiling is advisory (PARTIAL).** Raised to 4096 MB to accommodate
   the shared cache; `RLIMIT_NPROC` is not applied. `RLIMIT_CPU` and wall-clock
   timeout are enforced.
7. **`allow_network=True` is all-or-nothing.** SBPL permits port-level rules
   but not hostname filtering; we deliberately offer only deny/allow.
8. **Process-level isolation, not a VM.** A compromised confined process can
   still consume CPU, use permitted IPC and attack the kernel itself.
9. **Editable Keel source outside the workspace is not readable.** Running
   `-m keel` from a source checkout requires the checkout to be the workspace
   (or use a non-editable install under `sys.prefix`).

## 5. Test contract

`keel/tests/test_sandbox_macos.py` uses a module-level
`pytest.mark.skipif(sys.platform != "darwin", ...)`, so non-macOS runners skip
all 13 tests cleanly. On macOS the tests launch real confined processes and
assert: profile restrictiveness + injection rejection; interpreter launch;
workspace read/write; unrelated host file read denial; unauthorized write
denial; network denial; child-process inheritance; process-group timeout; CPU
rlimit; memory-ceiling reporting; sidecar scratch-dir placement; and that a
launch failure is reported with stderr rather than passed.

A launch failure calls `pytest.fail("BLOCKED: ...")` with the exact stderr;
it is never converted into a skip or a pass.

## 6. Native runner evidence

_To be filled from the `python-tests.yml` workflow_dispatch run on
`agent/macos-sandbox` (matrix includes `macos-latest`)._

## 7. References

* `man sandbox-exec` — DEPRECATED notice; `-p/-f/-n/-D` options.
* `man sandbox` — "New processes inherit the sandbox of their parent";
  restrictions apply at resource acquisition, not to already-open fds.
* Apple SBPL guide (BHDC 2011): <https://reverse.put.as/wp-content/uploads/2011/09/Apple-Sandbox-Guide-v1.0.pdf>
* Real restrictive CLI profile with global `file-read-metadata` and narrow
  runtime roots: `makepad/makepad`, `libs/ai/hub/src/claude_cli.sb`.
* CocoaPods `bin/sandbox-pod` — practical interpreter profile showing
  `process-fork`, `system-socket`, `ipc-posix-shm` and `file-read-metadata`.
* dyld shared cache location/size: <https://www.macinternals.app/en/blog/dyld-shared-cache>
