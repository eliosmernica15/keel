# Master Plan v6 — Architecture map

**Baseline:** `cadb343e84db1a1cc5fa2bed584996c33b629a4b`

## Runtime boundaries

```
   Surfaces                       Front door                     Authoritative runtime
 -----------                    ------------                    ----------------------
 Electron shell (desktop-app) --\
 Local web UI (site/, desktop/ui) ---> token-auth HTTP bridge --\
 CLI (keel ... commands) -------------> capability hub (capabilities.py) ---> Python modules (src/keel/*)
 TUI (keel tui) ---------------------> 224 capabilities            ---> SQLite / JSON state (~/.keel)
                                            |
                                            +--> policy_enforcement -> exec_policy  (binding at boundary)
                                            +--> permissions.evaluate (Tier-1, fail-closed)
```

- **Python is authoritative.** Electron is a shell; the web UI, CLI and TUI all converge on the same token-authenticated Python runtime and the same capability hub.
- **Capability hub** (`capabilities.py` core + `capability_registry.py` registrations): 224 capabilities across surfaces code/core/cowork/desktop/duet/external/fleet/release/web, each with an id, module, surface, permission tier (read/write/execute), JSON input schema, and a real handler. Handlers import lazily. `invoke()` enforces permissions and saved execution policies and converts handler exceptions into explicit errors — no fake success.
- **Web bridge** (`webapp.py`): binds loopback 127.0.0.1 only; fresh random token per launch; Origin check for non-GET; `/api/*` token-gated; `/api/fs/list` returns directory names only; streams real `keel` runs as NDJSON.
- **Storage:** SQLite canonical DB plus JSON/JSONL state under a state root (`~/.keel`); backups use `VACUUM INTO`; outbox and capability audit are append-only JSONL.
- **Execution:** `sandbox_exec.py` (Python audit-hook boundary, isolated cwd), `native_isolation.py` (Windows Job Object / POSIX rlimits), `exec_policy.py` + `policy_enforcement.py` (Codex-derived host/command policy, fail-closed).

## Entry points per surface

| Surface | Entry point | Backend path |
| --- | --- | --- |
| CLI | `python -m keel` → `cli/main.py:main()` | `runner.py` print-mode + `capability` command → `capabilities.invoke` |
| TUI | `keel tui` → `tui.py:Tui` | capability hub `/capabilities`, `/invoke` |
| Web/PWA | `webapp.py:make_server()` | `/api/*` + capability endpoints |
| Desktop | `desktop-app/` Electron main → spawns sidecar | sidecar = packaged `keel` webapp |
| Fleet | `fleet/routes.py`, `fleet/` | workflow engine, event bus, approvals |

## Major cross-boundary workflows (traced in tests)

- **Code:** inspect → codemod preview → apply → git status → sandbox run (`test_workflows_e2e.py`).
- **Cowork:** document create/read/write/export + channel delivery to local outbox (`test_e2e_local.py`, `test_no_fake_success.py`).
- **Duet:** completion → reviewer/best-of-N → selection using deterministic adapters (`test_duet.py`, `test_best_of_n.py`).
- **Fleet:** workflow versions → event bus → anomaly detector → approvals (`test_e2e_operations.py`, `test_fleet_*`).
- **Policy:** saved exec policy → capability invocation denied at boundary (`test_policy_enforcement.py`, `test_exec_policy.py`).
- **Concurrency/recovery:** concurrent capability invocations, timeouts, backup/recovery (`test_concurrency_recovery.py`).

## Disconnected modules / duplication

- No runtime-critical module was found fully disconnected: the capability registry wires ~224 handlers, and documentation (`AGENTS.md`, `architecture.md`) matches the code layout. `scripts/` and docs directories are developer tooling, not runtime surfaces.
- Some legacy descriptor helpers exist alongside real implementations (e.g. `sandbox.py` descriptors vs `sandbox_exec.py`/`external_adapters.py` real logic; `knowledge_work.py` descriptor helpers). These are intentionally kept for backward compatibility and are honestly labelled; they are not advertised as the enforcement path.
- No circular-import defect observed at runtime (handlers import lazily; `permissions` imports `shell_ast` only; policy module delays the `Decision` import to avoid a cycle).

## Lifecycle / failure propagation

- Server startup generates a token and binds loopback; shutdown is handled per-server in tests. Sandbox workspace cleanup is in `finally`. Capability handler failures become `CapabilityError` with `handler_error` code rather than swallowed success.
- Known limitation: `enforce_admins=false` and public visibility are repository-level (C11.1/C11.2), not application architecture defects.

## Doc-vs-code match verdict

`AGENTS.md`, `architecture.md`, and `Keel_Master_Plan_v6.md` accurately describe the Python-authoritative, Electron-shell, SQLite, local-first design and the capability hub. No material doc-vs-code mismatch was found on the audited baseline.

## Completion operation — native execution architecture (post-audit)

The completion operation added a real OS-enforcement layer beneath the existing authorization layer:

```
  capability hub (authorization: permissions + exec policy)
        |
        +--> core.os.sandbox.capabilities   (honest mechanism/limitation report)
        +--> core.os.sandbox.run            -> os_sandbox.run_confined
                                                   |
                    +------------------------------+------------------------------+
                    |                              |                              |
             sandbox_windows.py            sandbox_linux.py              sandbox_macos.py
       restricted primary token +       Landlock FS + seccomp-        Seatbelt (sandbox-exec):
       workspace ACLs + handle list +   BPF net deny + no_new_        write/network/rlimits
       Job Object (no breakaway)        privs + capability drop       confined; read isolation
       network NOT enforced (fail       fail-closed preflight         BLOCKED on macOS 26
       closed when allow_network=False)                               (sandbox-exec SIGABRT)
```

- `os_sandbox.run_confined` dispatches to a dedicated backend for **every** supported OS. There is no permissive fallback: a backend that cannot establish its boundary raises `SandboxUnavailable`.
- A real defect was fixed here: on the audited/pre-integration code, the Windows branch of `os_sandbox.run_confined` started children with **no** restricted token or ACL (it only checked `windows_job_object` and then ran `subprocess.run`). The reviewed `sandbox_windows.py` backend (707 lines) existed on origin/main but was never dispatched. It is now the Windows path.
- A second real defect was fixed: the legacy inline seccomp BPF filter loaded opcode `0x00` at offset `4` with an intervening `ja`, inverting the branch so network syscalls would be allowed and all others denied. It now uses opcode `0x20` at offset `0` with `jt=0/jf=1` jumps, and a cross-platform regression test simulates filter verdicts.
- Capability count grew from 224 to 226 (`core.os.sandbox.capabilities`, `core.os.sandbox.run`), both permission-tagged (`read`/`execute`). All 226 capability IDs are unique; all referenced modules import.
- Native execution evidence: real Windows restricted-token filesystem denial passes; network denial is unavailable and fails closed; macOS write/network confinement works while read isolation is honestly BLOCKED; Linux Landlock/seccomp cannot be executed on this Windows host and remains environment-gated.
