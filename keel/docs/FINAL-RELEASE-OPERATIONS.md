# Keel — final release operations (operator runbook)

**Verified state: 2026-11-23.** This runbook describes what the repository actually
does, not a target state. Source of truth: `.github/workflows/build-desktop.yml`,
`.github/workflows/signing-readiness.yml`, `keel/scripts/validate_desktop.py`,
`keel/docs/release/SIGNING-PREPARATION.md`, and the root
`master-plan-v6-*.md` evidence files (especially `master-plan-v6-final-report.md`,
`master-plan-v6-release-acceptance{, -addendum}.md`,
`master-plan-v6-platform-compatibility.md` and
`master-plan-v6-win-network-evidence.md`).

> **Not a production release.** C11.1 source hosting is PASS (private,
> owner-confirmed), but C11.2 repository security is **PARTIAL / owner-gated**, the
> installers are **unsigned**, no provider credentials or signing identity exist, and
> no clean-VM or native Linux/macOS validation was performed. Nothing was pushed,
> published, signed or deployed. Do not describe C11.2 as complete or the build as
> production-ready. No trademark registration or brand-protection claim is made;
> legal texts and the D6 name check remain owner actions.

---

## 1. Build from source (exact CI commands)

All build steps run with **`keel/` as the working directory**. Python 3.11, Node 22
are pinned by CI.

### Version gate (runs before every build job)

```bash
cd keel
python scripts/check_version_sync.py
# on a v* tag: python scripts/check_version_sync.py --tag "${GITHUB_REF#refs/tags/}"
```

`python -m pytest -q -o faulthandler_timeout=90` on the final integrated branch gave
**1296 passed, 46 skipped** (audited baseline 1270 passed, 10 skipped). The skips are
36 native-sandbox platform gates and 10 provider-credential gates. Version is **0.1.1**
everywhere (`keel/__init__.py`, `pyproject.toml`, manifest, sidecar).

### Windows (`windows-latest`, PowerShell)

```powershell
cd keel
python -m pip install --upgrade pip
pip install -e . pyinstaller pillow
python -m keel.release build --platform windows --out release
python -m keel.release licenses --out release
```

### macOS (`macos-latest`, shell)

```bash
cd keel
python -m pip install --upgrade pip
pip install -e . pyinstaller pillow
python -m keel.release build --platform macos --out release
python -m keel.release licenses --out release
```

### Linux (`ubuntu-latest`, shell)

```bash
sudo apt-get update
sudo apt-get install -y libarchive-tools desktop-file-utils rpm
cd keel
python -m pip install --upgrade pip
pip install -e . pyinstaller pillow
python -m keel.release build --platform linux --out release
python -m keel.release licenses --out release
```

Each job uploads `keel/release/**` as its platform artifact (`keel-windows`,
`keel-macos`, `keel-linux`). `electron-builder` never publishes (`--publish never`);
no release token is available to the packaging steps — the publish job alone carries
`GITHUB_TOKEN` from `secrets.GITHUB_TOKEN`.

### Publish (tag pushes only; owner-authorized)

```bash
# publish job, after all three builds and verification
python -m keel.release publish --artifacts ../artifacts --tag "$RELEASE_TAG" --out release
python -m keel.release verify \
  --manifest release/download.json \
  --compare "https://github.com/${{ github.repository }}/releases/latest/download/download.json" \
  --retries 10 --retry-delay 6 --timeout 600 \
  --require-available
```

`download.json` is written last, then re-fetched and compared; a missing file or
checksum mismatch fails the job. Installers are GitHub Release assets only — **no
third-party storage** (the former Cloudflare R2 plan is obsolete). No release has
actually been published.

---

## 2. Verify artifacts

Final-source Windows rebuild (`master-plan-v6-release-acceptance-addendum.md`, commit
`7fd9a6a`) used:

```bash
cd keel
python -m keel.release build --platform windows --out release_final
python -m keel.release licenses --out release_final
python -c "from keel.release_integrity import regenerate_latest_yml; regenerate_latest_yml('dist','release_final')"
python -m keel.release integrity --dist dist --artifacts release_final
```

Observed result: `integrity: 7/7 passed` — checksums (7 files), manifest (0.1.1),
`latest.yml` size/sha512, sidecar version (0.1.1), dependency inventory (5 entries),
secret scan (no clear-text secrets), signature paths (Ed25519 helpers present;
production signing owner-gated).

Final-source artifact:

| Property | Value |
| --- | --- |
| File | `keel/dist/Keel-Setup-0.1.1.exe` |
| Size | 141,118,394 bytes |
| SHA-256 | `F12E1D668EF9983F291CC2302FCD4A938327CFCD1B4DEF5E5A9BAC7C76C14054` |
| Version | 0.1.1 (manifest + sidecar agree) |
| Signing | **unsigned** |

The earlier audited artifact (`CC455DE1…`, 141,052,399 bytes) is **not** the
final-source build and must not be represented as such. Integrity is build integrity
only: it is **not** a signature result and **not** a clean-VM install/upgrade result.

Optional signature verification (only meaningful after an owner provisions keys and
CI passes `--public-key`):

```bash
python -m keel.release verify --manifest release/download.json --public-key <PUBLIC_KEY_FILE>
```

Without a public key, verification checks size/SHA-256/format and makes **no**
signature claim.

---

## 3. Current signing state — exact secret names required (names only)

**No signing identity exists.** Evidence: GitHub Actions secrets `total_count=0`, no
local code-signing certificate/private key, no signing environment variables, and no
signing job in CI. `signing-readiness.yml` only *reports* whether secrets are present;
it never prints values or claims a package is signed. `build-desktop.yml` runs builds
with no `--signing-key` and verification with no `--public-key`. Unsigned packages
must not be published as production-signed releases.

Secret **names** (never values) to create, by source:

| Purpose | Secret name(s) | Source |
| --- | --- | --- |
| Windows Authenticode | `WINDOWS_SIGNING_CERTIFICATE_BASE64`, `WINDOWS_SIGNING_PASSWORD` | `signing-readiness.yml`, `docs/release/SIGNING-PREPARATION.md` |
| macOS Developer ID + notarization | `MACOS_SIGNING_CERTIFICATE_BASE64`, `MACOS_SIGNING_PASSWORD`, `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`, `MACOS_NOTARIZATION_PASSWORD` | same |
| Linux provenance/integrity | `LINUX_SIGNING_KEY_BASE64`, `LINUX_SIGNING_PASSWORD` (if a key is configured) | `docs/release/SIGNING-PREPARATION.md` |
| Ed25519 release/manifest signing (free path, recommended) | `KEEL_RELEASE_SIGNING_KEY`, `KEEL_RELEASE_SIGNING_PUBLIC_KEY` | `master-plan-v6-release-acceptance.md` |
| Optional electron-builder aliases cited in the same evidence | `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | `master-plan-v6-release-acceptance.md` (paid paths currently excluded by the master plan) |

Required CI change (owner-owned, **not performed**): add a `sign` job after the three
build jobs and before `publish`, fail fast when `KEEL_RELEASE_SIGNING_KEY` is absent,
upload `*.sig` and the signed `RELEASE-MANIFEST.json`, and make `publish` depend on
verification with the matching public key. Do not add a fallback that silently
generates a development keypair for release artifacts. No certificate was generated,
no secret value was read or printed, and nothing was signed or published.

---

## 4. Known platform limitations

| Area | Verified fact |
| --- | --- |
| Windows sandbox | Restricted primary token + workspace ACLs + handle list + Job Object, adversarially verified. **Network denial is now enforced** without elevation via AppContainer (`Keel.Sandbox.NetworkDeny.v1`), merged as commit `9a77dae`; evidence `master-plan-v6-win-network-evidence.md`. The older "network enforcement unavailable / fails closed" caveat is obsolete. `socket()` creation still succeeds — only traffic is blocked; per-process WFP rules require admin and are not used. |
| Linux native sandbox | Landlock FS + seccomp-BPF backend integrated with ABI/BPF fixes, but **not executed on this Windows host** — 16 platform-gated tests skipped. Requires a Linux runner (kernel ≥5.13). |
| macOS native sandbox | Seatbelt backend integrated (writes/network/rlimits); **not executed on this Windows host** — 14 platform-gated tests skipped. **Read isolation is BLOCKED on macOS 26** (`sandbox-exec` SIGABRT on path-filtered `file-read*`); never claimed as enforced. `sandbox-exec` is deprecated; no Electron entitlement is relied upon. |
| macOS/Linux installers | No native runners: final-source DMG/ZIP/AppImage/deb were **not built**. Historical 0.1.0 artifacts exist in old CI runs only. |
| Desktop shells | Shipping installers come from `desktop-app/` (Electron) via the Python release manager + PyInstaller. `desktop/` is an optional Tauri v2 spike, on hold pending a host reboot for VS Build Tools; it is not the shipping path. |
| Phone companion | Local pairing/TLS/approval/outbox implementation only — see §6. |

---

## 5. Provider credential setup (secret names only — never values)

No `KEEL_*` provider key is configured on this host; no live call was made. Configure
as masked CI secrets or in Keel's encrypted settings store, never in chat or git.
Verified command:

```powershell
KEEL_<PROVIDER>_API_KEY=... python -m pytest keel/tests/test_live_smoke.py -q
```

| Provider | Key (name only) | Model override | Notes |
| --- | --- | --- | --- |
| openrouter | `KEEL_OPENROUTER_API_KEY` | `KEEL_OPENROUTER_MODEL` | Default chain member; OpenAI-compatible adapter |
| nvidia | `KEEL_NVIDIA_API_KEY` | `KEEL_NVIDIA_MODEL` | Default chain member; OpenAI-compatible adapter |
| google | `KEEL_GOOGLE_API_KEY` | `KEEL_GOOGLE_MODEL` | Default chain member; native Gemini adapter |
| anthropic | `KEEL_ANTHROPIC_API_KEY` | `KEEL_ANTHROPIC_MODEL` | **Opt-in only**, never a default |
| openai-compatible | `KEEL_COMPAT_API_KEY` | `KEEL_COMPAT_BASE_URL`, `KEEL_COMPAT_MODEL` | Base URL and model required to be usable |

Useful local commands: `keel provider validate`, `keel provider smoke <name>`,
`keel secrets providers|has|get`. Diagnostics and capabilities are presence-only;
values are returned only by an explicit `resolve(reveal=True)` or `keel secrets get`.

---

## 6. Phone hardware requirement

B4.8 is **BLOCKED — external hardware**. No Android/iOS device or emulator exists in
this environment (`adb`, `fastboot`, `xcrun`, `idevice_id` absent; no ADB server, no
USB phone — the only USB device is an integrated camera). There is no phone-side
companion client in this repository.

To close B4.8, an owner must provide a physical device or emulator plus a phone-side
client that:

1. Scans/parses the `keel://pair?host=&port=&token=&pin=` URI.
2. Establishes TLS and verifies the certificate SHA-256 **equals the pinned `pin` before sending the token**.
3. Presents the pairing token and obtains a pending approval record.
4. Demonstrates an authenticated control round-trip from the phone (not just `approvals.json` mutation).
5. Demonstrates that `revoke()` terminates that access.

QR rendering, payload generation, self-signed certificate generation and writing
`approvals.json` are **not** proof of real pairing. Relevant capabilities:
`core.companion.identity`, `release.pairing|pair|revoke`, `cowork.channel.deliver`.

---

## 7. Clean-VM validation commands (`keel/scripts/validate_desktop.py`)

Local, non-destructive checks:

```bash
cd keel
python scripts/validate_desktop.py --dist dist
# observed: {"pass": 5, "fail": 0, "external_unverified": 6}
```

The 5 local PASS checks are: `installer_present`, `electron_resources`,
`sidecar_starts`, `artifact_scan`, `update_manifest`. The installer name is derived
from the version (`Keel-Setup-0.1.1.exe`), not hard-coded.

The 6 external checks are deliberately reported **UNVERIFIED** with these exact
commands, to run on a disposable VM (never on the build machine):

1. `installer_install` — `<installer path> /S /D=%LOCALAPPDATA%\KeelValidation`
2. `desktop_startup_after_install` — `%LOCALAPPDATA%\KeelValidation\Keel.exe`
3. `backend_startup_shutdown` — observe the bundled `keel.exe serve` process on app exit
4. `uninstall` — run the uninstaller in `%LOCALAPPDATA%\KeelValidation`
5. `upgrade_and_rollback` — install 0.1.0 then 0.1.1; force 3 failed starts; verify rollback
6. `signed_launch` — owner gate; requires signing credentials (not performed)

Additional native-runner commands before any release decision:

```bash
# Linux runner
python -m pytest -q keel/tests/test_sandbox_linux.py keel/tests/sandbox_conformance.py
# macOS runner (arm64 and Intel)
python -m pytest -q keel/tests/test_sandbox_macos.py
```

---

## 8. Owner gates (all blocking; none discharged by this runbook)

| Gate | Required owner action | Status |
| --- | --- | --- |
| Plan upgrade / forge (C11.2) | Choose a plan supporting private branch protection, accept local compensating controls (`.githooks/pre-push`) as a documented exception, or move forge. Free private plan returns 403 and `protected: false`. | BLOCKED |
| 2FA | Enable on the owner account at GitHub security settings. Not exposed by the available API; only the owner can verify it. | UNVERIFIED / owner account |
| Signing identity | Create `KEEL_RELEASE_SIGNING_KEY` / `KEEL_RELEASE_SIGNING_PUBLIC_KEY` and/or platform certificate secrets; add the CI sign job with a missing-secret hard failure; decide on paid certificates/notarization. | BLOCKED |
| Push authorization | Authorize pushing/merging the local completion branch and publishing a release. SHA pinning is genuine only on that unpushed branch; live `main` is still tag-pinned. | BLOCKED |

No push, release publication, deployment, visibility change, history rewrite,
credential rotation or production signing has occurred. This document contains
secret **names only**; it contains no credential values.
