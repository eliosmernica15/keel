# Master Plan v6 — Security findings

**Baseline:** `cadb343e84db1a1cc5fa2bed584996c33b629a4b`
**Date:** 2026-11-23
**Scope:** permission/policy enforcement, execution routes, secret isolation, sandbox enforcement status, C11.1/C11.2 owner gates, red-team observations.

## 1. Permission and policy enforcement — VERIFIED

- `permissions.py` implements the Tier-1 evaluator with pinned order deny → ask → allow → mode policy. Unknown tools fail closed (`Decision("deny", ...)`); non-interactive `ask` resolves to deny.
- `policy_enforcement.py` is called **at real runtime boundaries**: from `permissions.evaluate()` and from `capabilities.invoke()` *before* any command or URL handler runs. Saved `forbidden` policies deny; `prompt` policies deny without interactive confirmation; `bypassPermissions` mode cannot widen a saved deny.
- Live probe: `invoke("code.sandbox.run", ..., allowed_permissions={"read"})` → `permission_denied`. Enforcement is real, not documentation.
- `test_security_validation.py`, `test_exec_policy.py`, `test_policy_enforcement.py` pass (see test evidence).

## 2. Secret isolation and redaction — VERIFIED

- `channel_ops.deliver_to_outbox()` writes a genuine local outbox record (`status: queued_local`) and explicitly does not claim online delivery; no fake success.
- `test_no_fake_success.py` asserts channel delivery really writes the outbox and that the CI mock is explicitly labelled (`mock=True`, "not a real run"). Default `external.ci.run` invokes the real local CLI.
- `redaction.py` redacts keys (e.g. `sk-…`) before provider/egress logging; `test_secret_redaction_in_provider_context` passes. The sandbox scrubs credential-like environment variables.
- "Sign out everywhere / revoke all tokens" (A3.6) and local secret providers (A4.7) are real local modules. No credential was exposed during this audit.

## 3. Sandbox enforcement status — HONEST PARTIAL (not OS-level)

This is the most important security clarification. The audited baseline provides **bounded local execution with an isolated working directory and a Python audit-hook boundary**, but **not OS-level containment**.

| Mechanism | Present on baseline? | What it actually enforces |
| --- | --- | --- |
| Isolated temp cwd + `subprocess` | Yes | Relative file ops confined to a fresh temp dir; guaranteed cleanup |
| Python `sys.addaudithook` policy (`sandbox_policy.py`) | Yes | Denies file access outside workspace/stdlib, process creation, native loading, network — for Python-level operations |
| Scrubbed environment | Yes | Credential-like variables removed |
| Wall-clock / output / POSIX memory+CPU limits | Yes | Resource bounds |
| Windows Job Object (`native_isolation.py`) | Yes | Active-process, CPU, memory limits; kills descendant tree on timeout. **No network/filesystem isolation.** |
| POSIX rlimits (`native_isolation.py`) | Yes | CPU/AS/NPROC/FSIZE limits |
| Landlock + seccomp-BPF (Linux) | **No on this baseline** | Exists only on origin/main (PR #10/#11), not audited |
| macOS Seatbelt / sandbox-exec | **No on this baseline** | Origin/main reports launch failure BLOCKED and open PR #15 is BLOCKED for read isolation |
| Windows restricted token / AppContainer | **No on this baseline** | Exists only on origin/main (PR #13) |

Honesty evidence in code and tests:
- `sandbox_exec.py` docstring: "this is a Python-level boundary, not OS-level containment."
- `native_isolation.platform_support()`: `"network_isolation": False`, note "Native process/resource limits only; not full OS sandboxing."
- `test_native_isolation.py` asserts those honest values.
- `test_sandbox_hardened.py` asserts `sandbox_status()["os_level_isolation"]["seccomp_apparmor_containers"] is False`.

**Red-team verdict:** a sandboxed Python subprocess cannot escape its isolated cwd via relative paths, cannot create processes or open network sockets through the audit hook, and inherits no credentials. Native code and kernel-level attacks are not prevented. This is correctly classified as a local_module with an honest boundary, **not** as full OS sandboxing. No false enforcement claim was found.

## 4. C11.1 / C11.2 — OWNER-GATED (live read-only evidence)

Live `gh api` inspection (read-only; token scopes `repo`, `read:org`, `workflow`) on repo `eliosmernica15/keel`:

| Setting | Observed value | Plan requirement | Status |
| --- | --- | --- | --- |
| Repository visibility | **`public`** (`private: false`) | v5 §0.1: source repo **must be private** | **VIOLATION — owner decision required (C11.1)** |
| Default branch | `main` | — | OK |
| PR reviews required on main | `true` | C11.2 | OK |
| Required status checks on main | 8 checks: validate-versions, build-windows/macos/linux, pytest (ubuntu/windows/macos), gitleaks (full history) | C11.2 | OK |
| Allow force pushes | `false` | C11.2 / gate G2 | OK |
| Allow deletions | `false` | C11.2 / gate G2 | OK |
| Enforce admins | `false` | C11.2 (admins can bypass) | GAP |
| Commit signature protection | `null` (not enforced) | C11.2: signed commits | GAP |
| Actions pinned by commit SHA | **No** — all 20 `uses:` are tag-pinned (`@v7`/`@v8`) | C11.2: Actions pinned by SHA | GAP |
| Forks restricted / disabled | `allow_forking: null`; public repo permits forks | C11.2: forks disabled | GAP |
| Mandatory 2FA, least-privilege tokens, environment secrets with required reviewer, access-review checklist | Not verifiable via available API | C11.2 | UNVERIFIED |

**No change was made.** Changing repository visibility, branch protection, collaborators, or security settings is an explicit owner gate (v5 §0.3 gates G1/G2/G4; mission §9). These are reported, not actioned. C11.1 and C11.2 remain classified `OWNER_BLOCKED` / `blocked`.

## 5. Remaining risks

- Repo is public — the single highest-priority owner decision (C11.1).
- C11.2 security hygiene partly unmet (SHA pinning, signature enforcement, admin enforcement, forks, 2FA).
- OS-level sandbox enforcement absent on the audited baseline; present only on divergent origin/main work that still reports macOS as BLOCKED.
- Real provider behaviour unverified (no credentials); clean-VM and cross-OS native verification not locally executable.
- No critical/high **code** defect requiring an implementation fix was found in the audited baseline; working functionality was preserved rather than churned.

---

## Completion operation — security changes after the audit

### Native OS enforcement (was: honest partial)

The audited baseline had only Python-level isolation. The completion operation integrated real OS backends (origin/main reviewed work) and fixed two integration defects (see `master-plan-v6-architecture-map.md`):

| OS | Enforcement on integrated branch | Evidence |
| --- | --- | --- |
| Windows | Restricted primary token + workspace-only ACLs + restricted handle inheritance + Job Object. Filesystem denial proven with real child processes. **Network is NOT enforced** — default `allow_network=False` fails closed with `SandboxUnavailable`. | `tests/test_sandbox_windows.py`, live capability probe |
| Linux | Landlock filesystem + seccomp-BPF network deny + `no_new_privs` + capability drop + rlimits; fail-closed preflight. Inverted BPF filter fixed. | `tests/test_sandbox_linux.py` (cannot execute on Windows host — environment-gated) |
| macOS | Seatbelt: writes/network/rlimits confined; read isolation BLOCKED on macOS 26 by `sandbox-exec` SIGABRT, reported honestly. | `tests/test_sandbox_macos.py`, PR #15 evidence |

Live Windows probe on the integrated branch:

```
capabilities() -> filesystem_enforcement: True, network_enforcement: False,
                 windows_restricted_token: True, windows_job_object: True
core.os.sandbox.run with allowed_permissions={'read'} -> permission_denied
core.os.sandbox.run (default, no network opt-in) -> SandboxUnavailable (fail closed)
core.os.sandbox.run with allow_network=True -> ok=True,
                 mechanism='windows-restricted-token+workspace-acl+job-object'
```

### Repository governance (C11.1/C11.2)

- **C11.1: PASS.** Owner explicitly confirmed, repo switched to private and live-verified; only the owner collaborator; all 7 Actions workflows remain active.
- **C11.2: PARTIAL / owner-and-plan gated.** The free private plan removed branch protection (403/404/422 on live API) — the exact caveat C11.1 predicted. Tag→SHA pinning of all 20 Actions references is PASS. A fail-closed local pre-push hook was added (no direct pushes to main, gitleaks, version gate); executing it locally showed it blocks because gitleaks is not installed. Signed commits, admin enforcement, fork disabling, and 2FA remain owner/plan actions. See `master-plan-v6-repository-security-evidence.md`.

### Supply chain

All 20 workflow `uses:` references are pinned to verified full commit SHAs (independently re-resolved via `git ls-remote`). Version drift defects were fixed (Cargo.toml, release/MCP version constants, installer-name derivation, SBOM license path) with regression tests; `python scripts/check_version_sync.py` passes. No workflow logic or protection was weakened.

### Remaining security weaknesses

- Windows network denial unavailable (requires admin firewall rule or AppContainer with elevated privileges).
- Linux/macOS native enforcement not executable on this Windows host.
- macOS read isolation BLOCKED by a host `sandbox-exec` regression.
- Branch protection absent on the free private plan; local compensating controls are not remote-enforced.
- No signing identity and no provider credentials in the environment.

### Independent red-team outcome (post-integration)

An independent red-team agent executed real confined processes against the Windows backend (outside read/write, `..` traversal, junction escape, child-process escape, secret env inheritance, timeout tree-kill, fail-closed checks, and BPF simulation). All forbidden filesystem and process actions were denied; both BPF builders map network syscalls to EPERM with zero mismatches; the default `allow_network=False` fails closed at backend, dispatcher and capability levels. No High/Critical vulnerability was found. Full evidence: `master-plan-v6-sandbox-verification.md`.

Two Low findings were accepted with explicit rationale rather than churning working security code:

- **F-02 (Low) — heuristic environment scrubbing.** An opaque-named variable (no secret-like substring in its name) is inherited. This is the documented division of labour: OS confinement provides process/filesystem/network isolation, while secret scrubbing belongs to the policy layer (`redaction.py` / `sandbox_policy.child_env`), whose hint-based tests pass. Changing the OS backend's environment handling would not fix unknown-name secrets and could break interpreter startup.
- **F-03 (Low) — transient workspace ACL widening.** The Windows backend grants the restricted SID (Everyone) `GENERIC_ALL` on the workspace for the run and restores the directory DACL afterwards; child objects created in the window can retain the inherited ACE. The default workspace is a fresh per-run temp directory, so exposure is normally empty, and no data escape was observed. Callers that pass a persistent/sensitive workspace should instead supply a disposable per-run directory. Rewriting the ACL propagation logic was rejected as a high-risk change to proven filesystem denial for a Low, environment-bounded finding.
