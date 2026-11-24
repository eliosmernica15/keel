# Master Plan v6 — Supply-chain evidence

Baseline: `cc6240e` on `final/v6-production`. All values below were re-verified in this operation.

## Version consistency

| Source | Version |
| --- | --- |
| `keel/pyproject.toml` | 0.1.1 |
| `keel/desktop-app/package.json` | 0.1.1 |
| `keel/src/keel/__init__.py` | 0.1.1 |
| `keel/src/keel/release/__init__.py` | 0.1.1 |
| `keel/desktop/src-tauri/Cargo.toml` | 0.1.1 |

Command: `python scripts/check_version_sync.py` → `OK - all sources agree on version 0.1.1 (tag v0.1.1)`.
The prior Cargo.toml / release / MCP version drift was fixed by agent commit `cdc41ca` with regression tests.

## GitHub Actions pinning

Local integration tree: 4 workflow files, **20 SHA-pinned** `uses:` refs, **0 tag-pinned** refs. All five distinct SHAs were independently re-resolved with `git ls-remote` against their upstream repositories.

Live repository `main` (read-only `gh api`): **23 tag-pinned refs across 7 workflows, 0 SHA-pinned**. Three workflows (`lifecycle.yml`, `provider-validation.yml`, `signing-readiness.yml`) exist only on the divergent `origin/main` branch and were not part of the local pinning change. The local branch has not been pushed. This distinction is an independent-review finding and is recorded in `master-plan-v6-repository-security-evidence.md`.

## Secret scanning and hygiene

- `.gitleaks.toml` present with scoped allowlists and `useDefault = true`.
- `.pre-commit-config.yaml` pins gitleaks `v8.30.1` with `--redact`.
- Fail-closed `.githooks/pre-push` enforces no-direct-main-push, gitleaks, and the version gate (installed via `git config core.hooksPath .githooks`).
- gitleaks binary is not installed on this host; the hook blocks pushes in that state (verified).

## Release artifacts (rebuilt from final source)

| Artifact | Size | SHA-256 |
| --- | --- | --- |
| `Keel-Setup-0.1.1.exe` (rebuilt at final HEAD `907f0d5`) | 141,180,133 | `C9500B06F3B2C996830765008F335D8BA9309E1D33B50A4EF3D240D847E88C08` |

The earlier `F12E1D66…` artifact was built at `7fd9a6a` (43 commits behind final); it is historical and no longer represents the audited source.
| `Keel-Setup-0.1.1.exe.blockmap` | 147,831 | `6CDDA7195772785923487B2D4D3D7A382F73DADDAB994DEA5A6DED8D4A0160B1` |
| `keel-app.jpg` | 44,343 | `FDA6540B1A25E8AC693C3BDF38885395D98383051ED77345E20C2A67A83AFC82` |

Command: `python -m keel.release integrity --dist dist --artifacts release_final` → **7/7 passed** (checksums, manifest, latest.yml, sidecar version, dependency inventory, secret scan, signature paths). Unsigned; signing remains owner-gated.

`python scripts/validate_desktop.py --dist dist` → `{'pass': 5, 'fail': 0, 'external_unverified': 6}`.

## Dependency inventory

`python -m keel.release licenses --out release_final` produced a 5-entry inventory (283 electron packages, 4 Python packages; `cryptography`/`keyring` marked unresolved — reported honestly). The generator and consumer paths were unified by agent `cdc41ca` (`keel/release/DEPENDENCY-LICENSES.json`).

## Limits

- No SBOM signed provenance attestation (no signing identity).
- Live publish workflow not exercised (owner-gated).
- macOS/Linux artifacts not built on this Windows host.
