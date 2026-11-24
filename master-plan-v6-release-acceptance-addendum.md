# Final-source Windows installer rebuild (completion operation addendum)

> **Update (final operation):** after the independent release audit found the original installer was built at `7fd9a6a` (43 commits behind final), it was rebuilt again from the true final integration HEAD `907f0d5` into `keel/release_final2/`. New SHA-256: **`C9500B06F3B2C996830765008F335D8BA9309E1D33B50A4EF3D240D847E88C08`**, size 141,180,133 bytes; `python -m keel.release integrity --dist dist --artifacts release_final2` → **7/7 passed**. The values below (`F12E1D66…`) are historical and no longer represent final source.

**Date:** 2026-11-23
**Branch / commit built:** `integration/v6-completion` @ `7fd9a6a` (final evidence commit; all implementation commits merged)
**Environment:** Windows 10 AMD64, Python 3.11.9, PyInstaller 6.19.0, Node v24.22.2, electron-builder (local `node_modules`)

## Result: BUILD PASS (unsigned)

Command:

```
cd keel
python -m keel.release build --platform windows --out release_final
python -m keel.release licenses --out release_final
python -c "from keel.release_integrity import regenerate_latest_yml; regenerate_latest_yml('dist','release_final')"
python -m keel.release integrity --dist dist --artifacts release_final
```

First build attempt failed with `PermissionError: [WinError 5] Access is denied: dist\keel-sidecar\keel.exe`. Root cause: two orphaned sidecars from earlier test runs (`keel.exe serve --port 8896/8897`, PIDs 22584/31404) held the file open. After stopping those orphaned processes, the build completed successfully (`BUILD_EXIT=0`). This is an environment hygiene issue, not a source defect; no source change was needed.

**Final-source artifact:**

| Property | Value |
| --- | --- |
| File | `keel/dist/Keel-Setup-0.1.1.exe` |
| Size | 141,118,394 bytes |
| SHA-256 | `F12E1D668EF9983F291CC2302FCD4A938327CFCD1B4DEF5E5A9BAC7C76C14054` |
| Previous (audited commit) artifact | 141,052,399 bytes, SHA-256 `CC455DE1...` — **different**, so the old installer must not be represented as final-source |
| Version | 0.1.1 (manifest + sidecar agree) |
| Signing | unsigned (no certificate configured; correctly skipped) |

`dist/latest.yml` was regenerated from the actual rebuilt artifact (the build command does not do this automatically) and the license inventory was generated with `keel.release licenses` (283 electron + 4 python packages; `cryptography`/`keyring` marked unresolved — honest reporting).

**Integrity verification (final):**

```
[OK] checksums: 7 files verified
[OK] manifest: version 0.1.1, 1 files
[OK] latest_yml: size and sha512 match artifact
[OK] sidecar_version: 0.1.1
[OK] dependency_inventory: 5 entries
[OK] secret_scan: no clear-text secrets
[OK] signature_paths: Ed25519 verify helpers present; production signing owner-gated
integrity: 7/7 passed
```

`python scripts/validate_desktop.py --dist dist` → `{'pass': 5, 'fail': 0, 'external_unverified': 6}` (clean artifact scan, packaged resources present, sidecar starts).

## Scope and limits

- This is a **build integrity** result only: the package was built from the final local commit and its hashes/manifest/scan are internally consistent. It is **not** a signing result and **not** a clean-VM install/upgrade/rollback result.
- No installation, launch, upgrade, rollback or uninstall was performed on this machine. The six external checks remain unverified with exact commands in `scripts/validate_desktop.py`.
- macOS and Linux packages were not built (no native runners on this host).
- Signing remains owner-gated; the unsigned installer must not be published as a production-signed release.
