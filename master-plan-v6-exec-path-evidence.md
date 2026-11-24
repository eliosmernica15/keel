# Master Plan v6 — Execution-path coverage evidence

Agent 18 (`agent/f-exec-paths`, base `cc6240e`). Scope: every route that can
execute arbitrary or untrusted code must pass the authoritative authorization
(permission tier **and** saved exec policy) **and** cross a native/process
sandbox boundary where a real one exists.

Enumeration performed with the `grep` tool over `keel/src` for
`subprocess.run/Popen/call/check_output`, `os.system/spawn/popen`, `eval(`,
`exec(`, `run_confined`, `run_python`, `create_task`, local task executors,
shell tools, codemods, notebooks, skills/plugins and MCP tools:

- **41** `subprocess.*` call sites,
- **2** real `exec(compile(...))` sites (`notebook.py`, `sandbox_policy.py`),
- **42** `run_confined` / `run_python` boundary references.

Nine capability-mediated routes that can reach a process were analyzed in
depth; six real gaps were found and fixed in owned files. Everything outside
the owned files is referred to the lead with an exact change request.

## A. Capability routes (product front door)

Policy = `capabilities.invoke` tier check + `policy_enforcement.enforce`.
Sandbox = `keel.os_sandbox.run_confined` (OS boundary) or
`keel.sandbox_exec.run_python` (Python audit-hook boundary).

| Route | file:line (current) | Policy enforced | Sandbox invoked | Fix applied / required change |
|---|---|---|---|---|
| `core.os.sandbox.run` (`argv`) | `capability_registry.py:670` | Before: **N** for `argv` (not a canonical policy field); hub tier = execute. After: **Y** | **Y** (`os_sandbox.py:241`, backend at 333) | FIXED: `exec_guard.enforce_command(..., field="argv")` normalises `argv` to `command` before `run_confined`. A saved `forbidden` rule now blocks the exact argv (test `test_saved_policy_binds_argv_route`). |
| `code.sandbox.run` (`code`) | `capability_registry.py:970` | Before: **N** for `code`; hub tier = execute. After: **Y** | **Y** (`sandbox_exec.py:60`, subprocess at 74) | FIXED: guard normalises `code`; unresolved `ask` now fails closed. Test `test_saved_policy_binds_code_route`. |
| `cowork.notebook.execute` (`source`) | `capability_registry.py:366` | Before: **N** for `source`; hub tier = execute. After: **Y** | **Y** (inside `notebook.execute_notebook` → `run_python`; `notebook.py:82` exec is *inside* the sandbox) | FIXED: guard normalises source. Test `test_saved_policy_binds_notebook_source_route`. |
| `code.debug.inspect` | `capability_registry.py:1020` | Before: **N** — declared `read`; path never policy-checked. After: **Y** — `execute` tier + guard on target path | Before: **N** (`debugger.py:52-60` ran arbitrary file code via `compile`+`bdb.run`). After: **Y** (source embedded as JSON in a bdb driver executed through `run_python`) | FIXED: tier raised `read` → `execute`; policy guard added; sandboxed driver preserves breakpoint/locals inspection. Existing `test_debugger.py` (direct module API) still passes. |
| `external.ci.run` | `capability_registry.py:1817` | Before: **N** — prompt in unrecognised field; hub tier = execute. After: **Y** | Before: **N** (`integrations.py:36` `subprocess.run([python, -m, keel, -p, prompt, ...])`). After: **Y** — `run_confined` in a fresh workspace | FIXED: handler builds the exact argv, calls `exec_guard.enforce_command`, then injects a confined transport into `CIAdapter`. `allow_network` defaults to True so a real headless run still works; returned `limitations` state where the platform has no network boundary. Mock path unchanged. |
| `core.secrets.has` | `capability_registry.py:142` | Before: **N** — read tier could trigger `CommandProvider.get` via local config. After: **Y** (read tier kept, exec provider filtered) | Before: **N** (`secret_providers.py:90` subprocess). After: **Y** (that provider is unreachable from this route) | FIXED: filter providers whose `describe()["kind"] == "exec"` before `resolve`. Test `test_read_tier_secret_lookup_does_not_spawn_command_provider`. Direct `CommandProvider` API remains opt-in. |
| `core.release.integrity` | `capability_registry.py:161`, `release_integrity.py:151-166` | **N** — read tier; fixed `dist/keel-sidecar/keel.exe --version` | **N** | REFERRED TO LEAD: execute a fixed local artifact, not model-supplied command text, but it is still a read-tier process spawn. Required change in `keel/src/keel/release_integrity.py:165`: route `verify_sidecar_version` through `os_sandbox.run_confined` with `workspace=dist` and fail closed, or split into an execute-tier capability. Not changed here (file not owned; `run_all` mixes file reads with the spawn). |
| `code.git.status` / `code.git.log` / `code.git.commit` | `capability_registry.py:926/933/941`, `git_extras_runtime.py:26` | **Y** for tier (read/read/write); policy sees no command (fixed argv via `git -C`) | **N** | ACCEPTED with documented rationale: argv-only, no shell, write commands gated by explicit `allow_write`. Not arbitrary/untrusted code execution. Redesign requires changing `git_extras_runtime.py` and would break repository writes; not in owned scope. |
| `code.api.run`, `release.webhook.send`, `cowork.email.send`, `cowork.channel.deliver` | `capability_registry.py:990/1730/401/1820` | **Y** — execute tier; URL checked by `policy_enforcement.url_from` | N/A (HTTP, no process) | No fix needed. |
| `core.config.inline_shell`, `core.config.editor_command`, `external.remote.cmd`, `external.wasm.cmd`, `external.container.cmd`, `external.image.cmd`, `code.browser.launch_cmd`, `code.model.load/runtime` | `capability_registry.py:52/59/1760/1769/1776/1787/1283/1912/1922` | **Y** (read tier for builders) | **N** (builders only — they return `args`; `browser_launch.launch` at line 68 and `model_runtime.start` at line 62 are *not* called by these handlers) | REFERRED TO LEAD: if a builder's returned argv is ever fed to a process by an outer agent, that consuming call site must apply tier + sandbox. Verify at the tool-consumer layer; no change needed in the builder handlers. |

## B. Non-capability execution sites (referred to the lead)

These are outside the files owned by Agent 18. Every one was read; the exact
required change is recorded here rather than being applied.

| Route | file:line | Policy enforced | Sandbox invoked | Exact required change for lead |
|---|---|---|---|---|
| Print-mode / session shell tools (`run_shell`, `run_tests`, `run_build`, `install_deps`, `background_shell`, `run_python`, `git_*`) | `runner.py:513, 532, 559, 577, 580, 604`; gate at `runner.py:364-369`, `1096`, `session.py:972` | **Y** (Tier-1 `permissions.evaluate` + Tier-2 `safety.tier2_check`) | **N** | In `keel/src/keel/runner.py`, replace `_run_python` (513), `_run_tests`/`_run_build` (532), `_install_deps` (559) and `_background_shell` (577/580) with `os_sandbox.run_confined` calls using a fresh workspace and an explicit `allow_network` from the tool input. `run_python` can alternatively use `sandbox_exec.run_python`. Keep the existing Tier-1/Tier-2 gates ahead of the boundary. |
| Print-mode workflows | `runner.py:728-739` | **Y** (`evaluate_noninteractive`) | **N** (inherits `RealTools`) | Fixed by the `runner.py` change above. |
| Fleet background shells | `fleet/shells.py:130`; caller `fleet/tools.py:319-328` | **Partial** — approval broker in `fleet/turn_core.py:350`, no direct `policy_enforcement` call in `shells.py`/`tools.py` | **N** | In `keel/src/keel/fleet/shells.py:130`, route `argv` through `run_confined` (fresh workspace, explicit network policy) before creating the `BackgroundShell` entry; add an explicit `policy_enforcement.enforce` call in `fleet/tools.py:_background_shell` using the canonical `command` field. |
| Desktop workflow API | `fleet/routes.py:1654-1664` | **Y** (`evaluate_noninteractive`) | **N** (inherits `RealTools`) | Fixed by the `runner.py` change above. |
| Hooks | `hooks.py:214-226` | **N** — hook command comes from user settings; no `policy_enforcement.enforce` call | **N** | In `keel/src/keel/hooks.py:221`, call `policy_enforcement.enforce("hook", {"command": hook.command})` and `os_sandbox.run_confined(argv, ...)`; fail closed on denial. Treat user settings as trusted config but still apply the saved policy. |
| MCP stdio servers | `mcp.py:149-168` | **Partial** — user config + `is_approved` gate in `fleet/turn_core.py:101-115` | **N** | In `keel/src/keel/mcp.py:163`, require an approved server and wrap the spawn in `run_confined` with a dedicated workspace; document that stdio MCP is a trusted local integration if sandboxing would break the protocol. |
| Web bridge sync/stream runs | `webapp.py:912`, `webapp.py:1333` | **Y** for token auth (`webapp.py:258-295`) and capability tier (`webapp.py:565`); `permission_mode` forwarded to child | **N** | In `keel/src/keel/webapp.py:900-914` and `1295-1333`, route the `python -m keel` argv through `run_confined` (fresh workspace, explicit network policy) instead of raw `subprocess`. |
| Automatic verification | `verification.py:17-45`; caller `session.py:1306-1309` | **N** — commands derived from project manifests; no policy call at the spawn | **N** | In `keel/src/keel/verification.py:43`, call `policy_enforcement.enforce` on the generated command and `run_confined(argv, ...)`; skip verification when the sandbox is unavailable. |
| `platform_gaps.LocalTaskExecutor.run` | `platform_gaps.py:259-267` | **Partial** — `submit` allowlist + `approved` flag, but no saved-policy call | **N** | In `keel/src/keel/platform_gaps.py:266`, call `policy_enforcement.enforce` with `{"argv": task["argv"]}` and `run_confined` before `subprocess.run`. Currently dormant (no capability calls it) but it is a real front-door candidate. |
| `secret_providers.CommandProvider.get` | `secret_providers.py:86-92` | **N** at the module boundary (config opt-in, key regex only) | **N** | Either require an execute-tier caller for every `resolve()` that can reach this provider, or add an optional `sandbox=` hook. The capability route was fixed by filtering it out; direct/config callers remain the lead's responsibility. |
| Release tooling | `release/common.py:161, 368`; `release_integrity.py:165` | **N** | **N** | These run build/release tooling against local artifacts. Add `run_confined` where the path can be influenced by a model-controlled capability. `release_integrity` is item A above. |
| OCR | `document_gaps.py:62-81` | **N** (no capability calls `ocr_image` today) | **N** | If `ocr_image` is exposed, add an execute-tier capability and `run_confined`. No change needed while it stays dormant. |
| Native isolation probes | `native_isolation.py:176, 206` | **N** (probe of user-supplied command) | **N** | Route probes through `run_confined` or clearly restrict to fixed argv. |
| Browser launch / model runtime start | `browser_launch.py:68`, `model_runtime.py:62` | **N** (opt-in helpers; builder capabilities do not call them) | **N** | Wrap `launch`/`start` in `run_confined` when invoked from a model-controlled route; keep opt-in user launches documented. |
| Shell AST probe | `shell_ast.py:606` | **N/A** — used for analysis/probing of parsed commands | **N** | Verify callers never feed model-controlled text without the normal Tier-1 gate. |
| Sandbox internals | `os_sandbox.py:307,333`; `sandbox_exec.py:74`; `sandbox_linux.py:643`; `sandbox_macos.py:189,398`; `sandbox_windows.py:542/631`; `sandbox_policy.py:129`; `notebook.py:82` | **Y** — these *are* the authoritative boundaries | **Y — this is the boundary itself** | No change. `notebook.py:82` and `sandbox_policy.py:129` execute inside a sandboxed child and are not unguarded host exec. |

## C. Tests and results

New file: `keel/tests/test_exec_path_coverage.py` (19 tests).

| Command | Result |
|---|---|
| `PYTHONPATH=<worktree>/keel/src python -m pytest tests/test_exec_path_coverage.py -q` | **19 passed in 2.05s** (18 exec-path tests + 1 audited additive best-of-N assertion) |
| `PYTHONPATH=<worktree>/keel/src python -m pytest tests/test_exec_path_coverage.py tests/test_security_validation.py tests/test_no_fake_success.py tests/test_policy_enforcement.py tests/test_debugger.py tests/test_notebook.py tests/test_concurrency_recovery.py tests/test_secret_providers.py tests/test_best_of_n.py -q` (after fixes) | **73 passed in 21.13s** |
| `PYTHONPATH=<worktree>/keel/src python -m pytest tests -q -k "capab or sandbox or exec or security or debugger or notebook or secret or policy or codemod or git or api or workflow"` | **247 passed, 46 skipped, 2 failed in 101.73s** — failures: `test_release_manifest_has_policy_fields` (worktree has no `keel/release/RELEASE-MANIFEST.json`, environment artifact) and `test_compat_runtime.py::test_tool_rejected_never_executes` (timing flake; passes alone: 1 passed in 2.10s). Neither touches changed code. |

Assertion coverage in the new tests:

- (a) all five command-bearing capabilities declare `execute` (helper asserts
  `execute`/`write` for every entry);
- (b) each is denied with `permission_denied` when only `read`/`write` is
  allowed;
- (c) spies confirm `run_confined` is called for `core.os.sandbox.run` and
  `external.ci.run`, and `run_python` for `code.sandbox.run` and
  `code.debug.inspect`;
- (d) saved forbidden policies now deny `argv`, `code` and notebook `source`
  routes *before* the sandbox spy is reached;
- (e) the read-tier secret lookup cannot spawn a configured command provider;
- (f) `test_best_of_n_hub_response_exposes_real_score` verifies the hub returns
  a numeric `score` and matching `evidence` for a deterministic candidate set
  (additive coordination fix, section E).

## E. Additive coordination fix: auditable best-of-N selection

Requested by the product-defect agent; no selection-logic change.

| Route | file:line | Change | Test |
|---|---|---|---|
| `duet.best_of_n` (`_bon`) | `capability_registry.py:1397` (handler at 1390) | The handler previously returned only `{"index", "value"}` although `keel.best_of_n.Candidate` already carries `score: float` and `evidence: str` (`best_of_n.py:14-20`). The dict now also includes `score` and `evidence` verbatim; the call into `best_of_n`, its generator and its selector are unchanged. | `tests/test_exec_path_coverage.py::test_best_of_n_hub_response_exposes_real_score` asserts `score == 0.9`, `isinstance(score, (int, float))`, `index == 1`, `evidence == "higher"`. Existing `tests/test_best_of_n.py` still passes. |

This makes "selected by real scoring" auditable through the capability hub
(the product's front door) without changing which candidate wins.

## D. Honest limitations

- On Windows, `run_confined` has no network boundary; `allow_network=True`
  (used by `external.ci.run` to preserve a real headless run) is reported in
  the capability result's `limitations`. All other sandbox routes default to
  `allow_network=False` and fail closed on Windows.
- The Python audit-hook sandbox is not kernel-level containment. OS-level
  confinement is only claimed where `os_sandbox.capabilities()` reports a
  real mechanism.
- The sandboxed debugger runs the target from embedded source under a virtual
  filename, so imports from the target's original directory and `__file__`
  semantics differ from the old unsandboxed `DebugSession`. This is an
  intentional security trade-off; the direct module API is unchanged.
