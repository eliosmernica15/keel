# Master Plan v6 — release acceptance readouts (phone companion + signing)

**Baseline:** `20bf5c3` (`C11.1 private + C11.2 local compensating controls and live evidence`)
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\completion\phone-signing` (branch `agent/phone-signing`)
**Date:** 2026-11-23
**Scope:** read-only inspection of the authorized environment plus this evidence file. No device was modified, nothing was signed or published, no secrets were printed, and no push was performed.

---

## Phone companion

### Local implementation (honest description)

| File | What it actually does | What it does NOT do |
| --- | --- | --- |
| `keel/src/keel/pairing.py` | `PairingStore` persists an explicit allowlist in `pairings.json`. `pair()` creates a random 16-hex `client_id`, label, `scope` (`lan`/`headless`), UTC `paired_at`, `revoked=False`. `is_paired()`, `list_clients()`, `revoke()` are local JSON operations. Module docstring states the bridge token remains the primary credential. | No QR, no TLS, no network handshake, no phone discovery, no remote approval transport. |
| `keel/src/keel/platform_gaps.py` (`companion_identity`, B4.8) | Generates a local self-signed RSA-2048 cert/key (`companion/cert.pem`, `key.pem`, key chmod 0600), SAN `localhost`/`127.0.0.1`, 365-day validity; writes a `pairing-token.txt`; `pin` = SHA-256 of the DER certificate; payload is `keel://pair?host=127.0.0.1&port=9284&token=<token>&pin=<pin>` (host/port configurable). Optional OpenCV renders a QR matrix; otherwise the URI is still complete. Returns `network: loopback by default`, `lan_opt_in_required: True`, note: "Phone reachability is external; no cloud service used." | No listener is started, no TLS session is established, the PIN is never verified by a peer, and no phone client exists in this repository. The private key is written unencrypted (protected only by file mode). |
| `keel/src/keel/platform_gaps.py` (`CompanionApprovals`) | `pending(device, pin)` writes an `approvals.json` record (`approved: False`, random 12-hex id); `approve(id)` flips it to `True` with a timestamp. | No binding between the approval and a real device, token, TLS connection, or network request. `pending()` accepts any caller-supplied `pin` string without checking it. |
| `keel/src/keel/channel_ops.py` | `deliver_with_fallback()` evaluates a chain in-process. `deliver_to_outbox()` durably appends a JSONL record with `ts`, channel, destination, message, `status: queued_local` to `outbox.jsonl`. `SubscriptionStore` stores webhook subscriptions with a locally rotatable secret. Docstring explicitly says external SMTP/webhook are separate opt-in adapters and "this function never claims to have sent anything online." | No SMTP, webhook, APNs, or phone push is performed. "Delivered" means written to the local outbox only. |
| `keel/src/keel/capability_registry.py` | Exposes `core.companion.identity` (read), `release.pairing` / `release.pair` / `release.revoke` (allowlist), and `cowork.channel.deliver`. The last one returns `delivered: any(a["ok"] ...)` plus the note "written to local outbox; external delivery requires an opt-in channel adapter". | The capability layer does not add a phone-side verifier or a real transport. |

Only two `keel://pair` references exist in the whole repository — the producer in `platform_gaps.py:64` and a prefix assertion in `test_gap_closure.py:105`. There is no companion phone app/client source in this worktree.

**Test command and observed result** (source pinned to the worktree; the globally installed editable package points at `C:\Users\Admin\Desktop\Claude clone\keel\src\keel`, so `PYTHONPATH` was set explicitly):

```powershell
cd "C:\Users\Admin\.local\share\opencode\worktree\completion\phone-signing\keel"
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -c "import keel; print(keel.__file__)"
# C:\Users\Admin\.local\share\opencode\worktree\completion\phone-signing\keel\src\keel\__init__.py

python -m pytest -q tests/test_pairing.py tests/test_channel_ops.py `
  tests/test_release_signing.py tests/test_release_no_secrets.py `
  tests/test_gap_closure.py::test_b48_companion_identity_and_approvals
# 15 passed in 6.74s
```

`test_gap_closure.py::test_b48_companion_identity_and_approvals` asserts only that the payload starts with `keel://pair?`, the PIN is 64 hex chars, LAN opt-in is required, and `pending()/approve()` flip a JSON flag. That is a local-format test, not a pairing test.

### Device / emulator availability (read-only checks)

**Device found: NO.** Evidence — exact commands and observations:

```powershell
Get-Command adb, fastboot, xcrun, idevice_id
# ADB_NOT_FOUND, FASTBOOT_NOT_FOUND, XCRUN_NOT_FOUND, IDEVICE_NOT_FOUND
# Therefore `adb devices`, `xcrun simctl list devices` and `idevice_id -l`
# were NOT executed: the binaries do not exist in this environment.

Get-PnpDevice -PresentOnly | Where-Object {
  $_.FriendlyName -match 'Android|iPhone|iPad|iPod|ADB|Apple Mobile' -or
  $_.InstanceId -match 'ADB|ANDROID|APPLE'
} | Select-Object Status, Class, FriendlyName
# OK  USB  "USB Composite Device"   USB\VID_04F2&PID_B725\0001

Get-PnpDevice -Class Camera,Image -PresentOnly | Select-Object Class, FriendlyName, InstanceId
# Camera  "Integrated Camera"  USB\VID_04F2&PID_B725&MI_00\...
# Get-PnpDeviceProperty DEVPKEY_Device_Service -> usbccgp (composite parent)
# => VID_04F2 is the integrated camera, NOT a phone.

Get-PnpDevice -Class Android -PresentOnly          # no devices
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'Android|iPhone|iPad|iPod|ADB|Apple Mobile' }
# no devices

Get-NetTCPConnection -LocalPort 5037 -State Listen  # NO_LISTENER_5037 (no ADB server)
Get-Process | Where-Object { $_.ProcessName -match 'adb|emulator|android|iphone|itunes|qemu|vbox' }
# no processes

Get-AppxPackage | Where-Object { $_.Name -match 'Android|Subsystem|Emulator' }
# only MicrosoftCorporationII.WindowsSubsystemForLinux (WSL), no WSA
```

Path probes (all MISSING unless noted): `%LOCALAPPDATA%\Android\Sdk`, `$env:ANDROID_HOME`, `$env:ANDROID_SDK_ROOT`, `C:\Program Files (x86)\Android\android-sdk`, `C:\Program Files\Android\android-sdk`, `%LOCALAPPDATA%\Microsoft\AndroidEmulator`, Android Studio install locations, BlueStacks/Nox/Genymotion/QEMU directories, `C:\Program Files\iPhone`. `C:\Program Files\Oracle\VirtualBox` exists but `VBoxManage` is not installed/on PATH. `C:\Users\Admin\.android` contains only `adbkey` and `adbkey.pub` — a *host* ADB key, not a connected device.

### Validation outcome and exact hardware requirement

No physical device, emulator, or ADB device exists, so **no real pairing or approval validation was performed**. The only observable evidence is local generation and JSON state manipulation.

To close B4.8 externally, an owner must provide an Android/iOS **physical device or emulator** reachable from the companion host, plus a phone-side companion client that:

1. Scans/parses the `keel://pair?host=&port=&token=&pin=` URI.
2. Establishes TLS to the host and verifies the certificate SHA-256 **equals the pinned `pin` before sending the token**.
3. Presents the pairing token and obtains a pending approval record.
4. Demonstrates an authenticated control round-trip from the phone (not just `approvals.json` mutation).
5. Demonstrates that `revoke()` terminates that access.

**Explicit limitation:** QR rendering, payload generation, self-signed certificate generation, and writing `approvals.json` are **NOT proof of real pairing**. No such claim is made here. Source/docs classification already marks B4.8 `external_validation_pending` (`master-plan-v6-final-report.md:33,79`; `Keel_Master_Plan_v6.md:140`).

---

## Signing readiness

### Local implementation and CI (honest description)

- `keel/src/keel/release/signing.py`: Ed25519 sign/verify over canonical JSON; `generate_keypair()` is explicitly labelled "ephemeral/development keypair. Never use for production." Header states production keys are owner-controlled and never generated here.
- `keel/src/keel/release/cli.py`: optional `--signing-key` (build) and `--public-key` (verify / update-check / dry-run).
- `keel/src/keel/release/build.py:140-150`: signs each artifact (`.sig`) and embeds a detached manifest signature **only if** `--signing-key` is supplied.
- `keel/src/keel/release/verify.py:231-238,259-269`: detached signatures are downloaded/checked **only if** `--public-key` is supplied; otherwise only size/SHA-256/format checks run.
- `keel/src/keel/release/common.py:27-40` and `publish.py:49`: release notes explicitly say **Unsigned** for Windows (SmartScreen), macOS (Gatekeeper) and Linux. `keel/docs/HOSTING.md:115`: "Claim the installers are signed or notarized. They are not."
- CI workflows present: `.github/workflows/build-desktop.yml`, `python-tests.yml`, `verify-install.yml`, `secret-scan.yml`. **There is no signing job, signing step, or code-signing tool invocation in any of them.** `build-desktop.yml` runs `python -m keel.release build --platform <os> --out release` with no `--signing-key`; `verify` runs with no `--public-key`.
- The only secret references in CI are the built-in `secrets.GITHUB_TOKEN` used for publishing/downloading release assets (`build-desktop.yml:146`, `verify-install.yml:34,92,114`). That is not a signing identity.

### Signing identity check (names only; no values printed)

```powershell
gh api repos/eliosmernica15/keel/actions/secrets --jq '.secrets[].name'
# exit 0, no output
gh api repos/eliosmernica15/keel/actions/secrets
# "total_count": 0  -> zero repository Actions secrets configured
```

Local environment variable **names only** matching `KEY|SECRET|SIGN|CERT|CSC|APPLE|TOKEN|PASS`: `B4M_API_KEY`, `B4M_PROXY_TOKEN`. Neither is a Keel signing identity.

Windows certificate stores, **names only** (`Cert:\CurrentUser\My`, 7 entries): `CrossDevice`, `ASP.NET Core HTTPS development certificate`, `APNS certificate`, `Microsoft Your Phone`, `CrossDevice` (trust), `Microsoft Your Phone` (trust), `APNS certificate Direct`. None has a Code Signing EKU or a Keel subject; both APNS entries report `HasPrivateKey=False`. `Cert:\LocalMachine\My` contains zero code-signing certificates. No `.pem/.p12/.pfx/.key/.asc/.sig` files exist in the repository outside vendored resource/config paths, and no `~/.keel` state directory exists.

**Signing identity found: NO** — no GitHub Actions secret, no local code-signing certificate/private key, and no environment variable indicating one.

### Exact secret names and owner setup required

No such names are currently defined; these are the **names to create**, mapped to the existing CLI contract:

| Purpose | Secret name to create | How it is consumed | Owner action |
| --- | --- | --- | --- |
| Ed25519 artifact + manifest signing (free path, recommended) | `KEEL_RELEASE_SIGNING_KEY` | New CI sign step writes the PEM to a 0600 temp file and passes `python -m keel.release build ... --signing-key <tempfile>`; file deleted in `always()` | Generate an Ed25519 PKCS#8 private key **outside** the repository with `openssl genpkeypair`-equivalent tooling (e.g. `cryptography`), store as an Actions secret; never commit it. |
| Matching verification/public key | `KEEL_RELEASE_SIGNING_PUBLIC_KEY` | New CI verify step passes `--public-key`; also publish the public PEM as a release asset for clients (a public key is not sensitive and may be committed) | Store the matching public PEM; distribute it to verifiers. |
| Windows Authenticode (optional, paid — currently excluded by master plan D3 / `Keel_Master_Plan_v6.md:425`) | `CSC_LINK`, `CSC_KEY_PASSWORD` | electron-builder code signing | Owner must purchase/obtain an OV/EV code-signing certificate; do not fabricate a PFX. |
| macOS Developer ID + notarization (optional, paid — excluded by `Keel_Master_Plan_v6.md:426`) | `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`, plus `CSC_LINK`/`CSC_KEY_PASSWORD` | electron-builder + `@electron/notarize` | Owner must enroll in the paid Apple Developer Program. |

Required workflow change (owner/CI owner, **not performed here**): add a `sign` job after the three build jobs and before `publish`; fail fast when `KEEL_RELEASE_SIGNING_KEY` is absent; upload `*.sig` and the signed `RELEASE-MANIFEST.json`; make `publish` depend on a verification step that supplies `KEEL_RELEASE_SIGNING_PUBLIC_KEY`. Do not add a fallback that silently generates a development keypair for release artifacts.

### Fail-safe verification observed

```powershell
cd "C:\Users\Admin\.local\share\opencode\worktree\completion\phone-signing"
git grep -n -E -- '--signing-key|--public-key|secrets\.' .github
# only secrets.GITHUB_TOKEN lines; NO --signing-key / --public-key in CI

cd keel
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -c "from keel.release import common; m=common.build_release_manifest({}, '0.1.1','v0.1.1','https://example.invalid/releases/download'); print('HAS_SIGNATURE=' + str('signature' in m)); print(','.join(sorted(m.keys())))"
# HAS_SIGNATURE=False
# blocked_versions,checksums_file,edition,files,generated,min_version,name,published_at,rollout,security_advisories,tag,version

python -m keel.release verify --manifest <temp manifest '{"channels":{},"version":"0.1.1"}'>
# OK - verified 0 available channel(s)   (exit 0; no signature claim)
```

**Honest conclusion on "fails safely":** with no signing secret present, the current workflow does **not hard-fail** — there is no signing gate to fail. What *is* safe today is that no signature is fabricated, no `--public-key` is passed, unsigned artifacts are labelled "Unsigned", and verification without a key makes no signature claim. To make absence of the signing identity a genuine build failure, the `sign` job and its fail-fast check above must be added by the owner. No certificate was generated, no secret value was read or printed, no workflow was dispatched, and nothing was signed or published.

---

## Blockers / owner actions (summary)

| # | Blocker | Owner action | Status |
| --- | --- | --- | --- |
| 1 | No Android/iOS device or emulator; no ADB/Xcode tooling in the authorized environment. | Provide a real device/emulator and a phone-side companion client; run the 5-step pairing/approval/revocation protocol above. | BLOCKED — external hardware |
| 2 | No GitHub Actions secrets (`total_count=0`), no local code-signing identity. | Create `KEEL_RELEASE_SIGNING_KEY` and `KEEL_RELEASE_SIGNING_PUBLIC_KEY`; optionally obtain paid platform certificates and add the four/five names listed above. | BLOCKED — owner credential |
| 3 | CI has no signing job or fail-fast check. | Add the `sign` job, `--signing-key`/`--public-key` plumbing, and a hard failure when the secret is missing, before enabling any signed release. | BLOCKED — owner/CI change |
| 4 | Master plan excludes paid macOS notarization / free Windows OSS-only signing on cost grounds (`Keel_Master_Plan_v6.md:419,425-426`). | Owner decision: accept unsigned releases with documented first-run steps, or approve paid certificates. | BLOCKED — owner decision |

No push, publish, or signing operation was performed. This file is the only change in this worktree.
