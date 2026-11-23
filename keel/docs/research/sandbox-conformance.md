# OS sandbox conformance evidence and threat model

This document is the static companion to `tests/sandbox_conformance.py`.
Generated evidence (JSON + Markdown) is written at test time into `tmp_path`;
no synthetic results are committed here.

## How the suite is run

```
cd keel
$env:PYTHONPATH = "$PWD\src"            # ensure the worktree source is tested
python -m pytest tests/sandbox_conformance.py -q -s --tb=short
```

`KEEL_SANDBOX_BACKEND=<module>` can substitute a platform-specific backend
(`keel.sandbox_linux`, `keel.sandbox_windows`, `keel.sandbox_macos`) once the
lead integrates one; absent modules are tolerated. `KEEL_CONFORMANCE_REPORT_DIR`
redirects generated evidence (CI artifact capture). The module is intentionally
not named `test_*.py`, so it does not run in the normal fast unit-test pass.

## Method

Every case launches a **real restricted child process** through
`keel.os_sandbox.run_confined`. No case passes by inspecting configuration or a
detection flag. The child emits `READY` before attempting anything, `BREACH:`
only when a forbidden action actually succeeded, `ALLOWED_OK:` for authorized
actions, and `DENIED:<ExcType>` when an exception is caught. A caught exception
is never converted into success.

Two safeguards prevent false verdicts:

1. **Unconfined negative control.** Network, filesystem, credential and process
   cases run the identical probe outside the sandbox. A denial counts as
   enforcement only if the control produced the `BREACH:` marker. This caught a
   case where an unreachable host made an unconfined connection fail and look
   like a sandbox denial.
2. **F6 / capability-claim rule.** `capabilities()` enforcement flags are read
   for every verdict:
   - if a flag claims enforcement and the process breaches, the case is **FAIL**;
   - if a flag claims enforcement and the process cannot launch or never reaches
     the probe, the case is **FAIL**, never `pytest.skip`;
   - `pytest.skip` is used only for **BLOCKED**, with the flag reported as False
     (or an environment/setup limitation) and the captured stderr embedded
     verbatim in the reason.
   - Additional `BLOCKED` reasons (symlink setup privilege, negative control
     unable to reproduce the action on the host) likewise carry exact stderr.

### Classification

| Class | Meaning |
| --- | --- |
| PASS | Restricted process behaved as expected; control supports the verdict. |
| PARTIAL | Restricted process ran, but the result is ambiguous or is a methodology finding. |
| BLOCKED | Mechanism unavailable on this host / setup impossible; skip with stderr evidence. |
| FAIL | Restricted process violated the expected boundary despite a capability claim. |

### Evidence format

`tmp_path/keel-docs-research/sandbox-conformance/`:

- `sandbox-conformance-report.json` — generated UTC timestamp, host OS/platform/
  Python/backend, summary counts, classification legend, and one record per case
  with: `case_id`, `category`, `os`, `mechanism`, `expected`, `actual`,
  `exit_status`, `observed_denial`, `safe_logs` (scrubbed stdout/stderr,
  `timed_out`, and control output), `classification`, `reason`.
- `sandbox-conformance-report.md` — human-readable case table with the same
  fields.

`_scrub()` redacts known secret sentinels and truncates logs before they enter
the report.

## Coverage matrix

Authorized workspace read/write; unauthorized host file read/write; path
traversal; symlink escape; inherited file descriptors/handles; external TCP and
UDP; DNS; localhost; inherited network descriptors; child-process network
access; provider/environment secrets; application config/credential files;
child-process inheritance; unauthorized process execution; process-tree
termination; concurrent execution; CPU/memory/process exhaustion; wall-clock
timeout; seccomp filter semantics; and a methodology case for the empty-env
artifact.

## Host results (Windows, `win32`, Python 3.11.9, backend `keel.os_sandbox`)

25 cases: **PASS 8 / PARTIAL 1 / BLOCKED 10 / FAIL 6** (pytest: 9 passed,
10 skipped, 6 failed). Exact records are in the generated JSON for that run.

### Findings

1. **HIGH — Windows filesystem claim is not enforced.**
   `capabilities()` reports `filesystem_enforcement: True` on Windows, yet the
   restricted process read and wrote arbitrary host files, escaped via `../`,
   read a credential file under a redirected `HOME`, and executed a binary
   outside the workspace. The Windows branch of `run_confined` sets
   `cmd = argv; preexec_fn = None` and applies no restricted token, Job Object,
   or FS ACL. Six cases are FAIL for this reason. The module docstring claims a
   "restricted primary token", but no token is created.
2. **HIGH — F6 all-skipped would have passed the old helper.** A previous
   `confined_or_blocked()` pattern turned `SandboxUnavailable` and many non-zero
   results into `pytest.skip("BLOCKED")`, letting a platform that claims
   enforcement pass with everything skipped. The shared suite removes that
   path: claims are read from `capabilities()`, and launch failures / breaches
   under a claim are hard FAILs.
3. **MEDIUM — empty default environment fabricates a network denial.**
   `run_confined(env=None)` passes `env={}`. On Windows that removes
   `SYSTEMROOT`, so Winsock raises `OSError` and an unconfined-equivalent
   network probe appears "denied". A dedicated case (`default-empty-env-artifact`,
   PARTIAL) demonstrated: default env → `DENIED:OSError`; full env →
   `BREACH:TCP` from the *same confined interface*. All network cases therefore
   pass a normal environment so confinement is the only variable, after which
   they correctly classify BLOCKED on this host (`network_enforcement: False`).
4. **MEDIUM — provider/env secrets leak through the OS layer.** With a custom
   env containing `KEEL_PROVIDER_SECRET` / `ANTHROPIC_API_KEY`, the confined
   child printed the secret. `os_sandbox.run_confined` does not scrub env;
   `sandbox_policy.child_env` does. Classified BLOCKED only because
   `capabilities()` has no env-scrubbing flag — this is an integration gap that
   callers must close.
5. **MEDIUM — suspected broken seccomp filter.** `_seccomp_deny_network` in
   `os_sandbox.py` builds BPF with `BPF_LD|BPF_W|BPF_IMM` (`0x00`) where an ABS
   load of the syscall number is required; the `jeq` branches are inverted
   (matching syscalls jump *over* the deny, non-matching ones execute it); and
   the return value `1` is `SECCOMP_RET_KILL_THREAD`, not the documented EPERM
   `SECCOMP_RET_ERRNO`. The dedicated `seccomp-filter-semantics` case is
   BLOCKED on this Windows host (stderr: `FILTER_SETUP_ERROR:TypeError:` from
   the attempted filter install). It must be run on Linux; a correct filter
   must deny `socket()` while still emitting the RESULT line via `write()`.
6. **LOW — vacuous assertion.** `tests/test_sandbox_hardened.py:91` reads
   `assert status["resources"]["audit_hook"] if "audit_hook" in status["resources"] else True`.
   `sandbox_status()["resources"]` has no `audit_hook` key (it has `timeout`,
   `output_cap`, `posix_memory_cpu`, `windows_job_objects`), so the assertion is
   always True and verifies nothing. The lead should replace it with a real
   assertion.
7. **Timeout enforcement, concurrent execution, inherited FD/handle isolation,
   and workspace read/write PASS on this host.** CPU/tree cases are PASS via
   wall-clock timeout on Windows; memory/process limits are BLOCKED because
   `capabilities()` reports no resource flag on this OS.

No sandbox implementation file or `capability_registry.py` was modified.

## Threat model: execution-route bypass audit

Read-only audit of the current source. "Calls interface" means the route
actually reaches `os_sandbox.run_confined` (OS boundary) or
`sandbox_exec.run_python` (Python audit-hook boundary); a route that only calls
`safety.tier2_check` is doing command authorization, **not** OS containment.

| Route | Where | Calls sandbox interface? | Notes / bypass |
| --- | --- | --- | --- |
| Keel Code (extended tools) | `runner.py` `_dispatch_extended`, `_run_python`, `run_shell`, `_run_tests`, `_run_build`, `_install_deps`, `_background_shell` (lines ~321-584) | **No** | Raw `subprocess.run/Popen`. Only `tier2_check` static analysis gates them. A shell command can spawn arbitrary children with full host FS/network and inherited env. |
| Cowork | `cowork_channels.py`, Fleet background shells `fleet/shells.py:130` | **No** | `subprocess.Popen(argv)` with full inherited environment; output redirected to `~/.keel/fleet/shells`. No confinement. |
| Fleet | `fleet/shells.py`, `fleet/connector_ops.py:96` (`npm root -g`) | **No** | Background shells and connector commands bypass both OS and audit-hook boundaries. |
| Tool execution | `tools/native.py`, `tools/registry.py`, `capability_registry.py` | **Partly** | `core.os.sandbox.run` (`capability_registry.py:653-666`) calls `run_confined`; `code.sandbox.run` (`:949`) calls `sandbox_exec.run_python`. Ordinary `run_python`/`run_shell` tool dispatch goes through `runner.py` and is unguarded. |
| Local task executor | `runner.py` real tools; `platform_gaps.py:259-274` `TaskQueue.run` | **No** | `LocalTaskExecutor` runs approved `argv` via `subprocess.run(shell=False)`; approval is an authorization record, not a boundary. `runner.py` is the primary unguarded path. |
| CLI | `cli/main.py:10` → `runner.run`; `notebook.execute_notebook` (`sandbox_exec.run_python`) | **Partly** | CLI tool execution inherits the unguarded `runner.py` path. Notebook cells use the Python-level audit hook, which explicitly admits native bypass. |
| Subprocesses (MCP, hooks, browser, model runtime, verification, webapp, secret providers) | `mcp.py:161`, `hooks.py:221`, `browser_launch.py:68`, `model_runtime.py:62`, `verification.py:43`, `webapp.py:912,1333`, `secret_providers.py:90` | **No** | Raw `subprocess` throughout. Each is a potential launch vector for unconfined code with the parent's environment. |
| Native isolation (separate module) | `native_isolation.py` `run_isolated` / `probe_backend` | **Different interface** | Applies POSIX rlimits / Windows Job Object, but is not called by `os_sandbox.run_confined` and is not wired into the execution routes above. |

### Bypass routes to close

1. Route every shell/Python/test/build/background command in `runner.py`,
   `fleet/shells.py`, and `platform_gaps.py` through `os_sandbox.run_confined`
   (or a single shared executor), with the workspace derived from the approved
   task/session root and a scrubbed env.
2. Fix the Windows branch of `run_confined` so `capabilities()` claims match
   reality: either implement a restricted token + Job Object + FS ACLs, or
   report `filesystem_enforcement: False` until it exists.
3. Scrub credential-like env vars in the OS boundary itself, not only in the
   Python policy layer.
4. Correct the seccomp BPF program and keep the dedicated conformance case in
   Linux CI so a regression fails the build.
5. Replace the vacuous assertion at `test_sandbox_hardened.py:91`.
