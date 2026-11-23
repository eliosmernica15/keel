# Master Plan v6 — Platform compatibility evidence

Baseline: `cc6240e` on `final/v6-production`. Environment: Windows 10 (10.0.26300-SP0), AMD64, Python 3.11.9, Node v24.22.2.

| Platform | Native sandbox backend | Native execution on this host | Lifecycle validation | Status |
| --- | --- | --- | --- | --- |
| Windows | restricted token + workspace ACLs + handle list + Job Object | Yes — real processes executed and adversarially attacked | Installer rebuilt from final source, 7/7 integrity; clean-VM install/upgrade/rollback not performed | PARTIAL |
| Linux | Landlock FS + seccomp-BPF network deny + no_new_privs + capability drop | No — Windows host; 16 tests platform-gated | No native runner | BLOCKED (external runner) |
| macOS | Seatbelt (`sandbox-exec`): write/network/rlimits; read isolation BLOCKED on macOS 26 | No — Windows host; 14 tests platform-gated | No native runner; unsigned DMG/ZIP only | BLOCKED (external runner) |

## Windows detail

- Full suite on integrated branch: 1296 passed, 46 skipped. Skips: 36 native-sandbox platform gates + 10 provider credential gates.
- Sandbox tests: 20 passed / 36 skipped (Linux/macOS/Windows-network gates).
- Independent red-team: real `cmd.exe` processes under the restricted token; outside reads/writes, `..` traversal, junction escape, child-process escape and timeout tree-kill all denied; no High/Critical findings.
- Windows network enforcement is **not** applied: default `allow_network=False` fails closed with `SandboxUnavailable`. This operation has a dedicated agent attempting a real non-elevated network boundary; see `master-plan-v6-win-network-evidence.md` when produced.
- Known host limitation: Python cannot launch under the restricted token on this host (`exit=0xC0000022`); `cmd.exe` does, and proves the boundary.

## Linux detail

- The prior `landlock_add_rule EINVAL` root cause (4th argument passed rule size instead of flags `0`) is fixed; ABI struct sizes and access-bit masks corrected.
- The inverted inline seccomp BPF filter (wrong opcode/offset/jumps) was fixed with a cross-platform regression test that simulates verdicts.
- Requires a Linux kernel ≥5.13 with Landlock and seccomp enabled; no such runner available locally.

## macOS detail

- Seatbelt backend integrated from the open PR branch; writes/network/rlimits confined.
- Read isolation BLOCKED on macOS 26 arm64: Apple's `sandbox-exec` aborts with SIGABRT for any path-filtered `file-read*` rule; reported honestly, never claimed as enforced.
- `sandbox-exec` is deprecated by Apple; App Sandbox is the supported replacement. No Electron entitlement is relied upon.

## Required external runners

1. Native Linux runner: `python -m pytest -q keel/tests/test_sandbox_linux.py keel/tests/sandbox_conformance.py`.
2. Native macOS runner (arm64 + Intel): `python -m pytest -q keel/tests/test_sandbox_macos.py`.
3. Clean VMs per OS for install / startup / upgrade / rollback / uninstall / user-data preservation (`scripts/validate_desktop.py` lists exact commands).
