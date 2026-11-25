# STAB-RUNTIME-EVIDENCE.md — runtime/state lifecycle stabilization

Branch `agent/stab-runtime`, worktree
`C:\Users\Admin\.local\share\opencode\worktree\stab\runtime`. Lifecycle work
started at stabilization base `f60b080` and was rebased onto the fetched
stabilization HEAD `c54c673` (workflow security hardening) before commit.
Owned code: `keel/src/keel/{settings.py,settings_store.py,webapp.py,commands.py}`,
`keel/src/keel/cli/main.py`, plus new `keel/tests/test_stab_lifecycle.py`.
No frontend files and no workflow endpoints were changed.

## Probe environment (exact)

PowerShell, from `…\stab\runtime\keel`:

```powershell
$env:HOME = "C:\Users\Admin\AppData\Local\Temp\opencode\stab-clean-home"
$env:USERPROFILE = $env:HOME
$env:PYTHONPATH = "C:\Users\Admin\.local\share\opencode\worktree\stab\runtime\keel\src"
cd "C:\Users\Admin\.local\share\opencode\worktree\stab\runtime\keel"
python -m pytest -q <targets>
```

`PYTHONPATH` is required because the developer workspace also has an editable
`keel` install; every probe below imported the worktree copy (verified with
`python -c "import keel; print(keel.__file__)"`).

---

## P1 — One authoritative state root

### Probe

```powershell
python -m pytest -q tests/test_stab_lifecycle.py::test_state_root_precedence_and_absolute_paths `
  tests/test_stab_lifecycle.py::test_no_relative_keel_fallback_in_owned_sources `
  tests/test_stab_lifecycle.py::test_cli_web_and_store_share_the_same_root `
  tests/test_settings.py
```

### Findings before the fix

- `settings.default_state_root()` ignored `KEEL_STATE_DIR`; it always returned
  `~ / .keel`.
- `settings_store` resolved `KEEL_STATE_DIR` or `Path.home()/.keel` at import
  time, independently of `settings`.
- `cli/main.py` had 12 sites using `os.environ.get("KEEL_STATE_DIR", ".keel")`
  (a *relative* `.keel` in the process CWD), plus two sites with a home fallback.
- `webapp.py` had four more `KEEL_STATE_DIR` / `Path.home()/.keel` fallbacks.
- `commands.py` used `Path.home()/.keel/commands` for the user command root.

So the same process could read settings from one directory, write notebooks and
policies into `./.keel`, and write web settings into `~ / .keel`.

### Fix

- `settings.default_state_root()` is now the single resolver: `KEEL_STATE_DIR`
  wins, a relative value is normalized to an absolute path against the CWD,
  an empty/whitespace value falls back to the home directory, and the returned
  path is always absolute.
- `settings_store.STATE_DIR` derives from that resolver.
- Every CLI subcommand, every web endpoint state path and `commands.py` user
  root now call the same resolver (`cli.main._state_root()`, `webapp._state_root()`).
- `webapp.prepare_runtime()` binds the Fleet DB (`fleet.db`) into the same root
  at startup, so the web runtime and CLI share one durable directory.

### Evidence

`test_state_root_precedence_and_absolute_paths` asserts home default, relative
normalization, absolute precedence and empty-variable fallback in a clean HOME.
`test_no_relative_keel_fallback_in_owned_sources` scans all five owned source
files for `os.environ.get("KEEL_STATE_DIR", ".keel")` and
`Path.home()/.keel` — zero matches allowed.
`test_cli_web_and_store_share_the_same_root` runs a real `python -m keel
notebook save` subprocess, asserts the notebook lands under `KEEL_STATE_DIR`,
asserts in a fresh interpreter that `settings_store.STATE_DIR ==
settings.default_state_root()`, and POSTs `/api/settings` to a real bridge and
asserts `settings.json` is written to that same root.

**Gate verdict: PASS.**

---

## P2 — Graceful shutdown (SIGINT / SIGTERM, workers, DB, events, exit code)

### Probe

```powershell
python -m pytest -q tests/test_stab_lifecycle.py::test_real_process_shutdown_and_restart_preserve_state `
  tests/test_stab_lifecycle.py::test_sigint_is_a_graceful_stop `
  tests/test_stab_lifecycle.py::test_shutdown_runtime_idempotent `
  tests/test_process_shutdown.py
```

The process test starts a real `python -m keel serve --port 0` child with a
clean HOME, parses the tokenized URL from stderr, writes durable state through
a real CLI subprocess, sends the platform signal, asserts exit code `0` and a
`keel webapp stopped` report, verifies the hash chain, then starts a second
server on the same state root and asserts the state is still readable.

### Findings before the fix

- `serve()` handled only `KeyboardInterrupt` from the same thread and called
  `server_close()`; there were no SIGTERM/SIGBREAK handlers.
- No worker drain: the Fleet scheduler was an unstoppable module-level daemon,
  in-flight turns and background shell processes were never cancelled.
- The Fleet DB connection was never closed.
- No durable lifecycle event was appended; readiness during shutdown was not
  represented anywhere.

### Fix

- `serve()` runs `serve_forever()` on a worker thread. SIGINT, SIGTERM and
  Windows SIGBREAK handlers only set a `threading.Event`; this avoids calling
  `server.shutdown()` from inside `serve_forever()` (which deadlocks).
- `shutdown_runtime()` is idempotent and, in order: stops HTTP, joins the
  owned Fleet worker thread (2 s budget), cancels all in-flight turns, kills
  tracked background processes, closes the Fleet DB, and appends an fsynced
  `runtime_shutdown` audit event to `observability.jsonl`.
- `prepare_runtime()` appends `runtime_start`, binds the Fleet DB to the
  authoritative root and starts a cancellable worker (the CLI no longer starts
  the unstoppable module daemon).
- Exit code convention: `0` for a clean signalled stop, `1` if a cleanup step
  reports failure. `main()` propagates `serve()`'s code.
- On Windows, `TerminateProcess` (used by `Popen.terminate()`) cannot reach a
  Python signal handler. The Windows path uses `CTRL_BREAK_EVENT` in a new
  process group, which maps to `SIGBREAK`; the test documents this. On POSIX
  both SIGTERM and SIGINT are exercised.

### Evidence

The real-process test asserts: clean exit `0`, `observability.jsonl` exists,
`verify_chain(root).ok`, both `runtime_start` and `runtime_shutdown` actions
present, notebook data intact after restart, and the restarted bridge reaches
`/api/ready`. `test_shutdown_runtime_idempotent` asserts the second call returns
`{"already_shutdown": True}` and the chain stays valid.
`test_process_shutdown.py` (unchanged) proves background process trees are
terminated by the same `cleanup_background_processes()` hook.

**Gate verdict: PASS** (SIGTERM/SIGBREAK where the OS can deliver it; SIGINT on
POSIX; Windows `terminate()` remains a hard kill by OS design).

---

## P3 — Health must not claim readiness

### Probe

```powershell
python -m pytest -q tests/test_stab_lifecycle.py::test_health_reports_real_readiness `
  "tests/test_stab_lifecycle.py::test_health_never_claims_readiness_with_broken_dependency"
```

### Findings before the fix

`/api/health` returned the constant `{"ok": true, "version": ...}`. The existing
`backend_observability.health_check()` / `readiness_probe()` (DB, provider,
worker, event-log probes) were never wired to an HTTP endpoint.

### Fix

- `webapp._readiness_dependencies()` defines real probes for the Fleet DB at
  the authoritative root (`PRAGMA quick_check`), the event log
  (`verify_chain`) and workers (shutdown not requested, owned worker alive).
- `/api/health` keeps `ok` as liveness (the process answered) and adds `ready`,
  `status`, per-dependency statuses and a correlation ID from
  `backend_observability.health_check()`. It never returns raw errors or paths.
- New backend-only `/api/ready` returns `200` when ready, `503` when not.
  No frontend file was touched: the existing UI still reads `ok` and
  `version`.

### Evidence

The healthy probe asserts `ok=True`, `ready=True`, `status="ready"` and all
three dependencies `"ok"`. The parametrized failure test injects an exception
into `database`, `events` and `workers` in turn and asserts `ready=False`,
`status="running"`, the failing dependency reported as `"error"`, and
`/api/ready` returning `503` — in each case liveness stays `True`.

**Gate verdict: PASS.**

---

## P4 — `keel stop` service command

### Decision: not added — documented rather than invented

There is no detached service in this architecture. `keel serve` is a
foreground loopback process whose credential is a fresh token printed once in
the launch URL; there is no service registry, PID file, supervisor or daemon
mode. `architecture.md` §12 describes an L4 *job* supervisor roster with a
status command for jobs, not an HTTP service stop command. A `keel stop`
would have to introduce one of:

1. a PID file (stale-PID and PID-reuse hazards, plus cross-platform process
   identity checks that do not exist in the codebase), or
2. an unauthenticated local shutdown endpoint, or
3. a token persisted to disk, which would weaken the "token is the only
   credential" model.

None of these is justified by the current architecture. The supported and
tested stop path is a direct process signal (SIGINT/SIGTERM/SIGBREAK), with the
same graceful shutdown code used in-process by `shutdown_runtime()`. The kill
switch (`POST /api/kill-switch`) already cancels active turns without stopping
the service.

**Gate verdict: PASS (documented decision, no code added).**

---

## P5 — CLI workflow `--confirm` integration (after merging `c54c673`)

### Probe

```powershell
python -m pytest -q tests/test_stab_lifecycle.py::test_cli_backend_workflow_forwards_confirm_to_prompt_policy `
  tests/test_stab_workflow_auth.py tests/test_backend_workflows.py `
  tests/test_security_remediation.py
```

### Finding and fix

`c54c673` changed `backend_workflows.run_workflow(name, params, *,
confirmed=False)` so a saved `prompt` policy is enforced at the authoritative
boundary. `_backend_workflow_cmd` in the CLI still called
`run_workflow(name, params)`, so `--confirm` satisfied only the CLI's own gate
and the workflow still failed closed with `confirmation_required`. The CLI now
passes `confirmed=("--confirm" in argv)`.

Two stale source-text/test expectations were updated to match the already
correct merged behavior (no runtime code outside the CLI fix was changed):

- `tests/test_stab_workflow_auth.py::test_cli_prompt_policy_confirm_is_the_explicit_approval`
  previously asserted the bug (even `--confirm` fails); it now asserts the
  confirmed CLI call succeeds and reaches the handler.
- `tests/test_security_remediation.py` expected the pre-hardening local
  variable name `"confirm": bool(request.get("confirm"))`; the merged webapp
  uses the strict `confirmed` boolean.

The new module-level regression test saves a real `prompt` policy for
`backend.workflow approval`, proves the direct unconfirmed call returns
`confirmation_required` with no ledger, proves the CLI without `--confirm`
fails its gate with no ledger, and proves the CLI **with** `--confirm` returns
`ok: true` and writes the workflow result ledger (handler side effect).

**Gate verdict: PASS.**

---

## P6 — Verification sets

### Required clean-HOME set (final, after the `c54c673` merge)

```powershell
python -m pytest -q tests/test_stab_lifecycle.py tests/test_stab_workflow_auth.py `
  tests/test_security_remediation.py tests/test_backend_workflows.py `
  tests/test_start_health.py tests/test_webapp.py tests/test_cli_e2e.py `
  tests/test_settings.py tests/test_process_shutdown.py
```

Result: **85 passed, 1 skipped**. The skip is the POSIX-only SIGINT test: on
Windows `CTRL_C_EVENT` cannot be delivered to a console child in a new process
group; the equivalent graceful path is covered by SIGBREAK/SIGTERM.

### Full suite (final)

```powershell
python -m pytest -q
```

Result: **4546 passed, 52 skipped, 3707 subtests passed, 0 failed** in 8m18s,
on the merged tree with all changes below applied. No artifact-only failures
remain at `c54c673` (deterministic release fixtures were added upstream).

**Gate verdict: PASS.**

---

## Files changed

- `keel/src/keel/settings.py` — single state-root resolver.
- `keel/src/keel/settings_store.py` — derive store paths from that resolver.
- `keel/src/keel/cli/main.py` — unified CLI state root; propagate serve exit;
  forward `--confirm` to `run_workflow(confirmed=True)`.
- `keel/src/keel/commands.py` — user command root and doctor/export state paths.
- `keel/src/keel/webapp.py` — startup binding, readiness endpoints, graceful
  shutdown, signal handling (startup/shutdown/health/state-root code only;
  `/api/backend-workflows` and all workflow endpoints untouched).
- `keel/tests/test_stab_lifecycle.py` — new verification set, including the
  CLI `--confirm` policy regression.
- `keel/tests/test_stab_workflow_auth.py` — stale expectation for the fixed CLI
  bug updated.
- `keel/tests/test_security_remediation.py` — stale source-text assertion
  updated for the merged strict-confirm variable.
- `STAB-RUNTIME-EVIDENCE.md` — this file.
