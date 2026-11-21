# Keel — Windows external validation package

This package is for a **clean Windows machine** that does not have Keel
installed. It validates the real installer, desktop app, Python sidecar,
persistence, upgrade, rollback and uninstall. Nothing in this repository runs
these steps on the owner's machine — that would require explicit approval.

## 1. Artifacts (from `release/`)

| File | Purpose |
| --- | --- |
| `Keel-Setup-0.1.0.exe` | Prior version (upgrade source) |
| `Keel-Setup-0.1.1.exe` | Candidate version under test |
| `RELEASE-SHA256SUMS.txt` | Canonical SHA-256 sums |
| `RELEASE-MANIFEST.json` | Version, file sizes, hashes, update policy |
| `DEPENDENCY-LICENSES.json` | Third-party dependency inventory |

Run locally before transferring:

```
python -m keel.release integrity --dist dist --artifacts release
python scripts/validate_desktop.py --dist dist
```

Expected: all 7 integrity checks OK; 5 local desktop checks PASS; 6 external
checks explicitly listed as unverified.

## 2. Verify checksums on the clean machine

PowerShell:

```powershell
Get-FileHash .\Keel-Setup-0.1.1.exe -Algorithm SHA256
Get-Content .\RELEASE-SHA256SUMS.txt
```

The hash must match the line for `Keel-Setup-0.1.1.exe` exactly.

## 3. Silent install to an isolated directory

```powershell
.\Keel-Setup-0.1.1.exe /S /D=%LOCALAPPDATA%\KeelValidation
```

Expected:
- `%LOCALAPPDATA%\KeelValidation\Keel.exe` exists.
- `%LOCALAPPDATA%\KeelValidation\resources\keel\keel.exe` exists (sidecar).
- No UAC prompt when installing to a per-user path (no admin required).

Do **not** use the owner's existing install directory (`%LOCALAPPDATA%\Programs\Keel`).

## 4. Desktop startup and backend lifecycle

1. Launch `%LOCALAPPDATA%\KeelValidation\Keel.exe`.
2. Expect the Keel window to open; a bundled `keel.exe serve` child process
   starts on a loopback port.
3. Confirm backend only listens on loopback (`127.0.0.1` / `::1`):
   ```powershell
   Get-NetTCPConnection -OwningProcess <sidecar-pid> | Select-Object LocalAddress,LocalPort
   ```
4. Close the window. The sidecar process must exit (no orphan backend).

## 5. User data, settings and profiles

1. Open Settings and save a UI preference (e.g. theme).
2. Open the Modules browser (Ctrl+Shift+M), invoke `core.hardware.detect`.
3. Create a profile named `work`, then restart the app.
4. Expected: theme, profile and `capability-audit.jsonl` persist under the
   user data directory; no secret material is written to logs.

## 6. Upgrade and rollback

Upgrade:
```powershell
.\Keel-Setup-0.1.0.exe /S /D=%LOCALAPPDATA%\KeelValidation
.\Keel-Setup-0.1.1.exe /S /D=%LOCALAPPDATA%\KeelValidation
```

Rollback check: start the app three times with a deliberately broken state
(e.g. corrupt a non-critical settings file) and confirm `start_health` flags
rollback after three failed starts; restore the backup and verify recovery.

## 7. Uninstall

Run the uninstaller under `%LOCALAPPDATA%\KeelValidation` (or Settings →
Apps → Keel). Expected: installed files removed; user data intentionally
retained unless the uninstaller explicitly asks to remove it.

## 8. Troubleshooting

| Symptom | Check |
| --- | --- |
| Installer refuses to run | Verify SHA-256; check SmartScreen/Defender quarantine |
| App window opens but no backend | Check bundled `keel.exe` exists and event logs |
| Backend unreachable | Confirm loopback-only binding and no proxy env vars |
| Settings lost on restart | Check user data dir permissions |
| Upgrade fails | Remove only the validation directory, reinstall 0.1.0 then 0.1.1 |

## 9. What remains owner/external gated

- Production code signing (no certificate is configured here).
- GitHub release publication and visibility (owner approval required).
- Clean-VM execution of sections 3–7 (not run on the owner's machine).
