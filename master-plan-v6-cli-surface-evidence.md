# Agent 27 — CLI/TUI surface validation and hardening evidence

**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\final\cli-surface`
**Branch:** `agent/f-cli-surface` · **Baseline:** `463481e`
**Owned files changed:** `keel/src/keel/cli/main.py`, `keel/src/keel/tui.py`,
`keel/tests/test_cli_surface_hardening.py` (new). This evidence file is new.
`keel/src/keel/cli_extras.py` was inspected but needed no change.

## Method

Every CLI command below was executed as a real subprocess
(`python -m keel …`) with:

- `PYTHONPATH` pinned to this worktree's `keel/src` (the editable install in
  this environment otherwise points at `C:\Users\Admin\Desktop\Claude clone\keel\src`);
- a fresh temporary cwd and `KEEL_STATE_DIR` per probe (no user state touched);
- no provider credential values left in the environment for the secret scan.

Helper probes live outside the repository in
`C:\Users\Admin\AppData\Local\Temp\opencode\run_*_probe.py`.

## 1. Commands exercised (exact observed output)

Baseline command matrix — 43 invocations, including `--help`, `--version`,
`capability list/describe/invoke`, `provider list`, `execpolicy help/list/active`,
`tui --help`, and every top-level command group's `--help`. Representative
exact outputs:

| Command | Baseline rc | Baseline stdout / stderr (verbatim) |
| :-- | --: | :-- |
| `keel` | 1 | stdout `''`; stderr `[keel:cli_validation] {"errors":"a prompt is required (-p/--print or a positional argument)"}\n` |
| `keel --help` | **1** | stdout `''`; stderr `[keel:cli_validation] {"errors":"unknown option: --help"}\n` |
| `keel -h` | **1** | stdout `''`; stderr `[keel:cli_validation] {"errors":"unknown option: -h"}\n` |
| `keel --version` | 0 | stdout `keel 0.1.1\n`; stderr `''` |
| `keel version` | 0 | stdout `keel 0.1.1\n`; stderr `''` |
| `keel capability list --surface core` | 0 | 58 sorted `core.*` rows, e.g. `core.hardware.detect                   [core/read] Detect local hardware capabilities` |
| `keel capability describe core.hardware.detect` | 0 | JSON with `id`, `module`, `surface`, `permission: read`, `description`, `input_schema`, `mutates: false` |
| `keel capability describe no.such.cap` | 1 | stderr `unknown capability: no.such.cap\n` |
| `keel capability invoke core.hardware.detect --params {}` | 0 | JSON envelope `{"ok": true, "capability": "core.hardware.detect", "result": {"os": "Windows", "arch": "AMD64", "cpu_count": 16, "ram_gb": null, "python": "3.11.9"}, "elapsed_ms": …}` |
| `keel capability invoke core.flags.set --params {"name":"x","enabled":true}` | 1 | stderr `core.flags.set requires --confirm (write)\n` |
| `keel capability invoke no.such.cap` | 1 | stderr `unknown capability: no.such.cap\n` |
| `keel capability invoke core.hardware.detect --params not-json` | 1 | stderr `--params must be valid JSON\n` |
| `keel provider list` | 0 | JSON array of 5 providers (`openrouter`, `nvidia`, `google`, `anthropic`, `openai-compatible`); `configured: false`, `key_source: null`, `key_hint: null` for all |
| `keel provider --help` | 0 | stderr listed only `list` and `smoke` — **`validate` missing** although implemented and documented |
| `keel provider validate` | 0 | JSON `{"providers": {…}}` with static PASS/SKIP checks; no live calls |
| `keel execpolicy list` | 0 | stdout `[]\n` |
| `keel execpolicy active` | 0 | stdout `{"active": false, "fingerprint": null}\n` |
| `keel execpolicy check <policy.json>` | **1** | stdout `''`, stderr `''` — silent failure |
| `keel execpolicy network <policy.json>` | **1** | stdout `''`, stderr `''` — silent failure |
| `keel tui --help` | 0 | stderr `usage: keel tui  (interactive terminal UI)\n` |
| `keel doctor` | **0 (wrong behavior)** | stdout `Keel scaffold: no model provider is wired yet. This run used the built-in scripted fake.\n`; stderr contained MCP/provider diagnostics — the *model loop and MCP startup* ran instead of the local readiness builtin |
| `keel doctor --help` | **1** | stderr `[keel:cli_validation] {"errors":"unknown option: --help"}\n` |
| every other group `--help` (`init`, `tools`, `settings`, `notebook`, `spec`, `docpack`, `vault`, `repoindex`, `openapi`, `webhook`, `gateway`, `model`, `costs`, `session`, `attach`, `serve`, `fleet`, `skills`, `mcp`, `secrets`, `capability`) | 0 | correct per-command usage text on stderr |

Capability-hub ↔ CLI coverage: `capability_registry.py` registers 224 real
capabilities; all are reachable through `capability list/describe/invoke` on the
CLI and `/capabilities` + `/invoke` in the TUI. No capability route was found
that lacks an intended surface; the defects were in the *behavior* of those
surfaces, not a missing command family.

## 2. Permission / policy interaction probes

Saved `KEEL_STATE_DIR/exec-policies/default.json` with a `prompt` rule for
`ssh deploy …`, then invoked the read-tier capability `external.remote.cmd`
with `{"kind":"ssh","location":"host","command":"ssh deploy now"}`:

- **Before fix**, with and without `--confirm`, both runs failed identically:
  `rc 1`, stderr
  `policy_denied: execution policy denied external.remote.cmd: policy requires consent for 'ssh deploy now'; no interactive approval in this mode`.
  The CLI's `--confirm` never reached `capabilities.invoke`'s
  `context["confirm"]`, which the web bridge already passes
  (`webapp.py:582`).
- **After fix**: without `--confirm` → `rc 1` with the same denial; with
  `--confirm` → `rc 0`, stdout
  `{"ok": true, "capability": "external.remote.cmd", "result": {"args": ["ssh", "host", "ssh deploy now"]}, "elapsed_ms": 0.0}`.

TUI probe, `Tui(input_fn=lambda _: "n")`, command
`/invoke core.flags.set {"name":"probe","enabled":true}`:

- **Before fix**: `rc 0`, output `{"enabled": true, "kill_switch": false}`,
  and `state/feature-flags.json` was created — the mutating capability ran
  with the user answering "no", and no capability-audit entry was written.
- **After fix**: output `[cancelled] core.flags.set not invoked`, no flag file,
  no audit entry. With `input_fn` returning `y`, the capability runs, writes the
  flag file, and appends `{"capability": "core.flags.set", "ok": true,
  "surface": "tui", "ts": …}` to `capability-audit.jsonl`.

TUI policy probe with the saved `prompt` policy: answering `n` cancels before
invocation; answering `y` passes `confirm=True` and `interactive=True` so the
command descriptor is produced. A `forbidden` rule still fails closed via
`CapabilityError(policy_denied)`.

Malformed saved policy (`default.json` = `{not json`):

- **Before fix**: `keel capability invoke core.hardware.detect --params {}` →
  `rc 1` with a multi-frame `Traceback (most recent call last)` ending in
  `json.JSONDecodeError` from `policy_enforcement.enforce`.
- **After fix**: `rc 1`, stderr
  `policy_error: JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)`,
  and a failed audit record with `code: policy_error`. The TUI prints the same
  fault as `[error] JSONDecodeError: …` and never raises out of the command loop.

## 3. Secret disclosure scan

With `KEEL_OPENROUTER_API_KEY=SUPERSECRETVALUE123`,
`KEEL_WEBHOOK_SECRET=WEBHOOKSECRET456`, `KEEL_TOKEN=TOKENSECRET789` set in the
subprocess environment, the exact strings were searched for in stdout+stderr of:
`--help`, `provider list`, `doctor`, `secrets providers`,
`secrets has KEEL_WEBHOOK_SECRET`, `capability invoke core.cli.env`,
`capability invoke core.config.reference`. **No leaks in any of the 7 commands.**
`doctor` prints `<set N chars>`/`<unset>`; `core.cli.env` and
`core.config.reference` report only set/empty state.

## 4. Defects fixed (minimal changes)

1. **Top-level help missing** (`cli/main.py`): `keel --help`, `-h`, `help` were
   parsed as invalid prompt options. Added a top-level usage block listing all
   command groups; prints to stdout, exits 0. Bare `keel` still exits 1 with
   the original prompt-required error (exit-code behavior preserved).
2. **`keel doctor` registration gap** (`cli/main.py`): the command is advertised
   in `Keel_Master_Plan_v6.md` but fell through to `parse_argv`, causing a fake
   model run and MCP startup. Now dispatches to the existing local
   `commands.execute_builtin("doctor", …)`; `--bundle` retains its original
   path, and `doctor --help` now exits 0 with an accurate usage line.
3. **Misleading provider help** (`cli/main.py`): added the already-implemented
   `keel provider validate [--live]` line.
4. **`--confirm` ignored by the CLI invoke path** (`cli/main.py`): the flag now
   sets `context["confirm"]` (and `context["interactive"] = False`) passed to
   `capabilities.invoke`, so an explicit confirmation satisfies a saved
   policy's `prompt` rule instead of being denied.
5. **Unhandled traceback on a broken saved policy** (`cli/main.py`): CLI invoke
   now catches `OSError`/`ValueError` from pre-handler policy enforcement,
   writes an auditable `policy_error`, and exits 1 with a one-line message.
6. **TUI `/invoke` permission bypass** (`tui.py`): mutating capabilities now
   require an explicit interactive confirmation through the pluggable
   `input_fn`; saved-policy `prompt` rules also trigger a confirmation probe.
   Declines cancel before any handler runs. `confirm`/`interactive` are passed
   to `invoke`, success and failure are audited with `surface: "tui"`, and
   unexpected faults are rendered as clean `[error]` lines rather than
   tracebacks.
7. **Silent `execpolicy check`/`network` failures** (`cli/main.py`): missing
   operands now print a specific error line while keeping exit code 1.

No speculative commands were added; all fixes wire or correct existing code.

## 5. Tests

New regression file `keel/tests/test_cli_surface_hardening.py` (9 tests) was
written first. On the initial run of its first 8 tests, **7 failed and 1 passed**
(the passing one guards the already-correct CLI audit behavior); the ninth
(malformed-policy traceback) was added after the direct probe above confirmed
the traceback on the unfixed code. After the fixes: **9/9 pass**.

Targeted suites (all green):

```
$ python -m pytest -q tests/test_cli_e2e.py tests/test_capability_cli_tui.py \
    tests/test_commands.py tests/test_tui_functional.py \
    tests/test_cli_surface_hardening.py
27 passed in 44.85s
```

Full worktree suite:

```
7 failed, 1311 passed, 49 skipped in 537.82s
```

The 7 failures are pre-existing/environmental and outside the owned files:
6 require generated `keel/release/` artifacts absent from this worktree
(`test_distribution_package` ×2, `test_gap_closure` ×2,
`test_release_integrity`, `test_plan_index` source-hash), and one async Fleet
approval test (`test_tool_requires_approval_then_approved_runs`) timed out once
but **passed on immediate re-run** (19 passed / 6 environmental failures in the
targeted re-run). No CLI/TUI test regressed.
